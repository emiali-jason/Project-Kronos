"""Factual governed DAY-to-1W and 60minute-to-4H aggregation.

This module owns no analytical state.  DOMAIN-008 schedules provide every
calendar/session boundary; the common implementation contains no market clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
import math

from kronos.market.schedule import (
    MarketAvailability,
    MarketSchedule,
    ScheduleFreshness,
    ScheduleIntegrity,
)
from kronos.provider.contracts.market_data import HistoricalCandle


DERIVED_TIMEFRAME_AGGREGATION_POLICY_ID = (
    "KRONOS-DERIVED-TIMEFRAME-AGGREGATION-V1"
)
DERIVED_TIMEFRAME_AGGREGATION_POLICY_VERSION = "1"


class DerivedTimeframe(StrEnum):
    WEEKLY = "1W"
    FOUR_HOUR = "4H"


class DerivedSourceTimeframe(StrEnum):
    DAY = "DAY"
    SIXTY_MINUTE = "60minute"


class DerivedBarStatus(StrEnum):
    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class DerivedBucketClass(StrEnum):
    FULL_DURATION = "FULL_DURATION"
    SESSION_REMAINDER = "SESSION_REMAINDER"


class OpenInterestAvailability(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class GovernedTradingWeek:
    """One explicit DOMAIN-008 exchange week; grouping is never inferred in UTC."""

    identity: str
    schedules: tuple[MarketSchedule, ...]

    def __post_init__(self) -> None:
        if (
            not self.identity
            or type(self.schedules) is not tuple
            or not self.schedules
            or any(type(item) is not MarketSchedule for item in self.schedules)
            or tuple(item.trading_date for item in self.schedules)
            != tuple(sorted(item.trading_date for item in self.schedules))
            or len({item.trading_date for item in self.schedules})
            != len(self.schedules)
            or len({item.market_identity for item in self.schedules}) != 1
            or len({item.calendar_identity for item in self.schedules}) != 1
            or len({item.calendar_version for item in self.schedules}) != 1
            or len({item.timezone for item in self.schedules}) != 1
            or any(not _usable_schedule(item) for item in self.schedules)
        ):
            raise ValueError("GOVERNED_TRADING_WEEK_INVALID")


@dataclass(frozen=True, slots=True)
class DerivedBarEvidence:
    """Provider-neutral derived OHLCV plus complete construction provenance."""

    canonical_instrument: str
    market_identity: str
    derived_timeframe: DerivedTimeframe
    source_timeframe: DerivedSourceTimeframe
    status: DerivedBarStatus
    calendar_identity: str
    calendar_version: str
    session_identity: str | None
    exchange_timezone: str
    derived_start: datetime
    derived_end: datetime
    actual_duration: timedelta
    bucket_class: DerivedBucketClass
    constituent_identities: tuple[str, ...]
    constituent_boundaries: tuple[tuple[datetime, datetime], ...]
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    open_interest_availability: OpenInterestAvailability
    open_interest: None
    source_provider_identity: str
    source_market_data_boundary: datetime
    freshness: str
    integrity: str
    provenance: tuple[str, ...]
    unavailable_reason: str | None = None
    aggregation_policy_identity: str = DERIVED_TIMEFRAME_AGGREGATION_POLICY_ID
    aggregation_policy_version: str = DERIVED_TIMEFRAME_AGGREGATION_POLICY_VERSION
    analytical_authority: str = "NONE"
    tradingview_equivalence_claimed: bool = False

    def __post_init__(self) -> None:
        complete = self.status is DerivedBarStatus.COMPLETE
        values = (self.open, self.high, self.low, self.close)
        if (
            not self.canonical_instrument
            or not self.market_identity
            or type(self.derived_timeframe) is not DerivedTimeframe
            or type(self.source_timeframe) is not DerivedSourceTimeframe
            or type(self.status) is not DerivedBarStatus
            or not self.calendar_identity
            or not self.calendar_version
            or not self.exchange_timezone
            or not _aware(self.derived_start)
            or not _aware(self.derived_end)
            or self.derived_start >= self.derived_end
            or self.actual_duration != self.derived_end - self.derived_start
            or self.actual_duration <= timedelta(0)
            or type(self.bucket_class) is not DerivedBucketClass
            or not self.constituent_identities
            or len(self.constituent_identities) != len(self.constituent_boundaries)
            or any(not _aware(start) or not _aware(end) or start >= end
                   for start, end in self.constituent_boundaries)
            or type(self.open_interest_availability) is not OpenInterestAvailability
            or self.open_interest is not None
            or not self.source_provider_identity
            or not _aware(self.source_market_data_boundary)
            or not self.freshness
            or not self.integrity
            or not self.provenance
            or self.aggregation_policy_identity
            != DERIVED_TIMEFRAME_AGGREGATION_POLICY_ID
            or self.aggregation_policy_version
            != DERIVED_TIMEFRAME_AGGREGATION_POLICY_VERSION
            or self.analytical_authority != "NONE"
            or self.tradingview_equivalence_claimed is not False
            or complete != (self.unavailable_reason is None)
            or complete != all(_finite(value) for value in values)
            or complete != (type(self.volume) is int and self.volume >= 0)
            or (
                complete
                and (
                    self.high < max(self.open, self.low, self.close)  # type: ignore[arg-type]
                    or self.low > min(self.open, self.high, self.close)  # type: ignore[arg-type]
                )
            )
            or (
                not complete
                and (any(value is not None for value in values) or self.volume is not None)
            )
            or (
                self.derived_timeframe is DerivedTimeframe.WEEKLY
                and (
                    self.source_timeframe is not DerivedSourceTimeframe.DAY
                    or self.session_identity is not None
                    or self.bucket_class is not DerivedBucketClass.FULL_DURATION
                )
            )
            or (
                self.derived_timeframe is DerivedTimeframe.FOUR_HOUR
                and (
                    self.source_timeframe is not DerivedSourceTimeframe.SIXTY_MINUTE
                    or not self.session_identity
                    or self.actual_duration > timedelta(hours=4)
                )
            )
        ):
            raise ValueError("DERIVED_BAR_EVIDENCE_INVALID")

    @property
    def partial_session_bucket(self) -> bool:
        return self.bucket_class is DerivedBucketClass.SESSION_REMAINDER


def derive_weekly_bar(
    *,
    canonical_instrument: str,
    trading_week: GovernedTradingWeek,
    daily_candles: tuple[HistoricalCandle, ...],
    source_provider_identity: str,
    source_market_data_boundary: datetime,
    observed_at: datetime,
) -> DerivedBarEvidence | None:
    """Return a complete/unavailable governed week, or exclude an open week."""

    if (
        not canonical_instrument
        or type(trading_week) is not GovernedTradingWeek
        or type(daily_candles) is not tuple
        or any(type(item) is not HistoricalCandle for item in daily_candles)
        or not source_provider_identity
        or not _aware(source_market_data_boundary)
        or not _aware(observed_at)
    ):
        raise ValueError("WEEKLY_AGGREGATION_REQUEST_INVALID")
    schedules = trading_week.schedules
    final_close = schedules[-1].windows[-1].window_close
    if observed_at < final_close:
        return None
    by_date = {item.timestamp.astimezone(final_close.tzinfo).date(): item for item in daily_candles}
    if len(by_date) != len(daily_candles):
        raise ValueError("WEEKLY_SOURCE_SEQUENCE_INVALID")
    expected_dates = tuple(item.trading_date for item in schedules)
    supplied = tuple(by_date.get(item) for item in expected_dates)
    boundaries = tuple(
        (item.windows[0].window_open, item.windows[-1].window_close)
        for item in schedules
    )
    common = _common(
        canonical_instrument,
        schedules[0],
        DerivedTimeframe.WEEKLY,
        DerivedSourceTimeframe.DAY,
        None,
        schedules[0].windows[0].window_open,
        final_close,
        DerivedBucketClass.FULL_DURATION,
        tuple(f"DAY:{item.isoformat()}" for item in expected_dates),
        boundaries,
        source_provider_identity,
        source_market_data_boundary,
        trading_week.identity,
    )
    if any(item is None for item in supplied):
        return DerivedBarEvidence(
            **common,
            status=DerivedBarStatus.UNAVAILABLE,
            open=None,
            high=None,
            low=None,
            close=None,
            volume=None,
            integrity="INCOMPLETE",
            unavailable_reason="EXPECTED_DAILY_CONSTITUENT_MISSING",
        )
    return _complete(common, tuple(item for item in supplied if item is not None))


def derive_session_four_hour_bars(
    *,
    canonical_instrument: str,
    schedule: MarketSchedule,
    sixty_minute_candles: tuple[HistoricalCandle, ...],
    source_provider_identity: str,
    source_market_data_boundary: datetime,
    observed_at: datetime,
) -> tuple[DerivedBarEvidence, ...]:
    """Build completed session-aligned buckets, including a completed remainder."""

    if (
        not canonical_instrument
        or type(schedule) is not MarketSchedule
        or not _usable_schedule(schedule)
        or type(sixty_minute_candles) is not tuple
        or any(type(item) is not HistoricalCandle for item in sixty_minute_candles)
        or not source_provider_identity
        or not _aware(source_market_data_boundary)
        or not _aware(observed_at)
    ):
        raise ValueError("FOUR_HOUR_AGGREGATION_REQUEST_INVALID")
    source_by_start = {item.timestamp: item for item in sixty_minute_candles}
    if len(source_by_start) != len(sixty_minute_candles):
        raise ValueError("FOUR_HOUR_SOURCE_SEQUENCE_INVALID")
    result: list[DerivedBarEvidence] = []
    for window in schedule.windows:
        derived_session_identity = (
            schedule.session_identity
            if len(schedule.windows) == 1
            else window.identity
        )
        expected = _expected_hour_boundaries(window.window_open, window.window_close)
        for offset in range(0, len(expected), 4):
            boundaries = expected[offset : offset + 4]
            bucket_end = boundaries[-1][1]
            if observed_at < bucket_end:
                break
            supplied = tuple(source_by_start.get(start) for start, _ in boundaries)
            bucket_class = (
                DerivedBucketClass.FULL_DURATION
                if bucket_end - boundaries[0][0] == timedelta(hours=4)
                else DerivedBucketClass.SESSION_REMAINDER
            )
            common = _common(
                canonical_instrument,
                schedule,
                DerivedTimeframe.FOUR_HOUR,
                DerivedSourceTimeframe.SIXTY_MINUTE,
                derived_session_identity,
                boundaries[0][0],
                bucket_end,
                bucket_class,
                tuple(f"60minute:{start.isoformat()}" for start, _ in boundaries),
                boundaries,
                source_provider_identity,
                source_market_data_boundary,
                derived_session_identity,
            )
            if any(item is None for item in supplied):
                result.append(DerivedBarEvidence(
                    **common,
                    status=DerivedBarStatus.UNAVAILABLE,
                    open=None,
                    high=None,
                    low=None,
                    close=None,
                    volume=None,
                    integrity="INCOMPLETE",
                    unavailable_reason="EXPECTED_60MINUTE_CONSTITUENT_MISSING",
                ))
            else:
                result.append(_complete(common, tuple(item for item in supplied if item is not None)))
    return tuple(result)


def _expected_hour_boundaries(start: datetime, end: datetime) -> tuple[tuple[datetime, datetime], ...]:
    boundaries = []
    cursor = start
    while cursor < end:
        next_boundary = min(cursor + timedelta(hours=1), end)
        boundaries.append((cursor, next_boundary))
        cursor = next_boundary
    return tuple(boundaries)


def _common(
    canonical_instrument: str,
    schedule: MarketSchedule,
    derived_timeframe: DerivedTimeframe,
    source_timeframe: DerivedSourceTimeframe,
    session_identity: str | None,
    start: datetime | None,
    end: datetime,
    bucket_class: DerivedBucketClass,
    identities: tuple[str, ...],
    boundaries: tuple[tuple[datetime, datetime], ...],
    provider_identity: str,
    source_boundary: datetime,
    provenance_identity: str,
) -> dict[str, object]:
    assert start is not None
    return {
        "canonical_instrument": canonical_instrument,
        "market_identity": schedule.market_identity,
        "derived_timeframe": derived_timeframe,
        "source_timeframe": source_timeframe,
        "calendar_identity": schedule.calendar_identity,
        "calendar_version": schedule.calendar_version,
        "session_identity": session_identity,
        "exchange_timezone": schedule.timezone,
        "derived_start": start,
        "derived_end": end,
        "actual_duration": end - start,
        "bucket_class": bucket_class,
        "constituent_identities": identities,
        "constituent_boundaries": boundaries,
        "open_interest_availability": OpenInterestAvailability.UNAVAILABLE,
        "open_interest": None,
        "source_provider_identity": provider_identity,
        "source_market_data_boundary": source_boundary,
        "freshness": schedule.freshness_status.value,
        "provenance": (
            DERIVED_TIMEFRAME_AGGREGATION_POLICY_ID,
            schedule.identity,
            provenance_identity,
            provider_identity,
        ),
    }


def _complete(common: dict[str, object], candles: tuple[HistoricalCandle, ...]) -> DerivedBarEvidence:
    return DerivedBarEvidence(
        **common,
        status=DerivedBarStatus.COMPLETE,
        open=candles[0].open,
        high=max(item.high for item in candles),
        low=min(item.low for item in candles),
        close=candles[-1].close,
        volume=sum(item.volume for item in candles),
        integrity="VALID",
        unavailable_reason=None,
    )


def _usable_schedule(schedule: MarketSchedule) -> bool:
    return (
        schedule.market_availability is not MarketAvailability.UNAVAILABLE
        and schedule.freshness_status is ScheduleFreshness.CURRENT
        and schedule.integrity_status is ScheduleIntegrity.VALID
        and bool(schedule.windows)
    )


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _finite(value: object) -> bool:
    return type(value) is float and math.isfinite(value) and value >= 0.0


__all__ = [
    "DERIVED_TIMEFRAME_AGGREGATION_POLICY_ID",
    "DERIVED_TIMEFRAME_AGGREGATION_POLICY_VERSION",
    "DerivedBarEvidence",
    "DerivedBarStatus",
    "DerivedBucketClass",
    "DerivedSourceTimeframe",
    "DerivedTimeframe",
    "GovernedTradingWeek",
    "OpenInterestAvailability",
    "derive_session_four_hour_bars",
    "derive_weekly_bar",
]
