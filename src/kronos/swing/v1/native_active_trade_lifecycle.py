"""Frozen Step 32-L Native active-trade lifecycle.

The lifecycle consumes governed Kite market facts and records Sponsor/Paper
position history.  It cannot place, modify, cancel, or close a broker order.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from typing import Callable
from zoneinfo import ZoneInfo

from kronos.market.schedule import MarketSchedule
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import ProviderMarketTick
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderOrderUpdateEvidence,
)
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_sponsor_decision import (
    SponsorInitiationResult,
    SponsorInitiationState,
    SponsorPositionRecord,
    SponsorTradeChoice,
    SponsorTradeDecisionRecord,
)
from kronos.swing.v1.native_trade_construction import TradePlanRecord


ACTIVE_TRADE_LIFECYCLE_POLICY_ID = "SWING-V1-ACTIVE-TRADE-LIFECYCLE-V0"
ACTIVE_TRADE_LIFECYCLE_POLICY_VERSION = "0"
ACTIVE_TRADE_LIFECYCLE_POLICY_STATUS = "FROZEN"
LIFECYCLE_EVENT_CONTRACT_ID = "KRONOS-SWING-V1-TRADE-LIFECYCLE-EVENT-V1"
TRADE_CLOSURE_CONTRACT_ID = "KRONOS-SWING-V1-TRADE-CLOSURE-V1"
LIFECYCLE_STORE_SCHEMA = "KRONOS-SWING-V1-ACTIVE-LIFECYCLE-STORE-V0"
LIFECYCLE_AUTHORITY = "FACTUAL_TRACKING_ONLY_NO_BROKER_EXECUTION_AUTHORITY"


class ActiveLifecycleState(StrEnum):
    PAPER_ARMED = "PAPER_ARMED"
    PAPER_ACTIVE = "PAPER_ACTIVE"
    LIVE_ACTIVE = "LIVE_ACTIVE"
    EVENT_UNRESOLVED = "EVENT_UNRESOLVED"
    MONITORING_UNAVAILABLE = "MONITORING_UNAVAILABLE"
    CLOSED = "CLOSED"


class LifecycleEventType(StrEnum):
    ENTRY_TRIGGERED = "ENTRY_TRIGGERED"
    PAPER_ENTRY_CAPTURED = "PAPER_ENTRY_CAPTURED"
    ENTRY_EVENT_UNRESOLVED = "ENTRY_EVENT_UNRESOLVED"
    STOP_HIT = "STOP_HIT"
    TARGET_HIT = "TARGET_HIT"
    INVALIDATION_OBSERVED = "INVALIDATION_OBSERVED"
    SPONSOR_MANUAL_EXIT = "SPONSOR_MANUAL_EXIT"
    LIVE_EXIT_RECORDED = "LIVE_EXIT_RECORDED"
    MONITORING_UNAVAILABLE = "MONITORING_UNAVAILABLE"
    MONITORING_RESUMED = "MONITORING_RESUMED"
    EVENT_UNRESOLVED = "EVENT_UNRESOLVED"


class LifecycleOrderingStatus(StrEnum):
    ESTABLISHED = "ESTABLISHED"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TradeExitReason(StrEnum):
    PAPER_STOP_HIT = "PAPER_STOP_HIT"
    PAPER_TARGET_HIT = "PAPER_TARGET_HIT"
    SPONSOR_MANUAL_EXIT = "SPONSOR_MANUAL_EXIT"
    SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION = "SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION"
    SPONSOR_EXIT_AFTER_STOP_NOTIFICATION = "SPONSOR_EXIT_AFTER_STOP_NOTIFICATION"
    SPONSOR_EXIT_AFTER_INVALIDATION_NOTIFICATION = "SPONSOR_EXIT_AFTER_INVALIDATION_NOTIFICATION"


@dataclass(frozen=True, slots=True)
class GovernedLifecycleObservation:
    observation_id: str
    canonical_instrument: str
    price: Decimal
    observed_at: datetime
    observation_boundary: datetime
    provider_source: str
    provider_connection_id: str
    source_sequence: int | None
    previous_interval_available: bool
    session_continuous: bool
    ordering_deterministic: bool
    market_identity: str
    calendar_identity: str
    calendar_version: str
    session_identity: str
    session_window_identity: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _positive(self.price))
        if (
            not _identity(self.observation_id)
            or not self.canonical_instrument
            or not _aware(self.observed_at)
            or not _aware(self.observation_boundary)
            or self.provider_source != "KITE_CONNECT_WEBSOCKET"
            or not _identity(self.provider_connection_id)
            or (self.source_sequence is not None and (type(self.source_sequence) is not int or self.source_sequence < 0))
            or type(self.previous_interval_available) is not bool
            or type(self.session_continuous) is not bool
            or type(self.ordering_deterministic) is not bool
            or not all((self.market_identity, self.calendar_identity, self.calendar_version, self.session_identity, self.session_window_identity))
            or not self.provenance
        ):
            raise ValueError("GOVERNED_LIFECYCLE_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class AnalyticalInvalidationEvidence:
    evidence_id: str
    canonical_instrument: str
    governing_timeframe: str
    evidence_boundary: datetime
    reference: Decimal
    established_at: datetime
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference", _positive(self.reference))
        if (
            not _identity(self.evidence_id) or not self.canonical_instrument
            or not _identity(self.governing_timeframe) or not _aware(self.evidence_boundary)
            or not _aware(self.established_at) or not self.provenance
        ):
            raise ValueError("ANALYTICAL_INVALIDATION_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ActiveLifecyclePosition:
    lifecycle_id: str
    position_id: str
    decision_id: str
    trade_plan_id: str
    trade_plan_hash: str
    mode: SponsorTradeChoice
    state: ActiveLifecycleState
    canonical_instrument: str
    direction: V1Direction
    model_entry: Decimal
    stop: Decimal
    invalidation: Decimal
    invalidation_condition: str
    target: Decimal
    actual_entry: Decimal | None
    entry_timestamp: datetime | None
    lots: int
    underlying_quantity: int
    model_risk_reward: Decimal
    domain001_identity: str
    domain008_calendar_identity: str | None
    domain008_calendar_version: str | None
    last_observation_id: str | None
    last_observed_price: Decimal | None
    last_observed_at: datetime | None
    monitoring_outage_started_at: datetime | None
    prior_state: ActiveLifecycleState | None
    outstanding_notification_ids: tuple[str, ...]
    lifecycle_event_ids: tuple[str, ...]
    observed_event_types: tuple[LifecycleEventType, ...]
    created_at: datetime
    updated_at: datetime
    provenance: tuple[str, ...]
    integrity_hash: str
    policy_identity: str = ACTIVE_TRADE_LIFECYCLE_POLICY_ID
    policy_version: str = ACTIVE_TRADE_LIFECYCLE_POLICY_VERSION
    policy_status: str = ACTIVE_TRADE_LIFECYCLE_POLICY_STATUS
    authority: str = LIFECYCLE_AUTHORITY

    def __post_init__(self) -> None:
        for name in ("model_entry", "stop", "invalidation", "target", "model_risk_reward"):
            object.__setattr__(self, name, _positive(getattr(self, name)))
        if self.actual_entry is not None:
            object.__setattr__(self, "actual_entry", _positive(self.actual_entry))
        if self.last_observed_price is not None:
            object.__setattr__(self, "last_observed_price", _positive(self.last_observed_price))
        if (
            not all(_identity(value) for value in (self.lifecycle_id, self.position_id, self.decision_id, self.trade_plan_id, self.domain001_identity))
            or not _digest(self.trade_plan_hash) or self.mode not in {SponsorTradeChoice.PAPER, SponsorTradeChoice.LIVE}
            or type(self.state) is not ActiveLifecycleState or not self.canonical_instrument
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not self.invalidation_condition
            or (self.actual_entry is None) != (self.entry_timestamp is None)
            or (self.entry_timestamp is not None and not _aware(self.entry_timestamp))
            or type(self.lots) is not int or self.lots <= 0
            or type(self.underlying_quantity) is not int or self.underlying_quantity <= 0
            or (self.last_observation_id is None) != (self.last_observed_price is None)
            or (self.last_observation_id is None) != (self.last_observed_at is None)
            or (self.last_observation_id is not None and not _identity(self.last_observation_id))
            or (self.last_observed_at is not None and not _aware(self.last_observed_at))
            or (self.monitoring_outage_started_at is not None and not _aware(self.monitoring_outage_started_at))
            or (self.prior_state is not None and type(self.prior_state) is not ActiveLifecycleState)
            or not all(_identity(value) for value in self.outstanding_notification_ids + self.lifecycle_event_ids)
            or any(type(value) is not LifecycleEventType for value in self.observed_event_types)
            or not _aware(self.created_at) or not _aware(self.updated_at) or not self.provenance
            or self.policy_identity != ACTIVE_TRADE_LIFECYCLE_POLICY_ID
            or self.policy_version != ACTIVE_TRADE_LIFECYCLE_POLICY_VERSION
            or self.policy_status != ACTIVE_TRADE_LIFECYCLE_POLICY_STATUS
            or self.authority != LIFECYCLE_AUTHORITY
            or not _digest(self.integrity_hash) or self.integrity_hash != _digest_record(self)
        ):
            raise ValueError("ACTIVE_LIFECYCLE_POSITION_INVALID")


@dataclass(frozen=True, slots=True)
class TradeLifecycleEvent:
    event_id: str
    position_id: str
    decision_id: str
    trade_plan_id: str
    trade_plan_hash: str
    mode: SponsorTradeChoice
    instrument: str
    direction: V1Direction
    event_type: LifecycleEventType
    observed_price: Decimal | None
    event_timestamp: datetime
    observation_boundary: datetime
    model_entry: Decimal
    stop: Decimal
    invalidation: Decimal
    target: Decimal
    actual_entry: Decimal | None
    provider_provenance: tuple[str, ...]
    domain008_context: tuple[str, ...]
    ordering_status: LifecycleOrderingStatus
    evidence_reference: str | None
    created_at: datetime
    integrity_hash: str
    contract_identity: str = LIFECYCLE_EVENT_CONTRACT_ID
    contract_version: str = "1"

    def __post_init__(self) -> None:
        for name in ("model_entry", "stop", "invalidation", "target"):
            object.__setattr__(self, name, _positive(getattr(self, name)))
        for name in ("observed_price", "actual_entry"):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, _positive(getattr(self, name)))
        if (
            self.contract_identity != LIFECYCLE_EVENT_CONTRACT_ID or self.contract_version != "1"
            or not all(_identity(value) for value in (self.event_id, self.position_id, self.decision_id, self.trade_plan_id))
            or not _digest(self.trade_plan_hash) or self.mode not in {SponsorTradeChoice.PAPER, SponsorTradeChoice.LIVE}
            or not self.instrument or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or type(self.event_type) is not LifecycleEventType or not _aware(self.event_timestamp)
            or not _aware(self.observation_boundary) or type(self.ordering_status) is not LifecycleOrderingStatus
            or not self.provider_provenance or not self.domain008_context
            or (self.evidence_reference is not None and not _identity(self.evidence_reference))
            or not _aware(self.created_at) or not _digest(self.integrity_hash)
            or self.integrity_hash != _digest_record(self)
        ):
            raise ValueError("TRADE_LIFECYCLE_EVENT_INVALID")


@dataclass(frozen=True, slots=True)
class LifecycleNotification:
    notification_id: str
    position_id: str
    event_id: str
    message: str
    action_required: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TradeClosureRecord:
    closure_id: str
    position_id: str
    decision_id: str
    trade_plan_id: str
    trade_plan_hash: str
    mode: SponsorTradeChoice
    instrument: str
    direction: V1Direction
    model_entry: Decimal
    actual_entry: Decimal
    stop: Decimal
    invalidation: Decimal
    target: Decimal
    actual_exit: Decimal
    exit_timestamp: datetime
    exit_reason: TradeExitReason
    observed_stop_event: bool
    observed_target_event: bool
    observed_invalidation_event: bool
    lots: int
    underlying_quantity: int
    gross_pnl: Decimal
    percentage_result: Decimal
    realised_r: Decimal
    holding_duration_seconds: int
    model_risk_reward: Decimal
    lifecycle_event_ids: tuple[str, ...]
    event_provenance: tuple[str, ...]
    commentary: str
    created_at: datetime
    integrity_hash: str
    contract_identity: str = TRADE_CLOSURE_CONTRACT_ID
    contract_version: str = "1"
    cost_model: str = "NOT_INCLUDED_V0"

    def __post_init__(self) -> None:
        for name in ("model_entry", "actual_entry", "stop", "invalidation", "target", "actual_exit", "model_risk_reward"):
            object.__setattr__(self, name, _positive(getattr(self, name)))
        for name in ("gross_pnl", "percentage_result", "realised_r"):
            object.__setattr__(self, name, _decimal(getattr(self, name)))
        if (
            self.contract_identity != TRADE_CLOSURE_CONTRACT_ID or self.contract_version != "1"
            or not all(_identity(value) for value in (self.closure_id, self.position_id, self.decision_id, self.trade_plan_id))
            or not _digest(self.trade_plan_hash) or self.mode not in {SponsorTradeChoice.PAPER, SponsorTradeChoice.LIVE}
            or not self.instrument or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not _aware(self.exit_timestamp) or type(self.exit_reason) is not TradeExitReason
            or type(self.holding_duration_seconds) is not int or self.holding_duration_seconds < 0
            or not self.lifecycle_event_ids or not self.event_provenance or not self.commentary
            or not _aware(self.created_at) or self.cost_model != "NOT_INCLUDED_V0"
            or not _digest(self.integrity_hash) or self.integrity_hash != _digest_record(self)
        ):
            raise ValueError("TRADE_CLOSURE_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class ActiveTradeLifecycleSnapshot:
    positions: tuple[ActiveLifecyclePosition, ...]
    events: tuple[TradeLifecycleEvent, ...]
    notifications: tuple[LifecycleNotification, ...]
    closures: tuple[TradeClosureRecord, ...]

    @property
    def active(self) -> tuple[ActiveLifecyclePosition, ...]:
        return tuple(item for item in self.positions if item.state is not ActiveLifecycleState.CLOSED)


def admit_kite_lifecycle_observation(
    position: ActiveLifecyclePosition,
    tick: ProviderMarketTick,
    schedule: MarketSchedule,
) -> GovernedLifecycleObservation:
    """Admit one factual tick under Provider binding and DOMAIN-008."""

    window = schedule.window_at(tick.observed_at)
    if (
        _canonical_provider_identity(tick.instrument) != position.canonical_instrument
        or tick.source != "KITE_CONNECT_WEBSOCKET"
        or schedule.exchange != tick.instrument.exchange
        or window is None
    ):
        raise ValueError("LIFECYCLE_OBSERVATION_ADMISSION_REJECTED")
    observation_id = _id(
        "LIFECYCLE-OBSERVATION", position.position_id, tick.connection_id,
        str(tick.source_sequence), tick.observed_at.isoformat(), str(tick.last_price),
    )
    return GovernedLifecycleObservation(
        observation_id, position.canonical_instrument, tick.last_price,
        tick.observed_at, tick.observed_at, tick.source, tick.connection_id,
        tick.source_sequence, tick.previous_interval_available,
        tick.session_continuous, tick.ordering_deterministic,
        schedule.market_identity, schedule.calendar_identity,
        schedule.calendar_version, schedule.session_identity, window.identity,
        (
            "KITE_CONNECT_WEBSOCKET", tick.instrument.provider,
            schedule.identity, schedule.source_identity,
        ),
    )


def create_active_lifecycle(
    decision: SponsorTradeDecisionRecord,
    position: SponsorPositionRecord,
    plan: TradePlanRecord,
) -> ActiveLifecyclePosition:
    if (
        decision.trade_plan_id != plan.trade_plan_id
        or decision.trade_plan_integrity_hash != plan.integrity_hash
        or position.decision_id != decision.decision_id
        or position.trade_plan_id != plan.trade_plan_id
        or position.canonical_instrument != plan.canonical_instrument
        or position.direction is not plan.native_direction
        or position.model_entry != plan.entry or position.stop != plan.stop
        or position.invalidation != plan.invalidation_reference
        or position.target != plan.canonical_target
        or position.state not in {SponsorInitiationState.PAPER_ARMED, SponsorInitiationState.PAPER_ACTIVE, SponsorInitiationState.LIVE_ACTIVE}
    ):
        raise ValueError("ACTIVE_LIFECYCLE_BINDING_INVALID")
    state = ActiveLifecycleState(position.state.value)
    values = dict(
        lifecycle_id=_id("ACTIVE-LIFECYCLE", position.position_id, plan.integrity_hash),
        position_id=position.position_id, decision_id=decision.decision_id,
        trade_plan_id=plan.trade_plan_id, trade_plan_hash=plan.integrity_hash,
        mode=position.mode, state=state, canonical_instrument=position.canonical_instrument,
        direction=position.direction, model_entry=position.model_entry,
        stop=position.stop, invalidation=position.invalidation, target=position.target,
        invalidation_condition=plan.invalidation_condition,
        actual_entry=position.actual_entry, entry_timestamp=position.entry_timestamp,
        lots=position.lots, underlying_quantity=position.underlying_quantity,
        model_risk_reward=decision.model_risk_reward,
        domain001_identity=plan.execution_context_identity,
        domain008_calendar_identity=None, domain008_calendar_version=None,
        last_observation_id=None, last_observed_price=None, last_observed_at=None,
        monitoring_outage_started_at=None, prior_state=None,
        outstanding_notification_ids=(), lifecycle_event_ids=(),
        observed_event_types=(),
        created_at=position.created_at, updated_at=position.created_at,
        provenance=(position.position_id, decision.decision_id, plan.trade_plan_id, "DOMAIN-001", "DOMAIN-008"),
    )
    return _position(values)


class ActiveTradeLifecycleEngine:
    """Deterministic lifecycle state machine; no transport or broker client."""

    @staticmethod
    def observe(
        position: ActiveLifecyclePosition,
        observation: GovernedLifecycleObservation,
    ) -> tuple[ActiveLifecyclePosition, tuple[TradeLifecycleEvent, ...], tuple[LifecycleNotification, ...], TradeClosureRecord | None]:
        _require_observation_binding(position, observation)
        if position.state is ActiveLifecycleState.CLOSED:
            return position, (), (), None
        if observation.observation_id == position.last_observation_id:
            return position, (), (), None
        prefix_events: tuple[TradeLifecycleEvent, ...] = ()
        prior_price = position.last_observed_price
        current = _with_observation(position, observation)
        if position.state is ActiveLifecycleState.MONITORING_UNAVAILABLE:
            resumed = _event(current, LifecycleEventType.MONITORING_RESUMED, observation, LifecycleOrderingStatus.ESTABLISHED)
            current = _update(current, state=position.prior_state or ActiveLifecycleState.EVENT_UNRESOLVED, prior_state=None, monitoring_outage_started_at=None)
            current = _append_events(current, (resumed,))
            prefix_events = (resumed,)
            if prior_price is not None and _span_covers_both(prior_price, observation.price, current.stop, current.target):
                return _unresolved(current, observation, (resumed,))
            position = current
        if position.state is ActiveLifecycleState.EVENT_UNRESOLVED:
            return position, prefix_events, (), None
        if position.state is ActiveLifecycleState.PAPER_ARMED:
            if prior_price is None:
                return current, prefix_events, (), None
            crossed = _pre_entry(prior_price, current.model_entry, current.direction) and _at_or_beyond(observation.price, current.model_entry, current.direction)
            if not crossed:
                return current, prefix_events, (), None
            if not _continuous(observation):
                event = _event(current, LifecycleEventType.ENTRY_EVENT_UNRESOLVED, observation, LifecycleOrderingStatus.UNRESOLVED)
                unresolved = _update(current, state=ActiveLifecycleState.EVENT_UNRESOLVED)
                return _append_events(unresolved, (event,)), (*prefix_events, event), (), None
            triggered = _event(current, LifecycleEventType.ENTRY_TRIGGERED, observation, LifecycleOrderingStatus.ESTABLISHED)
            captured = _event(current, LifecycleEventType.PAPER_ENTRY_CAPTURED, observation, LifecycleOrderingStatus.ESTABLISHED)
            active = _update(
                current, state=ActiveLifecycleState.PAPER_ACTIVE,
                actual_entry=observation.price, entry_timestamp=observation.observed_at,
            )
            return _append_events(active, (triggered, captured)), (*prefix_events, triggered, captured), (), None
        if prior_price is not None and _span_covers_both(prior_price, observation.price, current.stop, current.target):
            return _unresolved(current, observation, prefix_events)
        stop_hit = observation.price <= current.stop if current.direction is V1Direction.LONG else observation.price >= current.stop
        target_hit = observation.price >= current.target if current.direction is V1Direction.LONG else observation.price <= current.target
        if not stop_hit and not target_hit:
            return current, prefix_events, (), None
        event_type = LifecycleEventType.STOP_HIT if stop_hit else LifecycleEventType.TARGET_HIT
        if event_type in current.observed_event_types:
            return current, prefix_events, (), None
        event = _event(current, event_type, observation, LifecycleOrderingStatus.ESTABLISHED)
        current = _append_events(current, (event,))
        if current.mode is SponsorTradeChoice.LIVE:
            message = "ACTION REQUIRED — STOP HIT" if stop_hit else "ACTION REQUIRED — TARGET HIT"
            notification = _notification(current, event, message)
            return _update(current, outstanding_notification_ids=current.outstanding_notification_ids + (notification.notification_id,)), (*prefix_events, event), (notification,), None
        reason = TradeExitReason.PAPER_STOP_HIT if stop_hit else TradeExitReason.PAPER_TARGET_HIT
        closure = _closure(current, observation.price, observation.observed_at, reason, (event,), observation.provenance)
        return _update(current, state=ActiveLifecycleState.CLOSED), (*prefix_events, event), (), closure

    @staticmethod
    def observe_invalidation(
        position: ActiveLifecyclePosition,
        evidence: AnalyticalInvalidationEvidence,
    ) -> tuple[ActiveLifecyclePosition, TradeLifecycleEvent, LifecycleNotification | None]:
        if (
            position.state not in {ActiveLifecycleState.PAPER_ACTIVE, ActiveLifecycleState.LIVE_ACTIVE}
            or evidence.canonical_instrument != position.canonical_instrument
            or evidence.reference != position.invalidation
        ):
            raise ValueError("INVALIDATION_LIFECYCLE_NOT_APPLICABLE")
        event = _event_from_invalidation(position, evidence)
        updated = _append_events(position, (event,))
        if position.mode is SponsorTradeChoice.PAPER:
            return updated, event, None
        notification = _notification(updated, event, "ACTION REQUIRED — ANALYTICAL INVALIDATION OBSERVED")
        return _update(updated, outstanding_notification_ids=updated.outstanding_notification_ids + (notification.notification_id,)), event, notification

    @staticmethod
    def monitoring_unavailable(position: ActiveLifecyclePosition, *, occurred_at: datetime, provider_context: str) -> tuple[ActiveLifecyclePosition, TradeLifecycleEvent, LifecycleNotification]:
        if position.state is ActiveLifecycleState.CLOSED:
            raise ValueError("MONITORING_NOT_APPLICABLE")
        if position.state is ActiveLifecycleState.MONITORING_UNAVAILABLE:
            event_id = position.lifecycle_event_ids[-1]
            raise ValueError(f"MONITORING_ALREADY_UNAVAILABLE:{event_id}")
        event = _event_without_observation(position, LifecycleEventType.MONITORING_UNAVAILABLE, occurred_at, provider_context)
        notification = _notification(position, event, "MONITORING UNAVAILABLE")
        updated = _update(
            position, state=ActiveLifecycleState.MONITORING_UNAVAILABLE,
            prior_state=position.state, monitoring_outage_started_at=occurred_at,
            outstanding_notification_ids=position.outstanding_notification_ids + (notification.notification_id,),
        )
        return _append_events(updated, (event,)), event, notification

    @staticmethod
    def manual_paper_exit(position: ActiveLifecyclePosition, observation: GovernedLifecycleObservation) -> tuple[ActiveLifecyclePosition, TradeLifecycleEvent, TradeClosureRecord]:
        if position.state is not ActiveLifecycleState.PAPER_ACTIVE or observation.observation_id != position.last_observation_id or observation.observed_at != position.last_observed_at:
            raise ValueError("CURRENT_AUTHORITATIVE_OBSERVATION_UNAVAILABLE")
        event = _event(position, LifecycleEventType.SPONSOR_MANUAL_EXIT, observation, LifecycleOrderingStatus.ESTABLISHED)
        updated = _append_events(position, (event,))
        closure = _closure(updated, observation.price, observation.observed_at, TradeExitReason.SPONSOR_MANUAL_EXIT, (event,), observation.provenance)
        return _update(updated, state=ActiveLifecycleState.CLOSED), event, closure

    @staticmethod
    def record_live_exit(position: ActiveLifecyclePosition, *, actual_exit: Decimal | None, exit_timestamp: datetime, reason: TradeExitReason) -> tuple[ActiveLifecyclePosition, TradeLifecycleEvent | None, TradeClosureRecord | None]:
        if position.state is not ActiveLifecycleState.LIVE_ACTIVE:
            raise ValueError("LIVE_EXIT_NOT_APPLICABLE")
        if actual_exit is None:
            return position, None, None
        if reason not in {
            TradeExitReason.SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION,
            TradeExitReason.SPONSOR_EXIT_AFTER_STOP_NOTIFICATION,
            TradeExitReason.SPONSOR_EXIT_AFTER_INVALIDATION_NOTIFICATION,
            TradeExitReason.SPONSOR_MANUAL_EXIT,
        }:
            raise ValueError("LIVE_EXIT_REASON_INVALID")
        actual_exit = _positive(actual_exit)
        event = _event_for_live_exit(position, actual_exit, exit_timestamp, reason)
        updated = _append_events(position, (event,))
        closure = _closure(updated, actual_exit, exit_timestamp, reason, (event,), ("SPONSOR_ATTESTED_ACTUAL_BROKER_EXECUTION",))
        return _update(updated, state=ActiveLifecycleState.CLOSED, outstanding_notification_ids=()), event, closure


class LocalActiveTradeLifecycleStore:
    """Restart-safe current projection plus immutable event/closure records."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("ACTIVE_LIFECYCLE_STORE_INVALID")
        self._lock = RLock()

    def retain_position(self, position: ActiveLifecyclePosition) -> None:
        with self._lock:
            _atomic(self.root / position.position_id / "position.json", {"schema": LIFECYCLE_STORE_SCHEMA, "record": _primitive(position)})

    def retain_event(self, event: TradeLifecycleEvent) -> None:
        path = self.root / event.position_id / "events" / f"{event.event_id}.json"
        with self._lock:
            _immutable(path, {"schema": LIFECYCLE_STORE_SCHEMA, "record": _primitive(event)})

    def retain_notification(self, notification: LifecycleNotification) -> None:
        path = self.root / notification.position_id / "notifications" / f"{notification.notification_id}.json"
        with self._lock:
            _immutable(path, {"schema": LIFECYCLE_STORE_SCHEMA, "record": _primitive(notification)})

    def retain_closure(self, closure: TradeClosureRecord) -> None:
        path = self.root / closure.position_id / "closure.json"
        with self._lock:
            _immutable(path, {"schema": LIFECYCLE_STORE_SCHEMA, "record": _primitive(closure)})

    def load(self) -> ActiveTradeLifecycleSnapshot:
        if not self.root.exists():
            return ActiveTradeLifecycleSnapshot((), (), (), ())
        positions, events, notifications, closures = [], [], [], []
        for directory in sorted(path for path in self.root.iterdir() if path.is_dir()):
            if (directory / "position.json").exists():
                positions.append(_position_from_dict(_read(directory / "position.json")))
            for path in sorted((directory / "events").glob("*.json")):
                events.append(_event_from_dict(_read(path)))
            for path in sorted((directory / "notifications").glob("*.json")):
                notifications.append(_notification_from_dict(_read(path)))
            if (directory / "closure.json").exists():
                closures.append(_closure_from_dict(_read(directory / "closure.json")))
        return ActiveTradeLifecycleSnapshot(tuple(positions), tuple(events), tuple(notifications), tuple(closures))


