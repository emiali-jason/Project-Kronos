from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

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
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.native_trade_construction import construct_trade_plan
from kronos.swing.v1.paper_observation_track import (
    LocalPaperObservationTrackStore,
    PaperObservationMonitoringState,
    PaperObservationOutcome,
    PaperObservationTrackState,
)
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorActivationDisposition,
)
from kronos.swing.v1.step31_observation import construct_step31_observation
from tests.unit.swing.v1.test_kr370_step31_handoff import (
    _completed,
    _context,
    _evidence,
    _handoff,
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


def _decision(tmp_path, *, direction=V1Direction.LONG):  # type: ignore[no-untyped-def]
    if direction is V1Direction.LONG:
        completed, observation = _green(tmp_path)
    else:
        completed = _completed(tmp_path, direction=direction)
        handoff = _handoff(completed)
        evidence = _evidence(completed)
        context = _context(completed.requirement.canonical_instrument)
        plan = construct_trade_plan(
            completed.requirement, handoff, evidence, context, created_at=NOW
        )
        observation = construct_step31_observation(
            completed.requirement,
            handoff,
            evidence,
            context,
            created_at=NOW,
            conventional_plan=plan,
        )
    return _record(
        completed,
        observation,
        SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
    )


def _instrument(result):  # type: ignore[no-untyped-def]
    symbol = result.snapshot.canonical_instrument
    return InstrumentRecord("KITE", "NSE", "NSE", symbol, symbol, "EQ", None)


def _tick(
    instrument,
    price,
    sequence,
    at,
    *,
    connection="CONNECTION-1",
    received_at=None,
    ordering_deterministic=True,
    recovered=False,
):  # type: ignore[no-untyped-def]
    return ProviderMarketTick(
        instrument,
        Decimal(price),
        at,
        at if received_at is None else received_at,
        "KITE_CONNECT_WEBSOCKET",
        connection,
        sequence,
        True,
        True,
        ordering_deterministic,
        recovered,
    )


def _started(tmp_path, *, direction=V1Direction.LONG):  # type: ignore[no-untyped-def]
    result = _decision(tmp_path, direction=direction)
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    started = workflow.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    return workflow, store, started, _instrument(result)


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


def test_unsequenced_ticks_receive_distinct_kronos_observation_identities(
    tmp_path,
) -> None:
    workflow, store, started, instrument = _started(tmp_path)
    entry = started.track.observation_entry_reference
    assert entry is not None
    first = _tick(instrument, entry - Decimal("1"), None, NOW + timedelta(minutes=1))
    second = _tick(instrument, entry, None, NOW + timedelta(minutes=2))

    legacy_first = f"{first.source}:{first.connection_id}:NO_SEQUENCE"
    legacy_second = f"{second.source}:{second.connection_id}:NO_SEQUENCE"
    assert legacy_first == legacy_second  # Reproduces the removed collision rule.

    workflow.observe_tick(started.track.track_identity, first)
    projection = workflow.observe_tick(started.track.track_identity, second)
    facts = store.facts(started.track.track_identity)

    assert len(facts) == 2
    assert facts[0].source_identity != facts[1].source_identity
    assert all("KRONOS_UNSEQUENCED_OBSERVATION" in item.source_identity for item in facts)
    assert projection.entry_state is PaperObservationOutcome.ENTRY_OBSERVED
    assert projection.monitoring_reason != "PROVIDER_SEQUENCE_CONFLICT"


def test_exact_unsequenced_observation_replay_is_idempotent(tmp_path) -> None:
    workflow, store, started, instrument = _started(tmp_path)
    entry = started.track.observation_entry_reference
    assert entry is not None
    tick = _tick(instrument, entry - Decimal("1"), None, NOW + timedelta(minutes=1))

    first = workflow.observe_tick(started.track.track_identity, tick)
    replay = workflow.observe_tick(started.track.track_identity, tick)

    assert replay == first
    assert len(store.facts(started.track.track_identity)) == 1

    equivalent = _tick(
        instrument,
        Decimal(f"{tick.last_price}0"),
        None,
        tick.observed_at.astimezone(ZoneInfo("Asia/Kolkata")),
    )
    assert workflow.observe_tick(started.track.track_identity, equivalent) == first
    assert len(store.facts(started.track.track_identity)) == 1


def test_same_unsequenced_price_at_different_times_is_not_a_replay(tmp_path) -> None:
    workflow, store, started, instrument = _started(tmp_path)
    entry = started.track.observation_entry_reference
    assert entry is not None

    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), None, NOW + timedelta(minutes=1)),
    )
    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), None, NOW + timedelta(minutes=2)),
    )

    facts = store.facts(started.track.track_identity)
    assert len(facts) == 2
    assert facts[0].source_identity != facts[1].source_identity
    assert all(item.source_sequence is None for item in facts)


