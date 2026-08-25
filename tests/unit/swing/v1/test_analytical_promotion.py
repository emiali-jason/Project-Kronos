from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kronos.swing.v1.analytical_promotion import (
    KR370_PROMOTION_AUTHORITY,
    KR370_PROMOTION_CONTRACT_ID,
    Kr370AnalyticalClassification,
    Kr370CriterionIdentity,
    Kr370CriterionResult,
    Kr370CriterionState,
    Kr370Watchability,
    LocalKr370AnalyticalPromotionStore,
    _native_requirement_sha256,
    classify_kr370,
    evaluate_kr370_analytical_promotion,
)
from kronos.swing.v1.extension import (
    ExtensionAvailability,
    _fact as _extension_fact,
)
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_discovery import (
    Native1HState,
    Native1WState,
    Native4HState,
)
from kronos.swing.v1.path_clearance import (
    PathClearanceAvailability,
    PathObstacleComponent,
    PathObstacleSource,
    _fact as _path_fact,
)
from kronos.swing.v1.reference_facts import SwingReferenceChartTimeframe
from kronos.swing.v1.progression_watch import (
    GovernedCompletedBar,
    ProgressionRequirementState,
    ProgressionWatchState,
    activate_watch,
    derive_kr370_progression_requirements,
    observe_completed_bar,
)
from kronos.swing.v1.visual_evidence_v2 import VisualTimeframe
from kronos.swing.v1.visual_evidence_v3 import (
    VisualQuestionV3,
    VisualSetupQuality,
    VisualV3SetupQualityObservation,
)
from tests.unit.swing.v1.test_visual_evidence_v3 import (
    NOW,
    _context,
    _visual_for,
)


def _criteria(satisfied: int) -> tuple[Kr370CriterionResult, ...]:
    return tuple(
        Kr370CriterionResult(
            identity,
            (
                Kr370CriterionState.SATISFIED
                if index < satisfied
                else Kr370CriterionState.UNSATISFIED
            ),
            f"CONTROLLED_{identity.value}",
            (f"evidence-{index}",),
        )
        for index, identity in enumerate(Kr370CriterionIdentity)
    )


@pytest.mark.parametrize(
    ("direction", "satisfied", "expected"),
    (
        (V1Direction.LONG, 5, Kr370AnalyticalClassification.BUY_NOW),
        (V1Direction.SHORT, 5, Kr370AnalyticalClassification.SELL_NOW),
        (V1Direction.LONG, 4, Kr370AnalyticalClassification.BUY_READY),
        (V1Direction.SHORT, 4, Kr370AnalyticalClassification.SELL_READY),
        (V1Direction.LONG, 3, Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP),
        (V1Direction.SHORT, 2, Kr370AnalyticalClassification.POTENTIAL_SELL_SETUP),
        (V1Direction.LONG, 1, Kr370AnalyticalClassification.NO_SETUP),
        (V1Direction.SHORT, 0, Kr370AnalyticalClassification.NO_SETUP),
    ),
)
def test_exact_unweighted_five_criterion_mapping(
    direction: V1Direction,
    satisfied: int,
    expected: Kr370AnalyticalClassification,
) -> None:
    state, actual_satisfied, missing = classify_kr370(
        direction, _criteria(satisfied)
    )

    assert state is expected
    assert actual_satisfied == satisfied
    assert missing == 5 - satisfied


