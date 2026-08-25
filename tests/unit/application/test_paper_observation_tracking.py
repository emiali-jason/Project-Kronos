from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from kronos.application.paper_observation_tracking import (
    PAPER_OBSERVATION_TRACK_OWNER_IDENTITY,
    PaperObservationTrackingWorkflow,
)
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
)
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.paper_observation_track import (
    LocalPaperObservationTrackStore,
    PaperObservationMonitoringState,
    PaperObservationOutcome,
    PaperObservationTrackState,
)
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorActivationDisposition,
)
from tests.unit.swing.v1.test_sponsor_observation_decision import (
    NOW,
    _green,
    _record,
)


class _Session:
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


class _Capability:
    active = True

    def __init__(self) -> None:
        self.sessions = []

    def open_monitoring_session(self, consumer):  # type: ignore[no-untyped-def]
        session = _Session(consumer)
        self.sessions.append(session)
        return session


class _HistoricalCapability(_Capability):
    def __init__(self, candles) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self.candles = candles
        self.requests = []

    def historical_candles(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        return self.candles


class _OtherConsumer:
    owner_identity = "KR380_TEST_CONSUMER"

    def on_market_tick(self, _tick): return None  # type: ignore[no-untyped-def]
    def on_order_update(self, _update): return None  # type: ignore[no-untyped-def]
    def on_connection_state(self, _state): return None  # type: ignore[no-untyped-def]


def _decision(tmp_path):  # type: ignore[no-untyped-def]
    completed, observation = _green(tmp_path)
    return _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
    )


def _instrument(result):  # type: ignore[no-untyped-def]
    symbol = result.snapshot.canonical_instrument
    return InstrumentRecord("KITE", "NSE", "NSE", symbol, symbol, "EQ", None)


def _tick(instrument, price, sequence, at):  # type: ignore[no-untyped-def]
    return ProviderMarketTick(
        instrument,
        Decimal(price),
        at,
        at,
        "KITE_CONNECT_WEBSOCKET",
        "CONNECTION-1",
        sequence,
        True,
        True,
        True,
    )


def test_explicit_start_shares_one_socket_and_has_distinct_owner(tmp_path) -> None:
    result = _decision(tmp_path)
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    hub = SharedSwingMonitoringHub()
    workflow.set_shared_monitoring_hub(hub)
    capability = _Capability()
    instrument = _instrument(result)

    other = hub.open(capability, _OtherConsumer())
    other.subscribe((instrument,))
    other.connect()
    started = workflow.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    assert started.monitoring_state is PaperObservationMonitoringState.NOT_ACTIVE
    active = workflow.attach_monitoring(
        started.track.track_identity, capability, instrument
    )

    assert active.track_state is PaperObservationTrackState.ACTIVE
    assert len(capability.sessions) == 1
    assert hub.subscription_count == 1
    assert hub.subscription_reference_count(instrument) == 2
    assert hub.subscription_owner_identities(instrument) == (
        "KR380_TEST_CONSUMER",
        PAPER_OBSERVATION_TRACK_OWNER_IDENTITY,
    )
    workflow.close()
    assert hub.subscription_reference_count(instrument) == 1
    assert capability.sessions[0].disconnections == 0
    other.disconnect()
    assert capability.sessions[0].disconnections == 1


def test_ordered_ticks_record_entry_then_target_without_position_or_order(tmp_path) -> None:
    result = _decision(tmp_path)
    clock_values = iter(
        NOW + timedelta(seconds=value) for value in range(1, 20)
    )
    workflow = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(tmp_path / "tracks"),
        clock=lambda: next(clock_values),
    )
    hub = SharedSwingMonitoringHub()
    workflow.set_shared_monitoring_hub(hub)
    capability = _Capability()
    instrument = _instrument(result)
    started = workflow.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    workflow.attach_monitoring(started.track.track_identity, capability, instrument)
    entry = started.track.observation_entry_reference
    target = started.track.target
    assert entry is not None and target is not None

    transport = capability.sessions[0].consumer
    transport.on_market_tick(_tick(
        instrument, str(entry - Decimal("1")), 1, NOW + timedelta(minutes=1)
    ))
    transport.on_market_tick(_tick(instrument, str(entry), 2, NOW + timedelta(minutes=2)))
    entered = workflow.projection(started.track.track_identity)
    assert entered.entry_state is PaperObservationOutcome.ENTRY_OBSERVED
    transport.on_market_tick(_tick(instrument, str(target), 3, NOW + timedelta(minutes=3)))
    complete = workflow.projection(started.track.track_identity)

    assert complete.track_state is PaperObservationTrackState.COMPLETE
    assert complete.outcome_state is PaperObservationOutcome.TARGET_LEVEL_TOUCHED
    assert workflow.active_monitoring_count == 0
    assert capability.sessions[0].disconnections == 1
    transport.on_order_update(object())
    assert complete == workflow.projection(started.track.track_identity)
    assert not hasattr(complete, "position")
    assert not hasattr(complete, "order")


