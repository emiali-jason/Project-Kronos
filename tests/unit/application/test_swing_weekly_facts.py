from datetime import date, datetime, timedelta
from decimal import Decimal
import math
from random import Random
from zoneinfo import ZoneInfo

import pytest

from kronos.application.swing_weekly_facts import (
    _pivot_facts,
    acquire_nse_weekly_factual_foundation,
    bounded_day_request_windows,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.v1.weekly_facts import (
    FactualStructureCondition,
    NSE_WEEKLY_REQUIRED_COUNT,
    WeeklyFactAvailability,
    WeeklySmaDirection,
)


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 8, 14, 23, 59, tzinfo=IST)
RUN_ID = "SWING-RUN-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def _instrument() -> InstrumentRecord:
    return InstrumentRecord(
        "KITE", "NSE", "NSE", "RELIANCE", "RELIANCE", "EQ", None,
        Decimal("0.05"), 1,
    )


def _history(mode: str = "rising") -> tuple[HistoricalCandle, ...]:
    publication = MarketCalendarPublisher().publication("NSE")
    result = []
    total = len(publication.trading_dates)
    for index, day in enumerate(sorted(publication.trading_dates)):
        close = (
            100.0
            if mode == "flat"
            else 100.0 + index
            if mode == "rising"
            else 100.0 + total - index
        )
        result.append(HistoricalCandle(
            datetime.combine(day, datetime.min.time(), tzinfo=IST),
            close, close + 1.0, close - 1.0, close, 1000 + index,
        ))
    return tuple(result)


def _build(
    history: tuple[HistoricalCandle, ...],
    *,
    observed_at: datetime = NOW,
    predecessor=None,
    canonical_instrument: str = "RELIANCE",
):  # type: ignore[no-untyped-def]
    requests = []

    def retrieve(request):  # type: ignore[no-untyped-def]
        requests.append(request)
        return tuple(
            item for item in history
            if request.start <= item.timestamp.astimezone(request.start.tzinfo) <= request.end
        )

    foundation, acquired = acquire_nse_weekly_factual_foundation(
        run_identity=RUN_ID,
        canonical_instrument=canonical_instrument,
        provider_instrument=_instrument(),
        historical_candles=retrieve,
        calendar_publisher=MarketCalendarPublisher(),
        observed_at=observed_at,
        predecessor=predecessor,
    )
    return foundation, acquired, requests


def test_nse_weekly_bootstrap_builds_exact_205_weeks_and_exact_sma_windows() -> None:
    foundation, acquired, requests = _build(_history())

    assert foundation.availability is WeeklyFactAvailability.AVAILABLE
    assert len(foundation.completed_weekly_bars) == NSE_WEEKLY_REQUIRED_COUNT
    closes = tuple(item.close for item in foundation.completed_weekly_bars)
    assert foundation.current_sma200 == math.fsum(closes[-200:]) / 200
    assert foundation.prior_sma200_5w == math.fsum(closes[:-5][-200:]) / 200
    assert foundation.sma200_difference == (
        foundation.current_sma200 - foundation.prior_sma200_5w
    )
    assert foundation.sma200_direction is WeeklySmaDirection.RISING
    assert len(requests) == 1
    assert foundation.request_windows[0].result_count == len(acquired)
    assert foundation.calendar_identity == "KRONOS-NSE-CAPITAL-MARKET-2022-2026"
    assert foundation.calendar_version == "2026.1.2"


def test_corrected_bakri_id_week_is_complete_with_legitimate_provider_evidence() -> None:
    foundation, _, _ = _build(_history())
    week = next(
        item
        for item in foundation.completed_weekly_bars
        if item.trading_week_identity.endswith("WEEK:2023-06-26")
    )

    assert week.constituent_identities == (
        "DAY:2023-06-26",
        "DAY:2023-06-27",
        "DAY:2023-06-28",
        "DAY:2023-06-30",
    )


def test_bounded_day_windows_have_no_date_gap_or_overlap() -> None:
    windows = bounded_day_request_windows(
        date(2015, 1, 1), NOW, IST
    )

    assert len(windows) == 3
    assert all(
        current[0].date() == previous[1].date() + timedelta(days=1)
        for previous, current in zip(windows, windows[1:])
    )
    assert all((end.date() - start.date()).days + 1 <= 1900 for start, end in windows)


def test_provider_day_result_outside_bounded_window_fails_closed() -> None:
    outside = HistoricalCandle(
        datetime(2022, 9, 11, tzinfo=IST),
        100.0, 101.0, 99.0, 100.0, 1,
    )

    with pytest.raises(
        ValueError, match="NSE_WEEKLY_DAY_RESPONSE_OUTSIDE_REQUEST_WINDOW"
    ):
        acquire_nse_weekly_factual_foundation(
            run_identity=RUN_ID,
            canonical_instrument="RELIANCE",
            provider_instrument=_instrument(),
            historical_candles=lambda _request: (outside,),
            calendar_publisher=MarketCalendarPublisher(),
            observed_at=NOW,
        )


