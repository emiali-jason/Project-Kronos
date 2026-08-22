from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.application.swing_trade_window import SwingTradeWindowWorkflow
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.provider.contracts.monitoring import ProviderMarketTick
from kronos.swing.v1.kr370_step31_handoff import LocalKr370Step31HandoffStore
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_entry_timing import (
    EcpcV2Blocker,
    EcpcV2Outcome,
    Kr380V2State,
    LocalKr380V2Store,
    LocalObjectiveModelV1Store,
    LocalPortfolioStateV1Store,
    LocalRiskPermissionV1Store,
    PortfolioRuleDisposition,
    PortfolioRuleFact,
    activate_objective_model_v1,
    create_portfolio_state_v1,
    evaluate_kr380_v2,
    evaluate_risk_permission_v1,
    produce_native_ecpc_v2,
)
from kronos.swing.v1.native_trade_construction import LocalTradePlanStore
from kronos.swing.v1.step32 import (
    Availability,
    Freshness,
    MonitoringObservation,
    MonitoringSubmissionType,
    RiskState,
)
from kronos.swing.v1.trade_construction import TradeCandidateIntegrity
from tests.unit.swing.v1.test_kr370_step31_handoff import (
    NOW,
    _completed,
    _context,
    _evidence,
)


def _ready(tmp_path, *, direction=V1Direction.LONG):  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path, direction=direction)
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
    )
    projected = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    assert projected.trade_plan is not None and projected.handoff is not None
    return completed, projected.trade_plan, projected.handoff


def _portfolio(*, cycle="PORTFOLIO-CYCLE-1", rules=()):  # type: ignore[no-untyped-def]
    return create_portfolio_state_v1(
        cycle_identity=cycle,
        as_of_boundary=NOW,
        objective_exposures=(),
        sponsor_exposures=(),
        rule_facts=rules,
        source_identities=("OBJECTIVE-MODEL-STORE", "SPONSOR-POSITION-STORE"),
        sources_complete=True,
        provenance=("DOMAIN-005", "ADR-0013"),
    )


_DEFAULT_PORTFOLIO = object()


class _MonitoringSession:
    def __init__(self, consumer) -> None:  # type: ignore[no-untyped-def]
        self.consumer = consumer
        self.subscriptions = []
        self.disconnect_count = 0

    def subscribe(self, instruments):  # type: ignore[no-untyped-def]
        self.subscriptions.append(instruments)

    def unsubscribe(self, _instruments):  # type: ignore[no-untyped-def]
        return None

    def connect(self) -> None:
        self.consumer.on_connection_state(MonitoringConnectionState.CONNECTED)

    def disconnect(self) -> None:
        self.disconnect_count += 1


class _MonitoringCapability:
    active = True

    def __init__(self) -> None:
        self.sessions = []

    def open_monitoring_session(self, consumer):  # type: ignore[no-untyped-def]
        session = _MonitoringSession(consumer)
        self.sessions.append(session)
        return session


def _risk(plan, handoff, completed, portfolio=_DEFAULT_PORTFOLIO, **changes):  # type: ignore[no-untyped-def]
    actual = _portfolio() if portfolio is _DEFAULT_PORTFOLIO else portfolio
    values = dict(
        kr370_source_identity=completed.promotion.integrity_sha256,
        kr370_source_sha256=completed.promotion.integrity_sha256,
        portfolio_state=actual,
        current_trade_plan_id=plan.trade_plan_id,
        current_portfolio_cycle_identity=None if actual is None else actual.cycle_identity,
        evaluated_at=NOW,
    )
    values.update(changes)
    return evaluate_risk_permission_v1(plan, handoff, **values)


