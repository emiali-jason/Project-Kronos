from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from http.client import HTTPConnection
from io import BytesIO
import json
from threading import Thread
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.browser.reports import (
    ReportFamily,
    ReportProduct,
    ReportsQuery,
    ReportView,
    export_reports_csv,
    export_reports_json,
    export_reports_xlsx,
    project_historical_reports,
    reports_excel_filename,
)
from kronos.browser.views import render_reports
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_trade_journal import (
    LocalTradeJournalStore,
    TradeJournalService,
)
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.market.calendar import MarketCalendarPublisher
from kronos.swing.v1.observation_research_ledger_v2 import (
    ObservationMode,
    ObservationOperationalHandoffV2,
    ObservationOperationalRoute,
    ObservationProduct,
    WebSocketPresentationState,
)
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorActivationDisposition,
)
from kronos.swing.v1.step31_observation import Step31WarningSeverity
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.swing.v1.test_native_trade_journal import _run_paper


NOW = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
_XLSX_NAMESPACE = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _empty_journal(tmp_path):  # type: ignore[no-untyped-def]
    return TradeJournalService(LocalTradeJournalStore(tmp_path.resolve())).snapshot()


def _record(
    instrument: str,
    mode: ObservationMode,
    *,
    when: datetime = NOW,
    direction: V1Direction = V1Direction.LONG,
    route: ObservationOperationalRoute = ObservationOperationalRoute.HISTORICAL,
    pnl: Decimal | None = Decimal("125"),
    outcome: str = "TARGET_LEVEL_TOUCHED",
    suffix: str = "",
) -> ObservationOperationalHandoffV2:
    observation = mode is ObservationMode.PAPER_OBSERVATION
    return ObservationOperationalHandoffV2(
        ObservationProduct.SWING, mode, instrument, direction,
        "SPONSOR-OBSERVATION-DECISION-" + instrument + suffix,
        when - timedelta(days=3), Step31WarningSeverity.GREEN, (),
        "RISK_APPROVED",
        (
            SponsorActivationDisposition.BLOCKED_RISK_REJECTED
            if observation else SponsorActivationDisposition.ACTIVATED
        ),
        None if observation else "SPONSOR-POSITION-" + instrument + suffix,
        "UNAVAILABLE" if observation else "CLOSED",
        "PAPER-OBSERVATION-TRACK-" + instrument + suffix if observation else None,
        "COMPLETE" if observation else "NOT_APPLICABLE",
        "TARGET_LEVEL_TOUCHED" if observation else "NOT_APPLICABLE",
        outcome if observation else "NOT_APPLICABLE",
        "COMPLETE" if observation else "NOT_ACTIVE",
        "OBJECTIVE_COMPLETE", "TARGET_LEVEL_TOUCHED",
        Decimal("100"), None if observation else Decimal("110"),
        None if observation else pnl, Decimal("90"), Decimal("120"),
        None, None, None, None, "UNAVAILABLE", "UNAVAILABLE",
        "UNAVAILABLE" if observation or pnl is None else "AVAILABLE",
        when, route, WebSocketPresentationState.IDLE,
    )


def test_selected_history_actual_reports_html_and_json_csv_disclose_summary(tmp_path):
    from tests.unit.swing.v1.test_observation_research_ledger_v2 import _selected_history_service, NOW as FACT_TIME
    service,paper,track=_selected_history_service(tmp_path)
    operational=service.operational_handoffs(governed_current_trading_date=FACT_TIME.date())
    projection=project_historical_reports(operational,_empty_journal(tmp_path/'journal'),
        ReportsQuery(),governed_current_trading_date=FACT_TIME.date())
    assert len(projection.records)==1
    item=projection.records[0]
    assert item.status=='OUTCOME NOT ESTABLISHED'
    assert item.paper_history_representation=='COMPACT_HISTORICAL'
    assert item.paper_last_observation_at==FACT_TIME+timedelta(seconds=1)
    assert item.pnl is None and item.exit is None
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    html=render_reports(_ready(),projection,selected_record_id=item.record_identity)
    assert 'COMPACT_HISTORICAL' in html and 'HISTORICAL_DETAIL_UNAVAILABLE' in html
    assert item.paper_last_observation_at.isoformat() in html
    assert 'Recorded decision boundary' in html
    rows=json.loads(export_reports_json(projection))['records']
    assert rows[0]['paper_last_observation_at']==item.paper_last_observation_at.isoformat()
    assert rows[0]['paper_fact_count']==2
    assert 'COMPACT_SUMMARY_ONLY_RAW_FACTS_NOT_REVALIDATED' in export_reports_csv(projection).decode()
    assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def _xlsx_rows(payload: bytes, sheet: str = "sheet1.xml") -> list[list[str]]:
    with ZipFile(BytesIO(payload)) as archive:
        root = ElementTree.fromstring(archive.read("xl/worksheets/" + sheet))
    rows = []
    for row in root.findall(".//x:sheetData/x:row", _XLSX_NAMESPACE):
        values = []
        for cell in row.findall("x:c", _XLSX_NAMESPACE):
            if cell.get("t") == "inlineStr":
                text = cell.find("x:is/x:t", _XLSX_NAMESPACE)
            else:
                text = cell.find("x:v", _XLSX_NAMESPACE)
            values.append("" if text is None or text.text is None else text.text)
        rows.append(values)
    return rows


