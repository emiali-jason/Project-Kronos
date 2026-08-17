"""Governed Swing V1 Step-32 contracts and deterministic local lifecycle.

This module implements the approved SHADOW / VALIDATION ONLY architecture.
It has no public ingress, Pine runtime, broker client, order operation, or
position-changing authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.provider.contracts.monitoring import (
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
)

from kronos.swing.v1.trade_construction import (
    SwingV1TradeCandidate,
    TradeCandidateIntegrity,
    TradeCandidateStaleness,
    TradeConstructionStatus,
    TradeViabilityStatus,
)


BUSINESS_JUDGMENT_CONTRACT_ID = "KRONOS-SWING-V1-BUSINESS-JUDGMENT-V1"
RISK_APPROVAL_CONTRACT_ID = "KRONOS-SWING-V1-RISK-APPROVAL-V1"
SPONSOR_DECISION_CONTRACT_ID = "KRONOS-SWING-V1-SPONSOR-DECISION-V1"
SPONSOR_POSITION_CONTRACT_ID = "KRONOS-SWING-V1-SPONSOR-POSITION-V1"
MONITORING_SUBMISSION_CONTRACT_ID = "KRONOS-SWING-V1-MONITORING-SUBMISSION-V1"
MONITORING_OBSERVATION_CONTRACT_ID = "KRONOS-SWING-V1-MONITORING-OBSERVATION-V1"
LIFECYCLE_EVENT_CONTRACT_ID = "KRONOS-SWING-V1-LIFECYCLE-EVENT-V1"
CONTRACT_VERSION = "1"
STEP32_OPERATIONAL_AUTHORITY = "SHADOW / VALIDATION ONLY"


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Freshness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"


class RiskState(StrEnum):
    APPROVED = "RISK_APPROVED"
    CONSTRAINED = "RISK_CONSTRAINED"
    REJECTED = "RISK_REJECTED"
    UNAVAILABLE = "RISK_UNAVAILABLE"


class SponsorDecisionMode(StrEnum):
    LIVE = "LIVE"
    PAPER = "PAPER"
    IGNORE = "IGNORE"


class CandidateLifecycleState(StrEnum):
    WAITING_FOR_RISK = "WAITING_FOR_RISK"
    WAITING_FOR_ENTRY = "WAITING_FOR_ENTRY"
    RISK_REJECTED = "RISK_REJECTED"
    STALE = "STALE"
    PRE_ENTRY_INVALIDATED = "PRE_ENTRY_INVALIDATED"
    RECONCILIATION_REQUIRED_PRE_ENTRY = "RECONCILIATION_REQUIRED_PRE_ENTRY"


class MonitoringSubmissionType(StrEnum):
    FACTUAL_MARKET_TICK = "FACTUAL_MARKET_TICK"
    ENTRY_LEVEL_CROSSED = "ENTRY_LEVEL_CROSSED"
    STOP_LEVEL_CROSSED = "STOP_LEVEL_CROSSED"
    TARGET_LEVEL_CROSSED = "TARGET_LEVEL_CROSSED"
    DAILY_BOUNDARY_CLOSED = "DAILY_BOUNDARY_CLOSED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class EntryOutcomeState(StrEnum):
    ENTRY_NOT_TRIGGERED = "ENTRY_NOT_TRIGGERED"
    ENTRY_TRIGGERED = "ENTRY_TRIGGERED"
    RECONCILIATION_REQUIRED_PRE_ENTRY = "RECONCILIATION_REQUIRED_PRE_ENTRY"


class ObjectiveModelState(StrEnum):
    ACTIVE = "MODEL_TRADE_ACTIVE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    CLOSED = "MODEL_TRADE_CLOSED"


class ModelCloseReason(StrEnum):
    STOP = "STOP"
    TARGET = "TARGET"
    ANALYTICAL_INVALIDATION = "ANALYTICAL_INVALIDATION"
    OUTCOME_UNRESOLVED = "OUTCOME_UNRESOLVED"


class SponsorPositionState(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class LifecycleEventType(StrEnum):
    ENTRY_TRIGGERED = "SWING_ENTRY_TRIGGERED"
    MODEL_TRADE_CLOSED = "SWING_MODEL_TRADE_CLOSED"
    RECONCILIATION_REQUIRED = "SWING_RECONCILIATION_REQUIRED"
    LIVE_ACTION_REQUIRED = "SWING_LIVE_ACTION_REQUIRED"
    DATA_UNAVAILABLE = "SWING_DATA_UNAVAILABLE"


class RecoveryState(StrEnum):
    RECOVERED = "RECOVERED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class BusinessJudgment:
    contract_identity: str
    contract_version: str
    business_judgment_id: str
    candidate_id: str
    candidate_contract_identity: str
    candidate_contract_version: str
    candidate_digest: str
    validation_identity: str
    readiness_identity: str
    run_id: str
    market_data_boundary: datetime
    freshness: Freshness
    integrity: TradeCandidateIntegrity
    created_at: datetime
    provenance: tuple[str, ...]
    canonical_instrument_echo: str | None = None
    product_echo: str | None = None
    setup_echo: str | None = None
    direction_echo: str | None = None

    def __post_init__(self) -> None:
        if (
            self.contract_identity != BUSINESS_JUDGMENT_CONTRACT_ID
            or self.contract_version != CONTRACT_VERSION
            or not _identity(self.business_judgment_id)
            or not _identity(self.candidate_id)
            or not _digest(self.candidate_digest)
            or not _identity(self.validation_identity)
            or not _identity(self.readiness_identity)
            or not _identity(self.run_id)
            or not _aware(self.market_data_boundary)
            or not _aware(self.created_at)
            or type(self.freshness) is not Freshness
            or type(self.integrity) is not TradeCandidateIntegrity
            or not _identity_tuple(self.provenance)
        ):
            raise ValueError("BUSINESS_JUDGMENT_INVALID")


@dataclass(frozen=True, slots=True)
class RiskConstraints:
    maximum_quantity: Decimal | None = None
    maximum_notional: Decimal | None = None
    maximum_capital_at_risk: Decimal | None = None
    maximum_margin: Decimal | None = None
    maximum_exposure: Decimal | None = None
    maximum_concentration: Decimal | None = None
    maximum_lots: int | None = None

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if value is not None:
                if field.name == "maximum_lots":
                    if type(value) is not int or value <= 0:
                        raise ValueError("RISK_CONSTRAINT_INVALID")
                    continue
                value = _decimal(value)
                if value <= 0:
                    raise ValueError("RISK_CONSTRAINT_INVALID")
                object.__setattr__(self, field.name, value)

    @property
    def present(self) -> bool:
        return any(getattr(self, field.name) is not None for field in fields(self))


@dataclass(frozen=True, slots=True)
class RiskApproval:
    contract_identity: str
    contract_version: str
    risk_result_id: str
    candidate_id: str
    candidate_digest: str
    business_judgment_id: str
    run_id: str
    state: RiskState
    constraints: RiskConstraints
    reason: str
    evaluated_at: datetime
    valid_until: datetime | None
    provenance: tuple[str, ...]
    integrity: TradeCandidateIntegrity

    def __post_init__(self) -> None:
        if (
            self.contract_identity != RISK_APPROVAL_CONTRACT_ID
            or self.contract_version != CONTRACT_VERSION
            or not _identity(self.risk_result_id)
            or not _identity(self.candidate_id)
            or not _digest(self.candidate_digest)
            or not _identity(self.business_judgment_id)
            or not _identity(self.run_id)
            or type(self.state) is not RiskState
            or type(self.constraints) is not RiskConstraints
            or not _reason(self.reason)
            or not _aware(self.evaluated_at)
            or (self.valid_until is not None and not _aware(self.valid_until))
            or not _identity_tuple(self.provenance)
            or type(self.integrity) is not TradeCandidateIntegrity
            or (self.state is RiskState.CONSTRAINED and not self.constraints.present)
            or (self.state is not RiskState.CONSTRAINED and self.constraints.present)
        ):
            raise ValueError("RISK_APPROVAL_INVALID")

    @property
    def permits_entry(self) -> bool:
        return self.state in {RiskState.APPROVED, RiskState.CONSTRAINED}


@dataclass(frozen=True, slots=True)
class CandidateLifecycle:
    candidate_id: str
    candidate_digest: str
    monitoring_binding_id: str
    state: CandidateLifecycleState
    reason: str
    updated_at: datetime
    risk_result_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not _identity(self.candidate_id)
            or not _digest(self.candidate_digest)
            or not _identity(self.monitoring_binding_id)
            or type(self.state) is not CandidateLifecycleState
            or not _reason(self.reason)
            or not _aware(self.updated_at)
            or (self.risk_result_id is not None and not _identity(self.risk_result_id))
        ):
            raise ValueError("CANDIDATE_LIFECYCLE_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorDecision:
    contract_identity: str
    contract_version: str
    sponsor_decision_id: str
    candidate_id: str
    candidate_digest: str
    run_id: str
    risk_result_id: str
    revision: int
    mode: SponsorDecisionMode
    decided_at: datetime
    frozen: bool
    provenance: tuple[str, ...]
    integrity: TradeCandidateIntegrity

    def __post_init__(self) -> None:
        if (
            self.contract_identity != SPONSOR_DECISION_CONTRACT_ID
            or self.contract_version != CONTRACT_VERSION
            or not _identity(self.sponsor_decision_id)
            or not _identity(self.candidate_id)
            or not _digest(self.candidate_digest)
            or not _identity(self.run_id)
            or not _identity(self.risk_result_id)
            or type(self.revision) is not int
            or self.revision < 1
            or type(self.mode) is not SponsorDecisionMode
            or not _aware(self.decided_at)
            or type(self.frozen) is not bool
            or not _identity_tuple(self.provenance)
            or type(self.integrity) is not TradeCandidateIntegrity
        ):
            raise ValueError("SPONSOR_DECISION_INVALID")


@dataclass(frozen=True, slots=True)
class MonitoringSubmission:
    contract_identity: str
    contract_version: str
    submission_id: str
    candidate_id: str
    monitoring_binding_id: str
    model_trade_id: str | None
    canonical_instrument: str
    provider_instrument: str
    product: str
    direction: str
    submission_type: MonitoringSubmissionType
    observed_price_availability: Availability
    observed_price: Decimal | None
    reference: str
    observed_at: datetime
    boundary: datetime
    timeframe: str
    session_identity: str
    source: str
    source_connection_id: str
    source_provenance: tuple[str, ...]
    source_sequence: int | None
    previous_interval_available: bool
    session_continuous: bool
    ordering_deterministic: bool
    payload_digest: str

    def __post_init__(self) -> None:
        if self.observed_price is not None:
            object.__setattr__(self, "observed_price", _decimal(self.observed_price))
        if (
            self.contract_identity != MONITORING_SUBMISSION_CONTRACT_ID
            or self.contract_version != CONTRACT_VERSION
            or not _identity(self.submission_id)
            or not _identity(self.candidate_id)
            or not _identity(self.monitoring_binding_id)
            or (self.model_trade_id is not None and not _identity(self.model_trade_id))
            or not self.canonical_instrument
            or not self.provider_instrument
            or not self.product
            or self.direction not in (
                {"LONG", "SHORT", "NOT_APPLICABLE"}
                if self.submission_type is MonitoringSubmissionType.FACTUAL_MARKET_TICK
                else {"LONG", "SHORT"}
            )
            or type(self.submission_type) is not MonitoringSubmissionType
            or type(self.observed_price_availability) is not Availability
            or (self.observed_price_availability is Availability.AVAILABLE) != (self.observed_price is not None)
            or not _identity(self.reference)
            or not _aware(self.observed_at)
            or not _aware(self.boundary)
            or not _identity(self.timeframe)
            or not _identity(self.session_identity)
            or self.source not in {
                "KITE_CONNECT_WEBSOCKET",
                "KITE_CONNECT_HISTORICAL",
            }
            or not _identity(self.source_connection_id)
            or not _identity_tuple(self.source_provenance)
            or (self.source_sequence is not None and (type(self.source_sequence) is not int or self.source_sequence < 0))
            or type(self.previous_interval_available) is not bool
            or type(self.session_continuous) is not bool
            or type(self.ordering_deterministic) is not bool
            or not _digest(self.payload_digest)
        ):
            raise ValueError("MONITORING_SUBMISSION_INVALID")


@dataclass(frozen=True, slots=True)
class MonitoringAdmissionContext:
    candidate_id: str
    monitoring_binding_id: str
    model_trade_id: str | None
    canonical_instrument: str
    provider_instrument: str
    product: str
    direction: str
    provider_source: str
    source_connection_id: str
    binding_active: bool
    boundary: datetime
    timeframe: str
    session_identity: str


@dataclass(frozen=True, slots=True)
class MonitoringObservation:
    contract_identity: str
    contract_version: str
    observation_id: str
    source_submission_id: str
    source_payload_digest: str
    candidate_id: str
    monitoring_binding_id: str
    model_trade_id: str | None
    canonical_instrument: str
    provider_instrument: str
    product: str
    direction: str
    observation_type: MonitoringSubmissionType
    observed_price_availability: Availability
    observed_price: Decimal | None
    observed_at: datetime
    admitted_at: datetime
    boundary: datetime
    timeframe: str
    session_identity: str
    source_sequence: int | None
    previous_interval_available: bool
    session_continuous: bool
    ordering_deterministic: bool
    provenance: tuple[str, ...]
    freshness: Freshness
    integrity: TradeCandidateIntegrity

    def __post_init__(self) -> None:
        if self.observed_price is not None:
            object.__setattr__(self, "observed_price", _decimal(self.observed_price))
        if (
            self.contract_identity != MONITORING_OBSERVATION_CONTRACT_ID
            or self.contract_version != CONTRACT_VERSION
            or not _identity(self.observation_id)
            or not _identity(self.source_submission_id)
            or not _digest(self.source_payload_digest)
            or not _identity(self.candidate_id)
            or not _identity(self.monitoring_binding_id)
            or (self.model_trade_id is not None and not _identity(self.model_trade_id))
            or type(self.observation_type) is not MonitoringSubmissionType
            or type(self.observed_price_availability) is not Availability
            or (self.observed_price_availability is Availability.AVAILABLE) != (self.observed_price is not None)
            or not _aware(self.observed_at)
            or not _aware(self.admitted_at)
            or not _aware(self.boundary)
            or not _identity_tuple(self.provenance)
            or type(self.freshness) is not Freshness
            or type(self.integrity) is not TradeCandidateIntegrity
        ):
            raise ValueError("MONITORING_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class EntryOutcome:
    entry_outcome_id: str
    candidate_id: str
    candidate_digest: str
    monitoring_binding_id: str
    risk_result_id: str
    state: EntryOutcomeState
    model_reference_entry_availability: Availability
    model_reference_entry_price: Decimal | None
    source_observation_ids: tuple[str, ...]
    occurred_at: datetime
    reason: str
    integrity: TradeCandidateIntegrity

    def __post_init__(self) -> None:
        if self.model_reference_entry_price is not None:
            object.__setattr__(self, "model_reference_entry_price", _decimal(self.model_reference_entry_price))
        if (
            not _identity(self.entry_outcome_id)
            or not _identity(self.candidate_id)
            or not _digest(self.candidate_digest)
            or not _identity(self.monitoring_binding_id)
            or not _identity(self.risk_result_id)
            or type(self.state) is not EntryOutcomeState
            or type(self.model_reference_entry_availability) is not Availability
            or (self.model_reference_entry_availability is Availability.AVAILABLE) != (self.model_reference_entry_price is not None)
            or not _identity_tuple(self.source_observation_ids, allow_empty=True)
            or not _aware(self.occurred_at)
            or not _reason(self.reason)
            or type(self.integrity) is not TradeCandidateIntegrity
        ):
            raise ValueError("ENTRY_OUTCOME_INVALID")


@dataclass(frozen=True, slots=True)
class ObjectiveModelTrade:
    model_trade_id: str
    candidate_id: str
    candidate_digest: str
    monitoring_binding_id: str
    risk_result_id: str
    entry_outcome_id: str
    canonical_instrument: str
    product: str
    direction: str
    setup: str
    entry_price: Decimal
    stop_price: Decimal
    invalidation_level: Decimal
    invalidation_condition: str
    target_price: Decimal
    state: ObjectiveModelState
    close_reason: ModelCloseReason | None
    exit_price_availability: Availability
    exit_price: Decimal | None
    activated_at: datetime
    updated_at: datetime
    source_observation_ids: tuple[str, ...]
    integrity: TradeCandidateIntegrity

    def __post_init__(self) -> None:
        for name in ("entry_price", "stop_price", "invalidation_level", "target_price"):
            object.__setattr__(self, name, _decimal(getattr(self, name)))
        if self.exit_price is not None:
            object.__setattr__(self, "exit_price", _decimal(self.exit_price))
        if (
            not _identity(self.model_trade_id)
            or not _identity(self.candidate_id)
            or not _digest(self.candidate_digest)
            or not _identity(self.monitoring_binding_id)
            or not _identity(self.risk_result_id)
            or not _identity(self.entry_outcome_id)
            or self.direction not in {"LONG", "SHORT"}
            or type(self.state) is not ObjectiveModelState
            or (self.close_reason is not None and type(self.close_reason) is not ModelCloseReason)
            or type(self.exit_price_availability) is not Availability
            or (self.exit_price_availability is Availability.AVAILABLE) != (self.exit_price is not None)
            or not _aware(self.activated_at)
            or not _aware(self.updated_at)
            or not _identity_tuple(self.source_observation_ids, allow_empty=True)
            or type(self.integrity) is not TradeCandidateIntegrity
            or (self.state is ObjectiveModelState.CLOSED) != (self.close_reason is not None)
        ):
            raise ValueError("OBJECTIVE_MODEL_TRADE_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorExecutionEvidence:
    evidence_id: str
    actual_entry_price: Decimal
    actual_quantity: Decimal
    occurred_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "actual_entry_price", _decimal(self.actual_entry_price))
        object.__setattr__(self, "actual_quantity", _decimal(self.actual_quantity))
        if not _identity(self.evidence_id) or self.actual_entry_price <= 0 or self.actual_quantity <= 0 or not _aware(self.occurred_at):
            raise ValueError("SPONSOR_EXECUTION_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorOrderEvidence:
    """Optional Kite order evidence bound only to the Sponsor-position branch."""

    evidence_id: str
    provider_order_id: str
    sponsor_decision_id: str
    candidate_id: str
    canonical_instrument: str
    status: str
    side: str
    filled_quantity: Decimal
    average_price_availability: Availability
    average_price: Decimal | None
    observed_at: datetime
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "filled_quantity", _decimal(self.filled_quantity))
        if self.average_price is not None:
            object.__setattr__(self, "average_price", _decimal(self.average_price))
        if (
            not _identity(self.evidence_id)
            or not _identity(self.provider_order_id)
            or not _identity(self.sponsor_decision_id)
            or not _identity(self.candidate_id)
            or not _identity(self.canonical_instrument)
            or not _identity(self.status)
            or self.side not in {"BUY", "SELL"}
            or self.filled_quantity < 0
            or type(self.average_price_availability) is not Availability
            or not _availability_pair(self.average_price_availability, self.average_price)
            or not _aware(self.observed_at)
            or not _identity_tuple(self.provenance)
        ):
            raise ValueError("SPONSOR_ORDER_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorPosition:
    contract_identity: str
    contract_version: str
    sponsor_position_id: str
    sponsor_decision_id: str
    candidate_id: str
    model_trade_id: str
    mode: SponsorDecisionMode
    state: SponsorPositionState
    model_reference_entry_availability: Availability
    model_reference_entry_price: Decimal | None
    actual_entry_availability: Availability
    actual_entry_price: Decimal | None
    actual_quantity_availability: Availability
    actual_quantity: Decimal | None
    actual_exit_availability: Availability
    actual_exit_price: Decimal | None
    actual_pnl_availability: Availability
    actual_r_availability: Availability
    evidence_id: str | None
    updated_at: datetime
    provenance: tuple[str, ...]
    integrity: TradeCandidateIntegrity

    def __post_init__(self) -> None:
        for name in ("model_reference_entry_price", "actual_entry_price", "actual_quantity", "actual_exit_price"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(value))
        if (
            self.contract_identity != SPONSOR_POSITION_CONTRACT_ID
            or self.contract_version != CONTRACT_VERSION
            or not _identity(self.sponsor_position_id)
            or not _identity(self.sponsor_decision_id)
            or not _identity(self.candidate_id)
            or not _identity(self.model_trade_id)
            or self.mode not in {SponsorDecisionMode.LIVE, SponsorDecisionMode.PAPER}
            or type(self.state) is not SponsorPositionState
            or not _availability_pair(self.model_reference_entry_availability, self.model_reference_entry_price)
            or not _availability_pair(self.actual_entry_availability, self.actual_entry_price)
            or not _availability_pair(self.actual_quantity_availability, self.actual_quantity)
            or not _availability_pair(self.actual_exit_availability, self.actual_exit_price)
            or type(self.actual_pnl_availability) is not Availability
            or type(self.actual_r_availability) is not Availability
            or (self.evidence_id is not None and not _identity(self.evidence_id))
            or not _aware(self.updated_at)
            or not _identity_tuple(self.provenance)
            or type(self.integrity) is not TradeCandidateIntegrity
        ):
            raise ValueError("SPONSOR_POSITION_INVALID")


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    contract_identity: str
    contract_version: str
    event_id: str
    event_type: LifecycleEventType
    candidate_id: str
    model_trade_id: str | None
    source_domain: str
    source_outcome_id: str
    occurred_at: datetime
    published_at: datetime
    canonical_instrument: str
    product: str
    provenance: tuple[str, ...]
    integrity: TradeCandidateIntegrity

    def __post_init__(self) -> None:
        if (
            self.contract_identity != LIFECYCLE_EVENT_CONTRACT_ID
            or self.contract_version != CONTRACT_VERSION
            or not _identity(self.event_id)
            or type(self.event_type) is not LifecycleEventType
            or not _identity(self.candidate_id)
            or (self.model_trade_id is not None and not _identity(self.model_trade_id))
            or self.source_domain not in {"DOMAIN-004", "DOMAIN-005", "DOMAIN-002"}
            or not _identity(self.source_outcome_id)
            or not _aware(self.occurred_at)
            or not _aware(self.published_at)
            or not self.canonical_instrument
            or not self.product
            or not _identity_tuple(self.provenance)
            or type(self.integrity) is not TradeCandidateIntegrity
        ):
            raise ValueError("LIFECYCLE_EVENT_INVALID")


@dataclass(frozen=True, slots=True)
class StoredStep32Record:
    record_type: str
    record_id: str
    payload: dict[str, object]
    digest: str


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    state: RecoveryState
    reconstructed_model: ObjectiveModelTrade
    reason: str


def candidate_digest(candidate: SwingV1TradeCandidate) -> str:
    return sha256(_canonical_bytes(candidate)).hexdigest()


def create_business_judgment(
    candidate: SwingV1TradeCandidate,
    *,
    validation_identity: str,
    clock: datetime | None = None,
    canonical_instrument_echo: str | None = None,
    product_echo: str | None = None,
    setup_echo: str | None = None,
    direction_echo: str | None = None,
) -> BusinessJudgment:
    _require_candidate(candidate)
    echoes = (
        (canonical_instrument_echo, candidate.canonical_instrument),
        (product_echo, candidate.product),
        (setup_echo, candidate.setup_family),
        (direction_echo, candidate.direction),
    )
    if any(actual is not None and actual != expected for actual, expected in echoes):
        raise ValueError("BUSINESS_JUDGMENT_BOUND_ECHO_MISMATCH")
    digest = candidate_digest(candidate)
    created = clock or datetime.now(UTC)
    identity = _derived_id("BUSINESS-JUDGMENT", candidate.candidate_id, digest, validation_identity)
    return BusinessJudgment(
        BUSINESS_JUDGMENT_CONTRACT_ID,
        CONTRACT_VERSION,
        identity,
        candidate.candidate_id,
        candidate.contract_identity,
        candidate.contract_version,
        digest,
        validation_identity,
        candidate.readiness_identity,
        candidate.run_id,
        candidate.market_data_boundary,
        Freshness.CURRENT,
        TradeCandidateIntegrity.VALID,
        created,
        (candidate.candidate_id, validation_identity, candidate.readiness_identity),
        canonical_instrument_echo,
        product_echo,
        setup_echo,
        direction_echo,
    )


def record_risk_result(
    candidate: SwingV1TradeCandidate,
    judgment: BusinessJudgment,
    state: RiskState,
    *,
    constraints: RiskConstraints | None = None,
    reason: str,
    clock: datetime | None = None,
    valid_until: datetime | None = None,
) -> RiskApproval:
    _require_judgment_binding(candidate, judgment)
    actual_constraints = constraints or RiskConstraints()
    if state is RiskState.CONSTRAINED and not actual_constraints.present:
        raise ValueError("RISK_CONSTRAINT_REQUIRED")
    if state is not RiskState.CONSTRAINED and actual_constraints.present:
        raise ValueError("RISK_CONSTRAINT_NOT_APPLICABLE")
    evaluated = clock or datetime.now(UTC)
    return RiskApproval(
        RISK_APPROVAL_CONTRACT_ID,
        CONTRACT_VERSION,
        _derived_id("RISK-RESULT", judgment.business_judgment_id, state.value, evaluated.isoformat()),
        candidate.candidate_id,
        judgment.candidate_digest,
        judgment.business_judgment_id,
        candidate.run_id,
        state,
        actual_constraints,
        reason,
        evaluated,
        valid_until,
        (judgment.business_judgment_id, candidate.candidate_id, "DOMAIN-007"),
        TradeCandidateIntegrity.VALID,
    )


def start_candidate_lifecycle(
    candidate: SwingV1TradeCandidate,
    risk: RiskApproval,
    *,
    monitoring_binding_id: str,
    clock: datetime | None = None,
) -> CandidateLifecycle:
    _require_risk_binding(candidate, risk)
    if risk.state is RiskState.REJECTED:
        state, reason = CandidateLifecycleState.RISK_REJECTED, "RISK_REJECTED"
    elif risk.state is RiskState.UNAVAILABLE:
        state, reason = CandidateLifecycleState.WAITING_FOR_RISK, "RISK_UNAVAILABLE"
    else:
        state, reason = CandidateLifecycleState.WAITING_FOR_ENTRY, "RISK_PERMITS_ENTRY_MONITORING"
    return CandidateLifecycle(
        candidate.candidate_id,
        risk.candidate_digest,
        monitoring_binding_id,
        state,
        reason,
        clock or datetime.now(UTC),
        risk.risk_result_id,
    )


def transition_candidate_lifecycle(
    lifecycle: CandidateLifecycle,
    state: CandidateLifecycleState,
    *,
    reason: str,
    clock: datetime | None = None,
) -> CandidateLifecycle:
    allowed = {
        CandidateLifecycleState.WAITING_FOR_RISK: {CandidateLifecycleState.WAITING_FOR_ENTRY, CandidateLifecycleState.RISK_REJECTED, CandidateLifecycleState.STALE},
        CandidateLifecycleState.WAITING_FOR_ENTRY: {CandidateLifecycleState.STALE, CandidateLifecycleState.PRE_ENTRY_INVALIDATED, CandidateLifecycleState.RISK_REJECTED, CandidateLifecycleState.RECONCILIATION_REQUIRED_PRE_ENTRY},
    }
    if state not in allowed.get(lifecycle.state, set()):
        raise ValueError("CANDIDATE_LIFECYCLE_TRANSITION_INVALID")
    return CandidateLifecycle(
        lifecycle.candidate_id,
        lifecycle.candidate_digest,
        lifecycle.monitoring_binding_id,
        state,
        reason,
        clock or datetime.now(UTC),
        lifecycle.risk_result_id,
    )


def record_sponsor_decision(
    candidate: SwingV1TradeCandidate,
    risk: RiskApproval,
    lifecycle: CandidateLifecycle,
    mode: SponsorDecisionMode,
    *,
    previous: SponsorDecision | None = None,
    entry_outcome: EntryOutcome | None = None,
    clock: datetime | None = None,
) -> SponsorDecision:
    _require_risk_binding(candidate, risk)
    if (
        lifecycle.candidate_id != candidate.candidate_id
        or lifecycle.risk_result_id != risk.risk_result_id
        or (
            entry_outcome is not None
            and entry_outcome.state is EntryOutcomeState.ENTRY_TRIGGERED
        )
        or lifecycle.state not in {
            CandidateLifecycleState.WAITING_FOR_RISK,
            CandidateLifecycleState.WAITING_FOR_ENTRY,
        }
    ):
        raise ValueError("SPONSOR_DECISION_WINDOW_CLOSED")
    revision = 1
    if previous is not None:
        if previous.candidate_id != candidate.candidate_id or previous.frozen:
            raise ValueError("SPONSOR_DECISION_REVISION_INVALID")
        revision = previous.revision + 1
    decided = clock or datetime.now(UTC)
    return SponsorDecision(
        SPONSOR_DECISION_CONTRACT_ID,
        CONTRACT_VERSION,
        _derived_id("SPONSOR-DECISION", candidate.candidate_id, str(revision), mode.value),
        candidate.candidate_id,
        risk.candidate_digest,
        candidate.run_id,
        risk.risk_result_id,
        revision,
        mode,
        decided,
        False,
        (candidate.candidate_id, risk.risk_result_id, "SPONSOR"),
        TradeCandidateIntegrity.VALID,
    )


def freeze_sponsor_decision(decision: SponsorDecision) -> SponsorDecision:
    payload = asdict(decision)
    payload["frozen"] = True
    payload["mode"] = decision.mode
    payload["integrity"] = decision.integrity
    payload["provenance"] = decision.provenance
    return SponsorDecision(**payload)


def record_sponsor_order_evidence(
    update: ProviderOrderUpdateEvidence,
    candidate: SwingV1TradeCandidate,
    decision: SponsorDecision,
) -> SponsorOrderEvidence:
    """Bind optional order evidence without touching objective-model state."""

    _require_candidate(candidate)
    if (
        type(update) is not ProviderOrderUpdateEvidence
        or decision.candidate_id != candidate.candidate_id
        or decision.mode is not SponsorDecisionMode.LIVE
        or update.instrument.name not in {
            candidate.canonical_instrument,
            "",
        }
        and update.instrument.trading_symbol != candidate.canonical_instrument
    ):
        raise ValueError("SPONSOR_ORDER_EVIDENCE_BINDING_INVALID")
    expected_side = "BUY" if candidate.direction == "LONG" else "SELL"
    if update.side != expected_side:
        raise ValueError("SPONSOR_ORDER_EVIDENCE_SIDE_INVALID")
    availability = (
        Availability.AVAILABLE
        if update.average_price is not None
        else Availability.UNAVAILABLE
    )
    return SponsorOrderEvidence(
        _derived_id(
            "SPONSOR-ORDER-EVIDENCE",
            decision.sponsor_decision_id,
            update.order_id,
            update.observed_at.isoformat(),
        ),
        update.order_id,
        decision.sponsor_decision_id,
        candidate.candidate_id,
        candidate.canonical_instrument,
        update.status,
        update.side,
        update.filled_quantity,
        availability,
        update.average_price,
        update.observed_at,
        (
            update.source,
            update.order_id,
            decision.sponsor_decision_id,
            "SPONSOR_POSITION_ONLY",
        ),
    )


def build_monitoring_submission(
    tick: ProviderMarketTick,
    *,
    submission_id: str,
    candidate_id: str,
    monitoring_binding_id: str,
    model_trade_id: str | None,
    product: str,
    direction: str,
    submission_type: MonitoringSubmissionType,
    reference: str,
    boundary: datetime,
    timeframe: str,
    session_identity: str,
    canonical_instrument: str | None = None,
) -> MonitoringSubmission:
    """Bind one provider-neutral Kite tick to an untrusted lifecycle submission."""

    if type(tick) is not ProviderMarketTick:
        raise ValueError("MONITORING_TICK_INVALID")
    if submission_type is MonitoringSubmissionType.DAILY_BOUNDARY_CLOSED:
        raise ValueError("COMPLETED_DAILY_SOURCE_REQUIRED")
    payload: dict[str, object] = {
        "submission_id": submission_id,
        "candidate_id": candidate_id,
        "monitoring_binding_id": monitoring_binding_id,
        "model_trade_id": model_trade_id,
        "canonical_instrument": canonical_instrument
        or tick.instrument.name
        or tick.instrument.trading_symbol,
        "provider_instrument": f"{tick.instrument.exchange}:{tick.instrument.trading_symbol}",
        "product": product,
        "direction": direction,
        "submission_type": submission_type,
        "observed_price_availability": Availability.UNAVAILABLE
        if submission_type is MonitoringSubmissionType.DATA_UNAVAILABLE
        else Availability.AVAILABLE,
        "observed_price": None
        if submission_type is MonitoringSubmissionType.DATA_UNAVAILABLE
        else tick.last_price,
        "reference": reference,
        "observed_at": tick.observed_at,
        "boundary": boundary,
        "timeframe": timeframe,
        "session_identity": session_identity,
        "source": tick.source,
        "source_connection_id": tick.connection_id,
        "source_provenance": (
            tick.source,
            tick.connection_id,
            "PROVIDER_ADAPTER",
        ),
        "source_sequence": tick.source_sequence,
        "previous_interval_available": tick.previous_interval_available,
        "session_continuous": tick.session_continuous,
        "ordering_deterministic": tick.ordering_deterministic,
    }
    payload.setdefault("contract_identity", MONITORING_SUBMISSION_CONTRACT_ID)
    payload.setdefault("contract_version", CONTRACT_VERSION)
    payload["payload_digest"] = "0" * 64
    provisional = MonitoringSubmission(**payload)  # type: ignore[arg-type]
    payload["payload_digest"] = sha256(_canonical_bytes(provisional, omit={"payload_digest"})).hexdigest()
    return MonitoringSubmission(**payload)  # type: ignore[arg-type]


def build_completed_daily_submission(
    candle: HistoricalCandle,
    instrument: object,
    *,
    submission_id: str,
    candidate_id: str,
    monitoring_binding_id: str,
    model_trade_id: str,
    product: str,
    direction: str,
    reference: str,
    boundary: datetime,
    session_identity: str,
    source_request_id: str,
) -> MonitoringSubmission:
    """Build completed-Daily factual evidence from Provider historical data."""

    from kronos.provider.contracts.instrument import InstrumentRecord

    if type(candle) is not HistoricalCandle or type(instrument) is not InstrumentRecord:
        raise ValueError("COMPLETED_DAILY_EVIDENCE_INVALID")
    payload: dict[str, object] = {
        "contract_identity": MONITORING_SUBMISSION_CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "submission_id": submission_id,
        "candidate_id": candidate_id,
        "monitoring_binding_id": monitoring_binding_id,
        "model_trade_id": model_trade_id,
        "canonical_instrument": instrument.name or instrument.trading_symbol,
        "provider_instrument": f"{instrument.exchange}:{instrument.trading_symbol}",
        "product": product,
        "direction": direction,
        "submission_type": MonitoringSubmissionType.DAILY_BOUNDARY_CLOSED,
        "observed_price_availability": Availability.AVAILABLE,
        "observed_price": Decimal(str(candle.close)),
        "reference": reference,
        "observed_at": candle.timestamp,
        "boundary": boundary,
        "timeframe": "DAILY",
        "session_identity": session_identity,
        "source": "KITE_CONNECT_HISTORICAL",
        "source_connection_id": source_request_id,
        "source_provenance": (
            "KITE_CONNECT_HISTORICAL",
            source_request_id,
            "COMPLETED_DAILY",
            "PROVIDER_ADAPTER",
        ),
        "source_sequence": None,
        "previous_interval_available": True,
        "session_continuous": True,
        "ordering_deterministic": True,
        "payload_digest": "0" * 64,
    }
    provisional = MonitoringSubmission(**payload)  # type: ignore[arg-type]
    payload["payload_digest"] = sha256(
        _canonical_bytes(provisional, omit={"payload_digest"})
    ).hexdigest()
    return MonitoringSubmission(**payload)  # type: ignore[arg-type]


class MonitoringAdmissionRegistry:
    """Local deterministic admission; this is not a network ingress."""

    def __init__(self) -> None:
        self._accepted: dict[str, MonitoringObservation] = {}

    def admit(
        self,
        submission: MonitoringSubmission,
        context: MonitoringAdmissionContext,
        *,
        clock: datetime | None = None,
    ) -> MonitoringObservation:
        expected = (
            (submission.candidate_id, context.candidate_id),
            (submission.monitoring_binding_id, context.monitoring_binding_id),
            (submission.model_trade_id, context.model_trade_id),
            (submission.canonical_instrument, context.canonical_instrument),
            (submission.provider_instrument, context.provider_instrument),
            (submission.product, context.product),
            (submission.direction, context.direction),
            (submission.source, context.provider_source),
            (submission.source_connection_id, context.source_connection_id),
            (submission.boundary, context.boundary),
            (submission.timeframe, context.timeframe),
            (submission.session_identity, context.session_identity),
        )
        if not context.binding_active or any(actual != wanted for actual, wanted in expected):
            raise ValueError("MONITORING_BINDING_REJECTED")
        calculated = sha256(_canonical_bytes(submission, omit={"payload_digest"})).hexdigest()
        if calculated != submission.payload_digest:
            raise ValueError("MONITORING_SUBMISSION_DIGEST_INVALID")
        previous = self._accepted.get(submission.submission_id)
        if previous is not None:
            if previous.source_payload_digest != submission.payload_digest:
                raise ValueError("MONITORING_SUBMISSION_CONFLICT")
            return previous
        admitted = clock or datetime.now(UTC)
        observation = MonitoringObservation(
            MONITORING_OBSERVATION_CONTRACT_ID,
            CONTRACT_VERSION,
            _derived_id("OBSERVATION", submission.submission_id, submission.payload_digest),
            submission.submission_id,
            submission.payload_digest,
            submission.candidate_id,
            submission.monitoring_binding_id,
            submission.model_trade_id,
            submission.canonical_instrument,
            submission.provider_instrument,
            submission.product,
            submission.direction,
            submission.submission_type,
            submission.observed_price_availability,
            submission.observed_price,
            submission.observed_at,
            admitted,
            submission.boundary,
            submission.timeframe,
            submission.session_identity,
            submission.source_sequence,
            submission.previous_interval_available,
            submission.session_continuous,
            submission.ordering_deterministic,
            (
                submission.submission_id,
                submission.source,
                submission.source_connection_id,
                "DOMAIN-002",
            ),
            Freshness.CURRENT,
            TradeCandidateIntegrity.VALID,
        )
        self._accepted[submission.submission_id] = observation
        return observation


def evaluate_entry_timing(
    candidate: SwingV1TradeCandidate,
    risk: RiskApproval,
    lifecycle: CandidateLifecycle,
    previous: MonitoringObservation | None,
    current: MonitoringObservation,
    *,
    clock: datetime | None = None,
) -> EntryOutcome:
    _require_risk_binding(candidate, risk)
    occurred = clock or current.observed_at
    if (
        not risk.permits_entry
        or lifecycle.state is not CandidateLifecycleState.WAITING_FOR_ENTRY
        or (risk.valid_until is not None and occurred > risk.valid_until)
    ):
        raise ValueError("ENTRY_TIMING_NOT_PERMITTED")
    if current.candidate_id != candidate.candidate_id or current.monitoring_binding_id != lifecycle.monitoring_binding_id:
        raise ValueError("ENTRY_TIMING_BINDING_INVALID")
    entry = _required_price(candidate.entry_price)
    if current.observation_type is not MonitoringSubmissionType.ENTRY_LEVEL_CROSSED or (
        previous is not None
        and previous.observation_type is not MonitoringSubmissionType.ENTRY_LEVEL_CROSSED
    ):
        raise ValueError("ENTRY_TIMING_OBSERVATION_TYPE_INVALID")
    current_beyond = _at_or_beyond(current.observed_price, entry, candidate.direction)
    source_ids = (current.observation_id,) if previous is None else (previous.observation_id, current.observation_id)
    if previous is None:
        return _entry_outcome(candidate, risk, lifecycle, EntryOutcomeState.RECONCILIATION_REQUIRED_PRE_ENTRY if current_beyond else EntryOutcomeState.ENTRY_NOT_TRIGGERED, Availability.UNAVAILABLE, None, source_ids, occurred, "FIRST_OBSERVATION_BEYOND_ENTRY" if current_beyond else "ENTRY_NOT_TRIGGERED")
    if previous.candidate_id != current.candidate_id or previous.monitoring_binding_id != current.monitoring_binding_id:
        raise ValueError("ENTRY_TIMING_OBSERVATION_BINDING_INVALID")
    ordered = previous.observed_at < current.observed_at and (previous.source_sequence is None or current.source_sequence is None or previous.source_sequence < current.source_sequence)
    continuous = current.previous_interval_available and current.session_continuous
    deterministic = previous.ordering_deterministic and current.ordering_deterministic and ordered
    if current_beyond and (not continuous or not deterministic):
        return _entry_outcome(candidate, risk, lifecycle, EntryOutcomeState.RECONCILIATION_REQUIRED_PRE_ENTRY, Availability.UNAVAILABLE, None, source_ids, occurred, "ENTRY_SEQUENCE_UNAVAILABLE")
    previous_pre_side = _pre_entry_side(previous.observed_price, entry, candidate.direction)
    if current_beyond and not previous_pre_side:
        return _entry_outcome(candidate, risk, lifecycle, EntryOutcomeState.RECONCILIATION_REQUIRED_PRE_ENTRY, Availability.UNAVAILABLE, None, source_ids, occurred, "ENTRY_PRECEDING_SIDE_NOT_PROVEN")
    if previous_pre_side and current_beyond:
        return _entry_outcome(candidate, risk, lifecycle, EntryOutcomeState.ENTRY_TRIGGERED, Availability.AVAILABLE, entry, source_ids, occurred, "CONSECUTIVE_ACCEPTED_OBSERVATIONS_PROVE_ENTRY")
    return _entry_outcome(candidate, risk, lifecycle, EntryOutcomeState.ENTRY_NOT_TRIGGERED, Availability.UNAVAILABLE, None, source_ids, occurred, "ENTRY_NOT_TRIGGERED")


def activate_objective_model(
    candidate: SwingV1TradeCandidate,
    risk: RiskApproval,
    outcome: EntryOutcome,
) -> ObjectiveModelTrade:
    _require_risk_binding(candidate, risk)
    if outcome.state is not EntryOutcomeState.ENTRY_TRIGGERED or outcome.model_reference_entry_price != candidate.entry_price:
        raise ValueError("OBJECTIVE_MODEL_ACTIVATION_INVALID")
    if outcome.candidate_id != candidate.candidate_id or outcome.risk_result_id != risk.risk_result_id:
        raise ValueError("OBJECTIVE_MODEL_BINDING_INVALID")
    return ObjectiveModelTrade(
        _derived_id("MODEL-TRADE", candidate.candidate_id, outcome.entry_outcome_id),
        candidate.candidate_id,
        risk.candidate_digest,
        outcome.monitoring_binding_id,
        risk.risk_result_id,
        outcome.entry_outcome_id,
        candidate.canonical_instrument,
        candidate.product,
        candidate.direction,
        candidate.setup_family,
        _required_price(candidate.entry_price),
        _required_price(candidate.stop_price),
        _required_price(candidate.invalidation_level_or_reference),
        candidate.invalidation_condition,
        _required_price(candidate.target_price),
        ObjectiveModelState.ACTIVE,
        None,
        Availability.UNAVAILABLE,
        None,
        outcome.occurred_at,
        outcome.occurred_at,
        outcome.source_observation_ids,
        TradeCandidateIntegrity.VALID,
    )


def evaluate_objective_model(
    model: ObjectiveModelTrade,
    observations: tuple[MonitoringObservation, ...],
    *,
    irrecoverable_ambiguity: bool = False,
) -> ObjectiveModelTrade:
    if model.state is ObjectiveModelState.CLOSED:
        raise ValueError("OBJECTIVE_MODEL_ALREADY_CLOSED")
    applicable = tuple(item for item in observations if item.candidate_id == model.candidate_id and item.monitoring_binding_id == model.monitoring_binding_id and item.model_trade_id in {None, model.model_trade_id})
    if len(applicable) != len(observations):
        raise ValueError("OBJECTIVE_MODEL_OBSERVATION_BINDING_INVALID")
    if not applicable:
        return model
    ordered = sorted(applicable, key=lambda item: (item.observed_at, item.source_sequence if item.source_sequence is not None else -1, item.observation_id))
    if any(not item.previous_interval_available or not item.ordering_deterministic for item in ordered):
        return _reconcile_or_close(model, ordered, irrecoverable_ambiguity, "OUTCOME_CRITICAL_INTERVAL_UNAVAILABLE")
    for index, item in enumerate(ordered):
        same_time = tuple(other for other in ordered if other.observed_at == item.observed_at)
        kinds = {other.observation_type for other in same_time}
        has_authoritative_order = all(
            other.source_sequence is not None for other in same_time
        ) and len({other.source_sequence for other in same_time}) == len(same_time)
        if (
            {MonitoringSubmissionType.STOP_LEVEL_CROSSED, MonitoringSubmissionType.TARGET_LEVEL_CROSSED}
            <= kinds
            and not has_authoritative_order
        ):
            return _reconcile_or_close(model, ordered, irrecoverable_ambiguity, "STOP_TARGET_ORDER_AMBIGUOUS")
        if item.observation_type is MonitoringSubmissionType.DATA_UNAVAILABLE:
            return _reconcile_or_close(model, ordered[: index + 1], irrecoverable_ambiguity, "DATA_UNAVAILABLE")
        if item.observation_type is MonitoringSubmissionType.STOP_LEVEL_CROSSED:
            return _close_model(model, ModelCloseReason.STOP, item.observed_price_availability, item.observed_price, ordered[: index + 1])
        if item.observation_type is MonitoringSubmissionType.TARGET_LEVEL_CROSSED:
            return _close_model(model, ModelCloseReason.TARGET, Availability.AVAILABLE, model.target_price, ordered[: index + 1])
        if item.observation_type is MonitoringSubmissionType.DAILY_BOUNDARY_CLOSED and _invalidated(model, item.observed_price):
            return _close_model(model, ModelCloseReason.ANALYTICAL_INVALIDATION, item.observed_price_availability, item.observed_price, ordered[: index + 1])
    last = ordered[-1]
    return _replace_model(model, updated_at=last.observed_at, source_observation_ids=model.source_observation_ids + tuple(item.observation_id for item in ordered))


def create_sponsor_position(
    decision: SponsorDecision,
    candidate: SwingV1TradeCandidate,
    risk: RiskApproval,
    model: ObjectiveModelTrade,
    *,
    actual_evidence: SponsorExecutionEvidence | None = None,
    clock: datetime | None = None,
) -> SponsorPosition:
    _require_risk_binding(candidate, risk)
    if decision.mode is SponsorDecisionMode.IGNORE:
        raise ValueError("SPONSOR_POSITION_NOT_APPLICABLE")
    if decision.candidate_id != candidate.candidate_id or model.candidate_id != candidate.candidate_id:
        raise ValueError("SPONSOR_POSITION_BINDING_INVALID")
    updated = clock or model.updated_at
    if decision.mode is SponsorDecisionMode.PAPER:
        state = SponsorPositionState.ACTIVE
        actual_entry_availability = Availability.UNAVAILABLE
        actual_entry = None
        quantity_availability = Availability.UNAVAILABLE
        quantity = None
        evidence_id = None
    elif actual_evidence is None:
        state = SponsorPositionState.PLANNED
        actual_entry_availability = Availability.UNAVAILABLE
        actual_entry = None
        quantity_availability = Availability.UNAVAILABLE
        quantity = None
        evidence_id = None
    else:
        maximum_quantity = risk.constraints.maximum_quantity
        if maximum_quantity is not None and actual_evidence.actual_quantity > maximum_quantity:
            raise ValueError("SPONSOR_QUANTITY_EXCEEDS_RISK_CONSTRAINT")
        state = SponsorPositionState.ACTIVE
        actual_entry_availability = Availability.AVAILABLE
        actual_entry = actual_evidence.actual_entry_price
        quantity_availability = Availability.AVAILABLE
        quantity = actual_evidence.actual_quantity
        evidence_id = actual_evidence.evidence_id
    return SponsorPosition(
        SPONSOR_POSITION_CONTRACT_ID,
        CONTRACT_VERSION,
        _derived_id("SPONSOR-POSITION", decision.sponsor_decision_id, model.model_trade_id),
        decision.sponsor_decision_id,
        candidate.candidate_id,
        model.model_trade_id,
        decision.mode,
        state,
        Availability.AVAILABLE,
        model.entry_price,
        actual_entry_availability,
        actual_entry,
        quantity_availability,
        quantity,
        Availability.UNAVAILABLE,
        None,
        Availability.UNAVAILABLE,
        Availability.UNAVAILABLE,
        evidence_id,
        updated,
        (decision.sponsor_decision_id, model.model_trade_id, evidence_id or "NO-ACTUAL-EVIDENCE"),
        TradeCandidateIntegrity.VALID,
    )


def project_paper_position_closure(
    position: SponsorPosition,
    model: ObjectiveModelTrade,
    *,
    clock: datetime | None = None,
) -> SponsorPosition:
    if (
        position.mode is not SponsorDecisionMode.PAPER
        or position.model_trade_id != model.model_trade_id
        or model.state is not ObjectiveModelState.CLOSED
    ):
        raise ValueError("PAPER_POSITION_PROJECTION_INVALID")
    values = {field.name: getattr(position, field.name) for field in fields(position)}
    values.update(
        state=SponsorPositionState.CLOSED,
        updated_at=clock or model.updated_at,
        actual_exit_availability=Availability.UNAVAILABLE,
        actual_exit_price=None,
        actual_pnl_availability=Availability.UNAVAILABLE,
        actual_r_availability=Availability.UNAVAILABLE,
    )
    return SponsorPosition(**values)  # type: ignore[arg-type]


def publish_lifecycle_event(
    source: EntryOutcome | ObjectiveModelTrade | MonitoringObservation,
    *,
    canonical_instrument: str,
    product: str,
    clock: datetime | None = None,
) -> LifecycleEvent:
    if type(source) is EntryOutcome and source.state is EntryOutcomeState.ENTRY_TRIGGERED:
        event_type, domain, source_id, model_id = LifecycleEventType.ENTRY_TRIGGERED, "DOMAIN-004", source.entry_outcome_id, None
        occurred = source.occurred_at
        candidate_id = source.candidate_id
    elif type(source) is ObjectiveModelTrade and source.state is ObjectiveModelState.CLOSED:
        event_type, domain, source_id, model_id = LifecycleEventType.MODEL_TRADE_CLOSED, "DOMAIN-005", source.model_trade_id, source.model_trade_id
        occurred = source.updated_at
        candidate_id = source.candidate_id
    elif type(source) is ObjectiveModelTrade and source.state is ObjectiveModelState.RECONCILIATION_REQUIRED:
        event_type, domain, source_id, model_id = LifecycleEventType.RECONCILIATION_REQUIRED, "DOMAIN-005", source.model_trade_id, source.model_trade_id
        occurred = source.updated_at
        candidate_id = source.candidate_id
    elif type(source) is MonitoringObservation and source.observation_type is MonitoringSubmissionType.DATA_UNAVAILABLE:
        event_type, domain, source_id, model_id = LifecycleEventType.DATA_UNAVAILABLE, "DOMAIN-002", source.observation_id, source.model_trade_id
        occurred = source.observed_at
        candidate_id = source.candidate_id
    else:
        raise ValueError("LIFECYCLE_EVENT_SOURCE_NOT_AUTHORITATIVE")
    published = clock or datetime.now(UTC)
    return LifecycleEvent(
        LIFECYCLE_EVENT_CONTRACT_ID,
        CONTRACT_VERSION,
        _derived_id("LIFECYCLE-EVENT", source_id, event_type.value),
        event_type,
        candidate_id,
        model_id,
        domain,
        source_id,
        occurred,
        published,
        canonical_instrument,
        product,
        (source_id, domain),
        TradeCandidateIntegrity.VALID,
    )


def publish_live_action_required(
    model: ObjectiveModelTrade,
    position: SponsorPosition,
    *,
    clock: datetime | None = None,
) -> LifecycleEvent:
    if (
        model.state is not ObjectiveModelState.CLOSED
        or position.mode is not SponsorDecisionMode.LIVE
        or position.model_trade_id != model.model_trade_id
    ):
        raise ValueError("LIVE_ACTION_EVENT_SOURCE_INVALID")
    published = clock or datetime.now(UTC)
    return LifecycleEvent(
        LIFECYCLE_EVENT_CONTRACT_ID,
        CONTRACT_VERSION,
        _derived_id("LIFECYCLE-EVENT", model.model_trade_id, LifecycleEventType.LIVE_ACTION_REQUIRED.value),
        LifecycleEventType.LIVE_ACTION_REQUIRED,
        model.candidate_id,
        model.model_trade_id,
        "DOMAIN-005",
        model.model_trade_id,
        model.updated_at,
        published,
        model.canonical_instrument,
        model.product,
        (model.model_trade_id, position.sponsor_position_id, "SPONSOR-ACTION-ONLY"),
        TradeCandidateIntegrity.VALID,
    )


class LocalStep32Store:
    """Immutable local contract retention; no public ingress or broker state."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or root in {Path("/"), Path("/private/tmp")}:
            raise ValueError("STEP32_STORE_ROOT_INVALID")
        self._root = root

    def retain(self, record: object) -> Path:
        if not is_dataclass(record):
            raise ValueError("STEP32_RECORD_INVALID")
        record_type = type(record).__name__
        record_id = _record_id(record)
        payload = _json_value(record)
        digest = sha256(_canonical_bytes(payload)).hexdigest()
        envelope = {"record_type": record_type, "record_id": record_id, "payload": payload, "digest": digest}
        encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        path = self._root / record_type / f"{record_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists():
            if path.read_text(encoding="utf-8") != encoded:
                raise ValueError("STEP32_IMMUTABLE_RECORD_CONFLICT")
            return path
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return path

    def load(self, record_type: str, record_id: str) -> StoredStep32Record:
        path = self._root / record_type / f"{record_id}.json"
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if envelope.get("record_type") != record_type or envelope.get("record_id") != record_id:
            raise ValueError("STEP32_STORED_BINDING_INVALID")
        payload = envelope.get("payload")
        digest = envelope.get("digest")
        if not isinstance(payload, dict) or not _digest(digest) or sha256(_canonical_bytes(payload)).hexdigest() != digest:
            raise ValueError("STEP32_STORED_INTEGRITY_INVALID")
        return StoredStep32Record(record_type, record_id, payload, digest)


