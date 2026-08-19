from dataclasses import asdict, fields
from datetime import date, datetime, timedelta
import json
from zoneinfo import ZoneInfo

import pytest

from kronos.application.swing_mtf_facts import _completed_daily, _completed_weekly
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.v1.reference_facts import (
    CPR_CALCULATION_POLICY_IDENTITY,
    CPR_CALCULATION_POLICY_VERSION,
    REFERENCE_MACHINE_FACT_AUTHORITY,
    REFERENCE_MACHINE_FACT_SCHEMA,
    REFERENCE_POLICY_IDENTITY,
    REFERENCE_POLICY_VERSION,
    REFERENCE_SOURCE,
    SwingReferenceAvailability,
    SwingReferenceChartTimeframe,
    SwingReferencePeriodType,
    SwingReferenceUnavailableReason,
    build_reference_machine_facts,
    calculate_cpr,
    reference_machine_fact_from_dict,
    reference_period_type,
)


IST = ZoneInfo("Asia/Kolkata")
RUN_ID = "SWING-RUN-ABCDEF0123456789ABCDEF0123456789"


def _candle(day: date, sequence: int) -> HistoricalCandle:
    open_price = 100.0 + sequence
    return HistoricalCandle(
        datetime(day.year, day.month, day.day, tzinfo=IST),
        open_price,
        open_price + 4.0,
        open_price - 3.0,
        open_price + 2.0,
        1_000 + sequence,
    )


def _histories(
    exchange: str, observed_at: datetime
) -> tuple[
    MarketCalendarPublisher,
    tuple[HistoricalCandle, ...],
    tuple[tuple[object, str], ...],
]:
    publisher = MarketCalendarPublisher()
    publication = publisher.publication(exchange)
    trading_dates = tuple(
        day
        for day in sorted(publication.trading_dates)
        if day <= observed_at.date()
    )
    daily = tuple(_candle(day, index) for index, day in enumerate(trading_dates))
    completed = _completed_daily(exchange, daily, publisher, observed_at)
    weekly = _completed_weekly(
        exchange,
        "GOLDM" if exchange == "MCX" else "RELIANCE",
        completed,
        publisher,
        observed_at,
    )
    return publisher, tuple(item[0] for item in completed), weekly


def _facts(
    *,
    exchange: str = "NSE",
    observed_at: datetime = datetime(2026, 8, 14, 23, 59, tzinfo=IST),
    daily_transform=lambda value: value,
):  # type: ignore[no-untyped-def]
    publisher, daily, weekly = _histories(exchange, observed_at)
    latest_week, week_identity = weekly[-1]
    return build_reference_machine_facts(
        run_identity=RUN_ID,
        canonical_instrument="GOLDM" if exchange == "MCX" else "RELIANCE",
        exchange=exchange,
        completed_daily=tuple(daily_transform(daily)),
        completed_week=latest_week,
        completed_week_identity=week_identity,
        calendar_publisher=publisher,
        observed_at=observed_at,
        analysis_boundary=observed_at - timedelta(minutes=1),
        provider_source_identity=REFERENCE_SOURCE,
    )


@pytest.mark.parametrize(
    ("timeframe", "period"),
    (
        (SwingReferenceChartTimeframe.WEEKLY, SwingReferencePeriodType.PREVIOUS_MONTH),
        (SwingReferenceChartTimeframe.DAILY, SwingReferencePeriodType.PREVIOUS_MONTH),
        (SwingReferenceChartTimeframe.FOUR_HOUR, SwingReferencePeriodType.PREVIOUS_MONTH),
        (SwingReferenceChartTimeframe.ONE_HOUR, SwingReferencePeriodType.PREVIOUS_WEEK),
    ),
)
def test_auto_kgs_routes_exact_production_pine_reference_period(
    timeframe: SwingReferenceChartTimeframe,
    period: SwingReferencePeriodType,
) -> None:
    assert reference_period_type(timeframe) is period


