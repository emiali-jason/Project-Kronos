from datetime import UTC, datetime, timedelta
from dataclasses import replace
from decimal import Decimal
from threading import Thread
from pathlib import Path
import json
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
    PaperObservationMonitoringApplicabilityState,
    PaperObservationMonitoringAuthorityV1,
    PaperObservationMonitoringState,
    PaperObservationOutcome,
    PaperObservationTrackState,
    create_paper_observation_track,
    make_market_fact,
    make_monitoring_applicability,
    paper_observation_instrument_contract_identity,
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


def _monitoring_authority(track, *, material_revision="MATERIAL-REVISION-V1"):  # type: ignore[no-untyped-def]
    return PaperObservationMonitoringAuthorityV1(
        native_run_identity=track.native_run_identity,
        sponsor_decision_identity=track.sponsor_decision_identity,
        opportunity_identity=f"SWING-OPPORTUNITY-{track.canonical_instrument}",
        material_revision=material_revision,
        native_assessment_sha256=track.native_assessment_sha256,
        direction=track.direction,
        geometry_identity=track.step31_observation_identity,
        geometry_sha256=track.step31_observation_sha256,
        review_authority_identity="WO-SWING-07-REVIEW-V1",
        decision_authority_identity=track.sponsor_decision_identity,
        canonical_instrument=track.canonical_instrument,
        instrument_contract_identity=paper_observation_instrument_contract_identity(
            canonical_instrument=track.canonical_instrument,
            provider="KITE", exchange="NSE", segment="NSE",
            trading_symbol=track.canonical_instrument,
            instrument_type="EQ", expiry=None,
        ),
        monitoring_boundary_identity="SWING-D1-CLOSE",
        monitoring_window_identity="FROM_OBSERVATION_BOUNDARY_UNTIL_TERMINAL",
        capability_requirements=("KITE-READ-ONLY", "ORDERED-LIVE-TICKS"),
        policy_identity="SWING-SPONSOR-OBSERVATION-DECISION-V1",
        policy_version="1",
    )


def _retain_open_applicability(store, track):  # type: ignore[no-untyped-def]
    authority = _monitoring_authority(track)
    record = make_monitoring_applicability(
        track.track_identity,
        PaperObservationMonitoringApplicabilityState.OPEN,
        "MONITORING_OPENED",
        authority,
        NOW,
    )
    store.append_applicability(record)
    store.publish_current_applicability(record)
    return authority


def _admit(workflow, result, *, started_at=NOW, compact=False):  # type: ignore[no-untyped-def]
    track = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=started_at,
    )
    authority = _monitoring_authority(track)
    if not compact:
        # Retained V1 fixture: exercise the unchanged explicit full-history path.
        workflow._store.retain_track(track)
        _retain_open_applicability(workflow._store, track)
        workflow._retain_monitoring(track.track_identity,
            PaperObservationMonitoringState.NOT_ACTIVE,
            "MONITORING_CAPABILITY_NOT_YET_REGISTERED", started_at)
        return workflow.projection(track.track_identity)
    return workflow.start(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        started_at=started_at,
        monitoring_authority=authority,
        authority_is_current=lambda: True,
    )


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
    started = _admit(workflow, result)
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
    started = _admit(workflow, result)
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
    started = _admit(workflow, result)
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
    started = _admit(workflow, result)
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
    started = _admit(workflow, result)
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
    started = _admit(workflow, result)

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
    started = _admit(workflow, result)
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
    started = _admit(first, result)
    authority = _retain_open_applicability(first._store, started.track)
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
        restored_capability,
        lambda _symbol: _instrument(result),
        lambda _track: authority,
    )
    assert identities == (started.track.track_identity,)
    assert restored.projection(started.track.track_identity).monitoring_state is PaperObservationMonitoringState.ACTIVE
    restored_capability.sessions[0].consumer.on_connection_state(
        MonitoringConnectionState.RECONNECTING
    )
    interrupted = restored.projection(started.track.track_identity)
    assert interrupted.track_state is PaperObservationTrackState.MONITORING_INTERRUPTED
    assert interrupted.outcome_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED


def test_restart_restoration_reads_no_facts_and_registers_active_track_once(
    tmp_path, monkeypatch
) -> None:
    _, store, started, instrument = _started(tmp_path)
    authority = _retain_open_applicability(store, started.track)
    for sequence in range(256):
        store.append_fact(make_market_fact(
            started.track,
            last_price=started.track.observation_entry_reference or Decimal("100"),
            observed_at=NOW + timedelta(microseconds=sequence + 1),
            received_at=NOW + timedelta(microseconds=sequence + 1),
            source_identity=f"KITE:RESTORE-SCALE:{sequence}",
            source_sequence=sequence,
            ordering_deterministic=True,
            recovered=False,
        ))
    restored = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    restored.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    capability = _Capability()
    fact_reads = []

    def forbidden_facts(*_args):  # type: ignore[no-untyped-def]
        fact_reads.append(1)
        raise AssertionError("restoration must not read historical facts")

    monkeypatch.setattr(store, "facts", forbidden_facts)
    first = restored.restore_monitoring(
        capability, lambda _symbol: instrument, lambda _track: authority
    )
    second = restored.restore_monitoring(
        capability, lambda _symbol: instrument, lambda _track: authority
    )
    assert first == second == (started.track.track_identity,)
    assert fact_reads == []
    assert len(capability.sessions) == 1
    assert restored.active_monitoring_count == 1


def test_restart_restoration_excludes_completed_track(tmp_path) -> None:
    workflow, store, started, instrument = _started(tmp_path)
    entry = started.track.observation_entry_reference
    target = started.track.target
    assert entry is not None and target is not None
    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, str(entry - Decimal("1")), 1, NOW + timedelta(minutes=1)),
    )
    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, str(entry), 2, NOW + timedelta(minutes=2)),
    )
    workflow.observe_tick(
        started.track.track_identity,
        _tick(instrument, str(target), 3, NOW + timedelta(minutes=3)),
    )
    restored = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    restored.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    resolver_calls = []
    assert restored.restore_monitoring(
        _Capability(), lambda symbol: resolver_calls.append(symbol)
    ) == ()
    assert resolver_calls == []
    assert store.restoration_projection(started.track.track_identity).terminal


def test_legacy_and_incompatible_tracks_are_not_automatically_restored(tmp_path) -> None:
    _, store, started, instrument = _started(tmp_path)
    restored = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    restored.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    capability = _Capability()
    before = tuple(store.root.rglob("*.json"))
    assert restored.restore_monitoring(capability, lambda _symbol: instrument) == ()
    assert tuple(store.root.rglob("*.json")) == before
    assert capability.sessions == []

    retained = _retain_open_applicability(store, started.track)
    incompatible = _monitoring_authority(
        started.track, material_revision="MATERIAL-REVISION-V2"
    )
    assert restored.restore_monitoring(
        capability, lambda _symbol: instrument, lambda _track: incompatible
    ) == ()
    projection = store.restoration_projection(
        started.track.track_identity, incompatible
    )
    assert projection.applicability.state is PaperObservationMonitoringApplicabilityState.SUSPENDED
    assert projection.applicability.reason_codes == ("MATERIAL_REVISION_INCOMPATIBLE",)
    assert capability.sessions == []
    assert retained.material_revision == "MATERIAL-REVISION-V1"