def recover_objective_model(
    candidate: SwingV1TradeCandidate,
    risk: RiskApproval,
    outcome: EntryOutcome,
    observations: tuple[MonitoringObservation, ...],
    stored_projection: ObjectiveModelTrade,
) -> RecoveryResult:
    reconstructed = evaluate_objective_model(activate_objective_model(candidate, risk, outcome), observations)
    if _canonical_bytes(reconstructed) == _canonical_bytes(stored_projection):
        return RecoveryResult(RecoveryState.RECOVERED, reconstructed, "REPLAY_MATCHES_STORED_PROJECTION")
    reconciled = _replace_model(reconstructed, state=ObjectiveModelState.RECONCILIATION_REQUIRED, close_reason=None, exit_price_availability=Availability.UNAVAILABLE, exit_price=None)
    return RecoveryResult(RecoveryState.RECONCILIATION_REQUIRED, reconciled, "RESTART_RECONSTRUCTION_MISMATCH")


def _entry_outcome(candidate: SwingV1TradeCandidate, risk: RiskApproval, lifecycle: CandidateLifecycle, state: EntryOutcomeState, availability: Availability, price: Decimal | None, source_ids: tuple[str, ...], occurred: datetime, reason: str) -> EntryOutcome:
    return EntryOutcome(
        _derived_id("ENTRY-OUTCOME", candidate.candidate_id, lifecycle.monitoring_binding_id, state.value, occurred.isoformat()),
        candidate.candidate_id,
        risk.candidate_digest,
        lifecycle.monitoring_binding_id,
        risk.risk_result_id,
        state,
        availability,
        price,
        source_ids,
        occurred,
        reason,
        TradeCandidateIntegrity.VALID,
    )


