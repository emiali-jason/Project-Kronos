"""Historical MCX contracts reach the actual Swing lifecycle engine."""

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import MonitoringConnectionState, ProviderMarketTick
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_contract_lifecycle import (
    LocalMcxHistoricalContractStore, McxContractBoundLifecycle,
)
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleState, ActiveTradeLifecycleService,
    LocalActiveTradeLifecycleStore, TradeExitReason, _position as seal_position,
    ActiveLifecycleMonitoringCoordinator,
)
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from tests.unit.swing.v1.test_native_active_trade_lifecycle import _position


START = datetime(2026, 8, 17, 14, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


FAMILY_CONTRACTS = (
    (McxFamily.GOLDM, "GOLDM26OCTFUT", "GOLDM26NOVFUT"),
    (McxFamily.SILVERM, "SILVERM26NOVFUT", "SILVERM26DECFUT"),
    (McxFamily.COPPER, "COPPER26OCTFUT", "COPPER26NOVFUT"),
    (McxFamily.CRUDEOIL, "CRUDEOIL26OCTFUT", "CRUDEOIL26NOVFUT"),
    (McxFamily.NATURALGAS, "NATURALGAS26OCTFUT", "NATURALGAS26NOVFUT"),
)


def _fixture(tmp_path, family=McxFamily.GOLDM, symbol="GOLDM26OCTFUT",
             choice=SponsorTradeChoice.PAPER, v1=False, active_v1=False):
    options = {} if choice is SponsorTradeChoice.PAPER else {
        "actual_live_entry": Decimal("101"), "live_lots": 1,
    }
    old, _, _ = _position(choice, **options)
    values = {name: getattr(old, name) for name in old.__dataclass_fields__}
    values.update(
        canonical_instrument=family.value,
        underlying_quantity=1 if v1 else 10,
        mcx_v1_contract_symbol=symbol if v1 else None,
    )
    if active_v1:
        assert v1 and choice is SponsorTradeChoice.PAPER
        values.update(
            state=ActiveLifecycleState.PAPER_ACTIVE,
            actual_entry=Decimal("101"),
            entry_timestamp=START - timedelta(minutes=1),
            updated_at=START - timedelta(minutes=1),
            mcx_activation_outcome_sha256="a" * 64,
        )
    values.pop("integrity_hash")
    position = seal_position(values)
    root = tmp_path / "lifecycle"
    store = LocalActiveTradeLifecycleStore(root)
    store.retain_position(position)
    service = ActiveTradeLifecycleService(store)
    bindings = LocalMcxHistoricalContractStore(tmp_path / "bindings")
    adapter = McxContractBoundLifecycle(service, bindings)
    instrument = InstrumentRecord(
        "KITE", "MCX", "MCX-FUT", symbol, family.value, "FUT",
        datetime(2026, 10, 5).date(), Decimal("1"), 1,
    )
    adapter.retain_existing(position.position_id, instrument)
    schedule = MarketCalendarPublisher().schedule("MCX", START.date(), observed_at=START)
    return position, instrument, schedule, adapter, root, bindings.root


def _tick(instrument, minute, price):
    stamp = START + timedelta(minutes=minute)
    return ProviderMarketTick(
        instrument, Decimal(price), stamp, stamp, "KITE_CONNECT_WEBSOCKET",
        "KITE-CONNECTION-MCX", minute, True, True, True,
    )


def _wire_monitor(service, bindings, instrument, clock, owner=None):
    """Real shared owner and Kite adapter, isolated socket only."""
    from kronos.application.shared_monitoring import SharedSwingMonitoringHub
    from kronos.provider.adapters.kite.monitoring import KiteReadOnlyMonitoringSession
    from tests.unit.provider.test_kite_websocket_monitoring import _Socket

    class Capability:
        active = True
        def __init__(self):
            self.sessions = []
        def open_monitoring_session(self, consumer):
            self.socket = _Socket()
            self.session = KiteReadOnlyMonitoringSession(
                api_key="isolated-fixture", access_token="isolated-fixture",
                token_resolver=lambda item: 202 if item == instrument else None,
                consumer=consumer, clock=lambda: clock[0],
                socket_factory=lambda *_args: self.socket)
            self.sessions.append(self.session)
            return self.session
        def tick(self, price, *, observed=None, token=202):
            self.socket.on_ticks(self.socket, [{
                "instrument_token": token, "last_price": price,
                "timestamp": (observed or clock[0]).replace(tzinfo=None)}])

    hub = SharedSwingMonitoringHub()
    monitor = ActiveLifecycleMonitoringCoordinator(
        service, MarketCalendarPublisher(), clock=lambda: clock[0])
    monitor.set_shared_monitoring_hub(hub)
    monitor.set_mcx_historical_contracts(bindings)
    if owner is not None:
        monitor.set_mcx_v1_tick_owner(owner)
    return monitor, Capability(), hub


@pytest.mark.parametrize("restart", [False, True])
def test_active_paper_real_reconnect_preserves_entry_and_factual_exit(tmp_path, restart):
    from kronos.provider.contracts.monitoring import MonitoringError
    position, instrument, schedule, bound, root, binding_root = _fixture(
        tmp_path, v1=True, active_v1=True)
    clock = [START]
    monitor, capability, hub = _wire_monitor(
        bound.service, bound.bindings, instrument, clock)
    monitor.attach(position.position_id, capability, instrument)
    original_consumer = monitor._consumers[position.position_id]
    try:
        clock[0] += timedelta(minutes=1)
        capability.tick(102)
        old_tick, _ = monitor.latest_mcx_observation(position.position_id)
        clock[0] += timedelta(minutes=1)
        capability.socket.on_close(capability.socket, 1006, "fixture outage")
        clock[0] += timedelta(minutes=1)
        capability.socket.on_connect(capability.socket, {})
        assert capability.session.state is MonitoringConnectionState.CONTEXT_INCOMPLETE
        assert capability.socket.subscribed == [[202], [202]]
        assert len(capability.sessions) == hub.active_session_count == 1
        unavailable = bound.service._require(position.position_id)
        assert unavailable.state is ActiveLifecycleState.MONITORING_UNAVAILABLE
        assert unavailable.prior_state is ActiveLifecycleState.PAPER_ACTIVE
        assert monitor.latest_mcx_observation(position.position_id) is None
        before = bound.service.snapshot()
        # Correct token with a pre-resubscription timestamp is still stale.
        capability.tick(103, observed=START + timedelta(minutes=2))
        original_consumer.on_market_tick(old_tick)
        with pytest.raises(MonitoringError):
            capability.tick(103, token=999)
        assert bound.service.snapshot() == before
        if restart:
            monitor.close()
            bound = McxContractBoundLifecycle(
                ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root)),
                LocalMcxHistoricalContractStore(binding_root))
            monitor, capability, hub = _wire_monitor(
                bound.service, bound.bindings, instrument, clock)
            assert monitor.restore(capability, lambda _: pytest.fail("family rebind")) == (position.position_id,)
            # Retired owner's delayed callbacks cannot affect restored evidence.
            original_consumer.on_connection_state(MonitoringConnectionState.DISCONNECTED)
            original_consumer.on_market_tick(old_tick)
            assert bound.service.snapshot() == before
        clock[0] += timedelta(minutes=1)
        capability.tick(103)
        current = bound.service._require(position.position_id)
        assert current.state is ActiveLifecycleState.PAPER_ACTIVE
        assert (current.actual_entry, current.entry_timestamp,
                current.mcx_activation_outcome_sha256) == (
            position.actual_entry, position.entry_timestamp,
            position.mcx_activation_outcome_sha256)
        tick, state = monitor.latest_mcx_observation(position.position_id)
        assert state is (MonitoringConnectionState.CONNECTED if restart else
                         MonitoringConnectionState.CONTEXT_INCOMPLETE)
        assert tick.connection_id != old_tick.connection_id
        assert len(capability.sessions) == hub.active_session_count == 1
        assert hub.subscription_reference_count(instrument) == 1
        closure = bound.manual_paper_exit_at_cmp(position.position_id, tick, schedule)
        assert closure.actual_exit == Decimal("103")
        assert tick.connection_id in closure.event_provenance
        assert closure.mcx_v1_contract_symbol == instrument.trading_symbol
    finally:
        monitor.close()


