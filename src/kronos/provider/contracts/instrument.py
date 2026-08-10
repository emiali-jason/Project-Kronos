"""Provider-agnostic, read-only instrument contracts."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol


class InstrumentKind(StrEnum):
    """The bounded representative instrument classes required by V2."""

    NSE_EQUITY = "NSE_EQUITY"
    NSE_INDEX = "NSE_INDEX"
    MCX_FUTURE = "MCX_FUTURE"
    CDS_FUTURE = "CDS_FUTURE"


class InstrumentResolutionFailure(StrEnum):
    """Sanitized deterministic resolution failures."""

    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    INVALID_REQUEST = "INVALID_REQUEST"
    MALFORMED_PROVIDER_DATA = "MALFORMED_PROVIDER_DATA"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"


class InstrumentResolutionError(RuntimeError):
    """Fail-closed error that retains no Provider record or token."""

    def __init__(self, failure: InstrumentResolutionFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class InstrumentRecord:
    """Normalized non-sensitive instrument identity without Provider token."""

    provider: str
    exchange: str
    segment: str
    trading_symbol: str
    name: str
    instrument_type: str
    expiry: date | None

    def __post_init__(self) -> None:
        required = (
            self.provider,
            self.exchange,
            self.segment,
            self.trading_symbol,
        )
        if any(not value or value != value.strip() for value in required):
            raise ValueError("INSTRUMENT_RECORD_INVALID")
        if not isinstance(self.name, str) or self.name != self.name.strip():
            raise ValueError("INSTRUMENT_RECORD_INVALID")
        if self.instrument_type != self.instrument_type.strip():
            raise ValueError("INSTRUMENT_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class InstrumentResolutionRequest:
    """Exact deterministic lookup requested by an application caller."""

    kind: InstrumentKind
    symbol: str
    as_of: date

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not InstrumentKind
            or type(self.as_of) is not date
            or not self.symbol
            or self.symbol != self.symbol.strip().upper()
        ):
            raise ValueError("INSTRUMENT_RESOLUTION_REQUEST_INVALID")


class InstrumentProvider(Protocol):
    """Contract for provider instrument capabilities."""

    def retrieve(self, exchange: str) -> tuple[InstrumentRecord, ...]:
        """Retrieve one normalized exchange-scoped Instrument Master."""

    def resolve(self, request: InstrumentResolutionRequest) -> InstrumentRecord:
        """Resolve exactly one representative instrument or fail closed."""

    def resolve_from_records(
        self,
        records: tuple[InstrumentRecord, ...],
        request: InstrumentResolutionRequest,
    ) -> InstrumentRecord:
        """Resolve from one previously retrieved normalized exchange master."""


__all__ = [
    "InstrumentKind",
    "InstrumentProvider",
    "InstrumentRecord",
    "InstrumentResolutionError",
    "InstrumentResolutionFailure",
    "InstrumentResolutionRequest",
]
