import copy
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

import pytest

from kronos.instrument.facts import CanonicalInstrumentContext, InstrumentContextStatus
from kronos.application.swing_trade_window import (
    SwingTradeWindowWorkflow,
    TradeWindowState,
)
from kronos.application.swing_visual_v3 import CompletedVisualV3Review
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalClassification,
    evaluate_kr370_analytical_promotion,
)
from kronos.swing.v1.kr370_step31_handoff import (
    KR370_STEP31_HANDOFF_AUTHORITY,
    KR370_STEP31_HANDOFF_CONTRACT_ID,
    Kr370Step31HandoffRejected,
    LocalKr370Step31HandoffStore,
    create_kr370_step31_handoff,
)
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_discovery import Native1HState
from kronos.swing.v1.native_readiness_v3 import create_native_readiness_record_v3
from kronos.swing.v1.native_review import NativeLayer2EvidenceState
from kronos.swing.v1.native_trade_construction import (
    AuthoritativePriceEvidence,
    LocalTradePlanStore,
    QualificationCandleEvidence,
    TradePlanStatus,
    TradeSetupIdentity,
    create_trade_construction_evidence_package,
)
from kronos.swing.v1.pdf_visual_review_v3 import VisualV3ReviewPackRecord
from tests.unit.swing.v1.test_analytical_promotion import _scenario
from tests.unit.swing.v1.test_native_review import _layer2


NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)


def _completed(tmp_path, **scenario):  # type: ignore[no-untyped-def]
    requirement, facts, visual, path, extension = _scenario(**scenario)
    pack = VisualV3ReviewPackRecord(
        "KRONOS-V3-REVIEW-CONTROLLED",
        requirement.native_run_identity,
        requirement.canonical_instrument,
        requirement.thesis.native_assessment_sha256,
        NOW,
        str((tmp_path / "questions.pdf").resolve()),
        "1" * 64,
        tuple((item.timeframe.value, item.chart_revision_sha256) for item in visual),
        tuple(
            (item.chart_timeframe.value, item.integrity_sha256)
            for item in facts.instrument(requirement.canonical_instrument).reference_facts
        ),
    )
    readiness = create_native_readiness_record_v3(
        requirement,
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS),
        facts,
        visual,
        created_at=NOW,
    )
    promotion = evaluate_kr370_analytical_promotion(
        requirement,
        facts,
        visual,
        path,
        extension,
        review_pack_identity=pack.review_pack_id,
        created_at=NOW,
    )
    return CompletedVisualV3Review(
        requirement, facts, visual, readiness, pack, promotion
    )


def _handoff(completed):  # type: ignore[no-untyped-def]
    assert completed.promotion is not None
    return create_kr370_step31_handoff(
        completed.requirement,
        completed.readiness,
        completed.promotion,
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )


def _price(identity: str, value: str, boundary: datetime) -> AuthoritativePriceEvidence:
    return AuthoritativePriceEvidence(
        identity,
        sha256(identity.encode()).hexdigest(),
        Decimal(value),
        boundary,
        f"GOVERNED:{identity}",
        ("KITE:HISTORICAL",),
    )


def _evidence(completed, *, complete: bool = True):  # type: ignore[no-untyped-def]
    boundary = completed.promotion.analysis_boundary
    candle = QualificationCandleEvidence(
        "QUAL-CANDLE",
        "a" * 64,
        Decimal("100"),
        Decimal("95"),
        boundary,
        complete,
        "COMPLETED_OHLCV:QUALIFICATION_CANDLE",
        ("KITE:HISTORICAL", "DOMAIN-008"),
    )
    return create_trade_construction_evidence_package(
        package_identity="KR370-STEP31-CONTROLLED-PACKAGE",
        native_run_identity=completed.requirement.native_run_identity,
        canonical_instrument=completed.requirement.canonical_instrument,
        native_assessment_sha256=completed.requirement.thesis.native_assessment_sha256,
        setup_identity=TradeSetupIdentity.PULLBACK_CONTINUATION,
        observation_boundary=boundary,
        provenance=("KR370-CONTROLLED-PROOF",),
        qualification_candle=candle,
        governing_structural_low=_price("STRUCTURAL-LOW", "90", boundary),
        governing_structural_high=_price("STRUCTURAL-HIGH", "110", boundary),
        prior_directional_swing_high=_price("PRIOR-HIGH", "120", boundary),
        prior_directional_swing_low=_price("PRIOR-LOW", "80", boundary),
    )


def _context(instrument: str) -> CanonicalInstrumentContext:
    return CanonicalInstrumentContext(
        "INSTRUMENT-CONTEXT-" + "b" * 64,
        instrument,
        "CNC",
        "KITE",
        instrument,
        "NSE",
        "NSE",
        "EQ",
        Decimal("0.05"),
        1,
        2,
        InstrumentContextStatus.COMPLETE,
        ("DOMAIN-006:EAIC-002", f"KITE:NSE:{instrument}"),
    )


