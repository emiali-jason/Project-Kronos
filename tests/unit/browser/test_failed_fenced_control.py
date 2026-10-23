"""Exact R3 wire boundary; synthetic keys/claims confer no recovery authority."""
from __future__ import annotations

import io
import os
from threading import BoundedSemaphore, Condition, Event, Lock, Thread

import pytest

from kronos.browser.failed_fenced_control import (
    REQUEST_LINE, ControlFramingError, read_claim, read_budgeted_line, require_exact_claim,
    write_ack, write_denial,
)
from kronos.browser.restart_control import BrowserBackendRestartControl


class ClockBudget:
    def __init__(self, remaining=9.0):
        self.remaining = remaining
        self.deadlines = []
        self.expired = False

    def check(self, deadline_ns=None):
        self.deadlines.append(deadline_ns)
        if self.expired:
            raise TimeoutError("synthetic deadline expired")

    def remaining_seconds(self, deadline_ns=None):
        self.check(deadline_ns)
        return self.remaining


class Connection:
    def __init__(self):
        self.timeout = None
        self.observed = []

    def settimeout(self, value):
        self.timeout = value
        self.observed.append(value)

    def gettimeout(self):
        return self.timeout

    def setblocking(self, value):
        self.timeout = None if value else 0.0


@pytest.fixture
def control(tmp_path):
    # This is an isolated synthetic process-control checkpoint, never production.
    value = BrowserBackendRestartControl(tmp_path / "fixture.control", os.getpid(), "a" * 64)
    value.path.write_text(value._serialized(), encoding="ascii")
    value.path.chmod(0o600)
    value.path.parent.chmod(0o700)
    return value


def head(control, body=b'{"fixture":"untrusted"}', **changes):
    values = {
        "Host": "127.0.0.1:12345", "X-Kronos-Backend-Pid": str(os.getpid()),
        "X-Kronos-Restart-Token": control._token, "Content-Type": "application/json",
        "Content-Length": str(len(body)), "Connection": "close",
    }
    values.update(changes)
    return b"".join(f"{key}: {value}\r\n".encode("ascii") for key, value in values.items()) + b"\r\n" + body


def read(control, wire, *, line=REQUEST_LINE, budget=None):
    return read_claim(io.BufferedReader(io.BytesIO(wire)), line,
        connection=Connection(), control=control, endpoint_port=12345,
        budget=budget or ClockBudget())


def test_exact_request_returns_only_still_untrusted_claim(control):
    body = b'{"fixture":"untrusted"}'
    assert read(control, head(control, body)) == body


def test_header_names_case_insensitive_and_no_token_retention(control):
    wire = head(control).replace(b"Content-Type:", b"cOnTeNt-TyPe:")
    assert read(control, wire) == b'{"fixture":"untrusted"}'


@pytest.mark.parametrize("changes", [
    {"Host": "localhost:12345"}, {"Host": "127.0.0.1:8947"},
    {"X-Kronos-Backend-Pid": "0002"}, {"X-Kronos-Restart-Token": "b" * 64},
    {"Content-Type": "application/json; charset=utf-8"}, {"Connection": "keep-alive"},
    {"Content-Length": "0"}, {"Content-Length": "01"},
    {"Content-Length": "+1"}, {"Content-Length": "1048577"},
    {"Transfer-Encoding": "chunked"}, {"User-Agent": "unapproved"},
])
def test_mismatched_or_expanded_headers_deny(control, changes):
    with pytest.raises(ControlFramingError):
        read(control, head(control, **changes))


@pytest.mark.parametrize("prefix", [
    b"HOST: 127.0.0.1:12345\r\n", b"X-Kronos-Restart-Token: " + b"a" * 64 + b"\r\n",
    b" Content-Type: application/json\r\n", b"Host:127.0.0.1:12345\r\n",
    b"Unknown: " + b"x" * 8192 + b"\r\n",
])
def test_duplicate_folded_or_excessive_headers_deny_without_secret_error(control, prefix):
    with pytest.raises(ControlFramingError) as error:
        read(control, prefix + head(control))
    assert control._token not in str(error.value)


@pytest.mark.parametrize("line", [
    b"POST /control/failed-fenced-recovery/v1?retry=1 HTTP/1.0\r\n",
    b"POST /control/failed-fenced-recovery/v1 HTTP/1.1\r\n",
    b"GET /control/failed-fenced-recovery/v1 HTTP/1.0\r\n",
    b"POST /control/shutdown HTTP/1.0\r\n", REQUEST_LINE.replace(b"\r\n", b"\n"),
])
def test_other_protocol_or_route_never_selects_recovery(control, line):
    with pytest.raises(ControlFramingError):
        read(control, head(control), line=line)


