"""Governed Swing Auto-KGS reference and CPR machine facts.

This module owns deterministic numerical facts only.  It has no visual,
Readiness, trading, Sponsor-decision, or execution authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from hashlib import sha256
import json
import math
import re
from zoneinfo import ZoneInfo

from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.derived_timeframes import DerivedBarEvidence, DerivedBarStatus
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.run_identity import is_swing_analysis_run_id


REFERENCE_MACHINE_FACT_SCHEMA = "KRONOS-SWING-REFERENCE-CPR-MACHINE-FACT-V1"
REFERENCE_POLICY_IDENTITY = "SWING-AUTO-KGS-REFERENCE-POLICY"
REFERENCE_POLICY_VERSION = "1"
CPR_CALCULATION_POLICY_IDENTITY = "SWING-CPR-CALCULATION-POLICY"
CPR_CALCULATION_POLICY_VERSION = "1"
REFERENCE_MACHINE_FACT_AUTHORITY = "DETERMINISTIC_NUMERICAL_FACT_ONLY"
REFERENCE_SOURCE = "KITE_NORMALIZED_HISTORICAL"


class SwingReferenceChartTimeframe(StrEnum):
    WEEKLY = "1W"
    DAILY = "1D"
    FOUR_HOUR = "4H"
    ONE_HOUR = "1H"


class SwingReferencePeriodType(StrEnum):
    PREVIOUS_WEEK = "PREVIOUS_WEEK"
    PREVIOUS_MONTH = "PREVIOUS_MONTH"


class SwingReferenceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class SwingReferenceUnavailableReason(StrEnum):
    MISSING_REFERENCE_CONSTITUENTS = "MISSING_REFERENCE_CONSTITUENTS"
    REFERENCE_PERIOD_NOT_COMPLETE = "REFERENCE_PERIOD_NOT_COMPLETE"
    INSUFFICIENT_CURRENT_CONTRACT_HISTORY = (
        "INSUFFICIENT_CURRENT_CONTRACT_HISTORY"
    )
    CALENDAR_COMPLETION_UNAVAILABLE = "CALENDAR_COMPLETION_UNAVAILABLE"
    SOURCE_FACT_UNAVAILABLE = "SOURCE_FACT_UNAVAILABLE"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"


@dataclass(frozen=True, slots=True)
class GovernedReferencePeriod:
    """Typed calendar/session identity for one completed reference period."""

    period_type: SwingReferencePeriodType
    identity: str
    period_start: datetime
    period_end: datetime
    calendar_identity: str
    calendar_version: str
    constituent_identities: tuple[str, ...]
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.period_type) is not SwingReferencePeriodType
            or not self.identity
            or not _aware(self.period_start)
            or not _aware(self.period_end)
            or self.period_start >= self.period_end
            or not self.calendar_identity
            or not self.calendar_version
            or type(self.constituent_identities) is not tuple
            or not self.constituent_identities
            or len(set(self.constituent_identities))
            != len(self.constituent_identities)
            or not self.provenance
        ):
            raise ValueError("GOVERNED_REFERENCE_PERIOD_INVALID")


@dataclass(frozen=True, slots=True)
class _ReferenceOhlc:
    period: GovernedReferencePeriod
    open: float
    high: float
    low: float
    close: float
    source_market_data_boundary: datetime

    def __post_init__(self) -> None:
        values = (self.open, self.high, self.low, self.close)
        if (
            type(self.period) is not GovernedReferencePeriod
            or any(not _price(item) for item in values)
            or self.high < max(self.open, self.low, self.close)
            or self.low > min(self.open, self.high, self.close)
            or not _aware(self.source_market_data_boundary)
        ):
            raise ValueError("REFERENCE_OHLC_INVALID")


@dataclass(frozen=True, slots=True)
class SwingReferenceCprMachineFact:
    """Immutable same-run numerical fact with no downstream decision authority."""

    run_identity: str
    canonical_instrument: str
    chart_timeframe: SwingReferenceChartTimeframe
    reference_policy_identity: str
    reference_policy_version: str
    reference_period_type: SwingReferencePeriodType
    reference_period_identity: str
    reference_period_start: datetime
    reference_period_end: datetime
    reference_open: float | None
    reference_high: float | None
    reference_low: float | None
    reference_close: float | None
    cp: float | None
    bc: float | None
    tc: float | None
    source: str
    source_interval: str
    provider_source_identity: str
    source_market_data_boundary: datetime
    analysis_boundary: datetime
    calendar_identity: str
    calendar_version: str
    period_provenance: tuple[str, ...]
    calculation_policy_identity: str
    calculation_policy_version: str
    availability: SwingReferenceAvailability
    unavailable_reason: SwingReferenceUnavailableReason | None
    integrity_sha256: str
    authority: str = REFERENCE_MACHINE_FACT_AUTHORITY
    schema: str = REFERENCE_MACHINE_FACT_SCHEMA

    def __post_init__(self) -> None:
        numeric = (
            self.reference_open,
            self.reference_high,
            self.reference_low,
            self.reference_close,
            self.cp,
            self.bc,
            self.tc,
        )
        available = self.availability is SwingReferenceAvailability.AVAILABLE
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument)
            is None
            or type(self.chart_timeframe) is not SwingReferenceChartTimeframe
            or self.reference_policy_identity != REFERENCE_POLICY_IDENTITY
            or self.reference_policy_version != REFERENCE_POLICY_VERSION
            or type(self.reference_period_type) is not SwingReferencePeriodType
            or self.reference_period_type
            is not reference_period_type(self.chart_timeframe)
            or not self.reference_period_identity
            or not _aware(self.reference_period_start)
            or not _aware(self.reference_period_end)
            or self.reference_period_start >= self.reference_period_end
            or self.source != REFERENCE_SOURCE
            or self.source_interval != "DAY"
            or not self.provider_source_identity
            or not _aware(self.source_market_data_boundary)
            or not _aware(self.analysis_boundary)
            or not self.calendar_identity
            or not self.calendar_version
            or not self.period_provenance
            or self.calculation_policy_identity
            != CPR_CALCULATION_POLICY_IDENTITY
            or self.calculation_policy_version
            != CPR_CALCULATION_POLICY_VERSION
            or type(self.availability) is not SwingReferenceAvailability
            or self.authority != REFERENCE_MACHINE_FACT_AUTHORITY
            or self.schema != REFERENCE_MACHINE_FACT_SCHEMA
            or re.fullmatch(r"[0-9a-f]{64}", self.integrity_sha256) is None
            or (available and self.unavailable_reason is not None)
            or (
                not available
                and type(self.unavailable_reason)
                is not SwingReferenceUnavailableReason
            )
            or available != all(_price(item) for item in numeric)
            or (not available and any(item is not None for item in numeric))
            or (
                available
                and (
                    self.reference_high
                    < max(
                        self.reference_open,
                        self.reference_low,
                        self.reference_close,
                    )
                    or self.reference_low
                    > min(
                        self.reference_open,
                        self.reference_high,
                        self.reference_close,
                    )
                    or self.bc > self.tc
                )
            )
            or self.integrity_sha256 != machine_fact_integrity_sha256(self)
        ):
            raise ValueError("SWING_REFERENCE_MACHINE_FACT_INVALID")


def reference_period_type(
    timeframe: SwingReferenceChartTimeframe,
) -> SwingReferencePeriodType:
    """Return exact Production-Pine Auto-KGS routing for Swing timeframes."""

    if type(timeframe) is not SwingReferenceChartTimeframe:
        raise ValueError("SWING_REFERENCE_TIMEFRAME_INVALID")
    return (
        SwingReferencePeriodType.PREVIOUS_WEEK
        if timeframe is SwingReferenceChartTimeframe.ONE_HOUR
        else SwingReferencePeriodType.PREVIOUS_MONTH
    )


def calculate_cpr(high: float, low: float, close: float) -> tuple[float, float, float]:
    """Port Production Pine's exact CP and safety-normalized BC/TC arithmetic."""

    if any(not _price(item) for item in (high, low, close)) or high < max(low, close):
        raise ValueError("SWING_CPR_INPUT_INVALID")
    cp = (high + low + close) / 3.0
    raw_bc = (high + low) / 2.0
    raw_tc = (2.0 * cp) - raw_bc
    return cp, min(raw_bc, raw_tc), max(raw_bc, raw_tc)