def _observation(plan, binding, price, sequence, *, direction=None, **changes):  # type: ignore[no-untyped-def]
    occurred = NOW + timedelta(minutes=sequence)
    values = dict(
        contract_identity="KRONOS-SWING-V1-MONITORING-OBSERVATION-V1",
        contract_version="1",
        observation_id=f"OBSERVATION-{sequence}",
        source_submission_id=f"SUBMISSION-{sequence}",
        source_payload_digest="a" * 64,
        candidate_id=plan.trade_plan_id,
        monitoring_binding_id=binding,
        model_trade_id=None,
        canonical_instrument=plan.canonical_instrument,
        provider_instrument=f"NSE:{plan.canonical_instrument}",
        product="SWING",
        direction=direction or plan.native_direction.value,
        observation_type=MonitoringSubmissionType.ENTRY_LEVEL_CROSSED,
        observed_price_availability=Availability.AVAILABLE,
        observed_price=Decimal(price),
        observed_at=occurred,
        admitted_at=occurred + timedelta(seconds=1),
        boundary=plan.observation_boundary,
        timeframe="TICK",
        session_identity="NSE-20260821",
        source_sequence=sequence,
        previous_interval_available=True,
        session_continuous=True,
        ordering_deterministic=True,
        provenance=("KITE_CONNECT_WEBSOCKET", "DOMAIN-002"),
        freshness=Freshness.CURRENT,
        integrity=TradeCandidateIntegrity.VALID,
    )
    values.update(changes)
    return MonitoringObservation(**values)


def test_portfolio_and_risk_approved_are_immutable_and_restart_safe(tmp_path) -> None:
    completed, plan, handoff = _ready(tmp_path)
    portfolio = _portfolio()
    risk = _risk(plan, handoff, completed, portfolio)
    portfolio_store = LocalPortfolioStateV1Store(tmp_path / "portfolio")
    risk_store = LocalRiskPermissionV1Store(tmp_path / "risk")
    portfolio_store.retain_current(portfolio)
    risk_store.retain_current(risk)

    assert risk.state is RiskState.APPROVED and risk.permits_entry
    assert risk.constraints == ()
    assert not hasattr(risk, "quantity") and not hasattr(risk, "capital_risk")
    assert portfolio_store.load_current_state() == portfolio
    assert risk_store.load_for_plan(plan.trade_plan_id) == risk


@pytest.mark.parametrize(
    ("portfolio", "cycle", "state", "reason"),
    (
        (None, None, RiskState.UNAVAILABLE, "PORTFOLIO_STATE_UNAVAILABLE"),
        (_portfolio(cycle="OLD"), "CURRENT", RiskState.UNAVAILABLE, "PORTFOLIO_STATE_STALE_OR_INCOMPLETE"),
        (_portfolio(rules=(PortfolioRuleFact("RULE-1", PortfolioRuleDisposition.HARD_PROHIBITION, "EXPLICIT_HARD_PROHIBITION", "GOVERNED-RULE"),)), "PORTFOLIO-CYCLE-1", RiskState.REJECTED, "EXPLICIT_HARD_PROHIBITION"),
        (_portfolio(rules=(PortfolioRuleFact("RULE-2", PortfolioRuleDisposition.CONSTRAINT, "EXISTING_GOVERNED_CONSTRAINT", "GOVERNED-RULE"),)), "PORTFOLIO-CYCLE-1", RiskState.CONSTRAINED, "EXISTING_GOVERNED_CONSTRAINT"),
    ),
)
def test_risk_states_are_exact_and_fail_closed(tmp_path, portfolio, cycle, state, reason) -> None:  # type: ignore[no-untyped-def]
    completed, plan, handoff = _ready(tmp_path)
    risk = _risk(
        plan, handoff, completed, portfolio,
        current_portfolio_cycle_identity=cycle,
    )
    assert risk.state is state
    assert reason in risk.reason_codes
    assert risk.permits_entry is (state in {RiskState.APPROVED, RiskState.CONSTRAINED})


def test_plan_supersession_invalidates_risk(tmp_path) -> None:
    completed, plan, handoff = _ready(tmp_path)
    risk = _risk(
        plan, handoff, completed,
        current_trade_plan_id="SUPERSEDED-PLAN",
    )
    assert risk.state is RiskState.UNAVAILABLE
    assert not risk.permits_entry


