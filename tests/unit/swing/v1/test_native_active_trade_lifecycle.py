from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.swing.v1.native_active_trade_lifecycle import (
    ACTIVE_TRADE_LIFECYCLE_POLICY_ID,
    ActiveLifecycleState,
    ActiveTradeLifecycleEngine,
    ActiveLifecycleMonitoringCoordinator,
    ActiveTradeLifecycleService,
    AnalyticalInvalidationEvidence,
    GovernedLifecycleObservation,
    LIFECYCLE_EVENT_CONTRACT_ID,
    LifecycleEventType,
    LocalActiveTradeLifecycleStore,
    TRADE_CLOSURE_CONTRACT_ID,
    TradeExitReason,
    create_active_lifecycle,
    admit_kite_lifecycle_observation,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import MonitoringConnectionState, ProviderMarketTick
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from tests.unit.swing.v1.test_native_sponsor_decision import NOW, _go


def _position(choice=SponsorTradeChoice.PAPER, **kwargs):  # type: ignore[no-untyped-def]
    result, plan, *_ = _go(choice, **kwargs)
    return create_active_lifecycle(result.decision, result.position, plan), result, plan


def _observation(position, offset, price, *, continuous=True, identity=None):  # type: ignore[no-untyped-def]
    stamp = NOW + timedelta(minutes=offset)
    return GovernedLifecycleObservation(
        identity or f"OBS-{offset}", position.canonical_instrument, Decimal(price),
        stamp, stamp, "KITE_CONNECT_WEBSOCKET", "KITE-CONNECTION-1", offset,
        continuous, continuous, continuous, "NSE-CM", "NSE-CALENDAR-2026",
        "2026.1", "NSE-SESSION-1", "NSE-WINDOW-1",
        ("KITE_CONNECT_WEBSOCKET", "DOMAIN-002", "DOMAIN-008"),
    )


def _activate(position):  # type: ignore[no-untyped-def]
    first = _observation(position, 1, "99")
    position, events, _, _ = ActiveTradeLifecycleEngine.observe(position, first)
    assert not events
    second = _observation(position, 2, "102")
    position, events, _, _ = ActiveTradeLifecycleEngine.observe(position, second)
    assert tuple(item.event_type for item in events) == (
        LifecycleEventType.ENTRY_TRIGGERED,
        LifecycleEventType.PAPER_ENTRY_CAPTURED,
    )
    return position, second


def test_policy_binding_and_paper_entry_uses_first_observed_crossing_price() -> None:
    position, _, plan = _position()
    assert position.policy_identity == ACTIVE_TRADE_LIFECYCLE_POLICY_ID
    active, _ = _activate(position)
    assert active.state is ActiveLifecycleState.PAPER_ACTIVE
    assert active.actual_entry == Decimal("102")
    assert active.actual_entry != plan.entry


def test_paper_entry_does_not_trigger_before_crossing_and_replay_is_idempotent() -> None:
    position, *_ = _position()
    first = _observation(position, 1, "99")
    after, events, _, _ = ActiveTradeLifecycleEngine.observe(position, first)
    assert after.state is ActiveLifecycleState.PAPER_ARMED and events == ()
    replay, events, _, _ = ActiveTradeLifecycleEngine.observe(after, first)
    assert replay == after and events == ()


def test_discontinuous_entry_crossing_fails_closed() -> None:
    position, *_ = _position()
    position, *_ = ActiveTradeLifecycleEngine.observe(position, _observation(position, 1, "99"))
    position, events, _, closure = ActiveTradeLifecycleEngine.observe(
        position, _observation(position, 2, "102", continuous=False),
    )
    assert position.state is ActiveLifecycleState.EVENT_UNRESOLVED
    assert events[0].event_type is LifecycleEventType.ENTRY_EVENT_UNRESOLVED
    assert closure is None and position.actual_entry is None


@pytest.mark.parametrize(
    "exit_price,event_type,reason,pnl",
    (
        ("122", LifecycleEventType.TARGET_HIT, TradeExitReason.PAPER_TARGET_HIT, "20"),
        ("88", LifecycleEventType.STOP_HIT, TradeExitReason.PAPER_STOP_HIT, "-14"),
    ),
)
def test_long_paper_auto_close_uses_observed_exit_not_model_level(
    exit_price, event_type, reason, pnl,
) -> None:
    position, *_ = _position()
    position, _ = _activate(position)
    position, events, _, closure = ActiveTradeLifecycleEngine.observe(
        position, _observation(position, 3, exit_price),
    )
    assert position.state is ActiveLifecycleState.CLOSED
    assert events[0].event_type is event_type
    assert closure.contract_identity == TRADE_CLOSURE_CONTRACT_ID
    assert closure.actual_exit == Decimal(exit_price)
    assert closure.exit_reason is reason
    assert closure.gross_pnl == Decimal(pnl) * position.underlying_quantity


def test_short_paper_entry_target_and_realised_r() -> None:
    position, *_ = _position()
    # Rebind an otherwise valid controlled fixture to SHORT geometry.
    from dataclasses import replace
    from kronos.swing.v1.models import V1Direction
    from kronos.swing.v1.native_active_trade_lifecycle import _position as rebuild

    values = {name: getattr(position, name) for name in position.__dataclass_fields__}
    values.update(direction=V1Direction.SHORT, model_entry=Decimal("100"), stop=Decimal("105"), target=Decimal("90"))
    values.pop("integrity_hash")
    position = rebuild(values)
    position, *_ = ActiveTradeLifecycleEngine.observe(position, _observation(position, 1, "101"))
    position, events, _, _ = ActiveTradeLifecycleEngine.observe(position, _observation(position, 2, "98"))
    assert position.actual_entry == Decimal("98") and events[0].event_type is LifecycleEventType.ENTRY_TRIGGERED
    position, events, _, closure = ActiveTradeLifecycleEngine.observe(position, _observation(position, 3, "89"))
    assert events[0].event_type is LifecycleEventType.TARGET_HIT
    assert closure.gross_pnl == Decimal("9") * position.underlying_quantity
    assert closure.realised_r == Decimal("9") / Decimal("7")


def test_ambiguous_stop_target_span_never_selects_favourable_outcome() -> None:
    position, *_ = _position()
    position, _ = _activate(position)
    # Rebuild the last observation so one subsequent observation jump spans both levels.
    from kronos.swing.v1.native_active_trade_lifecycle import _update
    position = _update(position, last_observed_price=Decimal("121"))
    position, events, notifications, closure = ActiveTradeLifecycleEngine.observe(
        position, _observation(position, 4, "89"),
    )
    assert position.state is ActiveLifecycleState.EVENT_UNRESOLVED
    assert events[-1].event_type is LifecycleEventType.EVENT_UNRESOLVED
    assert not notifications and closure is None


def test_invalidation_is_independent_and_does_not_close_paper() -> None:
    position, *_ = _position()
    position, _ = _activate(position)
    evidence = AnalyticalInvalidationEvidence(
        "INVALIDATION-1", position.canonical_instrument, "1D", NOW,
        position.invalidation, NOW + timedelta(minutes=3), ("DOMAIN-002", "STEP-31"),
    )
    position, event, notification = ActiveTradeLifecycleEngine.observe_invalidation(position, evidence)
    assert position.state is ActiveLifecycleState.PAPER_ACTIVE
    assert event.event_type is LifecycleEventType.INVALIDATION_OBSERVED
    assert notification is None


def test_manual_paper_exit_requires_current_authoritative_observation() -> None:
    position, *_ = _position()
    position, current = _activate(position)
    with pytest.raises(ValueError, match="CURRENT_AUTHORITATIVE"):
        ActiveTradeLifecycleEngine.manual_paper_exit(position, _observation(position, 9, "103"))
    position, event, closure = ActiveTradeLifecycleEngine.manual_paper_exit(position, current)
    assert position.state is ActiveLifecycleState.CLOSED
    assert event.event_type is LifecycleEventType.SPONSOR_MANUAL_EXIT
    assert closure.exit_reason is TradeExitReason.SPONSOR_MANUAL_EXIT


def test_live_target_notifies_but_does_not_close_until_attested_exit() -> None:
    position, *_ = _position(
        SponsorTradeChoice.LIVE, actual_live_entry=Decimal("101"), live_lots=2,
    )
    position, events, notifications, closure = ActiveTradeLifecycleEngine.observe(
        position, _observation(position, 1, "122"),
    )
    assert position.state is ActiveLifecycleState.LIVE_ACTIVE and closure is None
    assert events[0].event_type is LifecycleEventType.TARGET_HIT
    assert notifications[0].message == "ACTION REQUIRED — TARGET HIT"
    repeated, duplicate_events, duplicate_notifications, _ = ActiveTradeLifecycleEngine.observe(
        position, _observation(position, 2, "123"),
    )
    assert repeated.last_observed_price == Decimal("123")
    assert duplicate_events == duplicate_notifications == ()
    unchanged, event, closure = ActiveTradeLifecycleEngine.record_live_exit(
        position, actual_exit=None, exit_timestamp=NOW + timedelta(minutes=2),
        reason=TradeExitReason.SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION,
    )
    assert unchanged == position and event is closure is None
    closed, event, closure = ActiveTradeLifecycleEngine.record_live_exit(
        position, actual_exit=Decimal("121.5"), exit_timestamp=NOW + timedelta(minutes=2),
        reason=TradeExitReason.SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION,
    )
    assert closed.state is ActiveLifecycleState.CLOSED
    assert event.event_type is LifecycleEventType.LIVE_EXIT_RECORDED
    assert closure.gross_pnl == Decimal("20.5") * position.underlying_quantity


def test_monitoring_outage_and_recovery_are_durable_fail_closed_events() -> None:
    position, *_ = _position(SponsorTradeChoice.LIVE, actual_live_entry=Decimal("101"), live_lots=1)
    unavailable, event, notification = ActiveTradeLifecycleEngine.monitoring_unavailable(
        position, occurred_at=NOW + timedelta(minutes=1), provider_context="CONNECTION-LOST",
    )
    assert unavailable.state is ActiveLifecycleState.MONITORING_UNAVAILABLE
    assert event.event_type is LifecycleEventType.MONITORING_UNAVAILABLE
    assert notification.message == "MONITORING UNAVAILABLE"
    recovered, events, _, _ = ActiveTradeLifecycleEngine.observe(
        unavailable, _observation(unavailable, 2, "102"),
    )
    assert recovered.state is ActiveLifecycleState.LIVE_ACTIVE
    assert events[0].event_type is LifecycleEventType.MONITORING_RESUMED


def test_store_restart_recovers_exact_state_events_notifications_and_closure(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result, plan, *_ = _go(SponsorTradeChoice.PAPER)
    service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(tmp_path.resolve()))
    position = service.register(result, plan)
    service.observe(position.position_id, _observation(position, 1, "99"))
    current = service.observe(position.position_id, _observation(position, 2, "102"))
    service.observe(current.position_id, _observation(current, 3, "122"))
    first = service.snapshot()
    restored = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(tmp_path.resolve())).snapshot()
    assert restored == first
    assert restored.positions[0].state is ActiveLifecycleState.CLOSED
    assert len(restored.events) == 3 and len(restored.closures) == 1
    assert restored.events[0].contract_identity == LIFECYCLE_EVENT_CONTRACT_ID
    assert service.manual_paper_exit(
        current.position_id, _observation(current, 3, "122")
    ) == first.closures[0]


