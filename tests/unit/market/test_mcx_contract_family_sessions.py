from __future__ import annotations

from datetime import date, datetime, timedelta
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
    MCX_CONTRACT_FAMILY_SESSION_CONTRACT_ID,
    MCX_CONTRACT_FAMILY_SESSION_CONTRACT_VERSION,
    MarketCalendarPublisher,
    McxContractSessionClassification,
    McxContractSessionUnavailable,
    McxContractSessionUnavailableReason,
    McxExpirySessionRule,
)


IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize(
    ("family", "expiry", "close"),
    (
        ("GOLDM", date(2026, 9, 4), (23, 30)),
        ("SILVERM", date(2026, 8, 31), (23, 30)),
        ("COPPER", date(2026, 8, 31), (17, 0)),
        ("NATURALGAS", date(2026, 8, 26), (23, 30)),
        ("CRUDEOIL", date(2026, 9, 21), (23, 30)),
    ),
)
def test_all_five_families_publish_exact_expiry_session_boundaries(
    family: str,
    expiry: date,
    close: tuple[int, int],
) -> None:
    publisher = MarketCalendarPublisher()
    before = publisher.mcx_contract_session_profile(
        contract_family=family,
        contract_expiry=expiry,
        trading_date=expiry,
        observed_at=datetime.combine(expiry, datetime.min.time(), IST).replace(
            hour=16,
            minute=59,
        ),
    )
    exact = publisher.mcx_contract_session_profile(
        contract_family=family,
        contract_expiry=expiry,
        trading_date=expiry,
        observed_at=datetime.combine(expiry, datetime.min.time(), IST).replace(
            hour=close[0],
            minute=close[1],
        ),
    )
    after = publisher.mcx_contract_session_profile(
        contract_family=family,
        contract_expiry=expiry,
        trading_date=expiry,
        observed_at=(
            datetime.combine(expiry, datetime.min.time(), IST).replace(
                hour=close[0],
                minute=close[1],
            )
            + timedelta(microseconds=1)
        ),
    )

    assert before.contract_family == family
    assert before.classification is (
        McxContractSessionClassification.EXPIRY_SESSION_BEFORE_CUTOFF
    )
    assert before.contract_eligible is True
    assert before.continuous_trading is not None
    assert before.continuous_trading.windows[-1].window_close.time() == (
        datetime.min.replace(hour=close[0], minute=close[1]).time()
    )
    assert exact.classification is (
        McxContractSessionClassification.EXPIRY_SESSION_BEFORE_CUTOFF
    )
    assert exact.contract_eligible is True
    assert after.classification is (
        McxContractSessionClassification.EXPIRY_SESSION_AFTER_CUTOFF
    )
    assert after.contract_eligible is False
    assert after.continuous_trading is not None


def test_publication_binds_sources_effective_periods_and_explicit_aliases() -> None:
    publication = MarketCalendarPublisher().mcx_contract_family_session_publication
    rules = {item.contract_family: item for item in publication.rules}

    assert (
        publication.publication_identity,
        publication.publication_version,
    ) == ("KRONOS-MCX-CONTRACT-FAMILY-EXPIRY-SESSIONS-2026", "2026.1.0")
    assert publication.coverage_start == date(2026, 1, 1)
    assert publication.coverage_end == date(2026, 12, 31)
    assert set(rules) == {"GOLDM", "SILVERM", "COPPER", "NATURALGAS", "CRUDEOIL"}
    assert rules["COPPER"].expiry_session_rule is McxExpirySessionRule.FIXED_LOCAL_CLOSE
    assert rules["COPPER"].expiry_local_close == datetime.strptime(
        "17:00", "%H:%M"
    ).time()
    assert all(
        item.expiry_session_rule is McxExpirySessionRule.NORMAL_MARKET_SESSION
        for family, item in rules.items()
        if family != "COPPER"
    )
    assert rules["NATURALGAS"].authorized_aliases == ("NATGAS",)
    assert rules["CRUDEOIL"].authorized_aliases == ("CRUDE",)
    assert {item.artifact_identity for item in publication.official_sources} == {
        "MCX-GOLDM-AUG-2026-ONWARDS",
        "MCX-SILVERM-AUG-2026-ONWARDS",
        "MCX-COPPER-MAY-2026-ONWARDS",
        "MCX-NATURALGAS-JAN-2026-ONWARDS",
        "MCX-CRUDEOIL-JAN-2026-ONWARDS",
    }
    assert all(item.official_uri.startswith("https://www.mcxindia.com/") for item in publication.official_sources)


