"""Application orchestration for TradingView intake and Slice-4 analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from typing import Callable

from kronos.swing.daily_data import SwingDailyDataset
from kronos.swing.v1.evidence_store import (
    LocalTradingViewEvidenceStore,
    StoredChartAnalysis,
    StoredChartAnalysisState,
    StoredChartRevision,
    TradingViewEvidencePackage,
)
from kronos.swing.v1.chart_evidence import (
    CHART_QUESTION_SET_V1_ID,
    ChartEvidenceProvider,
    ChartEvidenceProviderError,
    ChartEvidenceProviderFailureCode,
    ChartEvidenceRequest,
    ChartEvidenceResponse,
    ChartThesisContext,
    chart_revision,
    response_to_observations,
)
from kronos.swing.v1.chart_analyst_v2 import (
    ChartAnalystProduct,
    ChartAnalystV2Error,
    ChartAnalystV2FailureCode,
    ChartAnalystV2Provider,
    ChartAnalystV2Request,
    ChartAnalystV2Response,
    ChartAnalystV2Thesis,
)
from kronos.swing.v1.chart_analyst_v2_layer2 import (
    CHART_ANALYST_V2_OPERATIONAL_AUTHORITY,
    ChartAnalystV2Layer2Record,
    ChartAnalystV2Layer2State,
    integrate_chart_analyst_v2_layer2,
)
from kronos.swing.v1.chart_analyst_v2_integrity import (
    ChartAnalystV2OutputIntegrityError,
)
from kronos.swing.v1.layer1 import analyze_v1_layer1
from kronos.swing.v1.layer2 import (
    ReadinessAssessment,
    ReadinessState,
    build_layer2_review_record,
    context_incomplete_readiness,
    extract_tradingview_evidence,
)
from kronos.swing.v1.models import ProbableClassification, V1Layer1Assessment, V1Layer1Run
from kronos.swing.v1.tradingview import (
    ChartTimeframe,
    TradingViewContextPolicy,
    TradingViewReviewRequirement,
    build_tradingview_review_requirements,
)
from kronos.swing.run_identity import (
    LEGACY_UNBOUND_SWING_RUN_ID,
    is_swing_analysis_run_id,
    is_swing_run_binding,
)


class V1ReviewRunState(StrEnum):
    NOT_RUN = "NOT_RUN"
    TRADINGVIEW_REVIEW_REQUIRED = "TRADINGVIEW_REVIEW_REQUIRED"
    NO_TRADINGVIEW_REVIEW_REQUIRED = "NO_TRADINGVIEW_REVIEW_REQUIRED"


class ChartAnalysisState(StrEnum):
    CHARTS_REQUIRED = "CHARTS_REQUIRED"
    READY_TO_ANALYZE = "READY_TO_ANALYZE"
    ANALYZING_CHART_CONTEXT = "ANALYZING_CHART_CONTEXT"
    ANALYSIS_COMPLETE = "ANALYSIS_COMPLETE"
    CHART_ANALYSIS_UNAVAILABLE = "CHART_ANALYSIS_UNAVAILABLE"
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"


class V1BatchPreflightFailure(StrEnum):
    OPENAI_NOT_CONNECTED = "OPENAI NOT CONNECTED"
    CHART_ANALYST_V2_DISABLED = "CHART ANALYST V2 DISABLED"
    MODEL_NOT_SUPPORTED = "CHART ANALYST V2 MODEL NOT SUPPORTED"
    QUESTION_SET_UNAVAILABLE = "CHART ANALYST V2 QUESTION SET UNAVAILABLE"
    RUN_BINDING_INVALID = "CHART ANALYST V2 RUN BINDING INVALID"


@dataclass(frozen=True, slots=True)
class InstrumentChartAnalysisSnapshot:
    canonical_instrument: str
    state: ChartAnalysisState
    readiness: ReadinessAssessment | None
    provider_identity: str | None
    response_count: int
    failure_code: ChartEvidenceProviderFailureCode | ChartAnalystV2FailureCode | None
    v2_evidence: ChartAnalystV2Response | None = None
    v2_layer2: ChartAnalystV2Layer2Record | None = None

    def __post_init__(self) -> None:
        if (
            not self.canonical_instrument
            or type(self.state) is not ChartAnalysisState
            or (self.readiness is not None and type(self.readiness) is not ReadinessAssessment)
            or type(self.response_count) is not int
            or self.response_count < 0
            or (
                self.failure_code is not None
                and type(self.failure_code)
                not in {ChartEvidenceProviderFailureCode, ChartAnalystV2FailureCode}
            )
            or (
                self.v2_evidence is not None
                and type(self.v2_evidence) is not ChartAnalystV2Response
            )
            or (
                self.v2_layer2 is not None
                and type(self.v2_layer2) is not ChartAnalystV2Layer2Record
            )
            or (
                self.v2_layer2 is not None
                and (
                    self.v2_evidence != self.v2_layer2.response
                    or self.readiness != self.v2_layer2.readiness
                )
            )
            or (
                self.state is ChartAnalysisState.ANALYSIS_COMPLETE
                and (
                    (self.readiness is None and self.v2_evidence is None)
                    or self.failure_code is not None
                )
            )
            or (
                self.state in {
                    ChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE,
                    ChartAnalysisState.CONTEXT_INCOMPLETE,
                }
                and self.failure_code is None
            )
        ):
            raise ValueError("V1_INSTRUMENT_CHART_ANALYSIS_SNAPSHOT_INVALID")


STEP31_V1_HANDOFF_SCHEMA_ID = "KRONOS_SWING_V1_STEP31_ELIGIBILITY_HANDOFF_V1"


@dataclass(frozen=True, slots=True)
class Step31EligibleInstrument:
    canonical_instrument: str
    layer1_run_identity: str
    swing_analysis_run_identity: str
    observation_boundary: datetime
    probable_assessment_identities: tuple[str, ...]
    source_image_sha256: str
    readiness_state: ReadinessState
    readiness_policy_identity: str
    readiness_reason: str

    def __post_init__(self) -> None:
        if (
            not self.canonical_instrument
            or not self.layer1_run_identity
            or not is_swing_analysis_run_id(self.swing_analysis_run_identity)
            or self.observation_boundary.tzinfo is None
            or self.observation_boundary.utcoffset() is None
            or not self.probable_assessment_identities
            or len(self.source_image_sha256) != 64
            or self.readiness_state
            is not ReadinessState.READY_FOR_TRADE_CONSTRUCTION
            or not self.readiness_policy_identity
            or not self.readiness_reason
        ):
            raise ValueError("V1_STEP31_ELIGIBLE_INSTRUMENT_INVALID")


@dataclass(frozen=True, slots=True)
class Step31EligibilityHandoff:
    swing_analysis_run_identity: str
    layer1_run_identity: str
    eligible_instruments: tuple[Step31EligibleInstrument, ...]
    schema_identity: str = STEP31_V1_HANDOFF_SCHEMA_ID
    operational_authority: str = CHART_ANALYST_V2_OPERATIONAL_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not is_swing_analysis_run_id(self.swing_analysis_run_identity)
            or not self.layer1_run_identity
            or type(self.eligible_instruments) is not tuple
            or any(
                type(item) is not Step31EligibleInstrument
                or item.swing_analysis_run_identity
                != self.swing_analysis_run_identity
                or item.layer1_run_identity != self.layer1_run_identity
                for item in self.eligible_instruments
            )
            or len({item.canonical_instrument for item in self.eligible_instruments})
            != len(self.eligible_instruments)
            or self.schema_identity != STEP31_V1_HANDOFF_SCHEMA_ID
            or self.operational_authority
            != CHART_ANALYST_V2_OPERATIONAL_AUTHORITY
        ):
            raise ValueError("V1_STEP31_ELIGIBILITY_HANDOFF_INVALID")


@dataclass(frozen=True, slots=True)
class V1ReviewWorkflowSnapshot:
    run_state: V1ReviewRunState
    layer1_run: V1Layer1Run | None
    requirements: tuple[TradingViewReviewRequirement, ...]
    packages: tuple[TradingViewEvidencePackage, ...]
    analyses: tuple[InstrumentChartAnalysisSnapshot, ...]
    swing_analysis_run_identity: str | None = None
    batch_preflight_failure: V1BatchPreflightFailure | None = None

    def __post_init__(self) -> None:
        if (
            type(self.run_state) is not V1ReviewRunState
            or (
                self.batch_preflight_failure is not None
                and type(self.batch_preflight_failure) is not V1BatchPreflightFailure
            )
            or (
                self.swing_analysis_run_identity is not None
                and not is_swing_run_binding(self.swing_analysis_run_identity)
            )
            or type(self.requirements) is not tuple
            or type(self.packages) is not tuple
            or len(self.requirements) != len(self.packages)
            or len(self.requirements) != len(self.analyses)
            or len({item.canonical_instrument for item in self.requirements})
            != len(self.requirements)
            or any(
                package.requirement is not requirement
                for requirement, package in zip(self.requirements, self.packages, strict=True)
            )
            or (
                self.run_state is V1ReviewRunState.NOT_RUN
                and (
                    self.layer1_run is not None
                    or self.requirements
                    or self.packages
                    or self.swing_analysis_run_identity is not None
                )
            )
            or (
                self.run_state is V1ReviewRunState.NO_TRADINGVIEW_REVIEW_REQUIRED
                and (
                    self.layer1_run is None
                    or self.requirements
                    or self.packages
                    or self.analyses
                    or self.swing_analysis_run_identity is None
                )
            )
            or (
                self.run_state is V1ReviewRunState.TRADINGVIEW_REVIEW_REQUIRED
                and (
                    self.layer1_run is None
                    or not self.requirements
                    or self.swing_analysis_run_identity is None
                    or any(
                        item.swing_analysis_run_identity
                        != self.swing_analysis_run_identity
                        for item in self.requirements
                    )
                )
            )
        ):
            raise ValueError("V1_REVIEW_WORKFLOW_SNAPSHOT_INVALID")

    def requirement_for(self, instrument: str) -> TradingViewReviewRequirement | None:
        return next(
            (item for item in self.requirements if item.canonical_instrument == instrument),
            None,
        )

    def analysis_for(self, instrument: str) -> InstrumentChartAnalysisSnapshot | None:
        return next(
            (item for item in self.analyses if item.canonical_instrument == instrument),
            None,
        )

    @property
    def all_required_charts_present(self) -> bool:
        return bool(self.requirements) and all(
            not package.missing_required_timeframes for package in self.packages
        )


class SwingV1ReviewWorkflow:
    """Own the latest Layer-1 run and its durable instrument-level chart packages."""

    def __init__(
        self,
        store: LocalTradingViewEvidenceStore,
        *,
        context_policy: TradingViewContextPolicy = TradingViewContextPolicy(),
        chart_evidence_provider: ChartEvidenceProvider | None = None,
        chart_analyst_v2_provider: ChartAnalystV2Provider | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            type(store) is not LocalTradingViewEvidenceStore
            or type(context_policy) is not TradingViewContextPolicy
            or (
                chart_evidence_provider is not None
                and not isinstance(chart_evidence_provider, ChartEvidenceProvider)
            )
            or (
                chart_analyst_v2_provider is not None
                and not isinstance(chart_analyst_v2_provider, ChartAnalystV2Provider)
            )
            or (
                chart_evidence_provider is not None
                and chart_analyst_v2_provider is not None
            )
            or not callable(clock)
        ):
            raise TypeError("V1_REVIEW_WORKFLOW_DEPENDENCY_INVALID")
        self._store = store
        self._context_policy = context_policy
        self._chart_evidence_provider = chart_evidence_provider
        self._chart_analyst_v2_provider = chart_analyst_v2_provider
        self._clock = clock
        self._lock = RLock()
        self._run: V1Layer1Run | None = None
        self._swing_analysis_run_identity: str | None = None
        self._requirements: tuple[TradingViewReviewRequirement, ...] = ()
        self._inflight: set[str] = set()
        self._v2_failures: dict[
            tuple[str, str], ChartAnalystV2FailureCode
        ] = {}
        self._v2_completed: dict[tuple[str, str], ChartAnalystV2Response] = {}
        self._batch_preflight_failure: V1BatchPreflightFailure | None = None

    @property
    def evidence_root(self):  # type: ignore[no-untyped-def]
        return self._store.root

    def run_layer1(
        self,
        dataset: SwingDailyDataset,
        *,
        swing_analysis_run_identity: str = LEGACY_UNBOUND_SWING_RUN_ID,
    ) -> V1ReviewWorkflowSnapshot:
        if type(dataset) is not SwingDailyDataset:
            raise ValueError("V1_REVIEW_DATASET_INVALID")
        return self.publish_layer1(
            analyze_v1_layer1(dataset),
            swing_analysis_run_identity=swing_analysis_run_identity,
        )

    def prepare_layer1(
        self,
        dataset: SwingDailyDataset,
        *,
        swing_analysis_run_identity: str,
    ) -> V1ReviewWorkflowSnapshot:
        """Prepare once, preserving any matching pre-fix evidence as legacy."""

        if not is_swing_analysis_run_id(swing_analysis_run_identity):
            raise ValueError("V1_REVIEW_PARENT_RUN_INVALID")
        return self.prepare_layer1_run(
            analyze_v1_layer1(dataset),
            swing_analysis_run_identity=swing_analysis_run_identity,
        )

    def prepare_layer1_run(
        self,
        run: V1Layer1Run,
        *,
        swing_analysis_run_identity: str,
    ) -> V1ReviewWorkflowSnapshot:
        if type(run) is not V1Layer1Run:
            raise ValueError("V1_REVIEW_RUN_BINDING_INVALID")
        legacy_requirements = build_tradingview_review_requirements(
            run,
            context_policy=self._context_policy,
            swing_analysis_run_identity=LEGACY_UNBOUND_SWING_RUN_ID,
        )
        binding = (
            LEGACY_UNBOUND_SWING_RUN_ID
            if self._store.has_legacy_evidence(legacy_requirements)
            else swing_analysis_run_identity
        )
        return self.publish_layer1(
            run,
            swing_analysis_run_identity=binding,
        )

    def load_latest_dataset(
        self,
        dataset: SwingDailyDataset,
        *,
        swing_analysis_run_identity: str,
    ) -> V1ReviewWorkflowSnapshot:
        if type(dataset) is not SwingDailyDataset:
            raise ValueError("V1_REVIEW_DATASET_INVALID")
        return self.load_latest_layer1(
            analyze_v1_layer1(dataset),
            swing_analysis_run_identity=swing_analysis_run_identity,
        )

    def publish_layer1(
        self,
        run: V1Layer1Run,
        *,
        swing_analysis_run_identity: str = LEGACY_UNBOUND_SWING_RUN_ID,
    ) -> V1ReviewWorkflowSnapshot:
        return self._publish_layer1(
            run,
            swing_analysis_run_identity=swing_analysis_run_identity,
            replace_existing=False,
        )

    def load_latest_layer1(
        self,
        run: V1Layer1Run,
        *,
        swing_analysis_run_identity: str,
    ) -> V1ReviewWorkflowSnapshot:
        """Explicitly move the operator surface to a newer parent run."""

        if not is_swing_analysis_run_id(swing_analysis_run_identity):
            raise ValueError("V1_REVIEW_PARENT_RUN_INVALID")
        return self._publish_layer1(
            run,
            swing_analysis_run_identity=swing_analysis_run_identity,
            replace_existing=True,
        )

    def _publish_layer1(
        self,
        run: V1Layer1Run,
        *,
        swing_analysis_run_identity: str,
        replace_existing: bool,
    ) -> V1ReviewWorkflowSnapshot:
        if type(run) is not V1Layer1Run or not is_swing_run_binding(
            swing_analysis_run_identity
        ):
            raise ValueError("V1_REVIEW_RUN_BINDING_INVALID")
        requirements = build_tradingview_review_requirements(
            run,
            context_policy=self._context_policy,
            swing_analysis_run_identity=swing_analysis_run_identity,
        )
        with self._lock:
            if self._run is not None and not replace_existing:
                if (
                    self._swing_analysis_run_identity
                    != swing_analysis_run_identity
                    or self._run != run
                ):
                    raise ValueError("V1_REVIEW_IMMUTABLE_RUN")
                return self._snapshot_unlocked()
            if is_swing_analysis_run_id(swing_analysis_run_identity):
                self._store.retain_review_run(
                    run,
                    swing_analysis_run_identity=swing_analysis_run_identity,
                )
            self._run = run
            self._swing_analysis_run_identity = swing_analysis_run_identity
            self._requirements = requirements
            self._inflight.clear()
            self._v2_failures.clear()
            self._v2_completed.clear()
            self._batch_preflight_failure = None
            return self._snapshot_unlocked()

    def snapshot(self) -> V1ReviewWorkflowSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def step31_eligibility_handoff(self) -> Step31EligibilityHandoff:
        """Project only governed V1-ready instruments; construct no trade geometry."""

        with self._lock:
            if (
                self._run is None
                or not is_swing_analysis_run_id(
                    self._swing_analysis_run_identity or ""
                )
            ):
                raise ValueError("V1_STEP31_HANDOFF_RUN_UNAVAILABLE")
            snapshot = self._snapshot_unlocked()
            eligible: list[Step31EligibleInstrument] = []
            for requirement, package, analysis in zip(
                snapshot.requirements,
                snapshot.packages,
                snapshot.analyses,
                strict=True,
            ):
                layer2 = analysis.v2_layer2
                if (
                    layer2 is None
                    or layer2.state is not ChartAnalystV2Layer2State.SHADOW_COMPLETE
                    or analysis.readiness is None
                    or analysis.readiness.state
                    is not ReadinessState.READY_FOR_TRADE_CONSTRUCTION
                    or len(package.active_revisions) != 1
                ):
                    continue
                eligible.append(Step31EligibleInstrument(
                    canonical_instrument=requirement.canonical_instrument,
                    layer1_run_identity=requirement.run_identity,
                    swing_analysis_run_identity=(
                        requirement.swing_analysis_run_identity
                    ),
                    observation_boundary=requirement.observation_boundary,
                    probable_assessment_identities=(
                        analysis.readiness.probable_assessment_identities
                    ),
                    source_image_sha256=package.active_revisions[0].sha256,
                    readiness_state=analysis.readiness.state,
                    readiness_policy_identity=analysis.readiness.policy_identity,
                    readiness_reason=analysis.readiness.primary_reason,
                ))
            return Step31EligibilityHandoff(
                swing_analysis_run_identity=self._swing_analysis_run_identity,
                layer1_run_identity=self._run.run_identity,
                eligible_instruments=tuple(eligible),
            )

    def upload(
        self,
        *,
        instrument: str,
        timeframe: ChartTimeframe,
        content_type: str,
        original_bytes: bytes,
    ) -> StoredChartRevision:
        with self._lock:
            self._batch_preflight_failure = None
            requirement = next(
                (
                    item
                    for item in self._requirements
                    if item.canonical_instrument == instrument
                ),
                None,
            )
            if requirement is None:
                raise ValueError("TRADINGVIEW_INSTRUMENT_NOT_REQUESTED")
            return self._store.retain_upload(
                requirement,
                selected_instrument=instrument,
                selected_timeframe=timeframe,
                content_type=content_type,
                original_bytes=original_bytes,
            )

    def remove_chart(
        self,
        *,
        instrument: str,
        timeframe: ChartTimeframe,
    ) -> None:
        with self._lock:
            self._batch_preflight_failure = None
            requirement = self._requirement_for(instrument)
            self._store.remove_active_chart(
                requirement,
                selected_instrument=instrument,
                selected_timeframe=timeframe,
            )

    def active_chart(
        self,
        *,
        instrument: str,
        timeframe: ChartTimeframe,
        sha256: str,
    ) -> tuple[StoredChartRevision, bytes]:
        """Return only the currently bound revision for a strict preview request."""

        with self._lock:
            requirement = self._requirement_for(instrument)
            package = self._store.package_for(requirement)
            revision = next(
                (
                    item
                    for item in package.active_revisions
                    if item.timeframe is timeframe and item.sha256 == sha256
                ),
                None,
            )
            if revision is None:
                raise ValueError("TRADINGVIEW_ACTIVE_CHART_BINDING_INVALID")
            return revision, self._store.original_bytes(revision)

    def analyze_all_chart_context(self) -> V1ReviewWorkflowSnapshot:
        """Analyze the complete current intake set from one fail-closed action."""

        with self._lock:
            if self._run is None or not self._requirements:
                raise ValueError("TRADINGVIEW_REVIEW_NOT_AVAILABLE")
            run = self._run
            instruments = tuple(
                item.canonical_instrument for item in self._requirements
            )
            if any(
                self._store.package_for(item).missing_required_timeframes
                for item in self._requirements
            ):
                raise ValueError("TRADINGVIEW_REQUIRED_CHARTS_MISSING")
        for instrument in instruments:
            self.analyze_chart_context(instrument)
        with self._lock:
            if self._run is not run:
                raise ValueError("V1_CHART_ANALYSIS_RUN_SUPERSEDED")
            return self._snapshot_unlocked()

    @property
    def uses_chart_analyst_v2(self) -> bool:
        return self._chart_analyst_v2_provider is not None

    @property
    def chart_analyst_v2_configuration_ready(self) -> bool:
        if self._chart_analyst_v2_provider is None:
            return False
        return getattr(
            self._chart_analyst_v2_provider,
            "configuration_ready",
            True,
        ) is True

    @property
    def chart_analyst_v2_model_configured(self) -> bool:
        return (
            self._chart_analyst_v2_provider is not None
            and getattr(
                self._chart_analyst_v2_provider,
                "model_configured",
                True,
            ) is True
        )

    @property
    def chart_analyst_v2_question_set_available(self) -> bool:
        return (
            self._chart_analyst_v2_provider is not None
            and getattr(
                self._chart_analyst_v2_provider,
                "question_set_available",
                True,
            ) is True
        )

    def record_batch_preflight_failure(
        self,
        failure: V1BatchPreflightFailure,
    ) -> V1ReviewWorkflowSnapshot:
        if type(failure) is not V1BatchPreflightFailure:
            raise TypeError("V1_BATCH_PREFLIGHT_FAILURE_INVALID")
        with self._lock:
            self._batch_preflight_failure = failure
            return self._snapshot_unlocked()

    def clear_batch_preflight_failure(self) -> V1ReviewWorkflowSnapshot:
        with self._lock:
            self._batch_preflight_failure = None
            return self._snapshot_unlocked()

    def chart_analyst_v2_run_binding_valid(self) -> bool:
        """Validate the whole immutable run/image set without provider activity."""

        with self._lock:
            if (
                self._chart_analyst_v2_provider is None
                or self._run is None
                or not self._requirements
                or not is_swing_analysis_run_id(self._swing_analysis_run_identity or "")
            ):
                return False
            for requirement in self._requirements:
                package = self._store.package_for(requirement)
                assessments = _probable_assessments(
                    self._run,
                    requirement.canonical_instrument,
                )
                if (
                    requirement.run_identity != self._run.run_identity
                    or requirement.swing_analysis_run_identity
                    != self._swing_analysis_run_identity
                    or package.missing_required_timeframes
                    or len(package.active_revisions) != 1
                    or not assessments
                    or any(
                        revision.run_identity != requirement.run_identity
                        or revision.swing_analysis_run_identity
                        != requirement.swing_analysis_run_identity
                        or revision.canonical_instrument
                        != requirement.canonical_instrument
                        for revision in package.active_revisions
                    )
                    or any(
                        assessment.canonical_identity
                        != requirement.canonical_instrument
                        or assessment.observation_boundary
                        != requirement.observation_boundary
                        for assessment in assessments
                    )
                ):
                    return False
            return True

    def chart_analyst_v2_instrument_binding_valid(self, instrument: str) -> bool:
        """Validate exactly one selected run/image binding without provider activity."""

        if not instrument:
            return False
        with self._lock:
            if (
                self._chart_analyst_v2_provider is None
                or self._run is None
                or not is_swing_analysis_run_id(self._swing_analysis_run_identity or "")
            ):
                return False
            requirement = next(
                (
                    item
                    for item in self._requirements
                    if item.canonical_instrument == instrument
                ),
                None,
            )
            if requirement is None:
                return False
            package = self._store.package_for(requirement)
            assessments = _probable_assessments(self._run, instrument)
            return not (
                requirement.run_identity != self._run.run_identity
                or requirement.swing_analysis_run_identity
                != self._swing_analysis_run_identity
                or package.missing_required_timeframes
                or len(package.active_revisions) != 1
                or not assessments
                or any(
                    revision.run_identity != requirement.run_identity
                    or revision.swing_analysis_run_identity
                    != requirement.swing_analysis_run_identity
                    or revision.canonical_instrument != instrument
                    for revision in package.active_revisions
                )
                or any(
                    assessment.canonical_identity != instrument
                    or assessment.observation_boundary
                    != requirement.observation_boundary
                    for assessment in assessments
                )
            )

    def analyze_chart_context(
        self,
        instrument: str,
        *,
        force: bool = False,
    ) -> InstrumentChartAnalysisSnapshot:
        """Run exactly one explicit bounded provider analysis for each latest chart."""

        if type(force) is not bool:
            raise TypeError("V1_CHART_ANALYSIS_FORCE_INVALID")
        with self._lock:
            requirement = next(
                (item for item in self._requirements if item.canonical_instrument == instrument),
                None,
            )
            if requirement is None or self._run is None:
                raise ValueError("TRADINGVIEW_INSTRUMENT_NOT_REQUESTED")
            package = self._store.package_for(requirement)
            if package.missing_required_timeframes:
                raise ValueError("TRADINGVIEW_REQUIRED_CHARTS_MISSING")
            retained = self._analysis_snapshot(requirement, package)
            if (
                not force
                and retained.state is ChartAnalysisState.ANALYSIS_COMPLETE
            ):
                return retained
            latest = package.active_revisions
            assessments = _probable_assessments(self._run, instrument)
            if not assessments:
                raise ValueError("V1_LAYER2_ASSESSMENT_BINDING_INVALID")
            run = self._run
            self._inflight.add(instrument)
            provider = self._chart_evidence_provider
            v2_provider = self._chart_analyst_v2_provider
            request_count_before = _provider_request_count(provider)

        if v2_provider is not None:
            return self._analyze_chart_analyst_v2(
                requirement=requirement,
                revisions=latest,
                assessments=assessments,
                run=run,
                provider=v2_provider,
            )

        responses: list[ChartEvidenceResponse] = []
        try:
            if provider is None:
                raise ChartEvidenceProviderError(
                    ChartEvidenceProviderFailureCode.UNAVAILABLE
                )
            thesis = _thesis_context(assessments[0])
            for revision in latest:
                request_timestamp = self._clock()
                if (
                    not isinstance(request_timestamp, datetime)
                    or request_timestamp.tzinfo is None
                    or request_timestamp.utcoffset() is None
                ):
                    raise ValueError("V1_CHART_ANALYSIS_CLOCK_INVALID")
                request = ChartEvidenceRequest(
                    run_identity=requirement.run_identity,
                    canonical_instrument=requirement.canonical_instrument,
                    timeframe=revision.timeframe,
                    observation_boundary=requirement.observation_boundary,
                    chart_template_identity=requirement.chart_template_identity,
                    question_set_identity=CHART_QUESTION_SET_V1_ID,
                    request_timestamp=request_timestamp,
                    source_image_sha256=revision.sha256,
                    content_type=revision.content_type,
                    original_image=self._store.original_bytes(revision),
                    thesis_context=thesis,
                )
                responses.append(provider.analyze(request))
            observations = tuple(
                observation
                for response in responses
                for observation in response_to_observations(response)
            )
            extracted = extract_tradingview_evidence(
                requirement,
                tuple(chart_revision(item) for item in responses),
                observations,
                template_identity=requirement.chart_template_identity,
            )
            if extracted.evidence is None:
                raise ChartEvidenceProviderError(
                    ChartEvidenceProviderFailureCode.LOW_CONFIDENCE
                )
            record = build_layer2_review_record(
                requirement,
                assessments,
                extracted.evidence,
            )
            retained = StoredChartAnalysis(
                StoredChartAnalysisState.COMPLETE,
                tuple(item.sha256 for item in latest),
                _request_count_delta(provider, request_count_before, len(responses)),
                tuple(responses),
                record,
                None,
            )
        except ChartEvidenceProviderError as error:
            state = (
                StoredChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE
                if error.code in {
                    ChartEvidenceProviderFailureCode.DISABLED,
                    ChartEvidenceProviderFailureCode.UNAVAILABLE,
                    ChartEvidenceProviderFailureCode.TIMEOUT,
                }
                else StoredChartAnalysisState.CONTEXT_INCOMPLETE
            )
            retained = StoredChartAnalysis(
                state,
                tuple(item.sha256 for item in latest),
                _request_count_delta(provider, request_count_before, len(responses)),
                tuple(responses),
                None,
                error.code,
            )
        finally:
            with self._lock:
                self._inflight.discard(instrument)

        with self._lock:
            if self._run is not run:
                raise ValueError("V1_CHART_ANALYSIS_RUN_SUPERSEDED")
            self._store.retain_chart_analysis(requirement, retained)
            package = self._store.package_for(requirement)
            return self._analysis_snapshot(requirement, package)

    def _analyze_chart_analyst_v2(
        self,
        *,
        requirement: TradingViewReviewRequirement,
        revisions: tuple[StoredChartRevision, ...],
        assessments: tuple[V1Layer1Assessment, ...],
        run: V1Layer1Run,
        provider: ChartAnalystV2Provider,
    ) -> InstrumentChartAnalysisSnapshot:
        """Retain V2 evidence and replay the shadow-only 4F KRONOS chain."""

        if len(revisions) != 1:
            with self._lock:
                self._inflight.discard(requirement.canonical_instrument)
            raise ValueError("CHART_ANALYST_V2_ONE_SCREENSHOT_REQUIRED")
        revision = revisions[0]
        if (
            not is_swing_analysis_run_id(
                requirement.swing_analysis_run_identity
            )
            or revision.swing_analysis_run_identity
            != requirement.swing_analysis_run_identity
            or requirement.run_identity != run.run_identity
            or self._swing_analysis_run_identity
            != requirement.swing_analysis_run_identity
            or not assessments
            or any(
                assessment.canonical_identity
                != requirement.canonical_instrument
                or assessment.observation_boundary
                != requirement.observation_boundary
                for assessment in assessments
            )
        ):
            with self._lock:
                self._inflight.discard(requirement.canonical_instrument)
            raise ValueError("CHART_ANALYST_V2_RUN_BINDING_INVALID")
        try:
            request_timestamp = self._clock()
            if (
                not isinstance(request_timestamp, datetime)
                or request_timestamp.tzinfo is None
                or request_timestamp.utcoffset() is None
            ):
                raise ValueError("V1_CHART_ANALYSIS_CLOCK_INVALID")
            assessment = assessments[0]
            request = ChartAnalystV2Request(
                run_identity=requirement.run_identity,
                swing_analysis_run_identity=(
                    requirement.swing_analysis_run_identity
                ),
                instrument=requirement.canonical_instrument,
                product=(
                    ChartAnalystProduct.MCX
                    if assessment.asset_class.value == "MCX_COMMODITY"
                    else ChartAnalystProduct.NSE
                ),
                observation_boundary=requirement.observation_boundary,
                request_timestamp=request_timestamp,
                image_sha256=revision.sha256,
                content_type=revision.content_type,
                original_image=self._store.original_bytes(revision),
                thesis=ChartAnalystV2Thesis(
                    direction=assessment.direction,
                    setup=assessment.setup.value,
                ),
            )
            response = provider.analyze(request)
            response.validate_binding(request)
            layer2 = integrate_chart_analyst_v2_layer2(
                requirement,
                assessments,
                response,
                source_image_sha256=revision.sha256,
            )
            self._store.retain_chart_analyst_v2_layer2(requirement, layer2)
            with self._lock:
                self._v2_failures.pop(
                    (requirement.canonical_instrument, revision.sha256),
                    None,
                )
                self._v2_completed[
                    (requirement.canonical_instrument, revision.sha256)
                ] = response
        except ChartAnalystV2Error as error:
            with self._lock:
                self._v2_failures[
                    (requirement.canonical_instrument, revision.sha256)
                ] = error.code
        except ChartAnalystV2OutputIntegrityError:
            with self._lock:
                self._v2_failures[
                    (requirement.canonical_instrument, revision.sha256)
                ] = ChartAnalystV2FailureCode.INVALID_SCHEMA
        except ValueError as error:
            failure = (
                ChartAnalystV2FailureCode.IDENTITY_MISMATCH
                if any(
                    marker in str(error)
                    for marker in ("BINDING", "IDENTITY", "RUN_SUPERSEDED")
                )
                else ChartAnalystV2FailureCode.INVALID_SCHEMA
            )
            with self._lock:
                self._v2_failures[
                    (requirement.canonical_instrument, revision.sha256)
                ] = failure
        finally:
            with self._lock:
                self._inflight.discard(requirement.canonical_instrument)
        with self._lock:
            if self._run is not run:
                raise ValueError("V1_CHART_ANALYSIS_RUN_SUPERSEDED")
            return self._analysis_snapshot(
                requirement,
                self._store.package_for(requirement),
            )

    def _snapshot_unlocked(self) -> V1ReviewWorkflowSnapshot:
        if self._run is None:
            return V1ReviewWorkflowSnapshot(
                V1ReviewRunState.NOT_RUN,
                None,
                (),
                (),
                (),
                None,
                self._batch_preflight_failure,
            )
        packages = tuple(self._store.package_for(item) for item in self._requirements)
        analyses = tuple(
            self._analysis_snapshot(requirement, package)
            for requirement, package in zip(self._requirements, packages, strict=True)
        )
        return V1ReviewWorkflowSnapshot(
            (
                V1ReviewRunState.TRADINGVIEW_REVIEW_REQUIRED
                if self._requirements
                else V1ReviewRunState.NO_TRADINGVIEW_REVIEW_REQUIRED
            ),
            self._run,
            self._requirements,
            packages,
            analyses,
            self._swing_analysis_run_identity,
            self._batch_preflight_failure,
        )

    def _analysis_snapshot(
        self,
        requirement: TradingViewReviewRequirement,
        package: TradingViewEvidencePackage,
    ) -> InstrumentChartAnalysisSnapshot:
        if requirement.canonical_instrument in self._inflight:
            return InstrumentChartAnalysisSnapshot(
                requirement.canonical_instrument,
                ChartAnalysisState.ANALYZING_CHART_CONTEXT,
                None,
                (
                    self._chart_analyst_v2_provider.provider_identity
                    if self._chart_analyst_v2_provider is not None
                    else self._chart_evidence_provider.provider_identity
                    if self._chart_evidence_provider is not None
                    else None
                ),
                0,
                None,
            )
        if package.missing_required_timeframes:
            return InstrumentChartAnalysisSnapshot(
                requirement.canonical_instrument,
                ChartAnalysisState.CHARTS_REQUIRED,
                None,
                None,
                0,
                None,
            )
        if self._chart_analyst_v2_provider is not None:
            return self._v2_analysis_snapshot(requirement, package)
        stored = self._store.chart_analysis_for(requirement)
        latest_hashes = {item.sha256 for item in package.active_revisions}
        if stored is None or set(stored.source_image_hashes) != latest_hashes:
            return InstrumentChartAnalysisSnapshot(
                requirement.canonical_instrument,
                ChartAnalysisState.READY_TO_ANALYZE,
                None,
                None,
                0,
                None,
            )
        provider_identity = stored.responses[0].provider_identity if stored.responses else None
        if stored.state is StoredChartAnalysisState.COMPLETE:
            assert stored.layer2_record is not None
            return InstrumentChartAnalysisSnapshot(
                requirement.canonical_instrument,
                ChartAnalysisState.ANALYSIS_COMPLETE,
                stored.layer2_record.readiness,
                provider_identity,
                len(stored.responses),
                None,
            )
        assert stored.failure_code is not None
        return InstrumentChartAnalysisSnapshot(
            requirement.canonical_instrument,
            (
                ChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE
                if stored.state is StoredChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE
                else ChartAnalysisState.CONTEXT_INCOMPLETE
            ),
            context_incomplete_readiness(
                requirement,
                (stored.failure_code.value,),
            ),
            provider_identity,
            len(stored.responses),
            stored.failure_code,
        )

    def _v2_analysis_snapshot(
        self,
        requirement: TradingViewReviewRequirement,
        package: TradingViewEvidencePackage,
    ) -> InstrumentChartAnalysisSnapshot:
        if len(package.active_revisions) != 1:
            return InstrumentChartAnalysisSnapshot(
                requirement.canonical_instrument,
                ChartAnalysisState.CONTEXT_INCOMPLETE,
                None,
                self._chart_analyst_v2_provider.provider_identity,
                0,
                ChartAnalystV2FailureCode.INVALID_SCHEMA,
            )
        revision = package.active_revisions[0]
        layer2 = self._store.chart_analyst_v2_layer2_for(requirement)
        if layer2 is not None:
            return self._v2_layer2_snapshot(requirement, layer2)
        failure = self._v2_failures.get(
            (requirement.canonical_instrument, revision.sha256)
        )
        if failure is not None:
            return InstrumentChartAnalysisSnapshot(
                requirement.canonical_instrument,
                (
                    ChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE
                    if failure in {
                        ChartAnalystV2FailureCode.DISABLED,
                        ChartAnalystV2FailureCode.UNAVAILABLE,
                        ChartAnalystV2FailureCode.TIMEOUT,
                    }
                    else ChartAnalysisState.CONTEXT_INCOMPLETE
                ),
                None,
                self._chart_analyst_v2_provider.provider_identity,
                0,
                failure,
            )
        retained = getattr(self._chart_analyst_v2_provider, "retained_response", None)
        response = self._v2_completed.get(
            (requirement.canonical_instrument, revision.sha256)
        )
        if response is None and callable(retained):
            response = retained(
                run_identity=requirement.run_identity,
                swing_analysis_run_identity=(
                    requirement.swing_analysis_run_identity
                ),
                instrument=requirement.canonical_instrument,
                image_sha256=revision.sha256,
            )
        if response is not None:
            assessments = _probable_assessments(
                self._run,
                requirement.canonical_instrument,
            ) if self._run is not None else ()
            if assessments:
                layer2 = integrate_chart_analyst_v2_layer2(
                    requirement,
                    assessments,
                    response,
                    source_image_sha256=revision.sha256,
                )
                self._store.retain_chart_analyst_v2_layer2(requirement, layer2)
                return self._v2_layer2_snapshot(requirement, layer2)
        if response is None:
            return InstrumentChartAnalysisSnapshot(
                requirement.canonical_instrument,
                ChartAnalysisState.READY_TO_ANALYZE,
                None,
                None,
                0,
                None,
            )
        raise AssertionError("V1_CHART_ANALYST_V2_LAYER2_STATE_INVALID")

    def _v2_layer2_snapshot(
        self,
        requirement: TradingViewReviewRequirement,
        record: ChartAnalystV2Layer2Record,
    ) -> InstrumentChartAnalysisSnapshot:
        complete = record.state is ChartAnalystV2Layer2State.SHADOW_COMPLETE
        return InstrumentChartAnalysisSnapshot(
            requirement.canonical_instrument,
            (
                ChartAnalysisState.ANALYSIS_COMPLETE
                if complete
                else ChartAnalysisState.CONTEXT_INCOMPLETE
            ),
            record.readiness,
            record.response.provider_identity,
            1,
            None if complete else ChartAnalystV2FailureCode.INCOMPLETE,
            record.response,
            record,
        )

    def _requirement_for(self, instrument: str) -> TradingViewReviewRequirement:
        requirement = next(
            (
                item
                for item in self._requirements
                if item.canonical_instrument == instrument
            ),
            None,
        )
        if requirement is None:
            raise ValueError("TRADINGVIEW_INSTRUMENT_NOT_REQUESTED")
        return requirement


def _latest_revisions(
    revisions: tuple[StoredChartRevision, ...],
) -> tuple[StoredChartRevision, ...]:
    latest: dict[ChartTimeframe, StoredChartRevision] = {}
    for item in revisions:
        current = latest.get(item.timeframe)
        if current is None or item.revision > current.revision:
            latest[item.timeframe] = item
    return tuple(latest[key] for key in sorted(latest, key=lambda item: item.value))


def _probable_assessments(
    run: V1Layer1Run,
    instrument: str,
) -> tuple[V1Layer1Assessment, ...]:
    evidence = next(
        (item for item in run.instruments if item.canonical_identity == instrument),
        None,
    )
    return tuple(
        item
        for item in (evidence.assessments if evidence is not None else ())
        if item.classification is ProbableClassification.PROBABLE_CANDIDATE
    )


def _thesis_context(assessment: V1Layer1Assessment) -> ChartThesisContext:
    return ChartThesisContext(
        direction=assessment.direction,
        setup=assessment.setup.value,
        layer1_structure=(
            assessment.structural.consensus.value
            if assessment.structural.consensus is not None
            else "UNAVAILABLE"
        ),
        layer1_sma20_slope=assessment.moving_average.sma20_direction or "UNAVAILABLE",
        layer1_price_vs_sma20=assessment.moving_average.price_vs_sma20 or "UNAVAILABLE",
        layer1_volume_context=assessment.volume.policy_interpretation,
    )


def _provider_request_count(provider: ChartEvidenceProvider | None) -> int | None:
    value = getattr(provider, "request_count", None)
    return value if type(value) is int and value >= 0 else None


def _request_count_delta(
    provider: ChartEvidenceProvider | None,
    before: int | None,
    completed_response_count: int,
) -> int:
    after = _provider_request_count(provider)
    if before is not None and after is not None and after >= before:
        return after - before
    return completed_response_count


__all__ = [
    "ChartAnalysisState",
    "InstrumentChartAnalysisSnapshot",
    "STEP31_V1_HANDOFF_SCHEMA_ID",
    "Step31EligibilityHandoff",
    "Step31EligibleInstrument",
    "SwingV1ReviewWorkflow",
    "V1ReviewRunState",
    "V1ReviewWorkflowSnapshot",
    "V1BatchPreflightFailure",
]
