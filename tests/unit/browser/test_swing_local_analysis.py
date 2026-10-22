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


@pytest.mark.parametrize('path', ['/swing/opportunities','/swing/v1-review','/swing/nse-review'])
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
            if path == '/swing/opportunities':
                assert 'Independent Local' in body and 'NSE Local completed' in body
                assert 'VIEW NSE REVIEW' in body
                assert 'Immutable original identity and timestamps' not in body
                assert 'Conditional scenarios' not in body
            else:
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


_ADMISSION_WARNING = ('New analysis in progress. Previous Local opinion is '
    'unavailable until current evidence is established.')


def _admission_rig(tmp_path):
    """Canonical control shape; synthetic evidence, never production authority."""
    rig = _rig(tmp_path)
    bundle = rig.application.opportunities_bundle_projection
    def control():
        running = rig.state['attempt_state'] == 'RUNNING'
        value = dict(schema_version='KRONOS-SWING-RUN-PUBLICATION-V1',
            admission_generation=rig.state['generation'],
            current_manifest={'sha256':rig.state['manifest']}, latest_attempt=dict(
                run_id=rig.state.get('attempt_run', rig.state['native'].run_identity),
                state=rig.state['attempt_state'],
                predecessor_manifest={'sha256':rig.state['manifest']} if running else None,
                accepted_at=rig.state['facts'].observed_at.isoformat(),
                completed_at=None if running else rig.state['facts'].observed_at.isoformat(),
                failure_reason=None))
        for key, value_override in rig.state.get('control_overrides', {}).items():
            if key == 'latest_attempt':value[key].update(value_override)
            else:value[key] = value_override
        return value
    def current_bundle():
        snapshot, native, continuity, status = bundle()
        return snapshot, native, continuity, {**status, 'control':control()}
    rig.application.opportunities_bundle_projection = current_bundle
    rig.application.current_run_control_authority = lambda: (rig.state['native'], control())
    return rig


def _admit_successor(rig):
    rig.state.update(generation=rig.state['generation'] + 1, attempt_state='RUNNING',
                     attempt_run='SWING-RUN-' + 'B' * 32)


@pytest.mark.parametrize('boundary', ['before_get', 'during_page_preparation', 'during_render'])
def test_proven_successor_admission_keeps_native_only_opportunities_available(tmp_path, monkeypatch, boundary):
    from kronos.browser import server as server_module
    from kronos.application import swing_local_analysis as local_module
    rig = _admission_rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        original, = _originals(rig)
        before = _inventory(rig.research.store.root)
        intake_before = _inventory(rig.intake.store.root)
        render = server_module.render_opportunities
        calls = []
        def rendered(*args, **kwargs):
            body = render(*args, **kwargs)
            calls.append(kwargs)
            if boundary == 'during_render' and len(calls) == 1:_admit_successor(rig)
            return body
        monkeypatch.setattr(server_module, 'render_opportunities', rendered)
        if boundary == 'before_get':_admit_successor(rig)
        if boundary == 'during_page_preparation':
            recheck = rig.intake.recheck_response
            admitted = []
            def checked(prepared):
                recheck(prepared)
                if not admitted:
                    admitted.append(True)
                    _admit_successor(rig)
            monkeypatch.setattr(rig.intake, 'recheck_response', checked)
        def forbidden(*args, **kwargs):pytest.fail('Warning GET acquired, evaluated, scanned or wrote')
        monkeypatch.setattr(local_module, 'analyze_local', forbidden)
        monkeypatch.setattr(local_module, 'build_local_input', forbidden)
        monkeypatch.setattr(rig.research.store, 'records', forbidden)
        monkeypatch.setattr(rig.research.store, 'retain', forbidden)
        monkeypatch.setattr(rig.application, 'run_analysis', forbidden)
        monkeypatch.setattr(rig.application, 'authenticated_read_only_capability', forbidden)
        if boundary == 'before_get':
            monkeypatch.setattr(server, 'selected_opportunity_presentations', forbidden)
            monkeypatch.setattr(server, 'current_v2_promotions', forbidden)
        status, _, body = _request(server, 'GET', '/swing/opportunities')
        assert status == 200 and _ADMISSION_WARNING in body
        assert rig.requirement.canonical_instrument in body
        assert 'Analysis running' in body and 'Prior successful result retained' in body
        assert 'Review workspace unavailable' in body and 'BINDING UNAVAILABLE' in body
        assert original.identity not in body and 'Immutable original identity and timestamps' not in body
        assert '<h4>SUPPORT' not in body and 'BINDING CURRENT' not in body
        for action in ('Refresh Local Analysis', 'Open Native Review', 'Open Trade Window',
                       'Create Question Pack', 'Upload Answer'):
            assert action not in body
        assert calls[-1]['native_intake']['workspace'] is None
        assert calls[-1]['native_intake']['rows'] == ()
        assert not calls[-1].get('promotions_v2') and not calls[-1].get('trade_windows')
        assert _inventory(rig.research.store.root) == before
        assert _inventory(rig.intake.store.root) == intake_before
        # Existing Review behavior stays fail closed under this same admission.
        assert _request(server, 'GET', '/swing/v1-review')[0] == 409


