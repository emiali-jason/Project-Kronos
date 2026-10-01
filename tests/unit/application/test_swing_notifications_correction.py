"""WO-SWING-NEXT-13.1 behavior at existing owners; no real transport."""
from datetime import timedelta
from types import SimpleNamespace
import threading
import pytest

from kronos.application.swing_ux10 import Ux10DeliveryState, Ux10NotificationStore
from kronos.application.swing_notifications import monitoring_indicator
from kronos.application.swing_progression_watch import SwingProgressionWatchWorkflow
from kronos.provider.contracts.monitoring import MonitoringConnectionState as Connection
from kronos.integrations.telegram import TelegramDeliveryResult, TelegramDeliveryState
from kronos.swing.v1.analytical_promotion_v2 import create_record
from kronos.swing.v1.progression_watch import ProgressionWatchStore
from tests.unit.application.test_swing_ux10 import (ux10, Telegram, NOW,
    v2_source, v2_criteria, v2_nse, _triggered)


def promotion(count, offset=0, assessment=None):
    source = v2_source()
    if assessment is not None:
        source['native_assessment_sha256'] = assessment * 64
    return create_record(source=source, criteria=v2_criteria(count),
        confirmation=v2_nse(), created_at=NOW + timedelta(seconds=offset))


def test_same_run_successor_restart_replay_and_nonsemantic_churn(tmp_path):
    ready, now = promotion(4), promotion(5, 1)
    first = ux10(tmp_path)
    assert first.observe_promotions((ready,)) == ()
    restored = ux10(tmp_path)
    event, = restored.observe_promotions((now,))
    assert event.run_identity == ready.value['source']['native_run_identity']
    assert event.source_event_identity == now.value['integrity_sha256']
    again = ux10(tmp_path)
    assert again.observe_promotions((ready, now, promotion(4, 2), promotion(5, 3))) == ()
    assert len(again.snapshot().records) == 1
    assert again.evidence(event.notification_id)['predecessor_identity'] == ready.value['integrity_sha256']
    # A fresh authoritative assessment can provide another genuine edge.
    assert again.observe_promotions((promotion(4, 4, 'b'),)) == ()
    assert len(again.observe_promotions((promotion(5, 5, 'b'),))) == 1


def test_first_now_and_old_unknown_assessment_do_not_replay(tmp_path):
    service = ux10(tmp_path)
    assert service.observe_promotions((promotion(5, 10),)) == ()
    assert service.observe_promotions((promotion(4, 0, 'c'),)) == ()
    assert service.observe_promotions((promotion(5, 11, 'c'),)) == ()


def test_recovered_incident_dedups_disconnect_and_links_restoration(tmp_path):
    service = ux10(tmp_path)
    down = service.observe_connection_state('owner', 'CDSL', Connection.DISCONNECTED, occurred_at=NOW)
    restored = ux10(tmp_path)
    assert restored.observe_connection_state('owner', 'CDSL', Connection.RECONNECTING,
        occurred_at=NOW + timedelta(seconds=20)) is None
    up = restored.observe_connection_state('owner', 'CDSL', Connection.CONNECTED,
        occurred_at=NOW + timedelta(seconds=30))
    assert restored.evidence(down.notification_id)['incident_identity'] == restored.evidence(up.notification_id)['incident_identity']
    assert '30s' in up.summary
    again = ux10(tmp_path)
    assert again.observe_connection_state('owner', 'CDSL', Connection.CONNECTED,
        occurred_at=NOW + timedelta(seconds=31)) is None
    assert again.observe_connection_state('owner', 'CDSL', Connection.DISCONNECTED,
        occurred_at=NOW) is None
    assert len(again.snapshot().records) == 2


def test_connected_without_retained_incident_is_baseline_only(tmp_path):
    service = ux10(tmp_path)
    assert service.observe_connection_state('owner', 'CDSL', Connection.CONNECTED) is None
    assert service.snapshot().records == ()


