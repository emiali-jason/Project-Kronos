"""One-request standard-library loopback authentication callback transport."""

from __future__ import annotations

import http.server
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
MAX_JOIN_SECONDS = 1.0

_SUCCESS_HTML = b"<!doctype html><title>KRONOS</title>Callback accepted."
_REJECTION_HTML = b"<!doctype html><title>KRONOS</title>Callback rejected."
_EXPIRY_HTML = b"<!doctype html><title>KRONOS</title>Callback expired."
_PROVIDER_ERROR_FIELDS = frozenset(
    {"error", "error_type", "error_reason", "error_description", "message"}
)
_ResultT = TypeVar("_ResultT")


class CallbackCleanupCategory(StrEnum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    SUCCESS = "SUCCESS"
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
    __slots__ = ("_closed", "_token", "_used")

    def __init__(self, token: str) -> None:
        self._token: str | None = token
        self._used = False
        self._closed = False

    def consume_for_call(self, operation: Callable[[str], _ResultT]) -> _ResultT:
        if self._closed or self._used or self._token is None:
            raise RuntimeError("REQUEST_TOKEN_UNAVAILABLE")
        token = self._token
        self._used = True
        try:
            result = operation(token)
            if result is token or (isinstance(result, str) and result == token):
                raise RuntimeError("REQUEST_TOKEN_RETURNED")
            return result
        finally:
            self.close()

    def close(self) -> None:
        self._token = None
        self._closed = True

    def __repr__(self) -> str:
        return "<OneUseRequestToken redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("REQUEST_TOKEN_SERIALIZATION_PROHIBITED")


class LoopbackCallbackResult:
    """Sanitized terminal result with an optional one-use token carrier."""

    __slots__ = ("_category", "_closed", "_token")

    def __init__(
        self,
        category: CallbackCategory,
        token: _OneUseRequestToken | None = None,
    ) -> None:
        self._category = category
        self._token = token
        self._closed = False

    def category(self) -> CallbackCategory:
        return self._category

    def consume_request_token(
        self,
        operation: Callable[[_OneUseRequestToken], _ResultT],
    ) -> _ResultT:
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
            self._closed = True

    def close(self) -> None:
        token = self._token
        self._token = None
        self._closed = True
        if token is not None:
            token.close()

    def fixed_http_response(self) -> tuple[int, bytes]:
        if self._category is CallbackCategory.ACCEPTED:
            return 200, _SUCCESS_HTML
        if self._category is CallbackCategory.TIMED_OUT:
            return 408, _EXPIRY_HTML
        return 400, _REJECTION_HTML

    def __repr__(self) -> str:
        return f"<LoopbackCallbackResult {self._category.value}>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("CALLBACK_RESULT_SERIALIZATION_PROHIBITED")


class LoopbackCallbackSession:
    """Atomic first-request terminal callback classifier."""

    __slots__ = ("_lock", "_terminal")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._terminal = False

    def handle(self, request: LoopbackCallbackRequest) -> LoopbackCallbackResult:
        with self._lock:
            if self._terminal:
                return LoopbackCallbackResult(CallbackCategory.DUPLICATE)
            self._terminal = True
        try:
            return _classify_first_request(request)
        except Exception:
            return LoopbackCallbackResult(CallbackCategory.TRANSPORT_FAILURE)

    def timeout(self) -> LoopbackCallbackResult:
        with self._lock:
            if self._terminal:
                return LoopbackCallbackResult(CallbackCategory.DUPLICATE)
            self._terminal = True
        return LoopbackCallbackResult(CallbackCategory.TIMED_OUT)


class _TerminalServer(Protocol):
    def start(self) -> None: ...

    def receive_once(self, timeout_seconds: float) -> LoopbackCallbackResult: ...

    def close(self) -> None: ...

    def join(self, timeout_seconds: float) -> bool: ...


ServerFactory = Callable[[LoopbackCallbackSession], _TerminalServer]


class LoopbackAuthenticationCallbackListener:
    """Bounded listener whose server/socket boundary is explicitly injected."""

    __slots__ = (
        "_cleanup",
        "_clock",
        "_readiness",
        "_server",
        "_server_factory",
        "_session",
    )

    def __init__(
        self,
        *,
        server_factory: ServerFactory,
        clock: Callable[[], datetime],
    ) -> None:
        self._clock = clock
        self._session = LoopbackCallbackSession()
        self._server_factory = server_factory
        self._server: _TerminalServer | None = None
        self._readiness = CallbackReadiness.NOT_READY
        self._cleanup = CallbackCleanupCategory.NOT_ATTEMPTED

    def start(self) -> None:
        if self._readiness is not CallbackReadiness.NOT_READY:
            raise RuntimeError("CALLBACK_LISTENER_NOT_STARTABLE")
        try:
            server = self._server_factory(self._session)
            self._server = server
            server.start()
        except Exception:
            self._readiness = CallbackReadiness.CLOSED
            self._cleanup_transport()
            raise RuntimeError("CALLBACK_LISTENER_START_FAILED") from None
        self._readiness = CallbackReadiness.READY

    def readiness(self) -> CallbackReadiness:
        return self._readiness

    def receive_once(self, *, deadline: datetime) -> LoopbackCallbackResult:
        if self._readiness is not CallbackReadiness.READY:
            raise RuntimeError("CALLBACK_LISTENER_NOT_READY")
        try:
            remaining = (deadline - self._clock()).total_seconds()
            if remaining <= 0:
                return self._session.timeout()
            server = self._server
            if server is None:
                raise RuntimeError("CALLBACK_SERVER_UNAVAILABLE")
            return server.receive_once(remaining)
        except TimeoutError:
            return self._session.timeout()
        except Exception:
            return LoopbackCallbackResult(CallbackCategory.TRANSPORT_FAILURE)
        finally:
            self._readiness = CallbackReadiness.CLOSED
            self._cleanup_transport()

    def close(self) -> None:
        if self._readiness is CallbackReadiness.CLOSED:
            return
        self._readiness = CallbackReadiness.CLOSED
        self._cleanup_transport()

    def cleanup_category(self) -> CallbackCleanupCategory:
        return self._cleanup

    def _cleanup_transport(self) -> None:
        server = self._server
        if server is None:
            self._cleanup = CallbackCleanupCategory.SUCCESS
            return
        try:
            server.close()
            joined = server.join(MAX_JOIN_SECONDS)
        except Exception:
            self._cleanup = CallbackCleanupCategory.SANITIZED_FAILURE
            return
        self._cleanup = (
            CallbackCleanupCategory.SUCCESS
            if joined
            else CallbackCleanupCategory.SANITIZED_FAILURE
        )


class _OneRequestHTTPServer(http.server.HTTPServer):
    allow_reuse_address = False

    def __init__(self, session: LoopbackCallbackSession) -> None:
        self.session = session
        self.result: LoopbackCallbackResult | None = None
        super().__init__((LOOPBACK_ADDRESS, LOOPBACK_PORT), _CallbackRequestHandler)

    def handle_error(self, request: object, client_address: object) -> None:
        return None


class _CallbackRequestHandler(http.server.BaseHTTPRequestHandler):
    server: _OneRequestHTTPServer

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
        self.server.result = result
        status, body = result.fixed_http_response()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
            self.server.result = result
        _ignored_status, body = result.fixed_http_response()
        self.send_response_only(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if getattr(self, "command", None) != "HEAD":
            self.wfile.write(body)


class _StandardLibraryServer:
    __slots__ = ("_closed", "_finished", "_server", "_thread")

    def __init__(self, session: LoopbackCallbackSession) -> None:
        self._server = _OneRequestHTTPServer(session)
        self._server.timeout = 0.1
        self._closed = threading.Event()
        self._finished = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("CALLBACK_SERVER_ALREADY_STARTED")
        self._thread = threading.Thread(
            target=self._serve_one,
            name="kronos-loopback-callback",
            daemon=True,
        )
        self._thread.start()

    def receive_once(self, timeout_seconds: float) -> LoopbackCallbackResult:
        if self._thread is None:
            raise RuntimeError("CALLBACK_SERVER_NOT_STARTED")
        if not self._finished.wait(timeout_seconds):
            raise TimeoutError
        result = self._server.result
        if result is None:
            raise RuntimeError("CALLBACK_SERVER_TERMINATED")
        return result

    def close(self) -> None:
        self._closed.set()
        self._server.server_close()

    def join(self, timeout_seconds: float) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout_seconds)
        return not thread.is_alive()

    def _serve_one(self) -> None:
        try:
            while not self._closed.is_set() and self._server.result is None:
                self._server.handle_request()
        except Exception:
            return
        finally:
            self._finished.set()


def create_standard_library_server(
    session: LoopbackCallbackSession,
) -> _TerminalServer:
    """Construct the exact real loopback boundary; tests inject a fake factory."""

    return _StandardLibraryServer(session)


def _classify_first_request(
    request: LoopbackCallbackRequest,
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
    )


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
    "LoopbackAuthenticationCallbackListener",
    "LoopbackCallbackRequest",
    "LoopbackCallbackResult",
    "LoopbackCallbackSession",
    "create_standard_library_server",
]
