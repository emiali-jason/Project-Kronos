"""One-request standard-library loopback authentication callback transport."""

from __future__ import annotations

import http.server
import io
import math
import socket
import selectors
import time
import threading
from collections.abc import Callable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Protocol, TypeVar
from urllib.parse import parse_qs, urlsplit

from kronos.provider.models.authentication import CallbackCategory, CallbackReadiness


LOOPBACK_ADDRESS = "127.0.0.1"
LOOPBACK_PORT = 8765
LOOPBACK_HOST_HEADER = "127.0.0.1:8765"
LOOPBACK_PATH = "/kite/callback"
DEFAULT_CALLBACK_RETURN_URL = "http://127.0.0.1:8947/swing/opportunities"
MAX_JOIN_SECONDS = 1.0

_REJECTION_HTML = b"<!doctype html><title>KRONOS</title>Callback rejected."
_EXPIRY_HTML = b"<!doctype html><title>KRONOS</title>Callback expired."
_PROVIDER_ERROR_FIELDS = frozenset(
    {"error", "error_type", "error_reason", "error_description", "message"}
)
_ResultT = TypeVar("_ResultT")


class CallbackCleanupCategory(StrEnum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    SUCCESS = "SUCCESS"
    PENDING = "PENDING"
    SANITIZED_FAILURE = "SANITIZED_FAILURE"


class LoopbackCallbackRequest:
    """Transient synthetic request accepted by the transport decision seam."""

    __slots__ = ("content_length", "host_headers", "method", "target")

    def __init__(
        self,
        *,
        method: str,
        target: str = LOOPBACK_PATH,
        host_headers: tuple[str, ...] = (LOOPBACK_HOST_HEADER,),
        content_length: int = 0,
    ) -> None:
        self.method = method
        self.target = target
        self.host_headers = host_headers
        self.content_length = content_length

    def __repr__(self) -> str:
        return "<LoopbackCallbackRequest redacted>"

    def __str__(self) -> str:
        return "<LoopbackCallbackRequest redacted>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CALLBACK_REQUEST_SERIALIZATION_PROHIBITED")


class _OneUseRequestToken:
    __slots__ = ("_closed", "_token", "_used", "_lock")

    def __init__(self, token: str) -> None:
        self._lock = threading.Lock()
        self._token: str | None = token
        self._used = False
        self._closed = False

    def consume_for_call(self, operation: Callable[[str], _ResultT]) -> _ResultT:
        with self._lock:
            if self._closed or self._used or self._token is None:
                raise RuntimeError("REQUEST_TOKEN_UNAVAILABLE")
            token = self._token
            self._token = None
            self._used = True
        try:
            result = operation(token)
            if result is token or (isinstance(result, str) and result == token):
                raise RuntimeError("REQUEST_TOKEN_RETURNED")
            return result
        finally:
            self.close()

    def close(self) -> None:
        with self._lock:
            self._token = None
            self._closed = True

    def __repr__(self) -> str:
        return "<OneUseRequestToken redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("REQUEST_TOKEN_SERIALIZATION_PROHIBITED")


class LoopbackCallbackResult:
    """Sanitized terminal result with an optional one-use token carrier."""

    __slots__ = ("_category", "_closed", "_return_url", "_token", "_lock")

    def __init__(
        self,
        category: CallbackCategory,
        token: _OneUseRequestToken | None = None,
        *,
        return_url: str | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._category = category
        self._token = token
        self._return_url = return_url
        self._closed = False

    def category(self) -> CallbackCategory:
        return self._category

    def consume_request_token(
        self,
        operation: Callable[[_OneUseRequestToken], _ResultT],
    ) -> _ResultT:
        with self._lock:
            if self._closed or self._category is not CallbackCategory.ACCEPTED:
                raise RuntimeError("CALLBACK_TOKEN_UNAVAILABLE")
            token = self._token
            if token is None:
                raise RuntimeError("CALLBACK_TOKEN_UNAVAILABLE")
            self._token = None
        try:
            return operation(token)
        finally:
            token.close()
            with self._lock:
                self._closed = True

    def close(self) -> None:
        with self._lock:
            token = self._token
            self._token = None
            self._closed = True
        if token is not None:
            token.close()

    def fixed_http_response(self) -> tuple[int, bytes]:
        if self._category is CallbackCategory.ACCEPTED:
            return 303, b""
        if self._category is CallbackCategory.TIMED_OUT:
            return 408, _EXPIRY_HTML
        return 400, _REJECTION_HTML

    def fixed_http_headers(self) -> tuple[tuple[str, str], ...]:
        headers = (
            ("Cache-Control", "no-store"),
            ("Referrer-Policy", "no-referrer"),
        )
        if self._category is CallbackCategory.ACCEPTED:
            if self._return_url is None:
                raise RuntimeError("CALLBACK_RETURN_DESTINATION_UNAVAILABLE")
            return (("Location", self._return_url),) + headers
        return headers

    def __repr__(self) -> str:
        return f"<LoopbackCallbackResult {self._category.value}>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CALLBACK_RESULT_SERIALIZATION_PROHIBITED")


