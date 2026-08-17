from datetime import date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from kronos.market.calendar import (
    DEFAULT_MARKET_CALENDAR_ROOT,
    MarketCalendarPublisher,
)


IST = ZoneInfo("Asia/Kolkata")
OBSERVED = datetime(2026, 8, 14, 23, 59, tzinfo=IST)


def test_original_2026_publication_remains_byte_immutable() -> None:
    original = DEFAULT_MARKET_CALENDAR_ROOT / "NSE-CAPITAL-MARKET-2026.v1.json"
    assert sha256(original.read_bytes()).hexdigest() == (
        "50ec059dea93a30afad78e0ec0102a21f96776200555847bcbb67a7d005b839b"
    )


def test_historical_publication_covers_every_date_and_representative_holidays() -> None:
    publication = MarketCalendarPublisher().publication("NSE")
    assert publication.coverage_start == date(2022, 9, 12)
    assert publication.coverage_end == date(2026, 12, 31)
    assert len(publication.trading_dates) + len(publication.non_trading_dates) == (
        publication.coverage_end - publication.coverage_start
    ).days + 1
    assert publication.non_trading_dates[date(2022, 10, 5)] == "DUSSEHRA"
    assert publication.non_trading_dates[date(2023, 4, 14)] == (
        "DR_BABA_SAHEB_AMBEDKAR_JAYANTI"
    )
    assert publication.non_trading_dates[date(2024, 5, 20)] == (
        "PARLIAMENTARY_ELECTION"
    )
    assert publication.non_trading_dates[date(2024, 11, 20)] == (
        "ASSEMBLY_ELECTION"
    )
    assert publication.non_trading_dates[date(2025, 3, 14)] == "HOLI"
    assert publication.non_trading_dates[date(2026, 1, 15)] == (
        "MUNICIPAL_CORPORATION_ELECTION"
    )


def test_all_historical_special_sessions_have_authoritative_boundaries() -> None:
    publisher = MarketCalendarPublisher()
    expected = {
        date(2022, 10, 24): ("SPECIAL_MUHURAT", time(18, 15), time(19, 15)),
        date(2023, 11, 12): ("SPECIAL_MUHURAT", time(18, 15), time(19, 15)),
        date(2024, 1, 20): (
            "SPECIAL_REGULAR_PRIMARY_SITE", time(9, 15), time(15, 30)
        ),
        date(2024, 11, 1): ("SPECIAL_MUHURAT", time(18), time(19)),
        date(2025, 2, 1): (
            "SPECIAL_UNION_BUDGET", time(9, 15), time(15, 30)
        ),
        date(2025, 10, 21): ("SPECIAL_MUHURAT", time(13, 45), time(14, 45)),
        date(2026, 2, 1): (
            "SPECIAL_UNION_BUDGET", time(9, 15), time(15, 30)
        ),
    }
    for trading_date, (session_type, opening, closing) in expected.items():
        schedule = publisher.schedule("NSE", trading_date, observed_at=OBSERVED)
        assert schedule is not None
        assert schedule.session_type == session_type
        assert schedule.session_open is not None
        assert schedule.session_close is not None
        assert schedule.session_open.timetz().replace(tzinfo=None) == opening
        assert schedule.session_close.timetz().replace(tzinfo=None) == closing


def test_2024_live_dr_sessions_preserve_two_windows_and_closed_gap() -> None:
    publisher = MarketCalendarPublisher()
    for trading_date in (date(2024, 3, 2), date(2024, 5, 18)):
        schedule = publisher.schedule("NSE", trading_date, observed_at=OBSERVED)
        assert schedule is not None
        assert schedule.session_type == "SPECIAL_LIVE_DR"
        assert schedule.session_open is None
        assert schedule.session_close is None
        assert tuple(
            (
                window.window_open.timetz().replace(tzinfo=None),
                window.window_close.timetz().replace(tzinfo=None),
            )
            for window in schedule.windows
        ) == ((time(9, 15), time(10)), (time(11, 30), time(12, 30)))
        gap = datetime.combine(trading_date, time(10, 30), IST)
        assert schedule.window_at(gap) is None
        assert not schedule.trading_date_completed(
            datetime.combine(trading_date, time(10), IST)
        )
        assert schedule.trading_date_completed(
            datetime.combine(trading_date, time(12, 30), IST)
        )


def test_special_sessions_are_one_governed_trading_date_and_week_member() -> None:
    publisher = MarketCalendarPublisher()
    for trading_date in (
        date(2023, 11, 12),
        date(2024, 3, 2),
        date(2024, 5, 18),
    ):
        week = publisher.trading_week("NSE", trading_date, observed_at=OBSERVED)
        assert tuple(
            schedule.trading_date for schedule in week.schedules
        ).count(trading_date) == 1


def test_publication_establishes_205_completed_governed_weeks() -> None:
    publisher = MarketCalendarPublisher()
    publication = publisher.publication("NSE")
    weeks: dict[date, list[date]] = {}
    for trading_date in publication.trading_dates:
        week_start = trading_date - timedelta(days=trading_date.weekday())
        weeks.setdefault(week_start, []).append(trading_date)

    completed = []
    for week_start, members in sorted(weeks.items()):
        governed = publisher.trading_week("NSE", week_start, observed_at=OBSERVED)
        assert tuple(item.trading_date for item in governed.schedules) == tuple(sorted(members))
        if all(item.trading_date_completed(OBSERVED) for item in governed.schedules):
            completed.append(week_start)

    assert len(completed) == 205
    assert completed[0] == date(2022, 9, 12)
    assert completed[-1] == date(2026, 8, 10)


def test_holiday_never_creates_daily_constituent() -> None:
    publisher = MarketCalendarPublisher()
    for holiday in (
        date(2022, 10, 5),
        date(2023, 12, 25),
        date(2024, 5, 20),
        date(2025, 8, 15),
        date(2026, 1, 26),
    ):
        assert publisher.schedule("NSE", holiday, observed_at=OBSERVED) is None
