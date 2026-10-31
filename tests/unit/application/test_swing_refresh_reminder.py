from dataclasses import fields
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import threading
import time
import json

import pytest

from kronos.application.swing_refresh_reminder import (
    K5RefreshReminderRecord,
    K5RefreshReminderStore,
    RefreshReminderState,
    SwingK5RefreshReminderWorkflow,
    _integrity_values as reminder_integrity,
    next_completed_one_hour_boundary,
)
from kronos.application.swing_ux10 import (
    Ux10NotificationFamily,
    Ux10NotificationType,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalPromotionRecord,
    kr370_promotion_integrity_sha256,
)
from kronos.swing.v1.analytical_promotion_v2 import create_record
from tests.unit.swing.v1.test_analytical_promotion_v2 import (
    source as v2_source, criteria as v2_criteria, nse as v2_nse,
)
from tests.unit.swing.v1.test_kr370_step31_handoff import _completed
from tests.unit.application.test_swing_ux10 import Telegram, ux10


IST = ZoneInfo("Asia/Kolkata")


class Scheduler:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, delay, operation):  # type: ignore[no-untyped-def]
        handle = Handle(operation)
        self.calls.append((delay, handle))
        return handle


class Handle:
    def __init__(self, operation) -> None:  # type: ignore[no-untyped-def]
        self.operation = operation
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def test_v2_k5_ready_receives_existing_bounded_reminder_without_v1_conversion(tmp_path) -> None:
    promotion = create_record(
        source=v2_source(), criteria=v2_criteria(4), confirmation=v2_nse(),
        created_at=datetime(2026, 9, 21, 9, 0, tzinfo=ZoneInfo("UTC")))
    scheduler = Scheduler()
    workflow = SwingK5RefreshReminderWorkflow(
        K5RefreshReminderStore(tmp_path / "v2-reminders"),
        clock=lambda: datetime(2026, 9, 21, 14, 30, tzinfo=IST),
        scheduler=scheduler,
    )
    source = promotion.value["source"]
    snapshot = workflow.synchronize(
        source["native_run_identity"], (promotion,),
        {source["canonical_instrument"]: "NSE"},
    )
    assert len(snapshot.records) == 1
    record = snapshot.records[0]
    assert record.instrument_bindings == ((source["canonical_instrument"],
                                           source["native_assessment_sha256"],
                                           "BUY_READY", "NSE"),)
    assert len(scheduler.calls) == 1


def _ready(tmp_path: Path) -> Kr370AnalyticalPromotionRecord:
    value = _completed(tmp_path, extended=True).promotion
    assert value is not None
    return value


def _instrument(
    template: Kr370AnalyticalPromotionRecord,
    instrument: str,
    assessment: str,
) -> Kr370AnalyticalPromotionRecord:
    payload = {field.name: getattr(template, field.name) for field in fields(template)}
    payload.update(
        canonical_instrument=instrument,
        native_assessment_sha256=assessment,
        integrity_sha256="",
    )
    payload["integrity_sha256"] = kr370_promotion_integrity_sha256(payload)
    return Kr370AnalyticalPromotionRecord(**payload)


