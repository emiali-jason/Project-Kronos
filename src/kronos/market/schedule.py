"""DOMAIN-008 factual Market schedule service.

The service contains no exchange rules.  It only evaluates explicit schedules
provided by an authoritative source selected outside this component.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


MARKET_SCHEDULE_SCHEMA = "KRONOS-MARKET-SCHEDULE-V1"


class TradingDayStatus(StrEnum):
    TRADING = "TRADING"
    NON_TRADING = "NON_TRADING"


class MarketSessionState(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    BEFORE_SESSION = "BEFORE_SESSION"
    OPEN = "OPEN"
    BETWEEN_WINDOWS = "BETWEEN_WINDOWS"
    SESSION_ENDED = "SESSION_ENDED"


@dataclass(frozen=True, slots=True)
class MarketWindow:
    opens_at: datetime
    closes_at: datetime

    def __post_init__(self) -> None:
        if (
            not _aware(self.opens_at)
            or not _aware(self.closes_at)
            or self.opens_at >= self.closes_at
            or self.opens_at.tzinfo != self.closes_at.tzinfo
            or self.opens_at.date() != self.closes_at.date()
        ):
            raise ValueError("MARKET_WINDOW_INVALID")


@dataclass(frozen=True, slots=True)
class MarketDaySchedule:
    exchange: str
    trading_date: date
    session_id: str
    timezone: str
    status: TradingDayStatus
    windows: tuple[MarketWindow, ...]
    source_identity: str
    source_version: str
    special_session: bool = False
    schema_identity: str = MARKET_SCHEDULE_SCHEMA

    def __post_init__(self) -> None:
        try:
            zone = ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, TypeError) as error:
            raise ValueError("MARKET_SCHEDULE_INVALID") from error
        trading = self.status is TradingDayStatus.TRADING
        if (
            not _text(self.exchange)
            or type(self.trading_date) is not date
            or not _text(self.session_id)
            or type(self.status) is not TradingDayStatus
            or type(self.windows) is not tuple
            or any(type(window) is not MarketWindow for window in self.windows)
            or trading != bool(self.windows)
            or any(window.opens_at.date() != self.trading_date for window in self.windows)
            or any(window.opens_at.tzinfo != zone for window in self.windows)
            or any(current.opens_at < previous.closes_at for previous, current in zip(self.windows, self.windows[1:]))
            or not _text(self.source_identity)
            or not _text(self.source_version)
            or type(self.special_session) is not bool
            or self.schema_identity != MARKET_SCHEDULE_SCHEMA
        ):
            raise ValueError("MARKET_SCHEDULE_INVALID")


class MarketScheduleSource(Protocol):
    def schedule_for(self, exchange: str, trading_date: date) -> MarketDaySchedule | None:
        """Return one authoritative schedule or no fact."""


class InMemoryMarketScheduleSource:
    """Explicit schedule source useful for controlled composition and tests."""

    def __init__(self, schedules: Iterable[MarketDaySchedule]) -> None:
        items = tuple(schedules)
        if any(type(item) is not MarketDaySchedule for item in items):
            raise ValueError("MARKET_SCHEDULE_SOURCE_INVALID")
        indexed: dict[tuple[str, date], MarketDaySchedule] = {}
        for item in items:
            key = (item.exchange, item.trading_date)
            if key in indexed:
                raise ValueError("MARKET_SCHEDULE_SOURCE_CONFLICT")
            indexed[key] = item
        self._schedules = indexed

    def schedule_for(self, exchange: str, trading_date: date) -> MarketDaySchedule | None:
        return self._schedules.get((exchange, trading_date))


@dataclass(frozen=True, slots=True)
class MarketSessionFact:
    exchange: str
    trading_date: date
    observed_at: datetime
    availability: bool
    state: MarketSessionState
    schedule: MarketDaySchedule | None
    active_window: MarketWindow | None
    session_end: bool

    def __post_init__(self) -> None:
        schedule_matches = self.schedule is None or (
            self.schedule.exchange == self.exchange
            and self.schedule.trading_date == self.trading_date
        )
        unavailable = self.state is MarketSessionState.UNAVAILABLE
        non_trading = self.state is MarketSessionState.NON_TRADING_DAY
        if (
            not _text(self.exchange)
            or type(self.trading_date) is not date
            or not _aware(self.observed_at)
            or type(self.availability) is not bool
            or type(self.state) is not MarketSessionState
            or (self.availability != (self.schedule is not None))
            or not schedule_matches
            or (unavailable != (not self.availability))
            or (
                self.schedule is not None
                and non_trading
                != (self.schedule.status is TradingDayStatus.NON_TRADING)
            )
            or ((self.active_window is not None) != (self.state is MarketSessionState.OPEN))
            or type(self.session_end) is not bool
            or (
                self.session_end
                != (
                    self.state
                    in {
                        MarketSessionState.NON_TRADING_DAY,
                        MarketSessionState.SESSION_ENDED,
                    }
                )
            )
        ):
            raise ValueError("MARKET_SESSION_FACT_INVALID")


class MarketSessionService:
    def __init__(self, source: MarketScheduleSource) -> None:
        if not callable(getattr(source, "schedule_for", None)):
            raise ValueError("MARKET_SCHEDULE_SOURCE_INVALID")
        self._source = source

    def facts(self, *, exchange: str, trading_date: date, observed_at: datetime) -> MarketSessionFact:
        if not _text(exchange) or type(trading_date) is not date or not _aware(observed_at):
            raise ValueError("MARKET_SESSION_REQUEST_INVALID")
        schedule = self._source.schedule_for(exchange, trading_date)
        if schedule is None or type(schedule) is not MarketDaySchedule or schedule.exchange != exchange or schedule.trading_date != trading_date:
            return MarketSessionFact(exchange, trading_date, observed_at, False, MarketSessionState.UNAVAILABLE, None, None, False)
        local = observed_at.astimezone(ZoneInfo(schedule.timezone))
        if schedule.status is TradingDayStatus.NON_TRADING:
            return MarketSessionFact(exchange, trading_date, observed_at, True, MarketSessionState.NON_TRADING_DAY, schedule, None, True)
        first, last = schedule.windows[0], schedule.windows[-1]
        active = next((window for window in schedule.windows if window.opens_at <= local < window.closes_at), None)
        if active is not None:
            state = MarketSessionState.OPEN
        elif local < first.opens_at:
            state = MarketSessionState.BEFORE_SESSION
        elif local >= last.closes_at:
            state = MarketSessionState.SESSION_ENDED
        else:
            state = MarketSessionState.BETWEEN_WINDOWS
        return MarketSessionFact(
            exchange,
            trading_date,
            observed_at,
            True,
            state,
            schedule,
            active,
            local >= last.closes_at,
        )


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


__all__ = [
    "InMemoryMarketScheduleSource",
    "MARKET_SCHEDULE_SCHEMA",
    "MarketDaySchedule",
    "MarketScheduleSource",
    "MarketSessionFact",
    "MarketSessionService",
    "MarketSessionState",
    "MarketWindow",
    "TradingDayStatus",
]
