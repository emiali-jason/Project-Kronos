from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from kronos.application.swing_ux10 import (
    SwingUx10NotificationService,
    Ux10DeliveryState,
    Ux10NotificationFamily,
    Ux10NotificationStore,
    Ux10NotificationType,
    Ux10Priority,
)
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.integrations.telegram import (
    TelegramConfigurationState,
    TelegramConfigurationStatus,
    TelegramDeliveryResult,
    TelegramDeliveryState,
)
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalClassification,
    Kr370AnalyticalPromotionRecord,
    kr370_promotion_integrity_sha256,
)
from kronos.swing.v1.analytical_promotion_v2 import create_record
from tests.unit.swing.v1.test_analytical_promotion_v2 import (
    source as v2_source, criteria as v2_criteria, nse as v2_nse,
)
from kronos.swing.v1.native_active_trade_lifecycle import ActiveTradeLifecycleEngine
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from tests.unit.browser.test_browser_notifications import _triggered
from tests.unit.swing.v1.test_kr370_step31_handoff import _completed
from tests.unit.swing.v1.test_native_active_trade_lifecycle import _observation, _position


NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
RUN_1 = "SWING-RUN-11111111111111111111111111111111"
RUN_2 = "SWING-RUN-22222222222222222222222222222222"


def test_v2_exact_ready_to_now_notification_preserves_promotion_identity(tmp_path) -> None:
    def confirmation_for(run):
        confirmation = v2_nse()
        confirmation["nse_binding"]["payload"]["run_identity"] = run
        return confirmation

    first_source = v2_source()
    first_source["native_run_identity"] = RUN_1
    ready = create_record(
        source=first_source, criteria=v2_criteria(4),
        confirmation=confirmation_for(RUN_1), created_at=NOW)
    second_source = v2_source()
    second_source["native_run_identity"] = RUN_2
    now = create_record(
        source=second_source, criteria=v2_criteria(),
        confirmation=confirmation_for(RUN_2), created_at=NOW)
    service = ux10(tmp_path)
    assert service.observe_promotions((ready,)) == ()
    created = service.observe_promotions((now,))
    assert len(created) == 1
    assert created[0].notification_type is Ux10NotificationType.ANALYTICAL_NOW_CONFIRMED
    assert created[0].source_event_identity == now.value["integrity_sha256"]
    assert service.observe_promotions((now,)) == ()


class Telegram:
    def __init__(self, results=(), *, enabled=True) -> None:  # type: ignore[no-untyped-def]
        self.messages = []
        self.results = list(results)
        self.enabled = enabled

    def status(self):  # type: ignore[no-untyped-def]
        return TelegramConfigurationStatus(
            (
                TelegramConfigurationState.READY
                if self.enabled else TelegramConfigurationState.DISCONNECTED
            ),
            True, True, delivery_enabled=self.enabled,
        )

    def send(self, text):  # type: ignore[no-untyped-def]
        self.messages.append(text)
        if self.results:
            return self.results.pop(0)
        return TelegramDeliveryResult(TelegramDeliveryState.SENT)


def immediate(operation, _name):  # type: ignore[no-untyped-def]
    operation()


def ux10(tmp_path: Path, telegram=None):  # type: ignore[no-untyped-def]
    return SwingUx10NotificationService(
        Ux10NotificationStore(tmp_path), telegram=telegram,
        clock=lambda: NOW, background_runner=immediate,
        retry_scheduler=lambda _delay, _operation: None,
    )


def test_canonical_delivery_deferral_blocks_creation_retry_and_direct_worker_entry(tmp_path: Path) -> None:
    telegram = Telegram()
    service = SwingUx10NotificationService(
        Ux10NotificationStore(tmp_path), telegram=telegram, clock=lambda: NOW,
        background_runner=immediate, retry_scheduler=lambda _delay, _operation: None,
        defer_delivery=True,
    )

    record = service.observe_progression_watch(_triggered("CANBK"))
    assert record is not None
    assert record.telegram_delivery_state is Ux10DeliveryState.PENDING
    assert service.delivery_deferred
    assert telegram.messages == []
    assert Ux10NotificationStore(tmp_path).load() == (record,)

    service.retry_pending()
    service._retry_due(record.deduplication_key)
    service._schedule_delivery(record.deduplication_key)
    service._deliver(record.deduplication_key)
    retained = Ux10NotificationStore(tmp_path).load()[0]
    assert retained == record
    assert retained.delivery_attempts == 0
    assert telegram.messages == []

    assert service.activate_delivery() is True
    assert service.activate_delivery() is False
    service.retry_pending()
    assert len(telegram.messages) == 1
    assert service.snapshot().records[0].telegram_delivery_state is Ux10DeliveryState.SENT
    service.close()


