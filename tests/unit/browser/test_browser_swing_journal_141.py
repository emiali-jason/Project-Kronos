"""WO-14.1: exact Journal truth without opening runtime or Provider sessions."""
from dataclasses import replace
from datetime import timedelta
from threading import RLock
from types import SimpleNamespace

from kronos.application.paper_observation_tracking import PaperObservationTrackingWorkflow
from kronos.browser.views import render_trade_journal
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleMonitoringCoordinator, ActiveLifecycleState,
)
from kronos.swing.v1.observation_research_ledger_v2 import (
    ObservationMode, ObservationOperationalRoute,
)
from kronos.swing.v1.paper_observation_track import (
    PaperObservationMonitoringState, PaperObservationTrackState,
)
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.browser.test_browser_native_trade_journal import _operational, NOW


def _page(rows=(), *, search="", source="AVAILABLE", selected=None):
    return render_trade_journal(
        _ready(), None, operational=rows, search=search,
        operational_source_status=source, selected_record_id=selected,
        governed_trading_date=NOW.date(),
    )


def test_source_unavailable_healthy_empty_and_filter_no_match_are_distinct():
    assert "SWING JOURNAL SOURCE UNAVAILABLE" in _page(source="DATE_UNAVAILABLE")
    assert "NO CURRENT SWING TRADES OR OBSERVATIONS" in _page()
    row = _operational("NIFTY", ObservationMode.LIVE)
    assert "NO MATCHING SWING JOURNAL ROWS" in _page((row,), search="BANK")
    retained = _page((row,), source="SOURCE_UNAVAILABLE")
    assert "Retained rows are visible; currentness is unavailable" in retained
    assert "NIFTY" in retained


def test_paper_armed_waits_without_fill_or_fabricated_pnl_then_progresses():
    armed = replace(_operational("NIFTY", ObservationMode.PAPER),
                    sponsor_position_state="PAPER_ARMED", entry=None,
                    position_gross_pnl=None, monitoring_state="UNKNOWN")
    html = _page((armed,))
    assert "WAITING FOR ENTRY" in html
    assert "ARMED / WAITING" in html
    assert "1 WAITING · 0 ACTIVE" in html
    assert "₹0" not in html
    entered = replace(armed, sponsor_position_state="PAPER_ACTIVE",
                      entry=100, monitoring_state="ACTIVE")
    progressed = _page((entered,))
    assert "WAITING FOR ENTRY" not in progressed
    assert "● ACTIVE" in progressed


def test_exact_historical_lineage_and_missing_links_do_not_use_current_run():
    old = replace(
        _operational("NIFTY", ObservationMode.LIVE,
                     route=ObservationOperationalRoute.HISTORICAL, decision="DECISION-OLD"),
        native_run_identity="RUN-OLD", native_assessment_sha256="a" * 64,
        decision_snapshot_identity="SNAPSHOT-OLD", trade_plan_identity="PLAN-OLD",
        sponsor_position_identity="POSITION-OLD", research_record_identity="RESEARCH-OLD",
        source_events=(("LIFECYCLE_EVENT", "EVENT-OLD", "ACTIVE_LIFECYCLE / 1"),),
        source_versions=(("DECISION", "2"),),
        step33_record_identity="STEP33-OLD",
    )
    successor = replace(old, decision_identity="DECISION-NEW", native_run_identity="RUN-NEW")
    html = _page((old, successor), selected="DECISION-OLD")
    assert "RUN-OLD" in html and "RUN-NEW" not in html
    assert "PLAN-OLD" in html and "POSITION-OLD" in html
    assert "EVENT-OLD" in html and "DECISION / 2" in html
    assert '/journal?view=research&amp;record=STEP33-OLD' in html
    assert '/journal?product=SWING&amp;record=DECISION-OLD' in html
    missing = _page((replace(old, step33_record_identity=None,
                             trade_plan_identity=None, source_events=()),),
                    selected="DECISION-OLD")
    assert "UNAVAILABLE" in missing
    assert "STEP33-OLD" not in missing
    assert "EXACT JOURNAL RECORD UNAVAILABLE" in _page((old,), selected="MISSING")
    special = replace(old, decision_identity="DECISION+OLD")
    assert "record=DECISION%2BOLD" in _page((special,), selected="DECISION+OLD")