@pytest.mark.parametrize('result', [
    TelegramDeliveryResult(TelegramDeliveryState.FAILED_RETRYABLE, 'TELEGRAM_TRANSPORT_UNAVAILABLE'),
    TelegramDeliveryResult(TelegramDeliveryState.FAILED_FINAL, 'TELEGRAM_RESPONSE_INVALID'),
    TelegramDeliveryResult(TelegramDeliveryState.FAILED_RETRYABLE, 'TELEGRAM_CONFIGURATION_UNAVAILABLE'),
])
def test_ambiguous_transport_keeps_browser_and_never_automatically_retries(tmp_path, result):
    telegram = Telegram((result,))
    service = ux10(tmp_path, telegram)
    service.observe_progression_watch(_triggered('CANBK'))
    record, = service.snapshot().records
    assert record.telegram_delivery_state is Ux10DeliveryState.DELIVERY_UNCERTAIN
    assert record.delivery_attempt_identity and record.delivery_attempts == 1
    assert record.browser_delivery_state is Ux10DeliveryState.SENT
    restored = ux10(tmp_path, telegram)
    restored.retry_pending()
    assert len(telegram.messages) == 1


def test_crash_after_attempt_claim_before_send_is_uncertain(tmp_path):
    class CrashBeforeSend(Telegram):
        def send(self, text):
            retained, = Ux10NotificationStore(tmp_path).load()
            assert retained.delivery_attempt_identity
            assert retained.telegram_delivery_state is Ux10DeliveryState.DELIVERY_UNCERTAIN
            raise SystemExit('simulated process loss before transport acceptance')
    with pytest.raises(SystemExit):
        ux10(tmp_path, CrashBeforeSend()).observe_progression_watch(_triggered('CANBK'))
    telegram = Telegram()
    restored = ux10(tmp_path, telegram)
    restored.retry_pending()
    assert telegram.messages == []
    assert restored.snapshot().records[0].telegram_delivery_state is Ux10DeliveryState.DELIVERY_UNCERTAIN


def test_attempt_persistence_failure_prevents_send(tmp_path, monkeypatch):
    telegram = Telegram()
    service = ux10(tmp_path, telegram)
    retain = service._store.retain
    def fail_claim(record):
        if record.delivery_attempt_identity:
            raise OSError('controlled attempt persistence failure')
        retain(record)
    monkeypatch.setattr(service._store, 'retain', fail_claim)
    with pytest.raises(OSError):
        service.observe_progression_watch(_triggered('CANBK'))
    assert telegram.messages == []
    assert Ux10NotificationStore(tmp_path).load()[0].delivery_attempts == 0


def test_confirmed_delivery_persists_attempt_and_restart_does_not_resend(tmp_path):
    telegram = Telegram()
    service = ux10(tmp_path, telegram)
    service.observe_progression_watch(_triggered('CANBK'))
    record, = Ux10NotificationStore(tmp_path).load()
    assert record.telegram_delivery_state is Ux10DeliveryState.SENT
    assert record.delivery_attempt_identity and record.delivery_attempts == 1
    ux10(tmp_path, telegram).retry_pending()
    assert len(telegram.messages) == 1


def test_parallel_dispatch_has_one_durable_claim(tmp_path):
    entered, release = threading.Event(), threading.Event()
    class BlockingTelegram(Telegram):
        def send(self, text):
            self.messages.append(text)
            entered.set()
            assert release.wait(3)
            return TelegramDeliveryResult(TelegramDeliveryState.SENT)
    telegram = BlockingTelegram()
    service = ux10(tmp_path, telegram)
    pending = []
    service._background = lambda operation, _name: pending.append(operation)
    service.observe_progression_watch(_triggered('CANBK'))
    worker = threading.Thread(target=pending[0]); worker.start()
    assert entered.wait(3)
    service.retry_pending()
    assert len(pending) == 1
    release.set(); worker.join(3)
    assert not worker.is_alive() and len(telegram.messages) == 1


