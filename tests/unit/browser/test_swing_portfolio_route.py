"""WO15 Browser qualification with temporary canonical owners only.

The six-market retained fixtures establish engineering coverage. They are not
genuine positions, Provider observations, broker fills or live certification.
"""
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from html.parser import HTMLParser
from http.client import HTTPConnection
from threading import Thread

import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser.server import create_browser_server
from kronos.market.calendar import MarketCalendarPublisher
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveTradeLifecycleService,
    LocalActiveTradeLifecycleStore,
)
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from tests.unit.application.test_swing_opportunities import NOW, _ready
from tests.unit.browser.test_browser_reports import (
    _empty_mcx_reports_owner,
    _reports_get,
    _reports_inventory,
)
from tests.unit.browser.test_wo14_mcx_journal_integration import fixture as mcx_fixture
from tests.unit.intraday.test_wo1516_books import fixture as intraday_fixture
from tests.unit.swing.v1.test_native_active_trade_lifecycle import (
    _observation,
    _position,
)


MARKETS = ("NSE", *tuple(McxFamily))


def _no_provider():
    pytest.fail("Portfolio may not acquire or connect a Provider")


@contextmanager
def _server(root, *, native=None, control=None):
    """Real Browser shell, canonical installed empty owners, isolated listener."""
    native = native or NativeReviewWorkflow(
        NativeReviewEvidenceStore((root / "native").resolve())
    )
    application = SwingOpportunitiesApplication(
        _no_provider,
        initial_snapshot=_ready(),
        clock=lambda: NOW,
        market_calendar_publisher=MarketCalendarPublisher(),
    )
    application.current_swing_trading_date = lambda: NOW.date()
    server = create_browser_server(application, port=0, native_review=native)
    server.mcx_v1_control = control or _empty_mcx_reports_owner(root / "mcx", native)
    server._next_swing_journal_reconciliation = float("inf")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
        assert not thread.is_alive()


def _retained_position(root, market):
    if market != "NSE":
        control, position, instrument, plan = mcx_fixture(root, market, active=True)
        return control.native_review, control, position, plan.contract_symbol
    position, admitted, plan = _position()
    lifecycle = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root / "lifecycle"))
    lifecycle.register(admitted, plan)
    lifecycle.observe(position.position_id, _observation(position, 1, "99"))
    lifecycle.observe(position.position_id, _observation(position, 2, "102"))
    position, = lifecycle.snapshot().positions
    native = NativeReviewWorkflow(
        NativeReviewEvidenceStore((root / "native").resolve()),
        active_lifecycle_service=lifecycle,
    )
    return native, None, position, position.canonical_instrument


