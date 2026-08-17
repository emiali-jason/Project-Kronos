"""DOMAIN-008 governed static Market Calendar publication and publisher."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from kronos.market.schedule import (
    MarketDaySchedule,
    MarketScheduleSource,
    MarketWindow,
    TradingDayStatus,
)


MARKET_CALENDAR_SCHEMA = "KRONOS-MARKET-CALENDAR-V1"


class CalendarFactAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"


@dataclass(frozen=True, slots=True)
class MarketCalendarEntry:
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


@dataclass(frozen=True, slots=True)
class MarketCalendarPublication:
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


class MarketCalendarPublisher(MarketScheduleSource):
    """Publish normalized schedules from one integrity-checked calendar."""

    def __init__(self, publication: MarketCalendarPublication, *, observed_at: datetime) -> None:
        if type(publication) is not MarketCalendarPublication or not _aware(observed_at):
            raise ValueError("MARKET_CALENDAR_PUBLISHER_INVALID")
        self.publication = publication
        self.observed_at = observed_at
        self._entries = {item.trading_date: item for item in publication.entries}

    @classmethod
    def from_bytes(cls, encoded: bytes, *, observed_at: datetime) -> "MarketCalendarPublisher":
        return cls(parse_market_calendar_publication(encoded), observed_at=observed_at)

    @classmethod
    def from_path(cls, path: Path, *, observed_at: datetime) -> "MarketCalendarPublisher":
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


class MarketCalendarRegistrySource(MarketScheduleSource):
    """Compose non-overlapping governed publications without inference."""

    def __init__(self, publishers: tuple[MarketCalendarPublisher, ...]) -> None:
        if not publishers or any(type(item) is not MarketCalendarPublisher for item in publishers):
            raise ValueError("MARKET_CALENDAR_REGISTRY_INVALID")
        indexed: dict[tuple[str, date], MarketCalendarPublisher] = {}
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


def seal_market_calendar_document(document: dict[str, object]) -> bytes:
    """Seal a reviewable governed document with deterministic identities."""

    core = dict(document)
    if "calendar_identity" in core or "integrity_identity" in core:
        raise ValueError("MARKET_CALENDAR_DOCUMENT_ALREADY_SEALED")
    core["calendar_identity"] = _calendar_identity(core)
    core["integrity_identity"] = _integrity_identity(core)
    return json.dumps(core, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8")


def parse_market_calendar_publication(encoded: bytes) -> MarketCalendarPublication:
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
        publication = MarketCalendarPublication(
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


def _publication_core(publication: MarketCalendarPublication) -> dict[str, object]:
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


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


__all__ = [
    "CalendarFactAvailability",
    "MARKET_CALENDAR_SCHEMA",
    "MarketCalendarEntry",
    "MarketCalendarPublication",
    "MarketCalendarPublisher",
    "MarketCalendarRegistrySource",
    "parse_market_calendar_publication",
    "seal_market_calendar_document",
]
