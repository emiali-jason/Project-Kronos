"""WO-14.1 R2: pre-entry continuity and independent reconciliation health."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from http.client import HTTPConnection
from threading import Thread
from types import SimpleNamespace

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_trade_window import SwingTradeWindowWorkflow
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_trade_journal
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleState, ActiveTradeLifecycleEngine,
    LocalActiveTradeLifecycleStore,
)
from kronos.swing.v1.observation_research_ledger_v2 import ObservationMode
from kronos.swing.v1.observation_research_ledger_v2 import GovernedPositionPresentationFactsV2
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_native_trade_journal import _operational, NOW
from tests.unit.swing.v1.test_native_active_trade_lifecycle import _observation, _position
from tests.unit.swing.v1.test_native_trade_journal import _run_paper
from tests.unit.swing.v1.test_observation_research_ledger_v2 import _v2
from tests.unit.swing.v1.test_sponsor_observation_decision import _green, _record
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.sponsor_observation_decision import SponsorActivationDisposition


def _handoff_fact(position):
    """Exercise the real lifecycle-to-V2 handoff using a capturing ledger."""
    captured = {}
    window = SwingTradeWindowWorkflow.__new__(SwingTradeWindowWorkflow)
    window._shared_monitoring_hub = None
    window._observation_decisions = {
        "decision": SimpleNamespace(
            snapshot=SimpleNamespace(conventional_trade_plan_identity="PLAN"),
            activation=SimpleNamespace(sponsor_position_identity=position.position_id),
            decision=SimpleNamespace(decision_identity="DECISION"),
        )
    }
    window._positions = {"PLAN": position}
    window._closures = {}
    window._observation_research_v2 = SimpleNamespace(
        operational_handoffs=lambda **kw: captured.update(kw) or ()
    )
    window.observation_operational_handoffs_v2(governed_current_trading_date=NOW.date())
    return captured["position_facts"]["DECISION"]


def _page(position):
    fact = _handoff_fact(position)
    row = replace(
        _operational("NIFTY", ObservationMode.PAPER),
        sponsor_position_state=fact.state,
        sponsor_position_prior_state=fact.prior_state,
        entry=fact.actual_entry,
        position_gross_pnl=fact.gross_pnl,
        monitoring_state=("INTERRUPTED" if fact.state == "MONITORING_UNAVAILABLE"
                          else "UNKNOWN"),
    )
    return render_trade_journal(
        _ready(), None, operational=(row,),
        governed_trading_date=NOW.date(), selected_record_id=row.decision_identity,
    )


def test_armed_outage_restart_reconnection_and_actual_entry(tmp_path):
    armed, *_ = _position()
    store = LocalActiveTradeLifecycleStore(tmp_path.resolve())
    interrupted, _, _ = ActiveTradeLifecycleEngine.monitoring_unavailable(
        armed, occurred_at=NOW + timedelta(minutes=1), provider_context="CONNECTION-LOST"
    )
    store.retain_position(interrupted)
    restored = store.load().positions[0]
    assert restored.state is ActiveLifecycleState.MONITORING_UNAVAILABLE
    assert restored.prior_state is ActiveLifecycleState.PAPER_ARMED
    assert restored.actual_entry is restored.entry_timestamp is None
    for position in (armed, interrupted, restored):
        html = _page(position)
        assert "1 WAITING · 0 ACTIVE" in html
        assert "WAITING FOR ENTRY" in html
        assert "₹0" not in html
        assert "Observation / actual entry</span><strong>—" in html
        if position.state is ActiveLifecycleState.MONITORING_UNAVAILABLE:
            assert "● INTERRUPTED" in html

    reconnected, events, _, _ = ActiveTradeLifecycleEngine.observe(
        restored, _observation(restored, 2, "99")
    )
    assert reconnected.state is ActiveLifecycleState.PAPER_ARMED
    assert events[0].event_type.value == "MONITORING_RESUMED"
    assert "1 WAITING · 0 ACTIVE" in _page(reconnected)
    entered, _, _, _ = ActiveTradeLifecycleEngine.observe(
        reconnected, _observation(reconnected, 3, "102")
    )
    assert entered.state is ActiveLifecycleState.PAPER_ACTIVE
    assert entered.actual_entry == Decimal("102")
    assert "0 WAITING · 1 ACTIVE" in _page(entered)
    after_entry_outage, _, _ = ActiveTradeLifecycleEngine.monitoring_unavailable(
        entered, occurred_at=NOW + timedelta(minutes=4), provider_context="CONNECTION-LOST"
    )
    store.retain_position(after_entry_outage)
    restored_entered = store.load().positions[0]
    assert restored_entered.prior_state is ActiveLifecycleState.PAPER_ACTIVE
    active_html = _page(restored_entered)
    assert "0 WAITING · 1 ACTIVE" in active_html
    assert "MONITORING INTERRUPTED" in active_html
    assert "● INTERRUPTED" in active_html
    assert "102" in active_html


def test_v2_handoff_retains_interrupted_pre_entry_state(tmp_path):
    completed, observation = _green(tmp_path)
    activated = _record(
        completed, observation, SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.ACTIVATED,
        risk_state="RISK_APPROVED", risk_identity="RISK-1",
        existing_sponsor_decision_identity="SPONSOR-DECISION-1",
        sponsor_position_identity="SPONSOR-POSITION-1",
    )
    ledger, _ = _v2(tmp_path, activated)
    facts = GovernedPositionPresentationFactsV2(
        activated.decision.decision_identity, "SPONSOR-POSITION-1",
        SponsorTradeChoice.PAPER, "MONITORING_UNAVAILABLE",
        None, None, None, None, "9" * 64, prior_state="PAPER_ARMED",
    )
    row = ledger.operational_handoffs(
        governed_current_trading_date=NOW.date(),
        position_facts={activated.decision.decision_identity: facts},
    )[0]
    assert row.sponsor_position_state == "MONITORING_UNAVAILABLE"
    assert row.sponsor_position_prior_state == "PAPER_ARMED"
    assert row.entry is row.position_gross_pnl is None
    html = render_trade_journal(_ready(), None, operational=(row,),
                                governed_trading_date=NOW.date())
    assert "1 WAITING · 0 ACTIVE" in html
    assert "● INTERRUPTED" in html


def test_step33_failure_is_visible_on_research_and_history_without_get_repair(tmp_path):
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.current_swing_trading_date = lambda: NOW.date()
    cached, service, *_ = _run_paper(tmp_path / "cached-source")
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore((tmp_path / "review").resolve()),
        trade_journal_service=service,
    )
    assert workflow.journal_current_snapshot().records == cached.records
    historical_id = cached.records[0].journal_record_id
    server = create_browser_server(application, port=0, native_review=workflow)
    original_step33 = server.native_review.journal_snapshot
    original_v2 = server.trade_window.reconcile_journal_read_models
    calls = []
    def failed_step33():
        calls.append("STEP33")
        raise OSError("injected reconciliation failure")
    def healthy_v2():
        calls.append("V2")
    server.native_review.journal_snapshot = failed_step33
    server.trade_window.reconcile_journal_read_models = healthy_v2
    server._next_swing_journal_reconciliation = 0.0
    server._service_actions_admitted()
    assert calls == ["STEP33", "V2"]
    assert server._swing_step33_reconciliation_failure == "SOURCE_UNAVAILABLE"
    assert server._swing_v2_reconciliation_failure is None
    server._next_swing_journal_reconciliation = float("inf")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def get(route):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request("GET", route)
        response = connection.getresponse()
        result = response.status, response.read().decode("utf-8")
        connection.close()
        return result
    def inventory():
        return {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in tmp_path.rglob("*") if path.is_file()}
    try:
        before = inventory()
        for _ in range(2):
            operational = get("/journal")
            research = get("/journal?view=research")
            history = get("/journal?view=research&record=" + historical_id)
            assert operational[0] == 200 and "SWING JOURNAL SOURCE UNAVAILABLE" in operational[1]
            assert research[0] == history[0] == 503
            assert "Step-33 reconciliation unavailable" in research[1]
            assert "Step-33 reconciliation unavailable" in history[1]
        assert calls == ["STEP33", "V2"]
        assert inventory() == before

        server.native_review.journal_snapshot = original_step33
        server.trade_window.reconcile_journal_read_models = original_v2
        server._next_swing_journal_reconciliation = 0.0
        server._service_actions_admitted()
        server._next_swing_journal_reconciliation = float("inf")
        assert server._swing_step33_reconciliation_failure is None
        assert get("/journal?view=research")[0] == 200
        restored_history = get("/journal?view=research&record=" + historical_id)
        assert restored_history[0] == 200 and historical_id in restored_history[1]

        server.trade_window.reconcile_journal_read_models = lambda: (_ for _ in ()).throw(OSError("V2 failure"))
        server._next_swing_journal_reconciliation = 0.0
        server._service_actions_admitted()
        server._next_swing_journal_reconciliation = float("inf")
        assert server._swing_step33_reconciliation_failure is None
        assert server._swing_v2_reconciliation_failure == "SOURCE_UNAVAILABLE"
        assert get("/journal?view=research")[0] == 200
        assert get("/journal")[0] == 200
        assert "SWING JOURNAL SOURCE UNAVAILABLE" in get("/journal")[1]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
