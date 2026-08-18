"""Intraday-owned Browser routing and presentation dispatch."""

from __future__ import annotations

from kronos.browser.intraday_views import render_intraday_detail, render_intraday_workstation
from kronos.browser.product_routes import (
    BrowserGetRequest,
    BrowserRouteResponse,
    BrowserSnapshotProvider,
)


class IntradayBrowserRoutes:
    """Own Intraday Browser paths behind the stable product-route seam."""

    def __init__(self, workstation: object) -> None:
        if not callable(getattr(workstation, "snapshot", None)):
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        self._workstation = workstation

    def handle_get(
        self,
        request: BrowserGetRequest,
        snapshot_provider: BrowserSnapshotProvider,
    ) -> BrowserRouteResponse | None:
        detail_prefix = "/intraday/evidence/"
        if request.path == "/intraday":
            selected = request.query.get("instrument", [None])[0]
            renderer = render_intraday_workstation
        elif request.path.startswith(detail_prefix):
            selected = request.path.removeprefix(detail_prefix)
            renderer = render_intraday_detail
        else:
            return None
        return BrowserRouteResponse(
            renderer(
                snapshot_provider(),
                self._workstation.snapshot(selected),
            )
        )


__all__ = ["IntradayBrowserRoutes"]
