"""Bounded MCX advisory acquisition outside serial monitoring callbacks."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from threading import Event, RLock
from time import monotonic
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from kronos.application import swing_mcx_v1_operations as operations
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState, ProviderMarketTick,
)
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.native_active_trade_lifecycle import ActiveLifecycleState


NOW = datetime(2026, 9, 29, 14, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_bounded_worker_deduplicates_and_does_not_serialize_positions():
    worker = operations._BoundedMcxAdvisoryWorker()
    slow_started, release_slow, fast_done = Event(), Event(), Event()
    calls: list[str] = []

    def slow():
        calls.append("slow")
        slow_started.set()
        assert release_slow.wait(2)

    def fast():
        calls.append("fast")
        fast_done.set()

    assert worker.submit("position-a", "hour-1", slow)
    assert slow_started.wait(2)
    assert not worker.submit(
        "position-a", "hour-1", lambda: calls.append("duplicate"))
    assert worker.submit("position-b", "hour-1", fast)
    assert fast_done.wait(2)
    assert calls == ["slow", "fast"]
    release_slow.set()
    worker.close()
    assert worker.status()["pending"] == 0


def test_worker_failure_releases_counted_owner_and_allows_later_work():
    worker = operations._BoundedMcxAdvisoryWorker()
    admission = MaintenanceAdmissionCoordinator()
    parent = admission.admit("MONITORING_CALLBACK")
    assert parent is not None
    failed = Event()

    def failure():
        failed.set()
        raise RuntimeError("sanitized test failure")

    with parent.activate():
        child = admission.admit("MONITORING_CALLBACK")
        assert child is not None
        assert worker.submit("position-a", "hour-1", failure, child)
    parent.release()
    assert failed.wait(2)
    deadline = monotonic() + 2
    while worker.status()["failures"].get("position-a") != "RuntimeError":
        assert monotonic() < deadline
        failed.wait(0.01)
    assert not worker.submit("position-a", "hour-1", lambda: None)
    later_done = Event()
    assert worker.submit("position-a", "hour-2", later_done.set)
    assert later_done.wait(2)
    worker.close()
    assert admission.snapshot()["owners"] == {}
    assert worker.status()["failures"] == {}


def test_worker_pending_cleanup_precedes_final_ticket_release(monkeypatch):
    """Force the canonical handoff's zero-owner/pending-future race."""
    worker = operations._BoundedMcxAdvisoryWorker()
    admission = MaintenanceAdmissionCoordinator()
    ticket = admission.admit('MONITORING_CALLBACK')
    started, finish, releasing, permit_release = Event(), Event(), Event(), Event()
    original_release = admission._release
    observed = []

    def release(owner_ticket):
        observed.append(worker.status()['pending'])
        releasing.set()
        assert permit_release.wait(5)
        original_release(owner_ticket)

    monkeypatch.setattr(admission, '_release', release)

    def work():
        started.set()
        assert finish.wait(5)

    try:
        assert worker.submit('position-a', 'hour-1', work, ticket)
        assert started.wait(5)
        generation = 'e' * 64
        assert admission.claim(generation)
        admission.draining(generation)
        finish.set()
        assert releasing.wait(5)
        assert observed == [0]
        assert admission.snapshot()['owners'] == {'MONITORING_CALLBACK': 1}
        permit_release.set()
        assert admission.wait_for_zero(generation, 5)
        assert worker.status()['pending'] == 0
    finally:
        finish.set()
        permit_release.set()
        worker.close()


def test_already_completed_or_cancelled_future_releases_ticket_outside_worker_lock(monkeypatch):
    from concurrent.futures import Future
    from threading import Thread
    for cancelled in (False, True):
        worker = operations._BoundedMcxAdvisoryWorker()
        admission = MaintenanceAdmissionCoordinator()
        ticket = admission.admit('MONITORING_CALLBACK')
        future = Future()
        if cancelled:
            assert future.cancel()
        else:
            future.set_result(None)
        monkeypatch.setattr(worker._executor, 'submit', lambda *_args: future)
        original = admission._release
        threads = []

        def release(owner_ticket):
            acquired = Event()
            def inspect():
                assert worker.status()['pending'] == 0
                acquired.set()
            thread = Thread(target=inspect)
            threads.append(thread)
            thread.start()
            assert acquired.wait(5), 'release still holds the worker lock'
            original(owner_ticket)

        monkeypatch.setattr(admission, '_release', release)
        try:
            assert worker.submit('position-a', 'hour-1', lambda: None, ticket)
            assert admission.snapshot()['owners'] == {}
            assert worker.status()['pending'] == 0
            assert worker.status()['failures'] == ({'position-a': 'CancelledError'} if cancelled else {})
        finally:
            worker.close()
            for thread in threads:
                thread.join(5)
                assert not thread.is_alive()


