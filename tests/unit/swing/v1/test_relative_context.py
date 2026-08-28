from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.swing.universe import (
    SWING_PHASE1_UNIVERSE,
    SwingUniverseAssetClass,
    SwingUniverseMember,
)
from kronos.swing.v1.models import PivotCandidate, PivotKind
from kronos.swing.v1.mtf_facts import (
    CompletedTimeframeFact,
    FactualPivotSeries,
    FactualTimeframe,
    InstrumentMtfFactSnapshot,
    SameRunMtfFactSnapshot,
)
from kronos.swing.v1.relative_context import (
    DirectionalRelativeContext,
    RELATIVE_CONTEXT_AUTHORITY,
    RELATIVE_CONTEXT_BENCHMARK,
    RelativeContextEvidenceStore,
    RelativeContextReason,
    RelativeContextState,
    build_relative_context_record,
    build_relative_context_run,
    directional_relative_context,
)


IST = ZoneInfo("Asia/Kolkata")
RUN_A = "SWING-RUN-" + "A" * 32
RUN_B = "SWING-RUN-" + "B" * 32
OBSERVED = datetime(2026, 8, 28, 15, 30, tzinfo=IST)


def _pivots(radius: int) -> FactualPivotSeries:
    return FactualPivotSeries(
        f"FRACTAL_UNIQUE_EXTREME_RADIUS_{radius}",
        radius,
        (
            PivotCandidate(PivotKind.HIGH, 0, OBSERVED - timedelta(days=2), 101.0),
            PivotCandidate(PivotKind.HIGH, 1, OBSERVED - timedelta(days=1), 102.0),
        ),
        (
            PivotCandidate(PivotKind.LOW, 0, OBSERVED - timedelta(days=2), 99.0),
            PivotCandidate(PivotKind.LOW, 1, OBSERVED - timedelta(days=1), 100.0),
        ),
    )


def _fact(
    timeframe: FactualTimeframe,
    *,
    start: float,
    end: float,
    offset: timedelta | None = None,
) -> CompletedTimeframeFact:
    durations = {
        FactualTimeframe.WEEKLY: timedelta(days=4),
        FactualTimeframe.DAILY: timedelta(hours=6, minutes=15),
        FactualTimeframe.FOUR_HOUR: timedelta(hours=4),
        FactualTimeframe.ONE_HOUR: timedelta(hours=1),
    }
    duration = durations[timeframe]
    boundary = OBSERVED - (offset or timedelta())
    source = boundary - duration
    return CompletedTimeframeFact(
        timeframe=timeframe,
        observation_boundary=boundary,
        source_timestamp=source,
        open=float(start),
        high=float(max(start, end) + 1.0),
        low=float(min(start, end) - 1.0),
        close=float(end),
        volume=1_000,
        calendar_identity="KRONOS-MARKET-CALENDAR-V1-NSE-CAPITAL-MARKET",
        calendar_version="2026.1.2",
        session_identity=(
            "NSE-WEEK-2026-08-24"
            if timeframe is FactualTimeframe.WEEKLY
            else "NSE-REGULAR-2026-08-28"
        ),
        exchange_timezone="Asia/Kolkata",
        source_interval=(
            "DAY"
            if timeframe in {FactualTimeframe.WEEKLY, FactualTimeframe.DAILY}
            else "60minute"
        ),
        source_provider_identity="KITE_NORMALIZED_HISTORICAL",
        source_market_data_boundary=boundary,
        provenance=("provider=KITE", "completed=true"),
        structural_measurements=(_pivots(1), _pivots(2)),
        bucket_class=(
            "FULL_DURATION"
            if timeframe is FactualTimeframe.FOUR_HOUR else None
        ),
    )


def _instrument(
    symbol: str,
    start: float,
    end: float,
    *,
    mismatch: FactualTimeframe | None = None,
) -> InstrumentMtfFactSnapshot:
    return InstrumentMtfFactSnapshot(
        symbol,
        "MCX" if symbol == "GOLDM" else "NSE",
        tuple(
            _fact(
                timeframe,
                start=start,
                end=end,
                offset=(timedelta(hours=1) if timeframe is mismatch else None),
            )
            for timeframe in FactualTimeframe
        ),
    )


def _member(symbol: str) -> SwingUniverseMember:
    return next(item for item in SWING_PHASE1_UNIVERSE if item.canonical_identity == symbol)


