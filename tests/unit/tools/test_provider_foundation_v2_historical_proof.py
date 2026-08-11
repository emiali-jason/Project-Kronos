from datetime import UTC, date, datetime, timedelta
import inspect
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

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
from kronos.swing.daily_data import build_swing_daily_dataset
from kronos.swing.universe import enabled_swing_phase1_universe
from kronos.swing.zero import SwingDirection, SwingSetup


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


def test_universe_resolution_proof_resolves_all_98_without_market_data() -> None:
    class _UniverseCapability(_Capability):
        def instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
            self.exchanges.append(exchange)
            if exchange == "NSE":
                equities = tuple(
                    InstrumentRecord(
                        provider="KITE",
                        exchange="NSE",
                        segment="NSE",
                        trading_symbol=(
                            "BAJAJ-AUTO"
                            if member.canonical_identity == "BAJAJ_AUTO"
                            else member.canonical_identity
                        ),
                        name=member.canonical_identity,
                        instrument_type="EQ",
                        expiry=None,
                    )
                    for member in enabled_swing_phase1_universe()
                    if member.asset_class.value == "NSE_EQUITY"
                )
                return equities + (
                    InstrumentRecord(
                        "KITE", "NSE", "INDICES", "NIFTY 50", "NIFTY 50", "EQ", None
                    ),
                    InstrumentRecord(
                        "KITE", "NSE", "INDICES", "NIFTY BANK", "NIFTY BANK", "EQ", None
                    ),
                )
            return tuple(
                InstrumentRecord(
                    provider="KITE",
                    exchange="MCX",
                    segment="MCX-FUT",
                    trading_symbol=f"{member.canonical_identity}26AUGFUT",
                    name="",
                    instrument_type="FUT",
                    expiry=date(2026, 8, 28),
                )
                for member in enabled_swing_phase1_universe()
                if member.asset_class.value == "MCX_COMMODITY"
            )

    capability = _UniverseCapability()

    evidence = proof.execute_universe_resolution_proof(
        _Provider(capability),
        universe=enabled_swing_phase1_universe(),
        now=datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
    )

    assert len(evidence) == 98
    assert all(item.status == "PASS" for item in evidence)
    assert capability.exchanges == ["NSE", "MCX"]
    assert capability.historical_instruments == []
    mappings = {
        item.canonical_identity: item.provider_identity
        for item in evidence
        if item.canonical_identity != item.provider_identity
    }
    assert mappings["BAJAJ_AUTO"] == "BAJAJ-AUTO"
    assert mappings["NIFTY"] == "NIFTY 50"
    assert mappings["BANK NIFTY"] == "NIFTY BANK"


def test_swing_daily_dataset_proof_uses_one_retained_capability_for_all_98() -> None:
    class _UniverseDailyCapability(_Capability):
        def __init__(self) -> None:
            super().__init__()
            self.daily_requests = []

        def instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
            self.exchanges.append(exchange)
            if exchange == "NSE":
                equities = tuple(
                    InstrumentRecord(
                        provider="KITE",
                        exchange="NSE",
                        segment="NSE",
                        trading_symbol=(
                            "BAJAJ-AUTO"
                            if member.canonical_identity == "BAJAJ_AUTO"
                            else member.canonical_identity
                        ),
                        name=member.canonical_identity,
                        instrument_type="EQ",
                        expiry=None,
                    )
                    for member in enabled_swing_phase1_universe()
                    if member.asset_class.value == "NSE_EQUITY"
                )
                return equities + (
                    InstrumentRecord(
                        "KITE", "NSE", "INDICES", "NIFTY 50", "NIFTY 50", "EQ", None
                    ),
                    InstrumentRecord(
                        "KITE", "NSE", "INDICES", "NIFTY BANK", "NIFTY BANK", "EQ", None
                    ),
                )
            return tuple(
                InstrumentRecord(
                    provider="KITE",
                    exchange="MCX",
                    segment="MCX-FUT",
                    trading_symbol=f"{member.canonical_identity}26AUGFUT",
                    name="",
                    instrument_type="FUT",
                    expiry=date(2026, 8, 28),
                )
                for member in enabled_swing_phase1_universe()
                if member.asset_class.value == "MCX_COMMODITY"
            )

        def historical_candles(self, request):  # type: ignore[no-untyped-def]
            self.daily_requests.append(request)
            kolkata = ZoneInfo("Asia/Kolkata")
            return tuple(
                HistoricalCandle(
                    timestamp=datetime(2026, 7, 11, tzinfo=kolkata)
                    + timedelta(days=index),
                    open=100.0,
                    high=102.0,
                    low=99.0,
                    close=101.0,
                    volume=1000,
                )
                for index in range(31)
            )

    capability = _UniverseDailyCapability()
    pace_calls: list[None] = []
    ticks = iter((10.0, 13.5))

    evidence = proof.execute_swing_daily_dataset_proof(
        _Provider(capability),
        universe=enabled_swing_phase1_universe(),
        now=datetime(2026, 8, 10, 6, 30, tzinfo=UTC),
        pace=lambda: pace_calls.append(None),
        monotonic=lambda: next(ticks),
    )

    assert evidence.dataset.requested_count == 98
    assert evidence.dataset.ready_count == 98
    assert evidence.dataset.unavailable_count == 0
    assert evidence.nse_equities_ready == 91
    assert evidence.indices_ready == 2
    assert evidence.commodities_ready == 5
    assert evidence.current_incomplete_daily_excluded is True
    assert evidence.elapsed_seconds == 3.5
    assert evidence.failures == ()
    assert capability.exchanges == ["NSE", "MCX"]
    assert len(capability.daily_requests) == 98
    assert all(request.interval.value == "day" for request in capability.daily_requests)
    assert len(pace_calls) == 97
    assert "READY: 98/98" in evidence.render()
    assert "FAILED / UNAVAILABLE: 0/98" in evidence.render()