def _scenario(
    *,
    direction: V1Direction = V1Direction.LONG,
    progression: Native1HState = Native1HState.PROGRESSING,
    weekly: Native1WState = Native1WState.SUPPORTIVE,
    four_hour: Native4HState = Native4HState.STRUCTURAL_HOLD,
    cpr_accepted: bool = True,
    path_clear: bool | None = True,
    quality: VisualSetupQuality = VisualSetupQuality.CLEAN_DIRECTIONAL,
    extended: bool | None = False,
):
    facts, requirement = _context()
    instrument = facts.instrument(requirement.canonical_instrument)
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    reference = instrument.reference_fact(SwingReferenceChartTimeframe.ONE_HOUR)
    level = reference.tc if direction is V1Direction.LONG else reference.bc
    assert level is not None
    close = (
        level + 1.0
        if direction is V1Direction.LONG and cpr_accepted
        else level - 1.0
        if direction is V1Direction.SHORT and cpr_accepted
        else level - 1.0
        if direction is V1Direction.LONG
        else level + 1.0
    )
    changed_hour = replace(
        hour,
        close=float(close),
        high=float(max(hour.high, close)),
        low=float(min(hour.low, close)),
    )
    changed_instrument = replace(
        instrument,
        timeframes=tuple(
            changed_hour if item.timeframe is FactualTimeframe.ONE_HOUR else item
            for item in instrument.timeframes
        ),
    )
    changed_facts = replace(
        facts,
        instruments=tuple(
            changed_instrument if item is instrument else item
            for item in facts.instruments
        ),
    )
    thesis_hour = next(
        item
        for item in requirement.thesis.timeframe_facts
        if item.timeframe is FactualTimeframe.ONE_HOUR
    )
    thesis = replace(
        requirement.thesis,
        direction=direction,
        weekly_state=weekly,
        four_hour_state=four_hour,
        one_hour_state=progression,
        timeframe_facts=tuple(
            replace(thesis_hour, close=float(close), high=float(max(thesis_hour.high, close)), low=float(min(thesis_hour.low, close)))
            if item is thesis_hour
            else item
            for item in requirement.thesis.timeframe_facts
        ),
    )
    changed_requirement = replace(
        requirement, thesis=thesis, requirement_sha256="0" * 64
    )
    changed_requirement = replace(
        changed_requirement,
        requirement_sha256=_native_requirement_sha256(changed_requirement),
    )
    visual = list(_visual_for(changed_facts, changed_requirement))
    hour_response = next(
        item for item in visual if item.timeframe is VisualTimeframe.ONE_HOUR
    )
    quality_observation = next(
        item
        for item in hour_response.observations
        if item.question_id is VisualQuestionV3.PRICE_ACTION_QUALITY
    )
    assert type(quality_observation) is VisualV3SetupQualityObservation
    changed_quality = replace(quality_observation, setup_quality=quality)
    visual[visual.index(hour_response)] = replace(
        hour_response,
        observations=tuple(
            changed_quality if item is quality_observation else item
            for item in hour_response.observations
        ),
    )
    return (
        changed_requirement,
        changed_facts,
        tuple(visual),
        _path(changed_facts, changed_requirement, path_clear),
        _extension(changed_facts, changed_requirement, extended),
    )


def _path(facts, requirement, clear):  # type: ignore[no-untyped-def]
    instrument = facts.instrument(requirement.canonical_instrument)
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    atr = instrument.one_hour_atr
    assert atr is not None and atr.value is not None
    base = dict(
        run_identity=requirement.native_run_identity,
        canonical_instrument=requirement.canonical_instrument,
        direction=requirement.thesis.direction,
        analysis_boundary=atr.analysis_boundary,
        observation_boundary=hour.observation_boundary,
        source_market_data_boundary=hour.source_market_data_boundary,
        completed_price=hour.close,
        atr14=atr.value,
        atr_fact_integrity_sha256=atr.integrity_sha256,
    )
    if clear is None:
        return _path_fact(
            **base,
            available_sources=(),
            blocking_obstacles=(),
            availability=PathClearanceAvailability.UNAVAILABLE,
            unavailable_reason="CONTROLLED_E01_UNAVAILABLE",
            path_clear=None,
            clearance_level=None,
        )
    sources = (PathObstacleSource.ONE_HOUR_SMA200,)
    blockers = ()
    clearance = None
    if not clear:
        direction = requirement.thesis.direction
        level = (
            hour.close + atr.value * 0.1
            if direction is V1Direction.LONG
            else hour.close - atr.value * 0.1
        )
        blocker = PathObstacleComponent(
            PathObstacleSource.ONE_HOUR_SMA200,
            "CONTROLLED_1H_SMA200",
            float(level),
            float(atr.value * 0.1),
            0.1,
            hour.source_timestamp,
        )
        blockers = (blocker, replace(blocker, definition_identity="CONTROLLED_RADIUS_1"))
        clearance = float(level)
    return _path_fact(
        **base,
        available_sources=sources,
        blocking_obstacles=blockers,
        availability=PathClearanceAvailability.AVAILABLE,
        unavailable_reason=None,
        path_clear=clear,
        clearance_level=clearance,
    )


