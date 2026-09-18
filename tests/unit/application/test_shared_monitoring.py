from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from threading import Event, Thread

from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.application import shared_monitoring as monitoring_module
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
)


ONE = InstrumentRecord("KITE", "NSE", "NSE", "ONE", "ONE", "EQ", None)
TWO = InstrumentRecord("KITE", "NSE", "NSE", "TWO", "TWO", "EQ", None)
NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize('old_product,new_product', [('SWING','SWING'), ('SWING','INTRADAY'), ('INTRADAY','SWING')])
def test_detach_inflight_unsubscribe_reconciles_new_owner_without_duplicate_subscription(old_product,new_product):
    entered, release = Event(), Event()
    class WireSession(Session):
        def __init__(self, consumer):
            super().__init__(consumer)
            self.wire = set()
        def subscribe(self, values):
            assert not self.wire.intersection(values), 'duplicate active underlying subscription'
            self.wire.update(values)
            super().subscribe(values)
        def unsubscribe(self, values):
            entered.set()
            assert release.wait(5)
            self.wire.difference_update(values)
            super().unsubscribe(values)
    class WireCapability(Capability):
        def open_monitoring_session(self, consumer):
            session = WireSession(consumer)
            self.sessions.append(session)
            return session
    hub, capability = SharedSwingMonitoringHub(), WireCapability()
    def attach(instrument, product):
        consumer = Consumer(); consumer.owner_identity = product
        registration = hub.open(capability, consumer)
        registration.subscribe((instrument,)); registration.connect()
        return registration
    old = attach(ONE, old_product)
    other = attach(TWO, 'UNRELATED')
    hub.on_market_tick(tick(ONE)); hub.on_market_tick(tick(TWO))
    failures=[]
    def detach():
        try: old.disconnect()
        except Exception as error: failures.append(error)
    worker=Thread(target=detach);worker.start()
    try:
        assert entered.wait(5)
        assert hub.subscription_reference_count(ONE) == 0
        assert hub.latest_market_ticks == (tick(TWO),)
        new = attach(ONE, new_product)
        new.subscribe((ONE,)); new.connect()
        assert hub.status_document()['owner_count'] == 2
        assert new.active and other.active
    finally:
        release.set();worker.join(5)
    assert not worker.is_alive() and not failures
    session=capability.sessions[0]
    assert session.wire == {ONE,TWO}
    assert session.unsubscribed == [(ONE,)]
    assert session.subscribed.count((ONE,)) == 2  # original, then exact reconciliation
    assert len(capability.sessions) == 1 and session.connections == 1
    assert hub.subscription_reference_count(ONE) == 1
    assert hub.status_document()['release_counts']['final_owner_subscription_releases'] == 1
    old.disconnect()
    assert session.unsubscribed == [(ONE,)]
    assert old._consumer is None and old._capability is None and old._instruments == set()


def test_nonfinal_owner_preserves_cache_and_final_instrument_owner_evicts_only_its_tick():
    hub, capability = SharedSwingMonitoringHub(), Capability()
    registrations=[]
    for instrument in (ONE,ONE,TWO):
        registration=hub.open(capability,Consumer());registration.subscribe((instrument,));registration.connect()
        registrations.append(registration)
    hub.on_market_tick(tick(ONE));hub.on_market_tick(tick(TWO))
    registrations[0].disconnect()
    assert len(hub.latest_market_ticks)==2 and capability.sessions[0].unsubscribed==[]
    registrations[1].disconnect()
    assert hub.latest_market_ticks==(tick(TWO),)
    assert capability.sessions[0].unsubscribed==[(ONE,)]
    hub.on_market_tick(tick(ONE))
    assert hub.latest_market_ticks==(tick(TWO),)
    assert registrations[2].active


def test_concurrent_detach_is_one_release_and_retired_session_callbacks_are_inert():
    hub, capability=SharedSwingMonitoringHub(),Capability()
    old=hub.open(capability,Consumer());old.subscribe((ONE,));old.connect()
    workers=[Thread(target=old.disconnect) for _ in range(8)]
    for worker in workers:worker.start()
    for worker in workers:worker.join(3)
    assert all(not worker.is_alive() for worker in workers)
    assert capability.sessions[0].unsubscribed==[(ONE,)]
    assert capability.sessions[0].disconnections==1
    current=Consumer()
    new=hub.open(capability,current);new.subscribe((ONE,));new.connect()
    capability.sessions[0].consumer.on_market_tick(tick(ONE))
    capability.sessions[0].consumer.on_connection_state(MonitoringConnectionState.DISCONNECTED)
    assert current.ticks==[] and current.states==[] and hub.latest_market_ticks==()


