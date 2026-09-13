"""Product-neutral Sponsor projection over product-owned notification records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json

class NotificationProduct(StrEnum):
    SWING = "SWING"
    INTRADAY = "INTRADAY"


class NotificationState(StrEnum):
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    INACTIVE = "INACTIVE"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class NotificationHistoryEvent:
    event_identity: str
    event_type: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ManagedNotification:
    source_identity: str
    product: NotificationProduct
    instrument: str
    direction: str
    condition_identity: str
    condition_summary: str
    timeframe: str
    comparator: str
    authoritative_level: str
    source_run_identity: str
    activated_at: datetime
    state: NotificationState
    triggered_at: datetime | None
    trigger_summary: str
    consequence: str
    history: tuple[NotificationHistoryEvent, ...]
    monitoring_active: bool


@dataclass(frozen=True, slots=True)
class NotificationWorkspaceSnapshot:
    records: tuple[ManagedNotification, ...]

    def for_product(self, product: NotificationProduct | None) -> tuple[ManagedNotification, ...]:
        if product is None:
            return self.records
        return tuple(item for item in self.records if item.product is product)

    @property
    def action_required(self) -> tuple[ManagedNotification, ...]:
        return tuple(
            item for item in self.records
            if item.state is NotificationState.TRIGGERED
        )

    @property
    def revision(self) -> str:
        material = tuple(
            (
                item.source_identity,
                item.state.value,
                item.triggered_at.isoformat() if item.triggered_at else None,
                tuple(event.event_identity for event in item.history),
            )
            for item in self.records
        )
        return sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()


__all__ = [
    "ManagedNotification", "NotificationHistoryEvent", "NotificationProduct",
    "NotificationState", "NotificationWorkspaceSnapshot",
]


def notify_persisted(store, kind, identity):
    """Notify independent projections; failure cannot invalidate a committed source."""
    for attribute, failure in (
        ("notification_listener", "NOTIFICATION_PROJECTION_UNAVAILABLE"),
        ("journal_listener", "JOURNAL_PROJECTION_UNAVAILABLE"),
    ):
        listener = getattr(store, attribute, None)
        if listener is None:
            continue
        try:
            listener(kind, identity)
        except Exception:
            setattr(store, attribute.replace("listener", "failure"), failure)


def notify_journal_persisted(store, kind, identity):
    """Notify only the optional Journal projection after an immutable write."""
    listener = getattr(store, "journal_listener", None)
    if listener is not None:
        try:
            listener(kind, identity)
        except Exception:
            store.journal_failure = "JOURNAL_PROJECTION_UNAVAILABLE"
