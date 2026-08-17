"""Versioned factual contracts for the Intraday V1 Slice-0/1 boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import re
from uuid import uuid4


INTRADAY_FACT_SCHEMA = "KRONOS-INTRADAY-V1-FACTS-V1"
_RUN_ID = re.compile(r"INTRADAY-RUN-[0-9A-F]{32}\Z")
_IDENTITY = re.compile(r"[A-Z0-9][A-Z0-9._:/ &+-]{0,127}\Z")


class IntradayTimeframe(StrEnum):
    DAILY = "1D"
    ONE_HOUR = "1H"
    FIFTEEN_MINUTES = "15M"
    FIVE_MINUTES = "5M"

    @property
    def duration(self) -> timedelta:
        return {
            IntradayTimeframe.DAILY: timedelta(days=1),
            IntradayTimeframe.ONE_HOUR: timedelta(hours=1),
            IntradayTimeframe.FIFTEEN_MINUTES: timedelta(minutes=15),
            IntradayTimeframe.FIVE_MINUTES: timedelta(minutes=5),
        }[self]


class DataAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPLETE = "INCOMPLETE"


class CandleCompletion(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ObservationBoundary:
    observed_at: datetime

    def __post_init__(self) -> None:
        if not _aware(self.observed_at):
            raise ValueError("INTRADAY_OBSERVATION_BOUNDARY_INVALID")


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    provider: str
    source_identity: str
    retrieved_at: datetime
    source_version: str

    def __post_init__(self) -> None:
        if (
            not _text(self.provider)
            or not _text(self.source_identity)
            or not _aware(self.retrieved_at)
            or not _text(self.source_version)
        ):
            raise ValueError("INTRADAY_SOURCE_PROVENANCE_INVALID")


@dataclass(frozen=True, slots=True)
class IntradayRun:
    run_id: str
    created_at: datetime
    observation_boundary: ObservationBoundary
    schema_identity: str = INTRADAY_FACT_SCHEMA

    def __post_init__(self) -> None:
        if (
            _RUN_ID.fullmatch(self.run_id) is None
            or not _aware(self.created_at)
            or type(self.observation_boundary) is not ObservationBoundary
            or self.created_at > self.observation_boundary.observed_at
            or self.schema_identity != INTRADAY_FACT_SCHEMA
        ):
            raise ValueError("INTRADAY_RUN_INVALID")


def create_intraday_run(
    *, created_at: datetime, observation_boundary: datetime
) -> IntradayRun:
    return IntradayRun(
        run_id=f"INTRADAY-RUN-{uuid4().hex.upper()}",
        created_at=created_at,
        observation_boundary=ObservationBoundary(observation_boundary),
    )


@dataclass(frozen=True, slots=True)
class IntradayInstrumentReference:
    """Product consumption reference to an already-governed Instrument mapping."""

    canonical_instrument_id: str
    exchange: str
    segment: str
    instrument_type: str
    provider: str
    provider_symbol: str
    provider_instrument_token: int = field(repr=False)
    tick_size: Decimal
    lot_size: int
    price_precision: int
    mapping_identity: str

    def __post_init__(self) -> None:
        tick = _decimal(self.tick_size)
        expected = instrument_mapping_identity(
            canonical_instrument_id=self.canonical_instrument_id,
            exchange=self.exchange,
            segment=self.segment,
            instrument_type=self.instrument_type,
            provider=self.provider,
            provider_symbol=self.provider_symbol,
            provider_instrument_token=self.provider_instrument_token,
            tick_size=tick,
            lot_size=self.lot_size,
            price_precision=self.price_precision,
        )
        if (
            not _identity(self.canonical_instrument_id)
            or any(
                not _text(value)
                for value in (
                    self.exchange,
                    self.segment,
                    self.instrument_type,
                    self.provider,
                    self.provider_symbol,
                )
            )
            or type(self.provider_instrument_token) is not int
            or self.provider_instrument_token <= 0
            or tick <= 0
            or type(self.lot_size) is not int
            or self.lot_size <= 0
            or type(self.price_precision) is not int
            or self.price_precision < 0
            or -tick.as_tuple().exponent > self.price_precision
            or self.mapping_identity != expected
        ):
            raise ValueError("INTRADAY_INSTRUMENT_REFERENCE_INVALID")
        object.__setattr__(self, "tick_size", tick)


def instrument_mapping_identity(
    *,
    canonical_instrument_id: str,
    exchange: str,
    segment: str,
    instrument_type: str,
    provider: str,
    provider_symbol: str,
    provider_instrument_token: int,
    tick_size: Decimal,
    lot_size: int,
    price_precision: int,
) -> str:
    payload = {
        "canonical_instrument_id": canonical_instrument_id,
        "exchange": exchange,
        "instrument_type": instrument_type,
        "lot_size": lot_size,
        "price_precision": price_precision,
        "provider": provider,
        "provider_instrument_token": provider_instrument_token,
        "provider_symbol": provider_symbol,
        "segment": segment,
        "tick_size": str(_decimal(tick_size)),
    }
    return f"INSTRUMENT-MAPPING-{_digest(payload)}"


@dataclass(frozen=True, slots=True)
class CandleBoundary:
    trading_date: date
    session_id: str
    timeframe: IntradayTimeframe
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if (
            type(self.trading_date) is not date
            or not _identity(self.session_id)
            or type(self.timeframe) is not IntradayTimeframe
            or not _aware(self.start)
            or not _aware(self.end)
            or self.start >= self.end
            or self.start.utcoffset() != self.end.utcoffset()
        ):
            raise ValueError("INTRADAY_CANDLE_BOUNDARY_INVALID")


@dataclass(frozen=True, slots=True)
class GovernedCandle:
    candle_id: str
    canonical_instrument_id: str
    boundary: CandleBoundary
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    completion: CandleCompletion
    observation_boundary: ObservationBoundary
    provenance: SourceProvenance
    schema_identity: str = INTRADAY_FACT_SCHEMA

    def __post_init__(self) -> None:
        values = tuple(_decimal(value) for value in (self.open, self.high, self.low, self.close))
        expected = governed_candle_identity(
            canonical_instrument_id=self.canonical_instrument_id,
            boundary=self.boundary,
            values=values,
            volume=self.volume,
            provenance=self.provenance,
        )
        if (
            not _identity(self.canonical_instrument_id)
            or type(self.boundary) is not CandleBoundary
            or any(value < 0 for value in values)
            or values[1] < max(values[0], values[2], values[3])
            or values[2] > min(values[0], values[1], values[3])
            or type(self.volume) is not int
            or self.volume < 0
            or type(self.completion) is not CandleCompletion
            or type(self.observation_boundary) is not ObservationBoundary
            or type(self.provenance) is not SourceProvenance
            or self.completion
            is not (
                CandleCompletion.COMPLETE
                if self.observation_boundary.observed_at >= self.boundary.end
                else CandleCompletion.INCOMPLETE
            )
            or self.candle_id != expected
            or self.schema_identity != INTRADAY_FACT_SCHEMA
        ):
            raise ValueError("INTRADAY_GOVERNED_CANDLE_INVALID")
        object.__setattr__(self, "open", values[0])
        object.__setattr__(self, "high", values[1])
        object.__setattr__(self, "low", values[2])
        object.__setattr__(self, "close", values[3])


def governed_candle_identity(
    *,
    canonical_instrument_id: str,
    boundary: CandleBoundary,
    values: tuple[Decimal, Decimal, Decimal, Decimal],
    volume: int,
    provenance: SourceProvenance,
) -> str:
    payload = {
        "boundary": {
            "end": boundary.end.isoformat(),
            "session_id": boundary.session_id,
            "start": boundary.start.isoformat(),
            "timeframe": boundary.timeframe.value,
            "trading_date": boundary.trading_date.isoformat(),
        },
        "canonical_instrument_id": canonical_instrument_id,
        "ohlcv": [*(str(value) for value in values), volume],
        "provenance": {
            "provider": provenance.provider,
            "source_identity": provenance.source_identity,
            "source_version": provenance.source_version,
        },
    }
    return f"INTRADAY-CANDLE-{_digest(payload)}"


def _digest(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _identity(value: object) -> bool:
    return isinstance(value, str) and _IDENTITY.fullmatch(value) is not None


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("DECIMAL_INVALID")
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise ValueError("DECIMAL_INVALID") from error
    if not result.is_finite():
        raise ValueError("DECIMAL_INVALID")
    return result


__all__ = [
    "CandleBoundary",
    "CandleCompletion",
    "DataAvailability",
    "GovernedCandle",
    "INTRADAY_FACT_SCHEMA",
    "IntradayInstrumentReference",
    "IntradayRun",
    "IntradayTimeframe",
    "ObservationBoundary",
    "SourceProvenance",
    "create_intraday_run",
    "governed_candle_identity",
    "instrument_mapping_identity",
]
