"""Actual commissioned Native → WO09 → WO10 → WO11 in isolated stores."""
from datetime import timedelta
from types import SimpleNamespace
from decimal import Decimal as D
from dataclasses import replace
import pytest
import tests.unit.intraday.test_native_pullback_decision as native_test
from tests.unit.intraday.test_native_pullback_decision import source_fixture,NativeStructuralStore
from tests.unit.intraday.test_native_pullback_policy import START,SUBJECT
from tests.unit.intraday.test_wo10_futures import session
from kronos.intraday.wo11_lifecycle_store import LifecycleStore
from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
from kronos.application.intraday_lifecycle_intake import load_intake,instrument_record
from kronos.application.intraday_lifecycle_timing import qualify_timing
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.provider.contracts.monitoring import ProviderMarketTick,MonitoringConnectionState
from kronos.intraday.probables_v2_refresh import create_discovery_probables_v2_facts
from kronos.provider.contracts.market_data import HistoricalCandle
BOUNDARY=START+timedelta(hours=2)
from tests.unit.intraday.test_native_pullback_decision import source_document,build_completed_evidence_selection,build_semantic_qualification_evidence_v2,create_discovery_probables_evidence_v2,evaluate_probables_v2_run
from tests.unit.intraday.test_native_pullback_policy import SESSION,candles
from kronos.market.schedule import MarketDaySchedule,MarketWindow,TradingDayStatus

def early_source_fixture(direction='LONG', subject=SUBJECT, session=SESSION, binding=None, bundle=None):
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
        current_one_hour=tuple(raw(START+timedelta(hours=i),106+i if direction=="LONG" else 200-i,100+i if direction=="LONG" else 194-i,104+i if direction=="LONG" else 196-i) for i in range(2)),
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

def selected_fixture(tmp_path,monkeypatch,direction):
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
    source,f,m,run=early_source_fixture(direction)
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
    selected=app.select(comparison.identity,choice='SELECTED_FUTURE',lots=25,session=futures.session(BOUNDARY),action_identity='SPONSOR-1')
    assert selected.data['sponsor_selected_lots']==25
    assert len(app.store.records('WO10_SELECTED_TRADE_HANDOFF_V1'))==1
    assert len(provider.calls)==1
    return app, app.store.records("WO10_SELECTED_TRADE_HANDOFF_V1")[0], f, provider