class LoopbackCallbackSession:
    """Atomic first-request classification with a terminal cancellation fence."""

    __slots__ = ("_lock", "_terminal", "_cancelled", "_return_url")

    def __init__(self, *, return_url: str = DEFAULT_CALLBACK_RETURN_URL) -> None:
        self._lock = threading.Lock()
        self._terminal = False
        self._cancelled = False
        self._return_url = _validated_return_url(return_url)

    def handle(self, request: LoopbackCallbackRequest) -> LoopbackCallbackResult:
        with self._lock:
            if self._terminal:
                return LoopbackCallbackResult(CallbackCategory.DUPLICATE)
            self._terminal = True
        try:
            result = _classify_first_request(request, return_url=self._return_url)
        except Exception:
            result = LoopbackCallbackResult(CallbackCategory.TRANSPORT_FAILURE)
        with self._lock:
            cancelled = self._cancelled
        if cancelled:
            result.close()
            return LoopbackCallbackResult(CallbackCategory.TRANSPORT_FAILURE)
        return result

    def close(self) -> None:
        with self._lock:
            self._terminal = True
            self._cancelled = True

    def timeout(self) -> LoopbackCallbackResult:
        with self._lock:
            duplicate = self._terminal
            self._terminal = True
            self._cancelled = True
        return LoopbackCallbackResult(
            CallbackCategory.DUPLICATE if duplicate else CallbackCategory.TIMED_OUT
        )


class _TerminalServer(Protocol):
    def start(self) -> None: ...

    def receive_once(self, timeout_seconds: float) -> LoopbackCallbackResult: ...

    def close(self) -> None: ...

    def join(self, timeout_seconds: float) -> bool: ...


ServerFactory = Callable[[LoopbackCallbackSession], _TerminalServer]


