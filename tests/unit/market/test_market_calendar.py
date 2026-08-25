from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

import pytest

from kronos.market.calendar import (
    CalendarCoverageStatus,
    DEFAULT_MARKET_CALENDAR_ROOT,
    MARKET_CALENDAR_CONTRACT_ID,
    MarketCalendarPublisher,
)


IST = ZoneInfo("Asia/Kolkata")
OBSERVED = datetime(2026, 8, 17, 23, 59, tzinfo=IST)


def test_immutable_active_publications_have_exact_identity_coverage_and_sources() -> None:
    publisher = MarketCalendarPublisher()
    nse = publisher.publication("NSE")
    mcx = publisher.publication("MCX")

    assert MARKET_CALENDAR_CONTRACT_ID == "KRONOS-MARKET-CALENDAR-V1"
    assert (nse.calendar_identity, nse.calendar_version) == (
        "KRONOS-NSE-CAPITAL-MARKET-2022-2026", "2026.1.2"
    )
    assert (mcx.calendar_identity, mcx.calendar_version) == (
        "KRONOS-MCX-NON-AGRI-2026", "2026.1.1"
    )
    assert nse.coverage_start == date(2022, 9, 12)
    assert mcx.coverage_start == date(2026, 1, 1)
    assert nse.coverage_end == mcx.coverage_end == date(2026, 12, 31)
    assert {
        "NSE-MARKET-TIMINGS", "NSE-CMTR-50560", "NSE-CMTR-54023",
        "NSE-CMTR-54757", "NSE-CMTR-57285", "NSE-CMTR-59124", "NSE-CMTR-59722",
        "NSE-MSD-59999-SUPERSEDED", "NSE-CMTR-60338", "NSE-MSD-60340",
        "NSE-MSD-60677", "NSE-CMTR-61518", "NSE-MSD-61893",
        "NSE-CMTR-64628", "NSE-CMTR-64960", "NSE-CMTR-65587",
        "NSE-CMTR-65729", "NSE-CMTR-70319", "NSE-CMTR-71775",
        "NSE-CMTR-72260", "NSE-CMTR-72349",
    } == {item.artifact_identity for item in nse.official_sources}
    assert {item.artifact_identity for item in mcx.official_sources} == {
        "MCX-TRD-636-2025", "MCX-TRD-017-2026", "MCX-TRD-027-2026",
        "MCX-TRD-068-2026",
    }
    assert all(item.official_uri.startswith("https://") for item in (*nse.official_sources, *mcx.official_sources))


def test_non_trading_dates_are_explicit_and_never_published_as_sessions() -> None:
    publisher = MarketCalendarPublisher()
    assert publisher.publication("NSE").non_trading_dates[date(2026, 1, 26)] == "REPUBLIC_DAY"
    assert publisher.publication("NSE").non_trading_dates[date(2026, 1, 15)] == "MUNICIPAL_CORPORATION_ELECTION"
    assert publisher.publication("MCX").non_trading_dates[date(2026, 4, 3)] == "GOOD_FRIDAY"
    assert publisher.schedule("NSE", date(2026, 1, 26), observed_at=OBSERVED) is None
    assert publisher.schedule("MCX", date(2026, 4, 3), observed_at=OBSERVED) is None


def test_june_2023_bakri_id_amendment_is_active_and_prior_publication_is_immutable() -> None:
    publisher = MarketCalendarPublisher()
    nse = publisher.publication("NSE")
    old = DEFAULT_MARKET_CALENDAR_ROOT / "NSE-CAPITAL-MARKET-2022-2026.v1.json"

    assert sha256(old.read_bytes()).hexdigest() == (
        "2cd95c5770722d96656bc1fca578ce48a5eb365ccc91fe08df632ce677b1a589"
    )
    assert date(2023, 6, 28) in nse.trading_dates
    assert nse.non_trading_dates[date(2023, 6, 29)] == "BAKRI_ID"
    assert publisher.schedule("NSE", date(2023, 6, 29), observed_at=OBSERVED) is None
    assert {item.artifact_identity for item in nse.official_sources} >= {
        "NSE-CMTR-54757",
        "NSE-CMTR-57285",
    }
    week = publisher.trading_week("NSE", date(2023, 6, 26), observed_at=OBSERVED)
    assert tuple(item.trading_date for item in week.schedules) == (
        date(2023, 6, 26),
        date(2023, 6, 27),
        date(2023, 6, 28),
        date(2023, 6, 30),
    )


