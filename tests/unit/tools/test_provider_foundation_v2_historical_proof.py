from datetime import UTC, date, datetime
import inspect
from pathlib import Path

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    LiveSnapshotError,
    LiveSnapshotFailure,
    LtpSnapshot,
    OhlcSnapshot,
    OhlcValues,
    QuoteSnapshot,
)
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from tools.provider_pilots import provider_foundation_v2_historical_proof as proof


class _Capability:
    operations = frozenset(ReadOnlyProviderOperation)
    active = True

    def __init__(self, *, include_usdinr: bool = True) -> None:
        self.include_usdinr = include_usdinr
        self.exchanges: list[str] = []
        self.historical_instruments: list[str] = []
        self.live_operations: list[tuple[str, str]] = []

    def instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
        self.exchanges.append(exchange)
        records = {
            "NSE": (
                InstrumentRecord(
                    provider="KITE",
                    exchange="NSE",
                    segment="NSE",
                    trading_symbol="RELIANCE",
                    name="RELIANCE",
                    instrument_type="EQ",
                    expiry=None,
                ),
                InstrumentRecord(
                    provider="KITE",
                    exchange="NSE",
                    segment="INDICES",
                    trading_symbol="NIFTY 50",
                    name="NIFTY 50",
                    instrument_type="EQ",
                    expiry=None,
                ),
            ),
            "MCX": (
                InstrumentRecord(
                    provider="KITE",
                    exchange="MCX",
                    segment="MCX-FUT",
                    trading_symbol="GOLD26AUGFUT",
                    name="GOLD",
                    instrument_type="FUT",
                    expiry=date(2026, 8, 28),
                ),
                InstrumentRecord(
                    provider="KITE",
                    exchange="MCX",
                    segment="MCX-FUT",
                    trading_symbol="GOLDM26AUGFUT",
                    name="",
                    instrument_type="FUT",
                    expiry=date(2026, 8, 28),
                ),
            ),
            "CDS": (
                InstrumentRecord(
                    provider="KITE",
                    exchange="CDS",
                    segment="CDS-FUT",
                    trading_symbol="USDINR26AUGFUT",
                    name="USDINR",
                    instrument_type="FUT",
                    expiry=date(2026, 8, 26),
                ),
            ) if self.include_usdinr else (),
        }
        return records[exchange]

    def historical_candles(self, request):  # type: ignore[no-untyped-def]
        self.historical_instruments.append(request.instrument.trading_symbol)
        return (
            HistoricalCandle(
                timestamp=datetime(2026, 8, 7, 4, 0, tzinfo=UTC),
                open=100.0,
                high=102.0,
                low=99.0,
                close=101.0,
                volume=1000,
            ),
        )

    def quote(self, instrument: InstrumentRecord) -> QuoteSnapshot:
        self.live_operations.append(("quote", instrument.trading_symbol))
        return QuoteSnapshot(
            instrument=instrument,
            timestamp=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
            last_price=102.5,
            volume=1000,
            ohlc=_ohlc(),
        )

    def ltp(self, instrument: InstrumentRecord) -> LtpSnapshot:
        self.live_operations.append(("ltp", instrument.trading_symbol))
        return LtpSnapshot(instrument=instrument, last_price=102.5)

    def ohlc(self, instrument: InstrumentRecord) -> OhlcSnapshot:
        self.live_operations.append(("ohlc", instrument.trading_symbol))
        return OhlcSnapshot(
            instrument=instrument,
            last_price=102.5,
            ohlc=_ohlc(),
        )


def _ohlc() -> OhlcValues:
    return OhlcValues(open=100.0, high=104.0, low=99.0, close=101.0)


class _Provider:
    def __init__(self, capability: _Capability) -> None:
        self.capability = capability

    def authenticated_read_only_capability(self) -> _Capability:
        return self.capability


