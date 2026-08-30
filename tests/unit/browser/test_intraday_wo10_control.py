from __future__ import annotations

import json
from types import SimpleNamespace

from kronos.application.intraday_wo10 import IntradayWo10Application
from kronos.application.intraday_wo10_runtime import IntradayWo10RuntimeService
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_wo10_control import (
    WO10_CONTROL_ROUTE,
    WO10_PRODUCT_ROUTE,
    WO10_STATUS_ROUTE,
    IntradayWo10OperationalControl,
)
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.wo10 import Wo10State
from kronos.intraday.wo10_persistence import Wo10Store
from kronos.intraday.wo10_policies import Wo10PolicyRegistry
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_wo10_application import _Assembler, _Policy
from tests.unit.intraday.test_wo10_contracts import _bundle


class _Workstation:
    def snapshot(self, selected=None):  # type: ignore[no-untyped-def]
        del selected
        return SimpleNamespace(probables=None, probables_v2=None)


def _control(tmp_path, *, state=Wo10State.PROMOTION_READY):  # type: ignore[no-untyped-def]
    run, probable, request, snapshot, _ = _bundle()
    probables = ProbablesV2Store((tmp_path / "probables").resolve())
    probables.retain_result(probable)
    probables.retain_run(run)
    store = Wo10Store((tmp_path / "wo10").resolve())
    policy = _Policy(request.policy, state)
    registry = Wo10PolicyRegistry((policy,))
    application = IntradayWo10Application(
        run_store=probables,
        store=store,
        policy_registry=registry,
        evidence_assembler=_Assembler(snapshot),
    )
    runtime = IntradayWo10RuntimeService(application, store)
    return request, application, runtime, IntradayWo10OperationalControl(
        runtime, probables, registry
    )


def _payload(request):  # type: ignore[no-untyped-def]
    return {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "market_family": request.market_family.value,
        "probables_run_identity": request.probables_run_identity,
        "probables_run_integrity": request.probables_run_integrity,
        "probable_bindings": [
            {
                "probable_result_identity": item.probable_result_identity,
                "probable_result_integrity": item.probable_result_integrity,
                "canonical_subject_identity": item.canonical_subject_identity,
                "inherited_direction": item.inherited_direction.value,
                "analysis_boundary": item.analysis_boundary.isoformat(),
                "persisted_phase": item.persisted_phase.value,
            }
            for item in request.probable_bindings
        ],
        "policy": {
            "policy_identity": request.policy.policy_identity,
            "policy_version": request.policy.policy_version,
            "publication_identity": request.policy.publication_identity,
            "policy_checksum": request.policy.policy_checksum,
            "supported_market_family": request.policy.supported_market_family.value,
            "integrity_identity": request.policy.integrity_identity,
            "schema_identity": request.policy.schema_identity,
            "schema_version": request.policy.schema_version,
        },
        "requested_at": request.requested_at.isoformat(),
        "sponsor_operation_identity": request.sponsor_operation_identity,
        "provenance": list(request.provenance),
        "schema_identity": request.schema_identity,
        "schema_version": request.schema_version,
    }


def test_status_and_product_get_are_inert_and_absent_pointer_is_valid(tmp_path) -> None:
    _, _, runtime, control = _control(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo10_control=control)

    status = routes.handle_get(BrowserGetRequest(WO10_STATUS_ROUTE, {}), _snapshot)
    page = routes.handle_get(BrowserGetRequest(WO10_PRODUCT_ROUTE, {}), _snapshot)

    assert status is not None and status.status.value == 200
    assert {item["state"] for item in json.loads(status.body)["families"]} == {
        "NOT_YET_RUN"
    }
    assert page is not None and page.status.value == 200
    assert "WO-10 ANALYTICAL RECONCILIATION" in page.body
    assert runtime.last_execution is None


def test_exact_post_is_explicit_idempotent_and_restores_without_reevaluation(tmp_path) -> None:
    request, _, runtime, control = _control(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo10_control=control)
    body = json.dumps(_payload(request)).encode()
    post = BrowserPostRequest(WO10_CONTROL_ROUTE, {}, "application/json", body)

    first = routes.handle_post(post, _snapshot)
    second = routes.handle_post(post, _snapshot)

    assert first is not None and json.loads(first.body)["outcome"] == "COMPLETED"
    assert second is not None and json.loads(second.body)["outcome"] == "RETAINED"
    assert json.loads(second.body)["idempotent"] is True
    restored = runtime.family_statuses[0]
    assert restored.state == "LOADED"
    assert restored.restored is not None


def test_wrong_family_policy_or_member_fails_before_operation(tmp_path) -> None:
    request, _, runtime, control = _control(tmp_path)
    wrong_family = _payload(request)
    wrong_family["market_family"] = "MCX"
    wrong_member = _payload(request)
    wrong_member["probable_bindings"][0]["canonical_subject_identity"] = "NSE-EQ-TCS"

    assert control.execute_document(wrong_family)["failure_stage"] == "REQUEST_VALIDATION"
    assert control.execute_document(wrong_member)["failure_stage"] == "REQUEST_VALIDATION"
    assert runtime.last_execution is None


def test_busy_is_bounded_and_browser_promotion_wording_is_pre_entry(tmp_path) -> None:
    request, application, runtime, control = _control(tmp_path)
    assert application._lock.acquire(blocking=False)
    try:
        busy = control.execute_document(_payload(request))
    finally:
        application._lock.release()
    assert busy["outcome"] == "BUSY"
    assert busy["failure_reason"] == "WO10_OPERATION_BUSY"

    runtime.execute(request)
    page = IntradayBrowserRoutes(_Workstation(), wo10_control=control).handle_get(
        BrowserGetRequest(WO10_PRODUCT_ROUTE, {}), _snapshot
    )
    assert page is not None
    assert "Eligible to progress beyond WO-10 analytical reconciliation." in page.body
    for prohibited in ("BUY NOW", "SELL NOW", "BUY READY", "SELL READY"):
        assert prohibited not in page.body
