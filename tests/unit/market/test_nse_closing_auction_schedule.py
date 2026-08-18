from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.market.calendar import MarketCalendarPublisher


IST = ZoneInfo("Asia/Kolkata")
OBSERVED = datetime(2026, 8, 18, 19, 10, tzinfo=IST)


def _source(subject: str) -> CurrentMarketCalendarScheduleSource:
    return CurrentMarketCalendarScheduleSource(
        MarketCalendarPublisher(),
        observed_at=OBSERVED,
        canonical_instrument_id=subject,
    )


def test_pre_cas_replay_preserves_historical_nse_schedule() -> None:
    schedule = _source("RELIANCE").schedule_for("NSE", date(2026, 7, 31))

    assert schedule is not None
    assert schedule.windows[0].opens_at.time() == datetime.strptime("09:15", "%H:%M").time()
    assert schedule.windows[-1].closes_at.time() == datetime.strptime("15:30", "%H:%M").time()
    assert "CONTINUOUS_TRADING" not in schedule.session_id


def test_post_effective_reliance_has_distinct_continuous_and_cas_schedules() -> None:
    source = _source("RELIANCE")
    profile = source.session_profile_for("NSE", date(2026, 8, 18))

    assert profile is not None
    assert profile.continuous_trading.session_type == "CONTINUOUS_TRADING"
    assert profile.continuous_trading.session_open.time() == datetime.strptime("09:15", "%H:%M").time()
    assert profile.continuous_trading.session_close.time() == datetime.strptime("15:15", "%H:%M").time()
    assert profile.closing_auction_session is not None
    assert profile.closing_auction_session.session_type == "CLOSING_AUCTION_SESSION"
    assert profile.closing_auction_session.session_open.time() == datetime.strptime("15:15", "%H:%M").time()
    assert profile.closing_auction_session.session_close.time() == datetime.strptime("15:35", "%H:%M").time()
    assert profile.closing_auction_session.session_identity != profile.continuous_trading.session_identity
    assert "effective_date=2026-08-03" in profile.continuous_trading.provenance


def test_non_applicable_nse_subject_does_not_inherit_cas_schedule() -> None:
    source = _source("NIFTY")
    profile = source.session_profile_for("NSE", date(2026, 8, 18))

    assert profile is not None
    assert profile.closing_auction_session is None
    assert profile.continuous_trading.session_type == "REGULAR"
    assert profile.continuous_trading.session_close.time() == datetime.strptime("15:30", "%H:%M").time()


def test_reliance_continuous_boundaries_exclude_cas_for_all_intraday_frames() -> None:
    schedule = _source("RELIANCE").schedule_for("NSE", date(2026, 8, 18))

    assert schedule is not None
    expected_counts = {
        IntradayTimeframe.ONE_HOUR: 6,
        IntradayTimeframe.FIFTEEN_MINUTES: 24,
        IntradayTimeframe.FIVE_MINUTES: 72,
    }
    for timeframe, count in expected_counts.items():
        boundaries = expected_candle_boundaries(schedule, timeframe)
        assert len(boundaries) == count
        assert boundaries[-1].end == datetime(2026, 8, 18, 15, 15, tzinfo=IST)
        assert all(item.start < datetime(2026, 8, 18, 15, 15, tzinfo=IST) for item in boundaries)


def test_daily_close_semantics_explicitly_allow_distinct_values() -> None:
    profile = _source("RELIANCE").session_profile_for("NSE", date(2026, 8, 18))

    assert profile is not None
    assert profile.last_continuous_close_identity == "LAST_CONTINUOUS_INTRADAY_CLOSE"
    assert profile.official_daily_close_identity == "OFFICIAL_DAILY_CLOSE"
    assert profile.official_daily_close_may_differ is True


def test_effective_date_selection_is_deterministic_across_boundary() -> None:
    source = _source("RELIANCE")
    before = source.schedule_for("NSE", date(2026, 7, 31))
    after = source.schedule_for("NSE", date(2026, 8, 3))

    assert before is not None and after is not None
    assert before.windows[-1].closes_at.time() == datetime.strptime("15:30", "%H:%M").time()
    assert after.windows[-1].closes_at.time() == datetime.strptime("15:15", "%H:%M").time()
    assert after.windows[-1].closes_at - after.windows[0].opens_at == timedelta(hours=6)