def test_deferred_owner_restores_pending_work_and_closed_owner_cannot_activate(tmp_path: Path) -> None:
    unavailable = Telegram(enabled=False)
    seed = ux10(tmp_path, unavailable)
    original = seed.observe_progression_watch(_triggered("CANBK"))
    assert original.telegram_delivery_state is Ux10DeliveryState.PENDING
    seed.close()

    telegram = Telegram()
    restored = SwingUx10NotificationService(
        Ux10NotificationStore(tmp_path), telegram=telegram, clock=lambda: NOW,
        background_runner=immediate, defer_delivery=True,
    )
    assert restored.snapshot().records == (original,)
    assert telegram.messages == []
    restored.close()
    with pytest.raises(ValueError, match="UX10_DELIVERY_OWNER_CLOSED"):
        restored.activate_delivery()
    assert telegram.messages == []
    assert Ux10NotificationStore(tmp_path).load() == (original,)


def test_deferred_activation_enqueue_and_close_keep_one_counted_worker(tmp_path: Path) -> None:
    queued = []
    admission = MaintenanceAdmissionCoordinator()
    telegram = Telegram()
    service = SwingUx10NotificationService(
        Ux10NotificationStore(tmp_path), telegram=telegram, clock=lambda: NOW,
        background_runner=lambda operation, _name: queued.append(operation),
        maintenance_admission=admission, defer_delivery=True,
    )
    watch = _triggered("CANBK")
    record = service.observe_progression_watch(watch)
    assert record is not None

    barrier = __import__("threading").Barrier(4)
    errors = []
    def call(operation):
        barrier.wait()
        try:
            operation()
        except BaseException as error:
            errors.append(error)
    threads = [
        __import__("threading").Thread(target=call, args=(service.activate_delivery,)),
        __import__("threading").Thread(target=call, args=(service.activate_delivery,)),
        __import__("threading").Thread(target=call, args=(service.retry_pending,)),
        __import__("threading").Thread(target=call, args=(lambda: service.observe_progression_watch(watch),)),
    ]
    for thread in threads: thread.start()
    for thread in threads: thread.join(2)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(queued) == 1
    assert admission.snapshot()["owners"] == {"NOTIFICATION": 1}

    service.close()
    assert admission.snapshot()["owners"] == {"NOTIFICATION": 1}
    queued.pop()()
    assert admission.snapshot()["owners"] == {}
    retained = Ux10NotificationStore(tmp_path).load()
    assert retained == (record,)
    assert retained[0].telegram_delivery_state is Ux10DeliveryState.PENDING
    assert retained[0].delivery_attempts == 0
    assert telegram.messages == []


