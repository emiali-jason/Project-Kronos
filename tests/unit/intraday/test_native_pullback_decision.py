"""Typed Native publication and exact-source consumption qualification."""
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal as D
import json
import pytest
from kronos.intraday.native_pullback_decision import source_document,build_decision,retain_decision,decode_source
from kronos.intraday.native_structural_selection import NativeStructuralStore
from kronos.intraday.probables_v2_refresh import create_discovery_probables_v2_facts
from kronos.intraday.completed_evidence import build_completed_evidence_selection
from kronos.intraday.probables_v2 import build_semantic_qualification_evidence_v2,create_discovery_probables_evidence_v2,evaluate_probables_v2_run
from kronos.provider.contracts.market_data import HistoricalCandle
from tests.unit.intraday.test_native_pullback_policy import START,BOUNDARY,SESSION,SUBJECT,candles,BARS
from kronos.market.schedule import MarketDaySchedule,MarketWindow,TradingDayStatus

def source_fixture(direction='LONG', subject=SUBJECT, session=SESSION, binding=None, bundle=None):
    exchange='MCX' if subject.startswith('MCX-') else 'NSE'
    current=MarketDaySchedule(exchange,START.date(),session,'Asia/Kolkata',TradingDayStatus.TRADING,
        (MarketWindow(START,START+timedelta(hours=6,minutes=15)),),'DOMAIN008_ISOLATED','1')
    previous=MarketDaySchedule(exchange,(START-timedelta(days=1)).date(),'NSE-2026-09-10','Asia/Kolkata',TradingDayStatus.TRADING,
        (MarketWindow(START-timedelta(days=1),START-timedelta(days=1)+timedelta(hours=6,minutes=15)),),'DOMAIN008_ISOLATED','1')
    def raw(start,h,l,c):
        return HistoricalCandle(start,float(c),float(h),float(l),float(c),100)
    cs=candles(direction=direction)
    facts=create_discovery_probables_v2_facts(universe_member_identity='MEMBER',canonical_subject_identity=subject,
        subject_exchange=exchange,discovery_bundle_identity='BUNDLE' if bundle is None else bundle.bundle_identity,observation_boundary_identity='BOUNDARY',observation_boundary=BOUNDARY,
        current_schedule=current,previous_schedule=previous,
        previous_daily=(raw(previous.windows[0].opens_at,125,85,105),),
        previous_one_hour=tuple(raw(previous.windows[0].opens_at+timedelta(hours=i),104,100,102) for i in range(6)),
        current_one_hour=tuple(raw(START+timedelta(hours=i),106+i if direction=="LONG" else 200-i,100+i if direction=="LONG" else 194-i,104+i if direction=="LONG" else 196-i) for i in range(6)),
        current_fifteen_minute=tuple(raw(c.candle_start,c.high,c.low,c.close) for c in cs),
        current_five_minute=tuple(raw(START+timedelta(minutes=5*i),110+i if direction=="LONG" else 200-i,105+i if direction=="LONG" else 195-i,108+i if direction=="LONG" else 197-i) for i in range(24)))
    selection=build_completed_evidence_selection(canonical_subject_identity=subject,analysis_boundary=BOUNDARY,
        current_schedule=current,previous_schedule=previous,previous_daily=facts.previous_daily,
        previous_one_hour=facts.previous_one_hour,current_one_hour=facts.current_one_hour,
        current_fifteen_minute=facts.current_fifteen_minute,current_five_minute=facts.current_five_minute,provenance=('ISOLATED',))
    semantic=build_semantic_qualification_evidence_v2(selection=selection,narrow_cpr_fact=facts.previous_session_facts.narrow_cpr,
        participation_state='AVAILABLE_SUPPORTING_NON_BLOCKING',provenance=('ISOLATED',))
    mapping=create_discovery_probables_evidence_v2(universe_member_identity='MEMBER',source_discovery_run_identity='DISCOVERY',
        source_discovery_member_identity='MEMBER-RESULT',market_session_identity=session,completed_evidence=selection,
        semantic_evidence=semantic,opening_semantic=None,nifty_relative=None,provenance=('ISOLATED',facts.facts_identity))
    run=evaluate_probables_v2_run(source_discovery_run_identity='DISCOVERY',universe_identity='UNIVERSE',universe_version='1',
        reconciliation_identity='RECONCILIATION',reconciliation_version='1',market_session_identity=session,analysis_boundary=BOUNDARY,
        member_evidence=(mapping,),unavailable_members=(),provenance=('ISOLATED',))
    return source_document(facts,mapping,run.results[0],run.run_identity,mcx_binding=binding,machine_bundle=bundle),facts,mapping,run

