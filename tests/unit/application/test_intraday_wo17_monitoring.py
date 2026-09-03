from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from kronos.application.intraday_wo17 import (
    IntradayWo17Application,
    IntradayWo17RestorationService,
    create_wo17_operation_request,
)
from kronos.application.intraday_wo17_monitoring import (
    IntradayWo17MonitoringCoordinator,
    Wo17MonitoringBinding,
)
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.intraday.wo17_lifecycle import Wo17MonitoringAvailability
from kronos.intraday.wo17_persistence import Wo17Store
from kronos.intraday.wo17_position import Wo17PositionState
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
)
from tests.unit.intraday.test_wo17_lifecycle import _active


class _Session:
    def __init__(self, consumer) -> None:  # type: ignore[no-untyped-def]
        self.consumer = consumer
        self.subscriptions = ()

    def subscribe(self, instruments) -> None:  # type: ignore[no-untyped-def]
        self.subscriptions = instruments

    def unsubscribe(self, instruments) -> None:  # type: ignore[no-untyped-def]
        del instruments

    def connect(self) -> None:
        self.consumer.on_connection_state(MonitoringConnectionState.CONNECTED)

    def disconnect(self) -> None:
        self.consumer.on_connection_state(MonitoringConnectionState.DISCONNECTED)


class _Capability:
    active = True

    def __init__(self) -> None:
        self.sessions = []

    def open_monitoring_session(self, consumer):  # type: ignore[no-untyped-def]
        session = _Session(consumer)
        self.sessions.append(session)
        return session


class _ExistingConsumer:
    owner_identity = "EXISTING-SWING-MONITOR"

    def on_market_tick(self, tick) -> None:  # type: ignore[no-untyped-def]
        del tick

    def on_order_update(self, update) -> None:  # type: ignore[no-untyped-def]
        del update

    def on_connection_state(self, state) -> None:  # type: ignore[no-untyped-def]
        del state


def _coordinator(tmp_path, *, mcx=False):  # type: ignore[no-untyped-def]
    snapshot, position = _active(tmp_path / "facts", mcx=mcx)
    store = Wo17Store((tmp_path / "wo17").resolve())
    application = IntradayWo17Application(store=store)
    application.execute(create_wo17_operation_request(
        snapshot=snapshot,
        position=position,
        requested_at=position.last_transition_at + timedelta(seconds=1),
    ))
    capability = _Capability()
    coordinator = IntradayWo17MonitoringCoordinator(
        application,
        IntradayWo17RestorationService(store=store),
        lambda: capability,  # type: ignore[arg-type]
        clock=lambda: position.last_transition_at + timedelta(minutes=5),
    )
    hub = SharedSwingMonitoringHub()
    coordinator.set_shared_monitoring_hub(hub)
    instrument = InstrumentRecord(
        provider="KITE",
        exchange="MCX" if mcx else "NSE",
        segment="MCX" if mcx else "NSE",
        trading_symbol="GOLDM26OCTFUT" if mcx else "RELIANCE",
        name="GOLDM" if mcx else "RELIANCE",
        instrument_type="FUT" if mcx else "EQ",
        expiry=snapshot.lineage.contract_expiry,
        tick_size=Decimal("0.05"),
        lot_size=1,
    )
    binding = Wo17MonitoringBinding(
        snapshot.lineage.canonical_subject_identity,
        snapshot.lineage.instrument_identity,
        snapshot.lineage.actual_contract_identity,
        snapshot.lineage.roll_lineage_identity,
        instrument,
    )
    return coordinator, hub, capability, store, binding, position


def test_attach_reuses_shared_session_and_enters_recovery(tmp_path) -> None:
    coordinator, hub, capability, store, binding, position = _coordinator(tmp_path)
    at = position.last_transition_at + timedelta(seconds=2)

    coordinator.attach(binding, attached_at=at)

    restored = store.restore_current(binding.canonical_subject_identity)
    assert restored is not None
    assert restored.lifecycle is not None
    assert restored.lifecycle.monitoring_availability is Wo17MonitoringAvailability.RECOVERING
    assert restored.lifecycle.baseline is None
    assert hub.active_session_count == 1
    assert hub.subscription_count == 1
    assert capability.sessions[0].subscriptions == (binding.provider_instrument,)


