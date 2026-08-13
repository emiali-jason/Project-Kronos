from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from kronos.application.swing_v1_review import (
    Step31EligibilityHandoff,
    Step31EligibleInstrument,
)
from kronos.swing.v1.layer2 import ReadinessState
from kronos.swing.v1.models import V1Direction, V1Setup
from kronos.swing.v1.trade_construction import (
    DOMAIN_007_HANDOFF_ID,
    MaterialBarrier,
    MaterialBarrierStatus,
    LocalTradeCandidateStore,
    PreEntryObservation,
    TradeCandidateEntryState,
    TradeCandidateIntegrity,
    TradeCandidateStaleness,
    TradeConstructionExecutionContext,
    TradeConstructionInput,
    TradeConstructionStatus,
    TradeViabilityStatus,
    audit_reconstructs,
    assess_pre_entry,
    construct_all_trade_candidates,
    construct_trade_candidate,
    domain_007_handoff,
)


_BOUNDARY = datetime.fromisoformat("2026-08-12T00:00:00+05:30")
_NOW = datetime.fromisoformat("2026-08-13T10:00:00+05:30")
_RUN = "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"
_LAYER1 = "SWING-V1-LAYER1@2026-08-12T00:00:00+05:30"
_HASH = "a" * 64
_READINESS = "SWING-V1-READINESS-ASSESSMENT-POLICY"


def _identity(instrument: str, setup: V1Setup, direction: V1Direction) -> str:
    return "|".join((instrument, setup.value, direction.value, _BOUNDARY.isoformat()))


def _handoff(
    instrument: str = "RELIANCE",
    setup: V1Setup = V1Setup.PULLBACK_CONTINUATION,
    direction: V1Direction = V1Direction.LONG,
    *,
    extra: tuple[tuple[V1Setup, V1Direction], ...] = (),
) -> tuple[Step31EligibilityHandoff, Step31EligibleInstrument]:
    identities = (_identity(instrument, setup, direction),) + tuple(
        _identity(instrument, child_setup, child_direction)
        for child_setup, child_direction in extra
    )
    eligible = Step31EligibleInstrument(
        canonical_instrument=instrument,
        layer1_run_identity=_LAYER1,
        swing_analysis_run_identity=_RUN,
        observation_boundary=_BOUNDARY,
        probable_assessment_identities=identities,
        source_image_sha256=_HASH,
        readiness_state=ReadinessState.READY_FOR_TRADE_CONSTRUCTION,
        readiness_policy_identity=_READINESS,
        readiness_reason="READY_CONTEXT",
    )
    return Step31EligibilityHandoff(_RUN, _LAYER1, (eligible,)), eligible


def _context(
    instrument: str = "RELIANCE",
    *,
    product: str = "NSE_CASH_EQUITY",
    tick: str = "0.05",
    precision: int = 2,
) -> TradeConstructionExecutionContext:
    return TradeConstructionExecutionContext(
        identity=f"EXECUTION-CONTEXT-{instrument}-20260812",
        canonical_instrument=instrument,
        product=product,
        tick_size=Decimal(tick),
        price_precision=precision,
        session_calendar_identity="NSE-TRADING-CALENDAR",
        market_available=True,
    )