def test_blocked_transport_cleanup_remains_owned_until_current_generation_starts():
    entered, release = Event(), Event()

    class BlockingSession(Session):
        def disconnect(self):
            entered.set()
            assert release.wait(5)
            super().disconnect()

    class BlockingCapability(Capability):
        def open_monitoring_session(self, consumer):
            value = BlockingSession(consumer)
            self.sessions.append(value)
            return value

    hub, capability = SharedSwingMonitoringHub(), BlockingCapability()
    old = hub.open(capability, Consumer())
    old.subscribe((ONE,)); old.connect()
    worker = Thread(target=old.disconnect)
    worker.start()
    try:
        assert entered.wait(2)
        cleanup = hub.status_document()["transport_cleanup"]
        assert cleanup == {
            "state": "RUNNING",
            "retired_session_owned": True,
            "subscription_count": 1,
            "subscriptions": [{
                "exchange": "NSE", "segment": "NSE", "trading_symbol": "ONE",
            }],
            "failure": "",
        }
        assert hub.status_document()["session_count"] == 1
        current = hub.open(capability, Consumer())
        current.subscribe((ONE,)); current.connect()
        assert not current.active
    finally:
        release.set(); worker.join(5)
    assert not worker.is_alive()
    assert current.active
    assert len(capability.sessions) == 2
    assert hub.status_document()["transport_cleanup"]["state"] == "COMPLETE"
    assert hub.status_document()["session_count"] == 1


def test_failed_transport_cleanup_is_retained_and_fences_retry():
    class FailedSession(Session):
        def disconnect(self):
            self.disconnections += 1
            raise OSError("PRIVATE-TRANSPORT-FAILURE")

    class FailedCapability(Capability):
        def open_monitoring_session(self, consumer):
            value = FailedSession(consumer)
            self.sessions.append(value)
            return value

    hub, capability = SharedSwingMonitoringHub(), FailedCapability()
    old = hub.open(capability, Consumer())
    old.subscribe((ONE,)); old.connect()
    callbacks = capability.sessions[0].consumer
    with pytest.raises(OSError, match="PRIVATE-TRANSPORT-FAILURE"):
        old.disconnect()

    status = hub.status_document()
    assert status["session_count"] == 1
    assert status["active_session_count"] == 0
    assert status["transport_cleanup"] == {
        "state": "FAILED",
        "retired_session_owned": True,
        "subscription_count": 1,
        "subscriptions": [{
            "exchange": "NSE", "segment": "NSE", "trading_symbol": "ONE",
        }],
        "failure": "SHARED_MONITORING_TRANSPORT_CLEANUP_FAILED",
    }
    current = hub.open(capability, Consumer())
    current.subscribe((ONE,))
    with pytest.raises(ValueError, match="SHARED_MONITORING_CLEANUP_UNRESOLVED"):
        current.connect()
    callbacks.on_market_tick(tick(ONE))
    assert current._consumer.ticks == []
    assert len(capability.sessions) == 1


def test_failed_connect_cleanup_retains_the_unclosed_transport():
    class FailedActivationSession(Session):
        def connect(self):
            self.connections += 1
            raise RuntimeError("INJECTED-CONNECT-FAILURE")

        def disconnect(self):
            self.disconnections += 1
            raise RuntimeError("INJECTED-DISCONNECT-FAILURE")

    class FailedActivationCapability(Capability):
        def open_monitoring_session(self, consumer):
            value = FailedActivationSession(consumer)
            self.sessions.append(value)
            return value

    hub, capability = SharedSwingMonitoringHub(), FailedActivationCapability()
    owner = hub.open(capability, Consumer())
    owner.subscribe((ONE,))
    with pytest.raises(RuntimeError, match="INJECTED-CONNECT-FAILURE"):
        owner.connect()
    status = hub.status_document()
    assert status["transport_cleanup"]["state"] == "FAILED"
    assert status["transport_cleanup"]["retired_session_owned"]
    assert status["session_count"] == 1
    capability.sessions[0].consumer.on_market_tick(tick(ONE))
    assert owner._consumer.ticks == []


def test_repeated_transport_cycles_leave_no_retired_owner():
    hub, capability = SharedSwingMonitoringHub(), Capability()
    for _ in range(25):
        owner = hub.open(capability, Consumer())
        owner.subscribe((ONE,)); owner.connect(); owner.disconnect()
        status = hub.status_document()
        assert status["session_count"] == 0
        assert status["transport_cleanup"]["state"] == "COMPLETE"
        assert not status["transport_cleanup"]["retired_session_owned"]
    assert len(capability.sessions) == 25
    assert all(session.disconnections == 1 for session in capability.sessions)


def test_status_transport_ownership_is_local_and_never_reads_capability_state():
    class InertStatusCapability(Capability):
        inspect_forbidden = False

        @property
        def active(self):
            if self.inspect_forbidden:
                raise AssertionError("status must not inspect Provider capability")
            return True

    hub, capability = SharedSwingMonitoringHub(), InertStatusCapability()
    registration = hub.open(capability, Consumer())
    registration.subscribe((ONE,)); registration.connect()
    capability.inspect_forbidden = True
    assert hub.status_document()["owners"][0]["transport_active"] is True


