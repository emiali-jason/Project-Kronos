"""Coordinated Swing presentation, using synthetic isolated retained owners only."""
from copy import deepcopy
from dataclasses import replace
import json
import os
import re
from pathlib import Path
from threading import Thread, Event
from urllib.parse import urlencode

import pytest

from kronos.browser import swing_research_views as ui
from kronos.browser import views
from kronos.common.request_diagnostics import ROUTES
from tests.unit.application.test_nse_local_analysis_workflow import _rig, _refresh, _inventory
from tests.unit.browser.test_swing_local_analysis import _serving, _post
from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_swing_review_intake_binding import native_intake, _current_twelve, _page_load_server


@pytest.fixture(scope='module')
def retained(tmp_path_factory):
    rig = _rig(tmp_path_factory.mktemp('ux-retained'))
    _refresh(rig)
    assert rig.intake.prepare_page_state()
    with rig.intake.page_response() as response:
        projection = deepcopy(rig.intake.snapshot(_response=response))
    return rig, projection


def clone_row(projection, name, disposition='SUPPORT', state='SUCCEEDED'):
    """Synthetic presentation envelope, not a newly computed original opinion."""
    source = next(r for r in projection['rows'] if r.get('eligible') and r['market'] == 'NSE')
    source_local = next(r for r in projection['local_analysis']['rows'] if r['instrument'] == source['instrument'])
    row, local = deepcopy(source), deepcopy(source_local)
    token = __import__('hashlib').sha256(name.encode()).hexdigest()
    row.update(instrument=name, requirement_sha256=token)
    local.update(instrument=name, requirement_id=token, state=state)
    if local['result'] is not None:
        local['result']['binding'].update(instrument=name, requirement_sha256=token)
        local['result']['thesis']['overall']['disposition'] = disposition
    if state != 'SUCCEEDED':
        local['result'] = None
    return row, local


def population(projection, states):
    p = deepcopy(projection)
    pairs = [clone_row(p, 'SYNTHETIC-' + str(i), d, s) for i, (d, s) in enumerate(states)]
    p['rows'] = tuple(r for r, _ in pairs)
    p['local_analysis']['rows'] = tuple(l for _, l in pairs)
    p['workspace'].update(nse=len(pairs), mcx=0, eligible=len(pairs), population=len(pairs), excluded=0)
    return p


def test_all_conclusions_have_distinct_completed_denominators(retained):
    _, projection = retained
    p = population(projection, [(d, 'SUCCEEDED') for d in ui._DISPOSITIONS]
        + [('SUPPORT', state) for state in ('NOT_RECORDED','UNAVAILABLE','FAILED','STALE')])
    before = deepcopy(p)
    c = ui.build_dashboard_counts(p)
    assert c['nse_eligible'] == 9 and c['mcx_eligible'] == 0
    assert c['completed'] == 5
    assert all(c[k] == 1 for k in ('support','reject','challenge','wait','insufficient',
                                  'not_recorded','unavailable','failed','stale'))
    assert c['completed'] == sum(c[k] for k in ('support','reject','challenge','wait','insufficient'))
    assert c['nse_eligible'] == c['completed'] + sum(c[k] for k in ('not_recorded','unavailable','failed','stale'))
    assert c['attempts'] is None and c['historical'] is None
    assert p == before


@pytest.mark.parametrize('state', ['STALE','UNAVAILABLE','FAILED','CLOSED'])
def test_global_owner_state_does_not_invent_per_candidate_failure_or_stale_counts(retained, state):
    _, original = retained
    p = deepcopy(original);p['local_analysis']['state'] = state;p['local_analysis']['rows'] = ()
    c = ui.build_dashboard_counts(p)
    assert c['nse_eligible'] > 0
    assert all(c[k] is None for k in ('completed','failed','stale','unavailable','support'))
    assert 'Unavailable' in ui.render_stage_counts(p)
    assert 'No current local recommendation' not in ui.render_stage_counts(p)


@pytest.mark.parametrize('kind', ['error','run','duplicate','assessment','direction','market'])
def test_inconsistent_population_has_no_numeric_current_totals(retained, kind):
    rig, original = retained
    p = deepcopy(original)
    r = next(row for row in p['rows'] if row.get('eligible'))
    if kind == 'error': p['error'] = 'REVIEW_BINDING_STALE'
    elif kind == 'run': p['workspace']['run_identity'] = 'SWING-RUN-' + 'F'*32
    elif kind == 'duplicate': p['rows'] += (deepcopy(r),)
    elif kind == 'assessment': r['assessment_sha256'] = 'f'*64
    elif kind == 'direction': r['direction'] = 'SHORT' if r['direction'] == 'LONG' else 'LONG'
    else: r['market'] = 'MCX'
    c = ui.build_dashboard_counts(p, rig.state['native'])
    assert c['nse_eligible'] is None and c['completed'] is None


