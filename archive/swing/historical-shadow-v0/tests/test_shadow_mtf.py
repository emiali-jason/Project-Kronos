from datetime import UTC, datetime

import pytest

from kronos.swing.v1.models import StructuralState, V1Direction, V1Setup
from kronos.swing.v1.shadow_mtf import (
    DailyControlEvidence,
    DailyControlProbableIdentity,
    ShadowCandidateState,
    ShadowInstrumentAssessment,
    ShadowMtfRun,
    ShadowTimeframe,
    TimeframeStructuralEvidence,
    measure_shadow_timeframe,
    reconcile_shadow_candidate,
)


BOUNDARY = datetime(2026, 8, 14, tzinfo=UTC)


def _tf(
    timeframe: ShadowTimeframe,
    state: StructuralState,
    *,
    setup: V1Setup | None = None,
    direction: V1Direction = V1Direction.NONE,
    remainder: bool = False,
) -> TimeframeStructuralEvidence:
    return TimeframeStructuralEvidence(
        timeframe,
        BOUNDARY,
        state,
        setup,
        direction,
        "EXISTING_DETERMINISTIC_STRUCTURE",
        (),
        "MEASURED_NO_THRESHOLD_AUTHORITY",
        True,
        remainder,
    )


def _control(candidate: bool = False) -> DailyControlEvidence:
    return DailyControlEvidence(
        candidate,
        V1Setup.PULLBACK_CONTINUATION if candidate else None,
        V1Direction.LONG if candidate else V1Direction.NONE,
        "FROZEN_DAILY_LAYER1",
        BOUNDARY,
    )


def _assessment(
    *,
    weekly: StructuralState = StructuralState.BULLISH_HH_HL,
    daily: StructuralState = StructuralState.BULLISH_HH_HL,
    four: StructuralState = StructuralState.BULLISH_HH_HL,
    hour: StructuralState = StructuralState.BULLISH_HH_HL,
    previous: ShadowInstrumentAssessment | None = None,
    remainder: bool = False,
    material: bool = False,
) -> ShadowInstrumentAssessment:
    return reconcile_shadow_candidate(
        run_identity="SWING-SHADOW-RUN-001",
        provider_source_identity="KITE-SNAPSHOT-001",
        canonical_instrument="RELIANCE",
        control=_control(),
        weekly=_tf(ShadowTimeframe.WEEKLY, weekly),
        daily=_tf(ShadowTimeframe.DAILY, daily),
        four_hour=_tf(
            ShadowTimeframe.FOUR_HOUR,
            four,
            setup=V1Setup.PULLBACK_CONTINUATION,
            direction=V1Direction.LONG,
            remainder=remainder,
        ),
        one_hour=_tf(ShadowTimeframe.ONE_HOUR, hour),
        previous=previous,
        remainder_material_to_change=material,
    )


def test_shadow_creation_uses_completed_compatible_hierarchy() -> None:
    result = _assessment()
    assert result.state is ShadowCandidateState.CREATED
    assert result.direction is V1Direction.LONG
    assert result.authority == "SHADOW_VALIDATION_ONLY"


def test_shadow_maintenance_and_strengthening_are_state_transitions() -> None:
    created = _assessment()
    maintained = _assessment(previous=created)
    weakened = _assessment(previous=created, hour=StructuralState.MIXED_UNCLEAR)
    strengthened = _assessment(previous=weakened)
    assert maintained.state is ShadowCandidateState.MAINTAINED
    assert weakened.state is ShadowCandidateState.WEAKENED
    assert strengthened.state is ShadowCandidateState.STRENGTHENED


def test_one_hour_opposition_suspends_but_cannot_reverse_higher_thesis() -> None:
    result = _assessment(hour=StructuralState.BEARISH_LH_LL)
    assert result.state is ShadowCandidateState.SUSPENDED
    assert result.direction is V1Direction.LONG
    assert "1H_OPPOSES_1W_1D_4H" in result.contradictions


def test_incompatible_higher_context_prevents_creation() -> None:
    result = _assessment(daily=StructuralState.BEARISH_LH_LL)
    assert result.state is ShadowCandidateState.ABSENT
    assert result.setup is None
    assert result.direction is V1Direction.NONE


