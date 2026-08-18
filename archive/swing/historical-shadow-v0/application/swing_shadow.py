"""Production orchestration for same-run Shadow MTF validation evidence."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.derived_timeframes import (
    DerivedBarEvidence,
    DerivedBarStatus,
    DerivedBucketClass,
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
from kronos.swing.v1.models import ProbableClassification, V1Direction
from kronos.swing.v1.shadow_mtf import (
    DailyControlEvidence,
    DailyControlProbableIdentity,
    ShadowMtfRun,
    ShadowTimeframe,
    measure_shadow_timeframe,
    reconcile_shadow_candidate,
)


_INTRADAY_HISTORY_DAYS = 60
_SHADOW_SERIES_DEPTH = 30


def build_same_run_shadow_mtf(
    *,
    run_identity: str,
    daily_dataset: SwingDailyDataset,
    v1_layer1_run: object,
    historical_candles: object,
    calendar_publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> ShadowMtfRun:
    """Build the 98-member Shadow comparison without mutating Daily Control."""

    instruments = getattr(v1_layer1_run, "instruments", None)
    if (
        not run_identity
        or type(daily_dataset) is not SwingDailyDataset
        or daily_dataset.ready_count != 98
        or type(instruments) is not tuple
        or len(instruments) != 98
        or not callable(historical_candles)
        or type(calendar_publisher) is not MarketCalendarPublisher
        or not _aware(observed_at)
    ):
        raise ValueError("SHADOW_PRODUCTION_REQUEST_INVALID")
    layer1_by_identity = {item.canonical_identity: item for item in instruments}
    if set(layer1_by_identity) != {item.canonical_identity for item in daily_dataset.records}:
        raise ValueError("SHADOW_DAILY_CONTROL_POPULATION_MISMATCH")

    prepared = []
    source_material: list[object] = []
    for record in daily_dataset.records:
        if record.status is not SwingDailyStatus.READY or record._analysis_instrument is None:
            raise ValueError("SHADOW_DAILY_CONTROL_UNAVAILABLE")
        exchange = (
            "MCX"
            if record.asset_class is SwingUniverseAssetClass.MCX_COMMODITY
            else "NSE"
        )
        intraday = tuple(historical_candles(HistoricalCandleRequest(
            instrument=record._analysis_instrument,
            start=observed_at.astimezone(UTC) - timedelta(days=_INTRADAY_HISTORY_DAYS),
            end=observed_at.astimezone(UTC),
            interval=HistoricalInterval.SIXTY_MINUTE,
        )))
        if (
            not intraday
            or any(type(item) is not HistoricalCandle for item in intraday)
            or any(current.timestamp <= previous.timestamp for previous, current in zip(intraday, intraday[1:]))
        ):
            raise ValueError("SHADOW_60MINUTE_SERIES_INVALID")
        publication = calendar_publisher.publication(exchange)
        timezone = ZoneInfo(publication.timezone)
        weekly_daily = tuple(historical_candles(HistoricalCandleRequest(
            instrument=record._analysis_instrument,
            start=datetime.combine(
                publication.coverage_start, time.min, tzinfo=timezone
            ).astimezone(UTC),
            end=observed_at.astimezone(UTC),
            interval=HistoricalInterval.DAY,
        )))
        if (
            not weekly_daily
            or any(type(item) is not HistoricalCandle for item in weekly_daily)
            or any(
                current.timestamp <= previous.timestamp
                for previous, current in zip(weekly_daily, weekly_daily[1:])
            )
        ):
            raise ValueError("SHADOW_WEEKLY_DAILY_SERIES_INVALID")
        completed_weekly_daily = tuple(
            item
            for item in weekly_daily
            if item.timestamp.astimezone(timezone).date()
            <= record.observation_boundary.astimezone(timezone).date()
        )
        if not completed_weekly_daily:
            raise ValueError("SHADOW_WEEKLY_DAILY_SERIES_INVALID")
        completed_hourly = _completed_hourly(
            exchange, intraday, calendar_publisher, observed_at
        )
        weekly = _weekly_candles(
            exchange, record.canonical_identity, completed_weekly_daily,
            calendar_publisher, observed_at,
        )
        four_hour, full_four_hour, remainder_participated = _four_hour_candles(
            exchange, record.canonical_identity, completed_hourly,
            calendar_publisher, observed_at,
        )
        if not weekly or not four_hour or not completed_hourly:
            raise ValueError("SHADOW_DERIVED_EVIDENCE_UNAVAILABLE")
        prepared.append((record, layer1_by_identity[record.canonical_identity], weekly, four_hour, full_four_hour, completed_hourly, remainder_participated))
        source_material.append({
            "instrument": record.canonical_identity,
            "daily_boundary": record.observation_boundary.isoformat(),
            "weekly_daily": [
                _candle_value(item) for item in completed_weekly_daily
            ],
            "hourly": [_candle_value(item) for item in completed_hourly],
            "calendar": calendar_publisher.publication(exchange).publication_sha256,
        })

    source_identity = "SWING-SHADOW-SOURCE-" + sha256(
        json.dumps(source_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assessments = []
    for record, layer1, weekly_candles, four_hour_candles, full_four_hour_candles, hourly_candles, remainder in prepared:
        control = _daily_control(layer1, record.observation_boundary)
        weekly = measure_shadow_timeframe(
            timeframe=ShadowTimeframe.WEEKLY,
            candles=weekly_candles[-_SHADOW_SERIES_DEPTH:],
            completed=True,
        )
        daily = measure_shadow_timeframe(
            timeframe=ShadowTimeframe.DAILY,
            candles=record.candles[-_SHADOW_SERIES_DEPTH:],
            completed=True,
        )
        four = measure_shadow_timeframe(
            timeframe=ShadowTimeframe.FOUR_HOUR,
            candles=four_hour_candles[-_SHADOW_SERIES_DEPTH:],
            completed=True,
            session_remainder_participated=remainder,
        )
        hour = measure_shadow_timeframe(
            timeframe=ShadowTimeframe.ONE_HOUR,
            candles=hourly_candles[-_SHADOW_SERIES_DEPTH:],
            completed=True,
        )
        assessment = reconcile_shadow_candidate(
            run_identity=run_identity,
            provider_source_identity=source_identity,
            canonical_instrument=record.canonical_identity,
            control=control,
            weekly=weekly,
            daily=daily,
            four_hour=four,
            one_hour=hour,
        )
        if remainder:
            if full_four_hour_candles:
                without_remainder = measure_shadow_timeframe(
                    timeframe=ShadowTimeframe.FOUR_HOUR,
                    candles=full_four_hour_candles[-_SHADOW_SERIES_DEPTH:],
                    completed=True,
                )
                baseline = reconcile_shadow_candidate(
                    run_identity=run_identity,
                    provider_source_identity=source_identity,
                    canonical_instrument=record.canonical_identity,
                    control=control,
                    weekly=weekly,
                    daily=daily,
                    four_hour=without_remainder,
                    one_hour=hour,
                )
                if (baseline.state, baseline.setup, baseline.direction) != (
                    assessment.state, assessment.setup, assessment.direction
                ):
                    assessment = reconcile_shadow_candidate(
                        run_identity=run_identity,
                        provider_source_identity=source_identity,
                        canonical_instrument=record.canonical_identity,
                        control=control,
                        weekly=weekly,
                        daily=daily,
                        four_hour=four,
                        one_hour=hour,
                        remainder_material_to_change=True,
                    )
        assessments.append(assessment)
    return ShadowMtfRun(run_identity, source_identity, tuple(assessments))


def _daily_control(layer1: object, boundary: datetime) -> DailyControlEvidence:
    probable = tuple(
        item for item in layer1.assessments
        if item.classification is ProbableClassification.PROBABLE_CANDIDATE
    )
    identities = tuple(
        DailyControlProbableIdentity(item.setup, item.direction)
        for item in probable
    )
    if len(identities) == 1:
        item = identities[0]
        return DailyControlEvidence(
            True,
            item.setup,
            item.direction,
            "UNCHANGED_DAILY_LAYER1_PROBABLE",
            boundary,
            identities,
        )
    if identities:
        return DailyControlEvidence(
            True,
            None,
            V1Direction.NONE,
            "UNCHANGED_DAILY_LAYER1_MULTIPLE_PROBABLES",
            boundary,
            identities,
        )
    return DailyControlEvidence(
        False, None, V1Direction.NONE,
        "UNCHANGED_DAILY_LAYER1_NO_PROBABLE",
        boundary,
    )


def _completed_hourly(
    exchange: str,
    candles: tuple[HistoricalCandle, ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[HistoricalCandle, ...]:
    result = []
    for candle in candles:
        day = candle.timestamp.astimezone(ZoneInfo("Asia/Kolkata")).date()
        try:
            schedule = publisher.schedule(exchange, day, observed_at=observed_at)
        except ValueError as error:
            if str(error) == "MARKET_CALENDAR_DATE_OUTSIDE_PUBLICATION":
                continue
            raise
        if schedule is None:
            continue
        timestamp = candle.timestamp.astimezone(ZoneInfo(schedule.timezone))
        window = schedule.window_at(timestamp)
        if window is None:
            continue
        boundary = min(timestamp + timedelta(hours=1), window.window_close)
        if boundary <= observed_at:
            result.append(candle)
    return tuple(result)


def _weekly_candles(
    exchange: str,
    canonical_identity: str,
    daily: tuple[HistoricalCandle, ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[HistoricalCandle, ...]:
    by_week: dict[date, list[HistoricalCandle]] = {}
    for candle in daily:
        local_date = candle.timestamp.astimezone(ZoneInfo("Asia/Kolkata")).date()
        monday = local_date - timedelta(days=local_date.weekday())
        by_week.setdefault(monday, []).append(candle)
    result = []
    for monday, candles in sorted(by_week.items()):
        week = publisher.trading_week(exchange, monday, observed_at=observed_at)
        evidence = derive_weekly_bar(
            canonical_instrument=canonical_identity,
            trading_week=week,
            daily_candles=tuple(candles),
            source_provider_identity="KITE_NORMALIZED_HISTORICAL",
            source_market_data_boundary=daily[-1].timestamp,
            observed_at=observed_at,
        )
        if evidence is not None and evidence.status is DerivedBarStatus.COMPLETE:
            result.append(_derived_candle(evidence))
    return tuple(result)


def _four_hour_candles(
    exchange: str,
    canonical_identity: str,
    hourly: tuple[HistoricalCandle, ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[tuple[HistoricalCandle, ...], tuple[HistoricalCandle, ...], bool]:
    by_date: dict[date, list[HistoricalCandle]] = {}
    for candle in hourly:
        day = candle.timestamp.astimezone(ZoneInfo("Asia/Kolkata")).date()
        by_date.setdefault(day, []).append(candle)
    result: list[HistoricalCandle] = []
    full_duration: list[HistoricalCandle] = []
    remainder_flags: list[bool] = []
    for day, candles in sorted(by_date.items()):
        schedule = publisher.schedule(exchange, day, observed_at=observed_at)
        if schedule is None:
            continue
        evidence = derive_session_four_hour_bars(
            canonical_instrument=canonical_identity,
            schedule=schedule,
            sixty_minute_candles=tuple(candles),
            source_provider_identity="KITE_NORMALIZED_HISTORICAL",
            source_market_data_boundary=hourly[-1].timestamp,
            observed_at=observed_at,
        )
        for item in evidence:
            if item.status is DerivedBarStatus.COMPLETE:
                candle = _derived_candle(item)
                result.append(candle)
                if item.bucket_class is DerivedBucketClass.FULL_DURATION:
                    full_duration.append(candle)
                remainder_flags.append(item.bucket_class is DerivedBucketClass.SESSION_REMAINDER)
    selected_flags = remainder_flags[-_SHADOW_SERIES_DEPTH:]
    return tuple(result), tuple(full_duration), any(selected_flags)


def _derived_candle(item: DerivedBarEvidence) -> HistoricalCandle:
    assert item.open is not None and item.high is not None and item.low is not None and item.close is not None and item.volume is not None
    return HistoricalCandle(item.derived_end, item.open, item.high, item.low, item.close, item.volume)


def _candle_value(item: HistoricalCandle) -> tuple[object, ...]:
    return (item.timestamp.isoformat(), item.open, item.high, item.low, item.close, item.volume)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = ["build_same_run_shadow_mtf"]