@pytest.mark.parametrize('population,timestamp_kind', (
    ('SPONSOR_DECISION', 'DECISION'),
    ('ADVISORY_PLAN', 'PLAN_CREATED'),
    ('POSITION', 'DECISION'),
))
def test_reports_excel_timestamp_does_not_claim_noncompleted_rows_are_exits(
    tmp_path, population, timestamp_kind,
):
    projection = project_historical_reports(
        (_record('CANBK', ObservationMode.PAPER),), _empty_journal(tmp_path),
        ReportsQuery(), governed_current_trading_date=NOW.date(),
    )
    item = replace(
        projection.records[0], completed=False, population_kind=population,
        relevant_timestamp=NOW, record_date=NOW.date(), entry=None, exit=None, pnl=None,
        source_facts=(('timestamp_kind', timestamp_kind),),
    )
    projection = replace(
        projection, records=(item,), page_records=(item,),
        overview=replace(projection.overview, completed_records=0),
    )
    rows = _xlsx_rows(export_reports_xlsx(projection, generated_at=NOW))
    assert rows[0][1] == 'Recorded At'
    assert rows[1][1] == '2026-08-25 15:30:00 IST'
    assert rows[1][rows[0].index('Source Facts')] == json.dumps(item.source_facts)
    exported = json.loads(export_reports_json(projection))['records'][0]
    assert exported['completed'] is False
    assert exported['timestamp'] == NOW.isoformat()
    assert dict(json.loads(exported['source_facts']))['timestamp_kind'] == timestamp_kind


def test_swing_reports_wrap_full_coverage_and_provenance_without_styling_intraday(tmp_path):
    from kronos.browser.views import _report_detail

    projection = project_historical_reports(
        (_record('CRUDEOIL26OCTFUT', ObservationMode.PAPER),), _empty_journal(tmp_path),
        ReportsQuery(), governed_current_trading_date=NOW.date(),
    )
    record_id = 'RETAINED-DECISION-' + 'a' * 64
    source_id = 'RETAINED-SOURCE-' + 'b' * 64
    item = replace(
        projection.records[0], record_identity=record_id,
        source_contract_identity=source_id, source_facts=(('plan_sha256', 'c' * 64),),
    )
    projection = replace(projection, records=(item,), page_records=(item,))
    html = render_reports(_ready(), projection, selected_record_id=record_id)
    assert 'class="journal-detail reports-detail swing-reports-detail"' in html
    assert record_id in html and source_id in html and 'c' * 64 in html
    style = html.split('<style>.reports-coverage', 1)[1].split('</style>', 1)[0]
    assert '.reports-coverage pre{white-space:pre-wrap;overflow-wrap:anywhere;min-width:0}' in style
    assert '.swing-reports-detail :is(h2,strong,details,.journal-detail-grid>div,.v1-context-row)' in style
    assert '{min-width:0;overflow-wrap:anywhere}' in style
    assert 'overflow:hidden' not in style and 'text-overflow:ellipsis' not in style
    assert '.reports-table-wrap{overflow-x:auto;' in html
    intraday = replace(
        projection, query=ReportsQuery(product=ReportProduct.INTRADAY),
        records=(), page_records=(), total_records=0, page_count=0,
    )
    assert '<style>.reports-coverage' not in render_reports(_ready(), intraday)
    intraday_detail = _report_detail(replace(item, intraday_facts=json.dumps({'record_identity': record_id})))
    assert 'class="journal-detail reports-detail"' in intraday_detail
    assert 'swing-reports-detail' not in intraday_detail and record_id in intraday_detail


def test_reports_projection_separates_families_and_excludes_active(tmp_path) -> None:
    records = (
        _record("CANBK", ObservationMode.PAPER),
        _record("MCX", ObservationMode.LIVE, direction=V1Direction.SHORT),
        _record("SAIL", ObservationMode.PAPER_OBSERVATION),
        _record("ACTIVE", ObservationMode.PAPER, route=ObservationOperationalRoute.ACTIVE),
    )
    projection = project_historical_reports(
        records, _empty_journal(tmp_path), ReportsQuery(),
        governed_current_trading_date=NOW.date(),
    )
    assert {item.instrument for item in projection.records} == {"CANBK", "MCX", "SAIL"}
    assert {item.instrument: item.family for item in projection.records} == {
        "CANBK": ReportFamily.PAPER,
        "MCX": ReportFamily.LIVE,
        "SAIL": ReportFamily.PAPER_OBSERVATION,
    }
    assert projection.overview.gross_pnl == Decimal("250")
    assert projection.overview.net_pnl is None
    assert projection.overview.win_rate is None