def test_development_proof_uses_all_representative_read_only_paths() -> None:
    capability = _Capability()

    evidence = proof.execute_historical_proof(
        _Provider(capability),
        now=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    assert tuple(item.instrument for item in evidence) == (
        "RELIANCE",
        "NIFTY",
        "GOLD",
        "USDINR",
    )
    assert all(item.status == "PASS" for item in evidence)
    assert all(item.candle_count == 1 for item in evidence)
    assert capability.exchanges == ["NSE", "NSE", "MCX", "CDS"]
    assert capability.historical_instruments == [
        "RELIANCE",
        "NIFTY 50",
        "GOLD26AUGFUT",
        "USDINR26AUGFUT",
    ]


def test_usdinr_absence_is_sanitized_as_not_available() -> None:
    capability = _Capability(include_usdinr=False)

    evidence = proof.execute_historical_proof(
        _Provider(capability),
        now=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    assert evidence[-1].instrument == "USDINR"
    assert evidence[-1].status == "NOT AVAILABLE"
    assert evidence[-1].failure == ""


def test_live_snapshot_proof_uses_same_capability_for_all_representatives() -> None:
    capability = _Capability()

    evidence = proof.execute_live_snapshot_proof(
        _Provider(capability),
        now=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
    )

    assert tuple(item.instrument for item in evidence) == (
        "RELIANCE",
        "NIFTY 50",
        "GOLDM",
    )
    assert all(item.quote == "PASS" for item in evidence)
    assert all(item.ltp == "PASS" for item in evidence)
    assert all(item.ohlc == "PASS" for item in evidence)
    assert capability.live_operations == [
        (operation, instrument)
        for instrument in ("RELIANCE", "NIFTY 50", "GOLDM26AUGFUT")
        for operation in ("quote", "ltp", "ohlc")
    ]
    rendered = "\n".join(item.render() for item in evidence)
    assert "last=102.5" in rendered
    assert "instrument_token" not in rendered


def test_one_live_operation_failure_does_not_stop_remaining_proof() -> None:
    class _PartialFailureCapability(_Capability):
        def ltp(self, instrument: InstrumentRecord) -> LtpSnapshot:
            if instrument.trading_symbol == "NIFTY 50":
                raise LiveSnapshotError(LiveSnapshotFailure.PROVIDER_FAILURE)
            return super().ltp(instrument)

    capability = _PartialFailureCapability()

    evidence = proof.execute_live_snapshot_proof(
        _Provider(capability),
        now=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
    )

    assert evidence[1].quote == "PASS"
    assert evidence[1].ltp == "FAIL"
    assert evidence[1].ltp_failure == "PROVIDER_FAILURE"
    assert evidence[1].ohlc == "PASS"
    assert evidence[2].instrument == "GOLDM"
    assert evidence[2].quote == evidence[2].ltp == evidence[2].ohlc == "PASS"


def test_quote_only_proof_does_not_call_ltp_or_ohlc() -> None:
    capability = _Capability()

    evidence = proof.execute_live_snapshot_proof(
        _Provider(capability),
        now=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        quote_only=True,
    )

    assert all(item.quote == "PASS" for item in evidence)
    assert all(item.ltp == "NOT RUN" for item in evidence)
    assert all(item.ohlc == "NOT RUN" for item in evidence)
    assert capability.live_operations == [
        ("quote", instrument)
        for instrument in ("RELIANCE", "NIFTY 50", "GOLDM26AUGFUT")
    ]


def test_equity_quote_batch_reuses_one_master_and_calls_quote_only() -> None:
    class _BatchCapability(_Capability):
        def instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
            self.exchanges.append(exchange)
            return tuple(
                InstrumentRecord(
                    provider="KITE",
                    exchange="NSE",
                    segment="NSE",
                    trading_symbol=symbol,
                    name=symbol,
                    instrument_type="EQ",
                    expiry=None,
                )
                for symbol in ("ADANIENT", "BAJAJ-AUTO", "RELIANCE")
            )

    capability = _BatchCapability()
    pace_count: list[None] = []

    evidence = proof.execute_equity_quote_batch_proof(
        _Provider(capability),
        symbols=("ADANIENT", "BAJAJ_AUTO", "RELIANCE"),
        now=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        pace=lambda: pace_count.append(None),
    )

    assert all(item.quote == "PASS" for item in evidence)
    assert all(item.ltp == "NOT RUN" for item in evidence)
    assert all(item.ohlc == "NOT RUN" for item in evidence)
    assert capability.exchanges == ["NSE"]
    assert capability.live_operations == [
        ("quote", instrument)
        for instrument in ("ADANIENT", "BAJAJ-AUTO", "RELIANCE")
    ]
    assert len(pace_count) == 2


def test_mcx_quote_batch_reuses_one_master_and_calls_quote_only() -> None:
    class _McxCapability(_Capability):
        def instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
            self.exchanges.append(exchange)
            return tuple(
                InstrumentRecord(
                    provider="KITE",
                    exchange="MCX",
                    segment="MCX-FUT",
                    trading_symbol=f"{symbol}26AUGFUT",
                    name="",
                    instrument_type="FUT",
                    expiry=date(2026, 8, 28),
                )
                for symbol in ("NATGAS", "CRUDEOIL", "GOLDM", "SILVERM", "COPPER")
            )

    capability = _McxCapability()
    pace_count: list[None] = []
    symbols = ("NATGAS", "CRUDEOIL", "GOLDM", "SILVERM", "COPPER")

    evidence = proof.execute_mcx_quote_batch_proof(
        _Provider(capability),
        symbols=symbols,
        now=datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
        pace=lambda: pace_count.append(None),
    )

    assert all(item.quote == "PASS" for item in evidence)
    assert all(item.ltp == "NOT RUN" for item in evidence)
    assert all(item.ohlc == "NOT RUN" for item in evidence)
    assert capability.exchanges == ["MCX"]
    assert capability.live_operations == [
        ("quote", f"{symbol}26AUGFUT") for symbol in symbols
    ]
    assert len(pace_count) == 4


def test_resolution_and_history_failures_remain_sanitized_and_distinct() -> None:
    class _ResolutionFailureCapability(_Capability):
        def instrument_records(self, exchange: str):  # type: ignore[no-untyped-def]
            if exchange == "NSE":
                raise RuntimeError("raw instrument payload")
            return super().instrument_records(exchange)

    resolution = proof.execute_historical_proof(
        _Provider(_ResolutionFailureCapability()),
        now=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
    )

    assert resolution[0].failure == "RESOLUTION_SANITIZED_PROVIDER_FAILURE"
    assert "raw instrument payload" not in resolution[0].render()


def test_equity_batch_retrieves_one_master_and_tests_every_symbol() -> None:
    class _BatchCapability(_Capability):
        def instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
            self.exchanges.append(exchange)
            return tuple(
                InstrumentRecord(
                    provider="KITE",
                    exchange="NSE",
                    segment="NSE",
                    trading_symbol=symbol,
                    name=symbol,
                    instrument_type="EQ",
                    expiry=None,
                )
                for symbol in ("ADANIENT", "BAJAJ-AUTO", "RELIANCE")
            )

    capability = _BatchCapability()
    pace_count: list[None] = []

    evidence = proof.execute_equity_batch_proof(
        _Provider(capability),
        symbols=("ADANIENT", "BAJAJ_AUTO", "RELIANCE"),
        now=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        pace=lambda: pace_count.append(None),
    )

    assert all(item.status == "PASS" for item in evidence)
    assert capability.exchanges == ["NSE"]
    assert capability.historical_instruments == [
        "ADANIENT",
        "BAJAJ-AUTO",
        "RELIANCE",
    ]
    assert len(pace_count) == 2


def test_symbol_csv_is_bounded_unique_and_non_sensitive(tmp_path: Path) -> None:
    path = tmp_path / "symbols.csv"
    path.write_text(
        "Symbol,Description\nADANIENT,Adani Enterprises\nRELIANCE,Reliance\n",
        encoding="utf-8",
    )

    assert proof.load_equity_symbols(path) == ("ADANIENT", "RELIANCE")


def test_mcx_batch_retrieves_one_master_and_tests_requested_futures() -> None:
    class _McxCapability(_Capability):
        def instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
            self.exchanges.append(exchange)
            return tuple(
                InstrumentRecord(
                    provider="KITE",
                    exchange="MCX",
                    segment="MCX-FUT",
                    trading_symbol=f"{symbol}26AUGFUT",
                    name="",
                    instrument_type="FUT",
                    expiry=date(2026, 8, 28),
                )
                for symbol in ("GOLDM", "SILVERM", "COPPER")
            )

    capability = _McxCapability()
    pace_count: list[None] = []

    evidence = proof.execute_mcx_batch_proof(
        _Provider(capability),
        symbols=("GOLDM", "SILVERM", "COPPER"),
        now=datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
        pace=lambda: pace_count.append(None),
    )

    assert all(item.status == "PASS" for item in evidence)
    assert capability.exchanges == ["MCX"]
    assert capability.historical_instruments == [
        "GOLDM26AUGFUT",
        "SILVERM26AUGFUT",
        "COPPER26AUGFUT",
    ]
    assert len(pace_count) == 2


def test_entry_point_has_no_token_input_or_order_capability() -> None:
    source = inspect.getsource(proof)

    assert "KRONOS_KITE_ACCESS_TOKEN" not in source
    assert "paste" not in source.casefold()
    assert "place_order" not in source
    assert "modify_order" not in source
    assert "cancel_order" not in source
    assert "car017_live_authentication_launcher" not in source
    assert "LiveActivationContext" not in source


def test_gui_build_uses_application_configuration_and_secure_credential_source() -> None:
    source = inspect.getsource(proof._build_provider)

    assert "load_provider_authentication_configuration" in source
    assert "AppleKeychainCredentialSource" in source
    assert "AppleKeychainIntendedPrincipalResolver" in source
    assert "KRONOS_KITE_API_SECRET" not in source
    assert "KRONOS_KITE_ACCESS_TOKEN" not in source


def test_gui_maps_configuration_failure_to_one_sanitized_status() -> None:
    source = inspect.getsource(proof._ProofWindow._connect_to_kite)

    assert "except ConfigurationError" in source
    assert "CONFIGURATION_UNAVAILABLE" in source