def test_paper_joins_existing_shared_subscription_without_second_connect(tmp_path):
    from types import SimpleNamespace
    position, instrument, _, bound, _, _ = _fixture(tmp_path, v1=True, active_v1=True)
    clock = [START]
    monitor, capability, hub = _wire_monitor(bound.service, bound.bindings, instrument, clock)
    observations = []
    observer = SimpleNamespace(on_market_tick=observations.append,
                               on_order_update=lambda _: None,
                               on_connection_state=lambda _: None)
    other = hub.open(capability, observer)
    other.subscribe((instrument,))
    other.connect()
    try:
        monitor.attach(position.position_id, capability, instrument)
        assert len(capability.sessions) == 1
        assert capability.socket.subscribed == [[202]]
        assert hub.subscription_reference_count(instrument) == 2
        clock[0] += timedelta(minutes=1)
        capability.tick(102)
        tick, state = monitor.latest_mcx_observation(position.position_id)
        assert state is MonitoringConnectionState.CONNECTED
        assert observations == [tick]
        monitor.close()
        assert other.active and hub.active_session_count == 1
        assert hub.subscription_reference_count(instrument) == 1
        assert not capability.socket.closed
    finally:
        monitor.close()
        other.disconnect()


def test_restoration_subscribes_retained_future_not_family_current_contract(tmp_path):
    position, instrument, _, adapter, root, bindings_root = _fixture(
        tmp_path, choice=SponsorTradeChoice.LIVE, v1=True,
    )
    class Session:
        def __init__(self, consumer):
            self.consumer = consumer
            self.subscriptions = ()
        def subscribe(self, values):
            self.subscriptions = values
        def connect(self):
            pass
        def unsubscribe(self, values):
            pass
        def disconnect(self):
            pass
    class Capability:
        active = True
        def open_monitoring_session(self, consumer):
            self.session = Session(consumer)
            return self.session
    restored = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root))
    coordinator = ActiveLifecycleMonitoringCoordinator(
        restored, MarketCalendarPublisher(), clock=lambda: START,
    )
    coordinator.set_mcx_historical_contracts(
        LocalMcxHistoricalContractStore(bindings_root)
    )
    capability = Capability()
    def family_resolver(_family):
        pytest.fail("A family-level current contract must not be resolved")
    assert coordinator.restore(capability, family_resolver) == (position.position_id,)
    assert capability.session.subscriptions == (instrument,)
    assert restored.snapshot() == adapter.service.snapshot()


