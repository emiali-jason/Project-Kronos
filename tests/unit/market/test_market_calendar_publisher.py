from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from zoneinfo import ZoneInfo

import pytest

from kronos.market.calendar import (
    MARKET_CALENDAR_SCHEMA,
    MarketCalendarPublisher,
    MarketCalendarRegistrySource,
    parse_market_calendar_publication,
    seal_market_calendar_document,
)
from kronos.market.schedule import MarketSessionService, MarketSessionState, TradingDayStatus


IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 8, 17)
SOURCE_BOUNDARY = datetime(2026, 8, 16, 18, 0, tzinfo=IST)
OBSERVED = datetime(2026, 8, 17, 10, 0, tzinfo=IST)


def _window(opens: str, closes: str) -> dict[str, str]:
    return {"opens_at": opens, "closes_at": closes}


def _entry(
    day: str = "2026-08-17",
    *,
    disposition: str = "TRADING",
    windows: list[dict[str, str]] | None = None,
    special: bool = False,
) -> dict[str, object]:
    return {
        "trading_date": day,
        "trading_disposition": disposition,
        "session_id": f"NSE-{day.replace('-', '')}",
        "session_type": "SPECIAL" if special else "REGULAR",
        "special_session": special,
        "windows": (
            [_window(f"{day}T09:15:00+05:30", f"{day}T15:30:00+05:30")]
            if windows is None and disposition == "TRADING"
            else windows or []
        ),
        "market_availability": "AVAILABLE",
    }


def _document(entries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_identity": MARKET_CALENDAR_SCHEMA,
        "market_identity": "NSE-CASH",
        "exchange": "NSE",
        "exchange_timezone": "Asia/Kolkata",
        "calendar_version": "2026.08.17",
        "source_identity": "NSE-OFFICIAL-PUBLICATION-20260816",
        "source_boundary": SOURCE_BOUNDARY.isoformat(),
        "valid_through": (SOURCE_BOUNDARY + timedelta(days=7)).isoformat(),
        "entries": entries,
    }


def _publisher(entries: list[dict[str, object]]) -> MarketCalendarPublisher:
    return MarketCalendarPublisher.from_bytes(
        seal_market_calendar_document(_document(entries)),
        observed_at=OBSERVED,
    )


def test_governed_document_is_deterministically_sealed_and_published() -> None:
    first = seal_market_calendar_document(_document([_entry()]))
    second = seal_market_calendar_document(_document([_entry()]))
    publication = parse_market_calendar_publication(first)
    schedule = MarketCalendarPublisher(publication, observed_at=OBSERVED).schedule_for("NSE", DAY)

    assert first == second
    assert publication.calendar_identity.startswith("MARKET-CALENDAR-")
    assert publication.integrity_identity.startswith("SHA256-")
    assert schedule is not None
    assert schedule.schema_identity == "KRONOS-MARKET-SCHEDULE-V1"
    assert schedule.status is TradingDayStatus.TRADING
    assert schedule.windows[0].opens_at == datetime(2026, 8, 17, 9, 15, tzinfo=IST)
    assert "NSE-OFFICIAL-PUBLICATION" in schedule.source_identity


def test_non_trading_and_special_multi_window_dates_are_explicit() -> None:
    special_windows = [
        _window("2026-08-18T09:00:00+05:30", "2026-08-18T11:00:00+05:30"),
        _window("2026-08-18T13:00:00+05:30", "2026-08-18T15:00:00+05:30"),
    ]
    publisher = _publisher([
        _entry(disposition="NON_TRADING", windows=[]),
        _entry("2026-08-18", windows=special_windows, special=True),
    ])

    closed = publisher.schedule_for("NSE", DAY)
    special = publisher.schedule_for("NSE", date(2026, 8, 18))
    assert closed is not None and closed.status is TradingDayStatus.NON_TRADING
    assert special is not None and special.special_session is True
    assert len(special.windows) == 2
    between = MarketSessionService(publisher).facts(
        exchange="NSE",
        trading_date=date(2026, 8, 18),
        observed_at=datetime(2026, 8, 18, 12, 0, tzinfo=IST),
    )
    assert between.state is MarketSessionState.BETWEEN_WINDOWS


def test_out_of_coverage_wrong_exchange_and_stale_publication_are_unavailable() -> None:
    publisher = _publisher([_entry()])
    stale = MarketCalendarPublisher(
        publisher.publication,
        observed_at=publisher.publication.valid_through + timedelta(seconds=1),
    )

    assert publisher.schedule_for("NSE", date(2026, 8, 19)) is None
    assert publisher.schedule_for("MCX", DAY) is None
    assert stale.schedule_for("NSE", DAY) is None
    fact = MarketSessionService(publisher).facts(
        exchange="NSE",
        trading_date=date(2026, 8, 19),
        observed_at=OBSERVED,
    )
    assert fact.state is MarketSessionState.UNAVAILABLE


def test_integrity_timezone_duplicate_and_overlap_fail_closed() -> None:
    encoded = seal_market_calendar_document(_document([_entry()]))
    tampered = json.loads(encoded)
    tampered["entries"][0]["session_id"] = "TAMPERED"
    with pytest.raises(ValueError, match="MARKET_CALENDAR_INTEGRITY_MISMATCH"):
        parse_market_calendar_publication(json.dumps(tampered).encode())

    wrong_zone = _document([_entry()])
    wrong_zone["exchange_timezone"] = "UTC"
    with pytest.raises(ValueError, match="MARKET_CALENDAR_PUBLICATION_INVALID"):
        parse_market_calendar_publication(seal_market_calendar_document(wrong_zone))

    with pytest.raises(ValueError, match="MARKET_CALENDAR_PUBLICATION_INVALID"):
        parse_market_calendar_publication(
            seal_market_calendar_document(_document([_entry(), _entry()]))
        )

    overlap = _entry(windows=[
        _window("2026-08-17T09:00:00+05:30", "2026-08-17T12:00:00+05:30"),
        _window("2026-08-17T11:00:00+05:30", "2026-08-17T13:00:00+05:30"),
    ])
    with pytest.raises(ValueError, match="MARKET_CALENDAR_PUBLICATION_INVALID"):
        parse_market_calendar_publication(
            seal_market_calendar_document(_document([overlap]))
        )


def test_registry_rejects_conflicting_publications() -> None:
    first = _publisher([_entry()])
    second = _publisher([_entry()])
    with pytest.raises(ValueError, match="MARKET_CALENDAR_PUBLICATION_CONFLICT"):
        MarketCalendarRegistrySource((first, second))