@pytest.mark.parametrize(
    ("direction", "before_offset", "expected"),
    (
        (V1Direction.LONG, Decimal("-1"), Kr380V2State.LONG_ENTRY_TRIGGERED),
        (V1Direction.SHORT, Decimal("1"), Kr380V2State.SHORT_ENTRY_TRIGGERED),
    ),
)
def test_ecpc_and_kr380_crossing_activate_objective_model_without_sponsor_position(
    tmp_path, direction, before_offset, expected,
) -> None:  # type: ignore[no-untyped-def]
    completed, plan, handoff = _ready(tmp_path, direction=direction)
    assert plan.entry is not None
    risk = _risk(plan, handoff, completed)
    binding = "MONITORING-BINDING-1"
    context = produce_native_ecpc_v2(
        plan, risk, monitoring_binding_id=binding,
        session_identity="NSE-20260821",
        observation_boundary=plan.observation_boundary,
        outcome=EcpcV2Outcome.QUALIFIED, blockers=(),
    )
    previous = _observation(plan, binding, plan.entry + before_offset, 1)
    current = _observation(plan, binding, plan.entry, 2)
    outcome = evaluate_kr380_v2(
        plan, risk, context,
        kr370_source_identity=completed.promotion.integrity_sha256,
        previous=previous, current=current, evaluated_at=NOW + timedelta(minutes=2),
    )
    model = activate_objective_model_v1(
        plan, outcome, monitoring_state=MonitoringConnectionState.CONNECTED,
    )

    assert outcome.state is expected
    assert model.state.value == "MODEL_TRADE_ACTIVE"
    assert model.sponsor_position_identity is None
    assert model.broker_authority == "NONE"


def test_pending_context_forms_and_rejected_risk_cannot_create_context(tmp_path) -> None:
    completed, plan, handoff = _ready(tmp_path)
    approved = _risk(plan, handoff, completed)
    pending = produce_native_ecpc_v2(
        plan, approved, monitoring_binding_id="MONITORING-BINDING-1",
        session_identity="NSE-20260821", observation_boundary=plan.observation_boundary,
        outcome=EcpcV2Outcome.PENDING,
        blockers=(EcpcV2Blocker.EXECUTION_CONFIRMATION_PENDING,),
    )
    forming = evaluate_kr380_v2(
        plan, approved, pending,
        kr370_source_identity=completed.promotion.integrity_sha256,
        previous=None, current=None, evaluated_at=NOW,
    )
    assert forming.state is Kr380V2State.FORMING

    prohibited = _portfolio(rules=(PortfolioRuleFact(
        "RULE-1", PortfolioRuleDisposition.HARD_PROHIBITION,
        "EXPLICIT_HARD_PROHIBITION", "GOVERNED-RULE",
    ),))
    rejected = _risk(plan, handoff, completed, prohibited)
    with pytest.raises(ValueError, match="NATIVE_ECPC_V2_RISK_BINDING_INVALID"):
        produce_native_ecpc_v2(
            plan, rejected, monitoring_binding_id="MONITORING-BINDING-1",
            session_identity="NSE-20260821", observation_boundary=plan.observation_boundary,
            outcome=EcpcV2Outcome.QUALIFIED, blockers=(),
        )


@pytest.mark.parametrize(
    "change",
    ("first_beyond", "continuity", "ordering", "binding"),
)
def test_reconciliation_conditions_fail_closed(tmp_path, change) -> None:
    completed, plan, handoff = _ready(tmp_path)
    risk = _risk(plan, handoff, completed)
    binding = "MONITORING-BINDING-1"
    context = produce_native_ecpc_v2(
        plan, risk, monitoring_binding_id=binding,
        session_identity="NSE-20260821", observation_boundary=plan.observation_boundary,
        outcome=EcpcV2Outcome.QUALIFIED, blockers=(),
    )
    previous = None if change == "first_beyond" else _observation(plan, binding, "99", 1)
    changes = {}
    if change == "continuity":
        changes["previous_interval_available"] = False
    elif change == "ordering":
        changes["observed_at"] = NOW
    elif change == "binding":
        changes["candidate_id"] = "FOREIGN-PLAN"
    current = _observation(plan, binding, "100", 2, **changes)
    outcome = evaluate_kr380_v2(
        plan, risk, context,
        kr370_source_identity=completed.promotion.integrity_sha256,
        previous=previous, current=current, evaluated_at=NOW + timedelta(minutes=2),
    )
    assert outcome.state is Kr380V2State.FAILED
    assert "TRIGGERED" not in outcome.state.value