def test_reports_views_date_search_direction_and_status_filters(tmp_path) -> None:
    records = (
        _record("CANBK", ObservationMode.PAPER, when=NOW - timedelta(days=2)),
        _record("MCX", ObservationMode.LIVE, direction=V1Direction.SHORT),
        _record("SAIL", ObservationMode.PAPER_OBSERVATION),
    )
    journal = _empty_journal(tmp_path)
    paper = project_historical_reports(
        records, journal, ReportsQuery(view=ReportView.PAPER),
        governed_current_trading_date=NOW.date(),
    )
    assert [item.instrument for item in paper.records] == ["CANBK"]
    observations = project_historical_reports(
        records, journal,
        ReportsQuery(
            view=ReportView.PAPER_OBSERVATIONS,
            from_date=NOW.date(), to_date=NOW.date(), instrument="sai",
            direction=V1Direction.LONG, status="target",
        ),
        governed_current_trading_date=NOW.date(),
    )
    assert [item.instrument for item in observations.records] == ["SAIL"]


def test_reports_pagination_is_stable_without_duplicates(tmp_path) -> None:
    values = tuple(
        _record(
            f"ITEM{index:02d}", ObservationMode.PAPER,
            when=NOW - timedelta(minutes=index), suffix=f"-{index}",
        )
        for index in range(31)
    )
    first = project_historical_reports(
        values, _empty_journal(tmp_path), ReportsQuery(page=1, page_size=10),
        governed_current_trading_date=NOW.date(),
    )
    second = project_historical_reports(
        values, _empty_journal(tmp_path), ReportsQuery(page=2, page_size=10),
        governed_current_trading_date=NOW.date(),
    )
    assert first.page_count == 4
    assert len(first.page_records) == len(second.page_records) == 10
    assert not set(item.record_identity for item in first.page_records) & set(
        item.record_identity for item in second.page_records
    )
    assert first.page_records == project_historical_reports(
        values, _empty_journal(tmp_path), ReportsQuery(page=1, page_size=10),
        governed_current_trading_date=NOW.date(),
    ).page_records


def test_reports_export_preserves_filters_family_and_unavailable_values(tmp_path) -> None:
    projection = project_historical_reports(
        (_record("SAIL", ObservationMode.PAPER_OBSERVATION),),
        _empty_journal(tmp_path),
        ReportsQuery(view=ReportView.PAPER_OBSERVATIONS, instrument="SAIL"),
        governed_current_trading_date=NOW.date(),
    )
    payload = json.loads(export_reports_json(projection))
    assert payload["product"] == "SWING"
    assert payload["filters"]["instrument"] == "SAIL"
    assert payload["records"][0]["evidence_family"] == "PAPER_OBSERVATION"
    assert payload["records"][0]["pnl"] == "UNAVAILABLE"
    csv_value = export_reports_csv(projection).decode("utf-8")
    assert "PAPER_OBSERVATION" in csv_value and "UNAVAILABLE" in csv_value
    assert "win_rate" not in csv_value and "effectiveness" not in csv_value


def test_reports_excel_is_valid_filtered_mixed_family_workbook(tmp_path) -> None:
    projection = project_historical_reports(
        (
            _record("CANBK", ObservationMode.PAPER, pnl=Decimal("0")),
            _record("MCX", ObservationMode.LIVE, direction=V1Direction.SHORT),
            _record("SAIL", ObservationMode.PAPER_OBSERVATION),
        ),
        _empty_journal(tmp_path),
        ReportsQuery(view=ReportView.ALL_RECORDS),
        governed_current_trading_date=NOW.date(),
    )

    payload = export_reports_xlsx(projection, generated_at=NOW)
    with ZipFile(BytesIO(payload)) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        report_xml = archive.read("xl/worksheets/sheet1.xml")
        assert {"xl/workbook.xml", "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"} <= names
        assert b"<f" not in report_xml
    rows = _xlsx_rows(payload)
    summary = dict(_xlsx_rows(payload, "sheet2.xml"))

    assert rows[0][:6] == [
        "Date", "Recorded At", "Instrument", "Direction", "Family", "Status"
    ]
    assert len(rows) == 4
    assert {row[4] for row in rows[1:]} == {
        "PAPER POSITION", "LIVE POSITION", "PAPER OBSERVATION"
    }
    observation = next(row for row in rows[1:] if row[4] == "PAPER OBSERVATION")
    zero_position = next(row for row in rows[1:] if row[2] == "CANBK")
    assert observation[8] == "UNAVAILABLE"
    assert zero_position[8] == "0"
    assert "Actual R" not in rows[0]
    assert summary["Product"] == "SWING"
    assert summary["Report View"] == "ALL RECORDS"
    assert summary["Record Count"] == "3"
    assert reports_excel_filename(projection, NOW) == "KRONOS_SWING_REPORT_20260825_153000_IST.xlsx"