def _extension(facts, requirement, extended):  # type: ignore[no-untyped-def]
    instrument = facts.instrument(requirement.canonical_instrument)
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    atr = instrument.one_hour_atr
    assert atr is not None and atr.value is not None
    base = dict(
        run_identity=requirement.native_run_identity,
        native_assessment_sha256=requirement.thesis.native_assessment_sha256,
        canonical_instrument=requirement.canonical_instrument,
        direction=requirement.thesis.direction,
        analysis_boundary=atr.analysis_boundary,
        observation_boundary=hour.observation_boundary,
        source_market_data_boundary=hour.source_market_data_boundary,
        completed_close=hour.close,
        calendar_identity=hour.calendar_identity,
        calendar_version=hour.calendar_version,
        session_identity=hour.session_identity,
        exchange_timezone=hour.exchange_timezone,
        source_provider_identity=hour.source_provider_identity,
        provenance=hour.provenance,
        atr14=atr.value,
        atr_fact_integrity_sha256=atr.integrity_sha256,
    )
    if extended is None:
        return _extension_fact(
            **base,
            availability=ExtensionAvailability.UNAVAILABLE,
            unavailable_reason="CONTROLLED_E03_UNAVAILABLE",
            pivot_definition_identity=None,
            selected_pivot_radius=None,
            selected_pivot_identity=None,
            selected_pivot_boundary=None,
            anchor_price=None,
            directional_distance=None,
            extension_atr=None,
            materially_extended=None,
        )
    distance = atr.value * (3.0 if extended else 1.0)
    anchor = (
        hour.close - distance
        if requirement.thesis.direction is V1Direction.LONG
        else hour.close + distance
    )
    return _extension_fact(
        **base,
        availability=ExtensionAvailability.AVAILABLE,
        unavailable_reason=None,
        pivot_definition_identity="FRACTAL_UNIQUE_EXTREME_RADIUS_1",
        selected_pivot_radius=1,
        selected_pivot_identity="CONTROLLED_DIRECTIONAL_PIVOT",
        selected_pivot_boundary=hour.source_timestamp,
        anchor_price=float(anchor),
        directional_distance=float(distance),
        extension_atr=float(distance / atr.value),
        materially_extended=extended,
    )


def _evaluate(**changes):  # type: ignore[no-untyped-def]
    values = _scenario(**changes)
    return evaluate_kr370_analytical_promotion(
        *values,
        review_pack_identity="KRONOS-V3-REVIEW-PACK-CONTROLLED",
        created_at=NOW,
    )


@pytest.mark.parametrize(
    "quality",
    (VisualSetupQuality.MESSY_CHOPPY, VisualSetupQuality.CONFLICTING),
)
def test_setup_quality_hard_no_setup_overrides_count(
    quality: VisualSetupQuality,
) -> None:
    record = _evaluate(quality=quality)

    assert record.classification is Kr370AnalyticalClassification.NO_SETUP
    assert record.hard_gate_reason is not None
    assert record.criterion(Kr370CriterionIdentity.K4_SETUP_QUALITY).state is Kr370CriterionState.UNSATISFIED


@pytest.mark.parametrize(
    ("direction", "expected"),
    (
        (V1Direction.LONG, Kr370AnalyticalClassification.BUY_NOW),
        (V1Direction.SHORT, Kr370AnalyticalClassification.SELL_NOW),
    ),
)
def test_weekly_neutral_permits_now_and_weekly_opposing_hard_gates(
    direction: V1Direction,
    expected: Kr370AnalyticalClassification,
) -> None:
    neutral = _evaluate(direction=direction, weekly=Native1WState.NEUTRAL)
    opposing = _evaluate(direction=direction, weekly=Native1WState.OPPOSING)

    assert neutral.classification is expected
    assert neutral.satisfied_count == 5
    assert opposing.classification is Kr370AnalyticalClassification.NO_SETUP
    assert opposing.hard_gate_reason == "NSE_WEEKLY_OPPOSING"


