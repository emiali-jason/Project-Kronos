from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.application.swing_native_review import (
    NativeReviewRunState,
    NativeReviewWorkflowSnapshot,
)
from kronos.application.swing_trade_window import (
    GovernedKr380EntryOutcomeReference,
    GovernedModelLifecycleReference,
    Kr380EntryTimingState,
    SwingTradeWindowWorkflow,
    build_current_trade_construction_evidence,
)
from kronos.browser.views import render_native_trade_window, render_trade_journal
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.swing.v1.kr370_step31_handoff import LocalKr370Step31HandoffStore
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveTradeLifecycleService,
    GovernedLifecycleObservation,
    LocalActiveTradeLifecycleStore,
)
from kronos.swing.v1.native_sponsor_decision import (
    LocalSponsorDecisionStore,
    SponsorTradeChoice,
    create_trade_plan_business_judgment,
    initiate_sponsor_decision,
    record_trade_plan_risk_result,
)
from kronos.swing.v1.native_trade_construction import LocalTradePlanStore
from kronos.swing.v1.native_entry_timing import (
    LocalPortfolioStateV1Store,
    LocalRiskPermissionV1Store,
)
from kronos.swing.v1.native_trade_journal import (
    LocalTradeJournalStore,
    TradeJournalService,
)
from kronos.swing.v1.step32 import ObjectiveModelState, RiskState
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorActivationDisposition,
)
from kronos.swing.v1.observation_research_ledger import ObservationLinkKind
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.swing.v1.test_kr370_step31_handoff import (
    NOW,
    _completed,
    _context,
    _evidence,
)


def _workflow(tmp_path, *, short=False):  # type: ignore[no-untyped-def]
    completed = _completed(
        tmp_path,
        **({"direction": completed_direction()} if short else {}),
    )
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
    return completed, workflow, projection.trade_plan


def completed_direction():  # type: ignore[no-untyped-def]
    from kronos.swing.v1.models import V1Direction

    return V1Direction.SHORT


def _risk(plan, state=RiskState.APPROVED):  # type: ignore[no-untyped-def]
    judgment = create_trade_plan_business_judgment(
        plan, validation_identity="UX07-CONTROLLED", created_at=NOW,
    )
    risk = record_trade_plan_risk_result(
        plan, judgment, state, reason=state.value, evaluated_at=NOW,
    )
    return judgment, risk


def _kr380(plan, risk, state):  # type: ignore[no-untyped-def]
    return GovernedKr380EntryOutcomeReference(
        "KR380-OUTCOME-UX07", plan.native_run_identity,
        plan.canonical_instrument, plan.trade_plan_id, plan.integrity_hash,
        risk.risk_result_id, plan.execution_context_identity,
        "KR380-MONITORING-UX07", state, NOW, ("OBSERVATION-UX07",),
        "8" * 64,
    )


def _model(plan, risk, outcome, state, *, close_reason=None):  # type: ignore[no-untyped-def]
    return GovernedModelLifecycleReference(
        "MODEL-TRADE-UX07", plan.native_run_identity,
        plan.canonical_instrument, plan.trade_plan_id, plan.integrity_hash,
        risk.risk_result_id, outcome.entry_outcome_id, state,
        MonitoringConnectionState.CONNECTED, NOW, "9" * 64, close_reason,
    )


def _review(completed, plan, *, risk=(), sponsor=(), lifecycle=None, journal=None):  # type: ignore[no-untyped-def]
    values = dict(
        state=NativeReviewRunState.REVIEW_REQUIRED,
        native_run_identity=completed.requirement.native_run_identity,
        requirements=(completed.requirement,),
        layer2_records=(),
        trade_plans=(plan,),
        sponsor_initiations=sponsor,
        risk_records=risk,
    )
    if lifecycle is not None:
        values["active_lifecycle"] = lifecycle
    if journal is not None:
        values["trade_journal"] = journal
    return NativeReviewWorkflowSnapshot(**values)