def test_position_monitoring_requires_exact_owner_connected_session_and_latest_tick():
    tick = SimpleNamespace(instrument="NIFTY", observed_at=NOW,
                           connection_id="SESSION-1", session_continuous=True,
                           ordering_deterministic=True)
    position = SimpleNamespace(state=ActiveLifecycleState.PAPER_ACTIVE,
                               last_observed_at=NOW, last_observation_id="OBS-1")
    owner = ActiveLifecycleMonitoringCoordinator.__new__(ActiveLifecycleMonitoringCoordinator)
    owner._service = SimpleNamespace(_require=lambda identity: position)
    owner._lock = RLock()
    consumer = SimpleNamespace(closed=False, session=SimpleNamespace(
        connection_state=MonitoringConnectionState.CONNECTED),
        instrument="NIFTY", last_accepted_tick=tick)
    owner._consumers = {"POSITION-1": consumer}
    owner._monitoring_hub = SimpleNamespace(latest_market_ticks=(tick,))
    assert owner.journal_monitoring_evidence("POSITION-1") == ("ACTIVE", "SESSION-1", "OBS-1")
    assert owner.journal_monitoring_evidence("WRONG-POSITION")[0] == "UNKNOWN"
    consumer.session.subscriptions = ()
    assert owner.journal_monitoring_evidence("POSITION-1")[0] == "UNKNOWN"
    consumer.session.subscriptions = ("NIFTY",)
    owner._monitoring_hub.latest_market_ticks = (SimpleNamespace(
        instrument="NIFTY", observed_at=NOW + timedelta(seconds=1)),)
    assert owner.journal_monitoring_evidence("POSITION-1")[0] == "UNKNOWN"
    consumer.session.connection_state = MonitoringConnectionState.DISCONNECTED
    assert owner.journal_monitoring_evidence("POSITION-1")[0] == "INTERRUPTED"
    owner._consumers = {}  # restart before owner restoration
    assert owner.journal_monitoring_evidence("POSITION-1")[0] == "UNKNOWN"
    position.state = ActiveLifecycleState.CLOSED
    assert owner.journal_monitoring_evidence("POSITION-1")[0] == "NOT_REQUIRED"


def test_paper_observation_monitoring_has_separate_exact_track_owner():
    tick = SimpleNamespace(instrument="NIFTY", observed_at=NOW,
                           connection_id="TRACK-SESSION", session_continuous=True,
                           ordering_deterministic=True)
    projection = SimpleNamespace(track_state=PaperObservationTrackState.ACTIVE,
                                 monitoring_state=PaperObservationMonitoringState.ACTIVE,
                                 last_factual_observation_at=NOW)
    owner = PaperObservationTrackingWorkflow.__new__(PaperObservationTrackingWorkflow)
    owner.projection = lambda identity: projection
    owner._lock = RLock()
    registration = SimpleNamespace(active=True,
        connection_state=MonitoringConnectionState.CONNECTED)
    owner._registrations = {"TRACK-1": registration}
    owner._consumers = {"TRACK-1": SimpleNamespace(
        _detached=False, _last_accepted_tick=tick, _instrument="NIFTY")}
    owner._hub = SimpleNamespace(latest_market_ticks=(tick,))
    assert owner.journal_monitoring_evidence("TRACK-1")[0] == "ACTIVE"
    assert owner.journal_monitoring_evidence("WRONG-TRACK")[0] == "UNKNOWN"
    projection.last_factual_observation_at = NOW - timedelta(minutes=1)
    assert owner.journal_monitoring_evidence("TRACK-1")[0] == "UNKNOWN"
    projection.monitoring_state = PaperObservationMonitoringState.INTERRUPTED
    assert owner.journal_monitoring_evidence("TRACK-1")[0] == "INTERRUPTED"
    projection.track_state = PaperObservationTrackState.COMPLETE
    assert owner.journal_monitoring_evidence("TRACK-1")[0] == "NOT_REQUIRED"


def test_step33_current_snapshot_is_read_only_and_maintenance_reconciles(tmp_path):
    from kronos.application.swing_native_review import NativeReviewWorkflow
    from kronos.swing.v1.native_review import NativeReviewEvidenceStore
    from kronos.swing.v1.native_trade_journal import LocalTradeJournalStore, TradeJournalService

    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore((tmp_path / "review").resolve()),
        trade_journal_service=TradeJournalService(
            LocalTradeJournalStore((tmp_path / "step33").resolve())
        ),
    )
    def inventory():
        return {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in tmp_path.rglob("*") if path.is_file()}
    before = inventory()
    assert workflow.journal_current_snapshot() == workflow.journal_current_snapshot()
    assert inventory() == before
    calls = []
    workflow._reconcile_journal_unlocked = lambda: calls.append("STEP33")
    workflow.journal_current_snapshot()
    assert calls == []
    workflow.journal_snapshot()
    assert calls == ["STEP33"]


