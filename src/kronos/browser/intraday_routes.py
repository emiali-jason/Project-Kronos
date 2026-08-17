"""Intraday-owned Browser routing and presentation dispatch."""

from __future__ import annotations

from kronos.application.intraday_workstation import IntradayEvidenceWorkstation
from kronos.browser.intraday_views import render_intraday_workstation
from kronos.browser.product_routes import (
    BrowserGetRequest,
    BrowserRouteResponse,
    BrowserSnapshotProvider,
)


class IntradayBrowserRoutes:
    """Own Intraday Browser paths behind the stable product-route seam."""

    def __init__(self, workstation: object) -> None:
        if type(workstation) is not IntradayEvidenceWorkstation:
            raise ValueError("INTRADAY_BROWSER_ROUTES_INVALID")
        self._workstation = workstation

    def handle_get(
        self,
        request: BrowserGetRequest,
        snapshot_provider: BrowserSnapshotProvider,
    ) -> BrowserRouteResponse | None:
        if request.path != "/intraday":
            return None
        selected = request.query.get("instrument", [None])[0]
        return BrowserRouteResponse(
            render_intraday_workstation(
                snapshot_provider(),
                self._workstation.snapshot(selected),
            )
        )


__all__ = ["IntradayBrowserRoutes"]
