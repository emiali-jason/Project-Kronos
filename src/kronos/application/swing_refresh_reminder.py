"""Durable time-based reminders for K5-only KR-370 READY opportunities.

The initial reminder uses a governed DOMAIN-008 completed-hour boundary.
After delivery, recurrence is operational elapsed-time scheduling: the next
reminder is due one hour after the previous delivery.  The workflow never
evaluates K5, watches prices, or creates a trading state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Condition, RLock, Thread, Timer, current_thread
from time import monotonic
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from typing import Callable
from zoneinfo import ZoneInfo

from kronos.market.calendar import MarketCalendarPublisher
from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalClassification,
    Kr370AnalyticalPromotionRecord,
    Kr370CriterionIdentity,
)
from kronos.swing.v1.analytical_promotion_v2 import V2PromotionRecord
from kronos.swing.v1.mtf_facts import FactualTimeframe


REFRESH_REMINDER_CONTRACT = "KRONOS-SWING-K5-REFRESH-REMINDER-V1"
REFRESH_REMINDER_VERSION = "1"
REFRESH_REMINDER_AUTHORITY = "REMINDER_DELIVERY_ONLY_NO_ANALYTICAL_OR_TRADING_AUTHORITY"
DEFAULT_REFRESH_REMINDER_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "swing-v1" / "refresh-analysis-reminders-v1"
)


class RefreshReminderState(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True, slots=True)
class K5RefreshReminderRecord:
    reminder_identity: str
    run_identity: str
    instrument_bindings: tuple[tuple[str, str, str, str], ...]
    source_boundaries: tuple[tuple[str, datetime], ...]
    next_eligible_completed_1h_boundary: datetime
    calendar_bindings: tuple[tuple[str, str, str], ...]
    state: RefreshReminderState
    created_at: datetime
    updated_at: datetime
    notification_identity: str | None
    integrity_sha256: str
    product: str = "SWING"
    remaining_criterion: str = "K5_NON_EXTENSION"
    authority: str = REFRESH_REMINDER_AUTHORITY
    contract_identity: str = REFRESH_REMINDER_CONTRACT
    contract_version: str = REFRESH_REMINDER_VERSION

    def __post_init__(self) -> None:
        instruments = tuple(item[0] for item in self.instrument_bindings)
        if (
            len(self.reminder_identity) != 64
            or not is_swing_analysis_run_id(self.run_identity)
            or not self.instrument_bindings
            or instruments != tuple(sorted(set(instruments)))
            or any(
                len(item) != 4
                or not item[0]
                or len(item[1]) != 64
                or item[2] not in {"BUY_READY", "SELL_READY"}
                or item[3] not in {"NSE", "MCX"}
                for item in self.instrument_bindings
            )
            or tuple(item[0] for item in self.source_boundaries) != instruments
            or any(item[1].tzinfo is None for item in self.source_boundaries)
            or self.next_eligible_completed_1h_boundary.tzinfo is None
            or not self.calendar_bindings
            or any(
                len(item) != 3 or item[0] not in {"NSE", "MCX"}
                or not item[1] or not item[2]
                for item in self.calendar_bindings
            )
            or type(self.state) is not RefreshReminderState
            or self.created_at.tzinfo is None
            or self.updated_at.tzinfo is None
            or self.updated_at < self.created_at
            or (self.state is RefreshReminderState.SENT) != (
                self.notification_identity is not None
            )
            or self.product != "SWING"
            or self.remaining_criterion != "K5_NON_EXTENSION"
            or self.authority != REFRESH_REMINDER_AUTHORITY
            or self.contract_identity != REFRESH_REMINDER_CONTRACT
            or self.contract_version != REFRESH_REMINDER_VERSION
            or self.integrity_sha256 != _integrity(self)
        ):
            raise ValueError("K5_REFRESH_REMINDER_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class K5RefreshReminderSnapshot:
    records: tuple[K5RefreshReminderRecord, ...]

    def for_instrument(
        self, run_identity: str, instrument: str
    ) -> K5RefreshReminderRecord | None:
        return next((
            item for item in self.records
            if item.run_identity == run_identity
            and item.state in {RefreshReminderState.PENDING, RefreshReminderState.SENT}
            and instrument in {binding[0] for binding in item.instrument_bindings}
        ), None)


class K5RefreshReminderStore:
    """Append-only reminder revisions; prior states are never overwritten."""

    def __init__(self, root: Path = DEFAULT_REFRESH_REMINDER_ROOT) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def retain(self, record: K5RefreshReminderRecord) -> None:
        directory = self.root / record.reminder_identity
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{record.updated_at.isoformat().replace(':', '')}-{record.integrity_sha256}.json"
        payload = _record_dict(record)
        try:
            with path.open("x", encoding="utf-8") as target:
                json.dump(payload, target, sort_keys=True, separators=(",", ":"))
                target.flush()
                os.fsync(target.fileno())
            os.chmod(path, 0o600)
        except FileExistsError:
            if json.loads(path.read_text(encoding="utf-8")) != payload:
                raise ValueError("K5_REFRESH_REMINDER_IMMUTABILITY_VIOLATION")
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("K5_REFRESH_REMINDER_PERSISTENCE_FAILED") from error

    def load_current(self) -> tuple[K5RefreshReminderRecord, ...]:
        latest: dict[str, K5RefreshReminderRecord] = {}
        for path in sorted(self.root.glob("*/*.json")):
            try:
                record = _record_from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            previous = latest.get(record.reminder_identity)
            if previous is None or record.updated_at > previous.updated_at:
                latest[record.reminder_identity] = record
        return tuple(sorted(latest.values(), key=lambda item: item.created_at))


class SwingK5RefreshReminderWorkflow:
    """Create, restore, supersede, and deliver one reminder per due boundary."""

    def __init__(
        self,
        store: K5RefreshReminderStore | None = None,
        *,
        calendar: MarketCalendarPublisher | None = None,
        notification_listener: Callable[[K5RefreshReminderRecord], str] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        scheduler: Callable[[float, Callable[[], None]], object] | None = None,
        maintenance_admission: MaintenanceAdmissionCoordinator | None = None,
        defer_execution: bool = False,
    ) -> None:
        self._store = store or K5RefreshReminderStore()
        self._calendar = calendar or MarketCalendarPublisher()
        self._listener = notification_listener
        self._clock = clock
        self._scheduler = scheduler or _timer_scheduler
        self._lock = RLock()
        # Durable mutations serialize independently. Never hold the execution
        # state lock across store I/O: close must be able to fence and observe
        # a stalled write within the existing cleanup deadline.
        self._mutation_lock = RLock()
        self._mutations = 0
        self._completion = Condition(self._lock)
        self._deferred_execution = defer_execution
        self._active = not defer_execution
        self._closed = False
        self._failed = False
        self._cleanup_unresolved = False
        self._records = {
            item.reminder_identity: item for item in self._store.load_current()
        }
        # Reserve each timer BEFORE calling a scheduler that may start it before
        # returning its handle. Keep returned threads until actual termination.
        self._timers: dict[str, object] = {}
        self._handles: dict[object, object] = {}
        self._scheduling: set[object] = set()
        self._callbacks: set[object] = set()
        self._firing: set[str] = set()
        self._callback_threads: dict[object, Thread] = {}
        self._cancelled: set[object] = set()
        self._maintenance_admission = maintenance_admission
        for record in tuple(self._records.values()):
            if record.state is RefreshReminderState.PENDING:
                self._schedule(record)

    def snapshot(self) -> K5RefreshReminderSnapshot:
        with self._lock:
            return K5RefreshReminderSnapshot(tuple(sorted(
                self._records.values(), key=lambda item: item.created_at, reverse=True,
            )))

    def next_repeat_boundary(
        self, notification_identity: str, after: datetime
    ) -> datetime | None:
        """Return the operational repeat due time after a delivered reminder.

        DOMAIN-008 owns the initial completed-market-hour trigger.  Once that
        reminder has been delivered, recurrence asks only whether a successful
        Refresh Analysis has occurred, so it uses one elapsed wall-clock hour
        from the factual delivery timestamp supplied by the caller.
        """

        if not notification_identity or after.tzinfo is None:
            raise ValueError("K5_REFRESH_REPEAT_BOUNDARY_REQUEST_INVALID")
        with self._lock:
            record = next((
                item for item in self._records.values()
                if item.notification_identity == notification_identity
                and item.state is RefreshReminderState.SENT
            ), None)
        if record is None:
            return None
        return after + timedelta(hours=1)

    def synchronize(
        self,
        current_run_identity: str | None,
        promotions: tuple[Kr370AnalyticalPromotionRecord | V2PromotionRecord, ...],
        exchange_by_instrument: dict[str, str],
    ) -> K5RefreshReminderSnapshot:
        admission = self._maintenance_admission
        ticket = None if admission is None else admission.admit("REMINDER")
        if admission is not None and ticket is None:
            raise ValueError("K5_REFRESH_REMINDER_MAINTENANCE_FENCED")
        try:
            if ticket is None:
                return self._synchronize_owned(current_run_identity, promotions,
                                                exchange_by_instrument)
            with ticket.activate():
                return self._synchronize_owned(current_run_identity, promotions,
                                                exchange_by_instrument)
        finally:
            if ticket is not None:
                ticket.release()

    def _synchronize_owned(
        self, current_run_identity, promotions, exchange_by_instrument
    ) -> K5RefreshReminderSnapshot:
        with self._lock:
            if self._closed or self._failed:
                raise ValueError("K5_REFRESH_REMINDER_OWNER_CLOSED_OR_FAILED")
            self._mutations += 1
        try:
            with self._mutation_lock:
                self._synchronize_records(current_run_identity, promotions,
                                          exchange_by_instrument)
            with self._lock:
                pending = tuple(self._records.values())
            for record in pending:
                if record.state is RefreshReminderState.PENDING:
                    self._schedule(record)
            return self.snapshot()
        finally:
            with self._completion:
                self._mutations -= 1
                self._completion.notify_all()

    def _synchronize_records(
        self, current_run_identity, promotions, exchange_by_instrument
    ) -> None:
        if current_run_identity is not None and not is_swing_analysis_run_id(current_run_identity):
            raise ValueError("K5_REFRESH_REMINDER_RUN_INVALID")
        if type(promotions) is not tuple or any(
            type(item) not in {Kr370AnalyticalPromotionRecord, V2PromotionRecord}
            for item in promotions
        ):
            raise TypeError("K5_REFRESH_REMINDER_PROMOTIONS_INVALID")
        now = self._clock()
        eligible = tuple(
            fields for item in promotions
            if (fields := _promotion_reminder_fields(item)) is not None
            and fields[0] == current_run_identity
            and fields[3] in {"BUY_READY", "SELL_READY"}
            and fields[4] == Kr370CriterionIdentity.K5_NON_EXTENSION.value
        )
        grouped: dict[datetime, list[tuple[tuple, str]]] = {}
        for item in eligible:
            exchange = exchange_by_instrument.get(item[1])
            if exchange not in {"NSE", "MCX"}:
                raise ValueError("K5_REFRESH_REMINDER_EXCHANGE_UNAVAILABLE")
            source = item[5]
            due = next_completed_one_hour_boundary(
                self._calendar, exchange, source, observed_at=now
            )
            grouped.setdefault(due, []).append((item, exchange))

        desired: set[str] = set()
        for due, values in grouped.items():
            bindings = tuple(sorted(
                (
                    item[1],
                    item[2],
                    item[3],
                    exchange,
                )
                for item, exchange in values
            ))
            sources = tuple(
                (item[1], item[5])
                for item, _ in sorted(values, key=lambda value: value[0][1])
            )
            calendars = tuple(sorted({
                (
                    exchange,
                    self._calendar.publication(exchange).calendar_identity,
                    self._calendar.publication(exchange).calendar_version,
                )
                for _, exchange in values
            }))
            identity = _reminder_identity(current_run_identity, due, bindings)
            desired.add(identity)
            existing = self._records.get(identity)
            if existing is None:
                values_dict = dict(
                    reminder_identity=identity,
                    run_identity=current_run_identity,
                    instrument_bindings=bindings,
                    source_boundaries=sources,
                    next_eligible_completed_1h_boundary=due,
                    calendar_bindings=calendars,
                    state=RefreshReminderState.PENDING,
                    created_at=now,
                    updated_at=now,
                    notification_identity=None,
                    integrity_sha256="",
                )
                record = K5RefreshReminderRecord(**(
                    values_dict | {"integrity_sha256": _integrity_values(values_dict)}
                ))
                self._retain(record)

        with self._lock:
            pending = tuple(
                item for item in self._records.values()
                if item.state is RefreshReminderState.PENDING
                and item.reminder_identity not in desired
            )
        for record in pending:
            self._transition(record, RefreshReminderState.SUPERSEDED, now)
    def _activate_execution(self) -> bool:
        """Called by canonical composition only after verified custody release."""
        with self._lock:
            if self._closed or self._failed:
                raise ValueError("K5_REFRESH_REMINDER_OWNER_CLOSED_OR_FAILED")
            if self._active:
                return False
            self._active = True
            pending = tuple(self._records.values())
        for record in pending:
            if record.state is RefreshReminderState.PENDING:
                self._schedule(record)
        return True

    def _cancel(self, token: object) -> None:
        with self._lock:
            timer = self._handles.get(token)
            if timer is None or token in self._cancelled:
                return
            self._cancelled.add(token)
        try:
            timer.cancel()
        except BaseException:
            with self._lock:
                self._cleanup_unresolved = True
            raise

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._active = False
            tokens = tuple(self._handles)
            self._completion.notify_all()
        for token in tokens:
            self._cancel(token)

    def cleanup_complete(self) -> bool:
        with self._lock:
            return (self._closed and not self._scheduling and not self._callbacks
                and not self._firing and not self._mutations and not self._cleanup_unresolved
                and all(isinstance(handle, Thread) and handle.ident is not None
                        and not handle.is_alive()
                        for handle in self._handles.values()))

    def _wait_closed(self, deadline: float) -> bool:
        """Observe the same close operation within the caller's absolute budget."""
        while monotonic() < deadline:
            with self._lock:
                if self.cleanup_complete():
                    return True
                if self._cleanup_unresolved:
                    return False
                threads = tuple(handle for handle in self._handles.values()
                    if isinstance(handle, Thread) and handle.is_alive())
            for thread in threads:
                remaining = deadline - monotonic()
                if remaining <= 0 or thread is current_thread():
                    return False
                thread.join(timeout=min(.01, remaining))
            with self._completion:
                remaining = deadline - monotonic()
                if remaining > 0 and not self.cleanup_complete():
                    self._completion.wait(timeout=min(.01, remaining))
        return False

    def maintenance_status(self) -> dict[str, object]:
        with self._lock:
            return dict(closed=self._closed, active=self._active, failed=self._failed,
                scheduling=len(self._scheduling), callbacks=len(self._callbacks),
                mutations=self._mutations,
                firing=len(self._firing), live_timers=sum(
                    isinstance(handle, Thread) and handle.is_alive()
                    for handle in self._handles.values()),
                cleanup_unresolved=self._cleanup_unresolved,
                cleanup_complete=self.cleanup_complete())

    def _schedule(self, record: K5RefreshReminderRecord) -> None:
        with self._lock:
            if (not self._active or self._closed or self._failed
                    or self._records.get(record.reminder_identity) is not record
                    or record.state is not RefreshReminderState.PENDING
                    or record.reminder_identity in self._timers
                    or record.reminder_identity in self._firing):
                return
            # Reap only known terminated handles; never discard unresolved work.
            for old, handle in tuple(self._handles.items()):
                if (isinstance(handle, Thread) and handle.ident is not None
                        and not handle.is_alive()):
                    self._handles.pop(old)
                    self._callback_threads.pop(old, None)
                    self._cancelled.discard(old)
            token = object()
            self._timers[record.reminder_identity] = token
            self._scheduling.add(token)
        delay = max(
            0.0,
            (record.next_eligible_completed_1h_boundary - self._clock()).total_seconds(),
        )
        try:
            timer = self._scheduler(
                delay, lambda: self._fire(record.reminder_identity, token))
        except BaseException:
            with self._completion:
                # A scheduler may have started work before raising. Unknown
                # ownership is not repaired by an empty timer dictionary.
                self._failed = True
                self._active = False
                self._cleanup_unresolved = True
                self._scheduling.discard(token)
                self._completion.notify_all()
            raise
        with self._completion:
            self._handles[token] = timer
            self._scheduling.remove(token)
            entered = self._callback_threads.get(token)
            if isinstance(timer, Thread) and entered is not None and entered is not timer:
                self._cleanup_unresolved = True
            cancel = (self._closed or self._failed
                      or self._timers.get(record.reminder_identity) is not token)
            self._completion.notify_all()
        if cancel:
            self._cancel(token)

    def _fire(self, reminder_identity: str, token: object | None = None) -> None:
        scheduled = token is not None
        if token is None:
            token = object()
        with self._completion:
            self._callbacks.add(token)
            if scheduled:
                self._callback_threads[token] = current_thread()
            eligible = (self._active and not self._closed and not self._failed
                and reminder_identity not in self._firing
                and (not scheduled or self._timers.get(reminder_identity) is token))
            if eligible:
                self._firing.add(reminder_identity)
        admission = self._maintenance_admission
        ticket = None
        try:
            if not eligible:
                return
            ticket = None if admission is None else admission.admit("REMINDER")
            if admission is not None and ticket is None:
                return
            if ticket is None:
                self._fire_owned(reminder_identity)
            else:
                with ticket.activate():
                    self._fire_owned(reminder_identity)
        except BaseException:
            with self._lock:
                self._failed = True
                self._active = False
            raise
        finally:
            if ticket is not None:
                ticket.release()
            with self._completion:
                if eligible:
                    self._firing.discard(reminder_identity)
                self._callbacks.discard(token)
                if scheduled and self._timers.get(reminder_identity) is token:
                    self._timers.pop(reminder_identity)
                self._completion.notify_all()

    def _fire_owned(self, reminder_identity: str) -> None:
        with self._lock:
            record = self._records.get(reminder_identity)
            if not self._active or self._closed or self._failed:
                return
        if (
            record is None
            or record.state is not RefreshReminderState.PENDING
            or self._clock() < record.next_eligible_completed_1h_boundary
        ):
            return
        notification_identity = (
            "NOTIFICATION_NOT_CONFIGURED"
            if self._listener is None else self._listener(record)
        )
        self._transition(
            record,
            RefreshReminderState.SENT,
            self._clock(),
            notification_identity=notification_identity,
        )

    def _transition(
        self,
        record: K5RefreshReminderRecord,
        state: RefreshReminderState,
        occurred_at: datetime,
        *,
        notification_identity: str | None = None,
    ) -> None:
        values = asdict(record)
        values.update(
            state=state,
            updated_at=occurred_at,
            notification_identity=notification_identity,
            integrity_sha256="",
        )
        updated = K5RefreshReminderRecord(**(
            values | {"integrity_sha256": _integrity_values(values)}
        ))
        with self._mutation_lock:
            with self._lock:
                if self._records.get(record.reminder_identity) is not record:
                    return  # Never overwrite a later lawful reconciliation.
            self._retain(updated)
            with self._lock:
                token = self._timers.pop(record.reminder_identity, None)
        if token is not None:
            self._cancel(token)

    def _retain(self, record: K5RefreshReminderRecord) -> None:
        self._store.retain(record)
        with self._lock:
            self._records[record.reminder_identity] = record


