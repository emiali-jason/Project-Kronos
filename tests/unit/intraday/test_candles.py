from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.candles import (
    ReconciliationFailure,
    ReconciliationResult,
    expected_candle_boundaries,
    provider_interval,
    reconcile_provider_candles,
)
from kronos.intraday.contracts import (
    CandleCompletion,
    DataAvailability,
    IntradayInstrumentReference,
    IntradayTimeframe,
    SourceProvenance,
)
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.provider.contracts.market_data import HistoricalCandle, HistoricalInterval


IST = ZoneInfo("Asia/Kolkata")


def _candle(at: datetime, close: float = 101.0) -> HistoricalCandle:
    return HistoricalCandle(at, 100.0, 102.0, 99.0, close, 1000)


@pytest.mark.parametrize(
    ("timeframe", "expected_interval", "minutes"),
    [
        (IntradayTimeframe.FIVE_MINUTES, HistoricalInterval.FIVE_MINUTE, 5),
        (IntradayTimeframe.FIFTEEN_MINUTES, HistoricalInterval.FIFTEEN_MINUTE, 15),
        (IntradayTimeframe.ONE_HOUR, HistoricalInterval.SIXTY_MINUTE, 60),
    ],
)
def test_completed_and_current_incomplete_intraday_candles(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
    timeframe: IntradayTimeframe,
    expected_interval: HistoricalInterval,
    minutes: int,
) -> None:
    boundaries = expected_candle_boundaries(schedule, timeframe)
    first, current = boundaries[0], boundaries[1]
    observed = current.start + (current.end - current.start) / 2
    result = reconcile_provider_candles(
        instrument=instrument,
        timeframe=timeframe,
        schedule=schedule,
        provider_candles=(_candle(first.start), _candle(current.start)),
        observed_at=observed,
        provenance=provenance,
    )

    assert provider_interval(timeframe) is expected_interval
    assert int((first.end - first.start).total_seconds() / 60) == minutes
    assert result.result is ReconciliationResult.COMPLETE
    assert result.partial_current_boundary == current
    assert [item.completion for item in result.observations] == [
        CandleCompletion.COMPLETE,
        CandleCompletion.INCOMPLETE,
    ]
    assert result.structural_candles == (result.observations[0],)