@pytest.mark.parametrize(
    ("scenario", "classification"),
    (
        ({}, Kr370AnalyticalClassification.BUY_NOW),
        ({"direction": V1Direction.SHORT}, Kr370AnalyticalClassification.SELL_NOW),
    ),
)
def test_exact_now_states_create_bounded_handoff(tmp_path, scenario, classification) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path, **scenario)
    handoff = _handoff(completed)

    assert handoff.kr370_classification is classification
    assert handoff.contract_identity == KR370_STEP31_HANDOFF_CONTRACT_ID
    assert handoff.authority == KR370_STEP31_HANDOFF_AUTHORITY
    assert not any((
        handoff.geometry_authority,
        handoff.risk_authority,
        handoff.sponsor_decision_authority,
        handoff.entry_timing_authority,
        handoff.position_authority,
        handoff.alert_authority,
        handoff.execution_authority,
        handoff.broker_authority,
    ))


@pytest.mark.parametrize(
    "scenario",
    (
        {"cpr_accepted": False},
        {"cpr_accepted": False, "path_clear": False},
        {"progression": Native1HState.NEUTRAL, "cpr_accepted": False,
         "path_clear": False, "extended": True},
    ),
)
def test_ready_potential_and_no_setup_are_rejected(tmp_path, scenario) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path, **scenario)
    with pytest.raises(
        Kr370Step31HandoffRejected,
        match="KR370_STEP31_CLASSIFICATION_NOT_ELIGIBLE",
    ):
        _handoff(completed)


def test_not_evaluable_is_rejected_separately(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path, path_clear=None)
    with pytest.raises(Kr370Step31HandoffRejected, match="KR370_STEP31_NOT_EVALUABLE"):
        _handoff(completed)


@pytest.mark.parametrize(
    ("change", "reason"),
    (
        ("run", "KR370_STEP31_CURRENT_RUN_MISMATCH"),
        ("instrument", "KR370_STEP31_INSTRUMENT_MISMATCH"),
        ("assessment", "KR370_STEP31_ASSESSMENT_MISMATCH"),
        ("boundary", "KR370_STEP31_STALE_PROMOTION"),
    ),
)
def test_stale_and_foreign_bindings_fail_closed(tmp_path, change, reason) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    requirement = completed.requirement
    readiness = completed.readiness
    promotion = completed.promotion
    current_run = requirement.native_run_identity
    boundary = promotion.analysis_boundary
    if change == "run":
        current_run = "SWING-RUN-" + "F" * 32
    elif change == "instrument":
        readiness = copy.deepcopy(readiness)
        object.__setattr__(readiness, "canonical_instrument", "SBIN")
    elif change == "assessment":
        readiness = copy.deepcopy(readiness)
        object.__setattr__(readiness, "native_assessment_sha256", "f" * 64)
    else:
        boundary = boundary.replace(microsecond=1)
    with pytest.raises(Kr370Step31HandoffRejected, match=reason):
        create_kr370_step31_handoff(
            requirement,
            readiness,
            promotion,
            current_run_identity=current_run,
            current_analysis_boundary=boundary,
            created_at=NOW,
        )


def test_existing_step31_constructs_and_restores_exact_long_geometry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    projection = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )

    assert projection.state is TradeWindowState.TRADE_PLAN_READY
    assert projection.trade_plan is not None
    assert (
        projection.trade_plan.entry,
        projection.trade_plan.stop,
        projection.trade_plan.canonical_target,
        projection.trade_plan.invalidation_reference,
        projection.trade_plan.risk_reward_ratio,
    ) == (
        Decimal("100.00"), Decimal("90.00"), Decimal("120.00"),
        Decimal("90.00"), Decimal("2"),
    )
    assert projection.handoff.handoff_identity in projection.trade_plan.provenance
    assert projection.handoff.integrity_sha256 in projection.trade_plan.provenance
    assert projection.risk_state == "RISK_UNAVAILABLE"
    assert not projection.sponsor_controls_available
    assert projection.kr380_entry_timing_state == "NOT ESTABLISHED"

    restored = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    restored.restore((completed,))
    assert restored.project(
        completed.requirement.native_run_identity,
        completed.requirement.canonical_instrument,
    ) == projection


def test_existing_step31_constructs_exact_short_geometry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path, direction=V1Direction.SHORT)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    projection = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )

    assert projection.kr370_classification == "SELL_NOW"
    assert projection.state is TradeWindowState.TRADE_PLAN_READY
    assert projection.trade_plan is not None
    assert (
        projection.trade_plan.entry,
        projection.trade_plan.stop,
        projection.trade_plan.canonical_target,
        projection.trade_plan.invalidation_reference,
        projection.trade_plan.risk_reward_ratio,
    ) == (
        Decimal("95.00"), Decimal("110.00"), Decimal("80.00"),
        Decimal("110.00"), Decimal("1"),
    )


def test_step31_failure_is_not_persisted_as_a_trade_plan(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    plan_store = LocalTradePlanStore(tmp_path / "plans")
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"), plan_store
    )
    projection = workflow.construct(
        completed,
        _evidence(completed, complete=False),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )

    assert projection.state is TradeWindowState.TRADE_PLAN_UNAVAILABLE
    assert projection.reason == "ENTRY_AUTHORITY_UNAVAILABLE"
    assert projection.trade_plan is None
    assert plan_store.load_for_requirements((completed.requirement,)) == ()
