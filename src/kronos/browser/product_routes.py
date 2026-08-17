"""Stable Browser seam for product-owned GET routes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Protocol

from kronos.application.swing_opportunities import BrowserWorkspaceSnapshot


BrowserSnapshotProvider = Callable[[], BrowserWorkspaceSnapshot]


@dataclass(frozen=True, slots=True)
class BrowserGetRequest:
    path: str
    query: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class BrowserRouteResponse:
    body: str
    status: HTTPStatus = HTTPStatus.OK
    content_type: str = "text/html; charset=utf-8"

    def __post_init__(self) -> None:
        if (
            type(self.body) is not str
            or type(self.status) is not HTTPStatus
            or type(self.content_type) is not str
            or not self.content_type
        ):
            raise ValueError("BROWSER_ROUTE_RESPONSE_INVALID")


class BrowserGetRoute(Protocol):
    def handle_get(
        self,
        request: BrowserGetRequest,
        snapshot_provider: BrowserSnapshotProvider,
    ) -> BrowserRouteResponse | None:
        """Return a response when this product owns the route."""


class ProductBrowserRoutes:
    """Ordered, immutable dispatch for independently owned product routes."""

    def __init__(self, routes: tuple[BrowserGetRoute, ...]) -> None:
        if type(routes) is not tuple or any(
            not callable(getattr(route, "handle_get", None)) for route in routes
        ):
            raise ValueError("BROWSER_PRODUCT_ROUTES_INVALID")
        self._routes = routes

    def dispatch_get(
        self,
        request: BrowserGetRequest,
        snapshot_provider: BrowserSnapshotProvider,
    ) -> BrowserRouteResponse | None:
        if type(request) is not BrowserGetRequest or not callable(snapshot_provider):
            raise ValueError("BROWSER_PRODUCT_ROUTE_REQUEST_INVALID")
        for route in self._routes:
            response = route.handle_get(request, snapshot_provider)
            if response is not None:
                if type(response) is not BrowserRouteResponse:
                    raise ValueError("BROWSER_PRODUCT_ROUTE_RESPONSE_INVALID")
                return response
        return None


def default_product_browser_routes(
    *, intraday_workstation: object | None = None
) -> ProductBrowserRoutes:
    """Compose current products without placing their policy in the server."""

    from kronos.application.intraday_runtime import create_intraday_workstation
    from kronos.browser.intraday_routes import IntradayBrowserRoutes

    workstation = (
        create_intraday_workstation()
        if intraday_workstation is None
        else intraday_workstation
    )
    return ProductBrowserRoutes((IntradayBrowserRoutes(workstation),))


__all__ = [
    "BrowserGetRequest",
    "BrowserGetRoute",
    "BrowserRouteResponse",
    "BrowserSnapshotProvider",
    "ProductBrowserRoutes",
    "default_product_browser_routes",
]