def _close_model(model: ObjectiveModelTrade, reason: ModelCloseReason, availability: Availability, price: Decimal | None, observations: list[MonitoringObservation]) -> ObjectiveModelTrade:
    return _replace_model(
        model,
        state=ObjectiveModelState.CLOSED,
        close_reason=reason,
        exit_price_availability=availability,
        exit_price=price,
        updated_at=observations[-1].observed_at,
        source_observation_ids=model.source_observation_ids + tuple(item.observation_id for item in observations),
    )


def _reconcile_or_close(model: ObjectiveModelTrade, observations: list[MonitoringObservation], irrecoverable: bool, reason: str) -> ObjectiveModelTrade:
    if irrecoverable:
        return _close_model(model, ModelCloseReason.OUTCOME_UNRESOLVED, Availability.UNAVAILABLE, None, observations)
    return _replace_model(
        model,
        state=ObjectiveModelState.RECONCILIATION_REQUIRED,
        close_reason=None,
        exit_price_availability=Availability.UNAVAILABLE,
        exit_price=None,
        updated_at=observations[-1].observed_at,
        source_observation_ids=model.source_observation_ids + tuple(item.observation_id for item in observations),
    )


def _replace_model(model: ObjectiveModelTrade, **changes: object) -> ObjectiveModelTrade:
    values = {field.name: getattr(model, field.name) for field in fields(model)}
    values.update(changes)
    return ObjectiveModelTrade(**values)  # type: ignore[arg-type]