def test_current_v2_and_model_restart_without_duplicate_trigger(tmp_path) -> None:
    completed, plan, handoff = _ready(tmp_path)
    risk = _risk(plan, handoff, completed)
    context = produce_native_ecpc_v2(
        plan, risk, monitoring_binding_id="MONITORING-BINDING-1",
        session_identity="NSE-20260821", observation_boundary=plan.observation_boundary,
        outcome=EcpcV2Outcome.QUALIFIED, blockers=(),
    )
    previous = _observation(plan, context.monitoring_binding_id, "99", 1)
    current = _observation(plan, context.monitoring_binding_id, "100", 2)
    outcome = evaluate_kr380_v2(
        plan, risk, context,
        kr370_source_identity=completed.promotion.integrity_sha256,
        previous=previous, current=current, evaluated_at=NOW + timedelta(minutes=2),
    )
    model = activate_objective_model_v1(
        plan, outcome, monitoring_state=MonitoringConnectionState.CONNECTED,
    )
    outcome_store = LocalKr380V2Store(tmp_path / "kr380")
    model_store = LocalObjectiveModelV1Store(tmp_path / "kr390")
    first_path = outcome_store.retain_current(outcome)
    second_path = outcome_store.retain_current(outcome)
    model_store.retain_current(model)

    assert first_path == second_path
    assert outcome_store.load_for_plan(plan.trade_plan_id) == outcome
    assert model_store.load_for_plan(plan.trade_plan_id) == model


def test_production_workflow_restores_v2_into_ux07_and_reuses_shared_hub(tmp_path) -> None:
    completed = _completed(tmp_path, direction=V1Direction.LONG)
    handoffs = LocalKr370Step31HandoffStore(tmp_path / "handoffs")
    plans = LocalTradePlanStore(tmp_path / "plans")
    portfolio_store = LocalPortfolioStateV1Store(tmp_path / "portfolio")
    risk_store = LocalRiskPermissionV1Store(tmp_path / "risk")
    outcome_store = LocalKr380V2Store(tmp_path / "kr380")
    model_store = LocalObjectiveModelV1Store(tmp_path / "kr390")
    workflow = SwingTradeWindowWorkflow(
        handoffs, plans, portfolio_store, risk_store, outcome_store, model_store
    )
    shared_hub = SharedSwingMonitoringHub()
    workflow.set_shared_monitoring_hub(shared_hub)
    projected = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    assert projected.trade_plan is not None
    plan = projected.trade_plan
    workflow.publish_portfolio_state(
        cycle_identity="PORTFOLIO-CYCLE-1",
        as_of_boundary=NOW,
        objective_exposures=(),
        sponsor_exposures=(),
        source_identities=("OBJECTIVE-MODEL-STORE", "SPONSOR-POSITION-STORE"),
        sources_complete=True,
        provenance=("DOMAIN-005", "ADR-0013"),
    )
    binding = "MONITORING-BINDING-1"
    outcome = workflow.evaluate_current_entry_timing(
        plan.native_run_identity,
        plan.canonical_instrument,
        session_identity="NSE-20260821",
        observation_boundary=plan.observation_boundary,
        ecpc_outcome=EcpcV2Outcome.QUALIFIED,
        ecpc_blockers=(),
        previous=_observation(plan, binding, plan.entry - Decimal("1"), 1),
        current=_observation(plan, binding, plan.entry, 2),
        evaluated_at=NOW + timedelta(minutes=2),
        monitoring_binding_id=binding,
        monitoring_state=MonitoringConnectionState.CONNECTED,
    )
    assert outcome.state is Kr380V2State.LONG_ENTRY_TRIGGERED
    live_projection = workflow.project(plan.native_run_identity, plan.canonical_instrument)
    assert live_projection is not None
    assert live_projection.kr380_entry_timing_state == "LONG_ENTRY_TRIGGERED"
    assert live_projection.model_lifecycle_state == "MODEL_TRADE_ACTIVE"
    assert live_projection.sponsor_position_state == "NO SPONSOR POSITION"

    restored = SwingTradeWindowWorkflow(
        handoffs, plans, portfolio_store, risk_store, outcome_store, model_store
    )
    restored.set_shared_monitoring_hub(shared_hub)
    restored.restore((completed,))
    restored_projection = restored.project(
        plan.native_run_identity, plan.canonical_instrument
    )
    assert restored.shared_monitoring_hub is shared_hub
    assert shared_hub.active_session_count == 0
    assert restored_projection is not None
    assert restored_projection.kr380_entry_timing_state == "LONG_ENTRY_TRIGGERED"
    assert restored_projection.model_lifecycle_state == "MODEL_TRADE_ACTIVE"
    assert restored_projection.model_trade_id == live_projection.model_trade_id