class LoopbackAuthenticationCallbackListener:
    """Bounded callback owner; readiness never substitutes for physical cleanup."""

    __slots__ = (
        "_cleanup", "_clock", "_readiness", "_server", "_server_factory",
        "_session", "_lock", "_starting", "_receiving", "_cancelled",
        "_cleanup_running", "_expires_at", "_monotonic_clock",
    )

    def __init__(self, *, server_factory: ServerFactory,
                 clock: Callable[[], datetime],
                 return_url: str = DEFAULT_CALLBACK_RETURN_URL) -> None:
        self._clock = clock
        self._session = LoopbackCallbackSession(return_url=return_url)
        self._server_factory = server_factory
        self._server: _TerminalServer | None = None
        self._readiness = CallbackReadiness.NOT_READY
        self._cleanup = CallbackCleanupCategory.NOT_ATTEMPTED
        self._lock = threading.RLock()
        self._starting = False
        self._receiving = False
        self._cancelled = False
        self._cleanup_running = False
        self._expires_at: float | None = None
        self._monotonic_clock = time.monotonic

    def bind_deadline(self, expires_at: float, *,
                      monotonic_clock: Callable[[], float]) -> None:
        """Bind the service's absolute deadline; repeated calls only shorten it."""
        if not math.isfinite(expires_at) or not callable(monotonic_clock):
            raise ValueError("CALLBACK_DEADLINE_INVALID")
        with self._lock:
            if self._expires_at is not None and self._monotonic_clock is not monotonic_clock:
                raise ValueError("CALLBACK_DEADLINE_CLOCK_CHANGED")
            self._monotonic_clock = monotonic_clock
            self._expires_at = (expires_at if self._expires_at is None
                                else min(self._expires_at, expires_at))
            server = self._server
            bound = self._expires_at
        if server is not None:
            bind = getattr(server, "bind_deadline", None)
            if callable(bind):
                bind(bound, monotonic_clock=monotonic_clock)

    def start(self) -> None:
        with self._lock:
            if self._readiness is not CallbackReadiness.NOT_READY or self._starting:
                raise RuntimeError("CALLBACK_LISTENER_NOT_STARTABLE")
            self._starting = True
        failed = False
        try:
            server = self._server_factory(self._session)
            with self._lock:
                self._server = server
                cancelled = self._cancelled
                expires_at = self._expires_at
                clock = self._monotonic_clock
            if expires_at is not None:
                bind = getattr(server, "bind_deadline", None)
                if callable(bind):
                    bind(expires_at, monotonic_clock=clock)
            if not cancelled:
                server.start()
        except Exception:
            failed = True
        with self._lock:
            self._starting = False
            if failed or self._cancelled:
                self._cancelled = True
                self._readiness = CallbackReadiness.CLOSED
            else:
                self._readiness = CallbackReadiness.READY
            closed = self._cancelled
        if closed:
            self._session.close()
            self._cleanup_transport()
        if failed:
            raise RuntimeError("CALLBACK_LISTENER_START_FAILED")

    def readiness(self) -> CallbackReadiness:
        with self._lock:
            return self._readiness

    def receive_once(self, *, deadline: datetime) -> LoopbackCallbackResult:
        with self._lock:
            if self._readiness is not CallbackReadiness.READY or self._receiving:
                raise RuntimeError("CALLBACK_LISTENER_NOT_READY")
            self._receiving = True
            server = self._server
            clock = self._monotonic_clock
        result = None
        try:
            remaining = max(0.0, (deadline - self._clock()).total_seconds())
            self.bind_deadline(clock() + remaining, monotonic_clock=clock)
            with self._lock:
                remaining = max(0.0, self._expires_at - clock())
            if remaining <= 0:
                self._session.timeout()
                result = LoopbackCallbackResult(CallbackCategory.TIMED_OUT)
            elif server is None:
                result = LoopbackCallbackResult(CallbackCategory.TRANSPORT_FAILURE)
            else:
                result = server.receive_once(remaining)
        except TimeoutError:
            self._session.timeout()
            result = LoopbackCallbackResult(CallbackCategory.TIMED_OUT)
        except Exception:
            result = LoopbackCallbackResult(CallbackCategory.TRANSPORT_FAILURE)
        finally:
            with self._lock:
                self._readiness = CallbackReadiness.CLOSED
            self._cleanup_transport()
        with self._lock:
            cancelled = self._cancelled
            expired = self._expires_at is not None and clock() >= self._expires_at
            self._receiving = False
        if cancelled or expired:
            result.close()
            return LoopbackCallbackResult(
                CallbackCategory.TIMED_OUT if expired else CallbackCategory.TRANSPORT_FAILURE
            )
        return result

    def invalidate_pending(self) -> None:
        """Fence callback publication and drop unclaimed tokens; perform no I/O."""
        with self._lock:
            self._cancelled = True
            self._readiness = CallbackReadiness.CLOSED
            server = self._server
        self._session.close()
        if server is not None:
            invalidate = getattr(server, "invalidate_pending", None)
            if callable(invalidate):
                invalidate()

    def close(self) -> None:
        self.invalidate_pending()
        self._cleanup_transport()

    def cleanup_category(self) -> CallbackCleanupCategory:
        with self._lock:
            return self._cleanup

    @property
    def local_cleanup_state(self) -> str:
        with self._lock:
            return {
                CallbackCleanupCategory.NOT_ATTEMPTED: "OPEN",
                CallbackCleanupCategory.PENDING: "PENDING",
                CallbackCleanupCategory.SUCCESS: "COMPLETE",
                CallbackCleanupCategory.SANITIZED_FAILURE: "FAILED",
            }[self._cleanup]

    def _cleanup_transport(self) -> None:
        with self._lock:
            if self._cleanup in {CallbackCleanupCategory.SUCCESS,
                                 CallbackCleanupCategory.SANITIZED_FAILURE}:
                return
            self._cleanup = CallbackCleanupCategory.PENDING
            if self._starting or self._cleanup_running:
                return
            server = self._server
            if server is None:
                self._cleanup = CallbackCleanupCategory.SUCCESS
                return
            self._cleanup_running = True
        joined = False
        try:
            server.close()
            joined = server.join(MAX_JOIN_SECONDS)
        except Exception:
            pass
        with self._lock:
            self._cleanup_running = False
            self._cleanup = (CallbackCleanupCategory.SUCCESS if joined
                             else CallbackCleanupCategory.SANITIZED_FAILURE)


