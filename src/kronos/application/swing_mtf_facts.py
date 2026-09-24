"""Acquire current governed MTF facts without candidate or Pine authority."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
import json
import math
import statistics
from zoneinfo import ZoneInfo

from kronos.market.calendar import MarketCalendarPublisher
from kronos.application.swing_weekly_facts import (
    acquire_nse_weekly_factual_foundation,
)
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
from kronos.swing.v1.evidence import factual_pivot_candidates
from kronos.swing.v1.mtf_facts import (
    CompletedOneHourAtrFact,
    CompletedTimeframeBar,
    CompletedTimeframeFact,
    FactualMovingAverageFacts,
    FactualPivotSeries,
    FactualTimeframe,
    FactualVolumeFacts,
    InstrumentMtfFactSnapshot,
    ONE_HOUR_ATR_REQUIRED_CANDLES,
    OneHourAtrAvailability,
    SameRunMtfFactSnapshot,
    one_hour_atr_integrity_sha256,
)
from kronos.swing.v1.reference_facts import build_reference_machine_facts
from kronos.swing.v1.weekly_facts import NseWeeklyFactualFoundation


_INTRADAY_HISTORY_DAYS = 60
_FACT_SERIES_DEPTH = 30
_STRUCTURAL_DAILY_FOUR_HOUR_DEPTH = 60
_PROVIDER_SOURCE = "KITE_NORMALIZED_HISTORICAL"


def _session_subject_identity(canonical_instrument: str) -> str:
    """Return the existing DOMAIN-008 subject identity for one Swing label."""

    return "BANKNIFTY" if canonical_instrument == "BANK NIFTY" else canonical_instrument


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

    acquisition_boundary = analysis_boundary or observed_at
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
        acquisition_end = min(
            observed_at.astimezone(timezone),
            datetime.combine(
                acquisition_boundary.astimezone(timezone).date(),
                time.max,
                tzinfo=timezone,
            ),
        )
        hourly = _validated_series(historical_candles(HistoricalCandleRequest(
            instrument=record._analysis_instrument,
            start=acquisition_end.astimezone(UTC) - timedelta(days=_INTRADAY_HISTORY_DAYS),
            end=acquisition_end.astimezone(UTC),
            interval=HistoricalInterval.SIXTY_MINUTE,
        )), "MTF_FACT_60MINUTE_SERIES_INVALID")
        cas_finality = lambda candle: _cas_daily_finality_verified(
            record.canonical_identity,
            candle,
            hourly,
            calendar_publisher,
            observed_at,
        )
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
                analysis_boundary=acquisition_boundary,
                cas_daily_finality=cas_finality,
                predecessor=predecessor,
            )
        else:
            daily = _validated_series(historical_candles(HistoricalCandleRequest(
                instrument=record._analysis_instrument,
                start=datetime.combine(publication.coverage_start, time.min, tzinfo=timezone).astimezone(UTC),
                end=acquisition_end.astimezone(UTC),
                interval=HistoricalInterval.DAY,
            )), "MTF_FACT_DAY_SERIES_INVALID")

        completed_daily = _completed_daily(
            exchange,
            daily,
            calendar_publisher,
            observed_at,
            canonical_instrument=record.canonical_identity,
            hourly=hourly,
            analysis_boundary=acquisition_boundary,
        )
        completed_hourly = _completed_hourly(
            exchange,
            hourly,
            calendar_publisher,
            observed_at,
            canonical_instrument=record.canonical_identity,
            analysis_boundary=acquisition_boundary,
        )
        weekly = _completed_weekly(
            exchange, record.canonical_identity, completed_daily,
            calendar_publisher, acquisition_end,
        )
        four_hour = _completed_four_hour(
            exchange, record.canonical_identity,
            tuple(item[0] for item in completed_hourly),
            calendar_publisher, observed_at,
            analysis_boundary=acquisition_boundary,
        )
        if not completed_daily or not completed_hourly or not weekly or not four_hour:
            raise ValueError("MTF_FACT_COMPLETED_EVIDENCE_UNAVAILABLE")

        latest_daily, daily_schedule, daily_boundary = completed_daily[-1]
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
                daily_boundary, daily_candles, "DAY",
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
        # Retain only bars already admitted by the existing DOMAIN-008 paths.
        # No additional retrieval, completion rule, or analytical calculation.
        completed_series = (
            *(
                _retained_derived_bar(FactualTimeframe.WEEKLY, bar, week_id, "DAY")
                for bar, week_id in weekly
            ),
            *(
                _retained_source_bar(
                    FactualTimeframe.DAILY, bar, schedule,
                    boundary, daily_candles[-1].timestamp, "DAY",
                )
                for bar, schedule, boundary in completed_daily
            ),
            *(
                _retained_derived_bar(
                    FactualTimeframe.FOUR_HOUR, bar, bar.session_identity or "", "60minute"
                )
                for bar in four_hour
            ),
            *(
                _retained_source_bar(
                    FactualTimeframe.ONE_HOUR, bar, schedule, boundary,
                    hourly_candles[-1].timestamp, "60minute",
                )
                for bar, schedule, boundary in completed_hourly
            ),
        )
        effective_analysis_boundary = (
            analysis_boundary
            if analysis_boundary is not None
            else min(item.observation_boundary for item in facts)
        )
        one_hour_atr = _one_hour_atr_fact(
            run_identity=run_identity,
            canonical_instrument=record.canonical_identity,
            analysis_boundary=effective_analysis_boundary,
            one_hour_fact=facts[-1],
            completed_hourly=hourly_candles,
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
            analysis_boundary=effective_analysis_boundary,
            provider_source_identity=_PROVIDER_SOURCE,
        )
        instruments.append(InstrumentMtfFactSnapshot(
            record.canonical_identity,
            exchange,
            facts,
            weekly_foundation,
            reference_facts,
            one_hour_atr,
            completed_series,
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
            "one_hour_atr_integrity_sha256": one_hour_atr.integrity_sha256,
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
    *,
    canonical_instrument: str | None = None,
    hourly: tuple[HistoricalCandle, ...] = (),
    analysis_boundary: datetime | None = None,
) -> tuple[tuple[HistoricalCandle, object, datetime], ...]:
    result = []
    timezone = ZoneInfo(publisher.publication(exchange).timezone)
    boundary_date = (
        observed_at if analysis_boundary is None else analysis_boundary
    ).astimezone(timezone).date()
    admissible_days = tuple(
        candle.timestamp.astimezone(timezone).date()
        for candle in candles
        if candle.timestamp.astimezone(timezone).date() <= boundary_date
    )
    latest_admissible_day = max(admissible_days, default=None)
    for candle in candles:
        day = candle.timestamp.astimezone(timezone).date()
        if day > boundary_date:
            continue
        try:
            if exchange == "NSE" and canonical_instrument is not None:
                profile = publisher.instrument_session_profile(
                    exchange,
                    day,
                    canonical_instrument_id=_session_subject_identity(
                        canonical_instrument
                    ),
                    observed_at=observed_at,
                )
                if profile is None:
                    continue
                finality_schedule = (
                    profile.closing_auction_session
                    if profile.closing_auction_session is not None
                    else profile.continuous_trading
                )
                if (
                    profile.closing_auction_session is not None
                    and day == latest_admissible_day
                    and not _cas_daily_finality_verified(
                        canonical_instrument,
                        candle,
                        hourly,
                        publisher,
                        observed_at,
                    )
                ):
                    continue
                # The retained DAY boundary remains the governed NSE daily
                # analytical boundary. CAS authority controls admission and
                # availability; it does not create a second daily horizon.
                schedule = publisher.schedule(
                    exchange, day, observed_at=observed_at
                )
            else:
                schedule = publisher.schedule(exchange, day, observed_at=observed_at)
                finality_schedule = schedule
        except ValueError as error:
            if str(error) == "MARKET_CALENDAR_DATE_OUTSIDE_PUBLICATION":
                continue
            raise
        if (
            schedule is not None
            and finality_schedule is not None
            and finality_schedule.trading_date_completed(observed_at)
        ):
            result.append((candle, schedule, schedule.windows[-1].window_close))
    return tuple(result)


def _completed_hourly(
    exchange: str,
    candles: tuple[HistoricalCandle, ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
    *,
    canonical_instrument: str | None = None,
    analysis_boundary: datetime | None = None,
) -> tuple[tuple[HistoricalCandle, object, datetime], ...]:
    result = []
    timezone = ZoneInfo(publisher.publication(exchange).timezone)
    boundary_date = (
        None
        if analysis_boundary is None
        else analysis_boundary.astimezone(timezone).date()
    )
    for candle in candles:
        day = candle.timestamp.astimezone(timezone).date()
        if boundary_date is not None and day > boundary_date:
            continue
        try:
            if exchange == "NSE" and canonical_instrument is not None:
                profile = publisher.instrument_session_profile(
                    exchange,
                    day,
                    canonical_instrument_id=_session_subject_identity(
                        canonical_instrument
                    ),
                    observed_at=observed_at,
                )
                authority_schedule = (
                    None if profile is None else profile.continuous_trading
                )
                schedule = publisher.schedule(
                    exchange, day, observed_at=observed_at
                )
            else:
                authority_schedule = None
                schedule = publisher.schedule(exchange, day, observed_at=observed_at)
        except ValueError as error:
            if str(error) == "MARKET_CALENDAR_DATE_OUTSIDE_PUBLICATION":
                continue
            raise
        if schedule is None:
            continue
        timestamp = candle.timestamp.astimezone(timezone)
        if (
            authority_schedule is not None
            and timestamp >= authority_schedule.windows[-1].window_close
        ):
            continue
        window = schedule.window_at(timestamp)
        if window is None:
            continue
        boundary = min(
            timestamp + timedelta(hours=1),
            window.window_close,
            *(
                ()
                if authority_schedule is None
                else (authority_schedule.windows[-1].window_close,)
            ),
        )
        if boundary <= observed_at:
            result.append((candle, schedule, boundary))
    return tuple(result)


def _cas_daily_finality_verified(
    canonical_instrument: str,
    daily: HistoricalCandle,
    hourly: tuple[HistoricalCandle, ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> bool:
    """Prove the DAY payload contains evidence beyond the 15:15 close."""

    timezone = ZoneInfo(publisher.publication("NSE").timezone)
    day = daily.timestamp.astimezone(timezone).date()
    profile = publisher.instrument_session_profile(
        "NSE",
        day,
        canonical_instrument_id=_session_subject_identity(canonical_instrument),
        observed_at=observed_at,
    )
    if profile is None or profile.closing_auction_session is None:
        return True
    auction = profile.closing_auction_session
    if not auction.trading_date_completed(observed_at):
        return False
    completed = _completed_hourly(
        "NSE",
        hourly,
        publisher,
        observed_at,
        canonical_instrument=canonical_instrument,
        analysis_boundary=daily.timestamp,
    )
    same_day = tuple(
        candle
        for candle, _schedule, _boundary in completed
        if candle.timestamp.astimezone(timezone).date() == day
    )
    if not same_day:
        return False
    continuous_schedule = profile.continuous_trading
    expected_timestamps = []
    cursor = continuous_schedule.windows[0].window_open
    while cursor < continuous_schedule.windows[-1].window_close:
        expected_timestamps.append(cursor)
        cursor += timedelta(hours=1)
    if tuple(item.timestamp.astimezone(timezone) for item in same_day) != tuple(
        expected_timestamps
    ):
        return False
    continuous = HistoricalCandle(
        timestamp=daily.timestamp,
        open=same_day[0].open,
        high=max(item.high for item in same_day),
        low=min(item.low for item in same_day),
        close=same_day[-1].close,
        volume=sum(item.volume for item in same_day),
    )
    contains_continuous = (
        daily.open == continuous.open
        and daily.high >= continuous.high
        and daily.low <= continuous.low
        and daily.volume >= continuous.volume
    )
    # Price at the official daily close is the Provider evidence unavailable
    # in a pure 15:15 continuous aggregate. Volume alone is insufficient: a
    # DAY payload can also include pre-open volume.
    has_post_continuous_evidence = daily.close != continuous.close
    return contains_continuous and has_post_continuous_evidence


def _completed_weekly(
    exchange: str,
    canonical_identity: str,
    daily: tuple[tuple[HistoricalCandle, object, datetime], ...],
    publisher: MarketCalendarPublisher,
    observed_at: datetime,
) -> tuple[tuple[DerivedBarEvidence, str], ...]:
    by_week: dict[date, list[HistoricalCandle]] = defaultdict(list)
    timezone = ZoneInfo(publisher.publication(exchange).timezone)
    for candle, _schedule, _boundary in daily:
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
    *,
    analysis_boundary: datetime | None = None,
) -> tuple[DerivedBarEvidence, ...]:
    by_date: dict[date, list[HistoricalCandle]] = defaultdict(list)
    timezone = ZoneInfo(publisher.publication(exchange).timezone)
    for candle in hourly:
        by_date[candle.timestamp.astimezone(timezone).date()].append(candle)
    result = []
    for day, candles in sorted(by_date.items()):
        if (
            analysis_boundary is not None
            and day > analysis_boundary.astimezone(timezone).date()
        ):
            continue
        if exchange == "NSE":
            profile = publisher.instrument_session_profile(
                exchange,
                day,
                canonical_instrument_id=_session_subject_identity(
                    canonical_identity
                ),
                observed_at=observed_at,
            )
            if profile is None:
                schedule = None
                remainder_schedule = None
            else:
                continuous_close = profile.continuous_trading.windows[-1].window_close
                candles = [
                    candle for candle in candles
                    if candle.timestamp.astimezone(timezone) < continuous_close
                ]
                schedule = publisher.schedule(
                    exchange, day, observed_at=observed_at
                )
                remainder_schedule = profile.continuous_trading
        else:
            schedule = publisher.schedule(exchange, day, observed_at=observed_at)
            remainder_schedule = None
        if schedule is None:
            continue
        generic = derive_session_four_hour_bars(
            canonical_instrument=canonical_identity,
            schedule=schedule,
            sixty_minute_candles=tuple(candles),
            source_provider_identity=_PROVIDER_SOURCE,
            source_market_data_boundary=hourly[-1].timestamp,
            observed_at=observed_at,
        )
        generic_complete = tuple(
            item for item in generic
            if item.status is DerivedBarStatus.COMPLETE
        )
        result.extend(generic_complete)
        if remainder_schedule is not None:
            subject = derive_session_four_hour_bars(
                canonical_instrument=canonical_identity,
                schedule=remainder_schedule,
                sixty_minute_candles=tuple(candles),
                source_provider_identity=_PROVIDER_SOURCE,
                source_market_data_boundary=hourly[-1].timestamp,
                observed_at=observed_at,
            )
            result.extend(
                item for item in subject
                if item.status is DerivedBarStatus.COMPLETE
                and item.bucket_class is DerivedBucketClass.SESSION_REMAINDER
                and (item.derived_end, item.derived_start) not in {
                    (existing.derived_end, existing.derived_start)
                    for existing in generic_complete
                }
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
        structural_measurements=_structural_measurements(series, timeframe),
        moving_averages=_moving_average_facts(series),
        volume_facts=_volume_facts(series),
    )


def _retained_source_bar(
    timeframe: FactualTimeframe,
    candle: HistoricalCandle,
    schedule: object,
    boundary: datetime,
    source_boundary: datetime,
    interval: str,
) -> CompletedTimeframeBar:
    return CompletedTimeframeBar(
        timeframe=timeframe,
        observation_boundary=boundary,
        source_timestamp=candle.timestamp,
        open=candle.open, high=candle.high, low=candle.low,
        close=candle.close, volume=candle.volume,
        calendar_identity=schedule.calendar_identity,
        calendar_version=schedule.calendar_version,
        session_identity=schedule.session_identity,
        exchange_timezone=schedule.timezone,
        source_interval=interval,
        source_provider_identity=_PROVIDER_SOURCE,
        source_market_data_boundary=source_boundary,
        provenance=tuple(schedule.provenance),
    )


def _retained_derived_bar(
    timeframe: FactualTimeframe,
    evidence: DerivedBarEvidence,
    session_identity: str,
    interval: str,
) -> CompletedTimeframeBar:
    if evidence.status is not DerivedBarStatus.COMPLETE:
        raise ValueError("MTF_FACT_COMPLETED_EVIDENCE_UNAVAILABLE")
    return CompletedTimeframeBar(
        timeframe=timeframe,
        observation_boundary=evidence.derived_end,
        source_timestamp=evidence.derived_start,
        open=evidence.open, high=evidence.high, low=evidence.low,
        close=evidence.close, volume=evidence.volume,
        calendar_identity=evidence.calendar_identity,
        calendar_version=evidence.calendar_version,
        session_identity=session_identity,
        exchange_timezone=evidence.exchange_timezone,
        source_interval=interval,
        source_provider_identity=evidence.source_provider_identity,
        source_market_data_boundary=evidence.source_market_data_boundary,
        provenance=evidence.provenance,
        bucket_class=(evidence.bucket_class.value
                      if timeframe is FactualTimeframe.FOUR_HOUR else None),
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
        structural_measurements=_structural_measurements(series, timeframe),
        moving_averages=_moving_average_facts(series),
        volume_facts=_volume_facts(series),
        bucket_class=(
            evidence.bucket_class.value
            if timeframe is FactualTimeframe.FOUR_HOUR else None
        ),
    )


def _structural_measurements(
    candles: tuple[HistoricalCandle, ...],
    timeframe: FactualTimeframe,
) -> tuple[FactualPivotSeries, ...]:
    depth = (
        _STRUCTURAL_DAILY_FOUR_HOUR_DEPTH
        if timeframe in {FactualTimeframe.DAILY, FactualTimeframe.FOUR_HOUR}
        else _FACT_SERIES_DEPTH
    )
    selected = candles[-depth:]
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


def _one_hour_atr_fact(
    *,
    run_identity: str,
    canonical_instrument: str,
    analysis_boundary: datetime,
    one_hour_fact: CompletedTimeframeFact,
    completed_hourly: tuple[HistoricalCandle, ...],
) -> CompletedOneHourAtrFact:
    value = _completed_arithmetic_atr14(completed_hourly)
    available = value is not None
    values: dict[str, object] = {
        "run_identity": run_identity,
        "canonical_instrument": canonical_instrument,
        "analysis_boundary": analysis_boundary,
        "observation_boundary": one_hour_fact.observation_boundary,
        "source_market_data_boundary": one_hour_fact.source_market_data_boundary,
        "calendar_identity": one_hour_fact.calendar_identity,
        "calendar_version": one_hour_fact.calendar_version,
        "session_identity": one_hour_fact.session_identity,
        "exchange_timezone": one_hour_fact.exchange_timezone,
        "source_provider_identity": one_hour_fact.source_provider_identity,
        "provenance": one_hour_fact.provenance,
        "completed_candle_count": len(completed_hourly),
        "availability": (
            OneHourAtrAvailability.AVAILABLE
            if available
            else OneHourAtrAvailability.UNAVAILABLE
        ),
        "unavailable_reason": (
            None if available else "INSUFFICIENT_COMPLETED_1H_HISTORY"
        ),
        "value": value,
    }
    return CompletedOneHourAtrFact(
        **values,  # type: ignore[arg-type]
        integrity_sha256=one_hour_atr_integrity_sha256(values),
    )


def _completed_arithmetic_atr14(
    candles: tuple[HistoricalCandle, ...],
) -> float | None:
    """Match the established KRONOS arithmetic mean True Range convention."""

    if len(candles) < ONE_HOUR_ATR_REQUIRED_CANDLES:
        return None
    true_ranges = []
    for index in range(
        len(candles) - (ONE_HOUR_ATR_REQUIRED_CANDLES - 1), len(candles)
    ):
        candle = candles[index]
        previous_close = candles[index - 1].close
        true_ranges.append(max(
            candle.high - candle.low,
            abs(candle.high - previous_close),
            abs(candle.low - previous_close),
        ))
    return statistics.fmean(true_ranges)


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
