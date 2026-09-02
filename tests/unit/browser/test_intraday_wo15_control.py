from __future__ import annotations

import json
from types import SimpleNamespace

from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.application.intraday_wo15 import IntradayWo15RestorationService
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_wo15_control import (
    MAX_WO15_REQUEST_BYTES,
    WO15_CONTROL_ROUTE,
    WO15_PRODUCT_ROUTE,
    WO15_STATUS_ROUTE,
    IntradayWo15OperationalControl,
    operation_document,
)
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.wo15 import Wo15ProgressionSemantics
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_wo15_application import _environment
from tests.unit.intraday.test_wo15_contracts import _wo13
from tests.unit.provider.test_shared_provider_runtime import _shared


class _Workstation:
    def snapshot(self, selected=None):  # type: ignore[no-untyped-def]
        del selected
        return SimpleNamespace(probables=None, probables_v2=None)


def _control(tmp_path, **kwargs):  # type: ignore[no-untyped-def]
    wo13_store, store, application, request = _environment(tmp_path, **kwargs)
    return (
        IntradayWo15OperationalControl(
            application,
            IntradayWo15RestorationService(store=store),
        ),
        wo13_store,
        store,
        request,
    )


def _post(
    control,
    payload,
    *,
    content_type="application/json",
    query=None,
    raw=None,
):  # type: ignore[no-untyped-def]
    body = (
        raw if raw is not None
        else json.dumps(payload).encode() if payload is not None
        else b""
    )
    return IntradayBrowserRoutes(
        _Workstation(), wo15_control=control
    ).handle_post(
        BrowserPostRequest(
            WO15_CONTROL_ROUTE, {} if query is None else query, content_type, body
        ),
        _snapshot,
    )


def _fingerprint(root):  # type: ignore[no-untyped-def]
    if not root.exists():
        return ()
    return tuple(
        (str(path.relative_to(root)), path.read_bytes())
        for path in sorted(root.rglob("*")) if path.is_file()
    )


def test_runtime_composes_governed_wo15_root_and_restores_inertly(tmp_path) -> None:
    shared, provider, factory_calls = _shared()
    root = tmp_path.resolve()

    composition = create_intraday_runtime(shared, evidence_root=root)

    assert composition.wo15_store.root == root / "wo15-entry-timing-v1"
    assert composition.wo15_application.store is composition.wo15_store
    assert composition.wo15_application.wo13_store is composition.wo13_store
    assert composition.wo15_restored.state == "NOT_YET_RUN"
    assert composition.wo15_restoration.restore().state == "NOT_YET_RUN"
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []
    assert _fingerprint(composition.wo15_store.root) == ()


def test_empty_product_and_status_get_are_inert(tmp_path) -> None:
    control, _, store, _ = _control(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo15_control=control)
    before = _fingerprint(store.root)

    page = routes.handle_get(BrowserGetRequest(WO15_PRODUCT_ROUTE, {}), _snapshot)
    status = routes.handle_get(BrowserGetRequest(WO15_STATUS_ROUTE, {}), _snapshot)

    assert page is not None and page.status.value == 200
    assert "NOT_YET_RUN" in page.body
    assert status is not None and status.status.value == 200
    document = json.loads(status.body)
    assert document["restoration_state"] == "NOT_YET_RUN"
    for counter in (
        "provider_calls", "timing_evaluations", "wo13_operations",
        "wo14_operations", "upstream_operations", "autonomous_operations",
        "sponsor_operations", "broker_operations",
    ):
        assert document[counter] == 0
    assert _fingerprint(store.root) == before


def test_exact_post_restores_and_exact_replay_is_retained(tmp_path) -> None:
    control, _, store, request = _control(tmp_path)
    payload = operation_document(request)

    first = _post(control, payload)
    second = _post(control, payload)

    assert first is not None and first.status.value == 200
    assert second is not None and second.status.value == 200
    assert json.loads(first.body)["outcome"] == "COMPLETED"
    assert json.loads(second.body)["outcome"] == "RETAINED"
    restored = store.restore_current()
    assert restored is not None
    status = control.status_document()
    assert status["current_timing"]["timing_result"]["result_identity"] == (
        restored.result.result_identity
    )
    assert status["timing_evaluations"] == 1
    assert status["sponsor_operations"] == 2
    assert len(status["timing_history"]) >= 2
    before_restart_get = _fingerprint(store.root)
    restarted = IntradayWo15OperationalControl(
        control.application,
        IntradayWo15RestorationService(store=store),
    )
    assert restarted.status_document()["current_timing"] == status["current_timing"]
    assert restarted.status_document()["timing_history"] == status["timing_history"]
    assert _fingerprint(store.root) == before_restart_get


