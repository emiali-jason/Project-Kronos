"""Zero-discretion application and inert restoration for Intraday WO-15D."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import Wo13ContractError
from kronos.intraday.wo13_persistence import Wo13PersistenceError, Wo13Store
from kronos.intraday.wo15 import (
    Wo15ContractError,
    Wo15TimingState,
    create_wo15_wo13_handoff,
)
from kronos.intraday.wo15_handoff import (
    Wo15TimingHandoff,
    create_wo15_timing_handoff,
)
from kronos.intraday.wo15_persistence import (
    CurrentWo15Pointer,
    RestoredWo15State,
    Wo15InvalidOperationProvenance,
    Wo15OperationOutcome,
    Wo15OperationProvenance,
    Wo15OperationRequest,
    Wo15OperationStage,
    Wo15PersistenceError,
    Wo15Store,
    Wo15SupersessionLineage,
    Wo15SupersessionReason,
    create_current_wo15_pointer,
    create_wo15_invalid_operation,
    create_wo15_operation_provenance,
    create_wo15_supersession,
)
from kronos.intraday.wo15_telemetry import (
    Wo15ResearchTelemetry,
    Wo15TelemetryError,
    build_wo15_research_telemetry,
)
from kronos.intraday.wo15_timing import (
    Wo15ResetAssessment,
    Wo15TimingEvaluationResult,
    Wo15TimingGrammarError,
    evaluate_wo15_successor_cycle,
    evaluate_wo15_timing,
)


class Wo15ApplicationError(Wo15ContractError):
    """Sanitized timing orchestration or concurrency failure."""


@dataclass(frozen=True, slots=True)
class Wo15Execution:
    request_identity: str
    timing_result: Wo15TimingEvaluationResult
    telemetry: Wo15ResearchTelemetry | None
    timing_handoff: Wo15TimingHandoff | None
    pointer: CurrentWo15Pointer
    operation: Wo15OperationProvenance
    supersession: Wo15SupersessionLineage | None
    reset_assessment: Wo15ResetAssessment | None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class Wo15RestorationStatus:
    state: str
    restored: RestoredWo15State | None
    latest_failure: Wo15InvalidOperationProvenance | None
    failure_stage: str | None = None
    failure_reason: str | None = None


class IntradayWo15Application:
    """Evaluate one exact current WO-13 plan using the published WO-15 engine."""

    def __init__(self, *, wo13_store: Wo13Store, store: Wo15Store) -> None:
        if type(wo13_store) is not Wo13Store or type(store) is not Wo15Store:
            raise ValueError("WO15_APPLICATION_CONFIGURATION_INVALID")
        self._wo13_store = wo13_store
        self._store = store
        self._lock = Lock()

    @property
    def store(self) -> Wo15Store:
        return self._store

    @property
    def wo13_store(self) -> Wo13Store:
        return self._wo13_store

    def execute(self, request: Wo15OperationRequest) -> Wo15Execution:
        if type(request) is not Wo15OperationRequest:
            raise Wo15ApplicationError("WO15_REQUEST_INVALID")
        try:
            request.__post_init__()
        except (TypeError, ValueError) as error:
            raise Wo15ApplicationError("WO15_REQUEST_INVALID") from error
        if not self._lock.acquire(blocking=False):
            raise Wo15ApplicationError("WO15_OPERATION_BUSY")

        stage = Wo15OperationStage.REQUEST_VALIDATION
        started_at = request.requested_at
        provenance = (*request.provenance, "WO15_ZERO_DISCRETION_APPLICATION_V1")
        try:
            current = self._store.load_current()
            if current is not None and current.request_identity == request.request_identity:
                restored = self._store.restore_current()
                if restored is None or restored.request != request:
                    raise Wo15ApplicationError("WO15_IDEMPOTENT_REPLAY_INVALID")
                return Wo15Execution(
                    request.request_identity,
                    restored.result,
                    restored.telemetry,
                    restored.timing_handoff,
                    restored.pointer,
                    restored.operation,
                    restored.supersession,
                    None,
                    True,
                )

            self._store.retain_request(request)
            self._started(request, stage, started_at,
                          (*provenance, "REQUEST_PERSISTED"))

            stage = Wo15OperationStage.WO13_PLAN_RELOAD
            self._validate_current_wo13(request)
            self._validate_lineage(request)
            self._started(
                request, stage, started_at,
                (*provenance, request.admission.wo13_trade_plan_identity),
            )

            previous = None
            if (
                current is not None
                and current.wo13_trade_plan_identity
                == request.admission.wo13_trade_plan_identity
            ):
                previous = self._store.load_result(current.timing_result_identity)
                if previous.result_integrity != current.timing_result_integrity:
                    raise Wo15ApplicationError("WO15_CURRENT_RESULT_INVALID")

            stage = Wo15OperationStage.TIMING_EVALUATION
            reset_assessment = None
            if (
                previous is not None
                and previous.current_state is Wo15TimingState.TIMING_FAILED
            ):
                reset_assessment, result = evaluate_wo15_successor_cycle(
                    admission=request.admission,
                    session=request.session,
                    predecessor=previous,
                    source_candle=request.source_candle,
                    evidence=request.evidence,
                    progression=request.progression,
                    observed_at=request.observed_at,
                    expiry_event=request.expiry_event,
                )
                self._store.retain_reset_assessment(reset_assessment)
                if result is None:
                    raise Wo15ApplicationError(
                        f"WO15_RESET_{reset_assessment.disposition.value}"
                    )
            else:
                result = evaluate_wo15_timing(
                    admission=request.admission,
                    session=request.session,
                    source_candle=request.source_candle,
                    evidence=request.evidence,
                    progression=request.progression,
                    observed_at=request.observed_at,
                    previous=previous,
                    expiry_event=request.expiry_event,
                    wo14_reference_state=request.wo14_reference_state,
                    model_rr_context=request.model_rr_context,
                )
            self._started(
                request, stage, started_at,
                (*provenance, result.result_identity),
            )

            stage = Wo15OperationStage.TELEMETRY
            telemetry = self._build_telemetry(request, result)
            self._started(
                request, stage, started_at,
                (*provenance, "TELEMETRY_UNAVAILABLE" if telemetry is None
                 else telemetry.telemetry_identity),
            )

            supersession = self._supersession(
                current=current,
                previous=previous,
                result=result,
                request=request,
                reset=reset_assessment,
            )

            stage = Wo15OperationStage.HANDOFF
            timing_handoff = self._handoff(
                request=request,
                result=result,
                telemetry=telemetry,
                current=current,
                supersession=supersession,
            )
            self._started(
                request, stage, started_at,
                (*provenance, "TIMING_HANDOFF_NOT_REQUIRED"
                 if timing_handoff is None else timing_handoff.handoff_identity),
            )

            stage = Wo15OperationStage.PERSISTENCE
            self._retain_result_graph(
                request=request,
                result=result,
                telemetry=telemetry,
                handoff=timing_handoff,
                supersession=supersession,
            )
            self._started(
                request, stage, started_at,
                (*provenance, "EXACT_ARTIFACT_RELOAD_COMPLETE"),
            )

            stage = Wo15OperationStage.POINTER_PUBLICATION
            completed = create_wo15_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo15OperationOutcome.COMPLETED,
                started_at=started_at,
                completed_at=request.observed_at,
                timing_result=result,
                timing_handoff=timing_handoff,
                provenance=(*provenance, "RESULT_RELOADED_POINTER_READY"),
            )
            self._store.retain_operation(completed)
            pointer = create_current_wo15_pointer(
                request=request,
                result=result,
                operation=completed,
                telemetry=telemetry,
                timing_handoff=timing_handoff,
                supersession=supersession,
                published_at=request.observed_at,
            )
            candidate = self._store.restore_pointer(pointer)
            if (
                candidate.pointer != pointer
                or candidate.request != request
                or candidate.result != result
                or candidate.telemetry != telemetry
                or candidate.timing_handoff != timing_handoff
            ):
                raise Wo15ApplicationError("WO15_PRE_PUBLICATION_RELOAD_INVALID")
            self._store.publish_current(pointer)

            stage = Wo15OperationStage.RESTORATION
            restored = self._store.restore_current()
            if (
                restored is None
                or restored.pointer != pointer
                or restored.request != request
                or restored.result != result
                or restored.telemetry != telemetry
                or restored.timing_handoff != timing_handoff
            ):
                raise Wo15ApplicationError("WO15_POST_PUBLICATION_RELOAD_INVALID")
            return Wo15Execution(
                request.request_identity,
                result,
                telemetry,
                timing_handoff,
                pointer,
                completed,
                supersession,
                reset_assessment,
            )
        except Exception as error:
            reason = _failure_code(error)
            self._record_failure(request, stage, started_at, reason, provenance)
            raise Wo15ApplicationError(reason) from error
        finally:
            self._lock.release()

    def restore_current(self) -> RestoredWo15State | None:
        return self._store.restore_current()

    def _validate_current_wo13(self, request: Wo15OperationRequest) -> None:
        current = self._wo13_store.load_current()
        if current is None:
            raise Wo15ApplicationError("WO15_CURRENT_WO13_UNAVAILABLE")
        admission = request.admission
        if (
            current.pointer_identity != admission.current_pointer_identity
            or current.pointer_integrity != admission.current_pointer_integrity
            or current.trade_plan_identity != admission.wo13_trade_plan_identity
            or current.trade_plan_integrity != admission.wo13_trade_plan_integrity
        ):
            raise Wo15ApplicationError("WO15_SUPERSEDED_WO13_REJECTED")
        plan = self._wo13_store.load_trade_plan(current.trade_plan_identity)
        source_handoff = self._wo13_store.load_handoff(current.handoff_identity)
        rebound = create_wo15_wo13_handoff(
            current_pointer=current,
            trade_plan=plan,
            source_handoff=source_handoff,
            policy=admission.policy,
            provenance=admission.provenance,
        )
        if rebound != admission:
            raise Wo15ApplicationError("WO15_WO13_ADMISSION_RELOAD_MISMATCH")

    @staticmethod
    def _validate_lineage(request: Wo15OperationRequest) -> None:
        admission = request.admission
        session = request.session
        evidence = request.evidence
        progression = request.progression
        mcx = admission.market_family is IntradayMarketFamily.MCX
        if (
            evidence.canonical_subject_identity
            != admission.canonical_subject_identity
            or evidence.market_family is not admission.market_family
            or evidence.instrument_identity != admission.instrument_identity
            or evidence.actual_contract_identity
            != admission.actual_contract_identity
            or evidence.roll_lineage_identity != admission.roll_lineage_identity
            or evidence.session_identity != session.session_identity
            or evidence.trading_date != session.trading_date
            or progression.canonical_subject_identity
            != admission.canonical_subject_identity
            or progression.analysis_boundary != evidence.observation_boundary
            or mcx != (evidence.actual_contract_identity is not None)
            or mcx != (evidence.roll_lineage_identity is not None)
        ):
            raise Wo15ApplicationError("WO15_REQUEST_LINEAGE_MISMATCH")

    @staticmethod
    def _build_telemetry(
        request: Wo15OperationRequest,
        result: Wo15TimingEvaluationResult,
    ) -> Wo15ResearchTelemetry | None:
        if request.telemetry_measurement is None:
            return None
        telemetry = build_wo15_research_telemetry(
            admission=request.admission,
            session=request.session,
            timing_result=result,
            measurement=request.telemetry_measurement,
            atr_history=request.telemetry_atr_history,
            cycle_history=request.telemetry_cycle_history,
            research_references=request.telemetry_references,
        )
        if telemetry.timing_state_observed is not result.current_state:
            raise Wo15ApplicationError("WO15_TELEMETRY_TIMING_MUTATION")
        return telemetry

    def _supersession(
        self, *, current: CurrentWo15Pointer | None,
        previous: Wo15TimingEvaluationResult | None,
        result: Wo15TimingEvaluationResult,
        request: Wo15OperationRequest,
        reset: Wo15ResetAssessment | None,
    ) -> Wo15SupersessionLineage | None:
        if current is None:
            return None
        predecessor = (
            previous
            if previous is not None
            else self._store.load_result(current.timing_result_identity)
        )
        if predecessor.result_identity == result.result_identity:
            return None
        reason = Wo15SupersessionReason.LATER_TIMING_EVALUATION
        if reset is not None and reset.eligible:
            reason = Wo15SupersessionReason.RESET_SUCCESSOR_CYCLE
        elif current.wo13_trade_plan_identity != result.wo13_trade_plan_identity:
            reason = Wo15SupersessionReason.WO13_PLAN_SUPERSEDED
        elif (
            current.instrument_identity != request.admission.instrument_identity
            or current.actual_contract_identity
            != request.admission.actual_contract_identity
            or current.roll_lineage_identity != request.admission.roll_lineage_identity
        ):
            reason = Wo15SupersessionReason.INSTRUMENT_CONTRACT_SUPERSEDED
        elif current.session_identity != request.session.session_identity:
            reason = Wo15SupersessionReason.SESSION_EXPIRED
        return create_wo15_supersession(
            predecessor_pointer=current,
            predecessor=predecessor,
            successor=result,
            reason=reason,
            superseded_at=request.observed_at,
        )

    def _handoff(
        self, *, request: Wo15OperationRequest,
        result: Wo15TimingEvaluationResult,
        telemetry: Wo15ResearchTelemetry | None,
        current: CurrentWo15Pointer | None,
        supersession: Wo15SupersessionLineage | None,
    ) -> Wo15TimingHandoff | None:
        if (
            result.cycle_evaluation is None
            or result.current_state is Wo15TimingState.TIMING_WAITING
        ):
            return None
        predecessor = None
        if (
            current is not None
            and current.timing_handoff_identity is not None
            and current.timing_cycle_identity == result.timing_cycle_id
        ):
            candidate = self._store.load_handoff(
                current.timing_handoff_identity
            )
            if (
                candidate.current_state is Wo15TimingState.TIMING_QUALIFIED
                and result.current_state in {
                    Wo15TimingState.TIMING_FAILED,
                    Wo15TimingState.TIMING_EXPIRED,
                }
            ):
                predecessor = candidate
        references = (
            () if telemetry is None else (telemetry.telemetry_identity,)
        )
        return create_wo15_timing_handoff(
            admission=request.admission,
            evaluation=result.cycle_evaluation,
            handoff_created_at=request.observed_at,
            research_references=references,
            wo14_observation_identity=request.wo14_observation_identity,
            wo14_observation_integrity=request.wo14_observation_integrity,
            predecessor=predecessor,
            supersession_lineage_identity=(
                None if supersession is None else supersession.lineage_identity
            ),
            provenance=(*request.provenance, "WO-15D"),
        )

    def _retain_result_graph(
        self, *, request: Wo15OperationRequest,
        result: Wo15TimingEvaluationResult,
        telemetry: Wo15ResearchTelemetry | None,
        handoff: Wo15TimingHandoff | None,
        supersession: Wo15SupersessionLineage | None,
    ) -> None:
        self._store.retain_admission(request.admission)
        self._store.retain_session(request.session)
        self._store.retain_evidence(request.evidence)
        self._store.retain_progression(request.progression)
        evaluation = result.cycle_evaluation
        if evaluation is not None:
            self._store.retain_cycle(evaluation.cycle)
            self._store.retain_observation(evaluation.observation)
            self._store.retain_transition(evaluation.transition)
            self._store.retain_evaluation(evaluation)
        if result.local_history is not None:
            self._store.retain_history(result.local_history)
        self._store.retain_result(result)
        if telemetry is not None:
            self._store.retain_telemetry(telemetry)
        if supersession is not None:
            self._store.retain_supersession(supersession)
        if handoff is not None:
            self._store.retain_handoff(handoff)

        if self._store.load_result(result.result_identity) != result:
            raise Wo15ApplicationError("WO15_RESULT_RELOAD_INVALID")
        if telemetry is not None and (
            self._store.load_telemetry(telemetry.telemetry_identity) != telemetry
        ):
            raise Wo15ApplicationError("WO15_TELEMETRY_RELOAD_INVALID")
        if handoff is not None and (
            self._store.load_handoff(handoff.handoff_identity) != handoff
        ):
            raise Wo15ApplicationError("WO15_HANDOFF_RELOAD_INVALID")

    def _started(
        self, request: Wo15OperationRequest, stage: Wo15OperationStage,
        started_at, provenance: tuple[str, ...],  # type: ignore[no-untyped-def]
    ) -> None:
        self._store.retain_operation(create_wo15_operation_provenance(
            request=request,
            stage=stage,
            outcome=Wo15OperationOutcome.STARTED,
            started_at=started_at,
            provenance=provenance,
        ))

    def _record_failure(
        self, request: Wo15OperationRequest, stage: Wo15OperationStage,
        started_at, reason: str, provenance: tuple[str, ...],  # type: ignore[no-untyped-def]
    ) -> None:
        try:
            failed = create_wo15_operation_provenance(
                request=request,
                stage=stage,
                outcome=Wo15OperationOutcome.FAILED,
                started_at=started_at,
                failed_at=request.observed_at,
                failure_reason=reason,
                provenance=(*provenance, "CURRENT_WO15_POINTER_PRESERVED"),
            )
            invalid = create_wo15_invalid_operation(
                request=request,
                stage=stage,
                reason=reason,
                failed_at=request.observed_at,
            )
            self._store.retain_operation(failed)
            self._store.publish_latest_failure(invalid)
        except (OSError, ValueError):
            # Never replace the original sanitized application failure with a
            # secondary provenance-write failure.
            return


class IntradayWo15RestorationService:
    """Provider-independent exact restoration without timing recalculation."""

    def __init__(self, *, store: Wo15Store) -> None:
        if type(store) is not Wo15Store:
            raise ValueError("WO15_RESTORATION_CONFIGURATION_INVALID")
        self._store = store

    def restore(self) -> Wo15RestorationStatus:
        try:
            restored = self._store.restore_current()
            latest_failure = self._store.load_latest_failure()
        except (Wo15PersistenceError, Wo15ContractError, OSError, ValueError):
            return Wo15RestorationStatus(
                "CORRUPT", None, None, "RESTORATION",
                "WO15_RESTORATION_FAILED",
            )
        return Wo15RestorationStatus(
            "NOT_YET_RUN" if restored is None else "LOADED",
            restored,
            latest_failure,
        )


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if type(value) is str and value.startswith("WO15_") and len(value) <= 128:
        return value
    if isinstance(error, Wo13PersistenceError):
        return "WO15_WO13_PLAN_RELOAD_FAILED"
    if isinstance(error, Wo13ContractError):
        return "WO15_WO13_PLAN_INVALID"
    if isinstance(error, Wo15PersistenceError):
        return "WO15_PERSISTENCE_FAILURE"
    if isinstance(error, Wo15TimingGrammarError):
        return "WO15_TIMING_EVALUATION_FAILED"
    if isinstance(error, Wo15TelemetryError):
        return "WO15_TELEMETRY_FAILURE"
    return "WO15_APPLICATION_FAILURE"


__all__ = [
    "IntradayWo15Application", "IntradayWo15RestorationService",
    "Wo15ApplicationError", "Wo15Execution", "Wo15RestorationStatus",
]