def _invalidated(model: ObjectiveModelTrade, price: Decimal | None) -> bool:
    if price is None:
        return False
    if model.invalidation_condition.endswith("BELOW_PULLBACK_STRUCTURAL_LOW"):
        return price < model.invalidation_level
    if model.invalidation_condition.endswith("ABOVE_PULLBACK_STRUCTURAL_HIGH"):
        return price > model.invalidation_level
    if model.invalidation_condition.endswith("AT_OR_BELOW_ORIGINAL_RANGE_HIGH"):
        return price <= model.invalidation_level
    if model.invalidation_condition.endswith("AT_OR_ABOVE_ORIGINAL_RANGE_LOW"):
        return price >= model.invalidation_level
    raise ValueError("MODEL_INVALIDATION_CONDITION_UNSUPPORTED")


def _require_candidate(candidate: SwingV1TradeCandidate) -> None:
    if (
        type(candidate) is not SwingV1TradeCandidate
        or candidate.construction_status is not TradeConstructionStatus.COMPLETE
        or candidate.viability_status is not TradeViabilityStatus.VIABLE
        or candidate.integrity_status is not TradeCandidateIntegrity.VALID
        or candidate.staleness_status is not TradeCandidateStaleness.CURRENT
    ):
        raise ValueError("STEP32_CANDIDATE_INELIGIBLE")