def test_activation_failure_is_sticky_and_blocks_earlier_queued_delivery(tmp_path: Path) -> None:
    queued = []
    admission = MaintenanceAdmissionCoordinator()
    telegram = Telegram()

    def submit(operation, _name):
        if queued:
            raise RuntimeError("UX10_SECOND_SCHEDULE_FAILED")
        queued.append(operation)

    service = SwingUx10NotificationService(
        Ux10NotificationStore(tmp_path), telegram=telegram, clock=lambda: NOW,
        background_runner=submit, retry_scheduler=lambda _delay, _operation: None,
        maintenance_admission=admission, defer_delivery=True,
    )
    first = service.observe_progression_watch(_triggered("CANBK"))
    second = service._create(
        family=Ux10NotificationFamily.PROMOTION_WATCH,
        notification_type=Ux10NotificationType.PROMOTION_CONDITION_MET,
        priority=Ux10Priority.NORMAL,
        instrument="INFY",
        source_event_identity="C01-DISPOSABLE-SECOND-SOURCE",
        summary="C01 distinct pending fixture.",
        action="NO TRADE HAS BEEN AUTHORIZED",
    )
    assert first is not None and second is not None
    before = Ux10NotificationStore(tmp_path).load()
    assert len(before) == 2
    assert all(item.telegram_delivery_state is Ux10DeliveryState.PENDING
               and item.delivery_attempts == 0 for item in before)

    with pytest.raises(RuntimeError, match="UX10_SECOND_SCHEDULE_FAILED"):
        service.activate_delivery()

    assert service._delivery_activation_failed is True
    assert service._delivery_active is False
    assert len(queued) == 1  # The first worker is submitted but not yet claimed.
    assert admission.snapshot()["owners"] == {"NOTIFICATION": 1}

    with pytest.raises(ValueError, match="UX10_DELIVERY_ACTIVATION_FAILED"):
        service.activate_delivery()
    third = service._create(
        family=Ux10NotificationFamily.PROMOTION_WATCH,
        notification_type=Ux10NotificationType.PROMOTION_CONDITION_MET,
        priority=Ux10Priority.NORMAL,
        instrument="TCS",
        source_event_identity="C01-DISPOSABLE-THIRD-SOURCE",
        summary="C01 enqueue after failed activation.",
        action="NO TRADE HAS BEEN AUTHORIZED",
    )
    assert third is not None  # New facts are retained, but cannot be dispatched.
    service.retry_pending()
    service._retry_due(first.deduplication_key)
    service._schedule_delivery(first.deduplication_key)
    service._deliver(first.deduplication_key)
    assert len(queued) == 1
    assert telegram.messages == []

    queued.pop()()  # The already-submitted, still-unclaimed worker is denied.
    assert admission.snapshot()["owners"] == {}
    after = Ux10NotificationStore(tmp_path).load()
    assert len(after) == 3
    for original in before:
        retained = next(item for item in after if item.deduplication_key == original.deduplication_key)
        assert retained == original
        assert retained.delivery_attempts == 0
        assert retained.telegram_delivery_state is Ux10DeliveryState.PENDING
    assert telegram.messages == []
    service.close()


def test_activation_clock_failure_latches_owner_before_propagating_original_exception(
    tmp_path: Path,
) -> None:
    telegram = Telegram()
    service = SwingUx10NotificationService(
        Ux10NotificationStore(tmp_path), telegram=telegram, clock=lambda: NOW,
        background_runner=immediate, defer_delivery=True,
    )
    original = service.observe_progression_watch(_triggered("CANBK"))
    assert original is not None
    before = Ux10NotificationStore(tmp_path).load()

    failure = RuntimeError("UX10_ACTIVATION_CLOCK_FAILED")
    def failed_clock():
        raise failure
    service._clock = failed_clock

    with pytest.raises(RuntimeError, match="UX10_ACTIVATION_CLOCK_FAILED") as raised:
        service.activate_delivery()
    assert raised.value is failure
    assert service._delivery_activation_failed is True
    assert service._delivery_active is False

    with pytest.raises(ValueError, match="UX10_DELIVERY_ACTIVATION_FAILED"):
        service.activate_delivery()
    service.retry_pending()
    service._schedule_delivery(original.deduplication_key)
    service._retry_due(original.deduplication_key)
    service._deliver(original.deduplication_key)

    assert Ux10NotificationStore(tmp_path).load() == before
    assert service.snapshot().records == before
    assert before[0].telegram_delivery_state is Ux10DeliveryState.PENDING
    assert before[0].delivery_attempts == 0
    assert telegram.messages == []


