"""LOCAL-02 genuine Browser dispatch/rendering against synthetic isolated owners."""
from contextlib import contextmanager
from copy import deepcopy
from threading import Thread
from urllib.parse import urlencode

import pytest

from kronos.application.swing_research_control import SwingResearchControl
from kronos.application.swing_research_inbox import SwingResearchInbox
from kronos.application.swing_research_integration import SwingResearchEventCapture
from kronos.browser.server import create_browser_server
from kronos.browser import views
from tests.unit.application.test_nse_local_analysis_workflow import (
    _rig, _refresh, _originals, _inventory, _projection,
)
from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_browser_chart_analyst_credentials import _origin_headers
from tests.unit.swing.v1.test_nse_local_analysis import _case


def _server(rig):
    rig.application.clear_local_analysis(rig.owner)
    rig.intake.clear_local_analysis(rig.owner)
    rig.owner.close()
    capture = SwingResearchEventCapture(rig.research, require_commissioning=True,
        inbox=SwingResearchInbox(rig.root / 'capture-inbox'))
    control = SwingResearchControl(application=rig.application, intake=rig.intake,
        research=rig.research, capture=capture, calendar=None)
    server = create_browser_server(rig.application, port=0,
        native_review=rig.intake.native_review, visual_v3_live=rig.intake.live,
        swing_research_control=control)
    rig.owner = server.local_analysis
    rig.intake = server.native_intake
    return server


@contextmanager
def _serving(rig):
    server = _server(rig)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown(); thread.join(10); server.server_close()
        assert not thread.is_alive()


def _fields(rig):
    return dict(action='REFRESH_LOCAL_ANALYSIS', run_identity=rig.state['native'].run_identity,
                publication_sha256=rig.state['manifest'],
                requirement_id=rig.requirement.requirement_sha256)


def _post(server, rig, *, body=None, headers=None, path='/swing/v1/native-review-refresh'):
    return _request(server, 'POST', path,
        headers=headers or _origin_headers(server, **{'Content-Type':'application/x-www-form-urlencoded'}),
        body=urlencode(_fields(rig)) if body is None else body)


def _prepared_projection(rig):
    assert rig.intake.prepare_page_state()
    with rig.intake.page_response() as response:
        return rig.intake.snapshot(_response=response)


def test_real_retained_only_manual_action_is_bound_counted_and_cleans_up(tmp_path, monkeypatch):
    rig = _rig(tmp_path)
    with _serving(rig) as server:
        def forbidden(*a, **k): pytest.fail('Local refresh invoked acquiring/visual workflow')
        monkeypatch.setattr(rig.application, 'run_analysis', forbidden)
        monkeypatch.setattr(rig.application, 'authenticated_read_only_capability', forbidden)
        monkeypatch.setattr(server.native_review, 'refresh', forbidden)
        monkeypatch.setattr(server.swing_research_control, 'submit_update', forbidden)
        refresh = rig.owner.refresh
        counted = []
        def observed(**kwargs):
            counted.append(server.maintenance_admission.snapshot()['owners'])
            return refresh(**kwargs)
        monkeypatch.setattr(rig.owner, 'refresh', observed)
        status, headers, _ = _post(server, rig)
        assert status == 303 and headers['Location'] == '/swing/v1-review'
        assert len(_originals(rig)) == 1
        assert counted and counted[0].get('BROWSER_POST') == 1
        assert not server.maintenance_admission.snapshot()['owners'].get('BROWSER_POST')
        assert not server.native_review.snapshot().analysis_outcomes


