"""WO-17 Slice 3 Provider-neutral lifecycle observation.

The engine accepts explicitly supplied facts for an existing active WO-17
position.  It neither acquires observations nor closes, persists, publishes,
or otherwise operates a position.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Sequence

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo17 import (
    WO17_CONTRACT_VERSION,
    WO17_POLICY_CHECKSUM,
    WO17_POLICY_IDENTITY,
    WO17_POLICY_VERSION,
    Wo17ContractError,
    canonical_document_bytes,
)
from kronos.intraday.wo17_position import (
    Wo17PositionMachine,
    Wo17PositionState,
)


WO17_LIFECYCLE_OBSERVATION_IDENTITY = (
    "KRONOS-INTRADAY-WO17-LIFECYCLE-OBSERVATION-V1"
)
WO17_LIFECYCLE_ASSESSMENT_IDENTITY = (
    "KRONOS-INTRADAY-WO17-LIFECYCLE-ASSESSMENT-V1"
)
WO17_SESSION_END_FACT_IDENTITY = "KRONOS-INTRADAY-WO17-SESSION-END-FACT-V1"
WO17_LIFECYCLE_STATE_IDENTITY = "KRONOS-INTRADAY-WO17-LIFECYCLE-STATE-V1"


class Wo17MonitoringAvailability(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    AVAILABLE = "AVAILABLE"
    INTERRUPTED = "INTERRUPTED"
    RECOVERING = "RECOVERING"
    SESSION_ENDED = "SESSION_ENDED"
    UNAVAILABLE = "UNAVAILABLE"


class Wo17LifecycleEvent(StrEnum):
    STOP_OBSERVED = "STOP_OBSERVED"
    TARGET_OBSERVED = "TARGET_OBSERVED"
    INVALIDATION_OBSERVED = "INVALIDATION_OBSERVED"
    LIFECYCLE_EVENT_ORDER_UNRESOLVED = "LIFECYCLE_EVENT_ORDER_UNRESOLVED"


class Wo17LifecycleAssessmentCode(StrEnum):
    BASELINE_ONLY = "BASELINE_ONLY"
    SEQUENCE_GAP_BASELINE_ONLY = "SEQUENCE_GAP_BASELINE_ONLY"
    NO_LIFECYCLE_EVENT = "NO_LIFECYCLE_EVENT"
    FACTUAL_LIFECYCLE_OBSERVATION = "FACTUAL_LIFECYCLE_OBSERVATION"


class Wo17LifecycleTransitionCode(StrEnum):
    OBSERVATION_ACCEPTED = "OBSERVATION_ACCEPTED"
    EXACT_REPLAY = "EXACT_REPLAY"
    MONITORING_INTERRUPTED = "MONITORING_INTERRUPTED"
    MONITORING_RECOVERED = "MONITORING_RECOVERED"
    SESSION_ENDED = "SESSION_ENDED"


class Wo17LifecycleFailure(StrEnum):
    SOURCE_CONTRACT_INVALID = "SOURCE_CONTRACT_INVALID"
    POSITION_NOT_ACTIVE = "POSITION_NOT_ACTIVE"
    POSITION_BINDING_MISMATCH = "POSITION_BINDING_MISMATCH"
    MONITORING_NOT_AVAILABLE = "MONITORING_NOT_AVAILABLE"
    CONTINUITY_TRANSITION_INVALID = "CONTINUITY_TRANSITION_INVALID"
    OBSERVATION_OLDER_THAN_CURRENT = "OBSERVATION_OLDER_THAN_CURRENT"
    OBSERVATION_EQUAL_TIME_CONFLICT = "OBSERVATION_EQUAL_TIME_CONFLICT"
    SOURCE_SEQUENCE_CONFLICT = "SOURCE_SEQUENCE_CONFLICT"
    DOMAIN_008_SESSION_MISMATCH = "DOMAIN_008_SESSION_MISMATCH"
    SESSION_NOT_ENDED = "SESSION_NOT_ENDED"
    SESSION_END_CONFLICT = "SESSION_END_CONFLICT"


class Wo17LifecycleRejected(Wo17ContractError):
    def __init__(self, failure: Wo17LifecycleFailure):
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class Wo17LifecycleObservation:
    observation_identity: str
    observation_integrity: str
    position_identity: str
    position_integrity: str
    upstream_snapshot_identity: str
    upstream_lineage_identity: str
    provider_identity: str
    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    trading_date: date
    direction: SemanticDirection
    observed_price: Decimal
    observed_low: Decimal
    observed_high: Decimal
    observed_at: datetime
    source_sequence_identity: str
    source_sequence: int
    provenance: tuple[str, ...]
    schema_identity: str = WO17_LIFECYCLE_OBSERVATION_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    provider_acquisition_authority: bool = False
    broker_order_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "observation_identity", "observation_integrity")
        if (
            not _texts(
                (
                    self.position_identity,
                    self.position_integrity,
                    self.upstream_snapshot_identity,
                    self.upstream_lineage_identity,
                    self.provider_identity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.session_identity,
                    self.source_sequence_identity,
                    *self.provenance,
                )
            )
            or type(self.trading_date) is not date
            or type(self.direction) is not SemanticDirection
            or not all(
                _decimal(value)
                for value in (
                    self.observed_price,
                    self.observed_low,
                    self.observed_high,
                )
            )
            or not self.observed_low <= self.observed_price <= self.observed_high
            or not _aware(self.observed_at)
            or type(self.source_sequence) is not int
            or self.source_sequence < 0
            or self.schema_identity != WO17_LIFECYCLE_OBSERVATION_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.provider_acquisition_authority
            or self.broker_order_authority
            or self.execution_authority
            or self.observation_identity
            != _identity("INTRADAY-WO17-LIFECYCLE-OBSERVATION-", values)
            or self.observation_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-LIFECYCLE-OBSERVATION-", values)
        ):
            raise Wo17ContractError("WO17_LIFECYCLE_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17LifecycleAssessment:
    assessment_identity: str
    assessment_integrity: str
    position_identity: str
    position_integrity: str
    observation_identity: str
    observation_integrity: str
    upstream_lineage_identity: str
    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    trading_date: date
    direction: SemanticDirection
    entry_reference: Decimal
    stop: Decimal
    canonical_target: Decimal
    thesis_invalidation_reference: Decimal
    thesis_invalidation_event: str
    assessment_code: Wo17LifecycleAssessmentCode
    observed_events: tuple[Wo17LifecycleEvent, ...]
    stop_observed: bool
    target_observed: bool
    invalidation_observed: bool
    ordering_unresolved: bool
    assessed_at: datetime
    source_sequence_identity: str
    source_sequence: int
    provenance: tuple[str, ...]
    schema_identity: str = WO17_LIFECYCLE_ASSESSMENT_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    position_state_changed: bool = False
    position_closed: bool = False
    closure_authority: bool = False
    broker_order_authority: bool = False
    execution_authority: bool = False
    quantity: str = "UNAVAILABLE"
    fees: str = "UNAVAILABLE"
    monetary_pnl: str = "UNAVAILABLE"
    realised_r: str = "UNAVAILABLE"

    def __post_init__(self) -> None:
        values = _without(self, "assessment_identity", "assessment_integrity")
        unavailable = (self.quantity, self.fees, self.monetary_pnl, self.realised_r)
        expected_events: tuple[Wo17LifecycleEvent, ...]
        if self.ordering_unresolved:
            expected_events = (
                Wo17LifecycleEvent.LIFECYCLE_EVENT_ORDER_UNRESOLVED,
            )
        else:
            event_items: list[Wo17LifecycleEvent] = []
            if self.stop_observed:
                event_items.append(Wo17LifecycleEvent.STOP_OBSERVED)
            if self.target_observed:
                event_items.append(Wo17LifecycleEvent.TARGET_OBSERVED)
            if self.invalidation_observed:
                event_items.append(Wo17LifecycleEvent.INVALIDATION_OBSERVED)
            expected_events = tuple(event_items)
        if (
            not _texts(
                (
                    self.position_identity,
                    self.position_integrity,
                    self.observation_identity,
                    self.observation_integrity,
                    self.upstream_lineage_identity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.session_identity,
                    self.thesis_invalidation_event,
                    self.source_sequence_identity,
                    *self.provenance,
                )
            )
            or type(self.trading_date) is not date
            or type(self.direction) is not SemanticDirection
            or not all(
                _decimal(value)
                for value in (
                    self.entry_reference,
                    self.stop,
                    self.canonical_target,
                    self.thesis_invalidation_reference,
                )
            )
            or type(self.assessment_code) is not Wo17LifecycleAssessmentCode
            or any(type(item) is not Wo17LifecycleEvent for item in self.observed_events)
            or len(set(self.observed_events)) != len(self.observed_events)
            or not _aware(self.assessed_at)
            or type(self.source_sequence) is not int
            or self.ordering_unresolved
            != (Wo17LifecycleEvent.LIFECYCLE_EVENT_ORDER_UNRESOLVED in self.observed_events)
            or (self.ordering_unresolved and (self.stop_observed is not True or self.target_observed is not True))
            or self.observed_events != expected_events
            or (
                self.assessment_code
                in {
                    Wo17LifecycleAssessmentCode.BASELINE_ONLY,
                    Wo17LifecycleAssessmentCode.SEQUENCE_GAP_BASELINE_ONLY,
                    Wo17LifecycleAssessmentCode.NO_LIFECYCLE_EVENT,
                }
                and bool(self.observed_events)
            )
            or (
                self.assessment_code
                is Wo17LifecycleAssessmentCode.FACTUAL_LIFECYCLE_OBSERVATION
                and not self.observed_events
            )
            or any(value != "UNAVAILABLE" for value in unavailable)
            or self.schema_identity != WO17_LIFECYCLE_ASSESSMENT_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.position_state_changed
            or self.position_closed
            or self.closure_authority
            or self.broker_order_authority
            or self.execution_authority
            or self.assessment_identity
            != _identity("INTRADAY-WO17-LIFECYCLE-ASSESSMENT-", values)
            or self.assessment_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-LIFECYCLE-ASSESSMENT-", values)
        ):
            raise Wo17ContractError("WO17_LIFECYCLE_ASSESSMENT_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17SessionEndFact:
    fact_identity: str
    fact_integrity: str
    position_identity: str
    position_integrity: str
    upstream_lineage_identity: str
    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    calendar_identity: str
    calendar_version: str
    trading_date: date
    session_closes_at: datetime
    observed_at: datetime
    source_fact_identity: str
    provenance: tuple[str, ...]
    schema_identity: str = WO17_SESSION_END_FACT_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    force_close: bool = False
    overnight_carry_authority: bool = False
    automatic_reactivation_authority: bool = False
    automatic_contract_migration_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "fact_identity", "fact_integrity")
        if (
            not _texts(
                (
                    self.position_identity,
                    self.position_integrity,
                    self.upstream_lineage_identity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.session_identity,
                    self.calendar_identity,
                    self.calendar_version,
                    self.source_fact_identity,
                    *self.provenance,
                )
            )
            or type(self.trading_date) is not date
            or not _aware(self.session_closes_at)
            or not _aware(self.observed_at)
            or self.observed_at < self.session_closes_at
            or self.schema_identity != WO17_SESSION_END_FACT_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.force_close
            or self.overnight_carry_authority
            or self.automatic_reactivation_authority
            or self.automatic_contract_migration_authority
            or self.fact_identity != _identity("INTRADAY-WO17-SESSION-END-", values)
            or self.fact_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-SESSION-END-", values)
        ):
            raise Wo17ContractError("WO17_SESSION_END_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17LifecycleMachine:
    state_identity: str
    state_integrity: str
    position: Wo17PositionMachine
    position_state: Wo17PositionState
    monitoring_availability: Wo17MonitoringAvailability
    baseline: Wo17LifecycleObservation | None
    observations: tuple[Wo17LifecycleObservation, ...]
    assessments: tuple[Wo17LifecycleAssessment, ...]
    session_end_fact: Wo17SessionEndFact | None
    last_transition_at: datetime
    policy_identity: str = WO17_POLICY_IDENTITY
    policy_version: str = WO17_POLICY_VERSION
    policy_checksum: str = WO17_POLICY_CHECKSUM
    schema_identity: str = WO17_LIFECYCLE_STATE_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    position_creation_authority: bool = False
    position_closure_authority: bool = False
    provider_acquisition_authority: bool = False
    persistence_authority: bool = False
    notification_publication_authority: bool = False
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
            or self.position_state is not self.position.state
            or type(self.monitoring_availability) is not Wo17MonitoringAvailability
            or any(type(item) is not Wo17LifecycleObservation for item in self.observations)
            or any(type(item) is not Wo17LifecycleAssessment for item in self.assessments)
            or not _aware(self.last_transition_at)
            or (
                self.monitoring_availability is Wo17MonitoringAvailability.SESSION_ENDED
            )
            != (self.session_end_fact is not None)
            or self.policy_identity != WO17_POLICY_IDENTITY
            or self.policy_version != WO17_POLICY_VERSION
            or self.policy_checksum != WO17_POLICY_CHECKSUM
            or self.schema_identity != WO17_LIFECYCLE_STATE_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or any(
                (
                    self.position_creation_authority,
                    self.position_closure_authority,
                    self.provider_acquisition_authority,
                    self.persistence_authority,
                    self.notification_publication_authority,
                    self.broker_order_authority,
                    self.execution_authority,
                )
            )
            or any(value != "UNAVAILABLE" for value in unavailable)
            or self.state_identity != _identity("INTRADAY-WO17-LIFECYCLE-STATE-", values)
            or self.state_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-LIFECYCLE-STATE-", values)
        ):
            raise Wo17ContractError("WO17_LIFECYCLE_STATE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17LifecycleTransition:
    previous_state_identity: str
    current: Wo17LifecycleMachine
    transition_code: Wo17LifecycleTransitionCode
    assessment: Wo17LifecycleAssessment | None
    applied: bool
    replayed: bool = False


def create_wo17_lifecycle_machine(
    position: Wo17PositionMachine,
    *,
    monitoring_availability: Wo17MonitoringAvailability = (
        Wo17MonitoringAvailability.AVAILABLE
    ),
) -> Wo17LifecycleMachine:
    if (
        type(position) is not Wo17PositionMachine
        or position.state
        not in {Wo17PositionState.PAPER_ACTIVE, Wo17PositionState.LIVE_ACTIVE}
        or position.position_evidence is None
    ):
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.POSITION_NOT_ACTIVE)
    if type(monitoring_availability) is not Wo17MonitoringAvailability:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.SOURCE_CONTRACT_INVALID)
    if monitoring_availability not in {
        Wo17MonitoringAvailability.AVAILABLE,
        Wo17MonitoringAvailability.NOT_APPLICABLE,
        Wo17MonitoringAvailability.UNAVAILABLE,
    }:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.SOURCE_CONTRACT_INVALID)
    return _machine(
        position=position,
        position_state=position.state,
        monitoring_availability=monitoring_availability,
        baseline=None,
        observations=(),
        assessments=(),
        session_end_fact=None,
        last_transition_at=position.last_transition_at,
    )


def create_wo17_lifecycle_observation(
    *,
    machine: Wo17LifecycleMachine,
    provider_identity: str,
    observed_price: Decimal,
    observed_at: datetime,
    source_sequence_identity: str,
    source_sequence: int,
    provenance: tuple[str, ...],
    observed_low: Decimal | None = None,
    observed_high: Decimal | None = None,
) -> Wo17LifecycleObservation:
    position = machine.position.position_evidence
    if position is None:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.POSITION_NOT_ACTIVE)
    lineage = machine.position.upstream_snapshot.lineage
    values = {
        "position_identity": position.position_identity,
        "position_integrity": position.position_integrity,
        "upstream_snapshot_identity": machine.position.upstream_snapshot.snapshot_identity,
        "upstream_lineage_identity": lineage.lineage_identity,
        "provider_identity": provider_identity,
        "canonical_subject_identity": lineage.canonical_subject_identity,
        "instrument_identity": lineage.instrument_identity,
        "actual_contract_identity": lineage.actual_contract_identity,
        "roll_lineage_identity": lineage.roll_lineage_identity,
        "session_identity": lineage.session_identity,
        "trading_date": lineage.trading_date,
        "direction": lineage.direction,
        "observed_price": observed_price,
        "observed_low": observed_price if observed_low is None else observed_low,
        "observed_high": observed_price if observed_high is None else observed_high,
        "observed_at": observed_at,
        "source_sequence_identity": source_sequence_identity,
        "source_sequence": source_sequence,
        "provenance": provenance,
        "schema_identity": WO17_LIFECYCLE_OBSERVATION_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "provider_acquisition_authority": False,
        "broker_order_authority": False,
        "execution_authority": False,
    }
    return Wo17LifecycleObservation(
        observation_identity=_identity("INTRADAY-WO17-LIFECYCLE-OBSERVATION-", values),
        observation_integrity=_identity(
            "INTEGRITY-INTRADAY-WO17-LIFECYCLE-OBSERVATION-", values
        ),
        **values,
    )


def observe_wo17_lifecycle(
    machine: Wo17LifecycleMachine,
    observation: Wo17LifecycleObservation,
) -> Wo17LifecycleTransition:
    _require_machine(machine)
    _require_observation_binding(machine, observation)
    if _exact_replay(machine, observation):
        return Wo17LifecycleTransition(
            machine.state_identity,
            machine,
            Wo17LifecycleTransitionCode.EXACT_REPLAY,
            None,
            False,
            True,
        )
    if machine.monitoring_availability not in {
        Wo17MonitoringAvailability.AVAILABLE,
        Wo17MonitoringAvailability.RECOVERING,
    }:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.MONITORING_NOT_AVAILABLE)
    _require_observation_time(machine, observation)
    previous = machine.observations[-1] if machine.observations else None
    if previous is not None:
        if observation.observed_at < previous.observed_at:
            raise Wo17LifecycleRejected(
                Wo17LifecycleFailure.OBSERVATION_OLDER_THAN_CURRENT
            )
        if observation.observed_at == previous.observed_at:
            raise Wo17LifecycleRejected(
                Wo17LifecycleFailure.OBSERVATION_EQUAL_TIME_CONFLICT
            )
        if observation.source_sequence < previous.source_sequence:
            raise Wo17LifecycleRejected(
                Wo17LifecycleFailure.OBSERVATION_OLDER_THAN_CURRENT
            )

    history = (*machine.observations, observation)
    baseline = machine.baseline
    if baseline is None:
        assessment = _assessment(
            machine,
            observation,
            Wo17LifecycleAssessmentCode.BASELINE_ONLY,
            (),
            stop_observed=False,
            target_observed=False,
            invalidation_observed=False,
            ordering_unresolved=False,
        )
        current = _update(
            machine,
            monitoring_availability=Wo17MonitoringAvailability.AVAILABLE,
            baseline=observation,
            observations=history,
            assessments=(*machine.assessments, assessment),
            last_transition_at=observation.observed_at,
        )
        return _accepted(machine, current, assessment)

    if observation.source_sequence != baseline.source_sequence + 1:
        stop, target, invalidation = _contacts(machine, observation)
        unresolved = stop and target
        events = (
            (Wo17LifecycleEvent.LIFECYCLE_EVENT_ORDER_UNRESOLVED,)
            if unresolved
            else ()
        )
        assessment = _assessment(
            machine,
            observation,
            (
                Wo17LifecycleAssessmentCode.FACTUAL_LIFECYCLE_OBSERVATION
                if unresolved
                else Wo17LifecycleAssessmentCode.SEQUENCE_GAP_BASELINE_ONLY
            ),
            events,
            stop_observed=stop if unresolved else False,
            target_observed=target if unresolved else False,
            invalidation_observed=invalidation if unresolved else False,
            ordering_unresolved=unresolved,
        )
        current = _update(
            machine,
            baseline=observation,
            observations=history,
            assessments=(*machine.assessments, assessment),
            last_transition_at=observation.observed_at,
        )
        return _accepted(machine, current, assessment)

    stop, target, invalidation = _contacts(machine, observation)
    unresolved = stop and target
    events: tuple[Wo17LifecycleEvent, ...]
    if unresolved:
        events = (Wo17LifecycleEvent.LIFECYCLE_EVENT_ORDER_UNRESOLVED,)
    else:
        event_items: list[Wo17LifecycleEvent] = []
        if stop:
            event_items.append(Wo17LifecycleEvent.STOP_OBSERVED)
        if target:
            event_items.append(Wo17LifecycleEvent.TARGET_OBSERVED)
        if invalidation:
            event_items.append(Wo17LifecycleEvent.INVALIDATION_OBSERVED)
        events = tuple(event_items)
    assessment = _assessment(
        machine,
        observation,
        (
            Wo17LifecycleAssessmentCode.FACTUAL_LIFECYCLE_OBSERVATION
            if events
            else Wo17LifecycleAssessmentCode.NO_LIFECYCLE_EVENT
        ),
        events,
        stop_observed=stop,
        target_observed=target,
        invalidation_observed=invalidation,
        ordering_unresolved=unresolved,
    )
    current = _update(
        machine,
        baseline=observation,
        observations=history,
        assessments=(*machine.assessments, assessment),
        last_transition_at=observation.observed_at,
    )
    return _accepted(machine, current, assessment)


def interrupt_wo17_lifecycle(
    machine: Wo17LifecycleMachine,
    *,
    occurred_at: datetime,
) -> Wo17LifecycleTransition:
    _require_machine(machine)
    if machine.monitoring_availability not in {
        Wo17MonitoringAvailability.AVAILABLE,
        Wo17MonitoringAvailability.RECOVERING,
    }:
        raise Wo17LifecycleRejected(
            Wo17LifecycleFailure.CONTINUITY_TRANSITION_INVALID
        )
    _require_transition_time(machine, occurred_at, within_session=True)
    current = _update(
        machine,
        monitoring_availability=Wo17MonitoringAvailability.INTERRUPTED,
        baseline=None,
        last_transition_at=occurred_at,
    )
    return Wo17LifecycleTransition(
        machine.state_identity,
        current,
        Wo17LifecycleTransitionCode.MONITORING_INTERRUPTED,
        None,
        True,
    )


def recover_wo17_lifecycle(
    machine: Wo17LifecycleMachine,
    *,
    recovered_at: datetime,
) -> Wo17LifecycleTransition:
    _require_machine(machine)
    if machine.monitoring_availability is not Wo17MonitoringAvailability.INTERRUPTED:
        raise Wo17LifecycleRejected(
            Wo17LifecycleFailure.CONTINUITY_TRANSITION_INVALID
        )
    _require_transition_time(machine, recovered_at, within_session=True)
    current = _update(
        machine,
        monitoring_availability=Wo17MonitoringAvailability.RECOVERING,
        baseline=None,
        last_transition_at=recovered_at,
    )
    return Wo17LifecycleTransition(
        machine.state_identity,
        current,
        Wo17LifecycleTransitionCode.MONITORING_RECOVERED,
        None,
        True,
    )


def create_wo17_session_end_fact(
    *,
    machine: Wo17LifecycleMachine,
    observed_at: datetime,
    source_fact_identity: str,
    provenance: tuple[str, ...],
) -> Wo17SessionEndFact:
    position = machine.position.position_evidence
    if position is None:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.POSITION_NOT_ACTIVE)
    lineage = machine.position.upstream_snapshot.lineage
    values = {
        "position_identity": position.position_identity,
        "position_integrity": position.position_integrity,
        "upstream_lineage_identity": lineage.lineage_identity,
        "canonical_subject_identity": lineage.canonical_subject_identity,
        "instrument_identity": lineage.instrument_identity,
        "actual_contract_identity": lineage.actual_contract_identity,
        "roll_lineage_identity": lineage.roll_lineage_identity,
        "session_identity": lineage.session_identity,
        "calendar_identity": lineage.calendar_identity,
        "calendar_version": lineage.calendar_version,
        "trading_date": lineage.trading_date,
        "session_closes_at": lineage.active_window_closes_at,
        "observed_at": observed_at,
        "source_fact_identity": source_fact_identity,
        "provenance": provenance,
        "schema_identity": WO17_SESSION_END_FACT_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "force_close": False,
        "overnight_carry_authority": False,
        "automatic_reactivation_authority": False,
        "automatic_contract_migration_authority": False,
    }
    return Wo17SessionEndFact(
        fact_identity=_identity("INTRADAY-WO17-SESSION-END-", values),
        fact_integrity=_identity("INTEGRITY-INTRADAY-WO17-SESSION-END-", values),
        **values,
    )


def end_wo17_lifecycle_session(
    machine: Wo17LifecycleMachine,
    fact: Wo17SessionEndFact,
) -> Wo17LifecycleTransition:
    _require_machine(machine)
    if machine.session_end_fact == fact:
        return Wo17LifecycleTransition(
            machine.state_identity,
            machine,
            Wo17LifecycleTransitionCode.EXACT_REPLAY,
            None,
            False,
            True,
        )
    if machine.session_end_fact is not None:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.SESSION_END_CONFLICT)
    _require_session_end_binding(machine, fact)
    if fact.observed_at < machine.position.upstream_snapshot.lineage.active_window_closes_at:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.SESSION_NOT_ENDED)
    current = _update(
        machine,
        monitoring_availability=Wo17MonitoringAvailability.SESSION_ENDED,
        baseline=None,
        session_end_fact=fact,
        last_transition_at=fact.observed_at,
    )
    return Wo17LifecycleTransition(
        machine.state_identity,
        current,
        Wo17LifecycleTransitionCode.SESSION_ENDED,
        None,
        True,
    )


def _contacts(
    machine: Wo17LifecycleMachine,
    observation: Wo17LifecycleObservation,
) -> tuple[bool, bool, bool]:
    lineage = machine.position.upstream_snapshot.lineage
    if lineage.direction is SemanticDirection.LONG:
        return (
            observation.observed_low <= lineage.stop,
            observation.observed_high >= lineage.canonical_target,
            observation.observed_low <= lineage.thesis_invalidation_reference,
        )
    return (
        observation.observed_high >= lineage.stop,
        observation.observed_low <= lineage.canonical_target,
        observation.observed_high >= lineage.thesis_invalidation_reference,
    )


def _assessment(
    machine: Wo17LifecycleMachine,
    observation: Wo17LifecycleObservation,
    code: Wo17LifecycleAssessmentCode,
    events: tuple[Wo17LifecycleEvent, ...],
    *,
    stop_observed: bool,
    target_observed: bool,
    invalidation_observed: bool,
    ordering_unresolved: bool,
) -> Wo17LifecycleAssessment:
    position = machine.position.position_evidence
    if position is None:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.POSITION_NOT_ACTIVE)
    lineage = machine.position.upstream_snapshot.lineage
    values = {
        "position_identity": position.position_identity,
        "position_integrity": position.position_integrity,
        "observation_identity": observation.observation_identity,
        "observation_integrity": observation.observation_integrity,
        "upstream_lineage_identity": lineage.lineage_identity,
        "canonical_subject_identity": lineage.canonical_subject_identity,
        "instrument_identity": lineage.instrument_identity,
        "actual_contract_identity": lineage.actual_contract_identity,
        "roll_lineage_identity": lineage.roll_lineage_identity,
        "session_identity": lineage.session_identity,
        "trading_date": lineage.trading_date,
        "direction": lineage.direction,
        "entry_reference": lineage.entry_reference,
        "stop": lineage.stop,
        "canonical_target": lineage.canonical_target,
        "thesis_invalidation_reference": lineage.thesis_invalidation_reference,
        "thesis_invalidation_event": lineage.thesis_invalidation_event,
        "assessment_code": code,
        "observed_events": events,
        "stop_observed": stop_observed,
        "target_observed": target_observed,
        "invalidation_observed": invalidation_observed,
        "ordering_unresolved": ordering_unresolved,
        "assessed_at": observation.observed_at,
        "source_sequence_identity": observation.source_sequence_identity,
        "source_sequence": observation.source_sequence,
        "provenance": (observation.observation_identity, "ADR-0027", "WO-17-SLICE-3"),
        "schema_identity": WO17_LIFECYCLE_ASSESSMENT_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "position_state_changed": False,
        "position_closed": False,
        "closure_authority": False,
        "broker_order_authority": False,
        "execution_authority": False,
        "quantity": "UNAVAILABLE",
        "fees": "UNAVAILABLE",
        "monetary_pnl": "UNAVAILABLE",
        "realised_r": "UNAVAILABLE",
    }
    return Wo17LifecycleAssessment(
        assessment_identity=_identity("INTRADAY-WO17-LIFECYCLE-ASSESSMENT-", values),
        assessment_integrity=_identity(
            "INTEGRITY-INTRADAY-WO17-LIFECYCLE-ASSESSMENT-", values
        ),
        **values,
    )


def _accepted(
    previous: Wo17LifecycleMachine,
    current: Wo17LifecycleMachine,
    assessment: Wo17LifecycleAssessment,
) -> Wo17LifecycleTransition:
    return Wo17LifecycleTransition(
        previous.state_identity,
        current,
        Wo17LifecycleTransitionCode.OBSERVATION_ACCEPTED,
        assessment,
        True,
    )


def _exact_replay(
    machine: Wo17LifecycleMachine,
    observation: Wo17LifecycleObservation,
) -> bool:
    for existing in machine.observations:
        if existing.observation_identity == observation.observation_identity:
            if existing == observation:
                return True
            raise Wo17LifecycleRejected(Wo17LifecycleFailure.SOURCE_SEQUENCE_CONFLICT)
        if existing.source_sequence_identity == observation.source_sequence_identity:
            if canonical_document_bytes(existing) == canonical_document_bytes(observation):
                return True
            raise Wo17LifecycleRejected(Wo17LifecycleFailure.SOURCE_SEQUENCE_CONFLICT)
        if existing.source_sequence == observation.source_sequence:
            raise Wo17LifecycleRejected(Wo17LifecycleFailure.SOURCE_SEQUENCE_CONFLICT)
        if existing.observed_at == observation.observed_at:
            raise Wo17LifecycleRejected(
                Wo17LifecycleFailure.OBSERVATION_EQUAL_TIME_CONFLICT
            )
    position = machine.position.position_evidence
    if position is not None and position.source_sequence_identity is not None:
        if (
            observation.source_sequence_identity == position.source_sequence_identity
            or observation.source_sequence == position.source_sequence
        ):
            raise Wo17LifecycleRejected(Wo17LifecycleFailure.SOURCE_SEQUENCE_CONFLICT)
    return False


def _require_observation_binding(
    machine: Wo17LifecycleMachine,
    observation: Wo17LifecycleObservation,
) -> None:
    position = machine.position.position_evidence
    if position is None:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.POSITION_NOT_ACTIVE)
    lineage = machine.position.upstream_snapshot.lineage
    expected = (
        position.position_identity,
        position.position_integrity,
        machine.position.upstream_snapshot.snapshot_identity,
        lineage.lineage_identity,
        lineage.canonical_subject_identity,
        lineage.instrument_identity,
        lineage.actual_contract_identity,
        lineage.roll_lineage_identity,
        lineage.session_identity,
        lineage.trading_date,
        lineage.direction,
    )
    received = (
        observation.position_identity,
        observation.position_integrity,
        observation.upstream_snapshot_identity,
        observation.upstream_lineage_identity,
        observation.canonical_subject_identity,
        observation.instrument_identity,
        observation.actual_contract_identity,
        observation.roll_lineage_identity,
        observation.session_identity,
        observation.trading_date,
        observation.direction,
    )
    if received != expected:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.POSITION_BINDING_MISMATCH)


def _require_observation_time(
    machine: Wo17LifecycleMachine,
    observation: Wo17LifecycleObservation,
) -> None:
    lineage = machine.position.upstream_snapshot.lineage
    position = machine.position.position_evidence
    if position is None:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.POSITION_NOT_ACTIVE)
    if (
        observation.observed_at <= machine.last_transition_at
        or observation.observed_at <= position.evidence_recorded_at
    ):
        raise Wo17LifecycleRejected(
            Wo17LifecycleFailure.OBSERVATION_OLDER_THAN_CURRENT
        )
    if (
        observation.observed_at < lineage.active_window_opens_at
        or observation.observed_at >= lineage.active_window_closes_at
        or observation.observed_at.astimezone(
            lineage.active_window_opens_at.tzinfo
        ).date()
        != lineage.trading_date
    ):
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.DOMAIN_008_SESSION_MISMATCH)


def _require_transition_time(
    machine: Wo17LifecycleMachine,
    value: datetime,
    *,
    within_session: bool,
) -> None:
    if not _aware(value):
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.SOURCE_CONTRACT_INVALID)
    if value <= machine.last_transition_at:
        raise Wo17LifecycleRejected(
            Wo17LifecycleFailure.OBSERVATION_OLDER_THAN_CURRENT
        )
    if within_session:
        lineage = machine.position.upstream_snapshot.lineage
        if value < lineage.active_window_opens_at or value >= lineage.active_window_closes_at:
            raise Wo17LifecycleRejected(
                Wo17LifecycleFailure.DOMAIN_008_SESSION_MISMATCH
            )


def _require_session_end_binding(
    machine: Wo17LifecycleMachine,
    fact: Wo17SessionEndFact,
) -> None:
    position = machine.position.position_evidence
    if position is None:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.POSITION_NOT_ACTIVE)
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
        lineage.calendar_identity,
        lineage.calendar_version,
        lineage.trading_date,
        lineage.active_window_closes_at,
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
        fact.calendar_identity,
        fact.calendar_version,
        fact.trading_date,
        fact.session_closes_at,
    )
    if received != expected:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.POSITION_BINDING_MISMATCH)


def _require_machine(machine: Wo17LifecycleMachine) -> None:
    if type(machine) is not Wo17LifecycleMachine:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.SOURCE_CONTRACT_INVALID)
    if machine.position.state not in {
        Wo17PositionState.PAPER_ACTIVE,
        Wo17PositionState.LIVE_ACTIVE,
    }:
        raise Wo17LifecycleRejected(Wo17LifecycleFailure.POSITION_NOT_ACTIVE)


def _machine(**values: object) -> Wo17LifecycleMachine:
    common = {
        **values,
        "policy_identity": WO17_POLICY_IDENTITY,
        "policy_version": WO17_POLICY_VERSION,
        "policy_checksum": WO17_POLICY_CHECKSUM,
        "schema_identity": WO17_LIFECYCLE_STATE_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "position_creation_authority": False,
        "position_closure_authority": False,
        "provider_acquisition_authority": False,
        "persistence_authority": False,
        "notification_publication_authority": False,
        "broker_order_authority": False,
        "execution_authority": False,
        "quantity": "UNAVAILABLE",
        "fees": "UNAVAILABLE",
        "monetary_pnl": "UNAVAILABLE",
        "realised_r": "UNAVAILABLE",
    }
    return Wo17LifecycleMachine(
        state_identity=_identity("INTRADAY-WO17-LIFECYCLE-STATE-", common),
        state_integrity=_identity("INTEGRITY-INTRADAY-WO17-LIFECYCLE-STATE-", common),
        **common,  # type: ignore[arg-type]
    )


def _update(machine: Wo17LifecycleMachine, **changes: object) -> Wo17LifecycleMachine:
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
            "observe_",
            "interrupt_",
            "recover_",
            "end_",
        )
    )
]