def test_non_expiry_and_post_expiry_states_do_not_select_a_contract() -> None:
    publisher = MarketCalendarPublisher()
    pre = publisher.mcx_contract_session_profile(
        contract_family="COPPER",
        contract_expiry=date(2026, 8, 31),
        trading_date=date(2026, 8, 28),
        observed_at=datetime(2026, 8, 28, 18, 0, tzinfo=IST),
    )
    post = publisher.mcx_contract_session_profile(
        contract_family="COPPER",
        contract_expiry=date(2026, 8, 31),
        trading_date=date(2026, 9, 1),
        observed_at=datetime(2026, 9, 1, 9, 0, tzinfo=IST),
    )

    assert pre.classification is McxContractSessionClassification.PRE_EXPIRY_SESSION
    assert pre.contract_eligible is True
    assert pre.continuous_trading is not None
    assert pre.continuous_trading.windows[-1].window_close.time() == (
        datetime.strptime("23:30", "%H:%M").time()
    )
    assert post.classification is McxContractSessionClassification.POST_EXPIRY
    assert post.contract_eligible is False
    assert post.continuous_trading is None
    assert post.expiry_eligibility_boundary == datetime(
        2026, 8, 31, 17, 0, tzinfo=IST
    )


def test_explicit_intraday_aliases_resolve_without_fuzzy_matching() -> None:
    publisher = MarketCalendarPublisher()
    natgas = publisher.mcx_contract_session_profile(
        contract_family="NATGAS",
        contract_expiry=date(2026, 8, 26),
        trading_date=date(2026, 8, 26),
        observed_at=datetime(2026, 8, 26, 18, 0, tzinfo=IST),
    )
    crude = publisher.mcx_contract_session_profile(
        contract_family="CRUDE",
        contract_expiry=date(2026, 9, 21),
        trading_date=date(2026, 9, 21),
        observed_at=datetime(2026, 9, 21, 18, 0, tzinfo=IST),
    )

    assert (natgas.requested_contract_family, natgas.contract_family) == (
        "NATGAS",
        "NATURALGAS",
    )
    assert (crude.requested_contract_family, crude.contract_family) == (
        "CRUDE",
        "CRUDEOIL",
    )
    with pytest.raises(McxContractSessionUnavailable) as error:
        publisher.mcx_contract_session_profile(
            contract_family="NATURAL-GAS",
            contract_expiry=date(2026, 8, 26),
            trading_date=date(2026, 8, 26),
            observed_at=datetime(2026, 8, 26, 18, 0, tzinfo=IST),
        )
    assert error.value.reason is McxContractSessionUnavailableReason.UNKNOWN_FAMILY


def test_unknown_uncovered_and_unqualified_effective_periods_fail_closed() -> None:
    publisher = MarketCalendarPublisher()
    with pytest.raises(McxContractSessionUnavailable) as unknown:
        publisher.mcx_contract_session_profile(
            contract_family="GOLD",
            contract_expiry=date(2026, 9, 4),
            trading_date=date(2026, 9, 4),
            observed_at=datetime(2026, 9, 4, 17, 0, tzinfo=IST),
        )
    assert unknown.value.reason is McxContractSessionUnavailableReason.UNKNOWN_FAMILY

    with pytest.raises(McxContractSessionUnavailable) as uncovered:
        publisher.mcx_contract_session_profile(
            contract_family="NATURALGAS",
            contract_expiry=date(2027, 1, 27),
            trading_date=date(2027, 1, 27),
            observed_at=datetime(2027, 1, 27, 17, 0, tzinfo=IST),
        )
    assert uncovered.value.reason is (
        McxContractSessionUnavailableReason.DATE_OUTSIDE_PUBLICATION
    )

    with pytest.raises(McxContractSessionUnavailable) as historical_gap:
        publisher.mcx_contract_session_profile(
            contract_family="GOLDM",
            contract_expiry=date(2026, 7, 3),
            trading_date=date(2026, 7, 3),
            observed_at=datetime(2026, 7, 3, 17, 0, tzinfo=IST),
        )
    assert historical_gap.value.reason is (
        McxContractSessionUnavailableReason.EXPIRY_OUTSIDE_EFFECTIVE_PERIOD
    )

    with pytest.raises(McxContractSessionUnavailable) as future_gap:
        publisher.mcx_contract_session_profile(
            contract_family="SILVERM",
            contract_expiry=date(2026, 12, 31),
            trading_date=date(2026, 12, 31),
            observed_at=datetime(2026, 12, 31, 17, 0, tzinfo=IST),
        )
    assert future_gap.value.reason is (
        McxContractSessionUnavailableReason.EXPIRY_OUTSIDE_EFFECTIVE_PERIOD
    )


