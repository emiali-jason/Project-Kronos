"""WO-17 Slice 4 deterministic closure and lifecycle-event contracts.

The module consumes immutable Slice 2 position evidence and Slice 3 lifecycle
facts.  It never acquires market data, delivers a notification, persists a
record, calculates economics, or operates a broker position.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Sequence

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo16 import Wo16SponsorDecision
from kronos.intraday.wo17 import (
    WO17_CONTRACT_VERSION,
    WO17_POLICY_CHECKSUM,
    WO17_POLICY_IDENTITY,
    WO17_POLICY_VERSION,
    Wo17ContractError,
    canonical_document_bytes,
)
from kronos.intraday.wo17_lifecycle import (
    Wo17LifecycleAssessment,
    Wo17LifecycleEvent,
    Wo17LifecycleMachine,
    Wo17LifecycleTransition,
    Wo17LifecycleTransitionCode,
    Wo17MonitoringAvailability,
    Wo17SessionEndFact,
)
from kronos.intraday.wo17_position import (
    Wo17PositionEvent,
    Wo17PositionMachine,
    Wo17PositionState,
)


WO17_LIVE_EXIT_ATTESTATION_IDENTITY = (
    "KRONOS-INTRADAY-WO17-LIVE-EXIT-ATTESTATION-V1"
)
WO17_POSITION_CLOSURE_IDENTITY = "KRONOS-INTRADAY-WO17-POSITION-CLOSURE-V1"
WO17_NOTIFICATION_WORTHY_EVENT_IDENTITY = (
    "KRONOS-INTRADAY-WO17-NOTIFICATION-WORTHY-EVENT-V1"
)
WO17_CLOSURE_STATE_IDENTITY = "KRONOS-INTRADAY-WO17-CLOSURE-STATE-V1"


class Wo17ClosureState(StrEnum):
    ACTIVE = "ACTIVE"
    PAPER_CLOSED = "PAPER_CLOSED"
    LIVE_CLOSED = "LIVE_CLOSED"


class Wo17ClosureReason(StrEnum):
    STOP_OBSERVED = "STOP_OBSERVED"
    TARGET_OBSERVED = "TARGET_OBSERVED"
    SPONSOR_ATTESTED_ACTUAL_EXIT = "SPONSOR_ATTESTED_ACTUAL_EXIT"


class Wo17NotificationWorthyEvent(StrEnum):
    PAPER_ENTRY_OBSERVED = "PAPER_ENTRY_OBSERVED"
    LIVE_ENTRY_ATTESTED = "LIVE_ENTRY_ATTESTED"
    STOP_OBSERVED = "STOP_OBSERVED"
    TARGET_OBSERVED = "TARGET_OBSERVED"
    INVALIDATION_OBSERVED = "INVALIDATION_OBSERVED"
    MONITORING_INTERRUPTED = "MONITORING_INTERRUPTED"
    MONITORING_RECOVERED = "MONITORING_RECOVERED"
    LIFECYCLE_EVENT_ORDER_UNRESOLVED = "LIFECYCLE_EVENT_ORDER_UNRESOLVED"
    SESSION_ENDED = "SESSION_ENDED"
    PAPER_CLOSED = "PAPER_CLOSED"
    LIVE_CLOSURE_ATTESTED = "LIVE_CLOSURE_ATTESTED"


class Wo17ClosureTransitionCode(StrEnum):
    EVENT_RECORDED = "EVENT_RECORDED"
    PAPER_CLOSED = "PAPER_CLOSED"
    LIVE_CLOSED = "LIVE_CLOSED"
    EXACT_REPLAY = "EXACT_REPLAY"


class Wo17ClosureFailure(StrEnum):
    SOURCE_CONTRACT_INVALID = "SOURCE_CONTRACT_INVALID"
    POSITION_NOT_ACTIVE = "POSITION_NOT_ACTIVE"
    POSITION_MODE_MISMATCH = "POSITION_MODE_MISMATCH"
    POSITION_BINDING_MISMATCH = "POSITION_BINDING_MISMATCH"
    STALE_LIFECYCLE_EVIDENCE = "STALE_LIFECYCLE_EVIDENCE"
    PAPER_CLOSURE_SOURCE_NOT_AUTHORIZED = "PAPER_CLOSURE_SOURCE_NOT_AUTHORIZED"
    LIFECYCLE_EVENT_ORDER_UNRESOLVED = "LIFECYCLE_EVENT_ORDER_UNRESOLVED"
    MANUAL_PAPER_CLOSURE_PROHIBITED = "MANUAL_PAPER_CLOSURE_PROHIBITED"
    LIVE_EXIT_ATTESTATION_REQUIRED = "LIVE_EXIT_ATTESTATION_REQUIRED"
    LIVE_EXIT_BEFORE_ENTRY = "LIVE_EXIT_BEFORE_ENTRY"
    LIVE_ATTESTATION_BEFORE_EXIT = "LIVE_ATTESTATION_BEFORE_EXIT"
    CLOSURE_CONFLICT = "CLOSURE_CONFLICT"
    EVENT_SOURCE_NOT_AUTHORIZED = "EVENT_SOURCE_NOT_AUTHORIZED"
    EVENT_CONFLICT = "EVENT_CONFLICT"


class Wo17ClosureRejected(Wo17ContractError):
    def __init__(self, failure: Wo17ClosureFailure):
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class Wo17LiveExitAttestation:
    attestation_identity: str
    attestation_integrity: str
    position_identity: str
    position_integrity: str
    upstream_snapshot_identity: str
    upstream_snapshot_integrity: str
    upstream_lineage_identity: str
    upstream_lineage_integrity: str
    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    contract_expiry: date | None
    roll_lineage_identity: str | None
    entry_session_identity: str
    entry_trading_date: date
    direction: SemanticDirection
    actual_exit_price: Decimal
    actual_exit_timestamp: datetime
    attestation_operation_timestamp: datetime
    sponsor_operation_identity: str
    bounded_manual_action_provenance: tuple[str, ...]
    schema_identity: str = WO17_LIVE_EXIT_ATTESTATION_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    broker_confirmation: bool = False
    broker_acknowledgement: bool = False
    broker_fill_authority: bool = False
    broker_order_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "attestation_identity", "attestation_integrity")
        if (
            not _texts(
                (
                    self.position_identity,
                    self.position_integrity,
                    self.upstream_snapshot_identity,
                    self.upstream_snapshot_integrity,
                    self.upstream_lineage_identity,
                    self.upstream_lineage_integrity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.entry_session_identity,
                    self.sponsor_operation_identity,
                    *self.bounded_manual_action_provenance,
                )
            )
            or type(self.entry_trading_date) is not date
            or type(self.direction) is not SemanticDirection
            or not _decimal(self.actual_exit_price)
            or not _aware(self.actual_exit_timestamp)
            or not _aware(self.attestation_operation_timestamp)
            or self.attestation_operation_timestamp < self.actual_exit_timestamp
            or self.schema_identity != WO17_LIVE_EXIT_ATTESTATION_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or any(
                (
                    self.broker_confirmation,
                    self.broker_acknowledgement,
                    self.broker_fill_authority,
                    self.broker_order_authority,
                    self.execution_authority,
                )
            )
            or self.attestation_identity
            != _identity("INTRADAY-WO17-LIVE-EXIT-ATTESTATION-", values)
            or self.attestation_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-LIVE-EXIT-ATTESTATION-", values)
        ):
            raise Wo17ContractError("WO17_LIVE_EXIT_ATTESTATION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17PositionClosure:
    closure_identity: str
    closure_integrity: str
    position_identity: str
    position_integrity: str
    upstream_snapshot_identity: str
    upstream_snapshot_integrity: str
    upstream_lineage_identity: str
    upstream_lineage_integrity: str
    decision: Wo16SponsorDecision
    closure_state: Wo17ClosureState
    closure_reason: Wo17ClosureReason
    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    contract_expiry: date | None
    roll_lineage_identity: str | None
    entry_session_identity: str
    entry_trading_date: date
    direction: SemanticDirection
    entry_price: Decimal
    entry_timestamp: datetime
    exit_price: Decimal
    exit_timestamp: datetime
    closure_recorded_at: datetime
    source_schema_identity: str
    source_identity: str
    source_integrity: str
    live_exit_attestation_identity: str | None
    exit_evidence_role: str
    provenance: tuple[str, ...]
    schema_identity: str = WO17_POSITION_CLOSURE_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    manual_paper_closure: bool = False
    broker_confirmation: bool = False
    broker_acknowledgement: bool = False
    broker_fill: str = "UNAVAILABLE"
    quantity: str = "UNAVAILABLE"
    fees: str = "UNAVAILABLE"
    monetary_pnl: str = "UNAVAILABLE"
    realised_r: str = "UNAVAILABLE"
    broker_order_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "closure_identity", "closure_integrity")
        unavailable = (
            self.broker_fill,
            self.quantity,
            self.fees,
            self.monetary_pnl,
            self.realised_r,
        )
        paper = self.decision is Wo16SponsorDecision.PAPER
        if (
            self.decision not in {Wo16SponsorDecision.PAPER, Wo16SponsorDecision.LIVE}
            or type(self.closure_state) is not Wo17ClosureState
            or type(self.closure_reason) is not Wo17ClosureReason
            or not _texts(
                (
                    self.position_identity,
                    self.position_integrity,
                    self.upstream_snapshot_identity,
                    self.upstream_snapshot_integrity,
                    self.upstream_lineage_identity,
                    self.upstream_lineage_integrity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.entry_session_identity,
                    self.source_schema_identity,
                    self.source_identity,
                    self.source_integrity,
                    self.exit_evidence_role,
                    *self.provenance,
                )
            )
            or type(self.entry_trading_date) is not date
            or type(self.direction) is not SemanticDirection
            or not _decimal(self.entry_price)
            or not _decimal(self.exit_price)
            or not _aware(self.entry_timestamp)
            or not _aware(self.exit_timestamp)
            or not _aware(self.closure_recorded_at)
            or self.exit_timestamp < self.entry_timestamp
            or self.closure_recorded_at < self.exit_timestamp
            or (
                paper
                and (
                    self.closure_state is not Wo17ClosureState.PAPER_CLOSED
                    or self.closure_reason
                    not in {
                        Wo17ClosureReason.STOP_OBSERVED,
                        Wo17ClosureReason.TARGET_OBSERVED,
                    }
                    or self.live_exit_attestation_identity is not None
                    or self.exit_evidence_role != "MODEL_OBSERVED_EXIT_EVIDENCE"
                )
            )
            or (
                not paper
                and (
                    self.closure_state is not Wo17ClosureState.LIVE_CLOSED
                    or self.closure_reason
                    is not Wo17ClosureReason.SPONSOR_ATTESTED_ACTUAL_EXIT
                    or not _text(self.live_exit_attestation_identity)
                    or self.live_exit_attestation_identity != self.source_identity
                    or self.exit_evidence_role
                    != "SPONSOR_ATTESTED_ACTUAL_EXIT_EVIDENCE"
                )
            )
            or any(value != "UNAVAILABLE" for value in unavailable)
            or self.schema_identity != WO17_POSITION_CLOSURE_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.manual_paper_closure
            or self.broker_confirmation
            or self.broker_acknowledgement
            or self.broker_order_authority
            or self.execution_authority
            or self.closure_identity
            != _identity("INTRADAY-WO17-POSITION-CLOSURE-", values)
            or self.closure_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-POSITION-CLOSURE-", values)
        ):
            raise Wo17ContractError("WO17_POSITION_CLOSURE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17NotificationWorthyEventRecord:
    event_identity: str
    event_integrity: str
    event_type: Wo17NotificationWorthyEvent
    position_identity: str
    position_integrity: str
    upstream_snapshot_identity: str
    upstream_snapshot_integrity: str
    upstream_lineage_identity: str
    upstream_lineage_integrity: str
    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    entry_session_identity: str
    entry_trading_date: date
    direction: SemanticDirection
    source_schema_identity: str
    source_identity: str
    source_integrity: str
    event_at: datetime
    recorded_at: datetime
    provenance: tuple[str, ...]
    schema_identity: str = WO17_NOTIFICATION_WORTHY_EVENT_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    notification_worthy: bool = True
    notification_delivered: bool = False
    notification_delivery_authority: bool = False
    notification_lifecycle_authority: bool = False
    persistence_authority: bool = False
    broker_order_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "event_identity", "event_integrity")
        if (
            type(self.event_type) is not Wo17NotificationWorthyEvent
            or not _texts(
                (
                    self.position_identity,
                    self.position_integrity,
                    self.upstream_snapshot_identity,
                    self.upstream_snapshot_integrity,
                    self.upstream_lineage_identity,
                    self.upstream_lineage_integrity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.entry_session_identity,
                    self.source_schema_identity,
                    self.source_identity,
                    self.source_integrity,
                    *self.provenance,
                )
            )
            or type(self.entry_trading_date) is not date
            or type(self.direction) is not SemanticDirection
            or not _aware(self.event_at)
            or not _aware(self.recorded_at)
            or self.recorded_at < self.event_at
            or self.schema_identity != WO17_NOTIFICATION_WORTHY_EVENT_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.notification_worthy is not True
            or self.notification_delivered
            or self.notification_delivery_authority
            or self.notification_lifecycle_authority
            or self.persistence_authority
            or self.broker_order_authority
            or self.execution_authority
            or self.event_identity
            != _identity("INTRADAY-WO17-NOTIFICATION-WORTHY-EVENT-", values)
            or self.event_integrity
            != _identity(
                "INTEGRITY-INTRADAY-WO17-NOTIFICATION-WORTHY-EVENT-", values
            )
        ):
            raise Wo17ContractError("WO17_NOTIFICATION_WORTHY_EVENT_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17ClosureMachine:
    state_identity: str
    state_integrity: str
    position: Wo17PositionMachine
    closure_state: Wo17ClosureState
    closure: Wo17PositionClosure | None
    events: tuple[Wo17NotificationWorthyEventRecord, ...]
    last_transition_at: datetime
    policy_identity: str = WO17_POLICY_IDENTITY
    policy_version: str = WO17_POLICY_VERSION
    policy_checksum: str = WO17_POLICY_CHECKSUM
    schema_identity: str = WO17_CLOSURE_STATE_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    provider_acquisition_authority: bool = False
    persistence_authority: bool = False
    notification_delivery_authority: bool = False
    journal_authority: bool = False
    analytics_authority: bool = False
    broker_order_authority: bool = False
    execution_authority: bool = False
    quantity: str = "UNAVAILABLE"
    fees: str = "UNAVAILABLE"
    monetary_pnl: str = "UNAVAILABLE"
    realised_r: str = "UNAVAILABLE"

    def __post_init__(self) -> None:
        values = _without(self, "state_identity", "state_integrity")
        unavailable = (self.quantity, self.fees, self.monetary_pnl, self.realised_r)
        if (
            type(self.position) is not Wo17PositionMachine
            or self.position.state
            not in {Wo17PositionState.PAPER_ACTIVE, Wo17PositionState.LIVE_ACTIVE}
            or self.position.position_evidence is None
            or type(self.closure_state) is not Wo17ClosureState
            or any(
                type(item) is not Wo17NotificationWorthyEventRecord
                for item in self.events
            )
            or len({item.event_identity for item in self.events}) != len(self.events)
            or not _aware(self.last_transition_at)
            or (self.closure_state is Wo17ClosureState.ACTIVE)
            != (self.closure is None)
            or (
                self.closure is not None
                and self.closure.closure_state is not self.closure_state
            )
            or not _machine_bindings_valid(self)
            or self.policy_identity != WO17_POLICY_IDENTITY
            or self.policy_version != WO17_POLICY_VERSION
            or self.policy_checksum != WO17_POLICY_CHECKSUM
            or self.schema_identity != WO17_CLOSURE_STATE_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or any(
                (
                    self.provider_acquisition_authority,
                    self.persistence_authority,
                    self.notification_delivery_authority,
                    self.journal_authority,
                    self.analytics_authority,
                    self.broker_order_authority,
                    self.execution_authority,
                )
            )
            or any(value != "UNAVAILABLE" for value in unavailable)
            or self.state_identity != _identity("INTRADAY-WO17-CLOSURE-STATE-", values)
            or self.state_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-CLOSURE-STATE-", values)
        ):
            raise Wo17ContractError("WO17_CLOSURE_STATE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17ClosureTransition:
    previous_state_identity: str
    current: Wo17ClosureMachine
    transition_code: Wo17ClosureTransitionCode
    events: tuple[Wo17NotificationWorthyEventRecord, ...]
    closure: Wo17PositionClosure | None
    applied: bool
    replayed: bool = False


def create_wo17_closure_machine(position: Wo17PositionMachine) -> Wo17ClosureMachine:
    _require_active_position(position)
    return _machine(
        position=position,
        closure_state=Wo17ClosureState.ACTIVE,
        closure=None,
        events=(),
        last_transition_at=position.last_transition_at,
    )


def create_wo17_live_exit_attestation(
    *,
    machine: Wo17ClosureMachine,
    actual_exit_price: Decimal,
    actual_exit_timestamp: datetime,
    attestation_operation_timestamp: datetime,
    sponsor_operation_identity: str,
    bounded_manual_action_provenance: tuple[str, ...],
) -> Wo17LiveExitAttestation:
    _require_machine(machine)
    if machine.position.state is not Wo17PositionState.LIVE_ACTIVE:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_MODE_MISMATCH)
    position = machine.position.position_evidence
    if position is None:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_NOT_ACTIVE)
    if not _decimal(actual_exit_price) or not _aware(actual_exit_timestamp):
        raise Wo17ClosureRejected(Wo17ClosureFailure.SOURCE_CONTRACT_INVALID)
    if not _aware(attestation_operation_timestamp):
        raise Wo17ClosureRejected(Wo17ClosureFailure.SOURCE_CONTRACT_INVALID)
    if actual_exit_timestamp < position.entry_timestamp:
        raise Wo17ClosureRejected(Wo17ClosureFailure.LIVE_EXIT_BEFORE_ENTRY)
    if attestation_operation_timestamp < actual_exit_timestamp:
        raise Wo17ClosureRejected(Wo17ClosureFailure.LIVE_ATTESTATION_BEFORE_EXIT)
    snapshot = machine.position.upstream_snapshot
    lineage = snapshot.lineage
    values = {
        "position_identity": position.position_identity,
        "position_integrity": position.position_integrity,
        "upstream_snapshot_identity": snapshot.snapshot_identity,
        "upstream_snapshot_integrity": snapshot.snapshot_integrity,
        "upstream_lineage_identity": lineage.lineage_identity,
        "upstream_lineage_integrity": lineage.lineage_integrity,
        "canonical_subject_identity": lineage.canonical_subject_identity,
        "instrument_identity": lineage.instrument_identity,
        "actual_contract_identity": lineage.actual_contract_identity,
        "contract_expiry": lineage.contract_expiry,
        "roll_lineage_identity": lineage.roll_lineage_identity,
        "entry_session_identity": lineage.session_identity,
        "entry_trading_date": lineage.trading_date,
        "direction": lineage.direction,
        "actual_exit_price": actual_exit_price,
        "actual_exit_timestamp": actual_exit_timestamp,
        "attestation_operation_timestamp": attestation_operation_timestamp,
        "sponsor_operation_identity": sponsor_operation_identity,
        "bounded_manual_action_provenance": bounded_manual_action_provenance,
        "schema_identity": WO17_LIVE_EXIT_ATTESTATION_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "broker_confirmation": False,
        "broker_acknowledgement": False,
        "broker_fill_authority": False,
        "broker_order_authority": False,
        "execution_authority": False,
    }
    return Wo17LiveExitAttestation(
        attestation_identity=_identity(
            "INTRADAY-WO17-LIVE-EXIT-ATTESTATION-", values
        ),
        attestation_integrity=_identity(
            "INTEGRITY-INTRADAY-WO17-LIVE-EXIT-ATTESTATION-", values
        ),
        **values,
    )


def close_wo17_paper_position(
    machine: Wo17ClosureMachine,
    lifecycle: Wo17LifecycleMachine,
    assessment: Wo17LifecycleAssessment,
) -> Wo17ClosureTransition:
    _require_machine(machine)
    if machine.position.state is not Wo17PositionState.PAPER_ACTIVE:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_MODE_MISMATCH)
    observation = _require_current_assessment(machine, lifecycle, assessment)
    if assessment.ordering_unresolved:
        raise Wo17ClosureRejected(
            Wo17ClosureFailure.LIFECYCLE_EVENT_ORDER_UNRESOLVED
        )
    if assessment.stop_observed == assessment.target_observed:
        raise Wo17ClosureRejected(
            Wo17ClosureFailure.PAPER_CLOSURE_SOURCE_NOT_AUTHORIZED
        )
    reason = (
        Wo17ClosureReason.STOP_OBSERVED
        if assessment.stop_observed
        else Wo17ClosureReason.TARGET_OBSERVED
    )
    closure = _closure(
        machine,
        closure_state=Wo17ClosureState.PAPER_CLOSED,
        reason=reason,
        exit_price=observation.observed_price,
        exit_timestamp=observation.observed_at,
        recorded_at=assessment.assessed_at,
        source_schema_identity=assessment.schema_identity,
        source_identity=assessment.assessment_identity,
        source_integrity=assessment.assessment_integrity,
        live_exit_attestation_identity=None,
        exit_evidence_role="MODEL_OBSERVED_EXIT_EVIDENCE",
        provenance=(
            observation.observation_identity,
            assessment.assessment_identity,
            "ADR-0027",
            "WO-17-SLICE-4",
        ),
    )
    return _apply_closure(
        machine,
        closure,
        Wo17NotificationWorthyEvent.PAPER_CLOSED,
        Wo17ClosureTransitionCode.PAPER_CLOSED,
    )


def close_wo17_live_position(
    machine: Wo17ClosureMachine,
    attestation: Wo17LiveExitAttestation,
) -> Wo17ClosureTransition:
    _require_machine(machine)
    if machine.position.state is not Wo17PositionState.LIVE_ACTIVE:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_MODE_MISMATCH)
    if type(attestation) is not Wo17LiveExitAttestation:
        raise Wo17ClosureRejected(Wo17ClosureFailure.LIVE_EXIT_ATTESTATION_REQUIRED)
    _require_attestation_binding(machine, attestation)
    position = machine.position.position_evidence
    if position is None:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_NOT_ACTIVE)
    if attestation.actual_exit_timestamp < position.entry_timestamp:
        raise Wo17ClosureRejected(Wo17ClosureFailure.LIVE_EXIT_BEFORE_ENTRY)
    if attestation.attestation_operation_timestamp < attestation.actual_exit_timestamp:
        raise Wo17ClosureRejected(Wo17ClosureFailure.LIVE_ATTESTATION_BEFORE_EXIT)
    if attestation.attestation_operation_timestamp < machine.last_transition_at:
        raise Wo17ClosureRejected(Wo17ClosureFailure.STALE_LIFECYCLE_EVIDENCE)
    closure = _closure(
        machine,
        closure_state=Wo17ClosureState.LIVE_CLOSED,
        reason=Wo17ClosureReason.SPONSOR_ATTESTED_ACTUAL_EXIT,
        exit_price=attestation.actual_exit_price,
        exit_timestamp=attestation.actual_exit_timestamp,
        recorded_at=attestation.attestation_operation_timestamp,
        source_schema_identity=attestation.schema_identity,
        source_identity=attestation.attestation_identity,
        source_integrity=attestation.attestation_integrity,
        live_exit_attestation_identity=attestation.attestation_identity,
        exit_evidence_role="SPONSOR_ATTESTED_ACTUAL_EXIT_EVIDENCE",
        provenance=(attestation.attestation_identity, "ADR-0027", "WO-17-SLICE-4"),
    )
    return _apply_closure(
        machine,
        closure,
        Wo17NotificationWorthyEvent.LIVE_CLOSURE_ATTESTED,
        Wo17ClosureTransitionCode.LIVE_CLOSED,
    )


def reject_wo17_manual_paper_closure(
    machine: Wo17ClosureMachine,
) -> None:
    _require_machine(machine)
    if machine.position.state is not Wo17PositionState.PAPER_ACTIVE:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_MODE_MISMATCH)
    raise Wo17ClosureRejected(Wo17ClosureFailure.MANUAL_PAPER_CLOSURE_PROHIBITED)


def record_wo17_position_entry_event(
    machine: Wo17ClosureMachine,
) -> Wo17ClosureTransition:
    _require_machine(machine)
    position = machine.position.position_evidence
    if position is None:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_NOT_ACTIVE)
    event_type = (
        Wo17NotificationWorthyEvent.PAPER_ENTRY_OBSERVED
        if position.entry_event is Wo17PositionEvent.PAPER_ENTRY_OBSERVED
        else Wo17NotificationWorthyEvent.LIVE_ENTRY_ATTESTED
    )
    event = _event(
        machine,
        event_type=event_type,
        source_schema_identity=position.schema_identity,
        source_identity=position.position_identity,
        source_integrity=position.position_integrity,
        event_at=position.entry_timestamp,
        recorded_at=position.evidence_recorded_at,
        provenance=(position.position_identity, "ADR-0027", "WO-17-SLICE-4"),
    )
    return _record_events(machine, (event,))


def record_wo17_monitoring_event(
    machine: Wo17ClosureMachine,
    transition: Wo17LifecycleTransition,
) -> Wo17ClosureTransition:
    _require_machine(machine)
    if type(transition) is not Wo17LifecycleTransition or not transition.applied:
        raise Wo17ClosureRejected(Wo17ClosureFailure.EVENT_SOURCE_NOT_AUTHORIZED)
    if transition.current.position != machine.position:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_BINDING_MISMATCH)
    mapping = {
        Wo17LifecycleTransitionCode.MONITORING_INTERRUPTED: (
            Wo17MonitoringAvailability.INTERRUPTED,
            Wo17NotificationWorthyEvent.MONITORING_INTERRUPTED,
        ),
        Wo17LifecycleTransitionCode.MONITORING_RECOVERED: (
            Wo17MonitoringAvailability.RECOVERING,
            Wo17NotificationWorthyEvent.MONITORING_RECOVERED,
        ),
    }
    expected = mapping.get(transition.transition_code)
    if expected is None or transition.current.monitoring_availability is not expected[0]:
        raise Wo17ClosureRejected(Wo17ClosureFailure.EVENT_SOURCE_NOT_AUTHORIZED)
    event = _event(
        machine,
        event_type=expected[1],
        source_schema_identity=transition.current.schema_identity,
        source_identity=transition.current.state_identity,
        source_integrity=transition.current.state_integrity,
        event_at=transition.current.last_transition_at,
        recorded_at=transition.current.last_transition_at,
        provenance=(transition.current.state_identity, "ADR-0027", "WO-17-SLICE-4"),
    )
    return _record_events(machine, (event,))


def record_wo17_assessment_events(
    machine: Wo17ClosureMachine,
    lifecycle: Wo17LifecycleMachine,
    assessment: Wo17LifecycleAssessment,
) -> Wo17ClosureTransition:
    observation = _require_current_assessment(machine, lifecycle, assessment)
    if not assessment.observed_events:
        raise Wo17ClosureRejected(Wo17ClosureFailure.EVENT_SOURCE_NOT_AUTHORIZED)
    mapping = {
        Wo17LifecycleEvent.STOP_OBSERVED: Wo17NotificationWorthyEvent.STOP_OBSERVED,
        Wo17LifecycleEvent.TARGET_OBSERVED: Wo17NotificationWorthyEvent.TARGET_OBSERVED,
        Wo17LifecycleEvent.INVALIDATION_OBSERVED: (
            Wo17NotificationWorthyEvent.INVALIDATION_OBSERVED
        ),
        Wo17LifecycleEvent.LIFECYCLE_EVENT_ORDER_UNRESOLVED: (
            Wo17NotificationWorthyEvent.LIFECYCLE_EVENT_ORDER_UNRESOLVED
        ),
    }
    events = tuple(
        _event(
            machine,
            event_type=mapping[item],
            source_schema_identity=assessment.schema_identity,
            source_identity=assessment.assessment_identity,
            source_integrity=assessment.assessment_integrity,
            event_at=observation.observed_at,
            recorded_at=assessment.assessed_at,
            provenance=(
                observation.observation_identity,
                assessment.assessment_identity,
                "ADR-0027",
                "WO-17-SLICE-4",
            ),
        )
        for item in assessment.observed_events
    )
    return _record_events(machine, events)


def record_wo17_session_end_event(
    machine: Wo17ClosureMachine,
    lifecycle: Wo17LifecycleMachine,
    fact: Wo17SessionEndFact,
) -> Wo17ClosureTransition:
    _require_machine(machine)
    if (
        type(lifecycle) is not Wo17LifecycleMachine
        or lifecycle.position != machine.position
        or lifecycle.monitoring_availability is not Wo17MonitoringAvailability.SESSION_ENDED
        or lifecycle.session_end_fact != fact
    ):
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_BINDING_MISMATCH)
    _require_fact_binding(machine, fact)
    event = _event(
        machine,
        event_type=Wo17NotificationWorthyEvent.SESSION_ENDED,
        source_schema_identity=fact.schema_identity,
        source_identity=fact.fact_identity,
        source_integrity=fact.fact_integrity,
        event_at=fact.session_closes_at,
        recorded_at=fact.observed_at,
        provenance=(fact.fact_identity, "ADR-0027", "WO-17-SLICE-4"),
    )
    return _record_events(machine, (event,))


def _apply_closure(
    machine: Wo17ClosureMachine,
    closure: Wo17PositionClosure,
    event_type: Wo17NotificationWorthyEvent,
    code: Wo17ClosureTransitionCode,
) -> Wo17ClosureTransition:
    if machine.closure is not None:
        if machine.closure == closure:
            existing = tuple(
                item
                for item in machine.events
                if item.event_type is event_type
                and item.source_identity == closure.closure_identity
            )
            return Wo17ClosureTransition(
                machine.state_identity,
                machine,
                Wo17ClosureTransitionCode.EXACT_REPLAY,
                existing,
                machine.closure,
                False,
                True,
            )
        raise Wo17ClosureRejected(Wo17ClosureFailure.CLOSURE_CONFLICT)
    event = _event(
        machine,
        event_type=event_type,
        source_schema_identity=closure.schema_identity,
        source_identity=closure.closure_identity,
        source_integrity=closure.closure_integrity,
        event_at=closure.exit_timestamp,
        recorded_at=closure.closure_recorded_at,
        provenance=(closure.closure_identity, "ADR-0027", "WO-17-SLICE-4"),
    )
    current = _update(
        machine,
        closure_state=closure.closure_state,
        closure=closure,
        events=(*machine.events, event),
        last_transition_at=closure.closure_recorded_at,
    )
    return Wo17ClosureTransition(
        machine.state_identity, current, code, (event,), closure, True
    )


def _record_events(
    machine: Wo17ClosureMachine,
    events: tuple[Wo17NotificationWorthyEventRecord, ...],
) -> Wo17ClosureTransition:
    _require_machine(machine)
    additions: list[Wo17NotificationWorthyEventRecord] = []
    for event in events:
        _require_event_binding(machine, event)
        replay = False
        for existing in (*machine.events, *additions):
            if existing.event_identity == event.event_identity:
                if existing == event:
                    replay = True
                    break
                raise Wo17ClosureRejected(Wo17ClosureFailure.EVENT_CONFLICT)
            if (
                existing.event_type is event.event_type
                and existing.source_identity == event.source_identity
            ):
                if existing == event:
                    replay = True
                    break
                raise Wo17ClosureRejected(Wo17ClosureFailure.EVENT_CONFLICT)
        if not replay:
            additions.append(event)
    if not additions:
        return Wo17ClosureTransition(
            machine.state_identity,
            machine,
            Wo17ClosureTransitionCode.EXACT_REPLAY,
            events,
            machine.closure,
            False,
            True,
        )
    if machine.closure_state is not Wo17ClosureState.ACTIVE:
        raise Wo17ClosureRejected(Wo17ClosureFailure.EVENT_SOURCE_NOT_AUTHORIZED)
    recorded_at = max(item.recorded_at for item in additions)
    if recorded_at < machine.last_transition_at:
        raise Wo17ClosureRejected(Wo17ClosureFailure.STALE_LIFECYCLE_EVIDENCE)
    current = _update(
        machine,
        events=(*machine.events, *additions),
        last_transition_at=recorded_at,
    )
    return Wo17ClosureTransition(
        machine.state_identity,
        current,
        Wo17ClosureTransitionCode.EVENT_RECORDED,
        tuple(additions),
        machine.closure,
        True,
    )


def _require_current_assessment(
    machine: Wo17ClosureMachine,
    lifecycle: Wo17LifecycleMachine,
    assessment: Wo17LifecycleAssessment,
):
    _require_machine(machine)
    if (
        type(lifecycle) is not Wo17LifecycleMachine
        or lifecycle.position != machine.position
        or type(assessment) is not Wo17LifecycleAssessment
    ):
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_BINDING_MISMATCH)
    if not lifecycle.assessments or lifecycle.assessments[-1] != assessment:
        raise Wo17ClosureRejected(Wo17ClosureFailure.STALE_LIFECYCLE_EVIDENCE)
    if assessment.assessed_at < machine.last_transition_at:
        raise Wo17ClosureRejected(Wo17ClosureFailure.STALE_LIFECYCLE_EVIDENCE)
    matches = tuple(
        item
        for item in lifecycle.observations
        if item.observation_identity == assessment.observation_identity
        and item.observation_integrity == assessment.observation_integrity
    )
    if len(matches) != 1 or matches[0] != lifecycle.observations[-1]:
        raise Wo17ClosureRejected(Wo17ClosureFailure.STALE_LIFECYCLE_EVIDENCE)
    _require_assessment_binding(machine, assessment)
    return matches[0]


def _require_assessment_binding(
    machine: Wo17ClosureMachine,
    assessment: Wo17LifecycleAssessment,
) -> None:
    position = machine.position.position_evidence
    if position is None:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_NOT_ACTIVE)
    lineage = machine.position.upstream_snapshot.lineage
    expected = (
        position.position_identity,
        position.position_integrity,
        lineage.lineage_identity,
        lineage.canonical_subject_identity,
        lineage.instrument_identity,
        lineage.actual_contract_identity,
        lineage.roll_lineage_identity,
        lineage.session_identity,
        lineage.trading_date,
        lineage.direction,
        lineage.entry_reference,
        lineage.stop,
        lineage.canonical_target,
        lineage.thesis_invalidation_reference,
        lineage.thesis_invalidation_event,
    )
    received = (
        assessment.position_identity,
        assessment.position_integrity,
        assessment.upstream_lineage_identity,
        assessment.canonical_subject_identity,
        assessment.instrument_identity,
        assessment.actual_contract_identity,
        assessment.roll_lineage_identity,
        assessment.session_identity,
        assessment.trading_date,
        assessment.direction,
        assessment.entry_reference,
        assessment.stop,
        assessment.canonical_target,
        assessment.thesis_invalidation_reference,
        assessment.thesis_invalidation_event,
    )
    if received != expected:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_BINDING_MISMATCH)


def _require_attestation_binding(
    machine: Wo17ClosureMachine,
    attestation: Wo17LiveExitAttestation,
) -> None:
    position = machine.position.position_evidence
    if position is None:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_NOT_ACTIVE)
    snapshot = machine.position.upstream_snapshot
    lineage = snapshot.lineage
    expected = (
        position.position_identity,
        position.position_integrity,
        snapshot.snapshot_identity,
        snapshot.snapshot_integrity,
        lineage.lineage_identity,
        lineage.lineage_integrity,
        lineage.canonical_subject_identity,
        lineage.instrument_identity,
        lineage.actual_contract_identity,
        lineage.contract_expiry,
        lineage.roll_lineage_identity,
        lineage.session_identity,
        lineage.trading_date,
        lineage.direction,
    )
    received = (
        attestation.position_identity,
        attestation.position_integrity,
        attestation.upstream_snapshot_identity,
        attestation.upstream_snapshot_integrity,
        attestation.upstream_lineage_identity,
        attestation.upstream_lineage_integrity,
        attestation.canonical_subject_identity,
        attestation.instrument_identity,
        attestation.actual_contract_identity,
        attestation.contract_expiry,
        attestation.roll_lineage_identity,
        attestation.entry_session_identity,
        attestation.entry_trading_date,
        attestation.direction,
    )
    if received != expected:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_BINDING_MISMATCH)


def _require_fact_binding(
    machine: Wo17ClosureMachine,
    fact: Wo17SessionEndFact,
) -> None:
    position = machine.position.position_evidence
    if position is None:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_NOT_ACTIVE)
    lineage = machine.position.upstream_snapshot.lineage
    expected = (
        position.position_identity,
        position.position_integrity,
        lineage.lineage_identity,
        lineage.canonical_subject_identity,
        lineage.instrument_identity,
        lineage.actual_contract_identity,
        lineage.roll_lineage_identity,
        lineage.session_identity,
        lineage.trading_date,
    )
    received = (
        fact.position_identity,
        fact.position_integrity,
        fact.upstream_lineage_identity,
        fact.canonical_subject_identity,
        fact.instrument_identity,
        fact.actual_contract_identity,
        fact.roll_lineage_identity,
        fact.session_identity,
        fact.trading_date,
    )
    if received != expected:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_BINDING_MISMATCH)


def _require_event_binding(
    machine: Wo17ClosureMachine,
    event: Wo17NotificationWorthyEventRecord,
) -> None:
    if type(event) is not Wo17NotificationWorthyEventRecord:
        raise Wo17ClosureRejected(Wo17ClosureFailure.SOURCE_CONTRACT_INVALID)
    position = machine.position.position_evidence
    if position is None:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_NOT_ACTIVE)
    lineage = machine.position.upstream_snapshot.lineage
    expected = (
        position.position_identity,
        position.position_integrity,
        machine.position.upstream_snapshot.snapshot_identity,
        machine.position.upstream_snapshot.snapshot_integrity,
        lineage.lineage_identity,
        lineage.lineage_integrity,
        lineage.canonical_subject_identity,
        lineage.instrument_identity,
        lineage.actual_contract_identity,
        lineage.roll_lineage_identity,
        lineage.session_identity,
        lineage.trading_date,
        lineage.direction,
    )
    received = (
        event.position_identity,
        event.position_integrity,
        event.upstream_snapshot_identity,
        event.upstream_snapshot_integrity,
        event.upstream_lineage_identity,
        event.upstream_lineage_integrity,
        event.canonical_subject_identity,
        event.instrument_identity,
        event.actual_contract_identity,
        event.roll_lineage_identity,
        event.entry_session_identity,
        event.entry_trading_date,
        event.direction,
    )
    if received != expected:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_BINDING_MISMATCH)


def _closure(
    machine: Wo17ClosureMachine,
    *,
    closure_state: Wo17ClosureState,
    reason: Wo17ClosureReason,
    exit_price: Decimal,
    exit_timestamp: datetime,
    recorded_at: datetime,
    source_schema_identity: str,
    source_identity: str,
    source_integrity: str,
    live_exit_attestation_identity: str | None,
    exit_evidence_role: str,
    provenance: tuple[str, ...],
) -> Wo17PositionClosure:
    position = machine.position.position_evidence
    if position is None:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_NOT_ACTIVE)
    snapshot = machine.position.upstream_snapshot
    lineage = snapshot.lineage
    values = {
        "position_identity": position.position_identity,
        "position_integrity": position.position_integrity,
        "upstream_snapshot_identity": snapshot.snapshot_identity,
        "upstream_snapshot_integrity": snapshot.snapshot_integrity,
        "upstream_lineage_identity": lineage.lineage_identity,
        "upstream_lineage_integrity": lineage.lineage_integrity,
        "decision": position.decision,
        "closure_state": closure_state,
        "closure_reason": reason,
        "canonical_subject_identity": lineage.canonical_subject_identity,
        "instrument_identity": lineage.instrument_identity,
        "actual_contract_identity": lineage.actual_contract_identity,
        "contract_expiry": lineage.contract_expiry,
        "roll_lineage_identity": lineage.roll_lineage_identity,
        "entry_session_identity": lineage.session_identity,
        "entry_trading_date": lineage.trading_date,
        "direction": lineage.direction,
        "entry_price": position.entry_price,
        "entry_timestamp": position.entry_timestamp,
        "exit_price": exit_price,
        "exit_timestamp": exit_timestamp,
        "closure_recorded_at": recorded_at,
        "source_schema_identity": source_schema_identity,
        "source_identity": source_identity,
        "source_integrity": source_integrity,
        "live_exit_attestation_identity": live_exit_attestation_identity,
        "exit_evidence_role": exit_evidence_role,
        "provenance": provenance,
        "schema_identity": WO17_POSITION_CLOSURE_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "manual_paper_closure": False,
        "broker_confirmation": False,
        "broker_acknowledgement": False,
        "broker_fill": "UNAVAILABLE",
        "quantity": "UNAVAILABLE",
        "fees": "UNAVAILABLE",
        "monetary_pnl": "UNAVAILABLE",
        "realised_r": "UNAVAILABLE",
        "broker_order_authority": False,
        "execution_authority": False,
    }
    return Wo17PositionClosure(
        closure_identity=_identity("INTRADAY-WO17-POSITION-CLOSURE-", values),
        closure_integrity=_identity(
            "INTEGRITY-INTRADAY-WO17-POSITION-CLOSURE-", values
        ),
        **values,
    )


def _event(
    machine: Wo17ClosureMachine,
    *,
    event_type: Wo17NotificationWorthyEvent,
    source_schema_identity: str,
    source_identity: str,
    source_integrity: str,
    event_at: datetime,
    recorded_at: datetime,
    provenance: tuple[str, ...],
) -> Wo17NotificationWorthyEventRecord:
    position = machine.position.position_evidence
    if position is None:
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_NOT_ACTIVE)
    snapshot = machine.position.upstream_snapshot
    lineage = snapshot.lineage
    values = {
        "event_type": event_type,
        "position_identity": position.position_identity,
        "position_integrity": position.position_integrity,
        "upstream_snapshot_identity": snapshot.snapshot_identity,
        "upstream_snapshot_integrity": snapshot.snapshot_integrity,
        "upstream_lineage_identity": lineage.lineage_identity,
        "upstream_lineage_integrity": lineage.lineage_integrity,
        "canonical_subject_identity": lineage.canonical_subject_identity,
        "instrument_identity": lineage.instrument_identity,
        "actual_contract_identity": lineage.actual_contract_identity,
        "roll_lineage_identity": lineage.roll_lineage_identity,
        "entry_session_identity": lineage.session_identity,
        "entry_trading_date": lineage.trading_date,
        "direction": lineage.direction,
        "source_schema_identity": source_schema_identity,
        "source_identity": source_identity,
        "source_integrity": source_integrity,
        "event_at": event_at,
        "recorded_at": recorded_at,
        "provenance": provenance,
        "schema_identity": WO17_NOTIFICATION_WORTHY_EVENT_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "notification_worthy": True,
        "notification_delivered": False,
        "notification_delivery_authority": False,
        "notification_lifecycle_authority": False,
        "persistence_authority": False,
        "broker_order_authority": False,
        "execution_authority": False,
    }
    return Wo17NotificationWorthyEventRecord(
        event_identity=_identity(
            "INTRADAY-WO17-NOTIFICATION-WORTHY-EVENT-", values
        ),
        event_integrity=_identity(
            "INTEGRITY-INTRADAY-WO17-NOTIFICATION-WORTHY-EVENT-", values
        ),
        **values,
    )


def _require_active_position(position: Wo17PositionMachine) -> None:
    if (
        type(position) is not Wo17PositionMachine
        or position.state
        not in {Wo17PositionState.PAPER_ACTIVE, Wo17PositionState.LIVE_ACTIVE}
        or position.position_evidence is None
    ):
        raise Wo17ClosureRejected(Wo17ClosureFailure.POSITION_NOT_ACTIVE)


def _machine_bindings_valid(machine: Wo17ClosureMachine) -> bool:
    position = machine.position.position_evidence
    if position is None:
        return False
    snapshot = machine.position.upstream_snapshot
    lineage = snapshot.lineage
    expected_event = (
        position.position_identity,
        position.position_integrity,
        snapshot.snapshot_identity,
        snapshot.snapshot_integrity,
        lineage.lineage_identity,
        lineage.lineage_integrity,
        lineage.canonical_subject_identity,
        lineage.instrument_identity,
        lineage.actual_contract_identity,
        lineage.roll_lineage_identity,
        lineage.session_identity,
        lineage.trading_date,
        lineage.direction,
    )
    if any(
        (
            item.position_identity,
            item.position_integrity,
            item.upstream_snapshot_identity,
            item.upstream_snapshot_integrity,
            item.upstream_lineage_identity,
            item.upstream_lineage_integrity,
            item.canonical_subject_identity,
            item.instrument_identity,
            item.actual_contract_identity,
            item.roll_lineage_identity,
            item.entry_session_identity,
            item.entry_trading_date,
            item.direction,
        )
        != expected_event
        for item in machine.events
    ):
        return False
    closure = machine.closure
    if closure is not None:
        expected_closure = (
            position.position_identity,
            position.position_integrity,
            snapshot.snapshot_identity,
            snapshot.snapshot_integrity,
            lineage.lineage_identity,
            lineage.lineage_integrity,
            position.decision,
            lineage.canonical_subject_identity,
            lineage.instrument_identity,
            lineage.actual_contract_identity,
            lineage.contract_expiry,
            lineage.roll_lineage_identity,
            lineage.session_identity,
            lineage.trading_date,
            lineage.direction,
            position.entry_price,
            position.entry_timestamp,
        )
        received_closure = (
            closure.position_identity,
            closure.position_integrity,
            closure.upstream_snapshot_identity,
            closure.upstream_snapshot_integrity,
            closure.upstream_lineage_identity,
            closure.upstream_lineage_integrity,
            closure.decision,
            closure.canonical_subject_identity,
            closure.instrument_identity,
            closure.actual_contract_identity,
            closure.contract_expiry,
            closure.roll_lineage_identity,
            closure.entry_session_identity,
            closure.entry_trading_date,
            closure.direction,
            closure.entry_price,
            closure.entry_timestamp,
        )
        closure_event = (
            Wo17NotificationWorthyEvent.PAPER_CLOSED
            if closure.closure_state is Wo17ClosureState.PAPER_CLOSED
            else Wo17NotificationWorthyEvent.LIVE_CLOSURE_ATTESTED
        )
        if received_closure != expected_closure or sum(
            item.event_type is closure_event
            and item.source_identity == closure.closure_identity
            and item.source_integrity == closure.closure_integrity
            for item in machine.events
        ) != 1:
            return False
    elif any(
        item.event_type
        in {
            Wo17NotificationWorthyEvent.PAPER_CLOSED,
            Wo17NotificationWorthyEvent.LIVE_CLOSURE_ATTESTED,
        }
        for item in machine.events
    ):
        return False
    transition_times = [
        machine.position.last_transition_at,
        *(item.recorded_at for item in machine.events),
    ]
    if closure is not None:
        transition_times.append(closure.closure_recorded_at)
    return machine.last_transition_at == max(transition_times)


def _require_machine(machine: Wo17ClosureMachine) -> None:
    if type(machine) is not Wo17ClosureMachine:
        raise Wo17ClosureRejected(Wo17ClosureFailure.SOURCE_CONTRACT_INVALID)
    _require_active_position(machine.position)


def _machine(**values: object) -> Wo17ClosureMachine:
    common = {
        **values,
        "policy_identity": WO17_POLICY_IDENTITY,
        "policy_version": WO17_POLICY_VERSION,
        "policy_checksum": WO17_POLICY_CHECKSUM,
        "schema_identity": WO17_CLOSURE_STATE_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "provider_acquisition_authority": False,
        "persistence_authority": False,
        "notification_delivery_authority": False,
        "journal_authority": False,
        "analytics_authority": False,
        "broker_order_authority": False,
        "execution_authority": False,
        "quantity": "UNAVAILABLE",
        "fees": "UNAVAILABLE",
        "monetary_pnl": "UNAVAILABLE",
        "realised_r": "UNAVAILABLE",
    }
    return Wo17ClosureMachine(
        state_identity=_identity("INTRADAY-WO17-CLOSURE-STATE-", common),
        state_integrity=_identity("INTEGRITY-INTRADAY-WO17-CLOSURE-STATE-", common),
        **common,  # type: ignore[arg-type]
    )


def _update(machine: Wo17ClosureMachine, **changes: object) -> Wo17ClosureMachine:
    values = {
        item.name: getattr(machine, item.name)
        for item in fields(machine)
        if item.name not in {"state_identity", "state_integrity"}
    }
    values.update(changes)
    return _machine(**values)


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_document_bytes(value)).hexdigest().upper()


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _decimal(value: object) -> bool:
    return type(value) is Decimal and value.is_finite()


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(value) for value in values)


__all__ = [
    name
    for name in globals()
    if name.startswith(
        (
            "WO17_",
            "Wo17",
            "create_",
            "close_",
            "record_",
            "reject_",
        )
    )
]
