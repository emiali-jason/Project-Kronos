from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path

from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.browser.intraday_probables_v2_control import (
    IntradayProbablesV2OperationalControl,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.probables_v2 import PROBABLES_V2_METHODOLOGY_CHECKSUM
from kronos.intraday.refresh_v2 import REFRESH_V2_ROUTE
from tests.unit.application.test_intraday_discovery_operation import (
    SEMANTIC_BOUNDARY,
    _configured_shared,
)
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_probables_v2_refresh_control import _payload


def _routes(tmp_path: Path):  # type: ignore[no-untyped-def]
    shared, _, factory_calls, provider_requests = _configured_shared()
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: SEMANTIC_BOUNDARY,
    )
    control = IntradayProbablesV2OperationalControl(
        composition.discovery_v2_operation,
        composition.probables_v2_application,
        composition.refresh_v2_provenance_store,
        clock=lambda: SEMANTIC_BOUNDARY,
        process_identity=lambda: "KRONOS-BACKEND-PID-TEST",
    )
    return (
        IntradayBrowserRoutes(composition.workstation, probables_v2_control=control),
        composition,
        factory_calls,
        provider_requests,
    )


def test_normal_sponsor_control_targets_exact_v2_and_has_no_auto_trigger(
    tmp_path: Path,
) -> None:
    routes, composition, factory_calls, provider_requests = _routes(tmp_path)

    page = routes.handle_get(BrowserGetRequest("/intraday", {}), _snapshot)

    assert page is not None and page.status is HTTPStatus.OK
    assert "Refresh Analysis · V2 Phase-Aware" in page.body
    assert "PHASE-AWARE V2 · NOT YET RUN" in page.body
    assert "fetch('/control/intraday-discovery/v2'" in page.body
    assert PROBABLES_V2_METHODOLOGY_CHECKSUM in page.body
    assert page.body.count("fetch('/control/intraday-discovery/v2'") == 1
    assert page.body.index("intradayRefresh.addEventListener('click'") < page.body.index(
        "fetch('/control/intraday-discovery/v2'"
    )
    assert "addEventListener('visibilitychange'" not in page.body
    assert "addEventListener('focus'" not in page.body
    assert "<button type=\"button\" id=\"intraday-refresh-analysis\"" in page.body
    assert composition.discovery_operation.last_result is None
    assert composition.discovery_v2_operation.last_result is None
    assert factory_calls == []
    assert provider_requests == [0]


def test_status_get_is_read_only_and_v2_specific(tmp_path: Path) -> None:
    routes, composition, factory_calls, provider_requests = _routes(tmp_path)

    response = routes.handle_get(
        BrowserGetRequest("/control/intraday-discovery/v2/status", {}), _snapshot
    )
    document = json.loads(response.body) if response is not None else {}

    assert response is not None and response.status is HTTPStatus.OK
    assert document["state"] == "NOT_YET_RUN"
    assert document["route_identity"] == REFRESH_V2_ROUTE
    assert document["methodology_version"] == "2.0.0"
    assert composition.discovery_v2_operation.last_result is None
    assert factory_calls == []
    assert provider_requests == [0]


def test_wrong_v2_binding_returns_bounded_rejection_without_provider(
    tmp_path: Path,
) -> None:
    routes, _, factory_calls, provider_requests = _routes(tmp_path)
    payload = {**_payload(), "methodology_checksum": "WRONG"}

    response = routes.handle_post(
        BrowserPostRequest(
            path=REFRESH_V2_ROUTE,
            query={},
            content_type="application/json",
            body=json.dumps(payload).encode(),
        ),
        _snapshot,
    )
    document = json.loads(response.body) if response is not None else {}

    assert response is not None and response.status is HTTPStatus.BAD_REQUEST
    assert document["outcome"] == "REJECTED"
    assert document["failure"] == "INTRADAY_PROBABLES_V2_METHODOLOGY_BINDING_INVALID"
    assert factory_calls == []
    assert provider_requests == [0]


def test_malformed_body_is_audited_and_get_reload_remains_inert(tmp_path: Path) -> None:
    routes, composition, _, provider_requests = _routes(tmp_path)

    rejected = routes.handle_post(
        BrowserPostRequest(
            path=REFRESH_V2_ROUTE,
            query={},
            content_type="application/json",
            body=b"not-json",
        ),
        _snapshot,
    )
    first = routes.handle_get(BrowserGetRequest("/intraday", {}), _snapshot)
    second = routes.handle_get(BrowserGetRequest("/intraday", {}), _snapshot)

    assert rejected is not None and rejected.status is HTTPStatus.BAD_REQUEST
    assert json.loads(rejected.body)["outcome"] == "REJECTED"
    assert first is not None and second is not None
    assert composition.discovery_v2_operation.last_result is None
    assert provider_requests == [0]
