from __future__ import annotations

import json
from types import SimpleNamespace

from kronos.application.intraday_wo13 import (
    IntradayWo13Application,
    IntradayWo13RestorationService,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_wo13_control import (
    WO13_CONTROL_ROUTE,
    WO13_PRODUCT_ROUTE,
    WO13_STATUS_ROUTE,
    IntradayWo13OperationalControl,
    operation_document,
)
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.wo12_v2_persistence import Wo12V2Store
from kronos.intraday.wo12_k5_foundation import Wo12SetupFamily
from kronos.intraday.wo13 import create_wo13_construction_request
from kronos.intraday.wo13_handoff import create_wo13_step31_handoff
from kronos.intraday.wo13_persistence import Wo13Store
from kronos.intraday.wo13_breakout import construct_wo13_breakout_geometry
from kronos.intraday.wo13_pullback import construct_wo13_pullback_geometry
from kronos.intraday.wo13_targets import create_wo13_target_constraint_population
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_wo13_contracts import _artifacts
from tests.unit.intraday.test_wo13_breakout import _evidence as _breakout_evidence
from tests.unit.intraday.test_wo13_pullback import _evidence, _missing
from tests.unit.intraday.test_wo13_targets import _constraint


class _Workstation:
    def snapshot(self, selected=None):  # type: ignore[no-untyped-def]
        del selected
        return SimpleNamespace(probables=None, probables_v2=None)


def _seed_wo12(store: Wo12V2Store, artifacts: tuple[object, ...]) -> None:
    pointer, request, evidence, result, eligibility, _, _ = artifacts
    store.retain_handoff(request.handoff)
    store.retain_request(request)
    store.retain_evidence(evidence)
    store.retain_result(result)
    store.retain_eligibility(eligibility)
    store.publish_current(pointer)


def _components(
    tmp_path,
    *,
    artifacts=None,
    setup=Wo12SetupFamily.PULLBACK_CONTINUATION,
    partial=False,
    constrained=False,
):  # type: ignore[no-untyped-def]
    selected = (
        _artifacts(tmp_path / "source", setup=setup)
        if artifacts is None
        else artifacts
    )
    pointer, request12, evidence12, result12, eligibility, snapshot, setup_fact = selected
    handoff = create_wo13_step31_handoff(
        current_pointer=pointer,
        request=request12,
        evidence=evidence12,
        result=result12,
        eligibility=eligibility,
        wo10_snapshot=snapshot,
        setup_evidence=setup_fact,
    )
    if setup is Wo12SetupFamily.RANGE_BREAKOUT:
        evidence = _breakout_evidence(handoff)
        geometry = construct_wo13_breakout_geometry(evidence)
    else:
        evidence = _missing(1, handoff) if partial else _evidence(handoff)
        geometry = construct_wo13_pullback_geometry(evidence)
    request = create_wo13_construction_request(
        handoff=handoff,
        sponsor_operation_identity="SPONSOR-WO13-SLICE7",
        requested_at=handoff.analysis_boundary,
        provenance=("ADR-0022", "SLICE7-TEST"),
    )
    candidates = (_constraint(geometry, "101"),) if constrained else ()
    population = create_wo13_target_constraint_population(
        setup_geometry=geometry, candidates=candidates
    )
    wo12_store = Wo12V2Store((tmp_path / "wo12").resolve())
    _seed_wo12(wo12_store, selected)
    wo13_store = Wo13Store((tmp_path / "wo13").resolve())
    application = IntradayWo13Application(store=wo13_store)
    restoration = IntradayWo13RestorationService(store=wo13_store)
    control = IntradayWo13OperationalControl(
        application, restoration, wo12_store
    )
    return control, request, evidence, population, wo13_store


def _post(control, payload, *, content_type="application/json"):  # type: ignore[no-untyped-def]
    routes = IntradayBrowserRoutes(_Workstation(), wo13_control=control)
    body = json.dumps(payload).encode() if payload is not None else b""
    return routes.handle_post(
        BrowserPostRequest(WO13_CONTROL_ROUTE, {}, content_type, body), _snapshot
    )


def test_not_yet_run_status_and_product_get_are_inert(tmp_path) -> None:
    control, _, _, _, store = _components(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo13_control=control)

    status = routes.handle_get(BrowserGetRequest(WO13_STATUS_ROUTE, {}), _snapshot)
    page = routes.handle_get(BrowserGetRequest(WO13_PRODUCT_ROUTE, {}), _snapshot)

    assert status is not None and json.loads(status.body)["restoration_state"] == "NOT_YET_RUN"
    assert page is not None and page.status.value == 200
    assert "WO-13 STEP-31 TRADE CONSTRUCTION" in page.body
    assert "NOT_YET_RUN" in page.body
    assert store.load_current() is None
    assert control.status_document()["provider_calls"] == 0
    assert control.status_document()["autonomous_operations"] == 0


def test_exact_current_now_post_persists_projects_and_replays_idempotently(tmp_path) -> None:
    control, request, evidence, population, store = _components(tmp_path)
    payload = operation_document(request, evidence, population)

    first = _post(control, payload)
    second = _post(control, payload)

    assert first is not None and first.status.value == 200
    assert second is not None and second.status.value == 200
    first_document = json.loads(first.body)
    second_document = json.loads(second.body)
    assert first_document["outcome"] == "COMPLETED"
    assert second_document["outcome"] == "RETAINED"
    assert second_document["idempotent"] is True
    restored = store.restore_current()
    assert restored is not None
    projected = control.status_document()["current_plan"]
    assert projected["entry_reference"] == format(restored.trade_plan.entry_reference, "f")
    assert projected["stop"] == format(restored.trade_plan.stop, "f")
    assert projected["thesis_invalidation_reference"] == format(
        restored.trade_plan.thesis_invalidation_reference, "f"
    )
    assert projected["setup_native_target"] == format(
        restored.trade_plan.setup_native_target, "f"
    )
    assert projected["canonical_target"] == format(
        restored.trade_plan.canonical_target, "f"
    )
    assert projected["model_rr"] == format(restored.trade_plan.model_rr, "f")


def test_product_page_projects_persisted_geometry_and_no_later_authority(tmp_path) -> None:
    control, request, evidence, population, _ = _components(tmp_path)
    assert _post(control, operation_document(request, evidence, population)).status.value == 200
    routes = IntradayBrowserRoutes(_Workstation(), wo13_control=control)

    page = routes.handle_get(BrowserGetRequest(WO13_PRODUCT_ROUTE, {}), _snapshot)

    assert page is not None
    for label in (
        "Entry Reference",
        "Entry Condition",
        "Stop",
        "Thesis Invalidation",
        "Setup-native Target",
        "Canonical Target",
        "Risk Distance",
        "Reward Distance",
        "Model R:R",
        "GEOMETRY_COMPLETE",
    ):
        assert label in page.body
    for prohibited in (
        "RISK_APPROVED",
        "TIMING_QUALIFIED",
        "PAPER",
        "LIVE",
        "BROKER_ORDER_PLACED",
    ):
        assert prohibited not in page.body


def test_breakout_partial_and_poor_rr_projects_persisted_truth_neutrally(tmp_path) -> None:
    breakout = _components(tmp_path / "breakout", setup=Wo12SetupFamily.RANGE_BREAKOUT)
    partial = _components(tmp_path / "partial", partial=True)
    poor_rr = _components(tmp_path / "poor-rr", constrained=True)

    pages = []
    for control, request, evidence, population, _ in (breakout, partial, poor_rr):
        assert _post(
            control, operation_document(request, evidence, population)
        ).status.value == 200
        page = IntradayBrowserRoutes(
            _Workstation(), wo13_control=control
        ).handle_get(BrowserGetRequest(WO13_PRODUCT_ROUTE, {}), _snapshot)
        assert page is not None
        pages.append(page.body)

    assert "INTRADAY_RANGE_BREAKOUT" in pages[0]
    assert "GEOMETRY_PARTIAL" in pages[1]
    assert "UNAVAILABLE" in pages[1]
    assert "0.25" in pages[2]
    assert "FAVOURABLE" not in pages[2]
    assert "UNFAVOURABLE" not in pages[2]


def test_non_now_wrong_policy_and_malformed_requests_fail_closed(tmp_path) -> None:
    control, request, evidence, population, store = _components(tmp_path)
    valid = operation_document(request, evidence, population)
    non_now = json.loads(json.dumps(valid))
    non_now["request"]["handoff"]["wo12_classification"] = "BUY_READY"
    wrong_policy = json.loads(json.dumps(valid))
    wrong_policy["request"]["policy"]["policy_checksum"] = "WRONG"

    for payload in (non_now, wrong_policy, {"symbol": "RELIANCE"}):
        response = _post(control, payload)
        assert response is not None and response.status.value == 400
        assert json.loads(response.body)["outcome"] == "REJECTED"
    assert store.load_current() is None


def test_superseded_now_rejected_and_existing_current_plan_preserved(tmp_path) -> None:
    control, request, evidence, population, store = _components(tmp_path)
    payload = operation_document(request, evidence, population)
    assert _post(control, payload).status.value == 200
    retained = store.load_current()

    replacement = _artifacts(tmp_path / "replacement", minute=21)
    _seed_wo12(control._wo12_store, replacement)  # noqa: SLF001
    response = _post(control, payload)

    assert response is not None and response.status.value == 409
    document = json.loads(response.body)
    assert document["failure_reason"] == "WO13_SUPERSEDED_WO12_REJECTED"
    assert store.load_current() == retained
    assert control.status_document()["current_plan"] is not None
    assert control.status_document()["last_operation"]["outcome"] == "REJECTED"


def test_busy_content_type_body_and_corrupt_restoration_are_bounded(tmp_path) -> None:
    control, request, evidence, population, store = _components(tmp_path)
    payload = operation_document(request, evidence, population)
    control._active_request_identity = "ACTIVE-WO13-REQUEST"  # noqa: SLF001
    busy = _post(control, payload)
    control._active_request_identity = None  # noqa: SLF001
    invalid_content = _post(control, payload, content_type="text/plain")
    empty = _post(control, None)

    assert busy is not None and busy.status.value == 409
    assert json.loads(busy.body)["failure_reason"] == "WO13_OPERATION_BUSY"
    assert invalid_content is not None and invalid_content.status.value == 400
    assert empty is not None and empty.status.value == 400

    assert _post(control, payload).status.value == 200
    current = store.root / "current" / "CURRENT-INTRADAY-WO13-V1.json"
    current.write_text("{}", encoding="utf-8")
    corrupt = IntradayWo13OperationalControl(
        IntradayWo13Application(store=store),
        IntradayWo13RestorationService(store=store),
        control._wo12_store,  # noqa: SLF001
    )
    document = corrupt.status_document()
    assert document["restoration_state"] == "CORRUPT"
    assert document["failure_reason"] == "WO13_RESTORATION_FAILED"
    assert document["current_plan"] is None
