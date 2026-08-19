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