def test_swing_market_assessment_proof_times_only_analysis_and_is_sanitized(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    kolkata = ZoneInfo("Asia/Kolkata")
    now = datetime(2026, 8, 10, 12, 0, tzinfo=kolkata)

    def instrument(member):  # type: ignore[no-untyped-def]
        commodity = member.asset_class.value == "MCX_COMMODITY"
        return InstrumentRecord(
            provider="KITE",
            exchange="MCX" if commodity else "NSE",
            segment="MCX-FUT" if commodity else "NSE",
            trading_symbol=(
                f"{member.canonical_identity}26AUGFUT"
                if commodity
                else member.canonical_identity
            ),
            name=member.canonical_identity,
            instrument_type="FUT" if commodity else "EQ",
            expiry=date(2026, 8, 28) if commodity else None,
        )

    candles = tuple(
        HistoricalCandle(
            timestamp=datetime(2026, 7, 11, tzinfo=kolkata)
            + timedelta(days=index),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1000,
        )
        for index in range(30)
    )
    dataset = build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=instrument,
        historical_candles=lambda _request: candles,
        now=now,
    )
    daily = SimpleNamespace(dataset=dataset)
    provider = object()
    captured: list[object] = []

    def execute(received_provider, *, universe, now, pace):  # type: ignore[no-untyped-def]
        captured.extend((received_provider, universe, now, pace))
        return daily

    monkeypatch.setattr(proof, "execute_swing_daily_dataset_proof", execute)
    ticks = iter((5.0, 5.025))

    evidence = proof.execute_swing_market_assessment_proof(
        provider,
        universe=enabled_swing_phase1_universe(),
        now=now,
        pace=lambda: None,
        monotonic=lambda: next(ticks),
    )

    assert captured[0] is provider
    assert len(captured[1]) == 98  # type: ignore[arg-type]
    assert evidence.result.assessed_count == 98
    assert evidence.result.assessment_count == 196
    assert evidence.result.counts.pullback_no_setup == 98
    assert evidence.result.counts.breakout_forming == 98
    assert evidence.analysis_elapsed_seconds == pytest.approx(0.025)
    rendered = evidence.render()
    assert "Run identity: SWING-ZERO-V0-CLASSIFICATION-POLICY@" in rendered
    assert "Observation boundary: 2026-08-09T00:00:00+05:30" in rendered
    assert "Instruments assessed: 98/98" in rendered
    assert "Setup assessments: 196/196" in rendered
    assert "QUALIFIED instruments:\nNONE" in rendered
    assert "Analysis elapsed time: 0.025000 seconds" in rendered
    assert "CONSOLIDATION_BREAKOUT → NONE → FORMING →" in rendered
    assert "instrument_token" not in rendered