class ActiveTradeLifecycleService:
    """Persist every transition atomically enough for deterministic recovery."""

    def __init__(self, store: LocalActiveTradeLifecycleStore) -> None:
        self.store = store
        restored = store.load()
        self._positions = {item.position_id: item for item in restored.positions}
        self._events = {item.event_id: item for item in restored.events}
        self._notifications = {item.notification_id: item for item in restored.notifications}
        self._closures = {item.position_id: item for item in restored.closures}
        self._latest: dict[str, GovernedLifecycleObservation] = {}
        self._lock = RLock()

    def register(self, initiation: SponsorInitiationResult, plan: TradePlanRecord) -> ActiveLifecyclePosition | None:
        if initiation.decision is None or initiation.position is None:
            return None
        with self._lock:
            current = self._positions.get(initiation.position.position_id)
            if current is not None:
                if current.trade_plan_hash != plan.integrity_hash:
                    raise ValueError("ACTIVE_LIFECYCLE_RESTART_BINDING_INVALID")
                return current
            current = create_active_lifecycle(initiation.decision, initiation.position, plan)
            self.store.retain_position(current)
            self._positions[current.position_id] = current
            return current

    def observe(self, position_id: str, observation: GovernedLifecycleObservation) -> ActiveLifecyclePosition:
        with self._lock:
            current = self._require(position_id)
            updated, events, notifications, closure = ActiveTradeLifecycleEngine.observe(current, observation)
            self._persist(updated, events, notifications, closure)
            self._latest[position_id] = observation
            return updated

    def observe_tick(self, position_id: str, tick: ProviderMarketTick, schedule: MarketSchedule) -> ActiveLifecyclePosition:
        return self.observe(position_id, admit_kite_lifecycle_observation(self._require(position_id), tick, schedule))

    def observe_invalidation(self, position_id: str, evidence: AnalyticalInvalidationEvidence) -> ActiveLifecyclePosition:
        with self._lock:
            current = self._require(position_id)
            if LifecycleEventType.INVALIDATION_OBSERVED in current.observed_event_types:
                return current
            updated, event, notification = ActiveTradeLifecycleEngine.observe_invalidation(current, evidence)
            self._persist(updated, (event,), () if notification is None else (notification,), None)
            return updated

    def monitoring_unavailable(self, position_id: str, *, occurred_at: datetime, provider_context: str) -> ActiveLifecyclePosition:
        with self._lock:
            current = self._require(position_id)
            if current.state is ActiveLifecycleState.MONITORING_UNAVAILABLE:
                return current
            updated, event, notification = ActiveTradeLifecycleEngine.monitoring_unavailable(current, occurred_at=occurred_at, provider_context=provider_context)
            self._persist(updated, (event,), (notification,), None)
            return updated

    def manual_paper_exit(self, position_id: str, observation: GovernedLifecycleObservation) -> TradeClosureRecord:
        with self._lock:
            current = self._require(position_id)
            if current.state is ActiveLifecycleState.CLOSED and position_id in self._closures:
                return self._closures[position_id]
            updated, event, closure = ActiveTradeLifecycleEngine.manual_paper_exit(current, observation)
            self._persist(updated, (event,), (), closure)
            return closure

    def manual_paper_exit_current(self, position_id: str) -> TradeClosureRecord:
        """Use only an observation accepted in this live process; restart clears it."""

        try:
            observation = self._latest[position_id]
        except KeyError as error:
            raise ValueError("CURRENT_AUTHORITATIVE_OBSERVATION_UNAVAILABLE") from error
        return self.manual_paper_exit(position_id, observation)

    def record_live_exit(self, position_id: str, *, actual_exit: Decimal | None, exit_timestamp: datetime, reason: TradeExitReason) -> TradeClosureRecord | None:
        with self._lock:
            current = self._require(position_id)
            if current.state is ActiveLifecycleState.CLOSED and position_id in self._closures:
                return self._closures[position_id]
            updated, event, closure = ActiveTradeLifecycleEngine.record_live_exit(current, actual_exit=actual_exit, exit_timestamp=exit_timestamp, reason=reason)
            self._persist(updated, () if event is None else (event,), (), closure)
            return closure

    def snapshot(self) -> ActiveTradeLifecycleSnapshot:
        with self._lock:
            return ActiveTradeLifecycleSnapshot(
                tuple(sorted(self._positions.values(), key=lambda item: item.created_at)),
                tuple(sorted(self._events.values(), key=lambda item: (item.event_timestamp, item.event_id))),
                tuple(sorted(self._notifications.values(), key=lambda item: (item.created_at, item.notification_id))),
                tuple(sorted(self._closures.values(), key=lambda item: (item.exit_timestamp, item.closure_id))),
            )

    def _require(self, position_id: str) -> ActiveLifecyclePosition:
        try:
            return self._positions[position_id]
        except KeyError as error:
            raise ValueError("ACTIVE_LIFECYCLE_POSITION_UNAVAILABLE") from error

    def _persist(self, position, events, notifications, closure):  # type: ignore[no-untyped-def]
        for event in events:
            self.store.retain_event(event)
            self._events[event.event_id] = event
        for notification in notifications:
            self.store.retain_notification(notification)
            self._notifications[notification.notification_id] = notification
        if closure is not None:
            self.store.retain_closure(closure)
            self._closures[closure.position_id] = closure
        self.store.retain_position(position)
        self._positions[position.position_id] = position