def test_cas_applicability_and_timing_successors_are_integrity_bound() -> None:
    publisher = MarketCalendarPublisher()
    applicability = publisher.subject_session_applicability_publications
    old_regime = (
        DEFAULT_MARKET_CALENDAR_ROOT
        / "NSE-CLOSING-AUCTION-SESSION-2026.v1.json"
    )

    assert len(applicability) == 1
    assert (
        applicability[0].publication_identity,
        applicability[0].publication_version,
    ) == ("KRONOS-NSE-CAS-SUBJECT-APPLICABILITY-2026", "2026.1.0")
    assert applicability[0].coverage_start == date(2026, 8, 3)
    assert applicability[0].coverage_end == date(2026, 12, 31)
    assert {item.artifact_identity for item in applicability[0].official_sources} == {
        "NSE-CAS-SECURITY-MASTER-CMTR-73845",
        "NSE-CAS-HISTORICAL-DATA-2026-08-03-TO-2026-08-25",
    }
    assert sha256(old_regime.read_bytes()).hexdigest() == (
        "c1f0c887ff61be64e4ad875bd50b1bb6682080815de2206917e661c65cddb08a"
    )


def test_cas_applicability_digest_tampering_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "calendar"
    shutil.copytree(DEFAULT_MARKET_CALENDAR_ROOT, root)
    target = root / "NSE-CAS-SUBJECT-APPLICABILITY-2026.v1.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["coverage_end"] = "2026-08-26"
    target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="MARKET_SESSION_APPLICABILITY_PUBLICATION_DIGEST_MISMATCH",
    ):
        MarketCalendarPublisher(root)


def test_regular_special_and_shortened_sessions_publish_authoritative_boundaries() -> None:
    publisher = MarketCalendarPublisher()
    regular = publisher.schedule("NSE", date(2026, 8, 14), observed_at=OBSERVED)
    nse_special = publisher.schedule("NSE", date(2026, 2, 1), observed_at=OBSERVED)
    mcx_special = publisher.schedule("MCX", date(2026, 2, 1), observed_at=OBSERVED)
    mcx_election = publisher.schedule("MCX", date(2026, 1, 15), observed_at=OBSERVED)
    mcx_short = publisher.schedule("MCX", date(2026, 3, 3), observed_at=OBSERVED)
    mcx_pre_dst = publisher.schedule("MCX", date(2026, 3, 6), observed_at=OBSERVED)
    mcx_dst = publisher.schedule("MCX", date(2026, 3, 9), observed_at=OBSERVED)

    assert regular is not None and (regular.session_open.hour, regular.session_open.minute) == (9, 15)
    assert regular.session_close.hour == 15 and regular.session_close.minute == 30
    assert nse_special is not None and nse_special.session_type == "SPECIAL_UNION_BUDGET"
    assert nse_special.session_open.date() == date(2026, 2, 1)
    assert mcx_special is not None and mcx_special.session_close.hour == 17
    assert mcx_election is not None and mcx_election.session_type == "EVENING_ONLY_MUNICIPAL_ELECTION"
    assert (mcx_election.session_open.hour, mcx_election.session_close.hour, mcx_election.session_close.minute) == (17, 23, 55)
    assert mcx_short is not None and mcx_short.session_type == "EVENING_ONLY_HOLI"
    assert (mcx_short.session_open.hour, mcx_short.session_close.hour, mcx_short.session_close.minute) == (17, 23, 55)
    assert mcx_pre_dst is not None and (mcx_pre_dst.session_close.hour, mcx_pre_dst.session_close.minute) == (23, 55)
    assert mcx_dst is not None and (mcx_dst.session_close.hour, mcx_dst.session_close.minute) == (23, 30)
    assert all(item.timezone == "Asia/Kolkata" for item in (regular, nse_special, mcx_special, mcx_election, mcx_short, mcx_pre_dst, mcx_dst))
    assert all("publication_sha256=" in "|".join(item.provenance) for item in (regular, nse_special, mcx_special, mcx_election, mcx_short, mcx_pre_dst, mcx_dst))


def test_17_august_and_future_normal_sessions_are_authoritatively_published() -> None:
    publisher = MarketCalendarPublisher()
    nse = publisher.schedule("NSE", date(2026, 8, 17), observed_at=OBSERVED)
    mcx = publisher.schedule("MCX", date(2026, 8, 17), observed_at=OBSERVED)
    future = publisher.schedule("NSE", date(2026, 12, 31), observed_at=OBSERVED)

    assert nse is not None and nse.session_type == "REGULAR"
    assert (nse.session_open.hour, nse.session_open.minute) == (9, 15)
    assert (nse.session_close.hour, nse.session_close.minute) == (15, 30)
    assert mcx is not None and mcx.session_type == "REGULAR"
    assert (mcx.session_open.hour, mcx.session_open.minute) == (9, 0)
    assert (mcx.session_close.hour, mcx.session_close.minute) == (23, 30)
    assert future is not None


