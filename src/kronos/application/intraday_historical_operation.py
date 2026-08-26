"""WO-06HA Intraday-owned bounded historical research operation."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Protocol

from kronos.intraday.historical_operation import (
    COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY,
    COMPLETED_SESSION_EOD_BOUNDARY_VERSION,
    HISTORICAL_OPERATION_TIMEFRAMES,
    REQUIRED_HISTORICAL_FACT_FAMILIES,
    HistoricalEodSession,
    HistoricalOperationError,
    HistoricalOperationFailure,
    HistoricalOperationStage,
    HistoricalOperationState,
    HistoricalOperationalSubject,
    HistoricalProviderRequestPlan,
    HistoricalQualificationOperationRequest,
    HistoricalQualificationOperationResult,
    HistoricalSessionOperationAccounting,
    create_historical_request_plan,
    resolve_historical_eod_sessions,
    resolve_historical_operational_subjects,
)
from kronos.intraday.historical_qualification import (
    HistoricalBindingAvailability,
    HistoricalCalendarSource,
    HistoricalFailureClassification,
    HistoricalQualificationError,
    HistoricalQualificationFactBundle,
    HistoricalResearchSubjectSet,
    assess_historical_corpus_eligibility,
    create_historical_failure_evidence,
    create_historical_reconstruction,
    create_historical_research_subject_set,
)
from kronos.intraday.historical_qualification_persistence import (
    HistoricalQualificationStore,
)
from kronos.intraday.historical_source import (
    HistoricalProviderFactAcquisition,
    ProviderHistoricalQualificationFactualSource,
)
from kronos.intraday.historical_semantic_persistence import (
    HistoricalSemanticStore,
)
from kronos.intraday.qualification import (
    NARROW_CPR_CALCULATION_IDENTITY,
    PART1_CONTRACT_VERSION,
)
from kronos.intraday.reconciliation import ReconciliationPublication
from kronos.intraday.universe import IntradayUniversePublication
from kronos.provider.contracts.provider_authentication import (
    ReadOnlyProviderOperation,
)
from kronos.provider.runtime import (
    ProviderRuntimeAccessError,
    ProviderRuntimeFailure,
    ReadOnlyProviderLease,
    SharedAuthenticatedProviderRuntime,
    SharedProviderRuntimeLifecycle,
)


HISTORICAL_OPERATION_CONSUMER_IDENTITY = (
    "INTRADAY_HISTORICAL_QUALIFICATION_RESEARCH"
)
HISTORICAL_OPERATION_LEASE_CAPABILITIES = frozenset(
    {
        ReadOnlyProviderOperation.INSTRUMENTS,
        ReadOnlyProviderOperation.HISTORICAL_DATA,
    }
)


class HistoricalFactualSource(Protocol):
    @property
    def total_provider_request_count(self) -> int: ...

    def acquire(
        self,
        *,
        subject: HistoricalOperationalSubject,
        session: HistoricalEodSession,
        requested_factual_families: tuple,
        source_operation_identity: str,
    ) -> HistoricalProviderFactAcquisition: ...


HistoricalSourceFactory = Callable[[ReadOnlyProviderLease], HistoricalFactualSource]


class IntradayHistoricalQualificationOperationService:
    """Serialize one explicit research request without production state access."""

    def __init__(
        self,
        *,
        provider_runtime: SharedAuthenticatedProviderRuntime,
        universe: IntradayUniversePublication,
        reconciliation: ReconciliationPublication,
        calendar: HistoricalCalendarSource,
        store: HistoricalQualificationStore,
        semantic_store: HistoricalSemanticStore | None = None,
        source_factory: HistoricalSourceFactory | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if (
            type(provider_runtime) is not SharedAuthenticatedProviderRuntime
            or type(universe) is not IntradayUniversePublication
            or type(reconciliation) is not ReconciliationPublication
            or not callable(getattr(calendar, "schedule_for", None))
            or not callable(getattr(calendar, "previous_trading_schedule", None))
            or not callable(getattr(calendar, "for_subject", None))
            or type(store) is not HistoricalQualificationStore
            or semantic_store is not None
            and type(semantic_store) is not HistoricalSemanticStore
            or source_factory is not None and not callable(source_factory)
            or not callable(clock)
        ):
            raise ValueError("HISTORICAL_OPERATION_DEPENDENCY_INVALID")
        self._runtime = provider_runtime
        self._universe = universe
        self._reconciliation = reconciliation
        self._calendar = calendar
        self._store = store
        self._semantic_store = semantic_store or HistoricalSemanticStore(
            store.root
        )
        self._clock = clock
        self._source_factory = source_factory or (
            lambda lease: ProviderHistoricalQualificationFactualSource(
                lease,
                clock=clock,
            )
        )
        self._lock = RLock()
        self._active_identity: str | None = None
        self._results: dict[str, HistoricalQualificationOperationResult] = {}
        self._semantic_artifacts: dict[
            str, tuple[tuple[str, ...], tuple[str, ...]]
        ] = {}

    @property
    def operation_available(self) -> bool:
        return self._runtime.lifecycle_state is SharedProviderRuntimeLifecycle.ACTIVE

    @property
    def actual_context_state(self) -> str:
        return self._runtime.lifecycle_state.value

    @property
    def active_operation_identity(self) -> str | None:
        with self._lock:
            return self._active_identity

    @property
    def universe_publication(self) -> IntradayUniversePublication:
        """Expose the governed request universe to a bounded local adapter."""

        return self._universe

    @property
    def last_result(self) -> HistoricalQualificationOperationResult | None:
        with self._lock:
            return next(reversed(self._results.values()), None)

    def result_for(
        self, operation_identity: str
    ) -> HistoricalQualificationOperationResult | None:
        with self._lock:
            return self._results.get(operation_identity)

    def semantic_artifact_accounting(
        self, operation_identity: str
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return exact candle/evidence identities for one in-process operation."""

        with self._lock:
            return self._semantic_artifacts.get(operation_identity, ((), ()))

    def execute(
        self, request: HistoricalQualificationOperationRequest
    ) -> HistoricalQualificationOperationResult:
        if type(request) is not HistoricalQualificationOperationRequest:
            raise HistoricalOperationError(
                HistoricalOperationFailure.REQUEST_INVALID
            )
        with self._lock:
            completed = self._results.get(request.operation_identity)
            if completed is not None:
                return completed
            if self._active_identity is not None:
                return self._conflict(request)
            self._active_identity = request.operation_identity

        stage = HistoricalOperationStage.CONTEXT_VERIFICATION
        lease: ReadOnlyProviderLease | None = None
        source: HistoricalFactualSource | None = None
        subject_set: HistoricalResearchSubjectSet | None = None
        subjects: tuple[HistoricalOperationalSubject, ...] = ()
        sessions: tuple[HistoricalEodSession, ...] = ()
        plan: HistoricalProviderRequestPlan | None = None
        try:
            lifecycle = self._runtime.lifecycle_state
            if lifecycle is not SharedProviderRuntimeLifecycle.ACTIVE:
                failure = (
                    HistoricalOperationFailure.CONTEXT_EXPIRED
                    if lifecycle is SharedProviderRuntimeLifecycle.EXPIRED
                    else HistoricalOperationFailure.CONTEXT_UNAVAILABLE
                )
                return self._failure(request, stage=stage, failure=failure)

            stage = HistoricalOperationStage.REQUEST_VALIDATION
            self._validate_request(request)

            stage = HistoricalOperationStage.SUBJECT_SET_RESOLUTION
            subject_set = create_historical_research_subject_set(self._universe)
            subjects = resolve_historical_operational_subjects(
                subject_set=subject_set,
                reconciliation=self._reconciliation,
            )

            stage = HistoricalOperationStage.SESSION_RESOLUTION
            sessions = resolve_historical_eod_sessions(
                calendar=self._calendar,
                requested=request.sessions,
                exchange="NSE",
                provenance=(
                    request.operation_identity,
                    COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY,
                ),
            )

            stage = HistoricalOperationStage.REQUEST_PLANNING
            plan = create_historical_request_plan(
                request=request,
                subjects=subjects,
                sessions=sessions,
            )
            if plan.total_provider_request_count > request.maximum_provider_requests:
                return self._failure(
                    request,
                    stage=stage,
                    failure=HistoricalOperationFailure.REQUEST_BOUND_EXCEEDED,
                    subjects=subjects,
                    sessions=sessions,
                    plan=plan,
                )

            stage = HistoricalOperationStage.LEASE_ACQUISITION
            lease = self._runtime.acquire_lease(
                consumer_identity=HISTORICAL_OPERATION_CONSUMER_IDENTITY,
                operations=HISTORICAL_OPERATION_LEASE_CAPABILITIES,
            )
            if not lease.active or lease.operations != HISTORICAL_OPERATION_LEASE_CAPABILITIES:
                return self._failure(
                    request,
                    stage=stage,
                    failure=HistoricalOperationFailure.CONTEXT_UNAVAILABLE,
                    subjects=subjects,
                    sessions=sessions,
                    plan=plan,
                )
            source = self._source_factory(lease)

            return self._acquire_and_reconstruct(
                request=request,
                subject_set=subject_set,
                subjects=subjects,
                sessions=sessions,
                plan=plan,
                source=source,
            )
        except ProviderRuntimeAccessError as error:
            failure = (
                HistoricalOperationFailure.CONTEXT_EXPIRED
                if error.failure is ProviderRuntimeFailure.CONTEXT_EXPIRED
                else HistoricalOperationFailure.CONTEXT_UNAVAILABLE
            )
            return self._failure(
                request,
                stage=stage,
                failure=failure,
                subjects=subjects,
                sessions=sessions,
                plan=plan,
                provider_request_count=_provider_count(source),
            )
        except HistoricalOperationError as error:
            failure_stage = {
                HistoricalOperationFailure.PERSISTENCE_FAILED:
                    HistoricalOperationStage.PERSISTENCE,
                HistoricalOperationFailure.RELOAD_FAILED:
                    HistoricalOperationStage.RELOAD_VERIFICATION,
            }.get(error.failure, stage)
            return self._failure(
                request,
                stage=failure_stage,
                failure=error.failure,
                subjects=subjects,
                sessions=sessions,
                plan=plan,
                provider_request_count=_provider_count(source),
            )
        except HistoricalQualificationError:
            failure = {
                HistoricalOperationStage.PERSISTENCE:
                    HistoricalOperationFailure.PERSISTENCE_FAILED,
                HistoricalOperationStage.RELOAD_VERIFICATION:
                    HistoricalOperationFailure.RELOAD_FAILED,
            }.get(stage, HistoricalOperationFailure.INTEGRITY_INVALID)
            return self._failure(
                request,
                stage=stage,
                failure=failure,
                subjects=subjects,
                sessions=sessions,
                plan=plan,
                provider_request_count=_provider_count(source),
            )
        except Exception:
            return self._failure(
                request,
                stage=stage,
                failure=HistoricalOperationFailure.INTEGRITY_INVALID,
                subjects=subjects,
                sessions=sessions,
                plan=plan,
                provider_request_count=_provider_count(source),
            )
        finally:
            if lease is not None:
                lease.release()
            with self._lock:
                if self._active_identity == request.operation_identity:
                    self._active_identity = None

    def _validate_request(
        self, request: HistoricalQualificationOperationRequest
    ) -> None:
        if (
            request.universe_identity != self._universe.publication_identity
            or request.universe_version != self._universe.publication_version
            or request.universe_integrity_identity != self._universe.integrity_identity
            or request.boundary_family_identity
            != COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY
            or request.boundary_family_version
            != COMPLETED_SESSION_EOD_BOUNDARY_VERSION
            or request.timeframes != HISTORICAL_OPERATION_TIMEFRAMES
            or not set(REQUIRED_HISTORICAL_FACT_FAMILIES).issubset(
                request.requested_factual_families
            )
            or request.requested_outcome_families
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.REQUEST_INVALID
            )

    def _acquire_and_reconstruct(
        self,
        *,
        request: HistoricalQualificationOperationRequest,
        subject_set: HistoricalResearchSubjectSet,
        subjects: tuple[HistoricalOperationalSubject, ...],
        sessions: tuple[HistoricalEodSession, ...],
        plan: HistoricalProviderRequestPlan,
        source: HistoricalFactualSource,
    ) -> HistoricalQualificationOperationResult:
        eligible = tuple(
            item
            for item in subjects
            if item.binding.availability is HistoricalBindingAvailability.AVAILABLE
        )
        unavailable_count = len(subjects) - len(eligible)
        reconstruction_ids: list[str] = []
        bundle_ids: list[str] = []
        failure_evidence_ids: list[str] = []
        accounting: list[HistoricalSessionOperationAccounting] = []
        failures: Counter[str] = Counter()
        total_success = 0
        total_factual_failures = 0
        total_true = 0
        total_false = 0
        candle_payload_ids: list[str] = []
        semantic_evidence_ids: list[str] = []

        self._retain_and_verify(subject_set)
        for subject in subjects:
            self._retain_and_verify(subject.binding)
        for session in sessions:
            self._retain_and_verify(session.selection)

        for session in sessions:
            grouped_bundles: dict[
                tuple[str, str, str, datetime],
                tuple[HistoricalEodSession, list[HistoricalQualificationFactBundle]],
            ] = {}
            retained_selections: set[str] = set()
            session_failures = 0
            session_true = 0
            session_false = 0
            for subject in eligible:
                canonical_identity = subject.binding.canonical_identity
                if canonical_identity is None:
                    raise HistoricalOperationError(
                        HistoricalOperationFailure.INTEGRITY_INVALID
                    )
                try:
                    subject_calendar = self._calendar.for_subject(
                        canonical_identity=canonical_identity,
                        domain_008_subject_identity=subject.sponsor_label,
                    )
                    subject_session = resolve_historical_eod_sessions(
                        calendar=subject_calendar,
                        requested=(session.request,),
                        exchange=subject.exchange,
                        provenance=(
                            request.operation_identity,
                            COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY,
                            canonical_identity,
                        ),
                        require_requested_session_identity=False,
                    )[0]
                    if (
                        subject_session.selection.selection_identity
                        not in retained_selections
                    ):
                        self._retain_and_verify(subject_session.selection)
                        retained_selections.add(
                            subject_session.selection.selection_identity
                        )
                    acquisition = source.acquire(
                        subject=subject,
                        session=subject_session,
                        requested_factual_families=(
                            request.requested_factual_families
                        ),
                        source_operation_identity=request.operation_identity,
                    )
                except (HistoricalQualificationError, ValueError):
                    failures[HistoricalOperationFailure.SESSION_UNAVAILABLE.value] += 1
                    session_failures += 1
                    evidence = create_historical_failure_evidence(
                        canonical_identity=canonical_identity,
                        target_session_identity=session.request.session_identity,
                        timeframe=None,
                        expected_timestamp_count=0,
                        actual_timestamp_count=None,
                        classifications=(
                            HistoricalFailureClassification.EXPECTED_BOUNDARY_UNAVAILABLE,
                        ),
                        mismatch_ordinal=None,
                        observation_boundary=session.selection.observation_boundary,
                        diagnosed_at=self._clock(),
                        source_identity="DOMAIN-008:SUBJECT-AWARE-MARKET-SCHEDULE",
                        provider_failure_family=None,
                        provenance=(request.operation_identity,),
                    )
                    self._retain_and_verify(evidence)
                    failure_evidence_ids.append(evidence.evidence_identity)
                    continue
                except HistoricalOperationError as error:
                    failures[error.failure.value] += 1
                    session_failures += 1
                    evidence = error.evidence
                    if evidence is None and error.failure is HistoricalOperationFailure.SESSION_UNAVAILABLE:
                        evidence = create_historical_failure_evidence(
                            canonical_identity=canonical_identity,
                            target_session_identity=session.request.session_identity,
                            timeframe=None,
                            expected_timestamp_count=0,
                            actual_timestamp_count=None,
                            classifications=(
                                HistoricalFailureClassification.EXPECTED_BOUNDARY_UNAVAILABLE,
                            ),
                            mismatch_ordinal=None,
                            observation_boundary=session.selection.observation_boundary,
                            diagnosed_at=self._clock(),
                            source_identity="DOMAIN-008:SUBJECT-AWARE-MARKET-SCHEDULE",
                            provider_failure_family=None,
                            provenance=(request.operation_identity,),
                        )
                    if evidence is not None:
                        self._retain_and_verify(evidence)
                        failure_evidence_ids.append(evidence.evidence_identity)
                    continue
                for payload in acquisition.candle_payloads:
                    self._retain_semantic_and_verify(payload)
                    candle_payload_ids.append(payload.candle_identity)
                self._retain_semantic_and_verify(acquisition.semantic_evidence)
                semantic_evidence_ids.append(
                    acquisition.semantic_evidence.evidence_identity
                )
                self._retain_and_verify(acquisition.previous_session_facts)
                self._retain_and_verify(acquisition.bundle)
                group_key = (
                    subject_session.selection.target_session_identity,
                    subject_session.selection.previous_session_identity,
                    subject_session.selection.observation_boundary_identity,
                    subject_session.selection.observation_boundary,
                )
                group = grouped_bundles.setdefault(
                    group_key,
                    (subject_session, []),
                )
                group[1].append(acquisition.bundle)
                if acquisition.previous_session_facts.narrow_cpr.narrow_cpr_kgs_v0:
                    session_true += 1
                else:
                    session_false += 1

            stage_bundles = tuple(
                bundle
                for _, bundles in grouped_bundles.values()
                for bundle in bundles
            )
            for subject_session, group_bundles in grouped_bundles.values():
                stage = HistoricalOperationStage.RECONSTRUCTION
                reconstruction = create_historical_reconstruction(
                    subject_set=subject_set,
                    reconciliation_identity=self._reconciliation.publication_identity,
                    reconciliation_version=self._reconciliation.publication_version,
                    session=subject_session.selection,
                    fact_bundles=tuple(group_bundles),
                    hypothesis_versions=(
                        (
                            NARROW_CPR_CALCULATION_IDENTITY,
                            PART1_CONTRACT_VERSION,
                        ),
                    ),
                    provenance=(
                        request.operation_identity,
                        plan.plan_identity,
                    ),
                )
                eligibility = assess_historical_corpus_eligibility(reconstruction)
                self._retain_and_verify(reconstruction)
                self._retain_and_verify(eligibility)
                reconstruction_ids.append(reconstruction.reconstruction_identity)

            session_success = len(stage_bundles)
            unavailable = unavailable_count + session_failures
            accounting.append(
                HistoricalSessionOperationAccounting(
                    session_identity=session.target_schedule.session_id,
                    subject_set_count=len(subjects),
                    historically_evaluable_count=len(eligible),
                    prerequisite_unavailable_count=unavailable_count,
                    factual_success_count=session_success,
                    factual_failure_count=session_failures,
                    narrow_cpr_true_count=session_true,
                    narrow_cpr_false_count=session_false,
                    narrow_cpr_unavailable_count=unavailable,
                )
            )
            bundle_ids.extend(item.bundle_identity for item in stage_bundles)
            total_success += session_success
            total_factual_failures += session_failures
            total_true += session_true
            total_false += session_false

        result = HistoricalQualificationOperationResult(
            operation_identity=request.operation_identity,
            state=HistoricalOperationState.COMPLETE,
            stage=HistoricalOperationStage.COMPLETE,
            context_state=self._runtime.lifecycle_state.value,
            request_plan_identity=plan.plan_identity,
            subject_set_count=len(subjects),
            historically_resolvable_count=len(eligible),
            prerequisite_unavailable_count=unavailable_count,
            sessions_requested=len(request.sessions),
            sessions_valid=len(sessions),
            sessions_unavailable=0,
            subject_session_observations_planned=len(subjects) * len(sessions),
            successful_reconstructions=total_success,
            factual_failures=total_factual_failures,
            prerequisite_unavailable_observations=(
                unavailable_count * len(sessions)
            ),
            narrow_cpr_true_count=total_true,
            narrow_cpr_false_count=total_false,
            narrow_cpr_unavailable_count=(
                unavailable_count * len(sessions) + total_factual_failures
            ),
            provider_request_ceiling=request.maximum_provider_requests,
            provider_request_count=source.total_provider_request_count,
            reconstruction_identities=tuple(reconstruction_ids),
            bundle_identities=tuple(bundle_ids),
            failure_evidence_identities=tuple(failure_evidence_ids),
            session_accounting=tuple(accounting),
            observation_failure_counts=tuple(sorted(failures.items())),
            persistence_complete=True,
            reload_verified=True,
            corpus_binding_performed=False,
            production_state_mutated=False,
            failure=None,
            completed_at=self._clock(),
        )
        with self._lock:
            self._results[request.operation_identity] = result
            self._semantic_artifacts[request.operation_identity] = (
                tuple(candle_payload_ids),
                tuple(semantic_evidence_ids),
            )
        return result

    def _retain_and_verify(self, value: object) -> None:
        try:
            self._store.retain(value)
        except Exception:
            raise HistoricalOperationError(
                HistoricalOperationFailure.PERSISTENCE_FAILED
            ) from None
        try:
            document = self._store.load_document(
                artifact_type=type(value).__name__,
                artifact_identity=_artifact_identity(value),
            )
            reloaded = self._store.load(
                artifact_type=type(value).__name__,
                artifact_identity=_artifact_identity(value),
            )
        except Exception:
            raise HistoricalOperationError(
                HistoricalOperationFailure.RELOAD_FAILED
            ) from None
        if (
            reloaded != value
            or document["artifact_identity"] != _artifact_identity(value)
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.RELOAD_FAILED
            )

    def _retain_semantic_and_verify(self, value: object) -> None:
        identity = getattr(
            value,
            "candle_identity",
            getattr(value, "evidence_identity", None),
        )
        if type(identity) is not str:
            raise HistoricalOperationError(
                HistoricalOperationFailure.INTEGRITY_INVALID
            )
        try:
            self._semantic_store.retain(value)
            reloaded = self._semantic_store.load(
                artifact_type=type(value).__name__,
                artifact_identity=identity,
            )
        except Exception:
            raise HistoricalOperationError(
                HistoricalOperationFailure.PERSISTENCE_FAILED
            ) from None
        if reloaded != value:
            raise HistoricalOperationError(
                HistoricalOperationFailure.RELOAD_FAILED
            )

    def _failure(
        self,
        request: HistoricalQualificationOperationRequest,
        *,
        stage: HistoricalOperationStage,
        failure: HistoricalOperationFailure,
        subjects: tuple[HistoricalOperationalSubject, ...] = (),
        sessions: tuple[HistoricalEodSession, ...] = (),
        plan: HistoricalProviderRequestPlan | None = None,
        provider_request_count: int = 0,
    ) -> HistoricalQualificationOperationResult:
        eligible = sum(
            item.binding.availability is HistoricalBindingAvailability.AVAILABLE
            for item in subjects
        )
        result = HistoricalQualificationOperationResult(
            operation_identity=request.operation_identity,
            state=HistoricalOperationState.FAILED,
            stage=stage,
            context_state=self._runtime.lifecycle_state.value,
            request_plan_identity=None if plan is None else plan.plan_identity,
            subject_set_count=len(subjects),
            historically_resolvable_count=eligible,
            prerequisite_unavailable_count=len(subjects) - eligible,
            sessions_requested=len(request.sessions),
            sessions_valid=len(sessions),
            sessions_unavailable=len(request.sessions) - len(sessions),
            subject_session_observations_planned=(
                0 if plan is None else plan.subject_session_observations
            ),
            successful_reconstructions=0,
            factual_failures=0,
            prerequisite_unavailable_observations=0,
            narrow_cpr_true_count=0,
            narrow_cpr_false_count=0,
            narrow_cpr_unavailable_count=0,
            provider_request_ceiling=request.maximum_provider_requests,
            provider_request_count=provider_request_count,
            reconstruction_identities=(),
            bundle_identities=(),
            failure_evidence_identities=(),
            session_accounting=(),
            observation_failure_counts=(),
            persistence_complete=False,
            reload_verified=False,
            corpus_binding_performed=False,
            production_state_mutated=False,
            failure=failure,
            completed_at=self._clock(),
        )
        with self._lock:
            self._results[request.operation_identity] = result
        return result

    def _conflict(
        self, request: HistoricalQualificationOperationRequest
    ) -> HistoricalQualificationOperationResult:
        return HistoricalQualificationOperationResult(
            operation_identity=request.operation_identity,
            state=HistoricalOperationState.CONFLICT,
            stage=HistoricalOperationStage.CONTEXT_VERIFICATION,
            context_state=self._runtime.lifecycle_state.value,
            request_plan_identity=None,
            subject_set_count=0,
            historically_resolvable_count=0,
            prerequisite_unavailable_count=0,
            sessions_requested=len(request.sessions),
            sessions_valid=0,
            sessions_unavailable=0,
            subject_session_observations_planned=0,
            successful_reconstructions=0,
            factual_failures=0,
            prerequisite_unavailable_observations=0,
            narrow_cpr_true_count=0,
            narrow_cpr_false_count=0,
            narrow_cpr_unavailable_count=0,
            provider_request_ceiling=request.maximum_provider_requests,
            provider_request_count=0,
            reconstruction_identities=(),
            bundle_identities=(),
            failure_evidence_identities=(),
            session_accounting=(),
            observation_failure_counts=(),
            persistence_complete=False,
            reload_verified=False,
            corpus_binding_performed=False,
            production_state_mutated=False,
            failure=HistoricalOperationFailure.OPERATION_CONFLICT,
            completed_at=self._clock(),
        )


