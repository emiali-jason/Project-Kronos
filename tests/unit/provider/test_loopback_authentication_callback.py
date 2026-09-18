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
    assert len(server.received) == 1
    assert 2.9 < server.received[0] <= 3.0
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


# PF-02C real transport fixtures. The private test bind changes only the
# listening address; production Host/path validation remains exact and fixed.
def _pf02c_real_listener(monkeypatch, *, clock=None):
    import socket
    import threading
    from types import SimpleNamespace
    from kronos.provider.callbacks import loopback as transport

    accepted = threading.Event()
    sockets = []
    real_bind = transport._OneRequestHTTPServer.server_bind
    real_get = transport._OneRequestHTTPServer.get_request

    def isolated_bind(server):
        assert server.server_address == (transport.LOOPBACK_ADDRESS, transport.LOOPBACK_PORT)
        server.server_address = (transport.LOOPBACK_ADDRESS, 0)
        real_bind(server)
        assert server.server_address[1] not in {8765, 8947}

    def observed_accept(server):
        connection, address = real_get(server)
        sockets.append(connection)
        accepted.set()
        return connection, address

    monkeypatch.setattr(transport._OneRequestHTTPServer, "server_bind", isolated_bind)
    monkeypatch.setattr(transport._OneRequestHTTPServer, "get_request", observed_accept)
    servers = []

    def factory(session):
        server = transport.create_standard_library_server(session)
        servers.append(server)
        return server

    listener = transport.LoopbackAuthenticationCallbackListener(
        server_factory=factory, clock=clock or (lambda: datetime.now(UTC)),
    )
    return SimpleNamespace(
        listener=listener, servers=servers, accepted=accepted, sockets=sockets,
        connect=lambda: socket.create_connection(servers[-1]._server.server_address, timeout=1),
    )


def _pf02c_release(case, peer=None):
    import socket

    if peer is not None:
        try:
            peer.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        peer.close()
    case.listener.close()
    for server in case.servers:
        server.close()
        assert server.join(1.5), "fixture callback thread did not terminate"


def _pf02c_assert_released(case):
    assert case.listener.cleanup_category() is CallbackCleanupCategory.SUCCESS
    for server in case.servers:
        assert server._thread is None or not server._thread.is_alive()
        assert server._server.socket.fileno() == -1
    assert all(connection.fileno() == -1 for connection in case.sockets)


@pytest.mark.parametrize("partial", [b"GET /kite/call", b"GET /kite/callback HTTP/1.1\r\nHost: 127.0.0.1:8765\r\nX-Part:"])
def test_pf02c_close_terminates_real_partial_request(monkeypatch, partial):
    import time

    case = _pf02c_real_listener(monkeypatch)
    peer = None
    try:
        case.listener.start()
        peer = case.connect()
        peer.sendall(partial)
        assert case.accepted.wait(1)
        started = time.monotonic()
        case.listener.close()
        elapsed = time.monotonic() - started
        server = case.servers[0]
        print("PF02C_PARTIAL_CLOSE", {
            "thread_alive": server._thread.is_alive(),
            "accepted_socket_open": case.sockets[0].fileno() != -1,
            "listening_socket_open": server._server.socket.fileno() != -1,
            "cleanup": case.listener.cleanup_category().value,
            "elapsed_seconds": round(elapsed, 4),
        })
        assert elapsed < 1.5
        _pf02c_assert_released(case)
        assert peer.recv(4096) == b""
    finally:
        _pf02c_release(case, peer)


def _pf02c_request_bytes(*, target="/kite/callback?request_token=pf02c-synthetic-token", method="GET", host=LOOPBACK_HOST_HEADER):
    return f"{method} {target} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()


def _pf02c_receive(case, seconds=1):
    return case.listener.receive_once(deadline=datetime.now(UTC) + timedelta(seconds=seconds))


