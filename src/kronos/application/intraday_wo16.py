"""Deterministic, persistence-free Intraday WO-16 application boundary.

The service validates supplied immutable current-state facts, records one
Sponsor decision value and its factual lifecycle-admission disposition, and
returns those values to its caller.  It owns no store, pointer, runtime,
Browser, Provider, position, simulation, execution, or broker capability.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from threading import Lock

from kronos.intraday.wo13 import CurrentWo13Pointer, Wo13TradePlan
from kronos.intraday.wo13_handoff import Wo13Step31Handoff
from kronos.intraday.wo14 import CurrentWo14Pointer, Wo14RiskObservation
from kronos.intraday.wo15 import Wo15SessionBinding
from kronos.intraday.wo15_handoff import Wo15TimingHandoff
from kronos.intraday.wo16 import (
    WO16_CONTRACT_VERSION,
    Wo16ContractError,
    Wo16LifecycleAdmissionRecord,
    Wo16PolicyBinding,
    Wo16SponsorDecision,
    Wo16SponsorDecisionRecord,
    Wo16SponsorDecisionSnapshot,
    Wo16UpstreamLineage,
    canonical_document_bytes,
    create_wo16_lifecycle_admission_record,
    create_wo16_sponsor_decision_record,
    create_wo16_sponsor_decision_snapshot,
)
from kronos.intraday.wo16_adapters import (
    Wo16BindingRejected,
    Wo16CurrentWo15Pointer,
    bind_wo16_risk_observation,
    bind_wo16_session_fact,
    bind_wo16_timing_handoff,
    bind_wo16_trade_plan,
    bind_wo16_upstream,
    is_wo16_risk_state_admissible,
)
from kronos.market.schedule import MarketSessionFact


WO16_OPERATION_REQUEST_IDENTITY = "KRONOS-INTRADAY-WO16-OPERATION-REQUEST-V1"
WO16_APPLICATION_IDENTITY = "KRONOS-INTRADAY-WO16-APPLICATION-V1"


class Wo16ApplicationError(Wo16ContractError):
    """Sanitized WO-16 application-boundary rejection."""


class Wo16ApplicationOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    RETAINED_IDEMPOTENT = "RETAINED_IDEMPOTENT"
    BUSY = "BUSY"


@dataclass(frozen=True, slots=True)
class Wo16OperationRequest:
    """Exact immutable facts supplied for one Sponsor decision attempt."""

    request_identity: str
    request_integrity: str
    current_wo13_pointer: CurrentWo13Pointer
    wo13_trade_plan: Wo13TradePlan
    wo13_source_handoff: Wo13Step31Handoff
    current_wo14_pointer: CurrentWo14Pointer
    wo14_observation: Wo14RiskObservation
    current_wo15_pointer: Wo16CurrentWo15Pointer
    wo15_timing_handoff: Wo15TimingHandoff
    wo15_session: Wo15SessionBinding
    domain_008_session_fact: MarketSessionFact
    choice: Wo16SponsorDecision
    snapshot_timestamp: datetime
    decision_timestamp: datetime
    admission_recorded_at: datetime
    policy: Wo16PolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO16_OPERATION_REQUEST_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _request_values(self)
        if (
            type(self.current_wo13_pointer) is not CurrentWo13Pointer
            or type(self.wo13_trade_plan) is not Wo13TradePlan
            or type(self.wo13_source_handoff) is not Wo13Step31Handoff
            or type(self.current_wo14_pointer) is not CurrentWo14Pointer
            or type(self.wo14_observation) is not Wo14RiskObservation
            or type(self.wo15_timing_handoff) is not Wo15TimingHandoff
            or type(self.wo15_session) is not Wo15SessionBinding
            or type(self.domain_008_session_fact) is not MarketSessionFact
            or type(self.choice) is not Wo16SponsorDecision
            or not all(
                _aware(value)
                for value in (
                    self.snapshot_timestamp,
                    self.decision_timestamp,
                    self.admission_recorded_at,
                )
            )
            or not (
                self.domain_008_session_fact.observed_at
                <= self.snapshot_timestamp
                <= self.decision_timestamp
                <= self.admission_recorded_at
            )
            or type(self.policy) is not Wo16PolicyBinding
            or not _texts(self.provenance)
            or self.schema_identity != WO16_OPERATION_REQUEST_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or self.request_identity != _identity("INTRADAY-WO16-REQUEST-", values)
            or self.request_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-REQUEST-", values)
        ):
            raise Wo16ApplicationError("WO16_REQUEST_INVALID")
        _validate_source(self.current_wo13_pointer)
        _validate_source(self.wo13_trade_plan)
        _validate_source(self.wo13_source_handoff)
        _validate_source(self.current_wo14_pointer)
        _validate_source(self.wo14_observation)
        _validate_source(self.current_wo15_pointer)
        _validate_source(self.wo15_timing_handoff)
        _validate_source(self.wo15_session)
        _validate_source(self.domain_008_session_fact)


@dataclass(frozen=True, slots=True)
class Wo16Execution:
    """Immutable application result; caller remains responsible for retention."""

    request_identity: str
    request_integrity: str
    upstream_lineage: Wo16UpstreamLineage
    snapshot: Wo16SponsorDecisionSnapshot
    decision: Wo16SponsorDecisionRecord
    admission: Wo16LifecycleAdmissionRecord
    outcome: Wo16ApplicationOutcome
    replayed: bool
    application_identity: str = WO16_APPLICATION_IDENTITY
    application_version: str = WO16_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not _texts((self.request_identity, self.request_integrity))
            or type(self.upstream_lineage) is not Wo16UpstreamLineage
            or type(self.snapshot) is not Wo16SponsorDecisionSnapshot
            or type(self.decision) is not Wo16SponsorDecisionRecord
            or type(self.admission) is not Wo16LifecycleAdmissionRecord
            or self.snapshot.upstream_lineage != self.upstream_lineage
            or self.decision.request_identity != self.request_identity
            or self.decision.request_integrity != self.request_integrity
            or self.decision.snapshot_identity != self.snapshot.snapshot_identity
            or self.decision.snapshot_integrity != self.snapshot.snapshot_integrity
            or self.admission.decision_identity != self.decision.decision_identity
            or self.admission.decision_integrity != self.decision.decision_integrity
            or type(self.outcome) is not Wo16ApplicationOutcome
            or self.outcome not in {
                Wo16ApplicationOutcome.COMPLETED,
                Wo16ApplicationOutcome.RETAINED_IDEMPOTENT,
            }
            or self.replayed
            != (self.outcome is Wo16ApplicationOutcome.RETAINED_IDEMPOTENT)
            or self.application_identity != WO16_APPLICATION_IDENTITY
            or self.application_version != WO16_CONTRACT_VERSION
        ):
            raise Wo16ApplicationError("WO16_EXECUTION_INVALID")
        for value in (
            self.upstream_lineage,
            self.snapshot,
            self.decision,
            self.admission,
        ):
            _validate_source(value)


@dataclass(frozen=True, slots=True)
class Wo16BusyOutcome:
    """Bounded nonblocking response with no analytical or decision consequence."""

    request_identity: str
    outcome: Wo16ApplicationOutcome = Wo16ApplicationOutcome.BUSY
    reason: str = "WO16_OPERATION_BUSY"
    retry_performed: bool = False
    decision_created: bool = False
    admission_created: bool = False

    def __post_init__(self) -> None:
        if (
            not _text(self.request_identity)
            or self.outcome is not Wo16ApplicationOutcome.BUSY
            or self.reason != "WO16_OPERATION_BUSY"
            or self.retry_performed
            or self.decision_created
            or self.admission_created
        ):
            raise Wo16ApplicationError("WO16_BUSY_OUTCOME_INVALID")


def create_wo16_operation_request(
    *,
    current_wo13_pointer: CurrentWo13Pointer,
    wo13_trade_plan: Wo13TradePlan,
    wo13_source_handoff: Wo13Step31Handoff,
    current_wo14_pointer: CurrentWo14Pointer,
    wo14_observation: Wo14RiskObservation,
    current_wo15_pointer: Wo16CurrentWo15Pointer,
    wo15_timing_handoff: Wo15TimingHandoff,
    wo15_session: Wo15SessionBinding,
    domain_008_session_fact: MarketSessionFact,
    choice: Wo16SponsorDecision,
    snapshot_timestamp: datetime,
    decision_timestamp: datetime,
    admission_recorded_at: datetime,
    provenance: tuple[str, ...] = ("ADR-0026", "WO-16-SLICE-2"),
) -> Wo16OperationRequest:
    policy = Wo16PolicyBinding()
    values = {
        "current_wo13_pointer": current_wo13_pointer,
        "wo13_trade_plan": wo13_trade_plan,
        "wo13_source_handoff": wo13_source_handoff,
        "current_wo14_pointer": current_wo14_pointer,
        "wo14_observation": wo14_observation,
        "current_wo15_pointer": current_wo15_pointer,
        "wo15_timing_handoff": wo15_timing_handoff,
        "wo15_session": wo15_session,
        "domain_008_session_fact": domain_008_session_fact,
        "choice": choice,
        "snapshot_timestamp": snapshot_timestamp,
        "decision_timestamp": decision_timestamp,
        "admission_recorded_at": admission_recorded_at,
        "policy": policy,
        "provenance": provenance,
        "schema_identity": WO16_OPERATION_REQUEST_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
    }
    try:
        request_identity = _identity("INTRADAY-WO16-REQUEST-", values)
        request_integrity = _identity(
            "INTEGRITY-INTRADAY-WO16-REQUEST-", values
        )
    except Wo16ContractError as error:
        raise Wo16ApplicationError("WO16_REQUEST_INVALID") from error
    return Wo16OperationRequest(
        request_identity=request_identity,
        request_integrity=request_integrity,
        **values,
    )


class IntradayWo16Application:
    """Apply one supplied current-state decision without retaining hidden state."""

    def __init__(self) -> None:
        self._lock = Lock()

    def execute(
        self,
        request: Wo16OperationRequest,
        *,
        retained: Wo16Execution | None = None,
    ) -> Wo16Execution | Wo16BusyOutcome:
        if type(request) is not Wo16OperationRequest:
            raise Wo16ApplicationError("WO16_REQUEST_INVALID")
        try:
            request.__post_init__()
        except (AttributeError, TypeError, ValueError) as error:
            raise Wo16ApplicationError("WO16_REQUEST_INVALID") from error
        if not self._lock.acquire(blocking=False):
            return Wo16BusyOutcome(request.request_identity)

        try:
            trade_plan = bind_wo16_trade_plan(
                current_pointer=request.current_wo13_pointer,
                trade_plan=request.wo13_trade_plan,
                source_handoff=request.wo13_source_handoff,
            )
            risk_observation = bind_wo16_risk_observation(
                current_pointer=request.current_wo14_pointer,
                observation=request.wo14_observation,
                trade_plan=trade_plan,
            )
            if not is_wo16_risk_state_admissible(risk_observation.state):
                raise Wo16ApplicationError("WO16_RISK_OBSERVATION_INVALID")
            timing_handoff = bind_wo16_timing_handoff(
                current_pointer=request.current_wo15_pointer,
                handoff=request.wo15_timing_handoff,
                trade_plan=trade_plan,
                risk_observation=risk_observation,
            )
            session = bind_wo16_session_fact(
                wo15_session=request.wo15_session,
                fact=request.domain_008_session_fact,
                timing_handoff=timing_handoff,
            )
            upstream = bind_wo16_upstream(
                trade_plan=trade_plan,
                risk_observation=risk_observation,
                timing_handoff=timing_handoff,
                session=session,
            )
            snapshot = create_wo16_sponsor_decision_snapshot(
                upstream_lineage=upstream,
                snapshot_timestamp=request.snapshot_timestamp,
            )

            replay = _replay_or_conflict(request, snapshot, retained)
            if replay is not None:
                return replay

            decision = create_wo16_sponsor_decision_record(
                snapshot=snapshot,
                request_identity=request.request_identity,
                request_integrity=request.request_integrity,
                choice=request.choice,
                decision_timestamp=request.decision_timestamp,
            )
            admission = create_wo16_lifecycle_admission_record(
                decision=decision,
                recorded_at=request.admission_recorded_at,
            )
            return Wo16Execution(
                request_identity=request.request_identity,
                request_integrity=request.request_integrity,
                upstream_lineage=upstream,
                snapshot=snapshot,
                decision=decision,
                admission=admission,
                outcome=Wo16ApplicationOutcome.COMPLETED,
                replayed=False,
            )
        except Wo16ApplicationError:
            raise
        except (Wo16BindingRejected, Wo16ContractError) as error:
            raise Wo16ApplicationError(_failure_code(error)) from error
        except Exception as error:
            raise Wo16ApplicationError("WO16_APPLICATION_FAILURE") from error
        finally:
            self._lock.release()


def _replay_or_conflict(
    request: Wo16OperationRequest,
    snapshot: Wo16SponsorDecisionSnapshot,
    retained: Wo16Execution | None,
) -> Wo16Execution | None:
    if retained is None:
        return None
    if type(retained) is not Wo16Execution:
        raise Wo16ApplicationError("WO16_RETAINED_STATE_INVALID")
    try:
        retained.__post_init__()
    except (AttributeError, TypeError, ValueError) as error:
        raise Wo16ApplicationError("WO16_RETAINED_STATE_INVALID") from error

    if retained.request_identity == request.request_identity:
        if (
            retained.request_integrity != request.request_integrity
            or retained.snapshot != snapshot
            or retained.decision.choice is not request.choice
        ):
            raise Wo16ApplicationError("WO16_IDEMPOTENT_REPLAY_CONFLICT")
        return replace(
            retained,
            outcome=Wo16ApplicationOutcome.RETAINED_IDEMPOTENT,
            replayed=True,
        )

    same_handoff = (
        retained.decision.timing_handoff_identity
        == snapshot.upstream_lineage.timing_handoff.handoff_identity
    )
    same_lineage = (
        retained.upstream_lineage.lineage_identity
        == snapshot.upstream_lineage.lineage_identity
    )
    if same_handoff or same_lineage:
        raise Wo16ApplicationError("WO16_DECISION_ALREADY_FINAL")
    raise Wo16ApplicationError("WO16_RETAINED_STATE_LINEAGE_MISMATCH")


def _request_values(value: Wo16OperationRequest) -> dict[str, object]:
    return {
        "current_wo13_pointer": value.current_wo13_pointer,
        "wo13_trade_plan": value.wo13_trade_plan,
        "wo13_source_handoff": value.wo13_source_handoff,
        "current_wo14_pointer": value.current_wo14_pointer,
        "wo14_observation": value.wo14_observation,
        "current_wo15_pointer": value.current_wo15_pointer,
        "wo15_timing_handoff": value.wo15_timing_handoff,
        "wo15_session": value.wo15_session,
        "domain_008_session_fact": value.domain_008_session_fact,
        "choice": value.choice,
        "snapshot_timestamp": value.snapshot_timestamp,
        "decision_timestamp": value.decision_timestamp,
        "admission_recorded_at": value.admission_recorded_at,
        "policy": value.policy,
        "provenance": value.provenance,
        "schema_identity": value.schema_identity,
        "schema_version": value.schema_version,
    }


def _validate_source(value: object) -> None:
    try:
        value.__post_init__()  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError) as error:
        raise Wo16ApplicationError("WO16_REQUEST_SOURCE_INVALID") from error


def _failure_code(error: Exception) -> str:
    if isinstance(error, Wo16BindingRejected):
        return error.failure.value
    value = error.args[0] if error.args else None
    if type(value) is str and value.startswith("WO16_") and len(value) <= 128:
        return value
    return "WO16_APPLICATION_FAILURE"


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_document_bytes(value)).hexdigest().upper()


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: tuple[object, ...]) -> bool:
    return bool(values) and all(_text(value) for value in values)


__all__ = [
    "IntradayWo16Application",
    "WO16_APPLICATION_IDENTITY",
    "WO16_OPERATION_REQUEST_IDENTITY",
    "Wo16ApplicationError",
    "Wo16ApplicationOutcome",
    "Wo16BusyOutcome",
    "Wo16Execution",
    "Wo16OperationRequest",
    "create_wo16_operation_request",
]
