"""WO-17 Slice 2 immutable PAPER/LIVE position-evidence state machine.

This module consumes already-bound Slice 1 upstream snapshots.  It performs no
market-data acquisition, persistence, restoration, monitoring after entry, or
broker operation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Sequence
from zoneinfo import ZoneInfo

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo16 import Wo16SponsorDecision
from kronos.intraday.wo17 import (
    WO17_CONTRACT_VERSION,
    WO17_POLICY_CHECKSUM,
    WO17_POLICY_IDENTITY,
    WO17_POLICY_VERSION,
    Wo17ContractError,
    Wo17UpstreamSnapshot,
    canonical_document_bytes,
)


WO17_ENTRY_OBSERVATION_IDENTITY = "KRONOS-INTRADAY-WO17-ENTRY-OBSERVATION-V1"
WO17_LIVE_ATTESTATION_IDENTITY = "KRONOS-INTRADAY-WO17-LIVE-ENTRY-ATTESTATION-V1"
WO17_PRE_ENTRY_INVALIDATION_IDENTITY = (
    "KRONOS-INTRADAY-WO17-PRE-ENTRY-INVALIDATION-FACT-V1"
)
WO17_POSITION_EVIDENCE_IDENTITY = "KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-V1"
WO17_POSITION_STATE_IDENTITY = "KRONOS-INTRADAY-WO17-POSITION-STATE-V1"

_IST = ZoneInfo("Asia/Kolkata")
_NSE_CUTOFF = time(15, 0)
_MCX_CUTOFF = time(23, 0)


class Wo17PositionState(StrEnum):
    PAPER_ARMED = "PAPER_ARMED"
    PAPER_ACTIVE = "PAPER_ACTIVE"
    LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE = "LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE"
    LIVE_ACTIVE = "LIVE_ACTIVE"
    ENTRY_INVALIDATED_BEFORE_POSITION = "ENTRY_INVALIDATED_BEFORE_POSITION"
    ENTRY_WINDOW_EXPIRED = "ENTRY_WINDOW_EXPIRED"


class Wo17PositionEvent(StrEnum):
    PAPER_BASELINE_OBSERVED = "PAPER_BASELINE_OBSERVED"
    PAPER_ENTRY_OBSERVED = "PAPER_ENTRY_OBSERVED"
    LIVE_ENTRY_ATTESTED = "LIVE_ENTRY_ATTESTED"
    ENTRY_SEQUENCE_UNRESOLVED = "ENTRY_SEQUENCE_UNRESOLVED"
    MONITORING_INTERRUPTED = "MONITORING_INTERRUPTED"
    MONITORING_RECOVERED = "MONITORING_RECOVERED"
    ENTRY_INVALIDATED_BEFORE_POSITION = "ENTRY_INVALIDATED_BEFORE_POSITION"
    ENTRY_WINDOW_EXPIRED = "ENTRY_WINDOW_EXPIRED"
    EXACT_REPLAY = "EXACT_REPLAY"


class Wo17EntryContinuity(StrEnum):
    AVAILABLE = "AVAILABLE"
    INTERRUPTED = "INTERRUPTED"
    RECOVERING = "RECOVERING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Wo17PositionFailure(StrEnum):
    SOURCE_CONTRACT_INVALID = "SOURCE_CONTRACT_INVALID"
    UPSTREAM_LINEAGE_MISMATCH = "UPSTREAM_LINEAGE_MISMATCH"
    POSITION_MODE_MISMATCH = "POSITION_MODE_MISMATCH"
    POSITION_STATE_TERMINAL = "POSITION_STATE_TERMINAL"
    POSITION_ALREADY_ACTIVE = "POSITION_ALREADY_ACTIVE"
    ENTRY_CUTOFF_REACHED = "ENTRY_CUTOFF_REACHED"
    DOMAIN_008_SESSION_MISMATCH = "DOMAIN_008_SESSION_MISMATCH"
    OBSERVATION_OLDER_THAN_CURRENT = "OBSERVATION_OLDER_THAN_CURRENT"
    OBSERVATION_EQUAL_TIME_CONFLICT = "OBSERVATION_EQUAL_TIME_CONFLICT"
    SOURCE_SEQUENCE_CONFLICT = "SOURCE_SEQUENCE_CONFLICT"
    EXISTING_NON_CLOSED_POSITION = "EXISTING_NON_CLOSED_POSITION"
    CONTINUITY_TRANSITION_INVALID = "CONTINUITY_TRANSITION_INVALID"
    INVALIDATION_FACT_MISMATCH = "INVALIDATION_FACT_MISMATCH"
    ENTRY_WINDOW_NOT_EXPIRED = "ENTRY_WINDOW_NOT_EXPIRED"


class Wo17PositionRejected(Wo17ContractError):
    def __init__(self, failure: Wo17PositionFailure):
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class Wo17EntryObservation:
    observation_identity: str
    observation_integrity: str
    upstream_snapshot_identity: str
    upstream_snapshot_integrity: str
    upstream_lineage_identity: str
    upstream_lineage_integrity: str
    provider_identity: str
    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    trading_date: date
    direction: SemanticDirection
    observed_price: Decimal
    observed_at: datetime
    source_sequence_identity: str
    source_sequence: int
    provenance: tuple[str, ...]
    schema_identity: str = WO17_ENTRY_OBSERVATION_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    broker_order_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "observation_identity", "observation_integrity")
        if (
            not _texts(
                (
                    self.upstream_snapshot_identity,
                    self.upstream_snapshot_integrity,
                    self.upstream_lineage_identity,
                    self.upstream_lineage_integrity,
                    self.provider_identity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.session_identity,
                    self.source_sequence_identity,
                    *self.provenance,
                )
            )
            or type(self.direction) is not SemanticDirection
            or type(self.trading_date) is not date
            or not _decimal(self.observed_price)
            or not _aware(self.observed_at)
            or type(self.source_sequence) is not int
            or self.source_sequence < 0
            or self.schema_identity != WO17_ENTRY_OBSERVATION_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.broker_order_authority
            or self.execution_authority
            or self.observation_identity != _identity("INTRADAY-WO17-OBSERVATION-", values)
            or self.observation_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-OBSERVATION-", values)
        ):
            raise Wo17ContractError("WO17_ENTRY_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17LiveEntryAttestation:
    attestation_identity: str
    attestation_integrity: str
    upstream_snapshot_identity: str
    upstream_snapshot_integrity: str
    upstream_lineage_identity: str
    upstream_lineage_integrity: str
    wo16_decision_identity: str
    wo16_admission_identity: str
    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    trading_date: date
    direction: SemanticDirection
    actual_entry_price: Decimal
    actual_entry_timestamp: datetime
    attestation_operation_timestamp: datetime
    sponsor_operation_identity: str
    bounded_manual_action_provenance: tuple[str, ...]
    schema_identity: str = WO17_LIVE_ATTESTATION_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    broker_acknowledgement: bool = False
    broker_fill_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "attestation_identity", "attestation_integrity")
        if (
            not _texts(
                (
                    self.upstream_snapshot_identity,
                    self.upstream_snapshot_integrity,
                    self.upstream_lineage_identity,
                    self.upstream_lineage_integrity,
                    self.wo16_decision_identity,
                    self.wo16_admission_identity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.session_identity,
                    self.sponsor_operation_identity,
                    *self.bounded_manual_action_provenance,
                )
            )
            or type(self.direction) is not SemanticDirection
            or type(self.trading_date) is not date
            or not _decimal(self.actual_entry_price)
            or not _aware(self.actual_entry_timestamp)
            or not _aware(self.attestation_operation_timestamp)
            or self.schema_identity != WO17_LIVE_ATTESTATION_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.broker_acknowledgement
            or self.broker_fill_authority
            or self.execution_authority
            or self.attestation_identity != _identity("INTRADAY-WO17-ATTESTATION-", values)
            or self.attestation_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-ATTESTATION-", values)
        ):
            raise Wo17ContractError("WO17_LIVE_ENTRY_ATTESTATION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17PreEntryInvalidationFact:
    fact_identity: str
    fact_integrity: str
    upstream_snapshot_identity: str
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
    thesis_invalidation_reference: Decimal
    thesis_invalidation_event: str
    observed_at: datetime
    source_evidence_identity: str
    provenance: tuple[str, ...]
    schema_identity: str = WO17_PRE_ENTRY_INVALIDATION_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "fact_identity", "fact_integrity")
        if (
            not _texts(
                (
                    self.upstream_snapshot_identity,
                    self.upstream_lineage_identity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.session_identity,
                    self.thesis_invalidation_event,
                    self.source_evidence_identity,
                    *self.provenance,
                )
            )
            or type(self.direction) is not SemanticDirection
            or type(self.trading_date) is not date
            or not all(
                _decimal(value)
                for value in (
                    self.entry_reference,
                    self.stop,
                    self.thesis_invalidation_reference,
                )
            )
            or not _aware(self.observed_at)
            or self.schema_identity != WO17_PRE_ENTRY_INVALIDATION_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.fact_identity != _identity("INTRADAY-WO17-INVALIDATION-", values)
            or self.fact_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-INVALIDATION-", values)
        ):
            raise Wo17ContractError("WO17_PRE_ENTRY_INVALIDATION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17PositionEvidence:
    position_identity: str
    position_integrity: str
    entry_event: Wo17PositionEvent
    decision: Wo16SponsorDecision
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
    trading_date: date
    direction: SemanticDirection
    entry_price: Decimal
    entry_timestamp: datetime
    evidence_recorded_at: datetime
    source_sequence_identity: str | None
    source_sequence: int | None
    manual_action_provenance: tuple[str, ...]
    evidence_role: str
    provenance: tuple[str, ...]
    schema_identity: str = WO17_POSITION_EVIDENCE_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    fill: str = "UNAVAILABLE"
    quantity: str = "UNAVAILABLE"
    fees: str = "UNAVAILABLE"
    monetary_pnl: str = "UNAVAILABLE"
    realised_r: str = "UNAVAILABLE"
    broker_acknowledgement: bool = False
    broker_order_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "position_identity", "position_integrity")
        unavailable = (self.fill, self.quantity, self.fees, self.monetary_pnl, self.realised_r)
        paper = self.decision is Wo16SponsorDecision.PAPER
        if (
            self.entry_event
            not in {Wo17PositionEvent.PAPER_ENTRY_OBSERVED, Wo17PositionEvent.LIVE_ENTRY_ATTESTED}
            or self.decision not in {Wo16SponsorDecision.PAPER, Wo16SponsorDecision.LIVE}
            or not _texts(
                (
                    self.upstream_snapshot_identity,
                    self.upstream_snapshot_integrity,
                    self.upstream_lineage_identity,
                    self.upstream_lineage_integrity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.entry_session_identity,
                    self.evidence_role,
                    *self.provenance,
                )
            )
            or type(self.direction) is not SemanticDirection
            or type(self.trading_date) is not date
            or not _decimal(self.entry_price)
            or not _aware(self.entry_timestamp)
            or not _aware(self.evidence_recorded_at)
            or (paper and (self.source_sequence_identity is None or self.source_sequence is None))
            or (not paper and (self.source_sequence_identity is not None or self.source_sequence is not None))
            or (paper and self.manual_action_provenance)
            or (not paper and not _texts(self.manual_action_provenance))
            or any(value != "UNAVAILABLE" for value in unavailable)
            or self.schema_identity != WO17_POSITION_EVIDENCE_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or self.broker_acknowledgement
            or self.broker_order_authority
            or self.execution_authority
            or self.position_identity != _identity("INTRADAY-WO17-POSITION-", values)
            or self.position_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-POSITION-", values)
        ):
            raise Wo17ContractError("WO17_POSITION_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17PositionMachine:
    state_identity: str
    state_integrity: str
    upstream_snapshot: Wo17UpstreamSnapshot
    state: Wo17PositionState
    continuity: Wo17EntryContinuity
    baseline: Wo17EntryObservation | None
    observations: tuple[Wo17EntryObservation, ...]
    position_evidence: Wo17PositionEvidence | None
    live_attestation: Wo17LiveEntryAttestation | None
    terminal_fact_identity: str | None
    blocking_non_closed_position_identity: str | None
    last_transition_at: datetime
    policy_identity: str = WO17_POLICY_IDENTITY
    policy_version: str = WO17_POLICY_VERSION
    policy_checksum: str = WO17_POLICY_CHECKSUM
    schema_identity: str = WO17_POSITION_STATE_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    provider_acquisition_authority: bool = False
    persistence_authority: bool = False
    closure_authority: bool = False
    broker_order_authority: bool = False
    execution_authority: bool = False
    quantity_authority: bool = False
    pnl_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "state_identity", "state_integrity")
        initial_paper = self.state is Wo17PositionState.PAPER_ARMED
        initial_live = self.state is Wo17PositionState.LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE
        active_paper = self.state is Wo17PositionState.PAPER_ACTIVE
        active_live = self.state is Wo17PositionState.LIVE_ACTIVE
        terminal = self.state in {
            Wo17PositionState.ENTRY_INVALIDATED_BEFORE_POSITION,
            Wo17PositionState.ENTRY_WINDOW_EXPIRED,
        }
        if (
            type(self.upstream_snapshot) is not Wo17UpstreamSnapshot
            or type(self.state) is not Wo17PositionState
            or type(self.continuity) is not Wo17EntryContinuity
            or any(type(item) is not Wo17EntryObservation for item in self.observations)
            or not _aware(self.last_transition_at)
            or self.policy_identity != WO17_POLICY_IDENTITY
            or self.policy_version != WO17_POLICY_VERSION
            or self.policy_checksum != WO17_POLICY_CHECKSUM
            or self.schema_identity != WO17_POSITION_STATE_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or any(
                (
                    self.provider_acquisition_authority,
                    self.persistence_authority,
                    self.closure_authority,
                    self.broker_order_authority,
                    self.execution_authority,
                    self.quantity_authority,
                    self.pnl_authority,
                )
            )
            or (active_paper and (self.position_evidence is None or self.live_attestation is not None))
            or (active_live and (self.position_evidence is None or self.live_attestation is None))
            or ((initial_paper or initial_live or terminal) and self.position_evidence is not None)
            or (terminal != (self.terminal_fact_identity is not None))
            or (initial_live and self.continuity is not Wo17EntryContinuity.NOT_APPLICABLE)
            or (self.upstream_snapshot.lineage.sponsor_decision is Wo16SponsorDecision.PAPER and (initial_live or active_live))
            or (self.upstream_snapshot.lineage.sponsor_decision is Wo16SponsorDecision.LIVE and (initial_paper or active_paper))
            or self.state_identity != _identity("INTRADAY-WO17-STATE-", values)
            or self.state_integrity != _identity("INTEGRITY-INTRADAY-WO17-STATE-", values)
        ):
            raise Wo17ContractError("WO17_POSITION_STATE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17PositionTransition:
    previous_state_identity: str
    current: Wo17PositionMachine
    event: Wo17PositionEvent
    applied: bool
    replayed: bool = False


def create_wo17_position_machine(
    snapshot: Wo17UpstreamSnapshot,
    *,
    blocking_non_closed_position_identity: str | None = None,
) -> Wo17PositionMachine:
    if type(snapshot) is not Wo17UpstreamSnapshot:
        raise Wo17PositionRejected(Wo17PositionFailure.SOURCE_CONTRACT_INVALID)
    if blocking_non_closed_position_identity is not None and not _text(blocking_non_closed_position_identity):
        raise Wo17PositionRejected(Wo17PositionFailure.SOURCE_CONTRACT_INVALID)
    paper = snapshot.lineage.sponsor_decision is Wo16SponsorDecision.PAPER
    state = (
        Wo17PositionState.PAPER_ARMED
        if paper
        else Wo17PositionState.LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE
    )
    continuity = Wo17EntryContinuity.AVAILABLE if paper else Wo17EntryContinuity.NOT_APPLICABLE
    return _state(
        upstream_snapshot=snapshot,
        state=state,
        continuity=continuity,
        baseline=None,
        observations=(),
        position_evidence=None,
        live_attestation=None,
        terminal_fact_identity=None,
        blocking_non_closed_position_identity=blocking_non_closed_position_identity,
        last_transition_at=snapshot.bound_at,
    )


def create_wo17_entry_observation(
    *,
    snapshot: Wo17UpstreamSnapshot,
    provider_identity: str,
    observed_price: Decimal,
    observed_at: datetime,
    source_sequence_identity: str,
    source_sequence: int,
    provenance: tuple[str, ...],
) -> Wo17EntryObservation:
    lineage = snapshot.lineage
    values = {
        "upstream_snapshot_identity": snapshot.snapshot_identity,
        "upstream_snapshot_integrity": snapshot.snapshot_integrity,
        "upstream_lineage_identity": lineage.lineage_identity,
        "upstream_lineage_integrity": lineage.lineage_integrity,
        "provider_identity": provider_identity,
        "canonical_subject_identity": lineage.canonical_subject_identity,
        "instrument_identity": lineage.instrument_identity,
        "actual_contract_identity": lineage.actual_contract_identity,
        "roll_lineage_identity": lineage.roll_lineage_identity,
        "session_identity": lineage.session_identity,
        "trading_date": lineage.trading_date,
        "direction": lineage.direction,
        "observed_price": observed_price,
        "observed_at": observed_at,
        "source_sequence_identity": source_sequence_identity,
        "source_sequence": source_sequence,
        "provenance": provenance,
        "schema_identity": WO17_ENTRY_OBSERVATION_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "broker_order_authority": False,
        "execution_authority": False,
    }
    return Wo17EntryObservation(
        observation_identity=_identity("INTRADAY-WO17-OBSERVATION-", values),
        observation_integrity=_identity("INTEGRITY-INTRADAY-WO17-OBSERVATION-", values),
        **values,
    )


def create_wo17_live_entry_attestation(
    *,
    snapshot: Wo17UpstreamSnapshot,
    actual_entry_price: Decimal,
    actual_entry_timestamp: datetime,
    attestation_operation_timestamp: datetime,
    sponsor_operation_identity: str,
    bounded_manual_action_provenance: tuple[str, ...],
) -> Wo17LiveEntryAttestation:
    lineage = snapshot.lineage
    values = {
        "upstream_snapshot_identity": snapshot.snapshot_identity,
        "upstream_snapshot_integrity": snapshot.snapshot_integrity,
        "upstream_lineage_identity": lineage.lineage_identity,
        "upstream_lineage_integrity": lineage.lineage_integrity,
        "wo16_decision_identity": lineage.wo16_decision_identity,
        "wo16_admission_identity": lineage.wo16_admission_identity,
        "canonical_subject_identity": lineage.canonical_subject_identity,
        "instrument_identity": lineage.instrument_identity,
        "actual_contract_identity": lineage.actual_contract_identity,
        "roll_lineage_identity": lineage.roll_lineage_identity,
        "session_identity": lineage.session_identity,
        "trading_date": lineage.trading_date,
        "direction": lineage.direction,
        "actual_entry_price": actual_entry_price,
        "actual_entry_timestamp": actual_entry_timestamp,
        "attestation_operation_timestamp": attestation_operation_timestamp,
        "sponsor_operation_identity": sponsor_operation_identity,
        "bounded_manual_action_provenance": bounded_manual_action_provenance,
        "schema_identity": WO17_LIVE_ATTESTATION_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "broker_acknowledgement": False,
        "broker_fill_authority": False,
        "execution_authority": False,
    }
    return Wo17LiveEntryAttestation(
        attestation_identity=_identity("INTRADAY-WO17-ATTESTATION-", values),
        attestation_integrity=_identity("INTEGRITY-INTRADAY-WO17-ATTESTATION-", values),
        **values,
    )


def create_wo17_pre_entry_invalidation_fact(
    *, snapshot: Wo17UpstreamSnapshot, observed_at: datetime,
    source_evidence_identity: str, provenance: tuple[str, ...]
) -> Wo17PreEntryInvalidationFact:
    lineage = snapshot.lineage
    values = {
        "upstream_snapshot_identity": snapshot.snapshot_identity,
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
        "thesis_invalidation_reference": lineage.thesis_invalidation_reference,
        "thesis_invalidation_event": lineage.thesis_invalidation_event,
        "observed_at": observed_at,
        "source_evidence_identity": source_evidence_identity,
        "provenance": provenance,
        "schema_identity": WO17_PRE_ENTRY_INVALIDATION_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
    }
    return Wo17PreEntryInvalidationFact(
        fact_identity=_identity("INTRADAY-WO17-INVALIDATION-", values),
        fact_integrity=_identity("INTEGRITY-INTRADAY-WO17-INVALIDATION-", values),
        **values,
    )


def apply_paper_observation(
    machine: Wo17PositionMachine, observation: Wo17EntryObservation
) -> Wo17PositionTransition:
    _require_machine(machine)
    if machine.upstream_snapshot.lineage.sponsor_decision is not Wo16SponsorDecision.PAPER:
        raise Wo17PositionRejected(Wo17PositionFailure.POSITION_MODE_MISMATCH)
    _require_observation_binding(machine, observation)
    replay = _observation_replay(machine, observation)
    if replay:
        return Wo17PositionTransition(machine.state_identity, machine, Wo17PositionEvent.EXACT_REPLAY, False, True)
    _require_pre_entry(machine)
    if machine.continuity is Wo17EntryContinuity.INTERRUPTED:
        raise Wo17PositionRejected(Wo17PositionFailure.CONTINUITY_TRANSITION_INVALID)
    _require_entry_time(machine, observation.observed_at)
    if observation.observed_at <= machine.last_transition_at:
        raise Wo17PositionRejected(Wo17PositionFailure.OBSERVATION_OLDER_THAN_CURRENT)
    baseline = machine.baseline
    if baseline is not None:
        if observation.observed_at < baseline.observed_at or observation.source_sequence < baseline.source_sequence:
            raise Wo17PositionRejected(Wo17PositionFailure.OBSERVATION_OLDER_THAN_CURRENT)
        if observation.observed_at == baseline.observed_at:
            raise Wo17PositionRejected(Wo17PositionFailure.OBSERVATION_EQUAL_TIME_CONFLICT)
        if observation.source_sequence_identity == baseline.source_sequence_identity or observation.source_sequence == baseline.source_sequence:
            raise Wo17PositionRejected(Wo17PositionFailure.SOURCE_SEQUENCE_CONFLICT)
    history = (*machine.observations, observation)
    if baseline is None:
        current = _update(machine, baseline=observation, observations=history,
                          continuity=Wo17EntryContinuity.AVAILABLE,
                          last_transition_at=observation.observed_at)
        return Wo17PositionTransition(machine.state_identity, current, Wo17PositionEvent.PAPER_BASELINE_OBSERVED, True)
    if observation.source_sequence != baseline.source_sequence + 1:
        current = _update(machine, baseline=observation, observations=history,
                          continuity=Wo17EntryContinuity.AVAILABLE,
                          last_transition_at=observation.observed_at)
        return Wo17PositionTransition(machine.state_identity, current, Wo17PositionEvent.ENTRY_SEQUENCE_UNRESOLVED, True)
    lineage = machine.upstream_snapshot.lineage
    crossed = (
        baseline.observed_price < lineage.entry_reference <= observation.observed_price
        if lineage.direction is SemanticDirection.LONG
        else baseline.observed_price > lineage.entry_reference >= observation.observed_price
    )
    if not crossed:
        current = _update(machine, baseline=observation, observations=history,
                          last_transition_at=observation.observed_at)
        return Wo17PositionTransition(machine.state_identity, current, Wo17PositionEvent.PAPER_BASELINE_OBSERVED, True)
    _require_cardinality(machine)
    evidence = _paper_position(machine.upstream_snapshot, observation)
    current = _update(machine, state=Wo17PositionState.PAPER_ACTIVE,
                      baseline=observation, observations=history,
                      position_evidence=evidence,
                      last_transition_at=observation.observed_at)
    return Wo17PositionTransition(machine.state_identity, current, Wo17PositionEvent.PAPER_ENTRY_OBSERVED, True)


def apply_live_entry_attestation(
    machine: Wo17PositionMachine, attestation: Wo17LiveEntryAttestation
) -> Wo17PositionTransition:
    _require_machine(machine)
    if machine.state is Wo17PositionState.LIVE_ACTIVE and machine.live_attestation == attestation:
        return Wo17PositionTransition(machine.state_identity, machine, Wo17PositionEvent.EXACT_REPLAY, False, True)
    if machine.upstream_snapshot.lineage.sponsor_decision is not Wo16SponsorDecision.LIVE:
        raise Wo17PositionRejected(Wo17PositionFailure.POSITION_MODE_MISMATCH)
    _require_pre_entry(machine)
    _require_attestation_binding(machine, attestation)
    _require_entry_time(machine, attestation.actual_entry_timestamp)
    _require_entry_time(machine, attestation.attestation_operation_timestamp)
    if attestation.attestation_operation_timestamp < attestation.actual_entry_timestamp:
        raise Wo17PositionRejected(Wo17PositionFailure.SOURCE_CONTRACT_INVALID)
    _require_cardinality(machine)
    evidence = _live_position(machine.upstream_snapshot, attestation)
    current = _update(machine, state=Wo17PositionState.LIVE_ACTIVE,
                      position_evidence=evidence, live_attestation=attestation,
                      last_transition_at=attestation.attestation_operation_timestamp)
    return Wo17PositionTransition(machine.state_identity, current, Wo17PositionEvent.LIVE_ENTRY_ATTESTED, True)


def interrupt_paper_entry_sequence(
    machine: Wo17PositionMachine, *, occurred_at: datetime
) -> Wo17PositionTransition:
    _require_machine(machine)
    _require_paper_armed(machine)
    if machine.continuity is Wo17EntryContinuity.INTERRUPTED:
        raise Wo17PositionRejected(Wo17PositionFailure.CONTINUITY_TRANSITION_INVALID)
    _require_ordered_transition_time(machine, occurred_at)
    current = _update(machine, baseline=None, continuity=Wo17EntryContinuity.INTERRUPTED,
                      last_transition_at=occurred_at)
    return Wo17PositionTransition(machine.state_identity, current, Wo17PositionEvent.MONITORING_INTERRUPTED, True)


def recover_paper_entry_sequence(
    machine: Wo17PositionMachine, *, recovered_at: datetime
) -> Wo17PositionTransition:
    _require_machine(machine)
    _require_paper_armed(machine)
    if machine.continuity is not Wo17EntryContinuity.INTERRUPTED:
        raise Wo17PositionRejected(Wo17PositionFailure.CONTINUITY_TRANSITION_INVALID)
    _require_ordered_transition_time(machine, recovered_at)
    current = _update(machine, baseline=None, continuity=Wo17EntryContinuity.RECOVERING,
                      last_transition_at=recovered_at)
    return Wo17PositionTransition(machine.state_identity, current, Wo17PositionEvent.MONITORING_RECOVERED, True)


def apply_pre_entry_invalidation(
    machine: Wo17PositionMachine, fact: Wo17PreEntryInvalidationFact
) -> Wo17PositionTransition:
    _require_machine(machine)
    _require_pre_entry(machine)
    lineage = machine.upstream_snapshot.lineage
    expected = (
        machine.upstream_snapshot.snapshot_identity,
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
        lineage.thesis_invalidation_reference,
        lineage.thesis_invalidation_event,
    )
    received = (
        fact.upstream_snapshot_identity, fact.upstream_lineage_identity,
        fact.canonical_subject_identity, fact.instrument_identity,
        fact.actual_contract_identity, fact.roll_lineage_identity,
        fact.session_identity, fact.trading_date, fact.direction,
        fact.entry_reference, fact.stop, fact.thesis_invalidation_reference,
        fact.thesis_invalidation_event,
    )
    if received != expected:
        raise Wo17PositionRejected(Wo17PositionFailure.INVALIDATION_FACT_MISMATCH)
    _require_session_time(machine, fact.observed_at)
    current = _update(machine,
                      state=Wo17PositionState.ENTRY_INVALIDATED_BEFORE_POSITION,
                      baseline=None, terminal_fact_identity=fact.fact_identity,
                      last_transition_at=fact.observed_at)
    return Wo17PositionTransition(machine.state_identity, current,
                                  Wo17PositionEvent.ENTRY_INVALIDATED_BEFORE_POSITION, True)


def expire_entry_window(
    machine: Wo17PositionMachine, *, expired_at: datetime
) -> Wo17PositionTransition:
    _require_machine(machine)
    _require_pre_entry(machine)
    if not _aware(expired_at):
        raise Wo17PositionRejected(Wo17PositionFailure.SOURCE_CONTRACT_INVALID)
    boundary = _entry_window_end(machine.upstream_snapshot)
    if expired_at < boundary:
        raise Wo17PositionRejected(Wo17PositionFailure.ENTRY_WINDOW_NOT_EXPIRED)
    fact_identity = _identity("INTRADAY-WO17-ENTRY-WINDOW-EXPIRY-", {
        "snapshot_identity": machine.upstream_snapshot.snapshot_identity,
        "expired_at": expired_at,
        "boundary": boundary,
    })
    current = _update(machine, state=Wo17PositionState.ENTRY_WINDOW_EXPIRED,
                      baseline=None, terminal_fact_identity=fact_identity,
                      last_transition_at=expired_at)
    return Wo17PositionTransition(machine.state_identity, current,
                                  Wo17PositionEvent.ENTRY_WINDOW_EXPIRED, True)


def _paper_position(snapshot: Wo17UpstreamSnapshot, observation: Wo17EntryObservation) -> Wo17PositionEvidence:
    return _position(snapshot=snapshot, entry_event=Wo17PositionEvent.PAPER_ENTRY_OBSERVED,
                     entry_price=observation.observed_price,
                     entry_timestamp=observation.observed_at,
                     recorded_at=observation.observed_at,
                     source_sequence_identity=observation.source_sequence_identity,
                     source_sequence=observation.source_sequence,
                     manual_action_provenance=(), evidence_role="MODEL_POSITION_EVIDENCE",
                     provenance=(observation.observation_identity, "ADR-0027", "WO-17-SLICE-2"))


def _live_position(snapshot: Wo17UpstreamSnapshot, attestation: Wo17LiveEntryAttestation) -> Wo17PositionEvidence:
    return _position(snapshot=snapshot, entry_event=Wo17PositionEvent.LIVE_ENTRY_ATTESTED,
                     entry_price=attestation.actual_entry_price,
                     entry_timestamp=attestation.actual_entry_timestamp,
                     recorded_at=attestation.attestation_operation_timestamp,
                     source_sequence_identity=None, source_sequence=None,
                     manual_action_provenance=attestation.bounded_manual_action_provenance,
                     evidence_role="SPONSOR_ATTESTED_ACTUAL_ENTRY_EVIDENCE",
                     provenance=(attestation.attestation_identity, "ADR-0027", "WO-17-SLICE-2"))


def _position(*, snapshot: Wo17UpstreamSnapshot, entry_event: Wo17PositionEvent,
              entry_price: Decimal, entry_timestamp: datetime, recorded_at: datetime,
              source_sequence_identity: str | None, source_sequence: int | None,
              manual_action_provenance: tuple[str, ...], evidence_role: str,
              provenance: tuple[str, ...]) -> Wo17PositionEvidence:
    lineage = snapshot.lineage
    values = {
        "entry_event": entry_event,
        "decision": lineage.sponsor_decision,
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
        "trading_date": lineage.trading_date,
        "direction": lineage.direction,
        "entry_price": entry_price,
        "entry_timestamp": entry_timestamp,
        "evidence_recorded_at": recorded_at,
        "source_sequence_identity": source_sequence_identity,
        "source_sequence": source_sequence,
        "manual_action_provenance": manual_action_provenance,
        "evidence_role": evidence_role,
        "provenance": provenance,
        "schema_identity": WO17_POSITION_EVIDENCE_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "fill": "UNAVAILABLE", "quantity": "UNAVAILABLE", "fees": "UNAVAILABLE",
        "monetary_pnl": "UNAVAILABLE", "realised_r": "UNAVAILABLE",
        "broker_acknowledgement": False, "broker_order_authority": False,
        "execution_authority": False,
    }
    return Wo17PositionEvidence(
        position_identity=_identity("INTRADAY-WO17-POSITION-", values),
        position_integrity=_identity("INTEGRITY-INTRADAY-WO17-POSITION-", values),
        **values,
    )


def _observation_replay(machine: Wo17PositionMachine, observation: Wo17EntryObservation) -> bool:
    for existing in machine.observations:
        if existing.observation_identity == observation.observation_identity:
            if existing == observation:
                return True
            raise Wo17PositionRejected(Wo17PositionFailure.SOURCE_SEQUENCE_CONFLICT)
        if existing.source_sequence_identity == observation.source_sequence_identity:
            if canonical_document_bytes(existing) == canonical_document_bytes(observation):
                return True
            raise Wo17PositionRejected(Wo17PositionFailure.SOURCE_SEQUENCE_CONFLICT)
        if existing.source_sequence == observation.source_sequence:
            raise Wo17PositionRejected(Wo17PositionFailure.SOURCE_SEQUENCE_CONFLICT)
        if existing.observed_at == observation.observed_at:
            raise Wo17PositionRejected(Wo17PositionFailure.OBSERVATION_EQUAL_TIME_CONFLICT)
    return False


def _require_observation_binding(machine: Wo17PositionMachine, observation: Wo17EntryObservation) -> None:
    lineage = machine.upstream_snapshot.lineage
    expected = (
        machine.upstream_snapshot.snapshot_identity, machine.upstream_snapshot.snapshot_integrity,
        lineage.lineage_identity, lineage.lineage_integrity,
        lineage.canonical_subject_identity, lineage.instrument_identity,
        lineage.actual_contract_identity, lineage.roll_lineage_identity,
        lineage.session_identity, lineage.trading_date, lineage.direction,
    )
    received = (
        observation.upstream_snapshot_identity, observation.upstream_snapshot_integrity,
        observation.upstream_lineage_identity, observation.upstream_lineage_integrity,
        observation.canonical_subject_identity, observation.instrument_identity,
        observation.actual_contract_identity, observation.roll_lineage_identity,
        observation.session_identity, observation.trading_date, observation.direction,
    )
    if received != expected:
        raise Wo17PositionRejected(Wo17PositionFailure.UPSTREAM_LINEAGE_MISMATCH)


def _require_attestation_binding(machine: Wo17PositionMachine, item: Wo17LiveEntryAttestation) -> None:
    lineage = machine.upstream_snapshot.lineage
    expected = (
        machine.upstream_snapshot.snapshot_identity, machine.upstream_snapshot.snapshot_integrity,
        lineage.lineage_identity, lineage.lineage_integrity,
        lineage.wo16_decision_identity, lineage.wo16_admission_identity,
        lineage.canonical_subject_identity, lineage.instrument_identity,
        lineage.actual_contract_identity, lineage.roll_lineage_identity,
        lineage.session_identity, lineage.trading_date, lineage.direction,
    )
    received = (
        item.upstream_snapshot_identity, item.upstream_snapshot_integrity,
        item.upstream_lineage_identity, item.upstream_lineage_integrity,
        item.wo16_decision_identity, item.wo16_admission_identity,
        item.canonical_subject_identity, item.instrument_identity,
        item.actual_contract_identity, item.roll_lineage_identity,
        item.session_identity, item.trading_date, item.direction,
    )
    if received != expected:
        raise Wo17PositionRejected(Wo17PositionFailure.UPSTREAM_LINEAGE_MISMATCH)


def _require_machine(machine: Wo17PositionMachine) -> None:
    if type(machine) is not Wo17PositionMachine:
        raise Wo17PositionRejected(Wo17PositionFailure.SOURCE_CONTRACT_INVALID)


def _require_pre_entry(machine: Wo17PositionMachine) -> None:
    if machine.state in {Wo17PositionState.ENTRY_INVALIDATED_BEFORE_POSITION, Wo17PositionState.ENTRY_WINDOW_EXPIRED}:
        raise Wo17PositionRejected(Wo17PositionFailure.POSITION_STATE_TERMINAL)
    if machine.state in {Wo17PositionState.PAPER_ACTIVE, Wo17PositionState.LIVE_ACTIVE}:
        raise Wo17PositionRejected(Wo17PositionFailure.POSITION_ALREADY_ACTIVE)


def _require_paper_armed(machine: Wo17PositionMachine) -> None:
    if machine.state is not Wo17PositionState.PAPER_ARMED:
        _require_pre_entry(machine)
        raise Wo17PositionRejected(Wo17PositionFailure.POSITION_MODE_MISMATCH)


def _require_cardinality(machine: Wo17PositionMachine) -> None:
    if machine.blocking_non_closed_position_identity is not None:
        raise Wo17PositionRejected(Wo17PositionFailure.EXISTING_NON_CLOSED_POSITION)


def _require_ordered_transition_time(machine: Wo17PositionMachine, value: datetime) -> None:
    if not _aware(value):
        raise Wo17PositionRejected(Wo17PositionFailure.SOURCE_CONTRACT_INVALID)
    if value <= machine.last_transition_at:
        raise Wo17PositionRejected(Wo17PositionFailure.OBSERVATION_OLDER_THAN_CURRENT)
    _require_session_time(machine, value)


def _require_session_time(machine: Wo17PositionMachine, value: datetime) -> None:
    lineage = machine.upstream_snapshot.lineage
    if (
        value.astimezone(_IST).date() != lineage.trading_date
        or value < lineage.active_window_opens_at
        or value >= lineage.active_window_closes_at
    ):
        raise Wo17PositionRejected(Wo17PositionFailure.DOMAIN_008_SESSION_MISMATCH)


def _require_entry_time(machine: Wo17PositionMachine, value: datetime) -> None:
    _require_session_time(machine, value)
    if value < machine.upstream_snapshot.bound_at:
        raise Wo17PositionRejected(Wo17PositionFailure.UPSTREAM_LINEAGE_MISMATCH)
    if value >= _entry_window_end(machine.upstream_snapshot):
        raise Wo17PositionRejected(Wo17PositionFailure.ENTRY_CUTOFF_REACHED)


def _entry_window_end(snapshot: Wo17UpstreamSnapshot) -> datetime:
    lineage = snapshot.lineage
    cutoff = _MCX_CUTOFF if lineage.market_family is IntradayMarketFamily.MCX else _NSE_CUTOFF
    local = datetime.combine(lineage.trading_date, cutoff, tzinfo=_IST)
    return min(local, lineage.active_window_closes_at)


def _state(**values: object) -> Wo17PositionMachine:
    common = {
        **values,
        "policy_identity": WO17_POLICY_IDENTITY,
        "policy_version": WO17_POLICY_VERSION,
        "policy_checksum": WO17_POLICY_CHECKSUM,
        "schema_identity": WO17_POSITION_STATE_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "provider_acquisition_authority": False,
        "persistence_authority": False,
        "closure_authority": False,
        "broker_order_authority": False,
        "execution_authority": False,
        "quantity_authority": False,
        "pnl_authority": False,
    }
    return Wo17PositionMachine(
        state_identity=_identity("INTRADAY-WO17-STATE-", common),
        state_integrity=_identity("INTEGRITY-INTRADAY-WO17-STATE-", common),
        **common,  # type: ignore[arg-type]
    )


def _update(machine: Wo17PositionMachine, **changes: object) -> Wo17PositionMachine:
    values = {
        item.name: getattr(machine, item.name)
        for item in fields(machine)
        if item.name not in {"state_identity", "state_integrity"}
    }
    values.update(changes)
    return _state(**values)


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_document_bytes(value)).hexdigest().upper()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _decimal(value: object) -> bool:
    return type(value) is Decimal and value.is_finite()


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(value) for value in values)


__all__ = [name for name in globals() if name.startswith(("WO17_", "Wo17", "create_", "apply_", "interrupt_", "recover_", "expire_"))]
