"""Sponsor and developer entry point for the local KRONOS Browser V1."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import webbrowser

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.browser.server import create_browser_server
from kronos.browser.restart_control import BrowserBackendRestartControl
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
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
    application = SwingOpportunitiesApplication(
        swing_provider_factory,
        run_provenance_store=LocalSwingRunProvenanceStore(),
        market_calendar_publisher=MarketCalendarPublisher(),
        mtf_fact_evidence_store=mtf_fact_store,
        native_discovery_evidence_store=native_discovery_store,
    )
    restart_control = BrowserBackendRestartControl.create()
    try:
        server = create_browser_server(
            application,
            port=args.port,
            restart_control=restart_control,
            intraday_workstation=intraday_runtime.workstation,
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