@pytest.mark.parametrize('product', ['SWING', 'INTRADAY'])
def test_slice8_failed_final_unsubscribe_still_closes_retired_transport(monkeypatch, product):
    hub, capability = SharedSwingMonitoringHub(), Capability()
    consumer = Consumer(); consumer.owner_identity = product
    owner = hub.open(capability, consumer)
    owner.subscribe((ONE,)); owner.connect()
    old = capability.sessions[0]
    hub.on_market_tick(tick(ONE))
    monkeypatch.setattr(old, 'unsubscribe', lambda _: (_ for _ in ()).throw(OSError('isolated unsubscribe')))
    with pytest.raises(OSError, match='isolated unsubscribe'):
        owner.disconnect()
    assert old.disconnections == 1 and not owner.active
    assert hub.active_session_count == 0 and hub.subscription_count == 0
    assert hub.latest_market_ticks == () and not hub._transport_lock.locked()
    owner.disconnect()
    assert old.disconnections == 1
    new_consumer = Consumer()
    new = hub.open(capability, new_consumer)
    new.subscribe((ONE,)); new.connect()
    old.consumer.on_market_tick(tick(ONE))
    old.consumer.on_connection_state(MonitoringConnectionState.DISCONNECTED)
    assert new.active and new_consumer.ticks == [] and new_consumer.states == []
    assert len(capability.sessions) == 2


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


def test_owner_and_subscription_capacity_refusal_is_atomic_and_releasable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(monitoring_module, "_MAX_MONITORING_OWNERS", 2)
    monkeypatch.setattr(monitoring_module, "_MAX_MONITORING_SUBSCRIPTIONS", 1)
    hub, capability = SharedSwingMonitoringHub(), Capability()
    first = hub.open(capability, Consumer())
    first.subscribe((ONE,))
    assert hub.status_document()["capacity"]["instrument_count"] == 1
    second = hub.open(capability, Consumer())
    with pytest.raises(ValueError, match="SHARED_MONITORING_CAPACITY_UNAVAILABLE"):
        second.subscribe((TWO,))
    with pytest.raises(ValueError, match="SHARED_MONITORING_CAPACITY_UNAVAILABLE"):
        hub.open(capability, Consumer())
    status = hub.status_document()
    assert status["capacity"]["subscription_owner_count"] == 1
    assert status["capacity"]["refusals"] == 2
    assert second._instruments == set()
    first.disconnect(); second.disconnect()
    released = hub.open(capability, Consumer())
    released.subscribe((TWO,))
    assert hub.status_document()["capacity"]["subscription_owner_count"] == 1


def test_failed_cleanup_memory_remains_owned_and_fences_capacity(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    class FailedSession(Session):
        def disconnect(self):
            raise OSError("INJECTED-CLEANUP-FAILURE")

    class FailedCapability(Capability):
        def open_monitoring_session(self, consumer):
            value = FailedSession(consumer)
            self.sessions.append(value)
            return value

    monkeypatch.setattr(monitoring_module, "_MAX_MONITORING_INSTRUMENTS", 1)
    hub, capability = SharedSwingMonitoringHub(), FailedCapability()
    owner = hub.open(capability, Consumer())
    owner.subscribe((ONE,)); owner.connect()
    with pytest.raises(OSError, match="INJECTED-CLEANUP-FAILURE"):
        owner.disconnect()
    retained = hub.status_document()["capacity"]["retained_bytes"]
    replacement = hub.open(capability, Consumer())
    with pytest.raises(ValueError, match="SHARED_MONITORING_CAPACITY_UNAVAILABLE"):
        replacement.subscribe((TWO,))
    status = hub.status_document()
    assert status["transport_cleanup"]["retired_session_owned"] is True
    assert status["capacity"]["retained_bytes"] >= retained


def test_oversized_tick_is_dispatched_but_not_retained_as_latest() -> None:
    hub, capability, consumer = SharedSwingMonitoringHub(), Capability(), Consumer()
    owner = hub.open(capability, consumer)
    owner.subscribe((ONE,)); owner.connect()
    oversized = replace(tick(ONE), connection_id="X" * 4096)
    hub.on_market_tick(oversized)
    assert consumer.ticks == [oversized]
    assert hub.latest_market_ticks == ()
    status = hub.status_document()["capacity"]
    assert status["tick_cache_failure_count"] == 1
    assert status["refusals"] == 1
    hub.on_market_tick(tick(ONE))
    assert hub.latest_market_ticks == (tick(ONE),)
    assert hub.status_document()["capacity"]["tick_cache_failure_count"] == 0


def test_actual_connection_state_is_read_only_websocket_authority() -> None:
    hub = SharedSwingMonitoringHub()
    assert hub.connection_state is None

    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    assert hub.connection_state is MonitoringConnectionState.CONNECTED
    hub.on_connection_state(MonitoringConnectionState.RECONNECTING)
    assert hub.connection_state is MonitoringConnectionState.RECONNECTING

    with pytest.raises(TypeError, match="CONNECTION_STATE_INVALID"):
        hub.on_connection_state("CONNECTED")  # type: ignore[arg-type]
