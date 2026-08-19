"""Acquire current governed MTF facts without candidate or Pine authority."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
import json
import math
from zoneinfo import ZoneInfo

from kronos.market.calendar import MarketCalendarPublisher
from kronos.application.swing_weekly_facts import (
    acquire_nse_weekly_factual_foundation,
)
from kronos.market.derived_timeframes import (
    DerivedBarEvidence,
    DerivedBarStatus,
    derive_session_four_hour_bars,
    derive_weekly_bar,
)
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalInterval,
)
from kronos.swing.daily_data import SwingDailyDataset, SwingDailyStatus
from kronos.swing.universe import SwingUniverseAssetClass
from kronos.swing.v1.evidence import factual_pivot_candidates
from kronos.swing.v1.mtf_facts import (
    CompletedTimeframeFact,
    FactualMovingAverageFacts,
    FactualPivotSeries,
    FactualTimeframe,
    FactualVolumeFacts,
    InstrumentMtfFactSnapshot,
    SameRunMtfFactSnapshot,
)
from kronos.swing.v1.reference_facts import build_reference_machine_facts
from kronos.swing.v1.weekly_facts import NseWeeklyFactualFoundation


_INTRADAY_HISTORY_DAYS = 60
_FACT_SERIES_DEPTH = 30
_PROVIDER_SOURCE = "KITE_NORMALIZED_HISTORICAL"


def build_same_run_mtf_fact_snapshot(
    *,
    run_identity: str,
    daily_dataset: SwingDailyDataset,
    historical_candles: object,
    calendar_publisher: MarketCalendarPublisher,
    observed_at: datetime,
    analysis_boundary: datetime | None = None,
    predecessor_snapshot: SameRunMtfFactSnapshot | None = None,
) -> SameRunMtfFactSnapshot:
    """Build the complete same-98 factual snapshot from fresh Provider calls."""

    if (
        not run_identity
        or type(daily_dataset) is not SwingDailyDataset
        or daily_dataset.ready_count != 98
        or not callable(historical_candles)
        or type(calendar_publisher) is not MarketCalendarPublisher
        or not _aware(observed_at)
        or (analysis_boundary is not None and not _aware(analysis_boundary))
        or (
            predecessor_snapshot is not None
            and type(predecessor_snapshot) is not SameRunMtfFactSnapshot
        )
    ):
        raise ValueError("MTF_FACT_PRODUCTION_REQUEST_INVALID")

    instruments = []
    source_material = []
    for record in daily_dataset.records:
        if record.status is not SwingDailyStatus.READY or record._analysis_instrument is None:
            raise ValueError("MTF_FACT_DAILY_CONTROL_UNAVAILABLE")
        exchange = (
            "MCX"
            if record.asset_class is SwingUniverseAssetClass.MCX_COMMODITY
            else "NSE"
        )
        publication = calendar_publisher.publication(exchange)
        timezone = ZoneInfo(publication.timezone)
        weekly_foundation: NseWeeklyFactualFoundation | None = None
        if exchange == "NSE":
            predecessor = _predecessor_weekly_foundation(
                predecessor_snapshot, record.canonical_identity
            )
            weekly_foundation, daily = acquire_nse_weekly_factual_foundation(
                run_identity=run_identity,
                canonical_instrument=record.canonical_identity,
                provider_instrument=record._analysis_instrument,
                historical_candles=historical_candles,
                calendar_publisher=calendar_publisher,
                observed_at=observed_at,
                predecessor=predecessor,
            )
        else:
            daily = _validated_series(historical_candles(HistoricalCandleRequest(
                instrument=record._analysis_instrument,
                start=datetime.combine(publication.coverage_start, time.min, tzinfo=timezone).astimezone(UTC),
                end=observed_at.astimezone(UTC),
                interval=HistoricalInterval.DAY,
            )), "MTF_FACT_DAY_SERIES_INVALID")
        hourly = _validated_series(historical_candles(HistoricalCandleRequest(
            instrument=record._analysis_instrument,
            start=observed_at.astimezone(UTC) - timedelta(days=_INTRADAY_HISTORY_DAYS),
            end=observed_at.astimezone(UTC),
            interval=HistoricalInterval.SIXTY_MINUTE,
        )), "MTF_FACT_60MINUTE_SERIES_INVALID")

        completed_daily = _completed_daily(
            exchange, daily, calendar_publisher, observed_at
        )
        completed_hourly = _completed_hourly(
            exchange, hourly, calendar_publisher, observed_at
        )
        weekly = _completed_weekly(
            exchange, record.canonical_identity, completed_daily,
            calendar_publisher, observed_at,
        )
        four_hour = _completed_four_hour(
            exchange, record.canonical_identity,
            tuple(item[0] for item in completed_hourly),
            calendar_publisher, observed_at,
        )
        if not completed_daily or not completed_hourly or not weekly or not four_hour:
            raise ValueError("MTF_FACT_COMPLETED_EVIDENCE_UNAVAILABLE")

        latest_daily, daily_schedule = completed_daily[-1]
        latest_hour, hour_schedule, hour_boundary = completed_hourly[-1]
        latest_week, week_identity = weekly[-1]
        latest_four = four_hour[-1]
        weekly_candles = (
            tuple(_weekly_foundation_candle(item) for item in weekly_foundation.completed_weekly_bars)
            if weekly_foundation is not None and weekly_foundation.completed_weekly_bars
            else tuple(_derived_candle(item[0]) for item in weekly)
        )
        four_hour_candles = tuple(_derived_candle(item) for item in four_hour)
        hourly_candles = tuple(item[0] for item in completed_hourly)
        daily_candles = tuple(item[0] for item in completed_daily)

        facts = (
            _derived_fact(
                FactualTimeframe.WEEKLY, latest_week, week_identity,
                weekly_candles, source_interval="DAY",
            ),
            _source_fact(
                FactualTimeframe.DAILY, latest_daily, daily_schedule,
                daily_schedule.windows[-1].window_close, daily_candles, "DAY",
            ),
            _derived_fact(
                FactualTimeframe.FOUR_HOUR, latest_four,
                latest_four.session_identity or "",
                four_hour_candles, source_interval="60minute",
            ),
            _source_fact(
                FactualTimeframe.ONE_HOUR, latest_hour, hour_schedule,
                hour_boundary, hourly_candles, "60minute",
            ),
        )
        reference_facts = build_reference_machine_facts(
            run_identity=run_identity,
            canonical_instrument=record.canonical_identity,
            exchange=exchange,
            completed_daily=daily_candles,
            completed_week=latest_week,
            completed_week_identity=week_identity,
            calendar_publisher=calendar_publisher,
            observed_at=observed_at,
            analysis_boundary=(
                analysis_boundary
                if analysis_boundary is not None
                else min(item.observation_boundary for item in facts)
            ),
            provider_source_identity=_PROVIDER_SOURCE,
        )
        instruments.append(InstrumentMtfFactSnapshot(
            record.canonical_identity,
            exchange,
            facts,
            weekly_foundation,
            reference_facts,
        ))
        source_material.append({
            "instrument": record.canonical_identity,
            "exchange": exchange,
            "calendar_sha256": publication.publication_sha256,
            "nse_weekly_source_result_sha256": (
                None
                if weekly_foundation is None
                else weekly_foundation.source_result_sha256
            ),
            "timeframes": [
                [item.timeframe.value, item.observation_boundary.isoformat(),
                 item.open, item.high, item.low, item.close, item.volume]
                for item in facts
            ],
            "reference_facts": [
                [
                    item.chart_timeframe.value,
                    item.reference_period_identity,
                    item.availability.value,
                    item.integrity_sha256,
                ]
                for item in reference_facts
            ],
        })

    identity = "KITE-MTF-FACTS-" + sha256(
        json.dumps(source_material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return SameRunMtfFactSnapshot(
        run_identity, observed_at, identity, tuple(instruments)
    )


def _predecessor_weekly_foundation(
    snapshot: SameRunMtfFactSnapshot | None,
    canonical_identity: str,
) -> NseWeeklyFactualFoundation | None:
    if snapshot is None:
        return None
    try:
        return snapshot.instrument(canonical_identity).nse_weekly_foundation
    except ValueError:
        return None


def _completed_daily(
    exchange: str,
    candles: tuple[HistoricalCandle, ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[tuple[HistoricalCandle, object], ...]:
    result = []
    timezone = ZoneInfo(publisher.publication(exchange).timezone)
    for candle in candles:
        day = candle.timestamp.astimezone(timezone).date()
        try:
            schedule = publisher.schedule(exchange, day, observed_at=observed_at)
        except ValueError as error:
            if str(error) == "MARKET_CALENDAR_DATE_OUTSIDE_PUBLICATION":
                continue
            raise
        if (
            schedule is not None
            and schedule.trading_date_completed(observed_at)
        ):
            result.append((candle, schedule))
    return tuple(result)


def _completed_hourly(
    exchange: str,
    candles: tuple[HistoricalCandle, ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[tuple[HistoricalCandle, object, datetime], ...]:
    result = []
    timezone = ZoneInfo(publisher.publication(exchange).timezone)
    for candle in candles:
        day = candle.timestamp.astimezone(timezone).date()
        try:
            schedule = publisher.schedule(exchange, day, observed_at=observed_at)
        except ValueError as error:
            if str(error) == "MARKET_CALENDAR_DATE_OUTSIDE_PUBLICATION":
                continue
            raise
        if schedule is None:
            continue
        timestamp = candle.timestamp.astimezone(timezone)
        window = schedule.window_at(timestamp)
        if window is None:
            continue
        boundary = min(timestamp + timedelta(hours=1), window.window_close)
        if boundary <= observed_at:
            result.append((candle, schedule, boundary))
    return tuple(result)


def _completed_weekly(
    exchange: str,
    canonical_identity: str,
    daily: tuple[tuple[HistoricalCandle, object], ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[tuple[DerivedBarEvidence, str], ...]:
    by_week: dict[date, list[HistoricalCandle]] = defaultdict(list)
    timezone = ZoneInfo(publisher.publication(exchange).timezone)
    for candle, _schedule in daily:
        day = candle.timestamp.astimezone(timezone).date()
        by_week[day - timedelta(days=day.weekday())].append(candle)
    result = []
    for monday, candles in sorted(by_week.items()):
        week = publisher.trading_week(exchange, monday, observed_at=observed_at)
        evidence = derive_weekly_bar(
            canonical_instrument=canonical_identity,
            trading_week=week,
            daily_candles=tuple(candles),
            source_provider_identity=_PROVIDER_SOURCE,
            source_market_data_boundary=daily[-1][0].timestamp,
            observed_at=observed_at,
        )
        if evidence is not None and evidence.status is DerivedBarStatus.COMPLETE:
            result.append((evidence, week.identity))
    return tuple(result)


def _completed_four_hour(
    exchange: str,
    canonical_identity: str,
    hourly: tuple[HistoricalCandle, ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[DerivedBarEvidence, ...]:
    by_date: dict[date, list[HistoricalCandle]] = defaultdict(list)
    timezone = ZoneInfo(publisher.publication(exchange).timezone)
    for candle in hourly:
        by_date[candle.timestamp.astimezone(timezone).date()].append(candle)
    result = []
    for day, candles in sorted(by_date.items()):
        schedule = publisher.schedule(exchange, day, observed_at=observed_at)
        if schedule is None:
            continue
        result.extend(
            item for item in derive_session_four_hour_bars(
                canonical_instrument=canonical_identity,
                schedule=schedule,
                sixty_minute_candles=tuple(candles),
                source_provider_identity=_PROVIDER_SOURCE,
                source_market_data_boundary=hourly[-1].timestamp,
                observed_at=observed_at,
            )
            if item.status is DerivedBarStatus.COMPLETE
        )
    return tuple(result)


def _source_fact(
    timeframe: FactualTimeframe,
    candle: HistoricalCandle,
    schedule: object,
    boundary: datetime | None,
    series: tuple[HistoricalCandle, ...],
    source_interval: str,
) -> CompletedTimeframeFact:
    if boundary is None:
        raise ValueError("MTF_FACT_BOUNDARY_UNAVAILABLE")
    return CompletedTimeframeFact(
        timeframe=timeframe,
        observation_boundary=boundary,
        source_timestamp=candle.timestamp,
        open=candle.open, high=candle.high, low=candle.low,
        close=candle.close, volume=candle.volume,
        calendar_identity=getattr(schedule, "calendar_identity"),
        calendar_version=getattr(schedule, "calendar_version"),
        session_identity=getattr(schedule, "session_identity"),
        exchange_timezone=getattr(schedule, "timezone"),
        source_interval=source_interval,
        source_provider_identity=_PROVIDER_SOURCE,
        source_market_data_boundary=series[-1].timestamp,
        provenance=tuple(getattr(schedule, "provenance")),
        structural_measurements=_structural_measurements(series),
        moving_averages=_moving_average_facts(series),
        volume_facts=_volume_facts(series),
    )


def _derived_fact(
    timeframe: FactualTimeframe,
    evidence: DerivedBarEvidence,
    session_identity: str,
    series: tuple[HistoricalCandle, ...],
    *,
    source_interval: str,
) -> CompletedTimeframeFact:
    assert all(item is not None for item in (
        evidence.open, evidence.high, evidence.low, evidence.close, evidence.volume
    ))
    return CompletedTimeframeFact(
        timeframe=timeframe,
        observation_boundary=evidence.derived_end,
        source_timestamp=evidence.derived_start,
        open=evidence.open, high=evidence.high, low=evidence.low,  # type: ignore[arg-type]
        close=evidence.close, volume=evidence.volume,  # type: ignore[arg-type]
        calendar_identity=evidence.calendar_identity,
        calendar_version=evidence.calendar_version,
        session_identity=session_identity,
        exchange_timezone=evidence.exchange_timezone,
        source_interval=source_interval,
        source_provider_identity=evidence.source_provider_identity,
        source_market_data_boundary=evidence.source_market_data_boundary,
        provenance=evidence.provenance,
        structural_measurements=_structural_measurements(series),
        moving_averages=_moving_average_facts(series),
        volume_facts=_volume_facts(series),
        bucket_class=(
            evidence.bucket_class.value
            if timeframe is FactualTimeframe.FOUR_HOUR else None
        ),
    )


def _structural_measurements(
    candles: tuple[HistoricalCandle, ...],
) -> tuple[FactualPivotSeries, ...]:
    selected = candles[-_FACT_SERIES_DEPTH:]
    result = []
    for radius in (1, 2):
        highs, lows = factual_pivot_candidates(selected, radius)
        result.append(FactualPivotSeries(
            f"FRACTAL_UNIQUE_EXTREME_RADIUS_{radius}",
            radius,
            highs[-3:],
            lows[-3:],
        ))
    return tuple(result)


def _derived_candle(item: DerivedBarEvidence) -> HistoricalCandle:
    assert item.open is not None and item.high is not None and item.low is not None and item.close is not None and item.volume is not None
    return HistoricalCandle(
        item.derived_end, item.open, item.high, item.low, item.close, item.volume
    )


def _weekly_foundation_candle(item: object) -> HistoricalCandle:
    return HistoricalCandle(
        getattr(item, "observation_boundary"),
        getattr(item, "open"), getattr(item, "high"), getattr(item, "low"),
        getattr(item, "close"), getattr(item, "volume"),
    )


def _moving_average_facts(
    candles: tuple[HistoricalCandle, ...],
) -> FactualMovingAverageFacts:
    closes = tuple(item.close for item in candles)

    def average(period: int, values: tuple[float, ...] = closes) -> float | None:
        return None if len(values) < period else math.fsum(values[-period:]) / period

    prior = closes[:-5]
    return FactualMovingAverageFacts(
        len(closes), average(20), average(50), average(200),
        average(20, prior), average(50, prior), average(200, prior),
    )


def _volume_facts(
    candles: tuple[HistoricalCandle, ...],
) -> FactualVolumeFacts:
    prior = tuple(item.volume for item in candles[-21:-1])
    return FactualVolumeFacts(
        candles[-1].volume,
        None if len(prior) < 20 else math.fsum(prior) / len(prior),
    )


def _validated_series(value: object, reason: str) -> tuple[HistoricalCandle, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(reason)
    result = tuple(value)
    if (
        not result
        or any(type(item) is not HistoricalCandle for item in result)
        or any(current.timestamp <= previous.timestamp for previous, current in zip(result, result[1:]))
    ):
        raise ValueError(reason)
    return result


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = ["build_same_run_mtf_fact_snapshot"]