def build_reference_machine_facts(
    *,
    run_identity: str,
    canonical_instrument: str,
    exchange: str,
    completed_daily: tuple[HistoricalCandle, ...],
    completed_week: DerivedBarEvidence,
    completed_week_identity: str,
    calendar_publisher: MarketCalendarPublisher,
    observed_at: datetime,
    analysis_boundary: datetime,
    provider_source_identity: str = REFERENCE_SOURCE,
) -> tuple[SwingReferenceCprMachineFact, ...]:
    """Build all four same-run Swing reference facts without Provider rereads."""

    if (
        not is_swing_analysis_run_id(run_identity)
        or not canonical_instrument
        or exchange not in {"NSE", "MCX"}
        or type(completed_daily) is not tuple
        or any(type(item) is not HistoricalCandle for item in completed_daily)
        or type(completed_week) is not DerivedBarEvidence
        or completed_week.status is not DerivedBarStatus.COMPLETE
        or not completed_week_identity
        or type(calendar_publisher) is not MarketCalendarPublisher
        or not _aware(observed_at)
        or not _aware(analysis_boundary)
        or not provider_source_identity
    ):
        raise ValueError("SWING_REFERENCE_FACT_REQUEST_INVALID")

    week = _weekly_source(completed_week, completed_week_identity)
    month, month_reason = _previous_month_source(
        canonical_instrument=canonical_instrument,
        exchange=exchange,
        completed_daily=completed_daily,
        calendar_publisher=calendar_publisher,
        observed_at=observed_at,
    )
    result = []
    for timeframe in SwingReferenceChartTimeframe:
        if timeframe is SwingReferenceChartTimeframe.ONE_HOUR:
            result.append(_available_fact(
                run_identity,
                canonical_instrument,
                timeframe,
                week,
                analysis_boundary,
                provider_source_identity,
            ))
        elif month is not None:
            result.append(_available_fact(
                run_identity,
                canonical_instrument,
                timeframe,
                month,
                analysis_boundary,
                provider_source_identity,
            ))
        else:
            assert month_reason is not None
            result.append(_unavailable_month_fact(
                run_identity=run_identity,
                canonical_instrument=canonical_instrument,
                timeframe=timeframe,
                exchange=exchange,
                calendar_publisher=calendar_publisher,
                observed_at=observed_at,
                analysis_boundary=analysis_boundary,
                provider_source_identity=provider_source_identity,
                source_boundary=completed_daily[-1].timestamp,
                reason=month_reason,
            ))
    return tuple(result)


