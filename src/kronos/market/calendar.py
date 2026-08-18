"""Canonical DOMAIN-008 publications and explicit sealed-calendar adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum, StrEnum
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from kronos.market.derived_timeframes import GovernedTradingWeek
from kronos.market.schedule import (
    AuthoritativeMarketScheduleFacts,
    MarketAvailability,
    MarketDaySchedule,
    MarketSchedule,
    MarketScheduleSource,
    MarketSessionWindow,
    MarketWindow,
    McxMarketScheduleAdapter,
    NseMarketScheduleAdapter,
    ScheduleFreshness,
    ScheduleIntegrity,
    TradingDayStatus,
)


MARKET_CALENDAR_CONTRACT_ID = "KRONOS-MARKET-CALENDAR-V1"
MARKET_CALENDAR_CONTRACT_VERSION = "1"
MARKET_CALENDAR_PUBLICATION_SCHEMA = "KRONOS-MARKET-CALENDAR-PUBLICATION-V1"
MARKET_CALENDAR_MANIFEST_SCHEMA = "KRONOS-MARKET-CALENDAR-MANIFEST-V1"
MARKET_SESSION_REGIME_PUBLICATION_SCHEMA = (
    "KRONOS-MARKET-SESSION-REGIME-PUBLICATION-V1"
)
DEFAULT_MARKET_CALENDAR_ROOT = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "market_calendars"
    / MARKET_CALENDAR_CONTRACT_ID
)
DEFAULT_CALENDAR_EXPIRY_WARNING_DAYS = 30
MARKET_CALENDAR_SCHEMA = "KRONOS-MARKET-CALENDAR-V1"


class CalendarFactAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"


@dataclass(frozen=True, slots=True)
class MarketCalendarEntry:
    """One entry in the explicit sealed-calendar compatibility format."""

    trading_date: date
    trading_disposition: TradingDayStatus
    session_id: str
    session_type: str
    special_session: bool
    windows: tuple[MarketWindow, ...]
    market_availability: CalendarFactAvailability

    def __post_init__(self) -> None:
        trading = self.trading_disposition is TradingDayStatus.TRADING
        if (
            type(self.trading_date) is not date
            or type(self.trading_disposition) is not TradingDayStatus
            or not _text(self.session_id)
            or not _text(self.session_type)
            or type(self.special_session) is not bool
            or type(self.windows) is not tuple
            or any(type(item) is not MarketWindow for item in self.windows)
            or trading != bool(self.windows)
            or any(item.opens_at.date() != self.trading_date for item in self.windows)
            or any(
                current.opens_at < previous.closes_at
                for previous, current in zip(self.windows, self.windows[1:])
            )
            or type(self.market_availability) is not CalendarFactAvailability
        ):
            raise ValueError("MARKET_CALENDAR_ENTRY_INVALID")


class CalendarCoverageStatus(str, Enum):
    """Operational health of one immutable calendar publication."""

    CURRENT = "CURRENT"
    EXPIRING = "EXPIRING"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class CalendarCoverageHealth:
    exchange: str
    calendar_identity: str
    calendar_version: str
    valid_through: date
    observed_date: date
    status: CalendarCoverageStatus

    def __post_init__(self) -> None:
        if (
            self.exchange not in {"NSE", "MCX"}
            or not self.calendar_identity
            or not self.calendar_version
            or type(self.valid_through) is not date
            or type(self.observed_date) is not date
            or type(self.status) is not CalendarCoverageStatus
        ):
            raise ValueError("MARKET_CALENDAR_COVERAGE_HEALTH_INVALID")


@dataclass(frozen=True, slots=True)
class OfficialCalendarSource:
    artifact_identity: str
    title: str
    official_uri: str
    reference: str
    publication_date: date

    def __post_init__(self) -> None:
        if (
            not self.artifact_identity
            or not self.title
            or not self.official_uri.startswith("https://")
            or not self.reference
            or type(self.publication_date) is not date
        ):
            raise ValueError("MARKET_CALENDAR_SOURCE_INVALID")


@dataclass(frozen=True, slots=True)
class PublishedTradingWindow:
    """One ordered exchange-authoritative window expressed in local time."""

    order: int
    window_open: time
    window_close: time

    def __post_init__(self) -> None:
        if (
            type(self.order) is not int
            or self.order < 1
            or type(self.window_open) is not time
            or type(self.window_close) is not time
            or self.window_open >= self.window_close
        ):
            raise ValueError("MARKET_CALENDAR_WINDOW_INVALID")


@dataclass(frozen=True, slots=True)
class PublishedTradingSession:
    trading_date: date
    session_type: str
    session_open: time | None
    session_close: time | None
    windows: tuple[PublishedTradingWindow, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.trading_date) is not date
            or not self.session_type
            or type(self.windows) is not tuple
        ):
            raise ValueError("MARKET_CALENDAR_SESSION_INVALID")
        windows = self.windows
        if not windows and type(self.session_open) is time and type(self.session_close) is time:
            windows = (PublishedTradingWindow(1, self.session_open, self.session_close),)
            object.__setattr__(self, "windows", windows)
        if (
            not windows
            or any(type(item) is not PublishedTradingWindow for item in windows)
            or tuple(item.order for item in windows) != tuple(range(1, len(windows) + 1))
            or any(
                previous.window_close > current.window_open
                for previous, current in zip(windows, windows[1:])
            )
            or (
                len(windows) == 1
                and (
                    self.session_open != windows[0].window_open
                    or self.session_close != windows[0].window_close
                )
            )
            or (
                len(windows) > 1
                and (self.session_open is not None or self.session_close is not None)
            )
        ):
            raise ValueError("MARKET_CALENDAR_SESSION_INVALID")


@dataclass(frozen=True, slots=True)
class SealedMarketCalendarPublication:
    """One integrity-sealed calendar publication adapted for Intraday."""

    market_identity: str
    exchange: str
    exchange_timezone: str
    calendar_identity: str
    calendar_version: str
    source_identity: str
    source_boundary: datetime
    valid_through: datetime
    entries: tuple[MarketCalendarEntry, ...]
    integrity_identity: str
    schema_identity: str = MARKET_CALENDAR_SCHEMA

    def __post_init__(self) -> None:
        try:
            zone = ZoneInfo(self.exchange_timezone)
        except (ZoneInfoNotFoundError, TypeError) as error:
            raise ValueError("MARKET_CALENDAR_PUBLICATION_INVALID") from error
        dates = tuple(item.trading_date for item in self.entries)
        core = _publication_core(self)
        with_identity = {**core, "calendar_identity": self.calendar_identity}
        if (
            any(
                not _text(value)
                for value in (
                    self.market_identity,
                    self.exchange,
                    self.calendar_version,
                    self.source_identity,
                )
            )
            or not _aware(self.source_boundary)
            or not _aware(self.valid_through)
            or self.valid_through < self.source_boundary
            or not self.entries
            or any(type(item) is not MarketCalendarEntry for item in self.entries)
            or len(set(dates)) != len(dates)
            or tuple(sorted(dates)) != dates
            or any(window.opens_at.tzinfo != zone for item in self.entries for window in item.windows)
            or self.calendar_identity != _calendar_identity(core)
            or self.integrity_identity != _integrity_identity(with_identity)
            or self.schema_identity != MARKET_CALENDAR_SCHEMA
        ):
            raise ValueError("MARKET_CALENDAR_PUBLICATION_INVALID")


class SealedMarketCalendarPublisher(MarketScheduleSource):
    """Adapt one integrity-sealed publication to ``MarketScheduleSource``."""

    def __init__(
        self,
        publication: SealedMarketCalendarPublication,
        *,
        observed_at: datetime,
    ) -> None:
        if type(publication) is not SealedMarketCalendarPublication or not _aware(observed_at):
            raise ValueError("MARKET_CALENDAR_PUBLISHER_INVALID")
        self.publication = publication
        self.observed_at = observed_at
        self._entries = {item.trading_date: item for item in publication.entries}

    @classmethod
    def from_bytes(
        cls,
        encoded: bytes,
        *,
        observed_at: datetime,
    ) -> "SealedMarketCalendarPublisher":
        return cls(parse_market_calendar_publication(encoded), observed_at=observed_at)

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        observed_at: datetime,
    ) -> "SealedMarketCalendarPublisher":
        path = Path(path)
        try:
            encoded = path.read_bytes()
        except OSError as error:
            raise ValueError("MARKET_CALENDAR_PUBLICATION_UNAVAILABLE") from error
        return cls.from_bytes(encoded, observed_at=observed_at)

    def schedule_for(self, exchange: str, trading_date: date) -> MarketDaySchedule | None:
        if (
            exchange != self.publication.exchange
            or self.observed_at < self.publication.source_boundary
            or self.observed_at > self.publication.valid_through
        ):
            return None
        entry = self._entries.get(trading_date)
        if entry is None:
            return None
        return MarketDaySchedule(
            exchange=self.publication.exchange,
            trading_date=entry.trading_date,
            session_id=entry.session_id,
            timezone=self.publication.exchange_timezone,
            status=entry.trading_disposition,
            windows=entry.windows,
            source_identity=(
                f"{self.publication.source_identity}|"
                f"{self.publication.calendar_identity}"
            ),
            source_version=self.publication.calendar_version,
            special_session=entry.special_session,
        )

    def previous_trading_schedule(
        self, exchange: str, before_date: date
    ) -> MarketDaySchedule | None:
        """Return the preceding published trading session without calendar inference."""

        if type(before_date) is not date or exchange != self.publication.exchange:
            return None
        candidates = (
            entry.trading_date
            for entry in self.publication.entries
            if entry.trading_date < before_date
            and entry.trading_disposition is TradingDayStatus.TRADING
        )
        previous = max(candidates, default=None)
        return None if previous is None else self.schedule_for(exchange, previous)


class MarketCalendarRegistrySource(MarketScheduleSource):
    """Compose non-overlapping governed publications without inference."""

    def __init__(self, publishers: tuple[SealedMarketCalendarPublisher, ...]) -> None:
        if not publishers or any(
            type(item) is not SealedMarketCalendarPublisher for item in publishers
        ):
            raise ValueError("MARKET_CALENDAR_REGISTRY_INVALID")
        indexed: dict[tuple[str, date], SealedMarketCalendarPublisher] = {}
        for publisher in publishers:
            for entry in publisher.publication.entries:
                key = (publisher.publication.exchange, entry.trading_date)
                if key in indexed:
                    raise ValueError("MARKET_CALENDAR_PUBLICATION_CONFLICT")
                indexed[key] = publisher
        self._publishers = indexed

    def schedule_for(self, exchange: str, trading_date: date) -> MarketDaySchedule | None:
        publisher = self._publishers.get((exchange, trading_date))
        return None if publisher is None else publisher.schedule_for(exchange, trading_date)

    def previous_trading_schedule(
        self, exchange: str, before_date: date
    ) -> MarketDaySchedule | None:
        if type(before_date) is not date:
            return None
        candidates = (
            trading_date
            for candidate_exchange, trading_date in self._publishers
            if candidate_exchange == exchange and trading_date < before_date
        )
        for trading_date in sorted(candidates, reverse=True):
            schedule = self.schedule_for(exchange, trading_date)
            if schedule is not None and schedule.status is TradingDayStatus.TRADING:
                return schedule
        return None


def seal_market_calendar_document(document: dict[str, object]) -> bytes:
    """Seal a reviewable governed document with deterministic identities."""

    core = dict(document)
    if "calendar_identity" in core or "integrity_identity" in core:
        raise ValueError("MARKET_CALENDAR_DOCUMENT_ALREADY_SEALED")
    core["calendar_identity"] = _calendar_identity(core)
    core["integrity_identity"] = _integrity_identity(core)
    return json.dumps(core, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8")


def parse_market_calendar_publication(encoded: bytes) -> SealedMarketCalendarPublication:
    if type(encoded) is not bytes:
        raise ValueError("MARKET_CALENDAR_PUBLICATION_INVALID")
    try:
        document = json.loads(encoded)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("MARKET_CALENDAR_PUBLICATION_INVALID") from error
    required = {
        "schema_identity",
        "market_identity",
        "exchange",
        "exchange_timezone",
        "calendar_identity",
        "calendar_version",
        "source_identity",
        "source_boundary",
        "valid_through",
        "entries",
        "integrity_identity",
    }
    if not isinstance(document, dict) or set(document) != required:
        raise ValueError("MARKET_CALENDAR_PUBLICATION_INVALID")
    integrity = document["integrity_identity"]
    without_integrity = {key: value for key, value in document.items() if key != "integrity_identity"}
    without_identities = {
        key: value
        for key, value in without_integrity.items()
        if key != "calendar_identity"
    }
    if (
        document["schema_identity"] != MARKET_CALENDAR_SCHEMA
        or document["calendar_identity"] != _calendar_identity(without_identities)
        or integrity != _integrity_identity(without_integrity)
        or not isinstance(document["entries"], list)
    ):
        raise ValueError("MARKET_CALENDAR_INTEGRITY_MISMATCH")
    try:
        zone = ZoneInfo(document["exchange_timezone"])
        entries = tuple(_parse_entry(value, zone) for value in document["entries"])
        publication = SealedMarketCalendarPublication(
            market_identity=document["market_identity"],
            exchange=document["exchange"],
            exchange_timezone=document["exchange_timezone"],
            calendar_identity=document["calendar_identity"],
            calendar_version=document["calendar_version"],
            source_identity=document["source_identity"],
            source_boundary=datetime.fromisoformat(document["source_boundary"]),
            valid_through=datetime.fromisoformat(document["valid_through"]),
            entries=entries,
            integrity_identity=document["integrity_identity"],
        )
    except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("MARKET_CALENDAR_PUBLICATION_INVALID") from error
    return publication


def _parse_entry(value: object, zone: ZoneInfo) -> MarketCalendarEntry:
    required = {
        "trading_date",
        "trading_disposition",
        "session_id",
        "session_type",
        "special_session",
        "windows",
        "market_availability",
    }
    if not isinstance(value, dict) or set(value) != required or not isinstance(value["windows"], list):
        raise ValueError
    windows = tuple(_parse_window(item, zone) for item in value["windows"])
    return MarketCalendarEntry(
        trading_date=date.fromisoformat(value["trading_date"]),
        trading_disposition=TradingDayStatus(value["trading_disposition"]),
        session_id=value["session_id"],
        session_type=value["session_type"],
        special_session=value["special_session"],
        windows=windows,
        market_availability=CalendarFactAvailability(value["market_availability"]),
    )


def _parse_window(value: object, zone: ZoneInfo) -> MarketWindow:
    if not isinstance(value, dict) or set(value) != {"opens_at", "closes_at"}:
        raise ValueError
    opens_at = datetime.fromisoformat(value["opens_at"])
    closes_at = datetime.fromisoformat(value["closes_at"])
    if (
        not _aware(opens_at)
        or not _aware(closes_at)
        or opens_at.utcoffset() != zone.utcoffset(opens_at)
        or closes_at.utcoffset() != zone.utcoffset(closes_at)
    ):
        raise ValueError
    return MarketWindow(opens_at.astimezone(zone), closes_at.astimezone(zone))


def _calendar_identity(document: dict[str, object]) -> str:
    return f"MARKET-CALENDAR-{_digest(document)}"


def _publication_core(publication: SealedMarketCalendarPublication) -> dict[str, object]:
    return {
        "schema_identity": publication.schema_identity,
        "market_identity": publication.market_identity,
        "exchange": publication.exchange,
        "exchange_timezone": publication.exchange_timezone,
        "calendar_version": publication.calendar_version,
        "source_identity": publication.source_identity,
        "source_boundary": publication.source_boundary.isoformat(),
        "valid_through": publication.valid_through.isoformat(),
        "entries": [
            {
                "trading_date": entry.trading_date.isoformat(),
                "trading_disposition": entry.trading_disposition.value,
                "session_id": entry.session_id,
                "session_type": entry.session_type,
                "special_session": entry.special_session,
                "windows": [
                    {
                        "opens_at": window.opens_at.isoformat(),
                        "closes_at": window.closes_at.isoformat(),
                    }
                    for window in entry.windows
                ],
                "market_availability": entry.market_availability.value,
            }
            for entry in publication.entries
        ],
    }


def _integrity_identity(document: dict[str, object]) -> str:
    return f"SHA256-{_digest(document)}"


def _digest(document: object) -> str:
    canonical = json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MarketCalendarPublication:
    calendar_identity: str
    calendar_version: str
    market_identity: str
    exchange: str
    segment: str
    timezone: str
    coverage_start: date
    coverage_end: date
    source_boundary: datetime
    official_sources: tuple[OfficialCalendarSource, ...]
    trading_dates: Mapping[date, PublishedTradingSession]
    non_trading_dates: Mapping[date, str]
    publication_sha256: str

    def __post_init__(self) -> None:
        all_dates = set(self.trading_dates) | set(self.non_trading_dates)
        expected = {
            self.coverage_start + timedelta(days=offset)
            for offset in range((self.coverage_end - self.coverage_start).days + 1)
        }
        if (
            not self.calendar_identity
            or not self.calendar_version
            or not self.market_identity
            or self.exchange not in {"NSE", "MCX"}
            or not self.segment
            or self.timezone != "Asia/Kolkata"
            or self.coverage_start > self.coverage_end
            or not _aware(self.source_boundary)
            or not self.official_sources
            or len({item.artifact_identity for item in self.official_sources})
            != len(self.official_sources)
            or set(self.trading_dates) & set(self.non_trading_dates)
            or all_dates != expected
            or any(
                type(day) is not date
                or type(session) is not PublishedTradingSession
                or session.trading_date != day
                for day, session in self.trading_dates.items()
            )
            or any(type(day) is not date or not reason for day, reason in self.non_trading_dates.items())
            or len(self.publication_sha256) != 64
        ):
            raise ValueError("MARKET_CALENDAR_PUBLICATION_INVALID")
        try:
            ZoneInfo(self.timezone)
        except Exception as error:
            raise ValueError("MARKET_CALENDAR_PUBLICATION_INVALID") from error


@dataclass(frozen=True, slots=True)
class MarketSessionRegimePublication:
    """Effective-dated, instrument-applicable DOMAIN-008 session semantics."""

    regime_identity: str
    regime_version: str
    exchange: str
    segment: str
    timezone: str
    effective_date: date
    source_boundary: datetime
    official_source: OfficialCalendarSource
    applicable_canonical_instrument_ids: tuple[str, ...]
    continuous_open: time
    continuous_close: time
    closing_auction_open: time
    closing_auction_close: time
    publication_sha256: str

    def __post_init__(self) -> None:
        if (
            not _text(self.regime_identity)
            or not _text(self.regime_version)
            or self.exchange != "NSE"
            or not _text(self.segment)
            or self.timezone != "Asia/Kolkata"
            or type(self.effective_date) is not date
            or not _aware(self.source_boundary)
            or type(self.official_source) is not OfficialCalendarSource
            or not self.applicable_canonical_instrument_ids
            or any(not _text(item) for item in self.applicable_canonical_instrument_ids)
            or len(set(self.applicable_canonical_instrument_ids))
            != len(self.applicable_canonical_instrument_ids)
            or self.continuous_open >= self.continuous_close
            or self.continuous_close != self.closing_auction_open
            or self.closing_auction_open >= self.closing_auction_close
            or len(self.publication_sha256) != 64
        ):
            raise ValueError("MARKET_SESSION_REGIME_PUBLICATION_INVALID")


@dataclass(frozen=True, slots=True)
class MarketInstrumentSessionProfile:
    """Subject-applicable schedules without merging CAS into continuous trading."""

    canonical_instrument_id: str
    continuous_trading: MarketSchedule
    closing_auction_session: MarketSchedule | None
    last_continuous_close_identity: str = "LAST_CONTINUOUS_INTRADAY_CLOSE"
    official_daily_close_identity: str = "OFFICIAL_DAILY_CLOSE"
    official_daily_close_may_differ: bool = True

    def __post_init__(self) -> None:
        auction = self.closing_auction_session
        if (
            not _text(self.canonical_instrument_id)
            or type(self.continuous_trading) is not MarketSchedule
            or (auction is not None and type(auction) is not MarketSchedule)
            or (
                auction is not None
                and (
                    auction.exchange != self.continuous_trading.exchange
                    or auction.trading_date != self.continuous_trading.trading_date
                    or auction.session_identity
                    == self.continuous_trading.session_identity
                    or auction.windows[0].window_open
                    < self.continuous_trading.windows[-1].window_close
                )
            )
            or self.last_continuous_close_identity
            != "LAST_CONTINUOUS_INTRADAY_CLOSE"
            or self.official_daily_close_identity != "OFFICIAL_DAILY_CLOSE"
            or self.official_daily_close_may_differ is not True
        ):
            raise ValueError("MARKET_INSTRUMENT_SESSION_PROFILE_INVALID")


class MarketCalendarPublisher:
    """Publish exact versioned DOMAIN-008 schedules from checked-in facts."""

    def __init__(self, root: Path = DEFAULT_MARKET_CALENDAR_ROOT) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("MARKET_CALENDAR_ROOT_INVALID")
        self._root = root
        self._publications, self._session_regimes = self._load_manifest()

    @property
    def publications(self) -> tuple[MarketCalendarPublication, ...]:
        return tuple(self._publications[key] for key in sorted(self._publications))

    def publication(self, exchange: str) -> MarketCalendarPublication:
        try:
            return self._publications[exchange]
        except KeyError as error:
            raise ValueError("MARKET_CALENDAR_EXCHANGE_UNAVAILABLE") from error

    def coverage_health(
        self,
        exchange: str,
        *,
        observed_at: datetime,
        warning_days: int = DEFAULT_CALENDAR_EXPIRY_WARNING_DAYS,
    ) -> CalendarCoverageHealth:
        """Report calendar horizon health without extending authority implicitly."""

        if (
            not _aware(observed_at)
            or type(warning_days) is not int
            or warning_days < 1
        ):
            raise ValueError("MARKET_CALENDAR_COVERAGE_HEALTH_INVALID")
        publication = self.publication(exchange)
        observed_date = observed_at.astimezone(ZoneInfo(publication.timezone)).date()
        remaining = (publication.coverage_end - observed_date).days
        status = (
            CalendarCoverageStatus.EXPIRED
            if remaining < 0
            else CalendarCoverageStatus.EXPIRING
            if remaining <= warning_days
            else CalendarCoverageStatus.CURRENT
        )
        return CalendarCoverageHealth(
            exchange,
            publication.calendar_identity,
            publication.calendar_version,
            publication.coverage_end,
            observed_date,
            status,
        )

    def is_trading_date(self, exchange: str, trading_date: date) -> bool:
        publication = self.publication(exchange)
        self._require_covered(publication, trading_date)
        return trading_date in publication.trading_dates

    def schedule(
        self,
        exchange: str,
        trading_date: date,
        *,
        observed_at: datetime,
    ) -> MarketSchedule | None:
        publication = self.publication(exchange)
        self._require_covered(publication, trading_date)
        if not _aware(observed_at):
            raise ValueError("MARKET_CALENDAR_OBSERVATION_INVALID")
        session = publication.trading_dates.get(trading_date)
        if session is None:
            return None
        timezone = ZoneInfo(publication.timezone)
        windows = tuple(
            MarketSessionWindow(
                (
                    f"{publication.calendar_identity}:{publication.calendar_version}:"
                    f"{trading_date.isoformat()}:{session.session_type}:WINDOW:{item.order}"
                ),
                item.order,
                datetime.combine(trading_date, item.window_open, timezone),
                datetime.combine(trading_date, item.window_close, timezone),
            )
            for item in session.windows
        )
        opening = windows[0].window_open if len(windows) == 1 else None
        closing = windows[0].window_close if len(windows) == 1 else None
        facts = AuthoritativeMarketScheduleFacts(
            market_identity=publication.market_identity,
            exchange=publication.exchange,
            trading_date=trading_date,
            calendar_identity=publication.calendar_identity,
            calendar_version=publication.calendar_version,
            session_identity=(
                f"{publication.calendar_identity}:{publication.calendar_version}:"
                f"{trading_date.isoformat()}:{session.session_type}"
            ),
            session_type=session.session_type,
            session_open=opening,
            session_close=closing,
            timezone=publication.timezone,
            market_availability=MarketAvailability.CLOSED,
            as_of=observed_at,
            source_identity=MARKET_CALENDAR_CONTRACT_ID,
            source_boundary=publication.source_boundary,
            freshness_status=ScheduleFreshness.CURRENT,
            integrity_status=ScheduleIntegrity.VALID,
            provenance=(
                f"calendar={publication.calendar_identity}",
                f"version={publication.calendar_version}",
                f"publication_sha256={publication.publication_sha256}",
                *(f"official_source={item.artifact_identity}|{item.official_uri}" for item in publication.official_sources),
                *(f"window={item.order}|{item.window_open.isoformat()}|{item.window_close.isoformat()}" for item in windows),
            ),
            windows=windows,
        )
        adapter = NseMarketScheduleAdapter() if exchange == "NSE" else McxMarketScheduleAdapter()
        return adapter.normalize(facts)

    def instrument_session_profile(
        self,
        exchange: str,
        trading_date: date,
        *,
        canonical_instrument_id: str,
        observed_at: datetime,
    ) -> MarketInstrumentSessionProfile | None:
        """Publish effective-dated continuous and CAS schedules for one subject."""

        if not _text(canonical_instrument_id):
            raise ValueError("MARKET_SESSION_PROFILE_REQUEST_INVALID")
        base = self.schedule(exchange, trading_date, observed_at=observed_at)
        if base is None:
            return None
        regime = next(
            (
                item
                for item in self._session_regimes
                if item.exchange == exchange
                and trading_date >= item.effective_date
                and canonical_instrument_id
                in item.applicable_canonical_instrument_ids
            ),
            None,
        )
        if regime is None or not self._regular_window_accepts_regime(base, regime):
            return MarketInstrumentSessionProfile(canonical_instrument_id, base, None)
        continuous = self._regime_schedule(
            base=base,
            regime=regime,
            canonical_instrument_id=canonical_instrument_id,
            session_type="CONTINUOUS_TRADING",
            opening=regime.continuous_open,
            closing=regime.continuous_close,
            observed_at=observed_at,
        )
        auction = self._regime_schedule(
            base=base,
            regime=regime,
            canonical_instrument_id=canonical_instrument_id,
            session_type="CLOSING_AUCTION_SESSION",
            opening=regime.closing_auction_open,
            closing=regime.closing_auction_close,
            observed_at=observed_at,
        )
        return MarketInstrumentSessionProfile(
            canonical_instrument_id,
            continuous,
            auction,
        )

    @staticmethod
    def _regular_window_accepts_regime(
        schedule: MarketSchedule,
        regime: MarketSessionRegimePublication,
    ) -> bool:
        if len(schedule.windows) != 1:
            return False
        window = schedule.windows[0]
        return (
            window.window_open.timetz().replace(tzinfo=None)
            == regime.continuous_open
            and window.window_close.timetz().replace(tzinfo=None) >= regime.continuous_close
        )

    @staticmethod
    def _regime_schedule(
        *,
        base: MarketSchedule,
        regime: MarketSessionRegimePublication,
        canonical_instrument_id: str,
        session_type: str,
        opening: time,
        closing: time,
        observed_at: datetime,
    ) -> MarketSchedule:
        zone = ZoneInfo(regime.timezone)
        session_identity = (
            f"{regime.regime_identity}:{regime.regime_version}:"
            f"{base.trading_date.isoformat()}:{canonical_instrument_id}:{session_type}"
        )
        window = MarketSessionWindow(
            f"{session_identity}:WINDOW:1",
            1,
            datetime.combine(base.trading_date, opening, zone),
            datetime.combine(base.trading_date, closing, zone),
        )
        facts = AuthoritativeMarketScheduleFacts(
            market_identity=base.market_identity,
            exchange=base.exchange,
            trading_date=base.trading_date,
            calendar_identity=regime.regime_identity,
            calendar_version=regime.regime_version,
            session_identity=session_identity,
            session_type=session_type,
            session_open=window.window_open,
            session_close=window.window_close,
            timezone=regime.timezone,
            market_availability=MarketAvailability.CLOSED,
            as_of=observed_at,
            source_identity=MARKET_CALENDAR_CONTRACT_ID,
            source_boundary=regime.source_boundary,
            freshness_status=ScheduleFreshness.CURRENT,
            integrity_status=ScheduleIntegrity.VALID,
            provenance=(
                *base.provenance,
                f"session_regime={regime.regime_identity}",
                f"session_regime_version={regime.regime_version}",
                f"session_regime_sha256={regime.publication_sha256}",
                f"effective_date={regime.effective_date.isoformat()}",
                f"applicable_instrument={canonical_instrument_id}",
                (
                    f"official_source={regime.official_source.artifact_identity}|"
                    f"{regime.official_source.official_uri}"
                ),
                f"session_purpose={session_type}",
            ),
            windows=(window,),
        )
        return NseMarketScheduleAdapter().normalize(facts)

    def trading_week(
        self,
        exchange: str,
        member_date: date,
        *,
        observed_at: datetime,
    ) -> GovernedTradingWeek:
        start = member_date - timedelta(days=member_date.weekday())
        publication = self.publication(exchange)
        schedules = tuple(
            schedule
            for offset in range(7)
            if publication.coverage_start <= start + timedelta(days=offset) <= publication.coverage_end
            if (schedule := self.schedule(
                exchange,
                start + timedelta(days=offset),
                observed_at=observed_at,
            )) is not None
        )
        if not schedules:
            raise ValueError("MARKET_CALENDAR_TRADING_WEEK_UNAVAILABLE")
        return GovernedTradingWeek(
            f"{publication.calendar_identity}:{publication.calendar_version}:WEEK:{start.isoformat()}",
            schedules,
        )

    @staticmethod
    def _require_covered(publication: MarketCalendarPublication, day: date) -> None:
        if type(day) is not date or not publication.coverage_start <= day <= publication.coverage_end:
            raise ValueError("MARKET_CALENDAR_DATE_OUTSIDE_PUBLICATION")

    def _load_manifest(
        self,
    ) -> tuple[
        Mapping[str, MarketCalendarPublication],
        tuple[MarketSessionRegimePublication, ...],
    ]:
        try:
            manifest = json.loads((self._root / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("MARKET_CALENDAR_MANIFEST_INVALID") from error
        if (
            type(manifest) is not dict
            or set(manifest) != {"schema", "publications", "session_regimes"}
            or manifest["schema"] != MARKET_CALENDAR_MANIFEST_SCHEMA
            or type(manifest["publications"]) is not list
            or len(manifest["publications"]) != 2
            or type(manifest["session_regimes"]) is not list
        ):
            raise ValueError("MARKET_CALENDAR_MANIFEST_INVALID")
        publications: dict[str, MarketCalendarPublication] = {}
        for item in manifest["publications"]:
            if type(item) is not dict or set(item) != {"file", "sha256"}:
                raise ValueError("MARKET_CALENDAR_MANIFEST_INVALID")
            path = self._root / item["file"]
            try:
                raw = path.read_bytes()
            except OSError as error:
                raise ValueError("MARKET_CALENDAR_PUBLICATION_UNAVAILABLE") from error
            digest = sha256(raw).hexdigest()
            if digest != item["sha256"]:
                raise ValueError("MARKET_CALENDAR_PUBLICATION_DIGEST_MISMATCH")
            publication = _parse_publication(raw, digest)
            if publication.exchange in publications:
                raise ValueError("MARKET_CALENDAR_PUBLICATION_AMBIGUOUS")
            publications[publication.exchange] = publication
        if set(publications) != {"NSE", "MCX"}:
            raise ValueError("MARKET_CALENDAR_PUBLICATION_INCOMPLETE")
        regimes = tuple(
            self._load_session_regime(item) for item in manifest["session_regimes"]
        )
        if len({item.regime_identity for item in regimes}) != len(regimes):
            raise ValueError("MARKET_SESSION_REGIME_PUBLICATION_AMBIGUOUS")
        return MappingProxyType(publications), regimes

    def _load_session_regime(self, item: object) -> MarketSessionRegimePublication:
        if type(item) is not dict or set(item) != {"file", "sha256"}:
            raise ValueError("MARKET_CALENDAR_MANIFEST_INVALID")
        path = self._root / item["file"]
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise ValueError("MARKET_SESSION_REGIME_PUBLICATION_UNAVAILABLE") from error
        digest = sha256(raw).hexdigest()
        if digest != item["sha256"]:
            raise ValueError("MARKET_SESSION_REGIME_PUBLICATION_DIGEST_MISMATCH")
        return _parse_session_regime(raw, digest)


def _parse_publication(raw: bytes, digest: str) -> MarketCalendarPublication:
    try:
        payload = json.loads(raw)
        required = {
            "schema", "contract_identity", "contract_version", "calendar_identity",
            "calendar_version", "market_identity", "exchange", "segment", "timezone",
            "coverage_start", "coverage_end", "source_boundary", "official_sources",
            "trading_dates", "non_trading_dates",
        }
        if type(payload) is not dict or set(payload) != required:
            raise ValueError
        if (
            payload["schema"] != MARKET_CALENDAR_PUBLICATION_SCHEMA
            or payload["contract_identity"] != MARKET_CALENDAR_CONTRACT_ID
            or payload["contract_version"] != MARKET_CALENDAR_CONTRACT_VERSION
        ):
            raise ValueError
        sources = tuple(OfficialCalendarSource(
            artifact_identity=item["artifact_identity"],
            title=item["title"],
            official_uri=item["official_uri"],
            reference=item["reference"],
            publication_date=date.fromisoformat(item["publication_date"]),
        ) for item in payload["official_sources"])
        trading = {
            date.fromisoformat(day): _published_session(day, item)
            for day, item in payload["trading_dates"].items()
        }
        non_trading = {
            date.fromisoformat(day): reason
            for day, reason in payload["non_trading_dates"].items()
        }
        return MarketCalendarPublication(
            payload["calendar_identity"], payload["calendar_version"],
            payload["market_identity"], payload["exchange"], payload["segment"],
            payload["timezone"], date.fromisoformat(payload["coverage_start"]),
            date.fromisoformat(payload["coverage_end"]),
            datetime.fromisoformat(payload["source_boundary"]), sources,
            MappingProxyType(trading), MappingProxyType(non_trading), digest,
        )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError("MARKET_CALENDAR_PUBLICATION_INVALID") from error


def _parse_session_regime(
    raw: bytes,
    digest: str,
) -> MarketSessionRegimePublication:
    try:
        payload = json.loads(raw)
        required = {
            "schema",
            "regime_identity",
            "regime_version",
            "exchange",
            "segment",
            "timezone",
            "effective_date",
            "source_boundary",
            "official_source",
            "applicable_canonical_instrument_ids",
            "continuous_trading",
            "closing_auction_session",
            "daily_close_semantics",
        }
        if type(payload) is not dict or set(payload) != required:
            raise ValueError
        source = payload["official_source"]
        continuous = payload["continuous_trading"]
        auction = payload["closing_auction_session"]
        close_semantics = payload["daily_close_semantics"]
        if (
            payload["schema"] != MARKET_SESSION_REGIME_PUBLICATION_SCHEMA
            or type(source) is not dict
            or set(source)
            != {
                "artifact_identity",
                "title",
                "official_uri",
                "reference",
                "publication_date",
            }
            or type(payload["applicable_canonical_instrument_ids"]) is not list
            or type(continuous) is not dict
            or set(continuous) != {"session_type", "open", "close"}
            or continuous["session_type"] != "CONTINUOUS_TRADING"
            or type(auction) is not dict
            or set(auction) != {"session_type", "open", "close"}
            or auction["session_type"] != "CLOSING_AUCTION_SESSION"
            or close_semantics
            != {
                "last_continuous_close": "LAST_CONTINUOUS_INTRADAY_CLOSE",
                "official_daily_close": "OFFICIAL_DAILY_CLOSE",
                "equality_required": False,
            }
        ):
            raise ValueError
        return MarketSessionRegimePublication(
            regime_identity=payload["regime_identity"],
            regime_version=payload["regime_version"],
            exchange=payload["exchange"],
            segment=payload["segment"],
            timezone=payload["timezone"],
            effective_date=date.fromisoformat(payload["effective_date"]),
            source_boundary=datetime.fromisoformat(payload["source_boundary"]),
            official_source=OfficialCalendarSource(
                artifact_identity=source["artifact_identity"],
                title=source["title"],
                official_uri=source["official_uri"],
                reference=source["reference"],
                publication_date=date.fromisoformat(source["publication_date"]),
            ),
            applicable_canonical_instrument_ids=tuple(
                payload["applicable_canonical_instrument_ids"]
            ),
            continuous_open=time.fromisoformat(continuous["open"]),
            continuous_close=time.fromisoformat(continuous["close"]),
            closing_auction_open=time.fromisoformat(auction["open"]),
            closing_auction_close=time.fromisoformat(auction["close"]),
            publication_sha256=digest,
        )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError("MARKET_SESSION_REGIME_PUBLICATION_INVALID") from error


def _published_session(day: str, item: object) -> PublishedTradingSession:
    if type(item) is not dict or "session_type" not in item:
        raise ValueError("MARKET_CALENDAR_SESSION_INVALID")
    trading_date = date.fromisoformat(day)
    if set(item) == {"session_type", "open", "close"}:
        return PublishedTradingSession(
            trading_date,
            item["session_type"],
            time.fromisoformat(item["open"]),
            time.fromisoformat(item["close"]),
        )
    if set(item) != {"session_type", "windows"} or type(item["windows"]) is not list:
        raise ValueError("MARKET_CALENDAR_SESSION_INVALID")
    windows = tuple(
        PublishedTradingWindow(
            index,
            time.fromisoformat(window["open"]),
            time.fromisoformat(window["close"]),
        )
        for index, window in enumerate(item["windows"], start=1)
        if type(window) is dict and set(window) == {"open", "close"}
    )
    if len(windows) != len(item["windows"]):
        raise ValueError("MARKET_CALENDAR_SESSION_INVALID")
    return PublishedTradingSession(
        trading_date,
        item["session_type"],
        None,
        None,
        windows,
    )


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


__all__ = [
    "CalendarCoverageHealth",
    "CalendarCoverageStatus",
    "CalendarFactAvailability",
    "DEFAULT_CALENDAR_EXPIRY_WARNING_DAYS",
    "DEFAULT_MARKET_CALENDAR_ROOT",
    "MARKET_CALENDAR_CONTRACT_ID",
    "MARKET_CALENDAR_CONTRACT_VERSION",
    "MARKET_CALENDAR_SCHEMA",
    "MARKET_SESSION_REGIME_PUBLICATION_SCHEMA",
    "MarketCalendarEntry",
    "MarketCalendarPublication",
    "MarketCalendarPublisher",
    "MarketCalendarRegistrySource",
    "MarketInstrumentSessionProfile",
    "MarketSessionRegimePublication",
    "OfficialCalendarSource",
    "PublishedTradingSession",
    "PublishedTradingWindow",
    "SealedMarketCalendarPublication",
    "SealedMarketCalendarPublisher",
    "parse_market_calendar_publication",
    "seal_market_calendar_document",
]