def _input(
    setup: V1Setup = V1Setup.PULLBACK_CONTINUATION,
    direction: V1Direction = V1Direction.LONG,
    *,
    instrument: str = "RELIANCE",
    handoff: Step31EligibilityHandoff | None = None,
    eligible: Step31EligibleInstrument | None = None,
    context: TradeConstructionExecutionContext | None | object = ...,
    **changes: object,
) -> TradeConstructionInput:
    if handoff is None or eligible is None:
        handoff, eligible = _handoff(instrument, setup, direction)
    actual_context = _context(instrument) if context is ... else context
    values: dict[str, object] = {
        "handoff": handoff,
        "eligibility": eligible,
        "layer1_assessment_identity": _identity(instrument, setup, direction),
        "setup_family": setup,
        "direction": direction,
        "layer2_state_identity": "SHADOW_COMPLETE",
        "readiness_identity": _READINESS,
        "qualification_observation_boundary": _BOUNDARY,
        "active_chart_revision_identity": _HASH,
        "qualification_high": Decimal("100.02"),
        "qualification_low": Decimal("96.03"),
        "pullback_structural_low": Decimal("94.03"),
        "pullback_structural_high": Decimal("105.02"),
        "prior_directional_swing_high": Decimal("112.02"),
        "prior_directional_swing_low": Decimal("88.03"),
        "original_range_high": Decimal("100.02"),
        "original_range_low": Decimal("90.03"),
        "clear_air_identity": "CLEAR-AIR-REVIEW-1",
        "material_barriers": (),
        "execution_context": actual_context,
        "source_evidence_identities": ("LAYER1-EVIDENCE", "LAYER2-EVIDENCE"),
        "market_data_boundary": _BOUNDARY,
    }
    values.update(changes)
    return TradeConstructionInput(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("setup", "direction", "entry", "stop", "target", "invalidation"),
    (
        (V1Setup.PULLBACK_CONTINUATION, V1Direction.LONG, "100.05", "94.00", "112.00", "94.03"),
        (V1Setup.PULLBACK_CONTINUATION, V1Direction.SHORT, "96.00", "105.05", "88.05", "105.02"),
        (V1Setup.CONSOLIDATION_BREAKOUT, V1Direction.LONG, "100.05", "96.00", "110.00", "100.02"),
        (V1Setup.CONSOLIDATION_BREAKOUT, V1Direction.SHORT, "96.00", "100.05", "80.05", "90.03"),
    ),
)
def test_supported_geometry_and_directional_tick_rounding(
    setup: V1Setup,
    direction: V1Direction,
    entry: str,
    stop: str,
    target: str,
    invalidation: str,
) -> None:
    candidate = construct_trade_candidate(_input(setup, direction), clock=_NOW)

    assert candidate.construction_status is TradeConstructionStatus.COMPLETE
    assert candidate.viability_status is TradeViabilityStatus.VIABLE
    assert candidate.entry_price == Decimal(entry)
    assert candidate.stop_price == Decimal(stop)
    assert candidate.target_price == Decimal(target)
    assert candidate.invalidation_level_or_reference == Decimal(invalidation)
    assert candidate.stop_price != candidate.invalidation_level_or_reference
    assert candidate.entry_state is TradeCandidateEntryState.WAITING
    assert candidate.integrity_status is TradeCandidateIntegrity.VALID


def test_exact_risk_reward_and_ratio_use_final_rounded_prices() -> None:
    candidate = construct_trade_candidate(_input(), clock=_NOW)
    assert candidate.risk_per_unit == Decimal("6.05")
    assert candidate.reward_per_unit == Decimal("11.95")
    assert candidate.risk_reward_ratio == Decimal("11.95") / Decimal("6.05")


def test_material_barrier_truncates_to_nearest_positive_rounded_target() -> None:
    item = _input(material_barriers=(
        MaterialBarrier("BARRIER-FAR", Decimal("109.02")),
        MaterialBarrier("BARRIER-NEAR", Decimal("106.03")),
    ))
    candidate = construct_trade_candidate(item, clock=_NOW)
    assert candidate.target_price == Decimal("106.00")
    assert candidate.material_barrier_status is MaterialBarrierStatus.TARGET_TRUNCATED
    assert candidate.barrier_references == ("BARRIER-FAR", "BARRIER-NEAR")


