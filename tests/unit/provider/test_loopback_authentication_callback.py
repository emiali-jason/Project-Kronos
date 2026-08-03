from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import pickle

import pytest

from kronos.provider.callbacks.loopback import (
    CallbackCleanupCategory,
    LOOPBACK_HOST_HEADER,
    LoopbackAuthenticationCallbackListener,
    LoopbackCallbackRequest,
    LoopbackCallbackSession,
)
from kronos.provider.models.authentication import CallbackCategory, CallbackReadiness


def _request(
    query: str = "request_token=unit-request-token",
    *,
    method: str = "GET",
    path: str = "/kite/callback",
    hosts: tuple[str, ...] = (LOOPBACK_HOST_HEADER,),
    content_length: int = 0,
) -> LoopbackCallbackRequest:
    suffix = f"?{query}" if query else ""
    return LoopbackCallbackRequest(
        method=method,
        target=f"{path}{suffix}",
        host_headers=hosts,
        content_length=content_length,
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "HEAD"])
def test_only_get_is_accepted_and_first_request_is_terminal(method: str) -> None:
    session = LoopbackCallbackSession()

    assert session.handle(_request(method=method)).category() is CallbackCategory.INVALID_METHOD
    assert session.handle(_request()).category() is CallbackCategory.DUPLICATE


def test_request_body_is_rejected_without_reading_it() -> None:
    assert (
        LoopbackCallbackSession().handle(_request(content_length=1)).category()
        is CallbackCategory.INVALID_METHOD
    )


@pytest.mark.parametrize(
    "path",
    ["/", "/kite/callback/", "/other", "http://127.0.0.1:8765/kite/callback"],
)
def test_only_exact_callback_path_is_accepted(path: str) -> None:
    assert (
        LoopbackCallbackSession().handle(_request(path=path)).category()
        is CallbackCategory.INVALID_PATH
    )


@pytest.mark.parametrize(
    "hosts",
    [
        (),
        (LOOPBACK_HOST_HEADER, LOOPBACK_HOST_HEADER),
        ("localhost:8765",),
        ("127.0.0.1",),
        ("127.0.0.1:8766",),
        ("127.000.000.001:8765",),
        ("user@127.0.0.1:8765",),
        ("127.0.0.1:8765/path",),
        ("127.0.0.1:bad",),
        ("[::1]:8765",),
    ],
)
def test_host_validation_is_parsed_canonical_and_fail_closed(
    hosts: tuple[str, ...],
) -> None:
    assert (
        LoopbackCallbackSession().handle(_request(hosts=hosts)).category()
        is CallbackCategory.INVALID_HOST
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", CallbackCategory.TOKEN_MISSING),
        ("request_token=", CallbackCategory.TOKEN_MISSING),
        ("request_token=one&request_token=two", CallbackCategory.TOKEN_MULTIPLE),
        ("status=error&request_token=opaque", CallbackCategory.PROVIDER_REJECTED),
        ("error_type=Denied&request_token=opaque", CallbackCategory.PROVIDER_REJECTED),
    ],
)
def test_token_cardinality_and_provider_rejection_are_sanitized(
    query: str,
    expected: CallbackCategory,
) -> None:
    result = LoopbackCallbackSession().handle(_request(query))

    assert result.category() is expected
    assert "opaque" not in repr(result)


def test_one_token_is_accepted_consumed_once_and_not_retained() -> None:
    result = LoopbackCallbackSession().handle(_request())
    seen: list[str] = []

    assert result.category() is CallbackCategory.ACCEPTED
    assert result.consume_request_token(
        lambda token: token.consume_for_call(lambda value: seen.append(value))
    ) is None
    assert seen == ["unit-request-token"]
    with pytest.raises(RuntimeError, match="CALLBACK_TOKEN_UNAVAILABLE"):
        result.consume_request_token(lambda _token: None)
    assert "unit-request-token" not in repr(result)
    with pytest.raises(TypeError):
        pickle.dumps(result)


def test_fixed_html_never_reflects_callback_material() -> None:
    result = LoopbackCallbackSession().handle(_request("status=error&message=sensitive"))
    status, body = result.fixed_http_response()

    assert status == 400
    assert body == b"<!doctype html><title>KRONOS</title>Callback rejected."
    assert b"sensitive" not in body