class _OneRequestHTTPServer(http.server.HTTPServer):
    allow_reuse_address = False

    def __init__(self, session: LoopbackCallbackSession) -> None:
        self.session = session
        self.result: LoopbackCallbackResult | None = None
        self._state_lock = threading.RLock()
        self._closing = False
        self._request_seen = False
        self._connections: dict[socket.socket, str] = {}
        self._listening_state = "OPEN"
        self._expires_at: float | None = None
        self._monotonic_clock = time.monotonic
        super().__init__((LOOPBACK_ADDRESS, LOOPBACK_PORT), _CallbackRequestHandler)
        # A readiness/close race must never strand the worker inside accept().
        try:
            self.socket.setblocking(False)
        except Exception:
            self.server_close()
            raise

    def bind_deadline(self, expires_at: float, *,
                      monotonic_clock: Callable[[], float]) -> None:
        with self._state_lock:
            if self._expires_at is not None and self._monotonic_clock is not monotonic_clock:
                raise ValueError("CALLBACK_DEADLINE_CLOCK_CHANGED")
            self._monotonic_clock = monotonic_clock
            self._expires_at = (expires_at if self._expires_at is None
                                else min(self._expires_at, expires_at))

    def read_allowance(self) -> float:
        with self._state_lock:
            if self._closing:
                raise OSError("CALLBACK_TRANSPORT_CLOSED")
            remaining = (0.1 if self._expires_at is None
                         else self._expires_at - self._monotonic_clock())
        if remaining <= 0:
            raise TimeoutError("CALLBACK_DEADLINE_EXPIRED")
        return min(0.1, remaining)

    def expired(self) -> bool:
        with self._state_lock:
            return self._expires_at is not None and self._monotonic_clock() >= self._expires_at

    def get_request(self):
        connection, address = super().get_request()
        with self._state_lock:
            self._connections[connection] = "OPEN"
            self._request_seen = True
            closing = self._closing
        if closing:
            self.shutdown_request(connection)
            raise OSError("CALLBACK_TRANSPORT_CLOSED")
        return connection, address

    def shutdown_request(self, request) -> None:
        with self._state_lock:
            if self._connections.get(request) != "OPEN":
                return
            self._connections[request] = "CLOSING"
        failed = False
        try:
            request.shutdown(socket.SHUT_RDWR)
        except OSError:
            # Peer disconnect/already-shut direction is harmless if close and
            # actual worker termination are subsequently confirmed.
            pass
        except Exception:
            failed = True
        try:
            request.close()
            failed = failed or request.fileno() != -1
        except Exception:
            failed = True
        with self._state_lock:
            if failed:
                self._connections[request] = "FAILED"
            else:
                del self._connections[request]

    def server_close(self) -> None:
        with self._state_lock:
            self._closing = True
            connections = tuple(self._connections)
            close_listener = self._listening_state == "OPEN"
            if close_listener:
                self._listening_state = "CLOSING"
        if close_listener:
            failed = False
            try:
                super().server_close()
                failed = self.socket.fileno() != -1
            except Exception:
                failed = True
            with self._state_lock:
                self._listening_state = "FAILED" if failed else "COMPLETE"
        for connection in connections:
            self.shutdown_request(connection)

    def resources_released(self) -> bool:
        with self._state_lock:
            return self._listening_state == "COMPLETE" and not self._connections

    def publish_result(self, result: LoopbackCallbackResult) -> LoopbackCallbackResult:
        with self._state_lock:
            accepted = not self._closing and not self.expired() and self.result is None
            if accepted:
                self.result = result
        if not accepted:
            result.close()
            return LoopbackCallbackResult(CallbackCategory.TRANSPORT_FAILURE)
        return result

    def invalidate_pending(self) -> None:
        # Short state/token cleanup only: terminal service callbacks may call
        # this while publishing cancellation. The worker closes its sockets.
        with self._state_lock:
            self._closing = True
            result, self.result = self.result, None
        self.session.close()
        if result is not None:
            result.close()

    def take_result(self) -> LoopbackCallbackResult | None:
        with self._state_lock:
            result, self.result = self.result, None
        return result

    def handle_error(self, request: object, client_address: object) -> None:
        return None


