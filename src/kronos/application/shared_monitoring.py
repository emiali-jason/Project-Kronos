"""One provider-neutral monitoring session shared by governed Swing consumers."""

from __future__ import annotations

from kronos.common.maintenance import expected_transport_close

from collections import defaultdict
from threading import Lock, RLock
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
        self.maintenance_governance = None
        self._connection_listener: Callable[[MonitoringConnectionState], None] | None = None
        self._connection_state: MonitoringConnectionState | None = None
        self._latest_ticks: dict[InstrumentRecord, ProviderMarketTick] = {}
        self._last_interruption = None
        self._transport_lock = Lock()
        self._ownership_generation = 0
        self._session_generation = None
        self._subscribed: set[InstrumentRecord] = set()
        self._retired_session = None
        self._transport_cleanup_state = "COMPLETE"
        self._transport_cleanup_failure = ""
        self._cleanup_instruments: set[InstrumentRecord] = set()
        self._release_counts = dict(shared_subscription_retained=0,
            final_owner_subscription_releases=0, already_detached=0,
            stale_callbacks_rejected=0, cleanup_failures=0)

    def set_connection_listener(
        self, listener: Callable[[MonitoringConnectionState], None]
    ) -> None:
        if not callable(listener):
            raise TypeError("SHARED_MONITORING_CONNECTION_LISTENER_INVALID")
        with self._lock:
            self._connection_listener = listener

    def open(self, capability: object, consumer: object) -> "_SharedRegistration":
        if self.maintenance_governance is not None:
            self.maintenance_governance.require_operations()
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

    @property
    def connection_state(self) -> MonitoringConnectionState | None:
        """Expose actual WebSocket transport state without inferring from REST."""

        with self._lock:
            return self._connection_state

    @property
    def latest_market_ticks(self) -> tuple[ProviderMarketTick, ...]:
        """Return current process-local factual ticks for presentation only."""

        with self._lock:
            return tuple(
                self._latest_ticks[instrument]
                for instrument in sorted(
                    self._latest_ticks,
                    key=lambda item: (
                        item.exchange, item.segment, item.trading_symbol,
                    ),
                )
            )

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

    def status_document(self):
        """Bounded factual snapshot; no calls into Provider or owner consumers."""
        with self._lock:
            def instrument(item):
                return {"exchange": item.exchange, "segment": item.segment,
                        "trading_symbol": item.trading_symbol}
            owners = []
            for registration in self._registrations.values():
                scopes = []
                for item in sorted(registration._instruments, key=lambda i: (i.exchange, i.segment, i.trading_symbol)):
                    tick = self._latest_ticks.get(item)
                    scopes.append({**instrument(item), "latest_observation": None if tick is None else {
                        "connection_id": tick.connection_id, "observed_at": tick.observed_at.isoformat(),
                        "received_at": tick.received_at.isoformat(), "source_sequence": tick.source_sequence,
                        "session_continuous": tick.session_continuous,
                        "previous_interval_available": tick.previous_interval_available,
                        "ordering_deterministic": tick.ordering_deterministic, "recovered": tick.recovered}})
                transport_active = (
                    registration._connected
                    and self._session is not None
                    and self._capability is registration._capability
                    and bool(registration._instruments)
                    and registration._instruments.issubset(self._subscribed)
                    and all(
                        id(registration) in self._by_instrument.get(item, ())
                        for item in registration._instruments
                    )
                )
                owners.append({"owner_identity": registration.owner_identity,
                    "registered": True, "subscribed": registration._connected,
                    "transport_active": transport_active, "instruments": scopes})
            cleanup_instruments = tuple(sorted(
                self._cleanup_instruments,
                key=lambda i: (i.exchange, i.segment, i.trading_symbol),
            ))
            return {"schema": "KRONOS-SHARED-MONITORING-STATUS/1.0.0",
                "hub_state": "REGISTERED" if owners else "IDLE",
                "transport_state": (self._connection_state.value if self._connection_state is not None
                                    else "CONNECTING" if self._session is not None else "IDLE"),
                "session_count": int(self._session is not None) + int(self._retired_session is not None),
                "active_session_count": int(self._session is not None),
                "owner_count": len(owners), "subscription_count": len(self._by_instrument),
                "subscriptions": [instrument(i) for i in sorted(self._by_instrument,
                    key=lambda i: (i.exchange, i.segment, i.trading_symbol))],
                "owners": owners, "last_interruption": self._last_interruption,
                "release_counts": dict(self._release_counts),
                "transport_cleanup": {
                    "state": self._transport_cleanup_state,
                    "retired_session_owned": self._retired_session is not None,
                    "subscription_count": len(cleanup_instruments),
                    "subscriptions": [instrument(i) for i in cleanup_instruments],
                    "failure": self._transport_cleanup_failure,
                },
                "continuity_authority": "PER_OWNER_LIFECYCLE_EVIDENCE_NOT_RECONSTRUCTED"}

    def release_status(self):
        with self._lock:
            return dict(self._release_counts)

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
            connected = registration._connected
            if connected:
                for instrument in instruments:
                    self._by_instrument[instrument].add(id(registration))
                self._ownership_generation += 1
        if connected:
            self._reconcile_transport()

    def _connect(self, registration: "_SharedRegistration") -> None:
        with self._lock:
            if self._registrations.get(id(registration)) is not registration:
                raise ValueError("SHARED_MONITORING_REGISTRATION_CLOSED")
            if registration._connected:
                return
            if self._transport_cleanup_state == "FAILED":
                raise ValueError("SHARED_MONITORING_CLEANUP_UNRESOLVED")
            if any(owner._connected and owner._capability is not registration._capability
                   for owner in self._registrations.values()):
                raise ValueError("SHARED_MONITORING_CAPABILITY_MISMATCH")
            for instrument in registration._instruments:
                self._by_instrument[instrument].add(id(registration))
            registration._connected = True
            self._ownership_generation += 1
        self._reconcile_transport()

    def _count_release(self, name, count=1):
        self._release_counts[name] = min((1 << 63) - 1, self._release_counts[name] + count)

    def _reconcile_transport(self):
        """Drain ownership changes, never holding the state lock in Provider code.

        Contending/reentrant callers publish desired state and return. The one
        drainer reconciles each observed generation, including changes made
        while an external operation is in flight. This is event-driven work,
        not a timer/retry loop; no ownership history or per-request queue grows.
        """
        with self._lock:
            if not self._transport_lock.acquire(blocking=False):
                return
        deferred_error = None
        try:
            while True:
                with self._lock:
                    if self._transport_cleanup_state == "FAILED":
                        self._transport_lock.release()
                        return
                    generation = self._ownership_generation
                    desired = set(self._by_instrument)
                    capability = next((r._capability for r in self._registrations.values()
                                       if r._connected and r._instruments), None)
                    session, current_capability = self._session, self._capability
                    subscribed = set(self._subscribed)
                if session is not None and (not desired or capability is not current_capability):
                    with self._lock:
                        self._session = None
                        self._capability = None
                        self._session_generation = None
                        self._subscribed.clear()
                        self._retired_session = session
                        self._transport_cleanup_state = "RUNNING"
                        self._transport_cleanup_failure = ""
                        self._cleanup_instruments = set(subscribed)
                        self._connection_state = MonitoringConnectionState.DISCONNECTED
                        self._last_interruption = MonitoringConnectionState.DISCONNECTED.value
                    unsubscribe_error = None
                    try:
                        if subscribed:
                            session.unsubscribe(tuple(subscribed))
                    except BaseException as error:
                        unsubscribe_error = error
                    disconnect_error = None
                    try:
                        with expected_transport_close(self.maintenance_governance):
                            session.disconnect()
                    except BaseException as error:
                        disconnect_error = error
                    with self._lock:
                        if disconnect_error is None:
                            self._retired_session = None
                            self._transport_cleanup_state = "COMPLETE"
                            self._transport_cleanup_failure = ""
                            self._cleanup_instruments.clear()
                            self._count_release(
                                'final_owner_subscription_releases', len(subscribed)
                            )
                        else:
                            self._transport_cleanup_state = "FAILED"
                            self._transport_cleanup_failure = (
                                "SHARED_MONITORING_TRANSPORT_CLEANUP_FAILED"
                            )
                            self._count_release('cleanup_failures')
                    if disconnect_error is not None:
                        raise disconnect_error
                    if unsubscribe_error is not None:
                        deferred_error = unsubscribe_error
                    session = None
                if desired and session is None:
                    token = object()
                    session = capability.open_monitoring_session(_SessionCallbacks(self, token))
                    with self._lock:
                        self._session, self._capability = session, capability
                        self._session_generation = token
                        self._connection_state = None
                    try:
                        session.subscribe(tuple(desired))
                        with self._lock:
                            self._subscribed = set(desired)
                        session.connect()
                    except BaseException as activation_error:
                        with self._lock:
                            self._session = None
                            self._capability = None
                            self._session_generation = None
                            self._subscribed.clear()
                            self._retired_session = session
                            self._transport_cleanup_state = "RUNNING"
                            self._transport_cleanup_failure = ""
                            self._cleanup_instruments = set(desired)
                            self._connection_state = (
                                MonitoringConnectionState.DISCONNECTED
                            )
                            self._last_interruption = (
                                MonitoringConnectionState.DISCONNECTED.value
                            )
                        try:
                            session.unsubscribe(tuple(desired))
                        except BaseException:
                            pass
                        try:
                            with expected_transport_close(
                                self.maintenance_governance
                            ):
                                session.disconnect()
                        except BaseException:
                            with self._lock:
                                self._transport_cleanup_state = "FAILED"
                                self._transport_cleanup_failure = (
                                    "SHARED_MONITORING_TRANSPORT_CLEANUP_FAILED"
                                )
                                self._count_release('cleanup_failures')
                        else:
                            with self._lock:
                                self._retired_session = None
                                self._transport_cleanup_state = "COMPLETE"
                                self._transport_cleanup_failure = ""
                                self._cleanup_instruments.clear()
                        raise activation_error
                elif session is not None:
                    removals, additions = subscribed - desired, desired - subscribed
                    if removals:
                        with self._lock:
                            self._transport_cleanup_state = "RUNNING"
                            self._transport_cleanup_failure = ""
                            self._cleanup_instruments = set(removals)
                        try:
                            session.unsubscribe(tuple(removals))
                        except BaseException:
                            with self._lock:
                                self._transport_cleanup_state = "FAILED"
                                self._transport_cleanup_failure = (
                                    "SHARED_MONITORING_SUBSCRIPTION_CLEANUP_FAILED"
                                )
                                self._count_release('cleanup_failures')
                            raise
                        with self._lock:
                            self._subscribed.difference_update(removals)
                            self._transport_cleanup_state = "COMPLETE"
                            self._cleanup_instruments.clear()
                            self._count_release('final_owner_subscription_releases', len(removals))
                    if additions:
                        session.subscribe(tuple(additions))
                        with self._lock:
                            self._subscribed.update(additions)
                with self._lock:
                    if generation == self._ownership_generation:
                        if deferred_error is not None:
                            raise deferred_error
                        self._transport_lock.release()
                        return
        except BaseException:
            with self._lock:
                self._transport_lock.release()
            raise

    def _disconnect(self, registration: "_SharedRegistration") -> None:
        with self._lock:
            if id(registration) not in self._registrations:
                self._count_release('already_detached')
                return registration._detached_result
            self._registrations.pop(id(registration), None)
            removals = []
            retained = 0
            for instrument in registration._instruments:
                identities = self._by_instrument.get(instrument)
                if identities is None:
                    continue
                identities.discard(id(registration))
                if not identities:
                    self._by_instrument.pop(instrument, None)
                    self._latest_ticks.pop(instrument, None)
                    removals.append(instrument)
                else:
                    retained += 1
            self._count_release('shared_subscription_retained', retained)
            consumer = registration._consumer
            registration._connected = False
            registration._consumer = None
            registration._capability = None
            registration._instruments.clear()
            registration._detached_result = (len(removals), retained)
            self._ownership_generation += 1
        if self.maintenance_governance is not None and self.maintenance_governance.shutting_down:
            consumer.on_connection_state(MonitoringConnectionState.DISCONNECTED)
        self._reconcile_transport()
        return registration._detached_result

    def on_market_tick(self, tick: ProviderMarketTick, *, _generation=None) -> None:
        if self.maintenance_governance is not None and self.maintenance_governance.maintenance_active:
            return
        with self._lock:
            if _generation is not None and self._session_generation is not _generation:
                self._count_release('stale_callbacks_rejected')
                return
            if tick.instrument not in self._by_instrument:
                self._count_release('stale_callbacks_rejected')
                return
            self._latest_ticks[tick.instrument] = tick
            consumers = tuple(
                self._registrations[identity]._consumer
                for identity in self._by_instrument.get(tick.instrument, ())
                if identity in self._registrations
            )
        for consumer in consumers:
            consumer.on_market_tick(tick)

    def on_order_update(self, update: ProviderOrderUpdateEvidence, *, _generation=None) -> None:
        with self._lock:
            if _generation is not None and self._session_generation is not _generation:
                self._count_release('stale_callbacks_rejected')
                return
            consumers = tuple(
                registration._consumer for registration in self._registrations.values()
                if registration._connected
            )
        for consumer in consumers:
            consumer.on_order_update(update)

    def on_connection_state(self, state: MonitoringConnectionState, *, _generation=None) -> None:
        if type(state) is not MonitoringConnectionState:
            raise TypeError("SHARED_MONITORING_CONNECTION_STATE_INVALID")
        with self._lock:
            if _generation is not None and self._session_generation is not _generation:
                self._count_release('stale_callbacks_rejected')
                return
            self._connection_state = state
            if state is not MonitoringConnectionState.CONNECTED:
                self._last_interruption = state.value
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
        self._detached_result = (0, 0)

    @property
    def active(self) -> bool:
        """Current registration/subscription evidence, not a connection claim."""
        capability = self._capability
        if capability is None or getattr(capability, "active", False) is not True:
            return False
        with self._hub._lock:
            return (
                self._connected
                and self._hub._registrations.get(id(self)) is self
                and self._hub._session is not None
                and self._hub._capability is self._capability
                and self._capability is capability
                and bool(self._instruments)
                and self._instruments.issubset(self._hub._subscribed)
                and all(
                    id(self) in self._hub._by_instrument.get(instrument, ())
                    for instrument in self._instruments
                )
            )

    @property
    def connection_state(self) -> MonitoringConnectionState | None:
        """Only the shared session's observed callback state can be CONNECTED."""
        active = self.active
        with self._hub._lock:
            return (self._hub._connection_state if active
                    and self._hub._registrations.get(id(self)) is self else None)

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
        return self._hub._disconnect(self)


class _SessionCallbacks:
    """Fence a retired Provider session before dispatching to current owners."""
    def __init__(self, hub, generation):
        self._hub, self._generation = hub, generation

    def _dispatch(self, name, value):
        with self._hub._lock:
            if self._hub._session_generation is not self._generation:
                self._hub._count_release('stale_callbacks_rejected')
                return
        getattr(self._hub, name)(value, _generation=self._generation)

    def on_market_tick(self, value): self._dispatch('on_market_tick', value)
    def on_order_update(self, value): self._dispatch('on_order_update', value)
    def on_connection_state(self, value): self._dispatch('on_connection_state', value)


__all__ = ["SharedSwingMonitoringHub"]