def test_first_recovery_tick_is_baseline_and_order_updates_are_ignored(tmp_path) -> None:
    coordinator, hub, _, store, binding, position = _coordinator(tmp_path)
    at = position.last_transition_at + timedelta(seconds=2)
    coordinator.attach(binding, attached_at=at)
    tick_at = at + timedelta(seconds=2)
    hub.on_market_tick(ProviderMarketTick(
        instrument=binding.provider_instrument,
        last_price=position.upstream_snapshot.lineage.entry_reference,
        observed_at=tick_at,
        received_at=tick_at,
        source="KITE_CONNECT_WEBSOCKET",
        connection_id="KITE-WO17-TEST",
        source_sequence=10,
        previous_interval_available=False,
        session_continuous=True,
        ordering_deterministic=True,
    ))
    hub.on_order_update(ProviderOrderUpdateEvidence(
        order_id="ORDER-IGNORED",
        instrument=binding.provider_instrument,
        status="COMPLETE",
        side="BUY",
        filled_quantity=Decimal("1"),
        average_price=Decimal("100"),
        observed_at=tick_at,
        received_at=tick_at,
        source="KITE_CONNECT_ORDER_UPDATE",
    ))

    restored = store.restore_current(binding.canonical_subject_identity)
    assert restored is not None and restored.lifecycle is not None
    assert restored.lifecycle.monitoring_availability is Wo17MonitoringAvailability.AVAILABLE
    assert restored.lifecycle.assessments[-1].assessment_code.value == "BASELINE_ONLY"
    status = coordinator.status_document()
    assert status["order_updates_ignored"] == 1
    assert status["broker_operations"] == 0
    assert restored.position.position_evidence.fill == "UNAVAILABLE"


def test_foreign_tick_and_mcx_successor_contract_do_not_migrate(tmp_path) -> None:
    coordinator, hub, _, store, binding, position = _coordinator(tmp_path, mcx=True)
    coordinator.attach(
        binding, attached_at=position.last_transition_at + timedelta(seconds=2)
    )
    foreign = InstrumentRecord(
        provider="KITE", exchange="MCX", segment="MCX",
        trading_symbol="GOLDM26NOVFUT", name="GOLDM", instrument_type="FUT",
        expiry=binding.provider_instrument.expiry,
    )
    at = position.last_transition_at + timedelta(seconds=5)
    hub.on_market_tick(ProviderMarketTick(
        foreign, Decimal("100"), at, at, "KITE_CONNECT_WEBSOCKET",
        "FOREIGN-CONNECTION", 1, True, True, True,
    ))

    restored = store.restore_current(binding.canonical_subject_identity)
    assert restored is not None
    assert restored.pointer.actual_contract_identity == binding.actual_contract_identity
    assert restored.pointer.roll_lineage_identity == binding.roll_lineage_identity
    assert len(restored.lifecycle.observations) == 0  # type: ignore[union-attr]


def test_attach_reuses_exact_active_capability_and_existing_shared_session(
    tmp_path,
) -> None:
    coordinator, hub, capability, _, binding, position = _coordinator(tmp_path)
    existing = hub.open(capability, _ExistingConsumer())
    existing.subscribe((binding.provider_instrument,))
    existing.connect()
    coordinator.set_monitoring_capability_supplier(lambda: capability)

    coordinator.attach(
        binding, attached_at=position.last_transition_at + timedelta(seconds=2)
    )

    assert len(capability.sessions) == 1
    assert hub.active_session_count == 1
    assert hub.subscription_reference_count(binding.provider_instrument) == 2
    assert hub.subscription_owner_identities(binding.provider_instrument) == (
        "EXISTING-SWING-MONITOR",
        "INTRADAY-WO17-LIFECYCLE-MONITORING",
    )
    assert coordinator.status_document()["state"] == "CONNECTED"


def test_connection_interruption_preserves_position_and_recovery_resets_baseline(
    tmp_path,
) -> None:
    coordinator, hub, _, store, binding, position = _coordinator(tmp_path)
    coordinator.attach(
        binding, attached_at=position.last_transition_at + timedelta(seconds=2)
    )

    hub.on_connection_state(MonitoringConnectionState.DISCONNECTED)
    interrupted = store.restore_current(binding.canonical_subject_identity)
    assert interrupted is not None and interrupted.lifecycle is not None
    assert interrupted.position.state is Wo17PositionState.PAPER_ACTIVE
    assert (
        interrupted.lifecycle.monitoring_availability
        is Wo17MonitoringAvailability.INTERRUPTED
    )
    assert interrupted.lifecycle.baseline is None

    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    recovered = store.restore_current(binding.canonical_subject_identity)
    assert recovered is not None and recovered.lifecycle is not None
    assert recovered.position.state is Wo17PositionState.PAPER_ACTIVE
    assert (
        recovered.lifecycle.monitoring_availability
        is Wo17MonitoringAvailability.RECOVERING
    )
    assert recovered.lifecycle.baseline is None
