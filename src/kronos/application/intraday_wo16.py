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
    Wo16SuccessorLineage,
    Wo16SuccessorTrigger,
    Wo16UpstreamLineage,
    canonical_document_bytes,
    create_wo16_lifecycle_admission_record,
    create_wo16_sponsor_decision_record,
    create_wo16_sponsor_decision_snapshot,
    create_wo16_successor_lineage,
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
from kronos.intraday.wo16_persistence import (
    CurrentWo16Pointer,
    RestoredWo16State,
    Wo16InvalidOperationProvenance,
    Wo16OperationProvenance,
    Wo16OperationStage,
    Wo16PersistedOperationOutcome,
    Wo16PersistenceError,
    Wo16RestorationState,
    Wo16Store,
    create_current_wo16_pointer,
    create_wo16_invalid_operation,
    create_wo16_operation_provenance,
)


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


@dataclass(frozen=True, slots=True)
class Wo16PersistedExecution:
    """Committed immutable graph and projection returned by Slice 3."""

    execution: Wo16Execution
    pointer: CurrentWo16Pointer
    operation: Wo16OperationProvenance
    successor: Wo16SuccessorLineage | None
    replayed: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.execution) is not Wo16Execution
            or type(self.pointer) is not CurrentWo16Pointer
            or type(self.operation) is not Wo16OperationProvenance
            or self.successor is not None
            and type(self.successor) is not Wo16SuccessorLineage
            or self.pointer.request_identity != self.execution.request_identity
            or self.pointer.request_integrity != self.execution.request_integrity
            or self.pointer.decision_identity
            != self.execution.decision.decision_identity
            or self.pointer.admission_identity
            != self.execution.admission.admission_identity
            or self.pointer.operation_identity != self.operation.operation_identity
            or self.replayed != self.execution.replayed
        ):
            raise Wo16ApplicationError("WO16_PERSISTED_EXECUTION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16RestorationStatus:
    """Inert multi-subject restoration result."""

    state: Wo16RestorationState
    restored: tuple[RestoredWo16State, ...]
    latest_failures: tuple[Wo16InvalidOperationProvenance, ...]
    failure_stage: str | None = None
    failure_reason: str | None = None


class IntradayWo16PersistenceApplication:
    """Persist exact Slice-2 results without acquiring or recalculating facts."""

    def __init__(self, *, store: Wo16Store) -> None:
        if type(store) is not Wo16Store:
            raise ValueError("WO16_APPLICATION_CONFIGURATION_INVALID")
        self._store = store
        self._decision_service = IntradayWo16Application()
        self._lock = Lock()

    @property
    def store(self) -> Wo16Store:
        return self._store

    def execute(
        self, request: Wo16OperationRequest
    ) -> Wo16PersistedExecution | Wo16BusyOutcome:
        if type(request) is not Wo16OperationRequest:
            raise Wo16ApplicationError("WO16_REQUEST_INVALID")
        try:
            request.__post_init__()
        except (AttributeError, TypeError, ValueError) as error:
            raise Wo16ApplicationError("WO16_REQUEST_INVALID") from error
        if not self._lock.acquire(blocking=False):
            return Wo16BusyOutcome(request.request_identity)

        stage = Wo16OperationStage.REQUEST_VALIDATION
        started_at = request.domain_008_session_fact.observed_at
        provenance = (*request.provenance, "WO16_PERSISTENCE_APPLICATION_V1")
        try:
            stage = Wo16OperationStage.REPLAY_VALIDATION
            retained = self._store.find_completed_request(
                request.request_identity
            )
            if retained is not None:
                replay = self._decision_service.execute(
                    request, retained=_execution_from_restored(retained)
                )
                if type(replay) is not Wo16Execution or not replay.replayed:
                    raise Wo16ApplicationError("WO16_IDEMPOTENT_REPLAY_INVALID")
                return Wo16PersistedExecution(
                    replay,
                    retained.pointer,
                    retained.operation,
                    retained.successor,
                    True,
                )

            subject = request.wo13_trade_plan.canonical_subject_identity
            current = self._store.restore_current(subject)
            retained_current = (
                None if current is None else _execution_from_restored(current)
            )

            stage = Wo16OperationStage.UPSTREAM_BINDING
            if (
                retained_current is not None
                and retained_current.decision.timing_handoff_identity
                == request.wo15_timing_handoff.handoff_identity
            ):
                # The Slice-2 conflict boundary owns the final-decision rule.
                self._decision_service.execute(
                    request, retained=retained_current
                )
                raise Wo16ApplicationError("WO16_DECISION_ALREADY_FINAL")
            candidate = self._decision_service.execute(request)
            if type(candidate) is not Wo16Execution:
                raise Wo16ApplicationError("WO16_UNEXPECTED_BUSY_OUTCOME")

            stage = Wo16OperationStage.SUCCESSOR_BINDING
            successor = None
            if current is not None:
                trigger = _successor_trigger(current.pointer, candidate)
                successor = create_wo16_successor_lineage(
                    predecessor=current.decision,
                    successor_snapshot=candidate.snapshot,
                    trigger=trigger,
                    provenance=(*provenance, trigger.value),
                )
                decision = create_wo16_sponsor_decision_record(
                    snapshot=candidate.snapshot,
                    request_identity=request.request_identity,
                    request_integrity=request.request_integrity,
                    choice=request.choice,
                    decision_timestamp=request.decision_timestamp,
                    predecessor_decision_identity=(
                        current.decision.decision_identity
                    ),
                    supersession_lineage_identity=successor.lineage_identity,
                    provenance=(*provenance, "IMMUTABLE_SUCCESSOR"),
                )
                admission = create_wo16_lifecycle_admission_record(
                    decision=decision,
                    recorded_at=request.admission_recorded_at,
                    provenance=(*provenance, "FACTUAL_ADMISSION"),
                )
                candidate = Wo16Execution(
                    request_identity=request.request_identity,
                    request_integrity=request.request_integrity,
                    upstream_lineage=candidate.upstream_lineage,
                    snapshot=candidate.snapshot,
                    decision=decision,
                    admission=admission,
                    outcome=Wo16ApplicationOutcome.COMPLETED,
                    replayed=False,
                )

            stage = Wo16OperationStage.PERSISTENCE
            self._store.retain_request(request)
            self._store.retain_snapshot(candidate.snapshot)
            self._store.retain_decision(candidate.decision)
            self._store.retain_admission(candidate.admission)
            if successor is not None:
                self._store.retain_successor(successor)
            completed = create_wo16_operation_provenance(
                request=request,
                stage=Wo16OperationStage.POINTER_PUBLICATION,
                outcome=Wo16PersistedOperationOutcome.COMPLETED,
                started_at=started_at,
                completed_at=request.admission_recorded_at,
                snapshot=candidate.snapshot,
                decision=candidate.decision,
                admission=candidate.admission,
                successor=successor,
                provenance=(*provenance, "FULL_GRAPH_RELOAD_REQUIRED"),
            )
            self._store.retain_operation(completed)
            pointer = create_current_wo16_pointer(
                request=request,
                snapshot=candidate.snapshot,
                decision=candidate.decision,
                admission=candidate.admission,
                operation=completed,
                successor=successor,
                published_at=request.admission_recorded_at,
            )
            # The immutable pointer snapshot is not an alias and may safely
            # precede publication.  It enables validation of the full history.
            self._store.retain_pointer_snapshot(pointer)
            staged = self._store.restore_pointer(pointer)
            if (
                staged.request != request
                or staged.snapshot != candidate.snapshot
                or staged.decision != candidate.decision
                or staged.admission != candidate.admission
                or staged.operation != completed
                or staged.successor != successor
            ):
                raise Wo16ApplicationError("WO16_PRE_PUBLICATION_RELOAD_INVALID")

            stage = Wo16OperationStage.POINTER_PUBLICATION
            self._store.publish_current(pointer)
            stage = Wo16OperationStage.RESTORATION
            restored = self._store.restore_current(subject)
            if (
                restored is None
                or restored.pointer != pointer
                or restored.request != request
                or restored.snapshot != candidate.snapshot
                or restored.decision != candidate.decision
                or restored.admission != candidate.admission
                or restored.operation != completed
                or restored.successor != successor
            ):
                raise Wo16ApplicationError("WO16_POST_PUBLICATION_RELOAD_INVALID")
            return Wo16PersistedExecution(
                candidate, pointer, completed, successor
            )
        except Exception as error:
            reason = _persistent_failure_code(error)
            self._record_failure(
                request,
                stage,
                started_at,
                reason,
                provenance,
            )
            raise Wo16ApplicationError(reason) from error
        finally:
            self._lock.release()

    def restore_current(
        self, canonical_subject_identity: str
    ) -> RestoredWo16State | None:
        return self._store.restore_current(canonical_subject_identity)

    def _record_failure(
        self,
        request: Wo16OperationRequest,
        stage: Wo16OperationStage,
        started_at: datetime,
        reason: str,
        provenance: tuple[str, ...],
    ) -> None:
        try:
            failed = create_wo16_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo16PersistedOperationOutcome.FAILED,
                started_at=started_at,
                failed_at=request.admission_recorded_at,
                failure_reason=reason,
                provenance=(*provenance, "CURRENT_WO16_POINTER_PRESERVED"),
            )
            invalid = create_wo16_invalid_operation(
                request=request,
                stage=stage,
                reason=reason,
                failed_at=request.admission_recorded_at,
            )
            self._store.retain_operation(failed)
            self._store.publish_latest_failure(invalid)
        except (OSError, TypeError, ValueError):
            # Secondary provenance failure must never replace the original
            # sanitized application failure or move the current pointer.
            return


