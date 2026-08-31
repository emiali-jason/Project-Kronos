"""Explicit zero-discretion persistence/application boundary for WO-13."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from kronos.intraday.wo13 import (
    CurrentWo13Pointer, Wo13ConstructionRequest, Wo13ContractError,
    Wo13FieldAvailability, Wo13GeometryField, Wo13OperationOutcome,
    Wo13OperationProvenance, Wo13OperationStage, Wo13SupersessionLineage,
    Wo13SupersessionReason, Wo13TradePlan, create_current_wo13_pointer,
    create_wo13_field_availability, create_wo13_operation_provenance,
    create_wo13_supersession_lineage, create_wo13_supersession_reference,
    create_wo13_trade_plan_contract,
)
from kronos.intraday.wo13_adapters import finalize_wo13_family_geometry
from kronos.intraday.wo13_breakout import (
    Wo13BreakoutGeometryEvidence, construct_wo13_breakout_geometry,
)
from kronos.intraday.wo13_handoff import Wo13SetupFamily, Wo13Step31Handoff
from kronos.intraday.wo13_persistence import (
    RestoredWo13State, Wo13PersistenceError, Wo13Store,
)
from kronos.intraday.wo13_pullback import (
    Wo13PullbackGeometryEvidence, construct_wo13_pullback_geometry,
)
from kronos.intraday.wo13_targets import Wo13TargetConstraintPopulation


class Wo13ApplicationError(Wo13ContractError):
    """Sanitized construction orchestration or concurrency failure."""


@dataclass(frozen=True, slots=True)
class Wo13Execution:
    request_identity: str
    trade_plan: Wo13TradePlan
    pointer: CurrentWo13Pointer
    operation: Wo13OperationProvenance
    supersession: Wo13SupersessionLineage | None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class Wo13RestorationStatus:
    state: str
    restored: RestoredWo13State | None
    failure_stage: str | None = None
    failure_reason: str | None = None


class IntradayWo13Application:
    """Construct one exact request using only published WO-13 engines."""

    def __init__(self, *, store: Wo13Store) -> None:
        if type(store) is not Wo13Store:
            raise ValueError("WO13_APPLICATION_CONFIGURATION_INVALID")
        self._store = store
        self._lock = Lock()

    @property
    def store(self) -> Wo13Store:
        return self._store

    def execute(
        self,
        request: Wo13ConstructionRequest,
        evidence: Wo13PullbackGeometryEvidence | Wo13BreakoutGeometryEvidence,
        target_population: Wo13TargetConstraintPopulation,
    ) -> Wo13Execution:
        if type(request) is not Wo13ConstructionRequest:
            raise Wo13ApplicationError("WO13_REQUEST_INVALID")
        if not self._lock.acquire(blocking=False):
            raise Wo13ApplicationError("WO13_OPERATION_BUSY")
        started_at = request.requested_at
        stage = Wo13OperationStage.REQUEST_VALIDATION
        provenance = (*request.provenance, "WO13_ZERO_DISCRETION_APPLICATION_V1")
        try:
            current = self._store.load_current()
            if current is not None and current.request_identity == request.request_identity:
                restored = self._store.restore_current()
                if (
                    restored is None
                    or restored.request != request
                    or getattr(evidence, "handoff", None) != request.handoff
                    or target_population.population_identity
                    not in restored.trade_plan.provenance
                    or target_population.setup_geometry_identity
                    not in restored.trade_plan.provenance
                    or (
                        getattr(evidence, "evidence_identity", None),
                        getattr(evidence, "evidence_integrity", None),
                    ) not in set(zip(
                        restored.trade_plan.source_evidence_identities,
                        restored.trade_plan.source_evidence_integrities,
                        strict=True,
                    ))
                ):
                    raise Wo13ApplicationError("WO13_IDEMPOTENT_REPLAY_INVALID")
                return Wo13Execution(
                    request.request_identity, restored.trade_plan, restored.pointer,
                    restored.operation, restored.supersession, True,
                )

            self._store.retain_handoff(request.handoff)
            self._store.retain_request(request)
            self._started(request, stage, started_at, (*provenance, "REQUEST_PERSISTED"))

            stage = Wo13OperationStage.HANDOFF_VALIDATION
            handoff = self._store.load_handoff(request.handoff.handoff_identity)
            loaded_request = self._store.load_request(request.request_identity)
            if loaded_request != request or loaded_request.handoff != handoff:
                raise Wo13ApplicationError("WO13_HANDOFF_BINDING_INVALID")
            self._started(request, stage, started_at, (*provenance, "HANDOFF_EXACT_RELOAD"))

            stage = Wo13OperationStage.SOURCE_RELOAD
            if getattr(evidence, "handoff", None) != handoff:
                raise Wo13ApplicationError("WO13_SOURCE_HANDOFF_MISMATCH")
            self._started(request, stage, started_at, (*provenance, "SOURCE_BINDINGS_VALIDATED"))

            stage = Wo13OperationStage.GEOMETRY_ASSEMBLY
            geometry = _construct(handoff, evidence)
            self._started(request, stage, started_at, (*provenance, geometry.geometry_identity))

            stage = Wo13OperationStage.CONSTRUCTION
            adapted = finalize_wo13_family_geometry(
                setup_geometry=geometry, candidate_population=target_population
            )
            self._started(request, stage, started_at, (*provenance, adapted.adapter_identity))

            stage = Wo13OperationStage.CALCULATION
            supersession_reference, predecessor = self._supersession_reference(request)
            plan = _plan(request, geometry, adapted.selection, supersession_reference, provenance)

            stage = Wo13OperationStage.PERSISTENCE
            self._started(request, stage, started_at, (*provenance, "PLAN_PERSISTENCE"))
            self._store.retain_trade_plan(plan)
            if self._store.load_trade_plan(plan.trade_plan_identity) != plan:
                raise Wo13ApplicationError("WO13_TRADE_PLAN_RELOAD_INVALID")

            lineage = None
            if predecessor is not None and supersession_reference is not None:
                lineage = create_wo13_supersession_lineage(
                    predecessor_trade_plan_identity=predecessor.trade_plan_identity,
                    predecessor_trade_plan_integrity=predecessor.trade_plan_integrity,
                    successor_trade_plan_identity=plan.trade_plan_identity,
                    successor_trade_plan_integrity=plan.trade_plan_integrity,
                    source_wo12_request_identity=handoff.wo12_request_identity,
                    source_wo12_result_identity=handoff.wo12_result_identity,
                    reason=supersession_reference.reason,
                    supersession_boundary=handoff.analysis_boundary,
                )
                self._store.retain_supersession(lineage)

            stage = Wo13OperationStage.POINTER_PUBLICATION
            completed = create_wo13_operation_provenance(
                request=request, stage=stage, outcome=Wo13OperationOutcome.COMPLETED,
                started_at=started_at, completed_at=started_at, trade_plan=plan,
                provenance=(*provenance, "PLAN_RELOADED_POINTER_READY"),
            )
            self._store.retain_operation(completed)
            pointer = create_current_wo13_pointer(
                request=request, trade_plan=plan, operation=completed,
                published_at=started_at, supersession_lineage=lineage,
            )
            self._store.publish_current(pointer)
            restored = self._store.restore_current()
            if restored is None or restored.pointer != pointer or restored.trade_plan != plan:
                raise Wo13ApplicationError("WO13_POST_PUBLICATION_RELOAD_INVALID")
            return Wo13Execution(request.request_identity, plan, pointer, completed, lineage)
        except Exception as error:
            reason = _failure_code(error)
            failed = create_wo13_operation_provenance(
                request=request, stage=stage, outcome=Wo13OperationOutcome.FAILED,
                started_at=started_at, failed_at=started_at, failure_reason=reason,
                provenance=(*provenance, "CURRENT_POINTER_NOT_PUBLISHED"),
            )
            self._store.retain_operation(failed)
            raise Wo13ApplicationError(reason) from error
        finally:
            self._lock.release()

    def restore_current(self) -> RestoredWo13State | None:
        return self._store.restore_current()

    def _started(self, request, stage, started_at, provenance):  # type: ignore[no-untyped-def]
        self._store.retain_operation(create_wo13_operation_provenance(
            request=request, stage=stage, outcome=Wo13OperationOutcome.STARTED,
            started_at=started_at, provenance=provenance,
        ))

    def _supersession_reference(self, request):  # type: ignore[no-untyped-def]
        identity = request.handoff.predecessor_trade_plan_identity
        if identity is None:
            return None, None
        predecessor = self._store.load_trade_plan(identity)
        reason = (
            Wo13SupersessionReason.GOVERNED_ACTIVE_CONTRACT_ROLLED
            if predecessor.actual_contract_identity != request.handoff.actual_contract_identity
            else Wo13SupersessionReason.NEW_EXACT_ELIGIBLE_WO12_CYCLE
        )
        return create_wo13_supersession_reference(
            predecessor_trade_plan_identity=predecessor.trade_plan_identity,
            predecessor_trade_plan_integrity=predecessor.trade_plan_integrity,
            source_wo12_request_identity=request.handoff.wo12_request_identity,
            source_wo12_result_identity=request.handoff.wo12_result_identity,
            reason=reason, supersession_boundary=request.handoff.analysis_boundary,
        ), predecessor


class IntradayWo13RestorationService:
    """Provider-independent current-state reconstruction without reevaluation."""

    def __init__(self, *, store: Wo13Store) -> None:
        if type(store) is not Wo13Store:
            raise ValueError("WO13_RESTORATION_CONFIGURATION_INVALID")
        self._store = store

    def restore(self) -> Wo13RestorationStatus:
        try:
            restored = self._store.restore_current()
        except (Wo13PersistenceError, Wo13ContractError, OSError, ValueError):
            return Wo13RestorationStatus("CORRUPT", None, "RESTORATION", "WO13_RESTORATION_FAILED")
        return Wo13RestorationStatus("NOT_YET_RUN" if restored is None else "LOADED", restored)


def _construct(handoff, evidence):  # type: ignore[no-untyped-def]
    if handoff.setup_family is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION and type(evidence) is Wo13PullbackGeometryEvidence:
        return construct_wo13_pullback_geometry(evidence)
    if handoff.setup_family is Wo13SetupFamily.INTRADAY_RANGE_BREAKOUT and type(evidence) is Wo13BreakoutGeometryEvidence:
        return construct_wo13_breakout_geometry(evidence)
    raise Wo13ApplicationError("WO13_SETUP_FAMILY_EVIDENCE_MISMATCH")


def _plan(request, geometry, selection, supersession, provenance):  # type: ignore[no-untyped-def]
    entry = selection.entry_reference.selected_fact
    stop = geometry.stop.selected_fact
    invalidation = geometry.thesis_invalidation_reference.selected_fact
    native = selection.setup_native_target.selected_fact
    canonical = selection.canonical_target.selected_fact
    condition = geometry.entry_condition
    event = geometry.thesis_invalidation_event
    constrained = selection.constraining_candidates
    additional_sources = _source_pairs(
        (geometry.evidence.evidence_identity,),
        (geometry.evidence.evidence_integrity,),
        geometry.evidence.source_identities,
        geometry.evidence.source_integrities,
        selection.candidate_population.source_identities,
        selection.candidate_population.source_integrities,
    )
    values = {
        Wo13GeometryField.ENTRY_REFERENCE: None if entry is None else entry.price,
        Wo13GeometryField.ENTRY_CONDITION: None if condition is None else condition.condition_code.value,
        Wo13GeometryField.STOP: None if stop is None else stop.price,
        Wo13GeometryField.STOP_STRUCTURAL_BASIS: None if stop is None else stop.structural_role.value,
        Wo13GeometryField.THESIS_INVALIDATION_REFERENCE: None if invalidation is None else invalidation.price,
        Wo13GeometryField.THESIS_INVALIDATION_EVENT: None if event is None else event.event_code,
        Wo13GeometryField.SETUP_NATIVE_TARGET: None if native is None else native.price,
        Wo13GeometryField.CANONICAL_TARGET: None if canonical is None else canonical.price,
        Wo13GeometryField.TARGET_STRUCTURAL_BASIS: None if canonical is None else canonical.structural_role.value,
        Wo13GeometryField.CONSTRAINING_OBJECTIVE: None if not constrained or canonical is None else canonical.price,
        Wo13GeometryField.RISK_DISTANCE: selection.risk_distance,
        Wo13GeometryField.REWARD_DISTANCE: selection.reward_distance,
        Wo13GeometryField.MODEL_RR: selection.model_rr,
    }
    fields = tuple(create_wo13_field_availability(
        field,
        Wo13FieldAvailability.AVAILABLE if values[field] is not None else Wo13FieldAvailability.UNAVAILABLE,
        reason=f"{field.value}_{'AVAILABLE' if values[field] is not None else 'UNAVAILABLE'}",
        source_identities=request.handoff.source_identities,
        source_integrities=request.handoff.source_integrities,
    ) for field in Wo13GeometryField)
    return create_wo13_trade_plan_contract(
        request=request,
        entry_reference=values[Wo13GeometryField.ENTRY_REFERENCE],
        entry_condition=values[Wo13GeometryField.ENTRY_CONDITION],
        stop=values[Wo13GeometryField.STOP],
        stop_structural_basis=values[Wo13GeometryField.STOP_STRUCTURAL_BASIS],
        thesis_invalidation_reference=values[Wo13GeometryField.THESIS_INVALIDATION_REFERENCE],
        thesis_invalidation_event=values[Wo13GeometryField.THESIS_INVALIDATION_EVENT],
        setup_native_target=values[Wo13GeometryField.SETUP_NATIVE_TARGET],
        canonical_target=values[Wo13GeometryField.CANONICAL_TARGET],
        target_structural_basis=values[Wo13GeometryField.TARGET_STRUCTURAL_BASIS],
        constraining_objective=values[Wo13GeometryField.CONSTRAINING_OBJECTIVE],
        risk_distance=values[Wo13GeometryField.RISK_DISTANCE],
        reward_distance=values[Wo13GeometryField.REWARD_DISTANCE],
        model_rr=values[Wo13GeometryField.MODEL_RR],
        geometry_availability=selection.geometry_availability,
        field_availability=fields, warnings=selection.calculation.warnings,
        supersession=supersession,
        provenance=(
            *provenance,
            geometry.geometry_identity,
            selection.candidate_population.population_identity,
            selection.selection_identity,
        ),
        additional_source_identities=tuple(item[0] for item in additional_sources),
        additional_source_integrities=tuple(item[1] for item in additional_sources),
    )


def _source_pairs(*values: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    retained: dict[str, str] = {}
    for identities, integrities in zip(values[::2], values[1::2], strict=True):
        for identity, integrity in zip(identities, integrities, strict=True):
            previous = retained.get(identity)
            if previous is not None and previous != integrity:
                raise Wo13ApplicationError("WO13_SOURCE_INTEGRITY_CONFLICT")
            retained[identity] = integrity
    return tuple(sorted(retained.items()))


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if type(value) is str and value.startswith("WO13_") and len(value) <= 128:
        return value
    if isinstance(error, Wo13PersistenceError):
        return "WO13_PERSISTENCE_FAILURE"
    return "WO13_APPLICATION_FAILURE"


__all__ = ["IntradayWo13Application", "IntradayWo13RestorationService", "Wo13ApplicationError", "Wo13Execution", "Wo13RestorationStatus"]
