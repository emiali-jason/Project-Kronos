"""Governed candle completion and historical completeness reconciliation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from kronos.intraday.contracts import (
    CandleBoundary,
    CandleCompletion,
    DataAvailability,
    GovernedCandle,
    IntradayInstrumentReference,
    IntradayTimeframe,
    ObservationBoundary,
    SourceProvenance,
    governed_candle_identity,
)
from kronos.market.schedule import MarketDaySchedule, TradingDayStatus
from kronos.provider.contracts.market_data import HistoricalCandle, HistoricalInterval


class ReconciliationResult(StrEnum):
    COMPLETE = "COMPLETE"
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class ReconciliationFailure(StrEnum):
    NON_TRADING_DAY = "NON_TRADING_DAY"
    MALFORMED_PROVIDER_CANDLE = "MALFORMED_PROVIDER_CANDLE"
    MISSING_CANDLE = "MISSING_CANDLE"
    DUPLICATE_CANDLE = "DUPLICATE_CANDLE"
    OUT_OF_ORDER_PROVIDER_DATA = "OUT_OF_ORDER_PROVIDER_DATA"
    UNEXPECTED_CANDLE_BOUNDARY = "UNEXPECTED_CANDLE_BOUNDARY"


@dataclass(frozen=True, slots=True)
class CandleReconciliation:
    instrument: IntradayInstrumentReference
    timeframe: IntradayTimeframe
    schedule: MarketDaySchedule
    observation_boundary: ObservationBoundary
    provenance: SourceProvenance
    expected_boundaries: tuple[CandleBoundary, ...]
    received_boundaries: tuple[CandleBoundary, ...]
    missing_boundaries: tuple[CandleBoundary, ...]
    duplicate_boundaries: tuple[CandleBoundary, ...]
    partial_current_boundary: CandleBoundary | None
    unexpected_provider_timestamps: tuple[datetime, ...]
    out_of_order: bool
    observations: tuple[GovernedCandle, ...]
    structural_candles: tuple[GovernedCandle, ...]
    availability: DataAvailability
    result: ReconciliationResult
    failures: tuple[ReconciliationFailure, ...]
    backfill_required: bool

    def __post_init__(self) -> None:
        invalid = (
            type(self.instrument) is not IntradayInstrumentReference
            or type(self.timeframe) is not IntradayTimeframe
            or type(self.schedule) is not MarketDaySchedule
            or type(self.observation_boundary) is not ObservationBoundary
            or type(self.provenance) is not SourceProvenance
            or type(self.result) is not ReconciliationResult
            or type(self.availability) is not DataAvailability
            or any(type(item) is not ReconciliationFailure for item in self.failures)
            or any(item.completion is not CandleCompletion.COMPLETE for item in self.structural_candles)
            or any(item not in self.observations for item in self.structural_candles)
            or (self.result is ReconciliationResult.COMPLETE and bool(self.failures))
            or (self.result is not ReconciliationResult.COMPLETE and bool(self.structural_candles))
            or (self.backfill_required != bool(self.missing_boundaries))
        )
        if invalid:
            raise ValueError("INTRADAY_CANDLE_RECONCILIATION_INVALID")


def provider_interval(timeframe: IntradayTimeframe) -> HistoricalInterval:
    if type(timeframe) is not IntradayTimeframe:
        raise ValueError("INTRADAY_TIMEFRAME_INVALID")
    return {
        IntradayTimeframe.DAILY: HistoricalInterval.DAY,
        IntradayTimeframe.ONE_HOUR: HistoricalInterval.SIXTY_MINUTE,
        IntradayTimeframe.FIFTEEN_MINUTES: HistoricalInterval.FIFTEEN_MINUTE,
        IntradayTimeframe.FIVE_MINUTES: HistoricalInterval.FIVE_MINUTE,
    }[timeframe]


def expected_candle_boundaries(
    schedule: MarketDaySchedule,
    timeframe: IntradayTimeframe,
) -> tuple[CandleBoundary, ...]:
    if type(schedule) is not MarketDaySchedule or type(timeframe) is not IntradayTimeframe:
        raise ValueError("INTRADAY_CANDLE_BOUNDARY_REQUEST_INVALID")
    if schedule.status is TradingDayStatus.NON_TRADING:
        return ()
    if timeframe is IntradayTimeframe.DAILY:
        return (
            CandleBoundary(
                trading_date=schedule.trading_date,
                session_id=schedule.session_id,
                timeframe=timeframe,
                start=schedule.windows[0].opens_at,
                end=schedule.windows[-1].closes_at,
            ),
        )
    result: list[CandleBoundary] = []
    span = timeframe.duration
    for window in schedule.windows:
        start = window.opens_at
        while start < window.closes_at:
            end = min(start + span, window.closes_at)
            result.append(
                CandleBoundary(
                    trading_date=schedule.trading_date,
                    session_id=schedule.session_id,
                    timeframe=timeframe,
                    start=start,
                    end=end,
                )
            )
            start = end
    return tuple(result)


def reconcile_provider_candles(
    *,
    instrument: IntradayInstrumentReference,
    timeframe: IntradayTimeframe,
    schedule: MarketDaySchedule,
    provider_candles: Sequence[HistoricalCandle],
    observed_at: datetime,
    provenance: SourceProvenance,
) -> CandleReconciliation:
    """Reconcile Provider observations without interpolation or assumed facts."""

    if (
        type(instrument) is not IntradayInstrumentReference
        or type(timeframe) is not IntradayTimeframe
        or type(schedule) is not MarketDaySchedule
        or isinstance(provider_candles, (str, bytes))
        or not isinstance(provider_candles, Sequence)
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
        or type(provenance) is not SourceProvenance
        or schedule.exchange != instrument.exchange
    ):
        raise ValueError("INTRADAY_CANDLE_RECONCILIATION_REQUEST_INVALID")
    boundary = ObservationBoundary(observed_at)
    expected = expected_candle_boundaries(schedule, timeframe)
    if schedule.status is TradingDayStatus.NON_TRADING:
        return _failed(
            instrument=instrument,
            timeframe=timeframe,
            schedule=schedule,
            observation_boundary=boundary,
            provenance=provenance,
            expected=expected,
            failure=ReconciliationFailure.NON_TRADING_DAY,
        )
    supplied = tuple(provider_candles)
    if any(type(item) is not HistoricalCandle for item in supplied):
        return _failed(
            instrument=instrument,
            timeframe=timeframe,
            schedule=schedule,
            observation_boundary=boundary,
            provenance=provenance,
            expected=expected,
            failure=ReconciliationFailure.MALFORMED_PROVIDER_CANDLE,
        )

    supplied_timestamps = tuple(item.timestamp for item in supplied)
    out_of_order = any(current < previous for previous, current in zip(supplied_timestamps, supplied_timestamps[1:]))
    matches: list[tuple[HistoricalCandle, CandleBoundary]] = []
    unexpected: list[datetime] = []
    for candle in supplied:
        matched = _match_boundary(candle, expected, timeframe)
        if matched is None:
            unexpected.append(candle.timestamp)
        else:
            matches.append((candle, matched))

    counts = Counter(item.start for _, item in matches)
    duplicates = tuple(item for item in expected if counts[item.start] > 1)
    received = tuple(item for item in expected if counts[item.start] > 0)
    eligible = tuple(item for item in expected if item.end <= observed_at.astimezone(item.end.tzinfo))
    missing = tuple(item for item in eligible if counts[item.start] == 0)
    partial = next(
        (
            item
            for item in expected
            if item.start <= observed_at.astimezone(item.start.tzinfo) < item.end
        ),
        None,
    )

    observations = tuple(
        _governed(
            instrument=instrument,
            candle=candle,
            candle_boundary=candle_boundary,
            observed_at=observed_at,
            provenance=provenance,
        )
        for candle, candle_boundary in matches
    )
    failures: list[ReconciliationFailure] = []
    if missing:
        failures.append(ReconciliationFailure.MISSING_CANDLE)
    if duplicates:
        failures.append(ReconciliationFailure.DUPLICATE_CANDLE)
    if out_of_order:
        failures.append(ReconciliationFailure.OUT_OF_ORDER_PROVIDER_DATA)
    if unexpected:
        failures.append(ReconciliationFailure.UNEXPECTED_CANDLE_BOUNDARY)
    complete = not failures
    return CandleReconciliation(
        instrument=instrument,
        timeframe=timeframe,
        schedule=schedule,
        observation_boundary=boundary,
        provenance=provenance,
        expected_boundaries=expected,
        received_boundaries=received,
        missing_boundaries=missing,
        duplicate_boundaries=duplicates,
        partial_current_boundary=partial,
        unexpected_provider_timestamps=tuple(unexpected),
        out_of_order=out_of_order,
        observations=observations,
        structural_candles=(
            tuple(item for item in observations if item.completion is CandleCompletion.COMPLETE)
            if complete
            else ()
        ),
        availability=DataAvailability.AVAILABLE if complete else DataAvailability.INCOMPLETE,
        result=ReconciliationResult.COMPLETE if complete else ReconciliationResult.DATA_INCOMPLETE,
        failures=tuple(failures),
        backfill_required=bool(missing),
    )


def _match_boundary(
    candle: HistoricalCandle,
    expected: tuple[CandleBoundary, ...],
    timeframe: IntradayTimeframe,
) -> CandleBoundary | None:
    if timeframe is IntradayTimeframe.DAILY:
        return next(
            (
                item
                for item in expected
                if candle.timestamp.astimezone(item.start.tzinfo).date() == item.trading_date
            ),
            None,
        )
    return next((item for item in expected if candle.timestamp == item.start), None)


def _governed(
    *,
    instrument: IntradayInstrumentReference,
    candle: HistoricalCandle,
    candle_boundary: CandleBoundary,
    observed_at: datetime,
    provenance: SourceProvenance,
) -> GovernedCandle:
    values = tuple(Decimal(str(value)) for value in (candle.open, candle.high, candle.low, candle.close))
    fields = {
        "canonical_instrument_id": instrument.canonical_instrument_id,
        "boundary": candle_boundary,
        "values": values,
        "volume": candle.volume,
        "provenance": provenance,
    }
    return GovernedCandle(
        candle_id=governed_candle_identity(**fields),
        canonical_instrument_id=instrument.canonical_instrument_id,
        boundary=candle_boundary,
        open=values[0],
        high=values[1],
        low=values[2],
        close=values[3],
        volume=candle.volume,
        completion=(CandleCompletion.COMPLETE if observed_at >= candle_boundary.end else CandleCompletion.INCOMPLETE),
        observation_boundary=ObservationBoundary(observed_at),
        provenance=provenance,
    )


def _failed(
    *,
    instrument: IntradayInstrumentReference,
    timeframe: IntradayTimeframe,
    schedule: MarketDaySchedule,
    observation_boundary: ObservationBoundary,
    provenance: SourceProvenance,
    expected: tuple[CandleBoundary, ...],
    failure: ReconciliationFailure,
) -> CandleReconciliation:
    return CandleReconciliation(
        instrument=instrument,
        timeframe=timeframe,
        schedule=schedule,
        observation_boundary=observation_boundary,
        provenance=provenance,
        expected_boundaries=expected,
        received_boundaries=(),
        missing_boundaries=(),
        duplicate_boundaries=(),
        partial_current_boundary=None,
        unexpected_provider_timestamps=(),
        out_of_order=False,
        observations=(),
        structural_candles=(),
        availability=DataAvailability.UNAVAILABLE,
        result=ReconciliationResult.UNAVAILABLE,
        failures=(failure,),
        backfill_required=False,
    )


__all__ = [
    "CandleReconciliation",
    "ReconciliationFailure",
    "ReconciliationResult",
    "expected_candle_boundaries",
    "provider_interval",
    "reconcile_provider_candles",
]
