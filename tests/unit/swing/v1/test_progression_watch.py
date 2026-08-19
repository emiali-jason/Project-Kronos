from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_readiness import (
    LevelAvailability,
    NextConditionEvidence,
    NextConditionState,
    ThesisIntact,
)
from kronos.swing.v1.progression_watch import (
    GovernedCompletedBar,
    ProgressionComparator,
    ProgressionRequirement,
    ProgressionRequirementState,
    ProgressionWatchState,
    ProgressionWatchStore,
    activate_watch,
    deactivate_watch,
    derive_progression_requirements,
    hide_watch,
    mark_watch_stale,
    observe_completed_bar,
    reactivate_watch,
    tradingview_instruction,
)


NOW = datetime(2026, 8, 19, 8, 0, tzinfo=UTC)
RUN = "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"


def _watchable_requirement() -> ProgressionRequirement:
    return ProgressionRequirement(
        "1" * 64, "SWING", "RELIANCE", V1Direction.LONG, RUN, "2" * 64,
        "WAIT_PULLBACK_DEVELOPING", "ONE_HOUR_PROGRESSION",
        "1H close above 1482.5", ProgressionRequirementState.WATCH_AVAILABLE,
        FactualTimeframe.ONE_HOUR, ProgressionComparator.BAR_CLOSE_ABOVE,
        1482.5, None, None, ("3" * 64,), NOW, ("KITE_NORMALIZED_HISTORICAL",),
    )


def _bar(close: float, *, boundary: datetime | None = None) -> GovernedCompletedBar:
    return GovernedCompletedBar(
        "RELIANCE", FactualTimeframe.ONE_HOUR, close,
        boundary or NOW + timedelta(hours=1), "KITE_NORMALIZED_HISTORICAL",
        "KRONOS-MARKET-CALENDAR-V1-NSE", "2026.1.2", "NSE-CM-REGULAR",
        ("DOMAIN-008",),
    )


def test_missing_observational_levels_are_evidence_required_and_never_fabricated() -> None:
    values = derive_progression_requirements(
        canonical_instrument="RELIANCE", direction=V1Direction.LONG,
        native_run_identity=RUN, native_assessment_sha256="2" * 64,
        source_analytical_state="CONTEXT_INCOMPLETE", observation_boundary=NOW,
        provenance=("FROZEN_NATIVE_STATE",), readiness=None,
        missing_evidence=("CPR", "1H PDH/PDL", "Confluence Zone"),
    )
    by_summary = {item.summary: item for item in values}
    for name in ("CPR", "1H PDH/PDL", "Confluence Zone"):
        item = by_summary[f"{name} must be established"]
        assert item.state is ProgressionRequirementState.EVIDENCE_REQUIRED
        assert (item.price, item.zone_low, item.zone_high, item.comparator) == (None, None, None, None)
        with pytest.raises(ValueError, match="ACTIVATION_NOT_PERMITTED"):
            activate_watch(item, activated_at=NOW)


def test_existing_generic_pullback_review_is_not_recast_as_price_alert() -> None:
    next_condition = NextConditionEvidence(
        FactualTimeframe.FOUR_HOUR, "PULLBACK_REVIEW",
        "REVIEW_FOR_RENEWED_PROGRESSION", "OPERATIVE_ANCHOR",
        LevelAvailability.AVAILABLE, 1482.5, None, None, ("2" * 64,), NOW,
    )
    readiness = SimpleNamespace(
        conditions=SimpleNamespace(
            thesis_intact=ThesisIntact.YES,
            next_condition_state=NextConditionState.AVAILABLE,
            next_condition=next_condition,
        ), result_sha256="4" * 64,
    )
    values = derive_progression_requirements(
        canonical_instrument="RELIANCE", direction=V1Direction.LONG,
        native_run_identity=RUN, native_assessment_sha256="2" * 64,
        source_analytical_state="WAIT_PULLBACK_DEVELOPING",
        observation_boundary=NOW, provenance=("KITE",),
        readiness=readiness,
    )
    next_item = next(item for item in values if item.condition_identity == "PULLBACK_REVIEW")
    assert next_item.state is ProgressionRequirementState.NOT_WATCHABLE
    assert next_item.comparator is None


def test_approved_exact_bar_close_condition_becomes_watch_available() -> None:
    next_condition = NextConditionEvidence(
        FactualTimeframe.ONE_HOUR, "ONE_HOUR_PROGRESSION",
        "COMPLETED_ONE_HOUR_CLOSE_ABOVE", "STRUCTURAL_THRESHOLD",
        LevelAvailability.AVAILABLE, 1482.5, None, None,
        ("2" * 64,), NOW,
    )
    readiness = SimpleNamespace(
        conditions=SimpleNamespace(
            thesis_intact=ThesisIntact.YES,
            next_condition_state=NextConditionState.AVAILABLE,
            next_condition=next_condition,
        ), result_sha256="4" * 64,
    )
    values = derive_progression_requirements(
        canonical_instrument="RELIANCE", direction=V1Direction.LONG,
        native_run_identity=RUN, native_assessment_sha256="2" * 64,
        source_analytical_state="WAIT_PULLBACK_DEVELOPING",
        observation_boundary=NOW, provenance=("KITE",),
        readiness=readiness,
    )
    item = next(value for value in values if value.condition_identity == "ONE_HOUR_PROGRESSION")
    assert item.state is ProgressionRequirementState.WATCH_AVAILABLE
    assert item.price == 1482.5
    assert item.comparator is ProgressionComparator.BAR_CLOSE_ABOVE