def test_incomplete_weekly_evidence_fails_closed_without_claiming_contradiction() -> None:
    result = _assessment(weekly=StructuralState.EVIDENCE_INCOMPLETE)
    assert result.state is ShadowCandidateState.ABSENT
    assert result.setup is None
    assert result.direction is V1Direction.NONE
    assert "1W_EVIDENCE_INCOMPLETE" in result.contradictions
    assert "1W_1D_CONTEXT_INCOMPATIBLE" not in result.contradictions


def test_daily_control_can_retain_multiple_probable_identities() -> None:
    identities = (
        DailyControlProbableIdentity(
            V1Setup.PULLBACK_CONTINUATION,
            V1Direction.LONG,
        ),
        DailyControlProbableIdentity(
            V1Setup.CONSOLIDATION_BREAKOUT,
            V1Direction.LONG,
        ),
    )
    control = DailyControlEvidence(
        True,
        None,
        V1Direction.NONE,
        "UNCHANGED_DAILY_LAYER1_MULTIPLE_PROBABLES",
        BOUNDARY,
        identities,
    )
    assert control.candidate is True
    assert control.probable_identities == identities


def test_lost_higher_context_retires_prior_shadow_only() -> None:
    created = _assessment()
    result = _assessment(daily=StructuralState.BEARISH_LH_LL, previous=created)
    assert result.state is ShadowCandidateState.RETIRED
    assert result.control == created.control


def test_material_remainder_dependency_requires_factual_remainder_participation() -> None:
    result = _assessment(remainder=True, material=True)
    assert result.session_remainder_dependent_change is True
    with pytest.raises(ValueError, match="SHADOW_INSTRUMENT_ASSESSMENT_INVALID"):
        _assessment(remainder=False, material=True)


def test_same_98_run_and_provider_binding_is_enforced() -> None:
    base = _assessment()
    assessments = tuple(
        ShadowInstrumentAssessment(
            base.run_identity,
            base.provider_source_identity,
            f"INSTRUMENT {index}",
            base.control,
            base.weekly,
            base.daily,
            base.four_hour,
            base.one_hour,
            base.state,
            base.setup,
            base.direction,
            base.primary_reason,
            base.contradictions,
            base.session_remainder_dependent_change,
        )
        for index in range(98)
    )
    run = ShadowMtfRun("SWING-SHADOW-RUN-001", "KITE-SNAPSHOT-001", assessments)
    assert run.control_population_size == run.shadow_population_size == 98


def test_incomplete_timeframe_is_rejected_before_reconciliation() -> None:
    with pytest.raises(ValueError, match="SHADOW_TIMEFRAME_EVIDENCE_INVALID"):
        TimeframeStructuralEvidence(
            ShadowTimeframe.ONE_HOUR,
            BOUNDARY,
            StructuralState.BULLISH_HH_HL,
            None,
            V1Direction.NONE,
            "UNFINISHED",
            completed=False,
        )


def test_completed_structural_measurement_reuses_existing_evidence() -> None:
    from kronos.provider.contracts.market_data import HistoricalCandle

    candles = tuple(
        HistoricalCandle(
            datetime(2026, 7, index + 1, tzinfo=UTC),
            100.0 + index,
            102.0 + index,
            99.0 + index,
            101.0 + index,
            1_000 + index,
        )
        for index in range(30)
    )
    evidence = measure_shadow_timeframe(
        timeframe=ShadowTimeframe.DAILY,
        candles=candles,
        completed=True,
    )
    assert evidence.setup is None
    assert evidence.reason == "1D_STRUCTURAL_ROLE_ONLY"
    assert evidence.participation == "EXISTING_VOLUME_EVIDENCE_ONLY_NO_NEW_THRESHOLD"


def test_unfinished_series_cannot_enter_shadow_measurement() -> None:
    from kronos.provider.contracts.market_data import HistoricalCandle

    candle = HistoricalCandle(BOUNDARY, 100.0, 102.0, 99.0, 101.0, 100)
    with pytest.raises(ValueError, match="SHADOW_COMPLETED_SERIES_INVALID"):
        measure_shadow_timeframe(
            timeframe=ShadowTimeframe.ONE_HOUR,
            candles=(candle,),
            completed=False,
        )
