"""Authentication-only Sponsor GUI for Provider Foundation V2."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import threading
import tkinter as tk
from tkinter import ttk

from kronos.configuration.exceptions import ConfigurationError
from kronos.configuration.principals import PrincipalBindingResult
from kronos.provider.models.authentication import AuthenticationAttemptState
from tools.provider_pilots.provider_foundation_v2_historical_proof import (
    SanitizedHistoricalProof,
    SanitizedLiveSnapshotProof,
    _build_provider,
    execute_equity_batch_proof,
    execute_equity_quote_batch_proof,
    execute_historical_proof,
    execute_live_snapshot_proof,
    execute_mcx_batch_proof,
    execute_mcx_quote_batch_proof,
    load_equity_symbols,
)


WINDOW_TITLE = "KRONOS — Connect to Kite"


@dataclass(frozen=True, slots=True)
class SanitizedAuthenticationEvidence:
    authentication: str
    browser_login: str
    loopback_callback: str
    session_exchange: str
    principal_verification: str
    read_only_capability: str
    failure: str = ""
    instrument_master: str = ""
    historical_proofs: tuple[SanitizedHistoricalProof, ...] = ()
    live_snapshot_proofs: tuple[SanitizedLiveSnapshotProof, ...] = ()

    def render(self) -> str:
        lines = (
            f"Kite authentication: {self.authentication}",
            f"Browser login: {self.browser_login}",
            f"Loopback callback: {self.loopback_callback}",
            f"Session exchange: {self.session_exchange}",
            f"Principal verification: {self.principal_verification}",
            f"Read-only capability: {self.read_only_capability}",
            "Secrets exposed: NO",
            "Order capability exposed: NO",
            "Order operations: 0",
        )
        market_data = (
            (f"Instrument Master: {self.instrument_master}",)
            + tuple(proof.render() for proof in self.historical_proofs)
            + tuple(proof.render() for proof in self.live_snapshot_proofs)
            if self.instrument_master
            else ()
        )
        failure = (f"Failure: {self.failure}",) if self.failure else ()
        return "\n".join(lines + market_data + failure)


class _AuthenticationWindow:
    def __init__(
        self,
        root: tk.Tk,
        *,
        equity_symbols: tuple[str, ...] = (),
        mcx_symbols: tuple[str, ...] = (),
        live_snapshot_proof: bool = False,
        quote_only_proof: bool = False,
    ) -> None:
        self._root = root
        self._provider: object | None = None
        self._attempt: object | None = None
        self._equity_symbols = equity_symbols
        self._mcx_symbols = mcx_symbols
        self._live_snapshot_proof = live_snapshot_proof
        self._quote_only_proof = quote_only_proof
        root.title(WINDOW_TITLE)
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=18)
        frame.grid(row=0, column=0)
        ttk.Label(frame, text="Kite status: DISCONNECTED").grid(
            row=0,
            column=0,
            sticky="w",
        )
        self._status = tk.StringVar(value="Ready to connect securely.")
        ttk.Label(
            frame,
            textvariable=self._status,
            justify="left",
            wraplength=720,
        ).grid(row=1, column=0, sticky="w", pady=(10, 14))
        self._connect = ttk.Button(
            frame,
            text="Connect to Kite",
            command=self._connect_to_kite,
        )
        self._connect.grid(row=2, column=0, sticky="w")
        root.protocol("WM_DELETE_WINDOW", self._close)

    def _connect_to_kite(self) -> None:
        self._connect.configure(state="disabled")
        self._status.set("Opening official Kite login…")
        try:
            provider = _build_provider()
            attempt = provider.begin_login()
        except ConfigurationError:
            self._finish(
                SanitizedAuthenticationEvidence(
                    "FAIL",
                    "FAIL",
                    "FAIL",
                    "FAIL",
                    "FAIL",
                    "INACTIVE",
                    "CONFIGURATION_UNAVAILABLE",
                )
            )
            return
        except Exception:
            self._finish(
                SanitizedAuthenticationEvidence(
                    "FAIL",
                    "FAIL",
                    "FAIL",
                    "FAIL",
                    "FAIL",
                    "INACTIVE",
                    "LOGIN_INITIATION_FAILED",
                )
            )
            return
        self._provider = provider
        self._attempt = attempt
        self._status.set(
            "Official Kite login opened. Complete authentication in the browser."
        )
        threading.Thread(
            target=self._complete,
            name="kronos-v2-authentication",
            daemon=True,
        ).start()

    def _complete(self) -> None:
        provider = self._provider
        attempt = self._attempt
        if provider is None or attempt is None:
            return
        try:
            outcome = provider.complete_callback(attempt)  # type: ignore[attr-defined]
            active = False
            if outcome.state is AuthenticationAttemptState.SUCCEEDED:
                capability = provider.authenticated_read_only_capability()  # type: ignore[attr-defined]
                active = getattr(capability, "active", False) is True
            succeeded = (
                outcome.state is AuthenticationAttemptState.SUCCEEDED
                and outcome.binding_result is PrincipalBindingResult.MATCHED
                and active
            )
            if succeeded:
                try:
                    if self._live_snapshot_proof:
                        if self._quote_only_proof and self._equity_symbols:
                            live_proofs = execute_equity_quote_batch_proof(
                                provider,
                                symbols=self._equity_symbols,
                                now=datetime.now(UTC),
                            )
                        elif self._quote_only_proof and self._mcx_symbols:
                            live_proofs = execute_mcx_quote_batch_proof(
                                provider,
                                symbols=self._mcx_symbols,
                                now=datetime.now(UTC),
                            )
                        else:
                            live_proofs = execute_live_snapshot_proof(
                                provider,
                                now=datetime.now(UTC),
                                quote_only=self._quote_only_proof,
                            )
                        proofs = ()
                    elif self._equity_symbols:
                        proofs = execute_equity_batch_proof(
                            provider,
                            symbols=self._equity_symbols,
                            now=datetime.now(UTC),
                        )
                    elif self._mcx_symbols:
                        proofs = execute_mcx_batch_proof(
                            provider,
                            symbols=self._mcx_symbols,
                            now=datetime.now(UTC),
                        )
                    else:
                        proofs = execute_historical_proof(
                            provider,
                            now=datetime.now(UTC),
                        )
                    if not self._live_snapshot_proof:
                        live_proofs = ()
                except Exception:
                    evidence = SanitizedAuthenticationEvidence(
                        "PASS",
                        "PASS",
                        "PASS",
                        "PASS",
                        "PASS",
                        "ACTIVE",
                        "SANITIZED_MARKET_DATA_FAILURE",
                        "FAIL",
                    )
                else:
                    evidence = SanitizedAuthenticationEvidence(
                        "PASS",
                        "PASS",
                        "PASS",
                        "PASS",
                        "PASS",
                        "ACTIVE",
                        instrument_master="PASS",
                        historical_proofs=proofs,
                        live_snapshot_proofs=live_proofs,
                    )
            else:
                callback = "PASS" if outcome.callback_consumed else "FAIL"
                exchange = "PASS" if outcome.binding_result is not None else "FAIL"
                principal = (
                    "PASS"
                    if outcome.binding_result is PrincipalBindingResult.MATCHED
                    else "FAIL"
                )
                failure = getattr(
                    outcome.failure_code,
                    "value",
                    "SANITIZED_AUTHENTICATION_FAILURE",
                )
                evidence = SanitizedAuthenticationEvidence(
                    "FAIL",
                    "PASS",
                    callback,
                    exchange,
                    principal,
                    "INACTIVE",
                    failure,
                )
        except Exception:
            evidence = SanitizedAuthenticationEvidence(
                "FAIL",
                "PASS",
                "FAIL",
                "FAIL",
                "FAIL",
                "INACTIVE",
                "SANITIZED_AUTHENTICATION_FAILURE",
            )
        self._root.after(0, lambda: self._finish(evidence))

    def _finish(self, evidence: SanitizedAuthenticationEvidence) -> None:
        rendered = evidence.render()
        self._status.set(rendered)
        print(rendered, flush=True)

    def _close(self) -> None:
        provider = self._provider
        attempt = self._attempt
        if provider is not None and attempt is not None:
            try:
                provider.cancel_authentication_attempt(attempt)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                provider.end_kronos_session()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--equity-symbols-csv", type=Path)
    parser.add_argument("--mcx-symbol", action="append", default=[])
    parser.add_argument("--live-snapshot-proof", action="store_true")
    parser.add_argument("--quote-only-proof", action="store_true")
    arguments = parser.parse_args()
    symbols = (
        load_equity_symbols(arguments.equity_symbols_csv)
        if arguments.equity_symbols_csv is not None
        else ()
    )
    root = tk.Tk()
    _AuthenticationWindow(
        root,
        equity_symbols=symbols,
        mcx_symbols=tuple(arguments.mcx_symbol),
        live_snapshot_proof=(
            arguments.live_snapshot_proof or arguments.quote_only_proof
        ),
        quote_only_proof=arguments.quote_only_proof,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