@pytest.mark.parametrize(
    ("direction", "expected"),
    (
        (V1Direction.LONG, Kr370AnalyticalClassification.BUY_READY),
        (V1Direction.SHORT, Kr370AnalyticalClassification.SELL_READY),
    ),
)
def test_extension_is_one_missing_criterion_not_hard_gate(
    direction: V1Direction,
    expected: Kr370AnalyticalClassification,
) -> None:
    record = _evaluate(direction=direction, extended=True)

    assert record.classification is expected
    assert record.sole_missing_criterion is Kr370CriterionIdentity.K5_NON_EXTENSION
    assert record.hard_gate_reason is None
    assert record.watchability is Kr370Watchability.NO_AUTOMATED_ALERT_AVAILABLE


def test_mandatory_evidence_unavailable_is_not_fake_failure_count() -> None:
    record = _evaluate(extended=None)

    assert record.classification is Kr370AnalyticalClassification.NO_SETUP
    assert record.missing_count is None
    assert record.not_evaluable_reason is not None
    assert "K5_NON_EXTENSION" in record.not_evaluable_reason


def test_ready_k2_retains_exact_completed_close_condition() -> None:
    record = _evaluate(cpr_accepted=False)

    assert record.classification is Kr370AnalyticalClassification.BUY_READY
    assert record.sole_missing_criterion is Kr370CriterionIdentity.K2_CPR_ACCEPTANCE
    assert record.promotion_condition is not None
    assert record.promotion_condition.comparator == "BAR_CLOSE_ABOVE"
    assert record.promotion_condition.price == record.criterion(
        Kr370CriterionIdentity.K2_CPR_ACCEPTANCE
    ).level
    assert record.watchability is Kr370Watchability.WATCH_AVAILABLE


def test_multiple_e01_obstacles_are_one_missing_criterion() -> None:
    record = _evaluate(direction=V1Direction.SHORT, path_clear=False)
    criterion = record.criterion(Kr370CriterionIdentity.K3_PATH_CLEARANCE)

    assert record.classification is Kr370AnalyticalClassification.SELL_READY
    assert record.missing_count == 1
    assert record.sole_missing_criterion is Kr370CriterionIdentity.K3_PATH_CLEARANCE
    assert len(criterion.blocking_components) == 2


def test_store_is_immutable_exact_bound_and_restart_restorable(tmp_path: Path) -> None:
    record = _evaluate()
    store = LocalKr370AnalyticalPromotionStore((tmp_path / "promotion").resolve())

    first = store.retain(record)
    second = store.retain(record)
    restored = LocalKr370AnalyticalPromotionStore(store.root).load_exact(
        record.run_identity,
        record.canonical_instrument,
        record.native_assessment_sha256,
        record.review_pack_identity,
        tuple(item[1] for item in record.visual_evidence_bindings),
    )

    assert first == second
    assert restored == record
    assert restored.contract_identity == KR370_PROMOTION_CONTRACT_ID
    assert restored.authority == KR370_PROMOTION_AUTHORITY
    assert not restored.execution_authority
    assert not restored.risk_authority
    assert not restored.sponsor_decision_authority
    assert not restored.position_authority
    assert not restored.fill_authority
    assert not restored.broker_authority


