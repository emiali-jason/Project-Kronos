"""LOCAL-04 synthetic arithmetic/coverage fixtures, never market acceptance."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from kronos.swing.v1.prospective_research import (
    IST, record, origin, GovernedSession, GovernedCalendar, calendar_record,
    FollowupCandle, candle_record, HORIZONS as LEGACY_HORIZONS,
)
from kronos.swing.v1.local_research_outcomes import (
    measure, scenario_touch, aggregate, calendar_window, candle_window, HORIZONS,
)


def case(direction='LONG', local='LONG', disposition='SUPPORT'):
    signal = datetime(2026, 10, 1, 16, tzinfo=IST)
    sessions = tuple(GovernedSession('S'+str(i), 'NSE', (signal+timedelta(days=i)).date(),
        (signal+timedelta(days=i)).replace(hour=9), (signal+timedelta(days=i)).replace(hour=15))
        for i in range(1, 21))
    cal = calendar_record(GovernedCalendar('NSE', 'CAL', '1', signal, signal.date(), sessions[-1].trading_date, sessions))
    candles = tuple(candle_record(FollowupCandle('NSE:TEST:EQ', s.identity, 'C'+str(i), '1',
        s.closes_at+timedelta(minutes=1), str(100+i), str(102+i), str(98+i), True)) for i,s in enumerate(sessions, 1))
    binding=dict(run_identity='RUN',assessment_sha256='a'*64,instrument='TEST',direction=direction)
    original=record('LOCAL_ANALYSIS_ORIGINAL',completed_at=signal.isoformat())
    o=origin(continuity_identity='OBSERVED-TEST', market='NSE',instrument='TEST',contract_identity='NSE:TEST:EQ',
        expiry=None,direction=direction,admitted_at=signal,source_identity='NATIVE',source_version='1',source_sha256='b'*64,
        origin_run_identity='RUN',origin_assessment_sha256='a'*64,native_setup_identity='SETUP',
        contract_binding=dict(canonical_instrument='TEST',exchange='NSE',provider='KITE',segment='NSE',trading_symbol='TEST',instrument_type='EQ',expiry=None))
    body=dict(information_cutoff=signal.isoformat(),summary=dict(frames=[dict(timeframe='1D',values={'close':'100'},observed_boundary=signal.isoformat())]))
    result=dict(binding=binding,method_version='KRONOS-NSE-LOCAL-RESEARCH-1.0',thesis=dict(overall=dict(direction=local,disposition=disposition),scenarios=[]))
    return original,body,result,(cal,),candles,dict(as_of=sessions[-1].closes_at+timedelta(minutes=2),origin=o)


def scenario(direction='LONG'):
    return dict(state='AVAILABLE',reason=None,horizon='SHORT',kind='PULLBACK',direction=direction,structural_radius=1,
        entry_zone={'low':'99','high':'101'},stop_reference={'value':'95' if direction=='LONG' else '105'},
        target_zone={'low':'110' if direction=='LONG' else '90','high':'112' if direction=='LONG' else '92'},
        risk_reward={'conservative_ratio':'1.5'})


def bar(low,high,close='100',session='S1'):
    return candle_record(FollowupCandle('NSE:TEST:EQ',session,session,'1',datetime(2026,10,2,16,tzinfo=IST),close,high,low,True))


@pytest.mark.parametrize('native,local,disposition', [('LONG','LONG','SUPPORT'),('SHORT','SHORT','SUPPORT'),('LONG','SHORT','REJECT'),('SHORT','LONG','CHALLENGE'),('LONG','UNKNOWN','INSUFFICIENT_EVIDENCE')])
def test_matched_clocks_arithmetic_excursions_and_explicit_denominators(native,local,disposition):
    a,b,c,d,e,k=case(native,local,disposition);o=measure(a,b,c,d,e,**k)
    assert LEGACY_HORIZONS==(1,3,5,10) and HORIZONS==(1,3,5,10,20)
    assert len(o['direction'])==10 and o['win_probability'] is None
    for count in HORIZONS:
        n,l=[r for r in o['direction'] if r['horizon_sessions']==count]
        assert Decimal(n['direction_adjusted_pct'])==Decimal(count)*(1 if native=='LONG' else -1)
        assert Decimal(n['candle_mfe_pct'])>=0 and Decimal(n['candle_mae_pct'])<=0
        assert n['due_session']==l['due_session'] and n['status']=='OBSERVED'
        if local=='UNKNOWN':assert l['status']=='ABSTAINED' and l['result'] is None
        else:assert Decimal(l['direction_adjusted_pct'])==Decimal(count)*(1 if local=='LONG' else -1)
    assert all(r['observations']==r['observed']+r['pending']+r['unavailable']+r['abstained'] for r in aggregate([o]))
    assert measure(a,b,c,d,e,**k)==o


@pytest.mark.parametrize('problem,reason', [('missing','EXACT_COMPLETED_CANDLE_UNAVAILABLE'),('wrong_contract','EXACT_COMPLETED_CANDLE_UNAVAILABLE'),('wrong_session','EXACT_COMPLETED_CANDLE_UNAVAILABLE'),('future_capture','EXACT_COMPLETED_CANDLE_UNAVAILABLE'),('incomplete','CANDLE_COVERAGE_INCOMPLETE'),('corporate','CORPORATE_ACTION_COMMON_BASIS_UNAVAILABLE'),('basis','PRICE_BASIS_UNVERIFIED'),('early_capture','CANDLE_CAPTURE_BEFORE_SESSION_CLOSE'),('revision','CANDLE_REVISION_UNRESOLVED')])
def test_unavailable_evidence_never_creates_outcome(problem,reason):
    a,b,c,d,e,k=case();e=list(e);raw=dict(e[0].data)
    if problem=='missing':e=e[1:]
    else:
        if problem=='wrong_contract':raw['exact_contract_identity']='OTHER'
        if problem=='wrong_session':raw['session_identity']='OTHER'
        if problem=='future_capture':raw['retrieved_at']=(k['as_of']+timedelta(days=1)).isoformat()
        if problem=='incomplete':raw['coverage_complete']=False
        if problem=='corporate':raw['corporate_action']=True
        if problem=='basis':raw['price_basis_verified']=False
        if problem=='early_capture':raw['retrieved_at']=a.data['completed_at']
        if problem=='revision':raw.update(supersedes_source_identity='MISSING',revision_reason='revision')
        e[0]=record('CANDLE',**raw)
    o=measure(a,b,c,d,e,**k)
    assert all(r['status']=='UNAVAILABLE' and r['reason']==reason and r['direction_adjusted_pct'] is None for r in o['direction'])


def test_future_revision_does_not_replace_retained_cut_and_valid_revision_is_attributable():
    a,b,c,d,e,k=case();raw=dict(e[0].data);raw.update(source_identity='REV',supersedes_source_identity=raw['source_identity'],revision_reason='official correction',close='103',high='104',retrieved_at=(k['as_of']+timedelta(days=1)).isoformat())
    future=record('CANDLE',**raw)
    assert measure(a,b,c,d,(*e,future),**k)==measure(a,b,c,d,e,**k)
    k['as_of']+=timedelta(days=2)
    o=measure(a,b,c,d,(*e,future),**k)
    assert o['direction'][0]['direction_adjusted_pct']=='3.000000' and future.identity in o['source_records']


@pytest.mark.parametrize('issue', ['missing','future_calendar','contradiction','short_coverage','pending'])
def test_calendar_authority_not_wall_clock(issue):
    a,b,c,d,e,k=case();raw=dict(d[0].data)
    if issue=='missing':d=()
    elif issue=='future_calendar':raw['observed_at']=(k['as_of']+timedelta(days=1)).isoformat();d=(record('CALENDAR',**raw),)
    elif issue=='contradiction':raw['sessions']=[list(s) for s in raw['sessions']];raw['sessions'][0][0]='DIFFERENT';d=(*d,record('CALENDAR',**raw))
    elif issue=='short_coverage':raw['complete_through']=raw['sessions'][9][1];d=(record('CALENDAR',**raw),)
    else:k['as_of']=datetime(2026,10,2,14,tzinfo=IST)
    o=measure(a,b,c,d,e,**k)
    assert all(x['direction_adjusted_pct'] is None for x in o['direction'] if issue!='short_coverage')
    if issue=='short_coverage':assert o['direction'][-1]['reason']=='CALENDAR_HORIZON_NOT_COVERED' and o['direction'][0]['status']=='OBSERVED'
    if issue=='pending':assert o['direction'][0]['status']=='PENDING'


@pytest.mark.parametrize('direction', ['LONG','SHORT'])
def test_entry_and_target_same_coarse_candle_is_ambiguous(direction):
    r=scenario_touch(scenario(direction),[bar('89','113')])
    assert r['status']=='AMBIGUOUS' and r['realized_rr'] is None and r['realized_pnl'] is None


@pytest.mark.parametrize('direction,status,lo,hi,close', [('LONG','TARGET_TOUCH','109','112','111'),('LONG','INVALIDATION_TOUCH','94','98','96'),('SHORT','TARGET_TOUCH','89','93','91'),('SHORT','INVALIDATION_TOUCH','104','108','106')])
def test_later_level_touch_is_not_a_fill_or_realized_rr(direction,status,lo,hi,close):
    r=scenario_touch(scenario(direction),[bar('99','101'),bar(lo,hi,close,'S2')])
    assert r['status']==status and r['entry_session']=='S1' and r['terminal_session']=='S2'
    assert r['realized_rr'] is None and r['realized_pnl'] is None


def test_both_targets_after_entry_still_ambiguous_and_missing_geometry_unavailable():
    assert scenario_touch(scenario(),[bar('99','101'),bar('94','113',session='S2')])['status']=='AMBIGUOUS'
    assert scenario_touch(dict(scenario(),state='UNAVAILABLE',reason='NO_LEVELS'),[])['status']=='UNAVAILABLE'
    assert scenario_touch(scenario(),[bar('102','104','103')])['status']=='ENTRY_NOT_REACHED'
    assert scenario_touch(scenario(),[bar('99','101')])['status']=='ENTRY_TOUCH_ONLY'


def test_exact_origin_and_signal_fences():
    a,b,c,d,e,k=case();bad=dict(k['origin'].data);bad['origin_assessment_sha256']='c'*64;k['origin']=record('ORIGIN',**bad)
    with pytest.raises(ValueError,match='ORIGIN_BINDING'):measure(a,b,c,d,e,**k)
    k['origin']=None
    assert measure(a,b,c,d,e,**k)['direction'][0]['reason']=='EXACT_RESEARCH_ORIGIN_UNAVAILABLE'
    k['as_of']=datetime(2026,9,30,16,tzinfo=IST)
    assert measure(a,b,c,d,e,**k) is None


@pytest.mark.parametrize('state,expected', [('UNKNOWN','UNAVAILABLE'),('AFFECTED','UNAVAILABLE'),('VERIFIED_NO_ACTION','OBSERVED')])
def test_existing_corporate_action_authority_is_reused(state,expected):
    a,b,c,d,e,k=case();e=tuple(record('CANDLE',**{**r.data,'price_basis_verified':False}) for r in e)
    k['basis']=lambda *args:(state,'official-proof')
    o=measure(a,b,c,d,e,**k)
    assert o['direction'][0]['status']==expected and o['basis_identities']==['official-proof']


def test_scenario_windows_are_fixed_and_twenty_sessions_additive():
    a,b,c,d,e,k=case();c['thesis']['scenarios']=[dict(scenario(),horizon=h) for h in ('SHORT','MEDIUM','LONGER')]
    o=measure(a,b,c,d,e,**k)
    assert [s['entry_window_sessions'] for s in o['scenarios']]==[3,10,20]
    assert all(s['realized_pnl'] is None for s in o['scenarios'])


def test_method_versions_do_not_pool_and_rejected_native_positive_is_explicit():
    a,b,c,d,e,k=case('LONG','SHORT','REJECT');first=measure(a,b,c,d,e,**k)
    c=deepcopy(c);c['method_version']='TEST-FUTURE-METHOD';second=measure(a,b,c,d,e,**k)
    groups=aggregate([first,second])
    assert len(groups)==20 and all(g['observations']==1 for g in groups)
    assert all(g['observed_missed_native']==1 for g in groups if g['cohort']=='NATIVE_PAIRED')


def test_scenario_sample_denominators_retain_ambiguity():
    from kronos.swing.v1.local_research_outcomes import scenario_counts
    a,b,c,d,e,k=case();c['thesis']['scenarios']=[scenario()]
    o=measure(a,b,c,d,e,**k);groups=scenario_counts([o])
    assert groups[0]['observations']==1
    assert groups[0]['observations']==groups[0]['pending']+groups[0]['unavailable']+groups[0]['observed']


@pytest.mark.parametrize('bad',[0,-1,'NaN','Infinity',True])
def test_invalid_reference_cannot_manufacture_performance(bad):
    a,b,c,d,e,k=case();b['summary']['frames'][0]['values']['close']=bad
    with pytest.raises(ValueError):measure(a,b,c,d,e,**k)


def test_same_capture_time_revision_is_unresolved_like_canonical_owner():
    a,b,c,d,e,k=case();raw=dict(e[0].data)
    raw.update(source_identity='SAME-TIME-REVISION',supersedes_source_identity=raw['source_identity'],revision_reason='correction')
    # Choose a deterministic content identity whose sort comes after its parent
    # so the test exercises the timestamp guard, not incidental hash ordering.
    for i in range(100):
        raw['source_version']=str(i);revision=record('CANDLE',**raw)
        if revision.identity > e[0].identity:break
    assert revision.identity > e[0].identity
    o=measure(a,b,c,d,(*e,revision),**k)
    assert o['direction'][0]['reason']=='CANDLE_REVISION_UNRESOLVED'


def test_legacy_missing_basis_flag_preserved_and_measured_only_with_owner_proof():
    a,b,c,d,e,k=case();raw=dict(e[0].data);raw.pop('price_basis_verified');legacy=record('CANDLE',**raw)
    original=deepcopy(legacy.data)
    o=measure(a,b,c,d,(legacy,*e[1:]),**k)
    assert o['direction'][0]['reason']=='PRICE_BASIS_UNVERIFIED'
    k['basis']=lambda *args:('VERIFIED_NO_ACTION','GOVERNED-PROOF')
    assert measure(a,b,c,d,(legacy,*e[1:]),**k)['direction'][0]['status']=='OBSERVED'
    assert legacy.data==original and 'price_basis_verified' not in legacy.data