def test_armed_v1_subscription_uses_exact_contract_owner_and_fresh_connection(tmp_path):
    position, instrument, _, _, root, binding_root = _fixture(
        tmp_path, choice=SponsorTradeChoice.PAPER, v1=True,
    )
    class Session:
        def __init__(self, consumer):
            self.consumer = consumer
        def subscribe(self, values):
            assert values == (instrument,)
        def connect(self):
            self.consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
        def unsubscribe(self, _values):
            pass
        def disconnect(self):
            pass
    class Capability:
        active = True
        def open_monitoring_session(self, consumer):
            self.session = Session(consumer)
            return self.session
    service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root))
    coordinator = ActiveLifecycleMonitoringCoordinator(
        service, MarketCalendarPublisher(), clock=lambda: START,
    )
    coordinator.set_mcx_historical_contracts(
        LocalMcxHistoricalContractStore(binding_root))
    seen = []
    def owner(position_id, tick, state):
        seen.append((position_id, tick, state))
        return service._require(position_id)
    coordinator.set_mcx_v1_tick_owner(owner)
    capability = Capability()
    coordinator.attach(position.position_id, capability, instrument)
    tick = _tick(instrument, 2, "102")
    capability.session.consumer.on_market_tick(tick)
    assert seen == [(position.position_id, tick, MonitoringConnectionState.CONNECTED)]
    assert coordinator.latest_mcx_observation(position.position_id) == (
        tick, MonitoringConnectionState.CONNECTED)
    capability.session.consumer.on_connection_state(
        MonitoringConnectionState.CONTEXT_INCOMPLETE)
    assert coordinator.latest_mcx_observation(position.position_id) is None
    assert service._require(position.position_id).state is ActiveLifecycleState.MONITORING_UNAVAILABLE


