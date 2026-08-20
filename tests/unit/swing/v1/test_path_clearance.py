from dataclasses import replace
from datetime import datetime, timedelta
import inspect
from zoneinfo import ZoneInfo

import pytest

from kronos.application.swing_mtf_facts import _one_hour_atr_fact
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.v1.models import PivotCandidate, PivotKind, V1Direction
from kronos.swing.v1.mtf_facts import (
    CompletedTimeframeFact,
    FactualMovingAverageFacts,
    FactualPivotSeries,
    FactualTimeframe,
    FactualVolumeFacts,
    InstrumentMtfFactSnapshot,
    OneHourAtrAvailability,
)
from kronos.swing.v1 import path_clearance
from kronos.swing.v1.path_clearance import (
    PATH_CLEARANCE_AUTHORITY,
    PATH_CLEARANCE_NEAR_ATR_MULTIPLE,
    PathClearanceAvailability,
    PathObstacleSource,
    evaluate_one_hour_path_clearance,
)


IST = ZoneInfo("Asia/Kolkata")
RUN_ID = "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"
BOUNDARY = datetime(2026, 8, 20, 15, 30, tzinfo=IST)


def _pivot(kind: PivotKind, index: int, value: float) -> PivotCandidate:
    return PivotCandidate(
        kind, index, BOUNDARY - timedelta(hours=10 - index), value
    )


def _fact(
    timeframe: FactualTimeframe,
    *,
    close: float = 100.0,
    sma200: float | None = 104.0,
    highs: tuple[float, ...] = (103.0, 105.0, 104.5, 106.0),
    lows: tuple[float, ...] = (97.0, 95.0, 95.5, 94.0),
) -> CompletedTimeframeFact:
    structural = tuple(
        FactualPivotSeries(
            f"FRACTAL_UNIQUE_EXTREME_RADIUS_{radius}",
            radius,
            tuple(
                _pivot(PivotKind.HIGH, index, value)
                for index, value in enumerate(
                    highs[:2] if radius == 1 else highs[2:]
                )
            ),
            tuple(
                _pivot(PivotKind.LOW, index, value)
                for index, value in enumerate(
                    lows[:2] if radius == 1 else lows[2:]
                )
            ),
        )
        for radius in (1, 2)
    )
    return CompletedTimeframeFact(
        timeframe=timeframe,
        observation_boundary=BOUNDARY,
        source_timestamp=BOUNDARY - timedelta(hours=1),
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1000,
        calendar_identity="NSE-CALENDAR",
        calendar_version="1",
        session_identity="NSE-2026-08-20",
        exchange_timezone="Asia/Kolkata",
        source_interval="60minute" if timeframe in {
            FactualTimeframe.FOUR_HOUR, FactualTimeframe.ONE_HOUR
        } else "DAY",
        source_provider_identity="KITE_NORMALIZED_HISTORICAL",
        source_market_data_boundary=BOUNDARY - timedelta(hours=1),
        provenance=("DOMAIN-008",),
        structural_measurements=structural,
        moving_averages=FactualMovingAverageFacts(
            220, close, close, sma200, close, close, sma200
        ),
        volume_facts=FactualVolumeFacts(1000, 900.0),
        bucket_class=(
            "FULL_DURATION"
            if timeframe is FactualTimeframe.FOUR_HOUR else None
        ),
    )


def _candles(count: int = 15, true_range: float = 10.0) -> tuple[HistoricalCandle, ...]:
    result = []
    for index in range(count):
        close = 100.0
        result.append(HistoricalCandle(
            BOUNDARY - timedelta(hours=count - index),
            close,
            close + true_range / 2.0,
            close - true_range / 2.0,
            close,
            1000,
        ))
    return tuple(result)


def _instrument(
    *,
    sma200: float | None = 104.0,
    highs: tuple[float, ...] = (103.0, 105.0, 104.5, 106.0),
    lows: tuple[float, ...] = (97.0, 95.0, 95.5, 94.0),
    candle_count: int = 15,
) -> InstrumentMtfFactSnapshot:
    facts = tuple(
        _fact(
            timeframe, sma200=sma200, highs=highs, lows=lows
        )
        for timeframe in FactualTimeframe
    )
    atr = _one_hour_atr_fact(
        run_identity=RUN_ID,
        canonical_instrument="RELIANCE",
        analysis_boundary=BOUNDARY,
        one_hour_fact=facts[-1],
        completed_hourly=_candles(candle_count),
    )
    return InstrumentMtfFactSnapshot(
        "RELIANCE", "NSE", facts, None, (), atr
    )


def test_atr_fact_is_exact_bound_integrity_protected_and_fails_closed() -> None:
    available = _instrument().one_hour_atr
    unavailable = _instrument(candle_count=14).one_hour_atr
    assert available is not None and available.value == 10.0
    assert available.run_identity == RUN_ID
    assert available.canonical_instrument == "RELIANCE"
    assert available.observation_boundary == BOUNDARY
    assert available.availability is OneHourAtrAvailability.AVAILABLE
    assert unavailable is not None
    assert unavailable.availability is OneHourAtrAvailability.UNAVAILABLE
    assert unavailable.unavailable_reason == "INSUFFICIENT_COMPLETED_1H_HISTORY"
    assert unavailable.value is None
    with pytest.raises(ValueError, match="COMPLETED_ONE_HOUR_ATR_FACT_INVALID"):
        replace(available, value=11.0)