def test_tick_has_no_authority_and_only_later_completed_bar_triggers_once() -> None:
    watch = activate_watch(_watchable_requirement(), activated_at=NOW)
    assert observe_completed_bar(watch, _bar(1500.0, boundary=NOW)) == watch
    assert observe_completed_bar(watch, _bar(1482.5)).state is ProgressionWatchState.ACTIVE
    assert observe_completed_bar(watch, _bar(1400.0)).state is ProgressionWatchState.ACTIVE
    triggered = observe_completed_bar(watch, _bar(1500.0))
    assert triggered.state is ProgressionWatchState.TRIGGERED
    assert triggered.consequence == "REASSESSMENT_REQUIRED"
    assert observe_completed_bar(triggered, _bar(1600.0)) == triggered


def test_watch_persistence_restart_and_stale_state_are_fail_closed(tmp_path: Path) -> None:
    store = ProgressionWatchStore(tmp_path)
    watch = activate_watch(_watchable_requirement(), activated_at=NOW)
    store.retain(watch)
    assert store.load() == (watch,)
    triggered = observe_completed_bar(watch, _bar(1500.0))
    store.retain(triggered)
    assert store.load() == (triggered,)
    assert len(tuple((tmp_path / "events").glob("*.json"))) == 2
    with pytest.raises(ValueError, match="TRANSITION_INVALID"):
        store.retain(watch)
    assert mark_watch_stale(watch).state is ProgressionWatchState.STALE


def test_deactivate_reactivate_delete_preserve_one_identity_and_immutable_history(tmp_path: Path) -> None:
    store = ProgressionWatchStore(tmp_path)
    active = activate_watch(_watchable_requirement(), activated_at=NOW)
    store.retain(active)
    inactive = deactivate_watch(active, occurred_at=NOW + timedelta(minutes=1))
    store.retain(inactive)
    assert inactive.state is ProgressionWatchState.INACTIVE
    assert deactivate_watch(inactive, occurred_at=NOW + timedelta(minutes=2)) == inactive
    reactivated = reactivate_watch(inactive, occurred_at=NOW + timedelta(minutes=3))
    store.retain(reactivated)
    assert reactivated.watch_id == active.watch_id
    assert reactivated.state is ProgressionWatchState.ACTIVE
    hidden = hide_watch(reactivated, occurred_at=NOW + timedelta(minutes=4))
    store.retain(hidden)
    assert hidden.workspace_hidden is True
    assert hidden.state is ProgressionWatchState.INACTIVE
    assert hide_watch(hidden, occurred_at=NOW + timedelta(minutes=5)) == hidden
    assert store.load() == (hidden,)
    assert [event.event_type.value for event in hidden.history] == [
        "ACTIVATED", "DEACTIVATED", "REACTIVATED", "DELETED",
    ]
    assert len(tuple((tmp_path / "events").glob("*.json"))) == 4


def test_stale_or_hidden_watch_cannot_be_reactivated() -> None:
    active = activate_watch(_watchable_requirement(), activated_at=NOW)
    stale = mark_watch_stale(active, occurred_at=NOW + timedelta(minutes=1))
    with pytest.raises(ValueError, match="REACTIVATION_NOT_PERMITTED"):
        reactivate_watch(stale, occurred_at=NOW + timedelta(minutes=2))
    hidden = hide_watch(
        deactivate_watch(active, occurred_at=NOW + timedelta(minutes=1)),
        occurred_at=NOW + timedelta(minutes=2),
    )
    with pytest.raises(ValueError, match="REACTIVATION_NOT_PERMITTED"):
        reactivate_watch(hidden, occurred_at=NOW + timedelta(minutes=3))


def test_tradingview_instruction_is_exact_and_non_trading() -> None:
    fields = dict(tradingview_instruction(_watchable_requirement()))
    assert fields == {
        "Instrument": "RELIANCE", "Timeframe": "1H",
        "Condition": "Bar close crosses above 1482.5",
        "Purpose": "KRONOS progression watch",
    }
    assert not {"BUY", "SELL", "ENTRY"}.intersection(" ".join(fields.values()).upper().split())


def test_arbitrary_free_form_price_cannot_construct_requirement() -> None:
    with pytest.raises(ValueError, match="PROGRESSION_REQUIREMENT_INVALID"):
        replace(
            _watchable_requirement(), state=ProgressionRequirementState.EVIDENCE_REQUIRED,
            comparator=ProgressionComparator.BAR_CLOSE_ABOVE,
        )
