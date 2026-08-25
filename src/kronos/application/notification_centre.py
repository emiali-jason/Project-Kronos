"""Durable Sponsor lifecycle over governed Swing notification sources.

The centre owns presentation lifecycle only.  It never deletes or rewrites a
source watch/event, evaluates analysis, creates a position, or calls a broker.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from typing import Callable

from kronos.application.notifications import (
    ManagedNotification,
    NotificationState,
    NotificationWorkspaceSnapshot,
)
from kronos.application.swing_ux10 import (
    Ux10NotificationFamily,
    Ux10NotificationRecord,
    Ux10NotificationSnapshot,
    Ux10NotificationType,
    Ux10Priority,
)


NOTIFICATION_CENTRE_CONTRACT = "KRONOS-SPONSOR-NOTIFICATION-LIFECYCLE-V1"
NOTIFICATION_CENTRE_VERSION = "1"
NOTIFICATION_CENTRE_AUTHORITY = (
    "PRESENTATION_LIFECYCLE_ONLY_NO_SOURCE_ANALYTICAL_POSITION_OR_BROKER_AUTHORITY"
)
DEFAULT_NOTIFICATION_CENTRE_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "swing-v1" / "notification-centre-v1"
)


class SponsorNotificationState(StrEnum):
    LIVE = "LIVE"
    EXPIRED = "EXPIRED"


class SponsorNotificationFamily(StrEnum):
    ACTIONABLE = "ACTIONABLE"
    INFORMATIONAL = "INFORMATIONAL"
    FAILURE_OPERABILITY = "FAILURE_OPERABILITY"
    TIME_BOUND_REMINDER = "TIME_BOUND_REMINDER"


class SponsorNotificationAction(StrEnum):
    NONE = "NONE"
    OPEN = "OPEN"
    REFRESH = "REFRESH"


class SponsorNotificationFilter(StrEnum):
    ALL = "ALL"
    LIVE = "LIVE"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class SponsorNotificationHistoryEvent:
    event_identity: str
    event_type: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class SponsorNotificationRecord:
    notification_identity: str
    source_identity: str
    source_kind: str
    source_run_identity: str | None
    product: str
    family: SponsorNotificationFamily
    notification_type: str
    priority: str
    instrument: str | None
    summary: str
    action: SponsorNotificationAction
    action_path: str
    created_at: datetime
    updated_at: datetime
    state: SponsorNotificationState
    dismissed: bool
    reactivatable: bool
    reactivated_from: str | None
    generation: int
    last_reminded_at: datetime | None
    reminder_count: int
    next_reminder_at: datetime | None
    recurrence_cancelled: bool
    history: tuple[SponsorNotificationHistoryEvent, ...]
    integrity_sha256: str
    contract_identity: str = NOTIFICATION_CENTRE_CONTRACT
    contract_version: str = NOTIFICATION_CENTRE_VERSION
    authority: str = NOTIFICATION_CENTRE_AUTHORITY

    def __post_init__(self) -> None:
        if (
            len(self.notification_identity) != 64
            or not self.source_identity
            or self.source_kind not in {"UX08_WATCH", "UX10_EVENT"}
            or self.product != "SWING"
            or type(self.family) is not SponsorNotificationFamily
            or not self.notification_type
            or self.priority not in {"NORMAL", "HIGH"}
            or not self.summary
            or type(self.action) is not SponsorNotificationAction
            or self.created_at.tzinfo is None
            or self.updated_at.tzinfo is None
            or self.updated_at < self.created_at
            or type(self.state) is not SponsorNotificationState
            or type(self.dismissed) is not bool
            or type(self.reactivatable) is not bool
            or type(self.generation) is not int or self.generation < 0
            or type(self.reminder_count) is not int or self.reminder_count < 0
            or (self.last_reminded_at is not None and self.last_reminded_at.tzinfo is None)
            or (self.next_reminder_at is not None and self.next_reminder_at.tzinfo is None)
            or type(self.recurrence_cancelled) is not bool
            or any(
                len(item.event_identity) != 64 or item.occurred_at.tzinfo is None
                for item in self.history
            )
            or self.contract_identity != NOTIFICATION_CENTRE_CONTRACT
            or self.contract_version != NOTIFICATION_CENTRE_VERSION
            or self.authority != NOTIFICATION_CENTRE_AUTHORITY
            or self.integrity_sha256 != _integrity(self)
        ):
            raise ValueError("SPONSOR_NOTIFICATION_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorNotificationCentreSnapshot:
    records: tuple[SponsorNotificationRecord, ...]
    websocket_state: str

    @property
    def visible(self) -> tuple[SponsorNotificationRecord, ...]:
        return tuple(item for item in self.records if not item.dismissed)

    @property
    def live_count(self) -> int:
        return sum(item.state is SponsorNotificationState.LIVE for item in self.visible)

    @property
    def expired_count(self) -> int:
        return sum(item.state is SponsorNotificationState.EXPIRED for item in self.visible)

    @property
    def revision(self) -> str:
        material = tuple(
            (item.notification_identity, item.integrity_sha256)
            for item in self.records
        ) + (("WS", self.websocket_state),)
        return sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SponsorNotificationQuery:
    state: SponsorNotificationFilter = SponsorNotificationFilter.ALL
    search: str = ""
    page: int = 1
    page_size: int = 25

    def __post_init__(self) -> None:
        if (
            type(self.state) is not SponsorNotificationFilter
            or type(self.search) is not str or len(self.search) > 80
            or type(self.page) is not int or self.page < 1
            or type(self.page_size) is not int or not 1 <= self.page_size <= 100
        ):
            raise ValueError("SPONSOR_NOTIFICATION_QUERY_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorNotificationProjection:
    snapshot: SponsorNotificationCentreSnapshot
    query: SponsorNotificationQuery
    records: tuple[SponsorNotificationRecord, ...]
    page_records: tuple[SponsorNotificationRecord, ...]
    page_count: int


class SponsorNotificationLifecycleStore:
    """Append-only lifecycle revisions; source evidence is never addressed."""

    def __init__(self, root: Path = DEFAULT_NOTIFICATION_CENTRE_ROOT) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def retain(self, record: SponsorNotificationRecord) -> None:
        directory = self.root / record.notification_identity
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (
            record.updated_at.isoformat().replace(":", "")
            + "-" + record.integrity_sha256 + ".json"
        )
        payload = _record_dict(record)
        try:
            with path.open("x", encoding="utf-8") as target:
                json.dump(payload, target, sort_keys=True, separators=(",", ":"))
                target.flush()
                os.fsync(target.fileno())
            os.chmod(path, 0o600)
        except FileExistsError:
            if json.loads(path.read_text(encoding="utf-8")) != payload:
                raise ValueError("SPONSOR_NOTIFICATION_IMMUTABILITY_VIOLATION")
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("SPONSOR_NOTIFICATION_PERSISTENCE_FAILED") from error

    def load_current(self) -> tuple[SponsorNotificationRecord, ...]:
        latest: dict[str, SponsorNotificationRecord] = {}
        for path in sorted(self.root.glob("*/*.json")):
            try:
                record = _record_from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            previous = latest.get(record.notification_identity)
            if previous is None or (
                record.updated_at, len(record.history), record.integrity_sha256
            ) > (
                previous.updated_at, len(previous.history), previous.integrity_sha256
            ):
                latest[record.notification_identity] = record
        return tuple(sorted(latest.values(), key=_record_order))


class SponsorNotificationCentre:
    """Compose governed sources with durable Sponsor presentation lifecycle."""

    def __init__(
        self,
        store: SponsorNotificationLifecycleStore | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        reminder_boundary_resolver: (
            Callable[[str, datetime], datetime | None] | None
        ) = None,
    ) -> None:
        self._store = store or SponsorNotificationLifecycleStore()
        self._clock = clock
        self._reminder_boundary_resolver = reminder_boundary_resolver
        self._lock = RLock()
        self._records = {
            item.notification_identity: item for item in self._store.load_current()
        }

    def synchronize(
        self,
        watches: NotificationWorkspaceSnapshot,
        ux10: Ux10NotificationSnapshot,
        *,
        current_run_identity: str | None,
        websocket_state: str,
    ) -> SponsorNotificationCentreSnapshot:
        if (
            type(watches) is not NotificationWorkspaceSnapshot
            or type(ux10) is not Ux10NotificationSnapshot
            or websocket_state not in {"CONNECTED", "DISCONNECTED", "IDLE"}
        ):
            raise TypeError("SPONSOR_NOTIFICATION_SOURCE_INVALID")
        now = self._clock()
        watch_identities = {item.source_identity for item in watches.records}
        sources = tuple(_watch_source(item) for item in watches.records) + tuple(
            _ux10_source(item, ux10, current_run_identity)
            for item in ux10.records
            if not (
                item.family is Ux10NotificationFamily.PROMOTION_WATCH
                and item.watch_identity in watch_identities
            )
        )
        for source in sources:
            self._synchronize_source(source, now)
        with self._lock:
            records = tuple(sorted(self._records.values(), key=_record_order))
        return SponsorNotificationCentreSnapshot(records, websocket_state)

    def dismiss(
        self, notification_identity: str, expected_integrity: str, *, occurred_at: datetime | None = None
    ) -> SponsorNotificationRecord:
        record = self._required(notification_identity)
        if record.dismissed:
            return record
        self._expect(record, expected_integrity)
        return self._revise(
            record, occurred_at or self._clock(), "SPONSOR_DISMISSED",
            dismissed=True, recurrence_cancelled=True, next_reminder_at=None,
        )

    def dismiss_expired(self, *, occurred_at: datetime | None = None) -> int:
        now = occurred_at or self._clock()
        with self._lock:
            values = tuple(
                item for item in self._records.values()
                if not item.dismissed and item.state is SponsorNotificationState.EXPIRED
            )
        for item in values:
            self._revise(
                item, now, "SPONSOR_DISMISSED_EXPIRED",
                dismissed=True, recurrence_cancelled=True, next_reminder_at=None,
            )
        return len(values)

    def expire(
        self,
        notification_identity: str,
        expected_integrity: str,
        *,
        source_still_valid: bool,
        occurred_at: datetime | None = None,
    ) -> SponsorNotificationRecord:
        """Record governed resolution without changing the immutable source."""

        record = self._required(notification_identity)
        if record.state is SponsorNotificationState.EXPIRED:
            return record
        self._expect(record, expected_integrity)
        return self._revise(
            record, occurred_at or self._clock(), "GOVERNED_EXPIRED",
            state=SponsorNotificationState.EXPIRED,
            reactivatable=(record.reactivatable and source_still_valid),
            next_reminder_at=None,
        )

    def reactivate(
        self,
        notification_identity: str,
        expected_integrity: str,
        *,
        source_valid: bool,
        occurred_at: datetime | None = None,
    ) -> SponsorNotificationRecord:
        source = self._required(notification_identity)
        if source.dismissed or source.state is not SponsorNotificationState.EXPIRED:
            raise ValueError("NOTIFICATION_REACTIVATION_STATE_INVALID")
        self._expect(source, expected_integrity)
        if not source.reactivatable or not source_valid:
            raise ValueError("NOTIFICATION_SOURCE_SUPERSEDED")
        with self._lock:
            existing = next((
                item for item in self._records.values()
                if item.reactivated_from == source.notification_identity
                and not item.dismissed and item.state is SponsorNotificationState.LIVE
            ), None)
        if existing is not None:
            return existing
        now = occurred_at or self._clock()
        generation = source.generation + 1
        identity = sha256(
            f"REACTIVATED:{source.notification_identity}:{generation}".encode()
        ).hexdigest()
        reminder = source.family is SponsorNotificationFamily.TIME_BOUND_REMINDER
        values = asdict(source)
        values.update(
            notification_identity=identity,
            created_at=now,
            updated_at=now,
            state=SponsorNotificationState.LIVE,
            dismissed=False,
            reactivated_from=source.notification_identity,
            generation=generation,
            last_reminded_at=now if reminder else None,
            reminder_count=1 if reminder else 0,
            next_reminder_at=(
                self._next_reminder(source.source_identity, now) if reminder else None
            ),
            recurrence_cancelled=False,
            history=(_history(identity, "REACTIVATED", now),),
            integrity_sha256="",
        )
        record = _from_values(values)
        self._retain(record)
        return record

    def record(self, notification_identity: str) -> SponsorNotificationRecord | None:
        with self._lock:
            return self._records.get(notification_identity)

    def _synchronize_source(self, source: dict[str, object], now: datetime) -> None:
        identity = sha256(f"SOURCE:{source['source_identity']}:0".encode()).hexdigest()
        with self._lock:
            generations = tuple(
                item for item in self._records.values()
                if item.source_identity == source["source_identity"]
            )
            latest = max(generations, key=lambda item: item.generation, default=None)
        if latest is None:
            values = dict(source)
            values.update(
                notification_identity=identity, product="SWING",
                created_at=source["created_at"], updated_at=source["created_at"],
                dismissed=False, reactivated_from=None, generation=0,
                last_reminded_at=(
                    source["created_at"]
                    if source["family"] is SponsorNotificationFamily.TIME_BOUND_REMINDER
                    else None
                ),
                reminder_count=(
                    1 if source["family"] is SponsorNotificationFamily.TIME_BOUND_REMINDER else 0
                ),
                next_reminder_at=(
                    self._next_reminder(
                        str(source["source_identity"]), source["created_at"]
                    )
                    if source["state"] is SponsorNotificationState.LIVE
                    and source["family"] is SponsorNotificationFamily.TIME_BOUND_REMINDER
                    else None
                ),
                recurrence_cancelled=False,
                history=(_history(identity, "CREATED", source["created_at"]),),
                integrity_sha256="",
            )
            latest = _from_values(values)
            self._retain(latest)
        if latest.dismissed:
            return
        desired = source["state"]
        if latest.state is SponsorNotificationState.LIVE and desired is SponsorNotificationState.EXPIRED:
            latest = self._revise(
                latest, now, "SOURCE_RESOLVED", state=SponsorNotificationState.EXPIRED,
                reactivatable=bool(source["reactivatable"]), next_reminder_at=None,
            )
        if (
            latest.state is SponsorNotificationState.LIVE
            and latest.family is SponsorNotificationFamily.TIME_BOUND_REMINDER
            and not latest.recurrence_cancelled
            and latest.next_reminder_at is None
        ):
            next_due = self._next_reminder(latest.source_identity, now)
            if next_due is not None:
                latest = self._revise(
                    latest, now, "REMINDER_SCHEDULED", next_reminder_at=next_due,
                )
        if (
            latest.state is SponsorNotificationState.LIVE
            and latest.family is SponsorNotificationFamily.TIME_BOUND_REMINDER
            and not latest.recurrence_cancelled
            and latest.next_reminder_at is not None
            and now >= latest.next_reminder_at
        ):
            next_due = self._next_reminder(latest.source_identity, now)
            self._revise(
                latest, now, "HOURLY_REMINDER",
                last_reminded_at=now,
                reminder_count=latest.reminder_count + 1,
                next_reminder_at=next_due,
            )

    def _next_reminder(
        self, source_identity: str, after: datetime
    ) -> datetime | None:
        if self._reminder_boundary_resolver is None:
            return None
        boundary = self._reminder_boundary_resolver(source_identity, after)
        if boundary is not None and (
            boundary.tzinfo is None or boundary <= after
        ):
            raise ValueError("NOTIFICATION_REMINDER_BOUNDARY_INVALID")
        return boundary

    def _required(self, identity: str) -> SponsorNotificationRecord:
        if len(identity) != 64:
            raise ValueError("NOTIFICATION_IDENTITY_INVALID")
        with self._lock:
            record = self._records.get(identity)
        if record is None:
            raise ValueError("NOTIFICATION_NOT_FOUND")
        return record

    @staticmethod
    def _expect(record: SponsorNotificationRecord, expected: str) -> None:
        if expected != record.integrity_sha256:
            raise ValueError("NOTIFICATION_STALE_REVISION")

    def _revise(
        self, record: SponsorNotificationRecord, occurred_at: datetime,
        event_type: str, **updates: object,
    ) -> SponsorNotificationRecord:
        if occurred_at.tzinfo is None or occurred_at < record.updated_at:
            raise ValueError("NOTIFICATION_EVENT_TIME_INVALID")
        values = asdict(record)
        values.update(updates)
        values.update(
            updated_at=occurred_at,
            history=record.history + (_history(record.notification_identity, event_type, occurred_at),),
            integrity_sha256="",
        )
        updated = _from_values(values)
        self._retain(updated)
        return updated

    def _retain(self, record: SponsorNotificationRecord) -> None:
        self._store.retain(record)
        with self._lock:
            self._records[record.notification_identity] = record


def project_sponsor_notifications(
    snapshot: SponsorNotificationCentreSnapshot,
    query: SponsorNotificationQuery,
) -> SponsorNotificationProjection:
    records = snapshot.visible
    if query.state is not SponsorNotificationFilter.ALL:
        state = SponsorNotificationState(query.state.value)
        records = tuple(item for item in records if item.state is state)
    needle = query.search.strip().casefold()
    if needle:
        records = tuple(
            item for item in records
            if needle in ((item.instrument or "") + " " + item.summary).casefold()
        )
    records = tuple(sorted(records, key=_record_order))
    pages = (len(records) + query.page_size - 1) // query.page_size
    start = (query.page - 1) * query.page_size
    return SponsorNotificationProjection(
        snapshot, query, records, records[start:start + query.page_size], pages
    )


def _watch_source(item: ManagedNotification) -> dict[str, object]:
    live = item.state in {NotificationState.ACTIVE, NotificationState.TRIGGERED}
    return dict(
        source_identity=item.source_identity,
        source_kind="UX08_WATCH",
        source_run_identity=item.source_run_identity,
        family=SponsorNotificationFamily.ACTIONABLE,
        notification_type=(
            "PROMOTION_WATCH_REACHED"
            if item.state is NotificationState.TRIGGERED else "PROGRESSION_WATCH"
        ),
        priority="HIGH" if item.state is NotificationState.TRIGGERED else "NORMAL",
        instrument=item.instrument,
        summary=(item.trigger_summary or item.condition_summary),
        action=SponsorNotificationAction.OPEN,
        action_path=(
            f"/swing/analysis-details/{item.source_run_identity}/{item.instrument}"
            if item.state is not NotificationState.STALE else ""
        ),
        state=SponsorNotificationState.LIVE if live else SponsorNotificationState.EXPIRED,
        # An inactive source watch can only be restarted by the governed watch
        # workflow.  The Sponsor notification centre must never imply that its
        # presentation-only recycle action reactivates monitoring authority.
        reactivatable=False,
        created_at=item.triggered_at or item.activated_at,
    )


def _ux10_source(
    item: Ux10NotificationRecord,
    snapshot: Ux10NotificationSnapshot,
    current_run_identity: str | None,
) -> dict[str, object]:
    reminder = item.notification_type is Ux10NotificationType.REFRESH_ANALYSIS_REMINDER
    outage = item.notification_type in {
        Ux10NotificationType.WEBSOCKET_DISCONNECTED,
        Ux10NotificationType.MONITORING_GAP_RECONCILIATION_REQUIRED,
    }
    current_incidents = {value.notification_id for value in snapshot.active_incidents}
    promotion = item.family is Ux10NotificationFamily.PROMOTION_WATCH
    live = (
        (reminder and (current_run_identity is None or item.run_identity == current_run_identity))
        or (outage and item.notification_id in current_incidents)
        or (promotion and item.run_identity is not None and item.run_identity == current_run_identity)
    )
    family = (
        SponsorNotificationFamily.TIME_BOUND_REMINDER if reminder
        else SponsorNotificationFamily.FAILURE_OPERABILITY if outage
        else SponsorNotificationFamily.ACTIONABLE if promotion
        else SponsorNotificationFamily.INFORMATIONAL
    )
    action = (
        SponsorNotificationAction.REFRESH if reminder
        else SponsorNotificationAction.OPEN
        if family in {SponsorNotificationFamily.ACTIONABLE, SponsorNotificationFamily.FAILURE_OPERABILITY}
        else SponsorNotificationAction.NONE
    )
    path = "/swing/analysis" if action is SponsorNotificationAction.REFRESH else (
        "/journal" if action is SponsorNotificationAction.OPEN else ""
    )
    return dict(
        source_identity=item.notification_id,
        source_kind="UX10_EVENT",
        source_run_identity=item.run_identity,
        family=family,
        notification_type=item.notification_type.value,
        priority=item.priority.value,
        instrument=item.instrument,
        summary=item.summary,
        action=action,
        action_path=path,
        state=SponsorNotificationState.LIVE if live else SponsorNotificationState.EXPIRED,
        reactivatable=reminder and live,
        created_at=item.created_at,
    )


def _record_order(item: SponsorNotificationRecord) -> tuple[object, ...]:
    return (
        0 if item.state is SponsorNotificationState.LIVE else 1,
        -item.updated_at.timestamp(),
        item.notification_identity,
    )


def _history(identity: str, event_type: str, occurred_at: datetime) -> SponsorNotificationHistoryEvent:
    event = sha256(
        f"{identity}:{event_type}:{occurred_at.isoformat()}".encode()
    ).hexdigest()
    return SponsorNotificationHistoryEvent(event, event_type, occurred_at)


def _from_values(values: dict[str, object]) -> SponsorNotificationRecord:
    values = dict(values)
    values["family"] = SponsorNotificationFamily(values["family"])
    values["action"] = SponsorNotificationAction(values["action"])
    values["state"] = SponsorNotificationState(values["state"])
    values["history"] = tuple(
        item if type(item) is SponsorNotificationHistoryEvent
        else SponsorNotificationHistoryEvent(**item)
        for item in values["history"]
    )
    return SponsorNotificationRecord(**(
        values | {"integrity_sha256": _integrity_values(values)}
    ))


def _record_dict(record: SponsorNotificationRecord) -> dict[str, object]:
    values = asdict(record)
    for key in ("family", "action", "state"):
        values[key] = getattr(record, key).value
    for key in ("created_at", "updated_at", "last_reminded_at", "next_reminder_at"):
        value = getattr(record, key)
        values[key] = None if value is None else value.isoformat()
    values["history"] = tuple(
        dict(
            event_identity=item.event_identity,
            event_type=item.event_type,
            occurred_at=item.occurred_at.isoformat(),
        )
        for item in record.history
    )
    return values


def _record_from_dict(value: object) -> SponsorNotificationRecord:
    if type(value) is not dict:
        raise ValueError("SPONSOR_NOTIFICATION_RECORD_INVALID")
    values = dict(value)
    values["family"] = SponsorNotificationFamily(values["family"])
    values["action"] = SponsorNotificationAction(values["action"])
    values["state"] = SponsorNotificationState(values["state"])
    for key in ("created_at", "updated_at", "last_reminded_at", "next_reminder_at"):
        values[key] = datetime.fromisoformat(values[key]) if values.get(key) else None
    values["history"] = tuple(
        SponsorNotificationHistoryEvent(
            item["event_identity"], item["event_type"],
            datetime.fromisoformat(item["occurred_at"]),
        )
        for item in values["history"]
    )
    return SponsorNotificationRecord(**values)


def _integrity(record: SponsorNotificationRecord) -> str:
    values = asdict(record)
    values["integrity_sha256"] = ""
    return _integrity_values(values)


def _integrity_values(values: dict[str, object]) -> str:
    material = dict(values)
    material.setdefault("contract_identity", NOTIFICATION_CENTRE_CONTRACT)
    material.setdefault("contract_version", NOTIFICATION_CENTRE_VERSION)
    material.setdefault("authority", NOTIFICATION_CENTRE_AUTHORITY)
    material["integrity_sha256"] = ""
    return sha256(json.dumps(
        material, sort_keys=True, default=_json_default, separators=(",", ":")
    ).encode()).hexdigest()


def _json_default(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, SponsorNotificationHistoryEvent):
        return asdict(value)
    raise TypeError


__all__ = [
    "SponsorNotificationAction", "SponsorNotificationCentre",
    "SponsorNotificationCentreSnapshot", "SponsorNotificationFamily",
    "SponsorNotificationFilter", "SponsorNotificationLifecycleStore",
    "SponsorNotificationProjection", "SponsorNotificationQuery",
    "SponsorNotificationRecord", "SponsorNotificationState",
    "project_sponsor_notifications",
]