def test_ordered_ticks_record_entry_then_stop_without_position_or_loss_claim(tmp_path) -> None:
    result = _decision(tmp_path)
    clock_values = iter(
        NOW + timedelta(seconds=value) for value in range(1, 20)
    )
    workflow = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(tmp_path / "tracks"),
        clock=lambda: next(clock_values),
    )
    hub = SharedSwingMonitoringHub()
    workflow.set_shared_monitoring_hub(hub)
    capability = _Capability()
    instrument = _instrument(result)
    started = workflow.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    workflow.attach_monitoring(started.track.track_identity, capability, instrument)
    entry = started.track.observation_entry_reference
    stop = started.track.stop
    assert entry is not None and stop is not None

    transport = capability.sessions[0].consumer
    transport.on_market_tick(_tick(
        instrument, str(entry - Decimal("1")), 1, NOW + timedelta(minutes=1)
    ))
    transport.on_market_tick(_tick(instrument, str(entry), 2, NOW + timedelta(minutes=2)))
    transport.on_market_tick(_tick(instrument, str(stop), 3, NOW + timedelta(minutes=3)))
    complete = workflow.projection(started.track.track_identity)

    assert complete.track_state is PaperObservationTrackState.COMPLETE
    assert complete.entry_state is PaperObservationOutcome.ENTRY_OBSERVED
    assert complete.outcome_state is PaperObservationOutcome.STOP_LEVEL_TOUCHED
    assert not hasattr(complete, "position")
    assert not hasattr(complete, "pnl")


@pytest.mark.parametrize("level_name", ["stop", "target"])
def test_stop_or_target_before_entry_has_no_post_entry_outcome_authority(
    tmp_path, level_name
) -> None:  # type: ignore[no-untyped-def]
    result = _decision(tmp_path)
    workflow = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(tmp_path / "tracks"), clock=lambda: NOW
    )
    started = workflow.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    instrument = _instrument(result)
    entry = started.track.observation_entry_reference
    stop = started.track.stop
    target = started.track.target
    assert entry is not None and stop is not None and target is not None

    level = stop if level_name == "stop" else target
    before_entry = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, str(level), 1, NOW + timedelta(minutes=1)),
    )

    assert before_entry.track_state is PaperObservationTrackState.ACTIVE
    assert before_entry.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert before_entry.outcome_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED


def test_registration_failure_preserves_active_track_as_not_monitored(tmp_path) -> None:
    result = _decision(tmp_path)
    workflow = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(tmp_path / "tracks"), clock=lambda: NOW
    )
    started = workflow.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )

    retained = workflow.attach_monitoring(
        started.track.track_identity, _Capability(), _instrument(result)
    )

    assert retained.track_state is PaperObservationTrackState.ACTIVE
    assert retained.monitoring_state is PaperObservationMonitoringState.NOT_ACTIVE
    assert retained.monitoring_reason == "SHARED_MONITORING_HUB_UNAVAILABLE"