@pytest.mark.parametrize('field', ['instrument','run_identity','publication_sha256','assessment_sha256',
                                   'requirement_sha256','direction'])
def test_local_binding_mismatch_never_displays_completed_opinion(retained, field):
    _, original = retained
    p = deepcopy(original)
    r = next(r for r in p['rows'] if r.get('eligible') and r['market'] == 'NSE')
    local = next(l for l in p['local_analysis']['rows'] if l['instrument'] == r['instrument'])
    local['result']['binding'][field] = 'WRONG'
    value = ui.local_view(p, r)
    assert value['result'] is None and value['state'] == 'UNAVAILABLE'
    assert ui.build_dashboard_counts(p)['completed'] == 0


@pytest.mark.parametrize('change', ['method','input','original','output','authority','contract','duplicate','missing'])
def test_local_output_identity_and_availability_fences(retained, change):
    _, original = retained;p = deepcopy(original)
    row = next(r for r in p['rows'] if r.get('eligible') and r['market']=='NSE')
    local = next(l for l in p['local_analysis']['rows'] if l['instrument']==row['instrument'])
    if change == 'method': local['result']['method_version'] = 'OTHER'
    elif change == 'input': local['input_sha256'] = 'f'*64
    elif change == 'original': local['original_identity'] = None
    elif change == 'output': local['result_sha256'] = None
    elif change == 'authority': local['result']['authority'] = 'TRADE'
    elif change == 'contract': local['result']['contract'] = 'OTHER'
    elif change == 'duplicate': p['local_analysis']['rows'] += (deepcopy(local),)
    else: local['result'] = None
    value = ui.local_view(p,row)
    assert value['result'] is None and value['state']=='UNAVAILABLE'
    page=ui.render_nse_review(retained[0].application.snapshot(),p)
    assert '<h4>SUPPORT' not in page


def test_empty_populations_are_known_empty_without_history_or_local_evaluation(retained):
    rig, original = retained;p = population(original, [])
    c = ui.build_dashboard_counts(p)
    assert c['completed']==0 and c['nse_eligible']==0 and c['mcx_eligible']==0
    page=ui.render_nse_review(rig.application.snapshot(),p)
    assert 'No NSE Review candidates' in page
    assert 'Historical Local total · Unavailable' in page


def test_nse_table_reuses_full_original_math_without_chart_prerequisite(retained):
    rig, p = retained
    before=deepcopy(p)
    page=ui.render_nse_review(rig.application.snapshot(),p,rig.state['native'])
    for text in ('NSE Local Review','Security search','Local conclusion','Research availability',
                 'LONG and SHORT evidence','Four-timeframe analysis','Conditional scenarios',
                 'Immutable original identity and timestamps','KRONOS-NSE-LOCAL-RESEARCH-1.0',
                 'Q3 / Q5 / Q10','UNKNOWN','1W','1D','4H','1H','Legacy NSE chart evidence',
                 'Short horizon','Medium horizon','Longer horizon','name="swing-nse-security"'):
        assert text in page
    for forbidden in ('PASTE TRADINGVIEW CHART','CREATE ALL NSE REVIEW PDF','UPLOAD ANSWER'):
        assert forbidden not in page
    assert p==before


def test_escaping_long_identifiers_and_exact_focus(retained):
    rig, original=retained;p=population(original,[('SUPPORT','SUCCEEDED')])
    r=p['rows'][0];r['instrument']='<script>"&'+ 'X'*180
    local=p['local_analysis']['rows'][0];local['instrument']=r['instrument'];local['result']['binding']['instrument']=r['instrument']
    page=ui.render_nse_review(rig.application.snapshot(),p,focus=r['requirement_sha256'])
    assert '<script>"&' not in page and '&lt;script&gt;' in page
    assert 'data-security-detail name="swing-nse-security"' in page
    assert ' open><summary>' in page and 'overflow-wrap:anywhere' in page
    assert ui.validate_focus(p,r['run_identity'],r['requirement_sha256'])==r['requirement_sha256']
    with pytest.raises(ValueError,match='REVIEW_BINDING_STALE'):
        ui.validate_focus(p,'SWING-RUN-'+'E'*32,r['requirement_sha256'])


@pytest.mark.parametrize('market', ['NSE','MCX'])
def test_market_scope_is_a_copy_and_never_rebinds_expected_actions(retained, market):
    _, original=retained;p=deepcopy(original)
    other=deepcopy(p['rows'][0]);other.update(market='MCX',instrument='CRUDEOIL',expected={'CRUDEOIL':{'exact':'unchanged'}})
    p['rows'] += (other,)
    before=deepcopy(p)
    view=ui.scope_review(p,market)
    assert all(r['market']==market for r in view['rows'])
    if market=='MCX':
        assert view['local_analysis'] is None and view['technical_summaries']==()
        assert view['rows'][0]['expected'] is other['expected']
    assert p==before