def test_material_barrier_that_rounds_to_entry_fails_closed() -> None:
    context = _context(tick="1", precision=0)
    item = _input(
        context=context,
        qualification_high=Decimal("100"),
        material_barriers=(MaterialBarrier("BARRIER", Decimal("100.2")),),
    )
    candidate = construct_trade_candidate(item, clock=_NOW)
    assert candidate.construction_status is TradeConstructionStatus.INCOMPLETE
    assert candidate.viability_status is TradeViabilityStatus.NOT_VIABLE
    assert candidate.material_barrier_status is MaterialBarrierStatus.DESTROYS_POSITIVE_REWARD


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"direction": V1Direction.NONE}, "DIRECTION_INVALID"),
        ({"setup_family": "COMBINED"}, "SETUP_UNSUPPORTED_OR_AMBIGUOUS"),
        ({"qualification_high": None}, "ENTRY_MISSING"),
        ({"pullback_structural_low": None}, "STOP_OR_STRUCTURAL_EVIDENCE_MISSING"),
        ({"prior_directional_swing_high": None}, "TARGET_MISSING"),
        ({"pullback_structural_low": Decimal("101")}, "STOP_WRONG_SIDE_OR_RISK_NON_POSITIVE"),
        ({"prior_directional_swing_high": Decimal("99")}, "TARGET_WRONG_SIDE_OR_REWARD_NON_POSITIVE"),
        ({"execution_context": None}, "EXECUTION_CONTEXT_MISSING"),
        ({"layer2_state_identity": "CONTEXT_INCOMPLETE"}, "LAYER2_STATE_INVALID"),
        ({"active_chart_revision_identity": "b" * 64}, "ACTIVE_CHART_REVISION_MISMATCH"),
        ({"market_data_boundary": datetime.fromisoformat("2026-08-11T00:00:00+05:30")}, "COMPLETED_DAILY_BOUNDARY_INVALID"),
        ({"qualification_candle_completed": False}, "COMPLETED_DAILY_BOUNDARY_INVALID"),
    ),
)
def test_invalid_or_stale_inputs_fail_closed(
    changes: dict[str, object], reason: str
) -> None:
    candidate = construct_trade_candidate(_input(**changes), clock=_NOW)
    assert candidate.construction_status is TradeConstructionStatus.INCOMPLETE
    assert candidate.viability_status is TradeViabilityStatus.NOT_VIABLE
    assert candidate.integrity_status is TradeCandidateIntegrity.INVALID
    assert candidate.integrity_reason == reason
    with pytest.raises(ValueError, match="DOMAIN_007_HANDOFF_INELIGIBLE"):
        domain_007_handoff(candidate)


def test_wrong_run_and_eligibility_binding_fail_closed() -> None:
    handoff, eligible = _handoff()
    other_eligible = replace(eligible, canonical_instrument="OTHER")
    other_handoff = Step31EligibilityHandoff(_RUN, _LAYER1, (other_eligible,))
    candidate = construct_trade_candidate(
        _input(handoff=other_handoff, eligible=eligible), clock=_NOW
    )
    assert candidate.integrity_reason == "STEP31_ELIGIBILITY_BINDING_MISMATCH"


def test_execution_context_is_common_for_nse_index_and_mcx() -> None:
    for instrument, product, tick, precision in (
        ("NIFTY", "NSE_INDEX", "0.05", 2),
        ("GOLDM", "MCX_FUTURE", "1", 0),
    ):
        context = _context(instrument, product=product, tick=tick, precision=precision)
        candidate = construct_trade_candidate(
            _input(instrument=instrument, context=context), clock=_NOW
        )
        assert candidate.construction_status is TradeConstructionStatus.COMPLETE
        assert candidate.product == product


def test_multiple_ready_child_theses_are_all_constructed_without_ranking() -> None:
    handoff, eligible = _handoff(
        extra=((V1Setup.CONSOLIDATION_BREAKOUT, V1Direction.LONG),)
    )
    inputs = (
        _input(handoff=handoff, eligible=eligible),
        _input(
            V1Setup.CONSOLIDATION_BREAKOUT,
            V1Direction.LONG,
            handoff=handoff,
            eligible=eligible,
        ),
    )
    candidates = construct_all_trade_candidates(handoff, inputs, clock=_NOW)
    assert len(candidates) == 2
    assert {item.setup_family for item in candidates} == {
        V1Setup.PULLBACK_CONTINUATION.value,
        V1Setup.CONSOLIDATION_BREAKOUT.value,
    }
    assert all(not hasattr(item, "rank") for item in candidates)


def test_duplicate_or_missing_active_candidate_identity_is_rejected() -> None:
    handoff, eligible = _handoff()
    item = _input(handoff=handoff, eligible=eligible)
    with pytest.raises(ValueError, match="DUPLICATE_ACTIVE_CANDIDATE"):
        construct_all_trade_candidates(handoff, (item, item), clock=_NOW)
    with pytest.raises(ValueError, match="ELIGIBLE_POPULATION_MISMATCH"):
        construct_all_trade_candidates(handoff, (), clock=_NOW)


