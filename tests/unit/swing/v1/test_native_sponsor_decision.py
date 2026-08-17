from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.swing.v1.native_sponsor_decision import (
    LocalSponsorDecisionStore,
    SPONSOR_TRADE_DECISION_POLICY_ID,
    SponsorExecutionMode,
    SponsorInitiationState,
    SponsorTradeChoice,
    create_trade_plan_business_judgment,
    initiate_sponsor_decision,
    record_trade_plan_risk_result,
)
from kronos.swing.v1.native_trade_construction import construct_trade_plan
from kronos.swing.v1.step32 import RiskConstraints, RiskState
from tests.unit.swing.v1.test_native_trade_construction import NOW, _context, _package, _price, _ready
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.swing.v1.native_review import NativeLayer2EvidenceState, NativeReviewEvidenceStore
from tests.unit.swing.v1.test_native_readiness import _complete_visual_pairs
from tests.unit.swing.v1.test_native_review import _evidence_run, _layer2


def _inputs(state: RiskState = RiskState.APPROVED, constraints: RiskConstraints | None = None):  # type: ignore[no-untyped-def]
    readiness, requirement = _ready()
    context = _context(requirement.canonical_instrument)
    plan = construct_trade_plan(
        requirement, readiness, _package(requirement, readiness), context, created_at=NOW,
    )
    judgment = create_trade_plan_business_judgment(plan, validation_identity="VALIDATION-1", created_at=NOW)
    risk = record_trade_plan_risk_result(
        plan, judgment, state, reason=state.value, evaluated_at=NOW,
        constraints=constraints,
    )
    return plan, judgment, risk, context


def _go(choice: SponsorTradeChoice, *, state=RiskState.APPROVED, constraints=None, **kwargs):  # type: ignore[no-untyped-def]
    plan, judgment, risk, context = _inputs(state, constraints)
    result = initiate_sponsor_decision(
        plan, judgment, risk, context, choice,
        current_trade_plan_id=plan.trade_plan_id, decided_at=NOW, **kwargs,
    )
    return result, plan, judgment, risk, context


def test_policy_and_ready_approved_input_gate() -> None:
    result, *_ = _go(SponsorTradeChoice.PAPER)
    assert result.state is SponsorInitiationState.PAPER_ARMED
    assert result.decision.policy_identity == SPONSOR_TRADE_DECISION_POLICY_ID


def test_unavailable_plan_and_rejected_or_unavailable_risk_do_not_activate() -> None:
    readiness, requirement = _ready()
    context = _context(requirement.canonical_instrument)
    unavailable_plan = construct_trade_plan(
        requirement, readiness,
        _package(requirement, readiness, prior_directional_swing_high=None),
        context, created_at=NOW,
    )
    plan, judgment, risk, _ = _inputs()
    unavailable = initiate_sponsor_decision(
        unavailable_plan, judgment, risk, context, SponsorTradeChoice.PAPER,
        current_trade_plan_id=unavailable_plan.trade_plan_id, decided_at=NOW,
    )
    assert unavailable.state is SponsorInitiationState.DECISION_UNAVAILABLE
    assert unavailable.reason == "TRADE_PLAN_NOT_READY"
    rejected, *_ = _go(SponsorTradeChoice.PAPER, state=RiskState.REJECTED)
    assert rejected.state is SponsorInitiationState.DECISION_UNAVAILABLE
    waiting, *_ = _go(SponsorTradeChoice.PAPER, state=RiskState.UNAVAILABLE)
    assert waiting.state is SponsorInitiationState.WAITING_FOR_RISK
    assert waiting.decision is waiting.position is None


def test_paper_go_arms_one_lot_without_actual_entry_or_quote() -> None:
    result, plan, _, _, _ = _go(SponsorTradeChoice.PAPER)
    assert result.state is SponsorInitiationState.PAPER_ARMED
    assert result.reason == "WAITING_FOR_ENTRY"
    assert result.position.lots == 1
    assert result.position.actual_entry is None
    assert result.position.entry_timestamp is None
    assert result.position.model_entry == plan.entry
    assert (result.position.stop, result.position.target) == (plan.stop, plan.canonical_target)


def test_paper_quantity_is_locked_and_cannot_be_overridden() -> None:
    result, *_ = _go(SponsorTradeChoice.PAPER, paper_lots=2)
    assert result.state is SponsorInitiationState.DECISION_UNAVAILABLE
    assert result.reason == "PAPER_QUANTITY_LOCKED_TO_ONE_LOT"
    assert result.position is None