@pytest.mark.parametrize(('evidence', 'expected'), [
    (None, 'UNAVAILABLE'),
    ({'state': 'ACTIVE', 'registered': True, 'connection': 'CONNECTED'}, 'UNAVAILABLE'),
    ({'state': 'ACTIVE', 'registered': False, 'connection': 'CONNECTED'}, 'UNAVAILABLE'),
    ({'state': 'ACTIVE', 'registered': True, 'connection': 'DISCONNECTED'}, 'INTERRUPTED'),
    ({'state': 'TRIGGERED'}, 'NOT_REQUIRED'),
    ({'state': 'MONITORING_UNAVAILABLE', 'registered': True, 'connection': 'CONNECTED'}, 'INTERRUPTED'),
])
def test_per_item_indicator_never_infers_continuity(evidence, expected):
    assert monitoring_indicator(evidence) == expected


def test_exact_watch_consumer_and_session_not_another_connected_owner(tmp_path):
    workflow = SwingProgressionWatchWorkflow(ProgressionWatchStore(tmp_path))
    watch = _triggered('CANBK')
    from kronos.swing.v1.progression_watch import activate_watch
    watch = activate_watch(watch.requirement, activated_at=NOW)
    workflow._watches[watch.watch_id] = watch
    observation = dict(connection_id='exact-session', session_continuous=True,
        previous_interval_available=True, ordering_deterministic=True, recovered=False)
    consumer = SimpleNamespace(session=SimpleNamespace(active=True, connection_state=Connection.CONNECTED),
        notification_observation=observation)
    workflow._consumers['unrelated-owner'] = consumer
    assert monitoring_indicator(workflow.notification_monitoring_evidence(watch.watch_id)) == 'UNAVAILABLE'
    workflow._consumers[watch.watch_id] = consumer
    assert monitoring_indicator(workflow.notification_monitoring_evidence(watch.watch_id)) == 'LIVE'
    consumer.notification_observation = dict(observation, recovered=True)
    assert monitoring_indicator(workflow.notification_monitoring_evidence(watch.watch_id)) == 'INTERRUPTED'


def test_legacy_pending_is_uncertain_without_invented_attempt(tmp_path):
    from dataclasses import asdict
    from kronos.application.swing_ux10 import Ux10NotificationRecord, _integrity_values
    service = ux10(tmp_path, Telegram())
    service._background = lambda *_args: None
    service.observe_progression_watch(_triggered('CANBK'))
    record, = service.snapshot().records
    values = asdict(record)
    values.update(delivery_protocol=None, delivery_attempt_identity=None)
    legacy = Ux10NotificationRecord(**(values | {'integrity_sha256': _integrity_values(values)}))
    service._store.retain(legacy)
    telegram = Telegram()
    restored = ux10(tmp_path, telegram)
    restored.retry_pending()
    uncertain, = restored.snapshot().records
    assert uncertain.telegram_delivery_state is Ux10DeliveryState.DELIVERY_UNCERTAIN
    assert uncertain.delivery_attempt_identity is None and telegram.messages == []


def test_success_accepted_but_result_persistence_crashes_no_restart_resend(tmp_path, monkeypatch):
    telegram = Telegram()
    service = ux10(tmp_path, telegram)
    retain = service._store.retain
    def fail_confirmation(record):
        if record.telegram_delivery_state is Ux10DeliveryState.SENT:
            raise OSError('simulated lost confirmation persistence')
        retain(record)
    monkeypatch.setattr(service._store, 'retain', fail_confirmation)
    with pytest.raises(OSError):
        service.observe_progression_watch(_triggered('CANBK'))
    restored = ux10(tmp_path, telegram)
    restored.retry_pending()
    assert len(telegram.messages) == 1
    assert restored.snapshot().records[0].telegram_delivery_state is Ux10DeliveryState.DELIVERY_UNCERTAIN


