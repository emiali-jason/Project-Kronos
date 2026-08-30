"""Bounded application layer for Intraday WO-12 KR-370 core engineering."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from kronos.intraday.wo10 import (
    Wo10ReconciliationRequest,
    Wo10ReconciliationResult,
)
from kronos.intraday.wo10_evidence import Wo10EvidenceSnapshot
from kronos.intraday.wo10_persistence import Wo10PersistenceError, Wo10Store
from kronos.intraday.wo11 import Wo11Member, Wo11PromotionPublication
from kronos.intraday.wo11_persistence import Wo11PersistenceError, Wo11Store
from kronos.intraday.wo12 import (
    CurrentWo12Pointer,
    Wo12ContractError,
    Wo12Evidence,
    Wo12OperationOutcome,
    Wo12OperationProvenance,
    Wo12OperationStage,
    Wo12Request,
    Wo12Result,
    Wo13EligibilityRecord,
    create_current_wo12_pointer,
    create_wo12_evidence,
    create_wo12_handoff,
    create_wo12_operation_provenance,
    create_wo12_result,
    create_wo13_eligibility,
)
from kronos.intraday.wo12_facts import (
    Wo12EvidenceInputs,
    assemble_wo12_criteria,
)
from kronos.intraday.wo12_persistence import (
    RestoredWo12State,
    Wo12PersistenceError,
    Wo12Store,
)


class Wo12ApplicationError(Wo12ContractError):
    """Sanitized WO-12 orchestration or exact-binding failure."""


@dataclass(frozen=True, slots=True)
class Wo12Execution:
    request_identity: str
    evidence: Wo12Evidence
    result: Wo12Result
    eligibility: Wo13EligibilityRecord
    pointer: CurrentWo12Pointer
    operation: Wo12OperationProvenance


class IntradayWo12Application:
    """Evaluate only pre-acquired exact evidence; no Provider or Review action."""

    def __init__(
        self,
        *,
        wo10_store: Wo10Store,
        wo11_store: Wo11Store,
        store: Wo12Store,
    ) -> None:
        if (
            type(wo10_store) is not Wo10Store
            or type(wo11_store) is not Wo11Store
            or type(store) is not Wo12Store
        ):
            raise ValueError("WO12_APPLICATION_CONFIGURATION_INVALID")
        self._wo10 = wo10_store
        self._wo11 = wo11_store
        self._store = store
        self._lock = Lock()

    @property
    def store(self) -> Wo12Store:
        return self._store

    def execute(
        self,
        request: Wo12Request,
        inputs: Wo12EvidenceInputs,
    ) -> Wo12Execution:
        if type(request) is not Wo12Request or type(inputs) is not Wo12EvidenceInputs:
            raise Wo12ApplicationError("WO12_REQUEST_INVALID")
        if not self._lock.acquire(blocking=False):
            raise Wo12ApplicationError("WO12_OPERATION_BUSY")
        started_at = request.requested_at
        stage = Wo12OperationStage.REQUEST_VALIDATION
        provenance = (*request.provenance, "WO12_CORE_APPLICATION_V1")
        try:
            publication, member = self._reload_and_validate(request)
            self._store.retain_handoff(request.handoff)
            self._store.retain_request(request)
            self._retain_started(request, stage, (*provenance, "EXACT_REQUEST_VALIDATED"))

            stage = Wo12OperationStage.WO11_WO10_RELOAD
            self._retain_started(
                request,
                stage,
                (*provenance, publication.publication_identity, member.member_identity),
            )

            stage = Wo12OperationStage.EVIDENCE_ASSEMBLY
            criteria = assemble_wo12_criteria(request.handoff, inputs)
            evidence = create_wo12_evidence(
                request=request,
                criteria=criteria,
                exact_binding_valid=True,
                governing_15m_structure_failed=inputs.governing_15m_structure_failed,
                authoritative_directional_conflict=inputs.authoritative_directional_conflict,
                extension_measurement_identity=(
                    None
                    if inputs.extension_measurement is None
                    else inputs.extension_measurement.measurement_identity
                ),
                extension_measurement_integrity=(
                    None
                    if inputs.extension_measurement is None
                    else inputs.extension_measurement.measurement_integrity
                ),
            )
            self._retain_started(
                request,
                stage,
                (*provenance, evidence.evidence_identity, "EXACT_PREACQUIRED_EVIDENCE"),
            )

            stage = Wo12OperationStage.CLASSIFICATION
            result = create_wo12_result(
                request=request,
                evidence=evidence,
                created_at=request.requested_at,
                provenance=(*provenance, "COMMON_KR370_FIVE_CRITERION_CLASSIFIER"),
            )
            eligibility = create_wo13_eligibility(
                result,
                provenance=(*provenance, "WO13_ELIGIBILITY_ONLY_NO_GEOMETRY"),
            )
            self._retain_started(
                request,
                stage,
                (*provenance, result.result_identity, eligibility.eligibility_identity),
            )

            stage = Wo12OperationStage.PERSISTENCE
            if inputs.extension_measurement is not None:
                self._store.retain_extension_measurement(inputs.extension_measurement)
            self._store.retain_evidence(evidence)
            self._store.retain_result(result)
            self._store.retain_eligibility(eligibility)
            self._validate_explicit_reload(
                request,
                evidence,
                result,
                eligibility,
                inputs,
            )
            self._retain_started(
                request,
                stage,
                (*provenance, "IMMUTABLE_ARTIFACTS_RELOADED_EXPLICITLY"),
            )

            stage = Wo12OperationStage.POINTER_PUBLICATION
            pointer = create_current_wo12_pointer(request, result, eligibility)
            completed = create_wo12_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo12OperationOutcome.COMPLETED,
                started_at=started_at,
                completed_at=started_at,
                result=result,
                provenance=(*provenance, "FINAL_WRITE_POINTER_PUBLICATION"),
            )
            self._store.retain_operation(completed)
            self._store.publish_current(pointer)
            restored = self._store.restore_current()
            if (
                restored is None
                or restored.pointer != pointer
                or restored.result != result
                or restored.eligibility != eligibility
            ):
                raise Wo12ApplicationError("WO12_EXPLICIT_RESTORE_FAILED")
            return Wo12Execution(
                request.request_identity,
                evidence,
                result,
                eligibility,
                pointer,
                completed,
            )
        except Exception as error:
            reason = _failure_code(error)
            failed = create_wo12_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo12OperationOutcome.FAILED,
                started_at=started_at,
                failed_at=started_at,
                failure_reason=reason,
                provenance=(*provenance, "CURRENT_POINTER_NOT_PUBLISHED"),
            )
            self._store.retain_operation(failed)
            raise Wo12ApplicationError(reason) from error
        finally:
            self._lock.release()

    def restore_current(self) -> RestoredWo12State | None:
        return self._store.restore_current()

    def _retain_started(
        self,
        request: Wo12Request,
        stage: Wo12OperationStage,
        provenance: tuple[str, ...],
    ) -> None:
        self._store.retain_operation(create_wo12_operation_provenance(
            request=request,
            stage=stage,
            outcome=Wo12OperationOutcome.STARTED,
            started_at=request.requested_at,
            provenance=provenance,
        ))

    def _reload_and_validate(
        self,
        request: Wo12Request,
    ) -> tuple[Wo11PromotionPublication, Wo11Member]:
        handoff = request.handoff
        publication = self._wo11.load_publication(handoff.wo11_publication_identity)
        member = self._wo11.load_member(handoff.wo11_member_identity)
        wo11_handoff = self._wo11.load_handoff(
            publication.publication_identity,
            member.member_identity,
        )
        rebuilt = create_wo12_handoff(
            publication=publication,
            member=member,
            wo11_handoff=wo11_handoff,
        )
        if rebuilt != handoff:
            raise Wo12ApplicationError("WO12_WO11_HANDOFF_BINDING_INVALID")

        wo10_result = self._wo10.load_result(member.wo10_result_identity)
        wo10_request = self._wo10.load_request(member.source_wo10_request_identity)
        snapshot = self._wo10.load_evidence_snapshot(member.evidence_snapshot_identity)
        probable = next((
            item for item in wo10_request.probable_bindings
            if item.probable_result_identity == member.source_probable_result_identity
        ), None)
        self._validate_wo10_probables_lineage(
            member,
            wo10_result,
            wo10_request,
            snapshot,
            probable,
        )
        return publication, member

    @staticmethod
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
            or result.request_integrity != request.request_integrity
            or result.canonical_subject_identity != member.canonical_subject_identity
            or result.market_family is not member.market_family
            or result.inherited_direction is not member.inherited_direction
            or result.policy != member.wo10_policy
            or result.analysis_boundary != member.analysis_boundary
            or result.persisted_phase is not member.persisted_phase
            or result.evidence_snapshot_identity != snapshot.snapshot_identity
            or result.evidence_snapshot_integrity != snapshot.snapshot_integrity
            or request.probables_run_identity != member.source_probables_run_identity
            or request.probables_run_integrity != member.source_probables_run_integrity
            or getattr(probable, "probable_result_integrity", None)
            != member.source_probable_result_integrity
            or getattr(probable, "canonical_subject_identity", None)
            != member.canonical_subject_identity
            or getattr(probable, "inherited_direction", None)
            is not member.inherited_direction
            or getattr(probable, "analysis_boundary", None) != member.analysis_boundary
            or getattr(probable, "persisted_phase", None) is not member.persisted_phase
            or snapshot.probables_run_identity != member.source_probables_run_identity
            or snapshot.probables_run_integrity != member.source_probables_run_integrity
            or snapshot.probable_result_identity != member.source_probable_result_identity
            or snapshot.probable_result_integrity != member.source_probable_result_integrity
        ):
            raise Wo12ApplicationError("WO12_WO10_PROBABLES_LINEAGE_INVALID")

    def _validate_explicit_reload(
        self,
        request: Wo12Request,
        evidence: Wo12Evidence,
        result: Wo12Result,
        eligibility: Wo13EligibilityRecord,
        inputs: Wo12EvidenceInputs,
    ) -> None:
        if (
            self._store.load_handoff(request.handoff.handoff_identity) != request.handoff
            or self._store.load_request(request.request_identity) != request
            or self._store.load_evidence(evidence.evidence_identity) != evidence
            or self._store.load_result(result.result_identity) != result
            or self._store.load_eligibility(eligibility.eligibility_identity)
            != eligibility
            or (
                inputs.extension_measurement is not None
                and self._store.load_extension_measurement(
                    inputs.extension_measurement.measurement_identity
                ) != inputs.extension_measurement
            )
        ):
            raise Wo12ApplicationError("WO12_EXPLICIT_RELOAD_FAILED")


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if type(value) is str and value.startswith("WO12_") and len(value) <= 128:
        return value
    if isinstance(error, (Wo10PersistenceError, Wo11PersistenceError)):
        return "WO12_SOURCE_ARTIFACT_UNAVAILABLE"
    if isinstance(error, Wo12PersistenceError):
        return "WO12_PERSISTENCE_FAILURE"
    return "WO12_APPLICATION_FAILURE"


__all__ = [
    "IntradayWo12Application",
    "Wo12ApplicationError",
    "Wo12Execution",
]
