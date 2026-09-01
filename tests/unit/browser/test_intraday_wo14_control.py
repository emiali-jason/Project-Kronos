from __future__ import annotations

import json
from types import SimpleNamespace

from kronos.application.intraday_wo14 import IntradayWo14RestorationService
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_views import render_intraday_wo14
from kronos.browser.intraday_wo14_control import (
    WO14_CONTROL_ROUTE,
    WO14_PRODUCT_ROUTE,
    WO14_STATUS_ROUTE,
    IntradayWo14OperationalControl,
    operation_document,
)
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_wo14_application import _components
from kronos.intraday.wo13_persistence import Wo13Store
from kronos.intraday.wo14 import create_wo14_observation_request


class _Workstation:
    def snapshot(self, selected=None):  # type: ignore[no-untyped-def]
        del selected
        return SimpleNamespace(probables=None, probables_v2=None)


def _control(tmp_path):  # type: ignore[no-untyped-def]
    application, store, request = _components(tmp_path)
    control = IntradayWo14OperationalControl(
        application,
        IntradayWo14RestorationService(store=store),
    )
    return control, store, request


def _post(control, payload, *, content_type="application/json"):  # type: ignore[no-untyped-def]
    body = json.dumps(payload).encode() if payload is not None else b""
    return IntradayBrowserRoutes(
        _Workstation(), wo14_control=control
    ).handle_post(
        BrowserPostRequest(WO14_CONTROL_ROUTE, {}, content_type, body),
        _snapshot,
    )


def test_not_yet_run_product_and_status_get_are_inert(tmp_path) -> None:
    control, store, _ = _control(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo14_control=control)

    first = routes.handle_get(BrowserGetRequest(WO14_PRODUCT_ROUTE, {}), _snapshot)
    second = routes.handle_get(BrowserGetRequest(WO14_PRODUCT_ROUTE, {}), _snapshot)
    status = routes.handle_get(BrowserGetRequest(WO14_STATUS_ROUTE, {}), _snapshot)

    assert first is not None and first.status.value == 200
    assert second is not None and first.body == second.body
    assert "NOT_YET_RUN" in first.body
    assert status is not None
    document = json.loads(status.body)
    assert document["restoration_state"] == "NOT_YET_RUN"
    assert document["provider_calls"] == 0
    assert document["wo13_operations"] == 0
    assert document["autonomous_operations"] == 0
    assert store.load_current() is None


def test_exact_post_persists_projects_and_replays_idempotently(tmp_path) -> None:
    control, store, request = _control(tmp_path)
    payload = operation_document(request)

    first = _post(control, payload)
    second = _post(control, payload)

    assert first is not None and first.status.value == 200
    assert second is not None and second.status.value == 200
    assert json.loads(first.body)["outcome"] == "COMPLETED"
    assert json.loads(second.body)["outcome"] == "RETAINED"
    restored = store.restore_current()
    assert restored is not None
    projected = control.status_document()["current_observation"]
    assert projected["state"] == "RISK_OBSERVED"
    assert projected["trade_plan_identity"] == restored.observation.plan_binding.trade_plan_identity


def test_product_projects_neutral_loss_facts_and_no_later_authority(tmp_path) -> None:
    control, _, request = _control(tmp_path)
    assert _post(control, operation_document(request)).status.value == 200
    page = IntradayBrowserRoutes(
        _Workstation(), wo14_control=control
    ).handle_get(BrowserGetRequest(WO14_PRODUCT_ROUTE, {}), _snapshot)

    assert page is not None
    for expected in (
        "RISK_OBSERVED",
        "Structural risk / price unit",
        "Risk per share",
        "Loss at Stop",
        "Capital reference / fraction",
        "WO-13 Model R:R (context only)",
        "RISK_OBSERVATION_ONLY",
        "UNCLASSIFIED",
    ):
        assert expected in page.body
    for prohibited in (
        "RISK APPROVED",
        "RISK REJECTED",
        "TIMING_ALLOWED",
        "TIMING_BLOCKED",
        "PAPER/LIVE/IGNORE",
        "recommended quantity",
        "permitted quantity",
        "place_order",
    ):
        assert prohibited not in page.body


def test_malformed_content_type_and_busy_requests_fail_closed(tmp_path) -> None:
    control, store, request = _control(tmp_path)
    payload = operation_document(request)
    invalid = _post(control, payload, content_type="text/plain")
    empty = _post(control, None)
    control._active_request_identity = "ACTIVE-WO14"  # noqa: SLF001
    busy = _post(control, payload)
    control._active_request_identity = None  # noqa: SLF001

    assert invalid is not None and invalid.status.value == 400
    assert empty is not None and empty.status.value == 400
    assert busy is not None and busy.status.value == 409
    assert json.loads(busy.body)["failure_reason"] == "WO14_OPERATION_BUSY"
    assert store.load_current() is None


def test_synthetic_alert_projection_is_unclassified_and_non_veto() -> None:
    status = {
        "runtime_loaded": True,
        "restoration_state": "LOADED",
        "operation_state": "IDLE",
        "control_identity": "KRONOS-INTRADAY-WO14-SPONSOR-CONTROL-V1",
        "control_version": "1.0.0",
        "current_observation": {
            "canonical_subject_identity": "NSE-EQ-RELIANCE",
            "market_family": "NSE_EQUITY",
            "direction": "LONG",
            "setup_family": "INTRADAY_PULLBACK_CONTINUATION",
            "state": "RISK_ALERT",
            "alert_severity": "UNCLASSIFIED",
            "field_availability": [],
            "unavailable_reasons": [],
            "authority": "RISK_OBSERVATION_ONLY",
        },
    }
    page = render_intraday_wo14(_snapshot(), status)
    assert "RISK_ALERT" in page and "UNCLASSIFIED" in page
    assert "TIMING_ALLOWED" not in page and "TIMING_BLOCKED" not in page


def test_failed_successor_projects_latest_failure_separately_from_current(tmp_path) -> None:
    control, store, request = _control(tmp_path)
    assert _post(control, operation_document(request)).status.value == 200
    plan = control.application.wo13_store.load_trade_plan(
        request.plan_binding.trade_plan_identity
    )
    successor = create_wo14_observation_request(
        plan=plan,
        sponsor_operation_identity="SPONSOR-WO14-FAILED-SUCCESSOR",
        requested_at=plan.analysis_boundary,
        evaluation_boundary=plan.analysis_boundary,
        provenance=("ADR-0023", "WO14-FAILED-SUCCESSOR-TEST"),
    )
    control.application._wo13_store = Wo13Store(  # noqa: SLF001
        (tmp_path / "empty-wo13").resolve()
    )

    failed = _post(control, operation_document(successor))
    status = control.status_document()

    assert failed is not None and failed.status.value == 503
    assert status["current_observation"] is not None
    assert status["current_observation"]["observation_identity"] == (
        store.load_current().observation_identity
    )
    assert status["latest_persisted_failure"] is not None
    assert status["last_operation"]["outcome"] == "FAILED"