class _DeadlineSocketReader(io.RawIOBase):
    """Check the absolute attempt bound at every socket read, even on trickles."""

    def __init__(self, connection: socket.socket, server: _OneRequestHTTPServer) -> None:
        self._connection = connection
        self._server = server

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        while True:
            allowance = self._server.read_allowance()
            self._connection.settimeout(allowance)
            try:
                return self._connection.recv_into(buffer)
            except socket.timeout:
                # This is a short polling interval, not an inactivity lifetime.
                # Recheck the same absolute deadline without extending it.
                continue


class _CallbackRequestHandler(http.server.BaseHTTPRequestHandler):
    server: _OneRequestHTTPServer

    def setup(self) -> None:
        super().setup()
        self.rfile.close()
        self.rfile = io.BufferedReader(_DeadlineSocketReader(self.connection, self.server))

    def do_GET(self) -> None:
        self._handle_terminal_request()

    def do_POST(self) -> None:
        self._handle_terminal_request()

    def do_PUT(self) -> None:
        self._handle_terminal_request()

    def do_DELETE(self) -> None:
        self._handle_terminal_request()

    def __getattr__(self, name: str) -> object:
        if name.startswith("do_"):
            return self._handle_terminal_request
        raise AttributeError(name)

    def _handle_terminal_request(self) -> None:
        raw_lengths = self.headers.get_all("Content-Length", failobj=[])
        content_length = _safe_content_length(raw_lengths)
        result = self.server.session.handle(
            LoopbackCallbackRequest(
                method=self.command,
                target=self.path,
                host_headers=tuple(self.headers.get_all("Host", failobj=[])),
                content_length=content_length,
            )
        )
        result = self.server.publish_result(result)
        status, body = result.fixed_http_response()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for name, value in result.fixed_http_headers():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        return None

    def log_error(self, format: str, *args: object) -> None:
        return None

    def log_message(self, format: str, *args: object) -> None:
        return None

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        result = self.server.result
        if result is None:
            result = self.server.session.handle(
                LoopbackCallbackRequest(method="", target="")
            )
            result = self.server.publish_result(result)
        _ignored_status, body = result.fixed_http_response()
        self.send_response_only(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for name, value in result.fixed_http_headers():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if getattr(self, "command", None) != "HEAD":
            self.wfile.write(body)


class _StandardLibraryServer:
    __slots__ = ("_closed", "_finished", "_server", "_thread", "_lock")

    def __init__(self, session: LoopbackCallbackSession) -> None:
        self._server = _OneRequestHTTPServer(session)
        self._server.timeout = 0.1
        self._closed = threading.Event()
        self._finished = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def bind_deadline(self, expires_at: float, *,
                      monotonic_clock: Callable[[], float]) -> None:
        self._server.bind_deadline(expires_at, monotonic_clock=monotonic_clock)

    def start(self) -> None:
        with self._lock:
            if self._thread is not None or self._closed.is_set():
                raise RuntimeError("CALLBACK_SERVER_ALREADY_STARTED")
            self._thread = threading.Thread(
                target=self._serve_one, name="kronos-loopback-callback", daemon=True,
            )
            self._thread.start()

    def receive_once(self, timeout_seconds: float) -> LoopbackCallbackResult:
        if self._thread is None:
            raise RuntimeError("CALLBACK_SERVER_NOT_STARTED")
        if not self._finished.wait(timeout_seconds):
            raise TimeoutError
        result = self._server.take_result()
        if self._closed.is_set() or self._server.expired():
            if result is not None:
                result.close()
            raise TimeoutError
        if result is None:
            raise RuntimeError("CALLBACK_SERVER_TERMINATED")
        return result

    def invalidate_pending(self) -> None:
        with self._lock:
            self._closed.set()
        self._server.invalidate_pending()

    def close(self) -> None:
        self.invalidate_pending()
        self._server.server_close()

    def join(self, timeout_seconds: float) -> bool:
        thread = self._thread
        if thread is not None:
            thread.join(timeout_seconds)
        return (thread is None or not thread.is_alive()) and self._server.resources_released()

    def _serve_one(self) -> None:
        try:
            # HTTPServer.handle_request derives its select timeout from the
            # socket timeout, which is zero for nonblocking accept. Own the
            # bounded wait explicitly so an idle listener never busy-polls.
            with selectors.DefaultSelector() as selector:
                selector.register(self._server, selectors.EVENT_READ)
                while (not self._closed.is_set() and not self._server.expired()
                       and not self._server._request_seen):
                    if selector.select(self._server.read_allowance()):
                        self._server._handle_request_noblock()
        except Exception:
            pass
        finally:
            self._server.server_close()
            self._finished.set()


def create_standard_library_server(
    session: LoopbackCallbackSession,
) -> _TerminalServer:
    """Construct the exact production loopback address and validation boundary."""

    return _StandardLibraryServer(session)


def _classify_first_request(
    request: LoopbackCallbackRequest,
    *,
    return_url: str,
) -> LoopbackCallbackResult:
    if request.method != "GET" or request.content_length != 0:
        return LoopbackCallbackResult(CallbackCategory.INVALID_METHOD)
    parsed_target = urlsplit(request.target)
    if (
        parsed_target.scheme
        or parsed_target.netloc
        or parsed_target.path != LOOPBACK_PATH
        or parsed_target.fragment
    ):
        return LoopbackCallbackResult(CallbackCategory.INVALID_PATH)
    if not _valid_host_headers(request.host_headers):
        return LoopbackCallbackResult(CallbackCategory.INVALID_HOST)

    query = parse_qs(
        parsed_target.query,
        keep_blank_values=True,
        strict_parsing=False,
    )
    if query.get("status") == ["error"] or any(
        field in query for field in _PROVIDER_ERROR_FIELDS
    ):
        return LoopbackCallbackResult(CallbackCategory.PROVIDER_REJECTED)
    tokens = query.get("request_token", [])
    if len(tokens) > 1:
        return LoopbackCallbackResult(CallbackCategory.TOKEN_MULTIPLE)
    if len(tokens) != 1 or not tokens[0]:
        return LoopbackCallbackResult(CallbackCategory.TOKEN_MISSING)
    return LoopbackCallbackResult(
        CallbackCategory.ACCEPTED,
        _OneUseRequestToken(tokens[0]),
        return_url=return_url,
    )


def _validated_return_url(value: str) -> str:
    if type(value) is not str:
        raise ValueError("CALLBACK_RETURN_DESTINATION_INVALID")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("CALLBACK_RETURN_DESTINATION_INVALID") from None
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.hostname != LOOPBACK_ADDRESS
        or port is None
        or not 1 <= port <= 65535
        or parsed.netloc != f"{LOOPBACK_ADDRESS}:{port}"
        or parsed.path != "/swing/opportunities"
        or parsed.query
        or parsed.fragment
        or value != f"http://{LOOPBACK_ADDRESS}:{port}/swing/opportunities"
    ):
        raise ValueError("CALLBACK_RETURN_DESTINATION_INVALID")
    return value


def _valid_host_headers(host_headers: Sequence[str]) -> bool:
    if tuple(host_headers) != (LOOPBACK_HOST_HEADER,):
        return False
    value = host_headers[0]
    try:
        parsed = urlsplit("//" + value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.username is None
        and parsed.password is None
        and parsed.hostname == LOOPBACK_ADDRESS
        and port == LOOPBACK_PORT
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
        and value == LOOPBACK_HOST_HEADER
    )


def _safe_content_length(raw_lengths: Sequence[str]) -> int:
    if not raw_lengths:
        return 0
    if len(raw_lengths) != 1:
        return 1
    try:
        value = int(raw_lengths[0])
    except (TypeError, ValueError):
        return 1
    return value if value >= 0 else 1


__all__ = [
    "CallbackCleanupCategory",
    "LOOPBACK_ADDRESS",
    "LOOPBACK_HOST_HEADER",
    "LOOPBACK_PATH",
    "LOOPBACK_PORT",
    "DEFAULT_CALLBACK_RETURN_URL",
    "LoopbackAuthenticationCallbackListener",
    "LoopbackCallbackRequest",
    "LoopbackCallbackResult",
    "LoopbackCallbackSession",
    "create_standard_library_server",
]