def test_service_repeated_monitoring_unavailable_is_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result, plan, *_ = _go(
        SponsorTradeChoice.LIVE, actual_live_entry=Decimal("101"), live_lots=1,
    )
    service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(tmp_path.resolve()))
    position = service.register(result, plan)
    first = service.monitoring_unavailable(
        position.position_id, occurred_at=NOW, provider_context="DISCONNECTED",
    )
    second = service.monitoring_unavailable(
        position.position_id, occurred_at=NOW + timedelta(minutes=1),
        provider_context="DISCONNECTED",
    )
    assert second == first
    assert len(service.snapshot().events) == 1


def test_geometry_never_moves_and_no_broker_methods_exist() -> None:
    position, *_ = _position(SponsorTradeChoice.LIVE, actual_live_entry=Decimal("107"), live_lots=1)
    geometry = (position.model_entry, position.stop, position.invalidation, position.target)
    position, *_ = ActiveTradeLifecycleEngine.observe(position, _observation(position, 1, "108"))
    assert (position.model_entry, position.stop, position.invalidation, position.target) == geometry
    prohibited = {"place_order", "modify_order", "cancel_order", "close_broker_position"}
    assert prohibited.isdisjoint(dir(ActiveTradeLifecycleEngine))


def test_kite_observation_admission_requires_exact_instrument_and_open_domain008_window() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    position, *_ = _position()
    instrument = InstrumentRecord("KITE", "NSE", "NSE", "IOC", "IOC", "EQ", None)
    observed = datetime(2026, 8, 14, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    tick = ProviderMarketTick(
        instrument, Decimal("99"), observed, observed, "KITE_CONNECT_WEBSOCKET",
        "KITE-CONNECTION-1", 1, True, True, True,
    )
    schedule = MarketCalendarPublisher().schedule("NSE", observed.date(), observed_at=observed)
    admitted = admit_kite_lifecycle_observation(position, tick, schedule)
    assert admitted.canonical_instrument == "IOC"
    assert admitted.calendar_identity == schedule.calendar_identity
    closed_tick = ProviderMarketTick(
        instrument, Decimal("99"), observed.replace(hour=16), observed.replace(hour=16),
        "KITE_CONNECT_WEBSOCKET", "KITE-CONNECTION-1", 2, True, True, True,
    )
    with pytest.raises(ValueError, match="ADMISSION_REJECTED"):
        admit_kite_lifecycle_observation(position, closed_tick, schedule)


def test_monitoring_coordinator_subscribes_once_ignores_order_stream_and_stops_closed_paper(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from datetime import datetime
    from zoneinfo import ZoneInfo

    result, plan, *_ = _go(SponsorTradeChoice.PAPER)
    service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(tmp_path.resolve()))
    position = service.register(result, plan)
    instrument = InstrumentRecord("KITE", "NSE", "NSE", "IOC", "IOC", "EQ", None)

    class Session:
        def __init__(self, consumer):  # type: ignore[no-untyped-def]
            self.consumer = consumer; self.subscriptions = (); self.closed = False
        def subscribe(self, values): self.subscriptions = values  # type: ignore[no-untyped-def]
        def connect(self): self.consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
        def unsubscribe(self, values): self.subscriptions = tuple(item for item in self.subscriptions if item not in values)  # type: ignore[no-untyped-def]
        def disconnect(self): self.closed = True

    class Capability:
        active = True
        def __init__(self): self.session = None
        def open_monitoring_session(self, consumer):  # type: ignore[no-untyped-def]
            self.session = Session(consumer); return self.session

    clock = datetime(2026, 8, 14, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    capability = Capability()
    coordinator = ActiveLifecycleMonitoringCoordinator(
        service, MarketCalendarPublisher(), clock=lambda: clock,
    )
    coordinator.attach(position.position_id, capability, instrument)
    assert coordinator.active_position_ids == (position.position_id,)
    with pytest.raises(ValueError, match="ALREADY_ACTIVE"):
        coordinator.attach(position.position_id, capability, instrument)
    before_order = service.snapshot()
    capability.session.consumer.on_order_update(object())
    assert service.snapshot() == before_order
    for sequence, price in ((1, "99"), (2, "102"), (3, "122")):
        moment = clock + timedelta(minutes=sequence)
        capability.session.consumer.on_market_tick(ProviderMarketTick(
            instrument, Decimal(price), moment, moment, "KITE_CONNECT_WEBSOCKET",
            "KITE-CONNECTION-1", sequence, True, True, True,
        ))
    assert service.snapshot().positions[0].state is ActiveLifecycleState.CLOSED
    assert capability.session.closed is True
    assert coordinator.active_position_ids == ()


def test_monitoring_shutdown_closes_transport_without_mutating_position(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result, plan, *_ = _go(SponsorTradeChoice.PAPER)
    service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(tmp_path.resolve()))
    position = service.register(result, plan)
    instrument = InstrumentRecord("KITE", "NSE", "NSE", "IOC", "IOC", "EQ", None)

    class Session:
        def __init__(self, consumer): self.consumer = consumer; self.closed = False  # type: ignore[no-untyped-def]
        def subscribe(self, _values): pass  # type: ignore[no-untyped-def]
        def connect(self): pass
        def unsubscribe(self, _values): pass  # type: ignore[no-untyped-def]
        def disconnect(self):
            self.closed = True
            self.consumer.on_connection_state(MonitoringConnectionState.DISCONNECTED)

    class Capability:
        active = True
        def open_monitoring_session(self, consumer):  # type: ignore[no-untyped-def]
            self.session = Session(consumer)
            return self.session

    capability = Capability()
    coordinator = ActiveLifecycleMonitoringCoordinator(
        service, MarketCalendarPublisher(), clock=lambda: NOW,
    )
    coordinator.attach(position.position_id, capability, instrument)
    before = service.snapshot()
    coordinator.close()
    assert capability.session.closed is True
    assert coordinator.active_position_ids == ()
    assert service.snapshot() == before
    capability.session.consumer.on_market_tick(object())
    coordinator.close()
    assert service.snapshot() == before