@pytest.mark.parametrize("partial", [None, b"GET /kite/", b"GET /kite/callback HTTP/1.1\r\nHost:"])
def test_pf02c_absolute_deadline_ends_real_worker_before_receive(monkeypatch, partial):
    import time

    case = _pf02c_real_listener(monkeypatch)
    peer = None
    started = time.monotonic()
    expires = started + 0.12
    case.listener.bind_deadline(expires, monotonic_clock=time.monotonic)
    # A later attempt to lengthen the same bound cannot reset the lifetime.
    case.listener.bind_deadline(expires + 30, monotonic_clock=time.monotonic)
    try:
        case.listener.start()
        if partial is not None:
            peer = case.connect()
            peer.sendall(partial)
            assert case.accepted.wait(1)
        server = case.servers[0]
        server._thread.join(0.75)
        assert not server._thread.is_alive()
        assert time.monotonic() - started < 0.75
        assert server._server.socket.fileno() == -1
        assert all(sock.fileno() == -1 for sock in case.sockets)
        result = _pf02c_receive(case, 2)
        assert result.category() is CallbackCategory.TIMED_OUT
        _pf02c_assert_released(case)
    finally:
        _pf02c_release(case, peer)


@pytest.mark.parametrize("prefix", [b"GET /kite/", b"GET /kite/callback HTTP/1.1\r\nX-Trickle: "])
def test_pf02c_trickling_bytes_cannot_extend_total_deadline(monkeypatch, prefix):
    import threading
    import time

    case = _pf02c_real_listener(monkeypatch)
    stop = threading.Event()
    sent = []
    peer = writer = None
    started = time.monotonic()
    case.listener.bind_deadline(started + 0.2, monotonic_clock=time.monotonic)
    try:
        case.listener.start()
        peer = case.connect()
        peer.sendall(prefix)
        assert case.accepted.wait(1)

        def trickle():
            for _ in range(100):
                if stop.wait(0.01):
                    return
                try:
                    peer.sendall(b"x")
                    sent.append(time.monotonic())
                except OSError:
                    return

        writer = threading.Thread(target=trickle)
        writer.start()
        result = _pf02c_receive(case, 5)
        elapsed = time.monotonic() - started
        assert result.category() is CallbackCategory.TIMED_OUT
        assert len(sent) >= 4  # Traffic arrived much faster than the read poll.
        assert elapsed < 0.8
        _pf02c_assert_released(case)
        print("PF02C_TRICKLE", {"elapsed_seconds": round(elapsed, 4), "chunks": len(sent)})
    finally:
        stop.set()
        if writer is not None:
            writer.join(1)
            assert not writer.is_alive()
        _pf02c_release(case, peer)


@pytest.mark.parametrize("stage", ["before_start", "before_receive"])
def test_pf02c_explicit_close_prevents_later_use(monkeypatch, stage):
    case = _pf02c_real_listener(monkeypatch)
    if stage == "before_receive":
        case.listener.start()
    case.listener.close()
    case.listener.close()
    assert case.listener.readiness() is CallbackReadiness.CLOSED
    _pf02c_assert_released(case)
    with pytest.raises(RuntimeError):
        case.listener.start()
    with pytest.raises(RuntimeError):
        _pf02c_receive(case)


