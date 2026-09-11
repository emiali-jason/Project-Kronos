"""Notification-source projections from persisted WO-09 authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from kronos.intraday.wo09_readiness import AttentionState, CurrentnessState, ReadinessRecord, ReadinessState, artifact_bytes
from kronos.intraday.wo09_watch import WatchState, Wo09Watch


class Wo09NotificationState(StrEnum):
    ACTIVE = "ACTIVE"
    WITHDRAWN = "WITHDRAWN"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class Wo09NotificationSource:
    source_identity: str
    source_integrity: str
    readiness_identity: str
    canonical_subject_identity: str
    direction: str
    readiness_state: ReadinessState
    notification_type: str
    satisfied_count: int
    outstanding_count: int
    priority: str
    state: Wo09NotificationState
    summary: str
    created_at: datetime
    authority: str = "PERSISTED_WO09_PROJECTION_ONLY_NO_READINESS_CALCULATION_OR_PROVIDER_AUTHORITY"

    def __post_init__(self) -> None:
        values = _values(self)
        if (
            not self.source_identity or not self.readiness_identity
            or not self.canonical_subject_identity or self.direction not in {"LONG", "SHORT"}
            or type(self.readiness_state) is not ReadinessState
            or not self.notification_type
            or type(self.satisfied_count) is not int or not 3 <= self.satisfied_count <= 5
            or type(self.outstanding_count) is not int
            or self.satisfied_count + self.outstanding_count != 5
            or self.priority not in {"NORMAL", "HIGH"} or self.created_at.tzinfo is None
            or type(self.state) is not Wo09NotificationState
            or self.authority != "PERSISTED_WO09_PROJECTION_ONLY_NO_READINESS_CALCULATION_OR_PROVIDER_AUTHORITY"
            or self.source_integrity != _identity("INTEGRITY-INTRADAY-WO09-NOTIFICATION-", values)
        ):
            raise ValueError("WO09_NOTIFICATION_SOURCE_INVALID")


def project_notification(record: ReadinessRecord, *, currentness: CurrentnessState | None = None,
                         effective_at: datetime | None = None) -> Wo09NotificationSource | None:
    """Project one immutable source; repeated projection is deterministic/deduplicated."""
    if type(record) is not ReadinessRecord:
        raise ValueError("WO09_NOTIFICATION_INPUT_INVALID")
    if record.attention_state is AttentionState.NONE:
        return None
    effective_currentness = record.currentness if currentness is None else currentness
    if type(effective_currentness) is not CurrentnessState:
        raise ValueError("WO09_NOTIFICATION_CURRENTNESS_INVALID")
    state = (
        Wo09NotificationState.STALE
        if effective_currentness in {CurrentnessState.REASSESSMENT_DUE, CurrentnessState.STALE_UNAVAILABLE}
        else Wo09NotificationState.WITHDRAWN
        if effective_currentness is CurrentnessState.SUPERSEDED
        else Wo09NotificationState.ACTIVE
    )
    values = dict(
        readiness_identity=record.readiness_identity,
        canonical_subject_identity=record.canonical_subject_identity,
        direction=record.direction, readiness_state=record.readiness_state,
        notification_type=record.readiness_state.value,
        satisfied_count=record.satisfied_count, outstanding_count=record.outstanding_count,
        priority="HIGH" if record.attention_state in {AttentionState.HIGH, AttentionState.NEXT_WO_ONLY} else "NORMAL",
        state=state,
        summary=f"{record.canonical_subject_identity} {record.readiness_state.value} {record.satisfied_count}/5",
        created_at=record.created_at if effective_at is None else effective_at,
        authority="PERSISTED_WO09_PROJECTION_ONLY_NO_READINESS_CALCULATION_OR_PROVIDER_AUTHORITY",
    )
    identity = _identity("INTRADAY-WO09-NOTIFICATION-", {
        "readiness": record.readiness_identity,
        "currentness": effective_currentness,
        "effective_at": record.created_at if effective_at is None else effective_at,
    })
    return Wo09NotificationSource(source_identity=identity,
                                  source_integrity=_identity("INTEGRITY-INTRADAY-WO09-NOTIFICATION-", values), **values)


def project_reassessment_notification(
    record: ReadinessRecord,
    watch: Wo09Watch,
    *,
    effective_at: datetime,
) -> Wo09NotificationSource:
    """Project a governed criterion event without changing readiness."""
    if (
        type(record) is not ReadinessRecord
        or type(watch) is not Wo09Watch
        or watch.state is not WatchState.TRIGGERED
        or watch.readiness_identity != record.readiness_identity
        or watch.canonical_subject_identity != record.canonical_subject_identity
        or record.attention_state not in {AttentionState.NORMAL, AttentionState.HIGH}
        or effective_at.tzinfo is None
    ):
        raise ValueError("WO09_REASSESSMENT_NOTIFICATION_INVALID")
    notification_type = f"CRITERION_REASSESSMENT_EVENT:{watch.criterion_id.value}"
    values = dict(
        readiness_identity=record.readiness_identity,
        canonical_subject_identity=record.canonical_subject_identity,
        direction=record.direction,
        readiness_state=record.readiness_state,
        notification_type=notification_type,
        satisfied_count=record.satisfied_count,
        outstanding_count=record.outstanding_count,
        priority="HIGH" if record.attention_state is AttentionState.HIGH else "NORMAL",
        state=Wo09NotificationState.ACTIVE,
        summary=(
            f"{record.canonical_subject_identity} {watch.criterion_id.value} "
            "governed reassessment event"
        ),
        created_at=effective_at,
        authority="PERSISTED_WO09_PROJECTION_ONLY_NO_READINESS_CALCULATION_OR_PROVIDER_AUTHORITY",
    )
    identity = _identity("INTRADAY-WO09-NOTIFICATION-", {
        "readiness": record.readiness_identity,
        "watch": watch.watch_identity,
        "watch_integrity": watch.integrity_identity,
        "effective_at": effective_at,
    })
    return Wo09NotificationSource(
        source_identity=identity,
        source_integrity=_identity("INTEGRITY-INTRADAY-WO09-NOTIFICATION-", values),
        **values,
    )


def deduplicate_sources(values: tuple[Wo09NotificationSource, ...]) -> tuple[Wo09NotificationSource, ...]:
    retained: dict[str, Wo09NotificationSource] = {}
    for value in values:
        prior = retained.get(value.source_identity)
        if prior is not None and prior != value:
            raise ValueError("WO09_NOTIFICATION_SOURCE_CONFLICT")
        retained[value.source_identity] = value
    return tuple(sorted(retained.values(), key=lambda item: (-int(item.priority == "HIGH"), item.canonical_subject_identity)))


def _values(value: Wo09NotificationSource) -> dict[str, object]:
    return {name: getattr(value, name) for name in value.__slots__ if name not in {"source_identity", "source_integrity"}}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(artifact_bytes(value)).hexdigest().upper()


__all__ = [
    "Wo09NotificationSource", "Wo09NotificationState", "deduplicate_sources",
    "project_notification", "project_reassessment_notification",
]