@pytest.mark.parametrize('fence', ['current', 'component'])
def test_admission_does_not_bypass_changed_prepared_evidence_files(tmp_path, fence):
    rig = _admission_rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        original, = _originals(rig)
        before = _inventory(rig.research.store.root)
        _admit_successor(rig)
        page = rig.intake._page_publication.page
        entries = getattr(page, fence + '_fence').entries
        assert entries, 'Fixture must exercise an actual captured evidence path'
        path, expected = entries[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'invalid changed evidence')
        # The injected component can itself be a commissioned research file.
        # Compare GET against the deliberately faulted fixture, not its pre-fault bytes.
        faulted = _inventory(rig.research.store.root)
        original_files = {key:value for key, value in before.items() if original.identity in key}
        assert len(original_files) == 1
        assert original_files == {key:value for key, value in faulted.items() if original.identity in key}
        status, _, body = _request(server, 'GET', '/swing/opportunities')
        assert _ADMISSION_WARNING not in body
        assert original.identity not in body and 'BINDING CURRENT' not in body
        assert 'unavailable' in body.lower()
        assert status == (409 if fence == 'current' else 200)
        assert _inventory(rig.research.store.root) == faulted


@pytest.mark.parametrize('blocker', ['writer', 'reconciliation'])
def test_admission_warning_never_overrides_prepared_page_ownership_blockers(tmp_path, blocker):
    from dataclasses import replace
    rig = _admission_rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        before = _inventory(rig.research.store.root)
        _admit_successor(rig)
        if blocker == 'writer':rig.intake._page_writers += 1
        else:rig.intake._page_publication = replace(rig.intake._page_publication, reconciliation_failure=True)
        try:
            status, _, body = _request(server, 'GET', '/swing/opportunities')
            assert status == 409 and _ADMISSION_WARNING not in body
            assert 'Immutable original identity and timestamps' not in body
            assert _inventory(rig.research.store.root) == before
        finally:
            if blocker == 'writer':rig.intake._page_writers -= 1


@pytest.mark.parametrize('invalid', ['same_run','predecessor','generation','schema',
    'accepted_at','completion','failure','publication','reconciliation','clock'])
def test_unproven_or_invalid_admission_does_not_acquire_warning_response(tmp_path, monkeypatch, invalid):
    rig = _admission_rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        original, = _originals(rig)
        before = _inventory(rig.research.store.root)
        _admit_successor(rig)
        overrides = {}
        if invalid == 'same_run':overrides['latest_attempt'] = {'run_id':rig.state['native'].run_identity}
        elif invalid == 'predecessor':overrides['latest_attempt'] = {'predecessor_manifest':{'sha256':'c'*64}}
        elif invalid == 'generation':overrides['admission_generation'] = True
        elif invalid == 'schema':overrides['schema_version'] = 'UNTRUSTED'
        elif invalid == 'accepted_at':overrides['latest_attempt'] = {'accepted_at':'invalid'}
        elif invalid == 'completion':overrides['latest_attempt'] = {'completed_at':rig.state['facts'].observed_at.isoformat()}
        elif invalid == 'failure':overrides['latest_attempt'] = {'failure_reason':'FAILED'}
        elif invalid == 'publication':rig.state['manifest'] = 'c'*64
        elif invalid == 'reconciliation':rig.state['unavailable'] = True
        else:monkeypatch.setattr(rig.owner, '_now', lambda: rig.state['facts'].observed_at)
        rig.state['control_overrides'] = overrides
        status, _, body = _request(server, 'GET', '/swing/opportunities')
        assert status == 409 and _ADMISSION_WARNING not in body
        assert original.identity not in body
        assert _inventory(rig.research.store.root) == before


@pytest.mark.parametrize('change', ['control','native','facts','continuity','epoch'])
def test_native_warning_body_is_discarded_when_authority_changes_during_fallback(tmp_path, monkeypatch, change):
    from kronos.browser import server as server_module
    from dataclasses import replace
    rig = _admission_rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        before = _inventory(rig.research.store.root)
        _admit_successor(rig)
        render = server_module.render_opportunities
        def raced(*args, **kwargs):
            body = render(*args, **kwargs)
            if change == 'control':rig.state['generation'] += 1
            elif change == 'native':rig.state['native'] = replace(rig.state['native'])
            elif change == 'facts':rig.state['facts'] = replace(rig.state['facts'])
            elif change == 'continuity':
                bundle = rig.application.opportunities_bundle_projection
                rig.application.opportunities_bundle_projection = lambda: (*bundle()[:2], object(), bundle()[3])
            else:rig.intake._page_epoch += 1
            return body
        monkeypatch.setattr(server_module, 'render_opportunities', raced)
        status, _, body = _request(server, 'GET', '/swing/opportunities')
        assert status == 409 and _ADMISSION_WARNING not in body
        assert 'Immutable original identity and timestamps' not in body
        assert _inventory(rig.research.store.root) == before


@pytest.mark.parametrize('case', ['aligned','reject','mixed','missing'])
def test_existing_opportunities_and_review_show_actual_local_result_and_preserve_visual_authority(tmp_path, case):
    kwargs = {'aligned':{}, 'reject':{'directions':('SHORT',)*4},
        'mixed':{'directions':('SHORT','SHORT','LONG','LONG')},
        'missing':{'missing':('ma','history','volume'),'no_pivots':True,'no_atr':True}}[case]
    rig = _rig(tmp_path, arguments=_case(**kwargs))
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        for path in ('/swing/nse-review','/swing/v1-review'):
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


def test_admission_during_explicit_page_preparation_keeps_warning_and_withholds_local(tmp_path, monkeypatch):
    rig = _admission_rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        before = _inventory(rig.research.store.root)
        prepare = rig.owner.prepare
        def admitted_prepare(**kwargs):
            result = prepare(**kwargs)
            _admit_successor(rig)
            return result
        monkeypatch.setattr(rig.owner, 'prepare', admitted_prepare)
        assert rig.intake.prepare_page_state()
        status, _, body = _request(server, 'GET', '/swing/opportunities')
        assert status == 200 and _ADMISSION_WARNING in body
        assert 'Immutable original identity and timestamps' not in body
        assert 'BINDING CURRENT' not in body
        assert _request(server, 'GET', '/swing/v1-review')[0] == 409
        assert _inventory(rig.research.store.root) == before
