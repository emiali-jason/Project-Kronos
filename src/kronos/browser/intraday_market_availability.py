"""Read-only Sponsor projection of governed Intraday market availability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.market.calendar import MarketCalendarPublisher


_IST = ZoneInfo("Asia/Kolkata")
_FIRST_COMPLETED_CANDLE = timedelta(minutes=15)


class IntradayMarketAvailabilityState(StrEnum):
    PRE_MARKET = "PRE_MARKET"
    AVAILABLE = "AVAILABLE"
    CLOSED = "CLOSED"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class IntradayMarketAvailability:
    market_family: str
    exchange: str
    state: IntradayMarketAvailabilityState
    display: str
    observed_at: datetime
    trading_date: str
    analysis_opens_at: datetime | None
    analysis_closes_at: datetime | None
    domain_008_session_identity: str | None

    @property
    def available(self) -> bool:
        return self.state is IntradayMarketAvailabilityState.AVAILABLE


def project_intraday_market_availability(
    publisher: MarketCalendarPublisher,
    *,
    observed_at: datetime,
) -> tuple[IntradayMarketAvailability, IntradayMarketAvailability]:
    """Project current availability without changing DOMAIN-008 or analysis state."""

    if type(publisher) is not MarketCalendarPublisher or not _aware(observed_at):
        raise ValueError("INTRADAY_MARKET_AVAILABILITY_INPUT_INVALID")
    local = observed_at.astimezone(_IST)
    source = CurrentMarketCalendarScheduleSource(publisher, observed_at=observed_at)
    return (
        _project_one(
            source,
            market_family="EQUITY / INDEX",
            exchange="NSE",
            local=local,
            expected_open=time(9, 30),
            cutoff=time(15, 0),
        ),
        _project_one(
            source,
            market_family="MCX",
            exchange="MCX",
            local=local,
            expected_open=time(9, 15),
            cutoff=time(23, 0),
        ),
    )


def _project_one(
    source: CurrentMarketCalendarScheduleSource,
    *,
    market_family: str,
    exchange: str,
    local: datetime,
    expected_open: time,
    cutoff: time,
) -> IntradayMarketAvailability:
    try:
        schedule = source.schedule_for(exchange, local.date())
    except ValueError:
        return _projection(
            market_family,
            exchange,
            IntradayMarketAvailabilityState.UNAVAILABLE,
            "MARKET CALENDAR UNAVAILABLE",
            local,
        )
    if schedule is None:
        return _projection(
            market_family,
            exchange,
            IntradayMarketAvailabilityState.NON_TRADING_DAY,
            "NON-TRADING DAY — ANALYSIS UNAVAILABLE",
            local,
        )

    # V2 cannot select a phase before the first governed 15-minute candle is
    # complete.  DOMAIN-008 owns the actual session open and session end.
    derived_open = schedule.windows[0].opens_at + _FIRST_COMPLETED_CANDLE
    governed_open = datetime.combine(local.date(), expected_open, _IST)
    governed_cutoff = datetime.combine(local.date(), cutoff, _IST)
    session_close = schedule.windows[-1].closes_at
    analysis_close = min(governed_cutoff, session_close)
    if derived_open != governed_open or governed_open >= analysis_close:
        return _projection(
            market_family,
            exchange,
            IntradayMarketAvailabilityState.UNAVAILABLE,
            "GOVERNED ANALYSIS WINDOW UNAVAILABLE",
            local,
            session_identity=schedule.session_id,
        )
    if local < governed_open:
        state = IntradayMarketAvailabilityState.PRE_MARKET
        display = (
            "PRE-MARKET — ANALYSIS AVAILABLE FROM "
            + governed_open.strftime("%H:%M IST")
        )
    elif local >= analysis_close:
        state = IntradayMarketAvailabilityState.CLOSED
        display = "ANALYSIS WINDOW CLOSED"
    else:
        state = IntradayMarketAvailabilityState.AVAILABLE
        display = "AVAILABLE"
    return _projection(
        market_family,
        exchange,
        state,
        display,
        local,
        opens_at=governed_open,
        closes_at=analysis_close,
        session_identity=schedule.session_id,
    )


def _projection(
    market_family: str,
    exchange: str,
    state: IntradayMarketAvailabilityState,
    display: str,
    local: datetime,
    *,
    opens_at: datetime | None = None,
    closes_at: datetime | None = None,
    session_identity: str | None = None,
) -> IntradayMarketAvailability:
    return IntradayMarketAvailability(
        market_family=market_family,
        exchange=exchange,
        state=state,
        display=display,
        observed_at=local,
        trading_date=local.date().isoformat(),
        analysis_opens_at=opens_at,
        analysis_closes_at=closes_at,
        domain_008_session_identity=session_identity,
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "IntradayMarketAvailability",
    "IntradayMarketAvailabilityState",
    "project_intraday_market_availability",
]