def test_exact_parser_rejects_missing_extra_naive_and_numeric_decimal(tmp_path) -> None:
    control, _, store, request = _control(tmp_path)
    valid = operation_document(request)
    malformed = []
    missing = json.loads(json.dumps(valid))
    missing["request"].pop("provenance")
    malformed.append(missing)
    extra = json.loads(json.dumps(valid))
    extra["request"]["extra"] = True
    malformed.append(extra)
    naive = json.loads(json.dumps(valid))
    naive["request"]["observed_at"] = "2026-08-17T10:00:00"
    malformed.append(naive)
    numeric = json.loads(json.dumps(valid))
    numeric["request"]["admission"]["entry_reference"] = 100
    malformed.append(numeric)

    responses = [_post(control, payload) for payload in malformed]

    assert all(item is not None and item.status.value == 400 for item in responses)
    assert all(json.loads(item.body)["outcome"] == "REJECTED" for item in responses)
    assert store.load_current() is None


def test_transport_guards_and_concurrency_fail_closed(tmp_path) -> None:
    control, _, store, request = _control(tmp_path)
    payload = operation_document(request)
    responses = (
        _post(control, payload, content_type="text/plain"),
        _post(control, payload, query={"x": ["1"]}),
        _post(control, None, raw=b"{"),
        _post(control, None, raw=b"x" * (MAX_WO15_REQUEST_BYTES + 1)),
    )
    control._active_request_identity = "ACTIVE-WO15"  # noqa: SLF001
    busy = _post(control, payload)
    control._active_request_identity = None  # noqa: SLF001

    assert all(item is not None and item.status.value == 400 for item in responses)
    assert busy is not None and busy.status.value == 409
    assert json.loads(busy.body)["failure_reason"] == "WO15_OPERATION_BUSY"
    assert store.load_current() is None


def test_stale_wo13_returns_conflict_and_persists_failure(tmp_path) -> None:
    control, wo13_store, store, request = _control(tmp_path)
    newer = _wo13(tmp_path, minute=35)
    for item, retain in (
        (newer[0], wo13_store.retain_handoff),
        (newer[1], wo13_store.retain_request),
        (newer[2], wo13_store.retain_trade_plan),
        (newer[3], wo13_store.retain_operation),
    ):
        retain(item)
    wo13_store.publish_current(newer[4])

    response = _post(control, operation_document(request))

    assert response is not None and response.status.value == 409
    assert json.loads(response.body)["failure_reason"] == "WO15_SUPERSEDED_WO13_REJECTED"
    assert store.load_current() is None
    assert store.load_latest_failure() is not None


def test_later_failure_keeps_current_and_projects_failure_separately(tmp_path) -> None:
    from tests.unit.intraday.test_wo15_application import _next_request

    control, _, store, request = _control(tmp_path)
    assert _post(control, operation_document(request)).status.value == 200
    current = store.load_current()
    bad = _next_request(
        request,
        minute=10,
        close="102",
        semantics=Wo15ProgressionSemantics.ALIGNED,
    )
    control.application._wo13_store = type(control.application.wo13_store)(  # noqa: SLF001
        (tmp_path / "missing-wo13").resolve()
    )

    response = _post(control, operation_document(bad))
    status = control.status_document()

    assert response is not None and response.status.value == 503
    assert store.load_current() == current
    assert status["current_timing"] is not None
    assert status["last_operation"]["outcome"] == "FAILED"
    assert status["latest_persisted_failure"] is not None


def test_waiting_post_has_no_handoff_and_mcx_lineage_is_exact(tmp_path) -> None:
    waiting, _, _, wait_request = _control(tmp_path / "waiting", close="100")
    mcx, _, _, mcx_request = _control(tmp_path / "mcx", mcx=True)

    assert _post(waiting, operation_document(wait_request)).status.value == 200
    assert _post(mcx, operation_document(mcx_request)).status.value == 200
    waiting_current = waiting.status_document()["current_timing"]
    mcx_current = mcx.status_document()["current_timing"]

    assert waiting_current["timing_result"]["current_state"] == "TIMING_WAITING"
    assert waiting_current["timing_handoff"] is None
    assert mcx_current["actual_contract_identity"] == mcx_request.admission.actual_contract_identity
    assert mcx_current["roll_lineage_identity"] == mcx_request.admission.roll_lineage_identity


def test_failed_reset_successor_history_remains_immutable(tmp_path) -> None:
    from tests.unit.intraday.test_wo15_application import _next_request

    control, _, _, first_request = _control(
        tmp_path,
        close="100",
        semantics=Wo15ProgressionSemantics.CONTRADICTORY,
    )
    assert _post(control, operation_document(first_request)).status.value == 200
    successor = _next_request(
        first_request,
        minute=10,
        close="101",
        semantics=Wo15ProgressionSemantics.ALIGNED,
    )
    assert _post(control, operation_document(successor)).status.value == 200

    history = control.status_document()["timing_history"]
    result_states = [
        item["current_state"] for item in history if item["event"] == "TIMING_RESULT"
    ]
    assert "TIMING_FAILED" in result_states
    assert "TIMING_QUALIFIED" in result_states
    assert any(item["event"] == "SUPERSESSION" for item in history)
