"""WO-SWING-RS-ENG-03: common completed boundaries, never latest vs latest."""

from dataclasses import asdict, replace
from datetime import timedelta
import json

import pytest

from kronos.swing.v1.mtf_facts import (
    CompletedTimeframeBar,
    FactualTimeframe,
    MtfFactEvidenceStore,
    SameRunMtfFactSnapshot,
)
from kronos.swing.v1.relative_context import (
    RELATIVE_CONTEXT_AUTHORITY,
    RelativeContextReason,
    RelativeContextState,
    build_relative_context_record,
    build_relative_context_run,
)
from tests.unit.swing.v1.test_relative_context import (
    OBSERVED, RUN_A, SWING_PHASE1_UNIVERSE, _fact, _instrument, _member,
)


def _series_instrument(symbol, timeframe, *, later=False):
    source = _instrument(symbol, 100.0, 103.0 if symbol != "NIFTY" else 101.0)
    fact = source.fact(timeframe)
    # Reproduce the diagnosed intraday boundaries exactly, without a clock
    # fallback or tolerance in production selection.
    if timeframe is FactualTimeframe.ONE_HOUR:
        fact = replace(fact, source_timestamp=OBSERVED.replace(hour=14, minute=15),
                       observation_boundary=OBSERVED.replace(hour=15, minute=15))
    elif timeframe is FactualTimeframe.FOUR_HOUR:
        fact = replace(fact, source_timestamp=OBSERVED.replace(hour=9, minute=15),
                       observation_boundary=OBSERVED.replace(hour=13, minute=15))
    earlier = replace(fact, source_timestamp=fact.source_timestamp - timedelta(days=7),
                      observation_boundary=fact.observation_boundary - timedelta(days=7))
    selected = fact
    history = (CompletedTimeframeBar.from_fact(earlier), CompletedTimeframeBar.from_fact(fact))
    if later:
        selected = replace(
            fact, source_timestamp=fact.observation_boundary,
            observation_boundary=OBSERVED,
            open=100.0, high=151.0, close=150.0,
            bucket_class="SESSION_REMAINDER" if timeframe is FactualTimeframe.FOUR_HOUR else None,
        )
        history += (CompletedTimeframeBar.from_fact(selected),)
    latest = tuple(selected if item.timeframe is timeframe else item for item in source.timeframes)
    retained = tuple(
        bar for item in latest
        for bar in (history if item.timeframe is timeframe else (CompletedTimeframeBar.from_fact(item),))
    )
    return replace(source, timeframes=latest, completed_series=retained), fact


def _compare(stock, benchmark, *, observed_at=OBSERVED):
    return build_relative_context_record(
        run_identity=RUN_A, created_at=observed_at, member=_member(stock.canonical_instrument),
        instrument=stock, benchmark_run_identity=RUN_A, benchmark=benchmark,
    )


@pytest.mark.parametrize("timeframe", tuple(FactualTimeframe))
def test_latest_exact_common_bar_and_unchanged_return_math(timeframe):
    stock, selected_stock = _series_instrument("RELIANCE", timeframe)
    benchmark, selected_benchmark = _series_instrument(
        "NIFTY", timeframe, later=timeframe in (FactualTimeframe.ONE_HOUR, FactualTimeframe.FOUR_HOUR)
    )
    before = asdict(stock), asdict(benchmark)
    result = _compare(stock, benchmark)
    horizon = result.horizon(timeframe)
    assert horizon.stock_start_boundary == horizon.benchmark_start_boundary == selected_stock.source_timestamp
    assert horizon.stock_end_boundary == horizon.benchmark_end_boundary == selected_stock.observation_boundary
    assert horizon.stock_start_price == selected_stock.open
    assert horizon.stock_end_price == selected_stock.close
    assert horizon.benchmark_start_price == selected_benchmark.open
    assert horizon.benchmark_end_price == selected_benchmark.close
    assert horizon.stock_return_pct == ((103.0 / 100.0) - 1.0) * 100.0
    assert horizon.benchmark_return_pct == ((101.0 / 100.0) - 1.0) * 100.0
    assert horizon.relative_return_pct == horizon.stock_return_pct - horizon.benchmark_return_pct
    assert horizon.relative_state is RelativeContextState.OUTPERFORMING
    assert horizon.stock_provenance == selected_stock.provenance
    assert horizon.benchmark_provenance == selected_benchmark.provenance
    assert _compare(stock, benchmark) == result
    assert (asdict(stock), asdict(benchmark)) == before
    assert result.authority == RELATIVE_CONTEXT_AUTHORITY


