from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from kronos.market.calendar import (
    PublishedTradingSession,
    PublishedTradingWindow,
)
from kronos.market.derived_timeframes import (
    DerivedBucketClass,
    GovernedTradingWeek,
    derive_session_four_hour_bars,
    derive_weekly_bar,
)
from kronos.market.schedule import (
    AuthoritativeMarketScheduleFacts,
    MarketAvailability,
    MarketSessionWindow,
    NseMarketScheduleAdapter,
    ScheduleFreshness,
    ScheduleIntegrity,
)
from kronos.provider.contracts.market_data import HistoricalCandle


IST = ZoneInfo("Asia/Kolkata")
DAY = date(2024, 5, 18)


def _window(order: int, opening: time, closing: time) -> MarketSessionWindow:
    return MarketSessionWindow(
        f"NSE-SPECIAL-{DAY.isoformat()}:WINDOW:{order}",
        order,
        datetime.combine(DAY, opening, IST),
        datetime.combine(DAY, closing, IST),
    )


def _schedule(windows: tuple[MarketSessionWindow, ...]):  # type: ignore[no-untyped-def]
    observed_at = windows[-1].window_close
    return NseMarketScheduleAdapter().normalize(AuthoritativeMarketScheduleFacts(
        market_identity="NSE_CAPITAL_MARKET",
        exchange="NSE",
        trading_date=DAY,
        calendar_identity="KRONOS-NSE-CAPITAL-MARKET-TEST",
        calendar_version="TEST.1",
        session_identity=f"NSE-SPECIAL-{DAY.isoformat()}",
        session_type="SPECIAL_LIVE_DR",
        session_open=None,
        session_close=None,
        timezone="Asia/Kolkata",
        market_availability=MarketAvailability.CLOSED,
        as_of=observed_at,
        source_identity="KRONOS-MARKET-CALENDAR-V1",
        source_boundary=observed_at,
        freshness_status=ScheduleFreshness.CURRENT,
        integrity_status=ScheduleIntegrity.VALID,
        provenance=("NSE-MSD-61893",),
        windows=windows,
    ))


def _candle(timestamp: datetime, price: float) -> HistoricalCandle:
    return HistoricalCandle(
        timestamp,
        price,
        price + 2.0,
        price - 1.0,
        price + 1.0,
        100,
    )


def test_legacy_single_window_projection_remains_exact() -> None:
    opening = datetime.combine(DAY, time(9, 15), IST)
    closing = datetime.combine(DAY, time(15, 30), IST)
    schedule = NseMarketScheduleAdapter().normalize(AuthoritativeMarketScheduleFacts(
        market_identity="NSE_CAPITAL_MARKET",
        exchange="NSE",
        trading_date=DAY,
        calendar_identity="NSE-LEGACY",
        calendar_version="1",
        session_identity="NSE-LEGACY-SESSION",
        session_type="REGULAR",
        session_open=opening,
        session_close=closing,
        timezone="Asia/Kolkata",
        market_availability=MarketAvailability.CLOSED,
        as_of=closing,
        source_identity="DOMAIN-008",
        source_boundary=closing,
        freshness_status=ScheduleFreshness.CURRENT,
        integrity_status=ScheduleIntegrity.VALID,
        provenance=("NSE-MARKET-TIMINGS",),
    ))

    assert len(schedule.windows) == 1
    assert schedule.session_open == schedule.windows[0].window_open == opening
    assert schedule.session_close == schedule.windows[0].window_close == closing


