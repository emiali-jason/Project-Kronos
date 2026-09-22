import copy
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

import pytest

from kronos.instrument.facts import CanonicalInstrumentContext, InstrumentContextStatus
from kronos.application.swing_trade_window import (
    LocalTradePlanConstructionDiagnosticStore,
    SwingTradeWindowWorkflow,
    TradePlanConstructionAttemptResult,
    TradePlanConstructionStage,
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
    create_kr370_step31_handoff_v2,
    Kr370Step31EligibilityHandoffV2,
)
from kronos.swing.v1.analytical_promotion_v2 import create_record, _time
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
from tests.unit.swing.v1.test_analytical_promotion_v2 import (
    source as v2_source, criteria as v2_criteria, nse as v2_nse, mcx as v2_mcx,
)
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


def _v2_completed(tmp_path, *, direction=V1Direction.LONG, confirmation=True):
    completed = _completed(tmp_path, direction=direction)
    source = v2_source(direction=direction.value)
    source.update(
        native_run_identity=completed.requirement.native_run_identity,
        canonical_instrument=completed.requirement.canonical_instrument,
        native_opportunity_identity=completed.requirement.thesis.opportunity_identity.value,
        native_assessment_sha256=completed.requirement.thesis.native_assessment_sha256,
        native_requirement_sha256=completed.requirement.requirement_sha256,
        analysis_boundary=_time(completed.readiness.analysis_boundary),
        observation_boundaries=[
            dict(timeframe=item.timeframe.value, boundary=_time(item.observation_boundary))
            for item in completed.requirement.thesis.timeframe_facts
        ],
    )
    source["acceptance"]["review_pack_identity"] = completed.review_pack.review_pack_id
    for item in source["acceptance"]["visual_bindings"]:
        response = next(x for x in completed.responses if x.timeframe.value == item["timeframe"])
        item["chart_sha256"] = response.chart_revision_sha256
        item["evidence_integrity_sha256"] = response.evidence_sha256
    relative = v2_nse(
        direction=direction.value,
        states=(("OUTPERFORMING", "OUTPERFORMING") if direction is V1Direction.LONG
                else ("UNDERPERFORMING", "UNDERPERFORMING"))
        if confirmation else ("EQUAL", "EQUAL"),
    )
    promotion = create_record(
        source=source, criteria=v2_criteria(), confirmation=relative, created_at=NOW
    )
    return replace(completed, promotion_v2=promotion)


def _price(identity: str, value: str, boundary: datetime) -> AuthoritativePriceEvidence:
    return AuthoritativePriceEvidence(
        identity,
        sha256(identity.encode()).hexdigest(),
        Decimal(value),
        boundary,
        f"GOVERNED:COMPLETED_4H:{identity}",
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


@pytest.mark.parametrize("direction", (V1Direction.LONG, V1Direction.SHORT))
def test_v2_exact_now_handoff_keeps_step31_geometry_and_restores_distinct_version(
    tmp_path, direction,
) -> None:
    completed = _v2_completed(tmp_path, direction=direction)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    projection = workflow.construct(
        completed, _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.readiness.analysis_boundary,
        created_at=NOW,
    )
    assert type(projection.handoff) is Kr370Step31EligibilityHandoffV2
    assert projection.handoff.kr370_record_identity == completed.promotion_v2.identity
    assert projection.trade_plan is not None
    original = _completed(tmp_path, direction=direction)
    v1 = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "v1-handoffs"),
        LocalTradePlanStore(tmp_path / "v1-plans"),
    ).construct(
        original, _evidence(original),
        _context(original.requirement.canonical_instrument),
        current_run_identity=original.requirement.native_run_identity,
        current_analysis_boundary=original.readiness.analysis_boundary,
        created_at=NOW,
    )
    assert v1.trade_plan is not None
    assert (projection.trade_plan.entry, projection.trade_plan.stop,
            projection.trade_plan.canonical_target, projection.trade_plan.risk_reward_ratio) == (
        v1.trade_plan.entry, v1.trade_plan.stop,
        v1.trade_plan.canonical_target, v1.trade_plan.risk_reward_ratio)
    restored = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    restored.restore((completed,))
    assert restored.project(completed.requirement.native_run_identity,
                            completed.requirement.canonical_instrument) == projection


def test_v2_ready_cannot_publish_step31_handoff(tmp_path) -> None:
    completed = _v2_completed(tmp_path, confirmation=False)
    assert completed.promotion_v2.value["promotion_state"] == "BUY_READY"
    with pytest.raises(Kr370Step31HandoffRejected, match="NOT_CONFIRMED_NOW"):
        create_kr370_step31_handoff_v2(
            completed.requirement, completed.readiness, completed.promotion_v2,
            current_run_identity=completed.requirement.native_run_identity,
            current_analysis_boundary=completed.readiness.analysis_boundary,
            created_at=NOW,
        )