def test_malformed_synthetic_request_is_sanitized_and_terminal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = LoopbackCallbackSession()
    malformed = LoopbackCallbackRequest(method="GET", target=None)  # type: ignore[arg-type]

    result = session.handle(malformed)

    assert result.category() in {
        CallbackCategory.INVALID_PATH,
        CallbackCategory.TRANSPORT_FAILURE,
    }
    assert session.handle(_request()).category() is CallbackCategory.DUPLICATE
    assert capsys.readouterr() == ("", "")
    with pytest.raises(TypeError):
        asdict(malformed)  # type: ignore[arg-type]


class _FakeServer:
    def __init__(self, result: object) -> None:
        self.result = result
        self.started = 0
        self.received: list[float] = []
        self.closed = 0
        self.joined: list[float] = []

    def start(self) -> None:
        self.started += 1

    def receive_once(self, timeout_seconds: float):  # type: ignore[no-untyped-def]
        self.received.append(timeout_seconds)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    def close(self) -> None:
        self.closed += 1

    def join(self, timeout_seconds: float) -> bool:
        self.joined.append(timeout_seconds)
        return True


def _listener(server: _FakeServer, now: datetime) -> LoopbackAuthenticationCallbackListener:
    return LoopbackAuthenticationCallbackListener(
        server_factory=lambda _session: server,
        clock=lambda: now,
    )


def test_listener_readiness_deadline_and_terminal_cleanup() -> None:
    now = datetime(2026, 8, 3, tzinfo=UTC)
    result = LoopbackCallbackSession().handle(_request())
    server = _FakeServer(result)
    listener = _listener(server, now)

    assert listener.readiness() is CallbackReadiness.NOT_READY
    assert server.started == 0
    listener.start()
    assert listener.readiness() is CallbackReadiness.READY
    assert listener.receive_once(deadline=now + timedelta(seconds=3)) is result
    assert server.received == [3.0]
    assert server.closed == 1
    assert server.joined == [1.0]
    assert listener.readiness() is CallbackReadiness.CLOSED
    assert listener.cleanup_category() is CallbackCleanupCategory.SUCCESS


@pytest.mark.parametrize(
    ("server_result", "expected"),
    [
        (TimeoutError("raw timeout"), CallbackCategory.TIMED_OUT),
        (OSError("raw socket detail"), CallbackCategory.TRANSPORT_FAILURE),
    ],
)
def test_listener_failure_is_sanitized_and_cleanup_is_immediate(
    server_result: BaseException,
    expected: CallbackCategory,
) -> None:
    now = datetime(2026, 8, 3, tzinfo=UTC)
    server = _FakeServer(server_result)
    listener = _listener(server, now)
    listener.start()

    result = listener.receive_once(deadline=now + timedelta(seconds=2))

    assert result.category() is expected
    assert "raw" not in repr(result)
    assert server.closed == 1
    assert listener.cleanup_category() is CallbackCleanupCategory.SUCCESS


def test_elapsed_deadline_does_not_call_server_and_still_cleans_up() -> None:
    now = datetime(2026, 8, 3, tzinfo=UTC)
    server = _FakeServer(AssertionError("must not receive"))
    listener = _listener(server, now)
    listener.start()

    result = listener.receive_once(deadline=now)

    assert result.category() is CallbackCategory.TIMED_OUT
    assert server.received == []
    assert server.closed == 1


def test_explicit_close_is_idempotent_and_local_only() -> None:
    now = datetime(2026, 8, 3, tzinfo=UTC)
    server = _FakeServer(AssertionError("must not receive"))
    listener = _listener(server, now)

    listener.close()
    listener.close()

    assert server.started == 0
    assert server.received == []
    assert server.closed == 0
    assert listener.readiness() is CallbackReadiness.CLOSED


def test_server_factory_failure_is_sanitized_and_listener_closes() -> None:
    now = datetime(2026, 8, 3, tzinfo=UTC)
    listener = LoopbackAuthenticationCallbackListener(
        server_factory=lambda _session: (_ for _ in ()).throw(
            OSError("raw bind detail")
        ),
        clock=lambda: now,
    )

    with pytest.raises(RuntimeError, match="CALLBACK_LISTENER_START_FAILED") as error:
        listener.start()

    assert "raw bind detail" not in str(error.value)
    assert listener.readiness() is CallbackReadiness.CLOSED
    assert listener.cleanup_category() is CallbackCleanupCategory.SUCCESS