@pytest.mark.parametrize("method,target,host,expected", [
    ("GET", "/kite/callback?request_token=pf02c-synthetic-token", LOOPBACK_HOST_HEADER, CallbackCategory.ACCEPTED),
    ("POST", "/kite/callback?request_token=synthetic", LOOPBACK_HOST_HEADER, CallbackCategory.INVALID_METHOD),
    ("GET", "/kite/callback/?request_token=synthetic", LOOPBACK_HOST_HEADER, CallbackCategory.INVALID_PATH),
    ("GET", "/kite/callback?request_token=synthetic", "localhost:8765", CallbackCategory.INVALID_HOST),
    ("GET", "/kite/callback?request_token=synthetic", "TEST_BIND_PORT", CallbackCategory.INVALID_HOST),
    ("GET", "/kite/callback?request_token=one&request_token=two", LOOPBACK_HOST_HEADER, CallbackCategory.TOKEN_MULTIPLE),
    ("GET", "/kite/callback?status=error&message=pf02c-sensitive", LOOPBACK_HOST_HEADER, CallbackCategory.PROVIDER_REJECTED),
])
def test_pf02c_real_validation_and_fixed_nonreflecting_response(monkeypatch, capsys, method, target, host, expected):
    case = _pf02c_real_listener(monkeypatch)
    peer = None
    try:
        case.listener.start()
        if host == "TEST_BIND_PORT":
            host = f"127.0.0.1:{case.servers[0]._server.server_address[1]}"
        peer = case.connect()
        peer.sendall(_pf02c_request_bytes(method=method, target=target, host=host))
        result = _pf02c_receive(case)
        assert result.category() is expected
        _pf02c_assert_released(case)
        response = b""
        while chunk := peer.recv(4096):
            response += chunk
        body = response.split(b"\r\n\r\n", 1)[1]
        assert body == result.fixed_http_response()[1]
        assert b"synthetic" not in response and b"pf02c-sensitive" not in response
        if expected is CallbackCategory.ACCEPTED:
            seen = []
            result.consume_request_token(lambda token: token.consume_for_call(lambda value: seen.append(value)))
            assert seen == ["pf02c-synthetic-token"]
            with pytest.raises(RuntimeError):
                result.consume_request_token(lambda _token: None)
        result.close()
        assert capsys.readouterr() == ("", "")
    finally:
        _pf02c_release(case, peer)


def test_pf02c_close_disposes_successful_but_unconsumed_real_result(monkeypatch):
    case = _pf02c_real_listener(monkeypatch)
    peer = None
    try:
        case.listener.start()
        peer = case.connect()
        peer.sendall(_pf02c_request_bytes())
        server = case.servers[0]
        server._thread.join(1)
        assert not server._thread.is_alive()
        result = server._server.result
        assert result is not None and result.category() is CallbackCategory.ACCEPTED
        case.listener.close()
        assert server._server.result is None
        with pytest.raises(RuntimeError, match="CALLBACK_TOKEN_UNAVAILABLE"):
            result.consume_request_token(lambda _token: None)
        _pf02c_assert_released(case)
    finally:
        _pf02c_release(case, peer)


@pytest.mark.parametrize("complete_first", [False, True])
def test_pf02c_concurrent_close_owns_one_real_shutdown(monkeypatch, complete_first):
    import threading
    from kronos.provider.callbacks import loopback as transport

    case = _pf02c_real_listener(monkeypatch)
    calls, errors = [], []
    original_close = transport._StandardLibraryServer.close

    def observed_close(server):
        calls.append(server)
        return original_close(server)

    monkeypatch.setattr(transport._StandardLibraryServer, "close", observed_close)
    peer = None
    workers = []
    try:
        case.listener.start()
        peer = case.connect()
        peer.sendall(_pf02c_request_bytes() if complete_first else b"GET /kite/")
        assert case.accepted.wait(1)
        result = _pf02c_receive(case) if complete_first else None
        barrier = threading.Barrier(3)

        def close():
            try:
                barrier.wait(1)
                case.listener.close()
            except BaseException as error:
                errors.append(error)

        workers = [threading.Thread(target=close) for _ in range(2)]
        for worker in workers:
            worker.start()
        barrier.wait(1)
        for worker in workers:
            worker.join(1.5)
            assert not worker.is_alive()
        assert not errors and len(calls) == 1
        case.listener.close()
        assert len(calls) == 1
        _pf02c_assert_released(case)
        if result is not None:
            # A transferred callback remains owned by its receiver.
            seen = []
            result.consume_request_token(lambda token: token.consume_for_call(lambda value: seen.append(value)))
            assert seen == ["pf02c-synthetic-token"]
    finally:
        for worker in workers:
            worker.join(1.5)
        _pf02c_release(case, peer)