def test_truncated_claim_rejected(control):
    with pytest.raises(ControlFramingError):
        read(control, head(control)[:-1])


def test_pipelined_or_extra_body_rejected(control):
    with pytest.raises(ControlFramingError, match="EXTRA_BYTES"):
        read(control, head(control) + b"GET / HTTP/1.0\r\n\r\n")


def test_foreign_or_removed_live_control_rejected(control):
    control.path.unlink()
    with pytest.raises(ControlFramingError, match="BINDING_INVALID"):
        read(control, head(control))


@pytest.mark.parametrize("remaining", [0, -1, 15.00001])
def test_invalid_remaining_budget_rejected(control, remaining):
    with pytest.raises(ControlFramingError, match="BUDGET_INVALID"):
        read(control, head(control), budget=ClockBudget(remaining))


def test_expired_shared_budget_rejected_before_read(control):
    budget = ClockBudget()
    budget.expired = True
    with pytest.raises(TimeoutError):
        read(control, head(control), budget=budget)


def test_wire_claim_must_equal_exclusive_retained_claim():
    require_exact_claim(b"original", b"original")
    with pytest.raises(ControlFramingError):
        require_exact_claim(b"changed", b"original")


class PartialWriter(io.BytesIO):
    def write(self, data):
        return super().write(bytes(data[:7]))


def test_ack_exact_transport_and_partial_writes_share_work_deadline():
    out, budget = PartialWriter(), ClockBudget()
    write_ack(out, b"{}", connection=Connection(), budget=budget, work_deadline_ns=123)
    assert out.getvalue() == (b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n"
        b"Content-Length: 2\r\nConnection: close\r\n\r\n{}")
    assert set(budget.deadlines) == {123}
    assert b"Date:" not in out.getvalue() and b"Server:" not in out.getvalue()


def test_ack_expiry_never_writes_success():
    out, budget = io.BytesIO(), ClockBudget()
    budget.expired = True
    with pytest.raises(TimeoutError):
        write_ack(out, b"{}", connection=Connection(), budget=budget, work_deadline_ns=123)
    assert out.getvalue() == b""


def test_empty_pre_release_denial_has_only_permitted_headers():
    out = io.BytesIO()
    write_denial(out, connection=Connection(), budget=ClockBudget())
    assert out.getvalue() == b"HTTP/1.0 409 Conflict\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


def test_private_control_custody_and_once_only_removal(control):
    original = control._serialized().encode("ascii")
    assert control.private_bytes_for_recovery() == original
    control.remove_for_recovery()
    assert not control.path.exists()
    with pytest.raises(ValueError, match="FAILED_FENCED_CONTROL_CUSTODY_INVALID"):
        control.remove_for_recovery()


@pytest.mark.parametrize("mutation", ["file_mode", "directory_mode", "hard_link",
    "symlink", "changed_bytes", "foreign_pid"])
def test_custody_rejects_insecure_or_changed_control_without_repair(control, mutation):
    original = control._serialized().encode("ascii")
    if mutation == "file_mode":
        control.path.chmod(0o644)
    elif mutation == "directory_mode":
        control.path.parent.chmod(0o755)
    elif mutation == "hard_link":
        os.link(control.path, control.path.with_name("alias"))
    elif mutation == "symlink":
        saved = control.path.with_name("saved")
        control.path.rename(saved)
        control.path.symlink_to(saved)
    elif mutation == "changed_bytes":
        control.path.write_bytes(original + b"unexpected")
    else:
        control.process_id += 1
    with pytest.raises((OSError, ValueError)):
        control.remove_for_recovery()
    assert control.path.exists()


def test_ordinary_v1_control_removal_contract_preserved(control):
    control.path.unlink()
    # Ordinary control cleanup has its pre-existing idempotent semantics.
    control.remove()
    assert not control.path.exists()


def test_recovery_route_never_enters_ordinary_http_parser():
    from types import SimpleNamespace
    from kronos.browser.server import _BrowserHandler
    received = []
    handler = object.__new__(_BrowserHandler)
    handler.raw_requestline = REQUEST_LINE
    handler.server = SimpleNamespace(_failed_fenced_binding=SimpleNamespace(
        handle=lambda actual: received.append(actual)))
    assert handler.parse_request() is False
    assert received == [handler]
    assert handler.close_connection is True
    assert handler.request_version == "HTTP/1.0"


