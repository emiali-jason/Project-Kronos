"""IWO07 route/history assurance. Disposable fixtures; not live Analysis."""
from hashlib import sha256
from types import SimpleNamespace
from pathlib import Path
import json
import subprocess
import pytest
from kronos.browser.product_routes import BrowserGetRequest
from kronos.browser.intraday_wo08 import _analysis_history
from kronos.browser.intraday_machine_controls import CONTROLS_JS
from tests.unit.browser.test_iwo06c_observability import history_fixture, clone
from tests.unit.browser.test_intraday_wo08_browser import _routes
from tests.unit.browser.test_product_route_isolation import _snapshot


def inventory(root):
    return {str(p.relative_to(root)):sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def composed(tmp_path):
    runtime,control,record,accounting=history_fixture(tmp_path/'owner')
    runtime.discovery_v2_operation.accounting_store.retain(accounting)
    control._store.retain(record)
    document=dict(currentness='NOT_YET_ASSESSED',current_probables_run_identity=None,assessments=())
    routes=_routes(tmp_path/'routes',SimpleNamespace(status_document=lambda:document),probables_v2_control=control)
    return control,record,accounting,routes


def test_history_is_wired_through_real_intraday_route_and_get_is_inert(tmp_path):
    control,record,accounting,routes=composed(tmp_path)
    before=inventory(tmp_path)
    response=routes.handle_get(BrowserGetRequest('/intraday',{}),_snapshot)
    assert response.status.value==200
    assert '1m 22s' in response.body and '98 analysed' in response.body
    assert record.provenance_identity in response.body and accounting.accounting_identity in response.body
    assert inventory(tmp_path)==before
    assert control._store.latest()==record


@pytest.mark.parametrize('failure',['historical_provenance','linked_accounting'])
def test_history_transport_denies_corruption_without_repair_or_latest_invalidation(tmp_path,failure):
    control,record,accounting,routes=composed(tmp_path)
    if failure=='historical_provenance':
        from datetime import timedelta
        older=clone(record,request_identity='OLDER-HISTORY-ONLY',operation_accounting_identity=None,
            operation_completed_at=record.operation_completed_at-timedelta(seconds=1))
        control._store.retain(older)
        control._store._path(older.provenance_identity).write_bytes(b'corrupt')
    else:
        control.operation_service.accounting_store._path(accounting.accounting_identity).write_bytes(b'corrupt')
    before=inventory(tmp_path)
    response=routes.handle_get(BrowserGetRequest('/intraday',{}),_snapshot)
    assert response.status.value==503
    payload=json.loads(response.body)
    assert payload['failure_stage']=='READ_ONLY_PROJECTION' and payload['outcome']=='UNAVAILABLE'
    assert inventory(tmp_path)==before and control._store.latest()==record


def test_actual_filter_callback_only_changes_scoped_display():
    # Minimal DOM contract harness, not a visual/browser rehearsal. Execute the
    # complete candidate handler, including pairing, reset and combined controls.
    prelude = r"""
const assert=require('node:assert/strict');
const make=(price,score,secondary,security)=>({security,direction:'LONG',score,
 status:'Retained evidence',waiting:['Follow-through'],monitoring:'INACTIVE',price,secondary});
const records=[make('100','5',true,'Beta'),make('9.95','0',false,'Alpha'),make('UNAVAILABLE','UNAVAILABLE',false,'Conflict')];
const rows=records.map(data=>({dataset:{assessmentControls:JSON.stringify(data)},hidden:false,
 nextElementSibling:{hidden:false,open:true}}));
const before=JSON.stringify(rows.map(x=>x.dataset));
const fields=Object.fromEntries(['security','direction','score','status','waiting','monitoring','minimum','maximum','sort','secondary'].map(key=>[key,{
 dataset:{filter:key},type:key==='secondary'?'checkbox':'text',checked:false,value:key==='sort'?'original':'',options:[],append(option){this.options.push(option);}}]));
const listeners={},count={},empty={},clear={},body={children:[],append(fragment){this.children=fragment.children;}};
clear.addEventListener=(event,fn)=>clear.click=fn;
const controls={hidden:true,querySelectorAll:()=>Object.values(fields),
 querySelector:s=>s==='[data-filter-count]'?count:clear,addEventListener:(event,fn)=>listeners[event]=fn};
const browser={dataset:{population:'Complete Diagnostics population'},
 querySelector:s=>s==='.machine-controls'?controls:s==='[data-filter-empty]'?empty:body,
 querySelectorAll:()=>rows};
const document={querySelectorAll:()=>[browser],createElement:()=>({}),
 createDocumentFragment:()=>({children:[],append(...items){this.children.push(...items);}})};
"""
    checks = r"""
assert.equal(controls.hidden,false);assert.equal(count.textContent,'Showing 3 of 3 · Complete Diagnostics population');
assert.deepEqual(fields.score.options.map(x=>x.value),['0','5','UNAVAILABLE']);
fields.secondary.checked=true;listeners.change();assert.deepEqual(rows.map(x=>x.hidden),[false,true,true]);
fields.security.value='not found';listeners.input();assert.equal(empty.hidden,false);assert.ok(rows.every(x=>x.hidden));
clear.click();assert.equal(empty.hidden,true);assert.ok(rows.every(x=>!x.hidden));assert.equal(fields.secondary.checked,false);
fields.sort.value='price-asc';listeners.change();assert.equal(body.children[0],rows[1]);assert.equal(body.children[1],rows[1].nextElementSibling);
assert.equal(body.children[4],rows[2]);assert.equal(rows[1].nextElementSibling.open,true);
fields.minimum.value='10';listeners.input();assert.deepEqual(rows.map(x=>x.hidden),[false,true,true]);
assert.ok(rows.every(x=>x.hidden===x.nextElementSibling.hidden));
fields.minimum.value='invalid';listeners.input();assert.ok(count.textContent.startsWith('Enter valid'));
clear.click();assert.equal(body.children[0],rows[0]);assert.ok(rows.every(x=>!x.hidden));
assert.equal(JSON.stringify(rows.map(x=>x.dataset)),before);
"""
    result=subprocess.run(['/usr/local/bin/node','-e',prelude+CONTROLS_JS+checks],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_history_rollover_and_original_accounting_format_are_distinct_from_browser_time():
    rows=({'boundary':'2026-10-13T04:10:03.095000+00:00','result':'SUCCESS','duration_microseconds':81568302,'analysed_population':98},
          {'boundary':'2026-10-13T04:54:47+00:00','result':'SUCCESS','duration_microseconds':79490000,'analysed_population':98},
          {'boundary':'2026-09-30T20:00:00+00:00','result':'FAILED','duration_microseconds':None,'analysed_population':None})
    html=_analysis_history(dict(recent_analysis_history=rows))
    assert '1m 22s' in html and '1m 19s' in html and 'Duration unavailable' in html
    assert '13 OCT 2026 09:40 IST' in html and '13 OCT 2026 10:24 IST' in html and '01 OCT 2026 01:30 IST' in html


def test_history_route_with_refresh_control_never_synchronizes_provider(tmp_path,monkeypatch):
    from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
    control,record,accounting,routes=composed(tmp_path)
    owner=control.operation_service._runtime
    before=owner.read_only_status();files=inventory(tmp_path)
    def forbidden(*args,**kwargs):
        raise AssertionError('GET_CALLED_ACTION_TIME_PROVIDER_SYNCHRONIZATION')
    monkeypatch.setattr(SharedAuthenticatedProviderRuntime,'_SharedAuthenticatedProviderRuntime__synchronize_locked',forbidden)
    monkeypatch.setattr(SharedAuthenticatedProviderRuntime,'_SharedAuthenticatedProviderRuntime__revoke_locked',forbidden)
    response=routes.handle_get(BrowserGetRequest('/intraday',{}),_snapshot)
    assert response.status.value==200 and '1m 22s' in response.body
    assert owner.read_only_status()==before and inventory(tmp_path)==files


@pytest.mark.parametrize('operation_name',['discovery_operation','discovery_v2_operation','historical_operation'])
@pytest.mark.parametrize('state',['retained','expired','unavailable_clock'])
def test_intraday_status_getters_are_observational_even_with_retained_context(tmp_path,monkeypatch,operation_name,state):
    from tests.unit.intraday.test_probables_v2_refresh_control import _control
    from tests.unit.provider.test_shared_provider_runtime import VALID_THROUGH
    from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
    shared,runtime,control,calls,requests=_control(tmp_path)
    if state=='expired':
        monkeypatch.setattr(shared,'_SharedAuthenticatedProviderRuntime__clock',lambda:VALID_THROUGH)
    elif state=='unavailable_clock':
        monkeypatch.setattr(shared,'_SharedAuthenticatedProviderRuntime__clock',lambda:VALID_THROUGH.replace(tzinfo=None))
    before=shared.read_only_status();files=inventory(tmp_path);factory_before=tuple(calls)
    def forbidden(*args,**kwargs):
        raise AssertionError('STATUS_REVALIDATED_OR_REVOKED_CONTEXT')
    monkeypatch.setattr(SharedAuthenticatedProviderRuntime,'_SharedAuthenticatedProviderRuntime__synchronize_locked',forbidden)
    monkeypatch.setattr(SharedAuthenticatedProviderRuntime,'_SharedAuthenticatedProviderRuntime__revoke_locked',forbidden)
    service=getattr(runtime,operation_name)
    assert service.operation_available is (state=='retained')
    assert service.actual_context_state==before['retained_lifecycle']
    assert shared.read_only_status()==before and inventory(tmp_path)==files
    assert tuple(calls)==factory_before and requests==[0]


def test_status_correction_preserves_declared_execution_capability_code():
    import marshal
    from types import CodeType
    root=Path(__file__).resolve().parents[3]
    for name in ('intraday_discovery_operation.py','intraday_historical_operation.py'):
        relative='src/kronos/application/'+name
        base=subprocess.run(['git','show','40312309bca548a89ae3191fe96a7152728a300e:'+relative],
            cwd=root,capture_output=True,check=True).stdout
        current=(root/relative).read_bytes()
        assert base.count(b'\n')==current.count(b'\n')
        def functions(data):
            code=compile(data,str(root/relative),'exec',dont_inherit=True)
            found={}
            def visit(value,prefix=''):
                for item in value.co_consts:
                    if isinstance(item,CodeType):
                        found[prefix+item.co_name]=marshal.dumps(item)
                        visit(item,prefix+item.co_name+'.')
            visit(code)
            return found
        old,new=functions(base),functions(current)
        changed={key for key in old.keys()|new.keys() if old.get(key)!=new.get(key)}
        # Class container bytecode changes because it includes the two getters.
        assert {key for key in changed if '.' in key}=={
            next(key for key in old if key.endswith('.operation_available')),
            next(key for key in old if key.endswith('.actual_context_state')),
        }


def test_historical_identity_link_wraps_without_shortening_or_mutating_evidence(tmp_path):
    from tests.unit.browser.test_intraday_review_v2_control import _control,_payload
    from kronos.browser.intraday_wo08 import IntradayVisualHistory
    from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
    from kronos.intraday.visual_reconciliation_v2_persistence import VisualReconciliationStore
    run,application,control=_control(tmp_path/'history')
    control.execute_document(_payload(run))
    identity=application.snapshot().candidates[0].cycle_identity
    history=IntradayVisualHistory(application.review_store,
        IntradayMcxPairedReviewStore(tmp_path/'paired'),VisualReconciliationStore(tmp_path/'reconciled'))
    before=inventory(tmp_path)
    html=history.render(_snapshot())
    assert 'style="overflow-wrap:anywhere"' in html
    assert identity in html and 'kind=nse-cycle' in html and 'identity='+identity in html
    assert 'They confer no new production authority' in html
    assert inventory(tmp_path)==before


def canonical_comparison(tmp_path):
    from datetime import timedelta
    from tests.unit.application.test_iwo_experimental_rehearsal import configured_experimental_runtime
    from tests.unit.application.test_intraday_discovery_operation import _request_at
    from kronos.application.intraday_discovery_operation import DiscoveryOperationState
    runtime,shared,clock,stage,calls=configured_experimental_runtime(tmp_path,'LONG')
    clock[0]+=timedelta(minutes=5);stage[0]='COMPLETE'
    result=runtime.discovery_v2_operation.execute(_request_at('IWO07-EXACT-ORIGIN',clock[0]))
    assert result.state is DiscoveryOperationState.COMPLETE
    readiness=next(r for _,r in runtime.wo09_application.restore()
        if r.canonical_subject_identity=='NSE-EQ-LUPIN' and r.satisfied_count==5)
    handoff=runtime.wo09_application.create_handoff(readiness,created_at=clock[0])
    comparison=runtime.futures_application.construct_current(handoff_identity=handoff.handoff_identity,
        request_identity='IWO07-ORIGIN-CONSTRUCT')
    return runtime,clock,calls,readiness,comparison


@pytest.mark.parametrize('decision',['NONE','DO_NOTHING','ACTIVATE_PAPER'])
def test_canonical_books_preserve_original_origin_and_separate_trade_claim(tmp_path,decision):
    from kronos.application.intraday_books import IntradayBooks
    from kronos.application.intraday_journal import IntradayJournalApplication
    from kronos.intraday.wo14_journal_store import JournalStore
    from kronos.application.shared_monitoring import SharedSwingMonitoringHub
    from tests.unit.intraday.test_wo11_lifecycle_application import Capability
    runtime,clock,calls,readiness,comparison=canonical_comparison(tmp_path)
    books=IntradayBooks(research=runtime.research_store,futures=runtime.futures_application.store,
        lifecycle=runtime.lifecycle_application)
    books.bind()
    journal=IntradayJournalApplication(research=runtime.research_store,futures=runtime.futures_application.store,
        lifecycle=runtime.lifecycle_application,store=JournalStore(tmp_path/'journal-check'))
    journal.bind()
    choice='NONE' if decision=='NONE' else 'SELECTED_FUTURE'
    selection=runtime.futures_application.select(comparison.identity,choice=choice,lots=None if choice=='NONE' else 1,
        session=runtime.lifecycle_application.session_source(readiness.canonical_subject_identity,clock[0]),
        action_identity='IWO07-ORIGIN-SELECT')
    track=None
    if decision!='NONE':
        handoff=next(r for r in runtime.futures_application.store.records('WO10_SELECTED_TRADE_HANDOFF_V1')
            if r.data['selection_identity']==selection.identity)
        if decision=='ACTIVATE_PAPER':
            cap=Capability();hub=SharedSwingMonitoringHub()
            runtime.lifecycle_application.bind_monitoring(hub,lambda:cap)
        track=runtime.lifecycle_application.action(handoff_identity=handoff.identity,
            action=decision,action_identity='IWO07-ORIGIN-ACTION')
    row,=books.snapshot()
    origin=next(r for r in runtime.research_store.records('WO12_OPPORTUNITY_ORIGIN_V1')
        if r.data['opportunity_identity']==readiness.opportunity_identity)
    assert row.data['opportunity_identity']==origin.data['opportunity_identity']
    assert row.data['opportunity_id']==origin.data['opportunity_id']
    claim=comparison.data['opportunity_identity']
    assert claim.startswith('WO10_OPPORTUNITY_V1-') and claim!=row.data['opportunity_identity']
    assert claim in row.data['source_identities']
    assert books.portfolio()==()  # Arming/abstention is not entered exposure.
    assert runtime.journal_application is not journal  # Independent same-source owner.
    if decision=='ACTIVATE_PAPER':
        assert track.data['lots']==1 and track.data['entry'] is None
        plan=runtime.futures_application.store.load(track.data['intake']['plan_identity']).data
        intake=dict(track.data['intake'],experimental_opportunity_identity='UNRELATED-ORIGIN')
        with pytest.raises(ValueError,match='EXPERIMENTAL_LINEAGE_MISMATCH'):
            books._plan_origin(plan,claim,intake=intake)
        changed={**plan,'wo09':{**plan['wo09'],'opportunity_identity':'UNRELATED-ORIGIN'}}
        with pytest.raises(ValueError,match='EXPERIMENTAL_LINEAGE_MISMATCH'):
            books._plan_origin(changed,claim,intake=track.data['intake'])
        runtime.lifecycle_application.shutdown()
    assert any(r.data['opportunity_identity']==readiness.opportunity_identity
        for r in journal.store.snapshot().records)


def test_research_folder_presentation_wraps_without_changing_path_text():
    from kronos.browser.intraday_research import render_research
    folder='/Volumes/very-long-verified-volume-name/'+'bounded-path-component/'*8
    status=dict(current_month='2026_09',update_month='2026_09',publication_root=folder,
        receipt_identity=None,workbook_verified=False,workbook_path=None,last_update=None,sponsor_summary=None)
    html=render_research(_snapshot(),status,statistics=True)
    assert "<code style='overflow-wrap:anywhere'>" in html and folder in html
