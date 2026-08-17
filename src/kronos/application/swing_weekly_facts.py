"""Acquire and construct NSE 205-week facts without analytical authority."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
import math
from zoneinfo import ZoneInfo

from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.derived_timeframes import (
    DerivedBarEvidence,
    DerivedBarStatus,
    derive_weekly_bar,
)
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalInterval,
)
from kronos.swing.v1.evidence import factual_pivot_candidates
from kronos.swing.v1.models import PivotCandidate
from kronos.swing.v1.weekly_facts import (
    CompletedWeeklyBarFact,
    FactualPivotRelation,
    FactualPriceRelation,
    FactualStructureCondition,
    HistoricalDayRequestWindowFact,
    NSE_WEEKLY_REQUIRED_COUNT,
    NSE_WEEKLY_SMA_PERIOD,
    NseWeeklyFactualFoundation,
    WeeklyFactAvailability,
    WeeklyPivotFacts,
    WeeklySmaDirection,
    source_result_sha256,
)


_KITE_SAFE_DAY_REQUEST_SPAN = 1900
_INCREMENTAL_CONTEXT_DAYS = 320
_PROVIDER_SOURCE = "KITE_NORMALIZED_HISTORICAL"


def acquire_nse_weekly_factual_foundation(
    *,
    run_identity: str,
    canonical_instrument: str,
    provider_instrument: InstrumentRecord,
    historical_candles: object,
    calendar_publisher: MarketCalendarPublisher,
    observed_at: datetime,
    predecessor: NseWeeklyFactualFoundation | None = None,
) -> tuple[NseWeeklyFactualFoundation, tuple[HistoricalCandle, ...]]:
    """Acquire one deterministic DAY window and build independent NSE facts."""

    if (
        not run_identity
        or not canonical_instrument
        or type(provider_instrument) is not InstrumentRecord
        or provider_instrument.exchange != "NSE"
        or not callable(historical_candles)
        or type(calendar_publisher) is not MarketCalendarPublisher
        or not _aware(observed_at)
        or (
            predecessor is not None
            and type(predecessor) is not NseWeeklyFactualFoundation
        )
    ):
        raise ValueError("NSE_WEEKLY_FACTUAL_REQUEST_INVALID")

    publication = calendar_publisher.publication("NSE")
    timezone = ZoneInfo(publication.timezone)
    reusable = _reusable_predecessor(
        predecessor, canonical_instrument, provider_instrument,
        publication.calendar_identity, publication.calendar_version,
    )
    local_observed = observed_at.astimezone(timezone)
    acquisition_start = publication.coverage_start
    if reusable is not None:
        recent = max(
            publication.coverage_start,
            local_observed.date() - timedelta(days=_INCREMENTAL_CONTEXT_DAYS),
        )
        acquisition_start = max(
            publication.coverage_start,
            recent - timedelta(days=recent.weekday()),
        )
    windows = bounded_day_request_windows(
        acquisition_start, local_observed, timezone
    )
    acquired = []
    window_facts = []
    for start, end in windows:
        raw = historical_candles(HistoricalCandleRequest(
            instrument=provider_instrument,
            start=start.astimezone(UTC),
            end=end.astimezone(UTC),
            interval=HistoricalInterval.DAY,
        ))
        candles = _validated_series(raw)
        if any(
            not start <= item.timestamp.astimezone(timezone) <= end
            for item in candles
        ):
            raise ValueError("NSE_WEEKLY_DAY_RESPONSE_OUTSIDE_REQUEST_WINDOW")
        acquired.extend(candles)
        window_facts.append(HistoricalDayRequestWindowFact(start, end, len(candles)))
    acquired_series = _merge_candles(tuple(acquired))
    completed_daily = _completed_daily(
        acquired_series, calendar_publisher, observed_at
    )
    new_complete, new_incomplete = _derive_weekly(
        canonical_instrument, completed_daily, calendar_publisher, observed_at
    )

    previous_bars = () if reusable is None else reusable.completed_weekly_bars
    merged = {item.trading_week_identity: item for item in previous_bars}
    merged.update(
        (item.trading_week_identity, item)
        for item in (_weekly_bar_fact(evidence) for evidence in new_complete)
    )
    bars = tuple(sorted(merged.values(), key=lambda item: item.observation_boundary))
    bars = bars[-NSE_WEEKLY_REQUIRED_COUNT:]
    expected_latest_week = _latest_completed_week_identity(
        calendar_publisher, observed_at
    )
    reason = _unavailable_reason(
        bars=bars,
        incomplete=new_incomplete,
        completed_daily=completed_daily,
        coverage_start=publication.coverage_start,
        reusable=reusable,
        expected_latest_week=expected_latest_week,
    )
    common = {
        "canonical_instrument": canonical_instrument,
        "provider": provider_instrument.provider,
        "provider_exchange": provider_instrument.exchange,
        "provider_segment": provider_instrument.segment,
        "provider_trading_symbol": provider_instrument.trading_symbol,
        "provider_instrument_type": provider_instrument.instrument_type,
        "run_identity": run_identity,
        "request_windows": tuple(window_facts),
        "source_interval": "DAY",
        "calendar_identity": publication.calendar_identity,
        "calendar_version": publication.calendar_version,
        "calendar_publication_sha256": publication.publication_sha256,
        "predecessor_source_result_sha256": (
            None if reusable is None else reusable.source_result_sha256
        ),
        "completed_weekly_bars": bars,
    }
    if reason is not None:
        material = {**common, "availability": "UNAVAILABLE", "reason": reason}
        return NseWeeklyFactualFoundation(
            **common,
            availability=WeeklyFactAvailability.UNAVAILABLE,
            unavailable_reason=reason,
            current_sma200=None,
            prior_sma200_5w=None,
            sma200_difference=None,
            sma200_direction=None,
            latest_weekly_close=None,
            latest_close_relation=None,
            radius_2_structure=None,
            radius_1_developing=None,
            observation_boundary=None,
            source_result_sha256=source_result_sha256(material),
        ), acquired_series

    closes = tuple(item.close for item in bars)
    current = math.fsum(closes[-NSE_WEEKLY_SMA_PERIOD:]) / NSE_WEEKLY_SMA_PERIOD
    prior = math.fsum(closes[:-5][-NSE_WEEKLY_SMA_PERIOD:]) / NSE_WEEKLY_SMA_PERIOD
    difference = current - prior
    direction = (
        WeeklySmaDirection.RISING
        if current > prior
        else WeeklySmaDirection.FALLING
        if current < prior
        else WeeklySmaDirection.FLAT
    )
    latest_close = closes[-1]
    relation = (
        FactualPriceRelation.ABOVE
        if latest_close > current
        else FactualPriceRelation.BELOW
        if latest_close < current
        else FactualPriceRelation.AT
    )
    weekly_candles = tuple(_bar_candle(item) for item in bars)
    radius_2 = _pivot_facts(weekly_candles, 2)
    radius_1 = _pivot_facts(weekly_candles, 1)
    material = {
        **common,
        "availability": "AVAILABLE",
        "current_sma200": current,
        "prior_sma200_5w": prior,
        "difference": difference,
        "direction": direction,
        "latest_close": latest_close,
        "close_relation": relation,
        "radius_2": radius_2,
        "radius_1": radius_1,
        "observation_boundary": bars[-1].observation_boundary,
    }
    return NseWeeklyFactualFoundation(
        **common,
        availability=WeeklyFactAvailability.AVAILABLE,
        unavailable_reason=None,
        current_sma200=current,
        prior_sma200_5w=prior,
        sma200_difference=difference,
        sma200_direction=direction,
        latest_weekly_close=latest_close,
        latest_close_relation=relation,
        radius_2_structure=radius_2,
        radius_1_developing=radius_1,
        observation_boundary=bars[-1].observation_boundary,
        source_result_sha256=source_result_sha256(material),
    ), acquired_series


def bounded_day_request_windows(
    start: date,
    observed_at: datetime,
    timezone: ZoneInfo,
) -> tuple[tuple[datetime, datetime], ...]:
    """Split an inclusive local-date range with no gaps or overlap."""

    if type(start) is not date or not _aware(observed_at) or type(timezone) is not ZoneInfo:
        raise ValueError("NSE_WEEKLY_REQUEST_WINDOW_INVALID")
    local_end = observed_at.astimezone(timezone)
    if start > local_end.date():
        raise ValueError("NSE_WEEKLY_REQUEST_WINDOW_INVALID")
    result = []
    cursor = start
    while cursor <= local_end.date():
        last_date = min(
            cursor + timedelta(days=_KITE_SAFE_DAY_REQUEST_SPAN - 1),
            local_end.date(),
        )
        window_start = datetime.combine(cursor, time.min, tzinfo=timezone)
        window_end = (
            local_end
            if last_date == local_end.date()
            else datetime.combine(last_date, time.max, tzinfo=timezone)
        )
        result.append((window_start, window_end))
        cursor = last_date + timedelta(days=1)
    return tuple(result)


def _reusable_predecessor(
    value: NseWeeklyFactualFoundation | None,
    canonical_instrument: str,
    provider_instrument: InstrumentRecord,
    calendar_identity: str,
    calendar_version: str,
) -> NseWeeklyFactualFoundation | None:
    if value is None:
        return None
    if (
        value.canonical_instrument != canonical_instrument
        or value.provider != provider_instrument.provider
        or value.provider_exchange != provider_instrument.exchange
        or value.provider_segment != provider_instrument.segment
        or value.provider_trading_symbol != provider_instrument.trading_symbol
        or value.provider_instrument_type != provider_instrument.instrument_type
        or value.calendar_identity != calendar_identity
        or value.calendar_version != calendar_version
    ):
        return None
    return value


def _completed_daily(
    candles: tuple[HistoricalCandle, ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[HistoricalCandle, ...]:
    timezone = ZoneInfo(publisher.publication("NSE").timezone)
    result = []
    for candle in candles:
        day = candle.timestamp.astimezone(timezone).date()
        try:
            schedule = publisher.schedule("NSE", day, observed_at=observed_at)
        except ValueError as error:
            if str(error) == "MARKET_CALENDAR_DATE_OUTSIDE_PUBLICATION":
                continue
            raise
        if schedule is not None and schedule.trading_date_completed(observed_at):
            result.append(candle)
    return tuple(result)


def _derive_weekly(
    canonical_instrument: str,
    daily: tuple[HistoricalCandle, ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[tuple[DerivedBarEvidence, ...], tuple[DerivedBarEvidence, ...]]:
    timezone = ZoneInfo(publisher.publication("NSE").timezone)
    by_week: dict[date, list[HistoricalCandle]] = defaultdict(list)
    for candle in daily:
        day = candle.timestamp.astimezone(timezone).date()
        by_week[day - timedelta(days=day.weekday())].append(candle)
    if not by_week:
        return (), ()
    complete = []
    incomplete = []
    first_monday = min(by_week)
    last_monday = max(by_week)
    monday = first_monday
    source_boundary = daily[-1].timestamp
    while monday <= last_monday:
        week = publisher.trading_week("NSE", monday, observed_at=observed_at)
        evidence = derive_weekly_bar(
            canonical_instrument=canonical_instrument,
            trading_week=week,
            daily_candles=tuple(by_week.get(monday, ())),
            source_provider_identity=_PROVIDER_SOURCE,
            source_market_data_boundary=source_boundary,
            observed_at=observed_at,
        )
        if evidence is not None:
            (complete if evidence.status is DerivedBarStatus.COMPLETE else incomplete).append(evidence)
        monday += timedelta(days=7)
    return tuple(complete), tuple(incomplete)


def _weekly_bar_fact(evidence: DerivedBarEvidence) -> CompletedWeeklyBarFact:
    assert all(value is not None for value in (
        evidence.open, evidence.high, evidence.low, evidence.close, evidence.volume
    ))
    return CompletedWeeklyBarFact(
        trading_week_identity=evidence.provenance[2],
        observation_boundary=evidence.derived_end,
        source_start=evidence.derived_start,
        open=evidence.open,  # type: ignore[arg-type]
        high=evidence.high,  # type: ignore[arg-type]
        low=evidence.low,  # type: ignore[arg-type]
        close=evidence.close,  # type: ignore[arg-type]
        volume=evidence.volume,  # type: ignore[arg-type]
        constituent_identities=evidence.constituent_identities,
        source_provider_identity=evidence.source_provider_identity,
        source_market_data_boundary=evidence.source_market_data_boundary,
        provenance=evidence.provenance,
    )


def _unavailable_reason(
    *,
    bars: tuple[CompletedWeeklyBarFact, ...],
    incomplete: tuple[DerivedBarEvidence, ...],
    completed_daily: tuple[HistoricalCandle, ...],
    coverage_start: date,
    reusable: NseWeeklyFactualFoundation | None,
    expected_latest_week: str | None,
) -> str | None:
    latest_matches = bool(
        bars
        and expected_latest_week is not None
        and bars[-1].trading_week_identity == expected_latest_week
    )
    if len(bars) == NSE_WEEKLY_REQUIRED_COUNT and not incomplete and latest_matches:
        return None
    if not completed_daily:
        return "INSUFFICIENT_PROVIDER_HISTORY"
    first_source_date = completed_daily[0].timestamp.date()
    if reusable is None and first_source_date > coverage_start:
        return "INSUFFICIENT_PROVIDER_HISTORY"
    if incomplete:
        return "MISSING_REQUIRED_DAILY_CONSTITUENT"
    if not latest_matches:
        return "MISSING_REQUIRED_DAILY_CONSTITUENT"
    return "INSUFFICIENT_COMPLETED_GOVERNED_WEEKS"


def _latest_completed_week_identity(
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> str | None:
    publication = publisher.publication("NSE")
    monday = publication.coverage_start - timedelta(
        days=publication.coverage_start.weekday()
    )
    latest = None
    while monday <= publication.coverage_end:
        week = publisher.trading_week("NSE", monday, observed_at=observed_at)
        final_close = week.schedules[-1].windows[-1].window_close
        if final_close <= observed_at:
            latest = week.identity
        monday += timedelta(days=7)
    return latest


def _pivot_facts(
    candles: tuple[HistoricalCandle, ...], radius: int
) -> WeeklyPivotFacts:
    highs, lows = factual_pivot_candidates(candles, radius)
    preceding_high, latest_high = _latest_pair(highs)
    preceding_low, latest_low = _latest_pair(lows)
    high_relation = _relation(preceding_high, latest_high)
    low_relation = _relation(preceding_low, latest_low)
    condition = (
        FactualStructureCondition.INCOMPLETE
        if high_relation is None or low_relation is None
        else FactualStructureCondition.RELATIONS_AVAILABLE
        if high_relation is low_relation
        else FactualStructureCondition.MIXED
    )
    return WeeklyPivotFacts(
        radius, preceding_high, latest_high, high_relation,
        preceding_low, latest_low, low_relation, condition,
    )


def _latest_pair(
    values: tuple[PivotCandidate, ...]
) -> tuple[PivotCandidate | None, PivotCandidate | None]:
    if len(values) < 2:
        return None, values[-1] if values else None
    return values[-2], values[-1]


def _relation(
    previous: PivotCandidate | None, current: PivotCandidate | None
) -> FactualPivotRelation | None:
    if previous is None or current is None:
        return None
    return (
        FactualPivotRelation.HIGHER
        if current.value > previous.value
        else FactualPivotRelation.LOWER
        if current.value < previous.value
        else FactualPivotRelation.EQUAL
    )


def _bar_candle(item: CompletedWeeklyBarFact) -> HistoricalCandle:
    return HistoricalCandle(
        item.observation_boundary, item.open, item.high, item.low,
        item.close, item.volume,
    )


def _validated_series(value: object) -> tuple[HistoricalCandle, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError("NSE_WEEKLY_DAY_SERIES_INVALID")
    result = tuple(value)
    if (
        any(type(item) is not HistoricalCandle for item in result)
        or any(current.timestamp <= previous.timestamp for previous, current in zip(result, result[1:]))
    ):
        raise ValueError("NSE_WEEKLY_DAY_SERIES_INVALID")
    return result


def _merge_candles(candles: tuple[HistoricalCandle, ...]) -> tuple[HistoricalCandle, ...]:
    by_timestamp = {item.timestamp: item for item in candles}
    if len(by_timestamp) != len(candles):
        raise ValueError("NSE_WEEKLY_DAY_SERIES_AMBIGUOUS")
    return tuple(by_timestamp[key] for key in sorted(by_timestamp))


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "acquire_nse_weekly_factual_foundation",
    "bounded_day_request_windows",
]