def test_k5_ready_deduplicates_same_boundary_and_delivers_once(tmp_path: Path) -> None:
    promotion = _ready(tmp_path / "source")
    values = (
        promotion,
        _instrument(promotion, "RVNL", "2" * 64),
        _instrument(promotion, "VBL", "3" * 64),
    )
    now = [datetime(2026, 8, 14, 16, 0, tzinfo=IST)]
    scheduler = Scheduler()
    telegram = Telegram()
    notifications = ux10(tmp_path / "notifications", telegram)
    delivered = []
    workflow = SwingK5RefreshReminderWorkflow(
        K5RefreshReminderStore(tmp_path / "reminders"),
        clock=lambda: now[0],
        scheduler=scheduler,
        notification_listener=lambda value: (
            delivered.append(value)
            or notifications.observe_refresh_analysis_reminder(value).notification_id
        ),
    )

    snapshot = workflow.synchronize(
        promotion.run_identity,
        values,
        {item.canonical_instrument: "NSE" for item in values},
    )

    assert len(snapshot.records) == 1
    record = snapshot.records[0]
    assert record.state is RefreshReminderState.PENDING
    assert tuple(item[0] for item in record.instrument_bindings) == (
        "IOC", "RVNL", "VBL",
    )
    assert record.next_eligible_completed_1h_boundary == datetime(
        2026, 8, 17, 10, 15, tzinfo=IST
    )
    assert len(scheduler.calls) == 1
    now[0] = record.next_eligible_completed_1h_boundary
    scheduler.calls[0][1].operation()
    assert len(delivered) == 1
    assert workflow.snapshot().records[0].state is RefreshReminderState.SENT
    notification = notifications.snapshot().records[0]
    assert notification.family is Ux10NotificationFamily.ANALYSIS_REMINDER
    assert notification.notification_type is Ux10NotificationType.REFRESH_ANALYSIS_REMINDER
    assert "K5 READY instruments" in notification.summary
    assert len(telegram.messages) == 1
    assert "REFRESH ANALYSIS REMINDER" in telegram.messages[0]
    assert workflow.next_repeat_boundary(
        notification.notification_id,
        record.next_eligible_completed_1h_boundary,
    ) == datetime(2026, 8, 17, 11, 15, tzinfo=IST)
    assert workflow.next_repeat_boundary(
        notification.notification_id,
        datetime(2026, 8, 17, 15, 30, tzinfo=IST),
    ) == datetime(2026, 8, 17, 16, 30, tzinfo=IST)
    assert workflow.next_repeat_boundary(
        notification.notification_id,
        datetime(2026, 8, 17, 23, 30, tzinfo=IST),
    ) == datetime(2026, 8, 18, 0, 30, tzinfo=IST)
    scheduler.calls[0][1].operation()
    assert len(delivered) == 1


def test_pending_restart_and_fresh_run_supersession_are_durable(tmp_path: Path) -> None:
    promotion = _ready(tmp_path / "source")
    root = tmp_path / "reminders"
    now = datetime(2026, 8, 14, 16, 0, tzinfo=IST)
    first = SwingK5RefreshReminderWorkflow(
        K5RefreshReminderStore(root), clock=lambda: now, scheduler=Scheduler()
    )
    first.synchronize(
        promotion.run_identity, (promotion,), {promotion.canonical_instrument: "NSE"}
    )
    first.close()

    scheduler = Scheduler()
    restored = SwingK5RefreshReminderWorkflow(
        K5RefreshReminderStore(root), clock=lambda: now, scheduler=scheduler
    )
    assert restored.snapshot().records[0].state is RefreshReminderState.PENDING
    assert len(scheduler.calls) == 1
    replacement = "SWING-RUN-FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
    restored.synchronize(replacement, (), {})
    assert restored.snapshot().records[0].state is RefreshReminderState.SUPERSEDED
    assert scheduler.calls[0][1].cancelled


def test_sent_reminder_is_not_rescheduled_or_resent_after_restart(tmp_path: Path) -> None:
    promotion = _ready(tmp_path / "source")
    root = tmp_path / "reminders"
    now = [datetime(2026, 8, 14, 16, 0, tzinfo=IST)]
    scheduler = Scheduler()
    delivered = []
    first = SwingK5RefreshReminderWorkflow(
        K5RefreshReminderStore(root),
        clock=lambda: now[0],
        scheduler=scheduler,
        notification_listener=lambda record: delivered.append(record) or "n" * 64,
    )
    first.synchronize(
        promotion.run_identity, (promotion,), {promotion.canonical_instrument: "NSE"}
    )
    now[0] = first.snapshot().records[0].next_eligible_completed_1h_boundary
    scheduler.calls[0][1].operation()
    assert len(delivered) == 1
    first.close()

    restarted_scheduler = Scheduler()
    restarted = SwingK5RefreshReminderWorkflow(
        K5RefreshReminderStore(root),
        clock=lambda: now[0],
        scheduler=restarted_scheduler,
        notification_listener=lambda record: delivered.append(record) or "m" * 64,
    )
    assert restarted.snapshot().records[0].state is RefreshReminderState.SENT
    assert restarted_scheduler.calls == []
    assert restarted.next_repeat_boundary(
        "n" * 64, now[0]
    ) == now[0] + timedelta(hours=1)
    restarted.synchronize(
        promotion.run_identity, (promotion,), {promotion.canonical_instrument: "NSE"}
    )
    assert len(delivered) == 1


