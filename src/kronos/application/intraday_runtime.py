"""Intraday-owned runtime composition seam for the shared Browser process."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from kronos.application.intraday_reliance_bootstrap import (
    DEFAULT_INTRADAY_EVIDENCE_ROOT,
    RelianceIntradayBootstrap,
)
from kronos.application.intraday_discovery import IntradayDiscoveryApplication
from kronos.application.intraday_discovery_operation import (
    IntradayDiscoveryOperationService,
    IntradayRefreshAdmission,
)
from kronos.application.intraday_probables import IntradayProbablesApplication
from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.application.intraday_review_mcx_paired import (
    IntradayMcxPairedReviewApplication,
)
from kronos.application.intraday_wo10 import (
    IntradayWo10Application,
)
from kronos.application.intraday_wo10_runtime import (
    IntradayWo10RuntimeService,
    RetainedWo10EvidenceLoader,
    RuntimeWo10EvidenceAssembler,
    RuntimeWo10PolicyRegistry,
)
from kronos.application.intraday_wo11 import (
    IntradayWo11Application,
    IntradayWo11RuntimeService,
)
from kronos.application.intraday_wo12_v2 import (
    IntradayWo12V2Application,
    IntradayWo12V2RuntimeService,
)
from kronos.application.intraday_historical_operation import (
    IntradayHistoricalQualificationHarness,
    IntradayHistoricalQualificationOperationService,
)
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.discovery_source import ProviderDiscoveryFactualSource
from kronos.intraday.historical_qualification_persistence import (
    HistoricalQualificationStore,
)
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.intraday.mcx_history_persistence import McxContractHistoryStore
from kronos.intraday.probables_persistence import ProbablesStore
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.probables_v2_diagnostics_persistence import (
    ProbablesV2DiagnosticsStore,
)
from kronos.intraday.refresh_v2_persistence import RefreshV2ProvenanceStore
from kronos.intraday.refresh_v2 import RefreshV2Outcome
from kronos.intraday.review_v2 import CurrentReviewPointerV2
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_mcx_paired_persistence import (
    IntradayMcxPairedReviewStore,
)
from kronos.intraday.review_v2_operation_persistence import (
    ReviewV2OperationProvenanceStore,
)
from kronos.intraday.probables_refresh_persistence import (
    RefreshOperationalStateStore,
)
from kronos.intraday.reconciliation import (
    RECONCILIATION_IDENTITY,
    RECONCILIATION_VERSION,
    ReconciliationPublication,
)
from kronos.intraday.reconciliation_persistence import IntradayReconciliationStore
from kronos.intraday.universe import (
    IntradayUniversePublication,
    load_intraday_universe_publication,
)
from kronos.intraday.wo10_persistence import Wo10Store
from kronos.intraday.wo11_persistence import Wo11Store
from kronos.intraday.wo12_v2_persistence import Wo12V2Store
from kronos.instrument.active_derivative import ACTIVE_DERIVATIVE_CATALOGUE_VERSION
from kronos.instrument.active_derivative_persistence import (
    ActiveDerivativeBindingStore,
)
from kronos.instrument.semantic_v2_persistence import (
    DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT,
    InstrumentSemanticV2Store,
)
from kronos.instrument.visual_identity import (
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_SUCCESSOR_VERSION,
)
from kronos.instrument.visual_identity_persistence import (
    load_visual_identity_resolver,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.runtime import (
    ReadOnlyProviderLease,
    SharedAuthenticatedProviderRuntime,
)
from kronos.provider.instrument_master_persistence import (
    ProviderInstrumentSnapshotStore,
)


_INTRADAY_READ_OPERATIONS = frozenset({
    ReadOnlyProviderOperation.INSTRUMENTS,
    ReadOnlyProviderOperation.INSTRUMENT_ASSERTIONS,
    ReadOnlyProviderOperation.HISTORICAL_DATA,
})
_DISCOVERY_READ_OPERATIONS = frozenset({
    ReadOnlyProviderOperation.INSTRUMENTS,
    ReadOnlyProviderOperation.HISTORICAL_DATA,
})


class IntradayProviderRuntimeAccess:
    """Product-owned adapter requesting only Intraday factual read operations."""

    __slots__ = ("_runtime",)

    def __init__(self, runtime: SharedAuthenticatedProviderRuntime) -> None:
        if type(runtime) is not SharedAuthenticatedProviderRuntime:
            raise ValueError("INTRADAY_PROVIDER_RUNTIME_INVALID")
        self._runtime = runtime

    def acquire_historical_lease(self) -> ReadOnlyProviderLease:
        return self._runtime.acquire_lease(
            consumer_identity="INTRADAY",
            operations=_INTRADAY_READ_OPERATIONS,
        )

    def acquire_discovery_lease(self) -> ReadOnlyProviderLease:
        return self._runtime.acquire_lease(
            consumer_identity="INTRADAY_NATIVE_DISCOVERY",
            operations=_DISCOVERY_READ_OPERATIONS,
        )


@dataclass(frozen=True, slots=True)
class IntradayRuntimeComposition:
    workstation: object
    provider_access: IntradayProviderRuntimeAccess
    discovery_application: IntradayDiscoveryApplication
    discovery_v2_application: IntradayDiscoveryApplication
    discovery_operation: IntradayDiscoveryOperationService
    discovery_v2_operation: IntradayDiscoveryOperationService
    historical_operation: IntradayHistoricalQualificationOperationService
    historical_invocation: IntradayHistoricalQualificationHarness
    probables_application: IntradayProbablesApplication
    probables_v2_application: IntradayProbablesV2Application
    probables_v2_store: ProbablesV2Store
    review_v2_store: IntradayReviewV2Store
    review_v2_application: IntradayReviewV2Application
    review_v2_current: CurrentReviewPointerV2 | None
    review_v2_operation_store: ReviewV2OperationProvenanceStore
    mcx_paired_review_store: IntradayMcxPairedReviewStore
    mcx_paired_review_application: IntradayMcxPairedReviewApplication
    wo10_store: Wo10Store
    wo10_policy_registry: RuntimeWo10PolicyRegistry
    wo10_application: IntradayWo10Application
    wo10_runtime: IntradayWo10RuntimeService
    wo11_store: Wo11Store
    wo11_application: IntradayWo11Application
    wo11_runtime: IntradayWo11RuntimeService
    wo12_v2_store: Wo12V2Store
    wo12_v2_application: IntradayWo12V2Application
    wo12_v2_runtime: IntradayWo12V2RuntimeService
    refresh_v2_provenance_store: RefreshV2ProvenanceStore
    probables_v2_diagnostics_store: ProbablesV2DiagnosticsStore
    mcx_history_store: McxContractHistoryStore
    refresh_state_store: RefreshOperationalStateStore
    reliance_bootstrap: RelianceIntradayBootstrap


def create_intraday_runtime(
    provider_runtime: SharedAuthenticatedProviderRuntime,
    *,
    calendar_publisher: MarketCalendarPublisher | None = None,
    evidence_root: Path = DEFAULT_INTRADAY_EVIDENCE_ROOT,
    last_successful_discovery_run_identity: str | None = None,
    last_successful_probables_run_identity: str | None = None,
    clock=lambda: datetime.now(timezone.utc),
) -> IntradayRuntimeComposition:
    """Compose Intraday without moving product policy into shared modules."""

    access = IntradayProviderRuntimeAccess(provider_runtime)
    calendar = calendar_publisher or MarketCalendarPublisher()
    bootstrap = RelianceIntradayBootstrap(
        acquire_lease=access.acquire_historical_lease,
        calendar_publisher=calendar,
        evidence_root=evidence_root,
        clock=clock,
    )
    store = NativeDiscoveryStore(Path(evidence_root) / "discovery")
    refresh_state_store = RefreshOperationalStateStore(Path(evidence_root))
    refresh_state = refresh_state_store.load_current()
    restored_discovery_identity = (
        last_successful_discovery_run_identity
        if last_successful_discovery_run_identity is not None
        else None
        if refresh_state is None
        else refresh_state.last_successful_discovery_run_identity
    )
    restored_probables_identity = (
        last_successful_probables_run_identity
        if last_successful_probables_run_identity is not None
        else None
        if refresh_state is None
        else refresh_state.last_successful_probables_run_identity
    )
    universe = load_intraday_universe_publication()
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version=RECONCILIATION_VERSION,
    )
    active_binding_store = ActiveDerivativeBindingStore(
        Path(evidence_root) / "active-derivative-bindings"
    )
    active_catalogue = InstrumentSemanticV2Store(
        DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT
    ).load(
        publication_identity="KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2",
        publication_version=ACTIVE_DERIVATIVE_CATALOGUE_VERSION,
    )
    probables = IntradayProbablesApplication(
        store=ProbablesStore(Path(evidence_root)),
        last_successful_run_identity=restored_probables_identity,
    )
    probables_v2_store = ProbablesV2Store(Path(evidence_root))
    probables_v2 = IntradayProbablesV2Application(store=probables_v2_store)
    review_v2_store = IntradayReviewV2Store(Path(evidence_root) / "review-v2")
    review_v2_current = review_v2_store.load_current()
    review_v2 = IntradayReviewV2Application(
        probables_store=probables_v2_store,
        review_store=review_v2_store,
        visual_identity_resolver=load_visual_identity_resolver(
            publication_version=(
                VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_SUCCESSOR_VERSION
            )
        ),
    )
    review_v2_operation_store = ReviewV2OperationProvenanceStore(
        review_v2_store.root
    )
    mcx_paired_review_store = IntradayMcxPairedReviewStore(
        Path(evidence_root) / "review-mcx-paired-v1"
    )
    mcx_paired_review = IntradayMcxPairedReviewApplication(
        store=mcx_paired_review_store
    )
    wo10_store = Wo10Store(Path(evidence_root) / "wo10-reconciliation-v2")
    wo10_registry = RuntimeWo10PolicyRegistry()
    wo10_loader = RetainedWo10EvidenceLoader(
        probables=probables_v2_store,
        review=review_v2_store,
        registry=wo10_registry,
    )
    wo10_application = IntradayWo10Application(
        run_store=probables_v2_store,
        store=wo10_store,
        policy_registry=wo10_registry,
        evidence_assembler=RuntimeWo10EvidenceAssembler(wo10_loader),
        backend_identity="KRONOS-INTRADAY-BROWSER",
    )
    wo10_runtime = IntradayWo10RuntimeService(wo10_application, wo10_store)
    wo11_store = Wo11Store(Path(evidence_root) / "wo11-promotion-publication-v1")
    wo11_application = IntradayWo11Application(
        wo10_store=wo10_store,
        store=wo11_store,
        backend_identity="KRONOS-INTRADAY-BROWSER",
    )
    wo11_runtime = IntradayWo11RuntimeService(wo11_application)
    wo12_v2_store = Wo12V2Store(Path(evidence_root) / "wo12-kr370-v2")
    wo12_v2_application = IntradayWo12V2Application(
        wo10_store=wo10_store,
        wo11_store=wo11_store,
        store=wo12_v2_store,
    )
    wo12_v2_runtime = IntradayWo12V2RuntimeService(wo12_v2_application)
    discovery = _create_discovery_application(
        store=store,
        last_successful_run_identity=restored_discovery_identity,
        universe=universe,
        reconciliation=reconciliation,
        probables=probables,
        probables_v2=probables_v2,
        active_derivative_binding_store=active_binding_store,
    )
    discovery_v2_store = NativeDiscoveryStore(Path(evidence_root) / "discovery-v2")
    discovery_v2 = _create_discovery_application(
        store=discovery_v2_store,
        last_successful_run_identity=(
            probables_v2.snapshot().last_successful_discovery_run_identity
        ),
        universe=universe,
        reconciliation=reconciliation,
        probables_v2=probables_v2,
        active_derivative_binding_store=active_binding_store,
    )
    operation = IntradayDiscoveryOperationService(
        refresh_admission=(refresh_admission := IntradayRefreshAdmission()),
        provider_runtime=provider_runtime,
        acquire_lease=access.acquire_discovery_lease,
        universe=universe,
        reconciliation=reconciliation,
        application=discovery,
        store=store,
        calendar_publisher=calendar,
        factual_source_factory=lambda lease, resolutions: ProviderDiscoveryFactualSource(
            lease=lease,
            calendar_publisher=calendar,
            universe_identity=universe.publication_identity,
            universe_version=universe.publication_version,
            reconciliation_identity=reconciliation.publication_identity,
            reconciliation_version=reconciliation.publication_version,
            reconciliation=reconciliation,
            active_derivative_resolutions=resolutions,
        ),
        probables=probables,
        refresh_state_store=refresh_state_store,
        active_derivative_catalogue=active_catalogue,
        active_derivative_binding_store=active_binding_store,
        provider_snapshot_store=ProviderInstrumentSnapshotStore(
            Path(evidence_root) / "provider-instrument-master"
        ),
        clock=clock,
    )
    refresh_v2_provenance_store = RefreshV2ProvenanceStore(Path(evidence_root))
    probables_v2_diagnostics_store = ProbablesV2DiagnosticsStore(Path(evidence_root))
    mcx_history_store = McxContractHistoryStore(Path(evidence_root))
    latest_v2_provenance = refresh_v2_provenance_store.latest()
    if (
        latest_v2_provenance is not None
        and latest_v2_provenance.outcome is RefreshV2Outcome.FAILED
        and latest_v2_provenance.failure is not None
        and latest_v2_provenance.failure_detail_identity is not None
    ):
        probables_v2.record_failure(
            latest_v2_provenance.failure,
            failure_detail=probables_v2_diagnostics_store.load_failure(
                latest_v2_provenance.failure_detail_identity
            ),
        )
    operation_v2 = IntradayDiscoveryOperationService(
        provider_runtime=provider_runtime,
        acquire_lease=access.acquire_discovery_lease,
        universe=universe,
        reconciliation=reconciliation,
        application=discovery_v2,
        store=discovery_v2_store,
        calendar_publisher=calendar,
        factual_source_factory=lambda lease, resolutions: ProviderDiscoveryFactualSource(
            lease=lease,
            calendar_publisher=calendar,
            universe_identity=universe.publication_identity,
            universe_version=universe.publication_version,
            reconciliation_identity=reconciliation.publication_identity,
            reconciliation_version=reconciliation.publication_version,
            reconciliation=reconciliation,
            active_derivative_resolutions=resolutions,
            produce_probables_v2_facts=True,
            mcx_history_store=mcx_history_store,
        ),
        probables_v2=probables_v2,
        probables_v2_diagnostics_store=probables_v2_diagnostics_store,
        refresh_admission=refresh_admission,
        active_derivative_catalogue=active_catalogue,
        active_derivative_binding_store=active_binding_store,
        provider_snapshot_store=ProviderInstrumentSnapshotStore(
            Path(evidence_root) / "provider-instrument-master"
        ),
        clock=clock,
    )
    historical_operation = IntradayHistoricalQualificationOperationService(
        provider_runtime=provider_runtime,
        universe=universe,
        reconciliation=reconciliation,
        calendar=CurrentMarketCalendarScheduleSource(
            calendar,
            observed_at=clock(),
        ),
        store=HistoricalQualificationStore(Path(evidence_root)),
        clock=clock,
    )
    if refresh_state is not None and refresh_state.current_failure is not None:
        if refresh_state.current_failure_stage in {
            "PROBABLES_EVIDENCE_MAPPING",
            "PROBABLES_INVOCATION",
        }:
            probables.record_failure(refresh_state.current_failure)
        else:
            discovery.record_failure(refresh_state.current_failure)
    return IntradayRuntimeComposition(
        workstation=discovery,
        provider_access=access,
        discovery_application=discovery,
        discovery_v2_application=discovery_v2,
        discovery_operation=operation,
        discovery_v2_operation=operation_v2,
        historical_operation=historical_operation,
        historical_invocation=IntradayHistoricalQualificationHarness(
            historical_operation
        ),
        probables_application=probables,
        probables_v2_application=probables_v2,
        probables_v2_store=probables_v2_store,
        review_v2_store=review_v2_store,
        review_v2_application=review_v2,
        review_v2_current=review_v2_current,
        review_v2_operation_store=review_v2_operation_store,
        mcx_paired_review_store=mcx_paired_review_store,
        mcx_paired_review_application=mcx_paired_review,
        wo10_store=wo10_store,
        wo10_policy_registry=wo10_registry,
        wo10_application=wo10_application,
        wo10_runtime=wo10_runtime,
        wo11_store=wo11_store,
        wo11_application=wo11_application,
        wo11_runtime=wo11_runtime,
        wo12_v2_store=wo12_v2_store,
        wo12_v2_application=wo12_v2_application,
        wo12_v2_runtime=wo12_v2_runtime,
        refresh_v2_provenance_store=refresh_v2_provenance_store,
        probables_v2_diagnostics_store=probables_v2_diagnostics_store,
        mcx_history_store=mcx_history_store,
        refresh_state_store=refresh_state_store,
        reliance_bootstrap=bootstrap,
    )


def create_intraday_workstation() -> IntradayDiscoveryApplication:
    """Create a read-only product projection without Provider acquisition."""

    return _create_discovery_application(store=NativeDiscoveryStore())


def _create_discovery_application(
    *,
    store: NativeDiscoveryStore,
    last_successful_run_identity: str | None = None,
    universe: IntradayUniversePublication | None = None,
    reconciliation: ReconciliationPublication | None = None,
    probables: IntradayProbablesApplication | None = None,
    probables_v2: IntradayProbablesV2Application | None = None,
    active_derivative_binding_store: ActiveDerivativeBindingStore | None = None,
) -> IntradayDiscoveryApplication:
    selected_universe = universe or load_intraday_universe_publication()
    selected_reconciliation = reconciliation or IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version=RECONCILIATION_VERSION,
    )
    return IntradayDiscoveryApplication(
        universe=selected_universe,
        reconciliation=selected_reconciliation,
        store=store,
        probables=probables,
        probables_v2=probables_v2,
        active_derivative_binding_store=active_derivative_binding_store,
        last_successful_run_identity=last_successful_run_identity,
    )


__all__ = [
    "IntradayProviderRuntimeAccess",
    "IntradayRuntimeComposition",
    "create_intraday_runtime",
    "create_intraday_workstation",
]
