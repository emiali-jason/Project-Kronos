"""Bounded observational diagnostics; deterministic clocks and lock barriers."""
from contextlib import contextmanager
from threading import Event, Lock, Thread
import json
import sys

import pytest

from kronos.common import request_diagnostics as d


def test_closed_fields_and_no_sensitive_payload():
    recorder = d.RequestDiagnostics()
    trace = recorder.start()
    trace.emit("ADMITTED")
    trace.parsed("GET", "/swing/opportunities?request_token=DO_NOT_RETAIN#secret")
    trace.response(200)
    trace.failure(ValueError("DO_NOT_RETAIN payload"))
    trace.finish()
    result = recorder.snapshot()
    assert not result["active"]
    assert "DO_NOT_RETAIN" not in json.dumps(result)
    events = result["events"]
    assert events[0]["route"] == events[0]["method"] == "UNKNOWN"
    assert events[1]["route"] == "/swing/opportunities"
    assert events[-1]["outcome"] == "EXCEPTION"
    assert {e["id"] for e in events} == {trace.identity}
    trace = recorder.start()
    trace.parsed("SECRET", "/unknown/DO_NOT_RETAIN")
    trace.emit("DO_NOT_RETAIN", stage="DO_NOT_RETAIN", mode="DO_NOT_RETAIN")
    assert "DO_NOT_RETAIN" not in json.dumps(recorder.snapshot())


def test_retention_payload_and_active_limits(monkeypatch):
    clock = [1_000_000_000]
    monkeypatch.setattr(d, "monotonic_ns", lambda: clock[0])
    recorder = d.RequestDiagnostics()
    trace = recorder.start()
    for _ in range(3000):
        trace.emit("PARSED")
    # Actual retained event objects, independent of another test's global
    # tracemalloc state. A separate clean-process probe retains peak evidence.
    retained = sys.getsizeof(recorder._events) + sum(
        sys.getsizeof(row) + sum(sys.getsizeof(value) for value in row)
        for row in recorder._events)
    assert len(recorder._events) == d.MAX_EVENTS
    assert sum(len(raw) for _, raw in recorder._events) <= d.MAX_EVENTS*d.MAX_EVENT_BYTES
    assert retained < 1024*1024
    for _ in range(100):
        recorder.start()
    result = recorder.snapshot()
    assert len(result["active"]) == d.MAX_ACTIVE
    assert result["dropped"] == 61 and result["evicted"] == 3000-d.MAX_EVENTS
    assert result["limits"]["disk_bytes"] == 0
    assert len(json.dumps(result).encode()) < 1024*1024
    clock[0] += d.RETENTION_NS+1
    before = tuple(recorder._events)
    assert recorder.snapshot()["events"] == []
    assert tuple(recorder._events) == before  # reads do not prune or write
    trace.emit("CLEANUP")
    assert len(recorder._events) == 1


def test_stage_times_distinguish_wait_and_processing(monkeypatch):
    clock = [100]
    monkeypatch.setattr(d, "monotonic_ns", lambda: clock[0])
    recorder = d.RequestDiagnostics()
    trace = recorder.start()
    class ControlledLock:
        def __enter__(self):
            clock[0] += 70
        def __exit__(self, *unused):
            pass
    with d.bind_trace(trace):
        with d.diagnostic_lock(ControlledLock(), "RESTORATION_LOCK"):
            with d.diagnostic_stage("SELECTED_PRESENTATIONS"):
                clock[0] += 11
    ends = [e for e in recorder.snapshot()["events"] if e["event"] == "STAGE_END"]
    assert [(e["stage"],e["mode"],e["duration_ns"]) for e in ends] == [
        ("RESTORATION_LOCK","WAIT",70), ("SELECTED_PRESENTATIONS","PROCESS",11)]
    assert trace.stages == []