def test_cpr_matches_production_pine_formula_and_normalizes_bc_tc() -> None:
    cp, bc, tc = calculate_cpr(120.0, 80.0, 90.0)

    assert cp == pytest.approx(96.66666666666667)
    assert bc == pytest.approx(93.33333333333334)
    assert tc == 100.0
    assert bc <= tc


def test_reference_facts_bind_completed_week_and_previous_month_ohlc() -> None:
    observed_at = datetime(2026, 8, 14, 23, 59, tzinfo=IST)
    publisher, daily, weekly = _histories("NSE", observed_at)
    latest_week, week_identity = weekly[-1]
    facts = _facts(observed_at=observed_at)
    by_timeframe = {item.chart_timeframe: item for item in facts}
    one_hour = by_timeframe[SwingReferenceChartTimeframe.ONE_HOUR]
    daily_fact = by_timeframe[SwingReferenceChartTimeframe.DAILY]
    july = tuple(
        item
        for item in daily
        if item.timestamp.year == 2026 and item.timestamp.month == 7
    )

    assert one_hour.reference_period_identity == week_identity
    assert one_hour.reference_period_start == latest_week.derived_start
    assert one_hour.reference_period_end == latest_week.derived_end
    assert (
        one_hour.reference_high,
        one_hour.reference_low,
        one_hour.reference_close,
    ) == (latest_week.high, latest_week.low, latest_week.close)
    assert daily_fact.reference_period_identity.endswith("MONTH:2026-07")
    assert daily_fact.reference_open == july[0].open
    assert daily_fact.reference_high == max(item.high for item in july)
    assert daily_fact.reference_low == min(item.low for item in july)
    assert daily_fact.reference_close == july[-1].close
    assert daily_fact.reference_period_start.date() == july[0].timestamp.date()
    assert daily_fact.reference_period_end.date() == july[-1].timestamp.date()
    assert daily_fact.calendar_identity == publisher.publication("NSE").calendar_identity


def test_open_current_month_never_substitutes_for_previous_completed_month() -> None:
    monthly = _facts()[0]

    assert monthly.reference_period_identity.endswith("MONTH:2026-07")
    assert monthly.reference_period_end.month == 7
    assert monthly.source_market_data_boundary.month == 7


def test_previous_month_respects_holiday_weekend_special_and_shortened_sessions() -> None:
    nse = _facts(observed_at=datetime(2026, 3, 2, 23, 59, tzinfo=IST))[0]
    mcx = _facts(
        exchange="MCX",
        observed_at=datetime(2026, 2, 2, 23, 59, tzinfo=IST),
    )[0]

    assert nse.reference_period_identity.endswith("MONTH:2026-02")
    assert any("2026-02-01" in item for item in nse.period_provenance)
    assert nse.reference_period_start.weekday() == 6
    assert mcx.reference_period_identity.endswith("MONTH:2026-01")
    assert any("2026-01-01" in item for item in mcx.period_provenance)
    assert any("17:00:00" in item for item in mcx.period_provenance)
    assert len(nse.period_provenance) > 20
    assert len(mcx.period_provenance) > 20


def test_previous_month_uses_domain_008_instrument_official_close() -> None:
    fact = _facts(
        observed_at=datetime(2026, 9, 2, 23, 59, tzinfo=IST)
    )[0]

    assert fact.reference_period_identity.endswith("MONTH:2026-08")
    assert (fact.reference_period_end.hour, fact.reference_period_end.minute) == (
        15,
        35,
    )
    assert any("CLOSING-AUCTION" in item for item in fact.period_provenance)


def test_missing_nse_constituent_fails_closed() -> None:
    def remove_one_july_constituent(value):  # type: ignore[no-untyped-def]
        july = next(
            item
            for item in value
            if item.timestamp.year == 2026 and item.timestamp.month == 7
        )
        return tuple(item for item in value if item is not july)

    facts = _facts(daily_transform=remove_one_july_constituent)

    assert all(
        item.availability is SwingReferenceAvailability.UNAVAILABLE
        and item.unavailable_reason
        is SwingReferenceUnavailableReason.MISSING_REFERENCE_CONSTITUENTS
        for item in facts[:3]
    )
    assert facts[3].availability is SwingReferenceAvailability.AVAILABLE


