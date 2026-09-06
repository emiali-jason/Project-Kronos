"""MON-ENG-04: deterministic restoration with no live Provider operations."""
from datetime import timedelta
from io import BytesIO
from threading import Event, RLock, Thread
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlencode

import pytest

from kronos.application.paper_observation_tracking import (
    PaperObservationTrackingWorkflow, paper_monitoring_failure_reason,
)
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.application.swing_opportunities import SwingOpportunitiesApplication, ProviderConnectionState
from kronos.browser.server import KronosBrowserServer, _BrowserHandler, create_browser_server
from kronos.provider.contracts.monitoring import MonitoringConnectionState, MonitoringError, MonitoringFailure
from kronos.provider.contracts.instrument import InstrumentResolutionError, InstrumentResolutionFailure
from kronos.swing.v1.paper_observation_track import LocalPaperObservationTrackStore
from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.application.test_paper_observation_tracking import _started, _Capability, NOW


def _composition(tmp_path, monkeypatch):
    workflow, store, track, instrument = _started(tmp_path)
    hub = SharedSwingMonitoringHub()
    workflow.set_shared_monitoring_hub(hub)
    queued = []
    capability = _Capability()
    application = SwingOpportunitiesApplication(
        lambda: _Provider(capability), background_runner=lambda op, name: queued.append(op),
    )
    server = object.__new__(KronosBrowserServer)
    server._sponsor_restoration_lock = RLock()
    server.application = application
    server.product_routes = SimpleNamespace(owns_post=lambda path: False)
    server._synchronize_trade_window = Mock()
    server.trade_window = SimpleNamespace(
        mark_paper_observation_monitoring_unavailable=workflow.mark_monitoring_unavailable,
        restore_paper_observation_monitoring=workflow.restore_monitoring,
        restore_current_entry_monitoring=Mock(return_value=()),
        projections=lambda: (),
    )
    server.native_review = SimpleNamespace(
        restore_lifecycle_monitoring=Mock(return_value=()),
        snapshot=lambda: SimpleNamespace(active_lifecycle=SimpleNamespace(active=())),
    )
    monkeypatch.setattr('kronos.browser.server.resolve_governed_monitoring_instrument', lambda *args: instrument)
    application.register_sponsor_operability_restorer(server.restore_sponsor_operability)
    return SimpleNamespace(w=workflow, store=store, t=track, instrument=instrument, hub=hub,
                           queue=queued, cap=capability, app=application, server=server)


def test_real_server_registers_completion_boundary(tmp_path):
    application = SwingOpportunitiesApplication(_Provider, background_runner=lambda op, name: None)
    server = create_browser_server(application, port=0)
    try:
        assert application._SwingOpportunitiesApplication__sponsor_operability_restorer == server.restore_sponsor_operability
    finally:
        server.server_close()


def test_async_route_restores_all_existing_owner_boundaries_after_auth(tmp_path, monkeypatch):
    c = _composition(tmp_path, monkeypatch)
    progression = SimpleNamespace(restore_active=Mock(), close_monitoring=Mock(), activate_requirement=Mock())
    c.app.register_progression_watch_workflow(progression)
    c.server.restore_sponsor_operability()
    assert c.w.projection(c.t.track.track_identity).monitoring_reason == 'PROVIDER_CAPABILITY_NOT_ACTIVE'
    handler = SimpleNamespace(server=c.server, _redirect=Mock())
    _BrowserHandler._dispatch_post(handler, '/provider/connect')
    assert c.app.snapshot().provider_state is ProviderConnectionState.CONNECTING
    assert c.w.active_monitoring_count == 0
    c.server.trade_window.restore_current_entry_monitoring.assert_not_called()
    complete = c.queue.pop()
    complete()
    assert c.app.snapshot().provider_state is ProviderConnectionState.CONNECTED
    assert c.app.authenticated_read_only_capability() is c.cap
    assert c.w.active_monitoring_count == 1
    assert c.w.projection(c.t.track.track_identity).monitoring_reason == 'SHARED_HUB_REGISTRATION_ACTIVE'
    assert c.hub.connection_state is None  # Auth/registration is NOT WebSocket proof.
    c.server.trade_window.restore_current_entry_monitoring.assert_called_once()
    c.server.native_review.restore_lifecycle_monitoring.assert_called_once()
    progression.restore_active.assert_called_once_with(c.cap)
    complete()
    progression.restore_active.assert_called_once()
    c.server.native_review.restore_lifecycle_monitoring.assert_called_once()
    assert len(c.cap.sessions) == 1