def _observation(position, number, price):  # type: ignore[no-untyped-def]
    stamp = NOW + timedelta(minutes=number)
    return GovernedLifecycleObservation(
        f"UX07-OBS-{number}", position.canonical_instrument, Decimal(price),
        stamp, stamp, "KITE_CONNECT_WEBSOCKET", "UX07-KITE", number,
        True, True, True, "NSE-CM", "NSE-CALENDAR-2026", "2026.1",
        "NSE-SESSION", "NSE-WINDOW",
        ("KITE_CONNECT_WEBSOCKET", "DOMAIN-002", "DOMAIN-008"),
    )


@pytest.mark.parametrize(
    ("short", "state", "label"),
    (
        (False, Kr380EntryTimingState.NO_TRIGGER, "NO_TRIGGER"),
        (False, Kr380EntryTimingState.LONG_ENTRY_TRIGGERED, "LONG_ENTRY_TRIGGERED"),
        (True, Kr380EntryTimingState.SHORT_ENTRY_TRIGGERED, "SHORT_ENTRY_TRIGGERED"),
    ),
)
def test_exact_risk_and_current_kr380_states_project_without_recalculation(
    tmp_path, short, state, label,
) -> None:
    completed, workflow, plan = _workflow(tmp_path, short=short)
    _, risk = _risk(plan)
    outcome = _kr380(plan, risk, state)
    workflow.synchronize_downstream(
        _review(completed, plan, risk=(risk,)), kr380_outcomes=(outcome,),
    )

    projection = workflow.project(plan.native_run_identity, plan.canonical_instrument)
    assert projection.risk_state == "RISK_APPROVED"
    assert projection.kr380_entry_timing_state == label
    html = render_native_trade_window(_ready(), projection)
    expected = {
        "NO_TRIGGER": "WAITING FOR ENTRY TRIGGER",
        "LONG_ENTRY_TRIGGERED": "ENTRY TRIGGERED — LONG",
        "SHORT_ENTRY_TRIGGERED": "ENTRY TRIGGERED — SHORT",
    }[label]
    assert expected in html


def test_current_portfolio_and_domain007_are_persisted_and_idempotent(
    tmp_path,
) -> None:
    completed = _completed(tmp_path)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
        LocalPortfolioStateV1Store(tmp_path / "portfolio"),
        LocalRiskPermissionV1Store(tmp_path / "risk"),
    )
    projection = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    plan = projection.trade_plan
    assert plan is not None
    portfolio = workflow.publish_current_portfolio_state(
        _review(completed, plan),
        native_run_identity=plan.native_run_identity,
        as_of_boundary=plan.observation_boundary,
    )
    first = workflow.evaluate_current_risk(
        plan.native_run_identity, plan.canonical_instrument, evaluated_at=NOW,
    )
    second = workflow.evaluate_current_risk(
        plan.native_run_identity,
        plan.canonical_instrument,
        evaluated_at=NOW + timedelta(minutes=1),
    )

    assert portfolio.sources_complete
    assert portfolio.objective_exposures == ()
    assert portfolio.sponsor_exposures == ()
    assert first.state is RiskState.APPROVED
    assert first.reason_codes == ("NO_GOVERNED_PROHIBITION",)
    assert second.risk_result_id == first.risk_result_id
    workflow.mark_sponsor_controls_available(plan.trade_plan_id)
    ready = workflow.project(plan.native_run_identity, plan.canonical_instrument)
    html = render_native_trade_window(_ready(), ready)
    assert "RISK APPROVED" in html
    assert "NO GOVERNED PROHIBITION" in html
    assert "PAPER</button>" in html
    assert "LIVE</button>" in html
    assert "IGNORE</button>" in html


def test_production_step31_evidence_uses_only_completed_governed_machine_facts(
    tmp_path,
) -> None:
    completed = _completed(tmp_path)

    evidence = build_current_trade_construction_evidence(completed)

    assert evidence.native_run_identity == completed.requirement.native_run_identity
    assert evidence.native_assessment_sha256 == completed.requirement.thesis.native_assessment_sha256
    assert evidence.qualification_candle is not None
    assert evidence.qualification_candle.completed
    assert "KITE_NORMALIZED_HISTORICAL" in evidence.qualification_candle.source
    assert "QUOTE" not in " ".join(evidence.provenance)
    assert "VISUAL" not in evidence.qualification_candle.source