def _require_judgment_binding(candidate: SwingV1TradeCandidate, judgment: BusinessJudgment) -> None:
    _require_candidate(candidate)
    if judgment.candidate_id != candidate.candidate_id or judgment.candidate_digest != candidate_digest(candidate) or judgment.run_id != candidate.run_id or judgment.integrity is not TradeCandidateIntegrity.VALID or judgment.freshness is not Freshness.CURRENT:
        raise ValueError("BUSINESS_JUDGMENT_BINDING_INVALID")


def _require_risk_binding(candidate: SwingV1TradeCandidate, risk: RiskApproval) -> None:
    _require_candidate(candidate)
    if risk.candidate_id != candidate.candidate_id or risk.candidate_digest != candidate_digest(candidate) or risk.run_id != candidate.run_id or risk.integrity is not TradeCandidateIntegrity.VALID:
        raise ValueError("RISK_BINDING_INVALID")


def _pre_entry_side(value: Decimal | None, entry: Decimal, direction: str) -> bool:
    return value is not None and (value < entry if direction == "LONG" else value > entry)


def _at_or_beyond(value: Decimal | None, entry: Decimal, direction: str) -> bool:
    return value is not None and (value >= entry if direction == "LONG" else value <= entry)


def _required_price(value: Decimal | None) -> Decimal:
    if value is None:
        raise ValueError("REQUIRED_PRICE_UNAVAILABLE")
    return _decimal(value)