@pytest.mark.parametrize('bad', ['unknown_action','duplicate','extra','blank','malformed_run','bad_sha','query','json'])
def test_local_manual_discriminator_rejects_malformed_requests_before_owner(tmp_path, monkeypatch, bad):
    rig = _rig(tmp_path)
    with _serving(rig) as server:
        fields = _fields(rig)
        headers = _origin_headers(server, **{'Content-Type':'application/x-www-form-urlencoded'})
        path = '/swing/v1/native-review-refresh'
        if bad == 'unknown_action': fields['action'] = 'ACQUIRE_AND_ANALYZE'
        elif bad == 'extra': fields['provider'] = 'KITE'
        elif bad == 'blank': fields['requirement_id'] = ''
        elif bad == 'malformed_run': fields['run_identity'] = '../run'
        elif bad == 'bad_sha': fields['publication_sha256'] = 'not-a-sha'
        elif bad == 'query': path += '?action=REFRESH_LOCAL_ANALYSIS'
        elif bad == 'json': headers['Content-Type'] = 'application/json'
        body = urlencode(fields)
        if bad == 'duplicate': body += '&action=REFRESH_LOCAL_ANALYSIS'
        monkeypatch.setattr(rig.owner, 'refresh', lambda **k: pytest.fail('Malformed request reached owner'))
        monkeypatch.setattr(server.native_review, 'refresh', lambda *a: pytest.fail('Malformed local fell through'))
        before = _inventory(rig.research.store.root)
        status, _, _ = _post(server, rig, body=body, headers=headers, path=path)
        assert status == 400
        assert _inventory(rig.research.store.root) == before
        assert not server.maintenance_admission.snapshot()['owners'].get('BROWSER_POST')


@pytest.mark.parametrize('failure', ['cross_origin','stale','maintenance'])
def test_manual_action_preserves_existing_origin_admission_and_source_guards(tmp_path, failure):
    rig = _rig(tmp_path)
    with _serving(rig) as server:
        fields = _fields(rig)
        headers = _origin_headers(server, **{'Content-Type':'application/x-www-form-urlencoded'})
        generation = None
        if failure == 'cross_origin': headers['Origin'] = 'https://invalid.example'
        elif failure == 'stale': fields['publication_sha256'] = 'b' * 64
        else:
            generation = 'c' * 64
            assert server.maintenance_admission.claim(generation)
        try:
            status, _, _ = _post(server, rig, body=urlencode(fields), headers=headers)
            assert status in {403, 409, 503}
            assert not _originals(rig)
            assert not server.maintenance_admission.snapshot()['owners'].get('BROWSER_POST')
        finally:
            if generation:
                server.maintenance_admission.draining(generation)
                server.maintenance_admission.finalizer(generation).release()
                server.maintenance_admission.ready(generation)


def test_default_empty_refresh_review_remains_its_existing_operation(tmp_path, monkeypatch):
    rig = _rig(tmp_path)
    with _serving(rig) as server:
        calls = []
        monkeypatch.setattr(server.native_review, 'refresh', lambda run, facts: calls.append((run, facts)))
        monkeypatch.setattr(rig.owner, 'refresh', lambda **k: pytest.fail('Default Review triggered local evaluation'))
        status, _, _ = _post(server, rig, body='')
        assert status == 303 and len(calls) == 1
        assert not _originals(rig)


@pytest.mark.parametrize('path', ['/swing/opportunities','/swing/v1-review'])
def test_prepared_gets_are_read_only_without_recomputation_history_scan_or_api(tmp_path, monkeypatch, path):
    from kronos.application import swing_local_analysis as local_module
    rig = _rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        before = _inventory(rig.research.store.root)
        def forbidden(*a, **k): pytest.fail('GET acquired, evaluated, scanned or wrote')
        monkeypatch.setattr(local_module, 'analyze_local', forbidden)
        monkeypatch.setattr(local_module, 'build_local_input', forbidden)
        monkeypatch.setattr(rig.research.store, 'records', forbidden)
        monkeypatch.setattr(rig.research.store, 'retain', forbidden)
        monkeypatch.setattr(rig.application, 'authenticated_read_only_capability', forbidden)
        for _ in range(2):
            status, _, body = _request(server, 'GET', path)
            assert status == 200
            assert 'Independent local analysis' in body
            assert 'KRONOS-NSE-LOCAL-RESEARCH-1.0' in body
            assert 'Immutable original identity and timestamps' in body
            assert 'No independent visual confirmation' in body
        assert _inventory(rig.research.store.root) == before