def test_mcx_v2_now_is_analytical_only_and_step31_not_commissioned(tmp_path) -> None:
    completed = _completed(tmp_path)
    mcx = create_record(
        source=v2_source(market="MCX"), criteria=v2_criteria(),
        confirmation=v2_mcx(), created_at=NOW)
    assert mcx.value["promotion_state"] == "BUY_NOW"
    with pytest.raises(Kr370Step31HandoffRejected, match="MCX_STEP31_NOT_COMMISSIONED"):
        create_kr370_step31_handoff_v2(
            completed.requirement, completed.readiness, mcx,
            current_run_identity=completed.requirement.native_run_identity,
            current_analysis_boundary=completed.readiness.analysis_boundary,
            created_at=NOW,
        )


def test_equity_cannot_claim_index_self_comparison_exemption(tmp_path) -> None:
    from tests.unit.swing.v1.test_analytical_promotion_v2 import index as v2_index

    completed = _completed(tmp_path)
    source = v2_source(asset_class="NSE_INDEX",
                       instrument=completed.requirement.canonical_instrument)
    record = create_record(source=source, criteria=v2_criteria(),
                           confirmation=v2_index(), created_at=NOW)
    with pytest.raises(Kr370Step31HandoffRejected, match="ASSET_CLASS_MISMATCH"):
        create_kr370_step31_handoff_v2(
            completed.requirement, completed.readiness, record,
            current_run_identity=completed.requirement.native_run_identity,
            current_analysis_boundary=completed.readiness.analysis_boundary,
            created_at=NOW,
        )


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

    assert projection.state is TradeWindowState.STEP31_OBSERVATION_AVAILABLE
    assert projection.reason == "STEP31_OBSERVATION_AVAILABLE"
    assert projection.trade_plan is None
    assert projection.step31_observation is not None
    assert projection.step31_observation.entry is None
    assert plan_store.load_for_requirements((completed.requirement,)) == ()


def test_construction_failures_are_immutable_stage_specific_and_restart_safe(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    store = LocalTradePlanConstructionDiagnosticStore(tmp_path / "diagnostics")
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
        diagnostic_store=store,
    )
    for offset, stage in enumerate((
        TradePlanConstructionStage.REQUEST_PARSE,
        TradePlanConstructionStage.CURRENT_BINDING,
        TradePlanConstructionStage.PROVIDER_CAPABILITY,
        TradePlanConstructionStage.EXECUTION_CONTEXT,
        TradePlanConstructionStage.EVIDENCE_PACKAGE,
    )):
        workflow.retain_construction_attempt(
            attempt_identity=f"{offset + 1:064x}",
            run_identity=completed.requirement.native_run_identity,
            canonical_instrument=completed.requirement.canonical_instrument,
            native_assessment_sha256=completed.requirement.thesis.native_assessment_sha256,
            attempt_timestamp=NOW.replace(microsecond=offset),
            stage=stage,
            result=TradePlanConstructionAttemptResult.FAILED,
            safe_failure_code="TRADE_PLAN_CONSTRUCTION_UNAVAILABLE",
            safe_bounded_reason=(
                "The current governed evidence could not complete Trade Plan construction."
            ),
        )
    assert len(store.load()) == 5
    with pytest.raises(
        ValueError, match="TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_INVALID"
    ):
        workflow.retain_construction_attempt(
            attempt_identity="f" * 64,
            run_identity=completed.requirement.native_run_identity,
            canonical_instrument=completed.requirement.canonical_instrument,
            native_assessment_sha256=(
                completed.requirement.thesis.native_assessment_sha256
            ),
            attempt_timestamp=NOW,
            stage=TradePlanConstructionStage.EVIDENCE_PACKAGE,
            result=TradePlanConstructionAttemptResult.FAILED,
            safe_failure_code="TRADE_PLAN_CONSTRUCTION_UNAVAILABLE",
            safe_bounded_reason="raw token or filesystem detail",
        )
    assert len(store.load()) == 5
    assert workflow.latest_construction_attempt(
        completed.requirement.native_run_identity,
        completed.requirement.canonical_instrument,
    ).stage is TradePlanConstructionStage.EVIDENCE_PACKAGE
    assert LocalTradePlanStore(tmp_path / "plans").load_for_requirements(
        (completed.requirement,)
    ) == ()
    assert LocalKr370Step31HandoffStore(tmp_path / "handoffs").load_exact(
        completed.requirement.native_run_identity,
        completed.requirement.canonical_instrument,
        completed.requirement.thesis.native_assessment_sha256,
        completed.promotion.integrity_sha256,
    ) is None

    restored = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
        diagnostic_store=store,
    )
    assert restored.latest_construction_attempt(
        completed.requirement.native_run_identity,
        completed.requirement.canonical_instrument,
    ).attempt_identity == f"{5:064x}"
