from __future__ import annotations

from collections import Counter
from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Event, Thread

import pytest

from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.intraday_discovery_control import (
    DISCOVERY_OPERATIONAL_INVOCATION_SURFACE_UNAVAILABLE,
    IntradayDiscoveryOperationalControl,
)
from kronos.browser.server import create_browser_server
from kronos.provider.contracts.market_data import HistoricalInterval
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from tests.unit.application.test_intraday_discovery_operation import (
    OBSERVED,
    _configured_shared,
)
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.provider.test_shared_provider_runtime import _authenticate


def _running_control(
    tmp_path: Path,
    *,
    authenticate: bool = False,
    block: Event | None = None,
    proceed: Event | None = None,
):  # type: ignore[no-untyped-def]
    shared, runtime, factory_calls, request_count = _configured_shared(
        block=block,
        proceed=proceed,
    )
    if authenticate:
        _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: OBSERVED,
    )
    control = IntradayDiscoveryOperationalControl(
        composition.discovery_operation,
        composition.discovery_application,
    )
    app = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    server = create_browser_server(
        app,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "swing-review")
        ),
        intraday_workstation=composition.discovery_application,
        intraday_discovery_control=control,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return (
        server,
        thread,
        shared,
        runtime,
        composition,
        control,
        factory_calls,
        request_count,
    )


def _request(
    server,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
):  # type: ignore[no-untyped-def]
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    rendered = response.read().decode("utf-8")
    status = response.status
    response_headers = dict(response.headers)
    connection.close()
    return status, response_headers, rendered


def _headers(server, *, origin: str | None = None, content_type: str = "application/json"):
    authority = f"127.0.0.1:{server.server_port}"
    return {
        "Host": authority,
        "Origin": origin or f"http://{authority}",
        "Content-Type": content_type,
    }


def _body(label: str = "WO-05B-CONTROLLED") -> bytes:
    return json.dumps({
        "request_identity": label,
        "observation_boundary": OBSERVED.isoformat(),
    }).encode("utf-8")


def _close(server, thread: Thread) -> None:  # type: ignore[no-untyped-def]
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_status_is_host_bounded_and_has_zero_side_effects(tmp_path: Path) -> None:
    server, thread, _, _, composition, control, factory_calls, requests = (
        _running_control(tmp_path)
    )
    try:
        authority = f"127.0.0.1:{server.server_port}"
        status, headers, body = _request(
            server,
            "GET",
            "/control/intraday-discovery/status",
            headers={"Host": authority},
        )
        payload = json.loads(body)
        assert status == 200
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert payload["service_available"] is True
        assert payload["operation_available"] is False
        assert payload["context_state"] == "ABSENT"
        assert payload["active_operation_identity"] is None
        assert payload["last_result"] is None
        assert payload["last_successful_run_identity"] is None
        assert control.operation_service is composition.discovery_operation
        assert control.operation_service.active_operation_identity is None
        assert requests == [0]
        assert factory_calls == []
        assert _request(
            server,
            "GET",
            "/control/intraday-discovery/status",
            headers={"Host": "localhost"},
        )[0] == 403
        assert _request(
            server,
            "GET",
            "/control/intraday-discovery/status?unexpected=1",
            headers={"Host": authority},
        )[0] == 400
        assert requests == [0]
        assert composition.discovery_operation.last_result is None
    finally:
        _close(server, thread)


def test_post_security_rejects_every_unbounded_request(tmp_path: Path) -> None:
    server, thread, _, _, composition, _, factory_calls, requests = _running_control(
        tmp_path
    )
    try:
        body = _body()
        authority = f"127.0.0.1:{server.server_port}"
        assert _request(
            server,
            "GET",
            "/control/intraday-discovery",
            headers={"Host": authority},
        )[0] == 404
        assert _request(
            server,
            "POST",
            "/control/intraday-discovery/status",
            body=body,
            headers=_headers(server),
        )[0] == 404
        assert _request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=body,
            headers=_headers(server, origin="http://evil.example"),
        )[0] == 403
        bad_host = _headers(server)
        bad_host["Host"] = "localhost"
        assert _request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=body,
            headers=bad_host,
        )[0] == 403
        assert _request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=body,
            headers=_headers(server, content_type="text/plain"),
        )[0] == 400
        assert _request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=b"x" * 513,
            headers=_headers(server),
        )[0] == 400
        invalid_payloads = (
            {"request_identity": "VALID"},
            {
                "request_identity": "VALID",
                "observation_boundary": OBSERVED.isoformat(),
                "unknown": True,
            },
            {
                "request_identity": "lowercase-is-rejected",
                "observation_boundary": OBSERVED.isoformat(),
            },
            {
                "request_identity": "VALID",
                "observation_boundary": OBSERVED.replace(tzinfo=None).isoformat(),
            },
        )
        for payload in invalid_payloads:
            assert _request(
                server,
                "POST",
                "/control/intraday-discovery",
                body=json.dumps(payload).encode("utf-8"),
                headers=_headers(server),
            )[0] == 400
        assert requests == [0]
        assert factory_calls == []
        assert composition.discovery_operation.last_result is None
    finally:
        _close(server, thread)