def test_unprepared_recovery_route_confers_no_authority():
    from types import SimpleNamespace
    from kronos.browser.server import _BrowserHandler
    handler = object.__new__(_BrowserHandler)
    handler.raw_requestline = REQUEST_LINE
    handler.server = SimpleNamespace(_failed_fenced_binding=None)
    assert handler.parse_request() is False
    assert handler.close_connection is True


def test_request_diagnostics_complete_once_before_seal():
    from kronos.browser.server import KronosBrowserServer
    server = object.__new__(KronosBrowserServer)
    request = object()
    finished = []
    class Trace:
        def finish(self):
            finished.append("pre-seal")
    server._request_capacity_lock = Lock()
    server._request_slots = BoundedSemaphore(1)
    server._request_slots.acquire()
    server._active_request_count = 1
    server._diagnostic_requests = {id(request): Trace()}
    server._failed_fenced_detached_requests = {}
    server._detach_failed_fenced_request(request)
    assert finished == ["pre-seal"]
    assert server._active_request_count == 0
    server._finish_request_owner(request)
    server._finish_request_owner(request)
    assert finished == ["pre-seal"]
    assert server._active_request_count == 0
    with pytest.raises(ValueError, match="ALREADY_DETACHED"):
        server._detach_failed_fenced_request(request)


def test_write_free_server_close_cannot_reenter_product_finalizers():
    from kronos.browser.server import KronosBrowserServer
    server = object.__new__(KronosBrowserServer)
    events = []
    class Listener:
        def close(self):
            events.append("descriptor-close")
    server.socket = Listener()
    server._failed_fenced_write_free = True
    server._close_domain_owners = lambda: pytest.fail("ordinary finalizer replay")
    server.server_close()
    assert events == ["descriptor-close"]


def transport_server():
    from kronos.browser.server import KronosBrowserServer
    server = object.__new__(KronosBrowserServer)
    server._request_capacity_lock = Lock()
    server._request_capacity_change = Condition(server._request_capacity_lock)
    server._failed_fenced_transport_frozen = False
    server._failed_fenced_dispatch_owners = 0
    server._failed_fenced_diagnostic_owners = 0
    server._active_request_count = 0
    return server


def test_transport_freeze_waits_for_actual_dispatch_return_and_closes_late_descriptor():
    server = transport_server()
    entered, finish, frozen = Event(), Event(), Event()
    opened = []
    def dispatch(request, address):
        opened.append(request)
        entered.set()
        assert finish.wait(2)
    server._process_request_open = dispatch
    first = object()
    worker = Thread(target=lambda: server.process_request(first, ("127.0.0.1", 1)))
    worker.start()
    assert entered.wait(1)
    freezer = Thread(target=lambda: (server._freeze_failed_fenced_transport(ClockBudget(), 123), frozen.set()))
    freezer.start()
    try:
        with server._request_capacity_lock:
            assert server._failed_fenced_dispatch_owners == 1
        assert not frozen.wait(0.03)
        closed = []
        class Late:
            def close(self):
                closed.append("closed-without-dispatch")
        server.process_request(Late(), ("127.0.0.1", 2))
        assert closed == ["closed-without-dispatch"] and opened == [first]
    finally:
        finish.set()
        worker.join(2)
        freezer.join(2)
    assert frozen.is_set() and not worker.is_alive() and not freezer.is_alive()


def test_transport_freeze_does_not_hide_final_diagnostic_writer():
    server = transport_server()
    server._request_slots = BoundedSemaphore(1)
    server._request_slots.acquire()
    entered, finish, frozen = Event(), Event(), Event()
    class Trace:
        def finish(self):
            entered.set()
            assert finish.wait(2)
    request = object()
    server._diagnostic_requests = {id(request): Trace()}
    server._failed_fenced_detached_requests = {}
    server._active_request_count = 1
    writer = Thread(target=lambda: server._finish_request_owner(request))
    writer.start()
    assert entered.wait(1)
    assert server._active_request_count == 0
    assert server._failed_fenced_diagnostic_owners == 1
    freezer = Thread(target=lambda: (server._freeze_failed_fenced_transport(ClockBudget(), 123), frozen.set()))
    freezer.start()
    try:
        assert not frozen.wait(0.03)
    finally:
        finish.set()
        writer.join(2)
        freezer.join(2)
    assert frozen.is_set() and server._failed_fenced_diagnostic_owners == 0