def test_repeat_boundary_is_one_shared_elapsed_hour_for_mixed_exchanges(
    tmp_path: Path,
) -> None:
    promotion = _ready(tmp_path / "source")
    delivered_at = datetime(2026, 8, 17, 15, 30, tzinfo=IST)
    values = dict(
        reminder_identity="4" * 64,
        run_identity=promotion.run_identity,
        instrument_bindings=(
            ("GOLDM", "5" * 64, "BUY_READY", "MCX"),
            ("IOC", promotion.native_assessment_sha256, "BUY_READY", "NSE"),
        ),
        source_boundaries=(
            ("GOLDM", delivered_at - timedelta(hours=1)),
            ("IOC", delivered_at - timedelta(hours=1)),
        ),
        next_eligible_completed_1h_boundary=delivered_at,
        calendar_bindings=(
            ("MCX", "KRONOS-MCX-NON-AGRI-2026", "2026.1.1"),
            ("NSE", "KRONOS-NSE-CAPITAL-MARKET-2022-2026", "2026.1.2"),
        ),
        state=RefreshReminderState.SENT,
        created_at=delivered_at,
        updated_at=delivered_at,
        notification_identity="6" * 64,
        integrity_sha256="",
    )
    record = K5RefreshReminderRecord(**(
        values | {"integrity_sha256": reminder_integrity(values)}
    ))
    store = K5RefreshReminderStore(tmp_path / "reminders")
    store.retain(record)
    workflow = SwingK5RefreshReminderWorkflow(store, scheduler=Scheduler())

    assert workflow.next_repeat_boundary(
        record.notification_identity or "", delivered_at
    ) == datetime(2026, 8, 17, 16, 30, tzinfo=IST)


def test_next_boundary_respects_holiday_and_mcx_session() -> None:
    calendar = MarketCalendarPublisher()
    observed = datetime(2026, 1, 23, 16, 0, tzinfo=IST)
    assert next_completed_one_hour_boundary(
        calendar,
        "NSE",
        datetime(2026, 1, 23, 15, 30, tzinfo=IST),
        observed_at=observed,
    ) == datetime(2026, 1, 27, 10, 15, tzinfo=IST)
    assert next_completed_one_hour_boundary(
        calendar,
        "MCX",
        datetime(2026, 8, 24, 10, 0, tzinfo=IST),
        observed_at=datetime(2026, 8, 24, 10, 1, tzinfo=IST),
    ) == datetime(2026, 8, 24, 11, 0, tzinfo=IST)


def _retained_pending(tmp_path):
    promotion = _ready(tmp_path / "source")
    clock = [datetime(2026, 8, 14, 16, 0, tzinfo=IST)]
    store = K5RefreshReminderStore(tmp_path / "reminders")
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: clock[0],
                                          defer_execution=True)
    pending = owner.synchronize(promotion.run_identity, (promotion,),
                               {promotion.canonical_instrument: "NSE"}).records[0]
    owner.close()
    assert owner.cleanup_complete()
    return store, promotion, clock, pending


def _raw_reminders(store):
    return {str(p.relative_to(store.root)): p.read_bytes()
            for p in store.root.rglob("*.json")}


def _retain_k5_observation(tmp_path, name, value):
    root = Path(__file__).resolve().parents[4] / "qualification" / "case-evidence" / tmp_path.parents[1].name / tmp_path.name
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps(value, indent=2) + "\n")


@pytest.mark.parametrize("restored", [True, False])
def test_deferred_reminders_load_and_reconcile_without_callback_effects(tmp_path, restored):
    store, promotion, now, pending = _retained_pending(tmp_path)
    if not restored:
        store = K5RefreshReminderStore(tmp_path / "new-during-startup")
    calls = []
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
        defer_execution=True, notification_listener=lambda r: calls.append(r) or "n")
    owner.synchronize(promotion.run_identity, (promotion,),
                      {promotion.canonical_instrument: "NSE"})
    before = _raw_reminders(store)
    now[0] = pending.next_eligible_completed_1h_boundary
    owner._fire(pending.reminder_identity)
    owner._fire_owned(pending.reminder_identity)
    assert owner.maintenance_status()["live_timers"] == 0
    assert not calls and not owner._timers
    assert _raw_reminders(store) == before
    assert owner.snapshot().records[0].state is RefreshReminderState.PENDING
    owner.close()
    assert owner.cleanup_complete()


