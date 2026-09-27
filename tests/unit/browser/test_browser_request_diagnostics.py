"""Real isolated HTTP sockets and controlled Browser request/owner barriers."""
from http.client import HTTPResponse, RemoteDisconnected
from threading import Barrier, Condition, Event, Lock, RLock, Thread
import json
import socket
import struct

import pytest

from kronos.browser import server as browser
from kronos.application.swing_visual_v3_live import NativeReviewIntakeWorkflow
from kronos.application.swing_trade_window import SwingTradeWindowWorkflow
from kronos.common.request_diagnostics import RequestDiagnostics, bind_trace
from tests.unit.browser.test_browser_server import _running_server, _request
from tests.unit.browser.test_sph_controls import running, request
from tests.unit.intraday.test_live_shadow_epochs import inventory


@pytest.fixture
def observed(monkeypatch):
    server, thread = _running_server()
    idle = Event()
    original = server._finish_request_owner
    def finish(sock):
        original(sock)
        if server.request_capacity_status()["active"] == 0:
            idle.set()
    monkeypatch.setattr(server, "_finish_request_owner", finish)
    yield server, idle
    server.shutdown()
    server.server_close()
    thread.join(5)
    assert not thread.is_alive()
    assert server.request_capacity_status()["active"] == 0


def events(server, identity):
    return [e for e in server.request_diagnostics.snapshot()["events"] if e["id"] == identity]


