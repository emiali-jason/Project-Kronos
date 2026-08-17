"""DOMAIN-008 factual and normalized Market schedule contracts.

The service contains no exchange rules.  It only evaluates explicit schedules
provided by an authoritative source selected outside this component.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
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

MARKET_SCHEDULE_CONTRACT_ID = "KRONOS-MARKET-SCHEDULE-V1"
MARKET_SCHEDULE_CONTRACT_VERSION = "1"


class MarketAvailability(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PRE_OPEN = "PRE_OPEN"
    POST_CLOSE = "POST_CLOSE"
    UNAVAILABLE = "UNAVAILABLE"


class ScheduleFreshness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class ScheduleIntegrity(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class MarketSessionWindow:
    """One ordered authoritative open interval within a trading date."""

    identity: str
    order: int
    window_open: datetime
    window_close: datetime

    def __post_init__(self) -> None:
        if (
            not self.identity
            or type(self.order) is not int
            or self.order < 1
            or not _aware(self.window_open)
            or not _aware(self.window_close)
            or self.window_open >= self.window_close
            or self.window_open.date() != self.window_close.date()
        ):
            raise ValueError("MARKET_SESSION_WINDOW_INVALID")


@dataclass(frozen=True, slots=True)
class AuthoritativeMarketScheduleFacts:
    """Facts supplied by an approved exchange-calendar source, not by ticks."""

    market_identity: str
    exchange: str
    trading_date: date
    calendar_identity: str
    calendar_version: str
    session_identity: str
    session_type: str
    session_open: datetime | None
    session_close: datetime | None
    timezone: str
    market_availability: MarketAvailability
    as_of: datetime
    source_identity: str
    source_boundary: datetime
    freshness_status: ScheduleFreshness
    integrity_status: ScheduleIntegrity
    provenance: tuple[str, ...]
    windows: tuple[MarketSessionWindow, ...] = ()


@dataclass(frozen=True, slots=True)
class MarketSchedule:
    contract_identity: str
    contract_version: str
    identity: str
    market_identity: str
    exchange: str
    trading_date: date
    calendar_identity: str
    calendar_version: str
    session_identity: str
    session_type: str
    session_open: datetime | None
    session_close: datetime | None
    timezone: str
    market_availability: MarketAvailability
    as_of: datetime
    source_identity: str
    source_boundary: datetime
    freshness_status: ScheduleFreshness
    integrity_status: ScheduleIntegrity
    provenance: tuple[str, ...]
    windows: tuple[MarketSessionWindow, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.windows
            and self.session_open is not None
            and self.session_close is not None
        ):
            object.__setattr__(
                self,
                "windows",
                (
                    MarketSessionWindow(
                        f"{self.session_identity}:WINDOW:1",
                        1,
                        self.session_open,
                        self.session_close,
                    ),
                ),
            )
        available = self.market_availability is not MarketAvailability.UNAVAILABLE
        valid_windows = _valid_windows(self.windows, self.trading_date, self.timezone)
        singleton = len(self.windows) == 1
        if (
            self.contract_identity != MARKET_SCHEDULE_CONTRACT_ID
            or self.contract_version != MARKET_SCHEDULE_CONTRACT_VERSION
            or not self.identity
            or not self.market_identity
            or not self.exchange
            or type(self.trading_date) is not date
            or not self.calendar_identity
            or not self.calendar_version
            or not self.session_identity
            or not self.session_type
            or not self.timezone
            or type(self.market_availability) is not MarketAvailability
            or type(self.freshness_status) is not ScheduleFreshness
            or type(self.integrity_status) is not ScheduleIntegrity
            or not _aware(self.as_of)
            or not _aware(self.source_boundary)
            or not self.source_identity
            or not self.provenance
            or (self.session_open is not None and not _aware(self.session_open))
            or (self.session_close is not None and not _aware(self.session_close))
            or type(self.windows) is not tuple
            or (available and not valid_windows)
            or (
                available
                and singleton
                and (
                    self.session_open != self.windows[0].window_open
                    or self.session_close != self.windows[0].window_close
                )
            )
            or (
                available
                and not singleton
                and (self.session_open is not None or self.session_close is not None)
            )
            or available
            and (
                self.freshness_status is not ScheduleFreshness.CURRENT
                or self.integrity_status is not ScheduleIntegrity.VALID
            )
        ):
            raise ValueError("MARKET_SCHEDULE_INVALID")
        try:
            ZoneInfo(self.timezone)
        except Exception as error:
            raise ValueError("MARKET_SCHEDULE_INVALID") from error

    def window_at(self, moment: datetime) -> MarketSessionWindow | None:
        """Return the authoritative window containing ``moment``, excluding gaps."""

        if not _aware(moment):
            raise ValueError("MARKET_SCHEDULE_OBSERVATION_INVALID")
        return next(
            (
                item
                for item in self.windows
                if item.window_open <= moment < item.window_close
            ),
            None,
        )

    def trading_date_completed(self, observed_at: datetime) -> bool:
        """Return whether every authoritative window for the date has closed."""

        if not _aware(observed_at):
            raise ValueError("MARKET_SCHEDULE_OBSERVATION_INVALID")
        return bool(self.windows) and self.windows[-1].window_close <= observed_at


class _ScheduleAdapter:
    exchange: str

    def normalize(self, facts: AuthoritativeMarketScheduleFacts) -> MarketSchedule:
        if type(facts) is not AuthoritativeMarketScheduleFacts:
            raise ValueError("MARKET_SCHEDULE_SOURCE_INVALID")
        if facts.exchange != self.exchange:
            raise ValueError("MARKET_SCHEDULE_EXCHANGE_MISMATCH")
        source_windows = facts.windows
        if not source_windows and facts.session_open is not None and facts.session_close is not None:
            source_windows = (
                MarketSessionWindow(
                    f"{facts.session_identity}:WINDOW:1",
                    1,
                    facts.session_open,
                    facts.session_close,
                ),
            )
        windows_valid = _valid_windows(source_windows, facts.trading_date, facts.timezone)
        legacy_valid = (
            len(source_windows) != 1
            or (
                facts.session_open == source_windows[0].window_open
                and facts.session_close == source_windows[0].window_close
            )
        ) and (
            len(source_windows) == 1
            or (facts.session_open is None and facts.session_close is None)
        )
        valid = (
            facts.integrity_status is ScheduleIntegrity.VALID
            and facts.freshness_status is ScheduleFreshness.CURRENT
            and windows_valid
            and legacy_valid
        )
        availability = facts.market_availability if valid else MarketAvailability.UNAVAILABLE
        digest = sha256("|".join((
            facts.market_identity,
            facts.exchange,
            facts.trading_date.isoformat(),
            facts.calendar_identity,
            facts.calendar_version,
            facts.session_identity,
            facts.source_identity,
            facts.source_boundary.isoformat(),
            *(f"{item.order}:{item.window_open.isoformat()}:{item.window_close.isoformat()}" for item in source_windows),
        )).encode()).hexdigest()
        retained_windows = source_windows if valid else ()
        legacy_open = retained_windows[0].window_open if len(retained_windows) == 1 else None
        legacy_close = retained_windows[0].window_close if len(retained_windows) == 1 else None
        return MarketSchedule(
            MARKET_SCHEDULE_CONTRACT_ID,
            MARKET_SCHEDULE_CONTRACT_VERSION,
            f"MARKET-SCHEDULE-{digest}",
            facts.market_identity,
            facts.exchange,
            facts.trading_date,
            facts.calendar_identity,
            facts.calendar_version,
            facts.session_identity,
            facts.session_type,
            legacy_open,
            legacy_close,
            facts.timezone,
            availability,
            facts.as_of,
            facts.source_identity,
            facts.source_boundary,
            facts.freshness_status if valid else ScheduleFreshness.UNAVAILABLE,
            facts.integrity_status if valid else ScheduleIntegrity.INVALID,
            facts.provenance,
            retained_windows,
        )


class NseMarketScheduleAdapter(_ScheduleAdapter):
    exchange = "NSE"


class McxMarketScheduleAdapter(_ScheduleAdapter):
    exchange = "MCX"

def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _valid_windows(
    windows: object,
    trading_date: date,
    timezone: str,
) -> bool:
    try:
        governed_timezone = ZoneInfo(timezone)
    except Exception:
        return False
    if (
        type(windows) is not tuple
        or not windows
        or any(type(item) is not MarketSessionWindow for item in windows)
        or tuple(item.order for item in windows) != tuple(range(1, len(windows) + 1))
        or any(item.window_open.astimezone(governed_timezone).date() != trading_date for item in windows)
        or any(item.window_close.astimezone(governed_timezone).date() != trading_date for item in windows)
        or any(
            item.window_open.utcoffset()
            != item.window_open.astimezone(governed_timezone).utcoffset()
            for item in windows
        )
        or any(
            item.window_close.utcoffset()
            != item.window_close.astimezone(governed_timezone).utcoffset()
            for item in windows
        )
    ):
        return False
    return all(
        previous.window_close <= current.window_open
        for previous, current in zip(windows, windows[1:])
    )


__all__ = [
    "AuthoritativeMarketScheduleFacts",
    "MARKET_SCHEDULE_CONTRACT_ID",
    "MARKET_SCHEDULE_CONTRACT_VERSION",
    "MarketAvailability",
    "MarketSessionWindow",
    "MarketSchedule",
    "McxMarketScheduleAdapter",
    "NseMarketScheduleAdapter",
    "ScheduleFreshness",
    "ScheduleIntegrity",
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
