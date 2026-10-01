"""Swing-only Browser correction; local mock-owned server, never production."""
from contextlib import contextmanager
from datetime import timedelta
from hashlib import sha256
from threading import Thread
from types import SimpleNamespace
from urllib.parse import urlencode
import json

from kronos.application.notifications import NotificationWorkspaceSnapshot
from kronos.application.swing_notifications import project_swing_notification_workspace, notification_revision
from kronos.application.swing_progression_watch import SwingProgressionWatchSnapshot
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.swing.v1 import LocalTradingViewEvidenceStore
from kronos.swing.v1.progression_watch import activate_watch
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.application.test_swing_ux10 import ux10
from tests.unit.application.test_swing_notifications_correction import promotion
from tests.unit.browser.test_browser_notifications import _triggered
from tests.unit.browser.test_browser_notification_centre import _centre, NOW, RUN
from tests.unit.browser.test_browser_server import _request


def watches(*items):
    return project_swing_notification_workspace(SwingProgressionWatchSnapshot(RUN, (), items))


def test_active_to_triggered_updates_same_card_once_and_keeps_dismissal(tmp_path):
    clock = [NOW + timedelta(days=10)]
    centre = _centre(tmp_path, clock)
    service = ux10(tmp_path/'ux10')
    triggered = _triggered('CANBK')
    active = activate_watch(triggered.requirement, activated_at=triggered.activated_at)
    assert active.watch_id == triggered.watch_id
    first, = centre.synchronize(watches(active), service.snapshot(),
        current_run_identity=RUN, websocket_state='CONNECTED').records
    service.observe_progression_watch(triggered)
    progressed, = centre.synchronize(watches(triggered), service.snapshot(),
        current_run_identity=RUN, websocket_state='CONNECTED').records
    assert progressed.notification_identity == first.notification_identity
    assert progressed.notification_type == 'PROMOTION_WATCH_REACHED'
    assert progressed.priority == 'HIGH' and progressed.summary != first.summary
    assert sum(e.event_type == 'WATCH_TRIGGERED' for e in progressed.history) == 1
    dismissed = centre.dismiss(progressed.notification_identity, progressed.integrity_sha256)
    final, = centre.synchronize(watches(triggered), service.snapshot(),
        current_run_identity=RUN, websocket_state='CONNECTED').records
    assert final == dismissed
    assert triggered.state.value == 'TRIGGERED'  # No owner mutation.


def test_dismissal_survives_replay_but_new_assessment_can_notify(tmp_path):
    centre = _centre(tmp_path, [NOW + timedelta(days=10)])
    service = ux10(tmp_path/'ux10')
    service.observe_promotions((promotion(4), promotion(5, 1)))
    run = promotion(4).value['source']['native_run_identity']
    first, = centre.synchronize(NotificationWorkspaceSnapshot(()), service.snapshot(),
        current_run_identity=run, websocket_state='IDLE').records
    centre.dismiss(first.notification_identity, first.integrity_sha256)
    restored = ux10(tmp_path/'ux10')
    restored.observe_promotions((promotion(4), promotion(5, 1)))
    assert centre.synchronize(NotificationWorkspaceSnapshot(()), restored.snapshot(),
        current_run_identity=run, websocket_state='IDLE').visible == ()
    restored.observe_promotions((promotion(4, 2, 'b'), promotion(5, 3, 'b')))
    visible, = centre.synchronize(NotificationWorkspaceSnapshot(()), restored.snapshot(),
        current_run_identity=run, websocket_state='IDLE').visible
    assert visible.notification_identity != first.notification_identity
    assert centre.record(first.notification_identity).dismissed


@contextmanager
def browser(tmp_path):
    service = ux10(tmp_path/'ux10')
    centre = _centre(tmp_path, [NOW + timedelta(days=10)])
    app = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    server = create_browser_server(app, port=0, ux10_notifications=service,
        notification_centre=centre,
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path/'review')))
    # Each test explicitly invokes the owned pulse; GET timing is independent.
    server.service_actions = lambda: None
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield server, service, centre
    finally:
        server.shutdown(); server.server_close(); thread.join(3)


