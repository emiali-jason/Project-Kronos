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
    from tests.unit.intraday.recovery_r2b_fixtures import governed_graph,historical_handoff
    graph=governed_graph(tmp_path,m,run,f,clock=lambda:BOUNDARY)
    wo09=graph.wo09;readiness=graph.readiness
    wo09.retain(readiness,graph.requirements,expected=wo09.expectation(readiness.canonical_subject_identity))
    h=historical_handoff(wo09,readiness,created_at=BOUNDARY,first_five_of_five_at=BOUNDARY)
    app=IntradayFuturesApplication(graph.futures,wo09,clock=lambda:BOUNDARY,
        structural_loader=NativeStructuralLoader(native),operational_guard=lambda:True,eligibility=graph.boundary)
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


def test_conflicting_negative_retains_restores_and_loads_exact_source(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from kronos.intraday.native_pullback_decision import load_decision_source
    from kronos.intraday.native_structural_selection import NativeStructuralLoader
    from kronos.intraday.wo10_native_adapter import adapt_native

    # SHORT hourly facts and LONG 15M facts establish a real semantic conflict.
    source, facts, mapping, run = source_fixture('CONFLICTING')
    result, = run.results
    assert (result.direction.value, result.state.value) == ('CONFLICTING', 'NOT_ADMITTED')
    store = NativeStructuralStore(tmp_path / 'native')
    decision = retain_decision(store, source, created_at=BOUNDARY)
    d = decision.data
    assert (d['direction'], d['result'], d['reasons']) == (
        'CONFLICTING', 'NOT_ESTABLISHED', ['SOURCE_DIRECTION_MISMATCH'])
    assert all(d[k] is None for k in ('setup_family', 'setup_identity', 'cycle',
                                      'target_manifest', 'target_population_identity'))
    assert d['roles'] == {} and d['target_completeness'] == 'INCOMPLETE'
    before = {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    assert retain_decision(store, source, created_at=BOUNDARY) == decision
    assert before == {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    restored = NativeStructuralStore(store.root)
    assert restored.load(decision.identity) == decision
    assert restored.bound_identity(mapping.semantic_evidence.evidence_identity) == decision.identity
    # A loader-only lineage probe is not a commissioned WO09 handoff.
    handoff = SimpleNamespace(__post_init__=lambda: None,
        machine_evidence_identities=(d['machine_identity'],), canonical_subject_identity=d['subject'],
        direction=d['direction'], session_identity=d['session'], analysis_boundary=BOUNDARY,
        exact_mcx_contract_identity=None, exact_mcx_roll_lineage=None,
        machine_evidence_integrity=d['machine_integrity'], created_at=BOUNDARY)
    monkeypatch.setattr('kronos.intraday.native_pullback_decision.select_cycle',
                        lambda *a, **k: pytest.fail('negative loading must not reselect'))
    assert NativeStructuralLoader(restored).load(handoff, now=BOUNDARY) == decision
    assert load_decision_source(restored, decision, handoff) == source
    with pytest.raises(ValueError, match='TARGET_POPULATION_INCOMPLETE'):
        adapt_native(decision, handoff, None, None, now=BOUNDARY)


@pytest.mark.parametrize('field,value', [
    ('result', 'PULLBACK'), ('result', 'BREAKOUT'),
    ('reasons', []), ('reasons', ['NO_CONFIRMED_STRUCTURAL_CYCLE']),
    ('reasons', ['SOURCE_DIRECTION_MISMATCH', 'SOURCE_INTEGRITY_INVALID']),
    ('setup_family', 'PULLBACK'), ('setup_identity', 'forged-setup'),
    ('cycle', {'identity': 'forged-cycle'}), ('roles', {'ORIGIN_LOW': {}}),
    ('target_manifest', {}), ('target_population_identity', 'forged-target'),
    ('target_completeness', 'COMPLETE_WITH_TARGETS'),
    ('target_completeness', 'COMPLETE_NO_APPLICABLE_FORWARD_CONSTRAINTS'),
])
def test_conflicting_contract_rejects_promotion_and_attached_authority(field, value):
    from kronos.intraday.native_structural_selection import create_native_selection
    source, *_ = source_fixture('CONFLICTING')
    values = build_decision(source, created_at=BOUNDARY).data
    values[field] = value
    # Recompute the seal: rejection must come from the contract, not an old hash.
    with pytest.raises(ValueError, match='STRUCTURAL_CONTRACT_AUTHORITY_INVALID'):
        create_native_selection(**values)


@pytest.mark.parametrize('original_direction', ['LONG', 'SHORT'])
def test_complete_positive_payload_cannot_be_relabelled_conflicting(original_direction):
    from kronos.intraday.native_structural_selection import create_native_selection
    source, *_ = source_fixture(original_direction)
    values = build_decision(source, created_at=BOUNDARY).data
    assert values['result'] == 'PULLBACK' and values['cycle'] and values['roles']
    values['direction'] = 'CONFLICTING'
    with pytest.raises(ValueError, match='STRUCTURAL_CONTRACT_AUTHORITY_INVALID'):
        create_native_selection(**values)


@pytest.mark.parametrize('family', ['CRUDE', 'COPPER', 'GOLDM', 'SILVERM', 'NATGAS'])
def test_mcx_conflict_and_commissioning_hold_preserve_exact_binding(tmp_path, family):
    from tests.unit.intraday.test_native_pullback_mcx import mcx_source
    from kronos.intraday.native_pullback_decision import load_decision_source
    _, _, _, _, binding, bundle = mcx_source(family)
    source, _, _, run = source_fixture('CONFLICTING', subject=binding.canonical_subject_id,
        session=binding.domain008_session_identity, binding=binding, bundle=bundle)
    result, = run.results
    if family == 'NATGAS':
        # Its independent commissioning hold precedes directional admission.
        assert result.direction is None and result.state.value == 'UNAVAILABLE'
        assert result.execution_eligibility != 'ELIGIBLE'
    else:
        assert (result.direction.value, result.state.value) == ('CONFLICTING', 'NOT_ADMITTED')
    store = NativeStructuralStore(tmp_path / 'native')
    decision = retain_decision(store, source, created_at=BOUNDARY)
    assert decision.data['direction'] == ('UNAVAILABLE' if family == 'NATGAS' else 'CONFLICTING')
    assert decision.data['result'] == 'NOT_ESTABLISHED'
    assert decision.data['reasons'] == ['SOURCE_DIRECTION_MISMATCH']
    assert decision.data['exact_contract'] == binding.active_binding.derivative_contract_id
    assert decision.data['roll_lineage'] == binding.binding_identity
    assert store.load(decision.identity) == decision
    assert load_decision_source(store, decision, None) == source


@pytest.mark.parametrize('direction', ['INVALID_DIRECTION', 'conflicting', '', None])
def test_native_contract_still_rejects_invalid_directions(direction):
    from kronos.intraday.native_structural_selection import create_native_selection
    source, *_ = source_fixture('CONFLICTING')
    values = build_decision(source, created_at=BOUNDARY).data
    values['direction'] = direction
    with pytest.raises(ValueError, match='STRUCTURAL_CONTRACT_AUTHORITY_INVALID'):
        create_native_selection(**values)


@pytest.mark.parametrize('corruption', ['decision', 'source'])
def test_conflicting_negative_does_not_bypass_integrity(tmp_path, corruption):
    from dataclasses import replace
    from kronos.intraday.native_pullback_decision import load_decision_source
    source, *_ = source_fixture('CONFLICTING')
    store = NativeStructuralStore(tmp_path / 'native')
    decision = retain_decision(store, source, created_at=BOUNDARY)
    with pytest.raises(ValueError, match='INTEGRITY_INVALID'):
        if corruption == 'decision':
            replace(decision, integrity='0' * 64)
        else:
            path = store.root / 'sources' / (decision.data['native_source_identity'] + '.json')
            path.write_text('{}')
            load_decision_source(store, decision, None)


@pytest.mark.parametrize('claimed_direction', ['LONG', 'SHORT'])
def test_conflicting_machine_facts_cannot_authorize_positive_readiness(claimed_direction):
    from kronos.intraday.wo09_readiness import evaluate_readiness, HardGate, create_next_wo_handoff
    from tests.unit.intraday.test_wo09_readiness import source as visual_source, evidence
    _, _, mapping, _ = source_fixture('CONFLICTING')
    semantic = mapping.semantic_evidence
    record, _ = evaluate_readiness(visual_source(direction=claimed_direction),
        evidence(direction=claimed_direction,
                 one_hour=semantic.fact('1H_REGIME').direction.value,
                 fifteen=semantic.fact('15M_STRUCTURE').direction.value), created_at=BOUNDARY)
    assert record.hard_gate is HardGate.AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT
    assert record.satisfied_count is None
    with pytest.raises(ValueError, match='WO09_HANDOFF_INVALID'):
        create_next_wo_handoff(record, created_at=BOUNDARY,
            current_readiness_identity=record.readiness_identity, current_pointer_integrity='exact-pointer',
            currentness=record.currentness, superseded_readiness_identity=None,
            first_five_of_five_at=BOUNDARY)


def conflicting_fallback_fixture(case):
    if case == 'missing_binding':
        from tests.unit.intraday.test_native_pullback_mcx import mcx_source
        _, _, _, _, binding, bundle = mcx_source('CRUDE')
        fixture = source_fixture('CONFLICTING', subject=binding.canonical_subject_id,
            session=binding.domain008_session_identity, binding=binding, bundle=bundle)
        return fixture, (fixture[1],), (bundle,), 'MCX_CONTRACT_BINDING_INVALID'
    assert case == 'missing_facts'
    fixture = source_fixture('CONFLICTING')
    return fixture, (), (), 'SOURCE_INTEGRITY_INVALID'


@pytest.mark.parametrize('case', ['missing_binding', 'missing_facts'])
def test_conflicting_fallback_retains_exact_negative_source_and_rejects_promotion(tmp_path, case):
    from types import SimpleNamespace
    from kronos.intraday.native_pullback_decision import unavailable_source, load_decision_source
    from kronos.intraday.native_structural_selection import NativeStructuralLoader, create_native_selection
    from kronos.intraday.wo10_native_adapter import adapt_native
    fixture, _, _, reason = conflicting_fallback_fixture(case)
    _, _, mapping, run = fixture
    result, = run.results
    source = unavailable_source(mapping, result, run.run_identity, reason)
    store = NativeStructuralStore(tmp_path / 'native')
    decision = retain_decision(store, source, created_at=BOUNDARY)
    d = decision.data
    assert (d['direction'], d['result'], d['reasons']) == ('CONFLICTING', 'NOT_ESTABLISHED', [reason])
    assert d['analysis_cycle'] == run.run_identity
    assert d['machine_identity'] == result.semantic_evidence_identity
    assert d['machine_integrity'] == mapping.semantic_evidence.integrity_identity
    assert d['probable_result_identity'] == result.result_identity
    assert d['completed_evidence_identity'] == result.completed_evidence_selection_identity
    assert d['instrument_identity'] == d['subject'] and d['exact_contract'] is None and d['roll_lineage'] is None
    assert all(d[k] is None for k in ('setup_family', 'setup_identity', 'cycle',
                                      'target_manifest', 'target_population_identity'))
    assert d['roles'] == {} and d['target_completeness'] == 'INCOMPLETE'
    restored = NativeStructuralStore(store.root)
    assert restored.load(decision.identity) == decision
    assert load_decision_source(restored, decision, None) == source
    # A lineage probe cannot commission a positive WO09 handoff.
    handoff = SimpleNamespace(__post_init__=lambda: None,
        machine_evidence_identities=(d['machine_identity'],), canonical_subject_identity=d['subject'],
        direction=d['direction'], session_identity=d['session'], analysis_boundary=BOUNDARY,
        exact_mcx_contract_identity=None, exact_mcx_roll_lineage=None,
        machine_evidence_integrity=d['machine_integrity'], created_at=BOUNDARY)
    assert NativeStructuralLoader(restored).load(handoff, now=BOUNDARY) == decision
    with pytest.raises(ValueError, match='TARGET_POPULATION_INCOMPLETE'):
        adapt_native(decision, handoff, None, None, now=BOUNDARY)
    for field, value in [('result', 'PULLBACK'), ('result', 'BREAKOUT'),
            ('setup_family', 'PULLBACK'), ('setup_identity', 'fabricated'), ('cycle', {}),
            ('roles', {'ORIGIN_LOW': {}}), ('target_manifest', {}),
            ('target_population_identity', 'fabricated'), ('target_completeness', 'COMPLETE_WITH_TARGETS'),
            ('reasons', [reason, 'SOURCE_DIRECTION_MISMATCH']), ('reasons', ['NO_CONFIRMED_STRUCTURAL_CYCLE'])]:
        with pytest.raises(ValueError, match='STRUCTURAL_CONTRACT_AUTHORITY_INVALID'):
            create_native_selection(**{**d, field: value})
    # A different bounded reason still cannot override the exact retained source failure.
    other = 'SOURCE_INTEGRITY_INVALID' if case == 'missing_binding' else 'SOURCE_DIRECTION_MISMATCH'
    changed = create_native_selection(**{**d, 'reasons': [other]})
    with pytest.raises(ValueError, match='SOURCE_INTEGRITY_INVALID'):
        load_decision_source(restored, changed, None)
    # No exact binding authority may be attached to a missing-binding source.
    if case == 'missing_binding':
        changed = create_native_selection(**{**d, 'exact_contract': 'fabricated-contract',
            'roll_lineage': 'fabricated-roll', 'instrument_identity': 'fabricated-contract'})
        with pytest.raises(ValueError, match='SOURCE_INTEGRITY_INVALID'):
            load_decision_source(restored, changed, None)


@pytest.mark.parametrize('reason', [r.value for r in __import__(
    'kronos.intraday.native_pullback_policy', fromlist=['Reason']).Reason
    if r.value not in {'SOURCE_INTEGRITY_INVALID'}] + ['ARBITRARY_REASON'])
def test_conflicting_nse_fallback_rejects_nonproducer_reasons(reason):
    from kronos.intraday.native_pullback_decision import unavailable_source
    _, _, mapping, run = source_fixture('CONFLICTING')
    with pytest.raises(ValueError, match='SOURCE_INTEGRITY_INVALID'):
        unavailable_source(mapping, run.results[0], run.run_identity, reason)


def test_conflicting_full_source_cannot_claim_fallback_reason(tmp_path):
    from kronos.intraday.native_pullback_decision import load_decision_source
    from kronos.intraday.native_structural_selection import create_native_selection
    source, *_ = source_fixture('CONFLICTING')
    store = NativeStructuralStore(tmp_path / 'native')
    decision = retain_decision(store, source, created_at=BOUNDARY)
    changed = create_native_selection(**{**decision.data, 'reasons': ['SOURCE_INTEGRITY_INVALID']})
    with pytest.raises(ValueError, match='SOURCE_INTEGRITY_INVALID'):
        load_decision_source(store, changed, None)