def test_inactive_context_fails_closed_despite_connected_swing_view(
    tmp_path: Path,
) -> None:
    server, thread, _, _, composition, _, factory_calls, requests = _running_control(
        tmp_path
    )
    try:
        assert server.application.snapshot().provider_state.value == "CONNECTED"
        status, _, rendered = _request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=_body("CONTEXT-CHECK"),
            headers=_headers(server),
        )
        payload = json.loads(rendered)
        assert status == 200
        assert payload["state"] == "FAILED"
        assert payload["context_state"] == "ABSENT"
        assert payload["failure"] == "CONTEXT_UNAVAILABLE"
        assert payload["historical_request_count"] == 0
        assert requests == [0]
        assert factory_calls == []
        assert composition.discovery_application.snapshot().current_failure == (
            "CONTEXT_UNAVAILABLE"
        )
    finally:
        _close(server, thread)


def test_post_reaches_exact_composed_service_and_is_idempotent(tmp_path: Path) -> None:
    (
        server,
        thread,
        shared,
        runtime,
        composition,
        control,
        factory_calls,
        requests,
    ) = _running_control(tmp_path, authenticate=True)
    try:
        assert control.operation_service is composition.discovery_operation
        assert control.operation_service._runtime is shared
        observed_requests = []
        historical_candles = runtime.capability.historical_candles

        def recording_historical(request):  # type: ignore[no-untyped-def]
            observed_requests.append(request)
            return historical_candles(request)

        runtime.capability.historical_candles = recording_historical  # type: ignore[method-assign]
        body = _body("CONTROLLED-ONE")
        first = json.loads(_request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=body,
            headers=_headers(server),
        )[2])
        duplicate = json.loads(_request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=body,
            headers=_headers(server),
        )[2])
        assert first == duplicate
        assert first["state"] == "COMPLETE"
        assert first["context_state"] == "ACTIVE"
        assert first["universe_count"] == 98
        assert first["pre_evaluable_count"] == 93
        assert first["prerequisite_unavailable_count"] == 5
        assert first["machine_fact_successes"] == 93
        assert first["machine_fact_failures"] == 0
        assert first["historical_request_count"] == 372
        assert first["persistence_complete"] is True
        assert first["snapshot_updated"] is True
        assert requests == [372]
        assert factory_calls == [1]
        assert shared.active_lease_count == 0
        intervals = Counter(item.interval for item in observed_requests)
        assert intervals == Counter({
            HistoricalInterval.DAY: 93,
            HistoricalInterval.SIXTY_MINUTE: 93,
            HistoricalInterval.FIFTEEN_MINUTE: 93,
            HistoricalInterval.FIVE_MINUTE: 93,
        })
        symbols = {item.instrument.trading_symbol for item in observed_requests}
        assert len(symbols) == 93
        assert symbols.isdisjoint({"GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"})
        snapshot = composition.discovery_application.snapshot()
        assert snapshot.last_successful_run_identity == first["run_identity"]
        assert snapshot.candidate_admitted_count == 0
        assert snapshot.candidate_not_admitted_count == 0
        calls_before_render = requests[0]
        status, _, page = _request(server, "GET", "/intraday")
        assert status == 200
        assert "LAST SUCCESSFUL ANALYSIS" in page
        assert requests == [calls_before_render]
        status_payload = json.loads(_request(
            server,
            "GET",
            "/control/intraday-discovery/status",
            headers={"Host": f"127.0.0.1:{server.server_port}"},
        )[2])
        assert status_payload["last_result"] == first
        assert status_payload["last_successful_run_identity"] == first["run_identity"]
    finally:
        _close(server, thread)


