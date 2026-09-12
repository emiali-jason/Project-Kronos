from __future__ import annotations

import json

from kronos.application.intraday_runtime import create_intraday_workstation
from kronos.browser.intraday_research import (
    RESEARCH_OPEN_ROUTE, RESEARCH_ROUTE, RESEARCH_UPDATE_ROUTE, IntradayResearchControl,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from tests.unit.application.test_intraday_research import _application
from tests.unit.application.test_swing_opportunities import _ready


def test_research_page_get_is_inert_and_exposes_only_local_controls(tmp_path) -> None:
    application, _ = _application(tmp_path)
    routes = IntradayBrowserRoutes(create_intraday_workstation(),
                                   research_control=IntradayResearchControl(application))
    before = list(tmp_path.rglob("*"))
    response = routes.handle_get(BrowserGetRequest(RESEARCH_ROUTE, {}), _ready)
    after = list(tmp_path.rglob("*"))
    assert response.status.value == 200
    assert "UPDATE RESEARCH" in response.body
    assert "OPEN MONTHLY EXCEL" not in response.body
    assert "Google Drive" not in response.body and "OAuth" not in response.body
    assert before == after


def test_explicit_update_then_verified_open(tmp_path) -> None:
    application, _ = _application(tmp_path)
    routes = IntradayBrowserRoutes(create_intraday_workstation(),
                                   research_control=IntradayResearchControl(application))
    request = BrowserPostRequest(RESEARCH_UPDATE_ROUTE, {}, "application/json",
                                 json.dumps({"operation_identity": "SPONSOR-UPDATE-001"}).encode())
    response = routes.handle_post(request, _ready)
    assert response.status.value == 200
    result = json.loads(response.body)
    assert result["outcome"] == "PUBLISHED"

    page = routes.handle_get(BrowserGetRequest(RESEARCH_ROUTE, {}), _ready)
    assert "OPEN MONTHLY EXCEL" in page.body
    opened = routes.handle_get(BrowserGetRequest(RESEARCH_OPEN_ROUTE, {"month": ["2026_08"]}), _ready)
    assert opened.status.value == 200
    assert opened.filename == "KRONOS_Intraday_Research_2026_08.xlsx"
    assert opened.body == application.open_current("2026_08")[1]


def test_tampered_monthly_file_fails_closed(tmp_path) -> None:
    application, _ = _application(tmp_path)
    routes = IntradayBrowserRoutes(create_intraday_workstation(),
                                   research_control=IntradayResearchControl(application))
    result = application.update(operation_identity="SPONSOR-UPDATE-001")
    result.workbook_path.write_bytes(b"tampered")
    response = routes.handle_get(BrowserGetRequest(RESEARCH_OPEN_ROUTE, {"month": ["2026_08"]}), _ready)
    assert response.status.value == 409
    assert response.body == "Verified monthly research workbook unavailable."


def test_opportunities_exposes_research_as_secondary_action_not_tab() -> None:
    routes = IntradayBrowserRoutes(create_intraday_workstation())
    response = routes.handle_get(BrowserGetRequest("/intraday", {}), _ready)
    navigation = response.body.split('<nav class="tabs intraday-tabs" aria-label="Intraday workflow">', 1)[1].split("</nav>", 1)[0]
    assert "RESEARCH / ANALYSIS DETAILS" in response.body
    assert "RESEARCH / ANALYSIS DETAILS" not in navigation
    assert 'href="/intraday/research"' in response.body