@pytest.mark.parametrize('path', ['/swing/opportunities','/swing/v1-review'])
@pytest.mark.parametrize('boundary', ['before_get','during_render'])
def test_new_admission_without_publication_change_withholds_prepared_local_recommendation(tmp_path, monkeypatch, path, boundary):
    from kronos.browser import server as server_module
    rig = _rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        original, = _originals(rig)
        before = _inventory(rig.research.store.root)
        def admit():
            rig.state['generation'] += 1
            rig.state['attempt_state'] = 'RUNNING'
        if boundary == 'before_get':
            admit()
        else:
            name = 'render_opportunities' if path == '/swing/opportunities' else 'render_v1_review'
            render = getattr(server_module, name)
            def raced(*args, **kwargs):
                result = render(*args, **kwargs)
                admit()
                return result
            monkeypatch.setattr(server_module, name, raced)
        status, _, body = _request(server, 'GET', path)
        assert status == 409
        assert body == 'Swing page unavailable. Reason: REVIEW_BINDING_STALE'
        assert 'Immutable original identity and timestamps' not in body
        assert '<h4>SUPPORT' not in body
        assert _originals(rig) == (original,)
        assert _inventory(rig.research.store.root) == before


@pytest.mark.parametrize('case', ['aligned','reject','mixed','missing'])
def test_existing_opportunities_and_review_show_actual_local_result_and_preserve_visual_authority(tmp_path, case):
    kwargs = {'aligned':{}, 'reject':{'directions':('SHORT',)*4},
        'mixed':{'directions':('SHORT','SHORT','LONG','LONG')},
        'missing':{'missing':('ma','history','volume'),'no_pivots':True,'no_atr':True}}[case]
    rig = _rig(tmp_path, arguments=_case(**kwargs))
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        for path in ('/swing/opportunities','/swing/v1-review'):
            status, _, body = _request(server, 'GET', path)
            assert status == 200
            for expected in ('Independent local analysis','NSE numerical technical findings',
                'Native direction','Four-timeframe analysis and missing evidence',
                'LONG and SHORT evidence','Conditional scenarios',
                'Refresh Local Analysis', 'retained evidence only', 'Q3 / Q5 / Q10',
                'No independent visual confirmation', 'K4/V2'):
                assert expected in body
            assert 'OpenAI' not in body.split('Independent local analysis',1)[1].split('</section>',1)[0]
            for frame in ('1W','1D','4H','1H'):
                assert '<strong>' + frame + ' · ' in body
            assert '<form method="post" action="/swing/v1/native-review-refresh">' in body
            assert 'action="/swing/research/update"' not in body


def test_browser_close_releases_local_owner_registration_without_research_writes(tmp_path):
    rig = _rig(tmp_path)
    server = _server(rig)
    before = _inventory(rig.research.store.root)
    server.server_close()
    assert rig.owner.status()['state'] == 'CLOSED'
    assert rig.application.local_analysis_workflow() is None
    assert _inventory(rig.research.store.root) == before


@pytest.mark.parametrize('path', ['/swing/opportunities','/swing/v1-review'])
def test_failed_local_capture_keeps_native_page_available_and_does_not_retry(tmp_path, monkeypatch, path):
    from kronos.application import swing_local_analysis as local_module
    rig = _rig(tmp_path)
    with _serving(rig) as server:
        attempts = []
        analyze = local_module.analyze_local
        def observed(*args, **kwargs):
            attempts.append(True)
            return analyze(*args, **kwargs)
        monkeypatch.setattr(local_module, 'analyze_local', observed)
        retain = rig.research.store.retain
        def failed(value):
            if value.schema == 'SWING_WO12_LOCAL_ANALYSIS_ORIGINAL_V1':
                raise OSError('synthetic local capture failure')
            return retain(value)
        monkeypatch.setattr(rig.research.store, 'retain', failed)
        assert _post(server, rig)[0] == 409
        assert not _originals(rig) and len(attempts) == 1
        status, _, body = _request(server, 'GET', path)
        assert status == 200
        assert rig.requirement.canonical_instrument in body
        assert 'Independent local analysis' in body
        assert 'No current local recommendation is established' in body
        assert '<h4>SUPPORT' not in body and len(attempts) == 1
        assert not server.maintenance_admission.snapshot()['owners'].get('BROWSER_POST')
