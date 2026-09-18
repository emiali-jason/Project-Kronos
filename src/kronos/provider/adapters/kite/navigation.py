"""Strict Kite login navigation with owned launch-dispatch helper custody."""

from __future__ import annotations

import re
import multiprocessing
import selectors
import socket
import threading
import webbrowser
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

from kronos.provider.models.authentication import (
    BrowserOpenCategory,
    BrowserOpenRequest,
    BrowserOpenResult,
)


_KITE_LOGIN_HOST = "kite.zerodha.com"
_KITE_LOGIN_PATH = "/connect/login"
_API_KEY_PATTERN = re.compile(r"[A-Za-z0-9]{1,64}\Z")

BrowserOpener = Callable[[str], bool]


class KiteLoginNavigator:
    """Dispatch one official login URL without fallback or authentication authority."""

    __slots__ = ("_opener", "_deadline", "_owner", "_lock")

    def __init__(self, *, opener: BrowserOpener | None = None) -> None:
        if opener is not None and not callable(opener):
            raise TypeError("BROWSER_OPENER_INVALID")
        self._opener = opener
        self._deadline = None
        self._owner = None
        self._lock = threading.Lock()

    def bind_attempt(self, deadline: object) -> None:
        with self._lock:
            if self._owner is not None and self._owner.local_cleanup_state != "COMPLETE":
                raise RuntimeError("BROWSER_HELPER_CLEANUP_PENDING")
            self._deadline = deadline

    def invalidate_pending(self) -> None:
        # State only: safe for the service terminalization callback.
        with self._lock:
            owner = self._owner
            if owner is not None:
                owner.cancelled.set()

    def open_official_login(self, request: BrowserOpenRequest) -> BrowserOpenResult:
        if not isinstance(request, BrowserOpenRequest):
            return BrowserOpenResult(BrowserOpenCategory.FAILED)
        login_url = request.official_login_url
        if not _approved_kite_login_url(login_url):
            return BrowserOpenResult(BrowserOpenCategory.FAILED)
        try:
            if self._opener is not None:
                # Explicit in-process injection is retained for existing callers.
                opened = self._opener(login_url)
            else:
                with self._lock:
                    if self._owner is not None and self._owner.local_cleanup_state != "COMPLETE":
                        raise RuntimeError("BROWSER_HELPER_CLEANUP_PENDING")
                    if self._deadline is None:
                        raise RuntimeError("BROWSER_HELPER_DEADLINE_REQUIRED")
                    owner = _BrowserLaunchHelper(self._deadline)
                    self._owner = owner
                opened = owner.launch(login_url)
        except Exception:
            return BrowserOpenResult(BrowserOpenCategory.FAILED)
        finally:
            del login_url
        return BrowserOpenResult(
            BrowserOpenCategory.OPENED
            if opened is True
            else BrowserOpenCategory.DECLINED
        )

    def __repr__(self) -> str:
        return "<KiteLoginNavigator redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_LOGIN_NAVIGATOR_SERIALIZATION_PROHIBITED")


_HELPER_STOP_GRACE_SECONDS = 0.25
_HELPER_POLL_SECONDS = 0.02


def _browser_socket_pair():
    """Return one private process channel owned by the launch helper."""

    return socket.socketpair()


def _close_browser_connection(connection):
    connection.close()


def _browser_launch_worker(sender, login_url: str) -> None:
    """Spawn receives launch material over its private channel, never argv/files."""
    try:
        opened = webbrowser.open_new_tab(login_url)
        sender.sendall(b"O" if opened is True else b"D")
    except BaseException:
        try:
            sender.sendall(b"F")
        except BaseException:
            pass
    finally:
        login_url = ""
        sender.close()