def test_pf02c_close_racing_accept_catches_the_late_owned_socket(monkeypatch):
    import socket
    import threading
    from kronos.provider.callbacks import loopback as transport

    case = _pf02c_real_listener(monkeypatch)
    accepted, release, transport_closed = threading.Event(), threading.Event(), threading.Event()
    real_accept = socket.socket.accept
    real_close = transport._OneRequestHTTPServer.server_close
    late = []
    errors = []
    closer = peer = None
    try:
        case.listener.start()
        server = case.servers[0]._server

        def gated_accept(sock):
            connection, address = real_accept(sock)
            if sock is server.socket:
                late.append(connection)
                accepted.set()
                assert release.wait(2), "accepted socket was not released"
            return connection, address

        def observed_close(owner):
            real_close(owner)
            if owner is server:
                transport_closed.set()

        monkeypatch.setattr(socket.socket, "accept", gated_accept)
        monkeypatch.setattr(transport._OneRequestHTTPServer, "server_close", observed_close)
        peer = case.connect()
        assert accepted.wait(1)

        def close():
            try:
                case.listener.close()
            except BaseException as error:
                errors.append(error)

        closer = threading.Thread(target=close)
        closer.start()
        assert transport_closed.wait(1)
        release.set()
        closer.join(1.5)
        assert not closer.is_alive() and not errors
        assert len(late) == 1 and late[0].fileno() == -1
        _pf02c_assert_released(case)
    finally:
        release.set()
        if closer is not None:
            closer.join(1.5)
        _pf02c_release(case, peer)


@pytest.mark.parametrize("terminal", ["cancel", "timeout"])
def test_pf02c_terminal_race_disposes_late_valid_callback(monkeypatch, terminal):
    import threading
    from kronos.provider.callbacks import loopback as transport

    case = _pf02c_real_listener(monkeypatch)
    now = [0.0]
    clock = lambda: now[0]
    case.listener.bind_deadline(1.0, monotonic_clock=clock)
    entered, release = threading.Event(), threading.Event()
    real_publish = transport._OneRequestHTTPServer.publish_result
    candidates = []
    closer = peer = None

    def gated_publish(server, result):
        candidates.append(result)
        entered.set()
        assert release.wait(2), "classified callback was not released"
        return real_publish(server, result)

    monkeypatch.setattr(transport._OneRequestHTTPServer, "publish_result", gated_publish)
    try:
        case.listener.start()
        peer = case.connect()
        peer.sendall(_pf02c_request_bytes())
        assert entered.wait(1)
        if terminal == "cancel":
            closer = threading.Thread(target=case.listener.close)
            closer.start()
            assert case.servers[0]._closed.wait(1)
        else:
            now[0] = 1.0
        release.set()
        if closer is not None:
            closer.join(1.5)
            assert not closer.is_alive()
        else:
            assert _pf02c_receive(case).category() is CallbackCategory.TIMED_OUT
        assert candidates and case.servers[0]._server.result is None
        with pytest.raises(RuntimeError, match="CALLBACK_TOKEN_UNAVAILABLE"):
            candidates[0].consume_request_token(lambda _token: None)
        _pf02c_assert_released(case)
    finally:
        release.set()
        if closer is not None:
            closer.join(1.5)
        _pf02c_release(case, peer)


@pytest.mark.parametrize("fault", ["peer_disconnect", "response_write"])
def test_pf02c_transport_faults_terminate_without_sensitive_output(monkeypatch, capsys, fault):
    from kronos.provider.callbacks import loopback as transport

    case = _pf02c_real_listener(monkeypatch)
    peer = None
    if fault == "response_write":
        def fail_write(handler):
            raise BrokenPipeError("pf02c-private-response-detail")
        monkeypatch.setattr(transport._CallbackRequestHandler, "end_headers", fail_write)
    try:
        case.listener.start()
        peer = case.connect()
        if fault == "response_write":
            peer.sendall(_pf02c_request_bytes())
        else:
            assert case.accepted.wait(1)
            peer.close()
            peer = None
        result = _pf02c_receive(case)
        expected = CallbackCategory.ACCEPTED if fault == "response_write" else CallbackCategory.TRANSPORT_FAILURE
        assert result.category() is expected
        result.close()
        _pf02c_assert_released(case)
        assert capsys.readouterr() == ("", "")
    finally:
        _pf02c_release(case, peer)


