"""Development-only GUI proof for the authenticated read-only Kite path."""

from __future__ import annotations

from collections.abc import Callable
import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import re
import secrets
import threading
import time
import tkinter as tk
from tkinter import ttk
import webbrowser

from kronos.configuration.apple_keychain import (
    AppleKeychainCredentialSource,
    AppleKeychainIntendedPrincipalResolver,
    run_security_framework_subprocess,
)
from kronos.configuration.exceptions import ConfigurationError
from kronos.configuration.loader import load_provider_authentication_configuration
from kronos.provider.adapters.kite.authentication import (
    create_kite_authentication_adapter,
)
from kronos.provider.adapters.kite.navigation import KiteLoginNavigator
from kronos.provider.callbacks.loopback import (
    LoopbackAuthenticationCallbackListener,
    create_standard_library_server,
)
from kronos.provider.contracts.instrument import (
    InstrumentKind,
    InstrumentResolutionError,
    InstrumentResolutionFailure,
    InstrumentResolutionRequest,
)
from kronos.provider.contracts.market_data import (
    HistoricalCandleRequest,
    HistoricalDataError,
    HistoricalDataFailure,
    HistoricalInterval,
    LiveSnapshotError,
)
from kronos.provider.kite.adapter.kite_provider import KiteProvider
from kronos.provider.kite.auth.kite_authentication import KiteAuthentication
from kronos.provider.kite.instruments.kite_instrument_provider import (
    KiteInstrumentProvider,
)
from kronos.provider.kite.marketdata.kite_market_data_provider import (
    KiteMarketDataProvider,
)
from kronos.provider.models.authentication import AuthenticationAttemptState
from kronos.provider.services.provider_authentication import (
    ProviderAuthenticationService,
)


WINDOW_TITLE = "KRONOS — Provider Foundation V2 Historical Proof"


@dataclass(frozen=True, slots=True)
class SanitizedHistoricalProof:
    instrument: str
    status: str
    interval: str = ""
    candle_count: int = 0
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    failure: str = ""

    def render(self) -> str:
        if self.status == "PASS":
            return (
                f"{self.instrument}: PASS | {self.interval} | "
                f"candles={self.candle_count} | "
                f"first={self.first_timestamp.isoformat()} | "
                f"last={self.last_timestamp.isoformat()}"
            )
        suffix = f" | {self.failure}" if self.failure else ""
        return f"{self.instrument}: {self.status}{suffix}"


@dataclass(frozen=True, slots=True)
class SanitizedLiveSnapshotProof:
    """Sanitized evidence for three independent live snapshot operations."""

    instrument: str
    quote: str
    ltp: str
    ohlc: str
    quote_value: str = ""
    ltp_value: str = ""
    ohlc_value: str = ""
    quote_failure: str = ""
    ltp_failure: str = ""
    ohlc_failure: str = ""

    def render(self) -> str:
        lines = [f"{self.instrument}:"]
        for label, status, value, failure in (
            ("Quote", self.quote, self.quote_value, self.quote_failure),
            ("LTP", self.ltp, self.ltp_value, self.ltp_failure),
            ("OHLC", self.ohlc, self.ohlc_value, self.ohlc_failure),
        ):
            suffix = f" | {value}" if value else f" | {failure}" if failure else ""
            lines.append(f"{label}: {status}{suffix}")
        return "\n".join(lines)


_TARGETS = (
    ("RELIANCE", InstrumentKind.NSE_EQUITY),
    ("NIFTY", InstrumentKind.NSE_INDEX),
    ("GOLD", InstrumentKind.MCX_FUTURE),
    ("USDINR", InstrumentKind.CDS_FUTURE),
)
_LIVE_TARGETS = (
    ("RELIANCE", "RELIANCE", InstrumentKind.NSE_EQUITY),
    ("NIFTY 50", "NIFTY", InstrumentKind.NSE_INDEX),
    ("GOLDM", "GOLDM", InstrumentKind.MCX_FUTURE),
)
_EQUITY_SYMBOL = re.compile(r"[A-Z0-9_&-]{1,32}\Z")