def test_later_holidays_special_hours_and_pending_muhurat_fail_closed() -> None:
    publisher = MarketCalendarPublisher()
    assert publisher.schedule("NSE", date(2026, 9, 14), observed_at=OBSERVED) is None
    assert publisher.schedule("MCX", date(2026, 10, 2), observed_at=OBSERVED) is None
    evening = publisher.schedule("MCX", date(2026, 9, 14), observed_at=OBSERVED)
    assert evening is not None
    assert evening.session_type == "EVENING_ONLY_GANESH_CHATURTHI"
    assert (evening.session_open.hour, evening.session_close.hour, evening.session_close.minute) == (17, 23, 30)
    assert publisher.schedule("NSE", date(2026, 11, 8), observed_at=OBSERVED) is None
    assert publisher.schedule("MCX", date(2026, 11, 8), observed_at=OBSERVED) is None
    assert publisher.publication("NSE").non_trading_dates[date(2026, 11, 8)] == "SPECIAL_MUHURAT_TIMING_PENDING"


def test_governed_week_uses_only_explicit_published_trading_dates() -> None:
    publisher = MarketCalendarPublisher()
    week = publisher.trading_week("NSE", date(2026, 1, 26), observed_at=OBSERVED)
    assert tuple(item.trading_date for item in week.schedules) == (
        date(2026, 1, 27), date(2026, 1, 28), date(2026, 1, 29),
        date(2026, 1, 30), date(2026, 2, 1),
    )


def test_digest_tampering_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "calendar"
    shutil.copytree(DEFAULT_MARKET_CALENDAR_ROOT, root)
    target = root / "NSE-CAPITAL-MARKET-2022-2026.v3.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["calendar_version"] = "2026.1.1"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="MARKET_CALENDAR_PUBLICATION_DIGEST_MISMATCH"):
        MarketCalendarPublisher(root)


def test_dates_outside_versioned_coverage_fail_closed() -> None:
    publisher = MarketCalendarPublisher()
    with pytest.raises(ValueError, match="MARKET_CALENDAR_DATE_OUTSIDE_PUBLICATION"):
        publisher.schedule("NSE", date(2027, 1, 1), observed_at=OBSERVED)


def test_coverage_health_warns_before_expiry_and_reports_expired() -> None:
    publisher = MarketCalendarPublisher()
    current = publisher.coverage_health("NSE", observed_at=OBSERVED)
    expiring = publisher.coverage_health(
        "NSE", observed_at=datetime(2026, 12, 2, 12, tzinfo=IST)
    )
    expired = publisher.coverage_health(
        "MCX", observed_at=datetime(2027, 1, 1, 12, tzinfo=IST)
    )

    assert current.status is CalendarCoverageStatus.CURRENT
    assert current.valid_through == date(2026, 12, 31)
    assert expiring.status is CalendarCoverageStatus.EXPIRING
    assert expired.status is CalendarCoverageStatus.EXPIRED
    with pytest.raises(ValueError, match="MARKET_CALENDAR_DATE_OUTSIDE_PUBLICATION"):
        publisher.schedule("MCX", date(2027, 1, 1), observed_at=datetime(2027, 1, 1, 12, tzinfo=IST))


def test_versioned_publication_loader_accepts_explicit_multi_window_date(tmp_path: Path) -> None:
    root = tmp_path / "calendar"
    shutil.copytree(DEFAULT_MARKET_CALENDAR_ROOT, root)
    target = root / "NSE-CAPITAL-MARKET-2022-2026.v3.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["trading_dates"]["2026-02-01"] = {
        "session_type": "SPECIAL_MULTI_WINDOW_TEST",
        "windows": [
            {"open": "09:15:00", "close": "10:00:00"},
            {"open": "11:30:00", "close": "12:30:00"},
        ],
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["publications"]:
        if item["file"] == target.name:
            item["sha256"] = sha256(target.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    schedule = MarketCalendarPublisher(root).schedule(
        "NSE",
        date(2026, 2, 1),
        observed_at=OBSERVED,
    )

    assert schedule is not None
    assert len(schedule.windows) == 2
    assert schedule.session_open is None
    assert schedule.session_close is None
    assert schedule.windows[0].window_close.hour == 10
    assert schedule.windows[1].window_open.hour == 11
    assert schedule.windows[1].window_open.minute == 30
    assert any("window=2|" in item for item in schedule.provenance)