def test_pf02c_real_join_failure_stays_owned_and_never_becomes_success(monkeypatch):
    import threading
    import time
    from kronos.provider.callbacks import loopback as transport

    case = _pf02c_real_listener(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    real_handle = transport._CallbackRequestHandler._handle_terminal_request
    real_close = transport._StandardLibraryServer.close
    calls = []

    def blocked_handler(handler):
        entered.set()
        assert release.wait(4), "test handler was not released"
        real_handle(handler)

    def counted_close(server):
        calls.append(server)
        real_close(server)

    monkeypatch.setattr(transport._CallbackRequestHandler, "_handle_terminal_request", blocked_handler)
    monkeypatch.setattr(transport._StandardLibraryServer, "close", counted_close)
    peer = None
    try:
        case.listener.start()
        peer = case.connect()
        peer.sendall(_pf02c_request_bytes())
        assert entered.wait(1)
        started = time.monotonic()
        case.listener.close()
        elapsed = time.monotonic() - started
        server = case.servers[0]
        assert transport.MAX_JOIN_SECONDS <= elapsed < transport.MAX_JOIN_SECONDS + 0.5
        assert server._thread.is_alive()
        assert case.listener._server is server
        assert case.listener.local_cleanup_state == "FAILED"
        assert case.listener.cleanup_category() is CallbackCleanupCategory.SANITIZED_FAILURE
        assert server._server.socket.fileno() == -1
        assert all(sock.fileno() == -1 for sock in case.sockets)
        for _ in range(3):
            case.listener.close()
            assert case.listener.local_cleanup_state == "FAILED"
        assert len(calls) == 1
        release.set()
        server._thread.join(1)
        assert not server._thread.is_alive()
        case.listener.close()
        assert case.listener.local_cleanup_state == "FAILED" and len(calls) == 1
        print("PF02C_JOIN_FAILURE", {"elapsed_seconds": round(elapsed, 4), "sticky": True})
    finally:
        release.set()
        if peer is not None:
            peer.close()
        for server in case.servers:
            server._thread.join(1.5)
            assert not server._thread.is_alive()


def test_pf02c_repeated_real_cycles_leave_no_owned_descriptors_or_threads(monkeypatch):
    import threading
    from kronos.provider.callbacks import loopback as transport

    original_workers = {thread.ident for thread in threading.enumerate() if thread.name == "kronos-loopback-callback"}
    case = _pf02c_real_listener(monkeypatch)
    factory = case.listener._server_factory
    for cycle in range(12):
        case.listener = transport.LoopbackAuthenticationCallbackListener(
            server_factory=factory, clock=lambda: datetime.now(UTC),
        )
        case.accepted.clear()
        peer = None
        try:
            case.listener.start()
            peer = case.connect()
            peer.sendall(_pf02c_request_bytes() if cycle % 2 else b"GET /partial")
            assert case.accepted.wait(1)
            if cycle % 2:
                result = _pf02c_receive(case)
                assert result.category() is CallbackCategory.ACCEPTED
                result.close()
            else:
                case.listener.close()
            _pf02c_assert_released(case)
        finally:
            _pf02c_release(case, peer)
    assert len(case.servers) == len(case.sockets) == 12
    assert all(not server._thread.is_alive() for server in case.servers)
    assert sum(sock.fileno() >= 0 for sock in case.sockets) == 0
    assert sum(server._server.socket.fileno() >= 0 for server in case.servers) == 0
    assert {thread.ident for thread in threading.enumerate() if thread.name == "kronos-loopback-callback"} == original_workers


def test_pf02c_failed_owned_socket_close_is_retained_and_not_repeated(monkeypatch):
    import gc
    import socket
    import weakref

    case = _pf02c_real_listener(monkeypatch)
    real_close = socket.socket.close
    peer = None
    retained = None
    calls = []
    try:
        case.listener.start()
        peer = case.connect()
        peer.sendall(b"GET /incomplete")
        assert case.accepted.wait(1)
        connection = case.sockets[0]
        target = id(connection)
        retained = weakref.ref(connection)

        def failed_close(sock):
            if id(sock) == target:
                calls.append(target)
                raise OSError("pf02c-private-close-failure")
            real_close(sock)

        monkeypatch.setattr(socket.socket, "close", failed_close)
        case.listener.close()
        server = case.servers[0]
        assert not server._thread.is_alive()
        assert server._server.socket.fileno() == -1
        assert connection.fileno() >= 0
        assert case.listener.local_cleanup_state == "FAILED"
        assert case.listener.cleanup_category() is CallbackCleanupCategory.SANITIZED_FAILURE
        assert server._server._connections[connection] == "FAILED"
        case.sockets.clear()
        del connection
        gc.collect()
        assert retained() is not None and retained().fileno() >= 0
        for _ in range(3):
            case.listener.close()
            assert case.listener.local_cleanup_state == "FAILED"
        assert calls == [target]
        # Explicit fixture-only release does not turn the production owner's
        # sticky failed disposition into a false successful cleanup result.
        real_close(retained())
        assert retained().fileno() == -1
        assert case.listener.local_cleanup_state == "FAILED"
    finally:
        if retained is not None and retained() is not None:
            real_close(retained())
        if peer is not None:
            real_close(peer)
        for server in case.servers:
            server._thread.join(1.5)
            assert not server._thread.is_alive()


def test_pf02c_close_during_real_server_construction_retains_pending_owner(monkeypatch):
    import threading

    case = _pf02c_real_listener(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    factory = case.listener._server_factory
    errors = []

    def held_factory(session):
        server = factory(session)
        entered.set()
        assert release.wait(2), "test server construction was not released"
        return server

    case.listener._server_factory = held_factory

    def start():
        try:
            case.listener.start()
        except BaseException as error:
            errors.append(error)

    starter = threading.Thread(target=start)
    starter.start()
    try:
        assert entered.wait(1)
        case.listener.close()
        assert case.listener.local_cleanup_state == "PENDING"
        assert case.listener.cleanup_category() is CallbackCleanupCategory.PENDING
        assert starter.is_alive()
        assert case.servers[0]._server.socket.fileno() >= 0
        release.set()
        starter.join(1.5)
        assert not starter.is_alive() and not errors
        assert case.servers[0]._thread is None
        _pf02c_assert_released(case)
    finally:
        release.set()
        starter.join(1.5)
        _pf02c_release(case)


def test_pf02c_idle_real_listener_waits_instead_of_spinning(monkeypatch):
    import selectors
    import socketserver
    import threading
    import time

    timeouts = []
    for selector_type in {selectors.DefaultSelector, socketserver._ServerSelector}:
        original = selector_type.select

        def observed_select(selector, timeout=None, original=original):
            if threading.current_thread().name == "kronos-loopback-callback" and len(timeouts) < 1000:
                timeouts.append(timeout)
            return original(selector, timeout)

        monkeypatch.setattr(selector_type, "select", observed_select)
    case = _pf02c_real_listener(monkeypatch)
    case.listener.bind_deadline(time.monotonic() + 0.08, monotonic_clock=time.monotonic)
    try:
        case.listener.start()
        case.servers[0]._thread.join(0.75)
        assert not case.servers[0]._thread.is_alive()
        case.listener.close()
        _pf02c_assert_released(case)
        assert timeouts and all(timeout is not None and 0 < timeout <= 0.1 for timeout in timeouts)
        assert len(timeouts) <= 3
    finally:
        _pf02c_release(case)