def test_reports_excel_preserves_exact_filters_and_formula_text(tmp_path) -> None:
    dangerous = "=HYPERLINK(\"https://invalid.example\")"
    projection = project_historical_reports(
        (
            _record(dangerous, ObservationMode.PAPER),
            _record("CANBK", ObservationMode.PAPER, direction=V1Direction.SHORT),
        ),
        _empty_journal(tmp_path),
        ReportsQuery(
            view=ReportView.PAPER,
            from_date=NOW.date(),
            to_date=NOW.date(),
            instrument="=HYPERLINK",
            direction=V1Direction.LONG,
            status="EXITED",
        ),
        governed_current_trading_date=NOW.date(),
    )

    payload = export_reports_xlsx(projection, generated_at=NOW)
    rows = _xlsx_rows(payload)
    summary = dict(_xlsx_rows(payload, "sheet2.xml"))
    with ZipFile(BytesIO(payload)) as archive:
        report_xml = archive.read("xl/worksheets/sheet1.xml")

    assert len(rows) == 2 and rows[1][2] == dangerous
    assert b"<f" not in report_xml
    assert b't="inlineStr"' in report_xml
    assert summary["From"] == summary["To"] == NOW.date().isoformat()
    assert summary["Instrument Filter"] == "=HYPERLINK"
    assert summary["Direction Filter"] == "LONG"
    assert summary["Status / Outcome Filter"] == "EXITED"


