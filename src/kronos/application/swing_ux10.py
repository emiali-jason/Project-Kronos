"""Governed Swing UX-10 watches and notification delivery.

This module is a delivery boundary only.  It consumes immutable analytical,
lifecycle, and Provider-connection events; it creates no trading decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock, Thread, Timer
from typing import Callable

from kronos.integrations.telegram import (
    TelegramConfigurationService,
    TelegramDeliveryState,
)
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalClassification,
    Kr370AnalyticalPromotionRecord,
)
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecyclePosition,
    LifecycleEventType,
    TradeLifecycleEvent,
)
from kronos.swing.v1.progression_watch import (
    ProgressionWatch,
    ProgressionWatchState,
)


UX10_NOTIFICATION_CONTRACT = "KRONOS-SWING-UX10-NOTIFICATION-V1"
UX10_NOTIFICATION_VERSION = "1"
UX10_AUTHORITY = "DELIVERY_ONLY_NO_TRADING_OR_EXECUTION_AUTHORITY"
DEFAULT_UX10_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "swing-v1" / "ux10-notifications-v1"
)


class Ux10NotificationFamily(StrEnum):
    PROMOTION_WATCH = "PROMOTION_WATCH"
    ACTIVE_TRADE_WATCH = "ACTIVE_TRADE_WATCH"
    SYSTEM_CONNECTIVITY = "SYSTEM_CONNECTIVITY"


class Ux10NotificationType(StrEnum):
    READY_MONITORING_ACTIVATED = "READY_MONITORING_ACTIVATED"
    ACTIVE_TRADE_MONITORING_ACTIVATED = "ACTIVE_TRADE_MONITORING_ACTIVATED"
    PROMOTION_CONDITION_MET = "PROMOTION_CONDITION_MET"
    ANALYTICAL_NOW_CONFIRMED = "ANALYTICAL_NOW_CONFIRMED"
    STOP_LEVEL_TOUCHED = "STOP_LEVEL_TOUCHED"
    TARGET_LEVEL_TOUCHED = "TARGET_LEVEL_TOUCHED"
    WEBSOCKET_DISCONNECTED = "WEBSOCKET_DISCONNECTED"
    WEBSOCKET_RESTORED = "WEBSOCKET_RESTORED"
    MONITORING_GAP_RECONCILIATION_REQUIRED = "MONITORING_GAP_RECONCILIATION_REQUIRED"


class Ux10Priority(StrEnum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"


class Ux10DeliveryState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"


@dataclass(frozen=True, slots=True)
class Ux10NotificationRecord:
    notification_id: str
    product: str
    family: Ux10NotificationFamily
    notification_type: Ux10NotificationType
    priority: Ux10Priority
    instrument: str | None
    direction: str | None
    run_identity: str | None
    trade_identity: str | None
    lifecycle_mode: str | None
    watch_identity: str | None
    lifecycle_event_identity: str | None
    source_event_identity: str
    summary: str
    action: str
    created_at: datetime
    browser_delivery_state: Ux10DeliveryState
    telegram_delivery_state: Ux10DeliveryState
    deduplication_key: str
    delivery_attempts: int
    next_retry_at: datetime | None
    last_safe_failure: str
    integrity_sha256: str
    contract_identity: str = UX10_NOTIFICATION_CONTRACT
    contract_version: str = UX10_NOTIFICATION_VERSION
    authority: str = UX10_AUTHORITY

    def __post_init__(self) -> None:
        if (
            len(self.notification_id) != 64
            or self.product != "SWING"
            or self.lifecycle_mode not in {None, "LIVE", "PAPER"}
            or type(self.family) is not Ux10NotificationFamily
            or type(self.notification_type) is not Ux10NotificationType
            or type(self.priority) is not Ux10Priority
            or not self.source_event_identity
            or not self.summary
            or not self.action
            or self.created_at.tzinfo is None
            or type(self.browser_delivery_state) is not Ux10DeliveryState
            or type(self.telegram_delivery_state) is not Ux10DeliveryState
            or len(self.deduplication_key) != 64
            or type(self.delivery_attempts) is not int
            or self.delivery_attempts < 0
            or (self.next_retry_at is not None and self.next_retry_at.tzinfo is None)
            or self.contract_identity != UX10_NOTIFICATION_CONTRACT
            or self.contract_version != UX10_NOTIFICATION_VERSION
            or self.authority != UX10_AUTHORITY
            or self.integrity_sha256 != _integrity(self)
        ):
            raise ValueError("UX10_NOTIFICATION_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class Ux10NotificationSnapshot:
    records: tuple[Ux10NotificationRecord, ...]

    @property
    def revision(self) -> str:
        return sha256(json.dumps(tuple(
            (item.notification_id, item.browser_delivery_state.value,
             item.telegram_delivery_state.value, item.delivery_attempts)
            for item in self.records
        ), separators=(",", ":")).encode()).hexdigest()

    @property
    def active_incidents(self) -> tuple[Ux10NotificationRecord, ...]:
        latest = {}
        for item in sorted(self.records, key=lambda value: value.created_at):
            if item.family is Ux10NotificationFamily.SYSTEM_CONNECTIVITY:
                latest[item.watch_identity] = item
        return tuple(
            item for item in latest.values()
            if item.notification_type in {
                Ux10NotificationType.WEBSOCKET_DISCONNECTED,
                Ux10NotificationType.MONITORING_GAP_RECONCILIATION_REQUIRED,
            }
        )


class Ux10NotificationStore:
    """Immutable file store with one current delivery projection per record."""

    def __init__(self, root: Path = DEFAULT_UX10_ROOT) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def retain(self, record: Ux10NotificationRecord) -> None:
        path = self.root / f"{record.notification_id}.json"
        payload = _record_dict(record)
        temporary = path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as target:
                json.dump(payload, target, sort_keys=True, separators=(",", ":"))
                target.flush()
                os.fsync(target.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        except OSError as error:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise ValueError("UX10_NOTIFICATION_PERSISTENCE_FAILED") from error

    def load(self) -> tuple[Ux10NotificationRecord, ...]:
        records = []
        for path in sorted(self.root.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                records.append(_record_from_dict(value))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return tuple(sorted(records, key=lambda item: (item.created_at, item.notification_id)))


class SwingUx10NotificationService:
    """Persist, deduplicate and deliver governed UX-10 notification edges."""

    def __init__(
        self,
        store: Ux10NotificationStore | None = None,
        *,
        telegram: TelegramConfigurationService | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        background_runner: Callable[[Callable[[], None], str], object] | None = None,
        retry_scheduler: Callable[[float, Callable[[], None]], object] | None = None,
    ) -> None:
        self._store = store or Ux10NotificationStore()
        self._telegram = telegram
        self._clock = clock
        self._background = background_runner or _thread_runner
        self._retry_scheduler = retry_scheduler or _timer_scheduler
        self._lock = RLock()
        self._records = {item.deduplication_key: item for item in self._store.load()}
        self._promotion_state: dict[tuple[str, str], tuple[str, str]] = {}
        self._connection_state: dict[str, tuple[MonitoringConnectionState, datetime]] = {}

    def snapshot(self) -> Ux10NotificationSnapshot:
        with self._lock:
            records = tuple(sorted(
                self._records.values(), key=lambda item: (item.created_at, item.notification_id),
                reverse=True,
            ))
        return Ux10NotificationSnapshot(records)

    def observe_progression_watch(self, watch: ProgressionWatch) -> Ux10NotificationRecord | None:
        if watch.state is not ProgressionWatchState.TRIGGERED or watch.trigger_bar is None:
            return None
        return self._create(
            family=Ux10NotificationFamily.PROMOTION_WATCH,
            notification_type=Ux10NotificationType.PROMOTION_CONDITION_MET,
            priority=Ux10Priority.NORMAL,
            instrument=watch.requirement.canonical_instrument,
            direction=watch.requirement.direction.value,
            run_identity=watch.requirement.native_run_identity,
            watch_identity=watch.watch_id,
            source_event_identity=watch.history[-1].event_id,
            summary=(
                f"Completed {watch.trigger_bar.timeframe.value} promotion condition met "
                f"for {watch.requirement.canonical_instrument}."
            ),
            action="REFRESH SWING ANALYSIS — NO TRADE HAS BEEN AUTHORIZED",
        )

    def observe_progression_monitoring_activation(
        self, watch: ProgressionWatch
    ) -> Ux10NotificationRecord | None:
        """Confirm that an eligible READY watch was actually registered."""

        if type(watch) is not ProgressionWatch or watch.state is not ProgressionWatchState.ACTIVE:
            return None
        return self._create(
            family=Ux10NotificationFamily.PROMOTION_WATCH,
            notification_type=Ux10NotificationType.READY_MONITORING_ACTIVATED,
            priority=Ux10Priority.NORMAL,
            instrument=watch.requirement.canonical_instrument,
            direction=watch.requirement.direction.value,
            run_identity=watch.requirement.native_run_identity,
            watch_identity=watch.watch_id,
            source_event_identity=watch.history[0].event_id,
            summary=(
                f"Watching {watch.requirement.condition_identity}; "
                "live monitoring is active."
            ),
            action="MONITORING ACTIVE — SATISFACTION STILL REQUIRES REFRESH ANALYSIS",
            created_at=watch.activated_at,
        )

    def observe_active_trade_monitoring_activation(
        self, position: ActiveLifecyclePosition
    ) -> Ux10NotificationRecord | None:
        """Confirm one successfully attached Stop/Target monitoring binding."""

        if type(position) is not ActiveLifecyclePosition:
            raise TypeError("ACTIVE_TRADE_MONITORING_ACTIVATION_INVALID")
        return self._create(
            family=Ux10NotificationFamily.ACTIVE_TRADE_WATCH,
            notification_type=Ux10NotificationType.ACTIVE_TRADE_MONITORING_ACTIVATED,
            priority=Ux10Priority.NORMAL,
            instrument=position.canonical_instrument,
            direction=position.direction.value,
            trade_identity=position.trade_plan_id,
            lifecycle_mode=position.mode.value,
            watch_identity=position.lifecycle_id,
            lifecycle_event_identity=position.position_id,
            source_event_identity=(
                f"{position.position_id}:{position.trade_plan_id}:"
                f"{position.lifecycle_id}:SL_TARGET_MONITORING"
            ),
            summary="Stop: Watching · Target: Watching",
            action="LIVE MONITORING ACTIVE — LEVEL TOUCHES ARE NOT BROKER FILLS",
            created_at=position.updated_at,
        )

    def observe_promotions(
        self, records: tuple[Kr370AnalyticalPromotionRecord, ...]
    ) -> tuple[Ux10NotificationRecord, ...]:
        created = []
        for record in records:
            key = (record.canonical_instrument, record.direction.value)
            previous = self._promotion_state.get(key)
            current = (record.run_identity, record.classification.value)
            if previous is not None and previous[0] != record.run_identity:
                if (
                    previous[1] in {"BUY_READY", "SELL_READY"}
                    and record.classification in {
                        Kr370AnalyticalClassification.BUY_NOW,
                        Kr370AnalyticalClassification.SELL_NOW,
                    }
                ):
                    value = self._create(
                        family=Ux10NotificationFamily.PROMOTION_WATCH,
                        notification_type=Ux10NotificationType.ANALYTICAL_NOW_CONFIRMED,
                        priority=Ux10Priority.HIGH,
                        instrument=record.canonical_instrument,
                        direction=record.direction.value,
                        run_identity=record.run_identity,
                        source_event_identity=record.integrity_sha256,
                        summary=(
                            f"{record.canonical_instrument} is now "
                            f"{record.classification.value.replace('_', ' ')} under KR-370."
                        ),
                        action="REVIEW CURRENT ANALYSIS — NO ENTRY OR EXECUTION AUTHORITY",
                    )
                    if value is not None:
                        created.append(value)
            self._promotion_state[key] = current
        return tuple(created)

    def observe_lifecycle_event(
        self, event: TradeLifecycleEvent
    ) -> Ux10NotificationRecord | None:
        mapping = {
            LifecycleEventType.STOP_HIT: Ux10NotificationType.STOP_LEVEL_TOUCHED,
            LifecycleEventType.TARGET_HIT: Ux10NotificationType.TARGET_LEVEL_TOUCHED,
        }
        event_type = mapping.get(event.event_type)
        if event_type is None:
            return None
        level = event.stop if event.event_type is LifecycleEventType.STOP_HIT else event.target
        return self._create(
            family=Ux10NotificationFamily.ACTIVE_TRADE_WATCH,
            notification_type=event_type,
            priority=Ux10Priority.HIGH,
            instrument=event.instrument,
            direction=event.direction.value,
            trade_identity=event.position_id,
            lifecycle_mode=event.mode.value,
            lifecycle_event_identity=event.event_id,
            source_event_identity=event.event_id,
            summary=f"{'Stop' if event.event_type is LifecycleEventType.STOP_HIT else 'Target'}: ₹{level}",
            action="OPEN KRONOS FOR TRADE STATUS — FACTUAL LEVEL TOUCH, NOT A FILL",
        )

    def observe_connection_state(
        self,
        watch_identity: str,
        instrument: str,
        state: MonitoringConnectionState,
        *,
        occurred_at: datetime | None = None,
    ) -> Ux10NotificationRecord | None:
        now = occurred_at or self._clock()
        previous = self._connection_state.get(watch_identity)
        self._connection_state[watch_identity] = (state, now)
        if previous is not None and previous[0] is state:
            return None
        outage_states = {
            MonitoringConnectionState.DISCONNECTED,
            MonitoringConnectionState.RECONNECTING,
        }
        if previous is not None and previous[0] in outage_states and state in outage_states:
            return None
        if state in {MonitoringConnectionState.DISCONNECTED, MonitoringConnectionState.RECONNECTING}:
            event_type = Ux10NotificationType.WEBSOCKET_DISCONNECTED
            priority = Ux10Priority.HIGH
            summary = f"Live market monitoring disconnected for {instrument}."
            action = "MONITORING MAY BE INCOMPLETE — DO NOT INFER MISSED EVENTS"
        elif state is MonitoringConnectionState.CONTEXT_INCOMPLETE:
            event_type = Ux10NotificationType.MONITORING_GAP_RECONCILIATION_REQUIRED
            priority = Ux10Priority.HIGH
            summary = f"Monitoring gap requires reconciliation for {instrument}."
            action = "RECONCILE THE GOVERNED GAP BEFORE RELYING ON NEW OBSERVATIONS"
        elif state is MonitoringConnectionState.CONNECTED and previous is not None:
            event_type = Ux10NotificationType.WEBSOCKET_RESTORED
            priority = Ux10Priority.NORMAL
            duration = max(0, int((now - previous[1]).total_seconds()))
            summary = f"Market-data monitoring restored for {instrument} after {duration}s."
            action = "SUBSCRIPTION RESTORED; GAP RULES REMAIN FAIL-CLOSED"
        else:
            return None
        source = sha256(
            f"{watch_identity}:{state.value}:{now.isoformat()}".encode()
        ).hexdigest()
        return self._create(
            family=Ux10NotificationFamily.SYSTEM_CONNECTIVITY,
            notification_type=event_type,
            priority=priority,
            instrument=instrument,
            watch_identity=watch_identity,
            source_event_identity=source,
            summary=summary,
            action=action,
            created_at=now,
        )

    def retry_pending(self) -> None:
        if (
            self._telegram is None
            or not self._telegram.status().delivery_enabled
        ):
            return
        now = self._clock()
        with self._lock:
            pending = tuple(
                item for item in self._records.values()
                if item.telegram_delivery_state in {
                    Ux10DeliveryState.PENDING,
                    Ux10DeliveryState.FAILED_RETRYABLE,
                }
                and item.delivery_attempts < 4
                and (item.next_retry_at is None or item.next_retry_at <= now)
            )
        for record in pending:
            self._schedule_delivery(record.deduplication_key)

    def _create(
        self,
        *,
        family: Ux10NotificationFamily,
        notification_type: Ux10NotificationType,
        priority: Ux10Priority,
        source_event_identity: str,
        summary: str,
        action: str,
        instrument: str | None = None,
        direction: str | None = None,
        run_identity: str | None = None,
        trade_identity: str | None = None,
        lifecycle_mode: str | None = None,
        watch_identity: str | None = None,
        lifecycle_event_identity: str | None = None,
        created_at: datetime | None = None,
    ) -> Ux10NotificationRecord | None:
        dedup = sha256(
            f"SWING:{notification_type.value}:{source_event_identity}".encode()
        ).hexdigest()
        with self._lock:
            if dedup in self._records:
                return None
        now = created_at or self._clock()
        telegram_status = (
            self._telegram.status() if self._telegram is not None else None
        )
        telegram_state = (
            Ux10DeliveryState.PENDING
            if telegram_status is not None and telegram_status.private_chat_configured
            else Ux10DeliveryState.NOT_CONFIGURED
        )
        values = dict(
            notification_id=sha256(f"UX10:{dedup}".encode()).hexdigest(),
            product="SWING", family=family, notification_type=notification_type,
            priority=priority, instrument=instrument, direction=direction,
            run_identity=run_identity, trade_identity=trade_identity,
            lifecycle_mode=lifecycle_mode,
            watch_identity=watch_identity,
            lifecycle_event_identity=lifecycle_event_identity,
            source_event_identity=source_event_identity, summary=summary, action=action,
            created_at=now, browser_delivery_state=Ux10DeliveryState.SENT,
            telegram_delivery_state=telegram_state, deduplication_key=dedup,
            delivery_attempts=0, next_retry_at=None, last_safe_failure="",
            integrity_sha256="",
        )
        record = Ux10NotificationRecord(**(values | {"integrity_sha256": _integrity_values(values)}))
        self._store.retain(record)
        with self._lock:
            self._records[dedup] = record
        if (
            telegram_state is Ux10DeliveryState.PENDING
            and telegram_status is not None
            and telegram_status.delivery_enabled
        ):
            self._schedule_delivery(dedup)
        return record

    def _schedule_delivery(self, dedup: str) -> None:
        self._background(lambda: self._deliver(dedup), "kronos-ux10-telegram")

    def _deliver(self, dedup: str) -> None:
        with self._lock:
            record = self._records.get(dedup)
        if (
            record is None
            or self._telegram is None
            or not self._telegram.status().delivery_enabled
            or record.telegram_delivery_state is Ux10DeliveryState.SENT
        ):
            return
        result = self._telegram.send(_telegram_message(record))
        attempts = record.delivery_attempts + 1
        if result.state is TelegramDeliveryState.SENT:
            state = Ux10DeliveryState.SENT
            retry_at = None
        elif result.state is TelegramDeliveryState.FAILED_RETRYABLE and attempts < 4:
            state = Ux10DeliveryState.FAILED_RETRYABLE
            delay = result.retry_after_seconds or min(300, 5 * (2 ** (attempts - 1)))
            retry_at = self._clock() + timedelta(seconds=delay)
        else:
            state = Ux10DeliveryState.FAILED_FINAL
            retry_at = None
        values = asdict(record)
        values.update(
            telegram_delivery_state=state,
            delivery_attempts=attempts,
            next_retry_at=retry_at,
            last_safe_failure=result.safe_reason,
            integrity_sha256="",
        )
        updated = Ux10NotificationRecord(**(values | {"integrity_sha256": _integrity_values(values)}))
        self._store.retain(updated)
        with self._lock:
            self._records[dedup] = updated
        if state is Ux10DeliveryState.FAILED_RETRYABLE and retry_at is not None:
            delay = max(0.0, (retry_at - self._clock()).total_seconds())
            self._retry_scheduler(delay, lambda: self._schedule_delivery(dedup))


def _telegram_message(record: Ux10NotificationRecord) -> str:
    mode = ""
    if record.family is Ux10NotificationFamily.ACTIVE_TRADE_WATCH:
        mode = f" · {record.lifecycle_mode or 'ACTIVE TRADE'}"
    event = record.notification_type.value.replace("_", " ")
    if record.notification_type is Ux10NotificationType.ANALYTICAL_NOW_CONFIRMED:
        event = "BUY NOW" if record.direction == "LONG" else "SELL NOW"
    lines = [f"KRONOS · SWING{mode}", event]
    if record.instrument:
        lines[1] += f" — {record.instrument}"
        if record.direction:
            lines.append(record.direction)
    lines.extend((record.summary, record.action))
    return "\n".join(lines)


def _record_dict(record: Ux10NotificationRecord) -> dict[str, object]:
    values = asdict(record)
    for key in ("family", "notification_type", "priority", "browser_delivery_state", "telegram_delivery_state"):
        values[key] = getattr(record, key).value
    values["created_at"] = record.created_at.isoformat()
    values["next_retry_at"] = record.next_retry_at.isoformat() if record.next_retry_at else None
    return values


def _record_from_dict(value: object) -> Ux10NotificationRecord:
    if not isinstance(value, dict):
        raise ValueError("UX10_NOTIFICATION_RECORD_INVALID")
    values = dict(value)
    values["family"] = Ux10NotificationFamily(values["family"])
    values["notification_type"] = Ux10NotificationType(values["notification_type"])
    values["priority"] = Ux10Priority(values["priority"])
    values["browser_delivery_state"] = Ux10DeliveryState(values["browser_delivery_state"])
    values["telegram_delivery_state"] = Ux10DeliveryState(values["telegram_delivery_state"])
    values["created_at"] = datetime.fromisoformat(values["created_at"])
    values["next_retry_at"] = (
        datetime.fromisoformat(values["next_retry_at"])
        if values.get("next_retry_at") else None
    )
    return Ux10NotificationRecord(**values)


def _integrity(record: Ux10NotificationRecord) -> str:
    values = asdict(record)
    values["integrity_sha256"] = ""
    return _integrity_values(values)


def _integrity_values(values: dict[str, object]) -> str:
    material = dict(values)
    material.setdefault("contract_identity", UX10_NOTIFICATION_CONTRACT)
    material.setdefault("contract_version", UX10_NOTIFICATION_VERSION)
    material.setdefault("authority", UX10_AUTHORITY)
    material["integrity_sha256"] = ""
    return sha256(json.dumps(material, sort_keys=True, default=_json_default, separators=(",", ":")).encode()).hexdigest()


def _json_default(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError


def _thread_runner(operation: Callable[[], None], name: str) -> Thread:
    thread = Thread(target=operation, name=name, daemon=True)
    thread.start()
    return thread


def _timer_scheduler(delay: float, operation: Callable[[], None]) -> Timer:
    timer = Timer(delay, operation)
    timer.daemon = True
    timer.start()
    return timer


__all__ = [
    "SwingUx10NotificationService", "Ux10DeliveryState",
    "Ux10NotificationFamily", "Ux10NotificationRecord", "Ux10NotificationSnapshot",
    "Ux10NotificationStore", "Ux10NotificationType", "Ux10Priority",
]