def test_existing_registration_repairs_only_transport_status_without_duplicates(tmp_path, monkeypatch):
    c = _composition(tmp_path, monkeypatch)
    c.cap.historical_candles = Mock(return_value=())
    c.app.connect_provider(); c.queue.pop()()
    c.cap.sessions[0].consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
    registration = c.w._registrations[c.t.track.track_identity]
    c.w.mark_monitoring_unavailable('PROVIDER_CAPABILITY_NOT_ACTIVE')
    files = {p: p.read_bytes() for p in c.store.root.rglob('*.json')}
    c.server.restore_sponsor_operability(c.cap)
    assert c.w.projection(c.t.track.track_identity).monitoring_reason == 'SHARED_MONITORING_CONNECTED'
    count = len(c.store.monitoring(c.t.track.track_identity))
    for _ in range(3):
        c.server.restore_sponsor_operability(c.cap)
    assert len(c.store.monitoring(c.t.track.track_identity)) == count
    assert c.w._registrations[c.t.track.track_identity] is registration
    assert len(c.cap.sessions) == 1
    assert c.cap.sessions[0].subscribed == [(c.instrument,)]
    assert c.hub.subscription_reference_count(c.instrument) == 1
    assert all(p.read_bytes() == data for p, data in files.items())


@pytest.mark.parametrize('state', [None, MonitoringConnectionState.DISCONNECTED, MonitoringConnectionState.RECONNECTING])
def test_auth_does_not_invent_websocket_connection(tmp_path, monkeypatch, state):
    c = _composition(tmp_path, monkeypatch)
    c.app.connect_provider(); c.queue.pop()()
    if state is not None:
        c.cap.sessions[0].consumer.on_connection_state(state)
    c.w.mark_monitoring_unavailable('PROVIDER_CAPABILITY_NOT_ACTIVE')
    c.server.restore_sponsor_operability(c.cap)
    assert c.w.projection(c.t.track.track_identity).monitoring_reason != 'SHARED_MONITORING_CONNECTED'
    assert c.hub.connection_state is state


def test_reconciliation_preserves_ordering_failure_and_provenance(tmp_path, monkeypatch):
    c = _composition(tmp_path, monkeypatch)
    c.app.connect_provider(); c.queue.pop()()
    c.cap.sessions[0].consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
    c.w.mark_monitoring_unavailable('ORDERED_LIVE_FACTS_UNAVAILABLE')
    before = c.store.monitoring(c.t.track.track_identity)
    c.server.restore_sponsor_operability(c.cap)
    assert c.store.monitoring(c.t.track.track_identity) == before
    assert c.store.facts(c.t.track.track_identity) == ()
    assert c.store.events(c.t.track.track_identity) == ()


def test_restart_reconciles_persisted_evidence_only_after_valid_capability(tmp_path, monkeypatch):
    c = _composition(tmp_path, monkeypatch)
    c.server.restore_sponsor_operability()
    restored = PaperObservationTrackingWorkflow(LocalPaperObservationTrackStore(c.store.root), clock=lambda: NOW + timedelta(seconds=10))
    restored.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    c.server.trade_window.restore_paper_observation_monitoring = restored.restore_monitoring
    c.server.trade_window.mark_paper_observation_monitoring_unavailable = restored.mark_monitoring_unavailable
    c.server.restore_sponsor_operability()
    assert restored.active_monitoring_count == 0
    assert restored.projection(c.t.track.track_identity).monitoring_reason == 'PROVIDER_CAPABILITY_NOT_ACTIVE'
    c.app.connect_provider(); c.queue.pop()()
    assert restored.active_monitoring_count == 1
    assert restored.projection(c.t.track.track_identity).track == c.t.track
    assert c.store.events(c.t.track.track_identity) == ()