def test_completed_opportunities_survives_60_seconds_and_2334_unrelated_events(monkeypatch):
    clock = [1_000_000_000_000]
    monkeypatch.setattr(d, "monotonic_ns", lambda: clock[0])
    recorder = d.RequestDiagnostics()
    opportunity = recorder.start()
    opportunity.parsed("GET", "/swing/opportunities?token=DO_NOT_RETAIN")
    with d.bind_trace(opportunity):
        with d.diagnostic_stage("RESTORATION_LOCK", "WAIT"):
            clock[0] += 18_000_000_000
        with d.diagnostic_stage("SELECTED_PRESENTATIONS"):
            clock[0] += 10_830_000_000
    opportunity.response(200)
    opportunity.finish()
    completed_at = clock[0]
    # The prior live capture lost 2,334 events between the two reads.
    status = recorder.start()
    status.parsed("GET", "/status")
    for _ in range(2_400):
        status.emit("PARSED")
    status.response(200)
    status.finish()
    clock[0] = completed_at + 60_000_000_000
    first = recorder.snapshot()
    second = recorder.snapshot()
    assert first == second  # observational reads neither prune nor persist
    assert all(row["id"] != opportunity.identity for row in first["events"])
    summary = first["completed_opportunities"][opportunity.identity]
    assert summary["complete"] is True
    assert summary["elapsed_ns"] == 28_830_000_000
    assert summary["status"] == 200 and summary["outcome"] == "RETURNED"
    assert summary["route"] == "/swing/opportunities" and summary["method"] == "GET"
    assert summary["evidence_lost"] is False and summary["truncated"] is False
    assert [(row["stage"], row["mode"], row["total_ns"]) for row in summary["stages"]] == [
        ("RESTORATION_LOCK", "WAIT", 18_000_000_000),
        ("SELECTED_PRESENTATIONS", "PROCESS", 10_830_000_000),
    ]
    assert "DO_NOT_RETAIN" not in json.dumps(first)
    assert len(json.dumps(first).encode()) < 1024*1024
    assert first["limits"]["completed_opportunities"] == d.MAX_COMPLETED_OPPORTUNITIES
    assert first["limits"]["completed_summary_bytes"] == d.MAX_COMPLETED_SUMMARY_BYTES
    assert first["limits"]["disk_bytes"] == 0


def test_completed_opportunities_is_bounded_by_count_age_and_bytes(monkeypatch):
    clock = [1_000_000_000]
    monkeypatch.setattr(d, "monotonic_ns", lambda: clock[0])
    recorder = d.RequestDiagnostics()
    ids = []
    for _ in range(d.MAX_COMPLETED_OPPORTUNITIES + 1):
        trace = recorder.start()
        trace.parsed("GET", "/swing/opportunities")
        trace.response(200)
        trace.finish()
        ids.append(trace.identity)
    result = recorder.snapshot()
    assert len(result["completed_opportunities"]) == d.MAX_COMPLETED_OPPORTUNITIES
    assert ids[0] not in result["completed_opportunities"]
    assert result["completed_evicted"] == 1
    assert sum(len(raw) for _, raw in recorder._completed_opportunities.values()) <= (
        d.MAX_COMPLETED_OPPORTUNITIES * d.MAX_COMPLETED_SUMMARY_BYTES)
    retained = tuple(recorder._completed_opportunities.items())
    clock[0] += d.COMPLETED_RETENTION_NS + 1
    assert recorder.snapshot()["completed_opportunities"] == {}
    assert tuple(recorder._completed_opportunities.items()) == retained


def test_aborted_opportunity_is_terminal_but_not_a_success():
    recorder = d.RequestDiagnostics()
    trace = recorder.start()
    trace.parsed("GET", "/swing/opportunities")
    trace.response(200)  # attempted response headers are not delivery proof
    trace.failure(BrokenPipeError())
    trace.finish()
    summary = recorder.snapshot()["completed_opportunities"][trace.identity]
    assert summary["outcome"] == "ABORTED_CLIENT" and summary["status"] == 200
    assert summary["complete"] is True and not summary["evidence_lost"]


def test_summary_marks_recorder_loss_and_depth_truncation(monkeypatch):
    recorder = d.RequestDiagnostics()
    trace = recorder.start()
    trace.parsed("GET", "/swing/opportunities")
    original = recorder.emit
    def one_failed_event(item, event, **fields):
        if event == "STAGE_END":
            raise OSError("DO_NOT_RETAIN")
        return original(item, event, **fields)
    monkeypatch.setattr(recorder, "emit", one_failed_event)
    with d.bind_trace(trace):
        with d.diagnostic_stage("CURRENTNESS"):
            pass
    trace.response(200)
    trace.finish()
    summary = recorder.snapshot()["completed_opportunities"][trace.identity]
    assert summary["evidence_lost"] is True and summary["complete"] is False
    assert "DO_NOT_RETAIN" not in json.dumps(recorder.snapshot())

    nested = recorder.start()
    nested.parsed("GET", "/swing/opportunities")
    from contextlib import ExitStack
    with d.bind_trace(nested), ExitStack() as stack:
        for _ in range(d.MAX_DEPTH + 1):
            stack.enter_context(d.diagnostic_stage("RENDER"))
    nested.response(200)
    nested.finish()
    summary = recorder.snapshot()["completed_opportunities"][nested.identity]
    assert summary["truncated"] is True and summary["complete"] is False