def test_activation_uses_actual_timer_and_same_current_pending_owner_once(tmp_path):
    store, _, now, pending = _retained_pending(tmp_path)
    now[0] = pending.next_eligible_completed_1h_boundary
    sent = threading.Event(); calls = []
    def listener(record):
        calls.append(record.reminder_identity); sent.set(); return "retained-notification"
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
        defer_execution=True, notification_listener=listener)
    original = _raw_reminders(store)
    try:
        assert owner._activate_execution() is True
        assert owner._activate_execution() is False
        assert sent.wait(2)
    finally:
        owner.close()
        assert owner._wait_closed(time.monotonic() + 2)
    assert calls == [pending.reminder_identity]
    assert owner.snapshot().records[0].state is RefreshReminderState.SENT
    assert all(_raw_reminders(store)[k] == v for k, v in original.items())


def test_concurrent_activation_and_reconciliation_schedule_one_actual_timer(tmp_path):
    store, promotion, now, pending = _retained_pending(tmp_path)
    gate = threading.Event(); fired = threading.Event(); calls = []; timers = []
    def schedule(_delay, operation):
        def queued():
            assert gate.wait(3)
            operation()
        timer = threading.Timer(0, queued); timers.append(timer); timer.start(); return timer
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
        defer_execution=True, scheduler=schedule,
        notification_listener=lambda r: calls.append(r.reminder_identity) or fired.set() or "n")
    start = threading.Barrier(4); results = []; errors = []
    def activate():
        try: start.wait(); results.append(owner._activate_execution())
        except BaseException as error: errors.append(error)
    def enqueue():
        try:
            start.wait(); owner.synchronize(promotion.run_identity, (promotion,),
                                          {promotion.canonical_instrument: "NSE"})
        except BaseException as error: errors.append(error)
    threads = [threading.Thread(target=f) for f in (activate, activate, enqueue)]
    for t in threads: t.start()
    start.wait()
    try:
        for t in threads: t.join(2); assert not t.is_alive()
        assert not errors and sorted(results) == [False, True]
        assert len(timers) == 1
        now[0] = pending.next_eligible_completed_1h_boundary
        gate.set(); assert fired.wait(2)
    finally:
        gate.set(); owner.close(); assert owner._wait_closed(time.monotonic() + 2)
    assert calls == [pending.reminder_identity]


def test_superseded_startup_record_and_closed_owner_cannot_activate(tmp_path):
    store, _, now, pending = _retained_pending(tmp_path)
    calls = []
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
        defer_execution=True, notification_listener=lambda r: calls.append(r) or "n")
    original = _raw_reminders(store)
    owner.synchronize("SWING-RUN-" + "F" * 32, (), {})
    now[0] = pending.next_eligible_completed_1h_boundary
    assert owner._activate_execution() is True
    owner._fire(pending.reminder_identity)
    assert owner.snapshot().records[0].state is RefreshReminderState.SUPERSEDED
    assert not owner._timers and not calls
    assert all(_raw_reminders(store)[k] == v for k, v in original.items())
    owner.close()
    with pytest.raises(ValueError, match="CLOSED_OR_FAILED"):
        owner._activate_execution()
    owner._fire(pending.reminder_identity)
    owner._fire_owned(pending.reminder_identity)
    assert not calls and owner.cleanup_complete()


def test_close_before_activation_and_queued_late_callback_have_no_effect(tmp_path):
    store, _, now, pending = _retained_pending(tmp_path)
    now[0] = pending.next_eligible_completed_1h_boundary
    gate = threading.Event(); queued = threading.Event(); calls = []
    def schedule(_delay, operation):
        def run():
            queued.set(); assert gate.wait(3); operation()
        timer = threading.Timer(0, run); timer.start(); return timer
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
        defer_execution=True, scheduler=schedule,
        notification_listener=lambda r: calls.append(r) or "n")
    original = _raw_reminders(store)
    assert owner._activate_execution(); assert queued.wait(2)
    owner.close()
    assert not owner.cleanup_complete()  # Cancel is not thread termination.
    gate.set(); assert owner._wait_closed(time.monotonic() + 2)
    assert not calls and _raw_reminders(store) == original
    with pytest.raises(ValueError, match="CLOSED_OR_FAILED"):
        owner._activate_execution()