def test_context_gap_escalates_once_with_same_incident_after_restart(tmp_path):
    service = ux10(tmp_path)
    down = service.observe_connection_state('owner', 'CDSL', Connection.DISCONNECTED, occurred_at=NOW)
    gap = service.observe_connection_state('owner', 'CDSL', Connection.CONTEXT_INCOMPLETE,
        occurred_at=NOW + timedelta(seconds=5))
    assert gap.notification_type.value == 'MONITORING_GAP_RECONCILIATION_REQUIRED'
    restored = ux10(tmp_path)
    assert restored.observe_connection_state('owner', 'CDSL', Connection.CONTEXT_INCOMPLETE,
        occurred_at=NOW + timedelta(seconds=6)) is None
    up = restored.observe_connection_state('owner', 'CDSL', Connection.CONNECTED,
        occurred_at=NOW + timedelta(seconds=10))
    identities = {restored.evidence(r.notification_id)['incident_identity'] for r in (down, gap, up)}
    assert len(identities) == 1 and '10s' in up.summary


def test_closed_notification_owner_never_writes_recovery_baselines(tmp_path):
    service = ux10(tmp_path)
    service.close()
    assert service.observe_promotions((promotion(4), promotion(5, 1))) == ()
    assert service.observe_connection_state('owner', 'CDSL', Connection.DISCONNECTED) is None
    assert not (tmp_path/'context').exists()


def test_corrupt_recovery_context_fails_closed(tmp_path):
    service = ux10(tmp_path)
    service.observe_promotions((promotion(4),))
    path = tmp_path/'context'/'promotion-baselines.json'
    import json
    value = json.loads(path.read_text()); value['sha256'] = '0'*64
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='RECOVERY_CONTEXT_INVALID'):
        ux10(tmp_path)


def test_safe_retries_are_bounded_and_attempt_ids_are_distinct(tmp_path):
    failures = [TelegramDeliveryResult(TelegramDeliveryState.FAILED_RETRYABLE,
        'TELEGRAM_RATE_LIMITED', 1)] * 5
    telegram = Telegram(failures)
    service = ux10(tmp_path, telegram)
    clock = [NOW]
    service._clock = lambda: clock[0]
    service.observe_progression_watch(_triggered('CANBK'))
    attempts = {service.snapshot().records[0].delivery_attempt_identity}
    for _ in range(5):
        clock[0] += timedelta(seconds=2)
        service.retry_pending()
        attempts.add(service.snapshot().records[0].delivery_attempt_identity)
    record, = service.snapshot().records
    assert len(attempts) == len(telegram.messages) == record.delivery_attempts == 4
    assert record.telegram_delivery_state is Ux10DeliveryState.FAILED_FINAL


def test_maintenance_fence_denies_baseline_and_incident_writes(tmp_path):
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    from kronos.application.swing_ux10 import SwingUx10NotificationService
    admission = MaintenanceAdmissionCoordinator()
    service = SwingUx10NotificationService(Ux10NotificationStore(tmp_path), maintenance_admission=admission)
    assert admission.claim('e'*64)
    assert service.observe_promotions((promotion(4), promotion(5, 1))) == ()
    assert service.observe_connection_state('owner', 'CDSL', Connection.DISCONNECTED) is None
    assert not (tmp_path/'context').exists()
    assert admission.snapshot()['owners'] == {}


def test_reconnected_consumer_needs_new_session_observation(tmp_path):
    from kronos.application.swing_progression_watch import _ProgressionMonitoringConsumer
    watch = _triggered('CANBK')
    workflow = SimpleNamespace(observe_connection_state=lambda *_: None, _clock=lambda: NOW)
    consumer = _ProgressionMonitoringConsumer(workflow, watch, None, None)
    consumer.notification_observation = {'connection_id': 'previous-session'}
    consumer.on_connection_state(Connection.CONNECTED)
    assert consumer.notification_observation is None


