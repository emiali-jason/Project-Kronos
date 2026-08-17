from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from kronos.application.swing_opportunities import (
    AnalysisState,
    BrowserWorkspaceSnapshot,
    ProviderConnectionState,
)
from kronos.application.swing_v1_browser import (
    BrowserCandidateRecord,
    SwingV1BrowserOperationalization,
)
from kronos.instrument import publish_instrument_context
from kronos.browser.views import (
    render_active_candidates,
    render_candidate_workspace,
    render_closed_candidates,
    render_trade_candidates,
)
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
)
from kronos.swing.v1.step32 import (
    MonitoringAdmissionRegistry,
    LocalStep32Store,
    RiskState,
    SponsorDecisionMode,
    activate_objective_model,
    create_business_judgment,
    create_sponsor_position,
    evaluate_objective_model,
    record_risk_result,
)
from tests.unit.swing.v1.test_step32_lifecycle import (
    _entry_fixture,
    _context,
    _lifecycle,
    _model_fixture,
    _model_observation,
    _risk,
    _submission,
)
from kronos.swing.v1.step32 import MonitoringSubmissionType


_NOW = datetime.fromisoformat("2026-08-14T09:30:00+05:30")


def _snapshot() -> BrowserWorkspaceSnapshot:
    return BrowserWorkspaceSnapshot(
        ProviderConnectionState.CONNECTED,
        AnalysisState.READY,
        98,
    )


def test_zero_eligible_run_renders_no_fabricated_candidate() -> None:
    workflow = SwingV1BrowserOperationalization()
    html = render_trade_candidates(_snapshot(), workflow.snapshot())
    assert "No instruments from the current chart review" in html
    assert not workflow.snapshot().records


def test_risk_unavailable_stops_at_waiting_for_risk() -> None:
    candidate, _, _, _, _ = _entry_fixture()
    judgment = create_business_judgment(
        candidate,
        validation_identity="SWING-V1-VALIDATION-20260814",
        clock=_NOW,
    )
    risk = record_risk_result(
        candidate,
        judgment,
        RiskState.UNAVAILABLE,
        reason="APPROVED_RISK_POLICY_UNAVAILABLE",
        clock=_NOW,
    )
    lifecycle = _lifecycle(candidate, risk)
    workflow = SwingV1BrowserOperationalization(
        recovered_records=(BrowserCandidateRecord(
            candidate,
            judgment,
            risk,
            lifecycle,
        ),)
    )
    record = workflow.snapshot().trade_candidates[0]
    html = render_candidate_workspace(_snapshot(), record)
    assert "RISK UNAVAILABLE" in html
    assert "Waiting for Risk" in html
    assert "LIVE" not in html and "PAPER" not in html and "IGNORE" not in html


def test_risk_permitted_decision_is_revisable_before_entry() -> None:
    candidate, risk, lifecycle, _, _ = _entry_fixture()
    workflow = SwingV1BrowserOperationalization(
        recovered_records=(BrowserCandidateRecord(
            candidate,
            create_business_judgment(
                candidate,
                validation_identity="SWING-V1-VALIDATION-20260814",
                clock=_NOW,
            ),
            risk,
            lifecycle,
        ),)
    )
    browser_key = workflow.snapshot().records[0].browser_key
    first = workflow.record_sponsor_choice(browser_key, SponsorDecisionMode.PAPER)
    revised = workflow.record_sponsor_choice(browser_key, SponsorDecisionMode.IGNORE)
    assert first.revision == 1
    assert revised.revision == 2
    assert workflow.snapshot().records[0].sponsor_decision == revised