def next_completed_one_hour_boundary(
    calendar: MarketCalendarPublisher,
    exchange: str,
    source_boundary: datetime,
    *,
    observed_at: datetime,
) -> datetime:
    """Return the next DOMAIN-008 session-aligned completed-hour boundary."""

    if (
        type(calendar) is not MarketCalendarPublisher
        or exchange not in {"NSE", "MCX"}
        or source_boundary.tzinfo is None
        or observed_at.tzinfo is None
    ):
        raise ValueError("K5_REFRESH_BOUNDARY_REQUEST_INVALID")
    publication = calendar.publication(exchange)
    zone_source = source_boundary.astimezone(ZoneInfo(publication.timezone))
    after = max(source_boundary, observed_at)
    for offset in range((publication.coverage_end - zone_source.date()).days + 1):
        day = zone_source.date() + timedelta(days=offset)
        schedule = calendar.schedule(exchange, day, observed_at=observed_at)
        if schedule is None:
            continue
        for window in schedule.windows:
            cursor = window.window_open
            while cursor < window.window_close:
                boundary = min(cursor + timedelta(hours=1), window.window_close)
                if boundary > after:
                    return boundary
                cursor = boundary
    raise ValueError("K5_REFRESH_NEXT_COMPLETED_1H_BOUNDARY_UNAVAILABLE")


