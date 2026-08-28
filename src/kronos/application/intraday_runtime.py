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
from kronos.intraday.probables_persistence import ProbablesStore
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.probables_v2_diagnostics_persistence import (
    ProbablesV2DiagnosticsStore,
)
from kronos.intraday.refresh_v2_persistence import RefreshV2ProvenanceStore
from kronos.intraday.refresh_v2 import RefreshV2Outcome
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
from kronos.instrument.active_derivative import ACTIVE_DERIVATIVE_CATALOGUE_VERSION
from kronos.instrument.active_derivative_persistence import (
    ActiveDerivativeBindingStore,
)
from kronos.instrument.semantic_v2_persistence import (
    DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT,
    InstrumentSemanticV2Store,
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
    refresh_v2_provenance_store: RefreshV2ProvenanceStore
    probables_v2_diagnostics_store: ProbablesV2DiagnosticsStore
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
    probables_v2 = IntradayProbablesV2Application(
        store=ProbablesV2Store(Path(evidence_root)),
    )
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
        refresh_v2_provenance_store=refresh_v2_provenance_store,
        probables_v2_diagnostics_store=probables_v2_diagnostics_store,
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
