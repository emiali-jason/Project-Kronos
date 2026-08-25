"""One provider-neutral monitoring session shared by governed Swing consumers."""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Callable

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
)


class SharedSwingMonitoringHub:
    """Multiplex one authenticated read-only Provider session without authority."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._capability = None
        self._session = None
        self._registrations: dict[int, _SharedRegistration] = {}
        self._by_instrument: dict[InstrumentRecord, set[int]] = defaultdict(set)
        self._connection_listener: Callable[[MonitoringConnectionState], None] | None = None

    def set_connection_listener(
        self, listener: Callable[[MonitoringConnectionState], None]
    ) -> None:
        if not callable(listener):
            raise TypeError("SHARED_MONITORING_CONNECTION_LISTENER_INVALID")
        with self._lock:
            self._connection_listener = listener

    def open(self, capability: object, consumer: object) -> "_SharedRegistration":
        if getattr(capability, "active", False) is not True:
            raise ValueError("SHARED_MONITORING_CAPABILITY_UNAVAILABLE")
        if not all(callable(getattr(consumer, name, None)) for name in (
            "on_market_tick", "on_order_update", "on_connection_state",
        )):
            raise TypeError("SHARED_MONITORING_CONSUMER_INVALID")
        registration = _SharedRegistration(self, capability, consumer)
        with self._lock:
            self._registrations[id(registration)] = registration
        return registration

    @property
    def active_session_count(self) -> int:
        with self._lock:
            return 1 if self._session is not None else 0

    @property
    def subscription_count(self) -> int:
        with self._lock:
            return len(self._by_instrument)

    def subscription_reference_count(self, instrument: InstrumentRecord) -> int:
        """Return the number of governed consumers sharing one subscription."""

        if type(instrument) is not InstrumentRecord:
            raise TypeError("SHARED_MONITORING_INSTRUMENT_INVALID")
        with self._lock:
            return len(self._by_instrument.get(instrument, ()))

    def subscription_owner_identities(
        self, instrument: InstrumentRecord
    ) -> tuple[str, ...]:
        """Expose bounded ownership facts without exposing Provider objects."""

        if type(instrument) is not InstrumentRecord:
            raise TypeError("SHARED_MONITORING_INSTRUMENT_INVALID")
        with self._lock:
            return tuple(sorted(
                self._registrations[identity].owner_identity
                for identity in self._by_instrument.get(instrument, ())
                if identity in self._registrations
            ))

    def close(self) -> None:
        with self._lock:
            registrations = tuple(self._registrations.values())
        for registration in registrations:
            registration.disconnect()

    def _subscribe(
        self, registration: "_SharedRegistration", instruments: tuple[InstrumentRecord, ...]
    ) -> None:
        if not instruments or any(type(item) is not InstrumentRecord for item in instruments):
            raise ValueError("SHARED_MONITORING_SUBSCRIPTION_INVALID")
        with self._lock:
            if id(registration) not in self._registrations:
                raise ValueError("SHARED_MONITORING_REGISTRATION_CLOSED")
            registration._instruments.update(instruments)

    def _connect(self, registration: "_SharedRegistration") -> None:
        with self._lock:
            if registration._connected:
                return
            if self._capability is not None and self._capability is not registration._capability:
                raise ValueError("SHARED_MONITORING_CAPABILITY_MISMATCH")
            additions = tuple(
                instrument for instrument in registration._instruments
                if instrument not in self._by_instrument
            )
            for instrument in registration._instruments:
                self._by_instrument[instrument].add(id(registration))
            registration._connected = True
            if self._session is None:
                self._capability = registration._capability
                self._session = registration._capability.open_monitoring_session(self)
                first = tuple(self._by_instrument)
                self._session.subscribe(first)
                self._session.connect()
            elif additions:
                self._session.subscribe(additions)

    def _disconnect(self, registration: "_SharedRegistration") -> None:
        with self._lock:
            if id(registration) not in self._registrations:
                return
            self._registrations.pop(id(registration), None)
            removals = []
            for instrument in registration._instruments:
                identities = self._by_instrument.get(instrument)
                if identities is None:
                    continue
                identities.discard(id(registration))
                if not identities:
                    self._by_instrument.pop(instrument, None)
                    removals.append(instrument)
            session = self._session
            last = not self._registrations
            if last:
                self._session = None
                self._capability = None
            registration._connected = False
        if session is not None:
            if removals:
                session.unsubscribe(tuple(removals))
            if last:
                session.disconnect()

    def on_market_tick(self, tick: ProviderMarketTick) -> None:
        with self._lock:
            consumers = tuple(
                self._registrations[identity]._consumer
                for identity in self._by_instrument.get(tick.instrument, ())
                if identity in self._registrations
            )
        for consumer in consumers:
            consumer.on_market_tick(tick)

    def on_order_update(self, update: ProviderOrderUpdateEvidence) -> None:
        with self._lock:
            consumers = tuple(
                registration._consumer for registration in self._registrations.values()
                if registration._connected
            )
        for consumer in consumers:
            consumer.on_order_update(update)

    def on_connection_state(self, state: MonitoringConnectionState) -> None:
        with self._lock:
            listener = self._connection_listener
            consumers = tuple(
                registration._consumer for registration in self._registrations.values()
                if registration._connected
            )
        if listener is not None:
            listener(state)
        for consumer in consumers:
            consumer.on_connection_state(state)


class _SharedRegistration:
    def __init__(self, hub, capability, consumer) -> None:  # type: ignore[no-untyped-def]
        self._hub = hub
        self._capability = capability
        self._consumer = consumer
        self._instruments: set[InstrumentRecord] = set()
        self._connected = False

    @property
    def owner_identity(self) -> str:
        value = getattr(self._consumer, "owner_identity", type(self._consumer).__name__)
        return value if type(value) is str and value else "UNIDENTIFIED_CONSUMER"

    def subscribe(self, instruments: tuple[InstrumentRecord, ...]) -> None:
        self._hub._subscribe(self, instruments)

    def unsubscribe(self, _instruments: tuple[InstrumentRecord, ...]) -> None:
        # Registration ownership is exact; disconnect performs reference-counted removal.
        return None

    def connect(self) -> None:
        self._hub._connect(self)

    def disconnect(self) -> None:
        self._hub._disconnect(self)


__all__ = ["SharedSwingMonitoringHub"]
