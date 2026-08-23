from __future__ import annotations

from datetime import date
from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Event, Thread

from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.intraday_historical_control import (
    HISTORICAL_OPERATION_IN_PROCESS_INVOCATION_UNAVAILABLE,
    INTRADAY_HISTORICAL_CONTROL_IDENTITY,
    INTRADAY_HISTORICAL_CONTROL_VERSION,
    IntradayHistoricalQualificationOperationalControl,
)
from kronos.browser.server import create_browser_server
from kronos.intraday.historical_operation import (
    HistoricalOperationStage,
    HistoricalOperationState,
    HistoricalQualificationOperationResult,
    create_historical_request_plan,
    resolve_historical_eod_sessions,
    resolve_historical_operational_subjects,
)
from kronos.intraday.historical_qualification import (
    HistoricalBindingAvailability,
    create_historical_research_subject_set,
)
from kronos.provider.models.authentication import AuthenticatedContextState
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from tests.unit.application.test_intraday_historical_operation import (
    NOW,
    _HistoricalCapability,
)
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.provider.test_shared_provider_runtime import _authenticate, _shared


FIVE_DATES = (
    date(2026, 8, 17),
    date(2026, 8, 18),
    date(2026, 8, 19),
    date(2026, 8, 20),
    date(2026, 8, 21),
)


def _running_control(
    tmp_path: Path,
    *,
    authenticate: bool = False,
    capability: _HistoricalCapability | None = None,
):  # type: ignore[no-untyped-def]
    shared, runtime, factory_calls = _shared()
    selected = capability or _HistoricalCapability()
    runtime.capability = selected
    if authenticate:
        _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: NOW,
    )
    control = IntradayHistoricalQualificationOperationalControl(
        composition.historical_invocation
    )
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "swing-review")
        ),
        intraday_workstation=composition.discovery_application,
        intraday_historical_control=control,
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
        selected,
        factory_calls,
    )


def _request(
    server,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
):  # type: ignore[no-untyped-def]
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=30)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    rendered = response.read().decode("utf-8")
    status = response.status
    response_headers = dict(response.headers)
    connection.close()
    return status, response_headers, rendered


def _headers(
    server,
    *,
    origin: str | None = None,
    content_type: str = "application/json",
) -> dict[str, str]:
    authority = f"127.0.0.1:{server.server_port}"
    return {
        "Host": authority,
        "Origin": origin or f"http://{authority}",
        "Content-Type": content_type,
    }


def _body(
    label: str = "KRONOS-WO-06HE-CONTROLLED",
    *,
    dates: tuple[date, ...] = (date(2026, 8, 17),),
    maximum: int = 373,
) -> bytes:
    return json.dumps({
        "request_identity": label,
        "sessions": [
            {
                "trading_date": day.isoformat(),
                "session_identity": (
                    "KRONOS-NSE-CAPITAL-MARKET-2022-2026:2026.1.2:"
                    f"{day.isoformat()}:REGULAR"
                ),
            }
            for day in dates
        ],
        "maximum_provider_requests": maximum,
        "requested_at": NOW.isoformat(),
    }).encode("utf-8")


def _close(server, thread: Thread) -> None:  # type: ignore[no-untyped-def]
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_status_is_loopback_bounded_and_side_effect_free(tmp_path: Path) -> None:
    (
        server,
        thread,
        _,
        runtime,
        composition,
        control,
        capability,
        factory_calls,
    ) = _running_control(tmp_path)
    try:
        authority = f"127.0.0.1:{server.server_port}"
        status, headers, rendered = _request(
            server,
            "GET",
            "/control/intraday-historical-qualification/status",
            headers={"Host": authority},
        )
        payload = json.loads(rendered)
        assert status == 200
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert payload == {
            "control_identity": INTRADAY_HISTORICAL_CONTROL_IDENTITY,
            "control_version": INTRADAY_HISTORICAL_CONTROL_VERSION,
            "service_identity": (
                "KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-V0"
            ),
            "service_version": "0.1.0",
            "service_available": True,
            "operation_available": False,
            "context_state": "ABSENT",
            "active_operation_identity": None,
            "last_result": None,
        }
        assert control.historical_invocation is composition.historical_invocation
        assert control.operation_service is composition.historical_operation
        assert control.operation_service._runtime is (
            composition.discovery_operation._runtime
        )
        assert capability.calls == 0
        assert runtime.begin_count == 0
        assert factory_calls == []
        assert _request(
            server,
            "GET",
            "/control/intraday-historical-qualification/status",
            headers={"Host": "localhost"},
        )[0] == 403
        assert _request(
            server,
            "GET",
            "/control/intraday-historical-qualification/status?unexpected=1",
            headers={"Host": authority},
        )[0] == 400
        for path in ("/intraday", "/status", "/swing/opportunities"):
            assert _request(server, "GET", path)[0] == 200
        assert capability.calls == 0
        assert composition.historical_operation.last_result is None
    finally:
        _close(server, thread)


