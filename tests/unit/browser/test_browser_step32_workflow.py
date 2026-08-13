from kronos.browser.views import (
    build_step32_sponsor_workflow_view,
    render_step32_sponsor_workflow,
)
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.swing.v1.step32 import (
    SponsorDecisionMode,
    activate_objective_model,
    create_sponsor_position,
    record_sponsor_decision,
)
from tests.unit.swing.v1.test_step32_lifecycle import (
    _candidate,
    _entry_fixture,
    _lifecycle,
    _risk,
)


def test_waiting_workflow_is_compact_and_sponsor_facing() -> None:
    candidate = _candidate()
    risk = _risk(candidate)
    lifecycle = _lifecycle(candidate, risk)
    view = build_step32_sponsor_workflow_view(candidate, risk, lifecycle)
    html = render_step32_sponsor_workflow(view)
    assert "RELIANCE — LONG" in html
    assert "Trade Plan" in html
    assert "Entry" in html and "Stop" in html and "Invalidation" in html and "Target" in html
    assert "APPROVED" in html
    assert "Waiting for Entry" in html
    assert "LIVE" in html and "PAPER" in html and "IGNORE" in html


def test_model_and_sponsor_position_are_clearly_separate() -> None:
    candidate, risk, lifecycle, _, outcome = _entry_fixture()
    model = activate_objective_model(candidate, risk, outcome)
    decision = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.PAPER)
    position = create_sponsor_position(decision, candidate, risk, model)
    html = render_step32_sponsor_workflow(
        build_step32_sponsor_workflow_view(
            candidate,
            risk,
            lifecycle,
            decision=decision,
            model=model,
            position=position,
            monitoring_state=MonitoringConnectionState.CONNECTED,
        )
    )
    assert "KRONOS Model" in html
    assert "Your Position" in html
    assert "ACTIVE" in html
    assert "PAPER · ACTIVE" in html
    assert "Kite Monitoring" in html and "CONNECTED" in html
    assert "Trade Monitoring" in html and "MONITORING OK" in html


def test_context_incomplete_is_sponsor_facing_without_raw_stream_details() -> None:
    candidate = _candidate()
    risk = _risk(candidate)
    html = render_step32_sponsor_workflow(
        build_step32_sponsor_workflow_view(
            candidate,
            risk,
            _lifecycle(candidate, risk),
            monitoring_state=MonitoringConnectionState.CONTEXT_INCOMPLETE,
        )
    )
    assert "CONTEXT INCOMPLETE" in html
    assert "RECONCILIATION REQUIRED" in html
    assert "instrument_token" not in html and "raw tick" not in html


def test_primary_workflow_hides_normal_operation_internals() -> None:
    candidate = _candidate()
    risk = _risk(candidate)
    html = render_step32_sponsor_workflow(
        build_step32_sponsor_workflow_view(candidate, risk, _lifecycle(candidate, risk))
    )
    for forbidden in (
        "DOMAIN-002",
        "KR-380",
        "KR-390",
        candidate.candidate_id,
        risk.risk_result_id,
        "monitoring_binding_id",
        "event_id",
        "replay",
    ):
        assert forbidden not in html


def test_step32_workflow_contains_no_broker_execution_control() -> None:
    candidate = _candidate()
    risk = _risk(candidate)
    html = render_step32_sponsor_workflow(
        build_step32_sponsor_workflow_view(candidate, risk, _lifecycle(candidate, risk))
    )
    for forbidden in ("place_order", "modify_order", "cancel_order", "Buy Now", "Sell Now"):
        assert forbidden not in html