def _promotion_reminder_fields(
    record: Kr370AnalyticalPromotionRecord | V2PromotionRecord,
) -> tuple[str, str, str, str, str | None, datetime] | None:
    """Select the existing K5-only reminder condition from either exact version."""
    if type(record) is V2PromotionRecord:
        value = record.value
        source = value["source"]
        boundary = next(item["boundary"] for item in source["observation_boundaries"]
                        if item["timeframe"] == "1H")
        return (source["native_run_identity"], source["canonical_instrument"],
                source["native_assessment_sha256"],
                value["promotion_state"] or value["evaluation_disposition"],
                value["sole_missing_criterion"], datetime.fromisoformat(boundary))
    if type(record) is Kr370AnalyticalPromotionRecord:
        return (record.run_identity, record.canonical_instrument,
                record.native_assessment_sha256, record.classification.value,
                None if record.sole_missing_criterion is None else
                record.sole_missing_criterion.value,
                dict(record.observation_boundaries)[FactualTimeframe.ONE_HOUR.value])
    raise TypeError("K5_REFRESH_REMINDER_PROMOTIONS_INVALID")


def _reminder_identity(
    run_identity: str | None,
    due: datetime,
    bindings: tuple[tuple[str, str, str, str], ...],
) -> str:
    return sha256(json.dumps(
        (run_identity, due.isoformat(), bindings), separators=(",", ":")
    ).encode()).hexdigest()