def test_two_historical_shaped_tracks_require_explicit_recovery(tmp_path) -> None:
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    first_result = _decision(tmp_path / "first", direction=V1Direction.LONG)
    second_result = _decision(tmp_path / "second", direction=V1Direction.SHORT)
    first = create_paper_observation_track(
        first_result,
        current_run_identity=first_result.snapshot.native_run_identity,
        created_at=NOW,
    )
    second = create_paper_observation_track(
        second_result,
        current_run_identity=second_result.snapshot.native_run_identity,
        created_at=NOW,
    )
    store.retain_track(first)
    store.retain_track(second)
    assert first.track_identity != second.track_identity
    assert first.canonical_instrument == second.canonical_instrument
    restored = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    restored.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    capability = _Capability()
    before = {path: path.read_bytes() for path in store.root.rglob("*.json")}
    assert restored.restore_monitoring(
        capability, lambda _symbol: _instrument(first_result)
    ) == ()
    assert capability.sessions == []
    assert {path: path.read_bytes() for path in store.root.rglob("*.json")} == before
    status = restored.restoration_status()
    assert status["legacy_without_applicability"] == 2
    assert status["recovery_required"] == 2
    assert status["restored"] == 0
    for track in (first, second):
        projection = store.restoration_projection(track.track_identity)
        assert projection.applicability.state is PaperObservationMonitoringApplicabilityState.SUSPENDED
        assert projection.applicability.operation == "RECOVERY_REQUIRED"


def test_gap_reconciliation_uses_only_completed_domain008_candles(tmp_path) -> None:
    result = _decision(tmp_path)
    workflow = PaperObservationTrackingWorkflow(
        LocalPaperObservationTrackStore(tmp_path / "tracks"), clock=lambda: NOW
    )
    started = _admit(workflow, result)
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
    started = _admit(workflow, result)
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
    started = _admit(first, result)
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
    started = _admit(first, result)
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


def test_prospective_admission_publishes_open_authority_and_exact_replay_is_idempotent(
    tmp_path,
) -> None:
    result = _decision(tmp_path)
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    first = _admit(workflow, result, compact=True)
    before = {path: path.read_bytes() for path in store.root.rglob("*.json")}
    second = _admit(workflow, result, started_at=NOW + timedelta(minutes=1), compact=True)
    current = store.current_applicability(first.track.track_identity)

    assert second.track == first.track
    assert current is not None
    assert current.state is PaperObservationMonitoringApplicabilityState.OPEN
    assert current.track_identity == first.track.track_identity
    assert current.authority.sponsor_decision_identity == first.track.sponsor_decision_identity
    assert {path: path.read_bytes() for path in store.root.rglob("*.json")} == before


def test_conflicting_admission_replay_fails_closed_and_preserves_current_pointer(
    tmp_path,
) -> None:
    result = _decision(tmp_path)
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    admitted = _admit(workflow, result, compact=True)
    current = store.current_applicability(admitted.track.track_identity)
    assert current is not None
    conflict = replace(current.authority, material_revision="MATERIAL-REVISION-CONFLICT")

    with pytest.raises(ValueError, match="CURRENT_CONFLICT"):
        workflow.start(
            result,
            current_run_identity=result.snapshot.native_run_identity,
            started_at=NOW + timedelta(minutes=1),
            monitoring_authority=conflict,
            authority_is_current=lambda: True,
        )
    assert store.current_applicability(admitted.track.track_identity) == current


@pytest.mark.parametrize("failure_point", ["record", "pointer"])
def test_partial_admission_never_exposes_restorable_owner(
    tmp_path, monkeypatch, failure_point
) -> None:  # type: ignore[no-untyped-def]
    result = _decision(tmp_path)
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    candidate = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    target = "append_applicability" if failure_point == "record" else "publish_current_applicability"
    monkeypatch.setattr(store, target, lambda _record: (_ for _ in ()).throw(OSError("fault")))

    with pytest.raises(OSError, match="fault"):
        workflow.start(
            result,
            current_run_identity=result.snapshot.native_run_identity,
            started_at=NOW,
            monitoring_authority=_monitoring_authority(candidate),
            authority_is_current=lambda: True,
        )
    projection = store.restoration_projection(candidate.track_identity)
    assert not projection.applicability.automatic_restoration
    assert projection.applicability.reason_codes == ("COMPACT_CHECKPOINT_RECOVERY_REQUIRED",)
    assert store.current_applicability(candidate.track_identity) is None


def test_authority_change_before_pointer_rejects_publication(tmp_path) -> None:
    result = _decision(tmp_path)
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    candidate = create_paper_observation_track(
        result,
        current_run_identity=result.snapshot.native_run_identity,
        created_at=NOW,
    )
    checks = iter((True, False))
    with pytest.raises(ValueError, match="AUTHORITY_STALE"):
        workflow.start(
            result,
            current_run_identity=result.snapshot.native_run_identity,
            started_at=NOW,
            monitoring_authority=_monitoring_authority(candidate),
            authority_is_current=lambda: next(checks),
        )
    assert store.current_applicability(candidate.track_identity) is None


def test_stale_capability_before_registration_cannot_publish_owner(tmp_path) -> None:
    _, store, started, instrument = _started(tmp_path)
    authority = _monitoring_authority(started.track)
    restored = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    restored.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    capability = _Capability()
    current = {"value": True}

    def resolver(_symbol):  # type: ignore[no-untyped-def]
        current["value"] = False
        return instrument

    assert restored.restore_monitoring(
        capability,
        resolver,
        lambda _track: authority,
        lambda: current["value"],
    ) == ()
    assert capability.sessions == []
    assert restored.active_monitoring_count == 0


def test_concurrent_restoration_is_single_flight_and_status_is_bounded(tmp_path) -> None:
    _, store, started, instrument = _started(tmp_path)
    authority = _monitoring_authority(started.track)
    restored = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    restored.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    capability = _Capability()
    results = []

    def restore():
        results.append(restored.restore_monitoring(
            capability, lambda _symbol: instrument, lambda _track: authority
        ))

    workers = (Thread(target=restore), Thread(target=restore))
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=2)

    assert all(not worker.is_alive() for worker in workers)
    assert results == [
        (started.track.track_identity,),
        (started.track.track_identity,),
    ]
    assert len(capability.sessions) == 1
    assert restored.active_monitoring_count == 1
    status = restored.restoration_status()
    assert status["open_compatible"] == 1
    assert status["duplicate_already_registered"] in {0, 1}
    assert set(status) == {
        "open_compatible", "recovery_required", "closed", "restored",
        "incompatible", "legacy_without_applicability",
        "duplicate_already_registered", "reasons",
    }


def _compact_started(tmp_path, *, direction=V1Direction.LONG):
    result = _decision(tmp_path, direction=direction)
    store = LocalPaperObservationTrackStore(tmp_path / "tracks")
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    started = _admit(workflow, result, compact=True)
    return workflow, store, started, _instrument(result)