def test_pending_claim_budget_is_applied_before_first_http_line(monkeypatch):
    from types import SimpleNamespace
    from http.server import BaseHTTPRequestHandler
    from kronos.browser.failed_fenced_control import RecoveryBrowserBinding
    from kronos.browser.server import _BrowserHandler
    events = []
    binding = object.__new__(RecoveryBrowserBinding)
    binding.transaction = SimpleNamespace(
        expected_claim_raw=lambda: events.append("verify-retained-claim"), budget=ClockBudget())
    handler = object.__new__(_BrowserHandler)
    handler.connection = Connection()
    handler.server = SimpleNamespace(_failed_fenced_binding=binding)
    handler.rfile = io.BytesIO(b"partial request line")
    monkeypatch.setattr(BaseHTTPRequestHandler, "setup", lambda actual: events.append("native-stream-setup"))
    handler.setup()
    assert events == ["native-stream-setup", "verify-retained-claim"]
    assert handler.connection.gettimeout() == 9.0


class TrickleBudget:
    """Deterministic absolute-time input for framing tests, not authority."""
    def __init__(self):
        self.elapsed = 0
        self.deadline = 3

    def check(self, deadline_ns=None):
        if self.elapsed >= self.deadline:
            raise TimeoutError("existing absolute deadline expired")

    def remaining_seconds(self, deadline_ns=None):
        self.check(deadline_ns)
        return self.deadline - self.elapsed


class TrickleRaw(io.RawIOBase):
    """One byte per underlying read; time progresses only in actual reads."""
    def __init__(self, payload, budget, *, charge_from=0):
        self.payload = payload
        self.budget = budget
        self.offset = 0
        self.charge_from = charge_from
        self.charged_reads = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.offset == len(self.payload):
            return 0
        if self.offset >= self.charge_from:
            self.budget.elapsed += 1
            self.charged_reads += 1
        buffer[0] = self.payload[self.offset]
        self.offset += 1
        return 1


@pytest.mark.parametrize("phase", ["request-line", "headers", "body"])
def test_trickled_receives_cannot_extend_absolute_budget(control, phase):
    budget, connection = TrickleBudget(), Connection()
    wire = REQUEST_LINE if phase == "request-line" else head(control)
    charge_from = wire.index(b"\r\n\r\n") + 4 if phase == "body" else 0
    raw = TrickleRaw(wire, budget, charge_from=charge_from)
    stream = io.BufferedReader(raw)
    with pytest.raises(TimeoutError, match="absolute deadline"):
        if phase == "request-line":
            read_budgeted_line(stream, 65537, connection=connection, budget=budget)
        else:
            read_claim(stream, REQUEST_LINE, connection=connection, control=control,
                       endpoint_port=12345, budget=budget)
    # A buffered readline/read would consume the rest using a repeated stale
    # socket timeout. Exactly three raw receives are allowed by this deadline.
    assert raw.charged_reads == 3
    assert raw.offset == charge_from + 3
    assert connection.observed[-3:] == [3, 2, 1]
    assert budget.deadline == 3


def test_budgeted_line_preserves_following_bytes_and_original_limit():
    stream = io.BufferedReader(io.BytesIO(REQUEST_LINE + b"body"))
    assert read_budgeted_line(stream, len(REQUEST_LINE), connection=Connection(),
                              budget=ClockBudget()) == REQUEST_LINE
    assert stream.read() == b"body"
    stream = io.BufferedReader(io.BytesIO(REQUEST_LINE))
    assert read_budgeted_line(stream, 4, connection=Connection(), budget=ClockBudget()) == b"POST"
    assert stream.read() == REQUEST_LINE[4:]


def test_short_single_read_body_fragments_preserve_exact_claim(control):
    class Fragmented(io.BytesIO):
        def read1(self, size=-1):
            return super().read(min(size, 3))
        def read(self, *args):
            pytest.fail("unbounded buffered body read")
        def readline(self, *args):
            pytest.fail("unbounded buffered line read")
        def peek(self, _size):
            at = self.tell()
            remaining = self.getvalue()[at:]
            return remaining
    body = b'{"fixture":"single-receive-fragments"}'
    assert read_claim(Fragmented(head(control, body)), REQUEST_LINE,
        connection=Connection(), control=control, endpoint_port=12345,
        budget=ClockBudget()) == body