def test_unsequenced_identity_does_not_invent_provider_sequence(tmp_path) -> None:
    workflow, store, started, instrument = _started(tmp_path)
    entry = started.track.observation_entry_reference
    assert entry is not None

    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), None, NOW + timedelta(minutes=1)),
    )
    fact = store.facts(started.track.track_identity)[0]

    assert fact.source_sequence is None
    assert not fact.source_identity.endswith(":0")
    assert not fact.source_identity.endswith(":1")
    assert ":NO_SEQUENCE" not in fact.source_identity


def test_equal_time_unsequenced_price_change_is_retained_without_order_authority(
    tmp_path,
) -> None:
    workflow, store, started, instrument = _started(tmp_path)
    entry = started.track.observation_entry_reference
    assert entry is not None
    observed_at = NOW + timedelta(minutes=1)

    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), None, observed_at),
    )
    projection = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry, None, observed_at),
    )

    assert len(store.facts(started.track.track_identity)) == 2
    assert projection.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert projection.monitoring_state is PaperObservationMonitoringState.INTERRUPTED
    assert projection.monitoring_reason == "ORDERED_LIVE_FACTS_UNAVAILABLE"

    later = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry + Decimal("1"), None, observed_at + timedelta(minutes=1)),
    )
    assert later.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert later.monitoring_reason == "ORDERED_LIVE_FACTS_UNAVAILABLE"


def test_older_unsequenced_tick_is_retained_without_order_authority(tmp_path) -> None:
    workflow, store, started, instrument = _started(tmp_path)
    entry = started.track.observation_entry_reference
    assert entry is not None

    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), None, NOW + timedelta(minutes=2)),
    )
    projection = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry, None, NOW + timedelta(minutes=1)),
    )

    assert len(store.facts(started.track.track_identity)) == 2
    assert projection.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert projection.monitoring_reason == "ORDERED_LIVE_FACTS_UNAVAILABLE"


def test_sequenced_duplicate_conflict_behavior_is_preserved(tmp_path) -> None:
    workflow, store, started, instrument = _started(tmp_path)
    entry = started.track.observation_entry_reference
    assert entry is not None

    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), 7, NOW + timedelta(minutes=1)),
    )
    projection = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry, 7, NOW + timedelta(minutes=2)),
    )

    assert len(store.facts(started.track.track_identity)) == 1
    assert projection.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert projection.monitoring_reason == "PROVIDER_SEQUENCE_CONFLICT"

    later = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry + Decimal("1"), 8, NOW + timedelta(minutes=3)),
    )
    assert later.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert later.monitoring_reason == "PROVIDER_SEQUENCE_CONFLICT"


def test_present_provider_sequence_behavior_is_unchanged(tmp_path) -> None:
    workflow, store, started, instrument = _started(tmp_path)
    entry = started.track.observation_entry_reference
    assert entry is not None

    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), 7, NOW + timedelta(minutes=1)),
    )
    projection = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry, 8, NOW + timedelta(minutes=2)),
    )

    assert projection.entry_state is PaperObservationOutcome.ENTRY_OBSERVED
    assert [item.source_sequence for item in store.facts(started.track.track_identity)] == [7, 8]


@pytest.mark.parametrize(
    ("direction", "before_offset", "cross_offset"),
    (
        (V1Direction.LONG, Decimal("-1"), Decimal("0")),
        (V1Direction.SHORT, Decimal("1"), Decimal("0")),
    ),
)
def test_unsequenced_exact_directional_crossing_observes_entry(
    tmp_path, direction, before_offset, cross_offset
) -> None:  # type: ignore[no-untyped-def]
    workflow, _store, started, instrument = _started(tmp_path, direction=direction)
    entry = started.track.observation_entry_reference
    assert entry is not None

    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry + before_offset, None, NOW + timedelta(minutes=1)),
    )
    projection = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry + cross_offset, None, NOW + timedelta(minutes=2)),
    )

    assert projection.entry_state is PaperObservationOutcome.ENTRY_OBSERVED


