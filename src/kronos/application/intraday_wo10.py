"""Explicit Sponsor-invoked application boundary for Intraday WO-10 V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Protocol, runtime_checkable

from kronos.intraday.mcx_commissioning import (
    McxCommissioningState,
    load_mcx_commissioning_publication,
)
from kronos.intraday.probables_v2 import ProbableMemberResultV2, ProbablesRunV2
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review_v2 import (
    ChartRevisionV2,
    ImportedVisualEvidenceV2,
    ReviewCycleV2,
    ReviewQuestionPackV2,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import (
    CurrentWo10ReconciliationPointer,
    Wo10BatchResult,
    Wo10ContractError,
    Wo10OperationOutcome,
    Wo10OperationProvenance,
    Wo10OperationStage,
    Wo10ReconciliationRequest,
    Wo10ReconciliationResult,
    create_current_wo10_pointer,
    create_wo10_batch_result,
    create_wo10_operation_provenance,
    create_wo10_reconciliation_result,
)
from kronos.intraday.wo10_evidence import (
    Wo10CommonFactBindings,
    Wo10EvidenceReference,
    Wo10EvidenceSnapshot,
    Wo10FamilyEvidenceExtension,
    create_wo10_evidence_snapshot,
)
from kronos.intraday.wo10_persistence import Wo10Store
from kronos.intraday.wo10_policies import Wo10PolicyRegistry


class Wo10ApplicationError(Wo10ContractError):
    """Sanitized orchestration, binding, or concurrency failure."""


@runtime_checkable
class Wo10EvidenceAssembler(Protocol):
    """Load retained artifacts and assemble one exact typed evidence snapshot."""

    def assemble(
        self,
        *,
        run: ProbablesRunV2,
        result: ProbableMemberResultV2,
        request: Wo10ReconciliationRequest,
    ) -> Wo10EvidenceSnapshot:
        """Return exact retained evidence; Provider acquisition is outside this seam."""


@dataclass(frozen=True, slots=True)
class Wo10EvidenceInputs:
    """Exact retained inputs from which the application constructs a snapshot."""

    cycle: ReviewCycleV2
    chart: ChartRevisionV2
    review_pack: ReviewQuestionPackV2
    imported_visual_evidence: ImportedVisualEvidenceV2
    common_facts: Wo10CommonFactBindings
    family_extension: Wo10FamilyEvidenceExtension
    source_references: tuple[Wo10EvidenceReference, ...]
    provenance: tuple[str, ...]


@runtime_checkable
class Wo10EvidenceInputLoader(Protocol):
    """Read exact retained Review/fact artifacts; it must not call a Provider."""

    def load(
        self,
        *,
        run: ProbablesRunV2,
        result: ProbableMemberResultV2,
        request: Wo10ReconciliationRequest,
    ) -> Wo10EvidenceInputs:
        """Return one candidate's exact retained evidence inputs."""


class Wo10TypedEvidenceAssembler:
    """Application-owned typed assembly over an explicit retained-input loader."""

    def __init__(self, loader: Wo10EvidenceInputLoader) -> None:
        if not isinstance(loader, Wo10EvidenceInputLoader):
            raise ValueError("WO10_EVIDENCE_LOADER_INVALID")
        self._loader = loader

    def assemble(
        self,
        *,
        run: ProbablesRunV2,
        result: ProbableMemberResultV2,
        request: Wo10ReconciliationRequest,
    ) -> Wo10EvidenceSnapshot:
        loaded = self._loader.load(run=run, result=result, request=request)
        if type(loaded) is not Wo10EvidenceInputs:
            raise Wo10ApplicationError("WO10_EVIDENCE_INPUTS_INVALID")
        return create_wo10_evidence_snapshot(
            run=run,
            result=result,
            cycle=loaded.cycle,
            chart=loaded.chart,
            review_pack=loaded.review_pack,
            imported_visual_evidence=loaded.imported_visual_evidence,
            market_family=request.market_family,
            policy=request.policy,
            common_facts=loaded.common_facts,
            family_extension=loaded.family_extension,
            source_references=loaded.source_references,
            provenance=loaded.provenance,
        )