def test_completed_bar_trigger_creates_one_reassessment_only_notification(tmp_path: Path) -> None:
    service = ux10(tmp_path)
    watch = _triggered("CANBK")
    record = service.observe_progression_watch(watch)
    assert record.notification_type is Ux10NotificationType.PROMOTION_CONDITION_MET
    assert record.family is Ux10NotificationFamily.PROMOTION_WATCH
    assert record.priority is Ux10Priority.NORMAL
    assert record.instrument == "CANBK"
    assert record.browser_delivery_state is Ux10DeliveryState.SENT
    assert "REFRESH SWING ANALYSIS" in record.action
    assert "NO TRADE HAS BEEN AUTHORIZED" in record.action
    assert service.observe_progression_watch(watch) is None
    assert len(service.snapshot().records) == 1


def test_disconnected_telegram_preserves_browser_notification_without_delivery(
    tmp_path: Path,
) -> None:
    telegram = Telegram(enabled=False)
    service = ux10(tmp_path, telegram)

    record = service.observe_progression_watch(_triggered("CANBK"))

    assert record is not None
    assert record.browser_delivery_state is Ux10DeliveryState.SENT
    assert record.telegram_delivery_state is Ux10DeliveryState.PENDING
    assert telegram.messages == []


def test_non_triggered_watch_does_not_notify(tmp_path: Path) -> None:
    from kronos.swing.v1.progression_watch import activate_watch
    from tests.unit.browser.test_browser_notifications import _requirement

    watch = activate_watch(_requirement("CANBK", "9"), activated_at=NOW)
    assert ux10(tmp_path).observe_progression_watch(watch) is None


def test_ready_monitoring_activation_is_durable_exactly_once_and_restart_safe(
    tmp_path: Path,
) -> None:
    from kronos.swing.v1.progression_watch import activate_watch
    from tests.unit.browser.test_browser_notifications import _requirement

    telegram = Telegram()
    root = tmp_path / "notifications"
    watch = activate_watch(_requirement("CANBK", "9"), activated_at=NOW)
    service = ux10(root, telegram)

    record = service.observe_progression_monitoring_activation(watch)

    assert record is not None
    assert record.notification_type is Ux10NotificationType.READY_MONITORING_ACTIVATED
    assert record.watch_identity == watch.watch_id
    assert "live monitoring is active" in record.summary
    assert len(telegram.messages) == 1
    assert "READY MONITORING ACTIVATED" in telegram.messages[0]
    assert service.observe_progression_monitoring_activation(watch) is None
    restored = ux10(root, telegram)
    assert restored.observe_progression_monitoring_activation(watch) is None
    assert len(telegram.messages) == 1


def test_active_trade_monitoring_activation_binds_plan_position_and_lifecycle(
    tmp_path: Path,
) -> None:
    position, *_ = _position(SponsorTradeChoice.PAPER)
    telegram = Telegram()
    service = ux10(tmp_path, telegram)

    record = service.observe_active_trade_monitoring_activation(position)

    assert record is not None
    assert record.notification_type is Ux10NotificationType.ACTIVE_TRADE_MONITORING_ACTIVATED
    assert record.trade_identity == position.trade_plan_id
    assert record.lifecycle_event_identity == position.position_id
    assert record.watch_identity == position.lifecycle_id
    assert record.summary == "Stop: Watching · Target: Watching"
    assert len(telegram.messages) == 1
    assert service.observe_active_trade_monitoring_activation(position) is None


def _promotion(template, run, classification):  # type: ignore[no-untyped-def]
    payload = {field.name: getattr(template, field.name) for field in fields(template)}
    payload.update(run_identity=run, classification=classification)
    payload["integrity_sha256"] = kr370_promotion_integrity_sha256(payload)
    return Kr370AnalyticalPromotionRecord(**payload)


def test_only_fresh_ready_to_now_transition_notifies(tmp_path: Path) -> None:
    ready = _completed(tmp_path / "ready", extended=True).promotion
    now = _completed(tmp_path / "now").promotion
    assert ready and now
    ready = _promotion(ready, RUN_1, Kr370AnalyticalClassification.BUY_READY)
    now = _promotion(now, RUN_2, Kr370AnalyticalClassification.BUY_NOW)
    service = ux10(tmp_path / "notifications")
    assert service.observe_promotions((ready,)) == ()
    created = service.observe_promotions((now,))
    assert len(created) == 1
    assert created[0].notification_type is Ux10NotificationType.ANALYTICAL_NOW_CONFIRMED
    assert created[0].priority is Ux10Priority.HIGH
    assert "NO ENTRY OR EXECUTION AUTHORITY" in created[0].action
    assert service.observe_promotions((now,)) == ()