def execute_historical_proof(
    provider: object,
    *,
    now: datetime,
) -> tuple[SanitizedHistoricalProof, ...]:
    """Run the bounded post-authentication proof and return sanitized evidence."""

    capability_factory = getattr(
        provider,
        "authenticated_read_only_capability",
        None,
    )
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    as_of = now.date()
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=5)
    proofs: list[SanitizedHistoricalProof] = []
    for symbol, kind in _TARGETS:
        try:
            resolved = instruments.resolve(
                InstrumentResolutionRequest(
                    kind=kind,
                    symbol=symbol,
                    as_of=as_of,
                )
            )
        except InstrumentResolutionError as error:
            if (
                symbol == "USDINR"
                and error.failure is InstrumentResolutionFailure.NO_MATCH
            ):
                proofs.append(
                    SanitizedHistoricalProof(symbol, "NOT AVAILABLE")
                )
            else:
                proofs.append(
                    SanitizedHistoricalProof(
                        symbol,
                        "FAIL",
                        failure=f"RESOLUTION_{error.failure.value}",
                    )
                )
            continue
        except Exception:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure="RESOLUTION_SANITIZED_PROVIDER_FAILURE",
                )
            )
            continue

        try:
            candles = market_data.historical_candles(
                HistoricalCandleRequest(
                    instrument=resolved,
                    start=start,
                    end=end,
                    interval=HistoricalInterval.SIXTY_MINUTE,
                )
            )
            if not candles:
                raise HistoricalDataError(
                    failure=HistoricalDataFailure.MALFORMED_PROVIDER_DATA
                )
        except HistoricalDataError as error:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure=f"HISTORY_{error.failure.value}",
                )
            )
        except Exception:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure="HISTORY_SANITIZED_PROVIDER_FAILURE",
                )
            )
        else:
            proofs.append(
                SanitizedHistoricalProof(
                    instrument=symbol,
                    status="PASS",
                    interval=HistoricalInterval.SIXTY_MINUTE.value,
                    candle_count=len(candles),
                    first_timestamp=candles[0].timestamp,
                    last_timestamp=candles[-1].timestamp,
                )
            )
    return tuple(proofs)


def execute_live_snapshot_proof(
    provider: object,
    *,
    now: datetime,
    quote_only: bool = False,
) -> tuple[SanitizedLiveSnapshotProof, ...]:
    """Run three bounded live operations without exposing Provider material."""

    capability_factory = getattr(
        provider,
        "authenticated_read_only_capability",
        None,
    )
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    proofs: list[SanitizedLiveSnapshotProof] = []
    for label, symbol, kind in _LIVE_TARGETS:
        try:
            resolved = instruments.resolve(
                InstrumentResolutionRequest(
                    kind=kind,
                    symbol=symbol,
                    as_of=now.date(),
                )
            )
        except InstrumentResolutionError as error:
            failure = f"RESOLUTION_{error.failure.value}"
            proofs.append(
                SanitizedLiveSnapshotProof(
                    label,
                    "FAIL",
                    "FAIL",
                    "FAIL",
                    quote_failure=failure,
                    ltp_failure=failure,
                    ohlc_failure=failure,
                )
            )
            continue
        except Exception:
            failure = "RESOLUTION_SANITIZED_PROVIDER_FAILURE"
            proofs.append(
                SanitizedLiveSnapshotProof(
                    label,
                    "FAIL",
                    "FAIL",
                    "FAIL",
                    quote_failure=failure,
                    ltp_failure=failure,
                    ohlc_failure=failure,
                )
            )
            continue

        quote_status, quote_value, quote_failure = _snapshot_operation(
            lambda: market_data.quote(resolved),
            lambda result: (
                f"last={result.last_price} | "
                f"ohlc={result.ohlc.open}/{result.ohlc.high}/"
                f"{result.ohlc.low}/{result.ohlc.close} | "
                f"timestamp={result.timestamp.isoformat()}"
            ),
        )
        if quote_only:
            ltp_status, ltp_value, ltp_failure = "NOT RUN", "", ""
            ohlc_status, ohlc_value, ohlc_failure = "NOT RUN", "", ""
        else:
            ltp_status, ltp_value, ltp_failure = _snapshot_operation(
                lambda: market_data.ltp(resolved),
                lambda result: f"last={result.last_price}",
            )
            ohlc_status, ohlc_value, ohlc_failure = _snapshot_operation(
                lambda: market_data.ohlc(resolved),
                lambda result: (
                    f"last={result.last_price} | "
                    f"ohlc={result.ohlc.open}/{result.ohlc.high}/"
                    f"{result.ohlc.low}/{result.ohlc.close}"
                ),
            )
        proofs.append(
            SanitizedLiveSnapshotProof(
                instrument=label,
                quote=quote_status,
                ltp=ltp_status,
                ohlc=ohlc_status,
                quote_value=quote_value,
                ltp_value=ltp_value,
                ohlc_value=ohlc_value,
                quote_failure=quote_failure,
                ltp_failure=ltp_failure,
                ohlc_failure=ohlc_failure,
            )
        )
    return tuple(proofs)