def test_reports_excel_empty_populations_are_valid_and_product_separated(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    empty = project_historical_reports(
        (), _empty_journal(tmp_path), ReportsQuery(),
        governed_current_trading_date=NOW.date(),
    )
    payload = export_reports_xlsx(empty, generated_at=NOW)
    assert len(_xlsx_rows(payload)) == 1
    assert dict(_xlsx_rows(payload, "sheet2.xml"))["Record Count"] == "0"

    intraday = project_historical_reports(
        (_record("CANBK", ObservationMode.PAPER),),
        _empty_journal(tmp_path),
        ReportsQuery(product=ReportProduct.INTRADAY),
        governed_current_trading_date=NOW.date(),
    )
    assert len(_xlsx_rows(export_reports_xlsx(intraday, generated_at=NOW))) == 1


def test_reports_unavailable_exit_and_position_pnl_are_not_zero(tmp_path) -> None:
    value = replace(_record("CANBK", ObservationMode.PAPER, pnl=None), exit=None)
    projection = project_historical_reports(
        (value,), _empty_journal(tmp_path), ReportsQuery(),
        governed_current_trading_date=NOW.date(),
    )
    record = projection.records[0]
    assert record.exit is None
    assert record.pnl is None and projection.overview.net_pnl is None
    html = render_reports(_ready(), projection)
    assert "₹0" not in html and "Gross P/L</span><strong>UNAVAILABLE" in html


def test_reports_preserves_legacy_v1_trade_without_backfill(tmp_path) -> None:
    journal, *_ = _run_paper(tmp_path)
    projection = project_historical_reports(
        (), journal, ReportsQuery(), governed_current_trading_date=NOW.date()
    )
    assert len(projection.records) == 1
    assert projection.records[0].source_contract_version == "1"
    assert projection.records[0].paper_track_outcome == "NOT_APPLICABLE"


def test_reports_render_factual_overview_tables_details_and_no_ws(tmp_path) -> None:
    records = (
        _record("CANBK", ObservationMode.PAPER),
        _record("MCX", ObservationMode.LIVE, direction=V1Direction.SHORT),
        _record("SAIL", ObservationMode.PAPER_OBSERVATION),
    )
    projection = project_historical_reports(
        records, _empty_journal(tmp_path), ReportsQuery(),
        governed_current_trading_date=NOW.date(),
    )
    sail = next(item for item in projection.records if item.instrument == "SAIL")
    html = render_reports(
        _ready(), projection, selected_record_id=sail.record_identity
    )
    assert "OVERVIEW" in html and "PAPER OBSERVATIONS" in html and "ALL RECORDS" in html
    assert "FACTUAL RECORDS BY MODE" in html.upper()
    assert "WIN RATE · AVERAGE R · MAX DRAWDOWN" in html
    assert "UNAVAILABLE — NOT GOVERNED IN SWING V1" in html
    assert "SAIL · HISTORICAL DETAIL" in html and "GOVERNED EVIDENCE" in html
    assert "Completed / exited at" in html and "15:30 IST" in html
    assert "TRADING JOURNAL" in html
    assert html.index(">EXCEL<") < html.index(">CSV<") < html.index(">JSON<")
    assert "WS ●" not in html and "LTP" not in html


def test_reports_observation_has_no_trade_or_pnl_semantics(tmp_path) -> None:
    projection = project_historical_reports(
        (_record(
            "SAIL", ObservationMode.PAPER_OBSERVATION,
            outcome="BOTH_ORDERING_UNRESOLVED",
        ),),
        _empty_journal(tmp_path), ReportsQuery(view=ReportView.PAPER_OBSERVATIONS),
        governed_current_trading_date=NOW.date(),
    )
    html = render_reports(_ready(), projection)
    assert "PAPER OBSERVATION" in html
    assert "BOTH_ORDERING_UNRESOLVED" in html
    assert "₹0" not in html and ">WIN<" not in html and ">LOSS<" not in html


def test_reports_intraday_is_bounded_and_has_no_swing_rows(tmp_path) -> None:
    projection = project_historical_reports(
        (_record("CANBK", ObservationMode.PAPER),), _empty_journal(tmp_path),
        ReportsQuery(product=ReportProduct.INTRADAY),
        governed_current_trading_date=NOW.date(),
    )
    html = render_reports(_ready(), projection)
    assert "LIVE_POSITION_NOT_COMMISSIONED_V1" in html and "NO HISTORICAL RECORDS" in html
    assert "CANBK" not in html


def test_reports_browser_route_and_filtered_exports_are_read_only(tmp_path) -> None:
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore((tmp_path / "native").resolve())
    )
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=_ready(),
        clock=lambda: NOW,
        market_calendar_publisher=MarketCalendarPublisher(),
    )
    server = create_browser_server(
        application, port=0, native_review=workflow,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore((tmp_path / "legacy").resolve())
        ),
    )
    server.mcx_v1_control = _empty_mcx_reports_owner(tmp_path/'empty-mcx',workflow)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for path, content_type, marker in (
            ("/reports?product=SWING&view=OVERVIEW", "text/html", "NO HISTORICAL RECORDS"),
            ("/reports/export.csv?product=SWING&view=ALL_RECORDS", "text/csv", "evidence_family"),
            ("/reports/export.json?product=SWING&view=ALL_RECORDS", "application/json", '"product":"SWING"'),
        ):
            connection = HTTPConnection(
                "127.0.0.1", server.server_port, timeout=3
            )
            connection.request("GET", path)
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            connection.close()
            assert response.status == 200
            assert response.getheader("Content-Type", "").startswith(content_type)
            assert marker in body

        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request("GET", "/reports/export.xlsx?product=SWING&view=ALL_RECORDS")
        response = connection.getresponse()
        workbook = response.read()
        content_disposition = response.getheader("Content-Disposition", "")
        connection.close()
        assert response.status == 200
        assert response.getheader("Content-Type") == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert content_disposition.startswith(
            'attachment; filename="KRONOS_SWING_REPORT_'
        ) and content_disposition.endswith('_IST.xlsx"')
        assert len(_xlsx_rows(workbook)) == 1

        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request("GET", "/reports/export.xlsx?product=INTRADAY")
        response = connection.getresponse()
        body = response.read()
        connection.close()
        assert response.status == 200
        assert len(_xlsx_rows(body)) == 1
        assert workflow.journal_snapshot().records == ()
    finally:
        server.shutdown(); thread.join(timeout=2); server.server_close()


_COMPATIBILITY_FORMATS = (
    '/reports', '/reports/export.csv', '/reports/export.json', '/reports/export.xlsx',
)


