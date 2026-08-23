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
)
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.discovery_source import ProviderDiscoveryFactualSource
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
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.runtime import (
    ReadOnlyProviderLease,
    SharedAuthenticatedProviderRuntime,
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
    discovery_operation: IntradayDiscoveryOperationService
    reliance_bootstrap: RelianceIntradayBootstrap


def create_intraday_runtime(
    provider_runtime: SharedAuthenticatedProviderRuntime,
    *,
    calendar_publisher: MarketCalendarPublisher | None = None,
    evidence_root: Path = DEFAULT_INTRADAY_EVIDENCE_ROOT,
    last_successful_discovery_run_identity: str | None = None,
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
    universe = load_intraday_universe_publication()
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version=RECONCILIATION_VERSION,
    )
    discovery = _create_discovery_application(
        store=store,
        last_successful_run_identity=last_successful_discovery_run_identity,
        universe=universe,
        reconciliation=reconciliation,
    )
    operation = IntradayDiscoveryOperationService(
        provider_runtime=provider_runtime,
        acquire_lease=access.acquire_discovery_lease,
        universe=universe,
        reconciliation=reconciliation,
        application=discovery,
        store=store,
        calendar_publisher=calendar,
        factual_source_factory=lambda lease: ProviderDiscoveryFactualSource(
            lease=lease,
            calendar_publisher=calendar,
            universe_identity=universe.publication_identity,
            universe_version=universe.publication_version,
            reconciliation_identity=reconciliation.publication_identity,
            reconciliation_version=reconciliation.publication_version,
            reconciliation=reconciliation,
        ),
        clock=clock,
    )
    return IntradayRuntimeComposition(
        workstation=discovery,
        provider_access=access,
        discovery_application=discovery,
        discovery_operation=operation,
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
        last_successful_run_identity=last_successful_run_identity,
    )


__all__ = [
    "IntradayProviderRuntimeAccess",
    "IntradayRuntimeComposition",
    "create_intraday_runtime",
    "create_intraday_workstation",
]