def _record_dict(record: K5RefreshReminderRecord) -> dict[str, object]:
    values = asdict(record)
    values["state"] = record.state.value
    for key in ("created_at", "updated_at", "next_eligible_completed_1h_boundary"):
        values[key] = getattr(record, key).isoformat()
    values["source_boundaries"] = tuple(
        (instrument, boundary.isoformat())
        for instrument, boundary in record.source_boundaries
    )
    return values


def _record_from_dict(value: object) -> K5RefreshReminderRecord:
    if type(value) is not dict:
        raise ValueError("K5_REFRESH_REMINDER_RECORD_INVALID")
    values = dict(value)
    values["state"] = RefreshReminderState(values["state"])
    for key in ("created_at", "updated_at", "next_eligible_completed_1h_boundary"):
        values[key] = datetime.fromisoformat(values[key])
    values["instrument_bindings"] = tuple(tuple(item) for item in values["instrument_bindings"])
    values["source_boundaries"] = tuple(
        (item[0], datetime.fromisoformat(item[1])) for item in values["source_boundaries"]
    )
    values["calendar_bindings"] = tuple(tuple(item) for item in values["calendar_bindings"])
    return K5RefreshReminderRecord(**values)


def _integrity(record: K5RefreshReminderRecord) -> str:
    values = asdict(record)
    values["integrity_sha256"] = ""
    return _integrity_values(values)


def _integrity_values(values: dict[str, object]) -> str:
    material = dict(values)
    material.setdefault("product", "SWING")
    material.setdefault("remaining_criterion", "K5_NON_EXTENSION")
    material.setdefault("authority", REFRESH_REMINDER_AUTHORITY)
    material.setdefault("contract_identity", REFRESH_REMINDER_CONTRACT)
    material.setdefault("contract_version", REFRESH_REMINDER_VERSION)
    material["integrity_sha256"] = ""
    return sha256(json.dumps(
        material, sort_keys=True, default=_json_default, separators=(",", ":")
    ).encode()).hexdigest()


def _json_default(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError


def _timer_scheduler(delay: float, operation: Callable[[], None]) -> Timer:
    timer = Timer(delay, operation)
    timer.daemon = True
    timer.start()
    return timer


__all__ = [
    "K5RefreshReminderRecord", "K5RefreshReminderSnapshot",
    "K5RefreshReminderStore", "RefreshReminderState",
    "SwingK5RefreshReminderWorkflow", "next_completed_one_hour_boundary",
]
