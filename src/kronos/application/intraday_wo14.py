"""Zero-discretion application and inert restoration for Intraday WO-14."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import Wo13ContractError
from kronos.intraday.wo13_persistence import Wo13PersistenceError, Wo13Store
from kronos.intraday.wo14 import (
    CurrentWo14Pointer,
    Wo14ContractError,
    Wo14InvalidObservationProvenance,
    Wo14ObservationRequest,
    Wo14OperationOutcome,
    Wo14OperationProvenance,
    Wo14OperationStage,
    Wo14RiskObservation,
    Wo14SupersessionLineage,
    bind_wo13_trade_plan,
    calculate_wo14_observation,
    create_current_wo14_pointer,
    create_wo14_invalid_provenance,
    create_wo14_operation_provenance,
    create_wo14_supersession,
)
from kronos.intraday.wo14_persistence import (
    RestoredWo14State,
    Wo14PersistenceError,
    Wo14Store,
)


class Wo14ApplicationError(Wo14ContractError):
    """Sanitized observation orchestration or concurrency failure."""


@dataclass(frozen=True, slots=True)
class Wo14Execution:
    request_identity: str
    observation: Wo14RiskObservation
    pointer: CurrentWo14Pointer
    operation: Wo14OperationProvenance
    supersession: Wo14SupersessionLineage | None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class Wo14RestorationStatus:
    state: str
    restored: RestoredWo14State | None
    latest_failure: Wo14InvalidObservationProvenance | None
    failure_stage: str | None = None
    failure_reason: str | None = None


class IntradayWo14Application:
    """Observe an exact persisted WO-13 plan without changing or rerunning it."""

    def __init__(self, *, wo13_store: Wo13Store, store: Wo14Store) -> None:
        if type(wo13_store) is not Wo13Store or type(store) is not Wo14Store:
            raise ValueError("WO14_APPLICATION_CONFIGURATION_INVALID")
        self._wo13_store = wo13_store
        self._store = store
        self._lock = Lock()

    @property
    def store(self) -> Wo14Store:
        return self._store

    @property
    def wo13_store(self) -> Wo13Store:
        return self._wo13_store

    def execute(self, request: Wo14ObservationRequest) -> Wo14Execution:
        if type(request) is not Wo14ObservationRequest:
            raise Wo14ApplicationError("WO14_REQUEST_INVALID")
        if not self._lock.acquire(blocking=False):
            raise Wo14ApplicationError("WO14_OPERATION_BUSY")
        started_at = request.requested_at
        stage = Wo14OperationStage.REQUEST_VALIDATION
        provenance = (*request.provenance, "WO14_ZERO_DISCRETION_APPLICATION_V1")
        try:
            current = self._store.load_current()
            if current is not None and current.request_identity == request.request_identity:
                restored = self._store.restore_current()
                if restored is None or restored.request != request:
                    raise Wo14ApplicationError("WO14_IDEMPOTENT_REPLAY_INVALID")
                return Wo14Execution(
                    request.request_identity, restored.observation, restored.pointer,
                    restored.operation, restored.supersession, True,
                )

            self._store.retain_request(request)
            self._started(request, stage, started_at, (*provenance, "REQUEST_PERSISTED"))

            stage = Wo14OperationStage.WO13_PLAN_RELOAD
            current_wo13 = self._wo13_store.load_current()
            if current_wo13 is None:
                raise Wo14ApplicationError("WO14_CURRENT_WO13_UNAVAILABLE")
            if (
                current_wo13.trade_plan_identity
                != request.plan_binding.trade_plan_identity
                or current_wo13.trade_plan_integrity
                != request.plan_binding.trade_plan_integrity
            ):
                raise Wo14ApplicationError("WO14_SUPERSEDED_WO13_REJECTED")
            plan = self._wo13_store.load_trade_plan(
                request.plan_binding.trade_plan_identity
            )
            if bind_wo13_trade_plan(plan) != request.plan_binding:
                raise Wo14ApplicationError("WO14_WO13_PLAN_BINDING_MISMATCH")
            handoff = self._wo13_store.load_handoff(plan.source_handoff_identity)
            if (
                handoff.handoff_integrity != plan.source_handoff_integrity
                or handoff.canonical_subject_identity != plan.canonical_subject_identity
                or handoff.market_family is not plan.market_family
                or handoff.inherited_direction is not plan.direction
                or handoff.setup_family is not plan.setup_family
                or handoff.analysis_boundary != plan.analysis_boundary
                or handoff.instrument_identity != plan.instrument_identity
                or handoff.actual_contract_identity != plan.actual_contract_identity
            ):
                raise Wo14ApplicationError("WO14_WO13_HANDOFF_BINDING_MISMATCH")
            self._started(
                request, stage, started_at,
                (*provenance, plan.trade_plan_identity, handoff.handoff_identity),
            )

            stage = Wo14OperationStage.INPUT_VALIDATION
            self._validate_optional_inputs(request, plan, handoff)
            self._started(request, stage, started_at, (*provenance, "INPUTS_VALIDATED"))

            stage = Wo14OperationStage.INSTRUMENT_ECONOMICS
            economics = request.instrument_economics
            self._started(
                request, stage, started_at,
                (*provenance, "ECONOMICS_NOT_SUPPLIED" if economics is None
                 else economics.economics_identity),
            )

            stage = Wo14OperationStage.CALCULATION
            observation = calculate_wo14_observation(request, plan)
            self._started(
                request, stage, started_at,
                (*provenance, observation.observation_identity),
            )

            stage = Wo14OperationStage.PERSISTENCE
            self._store.retain_observation(observation)
            if self._store.load_observation(observation.observation_identity) != observation:
                raise Wo14ApplicationError("WO14_OBSERVATION_RELOAD_INVALID")
            self._started(
                request, stage, started_at,
                (*provenance, "OBSERVATION_EXPLICIT_RELOAD"),
            )

            supersession = None
            if current is not None:
                predecessor = self._store.load_observation(
                    current.observation_identity
                )
                if predecessor.observation_identity != observation.observation_identity:
                    supersession = create_wo14_supersession(
                        predecessor=predecessor, successor=observation,
                        superseded_at=request.evaluation_boundary,
                    )
                    self._store.retain_supersession(supersession)

            stage = Wo14OperationStage.POINTER_PUBLICATION
            completed = create_wo14_operation_provenance(
                request=request, stage=stage,
                outcome=Wo14OperationOutcome.COMPLETED,
                started_at=started_at, completed_at=request.evaluation_boundary,
                observation=observation,
                provenance=(*provenance, "OBSERVATION_RELOADED_POINTER_READY"),
            )
            self._store.retain_operation(completed)
            pointer = create_current_wo14_pointer(
                request=request, observation=observation, operation=completed,
                published_at=request.evaluation_boundary,
                supersession=supersession,
            )
            self._store.publish_current(pointer)
            restored = self._store.restore_current()
            if (
                restored is None or restored.pointer != pointer
                or restored.observation != observation
            ):
                raise Wo14ApplicationError("WO14_POST_PUBLICATION_RELOAD_INVALID")
            return Wo14Execution(
                request.request_identity, observation, pointer, completed,
                supersession,
            )
        except Exception as error:
            reason = _failure_code(error)
            failed = create_wo14_operation_provenance(
                request=request, stage=stage,
                outcome=Wo14OperationOutcome.FAILED,
                started_at=started_at, failed_at=request.evaluation_boundary,
                failure_reason=reason,
                provenance=(*provenance, "CURRENT_OBSERVATION_POINTER_PRESERVED"),
            )
            invalid = create_wo14_invalid_provenance(
                request=request, stage=stage, reason=reason,
                source_identities=(
                    request.plan_binding.trade_plan_identity,
                    request.plan_binding.source_handoff_identity,
                ),
                failed_at=request.evaluation_boundary,
            )
            self._store.retain_operation(failed)
            self._store.publish_latest_failure(invalid)
            raise Wo14ApplicationError(reason) from error
        finally:
            self._lock.release()

    def restore_current(self) -> RestoredWo14State | None:
        return self._store.restore_current()

    def _started(
        self, request: Wo14ObservationRequest, stage: Wo14OperationStage,
        started_at, provenance: tuple[str, ...],  # type: ignore[no-untyped-def]
    ) -> None:
        self._store.retain_operation(create_wo14_operation_provenance(
            request=request, stage=stage, outcome=Wo14OperationOutcome.STARTED,
            started_at=started_at, provenance=provenance,
        ))

    @staticmethod
    def _validate_optional_inputs(request, plan, handoff) -> None:  # type: ignore[no-untyped-def]
        economics = request.instrument_economics
        if plan.market_family is not IntradayMarketFamily.MCX:
            if economics is not None:
                raise Wo14ApplicationError("WO14_FOREIGN_INSTRUMENT_ECONOMICS")
            return
        if economics is None:
            return
        if (
            economics.canonical_subject_identity != plan.canonical_subject_identity
            or economics.instrument_identity != plan.instrument_identity
            or economics.actual_contract_identity != plan.actual_contract_identity
            or economics.roll_lineage_identity != handoff.roll_lineage_identity
            or economics.lot_size != handoff.lot_size
            or Decimal(handoff.tick_size) != economics.tick_size
        ):
            raise Wo14ApplicationError("WO14_MCX_INSTRUMENT_ECONOMICS_MISMATCH")


class IntradayWo14RestorationService:
    """Provider-independent exact-state restoration with no recalculation."""

    def __init__(self, *, store: Wo14Store) -> None:
        if type(store) is not Wo14Store:
            raise ValueError("WO14_RESTORATION_CONFIGURATION_INVALID")
        self._store = store

    def restore(self) -> Wo14RestorationStatus:
        try:
            restored = self._store.restore_current()
            latest_failure = self._store.load_latest_failure()
        except (Wo14PersistenceError, Wo14ContractError, OSError, ValueError):
            return Wo14RestorationStatus(
                "CORRUPT", None, None, "RESTORATION", "WO14_RESTORATION_FAILED"
            )
        return Wo14RestorationStatus(
            "NOT_YET_RUN" if restored is None else "LOADED",
            restored,
            latest_failure,
        )


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if type(value) is str and value.startswith("WO14_") and len(value) <= 128:
        return value
    if isinstance(error, Wo13PersistenceError):
        return "WO14_WO13_PLAN_RELOAD_FAILED"
    if isinstance(error, Wo13ContractError):
        return "WO14_WO13_PLAN_INVALID"
    if isinstance(error, Wo14PersistenceError):
        return "WO14_PERSISTENCE_FAILURE"
    return "WO14_APPLICATION_FAILURE"


__all__ = [
    "IntradayWo14Application", "IntradayWo14RestorationService",
    "Wo14ApplicationError", "Wo14Execution", "Wo14RestorationStatus",
]