@pytest.mark.parametrize('path', ['/swing/nse-review','/swing/mcx-review','/swing/v1-review?market=NSE'])
def test_dedicated_gets_are_counted_read_only_and_cleanup(tmp_path,monkeypatch,path):
    from kronos.application import swing_local_analysis as local
    rig=_rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server,rig)[0]==303
        before=_inventory(rig.research.store.root)
        def forbidden(*a,**k):pytest.fail('GET called calculation/acquisition/history/write')
        for name in ('analyze_local','build_local_input'):monkeypatch.setattr(local,name,forbidden)
        for name in ('records','retain'):monkeypatch.setattr(rig.research.store,name,forbidden)
        monkeypatch.setattr(rig.application,'authenticated_read_only_capability',forbidden)
        monkeypatch.setattr(rig.application,'run_analysis',forbidden)
        completed=Event();finish=server._finish_request_owner
        def finished(sock):
            finish(sock);completed.set()
        monkeypatch.setattr(server,'_finish_request_owner',finished)
        status,headers,body=_request(server,'GET',path)
        assert status==200 and completed.wait(5)
        events=[e for e in server.request_diagnostics.snapshot()['events'] if e['id']==headers['X-Kronos-Request-ID']]
        assert {'RESPONSE','HANDLER_RETURNED','CLEANUP'} <= {e['event'] for e in events}
        assert all(e.get('route') in {path.split('?')[0],'UNKNOWN'} for e in events)
        assert 'NSE Review' in body and 'MCX Review' in body
        if path=='/swing/nse-review':assert 'Independent local analysis' in body and 'PASTE TRADINGVIEW CHART' not in body
        if path=='/swing/mcx-review':assert 'Independent local analysis' not in body and 'NSE numerical technical findings' not in body
        assert _inventory(rig.research.store.root)==before
        assert not server.maintenance_admission.snapshot()['owners'].get('BROWSER_GET')


@pytest.mark.parametrize('path', ['/swing/nse-review','/swing/mcx-review'])
@pytest.mark.parametrize('query',['?candidate='+'a'*64,'?run=bad&candidate='+'a'*64,'?market=NSE','?run=x&run=y&candidate=z','?unexpected=1'])
def test_new_routes_validate_query_before_owner_access(tmp_path,path,query):
    rig=_rig(tmp_path)
    with _serving(rig) as server:
        status,_,_=_request(server,'GET',path+query)
        assert status==400


@pytest.mark.parametrize('path', ['/swing/nse-review','/swing/mcx-review'])
def test_new_routes_reject_stale_focus_and_preserve_final_currentness(tmp_path,monkeypatch,path):
    rig=_rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server,rig)[0]==303
        status,_,_=_request(server,'GET',path+'?'+urlencode(dict(run='SWING-RUN-'+'E'*32,candidate='a'*64)))
        assert status==409
        if path=='/swing/nse-review':
            render=ui.render_nse_review
            def raced(*a,**k):
                body=render(*a,**k);rig.state['generation']+=1;rig.state['attempt_state']='RUNNING';return body
            monkeypatch.setattr(ui,'render_nse_review',raced)
            status,_,body=_request(server,'GET',path)
            assert status==409 and 'Immutable original identity' not in body


def test_new_routes_are_in_existing_diagnostic_allowlist():
    assert {'/swing/nse-review','/swing/mcx-review'} <= ROUTES


@pytest.mark.parametrize('native_intake',['NSE'],indirect=True)
def test_mixed_route_population_keeps_chart_contract_on_mcx_only(native_intake):
    state,names=_current_twelve(native_intake);server=_page_load_server(native_intake,state)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        for path,market in [('/swing/nse-review','NSE'),('/swing/mcx-review','MCX')]:
            status,_,body=_request(server,'GET',path);assert status==200
            if market=='NSE':
                assert 'CRUDEOIL · full research' not in body and 'PASTE TRADINGVIEW CHART' not in body
                assert all(n+' · full research' in body for n in names if n not in {'GOLDM','CRUDEOIL'})
            else:
                assert 'CREATE ALL MCX REVIEW PDF' in body and 'CREATE ALL NSE REVIEW PDF' not in body
                assert '>NSE REVIEW</h2>' not in body
                assert 'MCX SIX-PANEL COMPOSITE' in body and 'SUPPORTING COMEX' in body and 'SUPPORTING NYMEX' in body
                assert 'Independent local analysis' not in body and 'NSE numerical technical findings' not in body
                assert 'native-chart?' in body
    finally:
        server.shutdown();server.server_close();thread.join(10);assert not thread.is_alive()