def test_tick_callback_queues_once_then_uses_later_cmp(monkeypatch):
    instrument = InstrumentRecord(
        "KITE", "MCX", "MCX-FUT", "GOLDM26OCTFUT", "GOLDM", "FUT",
        date(2026, 10, 5), Decimal("1"), 1)
    position = SimpleNamespace(
        position_id="position-a", canonical_instrument=McxFamily.GOLDM.value,
        trade_plan_id="MCX-TRADE-PLAN-" + "a" * 64,
        mcx_v1_contract_symbol=instrument.trading_symbol,
        state=ActiveLifecycleState.PAPER_ARMED)
    plan = SimpleNamespace(
        native_run_identity="run-a", family=McxFamily.GOLDM,
        trade_plan_id=position.trade_plan_id, integrity_hash="b" * 64,
        observation_boundary=NOW - timedelta(hours=1),
        entry_eligibility_boundary=NOW + timedelta(hours=2))
    owner = SimpleNamespace(final_fence=lambda: None)
    outcome_slot = SimpleNamespace(value=None)
    issue_started, release_issue = Event(), Event()
    issue_calls: list[datetime] = []
    activation_calls: list[ProviderMarketTick] = []

    def issue(**values):
        issue_calls.append(values["evaluated_at"])
        issue_started.set()
        assert release_issue.wait(2)
        outcome_slot.value = SimpleNamespace(confirmed_at=NOW + timedelta(seconds=1))
        return outcome_slot.value

    monkeypatch.setattr(operations, "issue_v1_production_signal", issue)
    control = object.__new__(operations.SwingMcxV1OperationalControl)
    control._lock = RLock()
    control._maintenance_admission = None
    control._advisory_worker = operations._BoundedMcxAdvisoryWorker()
    control.lifecycle = SimpleNamespace(_require=lambda _identity: position)
    control.workflow = SimpleNamespace(run_identity="run-a")
    control.review_owner = owner
    control._plan = lambda *_args: plan
    control._current_plan_owner = lambda _plan: (instrument, owner)
    control._active_provider = lambda: SimpleNamespace()
    control._decision_inputs = lambda _plan: (None, SimpleNamespace())
    window = SimpleNamespace(window_close=NOW + timedelta(hours=4))
    schedule = SimpleNamespace(
        session_identity="session-a", window_at=lambda _moment: window)
    control.calendar = SimpleNamespace(
        schedule=lambda *_args, **_kwargs: schedule)
    control.master = control.mtf = object()
    control.plans = control.sponsor = object()
    control.outcomes = SimpleNamespace(
        load_for_plan=lambda _identity: outcome_slot.value)

    def activate(_position_id, _plan, _outcome, tick, *_args, **_kwargs):
        activation_calls.append(tick)
        return "activated"

    control.bound = SimpleNamespace(activate_v1_paper_at_observed_cmp=activate)
    tick = ProviderMarketTick(
        instrument, Decimal("101"), NOW, NOW, "KITE_CONNECT_WEBSOCKET",
        "connection-a", None, False, False, False)

    # Returning while the historical call is blocked proves callback isolation.
    assert control.on_paper_tick(
        position.position_id, tick, MonitoringConnectionState.CONNECTED) is None
    assert issue_started.wait(2)
    assert control.on_paper_tick(
        position.position_id, tick, MonitoringConnectionState.CONNECTED) is None
    assert issue_calls == [NOW]
    assert activation_calls == []

    release_issue.set()
    control.close()
    later = ProviderMarketTick(
        instrument, Decimal("102"), NOW + timedelta(seconds=2),
        NOW + timedelta(seconds=2), "KITE_CONNECT_WEBSOCKET",
        "connection-a", None, False, False, False)
    assert control.on_paper_tick(
        position.position_id, later,
        MonitoringConnectionState.CONNECTED) == "activated"
    assert activation_calls == [later]
