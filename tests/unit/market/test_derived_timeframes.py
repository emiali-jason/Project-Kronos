from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from kronos.market.derived_timeframes import (
    DERIVED_TIMEFRAME_AGGREGATION_POLICY_ID,
    DerivedBarStatus,
    DerivedBucketClass,
    GovernedTradingWeek,
    derive_session_four_hour_bars,
    derive_weekly_bar,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.schedule import (
    AuthoritativeMarketScheduleFacts,
    MarketAvailability,
    NseMarketScheduleAdapter,
    ScheduleFreshness,
    ScheduleIntegrity,
)
from kronos.provider.contracts.market_data import HistoricalCandle


IST = ZoneInfo("Asia/Kolkata")


def _schedule(day: date, opening: time, closing: time, *, session: str | None = None):
    start = datetime.combine(day, opening, IST)
    end = datetime.combine(day, closing, IST)
    return NseMarketScheduleAdapter().normalize(AuthoritativeMarketScheduleFacts(
        market_identity="NSE",
        exchange="NSE",
        trading_date=day,
        calendar_identity="DOMAIN-008-NSE",
        calendar_version="1",
        session_identity=session or f"NSE-{day.isoformat()}",
        session_type="REGULAR",
        session_open=start,
        session_close=end,
        timezone="Asia/Kolkata",
        market_availability=MarketAvailability.CLOSED,
        as_of=end,
        source_identity="DOMAIN-008",
        source_boundary=end,
        freshness_status=ScheduleFreshness.CURRENT,
        integrity_status=ScheduleIntegrity.VALID,
        provenance=("DOMAIN-008",),
    ))


def _candle(timestamp: datetime, price: float, *, volume: int = 10) -> HistoricalCandle:
    return HistoricalCandle(timestamp, price, price + 2.0, price - 1.0, price + 1.0, volume)


def test_completed_holiday_shortened_week_aggregates_four_expected_sessions() -> None:
    days = (date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 13), date(2026, 8, 14))
    schedules = tuple(_schedule(day, time(9, 15), time(15, 30)) for day in days)
    week = GovernedTradingWeek("NSE-WEEK-2026-08-10", schedules)
    candles = tuple(_candle(datetime.combine(day, time(0), IST), 100.0 + index) for index, day in enumerate(days))

    bar = derive_weekly_bar(
        canonical_instrument="RELIANCE",
        trading_week=week,
        daily_candles=candles,
        source_provider_identity="KITE",
        source_market_data_boundary=schedules[-1].session_close,
        observed_at=schedules[-1].session_close,
    )

    assert bar is not None
    assert bar.status is DerivedBarStatus.COMPLETE
    assert bar.open == 100.0
    assert bar.high == 105.0
    assert bar.low == 99.0
    assert bar.close == 104.0
    assert bar.volume == 40
    assert bar.aggregation_policy_identity == DERIVED_TIMEFRAME_AGGREGATION_POLICY_ID
    assert bar.analytical_authority == "NONE"
    assert bar.tradingview_equivalence_claimed is False
    assert len(bar.constituent_identities) == 4


def test_current_incomplete_week_is_excluded() -> None:
    schedules = tuple(
        _schedule(date(2026, 8, 10) + timedelta(days=index), time(9, 15), time(15, 30))
        for index in range(5)
    )
    assert derive_weekly_bar(
        canonical_instrument="RELIANCE",
        trading_week=GovernedTradingWeek("WEEK", schedules),
        daily_candles=(),
        source_provider_identity="KITE",
        source_market_data_boundary=schedules[2].session_close,
        observed_at=schedules[2].session_close,
    ) is None


def test_missing_expected_daily_constituent_fails_closed() -> None:
    schedules = tuple(
        _schedule(date(2026, 8, 10) + timedelta(days=index), time(9, 15), time(15, 30))
        for index in range(5)
    )
    candles = tuple(
        _candle(datetime.combine(item.trading_date, time(0), IST), 100.0)
        for item in schedules[:-1]
    )
    result = derive_weekly_bar(
        canonical_instrument="RELIANCE",
        trading_week=GovernedTradingWeek("WEEK", schedules),
        daily_candles=candles,
        source_provider_identity="KITE",
        source_market_data_boundary=schedules[-1].session_close,
        observed_at=schedules[-1].session_close,
    )
    assert result is not None
    assert result.status is DerivedBarStatus.UNAVAILABLE
    assert result.unavailable_reason == "EXPECTED_DAILY_CONSTITUENT_MISSING"
    assert result.open is None


