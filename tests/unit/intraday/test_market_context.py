from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe
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


def test_subject_bound_source_preserves_reliance_and_index_regimes() -> None:
    root = CurrentMarketCalendarScheduleSource(
        MarketCalendarPublisher(),
        observed_at=datetime(2026, 8, 18, 19, 0, tzinfo=IST),
    )
    reliance = root.for_subject(
        canonical_identity="RELIANCE",
        domain_008_subject_identity="RELIANCE",
    )
    adanient = root.for_subject(
        canonical_identity="NSE-EQUITY-ADANIENT",
        domain_008_subject_identity="ADANIENT",
    )
    nifty = root.for_subject(
        canonical_identity="NSE-INDEX-NIFTY",
        domain_008_subject_identity="NIFTY",
    )
    banknifty = root.for_subject(
        canonical_identity="NSE-INDEX-BANKNIFTY",
        domain_008_subject_identity="BANKNIFTY",
    )

    post = reliance.schedule_for("NSE", date(2026, 8, 18))
    adanient_post = adanient.schedule_for("NSE", date(2026, 8, 18))
    pre = reliance.schedule_for("NSE", date(2026, 7, 31))
    nifty_post = nifty.schedule_for("NSE", date(2026, 8, 18))
    banknifty_post = banknifty.schedule_for("NSE", date(2026, 8, 18))

    assert post is not None and pre is not None and adanient_post is not None
    assert nifty_post is not None and banknifty_post is not None
    assert post.windows[-1].closes_at.time() == datetime.strptime(
        "15:15", "%H:%M"
    ).time()
    assert pre.windows[-1].closes_at.time() == datetime.strptime(
        "15:30", "%H:%M"
    ).time()
    assert adanient_post.windows[-1].closes_at.time() == datetime.strptime(
        "15:15", "%H:%M"
    ).time()
    assert nifty_post.windows[-1].closes_at.time() == datetime.strptime(
        "15:30", "%H:%M"
    ).time()
    assert banknifty_post.windows[-1].closes_at.time() == datetime.strptime(
        "15:30", "%H:%M"
    ).time()
    reliance_hourly = expected_candle_boundaries(
        post, IntradayTimeframe.ONE_HOUR
    )
    assert tuple(
        (item.start.time(), item.end.time()) for item in reliance_hourly
    ) == tuple(
        (
            datetime.strptime(start, "%H:%M").time(),
            datetime.strptime(end, "%H:%M").time(),
        )
        for start, end in (
            ("09:15", "10:15"),
            ("10:15", "11:15"),
            ("11:15", "12:15"),
            ("12:15", "13:15"),
            ("13:15", "14:15"),
            ("14:15", "15:15"),
        )
    )
    assert reliance.canonical_subject_identity == "RELIANCE"
    assert nifty.canonical_subject_identity == "NSE-INDEX-NIFTY"


def test_subject_bound_source_fails_closed_when_domain_008_membership_is_unknown() -> None:
    source = CurrentMarketCalendarScheduleSource(
        MarketCalendarPublisher(),
        observed_at=datetime(2026, 8, 25, 19, 0, tzinfo=IST),
    ).for_subject(
        canonical_identity="NSE-EQUITY-UNKNOWN",
        domain_008_subject_identity="UNKNOWN",
    )

    with pytest.raises(ValueError, match="MARKET_SESSION_APPLICABILITY_UNAVAILABLE"):
        source.schedule_for("NSE", date(2026, 8, 18))


def test_subject_schedule_and_previous_session_do_not_leak() -> None:
    root = CurrentMarketCalendarScheduleSource(
        MarketCalendarPublisher(),
        observed_at=datetime(2026, 8, 18, 19, 0, tzinfo=IST),
    )
    reliance = root.for_subject(
        canonical_identity="RELIANCE",
        domain_008_subject_identity="RELIANCE",
    )
    nifty = root.for_subject(
        canonical_identity="NSE-INDEX-NIFTY",
        domain_008_subject_identity="NIFTY",
    )

    reliance_previous = reliance.previous_trading_schedule(
        "NSE", date(2026, 8, 18)
    )
    nifty_previous = nifty.previous_trading_schedule(
        "NSE", date(2026, 8, 18)
    )
    assert reliance_previous.trading_date == nifty_previous.trading_date == date(
        2026, 8, 17
    )
    assert reliance_previous.windows[-1].closes_at.time() == datetime.strptime(
        "15:15", "%H:%M"
    ).time()
    assert nifty_previous.windows[-1].closes_at.time() == datetime.strptime(
        "15:30", "%H:%M"
    ).time()