def inventory(path):
    return {str(p.relative_to(path)): sha256(p.read_bytes()).hexdigest()
        for p in path.rglob('*') if p.is_file()}


def test_owned_pulse_updates_centre_and_repeated_page_status_gets_never_write(tmp_path, monkeypatch):
    with browser(tmp_path) as (server, service, centre):
        service.observe_progression_watch(_triggered('CANBK'))
        assert centre.snapshot(product='SWING').records == ()
        server._service_actions_admitted()
        assert len(centre.snapshot(product='SWING').records) == 1
        before = inventory(tmp_path)
        def forbidden(*args, **kwargs):
            raise AssertionError('GET tried to synchronize or persist')
        monkeypatch.setattr(centre, 'synchronize', forbidden)
        monkeypatch.setattr(centre._store, 'retain', forbidden)
        for route in ['/notifications/swing', '/notifications', '/notifications/swing?state=EXPIRED&search=CANBK',
                      '/notifications/status', '/notifications/intraday', '/notifications/status?product=INTRADAY'] * 2:
            assert _request(server, 'GET', route)[0] == 200
        assert inventory(tmp_path) == before
        payload = json.loads(_request(server, 'GET', '/notifications/status')[2])
        current = server.swing_notification_status()
        assert payload['revision'] == notification_revision(current, server.swing_notification_indicators(current))
        assert payload['count'] == len(current.visible)


def test_historical_evidence_does_not_substitute_current_run_and_missing_is_explicit(tmp_path, monkeypatch):
    with browser(tmp_path) as (server, service, centre):
        service.observe_promotions((promotion(4), promotion(5, 1)))
        event, = service.snapshot().records
        old_run = event.run_identity
        monkeypatch.setattr(server.application, 'current_run_control_authority', lambda: (SimpleNamespace(run_identity=old_run), None))
        path = '/notifications/swing/evidence/UX10_EVENT/' + event.notification_id
        current = _request(server, 'GET', path)[2]
        assert 'CURRENT RUN' in current and event.source_event_identity in current and old_run in current
        new_run = 'SWING-RUN-' + '9'*32
        monkeypatch.setattr(server.application, 'current_run_control_authority', lambda: (SimpleNamespace(run_identity=new_run), None))
        historical = _request(server, 'GET', path)[2]
        assert 'HISTORICAL RUN' in historical and old_run in historical
        assert new_run not in historical
        assert 'PRESENTATION HISTORY' not in historical  # Distinct evidence destination.
        missing = _request(server, 'GET', '/notifications/swing/evidence/UX10_EVENT/' + 'f'*64)[2]
        assert 'UPSTREAM EVIDENCE UNAVAILABLE' in missing and new_run not in missing


def test_swing_cards_show_exact_owner_indicator_and_separate_history(tmp_path, monkeypatch):
    with browser(tmp_path) as (server, service, centre):
        triggered = _triggered('CANBK')
        active = activate_watch(triggered.requirement, activated_at=triggered.activated_at)
        server.progression_watches._watches[active.watch_id] = active
        server._service_actions_admitted()
        monkeypatch.setattr(server.progression_watches, 'notification_monitoring_evidence',
            lambda identity: {'state': 'ACTIVE', 'registered': True, 'connection': 'CONNECTED'}
                if identity == active.watch_id else None)
        html = _request(server, 'GET', '/notifications/swing')[2]
        assert 'MONITORING · UNAVAILABLE' in html
        assert 'PRESENTATION HISTORY' in html and 'UPSTREAM EVIDENCE' in html
        assert '/notifications/watch/delete' not in html
        status = json.loads(_request(server, 'GET', '/notifications/status')[2])
        assert status['revision'] in html