def test_vbl_like_unsequenced_short_path_retains_all_ticks_and_one_entry(
    tmp_path,
) -> None:
    workflow, store, started, instrument = _started(
        tmp_path, direction=V1Direction.SHORT
    )
    entry = started.track.observation_entry_reference
    assert entry is not None
    ticks = (
        _tick(instrument, entry + Decimal("0.35"), None, NOW + timedelta(minutes=1)),
        _tick(instrument, entry + Decimal("0.15"), None, NOW + timedelta(minutes=2)),
        _tick(instrument, entry - Decimal("0.05"), None, NOW + timedelta(minutes=3)),
        _tick(instrument, entry - Decimal("0.15"), None, NOW + timedelta(minutes=4)),
    )

    for tick in ticks:
        projection = workflow.observe_tick(started.track.track_identity, tick)
    replay = workflow.observe_tick(started.track.track_identity, ticks[1])
    events = store.events(started.track.track_identity)

    assert len(store.facts(started.track.track_identity)) == 4
    assert projection.entry_state is PaperObservationOutcome.ENTRY_OBSERVED
    assert replay.entry_state is PaperObservationOutcome.ENTRY_OBSERVED
    assert sum(
        item.outcome is PaperObservationOutcome.ENTRY_OBSERVED for item in events
    ) == 1
    assert replay.monitoring_reason != "PROVIDER_SEQUENCE_CONFLICT"


@pytest.mark.parametrize(
    ("direction", "first_offset", "second_offset"),
    (
        (V1Direction.LONG, Decimal("1"), Decimal("2")),
        (V1Direction.SHORT, Decimal("-1"), Decimal("-2")),
    ),
)
def test_first_unsequenced_tick_beyond_entry_does_not_establish_entry(
    tmp_path, direction, first_offset, second_offset
) -> None:  # type: ignore[no-untyped-def]
    workflow, _store, started, instrument = _started(tmp_path, direction=direction)
    entry = started.track.observation_entry_reference
    assert entry is not None

    first = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry + first_offset, None, NOW + timedelta(minutes=1)),
    )
    second = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry + second_offset, None, NOW + timedelta(minutes=2)),
    )

    assert first.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert second.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED


@pytest.mark.parametrize("terminal", ["target", "stop"])
def test_unsequenced_post_entry_terminal_crossing_remains_factual(
    tmp_path, terminal
) -> None:  # type: ignore[no-untyped-def]
    workflow, _store, started, instrument = _started(tmp_path)
    entry = started.track.observation_entry_reference
    level = getattr(started.track, terminal)
    assert entry is not None and level is not None

    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), None, NOW + timedelta(minutes=1)),
    )
    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry, None, NOW + timedelta(minutes=2)),
    )
    projection = workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, level, None, NOW + timedelta(minutes=3)),
    )

    expected = (
        PaperObservationOutcome.TARGET_LEVEL_TOUCHED
        if terminal == "target"
        else PaperObservationOutcome.STOP_LEVEL_TOUCHED
    )
    assert projection.track_state is PaperObservationTrackState.COMPLETE
    assert projection.outcome_state is expected
    assert not hasattr(projection, "position")
    assert not hasattr(projection, "pnl")


def test_restart_with_new_connection_preserves_unsequenced_crossing_continuity(
    tmp_path,
) -> None:
    result = _decision(tmp_path)
    root = tmp_path / "tracks"
    store = LocalPaperObservationTrackStore(root)
    first = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    started = first.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    instrument = _instrument(result)
    entry = started.track.observation_entry_reference
    assert entry is not None
    first.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), None, NOW + timedelta(minutes=1)),
    )

    restored_store = LocalPaperObservationTrackStore(root)
    restored = PaperObservationTrackingWorkflow(restored_store, clock=lambda: NOW)
    replay = restored.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), None, NOW + timedelta(minutes=1)),
    )
    assert replay.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert len(restored_store.facts(started.track.track_identity)) == 1
    assert restored_store.load_track(started.track.track_identity) == started.track

    projection = restored.observe_tick(
        started.track.track_identity,
        _tick(
            instrument,
            entry,
            None,
            NOW + timedelta(minutes=2),
            connection="CONNECTION-2",
        ),
    )

    assert projection.entry_state is PaperObservationOutcome.ENTRY_OBSERVED
    assert len(restored_store.facts(started.track.track_identity)) == 2


def test_new_connection_equal_time_tick_fails_closed_across_restart(tmp_path) -> None:
    result = _decision(tmp_path)
    root = tmp_path / "tracks"
    store = LocalPaperObservationTrackStore(root)
    first = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    started = first.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=NOW,
    )
    instrument = _instrument(result)
    entry = started.track.observation_entry_reference
    observed_at = NOW + timedelta(minutes=1)
    assert entry is not None
    first.observe_tick(
        started.track.track_identity,
        _tick(instrument, entry - Decimal("1"), None, observed_at),
    )

    restored = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(root), clock=lambda: NOW
    )
    projection = restored.observe_tick(
        started.track.track_identity,
        _tick(
            instrument,
            entry,
            None,
            observed_at,
            connection="CONNECTION-2",
        ),
    )

    assert projection.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert projection.monitoring_reason == "ORDERED_LIVE_FACTS_UNAVAILABLE"