def test_oversized_fixed_stage_set_is_retained_only_as_explicitly_truncated():
    recorder = d.RequestDiagnostics()
    trace = recorder.start()
    trace.parsed("GET", "/swing/opportunities")
    for name in d.STAGES:
        for mode in ("WAIT", "PROCESS"):
            trace.stage_starts += 1
            trace.measured_stage(name, mode, 28_840_000_000)
    trace.response(200)
    trace.finish()
    result = recorder.snapshot()
    summary = result["completed_opportunities"][trace.identity]
    assert summary["truncated"] is True and summary["complete"] is False
    assert summary["stages"] == []
    assert len(json.dumps(summary).encode()) <= d.MAX_COMPLETED_SUMMARY_BYTES


def test_opportunity_summary_saturation_never_claims_complete():
    recorder = d.RequestDiagnostics()
    held = [recorder.start() for _ in range(d.MAX_ACTIVE)]
    trace = recorder.start()
    trace.parsed("GET", "/swing/opportunities")
    trace.response(200)
    trace.finish()
    summary = recorder.snapshot()["completed_opportunities"][trace.identity]
    assert summary["evidence_lost"] is True and summary["complete"] is False
    assert len(recorder.snapshot()["active"]) == d.MAX_ACTIVE
    for active in held:
        active.finish()


def test_leaf_lock_contention_and_recording_failure_never_block_owner(monkeypatch):
    recorder = d.RequestDiagnostics()
    trace = recorder.start()
    business = Lock()
    done = Event()
    def work():
        with d.bind_trace(trace), d.diagnostic_lock(business, "TRADE_WINDOW_LOCK"):
            trace.emit("PARSED")
        trace.finish()
        done.set()
    with recorder._lock:
        thread = Thread(target=work)
        thread.start()
        assert done.wait(2)
        assert recorder.snapshot()["state"] == "BUSY"
    thread.join(2)
    assert not thread.is_alive() and not business.locked()
    assert recorder.snapshot()["active"] == []
    assert recorder.snapshot()["dropped"] > 0
    monkeypatch.setattr(recorder, "emit", lambda *a, **k: (_ for _ in ()).throw(OSError("secret")))
    with pytest.raises(ValueError, match="business failure"):
        with d.bind_trace(trace), d.diagnostic_lock(business, "TRADE_WINDOW_LOCK"):
            raise ValueError("business failure")
    assert not business.locked()


@pytest.mark.parametrize("suppress", [True, False])
def test_timed_context_preserves_exception_and_suppression(suppress):
    seen = []
    @contextmanager
    def owner():
        try:
            yield 42
        except ValueError:
            seen.append("exception")
            if not suppress:
                raise
        finally:
            seen.append("cleanup")
    recorder = d.RequestDiagnostics()
    with d.bind_trace(recorder.start()):
        try:
            with d.diagnostic_context(owner(), "INTAKE_ENTER", "INTAKE_EXIT") as result:
                assert result == 42
                raise ValueError("governed")
        except ValueError:
            assert not suppress
    assert seen == ["exception", "cleanup"]


@pytest.mark.parametrize("error,outcome,event", [
    (BrokenPipeError(), "ABORTED_CLIENT", "ABORT"),
    (ConnectionResetError(), "ABORTED_CLIENT", "ABORT"),
    (TimeoutError(), "TIMEOUT", "TIMEOUT"),
    (ValueError(), "EXCEPTION", "EXCEPTION"),
])
def test_safe_failure_classification(error, outcome, event):
    recorder = d.RequestDiagnostics()
    trace = recorder.start()
    trace.failure(error)
    trace.finish()
    assert recorder.snapshot()["events"][0]["event"] == event
    assert recorder.snapshot()["events"][-1]["outcome"] == outcome