def test_plan_portfolio_and_risk_restore_under_exact_current_binding(tmp_path) -> None:
    completed = _completed(tmp_path)
    handoffs = LocalKr370Step31HandoffStore(tmp_path / "handoffs")
    plans = LocalTradePlanStore(tmp_path / "plans")
    portfolios = LocalPortfolioStateV1Store(tmp_path / "portfolio")
    risks = LocalRiskPermissionV1Store(tmp_path / "risk")
    initial = SwingTradeWindowWorkflow(handoffs, plans, portfolios, risks)
    projection = initial.construct(
        completed, _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    plan = projection.trade_plan
    assert plan is not None
    initial.publish_current_portfolio_state(
        _review(completed, plan), native_run_identity=plan.native_run_identity,
        as_of_boundary=plan.observation_boundary,
    )
    risk = initial.evaluate_current_risk(
        plan.native_run_identity, plan.canonical_instrument, evaluated_at=NOW,
    )

    restored = SwingTradeWindowWorkflow(handoffs, plans, portfolios, risks)
    restored.restore((completed,))
    inputs = restored.current_operability_inputs(
        plan.native_run_identity, plan.canonical_instrument,
    )

    assert inputs is not None
    assert inputs[0] == plan
    assert inputs[1] == risk

    initial.publish_portfolio_state(
        cycle_identity="PORTFOLIO-CYCLE-SUPERSEDING",
        as_of_boundary=plan.observation_boundary + timedelta(minutes=1),
        objective_exposures=(), sponsor_exposures=(), source_identities=(
            "OBJECTIVE-MODEL-STORE", "SPONSOR-POSITION-STORE",
        ), sources_complete=True, provenance=("DOMAIN-005", "ADR-0013"),
    )
    stale = SwingTradeWindowWorkflow(handoffs, plans, portfolios, risks)
    stale.restore((completed,))
    assert stale.current_operability_inputs(
        plan.native_run_identity, plan.canonical_instrument,
    ) is None


def test_absent_or_rejected_risk_and_foreign_kr380_fail_closed(tmp_path) -> None:
    completed, workflow, plan = _workflow(tmp_path)
    _, rejected = _risk(plan, RiskState.REJECTED)
    outcome = _kr380(plan, rejected, Kr380EntryTimingState.LONG_ENTRY_TRIGGERED)
    workflow.synchronize_downstream(
        _review(completed, plan, risk=(rejected,)), kr380_outcomes=(outcome,),
    )
    projection = workflow.project(plan.native_run_identity, plan.canonical_instrument)
    assert projection.risk_state == "RISK_REJECTED"
    assert projection.kr380_entry_timing_state == "NOT ESTABLISHED"
    assert "STALE_OR_MISMATCHED_KR380_ENTRY_OUTCOME" in projection.continuity_warnings

    _, approved = _risk(plan)
    for foreign in (
        replace(outcome, native_run_identity="SWING-RUN-" + "F" * 32),
        replace(outcome, trade_plan_id="FOREIGN-TRADE-PLAN"),
    ):
        workflow.synchronize_downstream(
            _review(completed, plan, risk=(approved,)), kr380_outcomes=(foreign,),
        )
        assert workflow.project(
            plan.native_run_identity, plan.canonical_instrument,
        ).kr380_entry_timing_state == "NOT ESTABLISHED"


def test_model_and_sponsor_position_are_separate_authority_branches(tmp_path) -> None:
    completed, workflow, plan = _workflow(tmp_path)
    judgment, risk = _risk(plan)
    outcome = _kr380(plan, risk, Kr380EntryTimingState.LONG_ENTRY_TRIGGERED)
    model = _model(plan, risk, outcome, ObjectiveModelState.ACTIVE)
    workflow.synchronize_downstream(
        _review(completed, plan, risk=(risk,)),
        kr380_outcomes=(outcome,), model_lifecycles=(model,),
    )
    projection = workflow.project(plan.native_run_identity, plan.canonical_instrument)
    assert projection.model_lifecycle_state == "MODEL_TRADE_ACTIVE"
    assert projection.sponsor_position_state == "NO SPONSOR POSITION"

    initiation = initiate_sponsor_decision(
        plan, judgment, risk, _context(plan.canonical_instrument),
        SponsorTradeChoice.PAPER, current_trade_plan_id=plan.trade_plan_id,
        decided_at=NOW,
    )
    lifecycle = ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore((tmp_path / "lifecycle").resolve())
    )
    lifecycle.register(initiation, plan)
    workflow.synchronize_downstream(
        _review(
            completed, plan, risk=(risk,), sponsor=(initiation,),
            lifecycle=lifecycle.snapshot(),
        ),
        kr380_outcomes=(outcome,), model_lifecycles=(model,),
    )
    projection = workflow.project(plan.native_run_identity, plan.canonical_instrument)
    assert projection.model_lifecycle_state == "MODEL_TRADE_ACTIVE"
    assert projection.sponsor_position_state == "PAPER · PAPER_ARMED"
    assert projection.model_trade_id != projection.sponsor_position_id


