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
from tests.unit.swing.v1.test_observation_research_ledger import _service
from tests.unit.swing.v1.test_sponsor_observation_decision import _green, _record
from kronos.swing.v1.sponsor_observation_decision import SponsorActivationDisposition


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


def test_observation_research_is_compact_separate_and_has_no_performance_metrics(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed, observation = _green(tmp_path / "source")
    result = _record(
        completed, observation, SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
    )
    observations = _service(tmp_path / "ledger", result).snapshot()
    journal = TradeJournalService(
        LocalTradeJournalStore((tmp_path / "journal").resolve())
    ).snapshot()

    html = render_trade_journal(
        _ready(), journal, observations=observations,
        observation_choice="PAPER", observation_activation="BLOCKED",
    )
    research = html.split("EXISTING STEP-33 TRADING JOURNAL", 1)[0]
    assert "OBSERVATION RESEARCH" in research
    assert "DECISION-TIME EVIDENCE" in research
    assert "OBJECTIVE MODEL" in research and "SPONSOR POSITION" in research
    assert "BLOCKED_RISK_UNAVAILABLE" in research
    assert "Objective outcome</span><strong>UNAVAILABLE" in research
    assert "K1_1H_DIRECTIONAL_PROGRESSION" in research
    assert "Entry</span><strong>100" in research
    assert "Sponsor decision" in research and "Sponsor reason" in research
    assert "Observations</span><strong>1" in research
    assert "Win rate" not in research and "Gross P&amp;L" not in research
    assert "/journal?observation_choice=LIVE" in html
