from unittest.mock import Mock
from threading import Event

from tests.unit.browser.test_browser_server import _running_server, _request


def test_14_get_and_status_do_not_call_mutation_owners(monkeypatch):
    server, thread = _running_server()
    try:
        denied=[]
        def reject(*args,**kwargs):
            denied.append(True)
            raise AssertionError('GET mutation owner invoked')
        for owner,name in ((server,'_synchronize_trade_window'),(server,'reconcile_progression'),
            (server.application,'run_analysis'),(server.application,'auto_activate_progression_watches'),
            (server.progression_watches,'synchronize'),(server.refresh_reminders,'synchronize'),
            (server.ux10_notifications,'observe_promotions'),
            (server.notification_centre,'synchronize'),
            (server.notification_centre,'synchronize_wo09'),
            (server.native_review,'_reconcile_journal_unlocked'),
            (server.application,'reconcile_committed_analysis')):
            monkeypatch.setattr(owner,name,reject)
        for _ in range(3):
            assert _request(server,'GET','/swing/opportunities')[0]==200
            assert _request(server,'GET','/status')[0]==200
            assert _request(server,'GET','/notifications/status?product=SWING')[0]==200
        assert not denied
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_10_browser_has_no_newer_native_override():
    import inspect
    from kronos.browser.server import KronosBrowserServer, _BrowserHandler
    assert '.latest()' not in inspect.getsource(KronosBrowserServer.__init__)
    assert '.latest()' not in inspect.getsource(_BrowserHandler._refresh_native_review)


def test_15_only_authorized_swing_mutation_reconciles(monkeypatch):
    server, thread = _running_server()
    try:
        from kronos.browser.server import _BrowserHandler
        original = _BrowserHandler._dispatch_post
        completed = Event()
        finish = server.finish_sponsor_work
        def finish_work():
            finish()
            completed.set()
        monkeypatch.setattr(server, 'finish_sponsor_work', finish_work)
        calls = []
        def dispatch(handler, path):
            if path == '/swing/review/controlled-mutation':
                handler._redirect('/swing/opportunities')
            else:
                original(handler, path)
        monkeypatch.setattr(_BrowserHandler, '_dispatch_post', dispatch)
        monkeypatch.setattr(server.application, 'reconcile_committed_analysis', lambda: calls.append(True))
        path = '/swing/review/controlled-mutation'
        origin = {'Origin':f'http://127.0.0.1:{server.server_port}'}
        assert _request(server,'POST',path,headers={'Origin':'http://foreign.invalid'})[0] == 403
        assert not calls
        status, headers, _ = _request(server,'POST',path,headers=origin)
        assert completed.wait(5), 'WO-05 controlled mutation did not finish Sponsor work'
        assert status == 303
        assert headers['Location'] == '/swing/opportunities'
        assert calls == [True]
        completed.clear()
        status, headers, _ = _request(server,'POST','/swing/reconcile',headers=origin)
        assert completed.wait(5), 'WO-05 explicit reconciliation did not finish Sponsor work'
        assert status == 303
        assert headers['Location'] == '/swing/opportunities'
        assert calls == [True,True]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
