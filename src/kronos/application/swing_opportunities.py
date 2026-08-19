"""Same-process Browser V1 orchestration over published Provider and Swing cores."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
import re
from threading import RLock, Thread
import time
from typing import Protocol
from uuid import uuid4

from kronos.application.live_monitoring_e2e import (
    LiveMonitoringTestResult,
    LiveMonitoringTestState,
    governed_live_monitoring_instruments,
    run_live_monitoring_e2e,
)

from kronos.configuration.principals import PrincipalBindingResult
from kronos.application.swing_mtf_facts import build_same_run_mtf_fact_snapshot
from kronos.market.calendar import CalendarCoverageHealth, MarketCalendarPublisher
from kronos.provider.contracts.instrument import (
    InstrumentKind,
    InstrumentResolutionRequest,
)
from kronos.provider.contracts.market_data import HistoricalCandleRequest
from kronos.provider.kite.instruments.kite_instrument_provider import (
    KiteInstrumentProvider,
)
from kronos.provider.kite.marketdata.kite_market_data_provider import (
    KiteMarketDataProvider,
)
from kronos.provider.models.authentication import AuthenticationAttemptState
from kronos.swing.candidate_ranking import (
    SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID,
    CandidateRanking,
    rank_trade_plans,
)
from kronos.swing.candidate_validation import (
    SwingCandidateValidation,
    validate_qualified_candidates,
)
from kronos.swing.daily_data import SwingDailyDataset, build_swing_daily_dataset
from kronos.swing.market_assessment import SwingMarketAssessment, assess_swing_market
from kronos.swing.top_opportunity import (
    SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID,
    TopOpportunitySelection,
    select_top_opportunities,
)
from kronos.swing.trade_plan import (
    SWING_PHASE1_TRADE_PLAN_POLICY_ID,
    TradePlan,
    build_trade_plan,
)
from kronos.swing.universe import (
    SwingUniverseAssetClass,
    SwingUniverseMember,
    enabled_swing_phase1_universe,
)
from kronos.swing.zero import SWING_ZERO_POLICY_ID
from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.run_provenance import (
    LocalSwingRunProvenanceStore,
    SwingAnalysisRunProvenance,
    market_data_snapshot_identity,
)
from kronos.swing.v1.layer1 import analyze_v1_layer1
from kronos.swing.v1.models import (
    ProbableClassification,
    V1Direction,
    V1Layer1Run,
    V1Setup,
)
from kronos.swing.v1.mtf_facts import (
    MtfFactEvidenceStore,
    SameRunMtfFactSnapshot,
)
from kronos.swing.v1.native_discovery import (
    NativeDiscoveryEvidenceStore,
    NativeDiscoveryRun,
    discover_native_mtf,
)


class ProviderConnectionState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


class AnalysisState(StrEnum):
    NOT_RUN = "NOT RUN"
    RUNNING = "RUNNING"
    READY = "READY"
    ERROR = "ERROR"


class MarketPanel(StrEnum):
    EQUITIES_INDICES = "EQUITIES + INDICES"
    COMMODITIES = "COMMODITIES"


@dataclass(frozen=True, slots=True)
class V1ProbableSnapshot:
    """Compact active-Sponsor projection of one unique V1 probable instrument."""

    instrument: str
    panel: MarketPanel
    setups: tuple[V1Setup, ...]
    directions: tuple[V1Direction, ...]

    def __post_init__(self) -> None:
        if (
            not self.instrument
            or type(self.panel) is not MarketPanel
            or not self.setups
            or not self.directions
            or len(set(self.setups)) != len(self.setups)
            or len(set(self.directions)) != len(self.directions)
            or any(type(item) is not V1Setup for item in self.setups)
            or any(type(item) is not V1Direction for item in self.directions)
        ):
            raise ValueError("BROWSER_V1_PROBABLE_SNAPSHOT_INVALID")


class AnalysisStage(StrEnum):
    PROVIDER_CAPABILITY = "PROVIDER_CAPABILITY"
    UNIVERSE = "UNIVERSE"
    DAILY_DATA = "DAILY_DATA"
    MARKET_ASSESSMENT = "MARKET_ASSESSMENT"
    CANDIDATE_EXTRACTION = "CANDIDATE_EXTRACTION"
    TRADE_PLAN = "TRADE_PLAN"
    RANKING = "RANKING"
    TOP_OPPORTUNITY = "TOP_OPPORTUNITY"
    MTF_FACTS = "CURRENT_GOVERNED_MTF_FACTS"
    NATIVE_DISCOVERY = "KRONOS_NATIVE_MTF_DISCOVERY"
    BROWSER_PROJECTION = "BROWSER_APPLICATION_ORCHESTRATION"


@dataclass(frozen=True, slots=True)
class AnalysisProgress:
    """Sanitized in-memory marker for the currently executing stage."""

    stage: AnalysisStage
    canonical_instrument: str | None = None
    completed_instrument_count: int | None = None
    observation_boundary: datetime | None = None
    provider_capability_active: bool | None = None

    def __post_init__(self) -> None:
        if (
            type(self.stage) is not AnalysisStage
            or (
                self.canonical_instrument is not None
                and not re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument)
            )
            or (
                self.completed_instrument_count is not None
                and not 0 <= self.completed_instrument_count <= 98
            )
            or (
                self.observation_boundary is not None
                and (
                    self.observation_boundary.tzinfo is None
                    or self.observation_boundary.utcoffset() is None
                )
            )
            or self.provider_capability_active not in (True, False, None)
        ):
            raise ValueError("ANALYSIS_PROGRESS_INVALID")


@dataclass(frozen=True, slots=True)
class AnalysisFailureDiagnostic:
    """Bounded local evidence with no raw exception or Provider material."""

    attempt_id: str
    timestamp: datetime
    failing_stage: AnalysisStage
    exception_class: str
    sanitized_summary: str
    canonical_instrument: str | None
    completed_instrument_count: int | None
    observation_boundary: datetime | None
    provider_capability_active: bool | None

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"ANALYSIS-[0-9]{6}", self.attempt_id)
            or self.timestamp.tzinfo is None
            or self.timestamp.utcoffset() is None
            or type(self.failing_stage) is not AnalysisStage
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", self.exception_class)
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", self.sanitized_summary)
            or (
                self.canonical_instrument is not None
                and not re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument)
            )
            or (
                self.completed_instrument_count is not None
                and not 0 <= self.completed_instrument_count <= 98
            )
            or (
                self.observation_boundary is not None
                and (
                    self.observation_boundary.tzinfo is None
                    or self.observation_boundary.utcoffset() is None
                )
            )
            or self.provider_capability_active not in (True, False, None)
        ):
            raise ValueError("ANALYSIS_FAILURE_DIAGNOSTIC_INVALID")


@dataclass(frozen=True, slots=True)
class OpportunitySnapshot:
    """Allowlisted browser projection of one workspace-capable Trade Plan."""

    position: int
    panel: MarketPanel
    instrument: str
    direction: str
    setup: str
    state: str
    entry: float
    entry_condition: str
    stop: float
    thesis_invalidation: tuple[str, ...]
    target_1: float
    risk: float
    reward: float
    risk_reward: float
    why: str
    evidence_for: tuple[str, ...]
    evidence_against_or_risks: tuple[str, ...]
    next_required_event: str
    observation_boundary: datetime
    swing_zero_policy: str
    trade_plan_policy: str
    ranking_policy: str
    top_opportunity_policy: str

    def __post_init__(self) -> None:
        if (
            type(self.position) is not int
            or self.position < 1
            or type(self.panel) is not MarketPanel
            or not self.instrument
            or not self.direction
            or not self.setup
            or not self.state
            or not self.entry_condition
            or not self.thesis_invalidation
            or not self.why
            or not self.next_required_event
            or self.observation_boundary.tzinfo is None
            or self.observation_boundary.utcoffset() is None
        ):
            raise ValueError("BROWSER_OPPORTUNITY_INVALID")


@dataclass(frozen=True, slots=True)
class EligiblePlanSnapshot:
    """Immutable Browser projection of one Stage-8-ranked eligible plan."""

    stage8_rank: int
    opportunity: OpportunitySnapshot
    selection_status: str
    selection_reason: str
    top_position: int | None = None

    def __post_init__(self) -> None:
        selected = self.selection_status == "SELECTED"
        if (
            type(self.stage8_rank) is not int
            or self.stage8_rank < 1
            or type(self.opportunity) is not OpportunitySnapshot
            or self.opportunity.position != self.stage8_rank
            or self.selection_status not in ("SELECTED", "NOT SELECTED")
            or not self.selection_reason
            or selected != (self.top_position is not None)
            or (
                self.top_position is not None
                and self.top_position not in (1, 2)
            )
        ):
            raise ValueError("BROWSER_ELIGIBLE_PLAN_INVALID")


@dataclass(frozen=True, slots=True)
class BrowserWorkspaceSnapshot:
    """Immutable sanitized Browser V1 state; never contains Provider internals."""

    provider_state: ProviderConnectionState
    analysis_state: AnalysisState
    universe_count: int
    analysis_run_identity: str | None = None
    swing_analysis_run_identity: str | None = None
    v1_layer1_run_identity: str | None = None
    run_created_at: datetime | None = None
    market_data_snapshot_identity: str | None = None
    observation_boundary: datetime | None = None
    completed_at: datetime | None = None
    qualified_count: int = 0
    actionable_count: int = 0
    attention_eligible_count: int = 0
    opportunities: tuple[OpportunitySnapshot, ...] = ()
    v1_probables: tuple[V1ProbableSnapshot, ...] = ()
    eligible_plans: tuple[EligiblePlanSnapshot, ...] = ()
    provider_failure: str = ""
    analysis_failure: str = ""

    def __post_init__(self) -> None:
        if (
            type(self.provider_state) is not ProviderConnectionState
            or type(self.analysis_state) is not AnalysisState
            or self.universe_count != 98
            or (
                self.analysis_run_identity is not None
                and re.fullmatch(
                    r"ANALYSIS-[0-9]{6}", self.analysis_run_identity
                ) is None
            )
            or (
                self.swing_analysis_run_identity is not None
                and not is_swing_analysis_run_id(self.swing_analysis_run_identity)
            )
            or (
                self.v1_layer1_run_identity is not None
                and not self.v1_layer1_run_identity
            )
            or (
                self.run_created_at is not None
                and (
                    self.run_created_at.tzinfo is None
                    or self.run_created_at.utcoffset() is None
                )
            )
            or (
                self.completed_at is not None
                and (
                    self.completed_at.tzinfo is None
                    or self.completed_at.utcoffset() is None
                )
            )
            or (
                self.market_data_snapshot_identity is not None
                and re.fullmatch(
                    r"SWING-MARKET-DATA-SNAPSHOT-[0-9a-f]{64}",
                    self.market_data_snapshot_identity,
                ) is None
            )
            or type(self.opportunities) is not tuple
            or type(self.v1_probables) is not tuple
            or any(type(item) is not V1ProbableSnapshot for item in self.v1_probables)
            or len({item.instrument for item in self.v1_probables})
            != len(self.v1_probables)
            or type(self.eligible_plans) is not tuple
            or len(self.opportunities) > 2
            or any(type(item) is not OpportunitySnapshot for item in self.opportunities)
            or any(type(item) is not EligiblePlanSnapshot for item in self.eligible_plans)
            or tuple(item.position for item in self.opportunities)
            != tuple(range(1, len(self.opportunities) + 1))
            or len(self.eligible_plans) != self.attention_eligible_count
            or tuple(item.stage8_rank for item in self.eligible_plans)
            != tuple(sorted(item.stage8_rank for item in self.eligible_plans))
            or len({item.stage8_rank for item in self.eligible_plans})
            != len(self.eligible_plans)
            or any(value < 0 for value in (
                self.qualified_count,
                self.actionable_count,
                self.attention_eligible_count,
            ))
        ):
            raise ValueError("BROWSER_WORKSPACE_SNAPSHOT_INVALID")

    def opportunity(self, position: int) -> OpportunitySnapshot | None:
        return next(
            (item for item in self.opportunities if item.position == position),
            None,
        )

    def eligible_plan(self, stage8_rank: int) -> EligiblePlanSnapshot | None:
        return next(
            (item for item in self.eligible_plans if item.stage8_rank == stage8_rank),
            None,
        )


@dataclass(frozen=True, slots=True)
class SwingAnalysisEvidenceSnapshot:
    """Complete provider-neutral evidence retained for one successful run."""

    analysis_run_identity: str
    swing_analysis_run_identity: str
    run_created_at: datetime
    observation_boundary: datetime
    market_data_snapshot_identity: str
    swing_zero_policy: str
    trade_plan_policy: str
    ranking_policy: str
    top_opportunity_policy: str
    universe: tuple[SwingUniverseMember, ...]
    daily_dataset: SwingDailyDataset
    market_assessment: SwingMarketAssessment
    candidate_validation: SwingCandidateValidation
    trade_plans: tuple[TradePlan, ...]
    candidate_ranking: CandidateRanking
    top_opportunity_selection: TopOpportunitySelection
    provider_neutral_provenance: tuple[str, ...]
    v1_layer1_run: V1Layer1Run

    def __post_init__(self) -> None:
        identities = tuple(member.canonical_identity for member in self.universe)
        assessment_identities = tuple(
            item.canonical_identity for item in self.market_assessment.instruments
        )
        record_identities = tuple(
            item.canonical_identity for item in self.daily_dataset.records
        )
        plan_candidates = tuple(plan.candidate_identity for plan in self.trade_plans)
        validation_candidates = tuple(
            (
                f"{candidate.canonical_identity}|{candidate.setup.value}|"
                f"{candidate.direction.value}|"
                f"{candidate.observation_boundary.isoformat()}"
            )
            for candidate in self.candidate_validation.candidates
        )
        if (
            re.fullmatch(r"ANALYSIS-[0-9]{6}", self.analysis_run_identity) is None
            or not is_swing_analysis_run_id(self.swing_analysis_run_identity)
            or self.run_created_at.tzinfo is None
            or self.run_created_at.utcoffset() is None
            or self.observation_boundary.tzinfo is None
            or self.observation_boundary.utcoffset() is None
            or re.fullmatch(
                r"SWING-MARKET-DATA-SNAPSHOT-[0-9a-f]{64}",
                self.market_data_snapshot_identity,
            ) is None
            or self.swing_zero_policy != SWING_ZERO_POLICY_ID
            or self.trade_plan_policy != SWING_PHASE1_TRADE_PLAN_POLICY_ID
            or self.ranking_policy != SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID
            or self.top_opportunity_policy
            != SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID
            or type(self.universe) is not tuple
            or type(self.v1_layer1_run) is not V1Layer1Run
            or self.v1_layer1_run.observation_boundary
            != self.observation_boundary
            or len(self.universe) != 98
            or any(type(item) is not SwingUniverseMember for item in self.universe)
            or type(self.daily_dataset) is not SwingDailyDataset
            or type(self.market_assessment) is not SwingMarketAssessment
            or type(self.candidate_validation) is not SwingCandidateValidation
            or type(self.trade_plans) is not tuple
            or any(type(item) is not TradePlan for item in self.trade_plans)
            or type(self.candidate_ranking) is not CandidateRanking
            or type(self.top_opportunity_selection) is not TopOpportunitySelection
            or identities != record_identities
            or identities != assessment_identities
            or self.market_assessment.observation_boundary
            != self.observation_boundary
            or self.candidate_validation.observation_boundary
            != self.observation_boundary
            or not self.candidate_validation.passed
            or plan_candidates != validation_candidates
            or any(
                plan.qualification_boundary != self.observation_boundary
                for plan in self.trade_plans
            )
            or self.candidate_ranking.input_count != len(self.trade_plans)
            or self.top_opportunity_selection.ranked_input
            is not self.candidate_ranking
            or type(self.provider_neutral_provenance) is not tuple
            or not self.provider_neutral_provenance
            or any(not item for item in self.provider_neutral_provenance)
        ):
            raise ValueError("SWING_ANALYSIS_EVIDENCE_INVALID")

    @property
    def instrument_assessments(self):  # type: ignore[no-untyped-def]
        return self.market_assessment.instruments

    @property
    def assessments(self):  # type: ignore[no-untyped-def]
        return tuple(
            assessment
            for item in self.market_assessment.instruments
            for assessment in item.assessments
        )

    @property
    def analysis_failures(self):  # type: ignore[no-untyped-def]
        return tuple(
            item
            for item in self.market_assessment.instruments
            if item.failure is not None
        )

    @property
    def qualified_candidates(self):  # type: ignore[no-untyped-def]
        return self.candidate_validation.candidates

    @property
    def actionable_plans(self):  # type: ignore[no-untyped-def]
        return tuple(
            item.trade_plan for item in self.candidate_ranking.ranked_actionable
        )

    @property
    def not_actionable_plans(self):  # type: ignore[no-untyped-def]
        return self.candidate_ranking.preserved_not_actionable

    @property
    def invalid_plans(self):  # type: ignore[no-untyped-def]
        return self.candidate_ranking.preserved_invalid

    @property
    def ranked_actionable(self):  # type: ignore[no-untyped-def]
        return self.candidate_ranking.ranked_actionable

    @property
    def attention_eligible(self):  # type: ignore[no-untyped-def]
        return self.top_opportunity_selection.attention_eligible

    @property
    def provisional_selection(self):  # type: ignore[no-untyped-def]
        return self.top_opportunity_selection.selected_top_opportunities


@dataclass(frozen=True, slots=True)
class CompletedSwingAnalysis:
    """Atomically publishable Browser projection and complete evidence."""

    workspace: BrowserWorkspaceSnapshot
    evidence: SwingAnalysisEvidenceSnapshot
    mtf_fact_snapshot: SameRunMtfFactSnapshot | None = None
    native_discovery_run: NativeDiscoveryRun | None = None

    def __post_init__(self) -> None:
        if (
            type(self.workspace) is not BrowserWorkspaceSnapshot
            or type(self.evidence) is not SwingAnalysisEvidenceSnapshot
            or self.workspace.analysis_state is not AnalysisState.READY
            or self.workspace.analysis_run_identity
            != self.evidence.analysis_run_identity
            or self.workspace.swing_analysis_run_identity
            != self.evidence.swing_analysis_run_identity
            or self.workspace.v1_layer1_run_identity
            != self.evidence.v1_layer1_run.run_identity
            or self.workspace.run_created_at != self.evidence.run_created_at
            or self.workspace.market_data_snapshot_identity
            != self.evidence.market_data_snapshot_identity
            or self.workspace.observation_boundary
            != self.evidence.observation_boundary
            or self.workspace.universe_count != len(self.evidence.universe)
            or self.workspace.qualified_count
            != len(self.evidence.qualified_candidates)
            or self.workspace.actionable_count
            != len(self.evidence.actionable_plans)
            or self.workspace.attention_eligible_count
            != len(self.evidence.attention_eligible)
            or (
                self.mtf_fact_snapshot is not None
                and (
                    type(self.mtf_fact_snapshot) is not SameRunMtfFactSnapshot
                    or self.mtf_fact_snapshot.run_identity
                    != self.evidence.swing_analysis_run_identity
                    or len(self.mtf_fact_snapshot.instruments)
                    != len(self.evidence.universe)
                )
            )
            or (
                self.native_discovery_run is not None
                and (
                    type(self.native_discovery_run) is not NativeDiscoveryRun
                    or self.native_discovery_run.run_identity
                    != self.evidence.swing_analysis_run_identity
                    or len(self.native_discovery_run.assessments)
                    != len(self.evidence.universe)
                )
            )
        ):
            raise ValueError("COMPLETED_SWING_ANALYSIS_INVALID")


class _ProviderRuntime(Protocol):
    def begin_login(self) -> object: ...
    def complete_callback(self, attempt: object) -> object: ...
    def authenticated_read_only_capability(self) -> object | None: ...
    def end_kronos_session(self) -> None: ...


_BackgroundRunner = Callable[[Callable[[], None], str], None]
_ProgressObserver = Callable[[AnalysisProgress], None]
_SAFE_SUMMARY = re.compile(r"[A-Z][A-Z0-9_]{0,95}\Z")
_SAFE_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}\Z")


def _start_thread(operation: Callable[[], None], name: str) -> None:
    Thread(target=operation, name=name, daemon=True).start()


class SwingOpportunitiesApplication:
    """Own Provider capability and Swing analysis inside one browser process."""

    def __init__(
        self,
        provider_factory: Callable[[], _ProviderRuntime],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        pace: Callable[[], None] = lambda: time.sleep(0.4),
        background_runner: _BackgroundRunner = _start_thread,
        initial_snapshot: BrowserWorkspaceSnapshot | None = None,
        swing_run_identity_factory: Callable[[], str] = (
            lambda: f"SWING-RUN-{uuid4().hex.upper()}"
        ),
        run_provenance_store: LocalSwingRunProvenanceStore | None = None,
        market_calendar_publisher: MarketCalendarPublisher | None = None,
        mtf_fact_evidence_store: MtfFactEvidenceStore | None = None,
        native_discovery_evidence_store: NativeDiscoveryEvidenceStore | None = None,
        live_monitoring_timeout_seconds: float = 15.0,
    ) -> None:
        if not all(callable(item) for item in (
            provider_factory,
            clock,
            pace,
            background_runner,
            swing_run_identity_factory,
        )):
            raise TypeError("BROWSER_APPLICATION_DEPENDENCY_INVALID")
        if (
            run_provenance_store is not None
            and type(run_provenance_store) is not LocalSwingRunProvenanceStore
        ):
            raise TypeError("BROWSER_APPLICATION_DEPENDENCY_INVALID")
        if (
            market_calendar_publisher is not None
            and type(market_calendar_publisher) is not MarketCalendarPublisher
        ) or (
            mtf_fact_evidence_store is not None
            and type(mtf_fact_evidence_store) is not MtfFactEvidenceStore
        ) or (
            native_discovery_evidence_store is not None
            and type(native_discovery_evidence_store)
            is not NativeDiscoveryEvidenceStore
        ):
            raise TypeError("BROWSER_APPLICATION_DEPENDENCY_INVALID")
        if (
            type(live_monitoring_timeout_seconds) is not float
            or not 0.0 < live_monitoring_timeout_seconds <= 60.0
        ):
            raise TypeError("BROWSER_APPLICATION_DEPENDENCY_INVALID")
        self.__provider_factory = provider_factory
        self.__clock = clock
        self.__pace = pace
        self.__background_runner = background_runner
        self.__swing_run_identity_factory = swing_run_identity_factory
        self.__run_provenance_store = run_provenance_store
        self.__market_calendar_publisher = market_calendar_publisher
        self.__mtf_fact_evidence_store = mtf_fact_evidence_store
        self.__native_discovery_evidence_store = native_discovery_evidence_store
        self.__live_monitoring_timeout_seconds = live_monitoring_timeout_seconds
        self.__lock = RLock()
        self.__provider: _ProviderRuntime | None = None
        self.__progression_watch_workflow: object | None = None
        self.__analysis_attempt_count = 0
        self.__analysis_diagnostic: AnalysisFailureDiagnostic | None = None
        self.__completed_analysis_evidence: SwingAnalysisEvidenceSnapshot | None = None
        self.__completed_mtf_fact_snapshot: SameRunMtfFactSnapshot | None = None
        self.__completed_native_discovery_run: NativeDiscoveryRun | None = None
        self.__live_monitoring_result = LiveMonitoringTestResult(
            LiveMonitoringTestState.NOT_TESTED
        )
        if initial_snapshot is not None and type(initial_snapshot) is not BrowserWorkspaceSnapshot:
            raise TypeError("BROWSER_APPLICATION_DEPENDENCY_INVALID")
        self.__snapshot = initial_snapshot or BrowserWorkspaceSnapshot(
            ProviderConnectionState.DISCONNECTED, AnalysisState.NOT_RUN, 98
        )
        if run_provenance_store is not None:
            recovered = run_provenance_store.latest()
            if recovered is not None:
                self.restore_run_provenance(recovered)
                if mtf_fact_evidence_store is not None:
                    try:
                        self.restore_mtf_fact_snapshot(
                            mtf_fact_evidence_store.load(recovered.run_id)
                        )
                    except ValueError:
                        pass
                if native_discovery_evidence_store is not None:
                    try:
                        self.restore_native_discovery_run(
                            native_discovery_evidence_store.load(recovered.run_id)
                        )
                    except ValueError:
                        pass

    def snapshot(self) -> BrowserWorkspaceSnapshot:
        with self.__lock:
            return self.__snapshot

    def opportunities_projection(
        self,
    ) -> tuple[BrowserWorkspaceSnapshot, NativeDiscoveryRun | None]:
        """Return one atomically bound successful Opportunities projection."""

        with self.__lock:
            snapshot = self.__snapshot
            discovery = self.__completed_native_discovery_run
            if (
                discovery is None
                or discovery.run_identity != snapshot.swing_analysis_run_identity
            ):
                discovery = None
            return snapshot, discovery

    def analysis_diagnostic(self) -> AnalysisFailureDiagnostic | None:
        with self.__lock:
            return self.__analysis_diagnostic

    def market_calendar_health(self) -> tuple[CalendarCoverageHealth, ...]:
        """Return current DOMAIN-008 publication horizon health for operations."""

        if self.__market_calendar_publisher is None:
            return ()
        observed_at = self.__clock()
        return tuple(
            self.__market_calendar_publisher.coverage_health(
                exchange,
                observed_at=observed_at,
            )
            for exchange in ("NSE", "MCX")
        )

    def completed_analysis_evidence(self) -> SwingAnalysisEvidenceSnapshot | None:
        """Return the latest immutable successful-run evidence without recomputation."""

        with self.__lock:
            return self.__completed_analysis_evidence

    def restore_run_provenance(
        self,
        provenance: SwingAnalysisRunProvenance,
    ) -> BrowserWorkspaceSnapshot:
        """Restore the last-successful header from durable audit evidence."""

        if type(provenance) is not SwingAnalysisRunProvenance:
            raise ValueError("SWING_RUN_PROVENANCE_INVALID")
        with self.__lock:
            self.__snapshot = replace(
                self.__snapshot,
                swing_analysis_run_identity=provenance.run_id,
                run_created_at=provenance.run_created_at,
                market_data_snapshot_identity=provenance.market_data_snapshot_identity,
                observation_boundary=provenance.analysis_boundary,
                completed_at=provenance.successful_completed_at,
            )
            return self.__snapshot

    def mtf_fact_snapshot(self) -> SameRunMtfFactSnapshot | None:
        with self.__lock:
            return self.__completed_mtf_fact_snapshot

    def mtf_fact_evidence_store(self) -> MtfFactEvidenceStore | None:
        return self.__mtf_fact_evidence_store

    def native_discovery_run(self) -> NativeDiscoveryRun | None:
        with self.__lock:
            return self.__completed_native_discovery_run

    def native_discovery_evidence_store(self) -> NativeDiscoveryEvidenceStore | None:
        return self.__native_discovery_evidence_store

    def restore_mtf_fact_snapshot(self, snapshot: SameRunMtfFactSnapshot) -> None:
        if type(snapshot) is not SameRunMtfFactSnapshot:
            raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
        with self.__lock:
            current = self.__snapshot.swing_analysis_run_identity
            if current and current != snapshot.run_identity:
                raise ValueError("MTF_FACT_RUN_BINDING_MISMATCH")
            self.__completed_mtf_fact_snapshot = snapshot

    def restore_native_discovery_run(self, run: NativeDiscoveryRun) -> None:
        if type(run) is not NativeDiscoveryRun:
            raise ValueError("NATIVE_DISCOVERY_RUN_INVALID")
        with self.__lock:
            current = self.__snapshot.swing_analysis_run_identity
            if current and current != run.run_identity:
                raise ValueError("NATIVE_DISCOVERY_RUN_BINDING_MISMATCH")
            self.__completed_native_discovery_run = run

    def live_monitoring_result(self) -> LiveMonitoringTestResult:
        with self.__lock:
            return self.__live_monitoring_result

    def live_monitoring_instruments(self) -> tuple[str, ...]:
        return governed_live_monitoring_instruments()

    def test_live_monitoring(self, canonical_instrument: str) -> bool:
        """Start one bounded Sponsor E2E and reject invalid/concurrent attempts."""

        if canonical_instrument not in governed_live_monitoring_instruments():
            with self.__lock:
                self.__live_monitoring_result = LiveMonitoringTestResult(
                    LiveMonitoringTestState.FAIL,
                    safe_reason="GOVERNED_INSTRUMENT_INVALID",
                )
            return False
        with self.__lock:
            if self.__live_monitoring_result.state is LiveMonitoringTestState.TESTING:
                return False
            if self.__snapshot.provider_state is not ProviderConnectionState.CONNECTED:
                self.__live_monitoring_result = LiveMonitoringTestResult(
                    LiveMonitoringTestState.FAIL,
                    canonical_instrument,
                    safe_reason="KITE_DISCONNECTED",
                )
                return False
            self.__live_monitoring_result = LiveMonitoringTestResult(
                LiveMonitoringTestState.TESTING,
                canonical_instrument,
            )
        self.__background_runner(
            lambda: self.__complete_live_monitoring_test(canonical_instrument),
            "kronos-live-monitoring-e2e",
        )
        return True

    def restore_v1_review_projection(
        self,
        run: V1Layer1Run,
        provenance: SwingAnalysisRunProvenance,
    ) -> BrowserWorkspaceSnapshot:
        """Restore the durable V1 review header/population without recomputation."""

        if (
            type(run) is not V1Layer1Run
            or type(provenance) is not SwingAnalysisRunProvenance
            or run.observation_boundary != provenance.analysis_boundary
        ):
            raise ValueError("V1_REVIEW_PROJECTION_INVALID")
        panels = {
            item.canonical_identity: (
                MarketPanel.COMMODITIES
                if item.asset_class is SwingUniverseAssetClass.MCX_COMMODITY
                else MarketPanel.EQUITIES_INDICES
            )
            for item in run.instruments
        }
        with self.__lock:
            updates: dict[str, object] = {
                "v1_layer1_run_identity": run.run_identity,
                "v1_probables": _project_v1_probables(run, panels),
            }
            if self.__snapshot.completed_at is None:
                updates.update({
                    "swing_analysis_run_identity": provenance.run_id,
                    "run_created_at": provenance.run_created_at,
                    "market_data_snapshot_identity": (
                        provenance.market_data_snapshot_identity
                    ),
                    "observation_boundary": provenance.analysis_boundary,
                    "completed_at": provenance.successful_completed_at,
                })
            self.__snapshot = replace(self.__snapshot, **updates)
            return self.__snapshot

    def connect_provider(self) -> bool:
        """Begin one explicit Sponsor connection without blocking HTTP serving."""

        with self.__lock:
            if self.__snapshot.provider_state in {
                ProviderConnectionState.CONNECTING,
                ProviderConnectionState.CONNECTED,
            }:
                return False
            self.__snapshot = replace(
                self.__snapshot,
                provider_state=ProviderConnectionState.CONNECTING,
                provider_failure="",
            )
        self.__background_runner(self.__complete_connection, "kronos-browser-auth")
        return True

    def register_progression_watch_workflow(self, workflow: object) -> None:
        """Bind the product-local watch lifecycle without exposing Provider state."""

        if not all(callable(getattr(workflow, name, None)) for name in (
            "activate_requirement", "restore_active", "close_monitoring",
        )):
            raise TypeError("PROGRESSION_WATCH_WORKFLOW_INVALID")
        with self.__lock:
            if (
                self.__progression_watch_workflow is not None
                and self.__progression_watch_workflow is not workflow
            ):
                raise ValueError("PROGRESSION_WATCH_WORKFLOW_ALREADY_REGISTERED")
            self.__progression_watch_workflow = workflow

    def activate_progression_watch(self, requirement_id: str) -> bool:
        """Explicit Sponsor activation through the owned read-only capability."""

        with self.__lock:
            provider = self.__provider
            workflow = self.__progression_watch_workflow
            allowed = (
                self.__snapshot.provider_state is ProviderConnectionState.CONNECTED
                and self.__snapshot.analysis_state is not AnalysisState.RUNNING
                and provider is not None
                and workflow is not None
            )
        if not allowed:
            return False
        capability = provider.authenticated_read_only_capability()
        if capability is None or getattr(capability, "active", False) is not True:
            return False
        try:
            workflow.activate_requirement(requirement_id, capability)
        except (TypeError, ValueError):
            return False
        return True

    def run_analysis(self) -> bool:
        """Start one complete Stage 1-9 run and reject concurrent requests."""

        with self.__lock:
            if (
                self.__snapshot.provider_state is not ProviderConnectionState.CONNECTED
                or self.__snapshot.analysis_state is AnalysisState.RUNNING
                or self.__live_monitoring_result.state is LiveMonitoringTestState.TESTING
            ):
                return False
            self.__snapshot = replace(
                self.__snapshot,
                analysis_state=AnalysisState.RUNNING,
                analysis_failure="",
            )
            self.__analysis_attempt_count += 1
            attempt_id = f"ANALYSIS-{self.__analysis_attempt_count:06d}"
            swing_run_identity = self.__swing_run_identity_factory()
            if not is_swing_analysis_run_id(swing_run_identity):
                raise ValueError("SWING_ANALYSIS_RUN_IDENTITY_INVALID")
            run_created_at = self.__aware_now()
            self.__analysis_diagnostic = None
        self.__background_runner(
            lambda: self.__complete_analysis(
                attempt_id,
                swing_run_identity,
                run_created_at,
            ),
            "kronos-browser-swing",
        )
        return True

    def disconnect_provider(self) -> bool:
        """Release the authenticated Provider context outside an active analysis."""

        with self.__lock:
            if (
                self.__snapshot.provider_state is not ProviderConnectionState.CONNECTED
                or self.__snapshot.analysis_state is AnalysisState.RUNNING
                or self.__live_monitoring_result.state is LiveMonitoringTestState.TESTING
            ):
                return False
            provider = self.__provider
            workflow = self.__progression_watch_workflow
            self.__provider = None
            self.__snapshot = replace(
                self.__snapshot,
                provider_state=ProviderConnectionState.DISCONNECTED,
                provider_failure="",
            )
        if workflow is not None:
            workflow.close_monitoring()
        if provider is not None:
            try:
                provider.end_kronos_session()
            except Exception:
                pass
        return True

    def close(self) -> None:
        with self.__lock:
            provider = self.__provider
            workflow = self.__progression_watch_workflow
            self.__provider = None
            self.__snapshot = replace(
                self.__snapshot,
                provider_state=ProviderConnectionState.DISCONNECTED,
            )
        if workflow is not None:
            workflow.close_monitoring()
        if provider is not None:
            try:
                provider.end_kronos_session()
            except Exception:
                pass

    def __complete_connection(self) -> None:
        provider: _ProviderRuntime | None = None
        try:
            provider = self.__provider_factory()
            attempt = provider.begin_login()
            outcome = provider.complete_callback(attempt)
            capability = provider.authenticated_read_only_capability()
            success = (
                getattr(outcome, "state", None)
                is AuthenticationAttemptState.SUCCEEDED
                and getattr(outcome, "binding_result", None)
                is PrincipalBindingResult.MATCHED
                and capability is not None
                and getattr(capability, "active", False) is True
            )
            if not success:
                raise RuntimeError("PROVIDER_CONNECTION_FAILED")
        except Exception:
            if provider is not None:
                try:
                    provider.end_kronos_session()
                except Exception:
                    pass
            with self.__lock:
                self.__provider = None
                self.__snapshot = replace(
                    self.__snapshot,
                    provider_state=ProviderConnectionState.ERROR,
                    provider_failure="PROVIDER_CONNECTION_FAILED",
                )
            return
        with self.__lock:
            self.__provider = provider
            workflow = self.__progression_watch_workflow
            self.__snapshot = replace(
                self.__snapshot,
                provider_state=ProviderConnectionState.CONNECTED,
                provider_failure="",
            )
        if workflow is not None:
            try:
                workflow.restore_active(capability)
            except Exception:
                workflow.close_monitoring()

    def __complete_live_monitoring_test(self, canonical_instrument: str) -> None:
        with self.__lock:
            provider = self.__provider
        if provider is None:
            result = LiveMonitoringTestResult(
                LiveMonitoringTestState.FAIL,
                canonical_instrument,
                safe_reason="KITE_DISCONNECTED",
            )
        else:
            capability = provider.authenticated_read_only_capability()
            if capability is None or getattr(capability, "active", False) is not True:
                result = LiveMonitoringTestResult(
                    LiveMonitoringTestState.FAIL,
                    canonical_instrument,
                    safe_reason="KITE_DISCONNECTED",
                )
            else:
                try:
                    result = run_live_monitoring_e2e(
                        capability,
                        canonical_instrument,
                        timeout_seconds=self.__live_monitoring_timeout_seconds,
                        clock=self.__clock,
                    )
                except Exception as error:
                    summary = _safe_exception_summary(error)
                    result = LiveMonitoringTestResult(
                        LiveMonitoringTestState.FAIL,
                        canonical_instrument,
                        safe_reason=summary,
                    )
        with self.__lock:
            self.__live_monitoring_result = result

    def __complete_analysis(
        self,
        attempt_id: str,
        swing_run_identity: str,
        run_created_at: datetime,
    ) -> None:
        with self.__lock:
            provider = self.__provider
        progress = AnalysisProgress(AnalysisStage.PROVIDER_CAPABILITY)

        def observe(updated: AnalysisProgress) -> None:
            nonlocal progress
            progress = updated

        try:
            if provider is None:
                raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
            capability = provider.authenticated_read_only_capability()
            if capability is None or getattr(capability, "active", False) is not True:
                raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
            progress = replace(progress, provider_capability_active=True)
            completed = build_completed_swing_analysis(
                capability,
                analysis_run_identity=attempt_id,
                swing_analysis_run_identity=swing_run_identity,
                run_created_at=run_created_at,
                now=run_created_at,
                pace=self.__pace,
                progress_observer=observe,
                market_calendar_publisher=self.__market_calendar_publisher,
                mtf_fact_evidence_store=self.__mtf_fact_evidence_store,
                native_discovery_evidence_store=(
                    self.__native_discovery_evidence_store
                ),
            )
            successful_completed_at = self.__aware_now()
            published_workspace = replace(
                completed.workspace,
                completed_at=successful_completed_at,
            )
            mtf_fact_snapshot = getattr(completed, "mtf_fact_snapshot", None)
            native_discovery_run = getattr(completed, "native_discovery_run", None)
            if mtf_fact_snapshot is not None and self.__mtf_fact_evidence_store is not None:
                self.__mtf_fact_evidence_store.retain(mtf_fact_snapshot)
            if (
                native_discovery_run is not None
                and self.__native_discovery_evidence_store is not None
            ):
                self.__native_discovery_evidence_store.retain(native_discovery_run)
            if self.__run_provenance_store is not None:
                self.__run_provenance_store.retain(SwingAnalysisRunProvenance(
                    run_id=completed.evidence.swing_analysis_run_identity,
                    run_created_at=completed.evidence.run_created_at,
                    analysis_boundary=completed.evidence.observation_boundary,
                    market_data_snapshot_identity=(
                        completed.evidence.market_data_snapshot_identity
                    ),
                    successful_completed_at=successful_completed_at,
                ))
        except Exception as error:
            diagnostic = AnalysisFailureDiagnostic(
                attempt_id=attempt_id,
                timestamp=_diagnostic_timestamp(self.__clock),
                failing_stage=progress.stage,
                exception_class=_safe_exception_class(error),
                sanitized_summary=_safe_exception_summary(error),
                canonical_instrument=progress.canonical_instrument,
                completed_instrument_count=progress.completed_instrument_count,
                observation_boundary=progress.observation_boundary,
                provider_capability_active=progress.provider_capability_active,
            )
            with self.__lock:
                self.__analysis_diagnostic = diagnostic
                self.__snapshot = replace(
                    self.__snapshot,
                    analysis_state=AnalysisState.ERROR,
                    analysis_failure="SWING_ANALYSIS_FAILED",
                )
            return
        with self.__lock:
            self.__analysis_diagnostic = None
            self.__completed_analysis_evidence = completed.evidence
            self.__completed_mtf_fact_snapshot = mtf_fact_snapshot
            self.__completed_native_discovery_run = native_discovery_run
            self.__snapshot = replace(
                published_workspace,
                provider_state=ProviderConnectionState.CONNECTED,
            )

    def __aware_now(self) -> datetime:
        now = self.__clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("BROWSER_CLOCK_MUST_BE_TIMEZONE_AWARE")
        return now


def build_completed_swing_analysis(
    capability: object,
    *,
    analysis_run_identity: str,
    swing_analysis_run_identity: str = (
        "SWING-RUN-00000000000000000000000000000001"
    ),
    run_created_at: datetime | None = None,
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
    progress_observer: _ProgressObserver | None = None,
    market_calendar_publisher: MarketCalendarPublisher | None = None,
    mtf_fact_evidence_store: MtfFactEvidenceStore | None = None,
    native_discovery_evidence_store: NativeDiscoveryEvidenceStore | None = None,
) -> CompletedSwingAnalysis:
    """Run Stage 1-9 once and retain evidence beside the compact projection."""

    run_created_at = now if run_created_at is None else run_created_at
    if (
        getattr(capability, "active", False) is not True
        or re.fullmatch(r"ANALYSIS-[0-9]{6}", analysis_run_identity) is None
        or not is_swing_analysis_run_id(swing_analysis_run_identity)
        or now.tzinfo is None
        or now.utcoffset() is None
        or run_created_at.tzinfo is None
        or run_created_at.utcoffset() is None
        or not callable(pace)
        or (progress_observer is not None and not callable(progress_observer))
        or (
            market_calendar_publisher is not None
            and type(market_calendar_publisher) is not MarketCalendarPublisher
        )
        or (
            mtf_fact_evidence_store is not None
            and type(mtf_fact_evidence_store) is not MtfFactEvidenceStore
        )
        or (
            native_discovery_evidence_store is not None
            and type(native_discovery_evidence_store)
            is not NativeDiscoveryEvidenceStore
        )
    ):
        raise ValueError("BROWSER_ANALYSIS_REQUEST_INVALID")

    def observe(
        stage: AnalysisStage,
        *,
        canonical_instrument: str | None = None,
        completed_instrument_count: int | None = None,
        observation_boundary: datetime | None = None,
    ) -> None:
        if progress_observer is not None:
            progress_observer(AnalysisProgress(
                stage=stage,
                canonical_instrument=canonical_instrument,
                completed_instrument_count=completed_instrument_count,
                observation_boundary=observation_boundary,
                provider_capability_active=True,
            ))

    observe(AnalysisStage.UNIVERSE)
    universe = enabled_swing_phase1_universe()
    observe(AnalysisStage.DAILY_DATA)
    instruments = KiteInstrumentProvider(capability)  # type: ignore[arg-type]
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]
    masters = {
        "NSE": instruments.retrieve("NSE"),
        "MCX": instruments.retrieve("MCX"),
    }

    def resolve(member: SwingUniverseMember):  # type: ignore[no-untyped-def]
        if member.asset_class is SwingUniverseAssetClass.NSE_EQUITY:
            kind = InstrumentKind.NSE_EQUITY
            master = masters["NSE"]
        elif member.asset_class is SwingUniverseAssetClass.NSE_INDEX:
            kind = InstrumentKind.NSE_INDEX
            master = masters["NSE"]
        else:
            kind = InstrumentKind.MCX_FUTURE
            master = masters["MCX"]
        return instruments.resolve_from_records(
            master,
            InstrumentResolutionRequest(
                kind=kind,
                symbol=member.canonical_identity,
                as_of=now.date(),
            ),
        )

    historical_calls = 0

    def retrieve(request: HistoricalCandleRequest):  # type: ignore[no-untyped-def]
        nonlocal historical_calls
        if historical_calls:
            pace()
        historical_calls += 1
        return market_data.historical_candles(request)

    dataset = build_swing_daily_dataset(
        universe,
        resolve_instrument=resolve,
        historical_candles=retrieve,
        now=now,
        market_calendar_publisher=market_calendar_publisher,
    )
    snapshot_identity = market_data_snapshot_identity(dataset)
    v1_layer1_run = analyze_v1_layer1(dataset)
    observe(
        AnalysisStage.MARKET_ASSESSMENT,
        completed_instrument_count=dataset.ready_count,
    )
    market = assess_swing_market(dataset)
    observe(
        AnalysisStage.CANDIDATE_EXTRACTION,
        completed_instrument_count=dataset.ready_count,
        observation_boundary=market.observation_boundary,
    )
    validation = validate_qualified_candidates(market, dataset)
    if not validation.passed:
        raise RuntimeError("SWING_CANDIDATE_VALIDATION_FAILED")
    records = {record.canonical_identity: record for record in dataset.records}
    plans_list = []
    observe(
        AnalysisStage.TRADE_PLAN,
        completed_instrument_count=dataset.ready_count,
        observation_boundary=market.observation_boundary,
    )
    for candidate in validation.candidates:
        observe(
            AnalysisStage.TRADE_PLAN,
            canonical_instrument=candidate.canonical_identity,
            completed_instrument_count=dataset.ready_count,
            observation_boundary=market.observation_boundary,
        )
        plans_list.append(build_trade_plan(
            candidate,
            tuple(
                candle
                for candle in records[candidate.canonical_identity].candles
                if candle.timestamp <= market.observation_boundary
            ),
        ))
    plans = tuple(plans_list)
    observe(
        AnalysisStage.RANKING,
        completed_instrument_count=dataset.ready_count,
        observation_boundary=market.observation_boundary,
    )
    ranking = rank_trade_plans(plans)
    observe(
        AnalysisStage.TOP_OPPORTUNITY,
        completed_instrument_count=dataset.ready_count,
        observation_boundary=market.observation_boundary,
    )
    selection = select_top_opportunities(ranking)
    mtf_fact_snapshot = None
    native_discovery_run = None
    if market_calendar_publisher is not None:
        observe(
            AnalysisStage.MTF_FACTS,
            completed_instrument_count=dataset.ready_count,
            observation_boundary=market.observation_boundary,
        )
        mtf_fact_snapshot = build_same_run_mtf_fact_snapshot(
            run_identity=swing_analysis_run_identity,
            daily_dataset=dataset,
            historical_candles=retrieve,
            calendar_publisher=market_calendar_publisher,
            observed_at=now,
            predecessor_snapshot=(
                None
                if mtf_fact_evidence_store is None
                else mtf_fact_evidence_store.latest()
            ),
        )
        observe(
            AnalysisStage.NATIVE_DISCOVERY,
            completed_instrument_count=dataset.ready_count,
            observation_boundary=market.observation_boundary,
        )
        native_discovery_run = discover_native_mtf(
            mtf_fact_snapshot,
            predecessor=(
                None
                if native_discovery_evidence_store is None
                else native_discovery_evidence_store.latest()
            ),
            daily_control=v1_layer1_run,
        )
    observe(
        AnalysisStage.BROWSER_PROJECTION,
        completed_instrument_count=dataset.ready_count,
        observation_boundary=market.observation_boundary,
    )
    panels = {
        member.canonical_identity: (
            MarketPanel.COMMODITIES
            if member.asset_class is SwingUniverseAssetClass.MCX_COMMODITY
            else MarketPanel.EQUITIES_INDICES
        )
        for member in universe
    }
    v1_probables = _project_v1_probables(v1_layer1_run, panels)
    opportunities = tuple(
        _project_opportunity(item, panels[item.attention_entry.canonical_identity])
        for item in selection.selected_top_opportunities
    )
    selected_by_candidate = {
        item.trade_plan.candidate_identity: item
        for item in selection.selected_top_opportunities
    }
    selected_instruments = {
        item.attention_entry.canonical_identity
        for item in selection.selected_top_opportunities
    }
    eligible_plans = tuple(
        _project_eligible_plan(
            item,
            panels[item.ranked_plan.canonical_identity],
            selected_by_candidate.get(item.ranked_plan.trade_plan.candidate_identity),
            item.ranked_plan.canonical_identity in selected_instruments,
        )
        for item in selection.attention_eligible
    )
    workspace = BrowserWorkspaceSnapshot(
        provider_state=ProviderConnectionState.CONNECTED,
        analysis_state=AnalysisState.READY,
        universe_count=len(universe),
        analysis_run_identity=analysis_run_identity,
        swing_analysis_run_identity=swing_analysis_run_identity,
        v1_layer1_run_identity=v1_layer1_run.run_identity,
        run_created_at=run_created_at,
        market_data_snapshot_identity=snapshot_identity,
        observation_boundary=market.observation_boundary,
        completed_at=now,
        qualified_count=len(validation.candidates),
        actionable_count=len(ranking.ranked_actionable),
        attention_eligible_count=len(selection.attention_eligible),
        opportunities=opportunities,
        v1_probables=v1_probables,
        eligible_plans=eligible_plans,
    )
    evidence = SwingAnalysisEvidenceSnapshot(
        analysis_run_identity=analysis_run_identity,
        swing_analysis_run_identity=swing_analysis_run_identity,
        run_created_at=run_created_at,
        observation_boundary=market.observation_boundary,
        market_data_snapshot_identity=snapshot_identity,
        swing_zero_policy=SWING_ZERO_POLICY_ID,
        trade_plan_policy=SWING_PHASE1_TRADE_PLAN_POLICY_ID,
        ranking_policy=SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID,
        top_opportunity_policy=SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID,
        universe=universe,
        daily_dataset=dataset,
        market_assessment=market,
        candidate_validation=validation,
        trade_plans=plans,
        candidate_ranking=ranking,
        top_opportunity_selection=selection,
        provider_neutral_provenance=(
            "source=Provider Foundation V2 normalized completed Daily candles",
            f"completed_boundary={market.observation_boundary.isoformat()}",
            f"market_data_snapshot_identity={snapshot_identity}",
        ),
        v1_layer1_run=v1_layer1_run,
    )
    return CompletedSwingAnalysis(
        workspace=workspace,
        evidence=evidence,
        mtf_fact_snapshot=mtf_fact_snapshot,
        native_discovery_run=native_discovery_run,
    )


def build_browser_workspace_snapshot(
    capability: object,
    *,
    analysis_run_identity: str = "ANALYSIS-000001",
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
    progress_observer: _ProgressObserver | None = None,
) -> BrowserWorkspaceSnapshot:
    """Compatibility projection for callers that need Browser state only."""

    return build_completed_swing_analysis(
        capability,
        analysis_run_identity=analysis_run_identity,
        now=now,
        pace=pace,
        progress_observer=progress_observer,
    ).workspace


def _safe_exception_class(error: Exception) -> str:
    name = type(error).__name__
    return name if _SAFE_CLASS.fullmatch(name) else "Exception"


def _safe_exception_summary(error: Exception) -> str:
    failure = getattr(error, "failure", None)
    candidate = getattr(failure, "value", None)
    if not isinstance(candidate, str) and len(error.args) == 1:
        candidate = error.args[0]
    return candidate if isinstance(candidate, str) and _SAFE_SUMMARY.fullmatch(candidate) else "SANITIZED_FAILURE"


def _diagnostic_timestamp(clock: Callable[[], datetime]) -> datetime:
    try:
        value = clock()
    except Exception:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        return datetime.now(UTC)
    return value


def _project_v1_probables(
    run: V1Layer1Run,
    panels: dict[str, MarketPanel],
) -> tuple[V1ProbableSnapshot, ...]:
    projected: list[V1ProbableSnapshot] = []
    for instrument in run.instruments:
        probable = tuple(
            assessment
            for assessment in instrument.assessments
            if assessment.classification
            is ProbableClassification.PROBABLE_CANDIDATE
        )
        if not probable:
            continue
        projected.append(V1ProbableSnapshot(
            instrument=instrument.canonical_identity,
            panel=panels[instrument.canonical_identity],
            setups=tuple(dict.fromkeys(item.setup for item in probable)),
            directions=tuple(dict.fromkeys(item.direction for item in probable)),
        ))
    return tuple(projected)


def _project_opportunity(item, panel: MarketPanel) -> OpportunitySnapshot:  # type: ignore[no-untyped-def]
    return _project_trade_plan(item.trade_plan, item.position, panel)


def _project_eligible_plan(  # type: ignore[no-untyped-def]
    item,
    panel: MarketPanel,
    selected,
    instrument_selected: bool,
) -> EligiblePlanSnapshot:
    if selected is not None:
        status = "SELECTED"
        reason = selected.selection_explanation
        top_position = selected.position
    elif instrument_selected:
        status = "NOT SELECTED"
        reason = (
            "Attention eligible; not selected because its canonical instrument "
            "is already represented by a higher-ranked eligible plan."
        )
        top_position = None
    else:
        status = "NOT SELECTED"
        reason = (
            "Attention eligible; not selected because the global Top Opportunity "
            "limit is 2."
        )
        top_position = None
    return EligiblePlanSnapshot(
        stage8_rank=item.ranked_plan.position,
        opportunity=_project_trade_plan(
            item.ranked_plan.trade_plan,
            item.ranked_plan.position,
            panel,
        ),
        selection_status=status,
        selection_reason=reason,
        top_position=top_position,
    )


def _project_trade_plan(  # type: ignore[no-untyped-def]
    plan,
    position: int,
    panel: MarketPanel,
) -> OpportunitySnapshot:
    assessment = plan.original_assessment
    return OpportunitySnapshot(
        position=position,
        panel=panel,
        instrument=plan.canonical_identity,
        direction=plan.direction.value,
        setup=plan.setup.value,
        state=assessment.state.value,
        entry=plan.entry,
        entry_condition=plan.entry_condition,
        stop=plan.stop,
        thesis_invalidation=plan.thesis_invalidation,
        target_1=plan.target_1,
        risk=plan.risk_per_unit,
        reward=plan.reward_per_unit,
        risk_reward=plan.risk_reward,  # type: ignore[arg-type]
        why=assessment.why,
        evidence_for=assessment.evidence_for,
        evidence_against_or_risks=assessment.evidence_against_or_risks,
        next_required_event=assessment.next_required_event or plan.entry_condition,
        observation_boundary=assessment.observation_boundary,
        swing_zero_policy=SWING_ZERO_POLICY_ID,
        trade_plan_policy=SWING_PHASE1_TRADE_PLAN_POLICY_ID,
        ranking_policy=SWING_PHASE1_CANDIDATE_RANKING_POLICY_ID,
        top_opportunity_policy=SWING_PHASE1_TOP_OPPORTUNITY_POLICY_ID,
    )


__all__ = [
    "AnalysisFailureDiagnostic",
    "AnalysisProgress",
    "AnalysisStage",
    "AnalysisState",
    "BrowserWorkspaceSnapshot",
    "CompletedSwingAnalysis",
    "EligiblePlanSnapshot",
    "MarketPanel",
    "OpportunitySnapshot",
    "ProviderConnectionState",
    "SwingAnalysisEvidenceSnapshot",
    "SwingOpportunitiesApplication",
    "build_completed_swing_analysis",
    "build_browser_workspace_snapshot",
]