class IntradayHistoricalQualificationHarness:
    """Narrow non-Browser harness accepting only the governed request type."""

    def __init__(
        self, operation: IntradayHistoricalQualificationOperationService
    ) -> None:
        if type(operation) is not IntradayHistoricalQualificationOperationService:
            raise ValueError("HISTORICAL_OPERATION_HARNESS_INVALID")
        self._operation = operation

    @property
    def operation_service(self) -> IntradayHistoricalQualificationOperationService:
        """Return the exact composed service for local identity verification."""

        return self._operation

    def execute(
        self, request: HistoricalQualificationOperationRequest
    ) -> HistoricalQualificationOperationResult:
        if type(request) is not HistoricalQualificationOperationRequest:
            raise HistoricalOperationError(
                HistoricalOperationFailure.REQUEST_INVALID
            )
        return self._operation.execute(request)


def _provider_count(source: HistoricalFactualSource | None) -> int:
    return 0 if source is None else source.total_provider_request_count


def _artifact_identity(value: object) -> str:
    name = {
        "HistoricalResearchSubjectSet": "subject_set_identity",
        "HistoricalSubjectBinding": "binding_identity",
        "HistoricalSessionSelection": "selection_identity",
        "HistoricalFactualFailureEvidence": "evidence_identity",
        "HistoricalPreviousSessionFacts": "facts_identity",
        "HistoricalQualificationFactBundle": "bundle_identity",
        "HistoricalQualificationReconstruction": "reconstruction_identity",
        "HistoricalCorpusEligibility": "eligibility_identity",
    }.get(type(value).__name__)
    identity = None if name is None else getattr(value, name, None)
    if type(identity) is str:
        return identity
    raise HistoricalOperationError(HistoricalOperationFailure.INTEGRITY_INVALID)


__all__ = [
    "HISTORICAL_OPERATION_CONSUMER_IDENTITY",
    "HISTORICAL_OPERATION_LEASE_CAPABILITIES",
    "IntradayHistoricalQualificationHarness",
    "IntradayHistoricalQualificationOperationService",
]