def test_concurrent_same_and_different_requests_are_bounded(tmp_path: Path) -> None:
    blocked, proceed = Event(), Event()
    server, thread, _, _, _, control, factory_calls, requests = _running_control(
        tmp_path,
        authenticate=True,
        block=blocked,
        proceed=proceed,
    )
    outcome: list[dict[str, object]] = []
    first = Thread(
        target=lambda: outcome.append(json.loads(_request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=_body("ACTIVE"),
            headers=_headers(server),
        )[2])),
        daemon=True,
    )
    try:
        first.start()
        assert blocked.wait(timeout=3)
        assert control.operation_service.active_operation_identity is not None
        active_status = json.loads(_request(
            server,
            "GET",
            "/control/intraday-discovery/status",
            headers={"Host": f"127.0.0.1:{server.server_port}"},
        )[2])
        assert active_status["active_operation_identity"] is not None
        same = json.loads(_request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=_body("ACTIVE"),
            headers=_headers(server),
        )[2])
        different = json.loads(_request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=_body("DIFFERENT"),
            headers=_headers(server),
        )[2])
        assert same["state"] == different["state"] == "CONFLICT"
        assert same["failure"] == different["failure"] == "OPERATION_CONFLICT"
        assert requests == [1]
        proceed.set()
        first.join(timeout=10)
        assert outcome[0]["state"] == "COMPLETE"
        assert requests == [372]
        assert factory_calls == [1]
    finally:
        proceed.set()
        first.join(timeout=10)
        _close(server, thread)


def test_response_discards_provider_exception_and_preserves_last_success(
    tmp_path: Path,
) -> None:
    server, thread, shared, runtime, composition, _, factory_calls, requests = (
        _running_control(tmp_path, authenticate=True)
    )
    try:
        success = json.loads(_request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=_body("SUCCESS"),
            headers=_headers(server),
        )[2])
        shared.invalidate("CONTROLLED_CONTEXT_LOSS")
        failure_text = _request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=_body("AFTER-LOSS"),
            headers=_headers(server),
        )[2]
        failure = json.loads(failure_text)
        assert failure["failure"] == "CONTEXT_UNAVAILABLE"
        assert "token" not in failure_text.lower()
        assert "provider_record" not in failure_text
        assert "traceback" not in failure_text.lower()
        snapshot = composition.discovery_application.snapshot()
        assert snapshot.last_successful_run_identity == success["run_identity"]
        assert snapshot.current_failure == "CONTEXT_UNAVAILABLE"
        assert requests == [372]
        assert factory_calls == [1]
        assert runtime is not None
    finally:
        _close(server, thread)


def test_raw_provider_exception_is_not_exposed_and_is_not_retried(
    tmp_path: Path,
) -> None:
    server, thread, _, runtime, _, _, factory_calls, requests = _running_control(
        tmp_path,
        authenticate=True,
    )

    def unsafe_failure(_request):  # type: ignore[no-untyped-def]
        requests[0] += 1
        raise RuntimeError("access_token=PRIVATE provider_record={raw}")

    runtime.capability.historical_candles = unsafe_failure  # type: ignore[method-assign]
    try:
        status, _, response = _request(
            server,
            "POST",
            "/control/intraday-discovery",
            body=_body("SANITIZED"),
            headers=_headers(server),
        )
        payload = json.loads(response)
        assert status == 200
        assert payload["state"] == "COMPLETE"
        assert payload["machine_fact_successes"] == 0
        assert payload["machine_fact_failures"] == 93
        assert payload["historical_request_count"] == 93
        assert requests == [93]
        assert factory_calls == [1]
        assert "access_token" not in response
        assert "provider_record" not in response
        assert "PRIVATE" not in response
        assert "traceback" not in response.lower()
    finally:
        _close(server, thread)


def test_control_contract_contains_no_weekly_four_hour_or_broker_surface() -> None:
    assert DISCOVERY_OPERATIONAL_INVOCATION_SURFACE_UNAVAILABLE == (
        "DISCOVERY_OPERATIONAL_INVOCATION_SURFACE_UNAVAILABLE"
    )
    assert HistoricalInterval.DAY.value == "day"
    assert HistoricalInterval.SIXTY_MINUTE.value == "60minute"
    assert HistoricalInterval.FIFTEEN_MINUTE.value == "15minute"
    assert HistoricalInterval.FIVE_MINUTE.value == "5minute"
    assert not hasattr(IntradayDiscoveryOperationalControl, "place_order")
    assert not hasattr(IntradayDiscoveryOperationalControl, "authenticate")
    assert not hasattr(IntradayDiscoveryOperationalControl, "select_contract")


@pytest.mark.parametrize("invalid", [None, object(), {}, []])
def test_control_rejects_non_composed_dependencies(invalid: object) -> None:
    with pytest.raises(ValueError, match="INTRADAY_DISCOVERY_CONTROL_INVALID"):
        IntradayDiscoveryOperationalControl(invalid, invalid)  # type: ignore[arg-type]