class ActiveLifecycleMonitoringCoordinator:
    """One read-only Kite subscription per active Native Sponsor position."""

    def __init__(
        self,
        service: ActiveTradeLifecycleService,
        calendar: MarketCalendarPublisher,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._service = service
        self._calendar = calendar
        self._clock = clock
        self._consumers: dict[str, _LifecycleMonitoringConsumer] = {}
        self._lock = RLock()

    def attach(self, position_id: str, capability: object, instrument: InstrumentRecord) -> None:
        position = self._service._require(position_id)
        if (
            getattr(capability, "active", False) is not True
            or type(instrument) is not InstrumentRecord
            or _canonical_provider_identity(instrument) != position.canonical_instrument
            or position.state is ActiveLifecycleState.CLOSED
        ):
            raise ValueError("ACTIVE_LIFECYCLE_MONITORING_NOT_PERMITTED")
        with self._lock:
            if position_id in self._consumers:
                raise ValueError("ACTIVE_LIFECYCLE_MONITORING_ALREADY_ACTIVE")
            consumer = _LifecycleMonitoringConsumer(
                position_id, instrument, self._service, self._calendar,
                self._clock, lambda: self.detach(position_id),
            )
            session = capability.open_monitoring_session(consumer)
            consumer.bind(session)
            self._consumers[position_id] = consumer
        try:
            session.subscribe((instrument,))
            session.connect()
        except Exception:
            self.detach(position_id)
            current = self._service._require(position_id)
            if current.state is not ActiveLifecycleState.MONITORING_UNAVAILABLE:
                self._service.monitoring_unavailable(
                    position_id,
                    occurred_at=self._clock(),
                    provider_context="KITE_MONITORING_CONNECTION_FAILED",
                )
            raise ValueError("ACTIVE_LIFECYCLE_MONITORING_FAILED") from None

    def detach(self, position_id: str) -> None:
        with self._lock:
            consumer = self._consumers.pop(position_id, None)
        if consumer is not None:
            consumer.close()

    def restore(
        self,
        capability: object,
        instrument_resolver: Callable[[str], InstrumentRecord],
    ) -> tuple[str, ...]:
        """Reattach each validated persisted active position without recreating it."""

        restored = []
        for position in self._service.snapshot().active:
            if position.state is ActiveLifecycleState.EVENT_UNRESOLVED:
                continue
            self.attach(
                position.position_id,
                capability,
                instrument_resolver(position.canonical_instrument),
            )
            restored.append(position.position_id)
        return tuple(restored)

    @property
    def active_position_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._consumers))


