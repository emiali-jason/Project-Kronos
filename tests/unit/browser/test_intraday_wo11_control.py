from __future__ import annotations

import json
from types import SimpleNamespace

from kronos.application.intraday_wo11 import (
    IntradayWo11Application,
    IntradayWo11RuntimeService,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_wo11_control import (
    WO11_CONTROL_ROUTE,
    WO11_PRODUCT_ROUTE,
    WO11_STATUS_ROUTE,
    IntradayWo11OperationalControl,
)
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.wo10_persistence import Wo10Store
from kronos.intraday.wo11_persistence import Wo11Store
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_wo11 import _request, _retain_source


class _Workstation:
    def snapshot(self, selected=None):  # type: ignore[no-untyped-def]
        del selected
        return SimpleNamespace(probables=None, probables_v2=None)


def _control(tmp_path):  # type: ignore[no-untyped-def]
    wo10 = Wo10Store((tmp_path / "wo10").resolve())
    source, _, _ = _retain_source(wo10)
    store = Wo11Store((tmp_path / "wo11").resolve())
    runtime = IntradayWo11RuntimeService(
        IntradayWo11Application(wo10_store=wo10, store=store)
    )
    request = _request(source)
    return request, runtime, IntradayWo11OperationalControl(runtime)


def _payload(request):  # type: ignore[no-untyped-def]
    return {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "source_batches": [{
            "market_family": item.market_family.value,
            "batch_identity": item.batch_identity,
            "batch_integrity": item.batch_integrity,
            "request_identity": item.request_identity,
            "request_integrity": item.request_integrity,
            "operation_identity": item.operation_identity,
            "operation_integrity": item.operation_integrity,
            "policy": {
                "policy_identity": item.policy.policy_identity,
                "policy_version": item.policy.policy_version,
                "publication_identity": item.policy.publication_identity,
                "policy_checksum": item.policy.policy_checksum,
                "supported_market_family": item.policy.supported_market_family.value,
                "integrity_identity": item.policy.integrity_identity,
                "schema_identity": item.policy.schema_identity,
                "schema_version": item.policy.schema_version,
            },
            "probables_run_identity": item.probables_run_identity,
            "probables_run_integrity": item.probables_run_integrity,
            "published_population": item.published_population,
        } for item in request.source_batches],
        "requested_at": request.requested_at.isoformat(),
        "sponsor_operation_identity": request.sponsor_operation_identity,
        "provenance": list(request.provenance),
        "schema_identity": request.schema_identity,
        "schema_version": request.schema_version,
    }


def test_get_routes_are_inert_and_absent_publication_is_valid(tmp_path) -> None:
    _, runtime, control = _control(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo11_control=control)

    status = routes.handle_get(BrowserGetRequest(WO11_STATUS_ROUTE, {}), _snapshot)
    page = routes.handle_get(BrowserGetRequest(WO11_PRODUCT_ROUTE, {}), _snapshot)

    assert status is not None and status.status.value == 200
    assert json.loads(status.body)["state"] == "NOT_YET_PUBLISHED"
    assert page is not None and page.status.value == 200
    assert "WO-11 PROMOTION PUBLICATION" in page.body
    assert "PRE-KR-370" in page.body
    assert runtime.last_execution is None


def test_exact_post_publishes_once_and_repeat_is_idempotent(tmp_path) -> None:
    request, runtime, control = _control(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo11_control=control)
    post = BrowserPostRequest(
        WO11_CONTROL_ROUTE,
        {},
        "application/json",
        json.dumps(_payload(request)).encode(),
    )

    first = routes.handle_post(post, _snapshot)
    second = routes.handle_post(post, _snapshot)

    assert first is not None and json.loads(first.body)["outcome"] == "COMPLETED"
    assert second is not None and json.loads(second.body)["outcome"] == "RETAINED"
    assert json.loads(second.body)["idempotent"] is True
    assert runtime.status.restored is not None
    document = control.status_document()
    assert document["provider_calls"] == 0
    assert document["wo10_reruns"] == 0
    assert document["analytical_evaluations"] == 0

    page = routes.handle_get(BrowserGetRequest(WO11_PRODUCT_ROUTE, {}), _snapshot)
    assert page is not None
    assert "ELIGIBLE_FOR_DOWNSTREAM_HANDOFF" in page.body
    assert "KRONOS-INTRADAY-WO11-PROMOTION-PUBLICATION-V1" in page.body


def test_wrong_exact_batch_binding_rejects_before_publication(tmp_path) -> None:
    request, runtime, control = _control(tmp_path)
    payload = _payload(request)
    payload["source_batches"][0]["batch_integrity"] = "WRONG"
    result = control.execute_document(payload)
    assert result["outcome"] == "REJECTED"
    assert result["failure_stage"] == "REQUEST_VALIDATION"
    assert runtime.status.restored is None


def test_post_contract_and_body_admission_fail_closed(tmp_path) -> None:
    _, _, control = _control(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo11_control=control)
    response = routes.handle_post(
        BrowserPostRequest(WO11_CONTROL_ROUTE, {}, "text/plain", b"{}"),
        _snapshot,
    )
    assert response is not None and response.status.value == 400
    assert json.loads(response.body)["failure_stage"] == "REQUEST_VALIDATION"
