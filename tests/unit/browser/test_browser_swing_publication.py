from unittest.mock import Mock
from threading import Event

from tests.unit.browser.test_browser_server import _running_server, _request
from tests.unit.swing.test_run_publication import checkpoint, scenario


def test_wo07_committed_successor_with_old_review_has_pure_current_gets(checkpoint, tmp_path, monkeypatch):
    from dataclasses import replace
    from datetime import timedelta
    from threading import Thread
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.browser.server import create_browser_server
    from kronos.swing.v1.native_review import build_native_review_requirements
    from tests.unit.application.test_swing_opportunities import _Provider
    from tests.unit.browser.test_swing_visual_v3_live import _live
    from tests.unit.application.test_swing_run_publication import _guard_inventory
    from tests.unit.swing.test_run_publication import prepared

    co, old_facts, bindings, _ = checkpoint
    historical, _, live = _live(tmp_path / 'retained-review')
    old = historical.snapshot()
    # Supply genuinely newer 4H/1H facts; WO-04 correctly refuses uncertain
    # reuse of the adopted checkpoint's consumed 4H boundary.
    gold = old_facts.instrument('GOLDM')
    gold = replace(gold, timeframes=tuple(replace(fact,
        source_timestamp=fact.source_timestamp + timedelta(hours=4),
        observation_boundary=fact.observation_boundary + timedelta(hours=4))
        if fact.timeframe.value in {'4H', '1H'} else fact for fact in gold.timeframes))
    newer = replace(old_facts, instruments=tuple(gold if item.canonical_instrument == 'GOLDM' else item
                                               for item in old_facts.instruments))
    token, values = prepared(co, newer, bindings, 4)
    co.publish(token, co.prepare(token, **values), values['mtf'].observed_at)
    app = SwingOpportunitiesApplication(_Provider, run_publication=co,
        mtf_fact_evidence_store=co.mtf_store, native_discovery_evidence_store=co.native_store,
        relative_context_evidence_store=co.relative_store)
    # Startup cannot replace the retained old Review; GET must not require it.
    monkeypatch.setattr(historical, 'restore', lambda *_: old)
    server = create_browser_server(app, port=0, native_review=historical, visual_v3_live=live)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def forbidden(*args, **kwargs):
            raise AssertionError('Observational route invoked a mutation owner')
        for owner, names in ((historical, ('prepare', 'refresh', 'restore')),
                (app, ('run_analysis', 'reconcile_committed_analysis', 'publication_mutation_guard')),
                (live.cycle, ('prepare', 'complete', 'retain', 'restore_persisted')),
                (co, ('recover', 'adopt', 'publish')),
                (co.mtf_store, ('latest',)), (co.native_store, ('latest',))):
            for name in names:
                monkeypatch.setattr(owner, name, forbidden)
        expected = build_native_review_requirements(values['native'], values['mtf'])
        assert expected and old.native_run_identity != values['native'].run_identity
        before = _guard_inventory(tmp_path)
        revisions = []
        for _ in range(3):
            for route in ('/swing/v1-review', '/swing/opportunities', '/swing/v1/status', '/status', '/intraday'):
                status, _, body = _request(server, 'GET', route)
                assert status == 200
                if route in ('/swing/v1-review', '/swing/opportunities'):
                    assert values['native'].run_identity in body and 'BINDING CURRENT' in body
                    assert 'REVIEW_BINDING_UNAVAILABLE' not in body
            projection = server.native_intake.snapshot()
            assert {r['requirement_sha256'] for r in projection['rows']} == {r.requirement_sha256 for r in expected}
            assert all(r['expected'] and r['evidence'] == 'MISSING' for r in projection['rows'])
            revisions.append(server._derive_swing_projection_revision())
        assert len(set(revisions)) == 1
        assert historical.snapshot() == old
        assert _guard_inventory(tmp_path) == before
        assert server.native_intake.store.native_acceptance_history('MCX', values['native'].run_identity) == ()
        # A corrupt selected component must hide controls, not select older files.
        co._paths(values['native'].run_identity)['native'].write_bytes(b'SYNTHETIC INVALID EVIDENCE')
        broken = _guard_inventory(tmp_path)
        projection = server.native_intake.snapshot()
        assert projection['error'] == 'SWING_PUBLICATION_BUNDLE_INVALID'
        assert not projection['rows']
        status, _, body = _request(server, 'GET', '/swing/opportunities')
        assert status == 200 and 'Review workspace unavailable' in body
        assert 'href="/swing/v1-review">Open Native Review' not in body
        assert _guard_inventory(tmp_path) == broken
    finally:
        server.shutdown(); server.server_close(); thread.join(5)
        assert not thread.is_alive()


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
