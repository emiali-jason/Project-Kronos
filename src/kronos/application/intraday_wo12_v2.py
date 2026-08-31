"""Application and inert-restoring runtime service for Intraday WO-12 V2."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock, RLock

from kronos.intraday.wo10 import Wo10ReconciliationRequest, Wo10ReconciliationResult
from kronos.intraday.wo10_evidence import Wo10EvidenceSnapshot
from kronos.intraday.wo10_persistence import Wo10PersistenceError, Wo10Store
from kronos.intraday.wo11 import Wo11Member, Wo11PromotionPublication
from kronos.intraday.wo11_persistence import Wo11PersistenceError, Wo11Store
from kronos.intraday.wo12 import (
    Wo12ContractError,
    Wo12OperationOutcome,
    Wo12OperationStage,
    create_wo12_handoff,
)
from kronos.intraday.wo12_v2 import (
    CurrentWo12PointerV2,
    Wo12EvidenceInputsV2,
    Wo12EvidenceV2,
    Wo12OperationProvenanceV2,
    Wo12RequestV2,
    Wo12ResultV2,
    Wo13EligibilityRecordV2,
    assemble_wo12_criteria_v2,
    create_current_wo12_pointer_v2,
    create_wo12_evidence_v2,
    create_wo12_operation_provenance_v2,
    create_wo12_result_v2,
    create_wo13_eligibility_v2,
)
from kronos.intraday.wo12_v2_persistence import (
    RestoredWo12V2State,
    Wo12V2PersistenceError,
    Wo12V2Store,
)


class Wo12V2ApplicationError(Wo12ContractError):
    """Sanitized V2 orchestration or exact-binding failure."""


@dataclass(frozen=True, slots=True)
class Wo12V2Execution:
    request_identity: str
    evidence: Wo12EvidenceV2
    result: Wo12ResultV2
    eligibility: Wo13EligibilityRecordV2
    pointer: CurrentWo12PointerV2
    operation: Wo12OperationProvenanceV2


class IntradayWo12V2Application:
    """Evaluate only explicitly supplied pre-acquired K1–K4 evidence."""

    def __init__(self, *, wo10_store: Wo10Store, wo11_store: Wo11Store, store: Wo12V2Store) -> None:
        if type(wo10_store) is not Wo10Store or type(wo11_store) is not Wo11Store or type(store) is not Wo12V2Store:
            raise ValueError("WO12_V2_APPLICATION_CONFIGURATION_INVALID")
        self._wo10 = wo10_store
        self._wo11 = wo11_store
        self._store = store
        self._lock = Lock()

    @property
    def store(self) -> Wo12V2Store:
        return self._store

    def execute(self, request: Wo12RequestV2, inputs: Wo12EvidenceInputsV2) -> Wo12V2Execution:
        if type(request) is not Wo12RequestV2 or type(inputs) is not Wo12EvidenceInputsV2:
            raise Wo12V2ApplicationError("WO12_V2_REQUEST_INVALID")
        if not self._lock.acquire(blocking=False):
            raise Wo12V2ApplicationError("WO12_V2_OPERATION_BUSY")
        stage = Wo12OperationStage.REQUEST_VALIDATION
        provenance = (*request.provenance, "WO12_FOUR_K_APPLICATION_V2")
        try:
            publication, member = self._reload_and_validate(request)
            self._store.retain_handoff(request.handoff)
            self._store.retain_request(request)
            self._retain_started(request, stage, (*provenance, "EXACT_REQUEST_VALIDATED"))

            stage = Wo12OperationStage.WO11_WO10_RELOAD
            self._retain_started(request, stage, (*provenance, publication.publication_identity, member.member_identity))

            stage = Wo12OperationStage.EVIDENCE_ASSEMBLY
            criteria = assemble_wo12_criteria_v2(request.handoff, inputs)
            evidence = create_wo12_evidence_v2(
                request=request,
                criteria=criteria,
                exact_binding_valid=True,
                governing_15m_structure_failed=inputs.governing_15m_structure_failed,
                authoritative_directional_conflict=inputs.authoritative_directional_conflict,
            )
            self._retain_started(request, stage, (*provenance, evidence.evidence_identity, "EXACT_PREACQUIRED_K1_K4_EVIDENCE"))

            stage = Wo12OperationStage.CLASSIFICATION
            result = create_wo12_result_v2(
                request=request,
                evidence=evidence,
                created_at=request.requested_at,
                provenance=(*provenance, "INTRADAY_FOUR_CRITERION_ADAPTER"),
            )
            eligibility = create_wo13_eligibility_v2(
                result, provenance=(*provenance, "WO13_ELIGIBILITY_ONLY_NO_GEOMETRY")
            )
            self._retain_started(request, stage, (*provenance, result.result_identity, eligibility.eligibility_identity))

            stage = Wo12OperationStage.PERSISTENCE
            self._store.retain_evidence(evidence)
            self._store.retain_result(result)
            self._store.retain_eligibility(eligibility)
            if (
                self._store.load_request(request.request_identity) != request
                or self._store.load_evidence(evidence.evidence_identity) != evidence
                or self._store.load_result(result.result_identity) != result
                or self._store.load_eligibility(eligibility.eligibility_identity) != eligibility
            ):
                raise Wo12V2ApplicationError("WO12_V2_EXPLICIT_RELOAD_FAILED")

            stage = Wo12OperationStage.POINTER_PUBLICATION
            pointer = create_current_wo12_pointer_v2(request, result, eligibility)
            completed = create_wo12_operation_provenance_v2(
                request=request, stage=stage, outcome=Wo12OperationOutcome.COMPLETED,
                started_at=request.requested_at, completed_at=request.requested_at,
                result=result, provenance=(*provenance, "FINAL_WRITE_V2_POINTER_PUBLICATION"),
            )
            self._store.retain_operation(completed)
            self._store.publish_current(pointer)
            restored = self._store.restore_current()
            if restored is None or restored.pointer != pointer or restored.result != result or restored.eligibility != eligibility:
                raise Wo12V2ApplicationError("WO12_V2_EXPLICIT_RESTORE_FAILED")
            return Wo12V2Execution(request.request_identity, evidence, result, eligibility, pointer, completed)
        except Exception as error:
            reason = _failure_code(error)
            failed = create_wo12_operation_provenance_v2(
                request=request, stage=stage, outcome=Wo12OperationOutcome.FAILED,
                started_at=request.requested_at, failed_at=request.requested_at,
                failure_reason=reason, provenance=(*provenance, "CURRENT_V2_POINTER_NOT_PUBLISHED"),
            )
            self._store.retain_operation(failed)
            raise Wo12V2ApplicationError(reason) from error
        finally:
            self._lock.release()

    def restore_current(self) -> RestoredWo12V2State | None:
        return self._store.restore_current()

    def _retain_started(self, request: Wo12RequestV2, stage: Wo12OperationStage, provenance: tuple[str, ...]) -> None:
        self._store.retain_operation(create_wo12_operation_provenance_v2(
            request=request, stage=stage, outcome=Wo12OperationOutcome.STARTED,
            started_at=request.requested_at, provenance=provenance,
        ))

    def _reload_and_validate(self, request: Wo12RequestV2) -> tuple[Wo11PromotionPublication, Wo11Member]:
        handoff = request.handoff
        publication = self._wo11.load_publication(handoff.wo11_publication_identity)
        member = self._wo11.load_member(handoff.wo11_member_identity)
        reference = self._wo11.load_handoff(publication.publication_identity, member.member_identity)
        if create_wo12_handoff(publication=publication, member=member, wo11_handoff=reference) != handoff:
            raise Wo12V2ApplicationError("WO12_V2_WO11_HANDOFF_BINDING_INVALID")
        result = self._wo10.load_result(member.wo10_result_identity)
        source_request = self._wo10.load_request(member.source_wo10_request_identity)
        snapshot = self._wo10.load_evidence_snapshot(member.evidence_snapshot_identity)
        probable = next((item for item in source_request.probable_bindings if item.probable_result_identity == member.source_probable_result_identity), None)
        _validate_wo10_probables_lineage(member, result, source_request, snapshot, probable)
        return publication, member


@dataclass(frozen=True, slots=True)
class Wo12V2RuntimeStatus:
    state: str
    restored: RestoredWo12V2State | None
    failure_stage: str | None = None
    failure_reason: str | None = None


class IntradayWo12V2RuntimeService:
    """Restore V2 pointer inertly and execute only an explicit caller request."""

    def __init__(self, application: IntradayWo12V2Application) -> None:
        if type(application) is not IntradayWo12V2Application:
            raise ValueError("WO12_V2_RUNTIME_CONFIGURATION_INVALID")
        self._application = application
        self._lock = RLock()
        self._active_request_identity: str | None = None
        self._last_execution: Wo12V2Execution | None = None
        self._status = self._restore()

    @property
    def application(self) -> IntradayWo12V2Application:
        return self._application

    @property
    def store(self) -> Wo12V2Store:
        return self._application.store

    @property
    def status(self) -> Wo12V2RuntimeStatus:
        with self._lock:
            return self._status

    @property
    def active_request_identity(self) -> str | None:
        with self._lock:
            return self._active_request_identity

    @property
    def last_execution(self) -> Wo12V2Execution | None:
        with self._lock:
            return self._last_execution

    def execute(self, request: Wo12RequestV2, inputs: Wo12EvidenceInputsV2) -> Wo12V2Execution:
        with self._lock:
            self._active_request_identity = request.request_identity
        try:
            execution = self._application.execute(request, inputs)
            with self._lock:
                self._last_execution = execution
                self._status = self._restore()
            return execution
        finally:
            with self._lock:
                self._active_request_identity = None

    def _restore(self) -> Wo12V2RuntimeStatus:
        try:
            restored = self._application.restore_current()
        except (Wo12V2PersistenceError, Wo12ContractError, OSError, ValueError):
            return Wo12V2RuntimeStatus("CORRUPT", None, "RESTORATION", "WO12_V2_RESTORATION_FAILED")
        return Wo12V2RuntimeStatus("NOT_YET_RUN" if restored is None else "LOADED", restored)


def _validate_wo10_probables_lineage(
    member: Wo11Member,
    result: Wo10ReconciliationResult,
    request: Wo10ReconciliationRequest,
    snapshot: Wo10EvidenceSnapshot,
    probable: object,
) -> None:
    if (
        probable is None
        or result.result_identity != member.wo10_result_identity
        or result.result_integrity != member.wo10_result_integrity
        or result.request_identity != request.request_identity
        or result.canonical_subject_identity != member.canonical_subject_identity
        or result.market_family is not member.market_family
        or result.inherited_direction is not member.inherited_direction
        or result.policy != member.wo10_policy
        or result.analysis_boundary != member.analysis_boundary
        or result.persisted_phase is not member.persisted_phase
        or result.evidence_snapshot_identity != snapshot.snapshot_identity
        or request.probables_run_identity != member.source_probables_run_identity
        or getattr(probable, "probable_result_integrity", None) != member.source_probable_result_integrity
        or getattr(probable, "canonical_subject_identity", None) != member.canonical_subject_identity
        or getattr(probable, "inherited_direction", None) is not member.inherited_direction
        or snapshot.probables_run_identity != member.source_probables_run_identity
        or snapshot.probable_result_identity != member.source_probable_result_identity
    ):
        raise Wo12V2ApplicationError("WO12_V2_WO10_PROBABLES_LINEAGE_INVALID")


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if type(value) is str and value.startswith("WO12_") and len(value) <= 128:
        return value
    if isinstance(error, (Wo10PersistenceError, Wo11PersistenceError)):
        return "WO12_V2_SOURCE_ARTIFACT_UNAVAILABLE"
    if isinstance(error, Wo12V2PersistenceError):
        return "WO12_V2_PERSISTENCE_FAILURE"
    return "WO12_V2_APPLICATION_FAILURE"


__all__ = [
    "IntradayWo12V2Application",
    "IntradayWo12V2RuntimeService",
    "Wo12V2ApplicationError",
    "Wo12V2Execution",
    "Wo12V2RuntimeStatus",
]
