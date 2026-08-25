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
    assert projection.overview.net_pnl == Decimal("250")
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
        "Date", "Completed / Exited At", "Instrument", "Direction", "Family", "Status"
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


def test_reports_excel_empty_population_is_valid_and_intraday_fails_bounded(
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
    with pytest.raises(ValueError, match="REPORTS_EXCEL_PRODUCT_UNAVAILABLE"):
        export_reports_xlsx(intraday, generated_at=NOW)


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
    assert "₹0" not in html and "Net P/L</span><strong>UNAVAILABLE" in html


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
    assert "INTRADAY REPORTS" in html and "NOT YET OPERATIONAL" in html
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
        body = response.read().decode("utf-8")
        connection.close()
        assert response.status == 409
        assert body == "Intraday Excel reports are not yet operational."
        assert workflow.journal_snapshot().records == ()
    finally:
        server.shutdown(); thread.join(timeout=2); server.server_close()
