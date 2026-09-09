"""WO-06H isolated qualification. No production operations or evidence."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from itertools import product
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json
import os
import pytest

from kronos.intraday.live_shadow import *
from kronos.intraday.live_shadow_persistence import ShadowStore
from kronos.intraday.live_shadow_features import classify,snapshot,DEFINITIONS
from kronos.intraday.live_shadow_quote import capture,missing,native_context
from kronos.application.intraday_live_shadow import IntradayLiveShadowService,REQUIRED
from kronos.intraday.runtime_identity import LoadedCapability,create_runtime_manifest,LauncherConfiguration
from kronos.intraday.operation_accounting import ProviderRequestCounter,ProviderRequestCategory as Category
from kronos.provider.contracts.market_data import QuoteSnapshot,OhlcValues
from kronos.intraday.probables_v2 import _encode
from kronos.intraday.population_measurement import identity
from tests.unit.intraday.test_runtime_identity import _seed
from tests.unit.intraday.test_cpr_counterfactual_research import population,facts
from tests.unit.intraday.test_assessment_capture import instrument
from tests.unit.intraday.test_technical_context_research import window

NOW=datetime(2026,9,8,0,1,tzinfo=timezone.utc)


def service(root,now=NOW,accept=True):
    clock=[now];s=IntradayLiveShadowService(store=ShadowStore(root),clock=lambda:clock[0])
    m=create_runtime_manifest(_seed(startup_boundary_at=now),LauncherConfiguration(8947,False),
        tuple(LoadedCapability(n,'1.0.0','a'*64) for n in sorted(REQUIRED)))
    s.bind_runtime(m)
    if accept:s.accept_runtime(expected_revision='a'*40,request_identity='ISOLATED_ACCEPTANCE')
    return s,clock,m


def source_for(result,now=NOW,fault=None):
    index=result.canonical_subject_identity.startswith('NSE-INDEX-')
    record=instrument(segment='INDICES' if index else 'NSE')
    calls=[]
    def quote(r):
        calls.append(r)
        if fault=='failure':raise RuntimeError('SECRET_TOKEN_NOT_RETAINED')
        v=QuoteSnapshot(instrument=r,timestamp=now-timedelta(seconds=1),last_price=100.,volume=100,
                        ohlc=OhlcValues(99.,102.,98.,100.))
        if fault=='foreign':v=replace(v,instrument=instrument('FOREIGN'))
        if fault=='future':v=replace(v,timestamp=now+timedelta(days=1))
        if fault=='missing_time':object.__setattr__(v,'timestamp',None)
        if fault=='zero':object.__setattr__(v,'last_price',0.)
        return v
    s=SimpleNamespace(_admission_records={result.universe_member_identity:(result.canonical_subject_identity,record)},
        _request_counter=ProviderRequestCounter(lambda:now),_lease=SimpleNamespace(quote=quote),
        _active_derivative_resolutions=None,_mcx_history_store=None)
    return s,calls


@pytest.mark.parametrize('direction',['LONG','SHORT'])
@pytest.mark.parametrize('narrow',[False,True])
@pytest.mark.parametrize('prior,five,nifty',list(product(['SUPPORTING','INFORMATIONAL','CONFLICTING'],repeat=3)))
def test_only_cpr_gate_changes_membership(direction,narrow,prior,five,nifty):
    p=population(direction=direction,narrow=narrow,prior=prior,five=five,nifty=nifty)
    before=p.encode();f=next(iter(facts(p).values()));r=p.run.results[0]
    selected,failed=classify(p.run,p.mappings,None,{r.canonical_subject_identity:f})
    expected='CONFLICTING' not in (prior,five,nifty) and 'SUPPORTING' in (prior,five,nifty)
    assert len(selected)==int(expected) and not failed
    if expected:assert selected[0]==(r,COHORT_A if narrow else COHORT_B)
    assert p.encode()==before


@pytest.mark.parametrize('fault',['missing','foreign','tampered'])
def test_sole_blocker_source_fails_closed(fault):
    p=population(narrow=False);f=next(iter(facts(p).values()));subject=p.run.results[0].canonical_subject_identity
    if fault=='foreign':f=next(iter(facts(population(subject='NSE-EQ-FOREIGN')).values()))
    if fault=='tampered':object.__setattr__(f,'pivot',Decimal(999))
    selected,failed=classify(p.run,p.mappings,None,{} if fault=='missing' else {subject:f})
    assert selected==() and failed==(p.run.results[0].result_identity,)


def test_all_production_admissions_retained_with_missing_features():
    p=population();selected,failed=classify(p.run,p.mappings,None,{})
    assert len(selected)==1 and selected[0][1]==COHORT_A
    feature,_=snapshot(None,p.mappings[0],{})
    assert set(feature['values'])==set(FEATURES)
    assert all(feature['values'][tf]['body_ratio'] is None for tf in ('5M','15M'))
    assert 'slope' not in str(feature) and 'score' not in str(feature)


@pytest.mark.parametrize('fault',['failure','foreign','future','missing_time','zero'])
def test_b_quote_failure_missing_without_retry(fault):
    r=population(narrow=False).run.results[0];s,calls=source_for(r,fault=fault)
    value=capture(s,r,operation='ISOLATED',boundary=NOW,clock=lambda:NOW)
    assert value['state']==PRICE_MISSING and value['time'] is None
    assert len(calls)==1 and s._request_counter.snapshot()['actual_provider_requests']==1
    assert 'SECRET' not in str(value)


@pytest.mark.parametrize('subject',['NSE-EQ-RELIANCE','NSE-INDEX-NIFTY','NSE-INDEX-BANKNIFTY'])
def test_same_quote_pair_and_category_exact(subject):
    r=population(subject=subject,narrow=False).run.results[0];s,calls=source_for(r)
    result=capture(s,r,operation='ISOLATED',boundary=NOW,clock=lambda:NOW)
    assert result['price']=='100.0' and result['time']==(NOW-timedelta(seconds=1)).isoformat()
    assert result['time']!=result['received_at'] and len(calls)==1
    categories=dict(s._request_counter.snapshot()['request_categories'])
    assert categories[Category.COHORT_B_SHADOW_OBSERVATION_REQUEST]==1
    assert categories[Category.ASSESSMENT_OBSERVATION_REQUEST]==0
    assert sum(categories.values())==1


@pytest.mark.parametrize('kind',['foreign','index_proxy','future_contract','reference'])
def test_native_binding_rejects_before_quote(kind):
    subject='NSE-INDEX-NIFTY' if kind=='index_proxy' else 'MCX-SUBJECT-CRUDE' if kind=='reference' else 'NSE-EQ-RELIANCE'
    r=population(subject=subject,narrow=False).run.results[0];s,calls=source_for(r)
    canonical,record=s._admission_records[r.universe_member_identity]
    if kind=='foreign':canonical='NSE-EQ-FOREIGN'
    if kind=='index_proxy':record=instrument()
    if kind=='future_contract':record=instrument(kind='FUT')
    s._admission_records[r.universe_member_identity]=(canonical,record)
    assert capture(s,r,operation='ISOLATED',boundary=NOW,clock=lambda:NOW)['state']==PRICE_MISSING
    assert not calls and s._request_counter.snapshot()['actual_provider_requests']==0


def test_constructor_and_status_are_inert(tmp_path):
    s,_,_=service(tmp_path,accept=False)
    for _ in range(5):assert not s.status()['enabled']
    assert list(tmp_path.iterdir())==[]


def test_month_starts_only_at_explicit_acceptance_and_not_restart(tmp_path):
    s,clock,m=service(tmp_path)
    before={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    restored,c2,_=service(tmp_path,now=NOW+timedelta(days=1),accept=False)
    assert restored.status()['enabled'] and restored.status()['window']==s.status()['window']
    assert before=={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    restored.accept_runtime(expected_revision='a'*40,request_identity='ACCEPT_NEW_PROCESS')
    assert restored.status()['window']==s.status()['window']
    clock[0]=instant(s._window.body['end'])
    assert not s.status()['enabled']
    s.accept_runtime(expected_revision='a'*40,request_identity='EOD_COMPLETION_ONLY')
    assert not s.status()['enabled'] and instant(s.status()['window']['end'])==clock[0]


@pytest.mark.parametrize('change',[{'source_state':'DIRTY_WORKTREE'},{'process_id':999999},{'source_revision':'b'*40}])
def test_wrong_runtime_rejected(tmp_path,change):
    s,_,m=service(tmp_path,accept=False)
    s._manifest=create_runtime_manifest(_seed(**change),LauncherConfiguration(8947,False),m.capabilities)
    with pytest.raises(ShadowError):s.accept_runtime(expected_revision='a'*40,request_identity='X')
    assert list(tmp_path.iterdir())==[]


def test_missing_capability_rejected(tmp_path):
    s,_,m=service(tmp_path,accept=False)
    s._manifest=create_runtime_manifest(m.startup,LauncherConfiguration(8947,False),m.capabilities[:-1])
    with pytest.raises(ShadowError):s.accept_runtime(expected_revision='a'*40,request_identity='X')


@pytest.mark.parametrize('day,expected',[(28,28),(29,28),(30,28),(31,28)])
def test_calendar_month_clamps_without_fixed_30_day_clock(day,expected):
    d=datetime(2027,1,day,12,tzinfo=ZoneInfo('Asia/Kolkata'))
    assert next_month(d)==datetime(2027,2,expected,12,tzinfo=d.tzinfo)


def seed_row(s,cohort=COHORT_A,direction='LONG',price='100',subject='NSE-EQ-X'):
    w=window(subject=subject);m=population().mappings[0]
    feature,_=snapshot(None,m,{})
    oid=key('observation',s._window.key,'RUN','RESULT',cohort)
    bid=key('batch',s._window.key,'RUN')
    s.store.retain(artifact('batch',bid,dict(authority='RESEARCH_ONLY',window=s._window.key,run='RUN',
        run_integrity='INTEGRITY',operation='OP',boundary=NOW.isoformat(),recorded_at=NOW.isoformat(),expected={COHORT_A:[oid] if cohort==COHORT_A else [],
        COHORT_B:[oid] if cohort==COHORT_B else []},classification_failures=[])))
    pair=missing('WO06C_ADMISSION_PRICE' if cohort==COHORT_A else 'WO06H_COHORT_B_RESEARCH_QUOTE','UNAVAILABLE')
    if price is not None:pair.update(state='AVAILABLE',price=price,time=NOW.isoformat(),source='SOURCE',integrity='INTEGRITY',received_at=NOW.isoformat(),observation='QUOTE')
    body=dict(authority='RESEARCH_ONLY',window=s._window.key,run='RUN',result='RESULT',mapping='MAPPING',
        source_integrity='INTEGRITY',subject=subject,native=dict(state='NOT_APPLICABLE',contract=None,binding=None),
        session=w.schedule.session_id,schedule=json.loads(_encode(w.schedule)),phase='OPENING',direction=direction,
        methodology='2.2.0',boundary=NOW.isoformat(),captured_at=NOW.isoformat(),runtime=s._manifest.manifest_identity,
        cohort=cohort,assessment=pair,features=feature,grouping='GROUP',baseline_state='PROBABLE' if cohort==COHORT_A else 'REJECTED',
        narrow=cohort==COHORT_A,cpr_source='CPR',intent=key('intent',oid))
    row=artifact('observation',oid,body);s.store.retain(row);s._reconcile()
    return row,w


@pytest.mark.parametrize('direction',['LONG','SHORT'])
@pytest.mark.parametrize('price',['10','12','100',None])
def test_eod_same_schema_direction_missing_and_replay(tmp_path,direction,price):
    s,clock,_=service(tmp_path);row,w=seed_row(s,direction=direction,price=price)
    clock[0]=w.boundary+timedelta(seconds=1)
    result=s.complete_eod(row.key,schedule=w.schedule,candle=w.candles[-1])
    assert (result.body['move_pct'],result.body['state'])==directional_move(direction,price,'12')
    before={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    assert s.complete_eod(row.key,schedule=w.schedule,candle=w.candles[-1])==result
    assert before=={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    ledger=s.monthly_ledger('2026-09');assert len(ledger['rows'])==1
    assert not ledger['final_excel'] and ledger['predictive_value']==NE
    assert 'profit' not in str(ledger).lower() and 'pnl' not in str(ledger).lower()


@pytest.mark.parametrize('bad',['foreign','session','nonterminal','future','forming','tampered','no_assessment_foreign'])
def test_invalid_eod_rejected_and_original_observation_immutable(tmp_path,bad):
    s,clock,_=service(tmp_path);row,w=seed_row(s,price=None if bad=='no_assessment_foreign' else '100')
    clock[0]=w.boundary+timedelta(seconds=1);c=w.candles[-1];schedule=w.schedule
    if bad in {'foreign','no_assessment_foreign'}:c=window(subject='NSE-EQ-FOREIGN').candles[-1]
    if bad=='session':schedule=window(day=1).schedule
    if bad=='nonterminal':c=w.candles[0]
    if bad=='future':clock[0]=NOW
    if bad=='forming':object.__setattr__(c,'candle_end',w.boundary+timedelta(minutes=5))
    if bad=='tampered':object.__setattr__(c,'close',Decimal(999))
    before=row.payload
    with pytest.raises(ShadowError):s.complete_eod(row.key,schedule=schedule,candle=c)
    assert s.store.load('observation',row.key).payload==before and s.store.all('outcome')==()


@pytest.mark.parametrize('cohort',[COHORT_A,COHORT_B])
def test_restoration_and_monthly_completeness(tmp_path,cohort):
    s,_,_=service(tmp_path);row,_=seed_row(s,cohort=cohort,price=None)
    before={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    restored,_,_=service(tmp_path,accept=False)
    assert restored.status()['counts']['assessment_available']==0
    assert restored.status()['counts']['eod_available']==0
    assert restored.status()['enabled']
    assert len(restored.monthly_ledger('2026-09')['rows'])==1
    assert before=={p:p.read_bytes() for p in tmp_path.rglob('*.json')}


def test_atomic_immutable_and_conflicting_records(tmp_path):
    s,_,_=service(tmp_path);row,_=seed_row(s)
    assert s.store.retain(row) is False
    b=row.body;b['direction']='SHORT'
    with pytest.raises(ShadowError,match='CONFLICT'):s.store.retain(artifact('observation',row.key,b))
    assert s.store.load('observation',row.key)==row
    assert not list(tmp_path.rglob('*.tmp'))
    copy=row.body;copy['direction']='SHORT';assert row.body['direction']=='LONG'


@pytest.mark.parametrize('where',['root','ancestor','kind','leaf'])
def test_symlink_containment(tmp_path,where):
    safe=tmp_path/'safe';safe.mkdir();external=tmp_path/'external';external.mkdir()
    if where=='root':
        root=tmp_path/'linked';root.symlink_to(safe,target_is_directory=True)
        with pytest.raises(ShadowError):ShadowStore(root).all('window')
    elif where=='ancestor':
        link=tmp_path/'linked';link.symlink_to(safe,target_is_directory=True)
        with pytest.raises(ShadowError):ShadowStore(link/'child').all('window')
    else:
        s,_,_=service(safe);row,_=seed_row(s)
        if where=='kind':
            target=s.store.root/'observation';target.rename(safe/'old');target.symlink_to(external,target_is_directory=True)
        else:
            target=s.store.root/'observation'/(row.key+'.json');target.unlink();target.symlink_to(external/'missing')
        with pytest.raises((ShadowError,OSError)):s.store.all('observation')
    assert list(external.iterdir())==[]


@pytest.mark.parametrize('identifier',['../x','/tmp/x','WO06H-WINDOW-../x','x.json',''])
def test_path_traversal_rejected(tmp_path,identifier):
    with pytest.raises(ShadowError):ShadowStore(tmp_path).load('window',identifier)


@pytest.mark.parametrize('missing_gate',['closed','reconciled','excel_exists','excel_integrity','excel_readable'])
def test_retention_requires_each_finalization_gate(missing_gate):
    gates=dict(closed=True,reconciled=True,excel_exists=True,excel_integrity=True,excel_readable=True,conflicts=0)
    gates[missing_gate]=False
    assert not retention_eligible('2026-09',datetime(2026,10,6,tzinfo=timezone.utc),**gates)


@pytest.mark.parametrize('day,eligible',[(1,False),(5,False),(6,True),(31,True)])
def test_retention_calendar_grace(day,eligible):
    gates=dict(closed=True,reconciled=True,excel_exists=True,excel_integrity=True,excel_readable=True,conflicts=0)
    assert retention_eligible('2026-09',datetime(2026,10,day,tzinfo=timezone.utc),**gates)==eligible
    assert not retention_eligible('2026-10',datetime(2026,10,day,tzinfo=timezone.utc),**gates)
    assert not retention_eligible('2026-09',datetime(2026,10,day,tzinfo=timezone.utc),**(gates|{'conflicts':1}))


def test_unfinished_intent_cannot_reclaim_quote(tmp_path):
    s,_,_=service(tmp_path);oid=key('observation','X');iid=key('intent',oid)
    body=dict(authority='RESEARCH_ONLY',observation=oid,window=s._window.key,run='RUN',result='RESULT',cohort=COHORT_B,operation='OP',requested_at=NOW.isoformat())
    v=artifact('intent',iid,body)
    assert s.store.retain(v,claim=True)
    body['requested_at']=(NOW+timedelta(seconds=1)).isoformat()
    assert not s.store.retain(artifact('intent',iid,body),claim=True)
    assert s.store.load('intent',iid)==v


def test_unexpected_schema_fields_and_feature_values_rejected(tmp_path):
    s,_,_=service(tmp_path);row,_=seed_row(s)
    b=row.body;b['secret']='MUST_NOT_STORE'
    with pytest.raises(ShadowError):artifact('observation',row.key,b)
    b=row.body;b['features']['values']['5M']['body_ratio']='1.1'
    with pytest.raises(ShadowError):artifact('observation',row.key,b)


def test_two_process_intent_claim_is_exactly_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    s,_,_=service(tmp_path);oid=key('observation','X');iid=key('intent',oid)
    v=artifact('intent',iid,dict(authority='RESEARCH_ONLY',observation=oid,window=s._window.key,run='RUN',result='RESULT',cohort=COHORT_B,operation='OP',requested_at=NOW.isoformat()))
    with ThreadPoolExecutor(2) as pool:
        result=list(pool.map(lambda _:ShadowStore(tmp_path).retain(v,claim=True),range(2)))
    assert sorted(result)==[False,True]


@pytest.mark.parametrize('subject',['MCX-SUBJECT-CRUDE','MCX-SUBJECT-NATGAS','MCX-SUBJECT-GOLDM','MCX-SUBJECT-SILVERM','MCX-SUBJECT-COPPER'])
def test_generic_mcx_governed_contract_quote(subject):
    from tests.unit.instrument.test_active_derivative_selection import _resolve
    from tests.unit.intraday.test_discovery_source import OBSERVED
    from kronos.provider.contracts.instrument import InstrumentRecord
    resolutions=_resolve(OBSERVED);binding=resolutions.for_subject(subject).binding
    assert binding is not None
    record=InstrumentRecord(provider='KITE',exchange=binding.exchange,segment=binding.segment,
        trading_symbol=binding.provider_symbol,name=binding.provider_contract_family,instrument_type=binding.provider_instrument_type,
        expiry=binding.contract_expiry,tick_size=binding.tick_size,lot_size=binding.lot_size)
    result=SimpleNamespace(canonical_subject_identity=subject,universe_member_identity='MEMBER',result_identity='RESULT')
    calls=[]
    def quote(r):
        calls.append(r);return QuoteSnapshot(r,OBSERVED,100.,10,OhlcValues(100.,102.,98.,99.))
    source=SimpleNamespace(_admission_records={'MEMBER':(subject,record)},_active_derivative_resolutions=resolutions,
        _request_counter=ProviderRequestCounter(lambda:OBSERVED),_lease=SimpleNamespace(quote=quote))
    _,native=native_context(source,result,OBSERVED)
    assert native['contract']==binding.active_binding.derivative_contract_id
    assert native['binding']==binding.binding_identity
    pair=capture(source,result,operation='OP',boundary=OBSERVED,clock=lambda:OBSERVED)
    assert pair['state']=='AVAILABLE' and len(calls)==1
    source._admission_records['MEMBER']=(subject,replace(record,trading_symbol='FOREIGN'))
    assert capture(source,result,operation='OP',boundary=OBSERVED,clock=lambda:OBSERVED)['state']==PRICE_MISSING
    assert len(calls)==1
    with pytest.raises(ShadowError):native_context(source,result,OBSERVED+timedelta(days=1))


@pytest.mark.parametrize('bad',['missing','foreign_contract','foreign_subject','tampered'])
def test_eod_mcx_requires_exact_native_contract_proof(tmp_path,bad):
    from tests.unit.intraday.test_technical_context_research import native_index,native
    s,clock,_=service(tmp_path);row,w=seed_row(s,subject='MCX-SUBJECT-X')
    # Fixture replaces the initial test artifact before qualification, not a runtime revision.
    p=s.store.root/'observation'/(row.key+'.json');p.unlink()
    b=row.body;b['native']=dict(state='AVAILABLE',contract='MCX-FUT-X-2026',binding='BINDING')
    row=artifact('observation',row.key,b);s.store.retain(row)
    clock[0]=w.boundary+timedelta(seconds=1)
    retained=native_index(w.candles)
    if bad=='missing':retained={}
    if bad=='foreign_contract':retained=native_index(w.candles,dict(canonical_contract_identity='MCX-FUT-FOREIGN'))
    if bad=='foreign_subject':retained=native_index(w.candles,dict(canonical_subject_identity='MCX-SUBJECT-FOREIGN'))
    if bad=='tampered':object.__setattr__(next(iter(retained.values()))[0],'close',Decimal(999));retained={list(retained)[0]:next(iter(retained.values()))}
    with pytest.raises(ShadowError):s.complete_eod(row.key,schedule=w.schedule,candle=w.candles[-1],retained=retained)
    result=s.complete_eod(row.key,schedule=w.schedule,candle=w.candles[-1],retained=native_index(w.candles))
    assert result.body['native']['contract']==result.body['eod_native']['contract']=='MCX-FUT-X-2026'


def test_b_quote_inner_pair_tamper_rejected_even_after_outer_rehash(tmp_path):
    s,_,_=service(tmp_path);row,_=seed_row(s,cohort=COHORT_B,price=None)
    r=population(narrow=False).run.results[0];src,_=source_for(r)
    pair=capture(src,r,operation='OP',boundary=NOW,clock=lambda:NOW)
    b=row.body;b['assessment']=pair
    artifact('observation',row.key,b)
    b['assessment']['price']='999'
    with pytest.raises(ShadowError):artifact('observation',row.key,b)


def test_failed_window_publication_cannot_leave_accepted_memory_pointer(tmp_path,monkeypatch):
    s,_,_=service(tmp_path,accept=False)
    monkeypatch.setattr(s.store,'retain',Mock(side_effect=OSError('ISOLATED')))
    with pytest.raises(OSError):s.accept_runtime(expected_revision='a'*40,request_identity='FAIL')
    assert s._window is None and not s.status()['enabled']


def test_monthly_reconciliation_is_scoped_to_requested_month(tmp_path):
    s,_,_=service(tmp_path);seed_row(s)
    assert s.monthly_ledger('2026-09')['reconciliation']['expected_a']==1
    assert s.monthly_ledger('2026-10')['reconciliation']['expected_a']==0
    assert s.monthly_ledger('2026-10')['rows']==[]


def test_replacement_runtime_must_preserve_frozen_calculation_capability(tmp_path):
    s,_,m=service(tmp_path);window_bytes=s._window.payload
    restored=IntradayLiveShadowService(store=ShadowStore(tmp_path),clock=lambda:NOW)
    caps=tuple(replace(c,implementation_digest='b'*64) if c.identity=='WO_06H_LIVE_SHADOW' else c for c in m.capabilities)
    restored.bind_runtime(create_runtime_manifest(m.startup,LauncherConfiguration(8947,False),caps))
    with pytest.raises(ShadowError,match='FROZEN_IMPLEMENTATION'):restored.accept_runtime(expected_revision='a'*40,request_identity='CHANGED')
    assert restored._window.payload==window_bytes and not restored.status()['enabled']


def test_failed_quote_retains_known_request_time_without_inventing_response():
    r=population(narrow=False).run.results[0];s,calls=source_for(r,fault='failure')
    value=capture(s,r,operation='OP',boundary=NOW,clock=lambda:NOW)
    assert value['requested_at']==NOW.isoformat() and value['received_at'] is None
    assert value['time'] is None and len(calls)==1