def test_exact_position_owner_state_overrides_connected_session(tmp_path):
    from kronos.swing.v1.native_active_trade_lifecycle import ActiveLifecycleMonitoringCoordinator
    position = SimpleNamespace(state=SimpleNamespace(value='MONITORING_UNAVAILABLE'))
    coordinator = ActiveLifecycleMonitoringCoordinator(SimpleNamespace(_require=lambda _: position),
        None, clock=lambda: NOW)
    coordinator._consumers['position-1'] = SimpleNamespace(
        session=SimpleNamespace(active=True, connection_state=Connection.CONNECTED),
        notification_observation=dict(connection_id='current', session_continuous=True,
            previous_interval_available=True, ordering_deterministic=True, recovered=False))
    assert monitoring_indicator(coordinator.notification_monitoring_evidence('position-1')) == 'INTERRUPTED'
    position.state.value = 'PAPER_ACTIVE'
    assert monitoring_indicator(coordinator.notification_monitoring_evidence('position-1')) == 'LIVE'
    assert monitoring_indicator(coordinator.notification_monitoring_evidence('other-position')) == 'UNAVAILABLE'


def _connection(service, state, seconds):
    return service.observe_connection_state('owner', 'CDSL', state,
        occurred_at=NOW + timedelta(seconds=seconds))


def _retained_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob('*.json')}


@pytest.mark.parametrize('followup', [Connection.CONNECTED, Connection.DISCONNECTED])
def test_r3_retained_incident_overrides_old_connected_checkpoint_after_crash(
    tmp_path, monkeypatch, followup,
):
    from copy import deepcopy
    service = ux10(tmp_path)
    # Retained R2 schema: CONNECTED baseline existed before the lost checkpoint.
    service._store.retain_context('connection-baselines', {'owner': dict(
        state='CONNECTED', at=(NOW - timedelta(seconds=5)).isoformat(), incident=None, open=False)})
    service = ux10(tmp_path)
    original = service._store.retain_context
    def crash(name, value):
        if name == 'connection-baselines':
            raise SystemExit('event retained; process lost before recovery context')
        original(name, value)
    monkeypatch.setattr(service._store, 'retain_context', crash)
    with pytest.raises(SystemExit):
        _connection(service, Connection.DISCONNECTED, 0)
    records = Ux10NotificationStore(tmp_path).load()
    assert len(records) == 1
    down = records[0]
    assert Ux10NotificationStore(tmp_path).context('connection-baselines')['owner']['state'] == 'CONNECTED'
    before_restart = _retained_bytes(tmp_path)
    recovered = ux10(tmp_path)
    assert _retained_bytes(tmp_path) == before_restart  # Recovery reads; no startup writes.
    baseline = recovered._connection_state['owner']
    assert baseline['open'] and baseline['incident'] == down.source_event_identity
    assert baseline['incident_started_at'] == baseline['observed_at'] == NOW.isoformat()
    # A stale observation must not even repair the lagging checkpoint.
    memory = deepcopy(recovered._connection_state)
    assert _connection(recovered, Connection.CONNECTED, -1) is None
    assert recovered._connection_state == memory and _retained_bytes(tmp_path) == before_restart
    result = _connection(recovered, followup, 10)
    if followup is Connection.CONNECTED:
        assert result is not None and '10s' in result.summary
        assert recovered.evidence(result.notification_id)['incident_identity'] == down.source_event_identity
    else:
        assert result is None and len(recovered.snapshot().records) == 1
        assert recovered._connection_state['owner']['incident'] == down.source_event_identity
    assert recovered._store.context('connection-baselines') == recovered._connection_state
    for _ in range(2):
        recovered = ux10(tmp_path)
        retained = _retained_bytes(tmp_path)
        assert _connection(recovered, Connection.DISCONNECTED, 0) is None
        assert _connection(recovered, followup, 10) is None
        assert _retained_bytes(tmp_path) == retained
    if followup is Connection.DISCONNECTED:
        result = _connection(recovered, Connection.CONNECTED, 30)
        assert '30s' in result.summary
        assert recovered.evidence(result.notification_id)['incident_identity'] == down.source_event_identity
    restored = ux10(tmp_path)
    assert _connection(restored, Connection.CONNECTED, 30) is None
    assert len(restored.snapshot().records) == 2
    assert restored.snapshot().active_incidents == ()