def test_stage5_proof_reconstructs_exact_frozen_boundary_and_renders_safely(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    boundary = proof.FROZEN_STAGE4_OBSERVATION_BOUNDARY
    provider = object()
    dataset = object()
    daily_calls: list[object] = []

    def daily(received_provider, *, universe, now, pace):  # type: ignore[no-untyped-def]
        daily_calls.extend((received_provider, universe, now, pace))
        return SimpleNamespace(dataset=dataset)

    market = SimpleNamespace(observation_boundary=boundary)
    monkeypatch.setattr(proof, "execute_swing_daily_dataset_proof", daily)
    monkeypatch.setattr(proof, "assess_swing_market", lambda received: market)

    identities = tuple(f"CANDIDATE-{index}" for index in range(10)) + (
        "HDFCBANK",
        "HDFCBANK",
    )
    candidates = tuple(
        SimpleNamespace(
            canonical_identity=identity,
            setup=(
                SwingSetup.CONSOLIDATION_BREAKOUT
                if index == 11
                else SwingSetup.PULLBACK_CONTINUATION
            ),
            direction=SwingDirection.SHORT,
        )
        for index, identity in enumerate(identities)
    )
    validation = SimpleNamespace(
        observation_boundary=boundary,
        candidates=candidates,
        unique_instrument_count=11,
        audits=tuple(
            SimpleNamespace(candidate=candidate, passed=True)
            for candidate in candidates
        ),
        forming_audits=(),
        forming_leakage=0,
        no_setup_leakage=0,
        passed=True,
    )

    def validate(received_market, received_dataset):  # type: ignore[no-untyped-def]
        assert received_market is market
        assert received_dataset is dataset
        return validation

    monkeypatch.setattr(proof, "validate_qualified_candidates", validate)

    evidence = proof.execute_swing_candidate_validation_proof(
        provider,
        universe=enabled_swing_phase1_universe(),
        pace=lambda: None,
    )

    assert daily_calls[0] is provider
    assert daily_calls[2] == boundary + timedelta(days=1)
    assert evidence.validation is validation
    rendered = evidence.render()
    assert "Stage 5: PASS" in rendered
    assert "Qualified setup assessments: 12/12" in rendered
    assert "Unique qualified instruments: 11/11" in rendered
    assert "FORMING leakage: 0" in rendered
    assert "NO_SETUP leakage: 0" in rendered
    assert "instrument_token" not in rendered


def test_stage7_proof_uses_exact_frozen_candidates_and_same_dataset(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    boundary = proof.FROZEN_STAGE4_OBSERVATION_BOUNDARY
    provider = object()
    candles = (SimpleNamespace(timestamp=boundary),)
    records = tuple(
        SimpleNamespace(canonical_identity=f"CANDIDATE-{index}", candles=candles)
        for index in range(12)
    )
    dataset = SimpleNamespace(records=records)
    monkeypatch.setattr(
        proof,
        "execute_swing_daily_dataset_proof",
        lambda received_provider, *, universe, now, pace: SimpleNamespace(
            dataset=dataset
        ),
    )
    market = SimpleNamespace(observation_boundary=boundary)
    monkeypatch.setattr(proof, "assess_swing_market", lambda received: market)
    candidates = tuple(
        SimpleNamespace(canonical_identity=f"CANDIDATE-{index}")
        for index in range(12)
    )
    validation = SimpleNamespace(
        passed=True,
        candidates=candidates,
        unique_instrument_count=11,
    )
    monkeypatch.setattr(
        proof,
        "validate_qualified_candidates",
        lambda received_market, received_dataset: validation,
    )
    plans = tuple(object() for _ in range(12))
    calls: list[tuple[object, object]] = []

    def build(candidate, received_candles):  # type: ignore[no-untyped-def]
        calls.append((candidate, received_candles))
        return plans[len(calls) - 1]

    monkeypatch.setattr(proof, "build_trade_plan", build)

    evidence = proof.execute_swing_trade_plan_proof(
        provider,
        universe=enabled_swing_phase1_universe(),
        pace=lambda: None,
    )

    assert evidence.plans == plans
    assert len(calls) == 12
    assert all(received == candles for _, received in calls)


def test_stage8_proof_ranks_exact_stage7_plans_without_second_provider_path(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    provider = object()
    plans = tuple(object() for _ in range(12))
    trade_proof = SimpleNamespace(plans=plans)
    expected_ranking = object()
    calls: list[object] = []

    def trade(received_provider, *, universe, frozen_boundary, pace):  # type: ignore[no-untyped-def]
        calls.extend((received_provider, universe, frozen_boundary, pace))
        return trade_proof

    def rank(received_plans):  # type: ignore[no-untyped-def]
        calls.append(received_plans)
        return expected_ranking

    monkeypatch.setattr(proof, "execute_swing_trade_plan_proof", trade)
    monkeypatch.setattr(proof, "rank_trade_plans", rank)
    pace = lambda: None

    evidence = proof.execute_swing_candidate_ranking_proof(
        provider,
        universe=enabled_swing_phase1_universe(),
        pace=pace,
    )

    assert calls[0] is provider
    assert len(calls[1]) == 98  # type: ignore[arg-type]
    assert calls[2] == proof.FROZEN_STAGE4_OBSERVATION_BOUNDARY
    assert calls[3] is pace
    assert calls[4] is plans
    assert evidence.ranking is expected_ranking


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