@dataclass(frozen=True, slots=True)
class Wo10CandidateExecution:
    canonical_subject_identity: str
    probable_result_identity: str
    evidence_snapshot_identity: str | None
    reconciliation_result_identity: str | None
    state: str | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class Wo10Execution:
    request_identity: str
    candidates: tuple[Wo10CandidateExecution, ...]
    batch: Wo10BatchResult | None
    pointer: CurrentWo10ReconciliationPointer | None
    operation: Wo10OperationProvenance

    @property
    def completed(self) -> bool:
        return self.operation.outcome is Wo10OperationOutcome.COMPLETED


class IntradayWo10Application:
    """Persist-before-evaluate, exact-dispatch WO-10 orchestration.

    This boundary is inert until ``execute`` is called.  It has no Provider,
    Browser, polling, startup, timer, or background dependency.
    """

    def __init__(
        self,
        *,
        run_store: ProbablesV2Store,
        store: Wo10Store,
        policy_registry: Wo10PolicyRegistry,
        evidence_assembler: Wo10EvidenceAssembler,
        backend_identity: str | None = None,
        process_identity: str | None = None,
    ) -> None:
        if (
            type(run_store) is not ProbablesV2Store
            or type(store) is not Wo10Store
            or not isinstance(policy_registry, Wo10PolicyRegistry)
            or not isinstance(evidence_assembler, Wo10EvidenceAssembler)
            or (backend_identity is not None and not _text(backend_identity))
            or (process_identity is not None and not _text(process_identity))
        ):
            raise ValueError("WO10_APPLICATION_CONFIGURATION_INVALID")
        self._run_store = run_store
        self._store = store
        self._registry = policy_registry
        self._assembler = evidence_assembler
        self._backend_identity = backend_identity
        self._process_identity = process_identity
        self._lock = Lock()

    def execute(self, request: Wo10ReconciliationRequest) -> Wo10Execution:
        """Execute one explicit request; fail closed if concurrent or incomplete."""

        if type(request) is not Wo10ReconciliationRequest:
            raise Wo10ApplicationError("WO10_REQUEST_INVALID")
        if not self._lock.acquire(blocking=False):
            raise Wo10ApplicationError("WO10_OPERATION_BUSY")
        started_at = request.requested_at
        provenance = (*request.provenance, "WO10_APPLICATION_V2")
        stage = Wo10OperationStage.REQUEST
        retained_results: list[Wo10ReconciliationResult] = []
        candidates: list[Wo10CandidateExecution] = []
        try:
            started = create_wo10_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo10OperationOutcome.STARTED,
                started_at=started_at,
                backend_identity=self._backend_identity,
                process_identity=self._process_identity,
                provenance=(*provenance, "REQUEST_VALIDATED"),
            )
            self._store.retain_policy(request.policy)
            self._store.retain_request(request)
            self._store.retain_operation(started)
            self._retain_started(
                request, stage, started_at, (*provenance, "REQUEST_PERSISTED")
            )
            self._registry.resolve(request.policy)

            self._retain_started(
                request, stage, started_at, (*provenance, "EXACT_RUN_RELOAD")
            )
            run = self._load_exact_run(request)
            for binding in request.probable_bindings:
                stage = Wo10OperationStage.EVIDENCE
                snapshot: Wo10EvidenceSnapshot | None = None
                try:
                    self._retain_started(
                        request,
                        stage,
                        started_at,
                        (*provenance, f"CANDIDATE_BINDING_{binding.canonical_subject_identity}"),
                    )
                    probable = self._load_exact_candidate(run, request, binding.probable_result_identity)
                    if (
                        request.market_family is IntradayMarketFamily.MCX
                        and load_mcx_commissioning_publication()
                        .subject(binding.canonical_subject_identity).state
                        is not McxCommissioningState.COMMISSIONED
                    ):
                        raise Wo10ApplicationError("WO10_MCX_COMMISSIONING_HELD")
                    snapshot = self._assembler.assemble(
                        run=run,
                        result=probable,
                        request=request,
                    )
                    self._validate_snapshot(request, binding.probable_result_identity, snapshot)
                    self._store.retain_evidence_snapshot(snapshot)

                    stage = Wo10OperationStage.POLICY
                    self._retain_started(
                        request,
                        stage,
                        started_at,
                        (*provenance, f"POLICY_DISPATCH_{binding.canonical_subject_identity}"),
                    )
                    decision = self._registry.evaluate(request=request, evidence=snapshot)
                    stage = Wo10OperationStage.RESULT
                    self._retain_started(
                        request,
                        stage,
                        started_at,
                        (*provenance, f"RESULT_PERSISTENCE_{binding.canonical_subject_identity}"),
                    )
                    result = create_wo10_reconciliation_result(
                        request=request,
                        evidence=snapshot,
                        state=decision.state,
                        reasons=decision.reasons,
                        provenance=(*provenance, "EXACT_POLICY_DISPATCH"),
                    )
                    self._store.retain_result(result)
                    retained_results.append(result)
                    candidates.append(Wo10CandidateExecution(
                        canonical_subject_identity=binding.canonical_subject_identity,
                        probable_result_identity=binding.probable_result_identity,
                        evidence_snapshot_identity=snapshot.snapshot_identity,
                        reconciliation_result_identity=result.result_identity,
                        state=result.state.value,
                        failure_reason=None,
                    ))
                except Exception as error:  # candidate isolation is deliberate
                    failure = _failure_code(error)
                    failed = create_wo10_operation_provenance(
                        request=request,
                        stage=stage,
                        outcome=Wo10OperationOutcome.FAILED,
                        started_at=started_at,
                        failed_at=started_at,
                        backend_identity=self._backend_identity,
                        process_identity=self._process_identity,
                        failure_reason=failure,
                        provenance=(
                            *provenance,
                            f"CANDIDATE_{binding.canonical_subject_identity}",
                        ),
                    )
                    self._store.retain_operation(failed)
                    candidates.append(Wo10CandidateExecution(
                        canonical_subject_identity=binding.canonical_subject_identity,
                        probable_result_identity=binding.probable_result_identity,
                        evidence_snapshot_identity=(
                            None if snapshot is None else snapshot.snapshot_identity
                        ),
                        reconciliation_result_identity=None,
                        state=None,
                        failure_reason=failure,
                    ))

            if any(item.failure_reason is not None for item in candidates):
                failed = create_wo10_operation_provenance(
                    request=request,
                    stage=stage,
                    outcome=Wo10OperationOutcome.FAILED,
                    started_at=started_at,
                    failed_at=started_at,
                    backend_identity=self._backend_identity,
                    process_identity=self._process_identity,
                    failure_reason="WO10_BATCH_INCOMPLETE",
                    provenance=(*provenance, "CURRENT_POINTER_NOT_PUBLISHED"),
                )
                self._store.retain_operation(failed)
                return Wo10Execution(
                    request.request_identity, tuple(candidates), None, None, failed
                )

            stage = Wo10OperationStage.BATCH_PUBLICATION
            self._retain_started(
                request, stage, started_at, (*provenance, "BATCH_PERSISTENCE")
            )
            batch = create_wo10_batch_result(
                request=request,
                results=retained_results,
                completed_at=started_at,
                provenance=(*provenance, "COMPLETE_REQUEST_POPULATION"),
            )
            self._store.retain_batch(batch)
            self._retain_started(
                request, stage, started_at, (*provenance, "CURRENT_POINTER_PUBLICATION")
            )
            pointer = create_current_wo10_pointer(request, batch)
            completed = create_wo10_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo10OperationOutcome.COMPLETED,
                started_at=started_at,
                completed_at=started_at,
                backend_identity=self._backend_identity,
                process_identity=self._process_identity,
                results=retained_results,
                batch=batch,
                provenance=(*provenance, "BATCH_PERSISTED_POINTER_READY"),
            )
            self._store.retain_operation(completed)
            # The replaceable pointer is deliberately the final write.  Any
            # earlier failure therefore cannot publish false current state.
            self._store.publish_current(pointer)
            return Wo10Execution(
                request.request_identity, tuple(candidates), batch, pointer, completed
            )
        except Exception as error:
            failure = _failure_code(error)
            failed = create_wo10_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo10OperationOutcome.FAILED,
                started_at=started_at,
                failed_at=started_at,
                backend_identity=self._backend_identity,
                process_identity=self._process_identity,
                failure_reason=failure,
                provenance=(*provenance, "CURRENT_POINTER_NOT_PUBLISHED"),
            )
            self._store.retain_operation(failed)
            raise Wo10ApplicationError(failure) from error
        finally:
            self._lock.release()

    def restore_current(self, market_family):  # type: ignore[no-untyped-def]
        """Delegate exact Provider-independent restoration without reevaluation."""

        return self._store.restore_current(market_family)

    def _retain_started(
        self,
        request: Wo10ReconciliationRequest,
        stage: Wo10OperationStage,
        started_at: datetime,
        provenance: tuple[str, ...],
    ) -> None:
        self._store.retain_operation(create_wo10_operation_provenance(
            request=request,
            stage=stage,
            outcome=Wo10OperationOutcome.STARTED,
            started_at=started_at,
            backend_identity=self._backend_identity,
            process_identity=self._process_identity,
            provenance=provenance,
        ))

    def _load_exact_run(self, request: Wo10ReconciliationRequest) -> ProbablesRunV2:
        run = self._run_store.load_run(request.probables_run_identity)
        if (
            type(run) is not ProbablesRunV2
            or run.run_identity != request.probables_run_identity
            or run.integrity_identity != request.probables_run_integrity
        ):
            raise Wo10ApplicationError("WO10_PROBABLES_RUN_BINDING_INVALID")
        return run

    def _load_exact_candidate(
        self,
        run: ProbablesRunV2,
        request: Wo10ReconciliationRequest,
        result_identity: str,
    ) -> ProbableMemberResultV2:
        binding = next(
            item for item in request.probable_bindings
            if item.probable_result_identity == result_identity
        )
        result = self._run_store.load_result(result_identity)
        if (
            type(result) is not ProbableMemberResultV2
            or result not in run.results
            or result.integrity_identity != binding.probable_result_integrity
            or result.canonical_subject_identity != binding.canonical_subject_identity
            or result.direction is not binding.inherited_direction
            or result.analysis_boundary != binding.analysis_boundary
            or result.phase is not binding.persisted_phase
        ):
            raise Wo10ApplicationError("WO10_PROBABLE_RESULT_BINDING_INVALID")
        return result

    @staticmethod
    def _validate_snapshot(
        request: Wo10ReconciliationRequest,
        result_identity: str,
        snapshot: Wo10EvidenceSnapshot,
    ) -> None:
        binding = next(
            item for item in request.probable_bindings
            if item.probable_result_identity == result_identity
        )
        if (
            type(snapshot) is not Wo10EvidenceSnapshot
            or snapshot.probables_run_identity != request.probables_run_identity
            or snapshot.probables_run_integrity != request.probables_run_integrity
            or snapshot.probable_result_identity != binding.probable_result_identity
            or snapshot.probable_result_integrity != binding.probable_result_integrity
            or snapshot.canonical_subject_identity != binding.canonical_subject_identity
            or snapshot.inherited_direction is not binding.inherited_direction
            or snapshot.analysis_boundary != binding.analysis_boundary
            or snapshot.persisted_phase is not binding.persisted_phase
            or snapshot.market_family is not request.market_family
            or snapshot.policy != request.policy
        ):
            raise Wo10ApplicationError("WO10_EVIDENCE_BINDING_INVALID")


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if (
        type(value) is str
        and 3 <= len(value) <= 128
        and value[0].isalpha()
        and value[0].isupper()
        and all(character.isupper() or character.isdigit() or character == "_" for character in value)
    ):
        return value
    return "WO10_APPLICATION_FAILURE"


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


__all__ = [
    "IntradayWo10Application",
    "Wo10ApplicationError",
    "Wo10CandidateExecution",
    "Wo10EvidenceAssembler",
    "Wo10EvidenceInputLoader",
    "Wo10EvidenceInputs",
    "Wo10Execution",
    "Wo10TypedEvidenceAssembler",
]
