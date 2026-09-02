"""Immutable persistence contracts and store for Intraday WO-15D.

This module follows the commissioned WO-13/WO-14 evidence-store pattern.  It
does not evaluate timing, acquire market data, expose Browser/runtime controls,
or grant Sponsor, execution, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from typing import Mapping, Sequence
from uuid import uuid4

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    SemanticDirection,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo15 import (
    WO15_CONTRACT_VERSION,
    Wo15ContractError,
    Wo15CycleEvaluation,
    Wo15ExpiryCause,
    Wo15FiveMinuteEvidence,
    Wo15PolicyBinding,
    Wo15ProgressionEvidence,
    Wo15ProgressionSemantics,
    Wo15QualificationPath,
    Wo15SessionBinding,
    Wo15SessionDisposition,
    Wo15TimingCycle,
    Wo15TimingObservation,
    Wo15TimingState,
    Wo15TimingTransition,
    Wo15TrustFailure,
    Wo15Wo13Handoff,
)
from kronos.intraday.wo15_handoff import Wo15TimingHandoff
from kronos.intraday.wo15_telemetry import (
    Wo15Atr14Observation,
    Wo15AtrUnavailableReason,
    Wo15LatencyTelemetry,
    Wo15ResearchLocality,
    Wo15ResearchReference,
    Wo15ResearchRole,
    Wo15ResearchTelemetry,
    Wo15TelemetryAvailability,
    Wo15TelemetryCandle,
)
from kronos.intraday.wo15_timing import (
    Wo15ExpiryEvent,
    Wo15ResetAssessment,
    Wo15ResetDisposition,
    Wo15TimingCause,
    Wo15TimingEvaluationResult,
    Wo15TimingLocalHistory,
)


DEFAULT_WO15_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "intraday-v1" / "wo15-entry-timing-v1"
)

WO15_OPERATION_REQUEST_IDENTITY = "KRONOS-INTRADAY-WO15-OPERATION-REQUEST-V1"
WO15_OPERATION_PROVENANCE_IDENTITY = (
    "KRONOS-INTRADAY-WO15-OPERATION-PROVENANCE-V1"
)
WO15_INVALID_OPERATION_IDENTITY = "KRONOS-INTRADAY-WO15-INVALID-OPERATION-V1"
WO15_SUPERSESSION_IDENTITY = "KRONOS-INTRADAY-WO15-SUPERSESSION-LINEAGE-V1"
WO15_CURRENT_POINTER_IDENTITY = "KRONOS-INTRADAY-WO15-CURRENT-POINTER-V1"


class Wo15PersistenceError(Wo15ContractError):
    """Sanitized immutable-store or restoration failure."""


class Wo15OperationStage(StrEnum):
    REQUEST_VALIDATION = "REQUEST_VALIDATION"
    WO13_PLAN_RELOAD = "WO13_PLAN_RELOAD"
    TIMING_EVALUATION = "TIMING_EVALUATION"
    TELEMETRY = "TELEMETRY"
    HANDOFF = "HANDOFF"
    PERSISTENCE = "PERSISTENCE"
    POINTER_PUBLICATION = "POINTER_PUBLICATION"
    RESTORATION = "RESTORATION"


class Wo15OperationOutcome(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Wo15SupersessionReason(StrEnum):
    LATER_TIMING_EVALUATION = "LATER_TIMING_EVALUATION"
    RESET_SUCCESSOR_CYCLE = "RESET_SUCCESSOR_CYCLE"
    WO13_PLAN_SUPERSEDED = "WO13_PLAN_SUPERSEDED"
    UPSTREAM_CYCLE_SUPERSEDED = "UPSTREAM_CYCLE_SUPERSEDED"
    INSTRUMENT_CONTRACT_SUPERSEDED = "INSTRUMENT_CONTRACT_SUPERSEDED"
    SESSION_EXPIRED = "SESSION_EXPIRED"


@dataclass(frozen=True, slots=True)
class Wo15OperationRequest:
    """Exact immutable inputs for one zero-discretion timing evaluation."""

    request_identity: str
    request_integrity: str
    admission: Wo15Wo13Handoff
    session: Wo15SessionBinding
    source_candle: GovernedHistoricalCandlePayload | None
    evidence: Wo15FiveMinuteEvidence
    progression: Wo15ProgressionEvidence
    observed_at: datetime
    expiry_event: Wo15ExpiryEvent | None
    wo14_reference_state: str | None
    model_rr_context: Decimal | None
    telemetry_measurement: Wo15TelemetryCandle | None
    telemetry_atr_history: tuple[Wo15TelemetryCandle, ...]
    telemetry_cycle_history: tuple[Wo15TelemetryCandle, ...]
    telemetry_references: tuple[Wo15ResearchReference, ...]
    wo14_observation_identity: str | None
    wo14_observation_integrity: str | None
    requested_at: datetime
    provenance: tuple[str, ...]
    schema_identity: str = WO15_OPERATION_REQUEST_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.model_rr_context is not None:
            object.__setattr__(
                self, "model_rr_context", _decimal(self.model_rr_context)
            )
        values = _without(self, "request_identity", "request_integrity")
        risk_pair = (
            self.wo14_observation_identity,
            self.wo14_observation_integrity,
        )
        telemetry_supplied = self.telemetry_measurement is not None
        if (
            type(self.admission) is not Wo15Wo13Handoff
            or type(self.session) is not Wo15SessionBinding
            or self.source_candle is not None
            and type(self.source_candle) is not GovernedHistoricalCandlePayload
            or type(self.evidence) is not Wo15FiveMinuteEvidence
            or type(self.progression) is not Wo15ProgressionEvidence
            or not _aware(self.observed_at)
            or self.expiry_event is not None
            and type(self.expiry_event) is not Wo15ExpiryEvent
            or self.wo14_reference_state is not None
            and not _text(self.wo14_reference_state)
            or self.model_rr_context is not None
            and not self.model_rr_context.is_finite()
            or telemetry_supplied
            != bool(self.telemetry_atr_history or self.telemetry_cycle_history)
            or self.telemetry_references and not telemetry_supplied
            or any(type(item) is not Wo15TelemetryCandle for item in (
                *self.telemetry_atr_history, *self.telemetry_cycle_history,
            ))
            or any(type(item) is not Wo15ResearchReference
                   for item in self.telemetry_references)
            or (any(item is not None for item in risk_pair)
                and not _texts(risk_pair))
            or not _aware(self.requested_at)
            or self.requested_at > self.observed_at
            or not _texts(self.provenance)
            or self.schema_identity != WO15_OPERATION_REQUEST_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.request_identity
            != _identity("INTRADAY-WO15-REQUEST-", values)
            or self.request_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-REQUEST-", values)
        ):
            raise Wo15ContractError("WO15_OPERATION_REQUEST_INVALID")


def create_wo15_operation_request(
    *,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    source_candle: GovernedHistoricalCandlePayload | None,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
    observed_at: datetime,
    expiry_event: Wo15ExpiryEvent | None = None,
    wo14_reference_state: str | None = None,
    model_rr_context: Decimal | None = None,
    telemetry_measurement: Wo15TelemetryCandle | None = None,
    telemetry_atr_history: Sequence[Wo15TelemetryCandle] = (),
    telemetry_cycle_history: Sequence[Wo15TelemetryCandle] = (),
    telemetry_references: Sequence[Wo15ResearchReference] = (),
    wo14_observation_identity: str | None = None,
    wo14_observation_integrity: str | None = None,
    requested_at: datetime | None = None,
    provenance: tuple[str, ...] = ("ADR-0025", "WO-15D"),
) -> Wo15OperationRequest:
    values = {
        "admission": admission,
        "session": session,
        "source_candle": source_candle,
        "evidence": evidence,
        "progression": progression,
        "observed_at": observed_at,
        "expiry_event": expiry_event,
        "wo14_reference_state": wo14_reference_state,
        "model_rr_context": model_rr_context,
        "telemetry_measurement": telemetry_measurement,
        "telemetry_atr_history": tuple(telemetry_atr_history),
        "telemetry_cycle_history": tuple(telemetry_cycle_history),
        "telemetry_references": tuple(telemetry_references),
        "wo14_observation_identity": wo14_observation_identity,
        "wo14_observation_integrity": wo14_observation_integrity,
        "requested_at": observed_at if requested_at is None else requested_at,
        "provenance": provenance,
        "schema_identity": WO15_OPERATION_REQUEST_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    return Wo15OperationRequest(
        request_identity=_identity("INTRADAY-WO15-REQUEST-", values),
        request_integrity=_identity("INTEGRITY-INTRADAY-WO15-REQUEST-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo15OperationProvenance:
    operation_identity: str
    operation_integrity: str
    request_identity: str
    request_integrity: str
    stage: Wo15OperationStage
    outcome: Wo15OperationOutcome
    started_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    timing_result_identity: str | None
    timing_handoff_identity: str | None
    failure_reason: str | None
    provenance: tuple[str, ...]
    schema_identity: str = WO15_OPERATION_PROVENANCE_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "operation_identity", "operation_integrity")
        completed = self.outcome is Wo15OperationOutcome.COMPLETED
        failed = self.outcome is Wo15OperationOutcome.FAILED
        if (
            not _texts((self.request_identity, self.request_integrity,
                        *self.provenance))
            or type(self.stage) is not Wo15OperationStage
            or type(self.outcome) is not Wo15OperationOutcome
            or not _aware(self.started_at)
            or completed != (self.completed_at is not None)
            or completed != (self.timing_result_identity is not None)
            or failed != (self.failed_at is not None)
            or failed != (self.failure_reason is not None)
            or self.completed_at is not None and not _aware(self.completed_at)
            or self.failed_at is not None and not _aware(self.failed_at)
            or self.timing_handoff_identity is not None
            and not _text(self.timing_handoff_identity)
            or self.failure_reason is not None and not _code(self.failure_reason)
            or self.schema_identity != WO15_OPERATION_PROVENANCE_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.operation_identity
            != _identity("INTRADAY-WO15-OPERATION-", values)
            or self.operation_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-OPERATION-", values)
        ):
            raise Wo15ContractError("WO15_OPERATION_PROVENANCE_INVALID")


def create_wo15_operation_provenance(
    *, request: Wo15OperationRequest, stage: Wo15OperationStage,
    outcome: Wo15OperationOutcome, started_at: datetime,
    completed_at: datetime | None = None, failed_at: datetime | None = None,
    timing_result: Wo15TimingEvaluationResult | None = None,
    timing_handoff: Wo15TimingHandoff | None = None,
    failure_reason: str | None = None, provenance: tuple[str, ...],
) -> Wo15OperationProvenance:
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "stage": stage,
        "outcome": outcome,
        "started_at": started_at,
        "completed_at": completed_at,
        "failed_at": failed_at,
        "timing_result_identity": (
            None if timing_result is None else timing_result.result_identity
        ),
        "timing_handoff_identity": (
            None if timing_handoff is None else timing_handoff.handoff_identity
        ),
        "failure_reason": failure_reason,
        "provenance": provenance,
        "schema_identity": WO15_OPERATION_PROVENANCE_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    return Wo15OperationProvenance(
        operation_identity=_identity("INTRADAY-WO15-OPERATION-", values),
        operation_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-OPERATION-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo15InvalidOperationProvenance:
    invalid_identity: str
    invalid_integrity: str
    request_identity: str
    request_integrity: str
    stage: Wo15OperationStage
    reason: str
    source_identities: tuple[str, ...]
    failed_at: datetime
    schema_identity: str = WO15_INVALID_OPERATION_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "invalid_identity", "invalid_integrity")
        if (
            not _texts((self.request_identity, self.request_integrity,
                        *self.source_identities))
            or type(self.stage) is not Wo15OperationStage
            or not _code(self.reason)
            or not _aware(self.failed_at)
            or self.schema_identity != WO15_INVALID_OPERATION_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.invalid_identity
            != _identity("INTRADAY-WO15-INVALID-", values)
            or self.invalid_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-INVALID-", values)
        ):
            raise Wo15ContractError("WO15_INVALID_OPERATION_INVALID")


def create_wo15_invalid_operation(
    *, request: Wo15OperationRequest, stage: Wo15OperationStage,
    reason: str, failed_at: datetime,
) -> Wo15InvalidOperationProvenance:
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "stage": stage,
        "reason": reason,
        "source_identities": (
            request.admission.wo13_trade_plan_identity,
            request.admission.handoff_identity,
            request.evidence.evidence_identity,
            request.progression.adapter_identity,
        ),
        "failed_at": failed_at,
        "schema_identity": WO15_INVALID_OPERATION_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    return Wo15InvalidOperationProvenance(
        invalid_identity=_identity("INTRADAY-WO15-INVALID-", values),
        invalid_integrity=_identity("INTEGRITY-INTRADAY-WO15-INVALID-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo15SupersessionLineage:
    lineage_identity: str
    lineage_integrity: str
    predecessor_pointer_identity: str
    predecessor_result_identity: str
    predecessor_result_integrity: str
    predecessor_cycle_identity: str | None
    successor_result_identity: str
    successor_result_integrity: str
    successor_cycle_identity: str | None
    wo13_trade_plan_identity: str
    reason: Wo15SupersessionReason
    superseded_at: datetime
    schema_identity: str = WO15_SUPERSESSION_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "lineage_identity", "lineage_integrity")
        if (
            not _texts((self.predecessor_pointer_identity,
                        self.predecessor_result_identity,
                        self.predecessor_result_integrity,
                        self.successor_result_identity,
                        self.successor_result_integrity,
                        self.wo13_trade_plan_identity))
            or not _optional_text(self.predecessor_cycle_identity)
            or not _optional_text(self.successor_cycle_identity)
            or self.predecessor_result_identity == self.successor_result_identity
            or type(self.reason) is not Wo15SupersessionReason
            or not _aware(self.superseded_at)
            or self.schema_identity != WO15_SUPERSESSION_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.lineage_identity
            != _identity("INTRADAY-WO15-SUPERSESSION-", values)
            or self.lineage_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-SUPERSESSION-", values)
        ):
            raise Wo15ContractError("WO15_SUPERSESSION_INVALID")


def create_wo15_supersession(
    *, predecessor_pointer: CurrentWo15Pointer,
    predecessor: Wo15TimingEvaluationResult,
    successor: Wo15TimingEvaluationResult,
    reason: Wo15SupersessionReason,
    superseded_at: datetime,
) -> Wo15SupersessionLineage:
    values = {
        "predecessor_pointer_identity": predecessor_pointer.pointer_identity,
        "predecessor_result_identity": predecessor.result_identity,
        "predecessor_result_integrity": predecessor.result_integrity,
        "predecessor_cycle_identity": predecessor.timing_cycle_id,
        "successor_result_identity": successor.result_identity,
        "successor_result_integrity": successor.result_integrity,
        "successor_cycle_identity": successor.timing_cycle_id,
        "wo13_trade_plan_identity": successor.wo13_trade_plan_identity,
        "reason": reason,
        "superseded_at": superseded_at,
        "schema_identity": WO15_SUPERSESSION_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    return Wo15SupersessionLineage(
        lineage_identity=_identity("INTRADAY-WO15-SUPERSESSION-", values),
        lineage_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-SUPERSESSION-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class CurrentWo15Pointer:
    pointer_identity: str
    pointer_integrity: str
    request_identity: str
    request_integrity: str
    operation_identity: str
    operation_integrity: str
    admission_identity: str
    admission_integrity: str
    wo13_trade_plan_identity: str
    wo13_trade_plan_integrity: str
    timing_result_identity: str
    timing_result_integrity: str
    timing_cycle_identity: str | None
    timing_cycle_integrity: str | None
    timing_observation_identity: str | None
    timing_observation_integrity: str | None
    timing_transition_identity: str | None
    timing_transition_integrity: str | None
    evidence_identity: str
    evidence_integrity: str
    telemetry_identity: str | None
    telemetry_integrity: str | None
    timing_handoff_identity: str | None
    timing_handoff_integrity: str | None
    supersession_lineage_identity: str | None
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    direction: SemanticDirection
    setup_family: Wo13SetupFamily
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    calendar_identity: str
    calendar_version: str
    timing_state: Wo15TimingState
    policy: Wo15PolicyBinding
    published_at: datetime
    schema_identity: str = WO15_CURRENT_POINTER_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "pointer_identity", "pointer_integrity")
        optional_pairs = (
            (self.timing_cycle_identity, self.timing_cycle_integrity),
            (self.timing_observation_identity, self.timing_observation_integrity),
            (self.timing_transition_identity, self.timing_transition_integrity),
            (self.telemetry_identity, self.telemetry_integrity),
            (self.timing_handoff_identity, self.timing_handoff_integrity),
        )
        mcx = self.market_family is IntradayMarketFamily.MCX
        if (
            not _texts((self.request_identity, self.request_integrity,
                        self.operation_identity, self.operation_integrity,
                        self.admission_identity, self.admission_integrity,
                        self.wo13_trade_plan_identity,
                        self.wo13_trade_plan_integrity,
                        self.timing_result_identity,
                        self.timing_result_integrity,
                        self.evidence_identity, self.evidence_integrity,
                        self.canonical_subject_identity,
                        self.instrument_identity, self.session_identity,
                        self.calendar_identity, self.calendar_version))
            or any(not (all(item is None for item in pair)
                        or _texts(pair)) for pair in optional_pairs)
            or not _optional_text(self.supersession_lineage_identity)
            or type(self.market_family) is not IntradayMarketFamily
            or type(self.direction) is not SemanticDirection
            or type(self.setup_family) is not Wo13SetupFamily
            or mcx != (self.actual_contract_identity is not None)
            or mcx != (self.roll_lineage_identity is not None)
            or type(self.timing_state) is not Wo15TimingState
            or type(self.policy) is not Wo15PolicyBinding
            or not _aware(self.published_at)
            or self.schema_identity != WO15_CURRENT_POINTER_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.pointer_identity
            != _identity("CURRENT-INTRADAY-WO15-V1-", values)
            or self.pointer_integrity
            != _identity("INTEGRITY-CURRENT-INTRADAY-WO15-V1-", values)
        ):
            raise Wo15ContractError("WO15_CURRENT_POINTER_INVALID")


def create_current_wo15_pointer(
    *, request: Wo15OperationRequest,
    result: Wo15TimingEvaluationResult,
    operation: Wo15OperationProvenance,
    telemetry: Wo15ResearchTelemetry | None,
    timing_handoff: Wo15TimingHandoff | None,
    supersession: Wo15SupersessionLineage | None,
    published_at: datetime,
) -> CurrentWo15Pointer:
    evaluation = result.cycle_evaluation
    if (
        result.wo13_trade_plan_identity
        != request.admission.wo13_trade_plan_identity
        or operation.outcome is not Wo15OperationOutcome.COMPLETED
        or operation.timing_result_identity != result.result_identity
        or telemetry is not None
        and telemetry.timing_result_identity != result.result_identity
        or timing_handoff is not None
        and timing_handoff.timing_observation_identity
        != (None if evaluation is None
            else evaluation.observation.observation_identity)
    ):
        raise Wo15ContractError("WO15_CURRENT_POINTER_INPUT_INVALID")
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "operation_identity": operation.operation_identity,
        "operation_integrity": operation.operation_integrity,
        "admission_identity": request.admission.handoff_identity,
        "admission_integrity": request.admission.handoff_integrity,
        "wo13_trade_plan_identity": request.admission.wo13_trade_plan_identity,
        "wo13_trade_plan_integrity": request.admission.wo13_trade_plan_integrity,
        "timing_result_identity": result.result_identity,
        "timing_result_integrity": result.result_integrity,
        "timing_cycle_identity": (
            None if evaluation is None else evaluation.cycle.timing_cycle_id
        ),
        "timing_cycle_integrity": (
            None if evaluation is None else evaluation.cycle.timing_cycle_integrity
        ),
        "timing_observation_identity": (
            None if evaluation is None else evaluation.observation.observation_identity
        ),
        "timing_observation_integrity": (
            None if evaluation is None else evaluation.observation.observation_integrity
        ),
        "timing_transition_identity": (
            None if evaluation is None else evaluation.transition.transition_identity
        ),
        "timing_transition_integrity": (
            None if evaluation is None else evaluation.transition.transition_integrity
        ),
        "evidence_identity": request.evidence.evidence_identity,
        "evidence_integrity": request.evidence.evidence_integrity,
        "telemetry_identity": (
            None if telemetry is None else telemetry.telemetry_identity
        ),
        "telemetry_integrity": (
            None if telemetry is None else telemetry.telemetry_integrity
        ),
        "timing_handoff_identity": (
            None if timing_handoff is None else timing_handoff.handoff_identity
        ),
        "timing_handoff_integrity": (
            None if timing_handoff is None else timing_handoff.handoff_integrity
        ),
        "supersession_lineage_identity": (
            None if supersession is None else supersession.lineage_identity
        ),
        "canonical_subject_identity": request.admission.canonical_subject_identity,
        "market_family": request.admission.market_family,
        "direction": request.admission.direction,
        "setup_family": request.admission.setup_family,
        "instrument_identity": request.admission.instrument_identity,
        "actual_contract_identity": request.admission.actual_contract_identity,
        "roll_lineage_identity": request.admission.roll_lineage_identity,
        "session_identity": request.session.session_identity,
        "calendar_identity": request.session.calendar_identity,
        "calendar_version": request.session.calendar_version,
        "timing_state": result.current_state,
        "policy": request.admission.policy,
        "published_at": published_at,
        "schema_identity": WO15_CURRENT_POINTER_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    return CurrentWo15Pointer(
        pointer_identity=_identity("CURRENT-INTRADAY-WO15-V1-", values),
        pointer_integrity=_identity(
            "INTEGRITY-CURRENT-INTRADAY-WO15-V1-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class RestoredWo15State:
    pointer: CurrentWo15Pointer
    request: Wo15OperationRequest
    admission: Wo15Wo13Handoff
    session: Wo15SessionBinding
    evidence: Wo15FiveMinuteEvidence
    progression: Wo15ProgressionEvidence
    result: Wo15TimingEvaluationResult
    evaluation: Wo15CycleEvaluation | None
    telemetry: Wo15ResearchTelemetry | None
    timing_handoff: Wo15TimingHandoff | None
    operation: Wo15OperationProvenance
    supersession: Wo15SupersessionLineage | None
    latest_failure: Wo15InvalidOperationProvenance | None


class Wo15Store:
    """Dedicated append-only WO-15 artifacts and separate mutable aliases."""

    _FAMILIES = frozenset({
        "requests", "admissions", "sessions", "evidence", "progressions",
        "cycles", "observations", "transitions", "evaluations", "histories",
        "results", "reset-assessments", "telemetry", "handoffs", "operations",
        "invalid", "supersessions", "current",
    })

    def __init__(self, root: Path = DEFAULT_WO15_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("WO15_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_request(self, value: Wo15OperationRequest) -> Path:
        return self._retain("requests", value.request_identity, value)

    def retain_admission(self, value: Wo15Wo13Handoff) -> Path:
        return self._retain("admissions", value.handoff_identity, value)

    def retain_session(self, value: Wo15SessionBinding) -> Path:
        return self._retain("sessions", value.binding_identity, value)

    def retain_evidence(self, value: Wo15FiveMinuteEvidence) -> Path:
        return self._retain("evidence", value.evidence_identity, value)

    def retain_progression(self, value: Wo15ProgressionEvidence) -> Path:
        return self._retain("progressions", value.adapter_identity, value)

    def retain_cycle(self, value: Wo15TimingCycle) -> Path:
        return self._retain("cycles", value.timing_cycle_id, value)

    retain_timing_cycle = retain_cycle

    def retain_observation(self, value: Wo15TimingObservation) -> Path:
        return self._retain("observations", value.observation_identity, value)

    retain_timing_observation = retain_observation

    def retain_transition(self, value: Wo15TimingTransition) -> Path:
        return self._retain("transitions", value.transition_identity, value)

    retain_timing_transition = retain_transition

    def retain_evaluation(self, value: Wo15CycleEvaluation) -> Path:
        return self._retain("evaluations", value.evaluation_identity, value)

    def retain_history(self, value: Wo15TimingLocalHistory) -> Path:
        return self._retain("histories", value.history_identity, value)

    def retain_result(self, value: Wo15TimingEvaluationResult) -> Path:
        return self._retain("results", value.result_identity, value)

    def retain_reset_assessment(self, value: Wo15ResetAssessment) -> Path:
        return self._retain(
            "reset-assessments", value.assessment_identity, value
        )

    def retain_telemetry(self, value: Wo15ResearchTelemetry) -> Path:
        return self._retain("telemetry", value.telemetry_identity, value)

    def retain_handoff(self, value: Wo15TimingHandoff) -> Path:
        return self._retain("handoffs", value.handoff_identity, value)

    def retain_operation(self, value: Wo15OperationProvenance) -> Path:
        return self._retain("operations", value.operation_identity, value)

    def retain_invalid(self, value: Wo15InvalidOperationProvenance) -> Path:
        return self._retain("invalid", value.invalid_identity, value)

    def retain_supersession(self, value: Wo15SupersessionLineage) -> Path:
        return self._retain("supersessions", value.lineage_identity, value)

    def load_request(self, identity: str) -> Wo15OperationRequest:
        return self._load("requests", identity, Wo15OperationRequest,
                          "request_identity")

    def load_admission(self, identity: str) -> Wo15Wo13Handoff:
        return self._load("admissions", identity, Wo15Wo13Handoff,
                          "handoff_identity")

    def load_session(self, identity: str) -> Wo15SessionBinding:
        return self._load("sessions", identity, Wo15SessionBinding,
                          "binding_identity")

    def load_evidence(self, identity: str) -> Wo15FiveMinuteEvidence:
        return self._load("evidence", identity, Wo15FiveMinuteEvidence,
                          "evidence_identity")

    def load_progression(self, identity: str) -> Wo15ProgressionEvidence:
        return self._load("progressions", identity, Wo15ProgressionEvidence,
                          "adapter_identity")

    def load_cycle(self, identity: str) -> Wo15TimingCycle:
        return self._load("cycles", identity, Wo15TimingCycle,
                          "timing_cycle_id")

    load_timing_cycle = load_cycle

    def load_observation(self, identity: str) -> Wo15TimingObservation:
        return self._load("observations", identity, Wo15TimingObservation,
                          "observation_identity")

    load_timing_observation = load_observation

    def load_transition(self, identity: str) -> Wo15TimingTransition:
        return self._load("transitions", identity, Wo15TimingTransition,
                          "transition_identity")

    load_timing_transition = load_transition

    def load_evaluation(self, identity: str) -> Wo15CycleEvaluation:
        return self._load("evaluations", identity, Wo15CycleEvaluation,
                          "evaluation_identity")

    def load_history(self, identity: str) -> Wo15TimingLocalHistory:
        return self._load("histories", identity, Wo15TimingLocalHistory,
                          "history_identity")

    def load_result(self, identity: str) -> Wo15TimingEvaluationResult:
        return self._load("results", identity, Wo15TimingEvaluationResult,
                          "result_identity")

    def load_reset_assessment(self, identity: str) -> Wo15ResetAssessment:
        return self._load("reset-assessments", identity, Wo15ResetAssessment,
                          "assessment_identity")

    def load_telemetry(self, identity: str) -> Wo15ResearchTelemetry:
        return self._load("telemetry", identity, Wo15ResearchTelemetry,
                          "telemetry_identity")

    def load_handoff(self, identity: str) -> Wo15TimingHandoff:
        return self._load("handoffs", identity, Wo15TimingHandoff,
                          "handoff_identity")

    def load_operation(self, identity: str) -> Wo15OperationProvenance:
        return self._load("operations", identity, Wo15OperationProvenance,
                          "operation_identity")

    def load_invalid(self, identity: str) -> Wo15InvalidOperationProvenance:
        return self._load("invalid", identity, Wo15InvalidOperationProvenance,
                          "invalid_identity")

    def load_supersession(self, identity: str) -> Wo15SupersessionLineage:
        return self._load("supersessions", identity, Wo15SupersessionLineage,
                          "lineage_identity")

    def publish_current(self, value: CurrentWo15Pointer) -> Path:
        if type(value) is not CurrentWo15Pointer:
            raise Wo15PersistenceError("WO15_CURRENT_POINTER_INVALID")
        alias = self._root / "current" / "CURRENT-INTRADAY-WO15-V1.json"
        with self._lock:
            self._retain("current", value.pointer_identity, value)
            _replace_atomic(alias, _artifact_bytes(value))
        return alias

    def publish_latest_failure(
        self, value: Wo15InvalidOperationProvenance
    ) -> Path:
        if type(value) is not Wo15InvalidOperationProvenance:
            raise Wo15PersistenceError("WO15_INVALID_OPERATION_INVALID")
        alias = self._root / "current" / "LATEST-WO15-FAILURE-V1.json"
        with self._lock:
            self.retain_invalid(value)
            _replace_atomic(alias, _artifact_bytes(value))
        return alias

    def load_current(self) -> CurrentWo15Pointer | None:
        path = self._root / "current" / "CURRENT-INTRADAY-WO15-V1.json"
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if type(value) is not CurrentWo15Pointer:
            raise Wo15PersistenceError("WO15_CURRENT_POINTER_INTEGRITY_INVALID")
        return value

    def load_latest_failure(self) -> Wo15InvalidOperationProvenance | None:
        path = self._root / "current" / "LATEST-WO15-FAILURE-V1.json"
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if type(value) is not Wo15InvalidOperationProvenance:
            raise Wo15PersistenceError("WO15_FAILURE_POINTER_INTEGRITY_INVALID")
        return value

    def restore_current(self) -> RestoredWo15State | None:
        pointer = self.load_current()
        if pointer is None:
            return None
        return self.restore_pointer(pointer)

    def restore_pointer(self, pointer: CurrentWo15Pointer) -> RestoredWo15State:
        """Validate an exact pointer graph without changing the current alias."""

        if type(pointer) is not CurrentWo15Pointer:
            raise Wo15PersistenceError("WO15_CURRENT_POINTER_INVALID")
        request = self.load_request(pointer.request_identity)
        admission = self.load_admission(pointer.admission_identity)
        session = self.load_session(request.session.binding_identity)
        evidence = self.load_evidence(pointer.evidence_identity)
        progression = self.load_progression(request.progression.adapter_identity)
        result = self.load_result(pointer.timing_result_identity)
        evaluation = (
            None if pointer.timing_cycle_identity is None
            else result.cycle_evaluation
        )
        telemetry = (
            None if pointer.telemetry_identity is None
            else self.load_telemetry(pointer.telemetry_identity)
        )
        timing_handoff = (
            None if pointer.timing_handoff_identity is None
            else self.load_handoff(pointer.timing_handoff_identity)
        )
        operation = self.load_operation(pointer.operation_identity)
        supersession = (
            None if pointer.supersession_lineage_identity is None
            else self.load_supersession(pointer.supersession_lineage_identity)
        )
        latest_failure = self.load_latest_failure()
        if evaluation is not None:
            stored = self.load_evaluation(evaluation.evaluation_identity)
            if stored != evaluation:
                raise Wo15PersistenceError("WO15_RESTORATION_BINDING_INVALID")
            if (
                self.load_cycle(evaluation.cycle.timing_cycle_id)
                != evaluation.cycle
                or self.load_observation(
                    evaluation.observation.observation_identity
                ) != evaluation.observation
                or self.load_transition(
                    evaluation.transition.transition_identity
                ) != evaluation.transition
            ):
                raise Wo15PersistenceError("WO15_RESTORATION_BINDING_INVALID")
        if (
            request.request_integrity != pointer.request_integrity
            or request.admission != admission
            or request.session != session
            or request.evidence != evidence
            or request.progression != progression
            or admission.handoff_integrity != pointer.admission_integrity
            or admission.wo13_trade_plan_identity
            != pointer.wo13_trade_plan_identity
            or admission.wo13_trade_plan_integrity
            != pointer.wo13_trade_plan_integrity
            or result.result_integrity != pointer.timing_result_integrity
            or result.current_state is not pointer.timing_state
            or result.policy != pointer.policy
            or result.evidence_identity != evidence.evidence_identity
            or evaluation is None
            and any(item is not None for item in (
                pointer.timing_cycle_identity,
                pointer.timing_cycle_integrity,
                pointer.timing_observation_identity,
                pointer.timing_observation_integrity,
                pointer.timing_transition_identity,
                pointer.timing_transition_integrity,
            ))
            or evaluation is not None
            and (
                pointer.timing_cycle_identity
                != evaluation.cycle.timing_cycle_id
                or pointer.timing_cycle_integrity
                != evaluation.cycle.timing_cycle_integrity
                or pointer.timing_observation_identity
                != evaluation.observation.observation_identity
                or pointer.timing_observation_integrity
                != evaluation.observation.observation_integrity
                or pointer.timing_transition_identity
                != evaluation.transition.transition_identity
                or pointer.timing_transition_integrity
                != evaluation.transition.transition_integrity
            )
            or operation.operation_integrity != pointer.operation_integrity
            or operation.outcome is not Wo15OperationOutcome.COMPLETED
            or operation.timing_result_identity != result.result_identity
            or telemetry is not None
            and telemetry.telemetry_integrity != pointer.telemetry_integrity
            or timing_handoff is not None
            and timing_handoff.handoff_integrity != pointer.timing_handoff_integrity
            or supersession is not None
            and supersession.successor_result_identity != result.result_identity
        ):
            raise Wo15PersistenceError("WO15_RESTORATION_BINDING_INVALID")
        return RestoredWo15State(
            pointer, request, admission, session, evidence, progression, result,
            evaluation, telemetry, timing_handoff, operation, supersession,
            latest_failure,
        )

    def _retain(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        encoded = _artifact_bytes(value)
        with self._lock:
            if path.exists():
                if _read(path) != encoded:
                    raise Wo15PersistenceError("WO15_IMMUTABLE_CONFLICT")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(encoded)
        return path

    def _load(
        self, family: str, identity: str, expected: type, identity_name: str
    ):  # type: ignore[no-untyped-def]
        value = _artifact_from_bytes(_read(self._path(family, identity)))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise Wo15PersistenceError("WO15_ARTIFACT_INTEGRITY_INVALID")
        return value

    def _path(self, family: str, identity: str) -> Path:
        if family not in self._FAMILIES or not _component(identity):
            raise Wo15PersistenceError("WO15_ARTIFACT_PATH_INVALID")
        return self._root / family / f"{identity}.json"


_DATACLASSES = {item.__name__: item for item in (
    GovernedHistoricalCandlePayload,
    Wo15PolicyBinding, Wo15SessionBinding, Wo15Wo13Handoff,
    Wo15FiveMinuteEvidence, Wo15ProgressionEvidence, Wo15TimingCycle,
    Wo15TimingTransition, Wo15TimingObservation, Wo15CycleEvaluation,
    Wo15ExpiryEvent, Wo15TimingLocalHistory, Wo15TimingEvaluationResult,
    Wo15ResetAssessment, Wo15TelemetryCandle, Wo15Atr14Observation,
    Wo15ResearchReference, Wo15LatencyTelemetry, Wo15ResearchTelemetry,
    Wo15TimingHandoff, Wo15OperationRequest, Wo15OperationProvenance,
    Wo15InvalidOperationProvenance, Wo15SupersessionLineage,
    CurrentWo15Pointer,
)}
_ENUMS = {item.__name__: item for item in (
    IntradayTimeframe, SemanticDirection, IntradayMarketFamily, Wo13SetupFamily,
    Wo15ExpiryCause, Wo15ProgressionSemantics, Wo15QualificationPath,
    Wo15SessionDisposition, Wo15TimingState, Wo15TrustFailure,
    Wo15TimingCause, Wo15ResetDisposition, Wo15TelemetryAvailability,
    Wo15AtrUnavailableReason, Wo15ResearchRole, Wo15ResearchLocality,
    Wo15OperationStage, Wo15OperationOutcome, Wo15SupersessionReason,
)}


def _artifact_bytes(value: object) -> bytes:
    core = {
        "artifact_type": type(value).__name__,
        "artifact_identity": _artifact_identity(value),
        "artifact": _to_wire(value),
    }
    return _encode({
        **core, "document_integrity": sha256(_encode(core)).hexdigest()
    }) + b"\n"


def _artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
        core = {
            key: document[key]
            for key in ("artifact_type", "artifact_identity", "artifact")
        }
        if (
            set(document) != {*core, "document_integrity"}
            or document["document_integrity"]
            != sha256(_encode(core)).hexdigest()
        ):
            raise ValueError
        value = _from_wire(document["artifact"])
        if (
            type(value).__name__ != document["artifact_type"]
            or _artifact_identity(value) != document["artifact_identity"]
        ):
            raise ValueError
        return value
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise Wo15PersistenceError("WO15_ARTIFACT_INTEGRITY_INVALID") from error


def _artifact_identity(value: object) -> str:
    for name in (
        "request_identity", "handoff_identity", "binding_identity",
        "evidence_identity", "adapter_identity", "timing_cycle_id",
        "observation_identity", "transition_identity", "evaluation_identity",
        "history_identity", "result_identity", "assessment_identity",
        "telemetry_identity", "operation_identity", "invalid_identity",
        "lineage_identity", "pointer_identity",
    ):
        identity = getattr(value, name, None)
        if type(identity) is str:
            return identity
    raise Wo15PersistenceError("WO15_ARTIFACT_IDENTITY_INVALID")


def _to_wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "__dataclass__": type(value).__name__,
            "fields": {
                item.name: _to_wire(getattr(value, item.name))
                for item in fields(value)
            },
        }
    if isinstance(value, StrEnum):
        return {"__enum__": type(value).__name__, "value": value.value}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, timedelta):
        return {"__timedelta__": [value.days, value.seconds, value.microseconds]}
    if isinstance(value, Decimal):
        return {"__decimal__": format(value, "f")}
    if isinstance(value, tuple):
        return {"__tuple__": [_to_wire(item) for item in value]}
    if isinstance(value, Mapping):
        return {str(key): _to_wire(item) for key, item in value.items()}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise Wo15PersistenceError("WO15_ARTIFACT_ENCODING_INVALID")


def _from_wire(value: object) -> object:
    if type(value) is not dict:
        return value
    if set(value) == {"__datetime__"}:
        return datetime.fromisoformat(value["__datetime__"])
    if set(value) == {"__date__"}:
        return date.fromisoformat(value["__date__"])
    if set(value) == {"__timedelta__"}:
        days, seconds, microseconds = value["__timedelta__"]
        return timedelta(days=days, seconds=seconds, microseconds=microseconds)
    if set(value) == {"__decimal__"}:
        return Decimal(value["__decimal__"])
    if set(value) == {"__tuple__"}:
        return tuple(_from_wire(item) for item in value["__tuple__"])
    if set(value) == {"__enum__", "value"}:
        enum = _ENUMS.get(value["__enum__"])
        if enum is None:
            raise ValueError
        return enum(value["value"])
    if set(value) == {"__dataclass__", "fields"}:
        cls = _DATACLASSES.get(value["__dataclass__"])
        raw = value["fields"]
        if cls is None or type(raw) is not dict:
            raise ValueError
        return cls(**{key: _from_wire(item) for key, item in raw.items()})
    return {key: _from_wire(item) for key, item in value.items()}


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise Wo15PersistenceError("WO15_ARTIFACT_UNAVAILABLE") from error


def _replace_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(path)


def _encode(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(_normalize(value))).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return (value.days, value.seconds, value.microseconds)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _component(value: object) -> bool:
    return (
        type(value) is str
        and 2 < len(value) <= 256
        and all(item.isalnum() or item in "-_.:" for item in value)
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(item) for item in values)


def _optional_text(value: object) -> bool:
    return value is None or _text(value)


def _code(value: object) -> bool:
    return (
        _text(value)
        and len(value) <= 128
        and all(item.isupper() or item.isdigit() or item == "_" for item in value)
    )


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise Wo15ContractError("WO15_DECIMAL_INVALID") from error
    if not result.is_finite():
        raise Wo15ContractError("WO15_DECIMAL_INVALID")
    return result


__all__ = [
    "DEFAULT_WO15_ROOT", "CurrentWo15Pointer", "RestoredWo15State",
    "Wo15InvalidOperationProvenance", "Wo15OperationOutcome",
    "Wo15OperationProvenance", "Wo15OperationRequest", "Wo15OperationStage",
    "Wo15PersistenceError", "Wo15Store", "Wo15SupersessionLineage",
    "Wo15SupersessionReason", "create_current_wo15_pointer",
    "create_wo15_invalid_operation", "create_wo15_operation_provenance",
    "create_wo15_operation_request", "create_wo15_supersession",
]
