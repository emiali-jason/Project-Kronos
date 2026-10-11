"""Source-valid exact approved experiment, with isolated governed owner fixtures."""
from datetime import timedelta
from decimal import Decimal
import json
import pytest

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe as TF
from kronos.intraday.native_pullback_decision import source_document, build_decision
from kronos.intraday.probables_v2_refresh import create_discovery_probables_v2_facts
from kronos.intraday.completed_evidence import build_completed_evidence_selection
from kronos.intraday.probables_v2 import (build_semantic_qualification_evidence_v2,
    create_discovery_probables_evidence_v2, evaluate_probables_v2_run)
from kronos.intraday.wo08_experimental import assess_experimental, ExperimentalWo08Assessment
from kronos.intraday.wo08_assessment import canonical,digest
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.market.schedule import MarketDaySchedule,MarketWindow,TradingDayStatus
from tests.unit.intraday.test_native_pullback_policy import START,SESSION,SUBJECT,BARS


def experimental_fixture(direction='LONG', *, minutes=135, rows=None, five_rows=None,
                         missing_five=(), missing_fifteen=(), daily=(125,85,105),
                         subject=SUBJECT, session=SESSION, binding=None, bundle=None,
                         shortened=False):
    """Reusable source/facts/mapping/run/native/assessment, exact completed slots."""
    boundary=START+timedelta(minutes=minutes)
    exchange='MCX' if subject.startswith('MCX-') else 'NSE'
    current=MarketDaySchedule(exchange,START.date(),session,'Asia/Kolkata',TradingDayStatus.TRADING,
        (MarketWindow(START,boundary if shortened else START+timedelta(hours=6,minutes=15)),),'DOMAIN008_ISOLATED','1')
    yesterday=START-timedelta(days=1)
    previous=MarketDaySchedule(exchange,yesterday.date(),'NSE-2026-09-10','Asia/Kolkata',TradingDayStatus.TRADING,
        (MarketWindow(yesterday,yesterday+timedelta(hours=6,minutes=15)),),'DOMAIN008_ISOLATED','1')
    def raw(start,values):
        h,l,c=values
        if direction=='SHORT': h,l,c=300-l,300-h,300-c
        return HistoricalCandle(start,float(c),float(h),float(l),float(c),100)
    all_rows=list(BARS)+[(117,110,116)] if rows is None else rows
    five=[(108,102,106)]*25+[(115,110,114),(117,114,116)] if five_rows is None else five_rows
    facts=create_discovery_probables_v2_facts(universe_member_identity='MEMBER',canonical_subject_identity=subject,
        subject_exchange=exchange,discovery_bundle_identity='BUNDLE' if bundle is None else bundle.bundle_identity,
        observation_boundary_identity='BOUNDARY',observation_boundary=boundary,
        current_schedule=current,previous_schedule=previous,
        previous_daily=(raw(yesterday,daily),),
        previous_one_hour=tuple(raw(yesterday+timedelta(hours=i),(104+i,100+i,102+i)) for i in range(6)),
        current_one_hour=tuple(raw(b.start,(112+i*5,100+i*5,110+i*5)) for i,b in enumerate(expected_candle_boundaries(current,TF.ONE_HOUR)) if b.end<=boundary),
        current_fifteen_minute=tuple(raw(START+timedelta(minutes=15*i),row) for i,row in enumerate(all_rows) if i not in missing_fifteen and i<len(expected_candle_boundaries(current,TF.FIFTEEN_MINUTES)) and expected_candle_boundaries(current,TF.FIFTEEN_MINUTES)[i].end<=boundary),
        current_five_minute=tuple(raw(START+timedelta(minutes=5*i),row) for i,row in enumerate(five) if i not in missing_five and i<len(expected_candle_boundaries(current,TF.FIVE_MINUTES)) and expected_candle_boundaries(current,TF.FIVE_MINUTES)[i].end<=boundary))
    selection=build_completed_evidence_selection(canonical_subject_identity=subject,analysis_boundary=boundary,
        current_schedule=current,previous_schedule=previous,previous_daily=facts.previous_daily,
        previous_one_hour=facts.previous_one_hour,current_one_hour=facts.current_one_hour,
        current_fifteen_minute=facts.current_fifteen_minute,current_five_minute=facts.current_five_minute,provenance=('ISOLATED',))
    semantic=build_semantic_qualification_evidence_v2(selection=selection,narrow_cpr_fact=facts.previous_session_facts.narrow_cpr,
        participation_state='AVAILABLE_SUPPORTING_NON_BLOCKING',provenance=('ISOLATED',))
    mapping=create_discovery_probables_evidence_v2(universe_member_identity='MEMBER',source_discovery_run_identity='DISCOVERY',
        source_discovery_member_identity='MEMBER-RESULT',market_session_identity=session,completed_evidence=selection,
        semantic_evidence=semantic,opening_semantic=None,nifty_relative=None,provenance=('ISOLATED',facts.facts_identity))
    run=evaluate_probables_v2_run(source_discovery_run_identity='DISCOVERY',universe_identity='UNIVERSE',universe_version='1',
        reconciliation_identity='RECONCILIATION',reconciliation_version='1',market_session_identity=session,analysis_boundary=boundary,
        member_evidence=(mapping,),unavailable_members=(),provenance=('ISOLATED',))
    source=source_document(facts,mapping,run.results[0],run.run_identity,mcx_binding=binding,machine_bundle=bundle)
    native=build_decision(source,created_at=boundary)
    record=assess_experimental(run_identity=run.run_identity,run_integrity=run.integrity_identity,
        result=run.results[0],mapping=mapping,native=native,native_source=source,created_at=boundary)
    return source,facts,mapping,run,native,record


