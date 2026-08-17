from http.client import HTTPConnection
from threading import Thread

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_trade_journal
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.native_trade_journal import LocalTradeJournalStore, TradeJournalService
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.swing.v1.test_native_sponsor_decision import _go
from tests.unit.swing.v1.test_native_trade_journal import _empty_lifecycle, _run_paper
from tests.unit.swing.v1.test_native_trade_construction import _ready as _ready_inputs


def test_journal_renders_factual_analytics_model_actual_and_filters(tmp_path) -> None:  # type: ignore[no-untyped-def]
    journal, *_ = _run_paper(tmp_path)
    html = render_trade_journal(_ready(), journal)
    assert "Trading Journal" in html
    assert "Completed" in html and "Paper" in html and "Win rate" in html
    assert "Gross P&amp;L" in html
    assert "MODEL, ACTUAL & PROVENANCE" in html
    assert "Model Entry" in html and "Actual Entry" in html
    assert "/journal?filter=PAPER" in html and "/journal?filter=IGNORED" in html
    assert "place_order" not in html


def test_ignored_journal_renders_no_fake_position_or_pnl(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result, plan, *_ = _go(SponsorTradeChoice.IGNORE)
    readiness, _ = _ready_inputs()
    service = TradeJournalService(LocalTradeJournalStore(tmp_path.resolve()))
    journal = service.reconcile((plan,), (readiness,), (result,), _empty_lifecycle())
    html = render_trade_journal(_ready(), journal, selected_filter="IGNORED")
    assert "IGNORE ·" in html
    assert "Position</span><strong>NONE" in html
    assert "Outcome</span><strong>NOT APPLICABLE" in html


def test_empty_and_mode_filtered_journal_are_safe(tmp_path) -> None:  # type: ignore[no-untyped-def]
    journal, *_ = _run_paper(tmp_path)
    html = render_trade_journal(_ready(), journal, selected_filter="LIVE")
    assert "No journal records match this view." in html
    assert "Win rate" in html


def test_actual_browser_journal_route_restores_records_and_filters_without_mutation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    journal, service, *_ = _run_paper(tmp_path / "facts")
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore((tmp_path / "native").resolve()),
        trade_journal_service=service,
    )
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    server = create_browser_server(
        application, port=0, native_review=workflow,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore((tmp_path / "legacy").resolve())
        ),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request("GET", "/journal?filter=PAPER")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
        assert response.status == 200
        assert "PAPER ·" in body and journal.records[0].instrument in body
        assert "Trading Journal" in body
        assert workflow.journal_snapshot().records == journal.records
    finally:
        server.shutdown(); thread.join(timeout=2); server.server_close()
