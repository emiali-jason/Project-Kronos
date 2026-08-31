from __future__ import annotations

from datetime import timedelta
import json
from types import SimpleNamespace

import pytest

from kronos.application.intraday_wo12_v2 import (
    IntradayWo12V2Application,
    IntradayWo12V2RuntimeService,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_wo12_v2_control import (
    WO12_V2_CONTROL_ROUTE,
    WO12_V2_PRODUCT_ROUTE,
    WO12_V2_STATUS_ROUTE,
    IntradayWo12V2OperationalControl,
    operation_document,
)
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo12_facts import Wo12PathState, Wo12SetupQualityState
from kronos.intraday.wo12_facts import create_wo12_path_clearance_fact
from kronos.intraday.wo12_v2 import (
    Wo12EvidenceInputsV2,
    create_wo12_request_v2,
)
from kronos.intraday.wo12_v2_persistence import Wo12V2Store
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_wo10_contracts import REQUESTED_AT
from tests.unit.intraday.test_wo12 import _foundation, _inputs


class _Workstation:
    def snapshot(self, selected=None):  # type: ignore[no-untyped-def]
        del selected
        return SimpleNamespace(probables=None, probables_v2=None)


def _v2_inputs(handoff, **changes):  # type: ignore[no-untyped-def]
    legacy = _inputs(handoff, **changes)
    return Wo12EvidenceInputsV2(
        fifteen_minute_structure=legacy.fifteen_minute_structure,
        cpr_acceptance=legacy.cpr_acceptance,
        path_clearance=legacy.path_clearance,
        setup_quality=legacy.setup_quality,
        governing_15m_structure_failed=legacy.governing_15m_structure_failed,
        authoritative_directional_conflict=legacy.authoritative_directional_conflict,
    )


def _components(tmp_path, *, inputs=None, sponsor="SPONSOR-WO12-V2-CONTROL"):  # type: ignore[no-untyped-def]
    wo10, wo11, handoff, _ = _foundation(tmp_path)
    store = Wo12V2Store((tmp_path / "wo12-kr370-v2").resolve())
    application = IntradayWo12V2Application(
        wo10_store=wo10,
        wo11_store=wo11,
        store=store,
    )
    runtime = IntradayWo12V2RuntimeService(application)
    control = IntradayWo12V2OperationalControl(runtime)
    request = create_wo12_request_v2(
        handoff=handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=21),
        sponsor_operation_identity=sponsor,
        provenance=("ADR-0021", "EXPLICIT-SPONSOR-POST"),
    )
    selected_inputs = _v2_inputs(handoff) if inputs is None else inputs(handoff)
    return request, selected_inputs, runtime, control


def _post(control, payload):  # type: ignore[no-untyped-def]
    routes = IntradayBrowserRoutes(_Workstation(), wo12_v2_control=control)
    return routes.handle_post(
        BrowserPostRequest(
            WO12_V2_CONTROL_ROUTE,
            {},
            "application/json",
            json.dumps(payload).encode(),
        ),
        _snapshot,
    )


def test_get_status_and_product_are_inert_when_not_yet_run(tmp_path) -> None:
    _, _, runtime, control = _components(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo12_v2_control=control)

    status = routes.handle_get(BrowserGetRequest(WO12_V2_STATUS_ROUTE, {}), _snapshot)
    page = routes.handle_get(BrowserGetRequest(WO12_V2_PRODUCT_ROUTE, {}), _snapshot)

    assert status is not None and json.loads(status.body)["state"] == "NOT_YET_RUN"
    assert page is not None and page.status.value == 200
    assert "WO-12 KR-370 ANALYTICAL PROMOTION" in page.body
    assert "NOT_YET_RUN" in page.body
    assert runtime.last_execution is None
    assert control.status_document()["provider_calls"] == 0
    assert control.status_document()["autonomous_operations"] == 0