class IntradayWo16RestorationService:
    """Provider-independent restoration with no evaluation or writes."""

    def __init__(self, *, store: Wo16Store) -> None:
        if type(store) is not Wo16Store:
            raise ValueError("WO16_RESTORATION_CONFIGURATION_INVALID")
        self._store = store

    def restore(self) -> Wo16RestorationStatus:
        try:
            restored = self._store.restore_all()
            failure_subjects = self._store.failure_subjects()
            failures = tuple(
                failure
                for subject in failure_subjects
                if (failure := self._store.load_latest_failure(subject))
                is not None
            )
        except (Wo16PersistenceError, Wo16ContractError, OSError, ValueError):
            return Wo16RestorationStatus(
                Wo16RestorationState.CORRUPT,
                (),
                (),
                "RESTORATION",
                "WO16_RESTORATION_FAILED",
            )
        return Wo16RestorationStatus(
            (
                Wo16RestorationState.NOT_YET_RUN
                if not restored
                else Wo16RestorationState.LOADED
            ),
            restored,
            failures,
        )


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


def _execution_from_restored(value: RestoredWo16State) -> Wo16Execution:
    return Wo16Execution(
        request_identity=value.request.request_identity,
        request_integrity=value.request.request_integrity,
        upstream_lineage=value.snapshot.upstream_lineage,
        snapshot=value.snapshot,
        decision=value.decision,
        admission=value.admission,
        outcome=Wo16ApplicationOutcome.COMPLETED,
        replayed=False,
    )