class _LifecycleMonitoringConsumer:
    def __init__(self, position_id, instrument, service, calendar, clock, on_closed):  # type: ignore[no-untyped-def]
        self.position_id = position_id
        self.instrument = instrument
        self.service = service
        self.calendar = calendar
        self.clock = clock
        self.on_closed = on_closed
        self.session = None

    def bind(self, session) -> None:  # type: ignore[no-untyped-def]
        self.session = session

    def on_market_tick(self, tick: ProviderMarketTick) -> None:
        if tick.instrument != self.instrument:
            raise ValueError("ACTIVE_LIFECYCLE_INSTRUMENT_BINDING_MISMATCH")
        schedule = self.calendar.schedule(
            tick.instrument.exchange,
            tick.observed_at.astimezone(ZoneInfo("Asia/Kolkata")).date(),
            observed_at=tick.received_at,
        )
        if schedule is None:
            raise ValueError("ACTIVE_LIFECYCLE_NOT_TRADING_TIME")
        position = self.service.observe_tick(self.position_id, tick, schedule)
        if position.state is ActiveLifecycleState.CLOSED:
            self.on_closed()

    def on_order_update(self, update: ProviderOrderUpdateEvidence) -> None:
        # Order updates are intentionally isolated from lifecycle market authority.
        return None

    def on_connection_state(self, state: MonitoringConnectionState) -> None:
        if state in {MonitoringConnectionState.DISCONNECTED, MonitoringConnectionState.CONTEXT_INCOMPLETE}:
            position = self.service._require(self.position_id)
            if position.state not in {ActiveLifecycleState.CLOSED, ActiveLifecycleState.MONITORING_UNAVAILABLE}:
                self.service.monitoring_unavailable(
                    self.position_id, occurred_at=self.clock(), provider_context=state.value,
                )

    def close(self) -> None:
        session, self.session = self.session, None
        if session is None:
            return
        try:
            session.unsubscribe((self.instrument,))
        finally:
            session.disconnect()