def test_post_security_rejects_every_unbounded_shape(tmp_path: Path) -> None:
    server, thread, _, _, composition, _, capability, factory_calls = (
        _running_control(tmp_path)
    )
    try:
        body = _body()
        authority = f"127.0.0.1:{server.server_port}"
        assert _request(
            server,
            "GET",
            "/control/intraday-historical-qualification",
            headers={"Host": authority},
        )[0] == 404
        assert _request(
            server,
            "POST",
            "/control/intraday-historical-qualification/status",
            body=body,
            headers=_headers(server),
        )[0] == 404
        assert _request(
            server,
            "POST",
            "/control/intraday-historical-qualification?retry=1",
            body=body,
            headers=_headers(server),
        )[0] == 400
        assert _request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=body,
            headers=_headers(server, origin="http://evil.example"),
        )[0] == 403
        missing_origin = _headers(server)
        missing_origin.pop("Origin")
        assert _request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=body,
            headers=missing_origin,
        )[0] == 403
        wrong_host = _headers(server)
        wrong_host["Host"] = "localhost"
        assert _request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=body,
            headers=wrong_host,
        )[0] == 403
        assert _request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=body,
            headers=_headers(server, content_type="text/plain"),
        )[0] == 400
        assert _request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=b"x" * 4097,
            headers=_headers(server),
        )[0] == 400
        baseline = json.loads(body)
        invalid_payloads = (
            {
                name: value
                for name, value in baseline.items()
                if name != "maximum_provider_requests"
            },
            {**baseline, "symbol": "RELIANCE"},
            {**baseline, "timeframe": "5minute"},
            {**baseline, "unknown": True},
            {**baseline, "request_identity": "lowercase-rejected"},
            {**baseline, "sessions": []},
            {**baseline, "maximum_provider_requests": 10_001},
            {**baseline, "requested_at": NOW.replace(tzinfo=None).isoformat()},
            {
                **baseline,
                "sessions": [
                    {
                        **baseline["sessions"][0],
                        "symbol": "RELIANCE",
                    }
                ],
            },
        )
        for payload in invalid_payloads:
            assert _request(
                server,
                "POST",
                "/control/intraday-historical-qualification",
                body=json.dumps(payload).encode("utf-8"),
                headers=_headers(server),
            )[0] == 400
        assert capability.calls == 0
        assert factory_calls == []
        assert composition.historical_operation.last_result is None
    finally:
        _close(server, thread)


def test_context_states_fail_closed_without_authentication(tmp_path: Path) -> None:
    server, thread, shared, runtime, _, _, capability, factory_calls = (
        _running_control(tmp_path)
    )
    try:
        absent = json.loads(_request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=_body("WO-06HE-ABSENT"),
            headers=_headers(server),
        )[2])
        assert absent["state"] == "FAILED"
        assert absent["context_state"] == "ABSENT"
        assert absent["failure"] == "CONTEXT_UNAVAILABLE"
        assert absent["provider_request_count"] == 0
        assert capability.calls == 0
        assert runtime.begin_count == 0 and factory_calls == []

        _authenticate(shared)
        runtime.context_state = AuthenticatedContextState.EXPIRED
        begin_count = runtime.begin_count
        expired = json.loads(_request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=_body("WO-06HE-EXPIRED"),
            headers=_headers(server),
        )[2])
        assert expired["state"] == "FAILED"
        assert expired["context_state"] == "EXPIRED"
        assert expired["failure"] == "CONTEXT_EXPIRED"
        assert expired["provider_request_count"] == 0
        assert capability.calls == 0
        assert runtime.begin_count == begin_count
        assert len(factory_calls) == 1
    finally:
        _close(server, thread)


