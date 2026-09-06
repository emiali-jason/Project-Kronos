from __future__ import annotations

from dataclasses import replace
from http.client import HTTPConnection
from io import BytesIO
from threading import Thread
from xml.etree import ElementTree
from zipfile import ZipFile

from kronos.application.intraday_runtime import create_intraday_workstation
from kronos.application.intraday_statistics import (
    CANDIDATE_COLUMNS,
    IntradayStatisticsApplication,
    IntradayStatisticsRow,
    project_intraday_statistics,
)
from kronos.application.intraday_review_v2 import IntradayReviewV2Snapshot
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_statistics import (
    INTRADAY_XLSX_MIME,
    export_intraday_statistics_xlsx,
    intraday_statistics_filename,
)
from kronos.browser.product_routes import BrowserGetRequest, ProductBrowserRoutes
from kronos.browser.server import create_browser_server
from kronos.intraday.review_v2 import CURRENT_REVIEW_V2_POINTER_IDENTITY
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from tests.unit.application.test_intraday_statistics import _current, _projection
from tests.unit.application.test_swing_opportunities import _Provider, _ready


_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _rows(payload: bytes, sheet: int) -> list[list[str]]:
    with ZipFile(BytesIO(payload)) as archive:
        root = ElementTree.fromstring(
            archive.read(f"xl/worksheets/sheet{sheet}.xml")
        )
    rows = []
    for row in root.findall(".//x:sheetData/x:row", _NS):
        values = []
        for cell in row.findall("x:c", _NS):
            value = (
                cell.find("x:is/x:t", _NS)
                if cell.get("t") == "inlineStr"
                else cell.find("x:v", _NS)
            )
            values.append("" if value is None or value.text is None else value.text)
        rows.append(values)
    return rows


def test_intraday_workbook_is_deterministic_three_sheet_formula_free_xlsx() -> None:
    projection = _projection()
    first = export_intraday_statistics_xlsx(projection)
    second = export_intraday_statistics_xlsx(projection)
    assert first == second

    with ZipFile(BytesIO(first)) as archive:
        names = set(archive.namelist())
        workbook = archive.read("xl/workbook.xml").decode()
        summary = archive.read("xl/worksheets/sheet1.xml").decode()
        candidates = archive.read("xl/worksheets/sheet2.xml").decode()
        stages = archive.read("xl/worksheets/sheet3.xml").decode()
    assert names >= {
        "xl/worksheets/sheet1.xml",
        "xl/worksheets/sheet2.xml",
        "xl/worksheets/sheet3.xml",
        "xl/styles.xml",
    }
    assert "vbaProject" not in " ".join(names)
    assert "externalLinks" not in " ".join(names)
    assert [workbook.index(f'name="{name}"') for name in (
        "SUMMARY", "CURRENT CANDIDATES", "STAGE STATUS"
    )] == sorted(workbook.index(f'name="{name}"') for name in (
        "SUMMARY", "CURRENT CANDIDATES", "STAGE STATUS"
    ))
    for sheet in (summary, candidates, stages):
        assert '<pane ySplit="1"' in sheet
        assert "<autoFilter " in sheet
        assert "<f>" not in sheet
    assert _rows(first, 2)[0] == list(CANDIDATE_COLUMNS)
    assert len(_rows(first, 2)) == 2
    assert len(_rows(first, 3)) == 10
    # Count values remain numeric cells, while all identities remain inline strings.
    assert '<c r="B2"><v>1</v></c>' in summary
    assert 't="inlineStr"' in candidates


def test_formula_prefixes_remain_literal_inline_strings() -> None:
    projection = _projection()
    values = list(projection.candidates[0].values)
    values[0] = '=HYPERLINK("https://invalid.example")'
    poisoned = replace(
        projection,
        candidates=(IntradayStatisticsRow(tuple(values)),),
    )
    payload = export_intraday_statistics_xlsx(poisoned)
    with ZipFile(BytesIO(payload)) as archive:
        sheet = archive.read("xl/worksheets/sheet2.xml").decode()
        names = archive.namelist()
    assert "<f>" not in sheet
    assert "=HYPERLINK" in sheet
    assert "externalLinks" not in " ".join(names)


def test_intraday_filename_is_safe_and_exact() -> None:
    projection = _projection()
    assert intraday_statistics_filename(projection.generated_at) == (
        "KRONOS_INTRADAY_REPORT_20260828_111500_IST.xlsx"
    )


