"""Provider-agnostic, read-only market-data contracts."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math
from typing import Protocol

from kronos.provider.contracts.instrument import InstrumentRecord


class HistoricalInterval(StrEnum):
    """Kite-supported historical intervals represented provider-neutrally."""

    MINUTE = "minute"
    THREE_MINUTE = "3minute"
    FIVE_MINUTE = "5minute"
    TEN_MINUTE = "10minute"
    FIFTEEN_MINUTE = "15minute"
    THIRTY_MINUTE = "30minute"
    SIXTY_MINUTE = "60minute"
    DAY = "day"


class HistoricalDataFailure(StrEnum):
    """Sanitized fail-closed historical-data outcomes."""

    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    INSTRUMENT_NOT_RESOLVED = "INSTRUMENT_NOT_RESOLVED"
    INVALID_REQUEST = "INVALID_REQUEST"
    MALFORMED_PROVIDER_DATA = "MALFORMED_PROVIDER_DATA"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"


class HistoricalDataError(RuntimeError):
    """Historical failure retaining no SDK exception or Provider payload."""

    def __init__(self, failure: HistoricalDataFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class LiveSnapshotFailure(StrEnum):
    """Sanitized fail-closed live snapshot outcomes."""

    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    INSTRUMENT_NOT_RESOLVED = "INSTRUMENT_NOT_RESOLVED"
    INVALID_REQUEST = "INVALID_REQUEST"
    MALFORMED_PROVIDER_DATA = "MALFORMED_PROVIDER_DATA"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"


class LiveSnapshotError(RuntimeError):
    """Live snapshot failure retaining no SDK exception or Provider payload."""

    def __init__(self, failure: LiveSnapshotFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class HistoricalCandleRequest:
    """One bounded historical request for an already resolved instrument."""

    instrument: InstrumentRecord
    start: datetime
    end: datetime
    interval: HistoricalInterval

    def __post_init__(self) -> None:
        if (
            type(self.instrument) is not InstrumentRecord
            or type(self.interval) is not HistoricalInterval
            or not _aware(self.start)
            or not _aware(self.end)
            or self.start >= self.end
        ):
            raise ValueError("HISTORICAL_CANDLE_REQUEST_INVALID")


@dataclass(frozen=True, slots=True)
class HistoricalCandle:
    """Validated market observation containing no Provider implementation data."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def __post_init__(self) -> None:
        prices = (self.open, self.high, self.low, self.close)
        if (
            not _aware(self.timestamp)
            or any(
                type(value) is not float or not math.isfinite(value)
                for value in prices
            )
            or any(value < 0.0 for value in prices)
            or self.high < max(self.open, self.low, self.close)
            or self.low > min(self.open, self.high, self.close)
            or type(self.volume) is not int
            or self.volume < 0
        ):
            raise ValueError("HISTORICAL_CANDLE_INVALID")


@dataclass(frozen=True, slots=True)
class OhlcValues:
    """Provider-neutral daily OHLC values; close is the prior session close."""

    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        values = (self.open, self.high, self.low, self.close)
        if (
            any(
                type(value) is not float or not math.isfinite(value)
                for value in values
            )
            or any(value < 0.0 for value in values)
            or self.high < max(self.open, self.low)
            or self.low > min(self.open, self.high)
        ):
            raise ValueError("OHLC_VALUES_INVALID")


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    """Provider-neutral full quote subset for one resolved instrument."""

    instrument: InstrumentRecord
    timestamp: datetime
    last_price: float
    volume: int | None
    ohlc: OhlcValues

    def __post_init__(self) -> None:
        if (
            type(self.instrument) is not InstrumentRecord
            or not _aware(self.timestamp)
            or not _valid_price(self.last_price)
            or (
                self.volume is not None
                and (type(self.volume) is not int or self.volume < 0)
            )
            or type(self.ohlc) is not OhlcValues
        ):
            raise ValueError("QUOTE_SNAPSHOT_INVALID")


@dataclass(frozen=True, slots=True)
class LtpSnapshot:
    """Provider-neutral last-traded-price snapshot for one resolved instrument."""

    instrument: InstrumentRecord
    last_price: float

    def __post_init__(self) -> None:
        if type(self.instrument) is not InstrumentRecord or not _valid_price(
            self.last_price
        ):
            raise ValueError("LTP_SNAPSHOT_INVALID")


@dataclass(frozen=True, slots=True)
class OhlcSnapshot:
    """Provider-neutral OHLC snapshot for one resolved instrument."""

    instrument: InstrumentRecord
    last_price: float
    ohlc: OhlcValues

    def __post_init__(self) -> None:
        if (
            type(self.instrument) is not InstrumentRecord
            or not _valid_price(self.last_price)
            or type(self.ohlc) is not OhlcValues
        ):
            raise ValueError("OHLC_SNAPSHOT_INVALID")


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _valid_price(value: object) -> bool:
    return type(value) is float and math.isfinite(value) and value >= 0.0


class MarketDataProvider(Protocol):
    """Contract for provider market-data capabilities."""

    def historical_candles(
        self,
        request: HistoricalCandleRequest,
    ) -> tuple[HistoricalCandle, ...]:
        """Return validated candles for one resolved instrument."""

    def quote(self, instrument: InstrumentRecord) -> QuoteSnapshot:
        """Return one validated full quote subset."""

    def ltp(self, instrument: InstrumentRecord) -> LtpSnapshot:
        """Return one validated last-traded-price snapshot."""

    def ohlc(self, instrument: InstrumentRecord) -> OhlcSnapshot:
        """Return one validated OHLC snapshot."""


__all__ = [
    "HistoricalCandle",
    "HistoricalCandleRequest",
    "HistoricalDataError",
    "HistoricalDataFailure",
    "HistoricalInterval",
    "LiveSnapshotError",
    "LiveSnapshotFailure",
    "LtpSnapshot",
    "MarketDataProvider",
    "OhlcSnapshot",
    "OhlcValues",
    "QuoteSnapshot",
]
