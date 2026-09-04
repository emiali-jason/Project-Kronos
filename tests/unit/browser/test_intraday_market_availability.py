from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kronos.browser.intraday_market_availability import (
    IntradayMarketAvailabilityState,
    project_intraday_market_availability,
)
from kronos.market.calendar import MarketCalendarPublisher


IST = ZoneInfo("Asia/Kolkata")
TRADING_DAY = (2026, 8, 28)


def _at(hour: int, minute: int, second: int = 0):  # type: ignore[no-untyped-def]
    return project_intraday_market_availability(
        MarketCalendarPublisher(),
        observed_at=datetime(*TRADING_DAY, hour, minute, second, tzinfo=IST),
    )


@pytest.mark.parametrize(
    ("clock", "state", "display"),
    (
        ((9, 29, 59), IntradayMarketAvailabilityState.PRE_MARKET,
         "PRE-MARKET — ANALYSIS AVAILABLE FROM 09:30 IST"),
        ((9, 30, 0), IntradayMarketAvailabilityState.AVAILABLE, "AVAILABLE"),
        ((14, 59, 59), IntradayMarketAvailabilityState.AVAILABLE, "AVAILABLE"),
        ((15, 0, 0), IntradayMarketAvailabilityState.CLOSED,
         "ANALYSIS WINDOW CLOSED"),
    ),
)
def test_equity_index_analysis_window_exact_boundaries(
    clock: tuple[int, int, int],
    state: IntradayMarketAvailabilityState,
    display: str,
) -> None:
    equity, _ = _at(*clock)
    assert equity.market_family == "EQUITY / INDEX"
    assert equity.state is state
    assert equity.display == display


@pytest.mark.parametrize(
    ("clock", "state", "display"),
    (
        ((9, 14, 59), IntradayMarketAvailabilityState.PRE_MARKET,
         "PRE-MARKET — ANALYSIS AVAILABLE FROM 09:15 IST"),
        ((9, 15, 0), IntradayMarketAvailabilityState.AVAILABLE, "AVAILABLE"),
        ((22, 59, 59), IntradayMarketAvailabilityState.AVAILABLE, "AVAILABLE"),
        ((23, 0, 0), IntradayMarketAvailabilityState.CLOSED,
         "ANALYSIS WINDOW CLOSED"),
    ),
)
def test_mcx_analysis_window_exact_boundaries(
    clock: tuple[int, int, int],
    state: IntradayMarketAvailabilityState,
    display: str,
) -> None:
    _, mcx = _at(*clock)
    assert mcx.market_family == "MCX"
    assert mcx.state is state
    assert mcx.display == display


def test_domain_008_non_trading_day_disables_both_markets() -> None:
    projected = project_intraday_market_availability(
        MarketCalendarPublisher(),
        observed_at=datetime(2026, 8, 29, 10, 0, tzinfo=IST),
    )
    assert tuple(item.state for item in projected) == (
        IntradayMarketAvailabilityState.NON_TRADING_DAY,
        IntradayMarketAvailabilityState.NON_TRADING_DAY,
    )
    assert all(item.display == "NON-TRADING DAY — ANALYSIS UNAVAILABLE" for item in projected)


@pytest.mark.parametrize(
    ("clock", "available"),
    (
        ((8, 0, 0), ()),
        ((9, 20, 0), ("MCX",)),
        ((10, 0, 0), ("EQUITY / INDEX", "MCX")),
        ((15, 30, 0), ("MCX",)),
        ((23, 30, 0), ()),
    ),
)
def test_market_family_availability_combinations(
    clock: tuple[int, int, int], available: tuple[str, ...]
) -> None:
    projected = _at(*clock)
    assert tuple(item.market_family for item in projected if item.available) == available


def test_projection_is_deterministic_and_read_only() -> None:
    publisher = MarketCalendarPublisher()
    observed_at = datetime(2026, 8, 28, 15, 30, tzinfo=IST)
    first = project_intraday_market_availability(publisher, observed_at=observed_at)
    second = project_intraday_market_availability(publisher, observed_at=observed_at)
    assert first == second
    assert first[0].domain_008_session_identity
    assert first[1].domain_008_session_identity