def test_failed_owner_restore_does_not_skip_other_owners(tmp_path, monkeypatch, caplog):
    c = _composition(tmp_path, monkeypatch)
    c.server.trade_window.restore_current_entry_monitoring.side_effect = RuntimeError('PRIVATE-EXCEPTION-CONTENT')
    c.app.connect_provider(); c.queue.pop()()
    assert c.w.active_monitoring_count == 1
    c.server.native_review.restore_lifecycle_monitoring.assert_called_once()
    assert 'PRIVATE-EXCEPTION-CONTENT' not in caplog.text
    assert 'FACTUAL_MONITORING_REGISTRATION_FAILED' in caplog.text


@pytest.mark.parametrize('error,expected', [
    (MonitoringError(MonitoringFailure.INSTRUMENT_NOT_RESOLVED), 'INSTRUMENT_NOT_RESOLVED'),
    (MonitoringError(MonitoringFailure.CAPABILITY_UNAVAILABLE), 'CAPABILITY_UNAVAILABLE'),
    (InstrumentResolutionError(InstrumentResolutionFailure.NO_MATCH), 'NO_MATCH'),
    (ValueError('untrusted private content'), 'FACTUAL_MONITORING_REGISTRATION_FAILED'),
])
def test_registration_failures_keep_bounded_reasons(tmp_path, monkeypatch, error, expected):
    c = _composition(tmp_path, monkeypatch)
    c.cap.open_monitoring_session = Mock(side_effect=error)
    c.app.connect_provider(); c.queue.pop()()
    assert c.w.projection(c.t.track.track_identity).monitoring_reason == expected
    assert c.w.active_monitoring_count == 0
    assert c.hub.active_session_count == 0
    assert c.hub.subscription_count == 0
    assert c.store.events(c.t.track.track_identity) == ()


def test_missing_master_is_not_inactive_authentication(tmp_path, monkeypatch):
    c = _composition(tmp_path, monkeypatch)
    monkeypatch.setattr('kronos.browser.server.resolve_governed_monitoring_instrument', Mock(side_effect=MonitoringError(MonitoringFailure.INSTRUMENT_NOT_RESOLVED)))
    c.app.connect_provider(); c.queue.pop()()
    assert c.cap.active
    assert c.w.projection(c.t.track.track_identity).monitoring_reason == 'INSTRUMENT_NOT_RESOLVED'
    assert not c.cap.sessions


def test_inactive_capability_is_fail_closed(tmp_path, monkeypatch):
    c = _composition(tmp_path, monkeypatch)
    c.cap.active = False
    assert c.w.restore_monitoring(c.cap, Mock(side_effect=AssertionError('must not resolve'))) == ()
    assert c.w.projection(c.t.track.track_identity).monitoring_reason == 'PROVIDER_CAPABILITY_NOT_ACTIVE'
    assert c.hub.active_session_count == 0


def test_obsolete_queued_completion_cannot_restore_new_context():
    queue, restored = [], []
    provider = _Provider()
    factory = Mock(return_value=provider)
    app = SwingOpportunitiesApplication(factory, background_runner=lambda op, name: queue.append(op))
    app.register_sponsor_operability_restorer(restored.append)
    app.connect_provider(); old = queue.pop()
    app.close()
    app.connect_provider(); new = queue.pop()
    old()
    factory.assert_not_called()
    new(); old(); new()
    assert restored == [provider.capability]
    factory.assert_called_once()