def test_legacy_fallback_only_admitted_pulse_and_never_modern_owner(tmp_path, monkeypatch):
    calls = []
    original = __import__('kronos.application.notification_centre', fromlist=['SponsorNotificationCentre']).SponsorNotificationCentre.synchronize_wo09
    def capture(self, *args, **kwargs):
        calls.append('sync')
        return original(self, *args, **kwargs)
    monkeypatch.setattr('kronos.application.notification_centre.SponsorNotificationCentre.synchronize_wo09', capture)
    with browser(tmp_path) as (server, service, centre):
        assert calls == []  # Constructor absence is not legacy operating mode.
        server.intraday_wo09_notification_sources = lambda: (calls.append('source') or ())
        server.sponsor_notification_snapshot()
        _request(server, 'GET', '/notifications/status')
        assert calls == []
        # Invoke actual admission wrapper rather than the test's disabled pulse.
        from kronos.browser.server import KronosBrowserServer
        KronosBrowserServer.service_actions(server)
        assert calls == ['source', 'sync']
        server.intraday_notifications = SimpleNamespace()
        KronosBrowserServer.service_actions(server)
        assert calls == ['source', 'sync']
        del server.intraday_notifications
        monkeypatch.setattr(server.maintenance_admission, 'admit', lambda *_args: None)
        KronosBrowserServer.service_actions(server)
        assert calls == ['source', 'sync']


def test_legacy_fallback_failure_is_separate_and_does_not_block_swing(tmp_path):
    with browser(tmp_path) as (server, service, centre):
        def failed_source():
            raise ValueError('controlled legacy failure')
        server.intraday_wo09_notification_sources = failed_source
        service.observe_progression_watch(_triggered('CANBK'))
        server._service_actions_admitted()
        assert server._legacy_notification_failure == 'LEGACY_WO09_NOTIFICATION_SOURCE_UNAVAILABLE'
        assert server._swing_notification_failure is None
        assert len(server.swing_notification_status().records) == 1
        server._service_actions_admitted()
        assert _request(server, 'GET', '/notifications/swing')[0] == 200


def test_uncertain_delivery_remains_visible_on_swing_watch_card(tmp_path):
    from tests.unit.application.test_swing_ux10 import Telegram
    from kronos.integrations.telegram import TelegramDeliveryResult, TelegramDeliveryState
    with browser(tmp_path) as (server, service, centre):
        service._telegram = Telegram((TelegramDeliveryResult(TelegramDeliveryState.FAILED_RETRYABLE,
            'TELEGRAM_TRANSPORT_UNAVAILABLE'),))
        triggered = _triggered('CANBK')
        server.progression_watches._watches[triggered.watch_id] = triggered
        service.observe_progression_watch(triggered)
        server._service_actions_admitted()
        html = _request(server, 'GET', '/notifications/swing')[2]
        assert 'DELIVERY_UNCERTAIN' in html
        assert len(server.swing_notification_status().records) == 1


def test_legacy_delete_hides_its_card_without_replaying_ux10_copy(tmp_path):
    with browser(tmp_path) as (server, service, centre):
        triggered = _triggered('CANBK')
        server.progression_watches._watches[triggered.watch_id] = triggered
        service.observe_progression_watch(triggered)
        server._service_actions_admitted()
        assert len(server.swing_notification_status().visible) == 1
        body = urlencode({'watch_id': triggered.watch_id})
        authority = f'127.0.0.1:{server.server_port}'
        headers = {'Host': authority, 'Origin': 'http://'+authority,
            'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': str(len(body))}
        assert _request(server, 'POST', '/notifications/watch/delete', headers=headers, body=body)[0] == 303
        server._service_actions_admitted()
        assert server.swing_notification_status().visible == ()
        assert len(service.snapshot().records) == 1  # Retained source event survives.
        assert server.progression_watches.snapshot().watches[0].workspace_hidden