def test_active_and_closed_projection_preserve_model_position_separation() -> None:
    candidate, risk, lifecycle, registry, _, model = _model_fixture()
    base = BrowserCandidateRecord(
        candidate,
        create_business_judgment(
            candidate,
            validation_identity="SWING-V1-VALIDATION-20260814",
            clock=_NOW,
        ),
        risk,
        lifecycle,
        monitoring_state=MonitoringConnectionState.CONNECTED,
    )
    workflow = SwingV1BrowserOperationalization(recovered_records=(base,))
    decision = workflow.record_sponsor_choice(
        base.browser_key,
        SponsorDecisionMode.LIVE,
    )
    position = create_sponsor_position(decision, candidate, risk, model)
    active = BrowserCandidateRecord(
        candidate,
        base.business_judgment,
        risk,
        lifecycle,
        decision,
        model,
        position,
        MonitoringConnectionState.CONNECTED,
    )
    workflow.publish(active)
    active_html = render_active_candidates(_snapshot(), workflow.snapshot())
    detail = render_candidate_workspace(_snapshot(), active)
    assert "ACTIVE" in active_html
    assert "KRONOS Model" in detail and "Your Position" in detail
    assert "MONITORING OK" in detail

    stop = _model_observation(
        model,
        candidate,
        lifecycle,
        registry,
        MonitoringSubmissionType.STOP_LEVEL_CROSSED,
        "94.00",
        3,
    )
    closed_model = evaluate_objective_model(model, (stop,))
    closed = BrowserCandidateRecord(
        candidate,
        base.business_judgment,
        risk,
        lifecycle,
        decision,
        closed_model,
        position,
        MonitoringConnectionState.DISCONNECTED,
    )
    workflow.publish(closed)
    closed_html = render_closed_candidates(_snapshot(), workflow.snapshot())
    detail = render_candidate_workspace(_snapshot(), closed)
    assert "STOP" in closed_html
    assert "ACTION REQUIRED" in detail
    assert "CHECK / MANAGE YOUR LIVE POSITION" in detail


def test_governed_observations_drive_entry_and_closed_lifecycle(tmp_path) -> None:  # type: ignore[no-untyped-def]
    candidate, risk, lifecycle, _, _ = _entry_fixture()
    judgment = create_business_judgment(
        candidate,
        validation_identity="SWING-V1-VALIDATION-20260814",
        clock=_NOW,
    )
    record = BrowserCandidateRecord(candidate, judgment, risk, lifecycle)
    workflow = SwingV1BrowserOperationalization(
        step32_store=LocalStep32Store(tmp_path / "step32"),
    )
    workflow.publish(record)
    workflow.record_sponsor_choice(record.browser_key, SponsorDecisionMode.PAPER)
    registry = MonitoringAdmissionRegistry()
    previous = registry.admit(
        _submission(candidate, lifecycle, "99.00", 1),
        _context(candidate, lifecycle),
        clock=_NOW,
    )
    current = registry.admit(
        _submission(candidate, lifecycle, str(candidate.entry_price), 2),
        _context(candidate, lifecycle),
        clock=_NOW,
    )
    outcome = workflow.apply_entry_observations(
        record.browser_key,
        previous,
        current,
    )
    active = workflow.snapshot().active[0]
    assert outcome.state.value == "ENTRY_TRIGGERED"
    assert active.objective_model is not None
    assert active.sponsor_decision is not None and active.sponsor_decision.frozen
    assert active.sponsor_position is not None

    stop = _model_observation(
        active.objective_model,
        candidate,
        lifecycle,
        registry,
        MonitoringSubmissionType.STOP_LEVEL_CROSSED,
        "94.00",
        3,
    )
    closed = workflow.apply_model_observations(record.browser_key, (stop,))
    assert closed.state.value == "MODEL_TRADE_CLOSED"
    assert workflow.snapshot().closed[0].sponsor_position.state.value == "CLOSED"
    assert list((tmp_path / "step32").rglob("*.json"))


def test_restart_projection_uses_recovered_canonical_records() -> None:
    candidate, risk, lifecycle, _, _ = _entry_fixture()
    record = BrowserCandidateRecord(
        candidate,
        create_business_judgment(
            candidate,
            validation_identity="SWING-V1-VALIDATION-20260814",
            clock=_NOW,
        ),
        risk,
        lifecycle,
    )
    recovered = SwingV1BrowserOperationalization(
        recovered_records=(record,)
    ).snapshot()
    assert recovered.records == (record,)
    assert "Waiting for Entry" in render_candidate_workspace(
        _snapshot(),
        recovered.records[0],
    )


def test_unavailable_risk_rejects_sponsor_decision() -> None:
    candidate, _, _, _, _ = _entry_fixture()
    judgment = create_business_judgment(
        candidate,
        validation_identity="SWING-V1-VALIDATION-20260814",
        clock=_NOW,
    )
    risk = record_risk_result(
        candidate,
        judgment,
        RiskState.UNAVAILABLE,
        reason="APPROVED_RISK_POLICY_UNAVAILABLE",
        clock=_NOW,
    )
    record = BrowserCandidateRecord(
        candidate,
        judgment,
        risk,
        _lifecycle(candidate, risk),
    )
    workflow = SwingV1BrowserOperationalization(recovered_records=(record,))
    with pytest.raises(ValueError, match="NOT_PERMITTED"):
        workflow.record_sponsor_choice(record.browser_key, SponsorDecisionMode.LIVE)