@pytest.mark.parametrize(
    ("before_args", "after_args"),
    (
        ({"cpr_accepted": False, "path_clear": False}, {}),
        ({"extended": True}, {"extended": True}),
        ({}, {}),
    ),
)
def test_non_ready_to_now_transitions_do_not_notify(
    tmp_path: Path, before_args, after_args,
) -> None:  # type: ignore[no-untyped-def]
    before = _completed(tmp_path / "before", **before_args).promotion
    after = _completed(tmp_path / "after", **after_args).promotion
    assert before and after
    service = ux10(tmp_path / "notifications")
    service.observe_promotions((_promotion(before, RUN_1, before.classification),))
    assert service.observe_promotions(
        (_promotion(after, RUN_2, after.classification),)
    ) == ()


@pytest.mark.parametrize(
    ("price", "expected"),
    (("122", Ux10NotificationType.TARGET_LEVEL_TOUCHED),
     ("88", Ux10NotificationType.STOP_LEVEL_TOUCHED)),
)
def test_live_stop_and_target_events_notify_without_mutating_lifecycle(
    tmp_path: Path, price: str, expected: Ux10NotificationType,
) -> None:
    position, *_ = _position(
        SponsorTradeChoice.LIVE, actual_live_entry=Decimal("101"), live_lots=1
    )
    updated, events, _, closure = ActiveTradeLifecycleEngine.observe(
        position, _observation(position, 1, price)
    )
    before = updated
    record = ux10(tmp_path).observe_lifecycle_event(events[0])
    assert record.notification_type is expected
    label = (
        "Stop:"
        if expected is Ux10NotificationType.STOP_LEVEL_TOUCHED
        else "Target:"
    )
    assert record.summary.startswith(label)
    assert "NOT A FILL" in record.action
    assert record.lifecycle_mode == "LIVE"
    assert updated == before and closure is None


@pytest.mark.parametrize(
    "state",
    (
        MonitoringConnectionState.DISCONNECTED,
        MonitoringConnectionState.RECONNECTING,
        MonitoringConnectionState.CONTEXT_INCOMPLETE,
    ),
)
def test_connectivity_failures_are_high_priority_and_deduplicated(
    tmp_path: Path, state: MonitoringConnectionState,
) -> None:
    service = ux10(tmp_path)
    record = service.observe_connection_state("WATCH-1", "RELIANCE", state)
    assert record.priority is Ux10Priority.HIGH
    assert record.family is Ux10NotificationFamily.SYSTEM_CONNECTIVITY
    assert service.observe_connection_state("WATCH-1", "RELIANCE", state) is None


def test_restore_records_outage_duration_and_clears_active_incident(tmp_path: Path) -> None:
    service = SwingUx10NotificationService(
        Ux10NotificationStore(tmp_path), clock=lambda: NOW,
        background_runner=immediate,
    )
    service.observe_connection_state(
        "WATCH-1", "RELIANCE", MonitoringConnectionState.DISCONNECTED,
        occurred_at=NOW,
    )
    restored = service.observe_connection_state(
        "WATCH-1", "RELIANCE", MonitoringConnectionState.CONNECTED,
        occurred_at=NOW + timedelta(seconds=17),
    )
    assert restored.notification_type is Ux10NotificationType.WEBSOCKET_RESTORED
    assert "17s" in restored.summary
    assert service.snapshot().active_incidents == ()


def test_restart_recovers_sent_records_without_historical_spam(tmp_path: Path) -> None:
    telegram = Telegram()
    first = ux10(tmp_path, telegram)
    first.observe_progression_watch(_triggered("CANBK"))
    assert len(telegram.messages) == 1
    restored = ux10(tmp_path, telegram)
    restored.retry_pending()
    assert len(restored.snapshot().records) == 1
    assert len(telegram.messages) == 1