def test_owner_wire_roundtrip_and_retained_decision(tmp_path):
    source,f,m,r=source_fixture()
    assert decode_source(source)[:3]==(f,m,r.results[0])
    d=retain_decision(NativeStructuralStore(tmp_path/'native'),source,created_at=BOUNDARY)
    assert NativeStructuralStore(tmp_path/'native').load(d.identity)==d
    assert d.data['result']=='PULLBACK',d.data
    assert d.data['target_manifest']['completeness']!='INCOMPLETE'

def test_exact_source_loader_checks_without_reselecting(tmp_path,monkeypatch):
    from kronos.intraday.native_pullback_decision import load_decision_source
    import kronos.intraday.native_pullback_policy as policy
    source,*_=source_fixture();store=NativeStructuralStore(tmp_path/'native')
    d=retain_decision(store,source,created_at=BOUNDARY)
    monkeypatch.setattr(policy,'select_cycle',lambda *a,**k:pytest.fail('WO10 must not select'))
    assert load_decision_source(store,d,None)==source

@pytest.mark.parametrize('new,boundary_offset,expected',[(False,0,0),(True,1,0),(True,0,1)])
def test_prospective_publication_only(tmp_path,new,boundary_offset,expected):
    from kronos.application.intraday_native_selection import NativePullbackPublication
    source,f,m,run=source_fixture();store=NativeStructuralStore(tmp_path/'native')
    publisher=NativePullbackPublication(store,clock=lambda:BOUNDARY,commissioned_at=BOUNDARY+timedelta(seconds=boundary_offset))
    assert not store.root.exists()
    decisions=publisher.publish(run,(m,),facts=(f,),newly_published=new)
    assert len(decisions)==expected
    if not expected:assert not store.root.exists()
    else:
        before={str(p):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
        assert publisher.publish(run,(m,),facts=(f,),newly_published=True)==decisions
        assert before=={str(p):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}

def test_missing_facts_retains_explicit_negative(tmp_path):
    from kronos.application.intraday_native_selection import NativePullbackPublication
    from kronos.intraday.native_pullback_decision import load_decision_source
    source,f,m,run=source_fixture();store=NativeStructuralStore(tmp_path/'native')
    publisher=NativePullbackPublication(store,clock=lambda:BOUNDARY,commissioned_at=BOUNDARY)
    decision,=publisher.publish(run,(m,),newly_published=True)
    assert decision.data['result']=='NOT_ESTABLISHED'
    assert decision.data['reasons']==['SOURCE_INTEGRITY_INVALID']
    assert load_decision_source(store,decision,None)['failure']=='SOURCE_INTEGRITY_INVALID'

def test_native_failure_blocks_exposure_but_does_not_change_methodology(tmp_path):
    from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
    from kronos.intraday.probables_v2_persistence import ProbablesV2Store
    source,f,m,run=source_fixture()
    class Failed:
        def publish(self,*a,**k):raise OSError('ISOLATED retention failure')
    store=ProbablesV2Store(tmp_path/'probables');app=IntradayProbablesV2Application(store=store,native_selection=Failed())
    with pytest.raises(RuntimeError,match='PROBABLES_V2_REFRESH_FAILED'):
        app.refresh_analysis(source_discovery_run_identity=run.source_discovery_run_identity,universe_identity=run.universe_identity,
            universe_version=run.universe_version,reconciliation_identity=run.reconciliation_identity,reconciliation_version=run.reconciliation_version,
            market_session_identity=run.market_session_identity,analysis_boundary=run.analysis_boundary,member_evidence=(m,),unavailable_members=(),provenance=('ISOLATED',),native_facts=(f,))
    assert store.load_current_run() is None

@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_real_selector_through_wo09_geometry_future_risk_selection(tmp_path,monkeypatch,direction):
    from kronos.application.intraday_futures import IntradayFuturesApplication
    from kronos.application.intraday_wo09 import IntradayWo09Application
    from kronos.intraday.wo09_persistence import Wo09Store
    from kronos.intraday.wo09_readiness import evaluate_readiness
    from kronos.intraday.visual_reconciliation_v2 import VisualReconciliationInput,create_reconciliation_record,Q10Classification
    from kronos.intraday.wo10_futures_store import FuturesStore
    from kronos.intraday.native_structural_selection import NativeStructuralLoader
    from tests.unit.intraday.test_wo09_readiness import evidence,observation,POSITIVE
    import tests.unit.intraday.test_wo10_futures as futures
    from kronos.intraday.wo10_futures_contract import normalize
    # All market/Risk fixture authority is freshly bound to this isolated boundary.
    monkeypatch.setattr(futures,'NOW',BOUNDARY)
    source,f,m,run=source_fixture(direction)
    native=NativeStructuralStore(tmp_path/'native')
    from kronos.application.intraday_native_selection import NativePullbackPublication
    d,=NativePullbackPublication(native,clock=lambda:BOUNDARY,commissioned_at=BOUNDARY).publish(run,(m,),facts=(f,),newly_published=True)
    assert d.data['result']=='PULLBACK',d.data
    request=VisualReconciliationInput(SUBJECT,direction,'run','result','cycle','pack','chart','answer','a'*64,'visual','correspondence',
        (m.semantic_evidence.evidence_identity,),tuple(observation(k,v) for k,v in POSITIVE.items()),q10_classification=Q10Classification.NOT_APPLICABLE)
    visual=create_reconciliation_record(request,created_at=BOUNDARY)
    readiness,watch=evaluate_readiness(visual,evidence(subject=SUBJECT,direction=direction,analysis_boundary=BOUNDARY,
        machine_evidence_identity=m.semantic_evidence.evidence_identity,machine_evidence_integrity=m.semantic_evidence.integrity_identity),created_at=BOUNDARY)
    wo09=Wo09Store(tmp_path/'wo09');wo09.retain(readiness,watch)
    h=IntradayWo09Application(wo09).create_handoff(readiness,created_at=BOUNDARY,first_five_of_five_at=BOUNDARY)
    app=IntradayFuturesApplication(FuturesStore(tmp_path/'futures'),wo09,clock=lambda:BOUNDARY,
        structural_loader=NativeStructuralLoader(native),operational_guard=lambda:True)
    master,underlying=futures.master(SUBJECT)
    provider=futures.Provider(now=BOUNDARY)
    authority=dict(master=master,underlying=underlying,active_mcx=None,economics=None,configuration=futures.config())
    app.acquisition_source=lambda handoff,plan:dict(**authority,provider=provider,authority_source=lambda:authority,
        session_source=lambda now:futures.session(now))
    comparison=app.construct_current(handoff_identity=h.handoff_identity,request_identity='COMMISSIONED-1')
    assert comparison.schema=='WO10_SPONSOR_COMPARISON_V1',comparison.data.get('reason')
    assert comparison.data['executability']=='EXECUTABLE',comparison.data
    selected=app.select(comparison.identity,choice='SELECTED_FUTURE',lots=1,session=futures.session(BOUNDARY),action_identity='SPONSOR-1')
    assert selected.data['sponsor_selected_lots']==1
    assert len(app.store.records('WO10_SELECTED_TRADE_HANDOFF_V1'))==1
    assert len(provider.calls)==1

@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_target_manifest_preserves_prior_and_derived_lineage(direction):
    source,f,m,r=source_fixture(direction);d=build_decision(source,created_at=BOUNDARY).data
    rows=d['target_manifest']['rows'];assert len(rows)==13
    prior=[x['reference'] for x in rows if x['source_class']=='PDH_PDL']
    assert all(x['kind']=='PRIOR_SESSION_LEVEL' and x['origin_session']==f.previous_schedule.session_id for x in prior)
    pivots=[x['reference'] for x in rows if x['source_class']=='CLASSIC_PIVOTS']
    assert {x['field'] for x in pivots}=={'R1','R2','R3','R4','S1','S2','S3','S4'}
    assert all(x['kind']=='DERIVED_PIVOT_LEVEL' and x['candle_identity'] is None and x['source_evidence_identity']==f.previous_session_facts.facts_identity for x in pivots)
    assert all(not x['included'] for x in rows if x['source_class'] in {'CURRENT_SESSION_EXTREMES','GOVERNED_15M_BARRIERS'})

@pytest.mark.parametrize('path', ['roles','cycle','manifest','source'])
def test_sealed_tampering_cannot_change_loaded_roles(tmp_path,path):
    from kronos.intraday.native_pullback_decision import load_decision_source
    from kronos.intraday.native_structural_selection import create_native_selection
    source,f,m,r=source_fixture();store=NativeStructuralStore(tmp_path/'native');decision=retain_decision(store,source,created_at=BOUNDARY)
    d=decision.data
    with pytest.raises((ValueError,KeyError)):
        if path=='roles':d['roles']['PULLBACK_STRUCTURAL_LOW']['candle_identity']=f.current_fifteen_minute[1].candle_identity
        if path=='cycle':d['cycle']['qualification_index']=6
        if path=='manifest':d['target_manifest']['rows'][1]['included']=True
        if path=='source':d['source_integrity']='f'*64
        changed=create_native_selection(**d)
        load_decision_source(store,changed,None)

@pytest.mark.parametrize('target', ['SETUP_NATIVE_TARGET','PDH_PDL','CLASSIC_PIVOTS','CURRENT_SESSION_EXTREMES','GOVERNED_15M_BARRIERS'])
def test_no_source_class_can_disappear_from_manifest(target):
    from kronos.intraday.native_structural_selection import create_native_selection
    from kronos.intraday.wo10_futures_contract import digest
    source,*_=source_fixture();d=build_decision(source,created_at=BOUNDARY).data
    m=d['target_manifest'];m['rows']=[x for x in m['rows'] if x['source_class']!=target]
    m['identity']='NATIVE-TARGET-MANIFEST-'+digest({k:v for k,v in m.items() if k!='identity'});d['target_population_identity']=m['identity']
    with pytest.raises(ValueError,match='TARGET_SOURCE_POPULATION_INCOMPLETE'):create_native_selection(**d)

@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_typed_class_missing_required_prior_is_incomplete(direction):
    from types import SimpleNamespace
    from kronos.intraday.native_pullback_policy import select_cycle
    from kronos.intraday.native_pullback_decision import target_manifest
    source,f,m,r=source_fixture(direction)
    cycle,_=select_cycle(f.current_fifteen_minute,subject=f.canonical_subject_identity,direction=direction,session=SESSION,boundary=BOUNDARY)
    incomplete=SimpleNamespace(current_fifteen_minute=f.current_fifteen_minute,previous_session_facts=f.previous_session_facts,
        previous_daily=(),previous_schedule=f.previous_schedule,current_schedule=f.current_schedule)
    manifest=target_manifest(incomplete,cycle=cycle,direction=direction,source_id='ISOLATED')
    assert manifest['completeness']=='INCOMPLETE'
    assert {x['source_class'] for x in manifest['rows'] if x['availability']=='UNAVAILABLE'}=={'PDH_PDL','CLASSIC_PIVOTS'}

@pytest.mark.parametrize('group,kind,role',[('CURRENT_SESSION_EXTREMES','CURRENT_SESSION_LEVEL','SESSION_STRUCTURAL_HIGH'),
    ('GOVERNED_15M_BARRIERS','GOVERNED_STRUCTURAL_BARRIER','GOVERNED_STRUCTURAL_BARRIER')])
def test_optional_typed_class_cannot_claim_complete_with_missing_authority(group,kind,role):
    from kronos.intraday.native_pullback_policy import select_cycle
    from kronos.intraday.native_pullback_decision import target_manifest,candle_reference
    source,f,m,r=source_fixture();cycle,_=select_cycle(f.current_fifteen_minute,subject=SUBJECT,direction='LONG',session=SESSION,boundary=BOUNDARY)
    ref=candle_reference(f.current_fifteen_minute[3],'HIGH',cycle.identity,'ISOLATED');ref['kind']=kind
    manifest=target_manifest(f,cycle=cycle,direction='LONG',source_id='ISOLATED',additional_levels=[dict(source_class=group,reference=ref,role=role,class_complete=False)])
    assert manifest['completeness']=='INCOMPLETE'