def execute_equity_quote_batch_proof(
    provider: object,
    *,
    symbols: tuple[str, ...],
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(1.05),
) -> tuple[SanitizedLiveSnapshotProof, ...]:
    """Quote each supplied NSE equity through one retained read-only capability."""

    capability_factory = getattr(provider, "authenticated_read_only_capability", None)
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    master = instruments.retrieve("NSE")
    proofs: list[SanitizedLiveSnapshotProof] = []
    quote_count = 0
    for symbol in symbols:
        try:
            resolved = instruments.resolve_from_records(
                master,
                InstrumentResolutionRequest(
                    kind=InstrumentKind.NSE_EQUITY,
                    symbol=_kite_equity_symbol(symbol),
                    as_of=now.date(),
                ),
            )
        except InstrumentResolutionError as error:
            proofs.append(
                SanitizedLiveSnapshotProof(
                    symbol,
                    "FAIL",
                    "NOT RUN",
                    "NOT RUN",
                    quote_failure=f"RESOLUTION_{error.failure.value}",
                )
            )
            continue
        except Exception:
            proofs.append(
                SanitizedLiveSnapshotProof(
                    symbol,
                    "FAIL",
                    "NOT RUN",
                    "NOT RUN",
                    quote_failure="RESOLUTION_SANITIZED_PROVIDER_FAILURE",
                )
            )
            continue
        if quote_count:
            pace()
        quote_count += 1
        quote_status, quote_value, quote_failure = _snapshot_operation(
            lambda resolved=resolved: market_data.quote(resolved),
            lambda result: (
                f"last={result.last_price} | "
                f"ohlc={result.ohlc.open}/{result.ohlc.high}/"
                f"{result.ohlc.low}/{result.ohlc.close} | "
                f"timestamp={result.timestamp.isoformat()}"
            ),
        )
        proofs.append(
            SanitizedLiveSnapshotProof(
                symbol,
                quote_status,
                "NOT RUN",
                "NOT RUN",
                quote_value=quote_value,
                quote_failure=quote_failure,
            )
        )
    return tuple(proofs)


def execute_mcx_quote_batch_proof(
    provider: object,
    *,
    symbols: tuple[str, ...],
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(1.05),
) -> tuple[SanitizedLiveSnapshotProof, ...]:
    """Quote supplied nearest unexpired MCX futures through one capability."""

    capability_factory = getattr(provider, "authenticated_read_only_capability", None)
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    master = instruments.retrieve("MCX")
    proofs: list[SanitizedLiveSnapshotProof] = []
    quote_count = 0
    for symbol in symbols:
        try:
            resolved = instruments.resolve_from_records(
                master,
                InstrumentResolutionRequest(
                    kind=InstrumentKind.MCX_FUTURE,
                    symbol=symbol,
                    as_of=now.date(),
                ),
            )
        except InstrumentResolutionError as error:
            proofs.append(
                SanitizedLiveSnapshotProof(
                    symbol,
                    "FAIL",
                    "NOT RUN",
                    "NOT RUN",
                    quote_failure=f"RESOLUTION_{error.failure.value}",
                )
            )
            continue
        except Exception:
            proofs.append(
                SanitizedLiveSnapshotProof(
                    symbol,
                    "FAIL",
                    "NOT RUN",
                    "NOT RUN",
                    quote_failure="RESOLUTION_SANITIZED_PROVIDER_FAILURE",
                )
            )
            continue
        if quote_count:
            pace()
        quote_count += 1
        quote_status, quote_value, quote_failure = _snapshot_operation(
            lambda resolved=resolved: market_data.quote(resolved),
            lambda result: (
                f"last={result.last_price} | "
                f"ohlc={result.ohlc.open}/{result.ohlc.high}/"
                f"{result.ohlc.low}/{result.ohlc.close} | "
                f"timestamp={result.timestamp.isoformat()}"
            ),
        )
        proofs.append(
            SanitizedLiveSnapshotProof(
                symbol,
                quote_status,
                "NOT RUN",
                "NOT RUN",
                quote_value=quote_value,
                quote_failure=quote_failure,
            )
        )
    return tuple(proofs)