def test_retryable_delivery_is_persisted_and_bounded(tmp_path: Path) -> None:
    telegram = Telegram((
        TelegramDeliveryResult(
            TelegramDeliveryState.FAILED_RETRYABLE, "TELEGRAM_RATE_LIMITED", 1
        ),
    ))
    service = ux10(tmp_path, telegram)
    service.observe_progression_watch(_triggered("CANBK"))
    record = service.snapshot().records[0]
    assert record.telegram_delivery_state is Ux10DeliveryState.FAILED_RETRYABLE
    assert record.delivery_attempts == 1
    assert record.next_retry_at == NOW + timedelta(seconds=1)
    assert record.last_safe_failure == "TELEGRAM_RATE_LIMITED"


def test_maintenance_cancels_retry_timer_without_losing_durable_retry(tmp_path: Path) -> None:
    import threading

    scheduled = []

    class TimerHandle:
        cancelled = False
        finished = False
        thread = None

        def cancel(self) -> None:
            self.cancelled = True

        def is_alive(self) -> bool:
            return not self.finished

    handle = TimerHandle()

    def schedule(_delay, operation):  # type: ignore[no-untyped-def]
        def callback():
            try:
                operation()
            finally:
                handle.finished = True
        scheduled.append(callback)
        return handle

    admission = MaintenanceAdmissionCoordinator()
    telegram = Telegram((TelegramDeliveryResult(
        TelegramDeliveryState.FAILED_RETRYABLE, "TELEGRAM_RATE_LIMITED", 1
    ),))
    service = SwingUx10NotificationService(
        Ux10NotificationStore(tmp_path), telegram=telegram,
        clock=lambda: NOW, background_runner=immediate,
        retry_scheduler=schedule, maintenance_admission=admission,
    )
    service.observe_progression_watch(_triggered("CANBK"))
    assert service.maintenance_status() == {"closed": False, "retry_callbacks": 1}
    assert len(scheduled) == 1
    entered = threading.Event()
    release = threading.Event()
    original_due = service._retry_due

    def blocked_due(dedup):
        entered.set()
        assert release.wait(2)
        return original_due(dedup)

    service._retry_due = blocked_due

    operation = scheduled[0]

    def run_callback():
        try:
            operation()
        finally:
            pass

    handle.thread = threading.Thread(target=run_callback)
    handle.thread.start()
    assert entered.wait(2)
    generation = "d" * 64
    assert admission.claim(generation)
    admission.draining(generation)
    service.close()
    assert handle.cancelled
    assert service.maintenance_status() == {"closed": True, "retry_callbacks": 1}
    release.set()
    handle.thread.join(2)
    assert not handle.thread.is_alive()
    assert len(telegram.messages) == 1
    assert service.maintenance_status() == {"closed": True, "retry_callbacks": 0}
    assert Ux10NotificationStore(tmp_path).load()[0].next_retry_at is not None
    assert admission.wait_for_zero(generation, 0)


def test_telegram_message_has_product_identity_and_no_trading_command(tmp_path: Path) -> None:
    telegram = Telegram()
    service = ux10(tmp_path, telegram)
    service.observe_progression_watch(_triggered("CANBK"))
    message = telegram.messages[0]
    assert message.startswith("KRONOS · SWING\n")
    for prohibited in ("PLACE ORDER", "BUY NOW", "SELL NOW", "ENTER NOW"):
        assert prohibited not in message


def test_store_permissions_integrity_and_no_sensitive_fields(tmp_path: Path) -> None:
    record = ux10(tmp_path).observe_progression_watch(_triggered("CANBK"))
    path = tmp_path / f"{record.notification_id}.json"
    assert path.stat().st_mode & 0o777 == 0o600
    payload = path.read_text()
    assert record.integrity_sha256 in payload
    for forbidden in ("access_token", "request_token", "instrument_token", "api_secret"):
        assert forbidden not in payload.lower()


def test_no_broker_or_analytical_mutation_methods_exist() -> None:
    prohibited = {
        "place_order", "modify_order", "cancel_order", "run_analysis",
        "evaluate_readiness", "construct_trade_plan",
    }
    assert prohibited.isdisjoint(dir(SwingUx10NotificationService))