@pytest.mark.parametrize("entry,lots", ((None, 1), (Decimal("101"), 0), (Decimal("101"), -1), (Decimal("101"), 1.5)))
def test_live_requires_actual_entry_and_positive_integer_lots(entry, lots) -> None:  # type: ignore[no-untyped-def]
    result, *_ = _go(SponsorTradeChoice.LIVE, actual_live_entry=entry, live_lots=lots)
    assert result.state is SponsorInitiationState.DECISION_UNAVAILABLE
    assert result.position is None


def test_live_go_preserves_distinct_actual_and_model_entry() -> None:
    result, plan, *_ = _go(
        SponsorTradeChoice.LIVE, actual_live_entry=Decimal("103.25"), live_lots=2,
    )
    assert result.state is SponsorInitiationState.LIVE_ACTIVE
    assert result.position.actual_entry == Decimal("103.25")
    assert result.position.model_entry == plan.entry
    assert result.position.lots == 2
    assert result.position.underlying_quantity == 2 * result.position.lot_size
    assert result.decision.model_entry == plan.entry


def test_risk_constrained_maximum_lots_rejects_without_silent_reduction() -> None:
    constraints = RiskConstraints(maximum_lots=1)
    result, *_ = _go(
        SponsorTradeChoice.LIVE, state=RiskState.CONSTRAINED,
        constraints=constraints, actual_live_entry=Decimal("101"), live_lots=2,
    )
    assert result.state is SponsorInitiationState.DECISION_UNAVAILABLE
    assert result.reason == "RISK_MAXIMUM_LOTS_EXCEEDED"
    assert result.position is None


def test_risk_constrained_with_satisfied_maximum_lots_allows_live() -> None:
    result, *_ = _go(
        SponsorTradeChoice.LIVE, state=RiskState.CONSTRAINED,
        constraints=RiskConstraints(maximum_lots=2),
        actual_live_entry=Decimal("101"), live_lots=2,
    )
    assert result.state is SponsorInitiationState.LIVE_ACTIVE
    assert result.position.lots == 2


def test_risk_quantity_notional_and_capital_constraints_are_enforced() -> None:
    for constraints, reason in (
        (RiskConstraints(maximum_quantity=Decimal("0.5")), "RISK_MAXIMUM_QUANTITY_EXCEEDED"),
        (RiskConstraints(maximum_notional=Decimal("50")), "RISK_MAXIMUM_NOTIONAL_EXCEEDED"),
        (RiskConstraints(maximum_capital_at_risk=Decimal("5")), "RISK_MAXIMUM_CAPITAL_AT_RISK_EXCEEDED"),
    ):
        result, *_ = _go(
            SponsorTradeChoice.LIVE, state=RiskState.CONSTRAINED,
            constraints=constraints, actual_live_entry=Decimal("101"), live_lots=1,
        )
        assert result.reason == reason


def test_ignore_is_terminal_decision_without_position() -> None:
    result, *_ = _go(SponsorTradeChoice.IGNORE)
    assert result.state is SponsorInitiationState.IGNORED
    assert result.decision.decision is SponsorTradeChoice.IGNORE
    assert result.decision.go_timestamp is None
    assert result.position is None


def test_superseded_plan_expired_risk_and_binding_mismatch_fail_closed() -> None:
    plan, judgment, risk, context = _inputs()
    superseded = initiate_sponsor_decision(
        plan, judgment, risk, context, SponsorTradeChoice.PAPER,
        current_trade_plan_id="TRADE-PLAN-" + "f" * 64, decided_at=NOW,
    )
    assert superseded.reason == "TRADE_PLAN_SUPERSEDED"
    expired = replace(risk, valid_until=NOW - timedelta(seconds=1))
    assert initiate_sponsor_decision(
        plan, judgment, expired, context, SponsorTradeChoice.PAPER,
        current_trade_plan_id=plan.trade_plan_id, decided_at=NOW,
    ).reason == "RISK_BINDING_INVALID"
    foreign = replace(judgment, canonical_instrument_echo="FOREIGN")
    assert initiate_sponsor_decision(
        plan, foreign, risk, context, SponsorTradeChoice.PAPER,
        current_trade_plan_id=plan.trade_plan_id, decided_at=NOW,
    ).reason == "BUSINESS_JUDGMENT_BINDING_INVALID"


