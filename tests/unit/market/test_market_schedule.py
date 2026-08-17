from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from kronos.market.schedule import (
    InMemoryMarketScheduleSource,
    MarketDaySchedule,
    MarketSessionService,
    MarketSessionState,
    MarketWindow,
    TradingDayStatus,
)


IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 8, 17)


def _schedule(*, windows: tuple[MarketWindow, ...], status: TradingDayStatus = TradingDayStatus.TRADING, special: bool = False) -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange="GOVERNED-EXCHANGE",
        trading_date=DAY,
        session_id="GOVERNED-EXCHANGE-20260817",
        timezone="Asia/Kolkata",
        status=status,
        windows=windows,
        source_identity="AUTHORITATIVE-SOURCE",
        source_version="V1",
        special_session=special,
    )


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 17, hour, minute, tzinfo=IST)


def test_normal_session_before_open_at_end_and_after_session() -> None:
    schedule = _schedule(windows=(MarketWindow(_at(9, 15), _at(15, 30)),))
    service = MarketSessionService(InMemoryMarketScheduleSource((schedule,)))

    assert service.facts(exchange=schedule.exchange, trading_date=DAY, observed_at=_at(9)).state is MarketSessionState.BEFORE_SESSION
    open_fact = service.facts(exchange=schedule.exchange, trading_date=DAY, observed_at=_at(10))
    assert open_fact.state is MarketSessionState.OPEN
    assert open_fact.active_window == schedule.windows[0]
    assert open_fact.session_end is False
    at_end = service.facts(exchange=schedule.exchange, trading_date=DAY, observed_at=_at(15, 30))
    assert at_end.state is MarketSessionState.SESSION_ENDED
    assert at_end.session_end is True
    assert service.facts(exchange=schedule.exchange, trading_date=DAY, observed_at=_at(20)).session_end is True


def test_non_trading_day_and_missing_schedule_fail_closed() -> None:
    closed = _schedule(windows=(), status=TradingDayStatus.NON_TRADING)
    service = MarketSessionService(InMemoryMarketScheduleSource((closed,)))

    fact = service.facts(exchange=closed.exchange, trading_date=DAY, observed_at=_at(10))
    assert fact.availability is True
    assert fact.state is MarketSessionState.NON_TRADING_DAY
    assert fact.session_end is True
    unavailable = service.facts(exchange="UNKNOWN", trading_date=DAY, observed_at=_at(10))
    assert unavailable.availability is False
    assert unavailable.state is MarketSessionState.UNAVAILABLE


def test_timezone_current_date_and_trading_date_are_independent() -> None:
    schedule = _schedule(windows=(MarketWindow(_at(9), _at(10)),))
    service = MarketSessionService(InMemoryMarketScheduleSource((schedule,)))
    utc_next_date = datetime(2026, 8, 18, 0, 0, tzinfo=ZoneInfo("UTC"))

    fact = service.facts(exchange=schedule.exchange, trading_date=DAY, observed_at=utc_next_date)
    assert fact.trading_date == DAY
    assert fact.observed_at.date() != fact.trading_date
    assert fact.state is MarketSessionState.SESSION_ENDED


def test_multi_window_and_special_session_are_explicit_source_facts() -> None:
    schedule = _schedule(
        windows=(MarketWindow(_at(9), _at(11)), MarketWindow(_at(13), _at(15))),
        special=True,
    )
    service = MarketSessionService(InMemoryMarketScheduleSource((schedule,)))

    between = service.facts(exchange=schedule.exchange, trading_date=DAY, observed_at=_at(12))
    assert between.state is MarketSessionState.BETWEEN_WINDOWS
    assert between.active_window is None
    assert between.schedule is not None and between.schedule.special_session is True
    assert service.facts(exchange=schedule.exchange, trading_date=DAY, observed_at=_at(13)).state is MarketSessionState.OPEN


def test_overlapping_or_duplicate_authoritative_schedules_are_rejected() -> None:
    with pytest.raises(ValueError, match="MARKET_SCHEDULE_INVALID"):
        _schedule(windows=(MarketWindow(_at(9), _at(12)), MarketWindow(_at(11), _at(13))))
    schedule = _schedule(windows=(MarketWindow(_at(9), _at(10)),))
    with pytest.raises(ValueError, match="MARKET_SCHEDULE_SOURCE_CONFLICT"):
        InMemoryMarketScheduleSource((schedule, schedule))