def _inventory(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_compact_admission_and_ten_thousand_ticks_have_constant_file_population(tmp_path, monkeypatch):
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity = started.track.track_identity
    entry = started.track.observation_entry_reference
    before = _inventory(store.root)
    assert len(before) == 4  # track, applicability, pointer, checkpoint
    assert len(tuple(store.root.rglob("current-state.json"))) == 1
    def forbidden(*args, **kwargs):
        raise AssertionError("history access during compact tick")
    with monkeypatch.context() as guard:
        for name in ("facts", "events", "monitoring", "projection", "_load_fact"):
            guard.setattr(store, name, forbidden)
        guard.setattr(Path, "glob", forbidden)
        guard.setattr(Path, "rglob", forbidden)
        guard.setattr(Path, "iterdir", forbidden)
        for sequence in range(10000):
            workflow.observe_tick(identity, _tick(instrument, entry - Decimal("1"), sequence,
                NOW + timedelta(microseconds=sequence + 1)))
    after = _inventory(store.root)
    assert before.keys() == after.keys()
    assert [path for path in before if before[path] != after[path]] == [identity + "/current-state.json"]
    state = store.load_compact(identity)
    assert state.sequence == 9999 and state.material_count == 0
    assert state.high == state.low == entry - Decimal("1")
    assert workflow.compact_status()["ordinary_ticks_accepted"] == 10000


def test_compact_latest_replay_compares_complete_observation_and_older_replay_is_inert(tmp_path):
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity = started.track.track_identity
    price = started.track.observation_entry_reference - Decimal("1")
    latest = _tick(instrument, price, 100, NOW + timedelta(seconds=100))
    workflow.observe_tick(identity, latest)
    before = _inventory(store.root)
    first = workflow.projection(identity)
    assert workflow.observe_tick(identity, latest) == first
    assert workflow.compact_status()["latest_tick_disposition"] == "EXACT_LATEST_REPLAY"
    for n in range(10000):
        old = _tick(instrument, price if n % 2 else price + 100, 17, NOW + timedelta(seconds=17))
        assert workflow.observe_tick(identity, old) == first
    assert _inventory(store.root) == before
    assert workflow.compact_status()["historical_replays_unverifiable"] == 10000
    assert workflow.compact_status()["latest_tick_disposition"] == "PROVIDER_HISTORICAL_REPLAY_UNVERIFIABLE"
    assert workflow.compact_status()["duplicate_ticks_ignored"] == 1
    workflow._compact_counters["historical_replays_unverifiable"] = (1 << 63) - 1
    workflow.observe_tick(identity, old)
    assert workflow.compact_status()["historical_replays_unverifiable"] == (1 << 63) - 1


@pytest.mark.parametrize("field,value", [
    ("last_price", Decimal("9999")), ("received_at", NOW + timedelta(hours=2)),
    ("ordering_deterministic", False), ("session_continuous", False),
    ("recovered", True), ("previous_interval_available", False),
])
def test_compact_equal_sequence_conflict_never_accepts_any_changed_field(tmp_path, field, value):
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity = started.track.track_identity
    tick = _tick(instrument, started.track.observation_entry_reference - 1, 7, NOW + timedelta(seconds=1))
    workflow.observe_tick(identity, tick)
    before = store.load_compact(identity)
    result = workflow.observe_tick(identity, replace(tick, **{field: value}))
    after = store.load_compact(identity)
    assert result.monitoring_reason == "PROVIDER_SEQUENCE_CONFLICT"
    assert after.latest_observation == before.latest_observation
    assert (after.entry_at, after.stop_at, after.target_at, after.high, after.low) == (
        before.entry_at, before.stop_at, before.target_at, before.high, before.low)
    count = len(_inventory(store.root))
    workflow.observe_tick(identity, replace(tick, **{field: value}))
    assert len(_inventory(store.root)) == count


@pytest.mark.parametrize("level", ["stop", "target"])
@pytest.mark.parametrize("direction", [V1Direction.LONG, V1Direction.SHORT])
def test_compact_entry_and_terminal_touch_are_retained_once(tmp_path, level, direction):
    workflow, store, started, instrument = _compact_started(tmp_path, direction=direction)
    identity, track = started.track.track_identity, started.track
    before_price = track.observation_entry_reference + (-1 if direction is V1Direction.LONG else 1)
    prices = (before_price, track.observation_entry_reference, getattr(track, level))
    for sequence, price in enumerate(prices):
        final_tick = _tick(instrument, price, sequence, NOW + timedelta(seconds=sequence + 1))
        result = workflow.observe_tick(identity, final_tick)
    assert result.track_state is PaperObservationTrackState.COMPLETE
    assert result.outcome_state.value == ("STOP_LEVEL_TOUCHED" if level == "stop" else "TARGET_LEVEL_TOUCHED")
    assert store.load_compact(identity).material_count == 2
    before = _inventory(store.root)
    workflow.observe_tick(identity, final_tick)
    assert _inventory(store.root) == before
    assert not tuple(store.root.rglob("facts/*.json"))


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_compact_missing_or_corrupt_checkpoint_fails_closed_without_fallback(tmp_path, monkeypatch, fault):
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity = started.track.track_identity
    checkpoint = store.root / identity / "current-state.json"
    if fault == "missing":
        checkpoint.unlink()
    else:
        checkpoint.write_text("{}")
    before = _inventory(store.root)
    monkeypatch.setattr(store, "facts", lambda *_: pytest.fail("legacy fallback"))
    monkeypatch.setattr(store, "events", lambda *_: pytest.fail("material scan"))
    projection = store.restoration_projection(identity, _monitoring_authority(started.track))
    assert projection.applicability.operation == "RECOVERY_REQUIRED"
    restored = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    assert restored.restore_monitoring(_Capability(), lambda _: instrument,
        lambda _: _monitoring_authority(started.track)) == ()
    assert _inventory(store.root) == before


@pytest.mark.parametrize("fault", ["applicability", "capability", "checkpoint", "generation"])
def test_compact_preparation_is_fenced_before_publication(tmp_path, monkeypatch, fault):
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity = started.track.track_identity
    before = (store.root / identity / "current-state.json").read_bytes()
    original = store.prepare_compact
    cap = _Capability()
    workflow._compact_fences[identity] = (cap, lambda: cap.active, "GENERATION-1")
    def changed(*args, **kwargs):
        prepared = original(*args, **kwargs)
        if fault == "capability":
            cap.active = False
        elif fault == "checkpoint":
            workflow._compact_states[identity] = replace(workflow._compact_states[identity])
        elif fault == "generation":
            workflow._compact_fences[identity] = (cap, lambda: cap.active, "GENERATION-2")
        else:
            pointer = store.root / identity / "current-applicability.json"
            pointer.write_bytes(pointer.read_bytes() + b" ")
        return prepared
    monkeypatch.setattr(store, "prepare_compact", changed)
    with pytest.raises(ValueError, match="STALE"):
        workflow.observe_tick(identity, _tick(instrument, started.track.observation_entry_reference - 1, 1, NOW))
    assert (store.root / identity / "current-state.json").read_bytes() == before


@pytest.mark.parametrize("fault", ["before_transition", "after_transition", "replace"])
def test_compact_crash_visibility_is_old_or_complete_checkpoint(tmp_path, monkeypatch, fault):
    from kronos.swing.v1 import paper_observation_track as domain
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity, entry = started.track.track_identity, started.track.observation_entry_reference
    workflow.observe_tick(identity, _tick(instrument, entry - 1, 1, NOW))
    prior = store.load_compact(identity)
    original_append = store._retain_compact_transition
    original_atomic = domain._atomic_encoded
    def failed_append(*args, **kwargs):
        if fault == "before_transition":
            raise OSError("simulated crash")
        result = original_append(*args, **kwargs)
        if fault == "after_transition":
            raise OSError("simulated crash")
        return result
    def failed_atomic(path, encoded):
        if path.name == "current-state.json":
            raise OSError("simulated crash")
        return original_atomic(path, encoded)
    monkeypatch.setattr(store, "_retain_compact_transition", failed_append)
    if fault == "replace":
        monkeypatch.setattr(domain, "_atomic_encoded", failed_atomic)
    with pytest.raises(OSError, match="simulated crash"):
        workflow.observe_tick(identity, _tick(instrument, entry, 2, NOW + timedelta(seconds=1)))
    assert store.load_compact(identity) == prior
    assert workflow.projection(identity).entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED


def test_compact_session_reset_is_gap_not_historical_replay(tmp_path):
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity = started.track.track_identity
    workflow.observe_tick(identity, _tick(instrument, started.track.observation_entry_reference - 1, 100, NOW))
    prior = store.load_compact(identity)
    result = workflow.observe_tick(identity, _tick(instrument, started.track.observation_entry_reference, 1,
        NOW + timedelta(seconds=1), connection="REPLACEMENT-SESSION"))
    assert result.monitoring_reason == "COMPACT_GENERATION_RECOVERY_REQUIRED"
    after = store.load_compact(identity)
    assert after.latest_observation == prior.latest_observation
    assert after.gap_count == 1
    assert workflow.compact_status()["historical_replays_unverifiable"] == 0


@pytest.mark.parametrize("population", [0, 10000, 100000])
def test_compact_tick_is_independent_of_unrelated_legacy_population(tmp_path, monkeypatch, population):
    workflow, store, started, instrument = _compact_started(tmp_path)
    facts = store.root / "unrelated-legacy-track" / "facts"
    facts.mkdir(parents=True)
    for sequence in range(population):
        (facts / f"{sequence}.json").write_bytes(b"unrelated legacy bytes must not be read")
    identity, entry = started.track.track_identity, started.track.observation_entry_reference
    def forbidden(*args, **kwargs):
        pytest.fail("history or enumeration entered compact callback")
    with monkeypatch.context() as guard:
        for name in ("facts", "events", "monitoring", "projection"):
            guard.setattr(store, name, forbidden)
        for name in ("iterdir", "glob", "rglob", "read_bytes", "read_text"):
            guard.setattr(Path, name, forbidden)
        workflow.observe_tick(identity, _tick(instrument, entry - 2, 1, NOW))
        workflow.observe_tick(identity, _tick(instrument, entry - 1, 2, NOW + timedelta(seconds=1)))
        status = workflow.compact_status()
    state = store.load_compact(identity)
    assert (state.last_price, state.high, state.low) == (entry - 1, entry - 1, entry - 2)
    assert state.outcome is PaperObservationOutcome.ENTRY_NOT_OBSERVED
    assert state.material_count == 0 and status["ordinary_ticks_accepted"] == 2
    assert len(tuple(facts.iterdir())) == population


def test_compact_restart_refuses_unproven_continuity_without_writes(tmp_path, monkeypatch):
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity = started.track.track_identity
    workflow.observe_tick(identity, _tick(instrument, started.track.observation_entry_reference - 1, 1, NOW))
    before = _inventory(store.root)
    restored = PaperObservationTrackingWorkflow(LocalPaperObservationTrackStore(store.root), clock=lambda: NOW)
    restored.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    capability = _Capability()
    for name in ("facts", "events", "monitoring", "projection"):
        monkeypatch.setattr(restored._store, name, lambda *_: pytest.fail("restart history scan"))
    assert restored.restore_monitoring(capability, lambda _: instrument,
        lambda _: _monitoring_authority(started.track)) == ()
    assert capability.sessions == []
    assert restored.compact_status()["recovery_required_tracks"] == 1
    assert restored.startup_projections()[0].monitoring_reason == "RECOVERY_REQUIRED"
    assert _inventory(store.root) == before


def test_compact_empty_checkpoint_restores_once_without_persistence(tmp_path, monkeypatch):
    workflow, store, started, instrument = _compact_started(tmp_path)
    before = _inventory(store.root)
    workflow.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    capability = _Capability()
    for name in ("facts", "events", "monitoring", "projection"):
        monkeypatch.setattr(store, name, lambda *_: pytest.fail("restoration history scan"))
    for _ in range(2):
        assert workflow.restore_monitoring(capability, lambda _: instrument,
            lambda _: _monitoring_authority(started.track)) == (started.track.track_identity,)
    assert len(capability.sessions) == 1
    assert _inventory(store.root) == before
    workflow.close()


def test_compact_gap_reconciliation_resumes_new_session_only_with_contiguous_coverage(tmp_path, monkeypatch):
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity, entry = started.track.track_identity, started.track.observation_entry_reference
    start = datetime(2026, 8, 21, 8, 45, tzinfo=UTC)
    end = start + timedelta(hours=1)
    workflow.observe_tick(identity, _tick(instrument, entry - 2, 100, start))
    workflow.observe_connection_state(identity, MonitoringConnectionState.DISCONNECTED)
    gap = store.load_compact(identity)
    assert gap.gap_count == 1 and gap.material_count == 1
    capability = _HistoricalCapability((HistoricalCandle(
        timestamp=start, open=float(entry - 2), high=float(entry - 1),
        low=float(entry - 3), close=float(entry - 2), volume=1),))
    monkeypatch.setattr(store, "facts", lambda *_: pytest.fail("gap legacy facts"))
    workflow.reconcile_gap_from_provider(identity, capability, instrument, observed_at=end)
    resumed = store.load_compact(identity)
    assert resumed.resume_after_gap and resumed.material_count == 2
    workflow.observe_tick(identity, _tick(instrument, entry - 1, 1, end,
        connection="NEXT-SESSION"))
    current = store.load_compact(identity)
    assert current.sequence == 1 and current.session == "NEXT-SESSION"
    assert current.high == entry - 1 and current.low == entry - 3
    assert current.material_count == 2 and not current.resume_after_gap


def test_compact_candle_both_touch_preserves_ordering_ambiguity(tmp_path):
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity, track = started.track.track_identity, started.track
    result = workflow.reconcile_completed_candle(identity,
        low=min(track.stop, track.target) - 1, high=max(track.stop, track.target) + 1,
        interval_open=track.observation_entry_reference - 1,
        interval_close=track.observation_entry_reference + 1,
        completed_at=NOW + timedelta(hours=1), source_identity="DOMAIN008-COMPLETED",
        domain008_completed=True, gap_reconciliation=True)
    assert result.outcome_state is PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED
    assert result.track_state is PaperObservationTrackState.COMPLETE
    state = store.load_compact(identity)
    assert state.material_count == 1 and state.stop_at == state.target_at
    assert state.excursion_state == "UNAVAILABLE_NOT_DEFINED_BY_TRACK_V1"


def test_compact_crash_after_replacement_exposes_complete_new_state_and_fences_memory(tmp_path, monkeypatch):
    from kronos.swing.v1 import paper_observation_track as domain
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity, entry = started.track.track_identity, started.track.observation_entry_reference
    workflow.observe_tick(identity, _tick(instrument, entry - 1, 1, NOW))
    original = domain._atomic_encoded
    def fail_after_replace(path, encoded):
        original(path, encoded)
        if path.name == "current-state.json":
            raise OSError("post replacement failure")
    monkeypatch.setattr(domain, "_atomic_encoded", fail_after_replace)
    with pytest.raises(OSError, match="post replacement"):
        workflow.observe_tick(identity, _tick(instrument, entry, 2, NOW + timedelta(seconds=1)))
    current = store.load_compact(identity)
    assert current.entry_at == NOW + timedelta(seconds=1) and current.material_count == 1
    assert (store.root / identity / "transitions" / f"{current.material_head}.json").is_file()
    before = _inventory(store.root)
    with pytest.raises(ValueError, match="RECOVERY_REQUIRED"):
        workflow.observe_tick(identity, _tick(instrument, entry + 1, 3, NOW + timedelta(seconds=2)))
    assert _inventory(store.root) == before


def test_legacy_arbitrary_historical_replay_and_conflict_remain_exact(tmp_path):
    workflow, store, started, instrument = _started(tmp_path)
    identity, price = started.track.track_identity, started.track.observation_entry_reference - 1
    old = _tick(instrument, price, 1, NOW)
    workflow.observe_tick(identity, old)
    workflow.observe_tick(identity, _tick(instrument, price, 2, NOW + timedelta(seconds=1)))
    before = _inventory(store.root)
    exact = workflow.observe_tick(identity, old)
    assert exact.monitoring_reason != "PROVIDER_SEQUENCE_CONFLICT"
    assert _inventory(store.root) == before
    conflict = workflow.observe_tick(identity, replace(old, last_price=price + 100))
    assert conflict.monitoring_reason == "PROVIDER_SEQUENCE_CONFLICT"
    assert len(store.facts(identity)) == 2
    assert not (store.root / identity / "current-state.json").exists()


def test_compact_equal_time_without_comparable_sequences_preserves_ordering_failure(tmp_path):
    workflow, store, started, instrument = _compact_started(tmp_path)
    identity, entry = started.track.track_identity, started.track.observation_entry_reference
    workflow.observe_tick(identity, _tick(instrument, entry - 1, None, NOW))
    result = workflow.observe_tick(identity, _tick(instrument, entry, 1, NOW))
    assert result.monitoring_reason == "ORDERED_LIVE_FACTS_UNAVAILABLE"
    assert store.load_compact(identity).entry_at is None


def _registered_compact(tmp_path):
    workflow, store, started, instrument = _compact_started(tmp_path)
    hub, capability = SharedSwingMonitoringHub(), _Capability()
    workflow.set_shared_monitoring_hub(hub)
    identity=started.track.track_identity
    assert workflow.restore_monitoring(capability, lambda _: instrument,
        lambda _: _monitoring_authority(started.track)) == (identity,)
    return workflow,store,started,instrument,hub,capability,workflow._consumers[identity]


@pytest.mark.parametrize('state', [PaperObservationMonitoringApplicabilityState.SUSPENDED,
                                  PaperObservationMonitoringApplicabilityState.CLOSED])
def test_applicability_detach_preserves_checkpoint_and_fences_late_callbacks(tmp_path,state):
    workflow,store,started,instrument,hub,capability,consumer=_registered_compact(tmp_path)
    identity=started.track.track_identity
    checkpoint=(store.root/identity/'current-state.json').read_bytes()
    registration=workflow._registrations[identity]
    assert workflow.change_monitoring_applicability(identity,state,'SPONSOR_STOPPED_MONITORING')=='DETACHED'
    assert store.current_applicability(identity).state is state
    assert (store.root/identity/'current-state.json').read_bytes()==checkpoint
    assert workflow.active_monitoring_count==0 and hub.subscription_count==0
    assert identity not in workflow._compact_states and identity not in workflow._compact_fences
    assert identity not in workflow._owner_bindings and identity not in workflow._consumers
    assert consumer._capability is None and consumer._instrument is None and consumer._track is None
    assert registration._consumer is None and registration._capability is None
    before=_inventory(store.root)
    consumer.on_market_tick(_tick(instrument,started.track.observation_entry_reference,1,NOW))
    consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
    assert _inventory(store.root)==before
    assert workflow.restore_monitoring(capability,lambda _:instrument,
        lambda _:_monitoring_authority(started.track))==()
    assert _inventory(store.root)==before
    assert workflow.detachment_status()['stale_callbacks_rejected']==2


@pytest.mark.parametrize('field,value', [
    ('material_revision','MATERIAL-REPLACED'), ('native_assessment_sha256','f'*64),
    ('direction',V1Direction.SHORT), ('geometry_sha256','e'*64),
    ('review_authority_identity','REVIEW-REPLACED'), ('decision_authority_identity','DECISION-REPLACED'),
    ('instrument_contract_identity','CONTRACT-REPLACED'), ('monitoring_window_identity','WINDOW-ENDED')])
def test_established_authority_incompatibility_detaches_exact_owner_without_facts(tmp_path,monkeypatch,field,value):
    workflow,store,started,instrument,hub,capability,consumer=_registered_compact(tmp_path)
    for name in ('facts','events','projection','monitoring'):
        monkeypatch.setattr(store,name,lambda *_:pytest.fail('historical read during detach'))
    incompatible=replace(_monitoring_authority(started.track),**{field:value})
    workflow.reconcile_monitoring_owners(lambda _:incompatible)
    assert workflow.active_monitoring_count==0 and hub.subscription_count==0
    assert store.current_applicability(started.track.track_identity).state is PaperObservationMonitoringApplicabilityState.SUSPENDED
    assert consumer._detached


def test_terminal_publishes_final_checkpoint_then_closed_before_release(tmp_path,monkeypatch):
    workflow,store,started,instrument,hub,capability,consumer=_registered_compact(tmp_path)
    identity,entry=started.track.track_identity,started.track.observation_entry_reference
    trace=[]
    publish=store.publish_applicability_transition
    disconnect=workflow._registrations[identity].disconnect
    def observed_publish(prepared):
        assert store.load_compact(identity).terminal
        trace.append('FINAL_CHECKPOINT')
        publish(prepared)
        trace.append('CLOSED')
    def observed_disconnect():
        assert store.current_applicability(identity).state is PaperObservationMonitoringApplicabilityState.CLOSED
        trace.append('DETACH')
        return disconnect()
    monkeypatch.setattr(store,'publish_applicability_transition',observed_publish)
    monkeypatch.setattr(workflow._registrations[identity],'disconnect',observed_disconnect)
    consumer.on_market_tick(_tick(instrument,entry-1,1,NOW))
    consumer.on_market_tick(_tick(instrument,entry,2,NOW+timedelta(seconds=1)))
    consumer.on_market_tick(_tick(instrument,started.track.target,3,NOW+timedelta(seconds=2)))
    assert trace==['FINAL_CHECKPOINT','CLOSED','DETACH']
    assert store.load_compact(identity).outcome is PaperObservationOutcome.TARGET_LEVEL_TOUCHED
    assert workflow.detachment_status()['terminal_detachments']==1
    before=_inventory(store.root)
    consumer.on_market_tick(_tick(instrument,entry,4,NOW+timedelta(seconds=3)))
    assert _inventory(store.root)==before


def test_old_capability_and_detach_cannot_release_new_registration(tmp_path):
    workflow,store,started,instrument,hub,old_capability,old_consumer=_registered_compact(tmp_path)
    identity=started.track.track_identity
    old_registration=workflow._registrations[identity]
    old_capability.active=False
    new_capability=_Capability()
    assert workflow.restore_monitoring(new_capability,lambda _:instrument,
        lambda _:_monitoring_authority(started.track))==(identity,)
    new_registration=workflow._registrations[identity]
    assert new_registration is not old_registration and new_registration.active
    assert workflow.detach_monitoring(identity,expected_registration=old_registration)=='ALREADY_DETACHED'
    old_consumer.on_market_tick(_tick(instrument,started.track.observation_entry_reference,1,NOW))
    assert new_registration.active and hub.subscription_reference_count(instrument)==1


@pytest.mark.parametrize('callback', ['tick','connection'])
def test_detach_racing_prepared_tick_fences_publication(tmp_path,monkeypatch,callback):
    from threading import Event
    workflow,store,started,instrument,hub,capability,consumer=_registered_compact(tmp_path)
    identity=started.track.track_identity
    if callback=='connection':
        consumer.on_market_tick(_tick(instrument,started.track.observation_entry_reference-1,1,NOW))
    entered,release=Event(),Event()
    original=store.prepare_compact
    failures=[]
    def prepare(*args,**kwargs):
        result=original(*args,**kwargs);entered.set();assert release.wait(5);return result
    monkeypatch.setattr(store,'prepare_compact',prepare)
    def tick():
        try:
            if callback=='tick':
                consumer.on_market_tick(_tick(instrument,started.track.observation_entry_reference-1,1,NOW))
            else:
                consumer.on_connection_state(MonitoringConnectionState.DISCONNECTED)
        except Exception as error:failures.append(error)
    worker=Thread(target=tick);worker.start()
    try:
        assert entered.wait(5)
        workflow.change_monitoring_applicability(identity,PaperObservationMonitoringApplicabilityState.SUSPENDED,'SPONSOR_STOPPED_MONITORING')
        before=_inventory(store.root)
    finally:release.set();worker.join(5)
    assert not worker.is_alive() and not failures
    assert _inventory(store.root)==before and identity not in workflow._compact_states


def test_many_idempotent_detaches_keep_bounded_status_and_one_release(tmp_path):
    workflow,store,started,instrument,hub,capability,consumer=_registered_compact(tmp_path)
    identity=started.track.track_identity
    workers=[Thread(target=lambda:workflow.detach_monitoring(identity)) for _ in range(8)]
    for worker in workers:worker.start()
    for worker in workers:worker.join(3)
    before=_inventory(store.root)
    keys=workflow.detachment_status().keys()
    for _ in range(10000):workflow.detach_monitoring(identity)
    assert workflow.detachment_status().keys()==keys
    assert workflow.detachment_status()['already_detached']==10007
    assert capability.sessions[0].unsubscribed==[(instrument,)]
    assert _inventory(store.root)==before


def test_suspended_requires_explicit_new_open_generation_and_closed_cannot_resume(tmp_path):
    workflow,store,started,instrument,hub,capability,consumer=_registered_compact(tmp_path)
    identity=started.track.track_identity
    original=store.current_applicability(identity)
    workflow.change_monitoring_applicability(identity,PaperObservationMonitoringApplicabilityState.SUSPENDED,'SPONSOR_STOPPED_MONITORING')
    suspended=store.current_applicability(identity)
    assert workflow.restore_monitoring(capability,lambda _:instrument,lambda _:_monitoring_authority(started.track))==()
    opened=workflow.resume_monitoring(identity,_monitoring_authority(started.track),authority_is_current=lambda:True)
    assert opened.record_identity!=original.record_identity
    assert opened.predecessor_applicability_identity==suspended.record_identity
    assert store.load_compact(identity).applicability_identity==opened.record_identity
    assert workflow.restore_monitoring(capability,lambda _:instrument,lambda _:_monitoring_authority(started.track))==(identity,)
    workflow.change_monitoring_applicability(identity,PaperObservationMonitoringApplicabilityState.CLOSED,'SPONSOR_STOPPED_MONITORING')
    with pytest.raises(ValueError,match='RESUMPTION_UNAVAILABLE'):
        workflow.resume_monitoring(identity,_monitoring_authority(started.track),authority_is_current=lambda:True)


def test_detach_cancels_pending_restoration_without_duplicate_owner(tmp_path,monkeypatch):
    from threading import Event
    workflow,store,started,instrument=_compact_started(tmp_path)
    hub,capability=SharedSwingMonitoringHub(),_Capability()
    workflow.set_shared_monitoring_hub(hub)
    entered,release=Event(),Event()
    original=hub.open
    errors=[]
    def blocked(*args):
        entered.set();assert release.wait(5);return original(*args)
    monkeypatch.setattr(hub,'open',blocked)
    def restore():
        try: workflow.restore_monitoring(capability,lambda _:instrument,lambda _:_monitoring_authority(started.track))
        except Exception as error: errors.append(error)
    worker=Thread(target=restore);worker.start()
    try:
        assert entered.wait(5)
        workflow.detach_monitoring(started.track.track_identity)
    finally:release.set();worker.join(5)
    assert not worker.is_alive() and not errors
    assert workflow.active_monitoring_count==0 and hub.status_document()['owner_count']==0
    assert capability.sessions==[] and workflow._pending_owners=={}


@pytest.mark.parametrize('path',['track.json','current-state.json','current-applicability.json'])
def test_invalid_current_integrity_detaches_without_repair_or_history(tmp_path,monkeypatch,path):
    workflow,store,started,instrument,hub,capability,consumer=_registered_compact(tmp_path)
    (store.root/started.track.track_identity/path).write_bytes(b'{}')
    before=_inventory(store.root)
    monkeypatch.setattr(store,'facts',lambda *_:pytest.fail('historical fallback'))
    workflow.reconcile_monitoring_owners(lambda _:_monitoring_authority(started.track))
    assert workflow.active_monitoring_count==0 and consumer._detached
    assert _inventory(store.root)==before


def test_two_historical_vbl_owners_remain_inert_and_do_not_remove_current_intraday_subscription(tmp_path,monkeypatch):
    from kronos.swing.v1.paper_observation_track import PaperObservationTrackV1, _values_digest
    store=LocalPaperObservationTrackStore(tmp_path/'historical')
    identities=[]
    for index,direction in enumerate((V1Direction.LONG,V1Direction.SHORT)):
        decision=_decision(tmp_path/str(index),direction=direction)
        track=create_paper_observation_track(decision,current_run_identity=decision.snapshot.native_run_identity,created_at=NOW)
        values={name:getattr(track,name) for name in track.__dataclass_fields__}
        values.update(canonical_instrument='VBL',integrity_sha256='')
        values['integrity_sha256']=_values_digest(values)
        track=PaperObservationTrackV1(**values)
        store.retain_track(track)
        facts=store.root/track.track_identity/'facts';facts.mkdir()
        (facts/'legacy.json').write_bytes(b'UNCHANGED HISTORICAL VBL FACT SENTINEL')
        identities.append(track.track_identity)
    before=_inventory(store.root)
    workflow=PaperObservationTrackingWorkflow(store,clock=lambda:NOW)
    hub,capability=SharedSwingMonitoringHub(),_Capability()
    workflow.set_shared_monitoring_hub(hub)
    instrument=InstrumentRecord('KITE','NSE','NSE','VBL','VBL','EQ',None)
    intraday=hub.open(capability,_OtherConsumer());intraday.subscribe((instrument,));intraday.connect()
    monkeypatch.setattr(store,'facts',lambda *_:pytest.fail('legacy fact read'))
    monkeypatch.setattr(store,'_load_fact',lambda *_:pytest.fail('legacy fact read'))
    assert workflow.restore_monitoring(capability,lambda _:instrument)==()
    workflow.startup_projections()
    assert _inventory(store.root)==before
    assert intraday.active and hub.subscription_reference_count(instrument)==1
    assert capability.sessions[0].unsubscribed==[]
    assert workflow.active_monitoring_count==0
    assert all(store.current_applicability(identity) is None for identity in identities)
    assert workflow.restoration_status()['legacy_without_applicability']==2


def _slice8_decision(base, label, *, symbol="VBL"):
    """Distinct, integrity-valid isolated decisions; no production lineage reused."""
    from kronos.swing.v1.sponsor_observation_decision import _values_digest
    from hashlib import sha256
    def changed(record, **updates):
        values = {name: getattr(record, name) for name in record.__dataclass_fields__}
        values.update(updates, integrity_sha256="")
        values["integrity_sha256"] = _values_digest(values)
        return type(record)(**values)
    snapshot = changed(base.snapshot, snapshot_identity=f"SNAPSHOT-{label}",
        native_run_identity='SWING-RUN-' + sha256(label.encode()).hexdigest()[:32].upper(),
        canonical_instrument=symbol)
    decision = changed(base.decision, decision_identity=f"DECISION-{label}",
        snapshot_identity=snapshot.snapshot_identity, snapshot_sha256=snapshot.integrity_sha256,
        native_run_identity=snapshot.native_run_identity, canonical_instrument=symbol)
    activation = changed(base.activation, disposition_identity=f"ACTIVATION-{label}",
        decision_identity=decision.decision_identity)
    return type(base)(snapshot, decision, activation)


@pytest.mark.parametrize('boundary', ['before_pointer', 'after_pointer', 'attachment'])
def test_slice8_admission_interruption_selects_only_complete_authority(tmp_path, monkeypatch, boundary):
    result = _decision(tmp_path)
    store = LocalPaperObservationTrackStore(tmp_path / 'admission')
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    candidate = create_paper_observation_track(result,
        current_run_identity=result.snapshot.native_run_identity, created_at=NOW)
    hub, capability = SharedSwingMonitoringHub(), _Capability()
    workflow.set_shared_monitoring_hub(hub)
    publish = store.publish_current_applicability
    def interrupted(record):
        if boundary == 'before_pointer':
            raise OSError('isolated admission interruption')
        publish(record)
        raise OSError('isolated admission interruption')
    with monkeypatch.context() as fault:
        if boundary != 'attachment':
            fault.setattr(store, 'publish_current_applicability', interrupted)
            with pytest.raises(OSError, match='isolated'):
                _admit(workflow, result, compact=True)
        else:
            _admit(workflow, result, compact=True)
            fault.setattr(hub, 'open', lambda *_: (_ for _ in ()).throw(OSError('isolated attachment')))
            with pytest.raises(OSError, match='isolated'):
                workflow.restore_monitoring(capability, lambda _: _instrument(result), _monitoring_authority)
    assert not workflow._registrations and not workflow._pending_owners and not capability.sessions
    reopened = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    reopened.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    before = _inventory(store.root)
    restored = reopened.restore_monitoring(capability, lambda _: _instrument(result), _monitoring_authority)
    assert restored == (() if boundary == 'before_pointer' else (candidate.track_identity,))
    assert _inventory(store.root) == before
    if boundary == 'before_pointer':
        assert store.current_applicability(candidate.track_identity) is None
        assert not capability.sessions
    else:
        assert store.current_applicability(candidate.track_identity).state is PaperObservationMonitoringApplicabilityState.OPEN
        assert len(capability.sessions) == 1


def test_slice8_integrated_admission_gap_resumption_terminal_and_stale_callbacks(tmp_path):
    workflow, store, started, instrument, hub, capability, old_consumer = _registered_compact(tmp_path)
    identity, entry = started.track.track_identity, started.track.observation_entry_reference
    authority = _monitoring_authority(started.track)
    opened = store.current_applicability(identity)
    start = NOW + timedelta(minutes=45)
    first = _tick(instrument, entry - 2, 100, start)
    old_consumer.on_market_tick(first)
    before = _inventory(store.root)
    old_consumer.on_market_tick(first)
    assert _inventory(store.root) == before
    assert workflow.compact_status()['latest_tick_disposition'] == 'EXACT_LATEST_REPLAY'
    old_consumer.on_connection_state(MonitoringConnectionState.DISCONNECTED)
    capability.historical_candles = lambda request: (HistoricalCandle(
        timestamp=start, open=float(entry - 2), high=float(entry - 1),
        low=float(entry - 3), close=float(entry - 2), volume=1),)
    workflow.reconcile_gap_from_provider(identity, capability, instrument,
        observed_at=start + timedelta(hours=1))
    assert store.load_compact(identity).resume_after_gap
    workflow.change_monitoring_applicability(identity,
        PaperObservationMonitoringApplicabilityState.SUSPENDED, 'SPONSOR_STOPPED_MONITORING')
    assert workflow.restore_monitoring(capability, lambda _: instrument, lambda _: authority) == ()
    resumed = workflow.resume_monitoring(identity, authority, authority_is_current=lambda: True)
    assert resumed.record_identity != opened.record_identity
    assert workflow.restore_monitoring(capability, lambda _: instrument, lambda _: authority) == (identity,)
    consumer = workflow._consumers[identity]
    before = _inventory(store.root)
    old_consumer.on_market_tick(_tick(instrument, started.track.target, 101, start + timedelta(hours=1)))
    assert _inventory(store.root) == before
    boundary = start + timedelta(hours=1)
    consumer.on_market_tick(_tick(instrument, entry, 1, boundary, connection='RESUMED'))
    assert store.load_compact(identity).entry_at == boundary
    consumer.on_market_tick(_tick(instrument, started.track.target, 2,
        boundary + timedelta(seconds=1), connection='RESUMED'))
    final = store.load_compact(identity)
    assert final.terminal and final.outcome is PaperObservationOutcome.TARGET_LEVEL_TOUCHED
    assert store.current_applicability(identity).state is PaperObservationMonitoringApplicabilityState.CLOSED
    assert not workflow._registrations and hub.subscription_count == 0
    before = _inventory(store.root)
    consumer.on_market_tick(_tick(instrument, entry, 3, boundary + timedelta(seconds=2)))
    consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
    assert workflow.restore_monitoring(capability, lambda _: instrument, lambda _: authority) == ()
    assert _inventory(store.root) == before


def test_slice8_repeated_admit_restore_suspend_resume_close_releases_owner_state(tmp_path):
    base = _decision(tmp_path / 'source')
    store = LocalPaperObservationTrackStore(tmp_path / 'cycles')
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    hub, capability = SharedSwingMonitoringHub(), _Capability()
    workflow.set_shared_monitoring_hub(hub)
    coordination = (id(workflow._lock), id(hub._lock), id(hub._transport_lock))
    for cycle in range(32):
        result = _slice8_decision(base, f'CYCLE-{cycle}')
        admitted = _admit(workflow, result, compact=True)
        identity, instrument = admitted.track.track_identity, _instrument(result)
        assert workflow.restore_monitoring(capability, lambda _: instrument, _monitoring_authority) == (identity,)
        workflow.change_monitoring_applicability(identity,
            PaperObservationMonitoringApplicabilityState.SUSPENDED, 'SPONSOR_STOPPED_MONITORING')
        assert workflow.restore_monitoring(capability, lambda _: instrument, _monitoring_authority) == ()
        workflow.resume_monitoring(identity, _monitoring_authority(admitted.track), authority_is_current=lambda: True)
        assert workflow.restore_monitoring(capability, lambda _: instrument, _monitoring_authority) == (identity,)
        hub.on_market_tick(_tick(instrument, admitted.track.observation_entry_reference - 1, 1, NOW))
        assert store.load_compact(identity).sequence == 1
        workflow.change_monitoring_applicability(identity,
            PaperObservationMonitoringApplicabilityState.CLOSED, 'SPONSOR_STOPPED_MONITORING')
        for mapping in (workflow._registrations, workflow._consumers, workflow._pending_owners,
                workflow._owner_bindings, workflow._compact_states, workflow._compact_tracks,
                workflow._compact_modes, workflow._compact_fences, workflow._compact_live,
                workflow._compact_recovery, store._compact_tokens, store._compact_open,
                hub._registrations, hub._by_instrument, hub._latest_ticks, hub._subscribed):
            assert not mapping
        assert coordination == (id(workflow._lock), id(hub._lock), id(hub._transport_lock))
        assert hub.active_session_count == 0


def test_slice8_mixed_population_restores_only_current_and_preserves_intraday(tmp_path, monkeypatch):
    from kronos.swing.v1.paper_observation_track import make_monitoring_record
    base = _decision(tmp_path / 'source')
    store = LocalPaperObservationTrackStore(tmp_path / 'mixed')
    workflow = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    historical = []
    for label in ('VBL-LEGACY-1', 'VBL-LEGACY-2', 'VBL-COMPACT-HISTORY'):
        result = _slice8_decision(base, label)
        track = create_paper_observation_track(result,
            current_run_identity=result.snapshot.native_run_identity, created_at=NOW)
        store.retain_track(track)
        store.append_fact(make_market_fact(track, last_price=track.observation_entry_reference - 1,
            observed_at=NOW, received_at=NOW, source_identity=label, source_sequence=1,
            ordering_deterministic=True, recovered=False))
        store.append_monitoring(make_monitoring_record(track.track_identity,
            PaperObservationMonitoringState.INTERRUPTED, 'RECOVERY_REQUIRED', NOW))
        historical.append(track.track_identity)
    candidate = store.prepare_historical_consolidation(historical[-1], created_at=NOW + timedelta(days=1))
    store.publish_historical_consolidation(candidate, maintenance_identity='SLICE8-ISOLATED',
        published_at=NOW + timedelta(days=1))
    for path in (store.root / historical[-1] / 'facts').iterdir():
        path.unlink()
    terminal = _admit(workflow, _slice8_decision(base, 'VBL-TERMINAL'), compact=True)
    instrument = InstrumentRecord('KITE', 'NSE', 'NSE', 'VBL', 'VBL', 'EQ', None)
    for sequence, price in enumerate((terminal.track.observation_entry_reference - 1,
                                      terminal.track.observation_entry_reference, terminal.track.target), 1):
        workflow.observe_tick(terminal.track.track_identity, _tick(instrument, price, sequence,
            NOW + timedelta(seconds=sequence)))
    current = _admit(workflow, _slice8_decision(base, 'VBL-CURRENT'), compact=True)
    assert current.track.track_identity not in historical
    assert len(set(historical + [terminal.track.track_identity, current.track.track_identity])) == 5
    hub, capability = SharedSwingMonitoringHub(), _Capability()
    workflow.set_shared_monitoring_hub(hub)
    intraday_consumer = _OtherConsumer(); intraday_consumer.owner_identity = 'INTRADAY'
    intraday = hub.open(capability, intraday_consumer)
    intraday.subscribe((instrument,)); intraday.connect()
    other_instrument = replace(instrument, name='OTHER', trading_symbol='OTHER')
    other = hub.open(capability, _OtherConsumer())
    other.subscribe((other_instrument,)); other.connect()
    before = _inventory(store.root)
    for method in ('facts', '_load_fact', 'projection', 'prepare_historical_consolidation'):
        monkeypatch.setattr(store, method, lambda *_a, **_k: pytest.fail('operational historical reconstruction'))
    for _ in range(2):
        assert workflow.restore_monitoring(capability, lambda _: instrument, _monitoring_authority) == (current.track.track_identity,)
        workflow.startup_projections(); workflow.compact_status()
    assert _inventory(store.root) == before
    assert len(workflow._registrations) == 1 and len(capability.sessions) == 1
    assert hub.subscription_reference_count(instrument) == 2
    hub.on_market_tick(_tick(instrument, current.track.observation_entry_reference - 1, 1, NOW))
    hub.on_market_tick(_tick(other_instrument, 100, 1, NOW))
    workflow.change_monitoring_applicability(current.track.track_identity,
        PaperObservationMonitoringApplicabilityState.SUSPENDED, 'SPONSOR_STOPPED_MONITORING')
    assert intraday.active and hub.subscription_reference_count(instrument) == 1
    assert len(hub.latest_market_ticks) == 2 and capability.sessions[0].unsubscribed == []
    intraday.disconnect()
    assert [tick.instrument for tick in hub.latest_market_ticks] == [other_instrument]
    assert other.active and capability.sessions[0].unsubscribed == [(instrument,)]
    other.disconnect()
    assert not hub.latest_market_ticks and hub.active_session_count == 0


@pytest.mark.parametrize('boundary', ['before_closed_pointer', 'after_closed_pointer', 'release'])
def test_slice8_terminal_interruption_never_restores_terminal_owner(tmp_path, monkeypatch, boundary):
    workflow, store, started, instrument, hub, capability, consumer = _registered_compact(tmp_path)
    identity, entry = started.track.track_identity, started.track.observation_entry_reference
    consumer.on_market_tick(_tick(instrument, entry - 1, 1, NOW))
    consumer.on_market_tick(_tick(instrument, entry, 2, NOW + timedelta(seconds=1)))
    publish = store.publish_applicability_transition
    def interrupted(prepared):
        if boundary == 'before_closed_pointer':
            raise OSError('isolated interruption')
        publish(prepared)
        raise OSError('isolated interruption')
    with monkeypatch.context() as fault:
        if boundary == 'release':
            fault.setattr(capability.sessions[0], 'unsubscribe', lambda _: (_ for _ in ()).throw(OSError('isolated release')))
        else:
            fault.setattr(store, 'publish_applicability_transition', interrupted)
        consumer.on_market_tick(_tick(instrument, started.track.target, 3, NOW + timedelta(seconds=2)))
    assert store.load_compact(identity).terminal
    assert store.current_applicability(identity).state is (
        PaperObservationMonitoringApplicabilityState.OPEN if boundary == 'before_closed_pointer'
        else PaperObservationMonitoringApplicabilityState.CLOSED)
    restarted = PaperObservationTrackingWorkflow(store, clock=lambda: NOW)
    restarted.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    fresh = _Capability()
    before = _inventory(store.root)
    assert restarted.restore_monitoring(fresh, lambda _: instrument, _monitoring_authority) == ()
    assert not fresh.sessions and not restarted._registrations
    if boundary == 'release':
        assert capability.sessions[0].disconnections == 1
        assert hub.active_session_count == 0
    consumer.on_market_tick(_tick(instrument, entry, 4, NOW + timedelta(seconds=3)))
    assert _inventory(store.root) == before
