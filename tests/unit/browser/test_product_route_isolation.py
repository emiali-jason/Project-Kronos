from __future__ import annotations

import inspect

from kronos.application.intraday_runtime import create_intraday_workstation
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser import server as browser_server_module
from kronos.browser import views as browser_views_module
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_views import render_intraday_workstation
from kronos.browser.product_routes import (
    BrowserGetRequest,
    BrowserPostRequest,
    BrowserRouteResponse,
    ProductBrowserRoutes,
)
from tests.unit.application.test_swing_opportunities import _Provider


def _snapshot():  # type: ignore[no-untyped-def]
    return SwingOpportunitiesApplication(_Provider).snapshot()


def test_intraday_route_is_owned_and_testable_outside_shared_server() -> None:
    routes = IntradayBrowserRoutes(create_intraday_workstation())

    response = routes.handle_get(
        BrowserGetRequest("/intraday", {}),
        _snapshot,
    )

    assert type(response) is BrowserRouteResponse
    assert "Intraday Opportunities — Native Discovery" in response.body
    assert 'class="tabs intraday-tabs"' in response.body
    assert "NO SUCCESSFUL DISCOVERY RUN AVAILABLE" in response.body
    assert routes.handle_get(
        BrowserGetRequest("/swing/opportunities", {}),
        lambda: (_ for _ in ()).throw(AssertionError("snapshot must stay lazy")),
    ) is None


def test_product_registry_accepts_intraday_evolution_without_server_edit() -> None:
    class _FutureIntradayRoute:
        def handle_get(self, request, snapshot_provider):  # type: ignore[no-untyped-def]
            del snapshot_provider
            if request.path == "/intraday/evidence-detail":
                return BrowserRouteResponse("product-owned")
            return None

    registry = ProductBrowserRoutes((_FutureIntradayRoute(),))

    response = registry.dispatch_get(
        BrowserGetRequest("/intraday/evidence-detail", {}),
        _snapshot,
    )

    assert response == BrowserRouteResponse("product-owned")


def test_product_registry_has_bounded_generic_post_dispatch() -> None:
    class _ProductRoute:
        def handle_get(self, request, snapshot_provider):  # type: ignore[no-untyped-def]
            del request, snapshot_provider
            return None

        def owns_post(self, path):  # type: ignore[no-untyped-def]
            return path == "/intraday/product-action"

        def handle_post(self, request, snapshot_provider):  # type: ignore[no-untyped-def]
            del snapshot_provider
            return BrowserRouteResponse(request.body.decode("ascii"))

    registry = ProductBrowserRoutes((_ProductRoute(),))
    request = BrowserPostRequest(
        path="/intraday/product-action",
        query={},
        content_type="text/plain",
        body=b"product-owned",
    )

    assert registry.owns_post(request.path)
    assert registry.dispatch_post(request, _snapshot) == BrowserRouteResponse("product-owned")
    assert not registry.owns_post("/swing/opportunities")


def test_shared_browser_files_contain_only_stable_intraday_seams() -> None:
    server_source = inspect.getsource(browser_server_module)
    views_source = inspect.getsource(browser_views_module)

    assert 'path == "/intraday"' not in server_source
    assert "render_intraday" not in server_source
    assert "IntradayEvidenceWorkstation" not in server_source
    assert "render_intraday_body" not in views_source
    assert "from kronos.application.intraday_workstation" not in views_source
    assert ".intraday-panel" not in views_source
    assert "render_browser_page" in views_source


def test_published_intraday_view_import_remains_compatible() -> None:
    workstation = create_intraday_workstation()
    snapshot = _snapshot()

    assert browser_views_module.render_intraday_workstation(
        snapshot,
        workstation.snapshot(),
    ) == render_intraday_workstation(snapshot, workstation.snapshot())
