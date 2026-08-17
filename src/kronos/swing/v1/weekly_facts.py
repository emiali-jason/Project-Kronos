"""NSE weekly SMA200 and pivot facts with no Discovery authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
import json
import math
import re

from kronos.swing.v1.models import PivotCandidate, PivotKind
from kronos.swing.run_identity import is_swing_analysis_run_id


NSE_WEEKLY_FACT_SCHEMA = "KRONOS-NSE-205-WEEK-FACTUAL-FOUNDATION-V1"
NSE_WEEKLY_FACT_AUTHORITY = "FACTUAL_ONLY_NO_DISCOVERY_AUTHORITY"
NSE_WEEKLY_REQUIRED_COUNT = 205
NSE_WEEKLY_SMA_PERIOD = 200
NSE_WEEKLY_SMA_COMPARISON_HORIZON = 5


class WeeklyFactAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class WeeklySmaDirection(StrEnum):
    RISING = "RISING"
    FALLING = "FALLING"
    FLAT = "FLAT"


class FactualPriceRelation(StrEnum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    AT = "AT"


class FactualPivotRelation(StrEnum):
    HIGHER = "HIGHER"
    LOWER = "LOWER"
    EQUAL = "EQUAL"


class FactualStructureCondition(StrEnum):
    RELATIONS_AVAILABLE = "RELATIONS_AVAILABLE"
    MIXED = "MIXED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class HistoricalDayRequestWindowFact:
    """One non-overlapping Provider DAY request and its factual result count."""

    start: datetime
    end: datetime
    result_count: int

    def __post_init__(self) -> None:
        if (
            not _aware(self.start)
            or not _aware(self.end)
            or self.start >= self.end
            or type(self.result_count) is not int
            or self.result_count < 0
        ):
            raise ValueError("NSE_WEEKLY_REQUEST_WINDOW_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class CompletedWeeklyBarFact:
    """One completed governed week constructed only from canonical DAY candles."""

    trading_week_identity: str
    observation_boundary: datetime
    source_start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    constituent_identities: tuple[str, ...]
    source_provider_identity: str
    source_market_data_boundary: datetime
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        prices = (self.open, self.high, self.low, self.close)
        if (
            not self.trading_week_identity
            or not _aware(self.observation_boundary)
            or not _aware(self.source_start)
            or self.source_start > self.observation_boundary
            or any(type(item) is not float or not math.isfinite(item) or item < 0.0 for item in prices)
            or self.high < max(self.open, self.low, self.close)
            or self.low > min(self.open, self.high, self.close)
            or type(self.volume) is not int
            or self.volume < 0
            or not self.constituent_identities
            or not self.source_provider_identity
            or not _aware(self.source_market_data_boundary)
            or not self.provenance
        ):
            raise ValueError("COMPLETED_WEEKLY_BAR_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class WeeklyPivotFacts:
    """Independent factual pivot relations for one approved radius."""

    radius: int
    preceding_high: PivotCandidate | None
    latest_high: PivotCandidate | None
    high_relation: FactualPivotRelation | None
    preceding_low: PivotCandidate | None
    latest_low: PivotCandidate | None
    low_relation: FactualPivotRelation | None
    condition: FactualStructureCondition

    def __post_init__(self) -> None:
        highs = (self.preceding_high, self.latest_high)
        lows = (self.preceding_low, self.latest_low)
        high_complete = all(item is not None for item in highs)
        low_complete = all(item is not None for item in lows)
        complete = high_complete and low_complete
        expected = (
            FactualStructureCondition.INCOMPLETE
            if not complete
            else FactualStructureCondition.RELATIONS_AVAILABLE
            if self.high_relation is self.low_relation
            else FactualStructureCondition.MIXED
        )
        if (
            self.radius not in {1, 2}
            or any(item is not None and item.kind is not PivotKind.HIGH for item in highs)
            or any(item is not None and item.kind is not PivotKind.LOW for item in lows)
            or (self.high_relation is not None) is not high_complete
            or (self.low_relation is not None) is not low_complete
            or self.condition is not expected
        ):
            raise ValueError("WEEKLY_PIVOT_FACTS_INVALID")


@dataclass(frozen=True, slots=True)
class NseWeeklyFactualFoundation:
    """Immutable NSE 205-week facts; never a context or candidate classification."""

    canonical_instrument: str
    provider: str
    provider_exchange: str
    provider_segment: str
    provider_trading_symbol: str
    provider_instrument_type: str
    run_identity: str
    availability: WeeklyFactAvailability
    unavailable_reason: str | None
    request_windows: tuple[HistoricalDayRequestWindowFact, ...]
    source_interval: str
    calendar_identity: str
    calendar_version: str
    calendar_publication_sha256: str
    predecessor_source_result_sha256: str | None
    completed_weekly_bars: tuple[CompletedWeeklyBarFact, ...]
    current_sma200: float | None
    prior_sma200_5w: float | None
    sma200_difference: float | None
    sma200_direction: WeeklySmaDirection | None
    latest_weekly_close: float | None
    latest_close_relation: FactualPriceRelation | None
    radius_2_structure: WeeklyPivotFacts | None
    radius_1_developing: WeeklyPivotFacts | None
    observation_boundary: datetime | None
    source_result_sha256: str
    authority: str = NSE_WEEKLY_FACT_AUTHORITY
    schema: str = NSE_WEEKLY_FACT_SCHEMA

    def __post_init__(self) -> None:
        available = self.availability is WeeklyFactAvailability.AVAILABLE
        values = (
            self.current_sma200,
            self.prior_sma200_5w,
            self.sma200_difference,
            self.sma200_direction,
            self.latest_weekly_close,
            self.latest_close_relation,
            self.radius_2_structure,
            self.radius_1_developing,
            self.observation_boundary,
        )
        numeric = (
            self.current_sma200,
            self.prior_sma200_5w,
            self.sma200_difference,
            self.latest_weekly_close,
        )
        if (
            not re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument)
            or not all((self.provider, self.provider_exchange, self.provider_segment, self.provider_trading_symbol))
            or not isinstance(self.provider_instrument_type, str)
            or not is_swing_analysis_run_id(self.run_identity)
            or self.provider_exchange != "NSE"
            or type(self.availability) is not WeeklyFactAvailability
            or type(self.request_windows) is not tuple
            or any(
                current.start.date() != previous.end.date() + timedelta(days=1)
                for previous, current in zip(self.request_windows, self.request_windows[1:])
            )
            or self.source_interval != "DAY"
            or not self.calendar_identity
            or not self.calendar_version
            or len(self.calendar_publication_sha256) != 64
            or (
                self.predecessor_source_result_sha256 is not None
                and len(self.predecessor_source_result_sha256) != 64
            )
            or type(self.completed_weekly_bars) is not tuple
            or len({item.trading_week_identity for item in self.completed_weekly_bars})
            != len(self.completed_weekly_bars)
            or any(
                current.observation_boundary <= previous.observation_boundary
                for previous, current in zip(self.completed_weekly_bars, self.completed_weekly_bars[1:])
            )
            or len(self.source_result_sha256) != 64
            or self.authority != NSE_WEEKLY_FACT_AUTHORITY
            or self.schema != NSE_WEEKLY_FACT_SCHEMA
            or (available and (self.unavailable_reason is not None or len(self.completed_weekly_bars) != NSE_WEEKLY_REQUIRED_COUNT or any(item is None for item in values)))
            or (
                available
                and (
                    any(type(item) is not float or not math.isfinite(item) for item in numeric)
                    or self.sma200_difference != self.current_sma200 - self.prior_sma200_5w  # type: ignore[operator]
                    or self.observation_boundary != self.completed_weekly_bars[-1].observation_boundary
                )
            )
            or (not available and (not self.unavailable_reason or any(item is not None for item in values)))
        ):
            raise ValueError("NSE_WEEKLY_FACTUAL_FOUNDATION_INVALID")


def source_result_sha256(value: object) -> str:
    """Hash factual source/result material with stable JSON encoding."""

    return sha256(
        json.dumps(_json_value(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _json_value(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _json_value(asdict(value))
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
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "CompletedWeeklyBarFact", "FactualPivotRelation", "FactualPriceRelation",
    "FactualStructureCondition", "HistoricalDayRequestWindowFact",
    "NSE_WEEKLY_FACT_AUTHORITY", "NSE_WEEKLY_FACT_SCHEMA",
    "NSE_WEEKLY_REQUIRED_COUNT", "NSE_WEEKLY_SMA_COMPARISON_HORIZON",
    "NSE_WEEKLY_SMA_PERIOD", "NseWeeklyFactualFoundation",
    "WeeklyFactAvailability", "WeeklyPivotFacts", "WeeklySmaDirection",
    "source_result_sha256",
]
