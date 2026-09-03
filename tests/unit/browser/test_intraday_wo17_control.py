from __future__ import annotations

import json
from types import SimpleNamespace

from kronos.application.intraday_wo16 import IntradayWo16PersistenceApplication
from kronos.application.intraday_wo17 import (
    IntradayWo17Application,
    IntradayWo17RestorationService,
    create_wo17_operation_request,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_wo17_control import (
    MAX_WO17_REQUEST_BYTES,
    WO17_CONTROL_ROUTE,
    WO17_PRODUCT_ROUTE,
    WO17_STATUS_ROUTE,
    IntradayWo17OperationalControl,
    operation_document,
)
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.wo16_persistence import Wo16Store
from kronos.intraday.wo17 import WO17_POLICY_CHECKSUM
from kronos.intraday.wo17_adapters import bind_wo17_upstream
from kronos.intraday.wo17_persistence import Wo17Store
from kronos.intraday.wo17_position import create_wo17_position_machine
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_wo16_application import _request as _wo16_request
from tests.unit.intraday.test_wo16_contracts import _chain


class _Workstation:
    def snapshot(self, selected=None):  # type: ignore[no-untyped-def]
        del selected
        return SimpleNamespace(probables=None, probables_v2=None)


def _control(tmp_path):  # type: ignore[no-untyped-def]
    chain = _chain(tmp_path / "chain")
    wo16_store = Wo16Store((tmp_path / "wo16").resolve())
    wo16 = IntradayWo16PersistenceApplication(store=wo16_store).execute(
        _wo16_request(chain)
    )
    restored16 = wo16_store.restore_current(chain["plan"].canonical_subject_identity)
    assert restored16 is not None
    snapshot = bind_wo17_upstream(
        current_pointer=restored16.pointer,
        snapshot=restored16.snapshot,
        decision=restored16.decision,
        admission=restored16.admission,
        bound_at=restored16.admission.recorded_at,
    )
    position = create_wo17_position_machine(snapshot)
    request = create_wo17_operation_request(
        snapshot=snapshot,
        position=position,
        requested_at=position.last_transition_at,
    )
    store = Wo17Store((tmp_path / "wo17").resolve())
    control = IntradayWo17OperationalControl(
        IntradayWo17Application(store=store),
        IntradayWo17RestorationService(store=store),
        wo16_store=wo16_store,
    )
    return control, store, request


def _post(control, payload, *, content_type="application/json", query=None, raw=None):  # type: ignore[no-untyped-def]
    body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else b""
    return IntradayBrowserRoutes(_Workstation(), wo17_control=control).handle_post(
        BrowserPostRequest(
            WO17_CONTROL_ROUTE,
            {} if query is None else query,
            content_type,
            body,
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


def test_empty_page_and_status_get_are_inert(tmp_path) -> None:
    control, store, _ = _control(tmp_path)
    routes = IntradayBrowserRoutes(_Workstation(), wo17_control=control)
    before = _fingerprint(store.root)

    page = routes.handle_get(BrowserGetRequest(WO17_PRODUCT_ROUTE, {}), _snapshot)
    status = routes.handle_get(BrowserGetRequest(WO17_STATUS_ROUTE, {}), _snapshot)

    assert page is not None and page.status.value == 200
    assert status is not None and status.status.value == 200
    document = json.loads(status.body)
    assert document["restoration_state"] == "NOT_YET_RUN"
    assert document["current_positions"] == []
    assert document["provider_analytical_calls"] == 0
    assert document["sponsor_operations"] == 0
    assert document["broker_operations"] == 0
    assert document["persistence_writes_from_get"] == 0
    assert _fingerprint(store.root) == before


def test_exact_post_replay_and_current_wo16_binding(tmp_path) -> None:
    control, store, request = _control(tmp_path)
    payload = operation_document(request)

    first = _post(control, payload)
    before = _fingerprint(store.root)
    replay = _post(control, payload)

    assert first is not None and first.status.value == 200
    assert json.loads(first.body)["outcome"] == "COMPLETED"
    assert replay is not None and replay.status.value == 200
    assert json.loads(replay.body)["outcome"] == "RETAINED"
    assert _fingerprint(store.root) == before
    status = control.status_document()
    assert status["policy_checksum"] == WO17_POLICY_CHECKSUM
    assert status["current_positions"][0]["position_state"] == "PAPER_ARMED"


def test_status_reloads_monitoring_written_state_without_mutation(tmp_path) -> None:
    control, store, request = _control(tmp_path)
    control.application.execute(request)
    before = _fingerprint(store.root)

    status = control.status_document()

    assert status["restoration_state"] == "LOADED"
    assert status["current_positions"][0]["position_state"] == "PAPER_ARMED"
    assert _fingerprint(store.root) == before


def test_exact_transport_guards_and_sanitized_failure(tmp_path, monkeypatch) -> None:
    control, store, request = _control(tmp_path)
    valid = operation_document(request)
    missing = json.loads(json.dumps(valid))
    missing["request"].pop("provenance")
    extra = json.loads(json.dumps(valid))
    extra["request"]["unexpected"] = True
    numeric = json.loads(json.dumps(valid))
    numeric["request"]["snapshot"]["lineage"]["entry_reference"] = 100
    responses = (
        _post(control, missing),
        _post(control, extra),
        _post(control, numeric),
        _post(control, valid, content_type="text/plain"),
        _post(control, valid, query={"x": ["1"]}),
        _post(control, None, raw=b"{"),
        _post(control, None, raw=b"x" * (MAX_WO17_REQUEST_BYTES + 1)),
    )
    assert all(item is not None and item.status.value == 400 for item in responses)
    assert not store.root.exists()

    def fail(_request):  # type: ignore[no-untyped-def]
        raise OSError("/private/secret/path")

    monkeypatch.setattr(control.application, "execute", fail)
    failed = _post(control, valid)
    assert failed is not None and failed.status.value == 503
    assert "/private/secret/path" not in failed.body


def test_busy_and_noncurrent_lineage_are_conflicts(tmp_path) -> None:
    control, _, request = _control(tmp_path)
    payload = operation_document(request)
    control._active_request_identity = "ACTIVE"  # noqa: SLF001
    busy = _post(control, payload)
    control._active_request_identity = None  # noqa: SLF001
    control._wo16_store._current_path(  # noqa: SLF001
        request.canonical_subject_identity
    ).unlink()
    stale = _post(control, payload)

    assert busy is not None and busy.status.value == 409
    assert json.loads(busy.body)["failure_reason"] == "WO17_OPERATION_BUSY"
    assert stale is not None and stale.status.value == 409
    assert json.loads(stale.body)["failure_reason"] == "WO16_CURRENT_DECISION_UNAVAILABLE"


def test_wo17_route_is_product_owned_only_when_composed() -> None:
    routes = IntradayBrowserRoutes(_Workstation())
    response = routes.handle_get(BrowserGetRequest(WO17_PRODUCT_ROUTE, {}), _snapshot)
    assert response is not None and response.status.value == 404
    assert routes.owns_post(WO17_CONTROL_ROUTE)
    assert not routes.owns_post("/control/swing-run")
