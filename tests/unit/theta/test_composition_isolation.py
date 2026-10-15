"""Synthetic checks of the concrete EA-Swing/Intraday coordination boundaries."""

import builtins

import pytest

from kronos.browser import theta_routes as theta_module
from kronos.browser.product_routes import (
    BrowserGetRequest, BrowserPostRequest, BrowserRouteResponse,
    default_product_browser_routes,
)
from tests.unit.theta.test_rehearsal import request, running


@pytest.mark.parametrize("failure", [ImportError, OSError, RuntimeError])
def test_optional_theta_constructor_failure_does_not_block_intraday(monkeypatch, failure):
    def unavailable(*_):
        raise failure("SYNTHETIC private initialization detail")
    monkeypatch.setattr(theta_module, "ThetaBrowserRoutes", unavailable)
    with running(None) as server:
        status, _, body = request(server, "GET", "/intraday")
        assert status == 200 and b"Intraday Opportunities" in body
        assert b"SYNTHETIC private initialization detail" not in body
        assert not server.product_routes.owns_post("/theta-earners/import")


def test_optional_theta_import_failure_does_not_block_intraday(monkeypatch):
    original = builtins.__import__
    def unavailable(name, *args, **kwargs):
        if name == "kronos.browser.theta_routes":
            raise ImportError("SYNTHETIC unavailable optional Theta module")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", unavailable)
    with running(None) as server:
        assert request(server, "GET", "/intraday")[0] == 200


def test_invalid_optional_theta_route_cannot_invalidate_existing_registry(monkeypatch):
    monkeypatch.setattr(theta_module, "ThetaBrowserRoutes", lambda _: object())
    with running(None) as server:
        assert request(server, "GET", "/intraday")[0] == 200
        assert not server.product_routes.owns_post("/theta-earners/import")


@pytest.mark.parametrize("injected", [None, object()])
def test_intraday_get_post_precedence_and_none_or_malformed_theta_do_not_interfere(monkeypatch, injected):
    from kronos.browser import intraday_routes as module
    response = BrowserRouteResponse("SYNTHETIC unchanged Intraday owner response")
    class IntradayOwner:
        def handle_get(self, incoming, snapshot):
            return response if incoming.path.startswith("/intraday") else None
        def owns_post(self, path):
            return path == "/intraday/owned-action"
        def handle_post(self, incoming, snapshot):
            return response
    owner = IntradayOwner()
    monkeypatch.setattr(module, "IntradayBrowserRoutes", lambda _: owner)
    routes = default_product_browser_routes(intraday_workstation=object(), theta_workflow=injected)
    never_snapshot = lambda: (_ for _ in ()).throw(AssertionError("Snapshot must remain lazy"))
    assert routes.dispatch_get(BrowserGetRequest("/intraday", {}), never_snapshot) is response
    assert routes.dispatch_post(BrowserPostRequest("/intraday/owned-action", {}, "text/plain", b""), never_snapshot) is response
    assert routes._routes[0] is owner


def test_protected_swing_and_intraday_http_routes_keep_legacy_owners_with_optional_theta(monkeypatch):
    paths = ("/swing/opportunities", "/swing/v1-review", "/swing/mcx-v1",
        "/portfolio?product=SWING", "/reports?product=SWING&view=OVERVIEW", "/journal?product=SWING",
        "/notifications/swing", "/intraday")
    protected = ("/swing/analysis", "/swing/reconcile", "/swing/mcx-v1/observe",
        "/notifications/watch/deactivate", "/intraday/review/load")
    observed = []
    original = theta_module.ThetaBrowserRoutes
    for unavailable in (True, False):
        if unavailable:
            def absent(*_):
                raise ImportError("SYNTHETIC optional Theta unavailable")
            monkeypatch.setattr(theta_module, "ThetaBrowserRoutes", absent)
        else:
            monkeypatch.setattr(theta_module, "ThetaBrowserRoutes", original)
        with running(None) as server:
            assert all(not original(object()).owns_post(path) for path in protected)
            results = []
            for path in paths:
                status, headers, body = request(server, "GET", path)
                # This disposable application has no calendar publisher. The
                # existing Reports handler maps that missing date authority to
                # this exact 400, even with a valid explicit query. Do not add
                # synthetic calendar authority just to manufacture a 200.
                if path.startswith("/reports?"):
                    assert status == 400 and body == b"Reports filter is invalid.", (path, status)
                else:
                    # Other controlled 409/503 responses retain unavailable
                    # legacy evidence; they are not Theta failures.
                    assert status in (200, 302, 303, 409, 503), (path, status)
                assert b"SYNTHETIC optional Theta unavailable" not in body
                assert b"ACCEPTED_EXTERNAL_EVIDENCE" not in body
                results.append((status, headers.get("Content-Type")))
            observed.append(results)
    assert observed[0] == observed[1]


@pytest.mark.parametrize("path", ["/intraday", "/intraday/review", "/swing/opportunities",
    "/swing/v1-review", "/swing/mcx-v1", "/portfolio", "/reports", "/journal", "/notifications/swing"])
def test_theta_never_claims_protected_get_or_post(path):
    routes = theta_module.ThetaBrowserRoutes(object())
    never_snapshot = lambda: (_ for _ in ()).throw(AssertionError("Snapshot must remain lazy"))
    assert routes.handle_get(BrowserGetRequest(path, {}), never_snapshot) is None
    assert not routes.owns_post(path)
    assert routes.handle_post(BrowserPostRequest(path, {}, "text/plain", b""), never_snapshot) is None
