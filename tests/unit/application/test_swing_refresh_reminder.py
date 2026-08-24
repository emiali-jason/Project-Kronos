from dataclasses import fields
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from kronos.application.swing_refresh_reminder import (
    K5RefreshReminderStore,
    RefreshReminderState,
    SwingK5RefreshReminderWorkflow,
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
    restarted.synchronize(
        promotion.run_identity, (promotion,), {promotion.canonical_instrument: "NSE"}
    )
    assert len(delivered) == 1


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