def reference_machine_fact_from_dict(value: object) -> SwingReferenceCprMachineFact:
    """Restore one fact; the dataclass integrity check rejects tampering."""

    if type(value) is not dict:
        raise ValueError("SWING_REFERENCE_MACHINE_FACT_INVALID")
    try:
        return SwingReferenceCprMachineFact(
            run_identity=value["run_identity"],
            canonical_instrument=value["canonical_instrument"],
            chart_timeframe=SwingReferenceChartTimeframe(value["chart_timeframe"]),
            reference_policy_identity=value["reference_policy_identity"],
            reference_policy_version=value["reference_policy_version"],
            reference_period_type=SwingReferencePeriodType(value["reference_period_type"]),
            reference_period_identity=value["reference_period_identity"],
            reference_period_start=datetime.fromisoformat(value["reference_period_start"]),
            reference_period_end=datetime.fromisoformat(value["reference_period_end"]),
            reference_open=value["reference_open"],
            reference_high=value["reference_high"],
            reference_low=value["reference_low"],
            reference_close=value["reference_close"],
            cp=value["cp"],
            bc=value["bc"],
            tc=value["tc"],
            source=value["source"],
            source_interval=value["source_interval"],
            provider_source_identity=value["provider_source_identity"],
            source_market_data_boundary=datetime.fromisoformat(
                value["source_market_data_boundary"]
            ),
            analysis_boundary=datetime.fromisoformat(value["analysis_boundary"]),
            calendar_identity=value["calendar_identity"],
            calendar_version=value["calendar_version"],
            period_provenance=tuple(value["period_provenance"]),
            calculation_policy_identity=value["calculation_policy_identity"],
            calculation_policy_version=value["calculation_policy_version"],
            availability=SwingReferenceAvailability(value["availability"]),
            unavailable_reason=(
                None
                if value["unavailable_reason"] is None
                else SwingReferenceUnavailableReason(value["unavailable_reason"])
            ),
            integrity_sha256=value["integrity_sha256"],
            authority=value["authority"],
            schema=value["schema"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("SWING_REFERENCE_MACHINE_FACT_INVALID") from error


def machine_fact_integrity_sha256(fact: SwingReferenceCprMachineFact) -> str:
    material = asdict(fact)
    material.pop("integrity_sha256", None)
    return sha256(
        json.dumps(_json_value(material), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _weekly_source(
    evidence: DerivedBarEvidence,
    identity: str,
) -> _ReferenceOhlc:
    assert all(
        item is not None
        for item in (evidence.open, evidence.high, evidence.low, evidence.close)
    )
    period = GovernedReferencePeriod(
        SwingReferencePeriodType.PREVIOUS_WEEK,
        identity,
        evidence.derived_start,
        evidence.derived_end,
        evidence.calendar_identity,
        evidence.calendar_version,
        evidence.constituent_identities,
        evidence.provenance,
    )
    return _ReferenceOhlc(
        period,
        evidence.open,  # type: ignore[arg-type]
        evidence.high,  # type: ignore[arg-type]
        evidence.low,  # type: ignore[arg-type]
        evidence.close,  # type: ignore[arg-type]
        evidence.source_market_data_boundary,
    )


def _previous_month_source(
    *,
    canonical_instrument: str,
    exchange: str,
    completed_daily: tuple[HistoricalCandle, ...],
    calendar_publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[_ReferenceOhlc | None, SwingReferenceUnavailableReason | None]:
    publication = calendar_publisher.publication(exchange)
    zone = ZoneInfo(publication.timezone)
    local_date = observed_at.astimezone(zone).date()
    current_month = date(local_date.year, local_date.month, 1)
    final_day = current_month - timedelta(days=1)
    first_day = date(final_day.year, final_day.month, 1)

    if first_day < publication.coverage_start or final_day > publication.coverage_end:
        return None, SwingReferenceUnavailableReason.CALENDAR_COMPLETION_UNAVAILABLE
    if any(item.timestamp > observed_at for item in completed_daily):
        return None, SwingReferenceUnavailableReason.SOURCE_FACT_UNAVAILABLE

    schedules = []
    cursor = first_day
    while cursor <= final_day:
        try:
            schedule = calendar_publisher.schedule(
                exchange, cursor, observed_at=observed_at
            )
        except ValueError:
            return None, SwingReferenceUnavailableReason.CALENDAR_COMPLETION_UNAVAILABLE
        if schedule is not None:
            try:
                profile = calendar_publisher.instrument_session_profile(
                    exchange,
                    cursor,
                    canonical_instrument_id=canonical_instrument,
                    observed_at=observed_at,
                )
            except ValueError:
                return None, SwingReferenceUnavailableReason.CALENDAR_COMPLETION_UNAVAILABLE
            if profile is None:
                return None, SwingReferenceUnavailableReason.CALENDAR_COMPLETION_UNAVAILABLE
            authority_schedule = (
                profile.closing_auction_session
                if profile.closing_auction_session is not None
                else profile.continuous_trading
            )
            if not authority_schedule.trading_date_completed(observed_at):
                return None, SwingReferenceUnavailableReason.REFERENCE_PERIOD_NOT_COMPLETE
            schedules.append((schedule, authority_schedule))
        cursor += timedelta(days=1)
    if not schedules:
        return None, SwingReferenceUnavailableReason.CALENDAR_COMPLETION_UNAVAILABLE

    by_date: dict[date, HistoricalCandle] = {}
    for candle in completed_daily:
        candle_date = candle.timestamp.astimezone(zone).date()
        if first_day <= candle_date <= final_day:
            if candle_date in by_date:
                return None, SwingReferenceUnavailableReason.SOURCE_FACT_UNAVAILABLE
            by_date[candle_date] = candle
    expected_dates = tuple(item[0].trading_date for item in schedules)
    if any(day not in by_date for day in expected_dates):
        return None, (
            SwingReferenceUnavailableReason.INSUFFICIENT_CURRENT_CONTRACT_HISTORY
            if exchange == "MCX"
            else SwingReferenceUnavailableReason.MISSING_REFERENCE_CONSTITUENTS
        )
    if set(by_date) != set(expected_dates):
        return None, SwingReferenceUnavailableReason.SOURCE_FACT_UNAVAILABLE

    candles = tuple(by_date[day] for day in expected_dates)
    first_schedule = schedules[0][0]
    final_authority = schedules[-1][1]
    period = GovernedReferencePeriod(
        SwingReferencePeriodType.PREVIOUS_MONTH,
        (
            f"{publication.calendar_identity}:{publication.calendar_version}:"
            f"MONTH:{first_day:%Y-%m}"
        ),
        first_schedule.windows[0].window_open,
        final_authority.windows[-1].window_close,
        publication.calendar_identity,
        publication.calendar_version,
        tuple(item[0].session_identity for item in schedules),
        (
            "SWING-AUTO-KGS-PREVIOUS-MONTH",
            f"calendar={publication.calendar_identity}",
            f"version={publication.calendar_version}",
            f"publication_sha256={publication.publication_sha256}",
            *(f"constituent={item[0].session_identity}" for item in schedules),
            *(
                f"official_close={item[1].session_identity}|"
                f"{item[1].windows[-1].window_close.isoformat()}"
                for item in schedules
            ),
        ),
    )
    return _ReferenceOhlc(
        period,
        candles[0].open,
        max(item.high for item in candles),
        min(item.low for item in candles),
        candles[-1].close,
        candles[-1].timestamp,
    ), None


def _available_fact(
    run_identity: str,
    canonical_instrument: str,
    timeframe: SwingReferenceChartTimeframe,
    source: _ReferenceOhlc,
    analysis_boundary: datetime,
    provider_source_identity: str,
) -> SwingReferenceCprMachineFact:
    cp, bc, tc = calculate_cpr(source.high, source.low, source.close)
    values: dict[str, object] = {
        "run_identity": run_identity,
        "canonical_instrument": canonical_instrument,
        "chart_timeframe": timeframe,
        "reference_policy_identity": REFERENCE_POLICY_IDENTITY,
        "reference_policy_version": REFERENCE_POLICY_VERSION,
        "reference_period_type": source.period.period_type,
        "reference_period_identity": source.period.identity,
        "reference_period_start": source.period.period_start,
        "reference_period_end": source.period.period_end,
        "reference_open": source.open,
        "reference_high": source.high,
        "reference_low": source.low,
        "reference_close": source.close,
        "cp": cp,
        "bc": bc,
        "tc": tc,
        "source": REFERENCE_SOURCE,
        "source_interval": "DAY",
        "provider_source_identity": provider_source_identity,
        "source_market_data_boundary": source.source_market_data_boundary,
        "analysis_boundary": analysis_boundary,
        "calendar_identity": source.period.calendar_identity,
        "calendar_version": source.period.calendar_version,
        "period_provenance": source.period.provenance,
        "calculation_policy_identity": CPR_CALCULATION_POLICY_IDENTITY,
        "calculation_policy_version": CPR_CALCULATION_POLICY_VERSION,
        "availability": SwingReferenceAvailability.AVAILABLE,
        "unavailable_reason": None,
        "authority": REFERENCE_MACHINE_FACT_AUTHORITY,
        "schema": REFERENCE_MACHINE_FACT_SCHEMA,
    }
    return _fact(values)


def _unavailable_month_fact(
    *,
    run_identity: str,
    canonical_instrument: str,
    timeframe: SwingReferenceChartTimeframe,
    exchange: str,
    calendar_publisher: MarketCalendarPublisher,
    observed_at: datetime,
    analysis_boundary: datetime,
    provider_source_identity: str,
    source_boundary: datetime,
    reason: SwingReferenceUnavailableReason,
) -> SwingReferenceCprMachineFact:
    publication = calendar_publisher.publication(exchange)
    zone = ZoneInfo(publication.timezone)
    local = observed_at.astimezone(zone).date()
    current_month = date(local.year, local.month, 1)
    final_day = current_month - timedelta(days=1)
    first_day = date(final_day.year, final_day.month, 1)
    start = datetime.combine(first_day, time.min, zone)
    end = datetime.combine(final_day, time.max, zone)
    values: dict[str, object] = {
        "run_identity": run_identity,
        "canonical_instrument": canonical_instrument,
        "chart_timeframe": timeframe,
        "reference_policy_identity": REFERENCE_POLICY_IDENTITY,
        "reference_policy_version": REFERENCE_POLICY_VERSION,
        "reference_period_type": SwingReferencePeriodType.PREVIOUS_MONTH,
        "reference_period_identity": (
            f"{publication.calendar_identity}:{publication.calendar_version}:"
            f"MONTH:{first_day:%Y-%m}"
        ),
        "reference_period_start": start,
        "reference_period_end": end,
        "reference_open": None,
        "reference_high": None,
        "reference_low": None,
        "reference_close": None,
        "cp": None,
        "bc": None,
        "tc": None,
        "source": REFERENCE_SOURCE,
        "source_interval": "DAY",
        "provider_source_identity": provider_source_identity,
        "source_market_data_boundary": source_boundary,
        "analysis_boundary": analysis_boundary,
        "calendar_identity": publication.calendar_identity,
        "calendar_version": publication.calendar_version,
        "period_provenance": (
            "SWING-AUTO-KGS-PREVIOUS-MONTH",
            f"calendar={publication.calendar_identity}",
            f"version={publication.calendar_version}",
            f"unavailable={reason.value}",
        ),
        "calculation_policy_identity": CPR_CALCULATION_POLICY_IDENTITY,
        "calculation_policy_version": CPR_CALCULATION_POLICY_VERSION,
        "availability": SwingReferenceAvailability.UNAVAILABLE,
        "unavailable_reason": reason,
        "authority": REFERENCE_MACHINE_FACT_AUTHORITY,
        "schema": REFERENCE_MACHINE_FACT_SCHEMA,
    }
    return _fact(values)


def _fact(values: dict[str, object]) -> SwingReferenceCprMachineFact:
    digest = sha256(
        json.dumps(
            _json_value(values), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return SwingReferenceCprMachineFact(
        **values,  # type: ignore[arg-type]
        integrity_sha256=digest,
    )


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _price(value: object) -> bool:
    return type(value) is float and math.isfinite(value) and value >= 0.0


__all__ = [
    "CPR_CALCULATION_POLICY_IDENTITY",
    "CPR_CALCULATION_POLICY_VERSION",
    "GovernedReferencePeriod",
    "REFERENCE_MACHINE_FACT_AUTHORITY",
    "REFERENCE_MACHINE_FACT_SCHEMA",
    "REFERENCE_POLICY_IDENTITY",
    "REFERENCE_POLICY_VERSION",
    "REFERENCE_SOURCE",
    "SwingReferenceAvailability",
    "SwingReferenceChartTimeframe",
    "SwingReferenceCprMachineFact",
    "SwingReferencePeriodType",
    "SwingReferenceUnavailableReason",
    "build_reference_machine_facts",
    "calculate_cpr",
    "machine_fact_integrity_sha256",
    "reference_machine_fact_from_dict",
    "reference_period_type",
]