def _with_observation(position: ActiveLifecyclePosition, observation: GovernedLifecycleObservation) -> ActiveLifecyclePosition:
    return _update(
        position, last_observation_id=observation.observation_id,
        last_observed_price=observation.price, last_observed_at=observation.observed_at,
        domain008_calendar_identity=observation.calendar_identity,
        domain008_calendar_version=observation.calendar_version,
        updated_at=observation.observed_at,
    )


def _event(position, event_type, observation, ordering):  # type: ignore[no-untyped-def]
    values = dict(
        event_id=_id("LIFECYCLE-EVENT", position.position_id, event_type.value, observation.observation_id),
        position_id=position.position_id, decision_id=position.decision_id,
        trade_plan_id=position.trade_plan_id, trade_plan_hash=position.trade_plan_hash,
        mode=position.mode, instrument=position.canonical_instrument, direction=position.direction,
        event_type=event_type, observed_price=observation.price,
        event_timestamp=observation.observed_at, observation_boundary=observation.observation_boundary,
        model_entry=position.model_entry, stop=position.stop, invalidation=position.invalidation,
        target=position.target, actual_entry=position.actual_entry,
        provider_provenance=observation.provenance,
        domain008_context=(observation.calendar_identity, observation.calendar_version, observation.session_identity, observation.session_window_identity),
        ordering_status=ordering, evidence_reference=observation.observation_id,
        created_at=observation.observed_at,
    )
    return _lifecycle_event(values)