def _record(
    *,
    symbol: str = "RELIANCE",
    stock_start: float = 100.0,
    stock_end: float = 103.0,
    nifty_start: float = 100.0,
    nifty_end: float = 101.0,
    benchmark_run: str = RUN_A,
    mismatch: FactualTimeframe | None = None,
):  # type: ignore[no-untyped-def]
    return build_relative_context_record(
        run_identity=RUN_A,
        created_at=OBSERVED,
        member=_member(symbol),
        instrument=_instrument(symbol, stock_start, stock_end, mismatch=mismatch),
        benchmark_run_identity=benchmark_run,
        benchmark=_instrument("NIFTY", nifty_start, nifty_end),
    )


@pytest.mark.parametrize("timeframe", tuple(FactualTimeframe))
def test_matched_completed_horizons_use_exact_return_math(timeframe) -> None:  # type: ignore[no-untyped-def]
    fact = _record().horizon(timeframe)
    assert fact.stock_return_pct == pytest.approx(3.0)
    assert fact.benchmark_return_pct == pytest.approx(1.0)
    assert fact.relative_return_pct == pytest.approx(2.0)
    assert fact.relative_state is RelativeContextState.OUTPERFORMING
    assert fact.stock_start_boundary == fact.benchmark_start_boundary
    assert fact.stock_end_boundary == fact.benchmark_end_boundary


@pytest.mark.parametrize(
    ("stock", "benchmark", "state", "long_context", "short_context"),
    (
        (103.0, 101.0, RelativeContextState.OUTPERFORMING,
         DirectionalRelativeContext.SUPPORTIVE_CONTEXT,
         DirectionalRelativeContext.CONTRADICTORY_CONTEXT),
        (100.5, 101.5, RelativeContextState.UNDERPERFORMING,
         DirectionalRelativeContext.CONTRADICTORY_CONTEXT,
         DirectionalRelativeContext.SUPPORTIVE_CONTEXT),
        (101.0, 101.0, RelativeContextState.EQUAL,
         DirectionalRelativeContext.NEUTRAL_CONTEXT,
         DirectionalRelativeContext.NEUTRAL_CONTEXT),
    ),
)
def test_directional_context_is_non_veto_supporting_interpretation(
    stock, benchmark, state, long_context, short_context
) -> None:  # type: ignore[no-untyped-def]
    fact = _record(stock_end=stock, nifty_end=benchmark).horizon(
        FactualTimeframe.DAILY
    )
    assert fact.relative_state is state
    assert directional_relative_context(state, "LONG") is long_context
    assert directional_relative_context(state, "SHORT") is short_context
    assert "NO_DISCOVERY_READINESS_TRADE_OR_EXECUTION_AUTHORITY" in RELATIVE_CONTEXT_AUTHORITY


def test_benchmark_unavailable_run_mismatch_and_boundary_mismatch_fail_closed() -> None:
    missing = build_relative_context_record(
        run_identity=RUN_A,
        created_at=OBSERVED,
        member=_member("RELIANCE"),
        instrument=_instrument("RELIANCE", 100.0, 103.0),
        benchmark_run_identity=RUN_A,
        benchmark=None,
    )
    assert all(item.relative_state is RelativeContextState.UNAVAILABLE for item in missing.horizons)
    assert missing.horizons[0].reason_codes == (
        RelativeContextReason.BENCHMARK_FACT_UNAVAILABLE,
    )

    stale = _record(benchmark_run=RUN_B)
    assert all(item.reason_codes == (RelativeContextReason.RUN_MISMATCH,) for item in stale.horizons)

    boundary = _record(mismatch=FactualTimeframe.ONE_HOUR)
    assert boundary.horizon(FactualTimeframe.ONE_HOUR).relative_state is RelativeContextState.UNAVAILABLE
    assert boundary.horizon(FactualTimeframe.ONE_HOUR).reason_codes == (
        RelativeContextReason.BOUNDARY_MISMATCH,
    )
    assert boundary.horizon(FactualTimeframe.DAILY).relative_state is RelativeContextState.OUTPERFORMING


