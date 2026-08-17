"""Completed-Daily dataset orchestration for the Swing Phase 1 universe."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import (
    InstrumentRecord,
    InstrumentResolutionError,
)
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalDataError,
    HistoricalInterval,
)
from kronos.swing.universe import SwingUniverseAssetClass, SwingUniverseMember


MINIMUM_COMPLETED_DAILY_CANDLES = 25
OPERATIONAL_DAILY_HISTORY_DEPTH = 30
_REQUEST_CALENDAR_DAYS = 120
_KOLKATA = ZoneInfo("Asia/Kolkata")


class SwingDailyStatus(StrEnum):
    """Swing-level availability of one canonical Daily series."""

    READY = "READY"
    UNAVAILABLE = "UNAVAILABLE"


class SwingDailyFailure(StrEnum):
    """Sanitized per-member Daily dataset failures."""

    INSTRUMENT_UNAVAILABLE = "INSTRUMENT_UNAVAILABLE"
    HISTORICAL_DATA_UNAVAILABLE = "HISTORICAL_DATA_UNAVAILABLE"
    MALFORMED_CANDLE_SEQUENCE = "MALFORMED_CANDLE_SEQUENCE"
    INSUFFICIENT_COMPLETED_HISTORY = "INSUFFICIENT_COMPLETED_HISTORY"
    DATA_SOURCE_FAILURE = "DATA_SOURCE_FAILURE"


@dataclass(frozen=True, slots=True)
class SwingDailySeries:
    """One immutable canonical Swing subject and its completed Daily series."""

    canonical_identity: str
    asset_class: SwingUniverseAssetClass
    status: SwingDailyStatus
    candles: tuple[HistoricalCandle, ...]
    observation_boundary: datetime | None
    failure: SwingDailyFailure | None
    _analysis_instrument: InstrumentRecord | None = field(repr=False)

    def __post_init__(self) -> None:
        ready = self.status is SwingDailyStatus.READY
        if (
            type(self.canonical_identity) is not str
            or not self.canonical_identity
            or type(self.asset_class) is not SwingUniverseAssetClass
            or type(self.status) is not SwingDailyStatus
            or type(self.candles) is not tuple
            or any(type(candle) is not HistoricalCandle for candle in self.candles)
            or (ready and len(self.candles) < MINIMUM_COMPLETED_DAILY_CANDLES)
            or (ready and len(self.candles) > OPERATIONAL_DAILY_HISTORY_DEPTH)
            or (ready and self.observation_boundary != self.candles[-1].timestamp)
            or (ready and self.failure is not None)
            or (ready and type(self._analysis_instrument) is not InstrumentRecord)
            or (not ready and self.candles != ())
            or (not ready and self.observation_boundary is not None)
            or (not ready and type(self.failure) is not SwingDailyFailure)
            or (not ready and self._analysis_instrument is not None)
        ):
            raise ValueError("SWING_DAILY_SERIES_INVALID")


@dataclass(frozen=True, slots=True)
class SwingDailyDataset:
    """Deterministic immutable outcome for every requested Swing member."""

    history_depth: int
    records: tuple[SwingDailySeries, ...]

    def __post_init__(self) -> None:
        identities = tuple(record.canonical_identity for record in self.records)
        if (
            self.history_depth != OPERATIONAL_DAILY_HISTORY_DEPTH
            or type(self.records) is not tuple
            or not self.records
            or any(type(record) is not SwingDailySeries for record in self.records)
            or len(set(identities)) != len(identities)
        ):
            raise ValueError("SWING_DAILY_DATASET_INVALID")

    @property
    def requested_count(self) -> int:
        return len(self.records)

    @property
    def ready_count(self) -> int:
        return sum(record.status is SwingDailyStatus.READY for record in self.records)

    @property
    def unavailable_count(self) -> int:
        return self.requested_count - self.ready_count


def build_swing_daily_dataset(
    universe: tuple[SwingUniverseMember, ...],
    *,
    resolve_instrument: Callable[[SwingUniverseMember], InstrumentRecord],
    historical_candles: Callable[
        [HistoricalCandleRequest], Sequence[HistoricalCandle]
    ],
    now: datetime,
    market_calendar_publisher: MarketCalendarPublisher | None = None,
) -> SwingDailyDataset:
    """Build one complete per-member result without hiding isolated failures."""

    if (
        type(universe) is not tuple
        or len(universe) != 98
        or any(type(member) is not SwingUniverseMember for member in universe)
        or len({member.canonical_identity for member in universe}) != len(universe)
        or not callable(resolve_instrument)
        or not callable(historical_candles)
        or not _aware(now)
        or (
            market_calendar_publisher is not None
            and type(market_calendar_publisher) is not MarketCalendarPublisher
        )
    ):
        raise ValueError("SWING_DAILY_DATASET_REQUEST_INVALID")

    end = now.astimezone(UTC)
    start = end - timedelta(days=_REQUEST_CALENDAR_DAYS)
    records = tuple(
        _build_series(
            member,
            resolve_instrument=resolve_instrument,
            historical_candles=historical_candles,
            start=start,
            end=end,
            observed_at=now,
            market_calendar_publisher=market_calendar_publisher,
        )
        for member in universe
    )
    return SwingDailyDataset(OPERATIONAL_DAILY_HISTORY_DEPTH, records)


def _build_series(
    member: SwingUniverseMember,
    *,
    resolve_instrument: Callable[[SwingUniverseMember], InstrumentRecord],
    historical_candles: Callable[
        [HistoricalCandleRequest], Sequence[HistoricalCandle]
    ],
    start: datetime,
    end: datetime,
    observed_at: datetime,
    market_calendar_publisher: MarketCalendarPublisher | None,
) -> SwingDailySeries:
    try:
        instrument = resolve_instrument(member)
    except InstrumentResolutionError:
        return _unavailable(member, SwingDailyFailure.INSTRUMENT_UNAVAILABLE)
    except Exception:
        return _unavailable(member, SwingDailyFailure.DATA_SOURCE_FAILURE)
    if type(instrument) is not InstrumentRecord:
        return _unavailable(member, SwingDailyFailure.INSTRUMENT_UNAVAILABLE)

    try:
        supplied = historical_candles(
            HistoricalCandleRequest(
                instrument=instrument,
                start=start,
                end=end,
                interval=HistoricalInterval.DAY,
            )
        )
    except HistoricalDataError:
        return _unavailable(member, SwingDailyFailure.HISTORICAL_DATA_UNAVAILABLE)
    except Exception:
        return _unavailable(member, SwingDailyFailure.DATA_SOURCE_FAILURE)

    if isinstance(supplied, (str, bytes)) or not isinstance(supplied, Sequence):
        return _unavailable(member, SwingDailyFailure.MALFORMED_CANDLE_SEQUENCE)
    observations = tuple(supplied)
    if any(type(candle) is not HistoricalCandle for candle in observations):
        return _unavailable(member, SwingDailyFailure.MALFORMED_CANDLE_SEQUENCE)
    timestamps = tuple(candle.timestamp for candle in observations)
    if len(set(timestamps)) != len(timestamps) or any(
        current <= previous
        for previous, current in zip(timestamps, timestamps[1:])
    ):
        return _unavailable(member, SwingDailyFailure.MALFORMED_CANDLE_SEQUENCE)

    completed = tuple(
        candle for candle in observations
        if _daily_candle_completed(
            member,
            candle,
            observed_at,
            market_calendar_publisher,
        )
    )
    completed = completed[-OPERATIONAL_DAILY_HISTORY_DEPTH:]
    if len(completed) < MINIMUM_COMPLETED_DAILY_CANDLES:
        return _unavailable(
            member,
            SwingDailyFailure.INSUFFICIENT_COMPLETED_HISTORY,
        )
    return SwingDailySeries(
        canonical_identity=member.canonical_identity,
        asset_class=member.asset_class,
        status=SwingDailyStatus.READY,
        candles=completed,
        observation_boundary=completed[-1].timestamp,
        failure=None,
        _analysis_instrument=instrument,
    )


def _daily_candle_completed(
    member: SwingUniverseMember,
    candle: HistoricalCandle,
    observed_at: datetime,
    publisher: MarketCalendarPublisher | None,
) -> bool:
    """Use DOMAIN-008 for same-session completion; never admit a future bar."""

    candle_date = candle.timestamp.astimezone(_KOLKATA).date()
    observed_date = observed_at.astimezone(_KOLKATA).date()
    if candle_date < observed_date:
        return True
    if candle_date > observed_date or publisher is None:
        return False
    exchange = (
        "MCX"
        if member.asset_class is SwingUniverseAssetClass.MCX_COMMODITY
        else "NSE"
    )
    try:
        schedule = publisher.schedule(exchange, candle_date, observed_at=observed_at)
    except ValueError:
        return False
    return (
        schedule is not None
        and schedule.trading_date_completed(observed_at)
    )


def _unavailable(
    member: SwingUniverseMember,
    failure: SwingDailyFailure,
) -> SwingDailySeries:
    return SwingDailySeries(
        canonical_identity=member.canonical_identity,
        asset_class=member.asset_class,
        status=SwingDailyStatus.UNAVAILABLE,
        candles=(),
        observation_boundary=None,
        failure=failure,
        _analysis_instrument=None,
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "MINIMUM_COMPLETED_DAILY_CANDLES",
    "OPERATIONAL_DAILY_HISTORY_DEPTH",
    "SwingDailyDataset",
    "SwingDailyFailure",
    "SwingDailySeries",
    "SwingDailyStatus",
    "build_swing_daily_dataset",
]
