"""Application lifecycle for immutable Native Probable Review preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import logging
from threading import RLock
from typing import Callable

from kronos.swing.v1.evidence_store import (
    LocalTradingViewEvidenceStore,
    NativeChartReviewBinding,
    NativeTradingViewEvidencePackage,
    StoredChartRevision,
    TradingViewEvidenceStoreError,
)

from kronos.swing.v1.mtf_facts import FactualTimeframe, SameRunMtfFactSnapshot
from kronos.swing.v1.native_discovery import (
    NativeDiscoveryRun,
    NativeDiscoveryStatus,
    NativeInstrumentDiscovery,
)
from kronos.swing.v1.native_review import (
    McxReferenceEvidenceState,
    McxReferenceResult,
    McxReferenceStatus,
    NativeIndependentLayer2Evidence,
    NativeLayer2EvidenceState,
    NativeLayer2ReviewRecord,
    NativeReviewEvidenceStore,
    NativeReviewRequirement,
    build_native_review_requirements,
    reconcile_native_layer2,
)
from kronos.swing.v1.visual_evidence_v2 import (
    LocalVisualEvidenceV2DiagnosticStore,
    LocalVisualEvidenceV2Store,
    VisualEvidenceV2Request,
    VisualEvidenceV2Response,
    VisualEvidenceV2ValidationDiagnostic,
    VisualEvidenceV2ValidationStage,
    VisualEvidenceSubjectKind,
    VisualEvidenceV2Provider,
    VisualObservationStatus,
    VisualQuestionV2,
    VisualTimeframe,
    build_visual_evidence_v2_request,
)
from kronos.swing.v1.native_readiness import (
    NativeConditionInputs,
    NativeLayer2ReadinessRecord,
    NativeLayer2ReadinessStore,
    create_native_readiness_record,
)
from kronos.swing.v1.native_trade_construction import (
    LocalTradePlanStore,
    TradeConstructionEvidencePackage,
    TradePlanRecord,
    construct_trade_plan as build_trade_plan,
)
from kronos.swing.v1.native_sponsor_decision import (
    create_trade_plan_business_judgment,
    LocalSponsorDecisionStore,
    record_trade_plan_risk_result,
    SponsorInitiationResult,
    SponsorTradeChoice,
    initiate_sponsor_decision as initiate_native_sponsor_decision,
    validate_step32_inputs,
)
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleMonitoringCoordinator,
    ActiveTradeLifecycleService,
    ActiveTradeLifecycleSnapshot,
    GovernedLifecycleObservation,
    LocalActiveTradeLifecycleStore,
    TradeClosureRecord,
    TradeExitReason,
)
from kronos.swing.v1.native_trade_journal import (
    LocalTradeJournalStore,
    JournalValidationAnalytics,
    TradeJournalService,
    TradeJournalSnapshot,
    calculate_journal_analytics,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.swing.v1.step32 import BusinessJudgment, RiskApproval
from kronos.swing.v1.native_entry_timing import RiskPermissionV1
from kronos.instrument.facts import CanonicalInstrumentContext
from kronos.swing.v1.pdf_visual_review import (
    AnswerImportRecord,
    PdfReviewTransportError,
    PdfVisualReviewTransport,
    ReviewPackRecord,
)
from kronos.swing.v1.tradingview import ChartTimeframe
from kronos.swing.v1.chart_analyst_v2 import (
    ChartAnalystV2Error,
    ChartAnalystV2FailureCode,
)


_LOG = logging.getLogger(__name__)


class NativeReviewRunState(StrEnum):
    NOT_PREPARED = "NOT_PREPARED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class NativeReviewAnalysisState(StrEnum):
    NOT_ANALYZED = "NOT_ANALYZED"
    ANALYZING = "ANALYZING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


@dataclass(frozen=True, slots=True)
class NativeReviewAnalysisOutcome:
    canonical_instrument: str
    state: NativeReviewAnalysisState
    disposition: str
    sponsor_reason: str

    def __post_init__(self) -> None:
        if (
            not self.canonical_instrument
            or type(self.state) is not NativeReviewAnalysisState
            or self.disposition
            not in {"IN_PROGRESS", "SUCCESS", "SKIPPED", "FAILED"}
            or not self.sponsor_reason
        ):
            raise ValueError("NATIVE_REVIEW_ANALYSIS_OUTCOME_INVALID")


@dataclass(frozen=True, slots=True)
class NativeReviewWorkflowSnapshot:
    state: NativeReviewRunState
    native_run_identity: str | None
    requirements: tuple[NativeReviewRequirement, ...]
    layer2_records: tuple[NativeLayer2ReviewRecord, ...]
    chart_packages: tuple[NativeTradingViewEvidencePackage, ...] = ()
    reference_results: tuple[McxReferenceResult, ...] = ()
    visual_v2_results: tuple[VisualEvidenceV2Response, ...] = ()
    readiness_records: tuple[NativeLayer2ReadinessRecord, ...] = ()
    analysis_outcomes: tuple[NativeReviewAnalysisOutcome, ...] = ()
    visual_v2_diagnostics: tuple[VisualEvidenceV2ValidationDiagnostic, ...] = ()
    review_pack_record: ReviewPackRecord | None = None
    answer_import_records: tuple[AnswerImportRecord, ...] = ()
    review_pack_scope: str | None = None
    review_pack_skipped: tuple[tuple[str, str], ...] = ()
    review_pack_superseded: bool = False
    refresh_status: str | None = None
    trade_plans: tuple[TradePlanRecord, ...] = ()
    sponsor_initiations: tuple[SponsorInitiationResult, ...] = ()
    step32_eligible_plan_ids: tuple[str, ...] = ()
    active_lifecycle: ActiveTradeLifecycleSnapshot = field(
        default_factory=lambda: ActiveTradeLifecycleSnapshot((), (), (), ())
    )
    trade_journal: TradeJournalSnapshot = field(
        default_factory=lambda: TradeJournalSnapshot(
            (), calculate_journal_analytics(()),
            JournalValidationAnalytics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, (), ()),
        )
    )
    risk_records: tuple[RiskApproval, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.state) is not NativeReviewRunState
            or type(self.requirements) is not tuple
            or type(self.layer2_records) is not tuple
            or type(self.chart_packages) is not tuple
            or type(self.reference_results) is not tuple
            or type(self.visual_v2_results) is not tuple
            or type(self.readiness_records) is not tuple
            or type(self.analysis_outcomes) is not tuple
            or type(self.visual_v2_diagnostics) is not tuple
            or (
                self.review_pack_record is not None
                and type(self.review_pack_record) is not ReviewPackRecord
            )
            or type(self.answer_import_records) is not tuple
            or any(type(item) is not AnswerImportRecord for item in self.answer_import_records)
            or self.review_pack_scope not in {None, "ALL_ELIGIBLE", "INDIVIDUAL"}
            or type(self.review_pack_skipped) is not tuple
            or type(self.review_pack_superseded) is not bool
            or (self.refresh_status is not None and not self.refresh_status)
            or type(self.trade_plans) is not tuple
            or any(type(item) is not TradePlanRecord for item in self.trade_plans)
            or type(self.sponsor_initiations) is not tuple
            or any(type(item) is not SponsorInitiationResult for item in self.sponsor_initiations)
            or type(self.step32_eligible_plan_ids) is not tuple
            or type(self.active_lifecycle) is not ActiveTradeLifecycleSnapshot
            or type(self.trade_journal) is not TradeJournalSnapshot
            or type(self.risk_records) is not tuple
            or any(type(item) is not RiskApproval for item in self.risk_records)
            or (
                self.review_pack_record is None
                and (
                    self.review_pack_scope is not None
                    or self.review_pack_skipped
                    or self.review_pack_superseded
                )
            )
            or len({item.canonical_instrument for item in self.requirements})
            != len(self.requirements)
            or any(
                item.requirement not in self.requirements
                for item in self.layer2_records
            )
            or any(
                not any(
                    package.binding.native_run_identity
                    == requirement.native_run_identity
                    and package.binding.native_assessment_sha256
                    == requirement.thesis.native_assessment_sha256
                    and package.binding.canonical_instrument
                    == requirement.canonical_instrument
                    for requirement in self.requirements
                )
                for package in self.chart_packages
            )
            or len({item.requirement.mcx_canonical_instrument for item in self.reference_results})
            != len(self.reference_results)
            or any(
                item.requirement not in tuple(
                    requirement.mcx_reference for requirement in self.requirements
                    if requirement.mcx_reference is not None
                )
                for item in self.reference_results
            )
            or any(
                not any(
                    result.native_run_identity == requirement.native_run_identity
                    and result.native_assessment_sha256
                    == requirement.thesis.native_assessment_sha256
                    and result.native_canonical_instrument
                    == requirement.canonical_instrument
                    for requirement in self.requirements
                )
                for result in self.visual_v2_results
            )
            or any(
                not any(
                    result.run_identity == requirement.native_run_identity
                    and result.native_assessment_sha256
                    == requirement.thesis.native_assessment_sha256
                    and result.canonical_instrument == requirement.canonical_instrument
                    for requirement in self.requirements
                )
                for result in self.readiness_records
            )
            or any(
                not any(
                    plan.native_run_identity == requirement.native_run_identity
                    and plan.native_assessment_sha256
                    == requirement.thesis.native_assessment_sha256
                    and plan.canonical_instrument == requirement.canonical_instrument
                    and plan.native_opportunity_identity
                    == requirement.thesis.opportunity_identity
                    and plan.native_direction == requirement.thesis.direction
                    for requirement in self.requirements
                )
                for plan in self.trade_plans
            )
            or any(
                not any(
                    outcome.canonical_instrument
                    == requirement.canonical_instrument
                    for requirement in self.requirements
                )
                for outcome in self.analysis_outcomes
            )
            or (
                self.state is NativeReviewRunState.NOT_PREPARED
                and (
                    self.native_run_identity is not None or self.requirements
                    or self.layer2_records or self.chart_packages
                    or self.reference_results
                    or self.visual_v2_results
                    or self.readiness_records
                    or self.trade_plans
                    or self.sponsor_initiations
                    or self.step32_eligible_plan_ids
                    or self.analysis_outcomes
                    or self.visual_v2_diagnostics
                )
            )
            or (
                self.state is NativeReviewRunState.REVIEW_REQUIRED
                and (
                    self.native_run_identity is None
                    or not self.requirements
                    or any(
                        item.native_run_identity != self.native_run_identity
                        for item in self.requirements
                    )
                )
            )
        ):
            raise ValueError("NATIVE_REVIEW_WORKFLOW_SNAPSHOT_INVALID")

    def requirement_for(self, instrument: str) -> NativeReviewRequirement | None:
        return next(
            (item for item in self.requirements if item.canonical_instrument == instrument),
            None,
        )


@dataclass(frozen=True, slots=True)
class NativeAnalysisDetailsProjection:
    """Immutable, authority-free projection of one current Native review cycle."""

    assessment: NativeInstrumentDiscovery
    requirement: NativeReviewRequirement
    visual_v2_results: tuple[VisualEvidenceV2Response, ...]
    layer2_record: NativeLayer2ReviewRecord | None
    readiness_record: NativeLayer2ReadinessRecord | None
    chart_packages: tuple[NativeTradingViewEvidencePackage, ...]
    review_pack_record: ReviewPackRecord | None


def project_native_analysis_details(
    run: NativeDiscoveryRun,
    review: NativeReviewWorkflowSnapshot,
    run_identity: str,
    canonical_instrument: str,
) -> NativeAnalysisDetailsProjection | None:
    """Fail closed unless every available record binds to one run/instrument."""

    if (
        type(run) is not NativeDiscoveryRun
        or type(review) is not NativeReviewWorkflowSnapshot
        or run.run_identity != run_identity
        or review.native_run_identity != run_identity
        or not canonical_instrument
    ):
        return None
    assessment = next(
        (
            item for item in run.assessments
            if item.canonical_instrument == canonical_instrument
            and item.status is NativeDiscoveryStatus.PROBABLE
        ),
        None,
    )
    requirement = next(
        (
            item for item in review.requirements
            if item.native_run_identity == run_identity
            and item.canonical_instrument == canonical_instrument
        ),
        None,
    )
    if (
        assessment is None
        or requirement is None
        or requirement.thesis.native_assessment_sha256 != assessment.result_sha256
    ):
        return None
    pack = (
        None if review.review_pack_superseded else review.review_pack_record
    )
    if pack is not None:
        candidate = next(
            (
                item for item in pack.candidates
                if item.canonical_instrument == canonical_instrument
            ),
            None,
        )
        if (
            pack.native_run_identity != run_identity
            or candidate is None
            or candidate.native_assessment_sha256 != assessment.result_sha256
        ):
            return None
    visual = tuple(
        item for item in review.visual_v2_results
        if item.native_run_identity == run_identity
        and item.native_canonical_instrument == canonical_instrument
        and item.native_assessment_sha256 == assessment.result_sha256
    )
    layer2 = next(
        (
            item for item in review.layer2_records
            if item.requirement.native_run_identity == run_identity
            and item.requirement.canonical_instrument == canonical_instrument
            and item.requirement.thesis.native_assessment_sha256
            == assessment.result_sha256
        ),
        None,
    )
    readiness = next(
        (
            item for item in review.readiness_records
            if item.run_identity == run_identity
            and item.canonical_instrument == canonical_instrument
            and item.native_assessment_sha256 == assessment.result_sha256
        ),
        None,
    )
    packages = tuple(
        item for item in review.chart_packages
        if item.binding.native_run_identity == run_identity
        and item.binding.native_assessment_sha256 == assessment.result_sha256
    )
    return NativeAnalysisDetailsProjection(
        assessment, requirement, visual, layer2, readiness, packages, pack
    )


class NativeReviewWorkflow:
    """Prepare and retain Native Review without touching the legacy Review path."""

    def __init__(
        self,
        store: NativeReviewEvidenceStore,
        visual_v2_store: LocalVisualEvidenceV2Store | None = None,
        readiness_store: NativeLayer2ReadinessStore | None = None,
        chart_store: LocalTradingViewEvidenceStore | None = None,
        visual_v2_provider: VisualEvidenceV2Provider | None = None,
        visual_v2_diagnostic_store: LocalVisualEvidenceV2DiagnosticStore | None = None,
        pdf_transport: PdfVisualReviewTransport | None = None,
        trade_plan_store: LocalTradePlanStore | None = None,
        sponsor_decision_store: LocalSponsorDecisionStore | None = None,
        active_lifecycle_service: ActiveTradeLifecycleService | None = None,
        active_lifecycle_monitoring: ActiveLifecycleMonitoringCoordinator | None = None,
        trade_journal_service: TradeJournalService | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            type(store) is not NativeReviewEvidenceStore
            or (
                chart_store is not None
                and type(chart_store) is not LocalTradingViewEvidenceStore
            )
            or (
                visual_v2_provider is not None
                and not isinstance(visual_v2_provider, VisualEvidenceV2Provider)
            )
            or not callable(clock)
            or (
                pdf_transport is not None
                and type(pdf_transport) is not PdfVisualReviewTransport
            )
            or (
                visual_v2_diagnostic_store is not None
                and type(visual_v2_diagnostic_store)
                is not LocalVisualEvidenceV2DiagnosticStore
            )
            or (
                trade_plan_store is not None
                and type(trade_plan_store) is not LocalTradePlanStore
            )
            or (
                sponsor_decision_store is not None
                and type(sponsor_decision_store) is not LocalSponsorDecisionStore
            )
            or (
                active_lifecycle_service is not None
                and type(active_lifecycle_service) is not ActiveTradeLifecycleService
            )
            or (
                active_lifecycle_monitoring is not None
                and type(active_lifecycle_monitoring) is not ActiveLifecycleMonitoringCoordinator
            )
            or (
                trade_journal_service is not None
                and type(trade_journal_service) is not TradeJournalService
            )
        ):
            raise TypeError("NATIVE_REVIEW_WORKFLOW_DEPENDENCY_INVALID")
        self._store = store
        self._visual_v2_store = visual_v2_store or LocalVisualEvidenceV2Store(
            store.root / "visual-v2"
        )
        self._readiness_store = readiness_store or NativeLayer2ReadinessStore(
            store.root / "layer2-readiness-v0"
        )
        self._chart_store = chart_store or LocalTradingViewEvidenceStore()
        self._visual_v2_provider = visual_v2_provider
        self._visual_v2_diagnostic_store = (
            visual_v2_diagnostic_store
            or LocalVisualEvidenceV2DiagnosticStore(
                store.root / "visual-v2-diagnostics"
            )
        )
        self._clock = clock
        self._pdf_transport = pdf_transport
        self._trade_plan_store = trade_plan_store or LocalTradePlanStore(
            store.root / "trade-construction-v0"
        )
        self._sponsor_decision_store = sponsor_decision_store or LocalSponsorDecisionStore(
            store.root / "sponsor-trade-decision-v0"
        )
        self._active_lifecycle = active_lifecycle_service or ActiveTradeLifecycleService(
            LocalActiveTradeLifecycleStore(store.root / "active-trade-lifecycle-v0")
        )
        self._active_lifecycle_monitoring = (
            active_lifecycle_monitoring
            or ActiveLifecycleMonitoringCoordinator(
                self._active_lifecycle, MarketCalendarPublisher(), clock=self._clock,
            )
        )
        self._trade_journal = trade_journal_service or TradeJournalService(
            LocalTradeJournalStore(store.root / "trade-journal-v0")
        )
        self._lock = RLock()
        self._run_identity: str | None = None
        self._requirements: tuple[NativeReviewRequirement, ...] = ()
        self._layer2: dict[str, NativeLayer2ReviewRecord] = {}
        self._reference: dict[str, McxReferenceResult] = {}
        self._visual_v2: dict[tuple[str, str, str], VisualEvidenceV2Response] = {}
        self._readiness: dict[str, NativeLayer2ReadinessRecord] = {}
        self._trade_plans: dict[str, TradePlanRecord] = {}
        self._sponsor_initiations: dict[str, SponsorInitiationResult] = {}
        self._step32_inputs: dict[str, tuple[BusinessJudgment, RiskApproval, CanonicalInstrumentContext]] = {}
        self._analysis: dict[str, NativeReviewAnalysisOutcome] = {}
        self._review_pack: ReviewPackRecord | None = None
        self._answer_imports: tuple[AnswerImportRecord, ...] = ()
        self._review_pack_scope: str | None = None
        self._review_pack_skipped: tuple[tuple[str, str], ...] = ()
        self._refresh_status: str | None = None

    @property
    def evidence_root(self) -> Path:
        """Return the governed root so versioned Review services share one lifecycle."""

        return self._store.root

    def original_chart_bytes(self, revision: object) -> bytes:
        """Read one already-governed chart revision for a versioned Review cycle."""

        return self._chart_store.original_bytes(revision)  # type: ignore[arg-type]

    def set_ux10_lifecycle_event_listener(self, listener) -> None:  # type: ignore[no-untyped-def]
        """Attach UX-10 as a read-only observer of persisted lifecycle events."""

        self._active_lifecycle.set_ux10_event_listener(listener)

    def set_shared_monitoring_hub(self, hub: object) -> None:
        """Share one Provider transport across active-trade and progression watches."""

        self._active_lifecycle_monitoring.set_shared_monitoring_hub(hub)

    def prepare(
        self,
        native_run: NativeDiscoveryRun,
        facts: SameRunMtfFactSnapshot,
    ) -> NativeReviewWorkflowSnapshot:
        requirements = build_native_review_requirements(native_run, facts)
        if not requirements:
            raise ValueError("NATIVE_REVIEW_PROBABLES_UNAVAILABLE")
        with self._lock:
            if self._run_identity is not None:
                if self._run_identity != native_run.run_identity or self._requirements != requirements:
                    raise ValueError("NATIVE_REVIEW_ACTIVE_RUN_IMMUTABLE")
                return self._snapshot_unlocked()
            self._store.retain(requirements)
            self._run_identity = native_run.run_identity
            self._requirements = requirements
            self._refresh_status = "CURRENT REVIEW LOADED"
            return self._snapshot_unlocked()

    def refresh(
        self,
        native_run: NativeDiscoveryRun,
        facts: SameRunMtfFactSnapshot,
    ) -> NativeReviewWorkflowSnapshot:
        """Rebuild only the current Review projection from governed Native evidence."""

        requirements = build_native_review_requirements(native_run, facts)
        if not requirements:
            raise ValueError("NATIVE_REVIEW_PROBABLES_UNAVAILABLE")
        with self._lock:
            if (
                self._run_identity == native_run.run_identity
                and self._requirements == requirements
            ):
                self._refresh_status = "CURRENT REVIEW UNCHANGED"
                return self._snapshot_unlocked()
            self._store.retain(requirements)
            self._run_identity = native_run.run_identity
            self._requirements = requirements
            self._restore_current_pack_unlocked()
            review_pack_id = (
                self._review_pack.review_pack_id
                if self._review_pack is not None
                and self._review_pack.native_run_identity == native_run.run_identity
                else None
            )
            self._reference = {
                item.requirement.mcx_canonical_instrument: item
                for item in self._store.load_reference_results(
                    requirements, review_pack_id=review_pack_id,
                )
            }
            self._visual_v2 = {
                (item.subject_identity, item.timeframe.value, item.chart_revision_sha256): item
                for item in self._visual_v2_store.load_for_requirements(
                    requirements, review_pack_id=review_pack_id,
                )
            }
            self._readiness = {
                item.canonical_instrument: item
                for item in self._readiness_store.load_for_requirements(
                    requirements,
                    visual_evidence_hashes=frozenset(
                        item.evidence_sha256 for item in self._visual_v2.values()
                    ),
                )
            }
            self._trade_plans = {
                item.trade_plan_id: item
                for item in self._trade_plan_store.load_for_requirements(requirements)
            }
            self._restore_sponsor_decisions_unlocked()
            self._layer2.clear()
            self._analysis.clear()
            self._refresh_status = "CURRENT REVIEW REFRESHED"
            return self._snapshot_unlocked()

    def record_refresh_unavailable(self) -> None:
        with self._lock:
            self._refresh_status = (
                "REFRESH UNAVAILABLE · NO VALID CURRENT OPPORTUNITIES STATE"
            )

    def restore(
        self,
        native_run: NativeDiscoveryRun,
        facts: SameRunMtfFactSnapshot,
    ) -> NativeReviewWorkflowSnapshot:
        requirements = self._store.load(native_run, facts)
        with self._lock:
            self._run_identity = native_run.run_identity
            self._requirements = requirements
            self._restore_current_pack_unlocked()
            review_pack_id = (
                self._review_pack.review_pack_id
                if self._review_pack is not None
                and self._review_pack.native_run_identity == native_run.run_identity
                else None
            )
            self._reference = {
                item.requirement.mcx_canonical_instrument: item
                for item in self._store.load_reference_results(
                    requirements, review_pack_id=review_pack_id,
                )
            }
            self._visual_v2 = {
                (item.subject_identity, item.timeframe.value, item.chart_revision_sha256): item
                for item in self._visual_v2_store.load_for_requirements(
                    requirements, review_pack_id=review_pack_id,
                )
            }
            self._readiness = {
                item.canonical_instrument: item
                for item in self._readiness_store.load_for_requirements(
                    requirements,
                    visual_evidence_hashes=frozenset(
                        item.evidence_sha256 for item in self._visual_v2.values()
                    ),
                )
            }
            self._trade_plans = {
                item.trade_plan_id: item
                for item in self._trade_plan_store.load_for_requirements(requirements)
            }
            self._restore_sponsor_decisions_unlocked()
            self._layer2.clear()
            self._analysis.clear()
            self._refresh_status = "CURRENT REVIEW RESTORED"
            return self._snapshot_unlocked()

    def ingest_layer2(
        self,
        evidence: NativeIndependentLayer2Evidence,
    ) -> NativeLayer2ReviewRecord:
        with self._lock:
            requirement = next(
                (
                    item for item in self._requirements
                    if item.canonical_instrument == evidence.canonical_instrument
                ),
                None,
            )
            if requirement is None:
                raise ValueError("NATIVE_REVIEW_REQUIREMENT_UNAVAILABLE")
            record = reconcile_native_layer2(
                requirement,
                evidence,
                self._reference.get(evidence.canonical_instrument),
            )
            current = self._layer2.get(evidence.canonical_instrument)
            if current is not None and current != record:
                raise ValueError("NATIVE_REVIEW_LAYER2_IMMUTABLE")
            self._layer2[evidence.canonical_instrument] = record
            return record

    def snapshot(self) -> NativeReviewWorkflowSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def construct_trade_plan(
        self,
        instrument: str,
        evidence: TradeConstructionEvidencePackage,
        execution_context: CanonicalInstrumentContext,
    ) -> TradePlanRecord:
        """Construct and retain Step-31 geometry for one current ready binding."""

        with self._lock:
            requirement = self._requirement_for(instrument)
            readiness = self._readiness.get(instrument)
            if readiness is None:
                raise ValueError("NATIVE_READINESS_RECORD_UNAVAILABLE")
            record = build_trade_plan(
                requirement,
                readiness,
                evidence,
                execution_context,
                created_at=self._clock(),
            )
            current = self._trade_plans.get(record.trade_plan_id)
            if current is not None:
                return current
            self._trade_plan_store.retain(record)
            self._trade_plans[record.trade_plan_id] = record
            return record

    def bind_step32_inputs(
        self,
        trade_plan_id: str,
        judgment: BusinessJudgment,
        risk: RiskApproval,
        execution_context: CanonicalInstrumentContext,
    ) -> None:
        with self._lock:
            plan = self._trade_plans.get(trade_plan_id)
            if plan is None:
                raise ValueError("TRADE_PLAN_UNAVAILABLE")
            validate_step32_inputs(
                plan, judgment, risk, execution_context,
                current_trade_plan_id=trade_plan_id, validated_at=self._clock(),
            )
            self._step32_inputs[trade_plan_id] = (judgment, risk, execution_context)

    def bind_operability_inputs(
        self,
        plan: TradePlanRecord,
        risk_permission: RiskPermissionV1,
        execution_context: CanonicalInstrumentContext,
    ) -> tuple[BusinessJudgment, RiskApproval]:
        """Adapt current commissioned Risk truth to the existing Sponsor boundary."""

        if type(plan) is not TradePlanRecord or type(risk_permission) is not RiskPermissionV1:
            raise TypeError("OPERABILITY_STEP32_INPUT_INVALID")
        with self._lock:
            requirement = self._requirement_for(plan.canonical_instrument)
            if (
                plan.native_run_identity != requirement.native_run_identity
                or plan.native_assessment_sha256
                != requirement.thesis.native_assessment_sha256
                or risk_permission.trade_plan_id != plan.trade_plan_id
                or risk_permission.trade_plan_sha256 != plan.integrity_hash
                or not risk_permission.current
            ):
                raise ValueError("OPERABILITY_STEP32_BINDING_INVALID")
            if risk_permission.state.value == "RISK_CONSTRAINED":
                # V1 constraints are reason identities, not enforceable quantities.
                raise ValueError("RISK_CONSTRAINT_EXECUTION_DETAIL_UNAVAILABLE")
            judgment = create_trade_plan_business_judgment(
                plan,
                validation_identity=plan.readiness_record_identity,
                created_at=self._clock(),
            )
            risk = record_trade_plan_risk_result(
                plan,
                judgment,
                risk_permission.state,
                reason="_".join(risk_permission.reason_codes),
                evaluated_at=risk_permission.evaluated_at,
            )
            self._trade_plan_store.retain(plan)
            self._trade_plans[plan.trade_plan_id] = plan
            validate_step32_inputs(
                plan,
                judgment,
                risk,
                execution_context,
                current_trade_plan_id=plan.trade_plan_id,
                validated_at=self._clock(),
            )
            self._step32_inputs[plan.trade_plan_id] = (
                judgment, risk, execution_context
            )
            return judgment, risk

    def initiate_sponsor_decision(
        self,
        trade_plan_id: str,
        choice: SponsorTradeChoice,
        *,
        actual_live_entry=None,  # type: ignore[no-untyped-def]
        live_lots: int | None = None,
    ) -> SponsorInitiationResult:
        with self._lock:
            existing = self._sponsor_initiations.get(trade_plan_id)
            if existing is not None:
                if existing.decision is None or existing.decision.decision is not choice:
                    raise ValueError("SPONSOR_DECISION_ALREADY_FINAL")
                return existing
            plan = self._trade_plans.get(trade_plan_id)
            inputs = self._step32_inputs.get(trade_plan_id)
            if plan is None or inputs is None:
                raise ValueError("STEP32_INPUTS_UNAVAILABLE")
            judgment, risk, context = inputs
            result = initiate_native_sponsor_decision(
                plan, judgment, risk, context, choice,
                current_trade_plan_id=trade_plan_id, decided_at=self._clock(),
                actual_live_entry=actual_live_entry, live_lots=live_lots,
            )
            if result.decision is None:
                return result
            retained = self._sponsor_decision_store.retain(result)
            self._sponsor_initiations[trade_plan_id] = retained
            self._active_lifecycle.register(retained, plan)
            self._reconcile_journal_unlocked()
            return retained

    def record_lifecycle_observation(
        self,
        position_id: str,
        observation: GovernedLifecycleObservation,
    ):
        """Apply one already-governed Kite observation to a Native position."""

        result = self._active_lifecycle.observe(position_id, observation)
        with self._lock:
            self._reconcile_journal_unlocked()
        return result

    def attach_lifecycle_monitoring(
        self,
        position_id: str,
        capability: object,
        instrument: InstrumentRecord,
    ) -> None:
        self._active_lifecycle_monitoring.attach(position_id, capability, instrument)

    def detach_lifecycle_monitoring(self, position_id: str) -> None:
        self._active_lifecycle_monitoring.detach(position_id)

    @property
    def active_monitoring_count(self) -> int:
        """Return process-local active subscriptions without exposing provider state."""

        return len(self._active_lifecycle_monitoring.active_position_ids)

    def lifecycle_monitoring_active(self, position_id: str) -> bool:
        return position_id in self._active_lifecycle_monitoring.active_position_ids

    @property
    def active_lifecycle_monitoring_ids(self) -> tuple[str, ...]:
        return self._active_lifecycle_monitoring.active_position_ids

    def close(self) -> None:
        """Release process-owned monitoring without mutating retained evidence."""

        self._active_lifecycle_monitoring.close()

    def restore_lifecycle_monitoring(self, capability: object, instrument_resolver):  # type: ignore[no-untyped-def]
        return self._active_lifecycle_monitoring.restore(capability, instrument_resolver)

    def exit_paper_position(
        self,
        position_id: str,
        observation: GovernedLifecycleObservation,
    ) -> TradeClosureRecord:
        closure = self._active_lifecycle.manual_paper_exit(position_id, observation)
        with self._lock:
            self._reconcile_journal_unlocked()
        return closure

    def exit_paper_position_current(self, position_id: str) -> TradeClosureRecord:
        closure = self._active_lifecycle.manual_paper_exit_current(position_id)
        with self._lock:
            self._reconcile_journal_unlocked()
        return closure

    def record_live_exit(
        self,
        position_id: str,
        *,
        actual_exit,
        exit_reason: TradeExitReason,
    ) -> TradeClosureRecord | None:
        closure = self._active_lifecycle.record_live_exit(
            position_id,
            actual_exit=actual_exit,
            exit_timestamp=self._clock(),
            reason=exit_reason,
        )
        if closure is not None:
            with self._lock:
                self._reconcile_journal_unlocked()
        return closure

    def journal_snapshot(self) -> TradeJournalSnapshot:
        with self._lock:
            self._reconcile_journal_unlocked()
            return self._trade_journal.snapshot()

    def _reconcile_journal_unlocked(self) -> TradeJournalSnapshot:
        return self._trade_journal.reconcile(
            tuple(self._trade_plans.values()),
            tuple(self._readiness.values()),
            tuple(self._sponsor_initiations.values()),
            self._active_lifecycle.snapshot(),
        )

    def _restore_sponsor_decisions_unlocked(self) -> None:
        values = self._sponsor_decision_store.load_for_plans(tuple(self._trade_plans.values()))
        self._sponsor_initiations = {
            item.decision.trade_plan_id: item for item in values if item.decision is not None
        }

    def upload_chart(
        self,
        *,
        instrument: str,
        content_type: str,
        original_bytes: bytes,
        subject_kind: VisualEvidenceSubjectKind = VisualEvidenceSubjectKind.NATIVE,
    ) -> StoredChartRevision:
        """Retain one Native-bound revision without a legacy assessment identity."""

        with self._lock:
            requirement = self._requirement_for(instrument)
            if instrument in self._readiness:
                raise ValueError("NATIVE_REVIEW_ALREADY_FINALIZED")
            binding = self._binding_for(requirement, subject_kind)
            revision = self._chart_store.retain_native_upload(
                binding,
                selected_instrument=instrument,
                content_type=content_type,
                original_bytes=original_bytes,
            )
            if (
                subject_kind is VisualEvidenceSubjectKind.NATIVE
                and requirement.mcx_reference is not None
            ):
                self._chart_store.bind_shared_native_revision(
                    self._binding_for(
                        requirement, VisualEvidenceSubjectKind.REFERENCE
                    ),
                    selected_instrument=instrument,
                    source_revision=revision,
                )
            return revision

    def remove_chart(
        self,
        *,
        instrument: str,
        subject_kind: VisualEvidenceSubjectKind = VisualEvidenceSubjectKind.NATIVE,
    ) -> None:
        with self._lock:
            requirement = self._requirement_for(instrument)
            if instrument in self._readiness:
                raise ValueError("NATIVE_REVIEW_ALREADY_FINALIZED")
            self._chart_store.remove_native_active_chart(
                self._binding_for(requirement, subject_kind),
                selected_instrument=instrument,
            )
            if (
                subject_kind is VisualEvidenceSubjectKind.NATIVE
                and requirement.mcx_reference is not None
            ):
                self._chart_store.remove_native_active_chart(
                    self._binding_for(
                        requirement, VisualEvidenceSubjectKind.REFERENCE
                    ),
                    selected_instrument=instrument,
                )

    def active_chart(
        self,
        *,
        instrument: str,
        sha256: str,
        subject_kind: VisualEvidenceSubjectKind = VisualEvidenceSubjectKind.NATIVE,
    ) -> tuple[StoredChartRevision, bytes]:
        with self._lock:
            requirement = self._requirement_for(instrument)
            package = self._chart_store.native_package_for(
                self._binding_for(requirement, subject_kind)
            )
            revision = next(
                (
                    item for item in package.active_revisions
                    if item.sha256 == sha256
                ),
                None,
            )
            if revision is None:
                raise ValueError("NATIVE_TRADINGVIEW_ACTIVE_REVISION_INVALID")
            return revision, self._chart_store.original_bytes(revision)

    def analysis_binding_valid(self, instrument: str) -> bool:
        with self._lock:
            try:
                requirement = self._requirement_for(instrument)
            except ValueError:
                return False
            packages = [
                self._chart_store.native_package_for(
                    self._binding_for(
                        requirement, VisualEvidenceSubjectKind.NATIVE
                    )
                )
            ]
            if requirement.mcx_reference is not None:
                packages.append(
                    self._chart_store.native_package_for(
                        self._binding_for(
                            requirement, VisualEvidenceSubjectKind.REFERENCE
                        )
                    )
                )
            return all(
                not package.missing_required_timeframes
                and all(
                    revision.run_identity == requirement.native_run_identity
                    and revision.swing_analysis_run_identity
                    == requirement.native_run_identity
                    and revision.canonical_instrument
                    == requirement.canonical_instrument
                    for revision in package.active_revisions
                )
                for package in packages
            )

    def analyze(self, instrument: str) -> NativeLayer2ReadinessRecord:
        """Run one candidate independently and retain only sanitized UI state."""

        with self._lock:
            self._requirement_for(instrument)
            current = self._readiness.get(instrument)
            if current is not None:
                self._analysis[instrument] = NativeReviewAnalysisOutcome(
                    instrument,
                    NativeReviewAnalysisState.READY_FOR_REVIEW,
                    "SUCCESS",
                    "READINESS RECORD AVAILABLE",
                )
                return current
            self._analysis[instrument] = NativeReviewAnalysisOutcome(
                instrument,
                NativeReviewAnalysisState.ANALYZING,
                "IN_PROGRESS",
                "ANALYSIS IN PROGRESS",
            )
            _LOG.info("native_review workflow_started instrument=%s", instrument)
        try:
            result = self._analyze_once(instrument)
        except Exception as error:
            reason = _safe_analysis_failure(error)
            with self._lock:
                self._analysis[instrument] = NativeReviewAnalysisOutcome(
                    instrument,
                    NativeReviewAnalysisState.ANALYSIS_FAILED,
                    "FAILED",
                    reason,
                )
            _LOG.warning(
                "native_review workflow_failed instrument=%s exception=%s reason=%s",
                instrument,
                type(error).__name__,
                reason.replace(" ", "_"),
            )
            raise
        with self._lock:
            self._analysis[instrument] = NativeReviewAnalysisOutcome(
                instrument,
                NativeReviewAnalysisState.READY_FOR_REVIEW,
                "SUCCESS",
                "READINESS RECORD AVAILABLE",
            )
            _LOG.info("native_review workflow_completed instrument=%s", instrument)
        return result

    def record_analysis_failure(self, instrument: str, reason: str) -> None:
        """Publish one sanitized preflight failure for an existing Native thesis."""

        if not reason or len(reason) > 96:
            raise ValueError("NATIVE_REVIEW_FAILURE_REASON_INVALID")
        with self._lock:
            self._requirement_for(instrument)
            self._analysis[instrument] = NativeReviewAnalysisOutcome(
                instrument,
                NativeReviewAnalysisState.ANALYSIS_FAILED,
                "FAILED",
                reason,
            )

    def analyze_all(self) -> tuple[NativeReviewAnalysisOutcome, ...]:
        """Analyze every chart-complete candidate without cross-candidate failure."""

        outcomes = []
        for requirement in self.snapshot().requirements:
            instrument = requirement.canonical_instrument
            if not self.analysis_binding_valid(instrument):
                outcome = NativeReviewAnalysisOutcome(
                    instrument,
                    NativeReviewAnalysisState.NOT_ANALYZED,
                    "SKIPPED",
                    "VALID COMPOSITE CHART REQUIRED",
                )
                with self._lock:
                    self._analysis[instrument] = outcome
                outcomes.append(outcome)
                continue
            try:
                self.analyze(instrument)
            except Exception:
                with self._lock:
                    outcomes.append(self._analysis[instrument])
            else:
                with self._lock:
                    outcomes.append(self._analysis[instrument])
        return tuple(outcomes)

    def generate_review_pack(self, instrument: str | None = None) -> ReviewPackRecord:
        """Generate a new immutable individual or eligible A-Z PDF without OpenAI."""

        with self._lock:
            if self._pdf_transport is None:
                raise PdfReviewTransportError("PDF_REVIEW_TRANSPORT_UNAVAILABLE")
            if not self._requirements:
                raise PdfReviewTransportError("NATIVE_REVIEW_PROBABLES_UNAVAILABLE")
            if instrument is not None:
                self._requirement_for(instrument)
            all_packages = tuple(
                (
                    requirement,
                    self._chart_store.native_package_for(
                        self._binding_for(
                            requirement, VisualEvidenceSubjectKind.NATIVE
                        )
                    ),
                )
                for requirement in self._requirements
            )
            eligible = tuple(
                (requirement, package)
                for requirement, package in all_packages
                if not package.missing_required_timeframes
                and len(package.active_revisions) == 1
            )
            if instrument is not None:
                eligible = tuple(
                    item for item in eligible
                    if item[0].canonical_instrument == instrument
                )
                if not eligible:
                    raise PdfReviewTransportError(
                        f"REQUIRED_CHART_MISSING:{instrument}"
                    )
                skipped: tuple[tuple[str, str], ...] = ()
                scope = "INDIVIDUAL"
            else:
                skipped = tuple(sorted(
                    (
                        requirement.canonical_instrument,
                        "CHART REQUIRED",
                    )
                    for requirement, package in all_packages
                    if package.missing_required_timeframes
                    or len(package.active_revisions) != 1
                ))
                scope = "ALL_ELIGIBLE"
            if not eligible:
                raise PdfReviewTransportError("REQUIRED_CHART_MISSING")
            requirements = tuple(item[0] for item in eligible)
            packages = tuple(item[1] for item in eligible)
            revisions = {
                revision.sha256: revision
                for package in packages
                for revision in package.active_revisions
            }
            transport = self._pdf_transport
        record = transport.generate(
            requirements,
            packages,
            lambda digest: self._chart_store.original_bytes(revisions[digest]),
        )
        with self._lock:
            if self._run_identity != record.native_run_identity:
                raise PdfReviewTransportError("NATIVE_REVIEW_ACTIVE_RUN_SUPERSEDED")
            selection = transport.record_store.select_current(
                record, scope=scope, skipped=skipped
            )
            self._review_pack = record
            self._review_pack_scope = selection.scope
            self._review_pack_skipped = selection.skipped
            self._answer_imports = ()
            return record

    def upload_review_answer(
        self,
    ) -> tuple[AnswerImportRecord, tuple[NativeLayer2ReadinessRecord, ...]]:
        """Validate one governed Answer PDF and reuse existing V2/Readiness logic."""

        with self._lock:
            if self._pdf_transport is None:
                raise PdfReviewTransportError("PDF_REVIEW_TRANSPORT_UNAVAILABLE")
            if self._review_pack is None:
                raise PdfReviewTransportError("REVIEW_PACK_UNAVAILABLE")
            if not self._review_pack_is_current_unlocked():
                raise PdfReviewTransportError("REVIEW_PACK_SUPERSEDED")
            transport = self._pdf_transport
            record = self._review_pack
            requirements = {
                item.canonical_instrument: item for item in self._requirements
            }
            packages = {
                item.canonical_instrument: self._chart_store.native_package_for(
                    self._binding_for(item, VisualEvidenceSubjectKind.NATIVE)
                )
                for item in self._requirements
            }
        try:
            answer = transport.find_and_validate_answer(record)
        except PdfReviewTransportError as error:
            expected_path = (
                transport.configuration.answer_directory
                / record.expected_answer_filename
            )
            rejected = transport.record_rejection(record, expected_path, str(error))
            with self._lock:
                self._answer_imports = (*self._answer_imports, rejected)
            raise
        if not answer.candidates:
            imported = next(
                item
                for item in transport.record_store.load_answer_imports(
                    record.review_pack_id
                )
                if item.answer_pdf_sha256 == answer.answer_sha256 and item.consumed
            )
            return imported, tuple(
                self._readiness[item.canonical_instrument]
                for item in self._requirements
                if item.canonical_instrument in self._readiness
            )

        bound: list[tuple[VisualEvidenceV2Request, VisualEvidenceV2Response]] = []
        reference_results: dict[str, McxReferenceResult] = {}
        try:
            for candidate in answer.candidates:
                requirement = requirements[candidate.canonical_instrument]
                package = packages[candidate.canonical_instrument]
                revision = next(
                    (
                        item for item in package.active_revisions
                        if item.sha256 == candidate.chart_revision_sha256
                    ),
                    None,
                )
                if revision is None:
                    raise PdfReviewTransportError("CHART_REVISION_MISMATCH")
                original = self._chart_store.original_bytes(revision)
                for response in (
                    *candidate.responses,
                    *candidate.reference_responses,
                ):
                    subject_kind = response.subject_kind
                    request = build_visual_evidence_v2_request(
                        requirement,
                        timeframe=response.timeframe,
                        observation_boundary=response.observation_boundary,
                        chart_identity=response.chart_identity,
                        content_type=revision.content_type,
                        original_image=original,
                        request_timestamp=response.request_timestamp,
                        subject_kind=subject_kind,
                    )
                    response.validate_binding(request)
                    bound.append((request, response))
                if candidate.reference_responses:
                    reference = requirement.mcx_reference
                    if reference is None:
                        raise PdfReviewTransportError(
                            "REFERENCE_BINDING_MISMATCH"
                        )
                    reference_results[candidate.canonical_instrument] = (
                        McxReferenceResult(
                            reference,
                            McxReferenceStatus.RECEIVED,
                            McxReferenceEvidenceState.UNAVAILABLE,
                            candidate.chart_revision_sha256,
                            sha256(
                                "\x1f".join(
                                    item.evidence_sha256
                                    for item in candidate.reference_responses
                                ).encode("utf-8")
                            ).hexdigest(),
                            tuple(
                                (item.timeframe.value, item.observation_boundary)
                                for item in candidate.reference_responses
                            ),
                            tuple(
                                dict.fromkeys(
                                    value
                                    for item in candidate.reference_responses
                                    for value in item.source_provenance
                                )
                            ),
                            "SAME_RUN_REFERENCE_BOUND",
                            "REFERENCE_VISUAL_EVIDENCE_RECEIVED_RECONCILIATION_PENDING",
                        )
                    )
        except (KeyError, ValueError) as error:
            reason = (
                str(error)
                if isinstance(error, PdfReviewTransportError)
                else "ANSWER_BINDING_INVALID"
            )
            rejected = transport.record_rejection(record, answer.answer_path, reason)
            with self._lock:
                self._answer_imports = (*self._answer_imports, rejected)
            raise PdfReviewTransportError(reason) from error

        # Validation is complete. Preserve prior immutable cycles on disk while
        # replacing only the current Review projection for these candidates.
        candidate_names = {
            item.canonical_instrument for item in answer.candidates
        }
        with self._lock:
            previous_projection = (
                dict(self._visual_v2), dict(self._reference),
                dict(self._layer2), dict(self._readiness), dict(self._analysis),
            )
            self._visual_v2 = {
                key: value for key, value in self._visual_v2.items()
                if value.native_canonical_instrument not in candidate_names
            }
            for instrument in candidate_names:
                self._reference.pop(instrument, None)
                self._layer2.pop(instrument, None)
                self._readiness.pop(instrument, None)
                self._analysis.pop(instrument, None)
        try:
            # No governed evidence is written before the entire Answer passes.
            for request, response in bound:
                self.ingest_visual_v2(request, response)
            for result in reference_results.values():
                self.ingest_reference(result)

            readiness = []
            for candidate in answer.candidates:
                requirement = requirements[candidate.canonical_instrument]
                layer2 = _visual_layer2_evidence(requirement, candidate.responses)
                self.ingest_layer2(layer2)
                readiness.append(
                    self.ingest_readiness(layer2, created_at=self._now())
                )
                with self._lock:
                    self._analysis[candidate.canonical_instrument] = (
                        NativeReviewAnalysisOutcome(
                            candidate.canonical_instrument,
                            NativeReviewAnalysisState.READY_FOR_REVIEW,
                            "SUCCESS",
                            "READINESS RECORD AVAILABLE",
                        )
                    )
        except Exception:
            with self._lock:
                (
                    self._visual_v2, self._reference, self._layer2,
                    self._readiness, self._analysis,
                ) = previous_projection
            raise
        imported = transport.record_import(
            record,
            answer,
            tuple(response.evidence_sha256 for _, response in bound),
        )
        with self._lock:
            self._answer_imports = (*self._answer_imports, imported)
        return imported, tuple(readiness)

    def _analyze_once(self, instrument: str) -> NativeLayer2ReadinessRecord:
        """Run the governed V2→conditions→Readiness chain for one Native thesis."""

        with self._lock:
            requirement = self._requirement_for(instrument)
            current = self._readiness.get(instrument)
            if current is not None:
                return current
            if self._visual_v2_provider is None:
                raise ValueError("NATIVE_VISUAL_V2_PROVIDER_UNAVAILABLE")
            if not self.analysis_binding_valid(instrument):
                raise ValueError("NATIVE_TRADINGVIEW_REQUIRED_CHARTS_MISSING")
            packages = [
                self._chart_store.native_package_for(
                    self._binding_for(
                        requirement, VisualEvidenceSubjectKind.NATIVE
                    )
                )
            ]
            if requirement.mcx_reference is not None:
                packages.append(
                    self._chart_store.native_package_for(
                        self._binding_for(
                            requirement, VisualEvidenceSubjectKind.REFERENCE
                        )
                    )
                )
            provider = self._visual_v2_provider
        responses: list[VisualEvidenceV2Response] = []
        for package in packages:
            subject_kind = VisualEvidenceSubjectKind(
                "NATIVE_ANALYTICAL_SUBJECT"
                if package.binding.subject_kind == "NATIVE"
                else "REFERENCE_EVIDENCE_SUBJECT"
            )
            revision = package.active_revisions[0]
            for timeframe in package.binding.required_timeframes:
                visual_timeframe = _VISUAL_TIMEFRAME[timeframe]
                chart_identity = (
                    f"{package.binding.chart_subject_identity}:4-CHART"
                )
                with self._lock:
                    existing = self._visual_v2.get((
                        package.binding.chart_subject_identity,
                        visual_timeframe.value,
                        revision.sha256,
                    ))
                if existing is not None:
                    if (
                        existing.native_run_identity
                        != requirement.native_run_identity
                        or existing.native_assessment_sha256
                        != requirement.thesis.native_assessment_sha256
                        or existing.native_canonical_instrument
                        != requirement.canonical_instrument
                        or existing.subject_kind is not subject_kind
                        or existing.timeframe is not visual_timeframe
                        or existing.observation_boundary
                        != package.binding.observation_boundary(timeframe)
                        or existing.chart_identity != chart_identity
                        or existing.chart_revision_sha256 != revision.sha256
                    ):
                        raise ValueError("VISUAL_V2_RETRY_BINDING_INVALID")
                    responses.append(existing)
                    _LOG.info(
                        "native_review visual_result_reused instrument=%s timeframe=%s revision=%s",
                        instrument,
                        timeframe.value,
                        revision.sha256,
                    )
                    continue
                _LOG.info(
                    "native_review openai_request_attempted instrument=%s timeframe=%s revision=%s",
                    instrument,
                    timeframe.value,
                    revision.sha256,
                )
                request = build_visual_evidence_v2_request(
                    requirement,
                    timeframe=visual_timeframe,
                    observation_boundary=package.binding.observation_boundary(
                        timeframe
                    ),
                    chart_identity=chart_identity,
                    content_type=revision.content_type,
                    original_image=self._chart_store.original_bytes(revision),
                    request_timestamp=self._now(),
                    subject_kind=subject_kind,
                )
                response = provider.analyze(request)
                try:
                    self.ingest_visual_v2(request, response)
                except ValueError as error:
                    code = str(error)
                    self._visual_v2_diagnostic_store.retain(
                        VisualEvidenceV2ValidationDiagnostic(
                            native_run_identity=requirement.native_run_identity,
                            canonical_instrument=requirement.canonical_instrument,
                            timeframe=visual_timeframe,
                            chart_revision_sha256=revision.sha256,
                            model_identity=response.model_identity,
                            attempt=1,
                            api_request_completed=True,
                            input_tokens=0,
                            output_tokens=0,
                            total_tokens=0,
                            response_status="completed",
                            validation_stage=(
                                VisualEvidenceV2ValidationStage.PERSISTENCE_BINDING
                            ),
                            validation_error_code=(
                                code
                                if code.isascii()
                                and code.replace("_", "").isalnum()
                                else "VISUAL_V2_PERSISTENCE_BINDING_INVALID"
                            ),
                            structural_path="response.binding",
                            expected_constraint=(
                                "exact immutable same-run request/evidence binding"
                            ),
                            received_shape="binding rejected",
                            retry_disposition="FAILED_FINAL",
                            recorded_at=self._now(),
                        )
                    )
                    raise
                _LOG.info(
                    "native_review visual_result_persisted instrument=%s timeframe=%s revision=%s",
                    instrument,
                    timeframe.value,
                    revision.sha256,
                )
                responses.append(response)
        with self._lock:
            if requirement not in self._requirements:
                raise ValueError("NATIVE_REVIEW_ACTIVE_RUN_SUPERSEDED")
            reference = tuple(
                item for item in responses
                if item.subject_kind is VisualEvidenceSubjectKind.REFERENCE
            )
            if requirement.mcx_reference is not None and reference:
                result = McxReferenceResult(
                    requirement.mcx_reference,
                    McxReferenceStatus.UNAVAILABLE,
                    McxReferenceEvidenceState.UNAVAILABLE,
                    reference[0].chart_revision_sha256,
                    reference[0].evidence_sha256,
                    tuple(
                        (item.timeframe.value, item.observation_boundary)
                        for item in reference
                    ),
                    tuple(
                        dict.fromkeys(
                            value
                            for item in reference
                            for value in item.source_provenance
                        )
                    ),
                    "SAME_RUN_REFERENCE_BOUND",
                    "REFERENCE_VISUAL_EVIDENCE_REQUIRES_TYPED_RECONCILIATION",
                )
                self.ingest_reference(result)
            native = tuple(
                item for item in responses
                if item.subject_kind is VisualEvidenceSubjectKind.NATIVE
            )
            layer2 = _visual_layer2_evidence(requirement, native)
            self.ingest_layer2(layer2)
            _LOG.info("native_review readiness_invoked instrument=%s", instrument)
            return self.ingest_readiness(
                layer2, created_at=self._now()
            )

    def step31_eligible_readiness(
        self,
    ) -> tuple[NativeLayer2ReadinessRecord, ...]:
        """Expose only frozen Native READY records; construct no Step-31 geometry."""

        with self._lock:
            return tuple(
                self._readiness[item.canonical_instrument]
                for item in self._requirements
                if item.canonical_instrument in self._readiness
                and self._readiness[item.canonical_instrument].step31_eligible
            )

    def ingest_visual_v2(
        self,
        request: VisualEvidenceV2Request,
        response: VisualEvidenceV2Response,
    ) -> VisualEvidenceV2Response:
        with self._lock:
            if request.requirement not in self._requirements:
                raise ValueError("VISUAL_V2_NATIVE_REVIEW_BINDING_INVALID")
            response.validate_binding(request)
            key = (
                response.subject_identity,
                response.timeframe.value,
                response.chart_revision_sha256,
            )
            current = self._visual_v2.get(key)
            if current is not None and current != response:
                raise ValueError("VISUAL_V2_EVIDENCE_IMMUTABLE")
            self._visual_v2_store.retain(request, response)
            self._visual_v2[key] = response
            return response

    def ingest_readiness(
        self,
        evidence: NativeIndependentLayer2Evidence,
        *,
        created_at: datetime,
        inputs: NativeConditionInputs = NativeConditionInputs(),
    ) -> NativeLayer2ReadinessRecord:
        """Reconcile the exact retained evidence package under frozen Native V0."""

        with self._lock:
            requirement = next(
                (
                    item for item in self._requirements
                    if item.canonical_instrument == evidence.canonical_instrument
                ),
                None,
            )
            if requirement is None:
                raise ValueError("NATIVE_REVIEW_REQUIREMENT_UNAVAILABLE")
            visual = tuple(
                item for item in self._visual_v2.values()
                if item.native_run_identity == requirement.native_run_identity
                and item.native_assessment_sha256
                == requirement.thesis.native_assessment_sha256
            )
            record = create_native_readiness_record(
                requirement,
                evidence,
                visual,
                created_at=created_at,
                reference=self._reference.get(evidence.canonical_instrument),
                inputs=inputs,
            )
            current = self._readiness.get(evidence.canonical_instrument)
            if current is not None and current != record:
                raise ValueError("NATIVE_LAYER2_READINESS_RECORD_IMMUTABLE")
            self._readiness_store.retain(record)
            self._readiness[evidence.canonical_instrument] = record
            return record

    def ingest_reference(self, result: McxReferenceResult) -> McxReferenceResult:
        with self._lock:
            if result.requirement not in tuple(
                item.mcx_reference for item in self._requirements
                if item.mcx_reference is not None
            ):
                raise ValueError("MCX_REFERENCE_ORPHANED_EVIDENCE_REJECTED")
            current = self._reference.get(result.requirement.mcx_canonical_instrument)
            if current is not None and current != result:
                raise ValueError("MCX_REFERENCE_RESULT_IMMUTABLE")
            self._store.retain_reference_result(result)
            self._reference[result.requirement.mcx_canonical_instrument] = result
            current_layer2 = self._layer2.get(result.requirement.mcx_canonical_instrument)
            if current_layer2 is not None:
                self._layer2[result.requirement.mcx_canonical_instrument] = reconcile_native_layer2(
                    current_layer2.requirement,
                    current_layer2.evidence,
                    result,
                )
            return result

    def _requirement_for(self, instrument: str) -> NativeReviewRequirement:
        requirement = next(
            (
                item for item in self._requirements
                if item.canonical_instrument == instrument
            ),
            None,
        )
        if requirement is None:
            raise ValueError("NATIVE_REVIEW_REQUIREMENT_UNAVAILABLE")
        return requirement

    @staticmethod
    def _binding_for(
        requirement: NativeReviewRequirement,
        subject_kind: VisualEvidenceSubjectKind,
    ) -> NativeChartReviewBinding:
        if subject_kind is VisualEvidenceSubjectKind.NATIVE:
            timeframes = (
                ChartTimeframe.WEEKLY,
                ChartTimeframe.DAILY,
                ChartTimeframe.FOUR_HOUR,
                ChartTimeframe.ONE_HOUR,
            )
            identity = requirement.canonical_instrument
            kind = "NATIVE"
        else:
            if requirement.mcx_reference is None:
                raise ValueError("MCX_REFERENCE_NOT_REQUIRED")
            timeframes = (ChartTimeframe.DAILY,)
            identity = requirement.mcx_reference.reference_symbol
            kind = "REFERENCE"
        boundaries = tuple(
            (
                timeframe,
                next(
                    item.observation_boundary
                    for item in requirement.thesis.timeframe_facts
                    if item.timeframe is _FACTUAL_TIMEFRAME[timeframe]
                ),
            )
            for timeframe in timeframes
        )
        return NativeChartReviewBinding(
            native_run_identity=requirement.native_run_identity,
            native_assessment_sha256=(
                requirement.thesis.native_assessment_sha256
            ),
            canonical_instrument=requirement.canonical_instrument,
            direction=requirement.thesis.direction.value,
            opportunity_identity=(
                requirement.thesis.opportunity_identity.value
            ),
            subject_kind=kind,
            chart_subject_identity=identity,
            observation_boundaries=boundaries,
            required_timeframes=timeframes,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError("NATIVE_REVIEW_CLOCK_INVALID")
        return value

    def _restore_current_pack_unlocked(self) -> None:
        self._review_pack = None
        self._review_pack_scope = None
        self._review_pack_skipped = ()
        self._answer_imports = ()
        if self._pdf_transport is None:
            return
        current = self._pdf_transport.record_store.load_current()
        if current is None:
            return
        record, selection = current
        self._review_pack = record
        self._review_pack_scope = selection.scope
        self._review_pack_skipped = selection.skipped
        self._answer_imports = self._pdf_transport.record_store.load_answer_imports(
            record.review_pack_id
        )

    def _review_pack_is_current_unlocked(self) -> bool:
        record = self._review_pack
        if (
            record is None
            or self._run_identity != record.native_run_identity
            or self._review_pack_scope is None
        ):
            return False
        requirements = {
            item.canonical_instrument: item for item in self._requirements
        }
        candidate_names = {
            item.canonical_instrument for item in record.candidates
        }
        for candidate in record.candidates:
            requirement = requirements.get(candidate.canonical_instrument)
            if (
                requirement is None
                or requirement.thesis.native_assessment_sha256
                != candidate.native_assessment_sha256
            ):
                return False
            package = self._chart_store.native_package_for(
                self._binding_for(
                    requirement, VisualEvidenceSubjectKind.NATIVE
                )
            )
            if (
                package.missing_required_timeframes
                or len(package.active_revisions) != 1
                or package.active_revisions[0].sha256
                != candidate.chart_revision_sha256
                or package.binding.chart_subject_identity
                != candidate.chart_identity
            ):
                return False
        if self._review_pack_scope == "ALL_ELIGIBLE":
            eligible = {
                requirement.canonical_instrument
                for requirement in self._requirements
                if (
                    lambda package: (
                        not package.missing_required_timeframes
                        and len(package.active_revisions) == 1
                    )
                )(
                    self._chart_store.native_package_for(
                        self._binding_for(
                            requirement,
                            VisualEvidenceSubjectKind.NATIVE,
                        )
                    )
                )
            }
            if eligible != candidate_names:
                return False
        return True

    def _snapshot_unlocked(self) -> NativeReviewWorkflowSnapshot:
        if self._run_identity is None:
            return NativeReviewWorkflowSnapshot(
                NativeReviewRunState.NOT_PREPARED,
                None,
                (),
                (),
                (),
                (),
                (),
                (),
                (),
                (),
                refresh_status=self._refresh_status,
                active_lifecycle=self._active_lifecycle.snapshot(),
                trade_journal=self._trade_journal.snapshot(),
                risk_records=(),
            )
        return NativeReviewWorkflowSnapshot(
            NativeReviewRunState.REVIEW_REQUIRED,
            self._run_identity,
            self._requirements,
            tuple(
                self._layer2[item.canonical_instrument]
                for item in self._requirements
                if item.canonical_instrument in self._layer2
            ),
            tuple(
                package
                for requirement in self._requirements
                for package in (
                    self._chart_store.native_package_for(
                        self._binding_for(
                            requirement, VisualEvidenceSubjectKind.NATIVE
                        )
                    ),
                    *(
                        (
                            self._chart_store.native_package_for(
                                self._binding_for(
                                    requirement,
                                    VisualEvidenceSubjectKind.REFERENCE,
                                )
                            ),
                        )
                        if requirement.mcx_reference is not None
                        else ()
                    ),
                )
            ),
            tuple(
                self._reference[item.canonical_instrument]
                for item in self._requirements
                if item.canonical_instrument in self._reference
            ),
            tuple(self._visual_v2[key] for key in sorted(self._visual_v2)),
            tuple(
                self._readiness[item.canonical_instrument]
                for item in self._requirements
                if item.canonical_instrument in self._readiness
            ),
            tuple(
                self._analysis[item.canonical_instrument]
                for item in self._requirements
                if item.canonical_instrument in self._analysis
            ),
            self._visual_v2_diagnostic_store.load_for_run(self._run_identity),
            self._review_pack,
            self._answer_imports,
            self._review_pack_scope,
            self._review_pack_skipped,
            not self._review_pack_is_current_unlocked()
            if self._review_pack is not None else False,
            self._refresh_status,
            tuple(
                sorted(
                    self._trade_plans.values(),
                    key=lambda item: (item.canonical_instrument, item.created_at, item.trade_plan_id),
                )
            ),
            tuple(
                self._sponsor_initiations[key]
                for key in sorted(self._sponsor_initiations)
            ),
            tuple(sorted(
                key for key in self._step32_inputs
                if key not in self._sponsor_initiations
            )),
            self._active_lifecycle.snapshot(),
            self._reconcile_journal_unlocked(),
            tuple(
                self._step32_inputs[key][1]
                for key in sorted(self._step32_inputs)
            ),
        )


_FACTUAL_TIMEFRAME = {
    ChartTimeframe.WEEKLY: FactualTimeframe.WEEKLY,
    ChartTimeframe.DAILY: FactualTimeframe.DAILY,
    ChartTimeframe.FOUR_HOUR: FactualTimeframe.FOUR_HOUR,
    ChartTimeframe.ONE_HOUR: FactualTimeframe.ONE_HOUR,
}
_VISUAL_TIMEFRAME = {
    ChartTimeframe.WEEKLY: VisualTimeframe.WEEKLY,
    ChartTimeframe.DAILY: VisualTimeframe.DAILY,
    ChartTimeframe.FOUR_HOUR: VisualTimeframe.FOUR_HOUR,
    ChartTimeframe.ONE_HOUR: VisualTimeframe.ONE_HOUR,
}


def _safe_analysis_failure(error: Exception) -> str:
    if isinstance(error, ChartAnalystV2Error):
        if error.code in {
            ChartAnalystV2FailureCode.UNAVAILABLE,
            ChartAnalystV2FailureCode.TIMEOUT,
            ChartAnalystV2FailureCode.DISABLED,
        }:
            return "API REQUEST FAILED"
        if error.code in {
            ChartAnalystV2FailureCode.INVALID_SCHEMA,
            ChartAnalystV2FailureCode.INCOMPLETE,
            ChartAnalystV2FailureCode.IDENTITY_MISMATCH,
        }:
            return "SCHEMA VALIDATION FAILED"
        if error.code is ChartAnalystV2FailureCode.REFUSAL:
            return "ANALYSIS PROVIDER REFUSED REQUEST"
    if isinstance(error, TradingViewEvidenceStoreError):
        return "CHART BINDING INVALID"
    if isinstance(error, ValueError) and "CHART" in str(error):
        return "CHART BINDING INVALID"
    return "NATIVE REVIEW ANALYSIS FAILED"


def _visual_layer2_evidence(
    requirement: NativeReviewRequirement,
    responses: tuple[VisualEvidenceV2Response, ...],
) -> NativeIndependentLayer2Evidence:
    """Bind validated V2 facts without manufacturing support or contradiction."""

    by_timeframe = {item.timeframe: item for item in responses}
    states = []
    for factual in FactualTimeframe:
        visual = VisualTimeframe(factual.value)
        response = by_timeframe.get(visual)
        validation = (
            None
            if response is None
            else next(
                item for item in response.observations
                if item.question_id
                is VisualQuestionV2.VISUAL_CHART_VALIDATION
            )
        )
        states.append(
            (
                factual,
                NativeLayer2EvidenceState.MIXED
                if validation is not None
                and validation.observation_status
                is VisualObservationStatus.OBSERVED
                else NativeLayer2EvidenceState.UNAVAILABLE,
            )
        )
    return NativeIndependentLayer2Evidence(
        requirement.native_run_identity,
        requirement.canonical_instrument,
        tuple(states),
        NativeLayer2EvidenceState.UNAVAILABLE,
        tuple(
            dict.fromkeys(
                (
                    "SWING-V1-VISUAL-QUESTION-SET-V2",
                    *(item.evidence_sha256 for item in responses),
                )
            )
        ),
    )


__all__ = [
    "NativeAnalysisDetailsProjection",
    "NativeReviewAnalysisOutcome",
    "NativeReviewAnalysisState",
    "NativeReviewRunState",
    "NativeReviewWorkflow",
    "NativeReviewWorkflowSnapshot",
    "project_native_analysis_details",
]