def test_obsolete_inflight_completion_cannot_overwrite_new_attempt():
    entered, release = Event(), Event()
    first, second = _Provider(), _Provider()
    original = first.complete_callback
    def blocked(attempt):
        entered.set()
        assert release.wait(5)
        return original(attempt)
    first.complete_callback = blocked
    providers = iter((first, second))
    queue, restored = [], []
    app = SwingOpportunitiesApplication(lambda: next(providers), background_runner=lambda op, name: queue.append(op))
    app.register_sponsor_operability_restorer(restored.append)
    app.connect_provider()
    thread = Thread(target=queue.pop())
    thread.start()
    try:
        assert entered.wait(5)
        app.close()
        app.connect_provider()
    finally:
        release.set(); thread.join(5)
    assert not thread.is_alive()
    assert first.ended and not restored
    assert app.snapshot().provider_state is ProviderConnectionState.CONNECTING
    queue.pop()()
    assert restored == [second.capability]


def test_disconnect_reconnect_uses_new_capability_only():
    queue, restored = [], []
    first, second = _Provider(), _Provider()
    providers = iter((first, second))
    app = SwingOpportunitiesApplication(lambda: next(providers), background_runner=lambda op, name: queue.append(op))
    app.register_sponsor_operability_restorer(restored.append)
    app.connect_provider(); old = queue.pop(); old()
    assert app.disconnect_provider()
    app.connect_provider(); queue.pop()(); old()
    assert restored == [first.capability, second.capability]
    assert not first.capability.active and second.capability.active


@pytest.mark.parametrize('error,expected', [
    (ValueError('KITE_READ_ONLY_CAPABILITY_UNAVAILABLE'), 'PROVIDER_CAPABILITY_NOT_ACTIVE'),
    (MonitoringError(MonitoringFailure.INSTRUMENT_NOT_RESOLVED), 'INSTRUMENT_NOT_RESOLVED'),
    (MonitoringError(MonitoringFailure.CAPABILITY_UNAVAILABLE), 'CAPABILITY_UNAVAILABLE'),
    (ValueError('PRIVATE-GEOMETRY-ERROR'), 'FACTUAL_MONITORING_REGISTRATION_FAILED'),
])
def test_paper_start_route_records_failure_for_affected_track_only(error, expected):
    fields = dict(run_identity='RUN', canonical_instrument='VBL', native_assessment_sha256='SHA', decision_identity='DECISION', track_confirmed='YES')
    body = urlencode(fields).encode()
    failure = Mock()
    server = SimpleNamespace(
        trade_window=SimpleNamespace(
            project=lambda *args: SimpleNamespace(native_assessment_sha256='SHA', sponsor_observation_decision_id='DECISION', sponsor_observation_choice='PAPER', paper_observation_track_start_available=True, activation_disposition='BLOCKED_RISK_UNAVAILABLE'),
            start_paper_observation_track=lambda *args, **kw: SimpleNamespace(track=SimpleNamespace(track_identity='TRACK')),
            record_paper_observation_monitoring_failure=failure,
        ),
        application=SimpleNamespace(opportunities_projection=lambda: (None, SimpleNamespace(run_identity='RUN'))),
        _operability_context=Mock(side_effect=error), _synchronize_trade_window=Mock(),
    )
    handler = SimpleNamespace(server=server, path='/swing/trade-window/paper-observation/start', headers={'Content-Length':str(len(body)), 'Content-Type':'application/x-www-form-urlencoded'}, rfile=BytesIO(body), _redirect=Mock())
    _BrowserHandler._start_paper_observation_track(handler)
    failure.assert_called_once_with('TRACK', expected)
    assert paper_monitoring_failure_reason(error) == expected


