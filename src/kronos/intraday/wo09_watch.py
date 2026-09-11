"""Persistable reassessment-watch lifecycle for WO-09.

V1 watches can request governed reassessment.  They cannot calculate or mutate
readiness from ticks.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from kronos.intraday.wo09_readiness import (
    CriterionId, POLICY_IDENTITY, POLICY_VERSION, artifact_bytes,
    prospective_watch_identity,
)


OWNER_IDENTITY = "INTRADAY_WO09"


class WatchState(StrEnum):
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    INACTIVE = "INACTIVE"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class Wo09Watch:
    watch_identity: str
    readiness_identity: str
    criterion_id: CriterionId
    canonical_subject_identity: str
    exact_contract_identity: str | None
    source_fact_identity: str
    governed_trigger: str
    policy_identity: str
    policy_version: str
    owner_identity: str
    state: WatchState
    activated_at: datetime
    last_transition_at: datetime
    reacquisition_identity: str | None
    integrity_identity: str

    def __post_init__(self) -> None:
        values = _values(self)
        expected_identity = prospective_watch_identity(
            readiness_identity=self.readiness_identity,
            criterion_id=self.criterion_id,
            subject=self.canonical_subject_identity,
            exact_contract=self.exact_contract_identity,
            source_fact_identity=self.source_fact_identity,
            governed_trigger=self.governed_trigger,
        )
        if (
            self.owner_identity != OWNER_IDENTITY or self.policy_identity != POLICY_IDENTITY
            or self.policy_version != POLICY_VERSION or self.activated_at.tzinfo is None
            or self.last_transition_at.tzinfo is None or type(self.state) is not WatchState
            or self.watch_identity != expected_identity
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO09-WATCH-", values)
        ):
            raise ValueError("WO09_WATCH_INVALID")


def create_watch(*, readiness_identity: str, criterion_id: CriterionId, subject: str,
                 exact_contract: str | None, source_fact_identity: str,
                 governed_trigger: str, at: datetime) -> Wo09Watch:
    values = dict(
        readiness_identity=readiness_identity, criterion_id=criterion_id,
        canonical_subject_identity=subject, exact_contract_identity=exact_contract,
        source_fact_identity=source_fact_identity, governed_trigger=governed_trigger,
        policy_identity=POLICY_IDENTITY, policy_version=POLICY_VERSION,
        owner_identity=OWNER_IDENTITY, state=WatchState.ACTIVE, activated_at=at,
        last_transition_at=at, reacquisition_identity=None,
    )
    watch_identity = prospective_watch_identity(
        readiness_identity=readiness_identity, criterion_id=criterion_id,
        subject=subject, exact_contract=exact_contract,
        source_fact_identity=source_fact_identity, governed_trigger=governed_trigger,
    )
    return Wo09Watch(watch_identity=watch_identity,
                     integrity_identity=_identity("INTEGRITY-INTRADAY-WO09-WATCH-", values), **values)


def transition_watch(watch: Wo09Watch, state: WatchState, *, at: datetime,
                     governed_reassessment: bool = False,
                     reacquisition_identity: str | None = None) -> Wo09Watch:
    if type(watch) is not Wo09Watch or type(state) is not WatchState or at.tzinfo is None:
        raise ValueError("WO09_WATCH_TRANSITION_INVALID")
    if at < watch.last_transition_at:
        raise ValueError("WO09_WATCH_TRANSITION_TIME_INVALID")
    if state is WatchState.TRIGGERED and (
        not governed_reassessment or not reacquisition_identity
    ):
        raise ValueError("WO09_TICK_CANNOT_PROMOTE_READINESS")
    if watch.state is WatchState.STALE and state is WatchState.ACTIVE and not reacquisition_identity:
        raise ValueError("WO09_WATCH_REACQUISITION_REQUIRED")
    values = _values(watch)
    values.update(state=state, last_transition_at=at,
                  reacquisition_identity=reacquisition_identity)
    return Wo09Watch(
        watch_identity=watch.watch_identity,
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO09-WATCH-", values),
        **values,
    )


def mark_disconnect_gap(watch: Wo09Watch, *, at: datetime) -> Wo09Watch:
    if watch.state not in {WatchState.ACTIVE, WatchState.TRIGGERED}:
        return watch
    return transition_watch(watch, WatchState.STALE, at=at)


def _values(value: Wo09Watch) -> dict[str, object]:
    return {name: getattr(value, name) for name in value.__slots__ if name not in {"watch_identity", "integrity_identity"}}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(artifact_bytes(value)).hexdigest().upper()


__all__ = ["OWNER_IDENTITY", "WatchState", "Wo09Watch", "create_watch", "mark_disconnect_gap", "transition_watch"]