def _observation(candidate, **changes: object) -> PreEntryObservation:  # type: ignore[no-untyped-def]
    values: dict[str, object] = {
        "run_id": candidate.run_id,
        "active_chart_revision_identity": candidate.active_chart_revision_identity,
        "observation_boundary": candidate.market_data_boundary,
        "layer1_assessment_identity": candidate.layer1_assessment_identity,
        "direction": V1Direction(candidate.direction),
        "readiness_state": ReadinessState.READY_FOR_TRADE_CONSTRUCTION,
        "execution_context_identity": candidate.execution_context_identity,
        "completed_close": None,
        "observed_high": Decimal("99"),
        "observed_low": Decimal("98"),
        "candidate_armed": True,
    }
    values.update(changes)
    return PreEntryObservation(**values)  # type: ignore[arg-type]


def test_armed_entry_trigger_and_unarmed_gap_through_are_distinct() -> None:
    candidate = construct_trade_candidate(_input(), clock=_NOW)
    triggered = assess_pre_entry(
        candidate, _observation(candidate, observed_high=Decimal("101"))
    )
    gap = assess_pre_entry(
        candidate,
        _observation(
            candidate, observed_high=Decimal("101"), candidate_armed=False
        ),
    )
    assert triggered.entry_state is TradeCandidateEntryState.TRIGGERED
    assert gap.entry_state is TradeCandidateEntryState.RECONSTRUCTION_REQUIRED
    assert gap.reason == "ENTRY_TRADED_THROUGH_BEFORE_ARMED"


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"observation_boundary": datetime.fromisoformat("2026-08-13T00:00:00+05:30")}, "COMPLETED_DAILY_BOUNDARY_SUPERSEDED"),
        ({"active_chart_revision_identity": "b" * 64}, "CHART_REVISION_SUPERSEDED"),
        ({"readiness_state": ReadinessState.WEAKENING}, "READINESS_CHANGED"),
        ({"completed_close": Decimal("93")}, "ANALYTICAL_INVALIDATION_OCCURRED"),
        ({"observed_high": Decimal("113")}, "TARGET_REACHED_BEFORE_ENTRY"),
        ({"observed_low": Decimal("93")}, "STOP_SIDE_CROSSED_BEFORE_ENTRY"),
    ),
)
def test_deterministic_pre_entry_staleness(changes: dict[str, object], reason: str) -> None:
    candidate = construct_trade_candidate(_input(), clock=_NOW)
    result = assess_pre_entry(candidate, _observation(candidate, **changes))
    assert result.staleness_status is TradeCandidateStaleness.STALE
    assert result.reason == reason


def test_complete_candidate_produces_geometry_preserving_domain_007_handoff() -> None:
    candidate = construct_trade_candidate(_input(), clock=_NOW)
    handoff = domain_007_handoff(candidate)
    assert handoff.handoff_identity == DOMAIN_007_HANDOFF_ID
    assert handoff.entry_price == candidate.entry_price
    assert handoff.stop_price == candidate.stop_price
    assert not hasattr(handoff, "risk_decision")


def test_restart_recovery_immutability_and_audit_reconstruction(tmp_path: Path) -> None:
    candidate = construct_trade_candidate(_input(), clock=_NOW)
    store = LocalTradeCandidateStore(tmp_path / "trade-candidates")
    first = store.retain(candidate)
    assert store.retain(candidate) == first
    recovered = LocalTradeCandidateStore(tmp_path / "trade-candidates").load(
        candidate.run_id, candidate.candidate_id
    )
    assert recovered == candidate
    assert audit_reconstructs(recovered, _input())
    with pytest.raises(ValueError, match="IMMUTABLE_CONFLICT"):
        store.retain(replace(candidate, integrity_reason="CHANGED"))


def test_contract_exposes_no_external_geometry_authority_or_execution() -> None:
    candidate = construct_trade_candidate(_input(), clock=_NOW)
    representation = repr(candidate).lower()
    for forbidden in (
        "openai", "pine", "sponsor_price", "place_order", "position_size",
        "quantity", "live_decision", "paper_decision", "webhook",
    ):
        assert forbidden not in representation