def _reports_inventory(root):
    """Capture contents and metadata, including directory membership effects."""
    import hashlib
    return {
        str(path.relative_to(root)): (
            path.is_dir(), path.stat().st_size, path.stat().st_mode,
            path.stat().st_mtime_ns, path.stat().st_ctime_ns,
            None if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in (root, *sorted(root.rglob('*')))
    }


def _reports_get(server, route):
    connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
    try:
        connection.request('GET', route)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def _empty_mcx_reports_owner(root, native):
    """Read-only fixture adapter around actual empty MCX stores, not authority."""
    from types import SimpleNamespace
    from kronos.swing.v1.mcx_trade_plan import LocalMcxTradePlanStore
    from kronos.swing.v1.mcx_contract_lifecycle import McxContractBoundLifecycle, LocalMcxHistoricalContractStore
    lifecycle = native._active_lifecycle
    return SimpleNamespace(lifecycle=lifecycle, plans=LocalMcxTradePlanStore(root/'plans'),
                           native_review=native,
                           bound=McxContractBoundLifecycle(lifecycle,LocalMcxHistoricalContractStore(root/'bindings')),
                           close=lambda:None)


@pytest.fixture
def compatibility_reports_server(tmp_path):
    """Real cached Step-33 evidence; scheduled reconciliation stays separate."""
    cached, service, *_ = _run_paper(tmp_path / 'cached-step33')
    workflow = NativeReviewWorkflow(
        NativeReviewEvidenceStore((tmp_path / 'native').resolve()),
        trade_journal_service=service,
    )
    application = SwingOpportunitiesApplication(
        _Provider, initial_snapshot=_ready(), clock=lambda: NOW,
        market_calendar_publisher=MarketCalendarPublisher(),
    )
    application.current_swing_trading_date = lambda: NOW.date()
    server = create_browser_server(application, port=0, native_review=workflow)
    server.mcx_v1_control = _empty_mcx_reports_owner(tmp_path/'empty-mcx',workflow)
    assert workflow.journal_current_snapshot().records == cached.records
    assert cached.records
    server._next_swing_journal_reconciliation = float('inf')
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.mark.parametrize('route', _COMPATIBILITY_FORMATS)
def test_reports_compatibility_all_get_formats_are_observational(
    tmp_path, compatibility_reports_server, monkeypatch, route,
):
    server = compatibility_reports_server
    calls = []

    def forbidden(*args, **kwargs):
        calls.append('MUTATION_OR_ACQUISITION')
        raise AssertionError('Reports GET crossed an admitted mutation boundary')

    monkeypatch.setattr(server.native_review, 'journal_snapshot', forbidden)
    monkeypatch.setattr(server.trade_window, 'reconcile_journal_read_models', forbidden)
    monkeypatch.setattr(server.trade_window, '_synchronize_observation_research_links', forbidden)
    monkeypatch.setattr(server.trade_window._observation_research_v2, 'synchronize', forbidden)
    monkeypatch.setattr(server.application, 'run_analysis', forbidden)
    before = _reports_inventory(tmp_path)
    for _ in range(2):
        status, payload = _reports_get(server, route+'?product=SWING&view=ALL_RECORDS')
        assert status == 200
        assert payload
    assert calls == []
    assert _reports_inventory(tmp_path) == before


@pytest.mark.parametrize('route', _COMPATIBILITY_FORMATS)
@pytest.mark.parametrize('owner,marker', (
    ('_swing_step33_reconciliation_failure', b'Step-33 reconciliation unavailable'),
    ('_swing_v2_reconciliation_failure', b'V2 reconciliation unavailable'),
))
def test_reports_compatibility_retained_failure_cannot_hide_behind_cached_evidence(
    tmp_path, compatibility_reports_server, monkeypatch, route, owner, marker,
):
    server = compatibility_reports_server
    setattr(server, owner, 'SOURCE_UNAVAILABLE')
    calls = []

    def must_not_read(*args, **kwargs):
        calls.append('READ_OR_REPAIR')
        raise AssertionError('Known failed authority was consulted by Reports GET')

    monkeypatch.setattr(server.native_review, 'journal_snapshot', must_not_read)
    monkeypatch.setattr(server.native_review, 'journal_current_snapshot', must_not_read)
    monkeypatch.setattr(server.trade_window, 'observation_operational_handoffs_v2', must_not_read)
    before = _reports_inventory(tmp_path)
    status, body = _reports_get(server, route+'?product=SWING')
    assert status == 503 and marker in body
    assert b'NO HISTORICAL RECORDS' not in body
    assert calls == []
    assert _reports_inventory(tmp_path) == before


@pytest.mark.parametrize('route', _COMPATIBILITY_FORMATS)
@pytest.mark.parametrize('source', ('STEP33', 'V2'))
def test_reports_compatibility_missing_source_is_explicit_without_repair(
    tmp_path, compatibility_reports_server, monkeypatch, route, source,
):
    server = compatibility_reports_server

    def unavailable(*args, **kwargs):
        raise OSError('isolated retained source unavailable')

    owner, method = ((server.native_review, 'journal_current_snapshot')
                     if source == 'STEP33' else
                     (server.trade_window._observation_research_v2, 'snapshot'))
    monkeypatch.setattr(owner, method, unavailable)
    before = _reports_inventory(tmp_path)
    status, body = _reports_get(server, route+'?product=SWING')
    assert status == 503 and b'Swing Reports source evidence unavailable' in body
    assert b'NO HISTORICAL RECORDS' not in body and b'/Users/' not in body
    assert _reports_inventory(tmp_path) == before


def test_reports_compatibility_admitted_recovery_is_independent(
    compatibility_reports_server, monkeypatch,
):
    server = compatibility_reports_server
    original_step33 = server.native_review.journal_snapshot
    original_v2 = server.trade_window.reconcile_journal_read_models
    failed = {'STEP33', 'V2'}
    admissions = []

    def reconcile(name, original):
        def call():
            state = server.maintenance_admission.snapshot()
            assert state['owners'].get('SERVER_PULSE', 0) > 0
            admissions.append(name)
            if name in failed:
                raise OSError('isolated '+name+' reconciliation failure')
            return original()
        return call

    monkeypatch.setattr(server.native_review, 'journal_snapshot', reconcile('STEP33', original_step33))
    monkeypatch.setattr(server.trade_window, 'reconcile_journal_read_models', reconcile('V2', original_v2))

    def pulse():
        server._next_swing_journal_reconciliation = 0.0
        server.service_actions()
        server._next_swing_journal_reconciliation = float('inf')

    pulse()
    assert server._swing_step33_reconciliation_failure is not None
    assert server._swing_v2_reconciliation_failure is not None
    failed.remove('STEP33')
    pulse()
    assert server._swing_step33_reconciliation_failure is None
    assert server._swing_v2_reconciliation_failure is not None
    for route in _COMPATIBILITY_FORMATS:
        status, body = _reports_get(server, route+'?product=SWING')
        assert status == 503 and b'V2 reconciliation unavailable' in body
    failed.add('STEP33')
    failed.remove('V2')
    pulse()
    assert server._swing_step33_reconciliation_failure is not None
    assert server._swing_v2_reconciliation_failure is None
    for route in _COMPATIBILITY_FORMATS:
        status, body = _reports_get(server, route+'?product=SWING')
        assert status == 503 and b'Step-33 reconciliation unavailable' in body
    failed.clear()
    pulse()
    assert server._swing_step33_reconciliation_failure is None
    assert server._swing_v2_reconciliation_failure is None
    for route in _COMPATIBILITY_FORMATS:
        assert _reports_get(server, route+'?product=SWING')[0] == 200
    assert admissions == ['STEP33', 'V2'] * 4


@pytest.mark.parametrize('severity', [None, *Step31WarningSeverity])
def test_reports_compatibility_optional_severity_preserves_factual_exports(tmp_path, severity):
    row = replace(_record('CANBK', ObservationMode.PAPER), step31_severity=severity)
    projection = project_historical_reports(
        (row,), _empty_journal(tmp_path), ReportsQuery(),
        governed_current_trading_date=NOW.date(),
    )
    expected = 'UNAVAILABLE' if severity is None else severity.value
    record = projection.records[0]
    assert record.step31_severity == expected
    assert record.entry == row.entry and record.exit == row.exit
    assert record.pnl == row.position_gross_pnl
    assert record.source_contract_identity == row.projection_contract_identity
    assert expected in render_reports(_ready(), projection, selected_record_id=record.record_identity)
    assert json.loads(export_reports_json(projection))['records'][0]['step31_severity'] == expected
    assert expected in export_reports_csv(projection).decode()
    assert expected in _xlsx_rows(export_reports_xlsx(projection, generated_at=NOW))[1]


@pytest.mark.parametrize('route', _COMPATIBILITY_FORMATS)
def test_reports_compatibility_intraday_does_not_use_swing_health_or_sources(
    tmp_path, compatibility_reports_server, monkeypatch, route,
):
    from tests.unit.intraday.test_wo1516_books import fixture as books_fixture
    server = compatibility_reports_server
    books, *_ = books_fixture(tmp_path/'intraday-books')
    server.intraday_books = books
    server._swing_step33_reconciliation_failure = 'SOURCE_UNAVAILABLE'
    server._swing_v2_reconciliation_failure = 'SOURCE_UNAVAILABLE'

    def forbidden(*args, **kwargs):
        raise AssertionError('Intraday Reports consulted Swing authority')

    monkeypatch.setattr(server.native_review, 'journal_snapshot', forbidden)
    monkeypatch.setattr(server.native_review, 'journal_current_snapshot', forbidden)
    monkeypatch.setattr(server.trade_window, 'observation_operational_handoffs_v2', forbidden)
    expected = books.snapshot()
    before = _reports_inventory(tmp_path)
    status, body = _reports_get(server, route+'?product=INTRADAY&view=ALL_RECORDS')
    assert status == 200
    if route.endswith('.xlsx'):
        assert 'LUPIN-20260913-100000' in str(_xlsx_rows(body))
    else:
        assert b'LUPIN-20260913-100000' in body
    assert books.snapshot() == expected
    assert _reports_inventory(tmp_path) == before


@pytest.mark.parametrize('family', ('GOLDM', 'SILVERM', 'COPPER', 'CRUDEOIL', 'NATURALGAS'))
def test_reports_compatibility_exact_mcx_history_remains_factual(tmp_path, family):
    from tests.unit.browser.test_wo14_mcx_journal_integration import fixture as mcx_fixture
    from tests.unit.swing.v1.test_mcx_contract_lifecycle import _wire_monitor, START
    from kronos.application.swing_mcx_journal import mcx_journal_handoffs
    from kronos.swing.v1.mcx_contract_profile import McxFamily
    control, position, instrument, plan = mcx_fixture(tmp_path, McxFamily(family), active=True)
    clock = [START]
    monitor, capability, _ = _wire_monitor(
        control.lifecycle, control.bound.bindings, instrument, clock,
    )
    control.native_review._active_lifecycle_monitoring = monitor
    try:
        monitor.attach(position.position_id, capability, instrument)
        clock[0] += timedelta(minutes=1)
        capability.tick(103)
        tick, _ = monitor.latest_mcx_observation(position.position_id)
        schedule = monitor._calendar.schedule('MCX', START.date(), observed_at=clock[0])
        closure = control.bound.manual_paper_exit_at_cmp(position.position_id, tick, schedule)
        rows = mcx_journal_handoffs(control, START.date()+timedelta(days=1))
        journal = _empty_journal(tmp_path/'reports-journal')
        before = _reports_inventory(tmp_path)
        projection = project_historical_reports(
            rows, journal,
            ReportsQuery(instrument=plan.contract_symbol, view=ReportView.PAPER),
            governed_current_trading_date=START.date()+timedelta(days=1),
        )
        record = projection.records[0]
        assert len(projection.records) == 1
        assert record.instrument == plan.contract_symbol
        assert record.record_identity == position.position_id
        assert record.decision_identity == position.decision_id
        assert record.entry == Decimal('101') == closure.actual_entry
        assert record.exit == tick.last_price == closure.actual_exit == Decimal('103')
        assert record.relevant_timestamp == closure.exit_timestamp
        assert record.step31_severity == 'UNAVAILABLE'
        assert record.pnl is projection.overview.net_pnl is None
        payload = json.loads(export_reports_json(projection))
        exported = payload['records'][0]
        assert exported['instrument'] == plan.contract_symbol
        assert exported['step31_severity'] == exported['pnl'] == 'UNAVAILABLE'
        assert exported['entry'] == '101' and exported['exit'] == '103'
        assert plan.contract_symbol in export_reports_csv(projection).decode()
        assert plan.contract_symbol in str(_xlsx_rows(export_reports_xlsx(projection, generated_at=NOW)))
        html = render_reports(_ready(), projection, selected_record_id=record.record_identity)
        assert plan.contract_symbol in html
        # Reports projections and all exporters preserve the retained exact source.
        assert _reports_inventory(tmp_path) == before
    finally:
        monitor.close()


def test_reports_compatibility_does_not_mask_unexpected_projector_failure(
    compatibility_reports_server, monkeypatch,
):
    import sys
    from http.client import RemoteDisconnected
    from threading import Event
    import kronos.browser.server as browser_server
    server = compatibility_reports_server
    error = Event()
    observed = []

    def fail_projection(*args, **kwargs):
        raise ValueError('isolated projector defect, not source unavailability')

    def retain_error(*args, **kwargs):
        observed.append(type(sys.exc_info()[1]))
        error.set()

    monkeypatch.setattr(browser_server, 'project_historical_reports', fail_projection)
    monkeypatch.setattr(server, 'handle_error', retain_error)
    with pytest.raises(RemoteDisconnected):
        _reports_get(server, '/reports?product=SWING')
    assert error.wait(3) and observed == [ValueError]


@pytest.mark.parametrize('owner,marker', (
    ('_swing_step33_reconciliation_failure', b'Step-33 reconciliation unavailable'),
    ('_swing_v2_reconciliation_failure', b'V2 reconciliation unavailable'),
))
def test_reports_compatibility_failure_during_read_withholds_cached_report(
    tmp_path, compatibility_reports_server, monkeypatch, owner, marker,
):
    server = compatibility_reports_server
    original = server.native_review.journal_current_snapshot

    def fail_during_read():
        cached = original()
        setattr(server, owner, 'SOURCE_UNAVAILABLE')
        return cached

    monkeypatch.setattr(server.native_review, 'journal_current_snapshot', fail_during_read)
    before = _reports_inventory(tmp_path)
    status, body = _reports_get(server, '/reports?product=SWING')
    assert status == 503 and marker in body
    assert _reports_inventory(tmp_path) == before