@pytest.mark.parametrize(
    ("inputs", "classification", "satisfied", "eligible"),
    (
        (lambda handoff: _v2_inputs(handoff), "BUY_NOW", 4, True),
        (
            lambda handoff: _v2_inputs(
                handoff, quality=Wo12SetupQualityState.ADVERSE
            ),
            "BUY_READY",
            3,
            False,
        ),
        (
            lambda handoff: _v2_inputs(
                handoff,
                path=Wo12PathState.BLOCKED,
                quality=Wo12SetupQualityState.ADVERSE,
            ),
            "POTENTIAL_BUY_SETUP",
            2,
            False,
        ),
        (
            lambda handoff: _v2_inputs(
                handoff,
                close=100,
                path=Wo12PathState.BLOCKED,
                quality=Wo12SetupQualityState.ADVERSE,
            ),
            "NO_SETUP",
            1,
            False,
        ),
        (
            lambda handoff: _v2_inputs(
                handoff,
                progression=SemanticDirection.SHORT,
                close=100,
                path=Wo12PathState.BLOCKED,
                quality=Wo12SetupQualityState.ADVERSE,
            ),
            "NO_SETUP",
            0,
            False,
        ),
    ),
)
def test_exact_four_k_mapping_and_browser_projection(
    tmp_path, inputs, classification, satisfied, eligible
) -> None:  # type: ignore[no-untyped-def]
    request, evidence_inputs, runtime, control = _components(tmp_path, inputs=inputs)

    response = _post(control, operation_document(request, evidence_inputs))
    document = json.loads(response.body) if response is not None else {}
    page = IntradayBrowserRoutes(_Workstation(), wo12_v2_control=control).handle_get(
        BrowserGetRequest(WO12_V2_PRODUCT_ROUTE, {}), _snapshot
    )

    assert response is not None and response.status.value == 200
    assert document["outcome"] == "COMPLETED"
    assert document["result"]["classification"] == classification
    assert document["result"]["satisfied_count"] == satisfied
    assert len(document["result"]["criteria"]) == 4
    assert page is not None and f"{satisfied} / 4" in page.body
    assert classification in page.body
    expected_eligibility = (
        "ELIGIBLE_FOR_WO13_STEP31"
        if eligible
        else "NOT_ELIGIBLE_FOR_WO13_STEP31"
    )
    assert document["result"]["wo13_eligibility"] == expected_eligibility
    assert f"<dd>{expected_eligibility}</dd>" in page.body
    assert runtime.status.state == "LOADED"
    assert all(value not in page.body for value in ("K5_", "ATR", "5M trigger"))


def test_unavailable_and_hard_gate_fail_closed_and_project(tmp_path) -> None:
    request, inputs, _, control = _components(
        tmp_path,
        inputs=lambda handoff: _v2_inputs(
            handoff,
            quality=Wo12SetupQualityState.UNAVAILABLE,
            structure_failed=True,
        ),
    )

    response = _post(control, operation_document(request, inputs))
    document = json.loads(response.body) if response is not None else {}

    assert document["result"]["classification"] == "NO_SETUP"
    assert document["result"]["unavailable_criteria"] == ["K4_15M_SETUP_QUALITY"]
    assert document["result"]["hard_gates"] == [
        "MANDATORY_K_UNAVAILABLE",
        "GOVERNING_15M_STRUCTURE_FAILED",
    ]
    assert document["result"]["wo13_eligibility"] == "NOT_ELIGIBLE_FOR_WO13_STEP31"


def test_projection_contains_no_wo12_geometry_timing_risk_or_position_authority(
    tmp_path,
) -> None:
    request, inputs, _, control = _components(tmp_path)
    _post(control, operation_document(request, inputs))
    page = IntradayBrowserRoutes(_Workstation(), wo12_v2_control=control).handle_get(
        BrowserGetRequest(WO12_V2_PRODUCT_ROUTE, {}), _snapshot
    )
    assert page is not None
    for prohibited in (
        "Entry",
        "Entry Zone",
        "Stop",
        "Target",
        "R:R",
        "quantity",
        "position size",
        "Risk approval",
        "5M trigger",
        "PAPER",
        "LIVE",
        "IGNORE",
        "execution",
        "K5_",
        "ATR",
    ):
        assert prohibited not in page.body
    # The shared safe-exit shell retains its product-neutral negative assurance.
    assert page.body.count("broker order") == 1
    assert "No trade or broker order will be created." in page.body


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("handoff", "wo11_member_integrity"), "WRONG"),
        (("handoff", "market_family"), "MCX"),
        (("handoff", "inherited_direction"), "SHORT"),
    ),
)
def test_exact_lineage_family_and_direction_mutations_reject_before_evaluation(
    tmp_path, path, replacement
) -> None:  # type: ignore[no-untyped-def]
    request, inputs, runtime, control = _components(tmp_path)
    payload = operation_document(request, inputs)
    payload[path[0]][path[1]] = replacement

    response = _post(control, payload)
    document = json.loads(response.body) if response is not None else {}

    assert response is not None and response.status.value == 400
    assert document["outcome"] == "REJECTED"
    assert document["failure_stage"] == "REQUEST_VALIDATION"
    assert runtime.last_execution is None
    assert runtime.status.restored is None