def test_session_aligned_four_hour_includes_completed_shortened_remainder() -> None:
    schedule = _schedule(date(2026, 8, 14), time(9, 15), time(15, 30))
    starts = tuple(
        schedule.session_open + timedelta(hours=index)  # type: ignore[operator]
        for index in range(7)
        if schedule.session_open + timedelta(hours=index) < schedule.session_close  # type: ignore[operator]
    )
    candles = tuple(_candle(start, 100.0 + index) for index, start in enumerate(starts))
    bars = derive_session_four_hour_bars(
        canonical_instrument="RELIANCE",
        schedule=schedule,
        sixty_minute_candles=candles,
        source_provider_identity="KITE",
        source_market_data_boundary=schedule.session_close,
        observed_at=schedule.session_close,
    )
    assert len(bars) == 2
    assert bars[0].actual_duration == timedelta(hours=4)
    assert bars[0].bucket_class is DerivedBucketClass.FULL_DURATION
    assert bars[1].actual_duration == timedelta(hours=2, minutes=15)
    assert bars[1].bucket_class is DerivedBucketClass.SESSION_REMAINDER
    assert bars[1].partial_session_bucket is True
    assert bars[1].status is DerivedBarStatus.COMPLETE


def test_unfinished_four_hour_bucket_is_excluded() -> None:
    schedule = _schedule(date(2026, 8, 14), time(9, 15), time(15, 30))
    candles = tuple(
        _candle(schedule.session_open + timedelta(hours=index), 100.0 + index)  # type: ignore[operator]
        for index in range(7)
        if schedule.session_open + timedelta(hours=index) < schedule.session_close  # type: ignore[operator]
    )
    bars = derive_session_four_hour_bars(
        canonical_instrument="RELIANCE",
        schedule=schedule,
        sixty_minute_candles=candles,
        source_provider_identity="KITE",
        source_market_data_boundary=schedule.session_open + timedelta(hours=5),  # type: ignore[operator]
        observed_at=schedule.session_open + timedelta(hours=5),  # type: ignore[operator]
    )
    assert len(bars) == 1


def test_17_august_admits_only_completed_governed_hour_and_four_hour_buckets() -> None:
    publisher = MarketCalendarPublisher()
    observed_at = datetime(2026, 8, 17, 14, 0, tzinfo=IST)
    schedule = publisher.schedule("NSE", date(2026, 8, 17), observed_at=observed_at)
    assert schedule is not None and schedule.session_open is not None
    candles = tuple(
        _candle(schedule.session_open + timedelta(hours=index), 100.0 + index)
        for index in range(5)
    )
    bars = derive_session_four_hour_bars(
        canonical_instrument="RELIANCE",
        schedule=schedule,
        sixty_minute_candles=candles,
        source_provider_identity="KITE",
        source_market_data_boundary=candles[-1].timestamp,
        observed_at=observed_at,
    )

    assert len(bars) == 1
    assert bars[0].derived_start == schedule.session_open
    assert bars[0].derived_end == schedule.session_open + timedelta(hours=4)
    assert bars[0].status is DerivedBarStatus.COMPLETE


def test_missing_hour_makes_only_its_completed_bucket_unavailable() -> None:
    schedule = _schedule(date(2026, 8, 14), time(9), time(18))
    candles = tuple(
        _candle(schedule.session_open + timedelta(hours=index), 100.0 + index)  # type: ignore[operator]
        for index in range(9)
        if index != 2
    )
    bars = derive_session_four_hour_bars(
        canonical_instrument="RELIANCE",
        schedule=schedule,
        sixty_minute_candles=candles,
        source_provider_identity="KITE",
        source_market_data_boundary=schedule.session_close,
        observed_at=schedule.session_close,
    )
    assert tuple(item.status for item in bars) == (
        DerivedBarStatus.UNAVAILABLE,
        DerivedBarStatus.COMPLETE,
        DerivedBarStatus.COMPLETE,
    )
    assert bars[0].unavailable_reason == "EXPECTED_60MINUTE_CONSTITUENT_MISSING"


def test_special_short_session_uses_supplied_domain_008_boundaries() -> None:
    schedule = _schedule(date(2026, 8, 15), time(18), time(19), session="NSE-SPECIAL")
    bars = derive_session_four_hour_bars(
        canonical_instrument="NIFTY",
        schedule=schedule,
        sixty_minute_candles=(_candle(schedule.session_open, 100.0),),  # type: ignore[arg-type]
        source_provider_identity="KITE",
        source_market_data_boundary=schedule.session_close,
        observed_at=schedule.session_close,
    )
    assert len(bars) == 1
    assert bars[0].actual_duration == timedelta(hours=1)
    assert bars[0].partial_session_bucket
    assert bars[0].session_identity == "NSE-SPECIAL"


def test_governed_week_rejects_mixed_calendar_identity() -> None:
    first = _schedule(date(2026, 8, 10), time(9, 15), time(15, 30))
    second = _schedule(date(2026, 8, 11), time(9, 15), time(15, 30))
    object.__setattr__(second, "calendar_version", "2")
    with pytest.raises(ValueError, match="GOVERNED_TRADING_WEEK_INVALID"):
        GovernedTradingWeek("WEEK", (first, second))