def _snapshot_operation(
    operation: Callable[[], object],
    render: Callable[[object], str],
) -> tuple[str, str, str]:
    try:
        result = operation()
        return "PASS", render(result), ""
    except LiveSnapshotError as error:
        return "FAIL", "", error.failure.value
    except Exception:
        return "FAIL", "", "SANITIZED_PROVIDER_FAILURE"


def load_equity_symbols(path: Path) -> tuple[str, ...]:
    """Load one bounded, non-sensitive symbol column from a Sponsor CSV."""

    try:
        with path.open(newline="", encoding="utf-8-sig") as source:
            rows = tuple(csv.DictReader(source))
    except (OSError, UnicodeError, csv.Error):
        raise ValueError("SYMBOL_FILE_INVALID") from None
    symbols = tuple(row.get("Symbol", "") for row in rows)
    if (
        not symbols
        or len(symbols) > 500
        or len(set(symbols)) != len(symbols)
        or any(_EQUITY_SYMBOL.fullmatch(symbol) is None for symbol in symbols)
    ):
        raise ValueError("SYMBOL_FILE_INVALID")
    return symbols


def execute_equity_batch_proof(
    provider: object,
    *,
    symbols: tuple[str, ...],
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
) -> tuple[SanitizedHistoricalProof, ...]:
    """Retrieve one NSE master and test bounded history for each supplied equity."""

    capability_factory = getattr(provider, "authenticated_read_only_capability", None)
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    master = instruments.retrieve("NSE")
    as_of = now.date()
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=5)
    proofs: list[SanitizedHistoricalProof] = []
    for index, symbol in enumerate(symbols):
        request = InstrumentResolutionRequest(
            kind=InstrumentKind.NSE_EQUITY,
            symbol=_kite_equity_symbol(symbol),
            as_of=as_of,
        )
        try:
            resolved = instruments.resolve_from_records(master, request)
        except InstrumentResolutionError as error:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure=f"RESOLUTION_{error.failure.value}",
                )
            )
            continue
        if index:
            pace()
        try:
            candles = market_data.historical_candles(
                HistoricalCandleRequest(
                    instrument=resolved,
                    start=start,
                    end=end,
                    interval=HistoricalInterval.SIXTY_MINUTE,
                )
            )
            if not candles:
                raise HistoricalDataError(
                    HistoricalDataFailure.MALFORMED_PROVIDER_DATA
                )
        except HistoricalDataError as error:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure=f"HISTORY_{error.failure.value}",
                )
            )
        except Exception:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure="HISTORY_SANITIZED_PROVIDER_FAILURE",
                )
            )
        else:
            proofs.append(
                SanitizedHistoricalProof(
                    instrument=symbol,
                    status="PASS",
                    interval=HistoricalInterval.SIXTY_MINUTE.value,
                    candle_count=len(candles),
                    first_timestamp=candles[0].timestamp,
                    last_timestamp=candles[-1].timestamp,
                )
            )
    return tuple(proofs)


def execute_mcx_batch_proof(
    provider: object,
    *,
    symbols: tuple[str, ...],
    now: datetime,
    pace: Callable[[], None] = lambda: time.sleep(0.4),
) -> tuple[SanitizedHistoricalProof, ...]:
    """Retrieve one MCX master and test bounded history for supplied futures."""

    capability_factory = getattr(provider, "authenticated_read_only_capability", None)
    if not callable(capability_factory):
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    capability = capability_factory()
    if capability is None or getattr(capability, "active", False) is not True:
        raise RuntimeError("READ_ONLY_CAPABILITY_UNAVAILABLE")
    instruments = KiteInstrumentProvider(capability)
    market_data = KiteMarketDataProvider(capability)
    master = instruments.retrieve("MCX")
    as_of = now.date()
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=5)
    proofs: list[SanitizedHistoricalProof] = []
    for index, symbol in enumerate(symbols):
        try:
            resolved = instruments.resolve_from_records(
                master,
                InstrumentResolutionRequest(
                    kind=InstrumentKind.MCX_FUTURE,
                    symbol=symbol,
                    as_of=as_of,
                ),
            )
        except InstrumentResolutionError as error:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure=f"RESOLUTION_{error.failure.value}",
                )
            )
            continue
        if index:
            pace()
        try:
            candles = market_data.historical_candles(
                HistoricalCandleRequest(
                    instrument=resolved,
                    start=start,
                    end=end,
                    interval=HistoricalInterval.SIXTY_MINUTE,
                )
            )
            if not candles:
                raise HistoricalDataError(
                    HistoricalDataFailure.MALFORMED_PROVIDER_DATA
                )
        except HistoricalDataError as error:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure=f"HISTORY_{error.failure.value}",
                )
            )
        except Exception:
            proofs.append(
                SanitizedHistoricalProof(
                    symbol,
                    "FAIL",
                    failure="HISTORY_SANITIZED_PROVIDER_FAILURE",
                )
            )
        else:
            proofs.append(
                SanitizedHistoricalProof(
                    instrument=symbol,
                    status="PASS",
                    interval=HistoricalInterval.SIXTY_MINUTE.value,
                    candle_count=len(candles),
                    first_timestamp=candles[0].timestamp,
                    last_timestamp=candles[-1].timestamp,
                )
            )
    return tuple(proofs)


