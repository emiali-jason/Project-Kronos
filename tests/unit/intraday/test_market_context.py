from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.market_context import (
    CurrentMarketCalendarScheduleSource,
    IntradayMarketContextAdapter,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.schedule import (
    InMemoryMarketScheduleSource,
    MarketDaySchedule,
    MarketSessionService,
    MarketWindow,
    TradingDayStatus,
)


IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 8, 17)


def _source() -> InMemoryMarketScheduleSource:
    return InMemoryMarketScheduleSource((MarketDaySchedule(
        exchange="NSE",
        trading_date=DAY,
        session_id="NSE-20260817-REGULAR",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(MarketWindow(
            datetime(2026, 8, 17, 9, 15, tzinfo=IST),
            datetime(2026, 8, 17, 15, 30, tzinfo=IST),
        ),),
        source_identity="KRONOS-MARKET-CALENDAR-V1|NSE-2026",
        source_version="2026.08",
    ),))


def test_intraday_market_adapter_preserves_domain_008_fact_semantics() -> None:
    source = _source()
    observed_at = datetime(2026, 8, 17, 10, 0, tzinfo=IST)

    adapted = IntradayMarketContextAdapter(source).session_facts(
        exchange="NSE",
        trading_date=DAY,
        observed_at=observed_at,
    )
    governed = MarketSessionService(source).facts(
        exchange="NSE",
        trading_date=DAY,
        observed_at=observed_at,
    )

    assert adapted == governed


def test_intraday_market_adapter_rejects_non_domain_008_source() -> None:
    with pytest.raises(ValueError, match="INTRADAY_MARKET_CONTEXT_SOURCE_INVALID"):
        IntradayMarketContextAdapter(object())  # type: ignore[arg-type]


def test_current_domain_008_publisher_is_adapted_without_calendar_inference() -> None:
    observed = datetime(2026, 8, 18, 10, 17, tzinfo=IST)
    source = CurrentMarketCalendarScheduleSource(
        MarketCalendarPublisher(), observed_at=observed
    )

    current = source.schedule_for("NSE", date(2026, 8, 18))
    previous = source.previous_trading_schedule("NSE", date(2026, 8, 18))

    assert current is not None
    assert current.source_identity == "KRONOS-MARKET-CALENDAR-V1"
    assert current.source_version == "2026.1.2"
    assert (current.windows[0].opens_at.hour, current.windows[0].opens_at.minute) == (9, 15)
    assert previous.trading_date == date(2026, 8, 17)