def test_multi_window_validation_and_legacy_flattening_prohibition() -> None:
    windows = (
        _window(1, time(9, 15), time(10)),
        _window(2, time(11, 30), time(12, 30)),
    )
    schedule = _schedule(windows)

    assert schedule.windows == windows
    assert schedule.session_open is None
    assert schedule.session_close is None
    assert schedule.market_availability is MarketAvailability.CLOSED

    PublishedTradingSession(
        DAY,
        "SPECIAL_LIVE_DR",
        None,
        None,
        (
            PublishedTradingWindow(1, time(9, 15), time(10)),
            PublishedTradingWindow(2, time(11, 30), time(12, 30)),
        ),
    )
    with pytest.raises(ValueError, match="MARKET_CALENDAR_SESSION_INVALID"):
        PublishedTradingSession(
            DAY,
            "SPECIAL_LIVE_DR",
            None,
            None,
            (
                PublishedTradingWindow(1, time(11, 30), time(12, 30)),
                PublishedTradingWindow(2, time(9, 15), time(10)),
            ),
        )
    with pytest.raises(ValueError, match="MARKET_CALENDAR_SESSION_INVALID"):
        PublishedTradingSession(
            DAY,
            "SPECIAL_LIVE_DR",
            None,
            None,
            (
                PublishedTradingWindow(1, time(9, 15), time(11, 45)),
                PublishedTradingWindow(2, time(11, 30), time(12, 30)),
            ),
        )
    with pytest.raises(ValueError, match="MARKET_CALENDAR_WINDOW_INVALID"):
        PublishedTradingWindow(1, time(10), time(10))

    unavailable = NseMarketScheduleAdapter().normalize(AuthoritativeMarketScheduleFacts(
        market_identity="NSE_CAPITAL_MARKET",
        exchange="NSE",
        trading_date=DAY,
        calendar_identity="NSE-INCOMPLETE",
        calendar_version="1",
        session_identity="NSE-INCOMPLETE-SESSION",
        session_type="SPECIAL_LIVE_DR",
        session_open=None,
        session_close=None,
        timezone="Asia/Kolkata",
        market_availability=MarketAvailability.CLOSED,
        as_of=datetime.combine(DAY, time(12, 30), IST),
        source_identity="DOMAIN-008",
        source_boundary=datetime.combine(DAY, time(12, 30), IST),
        freshness_status=ScheduleFreshness.CURRENT,
        integrity_status=ScheduleIntegrity.VALID,
        provenance=("INCOMPLETE-OFFICIAL-SCHEDULE",),
    ))
    assert unavailable.market_availability is MarketAvailability.UNAVAILABLE
    assert unavailable.windows == ()


def test_closed_gap_and_final_window_completion_are_explicit() -> None:
    schedule = _schedule((
        _window(1, time(9, 15), time(10)),
        _window(2, time(11, 30), time(12, 30)),
    ))

    assert schedule.window_at(datetime.combine(DAY, time(9, 30), IST)) is schedule.windows[0]
    assert schedule.window_at(datetime.combine(DAY, time(10, 30), IST)) is None
    assert schedule.window_at(datetime.combine(DAY, time(12), IST)) is schedule.windows[1]
    assert not schedule.trading_date_completed(datetime.combine(DAY, time(10), IST))
    assert schedule.trading_date_completed(datetime.combine(DAY, time(12, 30), IST))


def test_four_hour_buckets_restart_at_each_window_and_never_cross_gap() -> None:
    schedule = _schedule((
        _window(1, time(9), time(11)),
        _window(2, time(12), time(16)),
    ))
    starts = (
        datetime.combine(DAY, time(9), IST),
        datetime.combine(DAY, time(10), IST),
        datetime.combine(DAY, time(12), IST),
        datetime.combine(DAY, time(13), IST),
        datetime.combine(DAY, time(14), IST),
        datetime.combine(DAY, time(15), IST),
    )
    bars = derive_session_four_hour_bars(
        canonical_instrument="NIFTY",
        schedule=schedule,
        sixty_minute_candles=tuple(
            _candle(timestamp, 100.0 + index)
            for index, timestamp in enumerate(starts)
        ),
        source_provider_identity="KITE",
        source_market_data_boundary=schedule.windows[-1].window_close,
        observed_at=schedule.windows[-1].window_close,
    )

    assert len(bars) == 2
    assert bars[0].derived_start == schedule.windows[0].window_open
    assert bars[0].derived_end == schedule.windows[0].window_close
    assert bars[0].actual_duration == timedelta(hours=2)
    assert bars[0].bucket_class is DerivedBucketClass.SESSION_REMAINDER
    assert bars[1].derived_start == schedule.windows[1].window_open
    assert bars[1].derived_end == schedule.windows[1].window_close
    assert bars[1].actual_duration == timedelta(hours=4)
    assert bars[1].bucket_class is DerivedBucketClass.FULL_DURATION
    assert bars[0].session_identity != bars[1].session_identity
    assert all(
        not (start < datetime.combine(DAY, time(12), IST) < end)
        for bar in bars
        for start, end in bar.constituent_boundaries
    )


def test_multi_window_date_remains_one_daily_and_weekly_constituent() -> None:
    schedule = _schedule((
        _window(1, time(9, 15), time(10)),
        _window(2, time(11, 30), time(12, 30)),
    ))
    week = GovernedTradingWeek("NSE-WEEK-2024-05-13", (schedule,))
    daily = _candle(datetime.combine(DAY, time(0), IST), 100.0)

    bar = derive_weekly_bar(
        canonical_instrument="NIFTY",
        trading_week=week,
        daily_candles=(daily,),
        source_provider_identity="KITE",
        source_market_data_boundary=schedule.windows[-1].window_close,
        observed_at=schedule.windows[-1].window_close,
    )

    assert bar is not None
    assert len(bar.constituent_identities) == 1
    assert bar.constituent_identities == (f"DAY:{DAY.isoformat()}",)
    assert week.identity == "NSE-WEEK-2024-05-13"