def test_restored_kr380_eligible_owner_is_attached_once(tmp_path, monkeypatch):
    from tests.unit.swing.v1 import test_native_entry_timing as nt
    from kronos.swing.v1.mtf_facts import FactualTimeframe
    c = _composition(tmp_path, monkeypatch)
    completed = nt._completed(tmp_path / 'native')
    stores = (
        nt.LocalKr370Step31HandoffStore(tmp_path / 'handoffs'),
        nt.LocalTradePlanStore(tmp_path / 'plans'),
        nt.LocalPortfolioStateV1Store(tmp_path / 'portfolio'),
        nt.LocalRiskPermissionV1Store(tmp_path / 'risk'),
        nt.LocalKr380V2Store(tmp_path / 'kr380'),
        nt.LocalObjectiveModelV1Store(tmp_path / 'kr390'),
    )
    workflow = nt.SwingTradeWindowWorkflow(*stores)
    projected = workflow.construct(completed, nt._evidence(completed), nt._context(completed.requirement.canonical_instrument), current_run_identity=completed.requirement.native_run_identity, current_analysis_boundary=completed.promotion.analysis_boundary, created_at=nt.NOW)
    plan = projected.trade_plan
    workflow.publish_portfolio_state(cycle_identity='TEST-CYCLE', as_of_boundary=nt.NOW, objective_exposures=(), sponsor_exposures=(), source_identities=('TEST-OBJECTIVE-STORE', 'TEST-POSITION-STORE'), sources_complete=True, provenance=('DOMAIN-005', 'ADR-0013'))
    workflow.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    cap = nt._MonitoringCapability()
    instrument = nt.InstrumentRecord('KITE', 'NSE', 'NSE', plan.canonical_instrument, plan.canonical_instrument, 'EQ', None)
    fact = completed.mtf_snapshot.instrument(plan.canonical_instrument).fact(FactualTimeframe.ONE_HOUR)
    binding = workflow.start_current_entry_monitoring(plan.native_run_identity, plan.canonical_instrument, capability=cap, instrument=instrument, session_identity=fact.session_identity, observation_boundary=fact.observation_boundary, ecpc_outcome=nt.EcpcV2Outcome.PENDING, ecpc_blockers=(nt.EcpcV2Blocker.EXECUTION_CONFIRMATION_PENDING,), clock=lambda: nt.NOW)
    outcome = workflow.evaluate_current_entry_timing(
        plan.native_run_identity, plan.canonical_instrument,
        session_identity=fact.session_identity, observation_boundary=fact.observation_boundary,
        ecpc_outcome=nt.EcpcV2Outcome.PENDING,
        ecpc_blockers=(nt.EcpcV2Blocker.EXECUTION_CONFIRMATION_PENDING,),
        previous=None, current=None, evaluated_at=nt.NOW,
        monitoring_binding_id=binding,
    )
    assert outcome.state is nt.Kr380V2State.FORMING
    workflow.close_monitoring()
    restored = nt.SwingTradeWindowWorkflow(*stores)
    restored.restore((completed,))
    restored.set_shared_monitoring_hub(c.hub)
    c.server.trade_window.restore_current_entry_monitoring = lambda capability, resolver: restored.restore_current_entry_monitoring(capability, lambda *args: instrument, clock=lambda: nt.NOW)
    c.app.connect_provider(); c.queue.pop()()
    assert plan.trade_plan_id in restored._monitoring_registrations
    before = c.hub.subscription_reference_count(instrument)
    c.server.restore_sponsor_operability(c.cap)
    assert c.hub.subscription_reference_count(instrument) == before
    assert len(c.cap.sessions) == 1
    assert stores[-1].load_for_plan(plan.trade_plan_id) is None