def test_historical_effective_interval_start_replays_from_official_2026_spec() -> None:
    profile = MarketCalendarPublisher().mcx_contract_session_profile(
        contract_family="NATURALGAS",
        contract_expiry=date(2026, 1, 27),
        trading_date=date(2026, 1, 27),
        observed_at=datetime(2026, 1, 27, 23, 55, tzinfo=IST),
    )

    assert profile.classification is (
        McxContractSessionClassification.EXPIRY_SESSION_BEFORE_CUTOFF
    )
    assert profile.contract_eligible is True
    assert profile.expiry_eligibility_boundary == datetime(
        2026, 1, 27, 23, 55, tzinfo=IST
    )


def test_missing_and_integrity_invalid_publications_fail_closed(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"
    shutil.copytree(DEFAULT_MARKET_CALENDAR_ROOT, missing_root)
    target = missing_root / "MCX-CONTRACT-FAMILY-EXPIRY-SESSIONS-2026.v1.json"
    target.unlink()
    with pytest.raises(McxContractSessionUnavailable) as missing:
        MarketCalendarPublisher(missing_root)
    assert missing.value.reason is (
        McxContractSessionUnavailableReason.PUBLICATION_UNAVAILABLE
    )

    invalid_root = tmp_path / "invalid"
    shutil.copytree(DEFAULT_MARKET_CALENDAR_ROOT, invalid_root)
    target = invalid_root / "MCX-CONTRACT-FAMILY-EXPIRY-SESSIONS-2026.v1.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["publication_version"] = "2026.1.1"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(McxContractSessionUnavailable) as invalid:
        MarketCalendarPublisher(invalid_root)
    assert invalid.value.reason is (
        McxContractSessionUnavailableReason.PUBLICATION_DIGEST_MISMATCH
    )


def test_historical_replay_is_deterministic_and_completed_candles_stop_at_cutoff() -> None:
    publisher = MarketCalendarPublisher()
    request = dict(
        contract_family="COPPER",
        contract_expiry=date(2026, 8, 31),
        trading_date=date(2026, 8, 31),
        observed_at=datetime(2026, 8, 31, 17, 0, tzinfo=IST),
    )
    first = publisher.mcx_contract_session_profile(**request)
    replay = MarketCalendarPublisher().mcx_contract_session_profile(**request)

    assert first == replay
    assert first.contract_identity == MCX_CONTRACT_FAMILY_SESSION_CONTRACT_ID
    assert first.contract_version == MCX_CONTRACT_FAMILY_SESSION_CONTRACT_VERSION
    assert first.continuous_trading is not None
    adapted = CurrentMarketCalendarScheduleSource._adapt(first.continuous_trading)
    hourly = expected_candle_boundaries(adapted, IntradayTimeframe.ONE_HOUR)
    five_minute = expected_candle_boundaries(
        adapted,
        IntradayTimeframe.FIVE_MINUTES,
    )
    assert hourly[-1].end == datetime(2026, 8, 31, 17, 0, tzinfo=IST)
    assert five_minute[-1].end == datetime(2026, 8, 31, 17, 0, tzinfo=IST)
    assert all(item.end <= datetime(2026, 8, 31, 17, 0, tzinfo=IST) for item in hourly)


def test_nse_cas_and_generic_mcx_schedules_remain_isolated() -> None:
    publisher = MarketCalendarPublisher()
    nse_equity = publisher.instrument_session_profile(
        "NSE",
        date(2026, 8, 18),
        canonical_instrument_id="RELIANCE",
        observed_at=datetime(2026, 8, 18, 19, 0, tzinfo=IST),
    )
    nifty = publisher.instrument_session_profile(
        "NSE",
        date(2026, 8, 18),
        canonical_instrument_id="NIFTY",
        observed_at=datetime(2026, 8, 18, 19, 0, tzinfo=IST),
    )
    generic_mcx = publisher.schedule(
        "MCX",
        date(2026, 8, 31),
        observed_at=datetime(2026, 8, 31, 18, 0, tzinfo=IST),
    )

    assert nse_equity is not None and nifty is not None and generic_mcx is not None
    assert nse_equity.continuous_trading.windows[-1].window_close.time() == (
        datetime.strptime("15:15", "%H:%M").time()
    )
    assert nifty.continuous_trading.windows[-1].window_close.time() == (
        datetime.strptime("15:30", "%H:%M").time()
    )
    assert generic_mcx.windows[-1].window_close.time() == datetime.strptime(
        "23:30", "%H:%M"
    ).time()