def _record_id(record: object) -> str:
    for name in (
        "business_judgment_id", "risk_result_id", "sponsor_decision_id",
        "candidate_id", "submission_id", "observation_id", "entry_outcome_id",
        "model_trade_id", "sponsor_position_id", "event_id",
    ):
        value = getattr(record, name, None)
        if _identity(value):
            return str(value)
    raise ValueError("STEP32_RECORD_ID_UNAVAILABLE")


def _derived_id(prefix: str, *parts: str) -> str:
    return f"{prefix}-{sha256('|'.join(parts).encode()).hexdigest()}"


def _canonical_bytes(value: object, *, omit: set[str] | None = None) -> bytes:
    normalized = _json_value(value, omit=omit or set())
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _json_value(value: object, *, omit: set[str] | None = None) -> Any:
    omitted = omit or set()
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name), omit=omitted) for field in fields(value) if field.name not in omitted}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item, omit=omitted) for item in value]
    if isinstance(value, list):
        return [_json_value(item, omit=omitted) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item, omit=omitted) for key, item in value.items() if str(key) not in omitted}
    return value


def _decimal(value: object) -> Decimal:
    try:
        result = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("DECIMAL_VALUE_INVALID") from exc
    if not result.is_finite():
        raise ValueError("DECIMAL_VALUE_INVALID")
    return result