@pytest.mark.parametrize("complete_in_budget", [True, False])
def test_actual_entered_callback_cleanup_uses_original_deadline(tmp_path, complete_in_budget):
    from kronos.browser.server import _StartupCleanup
    store, _, now, pending = _retained_pending(tmp_path)
    now[0] = pending.next_eligible_completed_1h_boundary
    entered = threading.Event(); release = threading.Event(); closing = threading.Event()
    def listener(record):
        entered.set(); assert release.wait(4); return "n"
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
        defer_execution=True, notification_listener=listener)
    assert owner._activate_execution(); assert entered.wait(2)
    ledger = _StartupCleanup()
    ledger.own("reminders", owner, "close", lambda o: o.cleanup_complete())
    actual_close = owner.close; close_calls = []
    def close():
        close_calls.append(True); actual_close(); closing.set()
    owner.close = close
    finisher = None
    if complete_in_budget:
        def finish():
            assert closing.wait(2); release.set()
        finisher = threading.Thread(target=finish); finisher.start()
    deadline = time.monotonic() + (.15 if not complete_in_budget else 2)
    try:
        result = ledger.close_one("reminders", _deadline=deadline)
        assert result is complete_in_budget
        assert close_calls == [True]
        row = ledger.snapshot()["reminders"]
        assert row["observation_deadline"] == deadline
        assert row["state"] == ("CREATED_AND_CLEANED" if complete_in_budget else "CLEANUP_UNRESOLVED")
        if not complete_in_budget:
            assert not owner.cleanup_complete()
            assert owner.maintenance_status()["callbacks"] == 1
            assert not ledger.close_one("reminders", _deadline=time.monotonic() + 2)
            assert close_calls == [True]  # No retry or deadline reset.
        _retain_k5_observation(tmp_path, "K5-CALLBACK-CLEANUP.json", dict(
            completion_in_budget=complete_in_budget, acknowledged=result,
            deadline=deadline, ledger=row, status=owner.maintenance_status(),
            close_calls=len(close_calls),
            timer_threads=[dict(identity=h.ident,alive=h.is_alive())
                          for h in owner._handles.values()],
            subsequent_fixture_release_is_not_application_cleanup=not complete_in_budget))
    finally:
        release.set()
        if finisher is not None: finisher.join(2)
        assert owner._wait_closed(time.monotonic() + 2)


def test_callback_before_handle_registration_cannot_be_acknowledged(tmp_path):
    from kronos.browser.server import _StartupCleanup
    store, _, now, pending = _retained_pending(tmp_path)
    now[0] = pending.next_eligible_completed_1h_boundary
    entered = threading.Event(); register = threading.Event(); release = threading.Event()
    def listener(record):
        entered.set(); assert release.wait(4); return "n"
    def schedule(_delay, operation):
        timer = threading.Timer(0, operation); timer.start()
        assert entered.wait(2); assert register.wait(4); return timer
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
        defer_execution=True, scheduler=schedule, notification_listener=listener)
    activation = threading.Thread(target=owner._activate_execution); activation.start()
    assert entered.wait(2)
    try:
        assert not owner._handles and owner.maintenance_status()["scheduling"] == 1
        ledger = _StartupCleanup()
        ledger.own("reminders", owner, "close", lambda o: o.cleanup_complete())
        assert not ledger.close_one("reminders", _deadline=time.monotonic() + .1)
        assert ledger.snapshot()["reminders"]["state"] == "CLEANUP_UNRESOLVED"
        assert not owner.cleanup_complete()
        _retain_k5_observation(tmp_path, "K5-PRE-REGISTRATION-CLEANUP.json", dict(
            ledger=ledger.snapshot()["reminders"],status=owner.maintenance_status(),
            registered_handles=len(owner._handles),
            subsequent_fixture_release_is_not_application_cleanup=True))
    finally:
        register.set(); release.set(); activation.join(2)
        assert not activation.is_alive()
        assert owner._wait_closed(time.monotonic() + 2)