def test_v1_active_paper_rejects_cached_pre_outage_quote_then_exits_at_fresh_cmp(
    tmp_path,
):
    position, instrument, schedule, adapter, root, _ = _fixture(
        tmp_path, v1=True, active_v1=True,
    )
    outage_at = START + timedelta(minutes=2)
    adapter.monitoring_unavailable(
        position.position_id, occurred_at=outage_at,
        provider_context="ISOLATED_RECONNECT",
    )
    before = {str(path): path.read_bytes() for path in root.rglob("*")
              if path.is_file()}
    cached = replace(_tick(instrument, 1, "102"),
                     received_at=START + timedelta(minutes=3))
    with pytest.raises(ValueError, match="MCX_V1_POST_OUTAGE_OBSERVATION_STALE"):
        adapter.observe_tick(position.position_id, cached, schedule)
    assert {str(path): path.read_bytes() for path in root.rglob("*")
            if path.is_file()} == before
    fresh = replace(_tick(instrument, 3, "103"), source_sequence=None,
                    previous_interval_available=False,
                    session_continuous=False, ordering_deterministic=False)
    assert adapter.observe_tick(position.position_id, fresh, schedule).state \
        is ActiveLifecycleState.PAPER_ACTIVE
    closure = adapter.manual_paper_exit_at_cmp(position.position_id, fresh, schedule)
    assert closure.actual_exit == Decimal("103")


def test_v1_active_callback_waits_for_connected_state_after_outage(tmp_path):
    position, instrument, _, adapter, root, binding_root = _fixture(
        tmp_path, v1=True, active_v1=True,
    )

    class Session:
        def __init__(self, consumer):
            self.consumer = consumer
        def subscribe(self, _values):
            pass
        def connect(self):
            self.consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
        def unsubscribe(self, _values):
            pass
        def disconnect(self):
            pass

    class Capability:
        active = True
        def open_monitoring_session(self, consumer):
            self.session = Session(consumer)
            return self.session

    coordinator = ActiveLifecycleMonitoringCoordinator(
        adapter.service, MarketCalendarPublisher(),
        clock=lambda: START + timedelta(minutes=2),
    )
    coordinator.set_mcx_historical_contracts(
        LocalMcxHistoricalContractStore(binding_root))
    capability = Capability()
    coordinator.attach(position.position_id, capability, instrument)
    consumer = capability.session.consumer
    consumer.on_connection_state(MonitoringConnectionState.CONTEXT_INCOMPLETE)
    before = {str(path): path.read_bytes() for path in root.rglob("*")
              if path.is_file()}
    fresh = replace(_tick(instrument, 3, "103"), source_sequence=None,
                    previous_interval_available=False,
                    session_continuous=False, ordering_deterministic=False)
    consumer.on_market_tick(fresh)
    assert {str(path): path.read_bytes() for path in root.rglob("*")
            if path.is_file()} == before
    assert coordinator.latest_mcx_observation(position.position_id) is None
    consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
    consumer.on_market_tick(fresh)
    assert adapter.service._require(position.position_id).state \
        is ActiveLifecycleState.PAPER_ACTIVE
    assert coordinator.latest_mcx_observation(position.position_id) == (
        fresh, MonitoringConnectionState.CONNECTED)


@pytest.mark.parametrize("family,symbol,new_symbol", FAMILY_CONTRACTS)
def test_exact_historical_contract_survives_roll_restart_and_paper_exit(
    tmp_path, family, symbol, new_symbol,
):
    position, instrument, schedule, adapter, lifecycle_root, binding_root = _fixture(
        tmp_path, family, symbol,
    )
    newer = InstrumentRecord(
        "KITE", "MCX", "MCX-FUT", new_symbol, family.value, "FUT",
        datetime(2026, 11, 5).date(), Decimal("1"), 1,
    )
    before = adapter.service.snapshot()
    with pytest.raises(ValueError, match="TICK_MISMATCH"):
        adapter.observe_tick(position.position_id, _tick(newer, 1, "99"), schedule)
    assert adapter.service.snapshot() == before
    adapter.observe_tick(position.position_id, _tick(instrument, 1, "99"), schedule)
    restarted = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(lifecycle_root)),
        LocalMcxHistoricalContractStore(binding_root),
    )
    active = restarted.observe_tick(position.position_id, _tick(instrument, 2, "102"), schedule)
    assert active.state is ActiveLifecycleState.PAPER_ACTIVE
    assert active.actual_entry == Decimal("102")
    closed = restarted.observe_tick(position.position_id, _tick(instrument, 3, "122"), schedule)
    assert closed.state is ActiveLifecycleState.CLOSED
    snapshot = restarted.service.snapshot()
    assert len(snapshot.closures) == 1
    assert snapshot.closures[0].position_id == position.position_id
    assert snapshot.closures[0].actual_exit == Decimal("122")
    assert snapshot == ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore(lifecycle_root)
    ).snapshot()