@pytest.mark.parametrize("field,value", (
    ("source_timestamp", OBSERVED - timedelta(minutes=40)),
    ("observation_boundary", OBSERVED + timedelta(minutes=1)),
    ("calendar_identity", "OTHER-CALENDAR"),
    ("calendar_version", "2026.999"),
    ("session_identity", "OTHER-SESSION"),
    ("source_interval", "DAY"),
))
def test_no_exact_identity_intersection_remains_unavailable(field, value):
    stock = _instrument("RELIANCE", 100.0, 103.0)
    benchmark = _instrument("NIFTY", 100.0, 101.0)
    benchmark = replace(benchmark, timeframes=tuple(
        replace(item, **{field: value}) if item.timeframe is FactualTimeframe.ONE_HOUR else item
        for item in benchmark.timeframes
    ))
    result = _compare(stock, benchmark).horizon(FactualTimeframe.ONE_HOUR)
    assert result.relative_state is RelativeContextState.UNAVAILABLE
    assert result.reason_codes == (RelativeContextReason.BOUNDARY_MISMATCH,)
    assert result.stock_return_pct is result.benchmark_return_pct is None


def test_incomplete_common_looking_candle_is_not_accepted():
    # Legacy latest-fact inputs must also be bounded by this run's observation.
    stock = _instrument("RELIANCE", 100.0, 103.0)
    benchmark = _instrument("NIFTY", 100.0, 101.0)
    result = _compare(stock, benchmark, observed_at=OBSERVED - timedelta(minutes=1))
    assert all(item.relative_state is RelativeContextState.UNAVAILABLE for item in result.horizons)


def test_unfinished_later_candle_cannot_displace_completed_common_bar():
    timeframe = FactualTimeframe.ONE_HOUR
    stock, _ = _series_instrument("RELIANCE", timeframe)
    benchmark, _ = _series_instrument("NIFTY", timeframe, later=True)
    result = _compare(stock, benchmark, observed_at=OBSERVED - timedelta(minutes=10))
    assert result.horizon(timeframe).stock_end_boundary == OBSERVED.replace(hour=15, minute=15)
    assert result.horizon(timeframe).benchmark_end_price == 101.0


def _snapshot():
    return SameRunMtfFactSnapshot(
        RUN_A, OBSERVED, "KITE-MTF-FACTS-" + "a" * 64,
        tuple(_series_instrument(member.canonical_identity, FactualTimeframe.ONE_HOUR,
                                 later=member.canonical_identity == "NIFTY")[0]
              for member in SWING_PHASE1_UNIVERSE),
    )


def test_series_restart_reproducible_no_provider_and_immutable(tmp_path, monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("RS must not retrieve Provider data")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    snapshot = _snapshot()
    before = asdict(snapshot)
    expected = build_relative_context_run(snapshot)
    store = MtfFactEvidenceStore(tmp_path)
    path = store.retain(snapshot)
    original = path.read_bytes()
    restored = MtfFactEvidenceStore(tmp_path).load(RUN_A)
    assert restored == snapshot
    assert build_relative_context_run(restored) == expected
    assert store.retain(restored) == path
    assert path.read_bytes() == original
    assert asdict(snapshot) == before
    assert len(expected.records) == 98


def test_old_snapshot_preserved_without_fabricating_history(tmp_path):
    snapshot = _snapshot()
    legacy = replace(snapshot, instruments=tuple(
        replace(item, completed_series=()) for item in snapshot.instruments
    ))
    store = MtfFactEvidenceStore(tmp_path)
    path = store.retain(legacy)
    before = path.read_bytes()
    assert "completed_series" not in json.loads(before)["snapshot"]["instruments"][0]
    restored = store.load(RUN_A)
    store.retain(restored)
    assert path.read_bytes() == before
    horizon = build_relative_context_run(restored).record("RELIANCE").horizon(FactualTimeframe.ONE_HOUR)
    assert horizon.reason_codes == (RelativeContextReason.BOUNDARY_MISMATCH,)


@pytest.mark.parametrize("mode", ("duplicate", "reverse", "missing_timeframe", "latest_mismatch"))
def test_malformed_series_rejected(mode):
    instrument, _ = _series_instrument("RELIANCE", FactualTimeframe.ONE_HOUR)
    series = instrument.completed_series
    if mode == "duplicate":
        series += (series[-1],)
    elif mode == "reverse":
        series = tuple(reversed(series))
    elif mode == "missing_timeframe":
        series = tuple(bar for bar in series if bar.timeframe is not FactualTimeframe.ONE_HOUR)
    else:
        series = (*series[:-1], replace(series[-1], close=102.5))
    with pytest.raises(ValueError, match="MTF_FACT_COMPLETED_SERIES_INVALID"):
        replace(instrument, completed_series=series)


def test_snapshot_cannot_admit_unfinished_retained_bars():
    with pytest.raises(ValueError, match="SAME_RUN_MTF_FACT_SNAPSHOT_INVALID"):
        replace(_snapshot(), observed_at=OBSERVED - timedelta(minutes=1))
