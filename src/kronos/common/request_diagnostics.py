"""Loss-tolerant operational diagnostics; no disk, worker, or domain authority.

The recorder is a leaf: it never waits for its lock, calls an owner, or does I/O.
Events may be lost under contention/failure; that must never affect a request.
Snapshots are bounded and observational. They are not durable audit evidence.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import os
import sys
from threading import Lock
from time import monotonic_ns, time_ns
from uuid import uuid4

MAX_EVENTS = 512
MAX_EVENT_BYTES = 512
MAX_ACTIVE = 40  # 32 HTTP owners plus bounded restoration diagnostics
MAX_DEPTH = 16
RETENTION_NS = 900 * 1_000_000_000
ROUTES = frozenset({"/status", "/runtime/status", "/dashboard",
    "/runtime/request-diagnostics", "/notifications/status", "/swing/v1/status",
    "/swing/v1/bulk-import-status", "/control/provider-instrument-master/status",
    "/control/intraday-discovery/status", "/control/intraday-historical-qualification/status",
    "/swing/opportunities", "/swing/v1-review", "/swing/trade-candidates",
    "/intraday", "/intraday/review", "/provider/connect", "/provider/disconnect",
    "/control/shutdown", "/control/maintenance/exit"})
METHODS = frozenset({"GET", "POST", "HEAD", "OPTIONS"})
STAGES = frozenset({"REQUEST_HEADERS", "INTAKE_ENTER", "INTAKE_EXIT",
    "INTAKE_READER_LOCK", "INTAKE_TRANSITION", "INTAKE_STATE_LOCK",
    "INTAKE_VALIDATE", "INTAKE_REVALIDATE", "PUBLICATION", "CURRENTNESS",
    "RESTORATION_LOCK", "SPONSOR_RESTORATION", "SELECTED_PRESENTATIONS",
    "TRADE_WINDOW", "TRADE_WINDOW_LOCK", "TRADE_WINDOW_RECONSTRUCT",
    "V2_SELECTION", "RENDER_INPUTS", "RENDER", "RESPONSE_WRITE"})
EVENTS = frozenset({"ADMITTED", "REFUSED", "THREAD_STARTED", "PARSED", "EOF", "TIMEOUT",
    "RESPONSE", "EXCEPTION", "ABORT", "HANDLER_RETURNED", "CLEANUP",
    "STAGE_START", "STAGE_END", "OPERATION_START"})
OUTCOMES = frozenset({"UNKNOWN", "RETURNED", "HTTP_ERROR", "EXCEPTION",
    "ABORTED_CLIENT", "CAPACITY_REFUSED", "TIMEOUT"})
_CURRENT = ContextVar("kronos_request_diagnostic", default=None)


def safe_call(function, *args, **kwargs):
    """Diagnostics must not replace an application exception or strand a slot."""
    try:
        return function(*args, **kwargs)
    except Exception:
        return None


def start_trace(recorder, kind="REQUEST"):
    try:
        return recorder.start(kind)
    except Exception:
        safe_call(recorder._drop)
        return None


@dataclass(slots=True)
class Trace:
    recorder: RequestDiagnostics
    identity: str
    started: int
    kind: str
    route: str = "UNKNOWN"
    method: str = "UNKNOWN"
    status: int | None = None
    outcome: str = "UNKNOWN"
    finished: bool = False
    stages: list = field(default_factory=list)

    def emit(self, event, *, stage="UNKNOWN", mode="UNKNOWN", duration=None):
        try:
            self.recorder.emit(self, event, stage=stage, mode=mode, duration=duration)
        except Exception:
            self.recorder._drop()

    def parsed(self, method, target):
        # Never store an arbitrary path, query, fragment, header or body.
        self.method = method if method in METHODS else "UNKNOWN"
        path = target.partition("?")[0].partition("#")[0] if len(target) <= 4096 else ""
        self.route = path if path in ROUTES else "UNKNOWN"
        self.emit("PARSED")

    def response(self, code):
        self.status = int(code) if isinstance(code, int) and 100 <= code <= 599 else None
        self.emit("RESPONSE")  # headers attempted, not proof of client delivery

    def failure(self, error):
        aborted = isinstance(error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError))
        timed_out = isinstance(error, TimeoutError)
        self.outcome = "ABORTED_CLIENT" if aborted else "TIMEOUT" if timed_out else "EXCEPTION"
        self.emit("ABORT" if aborted else "TIMEOUT" if timed_out else "EXCEPTION")

    def finish(self):
        self.finished = True  # cleanup truth does not depend on recorder availability
        if self.outcome == "UNKNOWN" and self.status is not None:
            self.outcome = "HTTP_ERROR" if self.status >= 400 else "RETURNED"
        self.emit("CLEANUP")


class RequestDiagnostics:
    def __init__(self):
        self._lock = Lock()
        self._events = deque(maxlen=MAX_EVENTS)
        self._active = {}
        self._dropped = 0
        self._evicted = 0
        self._sequence = 0
        self._epoch_ns = monotonic_ns()
        self._utc_ns = time_ns()
        self._instance = uuid4().hex

    def start(self, kind="REQUEST"):
        trace = Trace(self, uuid4().hex, monotonic_ns(),
                      kind if kind in {"REQUEST", "SPONSOR_RESTORATION"} else "UNKNOWN")
        if not self._lock.acquire(blocking=False):
            self._drop()
            return trace
        try:
            self._active = {k: v for k, v in self._active.items() if not v.finished}
            if len(self._active) < MAX_ACTIVE:
                self._active[trace.identity] = trace
            else:
                self._drop()
        finally:
            self._lock.release()
        return trace

    def _drop(self):
        self._dropped = min(2**31 - 1, self._dropped + 1)

    def emit(self, trace, event, *, stage="UNKNOWN", mode="UNKNOWN", duration=None):
        if not self._lock.acquire(blocking=False):
            self._drop()
            return
        try:
            now = monotonic_ns()
            self._sequence += 1
            row = dict(seq=self._sequence, id=trace.identity, event=event if event in EVENTS else "UNKNOWN",
                       route=trace.route, method=trace.method, kind=trace.kind,
                       at_ns=now-self._epoch_ns, elapsed_ns=now-trace.started,
                       status=trace.status, outcome=trace.outcome if trace.outcome in OUTCOMES else "UNKNOWN",
                       stage=stage if stage in STAGES else "UNKNOWN",
                       mode=mode if mode in {"WAIT", "PROCESS"} else "UNKNOWN",
                       duration_ns=duration)
            raw = json.dumps(row, separators=(",", ":")).encode("ascii")
            if len(raw) <= MAX_EVENT_BYTES:
                while self._events and now - self._events[0][0] > RETENTION_NS:
                    self._events.popleft()
                    self._evicted = min(2**31-1, self._evicted+1)
                if len(self._events) == MAX_EVENTS:
                    self._evicted = min(2**31-1, self._evicted+1)
                self._events.append((now, raw))
            else:
                self._drop()
            if trace.finished:
                self._active.pop(trace.identity, None)
        finally:
            self._lock.release()

    def snapshot(self):
        if not self._lock.acquire(blocking=False):
            return {"schema": "KRONOS_REQUEST_DIAGNOSTICS_V1", "state": "BUSY"}
        try:
            now = monotonic_ns()
            retained = tuple(raw for at, raw in self._events if now-at <= RETENTION_NS)
            active = [dict(id=t.identity, kind=t.kind, route=t.route, method=t.method,
                           elapsed_ns=now-t.started, status=t.status,
                           stages=tuple(t.stages))
                      for t in self._active.values() if not t.finished]
            dropped = self._dropped
            evicted = self._evicted
        finally:
            self._lock.release()
        return dict(schema="KRONOS_REQUEST_DIAGNOSTICS_V1", state="AVAILABLE",
                    instance=self._instance, pid=os.getpid(), epoch_utc_ns=self._utc_ns,
                    epoch_monotonic_ns=self._epoch_ns, observed_ns=now-self._epoch_ns,
                    limits=dict(events=MAX_EVENTS, event_bytes=MAX_EVENT_BYTES,
                                active=MAX_ACTIVE, stage_depth=MAX_DEPTH,
                                retention_seconds=900, disk_bytes=0),
                    dropped=dropped, evicted=evicted, active=active,
                    events=[json.loads(raw) for raw in retained])


@contextmanager
def bind_trace(trace):
    token = _CURRENT.set(trace)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def current_trace():
    return _CURRENT.get()


@contextmanager
def diagnostic_stage(name, mode="PROCESS"):
    trace = _CURRENT.get()
    if trace is None:
        yield
        return
    name = name if name in STAGES else "UNKNOWN"
    mode = mode if mode in {"PROCESS", "WAIT"} else "UNKNOWN"
    started = monotonic_ns()
    entry = (name, mode, started - trace.recorder._epoch_ns)
    tracked = len(trace.stages) < MAX_DEPTH
    if tracked:
        trace.stages.append(entry)
    trace.emit("STAGE_START", stage=name, mode=mode)
    try:
        yield
    finally:
        if tracked:
            trace.stages.pop()
        trace.emit("STAGE_END", stage=name, mode=mode, duration=monotonic_ns()-started)


@contextmanager
def diagnostic_lock(lock, name):
    # The original lock is acquired/released in its original order. The
    # diagnostic leaf never blocks, calls business code, or performs I/O.
    with diagnostic_stage(name, "WAIT"):
        lock.__enter__()
    try:
        yield
    finally:
        lock.__exit__(None, None, None)


@contextmanager
def diagnostic_context(context, enter, leave):
    with diagnostic_stage(enter):
        value = context.__enter__()
    try:
        yield value
    except BaseException:
        with diagnostic_stage(leave):
            suppress = context.__exit__(*sys.exc_info())
        if not suppress:
            raise
    else:
        with diagnostic_stage(leave):
            context.__exit__(None, None, None)


@contextmanager
def diagnostic_operation(server):
    recorder = getattr(server, "request_diagnostics", None)
    trace = start_trace(recorder, "SPONSOR_RESTORATION") if isinstance(recorder, RequestDiagnostics) else None
    with bind_trace(trace):
        if trace is not None:
            trace.emit("OPERATION_START")
        try:
            yield
        finally:
            if trace is not None:
                trace.finish()