def test_handler_first_line_uses_incremental_remaining_budget(monkeypatch):
    from types import SimpleNamespace
    from http.server import BaseHTTPRequestHandler
    from kronos.browser.failed_fenced_control import RecoveryBrowserBinding
    from kronos.browser.server import _BrowserHandler
    budget = TrickleBudget()
    raw = TrickleRaw(REQUEST_LINE, budget)
    binding = object.__new__(RecoveryBrowserBinding)
    binding.transaction = SimpleNamespace(expected_claim_raw=lambda: None, budget=budget)
    handler = object.__new__(_BrowserHandler)
    handler.connection = Connection()
    handler.server = SimpleNamespace(_failed_fenced_binding=binding)
    handler.rfile = io.BufferedReader(raw)
    monkeypatch.setattr(BaseHTTPRequestHandler, "setup", lambda actual: None)
    handler.setup()
    with pytest.raises(TimeoutError):
        handler.rfile.readline(65537)
    assert raw.charged_reads == 3
    assert handler.connection.observed[-3:] == [3, 2, 1]


def test_ordinary_unenrolled_handler_retains_original_reader(monkeypatch):
    from types import SimpleNamespace
    from http.server import BaseHTTPRequestHandler
    from kronos.browser.server import _BrowserHandler
    handler = object.__new__(_BrowserHandler)
    handler.connection = Connection()
    handler.server = SimpleNamespace(_failed_fenced_binding=None)
    handler.rfile = io.BytesIO(b"ordinary first line\nsecond")
    monkeypatch.setattr(BaseHTTPRequestHandler, "setup", lambda actual: None)
    handler.setup()
    assert handler.rfile.readline() == b"ordinary first line\n"
    assert handler.rfile.read() == b"second"
    assert handler.connection.observed == []


def test_enrolled_factory_is_acquired_before_first_control_read(monkeypatch):
    from types import SimpleNamespace
    from threading import RLock
    from http.server import BaseHTTPRequestHandler
    from kronos.browser.server import _BrowserHandler
    from kronos.common import failed_fenced_startup
    events = []
    binding = SimpleNamespace(prepare_transport=lambda connection: events.append('budget'),
        transaction=SimpleNamespace(budget=None))
    server = SimpleNamespace(_failed_fenced_binding=None,
        _failed_fenced_ledger=object(), _failed_fenced_binding_lock=RLock())
    def factory(actual):
        assert actual is server and events == []
        events.append('factory'); return binding
    def attach(actual):
        assert actual is binding and events == ['factory']
        events.append('attach'); server._failed_fenced_binding = actual
    server.bind_failed_fenced_recovery = attach
    monkeypatch.setattr(failed_fenced_startup, 'prepare_recovery_binding', factory)
    monkeypatch.setattr(BaseHTTPRequestHandler, 'setup', lambda handler: None)
    handler = object.__new__(_BrowserHandler)
    handler.server, handler.connection = server, Connection()
    class Unread(io.BytesIO):
        def readline(self, *args, **kwargs):
            pytest.fail('Factory setup consumed request input')
    handler.rfile = Unread(REQUEST_LINE)
    handler.setup()
    assert events == ['factory', 'attach', 'budget']
    assert server._failed_fenced_binding is binding


def test_present_invalid_preparation_denies_before_any_request_read(monkeypatch):
    from types import SimpleNamespace
    from threading import RLock
    from http.server import BaseHTTPRequestHandler
    from kronos.browser.server import _BrowserHandler
    from kronos.common import failed_fenced_startup
    handler = object.__new__(_BrowserHandler)
    handler.server = SimpleNamespace(_failed_fenced_binding=None,
        _failed_fenced_ledger=object(), _failed_fenced_binding_lock=RLock())
    handler.rfile = io.BytesIO(REQUEST_LINE)
    monkeypatch.setattr(BaseHTTPRequestHandler, 'setup', lambda actual: None)
    def invalid(actual):
        raise ValueError('RECOVERY_PREPARATION_INVALID')
    monkeypatch.setattr(failed_fenced_startup, 'prepare_recovery_binding', invalid)
    with pytest.raises(ValueError, match='RECOVERY_PREPARATION_INVALID'):
        handler.setup()
    assert handler.rfile.tell() == 0 and handler.server._failed_fenced_binding is None


def test_frozen_close_error_cannot_escape_to_ordinary_traceback(capsys):
    server = transport_server()
    server._failed_fenced_transport_frozen = True
    server._process_request_open = lambda *args: pytest.fail("late request dispatched")
    class FailedDescriptor:
        def close(self):
            raise OSError("injected descriptor close failure")
    server.process_request(FailedDescriptor(), ("127.0.0.1", 1))
    assert server._failed_fenced_dispatch_owners == 0
    assert capsys.readouterr().err == ""