def test_missing_or_changed_binding_blocks_tick_but_not_retained_exit(tmp_path):
    position, instrument, schedule, adapter, _, binding_root = _fixture(tmp_path)
    adapter.observe_tick(position.position_id, _tick(instrument, 1, "99"), schedule)
    active = adapter.observe_tick(position.position_id, _tick(instrument, 2, "102"), schedule)
    assert active.state is ActiveLifecycleState.PAPER_ACTIVE
    mismatched = InstrumentRecord(
        "KITE", "MCX", "MCX-FUT", instrument.trading_symbol,
        "GOLDM", "FUT", instrument.expiry, Decimal("0.5"), 1,
    )
    with pytest.raises(ValueError, match="TICK_MISMATCH"):
        adapter.observe_tick(position.position_id, _tick(mismatched, 3, "103"), schedule)
    assert adapter.service.snapshot().positions[0].state is ActiveLifecycleState.PAPER_ACTIVE
    with pytest.raises(ValueError, match="IMMUTABLE"):
        adapter.retain_existing(position.position_id, mismatched)
    assert adapter.bindings.load(position.position_id).instrument == instrument
    # Existing-position exit remains available even if a current master or
    # newer derivative cannot be supplied. It uses the last exact old tick.
    closure = adapter.manual_paper_exit_current(position.position_id)
    assert closure.position_id == position.position_id
    assert adapter.service.snapshot().positions[0].state is ActiveLifecycleState.CLOSED
    assert list(binding_root.glob("*.json"))


def test_existing_live_contract_monitoring_outage_and_attested_exit(tmp_path):
    position, instrument, schedule, adapter, lifecycle_root, binding_root = _fixture(
        tmp_path, choice=SponsorTradeChoice.LIVE,
    )
    newer = InstrumentRecord(
        "KITE", "MCX", "MCX-FUT", "GOLDM26NOVFUT", "GOLDM", "FUT",
        instrument.expiry, Decimal("1"), 1,
    )
    with pytest.raises(ValueError, match="TICK_MISMATCH"):
        adapter.observe_tick(position.position_id, _tick(newer, 1, "122"), schedule)
    observed = adapter.observe_tick(position.position_id, _tick(instrument, 1, "122"), schedule)
    assert observed.state is ActiveLifecycleState.LIVE_ACTIVE
    assert len(adapter.service.snapshot().notifications) == 1
    unavailable = adapter.monitoring_unavailable(
        position.position_id, occurred_at=START + timedelta(minutes=2),
        provider_context="ISOLATED_TEST_PROVIDER_OUTAGE",
    )
    assert unavailable.state is ActiveLifecycleState.MONITORING_UNAVAILABLE
    restarted = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(lifecycle_root)),
        LocalMcxHistoricalContractStore(binding_root),
    )
    assert restarted.service.snapshot().positions[0].state is ActiveLifecycleState.MONITORING_UNAVAILABLE
    resumed = restarted.observe_tick(position.position_id, _tick(instrument, 3, "123"), schedule)
    assert resumed.state is ActiveLifecycleState.LIVE_ACTIVE
    closure = restarted.record_live_exit(
        position.position_id, actual_exit=Decimal("121.5"),
        exit_timestamp=START + timedelta(minutes=4),
        reason=TradeExitReason.SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION,
    )
    assert closure is not None and closure.actual_exit == Decimal("121.5")
    assert restarted.service.snapshot().positions[0].state is ActiveLifecycleState.CLOSED
    assert restarted.service.snapshot().closures == ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore(lifecycle_root)
    ).snapshot().closures
