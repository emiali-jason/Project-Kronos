"""Provider-neutral factual monitoring contracts.

These contracts carry market and optional order evidence only.  They grant no
entry, lifecycle, Sponsor-decision, position-changing, or broker authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from kronos.provider.contracts.instrument import InstrumentRecord


class MonitoringConnectionState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"


class MonitoringFailure(StrEnum):
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    INSTRUMENT_NOT_RESOLVED = "INSTRUMENT_NOT_RESOLVED"
    INVALID_REQUEST = "INVALID_REQUEST"
    MALFORMED_PROVIDER_DATA = "MALFORMED_PROVIDER_DATA"
    INSTRUMENT_BINDING_MISMATCH = "INSTRUMENT_BINDING_MISMATCH"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class MonitoringError(RuntimeError):
    """Sanitized monitoring failure containing no Provider internals."""

    def __init__(self, failure: MonitoringFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class ProviderMarketTick:
    """One normalized factual Kite market observation."""

    instrument: InstrumentRecord
    last_price: Decimal
    observed_at: datetime
    received_at: datetime
    source: str
    connection_id: str
    source_sequence: int | None
    previous_interval_available: bool
    session_continuous: bool
    ordering_deterministic: bool
    recovered: bool = False

    def __post_init__(self) -> None:
        price = _decimal(self.last_price)
        object.__setattr__(self, "last_price", price)
        if (
            type(self.instrument) is not InstrumentRecord
            or price < 0
            or not _aware(self.observed_at)
            or not _aware(self.received_at)
            or self.observed_at > self.received_at
            or self.source != "KITE_CONNECT_WEBSOCKET"
            or not _identity(self.connection_id)
            or (
                self.source_sequence is not None
                and (type(self.source_sequence) is not int or self.source_sequence < 0)
            )
            or type(self.previous_interval_available) is not bool
            or type(self.session_continuous) is not bool
            or type(self.ordering_deterministic) is not bool
            or type(self.recovered) is not bool
        ):
            raise ValueError("PROVIDER_MARKET_TICK_INVALID")


@dataclass(frozen=True, slots=True)
class ProviderOrderUpdateEvidence:
    """Optional factual order evidence for the Sponsor-position branch only."""

    order_id: str
    instrument: InstrumentRecord
    status: str
    side: str
    filled_quantity: Decimal
    average_price: Decimal | None
    observed_at: datetime
    received_at: datetime
    source: str

    def __post_init__(self) -> None:
        quantity = _decimal(self.filled_quantity)
        price = None if self.average_price is None else _decimal(self.average_price)
        object.__setattr__(self, "filled_quantity", quantity)
        object.__setattr__(self, "average_price", price)
        if (
            not _identity(self.order_id)
            or type(self.instrument) is not InstrumentRecord
            or not _identity(self.status)
            or self.side not in {"BUY", "SELL"}
            or quantity < 0
            or (price is not None and price < 0)
            or not _aware(self.observed_at)
            or not _aware(self.received_at)
            or self.observed_at > self.received_at
            or self.source != "KITE_CONNECT_ORDER_UPDATE"
        ):
            raise ValueError("PROVIDER_ORDER_UPDATE_INVALID")


@dataclass(frozen=True, slots=True)
class MonitoringDisconnect:
    disconnected_at: datetime
    last_accepted_observation_at: datetime | None
    affected_instruments: tuple[InstrumentRecord, ...]
    reconnected_at: datetime | None = None
    first_post_reconnect_observation_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            not _aware(self.disconnected_at)
            or (
                self.last_accepted_observation_at is not None
                and not _aware(self.last_accepted_observation_at)
            )
            or any(type(item) is not InstrumentRecord for item in self.affected_instruments)
            or (self.reconnected_at is not None and not _aware(self.reconnected_at))
            or (
                self.first_post_reconnect_observation_at is not None
                and not _aware(self.first_post_reconnect_observation_at)
            )
            or (
                self.first_post_reconnect_observation_at is not None
                and self.reconnected_at is None
            )
        ):
            raise ValueError("MONITORING_DISCONNECT_INVALID")


@dataclass(frozen=True, slots=True)
class RecoveredMarketInterval:
    """Authoritative Provider reconstruction for one disconnected interval."""

    instrument: InstrumentRecord
    started_at: datetime
    ended_at: datetime
    observations: tuple[ProviderMarketTick, ...]
    source: str
    granularity: str
    authoritative_ordering: bool

    def __post_init__(self) -> None:
        if (
            type(self.instrument) is not InstrumentRecord
            or not _aware(self.started_at)
            or not _aware(self.ended_at)
            or self.started_at >= self.ended_at
            or not self.observations
            or any(
                type(item) is not ProviderMarketTick
                or item.instrument != self.instrument
                or not item.recovered
                or item.observed_at < self.started_at
                or item.observed_at > self.ended_at
                for item in self.observations
            )
            or not _identity(self.source)
            or not _identity(self.granularity)
            or type(self.authoritative_ordering) is not bool
        ):
            raise ValueError("RECOVERED_MARKET_INTERVAL_INVALID")


class MonitoringConsumer(Protocol):
    def on_market_tick(self, tick: ProviderMarketTick) -> None:
        """Consume one normalized market fact."""

    def on_order_update(self, update: ProviderOrderUpdateEvidence) -> None:
        """Consume optional Sponsor-position evidence."""

    def on_connection_state(self, state: MonitoringConnectionState) -> None:
        """Observe sanitized transport state."""


class ReadOnlyMonitoringSession(Protocol):
    @property
    def state(self) -> MonitoringConnectionState: ...

    @property
    def subscriptions(self) -> tuple[InstrumentRecord, ...]: ...

    @property
    def last_disconnect(self) -> MonitoringDisconnect | None: ...

    def connect(self) -> None: ...

    def subscribe(self, instruments: tuple[InstrumentRecord, ...]) -> None: ...

    def unsubscribe(self, instruments: tuple[InstrumentRecord, ...]) -> None: ...

    def disconnect(self) -> None: ...


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _identity(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _decimal(value: object) -> Decimal:
    if type(value) not in {Decimal, int, str, float} or isinstance(value, bool):
        raise ValueError("MONITORING_DECIMAL_INVALID")
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise ValueError("MONITORING_DECIMAL_INVALID") from error
    if not result.is_finite():
        raise ValueError("MONITORING_DECIMAL_INVALID")
    return result


__all__ = [
    "MonitoringConnectionState",
    "MonitoringConsumer",
    "MonitoringDisconnect",
    "MonitoringError",
    "MonitoringFailure",
    "ProviderMarketTick",
    "ProviderOrderUpdateEvidence",
    "ReadOnlyMonitoringSession",
    "RecoveredMarketInterval",
]