def test_post_reaches_exact_composed_harness_and_preserves_isolation(
    tmp_path: Path,
) -> None:
    (
        server,
        thread,
        shared,
        runtime,
        composition,
        control,
        capability,
        factory_calls,
    ) = _running_control(tmp_path, authenticate=True)
    before_intraday = composition.discovery_application.snapshot()
    before_swing = server.application.snapshot()
    try:
        assert control.historical_invocation is composition.historical_invocation
        assert control.operation_service is composition.historical_operation
        assert control.operation_service._runtime is shared
        body = _body("WO-06HE-EXACT-COMPOSED")
        first_text = _request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=body,
            headers=_headers(server),
        )[2]
        first = json.loads(first_text)
        calls_after_first = capability.calls
        duplicate = json.loads(_request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=body,
            headers=_headers(server),
        )[2])
        assert duplicate == first
        assert first["state"] == "COMPLETE"
        assert first["stage"] == "COMPLETE"
        assert first["context_state"] == "ACTIVE"
        assert first["subject_set_count"] == 98
        assert first["historically_resolvable_count"] == 93
        assert first["prerequisite_unavailable_count"] == 5
        assert first["provider_request_ceiling"] == 373
        assert first["provider_request_count"] == 373
        assert first["sessions_requested"] == first["sessions_valid"] == 1
        assert first["successful_reconstructions"] == 93
        assert first["persistence_complete"] is True
        assert first["reload_verified"] is True
        assert first["corpus_binding_performed"] is False
        assert first["production_state_mutated"] is False
        assert capability.instrument_calls == 1
        assert capability.historical_calls == 372
        assert capability.calls == calls_after_first
        assert runtime.begin_count == 1 and factory_calls == [1]
        assert shared.active_lease_count == 0
        assert composition.discovery_application.snapshot() == before_intraday
        assert server.application.snapshot() == before_swing
        for forbidden in (
            "access_token",
            "request_token",
            "api_secret",
            "Authorization",
            "instrument_token",
            "ohlcv",
            "traceback",
            "SDK",
        ):
            assert forbidden not in first_text
        calls_before_render = capability.calls
        for path in ("/intraday", "/status", "/swing/opportunities"):
            assert _request(server, "GET", path)[0] == 200
        assert capability.calls == calls_before_render
    finally:
        _close(server, thread)


