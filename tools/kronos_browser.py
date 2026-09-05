"""Sponsor and developer entry point for the local KRONOS Browser V1."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
import webbrowser

from kronos.application.provider_instrument_master_operation import (
    ProviderInstrumentMasterOperationalComposition,
)
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.browser.server import create_browser_server
from kronos.browser.intraday_discovery_control import (
    IntradayDiscoveryOperationalControl,
)
from kronos.browser.intraday_probables_v2_control import (
    IntradayProbablesV2OperationalControl,
)
from kronos.browser.intraday_review_v2_control import (
    IntradayReviewV2OperationalControl,
)
from kronos.browser.intraday_wo10_control import (
    IntradayWo10OperationalControl,
)
from kronos.browser.intraday_wo11_control import (
    IntradayWo11OperationalControl,
)
from kronos.browser.intraday_wo12_v2_control import (
    IntradayWo12V2OperationalControl,
)
from kronos.browser.intraday_wo13_control import IntradayWo13OperationalControl
from kronos.browser.intraday_wo14_control import IntradayWo14OperationalControl
from kronos.browser.intraday_wo15_control import IntradayWo15OperationalControl
from kronos.browser.intraday_wo16_control import IntradayWo16OperationalControl
from kronos.browser.intraday_wo17_control import IntradayWo17OperationalControl
from kronos.browser.intraday_operational_readiness import (
    IntradayOperationalReadinessProjection,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import ProductBrowserRoutes
from kronos.browser.intraday_historical_control import (
    IntradayHistoricalQualificationOperationalControl,
)
from kronos.browser.restart_control import BrowserBackendRestartControl
from kronos.market.calendar import MarketCalendarPublisher
from kronos.intraday.universe import load_intraday_universe_publication
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.instrument_master_persistence import (
    DEFAULT_PROVIDER_INSTRUMENT_SNAPSHOT_ROOT,
    ProviderInstrumentSnapshotStore,
)
from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
from kronos.swing.v1.mtf_facts import (
    DEFAULT_MTF_FACT_EVIDENCE_ROOT,
    MtfFactEvidenceStore,
)
from kronos.swing.v1.native_discovery import (
    DEFAULT_NATIVE_DISCOVERY_EVIDENCE_ROOT,
    NativeDiscoveryEvidenceStore,
)
from kronos.swing.v1.relative_context import (
    DEFAULT_RELATIVE_CONTEXT_EVIDENCE_ROOT,
    RelativeContextEvidenceStore,
)
from tools.provider_pilots.provider_foundation_v2_historical_proof import (
    _build_provider,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch local KRONOS Browser V1")
    parser.add_argument("--port", type=int, default=8947)
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    mtf_fact_store = MtfFactEvidenceStore(DEFAULT_MTF_FACT_EVIDENCE_ROOT)
    native_discovery_store = NativeDiscoveryEvidenceStore(
        DEFAULT_NATIVE_DISCOVERY_EVIDENCE_ROOT
    )
    relative_context_store = RelativeContextEvidenceStore(
        DEFAULT_RELATIVE_CONTEXT_EVIDENCE_ROOT
    )
    shared_provider_runtime = SharedAuthenticatedProviderRuntime(
        _build_provider,
        provider_identity="KITE",
    )
    swing_provider_factory = lambda: shared_provider_runtime.compatibility_facade(
        consumer_identity="SWING",
        operations=frozenset({
            ReadOnlyProviderOperation.INSTRUMENTS,
            ReadOnlyProviderOperation.HISTORICAL_DATA,
            ReadOnlyProviderOperation.QUOTE,
            ReadOnlyProviderOperation.LTP,
            ReadOnlyProviderOperation.OHLC,
            ReadOnlyProviderOperation.MONITORING,
        }),
    )
    intraday_runtime = create_intraday_runtime(shared_provider_runtime)
    intraday_discovery_control = IntradayDiscoveryOperationalControl(
        intraday_runtime.discovery_operation,
        intraday_runtime.discovery_application,
    )
    intraday_probables_v2_control = IntradayProbablesV2OperationalControl(
        intraday_runtime.discovery_v2_operation,
        intraday_runtime.probables_v2_application,
        intraday_runtime.refresh_v2_provenance_store,
    )
    intraday_review_v2_control = IntradayReviewV2OperationalControl(
        intraday_runtime.review_v2_application,
        intraday_runtime.review_v2_operation_store,
    )
    intraday_wo10_control = IntradayWo10OperationalControl(
        intraday_runtime.wo10_runtime,
        intraday_runtime.probables_v2_store,
        intraday_runtime.wo10_policy_registry,
    )
    intraday_wo11_control = IntradayWo11OperationalControl(
        intraday_runtime.wo11_runtime,
    )
    intraday_wo12_v2_control = IntradayWo12V2OperationalControl(
        intraday_runtime.wo12_v2_runtime,
    )
    intraday_wo13_control = IntradayWo13OperationalControl(
        intraday_runtime.wo13_application,
        intraday_runtime.wo13_restoration,
        intraday_runtime.wo12_v2_store,
    )
    intraday_wo14_control = IntradayWo14OperationalControl(
        intraday_runtime.wo14_application,
        intraday_runtime.wo14_restoration,
    )
    intraday_wo15_control = IntradayWo15OperationalControl(
        intraday_runtime.wo15_application,
        intraday_runtime.wo15_restoration,
    )
    intraday_wo16_control = IntradayWo16OperationalControl(
        intraday_runtime.wo16_application,
        intraday_runtime.wo16_restoration,
        wo13_store=intraday_runtime.wo13_store,
        wo14_store=intraday_runtime.wo14_store,
        wo15_store=intraday_runtime.wo15_store,
    )
    intraday_wo17_control = IntradayWo17OperationalControl(
        intraday_runtime.wo17_application,
        intraday_runtime.wo17_restoration,
        wo16_store=intraday_runtime.wo16_store,
        monitoring=intraday_runtime.wo17_monitoring,
    )
    intraday_operational_readiness = IntradayOperationalReadinessProjection(
        intraday_runtime.wo_b_runtime
    )
    product_routes = ProductBrowserRoutes((IntradayBrowserRoutes(
        intraday_runtime.discovery_v2_application,
        probables_v2_control=intraday_probables_v2_control,
        review_v2_control=intraday_review_v2_control,
        wo10_control=intraday_wo10_control,
        wo11_control=intraday_wo11_control,
        wo12_v2_control=intraday_wo12_v2_control,
        wo13_control=intraday_wo13_control,
        wo14_control=intraday_wo14_control,
        wo15_control=intraday_wo15_control,
        wo16_control=intraday_wo16_control,
        wo17_control=intraday_wo17_control,
        operational_readiness=intraday_operational_readiness,
        review_workstation=intraday_runtime.discovery_application,
    ),))
    intraday_historical_control = (
        IntradayHistoricalQualificationOperationalControl(
            intraday_runtime.historical_invocation
        )
    )
    provider_instrument_master_operation = (
        ProviderInstrumentMasterOperationalComposition(
            shared_provider_runtime,
            store=ProviderInstrumentSnapshotStore(
                DEFAULT_PROVIDER_INSTRUMENT_SNAPSHOT_ROOT
            ),
            universe=load_intraday_universe_publication(),
            clock=lambda: datetime.now(UTC),
        )
    )
    application = SwingOpportunitiesApplication(
        swing_provider_factory,
        run_provenance_store=LocalSwingRunProvenanceStore(),
        market_calendar_publisher=MarketCalendarPublisher(),
        mtf_fact_evidence_store=mtf_fact_store,
        native_discovery_evidence_store=native_discovery_store,
        relative_context_evidence_store=relative_context_store,
    )
    restart_control = BrowserBackendRestartControl.create()
    try:
        server = create_browser_server(
            application,
            port=args.port,
            restart_control=restart_control,
            product_routes=product_routes,
            provider_instrument_master_operation=(
                provider_instrument_master_operation
            ),
            intraday_discovery_control=intraday_discovery_control,
            intraday_historical_control=intraday_historical_control,
        )
        intraday_runtime.wo17_monitoring.set_shared_monitoring_hub(
            server.swing_monitoring_hub
        )
        intraday_runtime.wo17_monitoring.set_monitoring_capability_supplier(
            application.authenticated_read_only_capability
        )
    except Exception:
        restart_control.remove()
        raise
    url = f"http://127.0.0.1:{server.server_port}/swing/opportunities"
    if not args.no_browser:
        webbrowser.open_new_tab(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        shared_provider_runtime.end_kronos_session()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