def test_long_uses_only_overhead_and_aggregates_highest_nearby_clearance() -> None:
    result = evaluate_one_hour_path_clearance(
        run_identity=RUN_ID, instrument=_instrument(), direction=V1Direction.LONG
    )

    assert result.availability is PathClearanceAvailability.AVAILABLE
    assert result.path_clear is False
    assert result.clearance_level == 105.0
    assert tuple(item.level for item in result.blocking_obstacles) == (
        104.0, 103.0, 105.0, 104.5
    )
    assert all(item.level > result.completed_price for item in result.blocking_obstacles)
    assert max(item.distance_atr14 for item in result.blocking_obstacles) == 0.5
    assert all(item.level != 106.0 for item in result.blocking_obstacles)


def test_short_uses_only_support_below_and_aggregates_lowest_nearby_clearance() -> None:
    result = evaluate_one_hour_path_clearance(
        run_identity=RUN_ID, instrument=_instrument(sma200=96.0),
        direction=V1Direction.SHORT,
    )

    assert result.availability is PathClearanceAvailability.AVAILABLE
    assert result.path_clear is False
    assert result.clearance_level == 95.0
    assert tuple(item.level for item in result.blocking_obstacles) == (
        96.0, 97.0, 95.0, 95.5
    )
    assert all(item.level < result.completed_price for item in result.blocking_obstacles)
    assert max(item.distance_atr14 for item in result.blocking_obstacles) == 0.5
    assert all(item.level != 94.0 for item in result.blocking_obstacles)


def test_exact_half_atr_is_near_and_just_beyond_is_clear() -> None:
    exact = evaluate_one_hour_path_clearance(
        run_identity=RUN_ID,
        instrument=_instrument(sma200=None, highs=(105.0,), lows=(95.0,)),
        direction=V1Direction.LONG,
    )
    beyond = evaluate_one_hour_path_clearance(
        run_identity=RUN_ID,
        instrument=_instrument(sma200=None, highs=(105.000001,), lows=(94.999999,)),
        direction=V1Direction.LONG,
    )

    assert exact.path_clear is False and exact.clearance_level == 105.0
    assert exact.blocking_obstacles[0].distance_atr14 == PATH_CLEARANCE_NEAR_ATR_MULTIPLE
    assert beyond.path_clear is True and beyond.clearance_level is None


def test_optional_sma_absence_uses_pivots_but_no_sources_fail_closed() -> None:
    pivots = evaluate_one_hour_path_clearance(
        run_identity=RUN_ID,
        instrument=_instrument(sma200=None, highs=(103.0,), lows=(97.0,)),
        direction=V1Direction.LONG,
    )
    unavailable = evaluate_one_hour_path_clearance(
        run_identity=RUN_ID,
        instrument=_instrument(sma200=None, highs=(), lows=()),
        direction=V1Direction.LONG,
    )

    assert pivots.path_clear is False
    assert PathObstacleSource.ONE_HOUR_SMA200 not in pivots.available_sources
    assert unavailable.availability is PathClearanceAvailability.UNAVAILABLE
    assert unavailable.unavailable_reason == "NO_AUTHORITATIVE_1H_OBSTACLE_SOURCE"


def test_unavailable_atr_fails_closed_and_binding_or_tampering_is_rejected() -> None:
    unavailable = evaluate_one_hour_path_clearance(
        run_identity=RUN_ID, instrument=_instrument(candle_count=14),
        direction=V1Direction.LONG,
    )
    assert unavailable.availability is PathClearanceAvailability.UNAVAILABLE
    assert unavailable.path_clear is None
    with pytest.raises(ValueError, match="PATH_CLEARANCE_RUN_BINDING_INVALID"):
        evaluate_one_hour_path_clearance(
            run_identity="SWING-RUN-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            instrument=_instrument(), direction=V1Direction.LONG,
        )
    valid = evaluate_one_hour_path_clearance(
        run_identity=RUN_ID, instrument=_instrument(), direction=V1Direction.LONG
    )
    with pytest.raises(ValueError, match="ONE_HOUR_PATH_CLEARANCE_FACT_INVALID"):
        replace(valid, clearance_level=104.0)


def test_e01_has_no_intraday_pdh_rs_watch_or_sponsor_state_authority() -> None:
    source = inspect.getsource(path_clearance)
    forbidden = (
        "kronos.application.intraday", "intraday_reliance_bootstrap",
        "progression_watch", "BUY_NOW", "SELL_NOW", "BUY_READY", "SELL_READY",
    )
    assert all(item not in source for item in forbidden)
    assert set(PathObstacleSource) == {
        PathObstacleSource.ONE_HOUR_SMA200,
        PathObstacleSource.ONE_HOUR_STRUCTURAL_PIVOT_RADIUS_1,
        PathObstacleSource.ONE_HOUR_STRUCTURAL_PIVOT_RADIUS_2,
    }
    assert PATH_CLEARANCE_AUTHORITY == (
        "MACHINE_EVIDENCE_ONLY_NO_PROMOTION_WATCH_OR_EXECUTION_AUTHORITY"
    )