def test_identical_request_is_idempotent_and_conflicting_content_fails_closed(tmp_path) -> None:
    request, inputs, _, control = _components(tmp_path)
    payload = operation_document(request, inputs)

    first = _post(control, payload)
    second = _post(control, payload)
    conflicting = json.loads(json.dumps(payload))
    conflicting["policy"]["policy_version"] = "WRONG"
    third = _post(control, conflicting)

    assert json.loads(first.body)["outcome"] == "COMPLETED"
    assert json.loads(second.body)["outcome"] == "RETAINED"
    assert json.loads(second.body)["idempotent"] is True
    assert third is not None and third.status.value == 409
    assert json.loads(third.body)["failure_reason"] == "WO12_V2_REQUEST_IDENTITY_CONFLICT"


def test_busy_operation_is_bounded_and_does_not_publish_pointer(tmp_path) -> None:
    request, inputs, runtime, control = _components(
        tmp_path, sponsor="SPONSOR-WO12-V2-OVERLAP"
    )
    runtime.application._lock.acquire()  # type: ignore[attr-defined]
    try:
        response = _post(control, operation_document(request, inputs))
    finally:
        runtime.application._lock.release()  # type: ignore[attr-defined]

    document = json.loads(response.body) if response is not None else {}
    assert response is not None and response.status.value == 409
    assert document["outcome"] == "BUSY"
    assert document["failure_reason"] == "WO12_V2_OPERATION_BUSY"
    assert runtime.store.load_current() is None


def test_bound_evidence_failure_is_sanitized_and_does_not_publish_pointer(
    tmp_path,
) -> None:
    request, inputs, runtime, control = _components(tmp_path)
    wrong_path = create_wo12_path_clearance_fact(
        canonical_subject_identity="NSE-EQUITY-WRONG",
        market_family=request.handoff.market_family,
        analysis_boundary=request.handoff.analysis_boundary,
        state=Wo12PathState.CLEAR,
        source_evidence_identities=("WRONG-SOURCE",),
        source_evidence_integrities=("WRONG-INTEGRITY",),
        predicate_identity="EXISTING-DETERMINISTIC-STRUCTURAL-OBSTRUCTION-V1",
    )
    mismatched = Wo12EvidenceInputsV2(
        fifteen_minute_structure=inputs.fifteen_minute_structure,
        cpr_acceptance=inputs.cpr_acceptance,
        path_clearance=wrong_path,
        setup_quality=inputs.setup_quality,
    )

    response = _post(control, operation_document(request, mismatched))
    document = json.loads(response.body) if response is not None else {}

    assert response is not None and response.status.value == 503
    assert document["outcome"] == "FAILED"
    assert document["failure_reason"] == "WO12_CRITERION_FACT_BINDING_INVALID"
    assert "Traceback" not in response.body
    assert runtime.store.load_current() is None


def test_restart_restores_loaded_pointer_without_reexecution(tmp_path) -> None:
    request, inputs, runtime, control = _components(tmp_path)
    _post(control, operation_document(request, inputs))
    restarted = IntradayWo12V2RuntimeService(runtime.application)

    assert restarted.status.state == "LOADED"
    assert restarted.status.restored is not None
    assert restarted.status.restored.request == request
    assert restarted.last_execution is None


def test_corrupt_pointer_is_sanitized_and_browser_remains_available(tmp_path) -> None:
    request, _, runtime, _ = _components(tmp_path)
    pointer = runtime.store.root / "current" / "CURRENT-INTRADAY-WO12-V2.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_bytes(b"{}")
    restarted = IntradayWo12V2RuntimeService(runtime.application)
    control = IntradayWo12V2OperationalControl(restarted)
    page = IntradayBrowserRoutes(_Workstation(), wo12_v2_control=control).handle_get(
        BrowserGetRequest(WO12_V2_PRODUCT_ROUTE, {}), _snapshot
    )

    assert restarted.status.state == "CORRUPT"
    assert restarted.status.failure_reason == "WO12_V2_RESTORATION_FAILED"
    assert restarted.last_execution is None
    assert page is not None and page.status.value == 200 and "CORRUPT" in page.body
    assert request.request_identity not in page.body


def test_body_and_content_type_admission_fail_closed(tmp_path) -> None:
    _, _, runtime, control = _components(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo12_v2_control=control)
    response = routes.handle_post(
        BrowserPostRequest(WO12_V2_CONTROL_ROUTE, {}, "text/plain", b"{}"),
        _snapshot,
    )

    assert response is not None and response.status.value == 400
    assert json.loads(response.body)["failure_stage"] == "REQUEST_VALIDATION"
    assert runtime.last_execution is None