def _kite_equity_symbol(source_symbol: str) -> str:
    """Translate TradingView's underscore form to NSE's hyphen form."""

    return source_symbol.replace("_", "-")


def _build_provider() -> KiteProvider:
    configuration = load_provider_authentication_configuration()
    clock = lambda: datetime.now(UTC)
    service = ProviderAuthenticationService(
        configuration,
        credential_source=AppleKeychainCredentialSource(
            provider=configuration.provider,
            runner=run_security_framework_subprocess,
        ),
        principal_resolver=AppleKeychainIntendedPrincipalResolver(
            provider=configuration.provider,
            runner=run_security_framework_subprocess,
        ),
        adapter_factory=create_kite_authentication_adapter,
        listener_factory=lambda: LoopbackAuthenticationCallbackListener(
            server_factory=create_standard_library_server,
            clock=clock,
        ),
        navigator=KiteLoginNavigator(opener=webbrowser.open_new_tab),
        clock=clock,
        identity_factory=lambda: f"v2-proof-{secrets.token_hex(16)}",
    )
    return KiteProvider(KiteAuthentication(service))


class _ProofWindow:
    """Minimal Sponsor control surface with no sensitive input fields."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._provider: KiteProvider | None = None
        self._attempt: object | None = None
        root.title(WINDOW_TITLE)
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=18)
        frame.grid(row=0, column=0)
        ttk.Label(
            frame,
            text="Read-only Kite authentication and historical-data proof",
        ).grid(row=0, column=0, sticky="w")
        self._status = tk.StringVar(
            value="Ready. No Provider activity has started."
        )
        ttk.Label(
            frame,
            textvariable=self._status,
            justify="left",
            wraplength=760,
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
        self._status.set("Starting secure browser authentication…")
        try:
            provider = _build_provider()
            attempt = provider.begin_login()
        except ConfigurationError:
            self._status.set("Authentication: FAIL | CONFIGURATION_UNAVAILABLE")
            return
        except Exception:
            self._status.set("Authentication: FAIL | SANITIZED_LOCAL_FAILURE")
            return
        self._provider = provider
        self._attempt = attempt
        self._status.set(
            "Official Kite login opened. Complete authentication in the browser."
        )
        threading.Thread(
            target=self._complete,
            name="kronos-v2-historical-proof",
            daemon=True,
        ).start()

    def _complete(self) -> None:
        provider = self._provider
        attempt = self._attempt
        if provider is None or attempt is None:
            return
        try:
            outcome = provider.complete_callback(attempt)  # type: ignore[arg-type]
            if outcome.state is not AuthenticationAttemptState.SUCCEEDED:
                rendered = (
                    "Authentication: FAIL | "
                    f"{getattr(outcome.failure_code, 'value', 'SANITIZED_FAILURE')}"
                )
            else:
                proofs = execute_historical_proof(
                    provider,
                    now=datetime.now(UTC),
                )
                rendered = "Authentication: PASS\n" + "\n".join(
                    proof.render() for proof in proofs
                )
        except Exception:
            rendered = "Authentication: FAIL | SANITIZED_PROVIDER_FAILURE"
        finally:
            try:
                provider.end_kronos_session()
            except Exception:
                pass
        print(rendered, flush=True)
        self._root.after(0, lambda: self._status.set(rendered))

    def _close(self) -> None:
        provider = self._provider
        attempt = self._attempt
        if provider is not None and attempt is not None:
            try:
                provider.cancel_authentication_attempt(attempt)  # type: ignore[arg-type]
            except Exception:
                pass
            try:
                provider.end_kronos_session()
            except Exception:
                pass
        self._root.destroy()


def main() -> None:
    root = tk.Tk()
    _ProofWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