def test_production_kr380_consumes_facts_through_one_shared_provider_session(tmp_path) -> None:
    completed = _completed(tmp_path, direction=V1Direction.LONG)
    outcome_store = LocalKr380V2Store(tmp_path / "kr380")
    model_store = LocalObjectiveModelV1Store(tmp_path / "kr390")
    workflow = SwingTradeWindowWorkflow(
        LocalKr370Step31HandoffStore(tmp_path / "handoffs"),
        LocalTradePlanStore(tmp_path / "plans"),
        LocalPortfolioStateV1Store(tmp_path / "portfolio"),
        LocalRiskPermissionV1Store(tmp_path / "risk"),
        outcome_store,
        model_store,
    )
    projected = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    assert projected.trade_plan is not None
    plan = projected.trade_plan
    workflow.publish_portfolio_state(
        cycle_identity="PORTFOLIO-CYCLE-1",
        as_of_boundary=NOW,
        objective_exposures=(),
        sponsor_exposures=(),
        source_identities=("OBJECTIVE-MODEL-STORE", "SPONSOR-POSITION-STORE"),
        sources_complete=True,
        provenance=("DOMAIN-005", "ADR-0013"),
    )
    hub = SharedSwingMonitoringHub()
    workflow.set_shared_monitoring_hub(hub)
    capability = _MonitoringCapability()
    instrument = InstrumentRecord(
        "KITE", "NSE", "NSE", plan.canonical_instrument,
        plan.canonical_instrument, "EQ", None,
    )
    workflow.start_current_entry_monitoring(
        plan.native_run_identity,
        plan.canonical_instrument,
        capability=capability,
        instrument=instrument,
        session_identity="NSE-20260821",
        observation_boundary=plan.observation_boundary,
        ecpc_outcome=EcpcV2Outcome.QUALIFIED,
        ecpc_blockers=(),
        clock=lambda: NOW + timedelta(minutes=3),
    )
    assert len(capability.sessions) == 1
    assert hub.active_session_count == 1
    for sequence, price in ((1, plan.entry - Decimal("1")), (2, plan.entry)):
        observed = NOW + timedelta(minutes=sequence)
        capability.sessions[0].consumer.on_market_tick(ProviderMarketTick(
            instrument=instrument,
            last_price=price,
            observed_at=observed,
            received_at=observed + timedelta(seconds=1),
            source="KITE_CONNECT_WEBSOCKET",
            connection_id="CONNECTION-1",
            source_sequence=sequence,
            previous_interval_available=True,
            session_continuous=True,
            ordering_deterministic=True,
        ))
    retained = outcome_store.load_for_plan(plan.trade_plan_id)
    assert retained is not None
    assert retained.state is Kr380V2State.LONG_ENTRY_TRIGGERED
    model = model_store.load_for_plan(plan.trade_plan_id)
    assert model is not None and model.sponsor_position_identity is None
    assert len(capability.sessions) == 1
    workflow.close_monitoring()
    assert capability.sessions[0].disconnect_count == 1