class _LinksAndForms(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.forms = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a":
            self.links.append(values.get("href", ""))
        elif tag == "form":
            self.forms.append(values)


def test_empty_swing_book_requires_installed_canonical_owners(tmp_path):
    with _server(tmp_path / "sources") as server:
        before = _reports_inventory(tmp_path)
        status, body = _reports_get(server, "/portfolio?product=SWING")
        assert status == 200
        assert b"SWING PORTFOLIO" in body
        assert b"NOT YET OPERATIONAL" not in body
        assert b"ENTERED PAPER / MANUAL-LIVE POSITIONS" in body
        assert b"NO RETAINED ENTERED POSITIONS" in body
        assert b"CURRENT PLAN COVERAGE UNAVAILABLE" in body
        assert b"VALID EMPTY" not in body
        assert b"All required sources were validated" not in body
        assert _reports_inventory(tmp_path) == before


@pytest.mark.parametrize("market", MARKETS)
def test_six_market_current_position_projection_is_factual_and_read_only(tmp_path, market):
    native, control, position, instrument = _retained_position(tmp_path / "sources", market)
    with _server(tmp_path / "browser", native=native, control=control) as server:
        before = _reports_inventory(tmp_path)
        for route in ("/portfolio", "/portfolio?product=SWING&mode=PAPER&state=ACTIVE"):
            status, body = _reports_get(server, route)
            assert status == 200
            text = body.decode()
            assert instrument in text and position.position_id in text
            assert "PAPER" in text and "UNKNOWN" in text
            assert "NOT YET OPERATIONAL" not in text
            links = _LinksAndForms(text)
            assert any(link.startswith("/journal") for link in links.links)
            assert not any(
                form.get("method", "get").lower() == "post"
                and form.get("action", "").startswith("/portfolio")
                for form in links.forms
            )
        assert _reports_inventory(tmp_path) == before
        assert server.swing_monitoring_hub.active_session_count == 0
        assert server.swing_monitoring_hub.subscription_count == 0


def test_swing_filters_are_strict_and_intraday_retains_its_exact_filter_contract(tmp_path):
    books, journal, futures, lifecycle, current = intraday_fixture(tmp_path / "intraday")
    with _server(tmp_path / "browser") as server:
        server.intraday_books = books
        before = _reports_inventory(tmp_path)
        invalid = (
            "product=OTHER", "product=SWING&product=SWING", "raw=true",
            "search=" + "x" * 81, "direction=BUY", "market=OTHER",
            "family=OTHER", "mode=BROKER", "state=FILLED",
            "monitoring=CONNECTED", "mode=PAPER&mode=LIVE",
            "product=INTRADAY&market=NSE", "product=INTRADAY&mode=PAPER",
            "product=INTRADAY&state=ACTIVE", "product=INTRADAY&family=GOLDM",
            "product=INTRADAY&monitoring=ACTIVE",
        )
        for query in invalid:
            assert _reports_get(server, "/portfolio?" + query)[0] == 400, query
        for monitoring in ("LIVE", "INTERRUPTED", "IDLE", "UNAVAILABLE"):
            assert _reports_get(server, "/portfolio?product=INTRADAY&monitoring=" + monitoring)[0] == 200
        for mode in ("PAPER", "LIVE", "OBJECTIVE_MODEL", "OBSERVATION"):
            assert _reports_get(server, "/portfolio?product=SWING&mode=" + mode)[0] == 200
        assert _reports_inventory(tmp_path) == before
        assert lifecycle.owner_count == lifecycle.subscription_count == 1


def test_swing_mode_market_and_search_filters_do_not_leak_nonmatching_positions(tmp_path):
    native, control, position, instrument = _retained_position(tmp_path / "sources", McxFamily.GOLDM)
    with _server(tmp_path / "browser", native=native, control=control) as server:
        before = _reports_inventory(tmp_path)
        for query in ("mode=LIVE", "market=NSE", "family=SILVERM", "search=NO-SUCH-CONTRACT", "direction=SHORT"):
            status, body = _reports_get(server, "/portfolio?product=SWING&" + query)
            assert status == 200
            assert position.position_id.encode() not in body
        status, body = _reports_get(server, "/portfolio?product=SWING&market=MCX&family=GOLDM&mode=PAPER")
        assert status == 200 and instrument.encode() in body
        assert _reports_inventory(tmp_path) == before


@pytest.mark.parametrize("failure", ("mcx_owner", "model_owner", "lifecycle_store", "generation"))
def test_missing_required_owner_or_read_boundary_is_unavailable_not_empty(tmp_path, monkeypatch, failure):
    with _server(tmp_path / "sources") as server:
        if failure == "mcx_owner":
            monkeypatch.setattr(server, "mcx_v1_control", None)
        elif failure == "model_owner":
            monkeypatch.setattr(server.trade_window, "_objective_model_store", None)
        elif failure == "generation":
            generations = []
            def changing_generation():
                generations.append(True)
                return len(generations)
            monkeypatch.setattr(server.trade_window, "reports_generation", changing_generation)
        else:
            def unavailable():
                raise OSError("ISOLATED SOURCE /Users/private/evidence unavailable")
            monkeypatch.setattr(server.native_review._active_lifecycle.store, "load", unavailable)
        before = _reports_inventory(tmp_path)
        status, body = _reports_get(server, "/portfolio?product=SWING")
        assert status == 503
        assert b"unavailable" in body.lower()
        assert b"/Users/private" not in body
        assert b"NO ACTIVE" not in body and b"VALID_EMPTY" not in body
        assert _reports_inventory(tmp_path) == before


@pytest.mark.parametrize("owner", ("_swing_step33_reconciliation_failure", "_swing_v2_reconciliation_failure"))
def test_unrelated_presentation_health_cannot_erase_valid_owner_exposure(tmp_path, owner):
    native, control, position, instrument = _retained_position(tmp_path / "sources", McxFamily.GOLDM)
    with _server(tmp_path / "browser", native=native, control=control) as server:
        setattr(server, owner, "ISOLATED_PRESENTATION_FAILURE")
        before = _reports_inventory(tmp_path)
        status, body = _reports_get(server, "/portfolio")
        assert status == 200 and position.position_id.encode() in body
        assert instrument.encode() in body and b"VALID EMPTY" not in body
        assert _reports_inventory(tmp_path) == before


@pytest.mark.parametrize("failure", ("missing_plan", "changed_plan", "changed_lifecycle"))
def test_changed_or_missing_retained_sources_fail_closed_without_repair(tmp_path, monkeypatch, failure):
    native, control, position, instrument = _retained_position(tmp_path / "sources", McxFamily.COPPER)
    with _server(tmp_path / "browser", native=native, control=control) as server:
        assert _reports_get(server, "/portfolio")[0] == 200
        if failure == "missing_plan":
            next(control.plans.root.glob("*/*/*.json")).unlink()
        elif failure == "changed_plan":
            path = next(control.plans.root.glob("*/*/*.json"))
            path.write_bytes(path.read_bytes().replace(position.trade_plan_hash.encode(), b"f" * 64))
        else:
            snapshot = control.lifecycle.snapshot()
            calls = []
            def changed_during_read():
                calls.append(True)
                return snapshot if len(calls) == 1 else replace(snapshot, positions=())
            monkeypatch.setattr(control.lifecycle, "snapshot", changed_during_read)
        before = _reports_inventory(tmp_path)
        status, body = _reports_get(server, "/portfolio")
        assert status == 503 and b"unavailable" in body.lower()
        assert b"NO ACTIVE" not in body
        assert _reports_inventory(tmp_path) == before


def test_get_and_filter_reads_never_enter_mutation_acquisition_or_reconciliation(tmp_path, monkeypatch):
    native, control, position, instrument = _retained_position(tmp_path / "sources", McxFamily.NATURALGAS)
    with _server(tmp_path / "browser", native=native, control=control) as server:
        def forbidden(*args, **kwargs):
            pytest.fail("Portfolio GET crossed a canonical mutation or acquisition owner")
        monkeypatch.setattr(native, "journal_snapshot", forbidden)
        monkeypatch.setattr(native, "reports_journal_snapshot", forbidden)
        monkeypatch.setattr(server.trade_window, "reconcile_journal_read_models", forbidden)
        monkeypatch.setattr(server.trade_window, "_synchronize_observation_research_links", forbidden)
        monkeypatch.setattr(server.trade_window._observation_research_v2, "synchronize", forbidden)
        monkeypatch.setattr(server.application, "run_analysis", forbidden)
        monkeypatch.setattr(native._active_lifecycle, "register", forbidden)
        monkeypatch.setattr(native._active_lifecycle, "observe", forbidden)
        before = _reports_inventory(tmp_path)
        for route in ("/portfolio", "/portfolio?product=SWING&search=NATURALGAS", "/portfolio?mode=LIVE"):
            assert _reports_get(server, route)[0] == 200
        assert _reports_inventory(tmp_path) == before
        assert server.swing_monitoring_hub.active_session_count == 0


@pytest.mark.parametrize("market", MARKETS)
def test_notification_dismissal_cannot_remove_current_exposure(tmp_path, market):
    from kronos.application.notifications import NotificationWorkspaceSnapshot
    from tests.unit.application.test_swing_ux10 import ux10
    from tests.unit.browser.test_browser_notification_centre import _centre, NOW as CENTRE_NOW
    native, control, position, instrument = _retained_position(tmp_path / "sources", market)
    notifications = ux10(tmp_path / "notifications")
    centre = _centre(tmp_path / "centre", [CENTRE_NOW + timedelta(days=10)])
    event = notifications.observe_active_trade_monitoring_activation(position)
    card, = centre.synchronize(
        NotificationWorkspaceSnapshot(()), notifications.snapshot(),
        current_run_identity=None, websocket_state="IDLE",
    ).records
    assert notifications.evidence(event.notification_id)["position_identity"] == position.position_id
    with _server(tmp_path / "browser", native=native, control=control) as server:
        assert position.position_id.encode() in _reports_get(server, "/portfolio")[1]
        sources_before = _reports_inventory(tmp_path / "sources")
        centre.dismiss(card.notification_identity, card.integrity_sha256)
        assert centre.synchronize(
            NotificationWorkspaceSnapshot(()), notifications.snapshot(),
            current_run_identity=None, websocket_state="IDLE",
        ).visible == ()
        before = _reports_inventory(tmp_path)
        status, body = _reports_get(server, "/portfolio")
        assert status == 200 and position.position_id.encode() in body and instrument.encode() in body
        assert _reports_inventory(tmp_path) == before
        assert _reports_inventory(tmp_path / "sources") == sources_before


def test_shared_journal_presentation_suppression_preserves_both_portfolios(tmp_path):
    native, control, position, instrument = _retained_position(tmp_path / "sources", McxFamily.CRUDEOIL)
    books, journal, futures, lifecycle, current = intraday_fixture(tmp_path / "intraday")
    journal.consume_source("TRACK", current.identity)
    journal_row, = journal.snapshot().records
    with _server(tmp_path / "browser", native=native, control=control) as server:
        server.intraday_books = books
        initial_intraday = _reports_get(server, "/portfolio?product=INTRADAY")
        assert initial_intraday[0] == 200
        source_before = _reports_inventory(tmp_path / "sources")
        journal.suppress(
            journal_identity=journal_row.journal_identity,
            revision_identity=journal_row.revision_identity,
            action_identity="WO15_ISOLATED_PRESENTATION_DELETE",
        )
        assert journal.snapshot().records == ()
        before = _reports_inventory(tmp_path)
        status, body = _reports_get(server, "/portfolio?product=SWING")
        assert status == 200 and position.position_id.encode() in body
        assert _reports_get(server, "/portfolio?product=INTRADAY") == initial_intraday
        assert _reports_inventory(tmp_path) == before
        assert _reports_inventory(tmp_path / "sources") == source_before


def test_portfolio_does_not_introduce_a_post_or_execution_endpoint(tmp_path):
    with _server(tmp_path / "sources") as server:
        before = _reports_inventory(tmp_path)
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            connection.request(
                "POST", "/portfolio", body=b"",
                headers={"Origin": "http://127.0.0.1:" + str(server.server_port),
                         "Content-Type": "application/x-www-form-urlencoded"},
            )
            response = connection.getresponse()
            assert response.status == 404
            response.read()
        finally:
            connection.close()
        assert _reports_inventory(tmp_path) == before