class _BrowserLaunchHelper:
    """Custody of exactly one launch-dispatch child, not of any browser."""

    def __init__(self, deadline) -> None:
        self.deadline = deadline
        self.cancelled = threading.Event()
        self.process = None
        self.receiver = None
        self.sender = None
        self.local_cleanup_state = "PENDING"
        self.exitcode = None
        self.start_attempted = False
        self.start_returned = False

    def _require(self) -> None:
        self.deadline.require()
        if self.cancelled.is_set():
            raise TimeoutError("BROWSER_LAUNCH_TERMINAL")

    def launch(self, login_url: str) -> bool:
        self.deadline.hold_resource("BROWSER_LAUNCH_HELPER", self)
        self.deadline.add_terminal_callback(self.cancelled.set)
        payload = b""
        received = False
        try:
            self._require()
            context = multiprocessing.get_context("spawn")
            self.receiver, self.sender = _browser_socket_pair()
            self.process = context.Process(
                target=_browser_launch_worker, args=(self.sender, login_url), daemon=True,
            )
            # start() is an OS boundary: no state lock is held, and custody is
            # retained if it has not returned when the deadline terminalizes.
            self._require()
            self.start_attempted = True
            self.process.start()
            self.start_returned = True
            login_url = ""
            self.sender.close()
            self.receiver.setblocking(False)
            with selectors.DefaultSelector() as selector:
                selector.register(self.receiver, selectors.EVENT_READ)
                while len(payload) < 1:
                    self._require()
                    if not selector.select(min(_HELPER_POLL_SECONDS, self.deadline.remaining_seconds())):
                        continue
                    try:
                        chunk = self.receiver.recv(2 - len(payload))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        raise RuntimeError("BROWSER_HELPER_RESULT_INVALID")
                    payload += chunk
                if len(payload) != 1 or payload not in (b"O", b"D", b"F"):
                    raise RuntimeError("BROWSER_HELPER_RESULT_INVALID")
            self._require()
            received = True
        except BaseException:
            payload = b""
            raise
        finally:
            login_url = ""
            self._cleanup(force=not received or self.cancelled.is_set())
        try:
            self._require()
            if self.local_cleanup_state != "COMPLETE" or self.exitcode != 0 or payload == b"F":
                raise RuntimeError("BROWSER_LAUNCH_FAILED")
            with self.deadline.guard():
                self._require()
                return payload == b"O"
        finally:
            payload = b""

    def _cleanup(self, *, force: bool) -> None:
        if self.local_cleanup_state != "PENDING":
            return
        # An exception before start() supplies a child handle cannot prove
        # that the OS created no child. Retain this ambiguous startup fence.
        failed = self.start_attempted and not self.start_returned and self.process.pid is None
        process = self.process
        try:
            if process is not None:
                if process.pid is not None:
                    if not force:
                        process.join(_HELPER_STOP_GRACE_SECONDS)
                    if process.is_alive():
                        process.terminate()
                        process.join(_HELPER_STOP_GRACE_SECONDS)
                    if process.is_alive():
                        process.kill()
                        process.join(_HELPER_STOP_GRACE_SECONDS)
                    if process.is_alive():
                        raise RuntimeError("BROWSER_HELPER_STILL_RUNNING")
                    self.exitcode = process.exitcode
                process.close()
        except Exception:
            failed = True
        for connection in (self.receiver, self.sender):
            try:
                if connection is not None:
                    _close_browser_connection(connection)
            except Exception:
                failed = True
        self.local_cleanup_state = "FAILED" if failed else "COMPLETE"
        if not failed:
            self.deadline._resolve_pending_resource(self)

    def __repr__(self) -> str:
        return "<BrowserLaunchHelper redacted>"


def _approved_kite_login_url(candidate: object) -> bool:
    if not isinstance(candidate, str) or not candidate:
        return False
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
        query = parse_qs(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    except (TypeError, ValueError):
        return False
    if (
        parsed.scheme != "https"
        or parsed.hostname != _KITE_LOGIN_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.netloc not in {_KITE_LOGIN_HOST, f"{_KITE_LOGIN_HOST}:443"}
        or parsed.path != _KITE_LOGIN_PATH
        or parsed.fragment
        or set(query) != {"api_key", "v"}
        or query.get("v") != ["3"]
    ):
        return False
    api_keys = query.get("api_key", [])
    return (
        len(api_keys) == 1
        and _API_KEY_PATTERN.fullmatch(api_keys[0]) is not None
    )


__all__ = ["KiteLoginNavigator"]