def states(record): return [x['state'] for x in record.data['criteria']]


@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_complete_exact_source_five_of_five_mirror(direction):
    *_,record=experimental_fixture(direction)
    assert states(record)==['SATISFIED']*5,record.data
    assert record.data['authority']=='EXPERIMENTAL_PAPER_ONLY'
    assert record.data['trading_authority'] is False
    assert record.data['predictive_usefulness']=='NOT_ESTABLISHED'
    assert ExperimentalWo08Assessment(record.payload)==record
    assert 'assessment_price' not in record.data
    census=record.data['criteria'][2]['evidence']['obstacle_census']
    assert census['complete'] and len(census['classes'])==5
    assert len([x for x in census['levels'] if x['source_class']=='CLASSIC_PIVOTS'])==8
    assert len([x for x in census['levels'] if x['source_class']=='CPR'])==3


@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_pending_post_q_is_outstanding_but_missing_due_bars_unavailable(direction):
    *_,pending=experimental_fixture(direction,minutes=120)
    assert pending.data['criteria'][1]['state']=='OUTSTANDING'
    assert pending.data['criteria'][1]['reason_codes']==['POST_QUALIFICATION_COMPLETION_PENDING']
    *_,missing=experimental_fixture(direction,missing_five=(26,))
    assert missing.data['criteria'][1]['state']=='UNAVAILABLE'
    assert missing.data['criteria'][4]['state']=='UNAVAILABLE'
    assert missing.data['experimental_measurement'] is None


@pytest.mark.parametrize('direction',['LONG','SHORT'])
@pytest.mark.parametrize('which',['F1','F2','B','T'])
def test_strict_equalities_fail(direction,which):
    five=[(108,102,106)]*25+[(115,110,114),(117,114,116)]
    if which=='F1':five[-2]=(115,110,113)
    if which=='F2':five[-1]=(117,110,114)
    if which=='B':five[-1]=(117,99,116)
    if which=='T':five[-1]=(121,114,120)
    *_,record=experimental_fixture(direction,five_rows=five)
    assert record.data['criteria'][4 if which=='T' else 1]['state']=='OUTSTANDING'


@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_obstacle_at_price_blocks_but_target_endpoint_is_excluded(direction):
    *_,record=experimental_fixture(direction,daily=(116,85,100.5))
    blockers=record.data['criteria'][2]['evidence']['blocking_levels']
    assert any(x['name']=='PDH' if direction=='LONG' else x['name']=='PDL' for x in blockers)
    *_,clear=experimental_fixture(direction)
    census=clear.data['criteria'][2]['evidence']['obstacle_census']['levels']
    target='120.0' if direction=='LONG' else '180.0'
    assert len([x for x in census if x['price']==target])>=2
    assert clear.data['criteria'][2]['state']=='SATISFIED'


@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_known_pullback_breach_survives_recovery(direction):
    rows=list(BARS)+[(117,99,116),(118,110,117)]
    five=[(108,102,106)]*28+[(118,113,116),(119,115,117)]
    *_,record=experimental_fixture(direction,minutes=150,rows=rows,five_rows=five)
    assert record.data['criteria'][3]['state']=='OUTSTANDING'
    assert record.data['criteria'][3]['reason_codes']==['SELECTED_PULLBACK_STRUCTURE_BREACHED']
    assert record.data['criteria'][4]['state']=='SATISFIED'


def test_full_session_coverage_missing_cannot_be_clear_model():
    from tests.unit.intraday.test_native_pullback_decision import source_fixture
    source,facts,mapping,run=source_fixture()
    native=build_decision(source,created_at=run.analysis_boundary)
    record=assess_experimental(run_identity=run.run_identity,run_integrity=run.integrity_identity,
        result=run.results[0],mapping=mapping,native=native,native_source=source,created_at=run.analysis_boundary)
    assert record.data['criteria'][2]['state']=='UNAVAILABLE'
    assert record.data['criteria'][2]['reason_codes']==['MODEL_OBSTACLE_POPULATION_INCOMPLETE']
    assert not record.data['criteria'][2]['coverage']['complete']


