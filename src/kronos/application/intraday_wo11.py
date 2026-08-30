"""Explicit zero-discretion application and runtime boundary for WO-11."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock, RLock

from kronos.intraday.wo10 import (
    Wo10BatchResult,
    Wo10OperationOutcome,
    Wo10OperationProvenance,
    Wo10ReconciliationRequest,
    Wo10ReconciliationResult,
)
from kronos.intraday.wo10_persistence import Wo10PersistenceError, Wo10Store
from kronos.intraday.wo11 import (
    CurrentWo11PromotionPointer,
    Wo11ContractError,
    Wo11Member,
    Wo11OperationOutcome,
    Wo11OperationProvenance,
    Wo11OperationStage,
    Wo11PromotionPublication,
    Wo11PublicationRequest,
    Wo11SourceBatchBinding,
    create_current_wo11_pointer,
    create_wo11_member,
    create_wo11_operation_provenance,
    create_wo11_publication,
)
from kronos.intraday.wo11_persistence import (
    RestoredWo11State,
    Wo11PersistenceError,
    Wo11Store,
)


class Wo11ApplicationError(Wo11ContractError):
    """Sanitized WO-11 orchestration, binding, or concurrency failure."""


@dataclass(frozen=True, slots=True)
class Wo11Execution:
    request_identity: str
    publication: Wo11PromotionPublication
    members: tuple[Wo11Member, ...]
    pointer: CurrentWo11PromotionPointer
    operation: Wo11OperationProvenance


class IntradayWo11Application:
    """Validate and publish exact WO-10 results without analytical evaluation."""

    def __init__(
        self,
        *,
        wo10_store: Wo10Store,
        store: Wo11Store,
        backend_identity: str | None = None,
        process_identity: str | None = None,
    ) -> None:
        if (
            type(wo10_store) is not Wo10Store
            or type(store) is not Wo11Store
            or (backend_identity is not None and not _text(backend_identity))
            or (process_identity is not None and not _text(process_identity))
        ):
            raise ValueError("WO11_APPLICATION_CONFIGURATION_INVALID")
        self._wo10 = wo10_store
        self._store = store
        self._backend_identity = backend_identity
        self._process_identity = process_identity
        self._lock = Lock()

    @property
    def store(self) -> Wo11Store:
        return self._store

    def execute(self, request: Wo11PublicationRequest) -> Wo11Execution:
        if type(request) is not Wo11PublicationRequest:
            raise Wo11ApplicationError("WO11_REQUEST_INVALID")
        if not self._lock.acquire(blocking=False):
            raise Wo11ApplicationError("WO11_OPERATION_BUSY")
        started_at = request.requested_at
        stage = Wo11OperationStage.REQUEST_VALIDATION
        provenance = (*request.provenance, "WO11_ZERO_DISCRETION_APPLICATION_V1")
        try:
            self._store.retain_request(request)
            self._retain_started(request, stage, started_at, (*provenance, "REQUEST_VALIDATED"))

            loaded: list[tuple[
                Wo11SourceBatchBinding,
                Wo10BatchResult,
                Wo10ReconciliationRequest,
                tuple[Wo10ReconciliationResult, ...],
            ]] = []
            for source in request.source_batches:
                stage = Wo11OperationStage.WO10_BATCH_RELOAD
                self._retain_started(request, stage, started_at, (*provenance, source.batch_identity))
                batch = self._wo10.load_batch(source.batch_identity)
                wo10_request = self._wo10.load_request(source.request_identity)
                operation = self._wo10.load_operation(source.operation_identity)
                self._validate_source(source, batch, wo10_request, operation)

                stage = Wo11OperationStage.WO10_RESULT_VALIDATION
                self._retain_started(
                    request,
                    stage,
                    started_at,
                    (*provenance, source.batch_identity, "EXACT_RESULT_VALIDATION"),
                )
                results = tuple(self._wo10.load_result(item.result_identity) for item in batch.result_bindings)
                self._validate_results(source, batch, wo10_request, results)
                loaded.append((source, batch, wo10_request, results))

            stage = Wo11OperationStage.COLLATION
            self._retain_started(request, stage, started_at, (*provenance, "EXACT_RESULT_COLLATION"))
            members = tuple(
                create_wo11_member(
                    source=source,
                    batch=batch,
                    request=wo10_request,
                    result=result,
                    provenance=(*provenance, "WO10_STATE_PASSTHROUGH"),
                )
                for source, batch, wo10_request, results in loaded
                for result in results
            )

            stage = Wo11OperationStage.ELIGIBILITY_DERIVATION
            self._retain_started(request, stage, started_at, (*provenance, "MECHANICAL_ELIGIBILITY_ONLY"))
            publication = create_wo11_publication(
                request=request,
                members=members,
                published_at=request.requested_at,
                provenance=(*provenance, "NO_ANALYTICAL_EVALUATION"),
            )

            stage = Wo11OperationStage.PUBLICATION_PERSISTENCE
            self._retain_started(request, stage, started_at, (*provenance, "IMMUTABLE_PUBLICATION_PERSISTENCE"))
            for member in members:
                self._store.retain_member(member)
            self._store.retain_publication(publication)

            stage = Wo11OperationStage.POINTER_PUBLICATION
            pointer = create_current_wo11_pointer(publication)
            self._retain_started(
                request,
                stage,
                started_at,
                (*provenance, "FINAL_WRITE_POINTER_PUBLICATION"),
            )
            completed = create_wo11_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo11OperationOutcome.COMPLETED,
                started_at=started_at,
                completed_at=started_at,
                publication=publication,
                backend_identity=self._backend_identity,
                process_identity=self._process_identity,
                provenance=(*provenance, "PUBLICATION_PERSISTED_POINTER_READY"),
            )
            self._store.retain_operation(completed)
            # Replaceable current state is deliberately the final write.
            self._store.publish_current(pointer)
            return Wo11Execution(
                request.request_identity, publication, members, pointer, completed
            )
        except Exception as error:
            reason = _failure_code(error)
            failed = create_wo11_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo11OperationOutcome.FAILED,
                started_at=started_at,
                failed_at=started_at,
                failure_reason=reason,
                backend_identity=self._backend_identity,
                process_identity=self._process_identity,
                provenance=(*provenance, "CURRENT_POINTER_NOT_PUBLISHED"),
            )
            self._store.retain_operation(failed)
            raise Wo11ApplicationError(reason) from error
        finally:
            self._lock.release()

    def restore_current(self) -> RestoredWo11State | None:
        return self._store.restore_current()

    def _retain_started(
        self,
        request: Wo11PublicationRequest,
        stage: Wo11OperationStage,
        started_at: datetime,
        provenance: tuple[str, ...],
    ) -> None:
        self._store.retain_operation(create_wo11_operation_provenance(
            request=request,
            stage=stage,
            outcome=Wo11OperationOutcome.STARTED,
            started_at=started_at,
            backend_identity=self._backend_identity,
            process_identity=self._process_identity,
            provenance=provenance,
        ))

    def _validate_source(
        self,
        source: Wo11SourceBatchBinding,
        batch: Wo10BatchResult,
        request: Wo10ReconciliationRequest,
        operation: Wo10OperationProvenance,
    ) -> None:
        if (
            type(batch) is not Wo10BatchResult
            or type(request) is not Wo10ReconciliationRequest
            or type(operation) is not Wo10OperationProvenance
            or batch.batch_identity != source.batch_identity
            or batch.batch_integrity != source.batch_integrity
            or batch.request_identity != source.request_identity
            or batch.request_integrity != source.request_integrity
            or batch.market_family is not source.market_family
            or request.request_identity != source.request_identity
            or request.request_integrity != source.request_integrity
            or request.market_family is not source.market_family
            or request.policy != batch.policy
            or source.policy != request.policy
            or source.probables_run_identity != request.probables_run_identity
            or source.probables_run_integrity != request.probables_run_integrity
            or source.published_population != batch.published_population
            or operation.operation_identity != source.operation_identity
            or operation.integrity_identity != source.operation_integrity
            or operation.outcome is not Wo10OperationOutcome.COMPLETED
            or operation.batch_identity != batch.batch_identity
            or operation.request_identity != request.request_identity
            or operation.request_integrity != request.request_integrity
            or operation.policy != request.policy
            or operation.probables_run_identity != request.probables_run_identity
            or operation.result_identities
            != tuple(sorted(item.result_identity for item in batch.result_bindings))
        ):
            raise Wo11ApplicationError("WO11_WO10_SOURCE_BINDING_INVALID")

    def _validate_results(
        self,
        source: Wo11SourceBatchBinding,
        batch: Wo10BatchResult,
        request: Wo10ReconciliationRequest,
        results: tuple[Wo10ReconciliationResult, ...],
    ) -> None:
        probable_by_subject = {
            item.canonical_subject_identity: item for item in request.probable_bindings
        }
        if len(results) != len(batch.result_bindings):
            raise Wo11ApplicationError("WO11_WO10_RESULT_POPULATION_INVALID")
        for binding, result in zip(batch.result_bindings, results, strict=True):
            probable = probable_by_subject.get(binding.canonical_subject_identity)
            if (
                type(result) is not Wo10ReconciliationResult
                or probable is None
                or result.result_identity != binding.result_identity
                or result.result_integrity != binding.result_integrity
                or result.request_identity != request.request_identity
                or result.request_integrity != request.request_integrity
                or result.market_family is not source.market_family
                or result.policy != request.policy
                or result.canonical_subject_identity != probable.canonical_subject_identity
                or result.inherited_direction is not probable.inherited_direction
                or result.analysis_boundary != probable.analysis_boundary
                or result.persisted_phase is not probable.persisted_phase
            ):
                raise Wo11ApplicationError("WO11_WO10_RESULT_BINDING_INVALID")
            snapshot = self._wo10.load_evidence_snapshot(result.evidence_snapshot_identity)
            if (
                snapshot.snapshot_integrity != result.evidence_snapshot_integrity
                or snapshot.canonical_subject_identity != result.canonical_subject_identity
                or snapshot.inherited_direction is not result.inherited_direction
                or snapshot.market_family is not result.market_family
                or snapshot.policy != result.policy
                or snapshot.probables_run_identity != request.probables_run_identity
                or snapshot.probables_run_integrity != request.probables_run_integrity
                or snapshot.probable_result_identity != probable.probable_result_identity
                or snapshot.probable_result_integrity != probable.probable_result_integrity
            ):
                raise Wo11ApplicationError("WO11_WO10_EVIDENCE_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo11RuntimeStatus:
    state: str
    restored: RestoredWo11State | None
    failure_stage: str | None = None
    failure_reason: str | None = None


class IntradayWo11RuntimeService:
    """Provider-independent restoration; publication occurs only on execute."""

    def __init__(self, application: IntradayWo11Application) -> None:
        if type(application) is not IntradayWo11Application:
            raise ValueError("WO11_RUNTIME_CONFIGURATION_INVALID")
        self._application = application
        self._lock = RLock()
        self._active_request_identity: str | None = None
        self._last_execution: Wo11Execution | None = None
        self._status = self._restore()

    @property
    def application(self) -> IntradayWo11Application:
        return self._application

    @property
    def store(self) -> Wo11Store:
        return self._application.store

    @property
    def active_request_identity(self) -> str | None:
        with self._lock:
            return self._active_request_identity

    @property
    def last_execution(self) -> Wo11Execution | None:
        with self._lock:
            return self._last_execution

    @property
    def status(self) -> Wo11RuntimeStatus:
        with self._lock:
            return self._status

    def execute(self, request: Wo11PublicationRequest) -> Wo11Execution:
        with self._lock:
            self._active_request_identity = request.request_identity
        try:
            execution = self._application.execute(request)
            with self._lock:
                self._last_execution = execution
                self._status = self._restore()
            return execution
        finally:
            with self._lock:
                self._active_request_identity = None

    def _restore(self) -> Wo11RuntimeStatus:
        try:
            restored = self._application.restore_current()
        except (Wo11PersistenceError, Wo11ContractError, OSError, ValueError):
            return Wo11RuntimeStatus("CORRUPT", None, "RESTORATION", "WO11_RESTORATION_FAILED")
        return Wo11RuntimeStatus("NOT_YET_PUBLISHED" if restored is None else "LOADED", restored)


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if type(value) is str and value.startswith("WO11_") and len(value) <= 128:
        return value
    if isinstance(error, Wo10PersistenceError):
        return "WO11_WO10_ARTIFACT_UNAVAILABLE"
    return "WO11_APPLICATION_FAILURE"


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


__all__ = [
    "IntradayWo11Application",
    "IntradayWo11RuntimeService",
    "Wo11ApplicationError",
    "Wo11Execution",
    "Wo11RuntimeStatus",
]