def test_export_synthetic_previews_and_accounting(retained):
    target=os.environ.get('SWING_UX_PREVIEW_ROOT')
    if not target:return
    rig,p=retained;out=Path(target);out.mkdir(parents=True,exist_ok=True)
    def labelled(body):
        body = body.replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="connect-src &apos;none&apos;; form-action &apos;none&apos;">', 1)
        return re.sub(r'(<body\b[^>]*>)', lambda m:m.group(1)+'<aside style="position:sticky;top:0;z-index:9999;background:#fff2aa;color:#111;padding:8px">SYNTHETIC TEST FIXTURE — not live market evidence. Actions are not production operations.</aside>',body,count=1)
    p=population(p,[('SUPPORT','SUCCEEDED')]*4)
    rendered=labelled(ui.render_nse_review(rig.application.snapshot(),p))
    assert 'SYNTHETIC TEST FIXTURE' in rendered
    (out/'nse-review.html').write_text(rendered)
    c=ui.build_dashboard_counts(p);(out/'accounting.json').write_text(json.dumps(c,indent=2)+'\n')
    # Real Native/opportunity renderer from the retained synthetic owner.
    original=retained[1]
    (out/'opportunities.html').write_text(labelled(views.render_opportunities(rig.application.snapshot(),rig.state['native'],native_intake=original)))
    from tests.unit.browser.test_swing_opportunity_sponsor_simplification import fixture
    _,_,f=fixture(symbol='CRUDEOIL',market='MCX',complete=False,question=False,evidence='MISSING')
    row=f['rows'][0];row.update(market='MCX',requirement_sha256='a'*64,reference=('NYMEX Crude Oil',__import__('kronos.swing.v1.native_review',fromlist=['MCX_REFERENCE_MAPPINGS']).MCX_REFERENCE_MAPPINGS['CRUDEOIL'][1],'NYMEX:CL1!'),selected={'NATIVE_MCX':None,'SUPPORTING_REFERENCE':None},replaced=(),supported_result=None,downstream='NOT_RUN')
    f['workspace']=dict(state='CURRENT',run_identity=row['run_identity'],manifest='a'*64,analysis_time=__import__('datetime').datetime(2026,10,21,3,tzinfo=__import__('datetime').UTC),population=1,eligible=1,nse=0,mcx=1,excluded=0)
    (out/'mcx-review.html').write_text(labelled(views._page(title='Swing MCX Review · synthetic',subtitle='Existing chart workflow, no acquisition',snapshot=rig.application.snapshot(),active_nav='Swing',active_tab='MCX Review',body=views._receipt_native_review(f,market='MCX'))))


@pytest.mark.parametrize('native_intake',['GOLDM-LINEAGE','SILVERM-LINEAGE','COPPER-LINEAGE','CRUDEOIL-LINEAGE','NATURALGAS-LINEAGE'],indirect=True)
def test_mcx_view_discloses_exact_retained_contract_and_expiry_without_entry_authority(native_intake):
    workflow=native_intake
    facts=workflow.application.mtf_fact_snapshot()
    contracts=ui.mcx_contract_projection(facts,facts.run_identity)
    family=workflow.native_review.snapshot().requirements[0].canonical_instrument
    lineage=facts.instrument(family).mcx_request_lineage
    assert contracts[family]==dict(trading_symbol=lineage.trading_symbol,expiry=lineage.expiry)
    projection=workflow.snapshot();before=deepcopy(projection)
    html=views._receipt_native_review(projection,market='MCX',mcx_contracts=contracts)
    assert lineage.trading_symbol in html and lineage.expiry in html
    assert 'not a fresh Provider mapping, quote or entry-currentness certification' in html
    assert projection==before and 'Independent local analysis' not in html
    with pytest.raises(ValueError,match='SWING_REVIEW_CONTRACT_BINDING_INVALID'):
        ui.mcx_contract_projection(facts,'SWING-RUN-'+'E'*32)


def test_missing_mcx_lineage_is_explicit_not_a_family_substitution(retained):
    _,p=retained
    r=deepcopy(p['rows'][0]);r.update(market='MCX',instrument='CRUDEOIL',reference=('NYMEX Crude Oil',
        __import__('kronos.swing.v1.native_review',fromlist=['MCX_REFERENCE_MAPPINGS']).MCX_REFERENCE_MAPPINGS['CRUDEOIL'][1], 'NYMEX:CL1!'),selected={})
    view=dict(p,rows=(r,))
    html=views._receipt_native_review(view,market='MCX')
    assert 'Exact retained future / expiry · Unavailable' in html
    assert 'family label is not an exact futures contract' in html