def later_facts(f,now,direction):
    raw={}
    for key in ('previous_daily','previous_one_hour','current_one_hour','current_fifteen_minute','current_five_minute'):
        raw[key]=[HistoricalCandle(c.candle_start,float(c.open),float(c.high),float(c.low),float(c.close),c.volume) for c in getattr(f,key)]
    last=raw['current_five_minute'][-1];sign=1 if direction=='LONG' else -1
    for offset in range(1, int((now-BOUNDARY).total_seconds()//300)+1):
        raw['current_five_minute'].append(HistoricalCandle(BOUNDARY+timedelta(minutes=5*(offset-1)),last.open+sign*offset,last.high+sign*offset,last.low+sign*offset,last.close+sign*offset,100))
    return create_discovery_probables_v2_facts(universe_member_identity=f.universe_member_identity,
        canonical_subject_identity=f.canonical_subject_identity,subject_exchange=f.subject_exchange,
        discovery_bundle_identity=f.discovery_bundle_identity,observation_boundary_identity='ISOLATED-TIMING',observation_boundary=now,
        current_schedule=f.current_schedule,previous_schedule=f.previous_schedule,**raw)


class Capability:
    active=True
    def __init__(self):self.consumer=None;self.calls=[]
    def open_monitoring_session(self,consumer):self.consumer=consumer;return self
    def subscribe(self,instruments):self.calls.append(('subscribe',instruments))
    def unsubscribe(self,instruments):self.calls.append(('unsubscribe',instruments))
    def connect(self):self.consumer.on_connection_state(MonitoringConnectionState.CONNECTED)
    def disconnect(self):self.consumer.on_connection_state(MonitoringConnectionState.DISCONNECTED)


def fixture(tmp_path,monkeypatch,direction='LONG'):
    monkeypatch.setattr(native_test,'BOUNDARY',BOUNDARY)
    futures,h,f,provider=selected_fixture(tmp_path,monkeypatch,direction)
    clock=[BOUNDARY]
    app=IntradayLifecycleApplication(futures=futures,store=LifecycleStore(tmp_path/'wo11'),clock=lambda:clock[0],
        session_source=lambda subject,now:session(now),
        timing_source=lambda current:qualify_timing(current,later_facts(f,clock[0],direction),acquired_at=clock[0]),operational_guard=lambda:True)
    cap=Capability();hub=SharedSwingMonitoringHub();app.bind_monitoring(hub,lambda:cap)
    return app,h,f,provider,clock,cap,hub


def emit(app,cap,clock,current,price,*,lag=0,sequence=None):
    t=ProviderMarketTick(instrument_record(current.data['intake']['future']),D(price),clock[0],clock[0]+timedelta(seconds=lag),
        'KITE_CONNECT_WEBSOCKET','session-test',sequence,True,True,True)
    clock[0]=t.received_at
    cap.consumer.on_market_tick(t)
    return app.store.restore()[0]


@pytest.mark.parametrize('direction',['LONG','SHORT'])
@pytest.mark.parametrize('action',['ACTIVATE_PAPER','OBSERVE'])
def test_full_native_to_wo12_journey(tmp_path,monkeypatch,direction,action):
    app,h,f,provider,clock,cap,hub=fixture(tmp_path,monkeypatch,direction)
    current=app.action(handoff_identity=h.identity,action=action,action_identity='ARM')
    assert current.data['lots']==1 and current.data['intake']['selected_lots']==25
    assert hub.active_session_count==1 and hub.subscription_count==1
    assert app.store.restore()[0]==current
    clock[0]+=timedelta(minutes=5)
    app.pulse()
    current=app.store.restore()[0]
    assert current.data['state']=='AWAITING_ENTRY',app.last_failure
    clock[0]+=timedelta(seconds=1)
    sign=D(1) if direction=='LONG' else D(-1)
    entry=D(current.data['intake']['entry'])+sign
    current=emit(app,cap,clock,current,str(entry))
    assert current.data['state']=='ACTIVE',app.last_failure
    assert D(current.data['entry']['price'])==entry
    clock[0]+=timedelta(seconds=1)
    target=D(current.data['intake']['target'])+sign
    current=emit(app,cap,clock,current,str(target))
    assert current.data['state']=='CLOSED',app.last_failure
    assert current.data['exit_reason']=='TARGET' and current.data['terminal_status']=='CLOSED'
    handoffs=app.store.records('WO11_WO12_HANDOFF_V1')
    assert len(handoffs)==1 and handoffs[0].data['lots']==1
    assert len(provider.calls)==1 # WO10 only; never REST model-price acquisition.
    assert len(app.store.records('WO11_ENTRY_V1'))==len(app.store.records('WO11_EXIT_V1'))==1
    closure,=app.store.records('WO11_CLOSURE_V1')
    assert closure.data['exit_reason']=='TARGET' and closure.data['terminal_status']=='CLOSED'
    assert app.projection()['cards'][0]['terminal']


def test_persisted_exclusivity_and_inert_restore(tmp_path,monkeypatch):
    app,h,f,provider,clock,cap,hub=fixture(tmp_path,monkeypatch)
    current=app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM')
    with pytest.raises(ValueError,match='ALREADY_CLAIMED'):
        app.action(handoff_identity=h.identity,action='ACTIVATE_PAPER',action_identity='DIFFERENT')
    assert app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM')==current
    restored=LifecycleStore(app.store.root)
    before={p:p.read_bytes() for p in app.store.root.rglob('*') if p.is_file()}
    assert restored.restore()==(current,)
    assert before=={p:p.read_bytes() for p in app.store.root.rglob('*') if p.is_file()}
    restored_app=IntradayLifecycleApplication(futures=app.futures,store=restored,clock=app.clock,
        session_source=app.session_source,timing_source=app.timing_source,operational_guard=app.operational_guard)
    assert restored_app.projection()['cards'][0]['monitoring']=='UNATTACHED'
    assert len(provider.calls)==1


def test_corrupt_reachable_graph_fail_closed(tmp_path,monkeypatch):
    app,h,*_=fixture(tmp_path,monkeypatch)
    current=app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM')
    path=app.store.root/'records'/(current.data['authorization_identity']+'.json')
    path.write_text('{}')
    with pytest.raises((ValueError,TypeError)):
        app.store.restore()


def test_no_quantity_or_price_fields_in_control(tmp_path,monkeypatch):
    from kronos.browser.intraday_lifecycle_control import IntradayLifecycleControl
    app,h,*_=fixture(tmp_path,monkeypatch);control=IntradayLifecycleControl(app)
    for field in ('lots','quantity','entry_price','exit_price','price'):
        result=control.execute_document(dict(handoff_identity=h.identity,action='ACTIVATE_PAPER',action_identity='ARM',**{field:2}))
        assert result['outcome']=='REJECTED'
    assert not app.store.root.exists()


def test_production_composition_retains_operational_guard_and_is_inert(tmp_path):
    from kronos.application.intraday_runtime import create_intraday_runtime
    from tests.unit.provider.test_shared_provider_runtime import _shared
    shared,provider,calls=_shared()
    runtime=create_intraday_runtime(shared,evidence_root=tmp_path)
    runtime.futures_application.operational_guard=lambda:False
    app=runtime.lifecycle_application
    with pytest.raises(ValueError,match='WO10_OPERATIONAL_AUTHORITY_UNAVAILABLE'):
        app.action(handoff_identity='not-loaded',action='ACTIVATE_PAPER',action_identity='blocked')
    app.pulse()
    assert not app.store.root.exists()
    assert provider.capability.calls==0 and provider.begin_count==0 and calls==[]
    runtime.futures_application.operational_guard=lambda:True
    assert app.operational_guard() is True
    assert not hasattr(app,'production_blocker')


def test_blocked_sponsor_controls_do_not_offer_activation():
    from kronos.browser.intraday_lifecycle_control import actions_html
    html=actions_html(dict(lifecycle_blocker='WO11_OPERATIONAL_AUTHORITY_UNAVAILABLE',selected_handoff='selected'))
    assert 'unavailable' in html and '<button' not in html


def test_active_controls_and_closed_projection_use_three_exit_language():
    from kronos.browser.intraday_lifecycle_control import lifecycle_action_label,closure_outcome_html
    assert lifecycle_action_label('PAPER_POSITION')=='EXIT PAPER'
    assert lifecycle_action_label('PAPER_OBSERVATION')=='STOP OBSERVATION'
    assert closure_outcome_html({'exit_reason':'SPONSOR_EXIT','terminal_status':'CLOSED'})=='<p>EXIT: SPONSOR EXIT</p>'
    assert closure_outcome_html({'exit_reason':None,'terminal_status':'SESSION_ENDED'})=='<p>TERMINAL STATUS: SESSION ENDED</p>'


def test_policy_publication_checksums_are_independent():
    import json
    from pathlib import Path
    from kronos.intraday.wo11_lifecycle_contract import POLICY,VERSION,RULES,CHECKSUM,LATENESS_CHECKSUM,LATENESS_RULES,digest
    p=Path(__file__).resolve().parents[3]/'docs/architecture/products/intraday/KRONOS-INTRADAY-WO11-PROSPECTIVE-LIFECYCLE-POLICY-V1.json'
    publication=json.loads(p.read_text())
    assert (publication['policy_identity'],publication['policy_version'])==(POLICY,VERSION)
    assert publication['rules']==RULES and publication['checksum']==CHECKSUM==digest(publication['rules'])
    assert publication['latency_rules']==LATENESS_RULES and publication['latency_checksum']==LATENESS_CHECKSUM
