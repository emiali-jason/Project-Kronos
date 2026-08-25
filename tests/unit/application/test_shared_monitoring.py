from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
)


ONE = InstrumentRecord("KITE", "NSE", "NSE", "ONE", "ONE", "EQ", None)
TWO = InstrumentRecord("KITE", "NSE", "NSE", "TWO", "TWO", "EQ", None)
NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)


class Consumer:
    owner_identity = "TEST_CONSUMER"

    def __init__(self) -> None:
        self.ticks = []
        self.orders = []
        self.states = []

    def on_market_tick(self, tick): self.ticks.append(tick)  # type: ignore[no-untyped-def]
    def on_order_update(self, update): self.orders.append(update)  # type: ignore[no-untyped-def]
    def on_connection_state(self, state): self.states.append(state)  # type: ignore[no-untyped-def]


class Session:
    def __init__(self, consumer) -> None:  # type: ignore[no-untyped-def]
        self.consumer = consumer
        self.subscribed = []
        self.unsubscribed = []
        self.connections = 0
        self.disconnections = 0

    def subscribe(self, values): self.subscribed.append(values)  # type: ignore[no-untyped-def]
    def unsubscribe(self, values): self.unsubscribed.append(values)  # type: ignore[no-untyped-def]
    def connect(self): self.connections += 1
    def disconnect(self): self.disconnections += 1


class Capability:
    active = True

    def __init__(self) -> None:
        self.sessions = []

    def open_monitoring_session(self, consumer):  # type: ignore[no-untyped-def]
        value = Session(consumer)
        self.sessions.append(value)
        return value


def tick(instrument):  # type: ignore[no-untyped-def]
    return ProviderMarketTick(
        instrument, Decimal("100"), NOW, NOW, "KITE_CONNECT_WEBSOCKET",
        "CONNECTION-1", 1, True, True, True,
    )


def test_multiple_consumers_share_exactly_one_provider_session() -> None:
    capability = Capability()
    hub = SharedSwingMonitoringHub()
    one = hub.open(capability, Consumer())
    one.subscribe((ONE,))
    one.connect()
    two = hub.open(capability, Consumer())
    two.subscribe((TWO,))
    two.connect()
    assert len(capability.sessions) == 1
    assert hub.active_session_count == 1
    assert hub.subscription_count == 2
    assert capability.sessions[0].connections == 1


def test_ticks_route_only_to_exact_instrument_consumers() -> None:
    capability = Capability()
    hub = SharedSwingMonitoringHub()
    first, second = Consumer(), Consumer()
    for consumer, instrument in ((first, ONE), (second, TWO)):
        registration = hub.open(capability, consumer)
        registration.subscribe((instrument,))
        registration.connect()
    capability.sessions[0].consumer.on_market_tick(tick(ONE))
    assert len(first.ticks) == 1 and second.ticks == []
    assert hub.latest_market_ticks == (tick(ONE),)


def test_presentation_tick_cache_is_process_local_and_clears_with_last_owner() -> None:
    capability = Capability()
    hub = SharedSwingMonitoringHub()
    registration = hub.open(capability, Consumer())
    registration.subscribe((ONE,))
    registration.connect()
    capability.sessions[0].consumer.on_market_tick(tick(ONE))
    assert hub.latest_market_ticks[0].last_price == Decimal("100")
    registration.disconnect()
    assert hub.latest_market_ticks == ()


def test_shared_instrument_is_subscribed_once_and_fanned_out() -> None:
    capability = Capability()
    hub = SharedSwingMonitoringHub()
    values = (Consumer(), Consumer())
    registrations = []
    for consumer in values:
        registration = hub.open(capability, consumer)
        registration.subscribe((ONE,))
        registration.connect()
        registrations.append(registration)
    assert capability.sessions[0].subscribed == [(ONE,)]
    assert hub.subscription_reference_count(ONE) == 2
    assert hub.subscription_owner_identities(ONE) == (
        "TEST_CONSUMER", "TEST_CONSUMER"
    )
    capability.sessions[0].consumer.on_market_tick(tick(ONE))
    assert all(len(item.ticks) == 1 for item in values)


def test_reference_counted_disconnect_keeps_shared_socket_until_last_consumer() -> None:
    capability = Capability()
    hub = SharedSwingMonitoringHub()
    values = []
    for instrument in (ONE, TWO):
        registration = hub.open(capability, Consumer())
        registration.subscribe((instrument,))
        registration.connect()
        values.append(registration)
    values[0].disconnect()
    assert hub.subscription_reference_count(ONE) == 0
    assert capability.sessions[0].disconnections == 0
    values[1].disconnect()
    assert capability.sessions[0].disconnections == 1
    assert hub.active_session_count == 0


def test_connection_state_and_order_stream_are_fanned_out_without_interpretation() -> None:
    capability = Capability()
    hub = SharedSwingMonitoringHub()
    consumer = Consumer()
    registration = hub.open(capability, consumer)
    registration.subscribe((ONE,))
    registration.connect()
    capability.sessions[0].consumer.on_connection_state(MonitoringConnectionState.RECONNECTING)
    marker = object()
    capability.sessions[0].consumer.on_order_update(marker)
    assert consumer.states == [MonitoringConnectionState.RECONNECTING]
    assert consumer.orders == [marker]


def test_different_authenticated_capability_fails_closed() -> None:
    hub = SharedSwingMonitoringHub()
    first = hub.open(Capability(), Consumer())
    first.subscribe((ONE,))
    first.connect()
    second = hub.open(Capability(), Consumer())
    second.subscribe((TWO,))
    with pytest.raises(ValueError, match="CAPABILITY_MISMATCH"):
        second.connect()


def test_inactive_capability_and_invalid_consumer_fail_closed() -> None:
    capability = Capability()
    capability.active = False
    with pytest.raises(ValueError, match="CAPABILITY_UNAVAILABLE"):
        SharedSwingMonitoringHub().open(capability, Consumer())
    with pytest.raises(TypeError, match="CONSUMER_INVALID"):
        SharedSwingMonitoringHub().open(Capability(), object())


def test_close_is_idempotent_and_releases_one_socket() -> None:
    capability = Capability()
    hub = SharedSwingMonitoringHub()
    registration = hub.open(capability, Consumer())
    registration.subscribe((ONE,))
    registration.connect()
    hub.close()
    hub.close()
    assert capability.sessions[0].disconnections == 1


def test_actual_connection_state_is_read_only_websocket_authority() -> None:
    hub = SharedSwingMonitoringHub()
    assert hub.connection_state is None

    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    assert hub.connection_state is MonitoringConnectionState.CONNECTED
    hub.on_connection_state(MonitoringConnectionState.RECONNECTING)
    assert hub.connection_state is MonitoringConnectionState.RECONNECTING

    with pytest.raises(TypeError, match="CONNECTION_STATE_INVALID"):
        hub.on_connection_state("CONNECTED")  # type: ignore[arg-type]