def test_five_session_control_fixture_plans_exactly_without_provider_work(
    tmp_path: Path,
) -> None:
    server, thread, _, runtime, composition, _, capability, factory_calls = (
        _running_control(tmp_path)
    )
    observed = []
    plans = []
    unavailable_labels = []
    operation = composition.historical_operation

    def controlled_plan_only(request):  # type: ignore[no-untyped-def]
        observed.append(request)
        operation._validate_request(request)
        subject_set = create_historical_research_subject_set(
            operation.universe_publication
        )
        subjects = resolve_historical_operational_subjects(
            subject_set=subject_set,
            reconciliation=operation._reconciliation,
        )
        sessions = resolve_historical_eod_sessions(
            calendar=operation._calendar,
            requested=request.sessions,
            exchange="NSE",
            provenance=(request.operation_identity,),
        )
        plan = create_historical_request_plan(
            request=request,
            subjects=subjects,
            sessions=sessions,
        )
        plans.append(plan)
        unavailable_labels.extend(
            item.sponsor_label
            for item in subjects
            if item.binding.availability
            is HistoricalBindingAvailability.HISTORICAL_PREREQUISITE_UNAVAILABLE
        )
        return HistoricalQualificationOperationResult(
            operation_identity=request.operation_identity,
            state=HistoricalOperationState.READY,
            stage=HistoricalOperationStage.REQUEST_PLANNING,
            context_state=operation.actual_context_state,
            request_plan_identity=plan.plan_identity,
            subject_set_count=plan.subject_set_count,
            historically_resolvable_count=plan.eligible_subject_count,
            prerequisite_unavailable_count=plan.unavailable_subject_count,
            sessions_requested=plan.session_count,
            sessions_valid=plan.session_count,
            sessions_unavailable=0,
            subject_session_observations_planned=(
                plan.subject_session_observations
            ),
            successful_reconstructions=0,
            factual_failures=0,
            prerequisite_unavailable_observations=0,
            narrow_cpr_true_count=0,
            narrow_cpr_false_count=0,
            narrow_cpr_unavailable_count=0,
            provider_request_ceiling=request.maximum_provider_requests,
            provider_request_count=0,
            reconstruction_identities=(),
            bundle_identities=(),
            session_accounting=(),
            observation_failure_counts=(),
            persistence_complete=False,
            reload_verified=False,
            corpus_binding_performed=False,
            production_state_mutated=False,
            failure=None,
            completed_at=NOW,
        )

    operation.execute = controlled_plan_only  # type: ignore[method-assign]
    try:
        response = json.loads(_request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=_body(
                "KRONOS-WO-06HB-HISTORICAL-BOOTSTRAP-003",
                dates=FIVE_DATES,
                maximum=1861,
            ),
            headers=_headers(server),
        )[2])
        assert len(observed) == len(plans) == 1
        request = observed[0]
        plan = plans[0]
        assert tuple(item.trading_date for item in request.sessions) == FIVE_DATES
        assert request.maximum_provider_requests == 1861
        assert plan.subject_set_count == response["subject_set_count"] == 98
        assert plan.eligible_subject_count == 93
        assert plan.unavailable_subject_count == 5
        assert plan.historical_request_count == 1860
        assert plan.instrument_record_request_count == 1
        assert plan.total_provider_request_count == 1861
        assert plan.sequential is True and plan.automatic_retry is False
        assert set(unavailable_labels) == {
            "GOLDM",
            "SILVERM",
            "COPPER",
            "NATGAS",
            "CRUDE",
        }
        assert response["provider_request_count"] == 0
        assert capability.calls == 0
        assert runtime.begin_count == 0
        assert factory_calls == []
    finally:
        _close(server, thread)


def test_concurrency_and_sanitization_are_preserved(tmp_path: Path) -> None:
    blocked, proceed = Event(), Event()
    capability = _HistoricalCapability(block=blocked, proceed=proceed)
    (
        server,
        thread,
        _,
        _,
        _,
        control,
        _,
        factory_calls,
    ) = _running_control(tmp_path, authenticate=True, capability=capability)
    outcome: list[dict[str, object]] = []
    first_body = _body("WO-06HE-ACTIVE")
    first = Thread(
        target=lambda: outcome.append(json.loads(_request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=first_body,
            headers=_headers(server),
        )[2])),
        daemon=True,
    )
    try:
        first.start()
        assert blocked.wait(timeout=5)
        assert control.operation_service.active_operation_identity is not None
        same = json.loads(_request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=first_body,
            headers=_headers(server),
        )[2])
        different = json.loads(_request(
            server,
            "POST",
            "/control/intraday-historical-qualification",
            body=_body("WO-06HE-DIFFERENT"),
            headers=_headers(server),
        )[2])
        assert same["state"] == different["state"] == "CONFLICT"
        assert same["failure"] == different["failure"] == "OPERATION_CONFLICT"
        assert same["provider_request_count"] == 0
        assert different["provider_request_count"] == 0
        assert capability.instrument_calls == 1
        assert capability.historical_calls == 1
        proceed.set()
        first.join(timeout=30)
        assert outcome[0]["state"] == "COMPLETE"
        assert capability.instrument_calls == 1
        assert capability.historical_calls == 372
        assert factory_calls == [1]
        assert HISTORICAL_OPERATION_IN_PROCESS_INVOCATION_UNAVAILABLE.endswith(
            "INVOCATION_UNAVAILABLE"
        )
        assert not hasattr(control, "authenticate")
        assert not hasattr(control, "place_order")
        assert not hasattr(control, "select_contract")
    finally:
        proceed.set()
        first.join(timeout=30)
        _close(server, thread)
