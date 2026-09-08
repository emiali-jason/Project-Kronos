"""WO-06H production composition with isolated Provider doubles and local evidence."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from dataclasses import replace
from pathlib import Path
import json
import pytest

from tests.unit.application.test_intraday_discovery_operation import _configured_shared,_authenticate
from tests.unit.intraday.test_runtime_identity import _seed
from tests.unit.intraday.test_probables_v2_refresh_control import _payload
from tests.unit.intraday.test_live_shadow import service,seed_row,NOW
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.application.intraday_live_shadow import IntradayLiveShadowService
from kronos.browser.intraday_probables_v2_control import IntradayProbablesV2OperationalControl
from kronos.intraday.runtime_identity import LauncherConfiguration
from kronos.provider.contracts.market_data import HistoricalCandle,HistoricalInterval,QuoteSnapshot,OhlcValues
from kronos.intraday.live_shadow import SCHEMA,COHORT_A,COHORT_B,NE,ShadowError
from kronos.intraday.live_shadow_features import snapshot
from kronos.intraday.probables_v2_diagnostics import reconstruct_v2_execution,replay_v2_mapping
from kronos.intraday.operation_accounting import ProviderRequestCategory as Category
from kronos.intraday.probables_v2_persistence import _artifact_bytes
from kronos.intraday.live_shadow_persistence import ShadowStore

BOUNDARY=datetime(2026,8,24,9,30,tzinfo=ZoneInfo('Asia/Kolkata'))


def pipeline(root,*,narrow=True,active=True,direction='LONG',fault=None):
    shared,runtime,_,_=_configured_shared();_authenticate(shared)
    clock=[BOUNDARY];quotes=[];calls=[]
    def hist(req):
        calls.append(req)
        if req.interval is HistoricalInterval.DAY:
            return (HistoricalCandle(req.start,100.,104.,96.,100. if narrow else 103.,100),)
        step={HistoricalInterval.SIXTY_MINUTE:60,HistoricalInterval.FIFTEEN_MINUTE:15,HistoricalInterval.FIVE_MINUTE:5}[req.interval]
        cs=[];cursor=req.start;i=0
        while cursor<=req.end:
            sign=1 if direction=='LONG' else -1;op=100.+sign*i;close=op+sign*3.
            cs.append(HistoricalCandle(cursor,op,max(op,close)+1.,min(op,close)-1.,close,100))
            i+=1;cursor+=timedelta(minutes=step)
        return tuple(cs)
    runtime.capability.historical_candles=hist
    def quote(instrument):
        quotes.append(instrument)
        # A quote is before publication; a B quote is after production publication.
        assert c.probables_v2_application.snapshot().run is None if narrow else c.probables_v2_application.snapshot().run is not None
        if fault=='quote':raise RuntimeError('ISOLATED_SECRET_ERROR')
        return QuoteSnapshot(instrument,BOUNDARY,123.,100,OhlcValues(100.,125.,99.,100.))
    runtime.capability.quote=quote
    c=create_intraday_runtime(shared,evidence_root=root,clock=lambda:clock[0])
    sources=[];original=c.discovery_v2_operation._source_factory
    def factory(*args):
        value=original(*args);sources.append(value);return value
    c.discovery_v2_operation._source_factory=factory
    control=IntradayProbablesV2OperationalControl(c.discovery_v2_operation,c.probables_v2_application,
        c.refresh_v2_provenance_store,clock=lambda:clock[0],startup_evidence=_seed(startup_boundary_at=BOUNDARY),
        launcher_configuration=LauncherConfiguration(8947,False))
    s=c.discovery_v2_operation.live_shadow
    if active:
        accepted=control.shadow_document(dict(action='ACCEPT_RUNTIME',runtime=s._manifest.manifest_identity,
            schema=SCHEMA,revision='a'*40,request_identity='ISOLATED_ACCEPTANCE'))
        assert accepted['outcome']=='COMPLETE'
    if fault=='persist':
        retain=s.store.retain;failed=[]
        def broken(v,**kwargs):
            if v.kind=='observation' and not failed:
                failed.append(True);raise OSError('ISOLATED')
            return retain(v,**kwargs)
        s.store.retain=broken
    result=control.execute_document(_payload('WO06H-ISOLATED',boundary=BOUNDARY))
    assert result['outcome']=='SUCCESS'
    envelope=c.probables_v2_diagnostics_store.load_envelope(result['replay_envelope_identity'])
    return c,control,s,result,envelope,quotes,calls,sources,clock


@pytest.mark.parametrize('narrow',[True,False])
@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_full_composition_opening_cohorts_and_truthful_accounting(tmp_path,narrow,direction):
    c,control,s,result,e,quotes,calls,sources,clock=pipeline(tmp_path,narrow=narrow,direction=direction)
    run=c.probables_v2_application.snapshot().run;before=_artifact_bytes(run)
    obs=s.store.all('observation');counts=s.status()['counts']
    assert len(obs)==93 and counts['missing_rows']==counts['classification_failures']==counts['incomplete_operations']==0
    assert {o.body['cohort'] for o in obs}=={COHORT_A if narrow else COHORT_B}
    assert {o.body['direction'] for o in obs}=={direction}
    assert len(quotes)==93 and counts['assessment_available']==93
    assert run.diagnostics.total_probables==(93 if narrow else 0)
    categories=dict(c.discovery_v2_operation.last_result.accounting.request_categories)
    assert categories[Category.ASSESSMENT_OBSERVATION_REQUEST]==(93 if narrow else 0)
    assert categories[Category.COHORT_B_SHADOW_OBSERVATION_REQUEST]==(0 if narrow else 93)
    assert c.discovery_v2_operation.last_result.accounting.actual_provider_requests==sum(categories.values())
    assert c.probables_application.snapshot().run is None and c.discovery_operation.last_result is None
    for o in obs:
        v=o.body['features']['values']
        assert v['sma20_side']==v['sma50_side']==NE
        assert v['5M']['body_ratio'] is not None and v['15M']['body_ratio'] is not None
        assert o.body['phase']=='OPENING'
        assert v['vwap_side']==NE if o.body['subject'].startswith('NSE-INDEX-') else v['vwap_side'] in {'ABOVE','BELOW','AT'}
    for f in e.probables_v2_facts:
        assert not f.current_one_hour and len(f.current_five_minute)==3 and len(f.current_fifteen_minute)==1
    # Exact Browser replay and application replay retain every byte and do not quote.
    files={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    control.execute_document(_payload('WO06H-ISOLATED',boundary=BOUNDARY))
    mapping=replay_v2_mapping(e)
    s.capture_published(run,mapping.member_evidence,c.probables_v2_store.load_assessment_observations(run.run_identity),
        facts=e.probables_v2_facts,source=sources[0],operation=e.operation_identity,
        operation_start=BOUNDARY,newly_published=False)
    assert files=={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    assert len(quotes)==93 and _artifact_bytes(c.probables_v2_application.snapshot().run)==before


@pytest.mark.parametrize('narrow',[True,False])
def test_feature_inactivity_and_missing_quote_never_filter(tmp_path,narrow):
    c,_,s,_,_,quotes,*_=pipeline(tmp_path,narrow=narrow,fault='quote')
    assert len(s.store.all('observation'))==93 and len(quotes)==93
    assert s.status()['counts']['assessment_available']==0
    assert c.probables_v2_application.snapshot().run.diagnostics.total_probables==(93 if narrow else 0)
    assert 'SECRET' not in str(s.monthly_ledger('2026-08'))


def test_inactive_by_default_no_b_calls_or_shadow_files(tmp_path):
    c,control,s,_,e,quotes,*_=pipeline(tmp_path,narrow=False,active=False)
    assert not quotes and s.store.all('window')==() and s.store.all('operation')==()
    assert not control.status_document()['live_shadow']['enabled']
    assert c.probables_v2_application.snapshot().run.diagnostics.total_probables==0


def test_partial_failure_restores_expected_members_no_requote(tmp_path):
    c,_,s,result,e,quotes,calls,sources,_=pipeline(tmp_path,narrow=False,fault='persist')
    assert len(quotes)==93 and s.status()['counts']['missing_rows']==1
    producer={p:p.read_bytes() for p in tmp_path.rglob('*.json') if 'live-shadow-v1' not in p.parts}
    restored=IntradayLiveShadowService(store=ShadowStore(tmp_path),clock=lambda:BOUNDARY)
    assert not restored.status()['enabled'] and restored.status()['counts']['missing_rows']==1
    restored.bind_runtime(s._manifest);restored.accept_runtime(expected_revision='a'*40,request_identity='RESTORE')
    run=c.probables_v2_application.snapshot().run;m=replay_v2_mapping(e)
    restored.capture_published(run,m.member_evidence,None,facts=e.probables_v2_facts,source=sources[0],
        operation=e.operation_identity,operation_start=BOUNDARY,newly_published=False)
    assert len(quotes)==93 and len(restored.store.all('observation'))==93
    assert restored.status()['counts']['missing_rows']==0 and restored.status()['counts']['assessment_available']==92
    assert any(o.body['assessment']['reason']=='PRIOR_REQUEST_UNFINISHED_NO_REQUOTE' for o in restored.store.all('observation'))
    assert producer=={p:p.read_bytes() for p in tmp_path.rglob('*.json') if 'live-shadow-v1' not in p.parts}


def test_preexisting_historical_run_cannot_start_shadow_capture(tmp_path):
    c,_,s,_,e,quotes,_,sources,_=pipeline(tmp_path,narrow=False,active=False)
    s.accept_runtime(expected_revision='a'*40,request_identity='ACTIVATE_AFTER_RUN')
    run=c.probables_v2_application.snapshot().run;m=replay_v2_mapping(e)
    s.capture_published(run,m.member_evidence,None,facts=e.probables_v2_facts,source=sources[0],
        operation=e.operation_identity,operation_start=BOUNDARY,newly_published=False)
    assert not quotes and s.store.all('observation')==() and s.store.all('batch')==()
    assert s.store.all('receipt')[0].body['disposition']=='HISTORICAL_REPLAY_NO_CAPTURE'


def test_feature_exact_fact_binding_rejects_same_boundary_different_source(tmp_path):
    c,_,s,_,e,*_=pipeline(tmp_path)
    m=replay_v2_mapping(e).member_evidence[0]
    f=next(f for f in e.probables_v2_facts if f.canonical_subject_identity==m.canonical_subject_identity)
    normal,_=snapshot(f,m,{})
    assert normal['values']['5M']['body_ratio'] is not None
    other=next(x for x in e.probables_v2_facts if x.canonical_subject_identity!=m.canonical_subject_identity)
    bad,_=snapshot(other,m,{})
    assert 'FEATURE_BINDING_NOT_ESTABLISHED' in bad['unavailable']
    assert bad['values']['5M']['body_ratio'] is None


def test_unfinished_operation_remains_visible_after_restore(tmp_path):
    s,_,_=service(tmp_path);s.begin_operation('OP-CRASH',NOW)
    restored=IntradayLiveShadowService(store=ShadowStore(tmp_path),clock=lambda:NOW)
    assert restored.status()['counts']['incomplete_operations']==1
    assert restored.store.all('observation')==()


@pytest.mark.parametrize('mutation',['runtime','schema','revision','action','extra'])
def test_control_exact_acceptance_contract_rejects(tmp_path,mutation):
    from tests.unit.intraday.test_probables_v2_refresh_control import _control
    _,c,control,_,_=_control(tmp_path,authenticated=False)
    # No frozen manifest is enough to reject all proposed activation requests.
    p=dict(action='ACCEPT_RUNTIME',runtime='INVALID',schema=SCHEMA,revision='a'*40,request_identity='X')
    p[mutation]='INVALID'
    assert control.shadow_document(p)['outcome']=='REJECTED'
    assert c.discovery_v2_operation.live_shadow.store.all('window')==()


def test_explicit_post_route_is_product_owned_and_malformed_requests_inert(tmp_path):
    from tests.unit.intraday.test_probables_v2_refresh_control import _control
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    from kronos.browser.product_routes import BrowserPostRequest,BrowserGetRequest
    _,c,control,_,events=_control(tmp_path,authenticated=False)
    routes=IntradayBrowserRoutes(c.discovery_v2_application,probables_v2_control=control)
    path='/control/intraday-live-shadow/v1'
    assert routes.owns_post(path)
    assert routes.handle_get(BrowserGetRequest(path,{}),lambda:None) is None
    for body,content in [(b'{}','application/json'),(b'no','application/json'),(b'{}','text/plain'),(b'x'*4097,'application/json')]:
        response=routes.handle_post(BrowserPostRequest(path,{},content,body),lambda:None)
        assert response.status==400
    assert events==[0] and c.discovery_v2_operation.live_shadow.store.all('window')==()


def test_launcher_captures_shadow_implementation_imports_before_manifest_finish():
    import subprocess,sys,os
    root=Path(__file__).resolve().parents[3]
    script="from tools import kronos_browser as k; import json; print(json.dumps([x[0] for x in k._STARTUP_EVIDENCE.loaded_modules]))"
    names=json.loads(subprocess.check_output([sys.executable,'-B','-c',script],cwd=root,text=True,
        env=dict(os.environ,PYTHONPATH=str(root/'src')+':'+str(root),PYTHONDONTWRITEBYTECODE='1')))
    assert 'kronos.application.intraday_live_shadow' in names
    assert 'kronos.intraday.live_shadow_features' in names
    assert 'kronos.intraday.live_shadow_quote' in names


def test_wo05a_rejects_0929_requesting_0930_before_shadow_or_provider(tmp_path):
    from tests.unit.intraday.test_operation_accounting import _operation
    _,c,control,events=_operation(tmp_path,clock=lambda:BOUNDARY-timedelta(minutes=1))
    result=control.execute_document(_payload('FUTURE',boundary=BOUNDARY))
    assert result['outcome']=='REJECTED' and result['failure']=='OBSERVATION_BOUNDARY_FUTURE'
    assert events==[] and c.discovery_v2_operation.live_shadow.store.all('operation')==()


def test_month_cutoff_mid_batch_keeps_denominator_without_further_quotes(tmp_path,monkeypatch):
    import kronos.application.intraday_live_shadow as module
    original=module.capture;count=[]
    def cutoff(source,result,**kwargs):
        count.append(1)
        pair=original(source,result,**kwargs)
        # Clock change simulates the lawful month endpoint while a batch is in progress.
        owner=next(x for x in services if x._accepted is not None)
        owner.clock=lambda: __import__('datetime').datetime.fromisoformat(owner._window.body['end'])
        return pair
    services=[];old_init=module.IntradayLiveShadowService.__init__
    def init(self,**kwargs):old_init(self,**kwargs);services.append(self)
    monkeypatch.setattr(module.IntradayLiveShadowService,'__init__',init)
    monkeypatch.setattr(module,'capture',cutoff)
    _,_,s,_,_,quotes,*_=pipeline(tmp_path,narrow=False)
    assert len(quotes)==len(count)==1
    assert len(s.store.all('observation'))==93 and s.status()['counts']['missing_rows']==0
    assert not s.status()['enabled']
    assert sum(o.body['assessment']['reason']=='WINDOW_CLOSED_NO_QUOTE' for o in s.store.all('observation'))==92


def test_unexpected_shadow_callback_failure_cannot_change_published_admission(tmp_path,monkeypatch):
    def fail(self,*args,**kwargs):raise RuntimeError('ISOLATED_SECRET_ERROR')
    monkeypatch.setattr(IntradayLiveShadowService,'capture_published',fail)
    c,control,s,result,_,quotes,*_=pipeline(tmp_path,narrow=True)
    assert result['outcome']=='SUCCESS' and c.probables_v2_application.snapshot().run.diagnostics.total_probables==93
    assert len(quotes)==93 and s.store.all('observation')==()
    status=control.status_document()['live_shadow']
    assert status['publication_hook_failure']=='SHADOW_CAPTURE_INCOMPLETE'
    assert 'SECRET' not in str(status)