def test_daily_candle_uses_trading_date_and_session_end_for_completion(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    provider_daily_timestamp = datetime(2026, 8, 17, 0, 0, tzinfo=IST)
    before_close = reconcile_provider_candles(
        instrument=instrument,
        timeframe=IntradayTimeframe.DAILY,
        schedule=schedule,
        provider_candles=(_candle(provider_daily_timestamp),),
        observed_at=datetime(2026, 8, 17, 15, 29, tzinfo=IST),
        provenance=provenance,
    )
    at_close = reconcile_provider_candles(
        instrument=instrument,
        timeframe=IntradayTimeframe.DAILY,
        schedule=schedule,
        provider_candles=(_candle(provider_daily_timestamp),),
        observed_at=datetime(2026, 8, 17, 15, 30, tzinfo=IST),
        provenance=provenance,
    )

    assert before_close.observations[0].completion is CandleCompletion.INCOMPLETE
    assert before_close.structural_candles == ()
    assert at_close.observations[0].completion is CandleCompletion.COMPLETE
    assert at_close.structural_candles == at_close.observations


def test_missing_completed_candle_fails_closed_and_requests_backfill(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    boundaries = expected_candle_boundaries(schedule, IntradayTimeframe.FIVE_MINUTES)
    result = reconcile_provider_candles(
        instrument=instrument,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        schedule=schedule,
        provider_candles=(_candle(boundaries[0].start), _candle(boundaries[2].start)),
        observed_at=boundaries[2].end,
        provenance=provenance,
    )

    assert result.result is ReconciliationResult.DATA_INCOMPLETE
    assert result.availability is DataAvailability.INCOMPLETE
    assert result.missing_boundaries == (boundaries[1],)
    assert result.backfill_required is True
    assert result.structural_candles == ()


def test_duplicate_and_out_of_order_data_are_factual_failures(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    boundaries = expected_candle_boundaries(schedule, IntradayTimeframe.FIFTEEN_MINUTES)
    result = reconcile_provider_candles(
        instrument=instrument,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        schedule=schedule,
        provider_candles=(
            _candle(boundaries[1].start),
            _candle(boundaries[0].start),
            _candle(boundaries[0].start),
        ),
        observed_at=boundaries[1].end,
        provenance=provenance,
    )

    assert result.out_of_order is True
    assert result.duplicate_boundaries == (boundaries[0],)
    assert ReconciliationFailure.DUPLICATE_CANDLE in result.failures
    assert ReconciliationFailure.OUT_OF_ORDER_PROVIDER_DATA in result.failures
    assert result.structural_candles == ()


def test_malformed_and_unexpected_provider_candles_fail_closed(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    malformed = reconcile_provider_candles(
        instrument=instrument,
        timeframe=IntradayTimeframe.ONE_HOUR,
        schedule=schedule,
        provider_candles=(object(),),  # type: ignore[arg-type]
        observed_at=datetime(2026, 8, 17, 11, 15, tzinfo=IST),
        provenance=provenance,
    )
    unexpected = reconcile_provider_candles(
        instrument=instrument,
        timeframe=IntradayTimeframe.ONE_HOUR,
        schedule=schedule,
        provider_candles=(_candle(datetime(2026, 8, 17, 9, 16, tzinfo=IST)),),
        observed_at=datetime(2026, 8, 17, 10, 15, tzinfo=IST),
        provenance=provenance,
    )

    assert malformed.result is ReconciliationResult.UNAVAILABLE
    assert malformed.failures == (ReconciliationFailure.MALFORMED_PROVIDER_CANDLE,)
    assert unexpected.result is ReconciliationResult.DATA_INCOMPLETE
    assert ReconciliationFailure.UNEXPECTED_CANDLE_BOUNDARY in unexpected.failures


def test_multi_window_boundaries_do_not_create_candles_across_breaks(
    schedule: MarketDaySchedule,
) -> None:
    split = MarketDaySchedule(
        exchange=schedule.exchange,
        trading_date=schedule.trading_date,
        session_id="NSE-20260817-SPLIT",
        timezone=schedule.timezone,
        status=TradingDayStatus.TRADING,
        windows=(
            MarketWindow(
                datetime(2026, 8, 17, 9, 0, tzinfo=IST),
                datetime(2026, 8, 17, 10, 0, tzinfo=IST),
            ),
            MarketWindow(
                datetime(2026, 8, 17, 11, 0, tzinfo=IST),
                datetime(2026, 8, 17, 12, 0, tzinfo=IST),
            ),
        ),
        source_identity=schedule.source_identity,
        source_version=schedule.source_version,
    )
    boundaries = expected_candle_boundaries(split, IntradayTimeframe.ONE_HOUR)

    assert tuple((item.start.hour, item.end.hour) for item in boundaries) == ((9, 10), (11, 12))


def test_non_trading_day_produces_no_assumed_candles(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    closed = MarketDaySchedule(
        exchange=schedule.exchange,
        trading_date=schedule.trading_date,
        session_id="NSE-20260817-CLOSED",
        timezone=schedule.timezone,
        status=TradingDayStatus.NON_TRADING,
        windows=(),
        source_identity=schedule.source_identity,
        source_version=schedule.source_version,
    )
    result = reconcile_provider_candles(
        instrument=instrument,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        schedule=closed,
        provider_candles=(),
        observed_at=datetime(2026, 8, 17, 10, 0, tzinfo=IST),
        provenance=provenance,
    )
    assert result.result is ReconciliationResult.UNAVAILABLE
    assert result.expected_boundaries == ()
    assert result.failures == (ReconciliationFailure.NON_TRADING_DAY,)