def _availability_pair(availability: Availability, value: object | None) -> bool:
    return type(availability) is Availability and ((availability is Availability.AVAILABLE) == (value is not None))


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _identity(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:@|+/-]{1,512}", value) is not None


def _identity_tuple(value: object, *, allow_empty: bool = False) -> bool:
    return type(value) is tuple and (allow_empty or bool(value)) and all(_identity(item) for item in value)


def _reason(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Z0-9_]{1,256}", value) is not None


__all__ = [
    "Availability", "BusinessJudgment", "CandidateLifecycle",
    "CandidateLifecycleState", "EntryOutcome", "EntryOutcomeState",
    "Freshness", "LifecycleEvent", "LifecycleEventType", "LocalStep32Store",
    "ModelCloseReason", "MonitoringAdmissionContext", "MonitoringAdmissionRegistry",
    "MonitoringObservation", "MonitoringSubmission", "MonitoringSubmissionType",
    "ObjectiveModelState", "ObjectiveModelTrade", "RecoveryResult", "RecoveryState",
    "RiskApproval", "RiskConstraints", "RiskState", "SponsorDecision",
    "SponsorDecisionMode", "SponsorExecutionEvidence", "SponsorPosition",
    "SponsorPositionState", "STEP32_OPERATIONAL_AUTHORITY", "activate_objective_model",
    "build_monitoring_submission", "candidate_digest", "create_business_judgment",
    "create_sponsor_position", "evaluate_entry_timing", "evaluate_objective_model",
    "freeze_sponsor_decision", "publish_lifecycle_event", "record_risk_result",
    "project_paper_position_closure", "publish_live_action_required",
    "record_sponsor_decision", "recover_objective_model", "start_candidate_lifecycle",
    "transition_candidate_lifecycle",
]