def test_mcx_insufficient_current_contract_history_is_explicitly_unavailable() -> None:
    facts = _facts(exchange="MCX", daily_transform=lambda value: value[-20:])

    assert all(
        item.availability is SwingReferenceAvailability.UNAVAILABLE
        and item.unavailable_reason
        is SwingReferenceUnavailableReason.INSUFFICIENT_CURRENT_CONTRACT_HISTORY
        for item in facts[:3]
    )
    assert all("continuous" not in item.lower() for item in facts[0].period_provenance)


def test_future_source_constituent_is_rejected() -> None:
    def append_future(value):  # type: ignore[no-untyped-def]
        return value + (_candle(date(2026, 8, 15), 999),)

    facts = _facts(daily_transform=append_future)

    assert all(
        item.availability is SwingReferenceAvailability.UNAVAILABLE
        and item.unavailable_reason
        is SwingReferenceUnavailableReason.SOURCE_FACT_UNAVAILABLE
        for item in facts[:3]
    )


def test_fact_binds_run_instrument_timeframe_policies_boundaries_and_provider() -> None:
    fact = _facts()[0]

    assert fact.run_identity == RUN_ID
    assert fact.canonical_instrument == "RELIANCE"
    assert fact.chart_timeframe is SwingReferenceChartTimeframe.WEEKLY
    assert fact.reference_policy_identity == REFERENCE_POLICY_IDENTITY
    assert fact.reference_policy_version == REFERENCE_POLICY_VERSION
    assert fact.calculation_policy_identity == CPR_CALCULATION_POLICY_IDENTITY
    assert fact.calculation_policy_version == CPR_CALCULATION_POLICY_VERSION
    assert fact.source == REFERENCE_SOURCE
    assert fact.provider_source_identity == REFERENCE_SOURCE
    assert fact.source_interval == "DAY"
    assert fact.analysis_boundary == datetime(2026, 8, 14, 23, 58, tzinfo=IST)
    assert fact.source_market_data_boundary <= fact.analysis_boundary
    assert fact.calendar_identity and fact.calendar_version
    assert fact.schema == REFERENCE_MACHINE_FACT_SCHEMA
    assert fact.authority == REFERENCE_MACHINE_FACT_AUTHORITY


def test_integrity_is_deterministic_and_tampering_fails_closed() -> None:
    first = _facts()[0]
    second = _facts()[0]
    payload = asdict(first)
    payload.update(
        {
            "chart_timeframe": first.chart_timeframe.value,
            "reference_period_type": first.reference_period_type.value,
            "reference_period_start": first.reference_period_start.isoformat(),
            "reference_period_end": first.reference_period_end.isoformat(),
            "source_market_data_boundary": first.source_market_data_boundary.isoformat(),
            "analysis_boundary": first.analysis_boundary.isoformat(),
            "availability": first.availability.value,
            "unavailable_reason": None,
        }
    )

    assert first.integrity_sha256 == second.integrity_sha256
    assert reference_machine_fact_from_dict(payload) == first
    payload["reference_high"] += 1.0
    with pytest.raises(ValueError, match="SWING_REFERENCE_MACHINE_FACT_INVALID"):
        reference_machine_fact_from_dict(payload)


def test_machine_fact_contract_has_only_deterministic_numerical_authority() -> None:
    names = {item.name for item in fields(type(_facts()[0]))}

    assert {
        "visual_state",
        "readiness",
        "progression_watch",
        "trade_plan",
        "sponsor_decision",
        "broker_order",
        "confluence_zone",
    }.isdisjoint(names)
    assert _facts()[0].authority == "DETERMINISTIC_NUMERICAL_FACT_ONLY"


def test_json_round_trip_contains_no_provider_private_material() -> None:
    serialized = json.dumps(asdict(_facts()[0]), default=str).lower()

    assert all(
        item not in serialized
        for item in (
            "access_token",
            "request_token",
            "api_secret",
            "instrument_token",
            "raw_kite",
        )
    )
