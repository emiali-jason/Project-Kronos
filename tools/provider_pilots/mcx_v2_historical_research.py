"""Isolated Sponsor-authenticated runner for the MCX V2 research corpus.

The runner creates one isolated shared DOMAIN-006 runtime, performs no automatic
retry, and ends the context after the bounded acquisition.  Exact snapshot
identities are part of this reviewed commissioning request; directory order is
never used as authority.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
import json
import threading
import tkinter as tk
from tkinter import ttk

from kronos.instrument.semantic_v2_persistence import (
    DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT,
    InstrumentSemanticV2Store,
)
from kronos.intraday.mcx_historical_research import (
    acquire_mcx_historical_research_corpus,
)
from kronos.intraday.mcx_historical_research_persistence import (
    McxHistoricalResearchCorpusStore,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument_master import (
    KITE_INSTRUMENT_MASTER_DATASET,
)
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.instrument_master_persistence import (
    ProviderInstrumentSnapshotStore,
)
from kronos.provider.models.authentication import AuthenticationAttemptState
from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
from tools.provider_pilots.provider_foundation_v2_historical_proof import (
    _build_provider,
)


WINDOW_TITLE = "KRONOS — MCX V2 Historical Research Acquisition"
EVIDENCE_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
)
TARGET_DATES = tuple(date(2026, 8, day) for day in (24, 25, 26, 27, 28))
SNAPSHOT_BY_DATE = {
    date(2026, 8, 24): "PROVIDER-INSTRUMENT-SNAPSHOT-c32c3f5b40392d5075f222f298a85617111b37afcedd9b36755c54ad6c55c438",
    date(2026, 8, 25): "PROVIDER-INSTRUMENT-SNAPSHOT-c32c3f5b40392d5075f222f298a85617111b37afcedd9b36755c54ad6c55c438",
    date(2026, 8, 26): "PROVIDER-INSTRUMENT-SNAPSHOT-c32c3f5b40392d5075f222f298a85617111b37afcedd9b36755c54ad6c55c438",
    date(2026, 8, 27): "PROVIDER-INSTRUMENT-SNAPSHOT-b03630190ef0f7e6118998025edaf3ef84d6fbd0ab9fb351112fe80dda696cbb",
    date(2026, 8, 28): "PROVIDER-INSTRUMENT-SNAPSHOT-67453cd86409583be4500c3dc997ceed913be9fd5a455a9e6fdbabe3baef525e",
}


class _ResearchWindow:
    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._runtime = SharedAuthenticatedProviderRuntime(
            _build_provider,
            provider_identity="KITE",
        )
        self._attempt: object | None = None
        root.title(WINDOW_TITLE)
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=18)
        frame.grid(row=0, column=0)
        ttk.Label(
            frame,
            text="Read-only MCX historical research acquisition",
        ).grid(row=0, column=0, sticky="w")
        self._status = tk.StringVar(
            value="Ready. No Provider request has started."
        )
        ttk.Label(
            frame,
            textvariable=self._status,
            justify="left",
            wraplength=820,
        ).grid(row=1, column=0, sticky="w", pady=(10, 14))
        self._connect = ttk.Button(
            frame,
            text="Connect and acquire once",
            command=self._connect_once,
        )
        self._connect.grid(row=2, column=0, sticky="w")
        root.protocol("WM_DELETE_WINDOW", self._close)

    def _connect_once(self) -> None:
        self._connect.configure(state="disabled")
        self._status.set("Opening the governed Kite authentication flow…")
        try:
            self._attempt = self._runtime.begin_login()
        except Exception:
            self._status.set("Authentication: FAIL | SANITIZED_LOCAL_FAILURE")
            return
        self._status.set(
            "Official Kite login opened. Complete Sponsor authentication once."
        )
        threading.Thread(
            target=self._complete,
            name="kronos-mcx-v2-historical-research",
            daemon=True,
        ).start()

    def _complete(self) -> None:
        attempt = self._attempt
        if attempt is None:
            return
        rendered = ""
        try:
            outcome = self._runtime.complete_callback(attempt)
            if outcome.state is not AuthenticationAttemptState.SUCCEEDED:
                rendered = "Authentication: FAIL | SANITIZED_AUTHENTICATION_FAILURE"
            else:
                rendered = self._acquire()
        except Exception as error:
            rendered = (
                "Research acquisition: FAIL | "
                f"{getattr(getattr(error, 'failure', None), 'value', 'SANITIZED_FAILURE')}"
            )
        finally:
            try:
                self._runtime.end_kronos_session()
            except Exception:
                pass
        print(rendered, flush=True)
        self._root.after(0, lambda: self._status.set(rendered))

    def _acquire(self) -> str:
        snapshot_store = ProviderInstrumentSnapshotStore(
            EVIDENCE_ROOT / "provider-instrument-master"
        )
        snapshots = {
            trading_date: snapshot_store.load(
                provider="KITE",
                dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
                snapshot_identity=SNAPSHOT_BY_DATE[trading_date],
            )
            for trading_date in TARGET_DATES
        }
        catalogue = InstrumentSemanticV2Store(
            DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT
        ).load(
            publication_identity="KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2",
            publication_version="1.2.0",
        )
        lease = self._runtime.acquire_lease(
            consumer_identity="INTRADAY_MCX_HISTORICAL_RESEARCH",
            operations=frozenset({
                ReadOnlyProviderOperation.INSTRUMENTS,
                ReadOnlyProviderOperation.HISTORICAL_DATA,
            }),
        )
        try:
            corpus = acquire_mcx_historical_research_corpus(
                lease=lease,
                requested_trading_dates=TARGET_DATES,
                provider_snapshots=snapshots,
                catalogue=catalogue,
                calendar_publisher=MarketCalendarPublisher(),
                created_at=datetime.now(UTC),
                limitations=(
                    "Retrospective contract reconstruction uses explicitly identified immutable Provider snapshots.",
                    "Expired contracts absent from the authenticated current Instrument Master remain unavailable.",
                    "No production Discovery, Probables, Review, trading, Risk, or broker authority.",
                ),
            )
        finally:
            lease.release()
        store = McxHistoricalResearchCorpusStore()
        path = store.retain(corpus)
        reloaded = store.load(corpus_identity=corpus.corpus_identity)
        if reloaded != corpus:
            raise ValueError("MCX_HISTORICAL_RESEARCH_RELOAD_MISMATCH")
        counts = {
            subject: {
                "complete": sum(
                    item.state.value == "COMPLETE"
                    for item in corpus.sessions
                    if item.analytical_subject == subject
                ),
                "partial": sum(
                    item.state.value == "PARTIAL"
                    for item in corpus.sessions
                    if item.analytical_subject == subject
                ),
                "rejected": sum(
                    item.state.value == "REJECTED"
                    for item in corpus.sessions
                    if item.analytical_subject == subject
                ),
            }
            for subject in corpus.subjects
        }
        result = {
            "state": "COMPLETE",
            "corpus_identity": corpus.corpus_identity,
            "integrity_identity": corpus.integrity_identity,
            "path": str(path),
            "sessions": counts,
            "provider_instrument_requests": corpus.provider_instrument_request_count,
            "provider_historical_requests": corpus.provider_historical_request_count,
            "provider_failures": corpus.provider_failure_count,
            "automatic_retries": corpus.automatic_retry_count,
            "benchmark_applicability": corpus.benchmark_applicability,
            "reload_equal": True,
        }
        return json.dumps(result, sort_keys=True, indent=2)

    def _close(self) -> None:
        try:
            self._runtime.end_kronos_session()
        except Exception:
            pass
        self._root.destroy()


def main() -> None:
    root = tk.Tk()
    _ResearchWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