def _successor_trigger(
    predecessor: CurrentWo16Pointer,
    successor: Wo16Execution,
) -> Wo16SuccessorTrigger:
    trade = successor.upstream_lineage.trade_plan
    session = successor.upstream_lineage.session
    timing = successor.upstream_lineage.timing_handoff
    if (
        predecessor.actual_contract_identity != trade.actual_contract_identity
        or predecessor.roll_lineage_identity != trade.roll_lineage_identity
        or (
            predecessor.instrument_identity != trade.instrument_identity
            and trade.market_family.value == "MCX"
        )
    ):
        return Wo16SuccessorTrigger.MCX_ACTIVE_CONTRACT_OR_ROLL_LINEAGE
    if (
        predecessor.session_identity != session.session_identity
        or predecessor.trading_date != session.trading_date
        or predecessor.calendar_identity != session.calendar_identity
        or predecessor.calendar_version != session.calendar_version
    ):
        return Wo16SuccessorTrigger.MARKET_SESSION
    if predecessor.wo13_trade_plan_identity != trade.trade_plan_identity:
        return Wo16SuccessorTrigger.WO13_PLAN
    if predecessor.wo15_handoff_identity != timing.handoff_identity:
        return Wo16SuccessorTrigger.WO15_TIMING_HANDOFF
    raise Wo16ApplicationError("WO16_SUCCESSOR_TRIGGER_UNAVAILABLE")


def _persistent_failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    allowed_prefixes = (
        "WO13_",
        "WO14_",
        "WO15_",
        "WO16_",
        "DOMAIN_008_",
        "CALENDAR_",
        "SESSION_",
        "EXCHANGE_",
        "INSTRUMENT_",
        "CONTRACT_",
        "ROLL_",
    )
    if (
        type(value) is str
        and value.startswith(allowed_prefixes)
        and len(value) <= 128
        and all(
            character.isupper()
            or character.isdigit()
            or character == "_"
            for character in value
        )
    ):
        return value
    if isinstance(error, Wo16PersistenceError):
        return "WO16_PERSISTENCE_FAILURE"
    return "WO16_APPLICATION_FAILURE"


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
    "IntradayWo16PersistenceApplication",
    "IntradayWo16RestorationService",
    "WO16_APPLICATION_IDENTITY",
    "WO16_OPERATION_REQUEST_IDENTITY",
    "Wo16ApplicationError",
    "Wo16ApplicationOutcome",
    "Wo16BusyOutcome",
    "Wo16Execution",
    "Wo16OperationRequest",
    "Wo16PersistedExecution",
    "Wo16RestorationStatus",
    "create_wo16_operation_request",
]