def test_closed_chain_restores_and_links_exact_step33_record(tmp_path) -> None:
    completed, workflow, plan = _workflow(tmp_path)
    judgment, risk = _risk(plan)
    outcome = _kr380(plan, risk, Kr380EntryTimingState.LONG_ENTRY_TRIGGERED)
    initiation = initiate_sponsor_decision(
        plan, judgment, risk, _context(plan.canonical_instrument),
        SponsorTradeChoice.PAPER, current_trade_plan_id=plan.trade_plan_id,
        decided_at=NOW,
    )
    sponsor_store = LocalSponsorDecisionStore((tmp_path / "sponsor").resolve())
    sponsor_store.retain(initiation)
    lifecycle_root = (tmp_path / "lifecycle").resolve()
    lifecycle = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(lifecycle_root))
    position = lifecycle.register(initiation, plan)
    lifecycle.observe(position.position_id, _observation(position, 1, "99"))
    active = lifecycle.observe(position.position_id, _observation(position, 2, "102"))
    lifecycle.observe(active.position_id, _observation(active, 3, "122"))
    closure = lifecycle.snapshot().closures[0]
    journal_root = (tmp_path / "journal").resolve()
    journal = TradeJournalService(LocalTradeJournalStore(journal_root))
    journal_snapshot = journal.reconcile(
        (plan,), (completed.readiness,), (initiation,), lifecycle.snapshot(),
    )
    model = _model(
        plan, risk, outcome, ObjectiveModelState.CLOSED,
        close_reason="TARGET",
    )
    workflow.synchronize_downstream(
        _review(
            completed, plan, risk=(risk,), sponsor=(initiation,),
            lifecycle=lifecycle.snapshot(), journal=journal_snapshot,
        ),
        kr380_outcomes=(outcome,), model_lifecycles=(model,),
    )
    projection = workflow.project(plan.native_run_identity, plan.canonical_instrument)
    assert projection.closure_id == closure.closure_id
    assert projection.closure_reason == closure.exit_reason.value
    assert projection.journal_record_id == journal_snapshot.records[0].journal_record_id
    html = render_native_trade_window(_ready(), projection)
    assert "CLOSED" in html and "OPEN JOURNAL" in html
    assert f"/journal?record={projection.journal_record_id}" in html

    restored = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    restored.restore((completed,))
    restored_lifecycle = ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore(lifecycle_root)
    ).snapshot()
    restored_journal = TradeJournalService(
        LocalTradeJournalStore(journal_root)
    ).snapshot()
    restored_initiation = sponsor_store.load_plan(
        plan.native_run_identity, plan.trade_plan_id,
    )
    restored.synchronize_downstream(
        _review(
            completed, plan, risk=(risk,), sponsor=(restored_initiation,),
            lifecycle=restored_lifecycle, journal=restored_journal,
        ),
        kr380_outcomes=(outcome,), model_lifecycles=(model,),
    )
    assert restored.project(
        plan.native_run_identity, plan.canonical_instrument,
    ).journal_record_id == projection.journal_record_id

    journal_html = render_trade_journal(
        _ready(), restored_journal,
        selected_record_id=projection.journal_record_id,
    )
    assert projection.journal_record_id in journal_html