def test_incomplete_candle_is_excluded_and_same_candle_ordering_is_unresolved(
    tmp_path,
) -> None:
    result = _decision(tmp_path)
    workflow = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(tmp_path / "tracks"), clock=lambda: NOW
    )
    started = workflow.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    track = started.track
    values = tuple(
        value for value in (
            track.observation_entry_reference, track.stop, track.target
        ) if value is not None
    )
    low, high = min(values) - Decimal("1"), max(values) + Decimal("1")
    excluded = workflow.reconcile_completed_candle(
        track.track_identity,
        low=low,
        high=high,
        completed_at=NOW + timedelta(hours=1),
        source_identity="DOMAIN008-CANDLE-1",
        domain008_completed=False,
        interval_open=track.observation_entry_reference - Decimal("1"),
        interval_close=track.observation_entry_reference + Decimal("1"),
    )
    assert excluded.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    complete = workflow.reconcile_completed_candle(
        track.track_identity,
        low=low,
        high=high,
        completed_at=NOW + timedelta(hours=1),
        source_identity="DOMAIN008-CANDLE-1",
        domain008_completed=True,
        interval_open=track.observation_entry_reference - Decimal("1"),
        interval_close=track.observation_entry_reference + Decimal("1"),
    )
    assert complete.entry_state is PaperObservationOutcome.ENTRY_OBSERVED
    assert complete.outcome_state is PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED


def test_restart_restores_incomplete_track_and_disconnect_fails_closed(tmp_path) -> None:
    result = _decision(tmp_path)
    root = tmp_path / "tracks"
    first = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(root), clock=lambda: NOW
    )
    started = first.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    hub = SharedSwingMonitoringHub()
    first.set_shared_monitoring_hub(hub)
    capability = _Capability()
    first.attach_monitoring(
        started.track.track_identity, capability, _instrument(result)
    )
    first.mark_monitoring_unavailable("PROVIDER_DISCONNECTED")
    assert first.projection(started.track.track_identity).track_state is PaperObservationTrackState.MONITORING_INTERRUPTED

    restored = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(root), clock=lambda: NOW
    )
    restored_hub = SharedSwingMonitoringHub()
    restored.set_shared_monitoring_hub(restored_hub)
    restored_capability = _Capability()
    identities = restored.restore_monitoring(
        restored_capability, lambda _symbol: _instrument(result)
    )
    assert identities == (started.track.track_identity,)
    assert restored.projection(started.track.track_identity).monitoring_state is PaperObservationMonitoringState.ACTIVE
    restored_capability.sessions[0].consumer.on_connection_state(
        MonitoringConnectionState.RECONNECTING
    )
    interrupted = restored.projection(started.track.track_identity)
    assert interrupted.track_state is PaperObservationTrackState.MONITORING_INTERRUPTED
    assert interrupted.outcome_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED


def test_gap_reconciliation_uses_only_completed_domain008_candles(tmp_path) -> None:
    result = _decision(tmp_path)
    workflow = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(tmp_path / "tracks"), clock=lambda: NOW
    )
    started = workflow.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    values = tuple(
        value for value in (
            started.track.observation_entry_reference,
            started.track.stop,
            started.track.target,
        ) if value is not None
    )
    capability = _HistoricalCapability((HistoricalCandle(
        timestamp=datetime(2026, 8, 21, 8, 45, tzinfo=UTC),
        open=float(started.track.observation_entry_reference - Decimal("1")),
        high=float(max(values) + Decimal("1")),
        low=float(min(values) - Decimal("1")),
        close=float(started.track.observation_entry_reference + Decimal("1")),
        volume=100,
    ),))
    projection = workflow.reconcile_gap_from_provider(
        started.track.track_identity,
        capability,
        _instrument(result),
        observed_at=datetime(2026, 8, 21, 11, 0, tzinfo=UTC),
    )
    assert len(capability.requests) == 1
    assert projection.entry_state is PaperObservationOutcome.ENTRY_OBSERVED
    assert projection.outcome_state is PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED
    assert projection.track_state is PaperObservationTrackState.COMPLETE


def test_recovered_or_unordered_tick_is_factual_but_has_no_outcome_authority(
    tmp_path,
) -> None:
    result = _decision(tmp_path)
    workflow = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(tmp_path / "tracks"), clock=lambda: NOW
    )
    started = workflow.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    instrument = _instrument(result)
    tick = ProviderMarketTick(
        instrument,
        started.track.observation_entry_reference,
        NOW + timedelta(minutes=1),
        NOW + timedelta(minutes=1),
        "KITE_CONNECT_WEBSOCKET",
        "RECOVERED-CONNECTION",
        7,
        True,
        True,
        False,
    )
    projection = workflow.observe_tick(started.track.track_identity, tick)
    assert projection.track_state is PaperObservationTrackState.MONITORING_INTERRUPTED
    assert projection.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert projection.monitoring_reason == "ORDERED_LIVE_FACTS_UNAVAILABLE"