def _event_without_observation(position, event_type, occurred_at, provider_context):  # type: ignore[no-untyped-def]
    values = dict(
        event_id=_id("LIFECYCLE-EVENT", position.position_id, event_type.value, occurred_at.isoformat()),
        position_id=position.position_id, decision_id=position.decision_id,
        trade_plan_id=position.trade_plan_id, trade_plan_hash=position.trade_plan_hash,
        mode=position.mode, instrument=position.canonical_instrument, direction=position.direction,
        event_type=event_type, observed_price=position.last_observed_price,
        event_timestamp=occurred_at, observation_boundary=occurred_at,
        model_entry=position.model_entry, stop=position.stop, invalidation=position.invalidation,
        target=position.target, actual_entry=position.actual_entry,
        provider_provenance=("KITE_CONNECT_WEBSOCKET", provider_context),
        domain008_context=(position.domain008_calendar_identity or "DOMAIN-008-CONTEXT-UNAVAILABLE", position.domain008_calendar_version or "UNAVAILABLE"),
        ordering_status=LifecycleOrderingStatus.NOT_APPLICABLE, evidence_reference=None,
        created_at=occurred_at,
    )
    return _lifecycle_event(values)


def _event_from_invalidation(position, evidence):  # type: ignore[no-untyped-def]
    values = dict(
        event_id=_id("LIFECYCLE-EVENT", position.position_id, LifecycleEventType.INVALIDATION_OBSERVED.value, evidence.evidence_id),
        position_id=position.position_id, decision_id=position.decision_id,
        trade_plan_id=position.trade_plan_id, trade_plan_hash=position.trade_plan_hash,
        mode=position.mode, instrument=position.canonical_instrument, direction=position.direction,
        event_type=LifecycleEventType.INVALIDATION_OBSERVED, observed_price=evidence.reference,
        event_timestamp=evidence.established_at, observation_boundary=evidence.evidence_boundary,
        model_entry=position.model_entry, stop=position.stop, invalidation=position.invalidation,
        target=position.target, actual_entry=position.actual_entry,
        provider_provenance=evidence.provenance,
        domain008_context=(position.domain008_calendar_identity or "DOMAIN-008-CONTEXT-UNAVAILABLE", position.domain008_calendar_version or "UNAVAILABLE", evidence.governing_timeframe),
        ordering_status=LifecycleOrderingStatus.ESTABLISHED, evidence_reference=evidence.evidence_id,
        created_at=evidence.established_at,
    )
    return _lifecycle_event(values)