def test_existing_server_maintenance_pulse_owns_both_reconciliations(tmp_path):
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.browser.server import create_browser_server
    from tests.unit.application.test_swing_opportunities import _Provider

    server = create_browser_server(
        SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready()), port=0,
    )
    try:
        calls = []
        server.native_review.journal_snapshot = lambda: calls.append("STEP33")
        server.trade_window.reconcile_journal_read_models = lambda: calls.append("V2")
        server._next_swing_journal_reconciliation = 0.0
        server._service_actions_admitted()
        assert calls == ["STEP33", "V2"]
        server._service_actions_admitted()
        assert calls == ["STEP33", "V2"]
    finally:
        server.server_close()


def test_repeated_journal_and_status_gets_preserve_retained_bytes_and_metadata(tmp_path):
    from http.client import HTTPConnection
    from threading import Thread
    from kronos.application.swing_native_review import NativeReviewWorkflow
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.browser.server import create_browser_server
    from kronos.swing.v1.native_review import NativeReviewEvidenceStore
    from tests.unit.application.test_swing_opportunities import _Provider

    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.current_swing_trading_date = lambda: NOW.date()
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore((tmp_path / "review").resolve())
    )
    server = create_browser_server(application, port=0, native_review=workflow)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def inventory():
        return {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in tmp_path.rglob("*") if path.is_file()}
    try:
        before = inventory()
        for route in ("/journal", "/journal?record=MISSING",
                      "/journal?view=research", "/status"):
            for _ in range(2):
                connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                connection.request("GET", route)
                response = connection.getresponse()
                response.read()
                connection.close()
                assert response.status == 200
        assert inventory() == before
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_intraday_route_does_not_read_unavailable_swing_step33(tmp_path):
    from http.client import HTTPConnection
    from threading import Thread
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.browser.server import create_browser_server
    from kronos.intraday.wo14_journal_contract import JournalSnapshot
    from tests.unit.application.test_swing_opportunities import _Provider

    server = create_browser_server(
        SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready()), port=0,
    )
    server.intraday_journal = SimpleNamespace(snapshot=lambda **_: JournalSnapshot((), ()))
    def unavailable():
        raise AssertionError("Intraday GET read Swing Step-33")
    server.native_review.journal_current_snapshot = unavailable
    server.native_review.journal_snapshot = unavailable
    # Keep this route-level test independent of the admitted periodic pulse.
    server._next_swing_journal_reconciliation = float("inf")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request("GET", "/journal?product=INTRADAY")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
        assert response.status == 200
        assert "NO INTRADAY JOURNAL RECORDS" in body
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_lagging_step33_store_is_unchanged_by_read_then_reconciled_once(tmp_path):
    from kronos.application.swing_native_review import NativeReviewWorkflow
    from kronos.swing.v1.native_review import NativeReviewEvidenceStore
    from kronos.swing.v1.native_trade_journal import LocalTradeJournalStore, TradeJournalService
    from tests.unit.swing.v1.test_native_trade_journal import _run_paper

    expected, _, lifecycle, _, decision, plan, readiness = _run_paper(tmp_path / "source")
    lagging_root = (tmp_path / "lagging-step33").resolve()
    service = TradeJournalService(LocalTradeJournalStore(lagging_root))
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore((tmp_path / "review").resolve()),
        trade_journal_service=service,
    )
    def inventory():
        return {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in lagging_root.rglob("*") if path.is_file()}
    before = inventory()
    assert workflow.journal_current_snapshot().records == ()
    assert workflow.journal_current_snapshot().records == ()
    assert inventory() == before
    workflow._reconcile_journal_unlocked = lambda: service.reconcile(
        (plan,), (readiness,), (decision,), lifecycle.snapshot()
    )
    assert workflow.journal_snapshot().records == expected.records
    after = inventory()
    assert after != before
    workflow.journal_snapshot()
    assert inventory() == after
    restarted = TradeJournalService(LocalTradeJournalStore(lagging_root))
    assert restarted.snapshot().records == expected.records
    restarted.reconcile((plan,), (readiness,), (decision,), lifecycle.snapshot())
    assert inventory() == after