@pytest.mark.parametrize('path',['criterion','census','native_source'])
def test_rehashed_tampering_cannot_create_authority(path):
    *_,record=experimental_fixture()
    d=record.data
    if path=='criterion':d['criteria'][1]['state']='OUTSTANDING'
    elif path=='census':d['criteria'][2]['evidence']['obstacle_census']['levels'].pop()
    else:d['source_document']['native_source']['run_identity']='OTHER'
    core={k:v for k,v in d.items() if k not in {'assessment_identity','integrity_sha256'}}
    d.update(assessment_identity='WO08-ASSESSMENT-'+digest(core),integrity_sha256=digest(core))
    with pytest.raises(ValueError): ExperimentalWo08Assessment(canonical(d))


def test_shortened_final_schedule_bar_counts_as_completed():
    *_,record=experimental_fixture(minutes=133,shortened=True)
    assert states(record)==['SATISFIED']*5
    assert record.data['criteria'][2]['coverage']['complete']


@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_i3_only_four_of_five_is_source_valid(direction):
    *_,record=experimental_fixture(direction,daily=(118,92,105))
    assert states(record)==['SATISFIED','SATISFIED','OUTSTANDING','SATISFIED','SATISFIED']


@pytest.mark.parametrize('direction',['LONG','SHORT'])
@pytest.mark.parametrize('family',['GOLDM','SILVERM','COPPER','CRUDE','NATGAS'])
def test_mcx_exact_bound_source_and_natgas_gate(direction,family):
    from dataclasses import fields
    from tests.unit.instrument.test_active_derivative_selection import _resolve
    from tests.unit.intraday.test_discovery_runtime import _publications,_bundle
    from kronos.intraday.discovery_runtime import DiscoveryRunBoundary
    from kronos.intraday.discovery import create_machine_fact_bundle
    boundary=START+timedelta(minutes=135)
    subject='MCX-SUBJECT-'+family
    binding=_resolve(boundary).for_subject(subject).binding
    _,reconciliation=_publications()
    member=next(m for m in reconciliation.members if m.canonical_identity==subject)
    bundle=_bundle(member,DiscoveryRunBoundary(boundary,binding.domain008_session_identity,'BOUNDARY'),reconciliation)
    values={f.name:getattr(bundle,f.name) for f in fields(bundle) if f.name!='bundle_identity'}
    values['source_identities']+=(binding.binding_identity,binding.provider_snapshot_identity)
    values['provenance']+=(binding.integrity_identity,binding.domain008_session_identity)
    bundle=create_machine_fact_bundle(**values)
    *_,record=experimental_fixture(direction,subject=subject,session=binding.domain008_session_identity,binding=binding,bundle=bundle)
    assert record.data['exact_mcx_contract_identity']==binding.active_binding.derivative_contract_id
    assert record.data['exact_mcx_roll_lineage']==binding.binding_identity
    if family=='NATGAS':
        assert record.data['hard_gate']=='NATGAS_COMMISSIONING_HELD'
        assert states(record)==['NOT_APPLICABLE']*5
    else: assert states(record)==['SATISFIED']*5


def test_i1_retains_both_exact_fact_identities_and_integrities():
    _,_,mapping,_,_,record=experimental_fixture()
    expected=[mapping.semantic_evidence.fact(family) for family in ('1H_REGIME','15M_STRUCTURE')]
    assert record.data['criteria'][0]['source_fact_identities']==[f.fact_identity for f in expected]
    assert record.data['criteria'][0]['source_fact_integrities']==[f.integrity_identity for f in expected]


def test_experimental_population_persists_and_legacy_type_cannot_decode_it(tmp_path):
    from tests.unit.intraday.test_wo08_assessment import publish
    from kronos.intraday.wo08_assessment import Wo08Assessment
    from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
    run,_,_,owner,records=publish(tmp_path,experimental=True)
    assert len(records)==98 and all(type(r) is ExperimentalWo08Assessment for r in records)
    assert Wo08AssessmentStore(tmp_path).current_run()==records
    assert owner.store._manifest(run.run_identity)[0]['schema_version']=='0.1.0'
    with pytest.raises(ValueError): Wo08Assessment(records[0].payload)


def test_mixed_legacy_and_experimental_publication_is_rejected(tmp_path):
    from tests.unit.intraday.test_wo08_assessment import publish
    from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
    run,_,_,_,old=publish(tmp_path/'old')
    _,_,_,_,new=publish(tmp_path/'new',experimental=True)
    store=Wo08AssessmentStore(tmp_path/'mixed')
    with pytest.raises(ValueError,match='MIXED_METHOD'):
        store.publish(run,(new[0],*old[1:]))
    assert store.current_pointer() is None


def test_missing_retained_native_source_never_accepts_selected_roles_alone():
    _,_,mapping,run,native,_=experimental_fixture()
    with pytest.raises(ValueError,match='NATIVE_SOURCE_REQUIRED'):
        assess_experimental(run_identity=run.run_identity,run_integrity=run.integrity_identity,
            result=run.results[0],mapping=mapping,native=native,native_source=None,created_at=run.analysis_boundary)