def test_restored_sponsor_position_owner_is_attached_without_new_position(tmp_path, monkeypatch):
    from tests.unit.swing.v1 import test_native_active_trade_lifecycle as lifecycle
    from kronos.market.calendar import MarketCalendarPublisher
    c = _composition(tmp_path, monkeypatch)
    result, plan, *_ = lifecycle._go(lifecycle.SponsorTradeChoice.PAPER)
    store = lifecycle.LocalActiveTradeLifecycleStore(tmp_path / 'lifecycle')
    service = lifecycle.ActiveTradeLifecycleService(store)
    position = service.register(result, plan)
    restored = lifecycle.ActiveTradeLifecycleService(store)
    coordinator = lifecycle.ActiveLifecycleMonitoringCoordinator(restored, MarketCalendarPublisher(), clock=lambda: lifecycle.NOW)
    coordinator.set_shared_monitoring_hub(c.hub)
    instrument = lifecycle.InstrumentRecord('KITE', 'NSE', 'NSE', 'IOC', 'IOC', 'EQ', None)
    c.server.native_review.restore_lifecycle_monitoring = lambda capability, resolver: coordinator.restore(capability, lambda symbol: instrument)
    c.server.native_review.snapshot = lambda: SimpleNamespace(active_lifecycle=restored.snapshot())
    c.server.ux10_notifications = SimpleNamespace(observe_active_trade_monitoring_activation=Mock())
    before = restored.snapshot()
    c.app.connect_provider(); c.queue.pop()()
    assert coordinator.active_position_ids == (position.position_id,)
    c.server.restore_sponsor_operability(c.cap)
    assert coordinator.active_position_ids == (position.position_id,)
    # The Paper Track fixture and Sponsor Position are two legitimate owners.
    assert c.hub.subscription_reference_count(instrument) == 2
    assert len(c.cap.sessions) == 1
    assert restored.snapshot() == before


def test_restart_does_not_reuse_old_connected_callback(tmp_path, monkeypatch):
    c = _composition(tmp_path, monkeypatch)
    c.w.attach_monitoring(c.t.track.track_identity, c.cap, c.instrument)
    c.cap.sessions[0].consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
    restarted = PaperObservationTrackingWorkflow(LocalPaperObservationTrackStore(c.store.root), clock=lambda: NOW + timedelta(seconds=10))
    restarted.set_shared_monitoring_hub(SharedSwingMonitoringHub())
    fresh = _Capability()
    restarted.restore_monitoring(fresh, lambda symbol: c.instrument)
    assert restarted.projection(c.t.track.track_identity).monitoring_reason == 'SHARED_HUB_REGISTRATION_ACTIVE'
    assert restarted._hub.connection_state is None


def test_authentication_marker_cannot_hide_unresolved_ordering_failure(tmp_path, monkeypatch):
    c = _composition(tmp_path, monkeypatch)
    c.w.attach_monitoring(c.t.track.track_identity, c.cap, c.instrument)
    c.cap.sessions[0].consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
    c.w.mark_monitoring_unavailable('PROVIDER_SEQUENCE_CONFLICT')
    c.w.mark_monitoring_unavailable('PROVIDER_CAPABILITY_NOT_ACTIVE')
    c.w.attach_monitoring(c.t.track.track_identity, c.cap, c.instrument)
    assert c.w.projection(c.t.track.track_identity).monitoring_reason == 'PROVIDER_SEQUENCE_CONFLICT'
    assert len(c.cap.sessions) == 1
    assert c.store.events(c.t.track.track_identity) == ()


def test_existing_registration_cannot_claim_a_different_instrument_binding(tmp_path, monkeypatch):
    from dataclasses import replace
    c = _composition(tmp_path, monkeypatch)
    c.w.attach_monitoring(c.t.track.track_identity, c.cap, c.instrument)
    different = replace(c.instrument, trading_symbol=c.instrument.trading_symbol + '-OTHER')
    result = c.w.attach_monitoring(c.t.track.track_identity, c.cap, different)
    assert result.monitoring_reason == 'GOVERNED_INSTRUMENT_BINDING_INVALID'
    assert c.cap.sessions[0].subscribed == [(c.instrument,)]
    assert c.hub.subscription_count == 1
