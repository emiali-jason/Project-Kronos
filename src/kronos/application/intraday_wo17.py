"""WO-17 Slice 5 application, persistence, and restoration boundary.

The application accepts only immutable outputs of the published WO-17 Slice
1--4 engines.  It validates and persists those facts; it does not reproduce
their analytical or lifecycle logic.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from hashlib import sha256
from threading import Lock
from typing import Sequence

from kronos.intraday.wo17 import (
    WO17_CONTRACT_VERSION,
    Wo17ContractError,
    Wo17UpstreamSnapshot,
    canonical_document_bytes,
)
from kronos.intraday.wo17_closure import (
    Wo17ClosureMachine,
    Wo17ClosureState,
    Wo17LiveExitAttestation,
)
from kronos.intraday.wo17_lifecycle import Wo17LifecycleMachine
from kronos.intraday.wo17_persistence import (
    CurrentWo17Pointer,
    RestoredWo17State,
    Wo17InvalidOperationProvenance,
    Wo17OperationOutcome,
    Wo17OperationProvenance,
    Wo17OperationStage,
    Wo17PersistenceError,
    Wo17RestorationState,
    Wo17Store,
    _validate_graph,
    create_current_wo17_pointer,
    create_wo17_invalid_operation,
    create_wo17_operation_provenance,
    create_wo17_successor_lineage,
)
from kronos.intraday.wo17_position import (
    Wo17PositionMachine,
    Wo17PositionState,
    Wo17PreEntryInvalidationFact,
)


WO17_OPERATION_REQUEST_IDENTITY = "KRONOS-INTRADAY-WO17-OPERATION-REQUEST-V1"
WO17_APPLICATION_IDENTITY = "KRONOS-INTRADAY-WO17-APPLICATION-V1"


class Wo17ApplicationError(Wo17ContractError):
    """Sanitized application-boundary failure."""


@dataclass(frozen=True, slots=True)
class Wo17OperationRequest:
    request_identity: str
    request_integrity: str
    canonical_subject_identity: str
    snapshot: Wo17UpstreamSnapshot
    position: Wo17PositionMachine
    lifecycle: Wo17LifecycleMachine | None
    closure: Wo17ClosureMachine | None
    live_exit_attestation: Wo17LiveExitAttestation | None
    pre_entry_invalidation: Wo17PreEntryInvalidationFact | None
    requested_at: datetime
    provenance: tuple[str, ...]
    schema_identity: str = WO17_OPERATION_REQUEST_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    provider_acquisition_authority: bool = False
    clock_acquisition_authority: bool = False
    browser_authority: bool = False
    broker_order_authority: bool = False
    notification_delivery_authority: bool = False
    journal_analytics_authority: bool = False
    quantity: str = "UNAVAILABLE"
    fees: str = "UNAVAILABLE"
    monetary_pnl: str = "UNAVAILABLE"
    realised_r: str = "UNAVAILABLE"

    def __post_init__(self) -> None:
        values = _without(self, "request_identity", "request_integrity")
        latest_transition = max(
            item
            for item in (
                self.position.last_transition_at,
                None if self.lifecycle is None else self.lifecycle.last_transition_at,
                None if self.closure is None else self.closure.last_transition_at,
                None
                if self.live_exit_attestation is None
                else self.live_exit_attestation.attestation_operation_timestamp,
                None
                if self.pre_entry_invalidation is None
                else self.pre_entry_invalidation.observed_at,
            )
            if item is not None
        )
        if (
            not _text(self.canonical_subject_identity)
            or type(self.snapshot) is not Wo17UpstreamSnapshot
            or type(self.position) is not Wo17PositionMachine
            or self.lifecycle is not None
            and type(self.lifecycle) is not Wo17LifecycleMachine
            or self.closure is not None
            and type(self.closure) is not Wo17ClosureMachine
            or self.live_exit_attestation is not None
            and type(self.live_exit_attestation) is not Wo17LiveExitAttestation
            or self.pre_entry_invalidation is not None
            and type(self.pre_entry_invalidation) is not Wo17PreEntryInvalidationFact
            or not _aware(self.requested_at)
            or self.requested_at < latest_transition
            or not _texts(self.provenance)
            or self.schema_identity != WO17_OPERATION_REQUEST_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or any(
                (
                    self.provider_acquisition_authority,
                    self.clock_acquisition_authority,
                    self.browser_authority,
                    self.broker_order_authority,
                    self.notification_delivery_authority,
                    self.journal_analytics_authority,
                )
            )
            or any(
                item != "UNAVAILABLE"
                for item in (
                    self.quantity,
                    self.fees,
                    self.monetary_pnl,
                    self.realised_r,
                )
            )
            or self.request_identity != _identity("INTRADAY-WO17-REQUEST-", values)
            or self.request_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-REQUEST-", values)
        ):
            raise Wo17ApplicationError("WO17_REQUEST_INVALID")
        try:
            _validate_graph(self)
        except Wo17PersistenceError as error:
            raise Wo17ApplicationError(error.args[0]) from error


@dataclass(frozen=True, slots=True)
class Wo17PersistedExecution:
    request: Wo17OperationRequest
    pointer: CurrentWo17Pointer
    operation: Wo17OperationProvenance
    replayed: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.request) is not Wo17OperationRequest
            or type(self.pointer) is not CurrentWo17Pointer
            or type(self.operation) is not Wo17OperationProvenance
            or self.pointer.request_identity != self.request.request_identity
            or self.pointer.operation_identity != self.operation.operation_identity
            or self.operation.outcome is not Wo17OperationOutcome.COMPLETED
        ):
            raise Wo17ApplicationError("WO17_PERSISTED_EXECUTION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17BusyOutcome:
    request_identity: str
    outcome: str = "BUSY"
    writes_performed: int = 0


@dataclass(frozen=True, slots=True)
class Wo17RestorationStatus:
    state: Wo17RestorationState
    restored: tuple[RestoredWo17State, ...]
    latest_failures: tuple[Wo17InvalidOperationProvenance, ...]
    failure_stage: str | None = None
    failure_reason: str | None = None


def create_wo17_operation_request(
    *,
    snapshot: Wo17UpstreamSnapshot,
    position: Wo17PositionMachine,
    requested_at: datetime,
    lifecycle: Wo17LifecycleMachine | None = None,
    closure: Wo17ClosureMachine | None = None,
    live_exit_attestation: Wo17LiveExitAttestation | None = None,
    pre_entry_invalidation: Wo17PreEntryInvalidationFact | None = None,
    provenance: tuple[str, ...] = ("ADR-0027", "WO-17-SLICE-5"),
) -> Wo17OperationRequest:
    subject = snapshot.lineage.canonical_subject_identity
    values = {
        "canonical_subject_identity": subject,
        "snapshot": snapshot,
        "position": position,
        "lifecycle": lifecycle,
        "closure": closure,
        "live_exit_attestation": live_exit_attestation,
        "pre_entry_invalidation": pre_entry_invalidation,
        "requested_at": requested_at,
        "provenance": provenance,
        "schema_identity": WO17_OPERATION_REQUEST_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "provider_acquisition_authority": False,
        "clock_acquisition_authority": False,
        "browser_authority": False,
        "broker_order_authority": False,
        "notification_delivery_authority": False,
        "journal_analytics_authority": False,
        "quantity": "UNAVAILABLE",
        "fees": "UNAVAILABLE",
        "monetary_pnl": "UNAVAILABLE",
        "realised_r": "UNAVAILABLE",
    }
    return Wo17OperationRequest(
        request_identity=_identity("INTRADAY-WO17-REQUEST-", values),
        request_integrity=_identity("INTEGRITY-INTRADAY-WO17-REQUEST-", values),
        **values,
    )


class IntradayWo17Application:
    """Persist exact Slice 1--4 state using one nonblocking operation lock."""

    def __init__(self, *, store: Wo17Store) -> None:
        if type(store) is not Wo17Store:
            raise ValueError("WO17_APPLICATION_CONFIGURATION_INVALID")
        self._store = store
        self._lock = Lock()

    @property
    def store(self) -> Wo17Store:
        return self._store

    def execute(
        self, request: Wo17OperationRequest
    ) -> Wo17PersistedExecution | Wo17BusyOutcome:
        if type(request) is not Wo17OperationRequest:
            raise Wo17ApplicationError("WO17_REQUEST_INVALID")
        try:
            request.__post_init__()
        except (AttributeError, TypeError, ValueError) as error:
            raise Wo17ApplicationError(_failure_code(error)) from error
        if not self._lock.acquire(blocking=False):
            return Wo17BusyOutcome(request.request_identity)

        stage = Wo17OperationStage.REQUEST_VALIDATION
        try:
            stage = Wo17OperationStage.REPLAY_VALIDATION
            retained = self._store.find_completed_request(request.request_identity)
            if retained is not None:
                if retained.request != request:
                    raise Wo17ApplicationError("WO17_IDEMPOTENT_REPLAY_CONFLICT")
                return Wo17PersistedExecution(
                    retained.request,
                    retained.pointer,
                    retained.operation,
                    True,
                )

            stage = Wo17OperationStage.LINEAGE_VALIDATION
            _validate_graph(request)
            current = self._store.restore_current(request.canonical_subject_identity)

            stage = Wo17OperationStage.CARDINALITY_VALIDATION
            _validate_progression(current, request)

            stage = Wo17OperationStage.PERSISTENCE
            self._store.retain_graph(request)
            operation = create_wo17_operation_provenance(
                request=request,
                stage=Wo17OperationStage.POINTER_PUBLICATION,
                outcome=Wo17OperationOutcome.COMPLETED,
                started_at=request.requested_at,
                completed_at=request.requested_at,
                provenance=(*request.provenance, "FULL_GRAPH_RELOAD_REQUIRED"),
            )
            self._store.retain_operation(operation)
            successor = None
            if (
                current is not None
                and current.pointer.upstream_snapshot_identity
                != request.snapshot.snapshot_identity
            ):
                successor = create_wo17_successor_lineage(
                    predecessor=current.pointer,
                    request=request,
                    established_at=request.requested_at,
                )
                self._store.retain_successor(successor)
            pointer = create_current_wo17_pointer(
                request=request,
                operation=operation,
                predecessor=None if current is None else current.pointer,
                successor=successor,
                published_at=request.requested_at,
            )
            self._store.retain_pointer_snapshot(pointer)
            staged = self._store.restore_pointer(pointer)
            if (
                staged.request != request
                or staged.snapshot != request.snapshot
                or staged.position != request.position
                or staged.lifecycle != request.lifecycle
                or staged.closure != request.closure
                or staged.operation != operation
            ):
                raise Wo17ApplicationError("WO17_PRE_PUBLICATION_RELOAD_INVALID")

            stage = Wo17OperationStage.POINTER_PUBLICATION
            self._store.publish_current(pointer)
            stage = Wo17OperationStage.RESTORATION
            restored = self._store.restore_current(request.canonical_subject_identity)
            if restored is None or restored.pointer != pointer or restored.request != request:
                raise Wo17ApplicationError("WO17_POST_PUBLICATION_RELOAD_INVALID")
            return Wo17PersistedExecution(request, pointer, operation)
        except Exception as error:
            reason = _failure_code(error)
            self._record_failure(request, stage, reason)
            raise Wo17ApplicationError(reason) from error
        finally:
            self._lock.release()

    def _record_failure(
        self,
        request: Wo17OperationRequest,
        stage: Wo17OperationStage,
        reason: str,
    ) -> None:
        try:
            failed = create_wo17_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo17OperationOutcome.FAILED,
                started_at=request.requested_at,
                failed_at=request.requested_at,
                failure_reason=reason,
                provenance=(*request.provenance, "CURRENT_WO17_POINTER_PRESERVED"),
            )
            invalid = create_wo17_invalid_operation(
                request=request,
                stage=stage,
                reason=reason,
                failed_at=request.requested_at,
            )
            self._store.retain_operation(failed)
            self._store.publish_latest_failure(invalid)
        except (OSError, TypeError, ValueError):
            return


class IntradayWo17RestorationService:
    """Read-only restoration with no recalculation, transition, or writes."""

    def __init__(self, *, store: Wo17Store) -> None:
        if type(store) is not Wo17Store:
            raise ValueError("WO17_RESTORATION_CONFIGURATION_INVALID")
        self._store = store

    def restore(self) -> Wo17RestorationStatus:
        try:
            restored = self._store.restore_all()
            failures = tuple(
                value
                for subject in self._store.failure_subjects()
                if (value := self._store.load_latest_failure(subject)) is not None
            )
        except (Wo17PersistenceError, Wo17ContractError, OSError, ValueError):
            return Wo17RestorationStatus(
                Wo17RestorationState.CORRUPT,
                (),
                (),
                "RESTORATION",
                "WO17_RESTORATION_FAILED",
            )
        return Wo17RestorationStatus(
            Wo17RestorationState.NOT_YET_RUN if not restored else Wo17RestorationState.LOADED,
            restored,
            failures,
        )


def _validate_progression(
    current: RestoredWo17State | None, request: Wo17OperationRequest
) -> None:
    if current is None:
        return
    pointer = current.pointer
    if request.requested_at < pointer.published_at:
        raise Wo17ApplicationError("WO17_STALE_OPERATION")
    same_snapshot = pointer.upstream_snapshot_identity == request.snapshot.snapshot_identity
    if pointer.non_closed and not same_snapshot:
        raise Wo17ApplicationError("WO17_EXISTING_NON_CLOSED_POSITION")
    if not pointer.non_closed and same_snapshot:
        raise Wo17ApplicationError("WO17_CLOSED_POSITION_FINAL")
    if same_snapshot:
        if not _prefix(current.position.observations, request.position.observations):
            raise Wo17ApplicationError("WO17_POSITION_HISTORY_CONFLICT")
        if current.lifecycle is not None:
            if request.lifecycle is None:
                raise Wo17ApplicationError("WO17_LIFECYCLE_STATE_REGRESSION")
            if not _prefix(current.lifecycle.observations, request.lifecycle.observations):
                raise Wo17ApplicationError("WO17_OBSERVATION_HISTORY_CONFLICT")
            if not _prefix(current.lifecycle.assessments, request.lifecycle.assessments):
                raise Wo17ApplicationError("WO17_ASSESSMENT_HISTORY_CONFLICT")
        if current.closure is not None:
            if request.closure is None:
                raise Wo17ApplicationError("WO17_CLOSURE_STATE_REGRESSION")
            if not _prefix(current.closure.events, request.closure.events):
                raise Wo17ApplicationError("WO17_EVENT_HISTORY_CONFLICT")
            if current.closure.closure is not None and request.closure.closure != current.closure.closure:
                raise Wo17ApplicationError("WO17_CLOSURE_CONFLICT")


def _prefix(before: Sequence[object], after: Sequence[object]) -> bool:
    return len(after) >= len(before) and tuple(after[: len(before)]) == tuple(before)


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if (
        type(value) is str
        and value.startswith("WO17_")
        and len(value) <= 128
        and all(item.isupper() or item.isdigit() or item == "_" for item in value)
    ):
        return value
    if isinstance(error, Wo17PersistenceError):
        return "WO17_PERSISTENCE_FAILURE"
    return "WO17_APPLICATION_FAILURE"


def _without(value: object, *names: str) -> dict[str, object]:
    return {item.name: getattr(value, item.name) for item in fields(value) if item.name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_document_bytes(value)).hexdigest().upper()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(value) for value in values)


__all__ = [name for name in globals() if name.startswith(("WO17_", "Wo17", "Intraday", "create_"))]