@pytest.mark.parametrize(
    ("direction", "scenario", "expected"),
    (
        (V1Direction.LONG, {}, Kr370AnalyticalClassification.BUY_NOW),
        (V1Direction.SHORT, {}, Kr370AnalyticalClassification.SELL_NOW),
        (
            V1Direction.LONG,
            {"extended": True},
            Kr370AnalyticalClassification.BUY_READY,
        ),
        (
            V1Direction.SHORT,
            {"extended": True},
            Kr370AnalyticalClassification.SELL_READY,
        ),
        (
            V1Direction.LONG,
            {"extended": True, "cpr_accepted": False},
            Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP,
        ),
        (
            V1Direction.SHORT,
            {"extended": True, "cpr_accepted": False},
            Kr370AnalyticalClassification.POTENTIAL_SELL_SETUP,
        ),
        (
            V1Direction.LONG,
            {"quality": VisualSetupQuality.MESSY_CHOPPY},
            Kr370AnalyticalClassification.NO_SETUP,
        ),
    ),
)
def test_every_governed_promotion_state_restores_without_recalculation(
    tmp_path: Path,
    direction: V1Direction,
    scenario: dict[str, object],
    expected: Kr370AnalyticalClassification,
) -> None:
    record = _evaluate(direction=direction, **scenario)
    store = LocalKr370AnalyticalPromotionStore(
        (tmp_path / expected.value).resolve()
    )
    store.retain(record)

    restored = LocalKr370AnalyticalPromotionStore(store.root).load_exact(
        record.run_identity,
        record.canonical_instrument,
        record.native_assessment_sha256,
        record.review_pack_identity,
        tuple(item[1] for item in record.visual_evidence_bindings),
    )

    assert record.classification is expected
    assert restored == record
    assert not restored.kr390_current_input
    assert not restored.kr400_current_alert_source


def test_invalid_requirement_binding_fails_closed() -> None:
    requirement, facts, visual, path, extension = _scenario()
    invalid = replace(requirement, requirement_sha256="f" * 64)

    record = evaluate_kr370_analytical_promotion(
        invalid,
        facts,
        visual,
        path,
        extension,
        review_pack_identity="KRONOS-V3-REVIEW-PACK-CONTROLLED",
        created_at=datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
    )

    assert record.classification is Kr370AnalyticalClassification.NO_SETUP
    assert record.hard_gate_reason == "INVALID_EXACT_EVIDENCE_BINDING"
    assert record.not_evaluable_reason == "NATIVE_REQUIREMENT_INTEGRITY_INVALID"


def test_missing_or_historical_visual_contract_cannot_create_kr370_state() -> None:
    requirement, facts, _, path, extension = _scenario()

    with pytest.raises(ValueError, match="KR370_V3_1_EVIDENCE_REQUIRED"):
        evaluate_kr370_analytical_promotion(
            requirement,
            facts,
            (),
            path,
            extension,
            review_pack_identity="KRONOS-V3-REVIEW-PACK-CONTROLLED",
            created_at=NOW,
        )


def test_ready_watch_trigger_requests_reassessment_without_changing_kr370() -> None:
    record = _evaluate(cpr_accepted=False)
    requirements = derive_kr370_progression_requirements(record)
    k2 = next(
        item
        for item in requirements
        if item.condition_identity
        == Kr370CriterionIdentity.K2_CPR_ACCEPTANCE.value
    )
    assert k2.state is ProgressionRequirementState.WATCH_AVAILABLE
    assert k2.price is not None
    watch = activate_watch(
        k2, activated_at=k2.observation_boundary + timedelta(minutes=1)
    )
    triggered = observe_completed_bar(
        watch,
        GovernedCompletedBar(
            canonical_instrument=record.canonical_instrument,
            timeframe=FactualTimeframe.ONE_HOUR,
            close=k2.price + 1.0,
            observation_boundary=k2.observation_boundary + timedelta(hours=1),
            source_identity="CONTROLLED_COMPLETED_BAR",
            calendar_identity="CONTROLLED_CALENDAR",
            calendar_version="1",
            session_identity="CONTROLLED_SESSION",
            provenance=("CONTROLLED_REASSESSMENT_ONLY",),
        ),
    )

    assert triggered.state is ProgressionWatchState.TRIGGERED
    assert record.classification is Kr370AnalyticalClassification.BUY_READY
    assert record.authority == KR370_PROMOTION_AUTHORITY
    assert not record.kr390_current_input
    assert not record.kr400_current_alert_source
