"""Durable time-based reminders for K5-only KR-370 READY opportunities.

The workflow uses governed DOMAIN-008 session boundaries and owns reminder
delivery timing only.  It never evaluates K5, watches prices, or creates a
trading state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock, Timer
from typing import Callable
from zoneinfo import ZoneInfo

from kronos.market.calendar import MarketCalendarPublisher
from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalClassification,
    Kr370AnalyticalPromotionRecord,
    Kr370CriterionIdentity,
)
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
    ) -> None:
        self._store = store or K5RefreshReminderStore()
        self._calendar = calendar or MarketCalendarPublisher()
        self._listener = notification_listener
        self._clock = clock
        self._scheduler = scheduler or _timer_scheduler
        self._lock = RLock()
        self._records = {
            item.reminder_identity: item for item in self._store.load_current()
        }
        self._timers: dict[str, object] = {}
        for record in tuple(self._records.values()):
            if record.state is RefreshReminderState.PENDING:
                self._schedule(record)

    def snapshot(self) -> K5RefreshReminderSnapshot:
        with self._lock:
            return K5RefreshReminderSnapshot(tuple(sorted(
                self._records.values(), key=lambda item: item.created_at, reverse=True,
            )))

    def synchronize(
        self,
        current_run_identity: str | None,
        promotions: tuple[Kr370AnalyticalPromotionRecord, ...],
        exchange_by_instrument: dict[str, str],
    ) -> K5RefreshReminderSnapshot:
        if current_run_identity is not None and not is_swing_analysis_run_id(current_run_identity):
            raise ValueError("K5_REFRESH_REMINDER_RUN_INVALID")
        if type(promotions) is not tuple or any(
            type(item) is not Kr370AnalyticalPromotionRecord for item in promotions
        ):
            raise TypeError("K5_REFRESH_REMINDER_PROMOTIONS_INVALID")
        now = self._clock()
        eligible = tuple(
            item for item in promotions
            if item.run_identity == current_run_identity
            and item.classification in {
                Kr370AnalyticalClassification.BUY_READY,
                Kr370AnalyticalClassification.SELL_READY,
            }
            and item.sole_missing_criterion is Kr370CriterionIdentity.K5_NON_EXTENSION
        )
        grouped: dict[datetime, list[tuple[Kr370AnalyticalPromotionRecord, str]]] = {}
        for item in eligible:
            exchange = exchange_by_instrument.get(item.canonical_instrument)
            if exchange not in {"NSE", "MCX"}:
                raise ValueError("K5_REFRESH_REMINDER_EXCHANGE_UNAVAILABLE")
            source = dict(item.observation_boundaries)[FactualTimeframe.ONE_HOUR.value]
            due = next_completed_one_hour_boundary(
                self._calendar, exchange, source, observed_at=now
            )
            grouped.setdefault(due, []).append((item, exchange))

        desired: set[str] = set()
        for due, values in grouped.items():
            bindings = tuple(sorted(
                (
                    item.canonical_instrument,
                    item.native_assessment_sha256,
                    item.classification.value,
                    exchange,
                )
                for item, exchange in values
            ))
            sources = tuple(
                (item.canonical_instrument,
                 dict(item.observation_boundaries)[FactualTimeframe.ONE_HOUR.value])
                for item, _ in sorted(values, key=lambda value: value[0].canonical_instrument)
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
                self._schedule(record)

        with self._lock:
            pending = tuple(
                item for item in self._records.values()
                if item.state is RefreshReminderState.PENDING
                and item.reminder_identity not in desired
            )
        for record in pending:
            self._transition(record, RefreshReminderState.SUPERSEDED, now)
        return self.snapshot()

    def close(self) -> None:
        with self._lock:
            timers = tuple(self._timers.values())
            self._timers.clear()
        for timer in timers:
            cancel = getattr(timer, "cancel", None)
            if callable(cancel):
                cancel()

    def _schedule(self, record: K5RefreshReminderRecord) -> None:
        delay = max(
            0.0,
            (record.next_eligible_completed_1h_boundary - self._clock()).total_seconds(),
        )
        timer = self._scheduler(
            delay, lambda: self._fire(record.reminder_identity)
        )
        with self._lock:
            self._timers[record.reminder_identity] = timer

    def _fire(self, reminder_identity: str) -> None:
        with self._lock:
            record = self._records.get(reminder_identity)
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
        self._retain(updated)
        with self._lock:
            timer = self._timers.pop(record.reminder_identity, None)
        cancel = getattr(timer, "cancel", None)
        if callable(cancel):
            cancel()

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
    for offset in range((publication.coverage_end - zone_source.date()).days + 1):
        day = zone_source.date() + timedelta(days=offset)
        schedule = calendar.schedule(exchange, day, observed_at=observed_at)
        if schedule is None:
            continue
        for window in schedule.windows:
            cursor = window.window_open
            while cursor < window.window_close:
                boundary = min(cursor + timedelta(hours=1), window.window_close)
                if boundary > source_boundary:
                    return boundary
                cursor = boundary
    raise ValueError("K5_REFRESH_NEXT_COMPLETED_1H_BOUNDARY_UNAVAILABLE")


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