class _MonitoringSession:
    def __init__(self, consumer) -> None:  # type: ignore[no-untyped-def]
        self.consumer = consumer
        self.subscriptions = ()
        self.unsubscribed = ()
        self.disconnected = False

    def subscribe(self, instruments) -> None:  # type: ignore[no-untyped-def]
        self.subscriptions = instruments

    def connect(self) -> None:
        self.consumer.on_connection_state(MonitoringConnectionState.CONNECTED)

    def unsubscribe(self, instruments) -> None:  # type: ignore[no-untyped-def]
        self.unsubscribed = instruments

    def disconnect(self) -> None:
        self.disconnected = True


class _ReadOnlyCapability:
    active = True

    def __init__(self) -> None:
        self.session = None

    def open_monitoring_session(self, consumer):  # type: ignore[no-untyped-def]
        self.session = _MonitoringSession(consumer)
        return self.session


def _monitoring_fixture():  # type: ignore[no-untyped-def]
    instrument = InstrumentRecord(
        "KITE",
        "NSE",
        "NSE",
        "RELIANCE",
        "RELIANCE",
        "EQ",
        None,
        Decimal("0.05"),
        1,
    )
    candidate, _, _, _, _ = _entry_fixture()
    context = publish_instrument_context(
        candidate.canonical_instrument,
        candidate.product,
        instrument,
    )
    candidate = replace(
        candidate,
        execution_context_identity=f"{context.identity}|NSE-SCHEDULE-20260814",
    )
    judgment = create_business_judgment(
        candidate,
        validation_identity="SWING-V1-VALIDATION-20260814",
        clock=_NOW,
    )
    risk = record_risk_result(
        candidate,
        judgment,
        RiskState.APPROVED,
        reason="RISK_APPROVED",
        clock=_NOW,
    )
    lifecycle = _lifecycle(candidate, risk)
    record = BrowserCandidateRecord(candidate, judgment, risk, lifecycle)
    workflow = SwingV1BrowserOperationalization(recovered_records=(record,))
    capability = _ReadOnlyCapability()
    return workflow, record, capability, instrument


def _tick(
    instrument: InstrumentRecord,
    price: Decimal,
    sequence: int,
) -> ProviderMarketTick:
    observed = _NOW + timedelta(seconds=sequence)
    return ProviderMarketTick(
        instrument,
        price,
        observed,
        observed,
        "KITE_CONNECT_WEBSOCKET",
        "KITE-CANDIDATE-CONNECTION-1",
        sequence,
        True,
        True,
        True,
    )


def test_candidate_kite_session_binds_domain_002_and_closes_after_target() -> None:
    workflow, record, capability, instrument = _monitoring_fixture()
    workflow.record_sponsor_choice(record.browser_key, SponsorDecisionMode.PAPER)
    workflow.attach_candidate_monitoring(
        record.browser_key,
        capability,
        instrument,
    )
    assert capability.session.subscriptions == (instrument,)
    assert workflow.snapshot().records[0].monitoring_state is MonitoringConnectionState.CONNECTED

    capability.session.consumer.on_market_tick(
        _tick(instrument, record.candidate.entry_price - Decimal("1"), 1)
    )
    capability.session.consumer.on_market_tick(
        _tick(instrument, record.candidate.entry_price, 2)
    )
    assert workflow.snapshot().active

    capability.session.consumer.on_market_tick(
        _tick(instrument, record.candidate.target_price, 3)
    )
    assert workflow.snapshot().closed
    assert capability.session.unsubscribed == (instrument,)
    assert capability.session.disconnected is True


def test_candidate_monitoring_rejects_wrong_governed_execution_instrument() -> None:
    workflow, record, capability, _ = _monitoring_fixture()
    wrong = InstrumentRecord(
        "KITE", "NSE", "NSE", "TCS", "TCS", "EQ", None,
        Decimal("0.05"), 1,
    )
    with pytest.raises(ValueError, match="INSTRUMENT_BINDING_INVALID"):
        workflow.attach_candidate_monitoring(record.browser_key, capability, wrong)
    assert capability.session is None


def test_order_updates_do_not_enter_candidate_objective_monitoring() -> None:
    workflow, record, capability, instrument = _monitoring_fixture()
    workflow.attach_candidate_monitoring(
        record.browser_key,
        capability,
        instrument,
    )
    before = workflow.snapshot()
    capability.session.consumer.on_order_update(object())
    assert workflow.snapshot() == before
    assert not hasattr(capability, "place_order")
