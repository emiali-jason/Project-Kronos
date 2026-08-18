from dataclasses import replace
from datetime import UTC, datetime

import pytest

from kronos.swing.v1.models import StructuralState, V1Direction, V1Setup
from kronos.swing.v1.shadow_mtf import (
    DailyControlEvidence,
    DailyControlProbableIdentity,
    ShadowMtfRun,
    ShadowTimeframe,
    TimeframeStructuralEvidence,
    reconcile_shadow_candidate,
)
from kronos.swing.v1.validation_evidence import (
    AnalyticalClaimEvidence,
    NextConditionAuthority,
    NextConditionEvidence,
    NumericLevelAvailability,
    NumericReferenceEvidence,
    ReviewNumericEvidenceBundle,
    ShadowValidationEvidenceStore,
)


NOW = datetime(2026, 8, 14, 10, tzinfo=UTC)


def _reference(identity: str = "RANGE_HIGH") -> NumericReferenceEvidence:
    return NumericReferenceEvidence(
        identity,
        "4H",
        NOW,
        "KRONOS_DERIVED_4H",
        NumericLevelAvailability.AVAILABLE,
        price=128.5,
    )


def _assessment():
    def evidence(timeframe, *, setup=None, direction=V1Direction.NONE):
        return TimeframeStructuralEvidence(
            timeframe,
            NOW,
            StructuralState.BULLISH_HH_HL,
            setup,
            direction,
            "COMPLETED_STRUCTURE",
        )
    return reconcile_shadow_candidate(
        run_identity="RUN-001",
        provider_source_identity="KITE-SNAPSHOT",
        canonical_instrument="RELIANCE",
        control=DailyControlEvidence(False, None, V1Direction.NONE, "NO DAILY PROBABLE", NOW),
        weekly=evidence(ShadowTimeframe.WEEKLY),
        daily=evidence(ShadowTimeframe.DAILY),
        four_hour=evidence(
            ShadowTimeframe.FOUR_HOUR,
            setup=V1Setup.CONSOLIDATION_BREAKOUT,
            direction=V1Direction.LONG,
        ),
        one_hour=evidence(ShadowTimeframe.ONE_HOUR),
    )


@pytest.mark.parametrize("claim", [
    "SWING_HIGH",
    "SWING_LOW",
    "BARRIER_PRESENT",
    "CONSOLIDATION",
    "BREAKOUT",
    "ANALYTICAL_BOUNDARY_CLOSE",
    "INVALIDATION_RESET",
])
def test_numeric_claims_retain_exact_reference_and_provenance(claim: str) -> None:
    evidence = AnalyticalClaimEvidence(claim, _reference(claim), ("KITE", "DOMAIN-008"))
    assert evidence.reference.price == 128.5
    assert evidence.reference.observation_boundary == NOW


def test_unavailable_level_cannot_reconstruct_a_price_or_zone() -> None:
    unavailable = NumericReferenceEvidence(
        "BARRIER",
        "1D",
        NOW,
        "CHART_ANALYST_STRUCTURED_EVIDENCE",
        NumericLevelAvailability.LEVEL_UNAVAILABLE,
    )
    assert unavailable.price is None
    with pytest.raises(ValueError, match="NUMERIC_REFERENCE_EVIDENCE_INVALID"):
        NumericReferenceEvidence(
            "BARRIER",
            "1D",
            NOW,
            "SOURCE",
            NumericLevelAvailability.LEVEL_UNAVAILABLE,
            price=100.0,
        )


def test_next_condition_distinguishes_chart_health_from_trade_plan_readiness() -> None:
    condition = NextConditionEvidence(
        "WAIT_FOR_ACCEPTANCE",
        "4H",
        "CLOSE",
        "EXISTING_ANALYTICAL_NEXT_CONDITION",
        NumericLevelAvailability.AVAILABLE,
        NextConditionAuthority.CHART_HEALTH_EVENT,
        _reference(),
        False,
    )
    assert condition.ready_for_trade_plan is False
    with pytest.raises(ValueError, match="NEXT_CONDITION_EVIDENCE_INVALID"):
        NextConditionEvidence(
            "WAIT_FOR_ACCEPTANCE",
            "4H",
            "CLOSE",
            "SOURCE",
            NumericLevelAvailability.AVAILABLE,
            NextConditionAuthority.CHART_HEALTH_EVENT,
            _reference(),
            True,
        )


