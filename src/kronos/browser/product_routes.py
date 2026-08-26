"""Stable Browser seam for product-owned GET and bounded POST routes."""

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
class BrowserPostRequest:
    path: str
    query: dict[str, list[str]]
    content_type: str
    body: bytes

    def __post_init__(self) -> None:
        if (
            type(self.path) is not str
            or not self.path.startswith("/")
            or type(self.query) is not dict
            or type(self.content_type) is not str
            or type(self.body) is not bytes
        ):
            raise ValueError("BROWSER_POST_REQUEST_INVALID")


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


class BrowserPostRoute(Protocol):
    def owns_post(self, path: str) -> bool:
        """Declare ownership before the shared server reads a bounded body."""

    def handle_post(
        self,
        request: BrowserPostRequest,
        snapshot_provider: BrowserSnapshotProvider,
    ) -> BrowserRouteResponse | None:
        """Handle one same-origin, sponsor-work-admitted product request."""


class ProductBrowserRoutes:
    """Ordered, immutable dispatch for independently owned product routes."""

    def __init__(self, routes: tuple[BrowserGetRoute, ...]) -> None:
        if type(routes) is not tuple or any(
            not callable(getattr(route, "handle_get", None)) for route in routes
        ):
            raise ValueError("BROWSER_PRODUCT_ROUTES_INVALID")
        self._routes = routes

    def owns_post(self, path: str) -> bool:
        if type(path) is not str or not path.startswith("/"):
            raise ValueError("BROWSER_PRODUCT_POST_PATH_INVALID")
        return any(
            callable(getattr(route, "owns_post", None)) and route.owns_post(path)
            for route in self._routes
        )

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

    def dispatch_post(
        self,
        request: BrowserPostRequest,
        snapshot_provider: BrowserSnapshotProvider,
    ) -> BrowserRouteResponse | None:
        if type(request) is not BrowserPostRequest or not callable(snapshot_provider):
            raise ValueError("BROWSER_PRODUCT_POST_REQUEST_INVALID")
        for route in self._routes:
            owns = getattr(route, "owns_post", None)
            handler = getattr(route, "handle_post", None)
            if callable(owns) and owns(request.path):
                if not callable(handler):
                    raise ValueError("BROWSER_PRODUCT_POST_ROUTE_INVALID")
                response = handler(request, snapshot_provider)
                if response is not None and type(response) is not BrowserRouteResponse:
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
    "BrowserPostRequest",
    "BrowserPostRoute",
    "BrowserRouteResponse",
    "BrowserSnapshotProvider",
    "ProductBrowserRoutes",
    "default_product_browser_routes",
]