def _event_for_live_exit(position, price, occurred_at, reason):  # type: ignore[no-untyped-def]
    values = dict(
        event_id=_id("LIFECYCLE-EVENT", position.position_id, LifecycleEventType.LIVE_EXIT_RECORDED.value, occurred_at.isoformat(), str(price)),
        position_id=position.position_id, decision_id=position.decision_id,
        trade_plan_id=position.trade_plan_id, trade_plan_hash=position.trade_plan_hash,
        mode=position.mode, instrument=position.canonical_instrument, direction=position.direction,
        event_type=LifecycleEventType.LIVE_EXIT_RECORDED, observed_price=price,
        event_timestamp=occurred_at, observation_boundary=occurred_at,
        model_entry=position.model_entry, stop=position.stop, invalidation=position.invalidation,
        target=position.target, actual_entry=position.actual_entry,
        provider_provenance=("SPONSOR_ATTESTED_ACTUAL_BROKER_EXECUTION", reason.value),
        domain008_context=(position.domain008_calendar_identity or "DOMAIN-008-CONTEXT-UNAVAILABLE", position.domain008_calendar_version or "UNAVAILABLE"),
        ordering_status=LifecycleOrderingStatus.ESTABLISHED, evidence_reference=reason.value,
        created_at=occurred_at,
    )
    return _lifecycle_event(values)


def _unresolved(position, observation, prior_events):  # type: ignore[no-untyped-def]
    event = _event(position, LifecycleEventType.EVENT_UNRESOLVED, observation, LifecycleOrderingStatus.UNRESOLVED)
    notification = _notification(position, event, "ACTION REQUIRED — EVENT ORDER UNRESOLVED") if position.mode is SponsorTradeChoice.LIVE else None
    updated = _append_events(_update(position, state=ActiveLifecycleState.EVENT_UNRESOLVED), (event,))
    if notification is not None:
        updated = _update(updated, outstanding_notification_ids=updated.outstanding_notification_ids + (notification.notification_id,))
    return updated, (*prior_events, event), () if notification is None else (notification,), None


def _notification(position, event, message):  # type: ignore[no-untyped-def]
    return LifecycleNotification(
        _id("LIFECYCLE-NOTIFICATION", event.event_id, message), position.position_id,
        event.event_id, message, True, event.created_at,
    )


def _closure(position, exit_price, exit_time, reason, new_events, provenance):  # type: ignore[no-untyped-def]
    if position.actual_entry is None or position.entry_timestamp is None:
        raise ValueError("ACTUAL_ENTRY_UNAVAILABLE")
    move = exit_price - position.actual_entry if position.direction is V1Direction.LONG else position.actual_entry - exit_price
    pnl = move * Decimal(position.underlying_quantity)
    percentage = (move / position.actual_entry) * Decimal("100")
    risk_distance = abs(position.actual_entry - position.stop)
    if risk_distance == 0:
        raise ValueError("REALISED_R_UNAVAILABLE")
    realised_r = move / risk_distance
    event_ids = position.lifecycle_event_ids
    values = dict(
        closure_id=_id("TRADE-CLOSURE", position.position_id, reason.value, exit_time.isoformat(), str(exit_price)),
        position_id=position.position_id, decision_id=position.decision_id,
        trade_plan_id=position.trade_plan_id, trade_plan_hash=position.trade_plan_hash,
        mode=position.mode, instrument=position.canonical_instrument, direction=position.direction,
        model_entry=position.model_entry, actual_entry=position.actual_entry,
        stop=position.stop, invalidation=position.invalidation, target=position.target,
        actual_exit=exit_price, exit_timestamp=exit_time, exit_reason=reason,
        observed_stop_event=LifecycleEventType.STOP_HIT in position.observed_event_types,
        observed_target_event=LifecycleEventType.TARGET_HIT in position.observed_event_types,
        observed_invalidation_event=LifecycleEventType.INVALIDATION_OBSERVED in position.observed_event_types,
        lots=position.lots, underlying_quantity=position.underlying_quantity,
        gross_pnl=pnl, percentage_result=percentage, realised_r=realised_r,
        holding_duration_seconds=int((exit_time - position.entry_timestamp).total_seconds()),
        model_risk_reward=position.model_risk_reward,
        lifecycle_event_ids=event_ids,
        event_provenance=tuple(provenance),
        commentary=_commentary(position.mode, reason), created_at=exit_time,
    )
    return _closure_record(values)


def _commentary(mode: SponsorTradeChoice, reason: TradeExitReason) -> str:
    if reason is TradeExitReason.PAPER_TARGET_HIT:
        return "Paper trade closed after the Step-31 Target was observed before the protective Stop."
    if reason is TradeExitReason.PAPER_STOP_HIT:
        return "Paper trade closed after the protective Stop was observed before the Target."
    if mode is SponsorTradeChoice.LIVE and reason is TradeExitReason.SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION:
        return "Sponsor manually closed the Live trade after a Target notification."
    if mode is SponsorTradeChoice.LIVE and reason is TradeExitReason.SPONSOR_EXIT_AFTER_STOP_NOTIFICATION:
        return "Sponsor recorded the actual Live exit after a Stop notification."
    if mode is SponsorTradeChoice.LIVE and reason is TradeExitReason.SPONSOR_EXIT_AFTER_INVALIDATION_NOTIFICATION:
        return "Sponsor recorded the actual Live exit after an analytical invalidation notification."
    return f"Sponsor manually closed the {mode.value.title()} trade using factual exit evidence."


def _require_observation_binding(position, observation):  # type: ignore[no-untyped-def]
    if observation.canonical_instrument != position.canonical_instrument or observation.provider_source != "KITE_CONNECT_WEBSOCKET":
        raise ValueError("LIFECYCLE_OBSERVATION_BINDING_INVALID")
    if position.last_observed_at is not None and observation.observed_at < position.last_observed_at:
        raise ValueError("LIFECYCLE_OBSERVATION_ORDER_INVALID")


def _continuous(observation: GovernedLifecycleObservation) -> bool:
    return observation.previous_interval_available and observation.session_continuous and observation.ordering_deterministic


def _canonical_provider_identity(instrument: InstrumentRecord) -> str:
    return instrument.name or instrument.trading_symbol


def _pre_entry(price: Decimal, entry: Decimal, direction: V1Direction) -> bool:
    return price < entry if direction is V1Direction.LONG else price > entry


def _at_or_beyond(price: Decimal, entry: Decimal, direction: V1Direction) -> bool:
    return price >= entry if direction is V1Direction.LONG else price <= entry


def _span_covers_both(previous: Decimal, current: Decimal, stop: Decimal, target: Decimal) -> bool:
    low, high = sorted((previous, current))
    lower_level, upper_level = sorted((stop, target))
    return low <= lower_level and high >= upper_level


def _position(values: dict[str, object]) -> ActiveLifecyclePosition:
    complete = {
        **values,
        "policy_identity": ACTIVE_TRADE_LIFECYCLE_POLICY_ID,
        "policy_version": ACTIVE_TRADE_LIFECYCLE_POLICY_VERSION,
        "policy_status": ACTIVE_TRADE_LIFECYCLE_POLICY_STATUS,
        "authority": LIFECYCLE_AUTHORITY,
    }
    return ActiveLifecyclePosition(  # type: ignore[arg-type]
        **complete, integrity_hash=_digest_payload(complete)
    )