@pytest.mark.parametrize('restart_after_gap', [False, True])
def test_r3_gap_observation_boundary_rejects_stale_restoration(tmp_path, restart_after_gap):
    from copy import deepcopy
    service = ux10(tmp_path)
    down = _connection(service, Connection.DISCONNECTED, 0)
    gap = _connection(service, Connection.CONTEXT_INCOMPLETE, 20)
    if restart_after_gap:
        service = ux10(tmp_path)
    baseline = deepcopy(service._connection_state)
    assert baseline['owner']['incident_started_at'] == NOW.isoformat()
    assert baseline['owner']['observed_at'] == (NOW + timedelta(seconds=20)).isoformat()
    retained = _retained_bytes(tmp_path)
    assert _connection(service, Connection.CONNECTED, 10) is None
    assert service._connection_state == baseline and _retained_bytes(tmp_path) == retained
    assert len(service.snapshot().records) == 2 and service.snapshot().active_incidents
    service = ux10(tmp_path)
    assert _connection(service, Connection.CONNECTED, 10) is None
    up = _connection(service, Connection.CONNECTED, 30)
    assert '30s' in up.summary
    assert {service.evidence(r.notification_id)['incident_identity'] for r in (down, gap, up)} == {down.source_event_identity}
    retained = _retained_bytes(tmp_path)
    for _ in range(2):
        service = ux10(tmp_path)
        for state, second in [(Connection.DISCONNECTED, 0), (Connection.CONTEXT_INCOMPLETE, 20),
                              (Connection.CONNECTED, 10), (Connection.CONNECTED, 30)]:
            assert _connection(service, state, second) is None
        assert _retained_bytes(tmp_path) == retained
        assert len(service.snapshot().records) == 3 and service.snapshot().active_incidents == ()


@pytest.mark.parametrize('state', [Connection.DISCONNECTED, Connection.RECONNECTING,
    Connection.CONTEXT_INCOMPLETE, Connection.CONNECTED])
def test_r3_silent_observations_advance_durable_boundary(tmp_path, state):
    service = ux10(tmp_path)
    if state is not Connection.CONNECTED:
        _connection(service, state, 0)
    else:
        _connection(service, Connection.CONNECTED, 0)
    count = len(service.snapshot().records)
    assert _connection(service, state, 20) is None
    service = ux10(tmp_path)
    retained = _retained_bytes(tmp_path)
    assert _connection(service, Connection.DISCONNECTED if state is Connection.CONNECTED
        else Connection.CONNECTED, 10) is None
    assert len(service.snapshot().records) == count
    assert _retained_bytes(tmp_path) == retained
    assert service._connection_state['owner']['observed_at'] == (NOW + timedelta(seconds=20)).isoformat()


@pytest.mark.parametrize('transition', [Connection.DISCONNECTED, Connection.CONTEXT_INCOMPLETE,
    Connection.CONNECTED])
@pytest.mark.parametrize('failure', ['binding_before', 'binding_after', 'event_before',
    'event_after', 'checkpoint_before', 'checkpoint_after'])