def test_holiday_shortened_and_multi_window_weeks_are_factual_complete() -> None:
    foundation, _, _ = _build(_history())

    assert any(len(item.constituent_identities) < 5 for item in foundation.completed_weekly_bars)
    multi = next(
        item for item in foundation.completed_weekly_bars
        if "DAY:2024-03-02" in item.constituent_identities
    )
    assert multi.constituent_identities.count("DAY:2024-03-02") == 1


def test_missing_expected_daily_constituent_fails_closed_per_instrument() -> None:
    history = tuple(
        item for item in _history()
        if item.timestamp.astimezone(IST).date() != date(2025, 1, 15)
    )
    foundation, _, _ = _build(history)

    assert foundation.availability is WeeklyFactAvailability.UNAVAILABLE
    assert foundation.unavailable_reason == "MISSING_REQUIRED_DAILY_CONSTITUENT"
    assert foundation.current_sma200 is None


def test_insufficient_provider_history_is_unavailable_not_fabricated() -> None:
    foundation, _, _ = _build(_history()[-100:])

    assert foundation.availability is WeeklyFactAvailability.UNAVAILABLE
    assert foundation.unavailable_reason == "INSUFFICIENT_PROVIDER_HISTORY"
    assert len(foundation.completed_weekly_bars) < NSE_WEEKLY_REQUIRED_COUNT


@pytest.mark.parametrize(
    ("canonical_instrument", "listing_date"),
    (
        ("JIOFIN", date(2023, 8, 21)),
        ("KAYNES", date(2022, 11, 28)),
    ),
)
def test_recently_listed_subjects_remain_unavailable_without_fabricated_history(
    canonical_instrument: str,
    listing_date: date,
) -> None:
    history = tuple(
        item
        for item in _history()
        if item.timestamp.astimezone(IST).date() >= listing_date
    )

    foundation, _, _ = _build(
        history,
        canonical_instrument=canonical_instrument,
    )

    assert foundation.canonical_instrument == canonical_instrument
    assert foundation.availability is WeeklyFactAvailability.UNAVAILABLE
    assert foundation.unavailable_reason == "INSUFFICIENT_PROVIDER_HISTORY"
    assert len(foundation.completed_weekly_bars) < NSE_WEEKLY_REQUIRED_COUNT
    assert foundation.current_sma200 is None
    assert foundation.prior_sma200_5w is None


def test_current_incomplete_governed_week_is_excluded() -> None:
    observed_at = datetime(2026, 8, 12, 12, 0, tzinfo=IST)
    foundation, _, _ = _build(_history(), observed_at=observed_at)

    assert foundation.availability is WeeklyFactAvailability.UNAVAILABLE
    assert len(foundation.completed_weekly_bars) == 204
    assert all(
        item.observation_boundary <= observed_at
        for item in foundation.completed_weekly_bars
    )


def test_sma_direction_uses_strict_greater_less_and_exact_equality() -> None:
    rising, _, _ = _build(_history("rising"))
    falling, _, _ = _build(_history("falling"))
    flat, _, _ = _build(_history("flat"))

    assert rising.sma200_direction is WeeklySmaDirection.RISING
    assert falling.sma200_direction is WeeklySmaDirection.FALLING
    assert flat.sma200_direction is WeeklySmaDirection.FLAT
    assert flat.sma200_difference == 0.0


def test_radius_one_and_two_are_retained_independently_without_consensus_gate() -> None:
    random = Random(0)
    candles = []
    center = 100.0
    for index in range(60):
        center = max(10.0, center + random.uniform(-10.0, 10.0))
        candles.append(HistoricalCandle(
            NOW - timedelta(weeks=59 - index),
            center, center + random.uniform(0.1, 5.0),
            center - random.uniform(0.1, 5.0), center, 1000 + index,
        ))

    radius_1 = _pivot_facts(tuple(candles), 1)
    radius_2 = _pivot_facts(tuple(candles), 2)

    assert radius_1.radius == 1
    assert radius_2.radius == 2
    assert (radius_1.high_relation, radius_1.low_relation) != (
        radius_2.high_relation, radius_2.low_relation
    )
    assert radius_1.condition in FactualStructureCondition
    assert radius_2.condition in FactualStructureCondition


def test_available_predecessor_uses_bounded_daily_ma_context_and_preserves_205() -> None:
    predecessor, _, _ = _build(_history())
    next_run, _, requests = _build(_history(), predecessor=predecessor)

    assert next_run.availability is WeeklyFactAvailability.AVAILABLE
    assert len(next_run.completed_weekly_bars) == 205
    assert next_run.predecessor_source_result_sha256 == predecessor.source_result_sha256
    assert requests[0].start.astimezone(IST).date() > date(2025, 1, 1)
    assert requests[0].start.astimezone(IST).weekday() == 0