def test_shadow_evidence_and_sponsor_observation_survive_restart(tmp_path) -> None:
    assessment = _assessment()
    store = ShadowValidationEvidenceStore(tmp_path, clock=lambda: NOW)
    condition = NextConditionEvidence(
        "WAIT_FOR_ACCEPTANCE",
        "4H",
        "CLOSE",
        "EXISTING_ANALYTICAL_NEXT_CONDITION",
        NumericLevelAvailability.AVAILABLE,
        NextConditionAuthority.CHART_HEALTH_EVENT,
        _reference(),
        False,
    )
    bundle = ReviewNumericEvidenceBundle(
        (AnalyticalClaimEvidence("BREAKOUT", _reference(), ("KITE",)),),
        condition,
    )
    store.retain_assessment(assessment, bundle)
    store.record_sponsor_observation(
        assessment,
        "4H HH/HL continuation clearly developing",
    )

    recovered = ShadowValidationEvidenceStore(tmp_path).evidence_payload(
        assessment.run_identity,
        assessment.canonical_instrument,
    )
    assert recovered["assessment"]["state"] == "CREATED"  # type: ignore[index]
    assert recovered["review_numeric_evidence"]["claims"][0]["reference"]["price"] == 128.5  # type: ignore[index]
    observations = recovered["sponsor_observations"]
    assert observations[0]["observation"] == "4H HH/HL continuation clearly developing"  # type: ignore[index]
    assert "access_token" not in str(recovered).lower()


def test_retained_assessment_is_immutable(tmp_path) -> None:
    assessment = _assessment()
    store = ShadowValidationEvidenceStore(tmp_path)
    store.retain_assessment(assessment)
    changed = reconcile_shadow_candidate(
        run_identity=assessment.run_identity,
        provider_source_identity=assessment.provider_source_identity,
        canonical_instrument=assessment.canonical_instrument,
        control=assessment.control,
        weekly=assessment.weekly,
        daily=assessment.daily,
        four_hour=assessment.four_hour,
        one_hour=TimeframeStructuralEvidence(
            ShadowTimeframe.ONE_HOUR,
            NOW,
            StructuralState.BEARISH_LH_LL,
            None,
            V1Direction.NONE,
            "OPPOSING_STRUCTURE",
        ),
    )
    with pytest.raises(ValueError, match="SHADOW_VALIDATION_ASSESSMENT_IMMUTABLE"):
        store.retain_assessment(changed)


def test_complete_same_98_run_is_atomic_and_restart_recoverable(tmp_path) -> None:
    base = _assessment()
    run = ShadowMtfRun(
        base.run_identity,
        base.provider_source_identity,
        tuple(
            replace(base, canonical_instrument=f"INSTRUMENT {index}")
            for index in range(98)
        ),
    )
    path = ShadowValidationEvidenceStore(tmp_path).retain_run(run)

    assert path.name == "RUN-001.json"
    recovered = ShadowValidationEvidenceStore(tmp_path).load_run(run.run_identity)
    assert recovered == run
    assert len(recovered.assessments) == 98
    assert "access_token" not in path.read_text(encoding="utf-8").lower()


def test_multiple_daily_probables_survive_atomic_run_recovery(tmp_path) -> None:
    base = _assessment()
    control = DailyControlEvidence(
        True,
        None,
        V1Direction.NONE,
        "UNCHANGED_DAILY_LAYER1_MULTIPLE_PROBABLES",
        NOW,
        (
            DailyControlProbableIdentity(
                V1Setup.PULLBACK_CONTINUATION,
                V1Direction.LONG,
            ),
            DailyControlProbableIdentity(
                V1Setup.CONSOLIDATION_BREAKOUT,
                V1Direction.LONG,
            ),
        ),
    )
    base = replace(base, control=control)
    run = ShadowMtfRun(
        base.run_identity,
        base.provider_source_identity,
        tuple(
            replace(base, canonical_instrument=f"INSTRUMENT {index}")
            for index in range(98)
        ),
    )
    store = ShadowValidationEvidenceStore(tmp_path)
    store.retain_run(run)
    recovered = store.load_run(run.run_identity)
    assert recovered == run
    assert recovered.assessments[0].control.probable_identities == (
        DailyControlProbableIdentity(
            V1Setup.PULLBACK_CONTINUATION,
            V1Direction.LONG,
        ),
        DailyControlProbableIdentity(
            V1Setup.CONSOLIDATION_BREAKOUT,
            V1Direction.LONG,
        ),
    )