@pytest.mark.parametrize(
    ("symbol", "reason"),
    (
        ("NIFTY", RelativeContextReason.BENCHMARK_SELF_COMPARISON_NOT_APPLICABLE),
        ("BANK NIFTY", RelativeContextReason.NOT_APPLICABLE_ASSET_CLASS),
        ("GOLDM", RelativeContextReason.NOT_APPLICABLE_ASSET_CLASS),
        ("SILVERM", RelativeContextReason.NOT_APPLICABLE_ASSET_CLASS),
        ("COPPER", RelativeContextReason.NOT_APPLICABLE_ASSET_CLASS),
        ("CRUDEOIL", RelativeContextReason.NOT_APPLICABLE_ASSET_CLASS),
        ("NATURALGAS", RelativeContextReason.NOT_APPLICABLE_ASSET_CLASS),
    ),
)
def test_indices_and_mcx_are_not_applicable(symbol, reason) -> None:  # type: ignore[no-untyped-def]
    record = _record(symbol=symbol)
    assert all(item.relative_state is RelativeContextState.NOT_APPLICABLE for item in record.horizons)
    assert all(item.reason_codes == (reason,) for item in record.horizons)


def test_run_is_same_98_and_persistence_is_immutable_restart_safe_and_corrupt_closed(
    tmp_path: Path,
) -> None:
    instruments = tuple(
        _instrument(item.canonical_identity, 100.0, 101.0)
        for item in SWING_PHASE1_UNIVERSE
    )
    snapshot = SameRunMtfFactSnapshot(
        RUN_A,
        OBSERVED,
        "KITE-MTF-FACTS-" + "a" * 64,
        instruments,
    )
    run = build_relative_context_run(snapshot)
    assert len(run.records) == 98
    assert run.record("RELIANCE").benchmark_identity == RELATIVE_CONTEXT_BENCHMARK
    store = RelativeContextEvidenceStore(tmp_path)
    path = store.retain(run)
    assert store.retain(run) == path
    assert store.load(RUN_A) == run
    assert path.stat().st_mode & 0o777 == 0o600

    with pytest.raises(ValueError, match="RELATIVE_CONTEXT_RECORD_INVALID"):
        # Historical integrity prevents cross-run relabelling/reuse.
        replace(run.records[0], run_identity=RUN_B)

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["run"]["records"][0]["horizons"][0]["relative_return_pct"] = 999.0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="RELATIVE_CONTEXT_RUN_INVALID"):
        store.load(RUN_A)


def test_new_run_uses_only_its_own_stock_and_benchmark_facts(tmp_path: Path) -> None:
    def snapshot(run_identity: str, stock_end: float, nifty_end: float):  # type: ignore[no-untyped-def]
        instruments = tuple(
            _instrument(
                item.canonical_identity,
                100.0,
                nifty_end if item.canonical_identity == "NIFTY" else stock_end,
            )
            for item in SWING_PHASE1_UNIVERSE
        )
        return SameRunMtfFactSnapshot(
            run_identity,
            OBSERVED + (timedelta(minutes=1) if run_identity == RUN_B else timedelta()),
            "KITE-MTF-FACTS-" + ("b" if run_identity == RUN_B else "a") * 64,
            instruments,
        )

    first = build_relative_context_run(snapshot(RUN_A, 103.0, 101.0))
    second = build_relative_context_run(snapshot(RUN_B, 99.0, 102.0))
    store = RelativeContextEvidenceStore(tmp_path)
    store.retain(first)
    store.retain(second)

    assert store.load(RUN_A) == first
    assert store.load(RUN_B) == second
    assert first.record("RELIANCE").horizons[0].relative_return_pct == pytest.approx(2.0)
    assert second.record("RELIANCE").horizons[0].relative_return_pct == pytest.approx(-3.0)
    with pytest.raises(ValueError, match="RELATIVE_CONTEXT_EVIDENCE_INVALID"):
        store.load("SWING-RUN-" + "C" * 32)


def test_contract_rejects_wrong_benchmark_identity_and_non_equity_applicability() -> None:
    wrong = _instrument("BANK NIFTY", 100.0, 101.0)
    record = build_relative_context_record(
        run_identity=RUN_A,
        created_at=OBSERVED,
        member=_member("RELIANCE"),
        instrument=_instrument("RELIANCE", 100.0, 101.0),
        benchmark_run_identity=RUN_A,
        benchmark=wrong,
    )
    assert all(
        item.reason_codes == (RelativeContextReason.BENCHMARK_IDENTITY_INVALID,)
        for item in record.horizons
    )


def test_contract_contains_no_decision_or_trade_fields() -> None:
    record = _record()
    names = set(record.__dataclass_fields__)
    assert {
        "setup", "candidate", "readiness", "promotion", "entry", "stop",
        "target", "risk", "order", "position", "score",
    }.isdisjoint(names)
    assert record.product is SwingUniverseAssetClass.NSE_EQUITY