def _routes(calls: list[str] | None = None):  # type: ignore[no-untyped-def]
    run, review, readiness = _current()

    def probables():  # type: ignore[no-untyped-def]
        if calls is not None:
            calls.append("probables")
        return run

    def current_review():  # type: ignore[no-untyped-def]
        if calls is not None:
            calls.append("review")
        return review

    def current_readiness():  # type: ignore[no-untyped-def]
        if calls is not None:
            calls.append("readiness")
        return readiness

    statistics = IntradayStatisticsApplication(
        current_probables=probables,
        current_review=current_review,
        operational_readiness=current_readiness,
        clock=lambda: run.analysis_boundary,
    )
    return IntradayBrowserRoutes(
        create_intraday_workstation(), statistics=statistics
    ), statistics


def test_opportunities_control_is_compact_mobile_safe_and_get_is_inert() -> None:
    calls: list[str] = []
    routes, _ = _routes(calls)
    response = routes.handle_get(BrowserGetRequest("/intraday", {}), _ready)
    assert response is not None and response.status.value == 200
    assert type(response.body) is str
    assert "STATISTICS / EXCEL" in response.body
    assert 'href="/reports/export.xlsx?product=INTRADAY"' in response.body
    assert response.body.count("intraday-statistics-export\"") == 1
    navigation = response.body.split(
        '<nav class="tabs intraday-tabs" aria-label="Intraday workflow">', 1
    )[1].split("</nav>", 1)[0]
    assert "STATISTICS / EXCEL" not in navigation
    assert (
        '<div class="intraday-statistics-actions"><a '
        'class="intraday-statistics-export"'
    ) in response.body
    assert (
        ".intraday-statistics-shell{display:grid;"
        "grid-template-columns:minmax(0,1fr) auto"
    ) in response.body
    assert (
        "@media(max-width:760px){.intraday-statistics-shell{display:block;"
        "margin:-18px -18px 18px}"
    ) in response.body
    assert (
        ".intraday-statistics-export{box-sizing:border-box;"
        "flex:1 1 100%;width:100%}"
    ) in response.body
    assert calls == []

    review_page = routes.handle_get(
        BrowserGetRequest("/intraday/review", {}), _ready
    )
    assert review_page is not None
    assert "STATISTICS / EXCEL" not in review_page.body
    assert "Statistics" not in navigation


def test_download_route_returns_exact_attachment_without_persistence(tmp_path) -> None:
    routes, _ = _routes()
    application = SwingOpportunitiesApplication(
        _Provider, initial_snapshot=_ready()
    )
    server = create_browser_server(
        application,
        port=0,
        native_review=NativeReviewWorkflow(
            NativeReviewEvidenceStore((tmp_path / "native").resolve())
        ),
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore((tmp_path / "legacy").resolve())
        ),
        product_routes=ProductBrowserRoutes((routes,)),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request("GET", "/reports/export.xlsx?product=INTRADAY")
        response = connection.getresponse()
        payload = response.read()
        headers = dict(response.getheaders())
        connection.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert response.status == 200
    assert headers["Content-Type"] == INTRADAY_XLSX_MIME
    assert headers["Content-Disposition"] == (
        'attachment; filename="KRONOS_INTRADAY_REPORT_20260828_101500_IST.xlsx"'
    )
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert _rows(payload, 1)[0][0] == "Metric"
    assert before == after


def test_no_current_probables_returns_bounded_conflict() -> None:
    run, _, _ = _current()
    statistics = IntradayStatisticsApplication(
        current_probables=lambda: None,
        current_review=lambda: IntradayReviewV2Snapshot(None, None, ()),
        operational_readiness=lambda: {"reviews": ()},
        clock=lambda: run.analysis_boundary,
    )
    routes = IntradayBrowserRoutes(
        create_intraday_workstation(), statistics=statistics
    )
    response = routes.handle_get(
        BrowserGetRequest(
            "/reports/export.xlsx", {"product": ["INTRADAY"]}
        ),
        _ready,
    )
    assert response is not None
    assert response.status.value == 409
    assert response.body == (
        "Intraday current operational snapshot could not be generated."
    )


def test_workbook_provenance_uses_current_review_schema_only() -> None:
    projection = _projection()
    review_metric = next(
        item for item in projection.metrics if item.metric == "Review Cycles"
    )
    assert review_metric.source_schema_identity == CURRENT_REVIEW_V2_POINTER_IDENTITY
    assert "WO10" not in " ".join(
        str(value) for row in projection.candidates for value in row.values
    )
