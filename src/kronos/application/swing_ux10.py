"""Governed Swing UX-10 watches and notification delivery.

This module is a delivery boundary only.  It consumes immutable analytical,
lifecycle, and Provider-connection events; it creates no trading decision.
"""

from __future__ import annotations

from kronos.common.maintenance import defer_expected_disconnect

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock, Thread, Timer
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from typing import Callable

from kronos.integrations.telegram import (
    TelegramConfigurationService,
    TelegramDeliveryState,
)
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalPromotionRecord,
)
from kronos.swing.v1.analytical_promotion_v2 import V2PromotionRecord
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecyclePosition,
    LifecycleEventType,
    TradeLifecycleEvent,
)
from kronos.swing.v1.progression_watch import (
    ProgressionWatch,
    ProgressionWatchState,
)
from kronos.application.swing_refresh_reminder import K5RefreshReminderRecord


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
    ANALYSIS_REMINDER = "ANALYSIS_REMINDER"


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
    REFRESH_ANALYSIS_REMINDER = "REFRESH_ANALYSIS_REMINDER"


class Ux10Priority(StrEnum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"


class Ux10DeliveryState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    DELIVERY_UNCERTAIN = "DELIVERY_UNCERTAIN"


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
    delivery_attempt_identity: str | None = None
    delivery_protocol: str | None = None

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
            or self.delivery_protocol not in {None, "RETAINED_ATTEMPT_V1"}
            or (self.delivery_attempt_identity is not None and len(self.delivery_attempt_identity) != 64)
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
            _sync_directory(self.root)
        except OSError as error:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise ValueError("UX10_NOTIFICATION_PERSISTENCE_FAILED") from error

    def retain_context(self, name: str, value: dict) -> None:
        """Existing UX10 writer retains recovery context separately from events."""
        directory = self.root / "context"
        directory.mkdir(exist_ok=True)
        path = directory / (name + ".json")
        material = json.dumps(value, sort_keys=True, default=_json_default, separators=(",", ":"))
        envelope = {"value": json.loads(material), "sha256": sha256(material.encode()).hexdigest()}
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as target:
            json.dump(envelope, target, sort_keys=True, separators=(",", ":"))
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _sync_directory(directory)
        _sync_directory(self.root)

    def context(self, name: str) -> dict:
        path = self.root / "context" / (name + ".json")
        if not path.exists():
            return {}
        try:
            envelope = json.loads(path.read_text())
            material = json.dumps(envelope["value"], sort_keys=True, separators=(",", ":"))
            if sha256(material.encode()).hexdigest() != envelope["sha256"]:
                raise ValueError("UX10_RECOVERY_CONTEXT_INVALID")
            return envelope["value"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("UX10_RECOVERY_CONTEXT_INVALID") from error

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
        maintenance_admission: MaintenanceAdmissionCoordinator | None = None,
    ) -> None:
        self._store = store or Ux10NotificationStore()
        self._telegram = telegram
        self._clock = clock
        self._background = background_runner or _thread_runner
        self._retry_scheduler = retry_scheduler or _timer_scheduler
        self._maintenance_admission = maintenance_admission
        self._lock = RLock()
        self._closed = False
        self._retry_handles: dict[str, object | None] = {}
        self._records = {item.deduplication_key: item for item in self._store.load()}
        self._promotion_state = self._store.context("promotion-baselines")
        self._connection_state = self._store.context("connection-baselines")
        self._evidence = self._store.context("source-bindings")
        self._connection_checkpoint = self._connection_state
        self._reconcile_connection_baselines()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            handles = tuple(self._retry_handles.values())
            self._retry_handles.clear()
        for handle in handles:
            cancel = getattr(handle, "cancel", None)
            if callable(cancel):
                cancel()

    def maintenance_status(self) -> dict[str, object]:
        with self._lock:
            return {"closed": self._closed,
                    "retry_callbacks": len(self._retry_handles)}

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
            source_binding=_watch_binding(watch, watch.history[-1].event_id),
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
            source_binding=_watch_binding(watch, watch.history[0].event_id),
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
            source_binding=dict(kind="ACTIVE_POSITION", position_identity=position.position_id,
                plan_identity=position.trade_plan_id, lifecycle_identity=position.lifecycle_id,
                instrument=position.canonical_instrument, mode=position.mode.value,
                source_integrity=position.integrity_hash),
            summary="Stop: Watching · Target: Watching",
            action="LIVE MONITORING ACTIVE — LEVEL TOUCHES ARE NOT BROKER FILLS",
            created_at=position.updated_at,
        )

    def _observe_owned(self, operation, empty):
        admission = self._maintenance_admission
        ticket = None if admission is None else admission.admit("NOTIFICATION")
        if (admission is not None and ticket is None) or self._closed:
            if ticket is not None:
                ticket.release()
            return empty
        try:
            if ticket is None:
                return operation()
            with ticket.activate():
                return operation()
        finally:
            if ticket is not None:
                ticket.release()

    def observe_promotions(self, records):
        return self._observe_owned(lambda: self._observe_promotions_owned(records), ())

    def _observe_promotions_owned(
        self, records: tuple[Kr370AnalyticalPromotionRecord | V2PromotionRecord, ...]
    ) -> tuple[Ux10NotificationRecord, ...]:
        created = []
        for record in records:
            if type(record) is V2PromotionRecord:
                value = record.value
                source = value["source"]
                instrument = source["canonical_instrument"]
                direction = source["direction"]
                run_identity = source["native_run_identity"]
                classification = value["promotion_state"] or value["evaluation_disposition"]
                source_identity = value["integrity_sha256"]
                semantic = dict(value)
                for field in ("created_at", "integrity_sha256", "record_identity"):
                    semantic.pop(field, None)
                assessment_event = sha256(json.dumps(semantic, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest()
            elif type(record) is Kr370AnalyticalPromotionRecord:
                instrument = record.canonical_instrument
                direction = record.direction.value
                run_identity = record.run_identity
                classification = record.classification.value
                source_identity = record.integrity_sha256
                semantic = asdict(record)
                for field in ("created_at", "integrity_sha256"):
                    semantic.pop(field, None)
                assessment_event = sha256(json.dumps(semantic, sort_keys=True,
                    default=_json_default, separators=(",", ":")).encode()).hexdigest()
            else:
                raise TypeError("UX10_PROMOTION_VERSION_UNSUPPORTED")
            # The caller supplies an authoritative assessment; run identity is
            # context, not the transition discriminator. Known source bytes never
            # roll the baseline backwards on restart or historical replay.
            if type(record) is V2PromotionRecord:
                assessed_at = value["created_at"]
                boundary = source["analysis_boundary"]
                origin = source["native_opportunity_identity"]
                assessment = source["native_assessment_sha256"]
            else:
                assessed_at = record.created_at.isoformat()
                boundary = record.analysis_boundary.isoformat()
                origin = None
                assessment = record.native_assessment_sha256
            key = json.dumps((instrument, direction), separators=(",", ":"))
            with self._lock:
                previous = self._promotion_state.get(key)
                seen = [] if previous is None else previous["seen"]
                if assessment_event in seen:
                    continue
                ordering = (datetime.fromisoformat(boundary), datetime.fromisoformat(assessed_at))
                if previous is not None and ordering < (
                    datetime.fromisoformat(previous["boundary"]),
                    datetime.fromisoformat(previous["assessed_at"]),
                ):
                    continue
                if (previous is not None
                        and previous["classification"] in {"BUY_READY", "SELL_READY"}
                        and classification in {"BUY_NOW", "SELL_NOW"}):
                    event = self._create(
                        family=Ux10NotificationFamily.PROMOTION_WATCH,
                        notification_type=Ux10NotificationType.ANALYTICAL_NOW_CONFIRMED,
                        priority=Ux10Priority.HIGH, instrument=instrument,
                        direction=direction, run_identity=run_identity,
                        source_event_identity=source_identity,
                        summary=f"{instrument} is now {classification.replace('_', ' ')} under KR-370.",
                        action="REVIEW CURRENT ANALYSIS — NO ENTRY OR EXECUTION AUTHORITY",
                        source_binding=dict(kind="ANALYTICAL_ASSESSMENT", source_identity=source_identity,
                            run_identity=run_identity, instrument=instrument,
                            assessment_identity=assessment, opportunity_identity=origin,
                            predecessor_identity=previous["source_identity"],
                            classification=classification, assessed_at=assessed_at),
                    )
                    if event is not None:
                        created.append(event)
                self._promotion_state[key] = dict(source_identity=source_identity,
                    classification=classification, run_identity=run_identity,
                    boundary=boundary, assessed_at=assessed_at, seen=seen + [assessment_event])
                self._store.retain_context("promotion-baselines", self._promotion_state)
        return tuple(created)

    def observe_refresh_analysis_reminder(
        self, reminder: K5RefreshReminderRecord
    ) -> Ux10NotificationRecord:
        """Deliver one due K5 reminder without evaluating analytical state."""

        if type(reminder) is not K5RefreshReminderRecord:
            raise TypeError("UX10_REFRESH_REMINDER_INVALID")
        instruments = tuple(item[0] for item in reminder.instrument_bindings)
        visible = ", ".join(instruments[:12])
        if len(instruments) > 12:
            visible += f", +{len(instruments) - 12} more"
        created = self._create(
            family=Ux10NotificationFamily.ANALYSIS_REMINDER,
            notification_type=Ux10NotificationType.REFRESH_ANALYSIS_REMINDER,
            priority=Ux10Priority.NORMAL,
            run_identity=reminder.run_identity,
            source_event_identity=reminder.reminder_identity,
            source_binding=dict(kind="REFRESH_REMINDER", source_identity=reminder.reminder_identity,
                run_identity=reminder.run_identity, source_integrity=reminder.integrity_sha256,
                instruments=list(instruments), due_at=reminder.next_eligible_completed_1h_boundary.isoformat()),
            summary=(
                "A new completed 1H boundary is available. K5 READY instruments "
                "awaiting reassessment: " + visible
            ),
            action="REFRESH SWING ANALYSIS — REMINDER ONLY; NO ANALYTICAL STATE CHANGED",
            created_at=reminder.next_eligible_completed_1h_boundary,
        )
        if created is not None:
            return created
        with self._lock:
            existing = next((
                item for item in self._records.values()
                if item.notification_type is Ux10NotificationType.REFRESH_ANALYSIS_REMINDER
                and item.source_event_identity == reminder.reminder_identity
            ), None)
        if existing is None:
            raise ValueError("UX10_REFRESH_REMINDER_DELIVERY_UNAVAILABLE")
        return existing

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
            source_binding=dict(kind="LIFECYCLE_EVENT", source_identity=event.event_id,
                position_identity=event.position_id, plan_identity=event.trade_plan_id,
                plan_integrity=event.trade_plan_hash, instrument=event.instrument,
                mode=event.mode.value, event_type=event.event_type.value,
                source_integrity=event.integrity_hash, occurred_at=event.event_timestamp.isoformat()),
            summary=f"{'Stop' if event.event_type is LifecycleEventType.STOP_HIT else 'Target'}: ₹{level}",
            action="OPEN KRONOS FOR TRADE STATUS — FACTUAL LEVEL TOUCH, NOT A FILL",
        )

    def observe_connection_state(self, watch_identity, instrument, state, *, occurred_at=None):
        return self._observe_owned(lambda: self._observe_connection_state_owned(
            watch_identity, instrument, state, occurred_at=occurred_at), None)

    def _reconcile_connection_baselines(self) -> None:
        """Fold retained events over lagging context without emitting or writing.

        Event publication precedes context publication. Either can survive an
        interrupted call, so an older CONNECTED checkpoint is not authoritative
        over a newer retained incident. R2's `at` remains readable; new context
        separates incident start from the latest accepted observation boundary.
        """
        recovered = {}
        for owner, value in self._connection_state.items():
            recovered[owner] = dict(value,
                observed_at=value.get("observed_at", value["at"]),
                incident_started_at=value.get("incident_started_at",
                    value["at"] if value["open"] else None))
        events = sorted((item for item in self._records.values()
            if item.family is Ux10NotificationFamily.SYSTEM_CONNECTIVITY),
            key=lambda item: (item.created_at,
                {Ux10NotificationType.WEBSOCKET_DISCONNECTED: 0,
                 Ux10NotificationType.MONITORING_GAP_RECONCILIATION_REQUIRED: 1,
                 Ux10NotificationType.WEBSOCKET_RESTORED: 2}.get(item.notification_type, -1),
                item.notification_id))
        starts = {item.source_event_identity: item.created_at.isoformat()
            for item in events
            if item.notification_type is not Ux10NotificationType.WEBSOCKET_RESTORED}
        for item in events:
            previous = recovered.get(item.watch_identity)
            if previous is not None:
                boundary = datetime.fromisoformat(previous["observed_at"])
                if item.created_at < boundary or (item.created_at == boundary
                    and previous.get("last_event_identity") == item.source_event_identity):
                    continue
            binding = self._evidence.get(item.notification_id, {})
            if binding.get("source_identity") != item.source_event_identity:
                binding = {}
            restored = item.notification_type is Ux10NotificationType.WEBSOCKET_RESTORED
            gap = item.notification_type is Ux10NotificationType.MONITORING_GAP_RECONCILIATION_REQUIRED
            incident = binding.get("incident_identity")
            if incident is None:
                # Legacy events lack bindings. Continue an evidenced open
                # incident where available; never use a restoration as a start.
                incident = (previous.get("incident") if previous and previous["open"]
                    else None if restored else item.source_event_identity)
            same_incident = previous is not None and previous.get("incident") == incident
            started = binding.get("incident_started_at") or starts.get(incident)
            if started is None and same_incident:
                started = previous.get("incident_started_at")
            if started is None and not restored:
                started = item.created_at.isoformat()
            observed = item.created_at.isoformat()
            recovered[item.watch_identity] = dict(
                state=binding.get("state", "CONNECTED" if restored else
                    "CONTEXT_INCOMPLETE" if gap else "DISCONNECTED"),
                at=observed if restored else started,
                observed_at=observed, incident_started_at=started,
                incident=incident, open=not restored,
                gap=gap or bool(same_incident and previous.get("gap", False)),
                last_event_identity=item.source_event_identity)
        self._connection_state = recovered

    def _retain_connection_baseline(self, owner: str, value: dict) -> None:
        proposed = dict(self._connection_state)
        proposed[owner] = value
        # Do not advance RAM before the durable checkpoint succeeds.
        self._store.retain_context("connection-baselines", proposed)
        self._connection_state = proposed
        self._connection_checkpoint = proposed

    def _recover_connection_publication(self) -> None:
        # A writer may fail after atomic replacement (including fsync failure).
        # Re-read what survived instead of assuming either side was rolled back.
        # This is recovery of retained facts, not certification of fsync success.
        self._records = {item.deduplication_key: item for item in self._store.load()}
        self._evidence = self._store.context("source-bindings")
        self._connection_state = self._store.context("connection-baselines")
        self._connection_checkpoint = self._connection_state
        self._reconcile_connection_baselines()

    def _observe_connection_state_owned(
        self,
        watch_identity: str,
        instrument: str,
        state: MonitoringConnectionState,
        *,
        occurred_at: datetime | None = None,
    ) -> Ux10NotificationRecord | None:
        now = occurred_at or self._clock()
        with self._lock:
            try:
                return self._accept_connection_observation(watch_identity, instrument, state, now)
            except Exception:
                self._recover_connection_publication()
                raise

    def _accept_connection_observation(self, watch_identity, instrument, state, now):
        previous = self._connection_state.get(watch_identity)
        if previous is not None and now < datetime.fromisoformat(previous["observed_at"]):
            return None
        if state is MonitoringConnectionState.DISCONNECTED:
            def complete(expected):
                if expected:
                    with self._lock:
                        latest = self._connection_state.get(watch_identity)
                        if latest and now < datetime.fromisoformat(latest["observed_at"]):
                            return
                        try:
                            self._retain_connection_baseline(watch_identity, dict(
                                state=state.value, at=now.isoformat(), observed_at=now.isoformat(),
                                incident_started_at=None, incident=None, open=False,
                                last_event_identity=latest.get("last_event_identity") if latest else None))
                        except Exception:
                            self._recover_connection_publication()
                            raise
                else:
                    self.observe_connection_state(watch_identity, instrument, state, occurred_at=now)
            if defer_expected_disconnect(complete):
                return None
        outage = state in {MonitoringConnectionState.DISCONNECTED,
            MonitoringConnectionState.RECONNECTING, MonitoringConnectionState.CONTEXT_INCOMPLETE}
        if not outage and state is not MonitoringConnectionState.CONNECTED:
            return None
        open_incident = previous is not None and previous["open"]
        gap_escalation = (open_incident and state is MonitoringConnectionState.CONTEXT_INCOMPLETE
            and not previous.get("gap", False))
        if (outage and open_incident and not gap_escalation) or (
            state is MonitoringConnectionState.CONNECTED and not open_incident):
            # Even an observation that emits no alert advances the ordering
            # boundary. It must not reset the incident start or gap escalation.
            value = dict(previous or dict(at=now.isoformat(), incident=None,
                incident_started_at=None, open=False), state=state.value, observed_at=now.isoformat())
            if not open_incident:
                value["at"] = now.isoformat()
            if value != previous or self._connection_state != self._connection_checkpoint:
                self._retain_connection_baseline(watch_identity, value)
            return None
        incident = (previous["incident"] if open_incident else sha256(
            f"{watch_identity}:{state.value}:{now.isoformat()}".encode()).hexdigest())
        started = previous["incident_started_at"] if open_incident else now.isoformat()
        if outage:
            event_type = (Ux10NotificationType.MONITORING_GAP_RECONCILIATION_REQUIRED
                if state is MonitoringConnectionState.CONTEXT_INCOMPLETE
                else Ux10NotificationType.WEBSOCKET_DISCONNECTED)
            priority = Ux10Priority.HIGH
            summary = f"Live market monitoring interrupted for {instrument}."
            action = "MONITORING MAY BE INCOMPLETE — DO NOT INFER MISSED EVENTS"
            source = sha256(f"{incident}:GAP".encode()).hexdigest() if gap_escalation else incident
        else:
            event_type = Ux10NotificationType.WEBSOCKET_RESTORED
            priority = Ux10Priority.NORMAL
            duration = max(0, int((now - datetime.fromisoformat(started)).total_seconds()))
            summary = f"Market-data monitoring restored for {instrument} after {duration}s."
            action = "SUBSCRIPTION RESTORED; GAP RULES REMAIN FAIL-CLOSED"
            source = sha256(f"{incident}:RESTORED".encode()).hexdigest()
        event = self._create(family=Ux10NotificationFamily.SYSTEM_CONNECTIVITY,
            notification_type=event_type, priority=priority, instrument=instrument,
            watch_identity=watch_identity, source_event_identity=source,
            summary=summary, action=action, created_at=now,
            source_binding=dict(kind="CONNECTION_EVENT", source_identity=source,
                incident_identity=incident, incident_started_at=started, owner_identity=watch_identity,
                state=state.value, occurred_at=now.isoformat()))
        self._retain_connection_baseline(watch_identity, dict(state=state.value,
            at=started if outage else now.isoformat(), observed_at=now.isoformat(),
            incident_started_at=started, incident=incident, open=outage,
            gap=bool(gap_escalation or state is MonitoringConnectionState.CONTEXT_INCOMPLETE
                or (open_incident and previous.get("gap", False))),
            last_event_identity=source))
        return event

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

    def _create(self, **kwargs) -> Ux10NotificationRecord | None:
        admission = self._maintenance_admission
        ticket = None if admission is None else admission.admit("NOTIFICATION")
        if admission is not None and ticket is None:
            return None
        try:
            if ticket is None:
                return self._create_owned(**kwargs)
            with ticket.activate():
                return self._create_owned(**kwargs)
        finally:
            if ticket is not None:
                ticket.release()

    def _create_owned(
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
        source_binding: dict | None = None,
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
            delivery_protocol="RETAINED_ATTEMPT_V1",
            integrity_sha256="",
        )
        record = Ux10NotificationRecord(**(values | {"integrity_sha256": _integrity_values(values)}))
        with self._lock:
            if dedup in self._records:
                return None
            if source_binding is not None:
                self._evidence[record.notification_id] = dict(source_binding,
                    source_identity=source_event_identity)
                self._store.retain_context("source-bindings", self._evidence)
            self._store.retain(record)
            self._records[dedup] = record
        if (
            telegram_state is Ux10DeliveryState.PENDING
            and telegram_status is not None
            and telegram_status.delivery_enabled
        ):
            self._schedule_delivery(dedup)
        return record

    def _schedule_delivery(self, dedup: str) -> None:
        admission = self._maintenance_admission
        ticket = None if admission is None else admission.admit("NOTIFICATION")
        if admission is not None and ticket is None:
            return
        with self._lock:
            closed = self._closed
        if closed:
            if ticket is not None:
                ticket.release()
            return
        try:
            self._background(
                lambda: self._deliver_owned(dedup, ticket),
                "kronos-ux10-telegram",
            )
        except BaseException:
            if ticket is not None and not ticket._released:
                ticket.release()
            raise

    def _deliver_owned(self, dedup: str, ticket) -> None:
        try:
            if ticket is None:
                self._deliver(dedup)
            else:
                with ticket.activate():
                    self._deliver(dedup)
        finally:
            if ticket is not None:
                ticket.release()

    def evidence(self, notification_id: str) -> dict | None:
        with self._lock:
            binding = self._evidence.get(notification_id)
            event = next((item for item in self._records.values()
                if item.notification_id == notification_id), None)
            if binding is None or event is None or binding.get("source_identity") != event.source_event_identity:
                return None
            return json.loads(json.dumps(binding))

    def _deliver(self, dedup: str) -> None:
        with self._lock:
            record = self._records.get(dedup)
            if (self._closed or record is None or self._telegram is None
                    or not self._telegram.status().delivery_enabled
                    or record.telegram_delivery_state not in {
                        Ux10DeliveryState.PENDING, Ux10DeliveryState.FAILED_RETRYABLE}
                    or record.delivery_attempts >= 4
                    or (record.next_retry_at is not None and record.next_retry_at > self._clock())):
                return
            if record.delivery_protocol is None:
                # Legacy PENDING does not prove whether transport was already
                # entered before the old process ended. Never invent an attempt.
                values = asdict(record)
                values.update(telegram_delivery_state=Ux10DeliveryState.DELIVERY_UNCERTAIN,
                    next_retry_at=None, last_safe_failure="LEGACY_DELIVERY_ACCEPTANCE_UNKNOWN")
                uncertain = Ux10NotificationRecord(**(values | {"integrity_sha256": _integrity_values(values)}))
                self._store.retain(uncertain)
                self._records[dedup] = uncertain
                return
            attempts = record.delivery_attempts + 1
            attempt = sha256(f"{record.notification_id}:ATTEMPT:{attempts}".encode()).hexdigest()
            # Claim before transport. A crash even before send is uncertain: no
            # transport receipt exists to prove it safe to retry after restart.
            values = asdict(record)
            values.update(telegram_delivery_state=Ux10DeliveryState.DELIVERY_UNCERTAIN,
                delivery_attempt_identity=attempt, delivery_attempts=attempts,
                next_retry_at=None, last_safe_failure="DELIVERY_ATTEMPT_NOT_RECONCILED")
            claimed = Ux10NotificationRecord(**(values | {"integrity_sha256": _integrity_values(values)}))
            self._store.retain(claimed)
            self._records[dedup] = claimed
        try:
            result = self._telegram.send(_telegram_message(record))
        except Exception:
            return  # The durable uncertain claim is the Browser result.
        retry_at = None
        if result.state is TelegramDeliveryState.SENT:
            state, reason = Ux10DeliveryState.SENT, ""
        elif (result.state is TelegramDeliveryState.FAILED_RETRYABLE
                and result.safe_reason == "TELEGRAM_RATE_LIMITED"):
            # Existing transport explicitly identifies a rejected 429. Timeout,
            # HTTP 5xx and generic configuration errors cannot prove nonacceptance.
            state = Ux10DeliveryState.FAILED_RETRYABLE if attempts < 4 else Ux10DeliveryState.FAILED_FINAL
            reason = result.safe_reason
            if state is Ux10DeliveryState.FAILED_RETRYABLE:
                delay = result.retry_after_seconds or min(300, 5 * (2 ** (attempts - 1)))
                retry_at = self._clock() + timedelta(seconds=delay)
        elif result.state is TelegramDeliveryState.FAILED_FINAL and result.safe_reason in {
                "TELEGRAM_MESSAGE_INVALID", "TELEGRAM_DELIVERY_DISABLED", "TELEGRAM_PRIVATE_CHAT_INVALID"}:
            state, reason = Ux10DeliveryState.FAILED_FINAL, result.safe_reason
        else:
            state, reason = Ux10DeliveryState.DELIVERY_UNCERTAIN, "DELIVERY_ACCEPTANCE_UNKNOWN"
        with self._lock:
            values = asdict(claimed)
            values.update(telegram_delivery_state=state, next_retry_at=retry_at, last_safe_failure=reason)
            updated = Ux10NotificationRecord(**(values | {"integrity_sha256": _integrity_values(values)}))
            self._store.retain(updated)
            self._records[dedup] = updated
        if retry_at is not None:
            self._schedule_retry(dedup, max(0.0, (retry_at - self._clock()).total_seconds()))

    def _schedule_retry(self, dedup: str, delay: float) -> None:
        with self._lock:
            if self._closed:
                return  # The retained retry remains available after restoration.
            previous = self._retry_handles.get(dedup)
            self._retry_handles[dedup] = None
        cancel = getattr(previous, "cancel", None)
        if callable(cancel):
            cancel()
        try:
            handle = self._retry_scheduler(
                delay, lambda: self._retry_due(dedup)
            )
        except BaseException:
            with self._lock:
                self._retry_handles.pop(dedup, None)
            raise
        with self._lock:
            if self._closed or dedup not in self._retry_handles:
                cancel = getattr(handle, "cancel", None)
            else:
                self._retry_handles[dedup] = handle
                cancel = None
        if callable(cancel):
            cancel()

    def _retry_due(self, dedup: str) -> None:
        with self._lock:
            self._retry_handles.pop(dedup, None)
            if self._closed:
                return
        self._schedule_delivery(dedup)


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


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _watch_binding(watch: ProgressionWatch, event_identity: str) -> dict:
    return dict(kind="PROGRESSION_WATCH_EVENT", source_identity=event_identity,
        watch_identity=watch.watch_id, run_identity=watch.requirement.native_run_identity,
        instrument=watch.requirement.canonical_instrument,
        requirement_identity=watch.requirement.requirement_id,
        state=watch.state.value)


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
    for optional in ("delivery_attempt_identity", "delivery_protocol"):
        if material.get(optional) is None:
            material.pop(optional, None)
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