def test_unknown_scheduler_outcome_and_unstarted_handle_never_prove_cleanup(tmp_path):
    store, _, now, pending = _retained_pending(tmp_path)
    def broken(_delay, _operation):
        raise RuntimeError("SCHEDULER_OUTCOME_UNKNOWN")
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
                                          defer_execution=True, scheduler=broken)
    with pytest.raises(RuntimeError, match="OUTCOME_UNKNOWN"):
        owner._activate_execution()
    owner.close()
    assert not owner.cleanup_complete()
    with pytest.raises(ValueError, match="CLOSED_OR_FAILED"):
        owner._activate_execution()
    second = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
        defer_execution=True, scheduler=lambda d, op: threading.Timer(d, op))
    assert second._activate_execution()
    second.close()
    assert not second.cleanup_complete()  # A not-yet-started thread is not proven terminated.


def test_close_before_first_activation_preserves_pending_bytes(tmp_path):
    store, _, now, pending = _retained_pending(tmp_path)
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
                                          defer_execution=True)
    original = _raw_reminders(store)
    owner.close()
    with pytest.raises(ValueError, match="CLOSED_OR_FAILED"):
        owner._activate_execution()
    now[0] = pending.next_eligible_completed_1h_boundary
    owner._fire(pending.reminder_identity)
    owner._fire_owned(pending.reminder_identity)
    assert owner.cleanup_complete()
    assert _raw_reminders(store) == original


def test_actual_timer_preserves_counted_admission_fencing(tmp_path):
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    store, _, now, pending = _retained_pending(tmp_path)
    now[0] = pending.next_eligible_completed_1h_boundary
    admission = MaintenanceAdmissionCoordinator()
    assert admission.claim("a" * 64)
    calls = []
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
        defer_execution=True, maintenance_admission=admission,
        notification_listener=lambda r: calls.append(r) or "n")
    original = _raw_reminders(store)
    assert owner._activate_execution()
    owner.close()
    assert owner._wait_closed(time.monotonic() + 2)
    assert admission.snapshot()["owners"] == {}
    assert not calls and _raw_reminders(store) == original


@pytest.mark.parametrize("operation", ["reconcile", "callback"])
def test_delayed_durable_write_cannot_block_cleanup_before_deadline(tmp_path, operation):
    from kronos.browser.server import _StartupCleanup
    store, _, now, pending = _retained_pending(tmp_path)
    now[0] = pending.next_eligible_completed_1h_boundary
    entered = threading.Event(); release = threading.Event(); replied = threading.Event()
    original_retain = store.retain
    def retain(record):
        entered.set(); assert release.wait(4); return original_retain(record)
    store.retain = retain
    owner = SwingK5RefreshReminderWorkflow(store, clock=lambda: now[0],
        defer_execution=True, notification_listener=lambda r: "n")
    original = _raw_reminders(store)
    errors = []; replies = []; returned_at = []
    def work():
        try:
            if operation == "reconcile": owner.synchronize(None, (), {})
            else: owner._activate_execution()
        except BaseException as error: errors.append(error)
    producer = threading.Thread(target=work); producer.start()
    assert entered.wait(2)
    ledger = _StartupCleanup()
    ledger.own("reminders", owner, "close", lambda o: o.cleanup_complete())
    deadline = time.monotonic() + .1
    def close():
        try: replies.append(ledger.close_one("reminders", _deadline=deadline))
        finally: returned_at.append(time.monotonic()); replied.set()
    closer = threading.Thread(target=close); closer.start()
    try:
        answered_while_write_blocked = replied.wait(.4)
    finally:
        # Explicit fixture release is not an application cleanup acknowledgement.
        release.set(); producer.join(2); closer.join(2)
        assert not producer.is_alive() and not closer.is_alive()
        assert owner._wait_closed(time.monotonic() + 2)
    assert answered_while_write_blocked, "CLOSE_BLOCKED_ON_DURABLE_IO_BEFORE_DEADLINE_OBSERVATION"
    assert not errors and replies == [False]
    assert ledger.snapshot()["reminders"]["state"] == "CLEANUP_UNRESOLVED"
    assert all(_raw_reminders(store)[k] == v for k, v in original.items())
    _retain_k5_observation(tmp_path, "K5-DELAYED-WRITE-CLEANUP.json", dict(
        operation=operation,reply_before_fixture_release=answered_while_write_blocked,
        replies=replies,deadline=deadline,returned_at=returned_at,
        ledger=ledger.snapshot()["reminders"],
        final_status_after_fixture_release=owner.maintenance_status(),
        fixture_release_is_not_application_cleanup=True,
        original_records_preserved=True))
