from __future__ import annotations

from datetime import date, datetime, time, timedelta
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.market.calendar import (
    DEFAULT_MARKET_CALENDAR_ROOT,
    MarketCalendarPublisher,
    MarketSessionApplicabilityState,
)


IST = ZoneInfo("Asia/Kolkata")
OBSERVED = datetime(2026, 8, 18, 19, 10, tzinfo=IST)


def _source(subject: str) -> CurrentMarketCalendarScheduleSource:
    return CurrentMarketCalendarScheduleSource(
        MarketCalendarPublisher(),
        observed_at=OBSERVED,
        canonical_instrument_id=subject,
    )


def _modified_calendar_root(
    tmp_path: Path,
    mutate: object,
) -> Path:
    root = tmp_path / "calendar"
    shutil.copytree(DEFAULT_MARKET_CALENDAR_ROOT, root)
    target = root / "NSE-CAS-SUBJECT-APPLICABILITY-2026.v1.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    mutate(payload)  # type: ignore[operator]
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["subject_session_applicabilities"][0]["sha256"] = sha256(
        target.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return root


def test_pre_cas_replay_preserves_historical_nse_schedule() -> None:
    schedule = _source("RELIANCE").schedule_for("NSE", date(2026, 7, 31))

    assert schedule is not None
    assert schedule.windows[0].opens_at.time() == datetime.strptime("09:15", "%H:%M").time()
    assert schedule.windows[-1].closes_at.time() == datetime.strptime("15:30", "%H:%M").time()
    assert "CONTINUOUS_TRADING" not in schedule.session_id


def test_post_effective_reliance_has_distinct_continuous_and_cas_schedules() -> None:
    source = _source("RELIANCE")
    profile = source.session_profile_for("NSE", date(2026, 8, 18))

    assert profile is not None
    assert profile.continuous_trading.session_type == "CONTINUOUS_TRADING"
    assert profile.continuous_trading.session_open.time() == datetime.strptime("09:15", "%H:%M").time()
    assert profile.continuous_trading.session_close.time() == datetime.strptime("15:15", "%H:%M").time()
    assert profile.closing_auction_session is not None
    assert profile.closing_auction_session.session_type == "CLOSING_AUCTION_SESSION"
    assert profile.closing_auction_session.session_open.time() == datetime.strptime("15:15", "%H:%M").time()
    assert profile.closing_auction_session.session_close.time() == datetime.strptime("15:35", "%H:%M").time()
    assert profile.closing_auction_session.session_identity != profile.continuous_trading.session_identity
    assert "effective_date=2026-08-03" in profile.continuous_trading.provenance


def test_non_applicable_nse_subject_does_not_inherit_cas_schedule() -> None:
    source = _source("NIFTY")
    profile = source.session_profile_for("NSE", date(2026, 8, 18))

    assert profile is not None
    assert profile.closing_auction_session is None
    assert profile.continuous_trading.session_type == "REGULAR"
    assert profile.continuous_trading.session_close.time() == datetime.strptime("15:30", "%H:%M").time()


def test_explicit_non_cas_cash_subject_retains_regular_close(tmp_path: Path) -> None:
    def add_non_cas(payload: dict[str, object]) -> None:
        periods = payload["periods"]
        periods[0]["not_applicable_domain_subject_ids"] = ["TEST_NON_CAS"]

    publisher = MarketCalendarPublisher(
        _modified_calendar_root(tmp_path, add_non_cas)
    )
    profile = publisher.instrument_session_profile(
        "NSE",
        date(2026, 8, 18),
        canonical_instrument_id="TEST_NON_CAS",
        observed_at=OBSERVED,
    )

    assert profile is not None
    assert profile.closing_auction_session is None
    assert profile.continuous_trading.session_close.time() == time(15, 30)
    assert publisher.subject_session_applicability(
        "NSE",
        date(2026, 8, 18),
        domain_subject_identity="TEST_NON_CAS",
    ) is MarketSessionApplicabilityState.CAS_NOT_APPLICABLE


def test_unknown_applicability_fails_closed_and_current_publication_is_prospective() -> None:
    publisher = MarketCalendarPublisher()

    assert publisher.subject_session_applicability(
        "NSE",
        date(2026, 8, 18),
        domain_subject_identity="UNKNOWN_CASH_SUBJECT",
    ) is MarketSessionApplicabilityState.CAS_APPLICABILITY_UNAVAILABLE
    with pytest.raises(ValueError, match="MARKET_SESSION_APPLICABILITY_UNAVAILABLE"):
        publisher.instrument_session_profile(
            "NSE",
            date(2026, 8, 18),
            canonical_instrument_id="UNKNOWN_CASH_SUBJECT",
            observed_at=OBSERVED,
        )
    prospective = publisher.instrument_session_profile(
        "NSE",
        date(2026, 8, 26),
        canonical_instrument_id="RELIANCE",
        observed_at=OBSERVED,
    )
    assert prospective is not None
    assert prospective.continuous_trading.session_close.time() == time(15, 15)
    assert publisher.subject_session_applicability(
        "NSE",
        date(2027, 1, 1),
        domain_subject_identity="RELIANCE",
    ) is MarketSessionApplicabilityState.CAS_APPLICABILITY_UNAVAILABLE


def test_later_membership_change_does_not_rewrite_historical_applicability(
    tmp_path: Path,
) -> None:
    def change_membership(payload: dict[str, object]) -> None:
        original = payload["periods"][0]
        earlier = dict(original)
        earlier["effective_through"] = "2026-08-17"
        later = dict(original)
        later["effective_from"] = "2026-08-18"
        later["applicable_domain_subject_ids"] = [
            item
            for item in original["applicable_domain_subject_ids"]
            if item != "ADANIENT"
        ]
        later["not_applicable_domain_subject_ids"] = ["ADANIENT"]
        payload["periods"] = [earlier, later]

    publisher = MarketCalendarPublisher(
        _modified_calendar_root(tmp_path, change_membership)
    )

    historical = publisher.instrument_session_profile(
        "NSE",
        date(2026, 8, 17),
        canonical_instrument_id="ADANIENT",
        observed_at=OBSERVED,
    )
    changed = publisher.instrument_session_profile(
        "NSE",
        date(2026, 8, 18),
        canonical_instrument_id="ADANIENT",
        observed_at=OBSERVED,
    )

    assert historical is not None and changed is not None
    assert historical.continuous_trading.session_close.time() == time(15, 15)
    assert historical.closing_auction_session is not None
    assert changed.continuous_trading.session_close.time() == time(15, 30)
    assert changed.closing_auction_session is None


def test_reliance_continuous_boundaries_exclude_cas_for_all_intraday_frames() -> None:
    schedule = _source("RELIANCE").schedule_for("NSE", date(2026, 8, 18))

    assert schedule is not None
    expected_counts = {
        IntradayTimeframe.ONE_HOUR: 6,
        IntradayTimeframe.FIFTEEN_MINUTES: 24,
        IntradayTimeframe.FIVE_MINUTES: 72,
    }
    for timeframe, count in expected_counts.items():
        boundaries = expected_candle_boundaries(schedule, timeframe)
        assert len(boundaries) == count
        assert boundaries[-1].end == datetime(2026, 8, 18, 15, 15, tzinfo=IST)
        assert all(item.start < datetime(2026, 8, 18, 15, 15, tzinfo=IST) for item in boundaries)


def test_daily_close_semantics_explicitly_allow_distinct_values() -> None:
    profile = _source("RELIANCE").session_profile_for("NSE", date(2026, 8, 18))

    assert profile is not None
    assert profile.last_continuous_close_identity == "LAST_CONTINUOUS_INTRADAY_CLOSE"
    assert profile.official_daily_close_identity == "OFFICIAL_DAILY_CLOSE"
    assert profile.official_daily_close_may_differ is True


def test_effective_date_selection_is_deterministic_across_boundary() -> None:
    source = _source("RELIANCE")
    before = source.schedule_for("NSE", date(2026, 7, 31))
    after = source.schedule_for("NSE", date(2026, 8, 3))

    assert before is not None and after is not None
    assert before.windows[-1].closes_at.time() == datetime.strptime("15:30", "%H:%M").time()
    assert after.windows[-1].closes_at.time() == datetime.strptime("15:15", "%H:%M").time()
    assert after.windows[-1].closes_at - after.windows[0].opens_at == timedelta(hours=6)