def test_missing_portfolio_persists_fail_closed_no_trigger_for_ux07(tmp_path) -> None:
    completed = _completed(tmp_path, direction=V1Direction.LONG)
    handoffs = LocalKr370Step31HandoffStore(tmp_path / "handoffs")
    plans = LocalTradePlanStore(tmp_path / "plans")
    portfolio_store = LocalPortfolioStateV1Store(tmp_path / "portfolio")
    risk_store = LocalRiskPermissionV1Store(tmp_path / "risk")
    outcome_store = LocalKr380V2Store(tmp_path / "kr380")
    model_store = LocalObjectiveModelV1Store(tmp_path / "kr390")
    workflow = SwingTradeWindowWorkflow(
        handoffs, plans, portfolio_store, risk_store, outcome_store, model_store
    )
    projected = workflow.construct(
        completed,
        _evidence(completed),
        _context(completed.requirement.canonical_instrument),
        current_run_identity=completed.requirement.native_run_identity,
        current_analysis_boundary=completed.promotion.analysis_boundary,
        created_at=NOW,
    )
    assert projected.trade_plan is not None
    plan = projected.trade_plan
    outcome = workflow.evaluate_current_entry_timing(
        plan.native_run_identity,
        plan.canonical_instrument,
        session_identity="NSE-20260821",
        observation_boundary=plan.observation_boundary,
        ecpc_outcome=EcpcV2Outcome.PENDING,
        ecpc_blockers=(EcpcV2Blocker.EXECUTION_CONFIRMATION_PENDING,),
        previous=None,
        current=None,
        evaluated_at=NOW,
    )
    assert outcome.state is Kr380V2State.NO_TRIGGER
    unavailable = workflow.project(plan.native_run_identity, plan.canonical_instrument)
    assert unavailable is not None
    assert unavailable.risk_state == "RISK_UNAVAILABLE"
    assert unavailable.risk_result_id is not None
    assert unavailable.kr380_entry_timing_state == "NO_TRIGGER"
    assert unavailable.model_lifecycle_state == "NOT ESTABLISHED"

    restored = SwingTradeWindowWorkflow(
        handoffs, plans, portfolio_store, risk_store, outcome_store, model_store
    )
    restored.restore((completed,))
    restored_projection = restored.project(
        plan.native_run_identity, plan.canonical_instrument
    )
    assert restored_projection is not None
    assert restored_projection.kr380_entry_timing_state == "NO_TRIGGER"


@pytest.mark.parametrize(
    "state",
    (Kr380V2State.NO_TRIGGER, Kr380V2State.FORMING, Kr380V2State.EXTENDED, Kr380V2State.FAILED),
)
def test_non_trigger_states_cannot_activate_kr390(tmp_path, state) -> None:
    completed, plan, handoff = _ready(tmp_path)
    risk = _risk(plan, handoff, completed)
    context = produce_native_ecpc_v2(
        plan, risk, monitoring_binding_id="MONITORING-BINDING-1",
        session_identity="NSE-20260821", observation_boundary=plan.observation_boundary,
        outcome=EcpcV2Outcome.PENDING,
        blockers=(EcpcV2Blocker.EXECUTION_CONFIRMATION_PENDING,),
    )
    outcome = evaluate_kr380_v2(
        plan, risk, context,
        kr370_source_identity=completed.promotion.integrity_sha256,
        previous=None, current=None, evaluated_at=NOW,
    )
    object.__setattr__(outcome, "state", state)
    with pytest.raises(ValueError, match="KR390_V2_HANDOFF_INVALID"):
        activate_objective_model_v1(
            plan, outcome, monitoring_state=MonitoringConnectionState.CONNECTED,
        )