def _lifecycle_event(values: dict[str, object]) -> TradeLifecycleEvent:
    complete = {
        **values,
        "contract_identity": LIFECYCLE_EVENT_CONTRACT_ID,
        "contract_version": "1",
    }
    return TradeLifecycleEvent(  # type: ignore[arg-type]
        **complete, integrity_hash=_digest_payload(complete)
    )


def _closure_record(values: dict[str, object]) -> TradeClosureRecord:
    complete = {
        **values,
        "contract_identity": TRADE_CLOSURE_CONTRACT_ID,
        "contract_version": "1",
        "cost_model": "NOT_INCLUDED_V0",
    }
    return TradeClosureRecord(  # type: ignore[arg-type]
        **complete, integrity_hash=_digest_payload(complete)
    )


def _update(position: ActiveLifecyclePosition, **changes: object) -> ActiveLifecyclePosition:
    values = asdict(position)
    values.update(changes)
    for name in ("mode", "state", "direction", "prior_state"):
        if name in values and isinstance(values[name], str):
            enum = {"mode": SponsorTradeChoice, "state": ActiveLifecycleState, "direction": V1Direction, "prior_state": ActiveLifecycleState}[name]
            values[name] = enum(values[name])
    for name in ("outstanding_notification_ids", "lifecycle_event_ids", "provenance"):
        values[name] = tuple(values[name])
    values["observed_event_types"] = tuple(
        item if type(item) is LifecycleEventType else LifecycleEventType(item)
        for item in values["observed_event_types"]
    )
    values.pop("integrity_hash", None)
    return _position(values)


def _append_events(position: ActiveLifecyclePosition, events: tuple[TradeLifecycleEvent, ...]) -> ActiveLifecyclePosition:
    new = tuple(item.event_id for item in events if item.event_id not in position.lifecycle_event_ids)
    types = tuple(
        item.event_type for item in events
        if item.event_id not in position.lifecycle_event_ids
        and item.event_type not in position.observed_event_types
    )
    return _update(
        position,
        lifecycle_event_ids=position.lifecycle_event_ids + new,
        observed_event_types=position.observed_event_types + types,
    )


def _digest_record(value: object) -> str:
    data = _primitive(value)
    if isinstance(data, dict):
        data.pop("integrity_hash", None)
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _digest_payload(value: dict[str, object]) -> str:
    return sha256(
        json.dumps(_primitive(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _primitive(value):  # type: ignore[no-untyped-def]
    if hasattr(value, "__dataclass_fields__"):
        return {name: _primitive(getattr(value, name)) for name in value.__dataclass_fields__}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    return value


def _read(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != LIFECYCLE_STORE_SCHEMA or not isinstance(payload.get("record"), dict):
        raise ValueError("ACTIVE_LIFECYCLE_STORED_RECORD_INVALID")
    return payload["record"]


def _position_from_dict(value):  # type: ignore[no-untyped-def]
    data = dict(value)
    for name in ("mode", "state", "direction"):
        data[name] = {"mode": SponsorTradeChoice, "state": ActiveLifecycleState, "direction": V1Direction}[name](data[name])
    if data.get("prior_state") is not None:
        data["prior_state"] = ActiveLifecycleState(data["prior_state"])
    for name in ("model_entry", "stop", "invalidation", "target", "model_risk_reward", "actual_entry", "last_observed_price"):
        if data.get(name) is not None:
            data[name] = Decimal(data[name])
    for name in ("entry_timestamp", "last_observed_at", "monitoring_outage_started_at", "created_at", "updated_at"):
        if data.get(name) is not None:
            data[name] = datetime.fromisoformat(data[name])
    for name in ("outstanding_notification_ids", "lifecycle_event_ids", "provenance"):
        data[name] = tuple(data[name])
    data["observed_event_types"] = tuple(
        LifecycleEventType(item) for item in data["observed_event_types"]
    )
    return ActiveLifecyclePosition(**data)


def _event_from_dict(value):  # type: ignore[no-untyped-def]
    data = dict(value)
    data["mode"] = SponsorTradeChoice(data["mode"])
    data["direction"] = V1Direction(data["direction"])
    data["event_type"] = LifecycleEventType(data["event_type"])
    data["ordering_status"] = LifecycleOrderingStatus(data["ordering_status"])
    for name in ("observed_price", "model_entry", "stop", "invalidation", "target", "actual_entry"):
        if data.get(name) is not None:
            data[name] = Decimal(data[name])
    for name in ("event_timestamp", "observation_boundary", "created_at"):
        data[name] = datetime.fromisoformat(data[name])
    data["provider_provenance"] = tuple(data["provider_provenance"])
    data["domain008_context"] = tuple(data["domain008_context"])
    return TradeLifecycleEvent(**data)


def _notification_from_dict(value):  # type: ignore[no-untyped-def]
    data = dict(value)
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    return LifecycleNotification(**data)


def _closure_from_dict(value):  # type: ignore[no-untyped-def]
    data = dict(value)
    data["mode"] = SponsorTradeChoice(data["mode"])
    data["direction"] = V1Direction(data["direction"])
    data["exit_reason"] = TradeExitReason(data["exit_reason"])
    for name in ("model_entry", "actual_entry", "stop", "invalidation", "target", "actual_exit", "gross_pnl", "percentage_result", "realised_r", "model_risk_reward"):
        data[name] = Decimal(data[name])
    for name in ("exit_timestamp", "created_at"):
        data[name] = datetime.fromisoformat(data[name])
    data["lifecycle_event_ids"] = tuple(data["lifecycle_event_ids"])
    data["event_provenance"] = tuple(data["event_provenance"])
    return TradeClosureRecord(**data)


def _atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _immutable(path: Path, payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError("ACTIVE_LIFECYCLE_IMMUTABLE_RECORD_CONFLICT")
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(encoded, encoding="utf-8")
    os.chmod(path, 0o600)


def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}-{sha256('|'.join(parts).encode()).hexdigest()}"


def _identity(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(item in "0123456789abcdef" for item in value)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _decimal(value: object) -> Decimal:
    try:
        result = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError("LIFECYCLE_DECIMAL_INVALID") from error
    if not result.is_finite():
        raise ValueError("LIFECYCLE_DECIMAL_INVALID")
    return result


def _positive(value: object) -> Decimal:
    result = _decimal(value)
    if result <= 0:
        raise ValueError("LIFECYCLE_POSITIVE_VALUE_REQUIRED")
    return result


__all__ = [
    "ACTIVE_TRADE_LIFECYCLE_POLICY_ID", "ActiveLifecyclePosition",
    "ActiveLifecycleState", "ActiveTradeLifecycleEngine",
    "ActiveTradeLifecycleService", "ActiveTradeLifecycleSnapshot",
    "ActiveLifecycleMonitoringCoordinator",
    "AnalyticalInvalidationEvidence", "GovernedLifecycleObservation",
    "LIFECYCLE_EVENT_CONTRACT_ID", "LifecycleEventType",
    "LifecycleNotification", "LocalActiveTradeLifecycleStore",
    "TRADE_CLOSURE_CONTRACT_ID", "TradeClosureRecord", "TradeExitReason",
    "TradeLifecycleEvent", "admit_kite_lifecycle_observation",
    "create_active_lifecycle",
]
