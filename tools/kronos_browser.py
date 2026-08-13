"""Sponsor and developer entry point for the local KRONOS Browser V1."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import webbrowser

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser.server import create_browser_server
from kronos.browser.restart_control import BrowserBackendRestartControl
from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
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
    application = SwingOpportunitiesApplication(
        _build_provider,
        run_provenance_store=LocalSwingRunProvenanceStore(),
    )
    restart_control = BrowserBackendRestartControl.create()
    try:
        server = create_browser_server(
            application,
            port=args.port,
            restart_control=restart_control,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