def test_r3_publication_failure_reconciles_retained_event_and_context(
    tmp_path, monkeypatch, transition, failure,
):
    service = ux10(tmp_path)
    if transition is Connection.DISCONNECTED:
        _connection(service, Connection.CONNECTED, -5)
    else:
        _connection(service, Connection.DISCONNECTED, 0)
    original_retain = service._store.retain
    original_context = service._store.retain_context
    failed = [False]
    def retain(record):
        if failure.startswith('event_') and not failed[0]:
            failed[0] = True
            if failure.endswith('_after'):
                original_retain(record)
            raise OSError('injected event publication failure')
        original_retain(record)
    def context(name, value):
        target = 'source-bindings' if failure.startswith('binding_') else 'connection-baselines'
        if not failure.startswith('event_') and name == target and not failed[0]:
            failed[0] = True
            if failure.endswith('_after'):
                original_context(name, value)
            raise OSError('injected context publication failure')
        original_context(name, value)
    monkeypatch.setattr(service._store, 'retain', retain)
    monkeypatch.setattr(service._store, 'retain_context', context)
    with pytest.raises(OSError):
        _connection(service, transition, 20)
    restarted = ux10(tmp_path)
    assert service._connection_state == restarted._connection_state
    assert service.snapshot().records == restarted.snapshot().records
    survived = failure in {'event_after', 'checkpoint_before', 'checkpoint_after'}
    if survived:
        assert restarted._connection_state['owner']['observed_at'] == (NOW + timedelta(seconds=20)).isoformat()
        before = _retained_bytes(tmp_path)
        assert _connection(restarted, Connection.CONNECTED, 10) is None
        assert _retained_bytes(tmp_path) == before
        assert _connection(restarted, transition, 20) is None
    else:
        assert _connection(restarted, transition, 20) is not None
    assert restarted._store.context('connection-baselines') == restarted._connection_state
    if transition is not Connection.CONNECTED:
        restored = _connection(restarted, Connection.CONNECTED, 30)
        assert ('10s' if transition is Connection.DISCONNECTED else '30s') in restored.summary
    count = len(restarted.snapshot().records)
    for _ in range(2):
        restarted = ux10(tmp_path)
        assert _connection(restarted, transition, 20) is None
        assert _connection(restarted, Connection.CONNECTED, 30) is None
        assert len(restarted.snapshot().records) == count
        assert restarted.snapshot().active_incidents == ()


def test_r3_r2_gap_checkpoint_recovers_latest_boundary_without_resetting_start(tmp_path):
    service = ux10(tmp_path)
    down = _connection(service, Connection.DISCONNECTED, 0)
    gap = _connection(service, Connection.CONTEXT_INCOMPLETE, 20)
    # R2 used at=incident start, even after a later gap event was accepted.
    service._store.retain_context('connection-baselines', {'owner': dict(
        state='CONTEXT_INCOMPLETE', at=NOW.isoformat(),
        incident=down.source_event_identity, open=True, gap=True)})
    # R2 bindings also did not carry the newly explicit start field.
    bindings = service._store.context('source-bindings')
    for binding in bindings.values():
        binding.pop('incident_started_at', None)
    service._store.retain_context('source-bindings', bindings)
    recovered = ux10(tmp_path)
    before = _retained_bytes(tmp_path)
    assert _connection(recovered, Connection.CONNECTED, 10) is None
    assert _retained_bytes(tmp_path) == before
    up = _connection(recovered, Connection.CONNECTED, 30)
    assert '30s' in up.summary
    assert {recovered.evidence(r.notification_id)['incident_identity'] for r in (down, gap, up)} == {down.source_event_identity}
    assert _connection(ux10(tmp_path), Connection.CONNECTED, 30) is None


@pytest.mark.parametrize('after_write', [False, True])
@pytest.mark.parametrize('state', [Connection.CONNECTED, Connection.DISCONNECTED])
def test_r3_silent_checkpoint_failure_does_not_invent_an_event_or_ram_boundary(
    tmp_path, monkeypatch, after_write, state,
):
    service = ux10(tmp_path)
    _connection(service, state, 0)
    original = service._store.retain_context
    def fail(name, value):
        if after_write:
            original(name, value)
        raise OSError('injected silent checkpoint failure')
    monkeypatch.setattr(service._store, 'retain_context', fail)
    with pytest.raises(OSError):
        _connection(service, state, 20)
    recovered = ux10(tmp_path)
    assert service._connection_state == recovered._connection_state
    boundary = (NOW + timedelta(seconds=20 if after_write else 0)).isoformat()
    assert recovered._connection_state['owner']['observed_at'] == boundary
    assert len(recovered.snapshot().records) == (0 if state is Connection.CONNECTED else 1)
    assert _connection(recovered, state, 20) is None
    assert recovered._connection_state == recovered._store.context('connection-baselines')
