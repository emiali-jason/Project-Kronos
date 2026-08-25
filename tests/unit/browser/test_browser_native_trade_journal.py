from datetime import UTC, date, datetime
from decimal import Decimal
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
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.observation_research_ledger_v2 import (
    ObservationMode,
    ObservationOperationalHandoffV2,
    ObservationOperationalRoute,
    ObservationProduct,
    WebSocketPresentationState,
)
from kronos.swing.v1.step31_observation import Step31WarningSeverity


NOW = datetime(2026, 8, 25, 5, 0, tzinfo=UTC)


def _operational(
    instrument: str,
    mode: ObservationMode,
    *,
    direction: V1Direction = V1Direction.LONG,
    route: ObservationOperationalRoute = ObservationOperationalRoute.ACTIVE,
    websocket: WebSocketPresentationState = WebSocketPresentationState.CONNECTED,
    monitoring: str = "ACTIVE",
    decision: str | None = None,
) -> ObservationOperationalHandoffV2:
    observation = mode is ObservationMode.PAPER_OBSERVATION
    return ObservationOperationalHandoffV2(
        ObservationProduct.SWING, mode, instrument, direction,
        decision or "SPONSOR-OBSERVATION-DECISION-" + instrument,
        NOW, Step31WarningSeverity.GREEN, (), "RISK_APPROVED",
        (
            SponsorActivationDisposition.BLOCKED_RISK_REJECTED
            if observation else SponsorActivationDisposition.ACTIVATED
        ),
        None if observation else "SPONSOR-POSITION-" + instrument,
        "UNAVAILABLE" if observation else "ACTIVE",
        "PAPER-OBSERVATION-TRACK-" + instrument if observation else None,
        "ACTIVE" if observation else "NOT_APPLICABLE",
        "ENTRY_OBSERVED" if observation else "NOT_APPLICABLE",
        "OUTCOME_NOT_ESTABLISHED" if observation else "NOT_APPLICABLE",
        monitoring,
        "UNAVAILABLE", "UNAVAILABLE", Decimal("100"), None, None,
        Decimal("90"), Decimal("120"), Decimal("105"), NOW,
        Decimal("15"), Decimal("15"), "AVAILABLE", "AVAILABLE",
        "UNAVAILABLE" if observation else "NOT_YET_ESTABLISHED",
        NOW if route is ObservationOperationalRoute.COMPLETED_CURRENT_TRADING_DAY else None,
        route, websocket,
    )


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
        connection.request("GET", "/journal?view=research&filter=PAPER")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
        assert response.status == 200
        assert "PAPER ·" in body and journal.records[0].instrument in body
        assert "Trading Journal" in body
        assert workflow.journal_snapshot().records == journal.records
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request("GET", "/journal")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        connection.close()
        assert response.status == 200
        assert "NO ACTIVE SWING TRADES OR OBSERVATIONS" in body
        assert "OBSERVATION RESEARCH" not in body
        assert journal.records[0].instrument not in body
    finally:
        server.shutdown(); thread.join(timeout=2); server.server_close()


def test_operational_journal_is_compact_product_separated_and_current_day_only() -> None:
    # The operational view consumes only the V2 handoff; no Journal service mutation occurs.
    records = (
        _operational("CANBK", ObservationMode.PAPER),
        _operational("MCX", ObservationMode.LIVE, direction=V1Direction.SHORT),
        _operational("SAIL", ObservationMode.PAPER_OBSERVATION),
        _operational(
            "OLD", ObservationMode.PAPER,
            route=ObservationOperationalRoute.HISTORICAL,
        ),
    )
    html = render_trade_journal(
        _ready(),
        object(),  # type: ignore[arg-type]
        operational=records,
        governed_trading_date=date(2026, 8, 25),
    )
    assert "PAPER TRADES" in html and "LIVE TRADES" in html
    assert "PAPER OBSERVATIONS" in html
    assert "CANBK" in html and "MCX" in html and "SAIL" in html
    assert "OLD" not in html
    assert "WS ● CONNECTED" in html
    assert "VIEW HISTORICAL REPORTS" in html
    assert "Win rate" not in html and "OBSERVATION RESEARCH" not in html


def test_operational_journal_search_detail_and_intraday_placeholder() -> None:
    records = (
        _operational("CANBK", ObservationMode.PAPER),
        _operational("SAIL", ObservationMode.PAPER_OBSERVATION),
    )
    html = render_trade_journal(
        _ready(), object(),  # type: ignore[arg-type]
        operational=records, governed_trading_date=date(2026, 8, 25),
        search="sail", selected_record_id=records[1].decision_identity,
    )
    assert "SAIL · READ-ONLY DETAIL" in html and "CANBK" not in html
    assert "Observation / actual entry" in html and "GOVERNED EVIDENCE" in html
    intraday = render_trade_journal(
        _ready(), object(),  # type: ignore[arg-type]
        operational=records, selected_product="INTRADAY",
    )
    assert "INTRADAY JOURNAL" in intraday and "NOT YET OPERATIONAL" in intraday
    assert "CANBK" not in intraday and "WS ● CONNECTED" not in intraday


def test_operational_journal_ws_and_position_observation_authorities() -> None:
    disconnected = _operational(
        "CANBK", ObservationMode.PAPER,
        websocket=WebSocketPresentationState.DISCONNECTED,
        monitoring="INTERRUPTED",
    )
    html = render_trade_journal(
        _ready(), object(),  # type: ignore[arg-type]
        operational=(disconnected,), governed_trading_date=date(2026, 8, 25),
    )
    assert "WS ● DISCONNECTED" in html and "● INTERRUPTED" in html
    observation = _operational("SAIL", ObservationMode.PAPER_OBSERVATION)
    observation_html = render_trade_journal(
        _ready(), object(),  # type: ignore[arg-type]
        operational=(observation,), governed_trading_date=date(2026, 8, 25),
    )
    research = observation_html.split("PAPER OBSERVATIONS", 1)[1]
    assert "P/L" not in research and "Observation Entry" in research


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