def metadata(root):
    return {str(p.relative_to(root)): (s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            for p in (root, *root.rglob("*")) for s in (p.stat(),)}


def test_success_stages_response_id_and_governed_get_preservation(running):
    server, g, provider, calls, root = running
    before = inventory(root)
    before_metadata = metadata(root)
    idle = Event()
    finish = server._finish_request_owner
    def completed(sock):
        finish(sock)
        idle.set()
    server._finish_request_owner = completed
    for _ in range(2):
        idle.clear()
        code, headers, body = _request(server, "GET", "/swing/opportunities?token=DO_NOT_RETAIN")
        assert code == 200 and idle.wait(5)
        rows = events(server, headers["X-Kronos-Request-ID"])
        assert rows[0]["event"] == "ADMITTED" and rows[0]["route"] == "UNKNOWN"
        assert rows[-1]["event"] == "CLEANUP" and rows[-1]["outcome"] == "RETURNED"
        stages = {e["stage"] for e in rows if e["event"] == "STAGE_END"}
        assert {"INTAKE_ENTER", "PUBLICATION", "RESTORATION_LOCK", "SELECTED_PRESENTATIONS",
                "V2_SELECTION", "RENDER_INPUTS", "RENDER", "CURRENTNESS", "INTAKE_EXIT",
                "RESPONSE_WRITE"} <= stages
        assert "DO_NOT_RETAIN" not in json.dumps(rows)
    code, body = request(server, "/runtime/request-diagnostics")
    assert code == 200 and json.loads(body)["schema"] == "KRONOS_REQUEST_DIAGNOSTICS_V1"
    assert inventory(root) == before
    assert metadata(root) == before_metadata
    assert calls == [] and provider.begin_count == 0


def test_completed_opportunity_is_retrievable_after_status_churn_and_gets_write_nothing(running):
    server, _, provider, calls, root = running
    before = inventory(root)
    before_metadata = metadata(root)
    code, headers, _ = _request(server, "GET", "/swing/opportunities")
    assert code == 200
    identity = headers["X-Kronos-Request-ID"]
    for _ in range(70):
        assert _request(server, "GET", "/status")[0] == 200
    code, _, body = _request(server, "GET", "/runtime/request-diagnostics")
    assert code == 200
    result = json.loads(body)
    assert result["evicted"] > 0
    assert not any(row["id"] == identity for row in result["events"])
    summary = result["completed_opportunities"][identity]
    assert summary["complete"] is True
    assert summary["route"] == "/swing/opportunities"
    assert summary["status"] == 200 and summary["outcome"] == "RETURNED"
    assert any(row["stage"] == "RESTORATION_LOCK" and row["mode"] == "WAIT"
               for row in summary["stages"])
    assert len(body.encode()) < 1024*1024
    assert inventory(root) == before and metadata(root) == before_metadata
    assert calls == [] and provider.begin_count == 0


def test_concurrent_opportunities_keep_distinct_completed_summaries(observed, monkeypatch):
    server, idle = observed
    entered = Barrier(5)
    release = Event()
    def blocked(handler):
        entered.wait(5)
        assert release.wait(5)
        handler.send_response(200)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
    monkeypatch.setattr(browser._BrowserHandler, "do_GET", blocked)
    results = []
    clients = [Thread(target=lambda: results.append(_request(server, "GET", "/swing/opportunities")))
               for _ in range(4)]
    try:
        for thread in clients:
            thread.start()
        entered.wait(5)
        assert server.request_capacity_status()["active"] == 4
    finally:
        release.set()
        for thread in clients:
            thread.join(5)
    assert idle.wait(5) and len(results) == 4
    ids = {headers["X-Kronos-Request-ID"] for code, headers, _ in results if code == 200}
    assert len(ids) == 4
    completed = server.request_diagnostics.snapshot()["completed_opportunities"]
    assert ids <= set(completed)
    assert all(completed[identity]["complete"] is True for identity in ids)
    assert server.request_capacity_status()["active"] == 0


def test_concurrent_requests_keep_distinct_identity_and_release(observed, monkeypatch):
    server, idle = observed
    entered = Barrier(5)
    release = Event()
    def blocked(handler):
        entered.wait(5)
        assert release.wait(5)
        handler.send_response(200)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
    monkeypatch.setattr(browser._BrowserHandler, "do_GET", blocked)
    results = []
    clients = [Thread(target=lambda: results.append(_request(server, "GET", "/status"))) for _ in range(4)]
    try:
        for thread in clients:
            thread.start()
        entered.wait(5)
        snap = server.request_diagnostics.snapshot()
        assert len(snap["active"]) == 4
        assert server.request_capacity_status()["active"] == 4
    finally:
        release.set()
        for thread in clients:
            thread.join(5)
    assert idle.wait(5) and len(results) == 4
    ids = {headers["X-Kronos-Request-ID"] for code, headers, _ in results if code == 200}
    assert len(ids) == 4
    for identity in ids:
        assert events(server, identity)[-1]["event"] == "CLEANUP"
    assert server.request_diagnostics.snapshot()["active"] == []


def test_capacity_refusal_before_parsing_is_unknown(observed):
    server, idle = observed
    for _ in range(32):
        assert server._request_slots.acquire(blocking=False)
    try:
        code, headers, body = _request(server, "GET", "/status?secret=DO_NOT_RETAIN")
        assert code == 503 and "BROWSER_REQUEST_CAPACITY_UNAVAILABLE" in body
    finally:
        for _ in range(32):
            server._request_slots.release()
    # An accepted request behind the refusal proves accept-loop cleanup finished.
    assert _request(server, "GET", "/status")[0] == 200 and idle.wait(5)
    rows = server.request_diagnostics.snapshot()["events"]
    refused = next(e for e in rows if e["event"] == "REFUSED")
    assert refused["id"] == headers["X-Kronos-Request-ID"]
    own = events(server, refused["id"])
    assert all(e["route"] == e["method"] == "UNKNOWN" for e in own)
    assert own[-1]["outcome"] == "CAPACITY_REFUSED" and own[-1]["event"] == "CLEANUP"
    assert server.request_capacity_status()["refusals"] == 1


def test_unhandled_exception_is_sanitized_and_owner_released(observed, monkeypatch):
    server, idle = observed
    def fail(handler):
        raise ValueError("DO_NOT_RETAIN token and payload")
    monkeypatch.setattr(browser._BrowserHandler, "do_GET", fail)
    with pytest.raises(RemoteDisconnected):
        _request(server, "GET", "/status")
    assert idle.wait(5)
    snap = server.request_diagnostics.snapshot()
    assert not snap["active"] and "DO_NOT_RETAIN" not in json.dumps(snap)
    assert snap["events"][-1]["outcome"] == "EXCEPTION"


def test_reset_client_reports_abort_and_releases_owner(observed, monkeypatch):
    server, idle = observed
    entered, released = Event(), Event()
    def write_after_reset(handler):
        entered.set()
        assert released.wait(5)
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(b"x" * 1024*1024)
    monkeypatch.setattr(browser._BrowserHandler, "do_GET", write_after_reset)
    sock = socket.create_connection(("127.0.0.1", server.server_port), timeout=3)
    sock.sendall(b"GET /status HTTP/1.0\r\n\r\n")
    assert entered.wait(5)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    sock.close()
    released.set()
    assert idle.wait(5)
    rows = server.request_diagnostics.snapshot()["events"]
    assert rows[-1]["event"] == "CLEANUP" and rows[-1]["outcome"] == "ABORTED_CLIENT"


@pytest.mark.parametrize("fault", ["start", "emit", "snapshot"])
def test_diagnostic_fault_does_not_change_http_or_ownership(observed, monkeypatch, fault):
    server, idle = observed
    def fail(*args, **kwargs):
        raise OSError("diagnostic destination unavailable")
    monkeypatch.setattr(server.request_diagnostics, fault, fail)
    code, _, body = _request(server, "GET", "/runtime/request-diagnostics")
    assert code == 200 and idle.wait(5)
    assert server.request_capacity_status()["active"] == 0
    if fault == "snapshot":
        assert json.loads(body)["state"] == "UNAVAILABLE"
    else:
        assert json.loads(body)["dropped"] > 0


def test_full_ring_never_expands_launcher_status_or_calls_owners_for_diagnostics(observed, monkeypatch):
    server, idle = observed
    trace = server.request_diagnostics.start()
    trace.parsed("GET", "/swing/opportunities")
    for _ in range(600):
        trace.emit("PARSED")
    trace.finish()
    code, _, body = _request(server, "GET", "/runtime/status")
    assert code == 200 and idle.wait(5)
    assert "request_diagnostics" not in json.loads(body)
    assert len(body.encode()) < 64*1024  # unchanged launcher response ceiling
    def forbidden_owner_read():
        raise AssertionError("diagnostic read reached application owner")
    monkeypatch.setattr(server.application, "snapshot", forbidden_owner_read)
    idle.clear()
    code, _, body = _request(server, "GET", "/runtime/request-diagnostics")
    assert code == 200 and idle.wait(5)
    assert len(json.loads(body)["events"]) == 512
    assert len(body.encode()) < 1024*1024


def test_unparsed_socket_is_visible_as_header_wait_then_same_request_is_parsed(observed, monkeypatch):
    server, idle = observed
    entered = Event()
    original = server.request_diagnostics.emit
    def record(trace, event, **fields):
        original(trace, event, **fields)
        if event == "STAGE_START" and fields.get("stage") == "REQUEST_HEADERS":
            entered.set()
    monkeypatch.setattr(server.request_diagnostics, "emit", record)
    sock = socket.create_connection(("127.0.0.1", server.server_port), timeout=3)
    try:
        assert entered.wait(5)
        active = server.request_diagnostics.snapshot()["active"]
        assert len(active) == 1 and active[0]["route"] == active[0]["method"] == "UNKNOWN"
        assert active[0]["stages"][-1][:2] == ("REQUEST_HEADERS", "WAIT")
        identity = active[0]["id"]
        sock.sendall(b"GET /status HTTP/1.0\r\n\r\n")
        response = HTTPResponse(sock)
        response.begin()
        response.read()
        assert response.status == 200 and response.getheader("X-Kronos-Request-ID") == identity
        assert idle.wait(5)
        assert events(server, identity)[-1]["outcome"] == "RETURNED"
    finally:
        sock.close()


def test_restoration_wait_is_visible_without_holding_diagnostic_lock():
    server = object.__new__(browser.KronosBrowserServer)
    server.request_diagnostics = RequestDiagnostics()
    server.connection_governance = None
    acquired, complete = Event(), Event()
    lock = Lock()
    class ContendedLock:
        def __enter__(self):
            acquired.set()
            lock.acquire()
        def __exit__(self, *args):
            lock.release()
    server._sponsor_restoration_lock = ContendedLock()
    server._restore_sponsor_operability = lambda capability: None
    lock.acquire()
    thread = Thread(target=lambda: (server.restore_sponsor_operability(), complete.set()))
    thread.start()
    try:
        assert acquired.wait(5)
        active = server.request_diagnostics.snapshot()["active"]
        assert len(active) == 1 and active[0]["kind"] == "SPONSOR_RESTORATION"
        assert active[0]["stages"][0][:2] == ("RESTORATION_LOCK", "WAIT")
    finally:
        lock.release()
        thread.join(5)
    assert complete.is_set() and not server.request_diagnostics.snapshot()["active"]


def test_dispatch_failure_cleans_up_and_preserves_exception(observed, monkeypatch):
    server, idle = observed
    def fail(*args):
        raise RuntimeError("dispatch unavailable")
    monkeypatch.setattr(browser.ThreadingHTTPServer, "process_request", fail)
    with pytest.raises(RuntimeError, match="dispatch unavailable"):
        server.process_request(object(), ("127.0.0.1", 1))
    assert idle.wait(5)
    snap = server.request_diagnostics.snapshot()
    assert snap["active"] == [] and snap["events"][-1]["outcome"] == "EXCEPTION"
    assert not server._diagnostic_requests


def test_request_header_timeout_is_recorded_without_changing_parser_cleanup(observed, monkeypatch):
    server, idle = observed
    original = browser._BrowserHandler.setup
    def short_test_deadline(handler):
        original(handler)
        handler.connection.settimeout(0.05)
    monkeypatch.setattr(browser._BrowserHandler, "setup", short_test_deadline)
    sock = socket.create_connection(("127.0.0.1", server.server_port), timeout=3)
    try:
        sock.sendall(b"GET /status")  # incomplete header; the base parser handles timeout
        assert idle.wait(5)
        rows = server.request_diagnostics.snapshot()["events"]
        assert rows[-1]["event"] == "CLEANUP" and rows[-1]["outcome"] == "TIMEOUT"
        assert all(e["route"] == "UNKNOWN" for e in rows if e["kind"] == "REQUEST")
    finally:
        sock.close()


def test_intake_transition_wait_retains_original_reader_protocol():
    workflow = object.__new__(NativeReviewIntakeWorkflow)
    waiting, entered = Event(), Event()
    class ObservedCondition(Condition):
        def wait(self, *args):
            waiting.set()
            return super().wait(*args)
    workflow._page_transition_condition = ObservedCondition()
    workflow._page_transition_active = True
    workflow._page_active_readers = 0
    recorder = RequestDiagnostics()
    trace = recorder.start()
    def read():
        with bind_trace(trace), workflow._page_reader():
            entered.set()
        trace.finish()
    thread = Thread(target=read)
    thread.start()
    try:
        assert waiting.wait(5) and not entered.is_set()
        active = recorder.snapshot()["active"]
        assert active[0]["stages"][-1][:2] == ("INTAKE_TRANSITION", "WAIT")
    finally:
        with workflow._page_transition_condition:
            workflow._page_transition_active = False
            workflow._page_transition_condition.notify_all()
        thread.join(5)
    assert entered.is_set() and workflow._page_active_readers == 0
    assert not recorder.snapshot()["active"]


@pytest.mark.parametrize("current", [True, False])
def test_trade_window_instrumentation_preserves_exact_currentness(current):
    owner = object.__new__(SwingTradeWindowWorkflow)
    owner._projection_lock = RLock()
    owner._projection_changes = 0
    owner._projection_generation = 1
    owner._completed = {}
    recorder = RequestDiagnostics()
    trace = recorder.start()
    with bind_trace(trace):
        if current:
            assert owner.project_selected("SWING-RUN-"+"A"*32, "RBLBANK", "a"*64) is None
        else:
            with pytest.raises(ValueError, match="SWING_TRADE_WINDOW_SELECTION_STALE"):
                owner.project_selected("SWING-RUN-"+"A"*32, "RBLBANK", "a"*64,
                                       authority_is_current=lambda: False)
    trace.finish()
    stages = [e for e in recorder.snapshot()["events"] if e["event"] == "STAGE_END"]
    assert [e["mode"] for e in stages if e["stage"] == "TRADE_WINDOW_LOCK"] == (["WAIT"]*2 if current else ["WAIT"])
    assert not recorder.snapshot()["active"]