def test_observation_research_automatically_links_governed_downstream_chain(tmp_path) -> None:
    completed, workflow, plan = _workflow(tmp_path)
    judgment, risk = _risk(plan)
    outcome = _kr380(plan, risk, Kr380EntryTimingState.LONG_ENTRY_TRIGGERED)
    initiation = initiate_sponsor_decision(
        plan, judgment, risk, _context(plan.canonical_instrument),
        SponsorTradeChoice.PAPER, current_trade_plan_id=plan.trade_plan_id,
        decided_at=NOW,
    )
    lifecycle = ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore((tmp_path / "research-lifecycle").resolve())
    )
    position = lifecycle.register(initiation, plan)
    workflow.synchronize_downstream(
        _review(
            completed, plan, risk=(risk,), sponsor=(initiation,),
            lifecycle=lifecycle.snapshot(),
        ),
        kr380_outcomes=(outcome,),
        model_lifecycles=(_model(plan, risk, outcome, ObjectiveModelState.ACTIVE),),
    )
    observation = workflow.project(
        plan.native_run_identity, plan.canonical_instrument
    ).step31_observation
    assert observation is not None
    workflow.record_sponsor_observation_choice(
        plan.native_run_identity, plan.canonical_instrument,
        plan.native_assessment_sha256, observation.observation_evidence_id,
        SponsorTradeChoice.PAPER, SponsorActivationDisposition.ACTIVATED,
        current_run_identity=plan.native_run_identity, decided_at=NOW,
        warning_acknowledged=False, risk_identity=risk.risk_result_id,
        risk_state="RISK_APPROVED",
        existing_sponsor_decision_identity=initiation.decision.decision_id,
        sponsor_position_identity=position.position_id,
    )
    lifecycle.observe(position.position_id, _observation(position, 1, "99"))
    active = lifecycle.observe(position.position_id, _observation(position, 2, "102"))
    lifecycle.observe(active.position_id, _observation(active, 3, "122"))
    closed_model = _model(
        plan, risk, outcome, ObjectiveModelState.CLOSED, close_reason="TARGET"
    )
    workflow.synchronize_downstream(
        _review(
            completed, plan, risk=(risk,), sponsor=(initiation,),
            lifecycle=lifecycle.snapshot(),
        ),
        kr380_outcomes=(outcome,), model_lifecycles=(closed_model,),
    )

    research = workflow.observation_research_snapshot()
    assert len(research) == 1
    assert {item.kind for item in research[0].links} == {
        ObservationLinkKind.KR380_ENTRY_OUTCOME,
        ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME,
        ObservationLinkKind.SPONSOR_POSITION,
        ObservationLinkKind.SPONSOR_POSITION_OUTCOME,
    }
    assert research[0].objective_outcome_available
    assert research[0].sponsor_position_outcome_available


def test_journal_absence_creates_no_action(tmp_path) -> None:
    completed, workflow, plan = _workflow(tmp_path)
    workflow.synchronize_downstream(_review(completed, plan))
    projection = workflow.project(plan.native_run_identity, plan.canonical_instrument)
    html = render_native_trade_window(_ready(), projection)
    assert projection.risk_state == "RISK_UNAVAILABLE"
    assert projection.kr380_entry_timing_state == "NOT ESTABLISHED"
    assert projection.model_lifecycle_state == "NOT ESTABLISHED"
    assert projection.sponsor_position_state == "NO SPONSOR POSITION"
    assert projection.journal_record_id is None
    assert "OPEN JOURNAL" not in html
    assert "No journal record is manufactured" in html