def test_broker_managed_execution_is_reserved_and_non_executable() -> None:
    result, *_ = _go(
        SponsorTradeChoice.PAPER,
        execution_mode=SponsorExecutionMode.BROKER_MANAGED_EXECUTION,
    )
    assert result.state is SponsorInitiationState.DECISION_UNAVAILABLE
    assert result.reason == "BROKER_MANAGED_EXECUTION_RESERVED"


def test_store_is_idempotent_rejects_mode_conversion_and_restores(tmp_path) -> None:  # type: ignore[no-untyped-def]
    paper, plan, judgment, risk, context = _go(SponsorTradeChoice.PAPER)
    store = LocalSponsorDecisionStore(tmp_path.resolve())
    assert store.retain(paper) == paper
    assert store.retain(paper) == paper
    assert store.load_for_plans((plan,)) == (paper,)
    live = initiate_sponsor_decision(
        plan, judgment, risk, context, SponsorTradeChoice.LIVE,
        current_trade_plan_id=plan.trade_plan_id, decided_at=NOW,
        actual_live_entry=Decimal("101"), live_lots=1,
    )
    with pytest.raises(ValueError, match="ALREADY_FINAL"):
        store.retain(live)


def test_new_trade_plan_identity_requires_new_decision() -> None:
    first, first_plan, *_ = _go(SponsorTradeChoice.IGNORE)
    readiness, requirement = _ready()
    context = _context(requirement.canonical_instrument)
    second_plan = construct_trade_plan(
        requirement, readiness,
        _package(requirement, readiness, package_identity="STEP31-EVIDENCE-PACKAGE-NEW",
                 prior_directional_swing_high=_price("NEW-TARGET", "125", readiness.observation_boundary)),
        context, created_at=NOW,
    )
    assert second_plan.trade_plan_id != first_plan.trade_plan_id
    judgment = create_trade_plan_business_judgment(second_plan, validation_identity="VALIDATION-2", created_at=NOW)
    risk = record_trade_plan_risk_result(second_plan, judgment, RiskState.APPROVED, reason="APPROVED", evaluated_at=NOW)
    second = initiate_sponsor_decision(
        second_plan, judgment, risk, context, SponsorTradeChoice.IGNORE,
        current_trade_plan_id=second_plan.trade_plan_id, decided_at=NOW,
    )
    assert second.decision.decision_id != first.decision.decision_id


def test_geometry_is_never_mutated_and_no_broker_methods_exist() -> None:
    result, plan, *_ = _go(SponsorTradeChoice.LIVE, actual_live_entry=Decimal("105"), live_lots=1)
    assert (result.decision.model_entry, result.decision.stop, result.decision.target) == (
        plan.entry, plan.stop, plan.canonical_target,
    )
    forbidden = {"place_order", "modify_order", "cancel_order", "exit", "close_position"}
    assert forbidden.isdisjoint(dir(result))


def test_native_workflow_binds_initiates_and_restores_sponsor_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    facts, run, _ = _evidence_run()
    root = tmp_path.resolve()
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(root), clock=lambda: NOW)
    prepared = workflow.prepare(run, facts)
    for request, response in _complete_visual_pairs():
        workflow.ingest_visual_v2(request, response)
    requirement = prepared.requirements[0]
    readiness = workflow.ingest_readiness(
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS), created_at=NOW,
    )
    context = _context(requirement.canonical_instrument)
    plan = workflow.construct_trade_plan(
        requirement.canonical_instrument, _package(requirement, readiness), context,
    )
    judgment = create_trade_plan_business_judgment(plan, validation_identity="VALIDATION-WORKFLOW", created_at=NOW)
    risk = record_trade_plan_risk_result(plan, judgment, RiskState.APPROVED, reason="APPROVED", evaluated_at=NOW)
    workflow.bind_step32_inputs(plan.trade_plan_id, judgment, risk, context)
    assert workflow.snapshot().step32_eligible_plan_ids == (plan.trade_plan_id,)
    result = workflow.initiate_sponsor_decision(plan.trade_plan_id, SponsorTradeChoice.PAPER)
    assert result.state is SponsorInitiationState.PAPER_ARMED
    assert workflow.snapshot().active_lifecycle.positions[0].position_id == result.position.position_id
    with pytest.raises(ValueError, match="ALREADY_FINAL"):
        workflow.initiate_sponsor_decision(plan.trade_plan_id, SponsorTradeChoice.LIVE)
    restored = NativeReviewWorkflow(NativeReviewEvidenceStore(root)).restore(run, facts)
    assert restored.sponsor_initiations == (result,)
    assert restored.active_lifecycle.positions[0].position_id == result.position.position_id
