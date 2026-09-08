"""WO-06G exact geometry, chronology, identity and research-boundary qualification."""
import copy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D, localcontext
from types import SimpleNamespace
import pytest
from intraday.test_technical_context_research import window, native_index, native, payload
from kronos.intraday.candle_pattern_research import (
    geometries, measure, ResearchLevel, level_context, PATTERNS, DEFERRED, DEFER, NE, cohort,
)
from kronos.intraday.technical_context_research import ResearchError, TF
from kronos.application.intraday_candle_research import mask_counts, summarize, dependence, verify_input, project, strata


def candles(bars,subject='NSE-EQ-X'):
    w=window(len(bars),subject=subject);cs=[]
    for c,(o,h,l,z) in zip(w.candles,bars):
        cs.append(payload(canonical_subject_identity=c.canonical_subject_identity,exchange=c.exchange,
            market_identity=c.market_identity,market_session_identity=c.market_session_identity,timeframe=c.timeframe,
            candle_start=c.candle_start,candle_end=c.candle_end,open=D(str(o)),high=D(str(h)),low=D(str(l)),close=D(str(z)),
            volume=c.volume,observation_boundary=c.observation_boundary,provider_source_identity=c.provider_source_identity,
            source_operation_identity=c.source_operation_identity,provenance=c.provenance))
    return replace(w,candles=tuple(cs))


def level(w,v=10,name='PDH',**changes):
    args=dict(name=name,subject=w.subject,session=w.schedule.session_id,value=D(v),source='GOVERNED-TEST-LEVEL',
              available_at=w.candles[0].candle_start-timedelta(days=1),boundary=w.boundary)
    args.update(changes);return ResearchLevel(**args)


def test_geometry_independent_arithmetic_oracle():
    g=geometries(candles([(12,20,10,16)]),{})[0][0]
    assert {k:g[k] for k in ('range','body','upper_wick','lower_wick')}==dict(range='10',body='4',upper_wick='4',lower_wick='2')
    assert [g[k] for k in ('body_ratio','upper_wick_ratio','lower_wick_ratio','open_location','close_location')]==['0.4','0.4','0.2','0.2','0.6']
    assert g['body_direction']=='BULLISH' and g['price_authority']=='CANDLE_GEOMETRY_NOT_ASSESSMENT_PRICE'


@pytest.mark.parametrize('bar,direction', [((16,20,10,12),'BEARISH'),((12,20,10,12),'FLAT'),((12,12,12,12),'FLAT')])
def test_direction_and_zero_range(bar,direction):
    g=measure(candles([bar]),{})['latest'];assert g['body_direction']==direction
    if bar[1]==bar[2]:
        assert g['zero_range'] and all(g[k] is None for k in ('body_ratio','upper_wick_ratio','lower_wick_ratio','open_location','close_location'))


@pytest.mark.parametrize('subject',['NSE-INDEX-NIFTY','NSE-INDEX-BANKNIFTY'])
def test_no_index_volume_proxy(subject):
    g=measure(candles([(10,12,9,11)],subject),{})['latest'];assert g['volume'] is None and g['volume_authority']==NE


@pytest.mark.parametrize('bars,present', [
    ([(15,17,11,12),(11,18,10,16)],'BULLISH_BODY_ENGULFING'),
    ([(12,17,11,15),(16,18,10,11)],'BEARISH_BODY_ENGULFING'),
    ([(12,17,11,15),(13,16,12,14)],'INSIDE_BAR'),
    ([(12,17,11,15),(13,17,10,14)],'OUTSIDE_BAR'),
    ([(12,17,11,15),(13,18,11,14)],'OUTSIDE_BAR'),
    ([(12,17,11,15),(13,17,11,14)],'EQUAL_RANGE'),
    ([(12,17,11,15),(13,16,11,14)],'INSIDE_BAR'),
])
def test_exact_pair_definitions(bars,present):
    m=measure(candles(bars),{});assert m['patterns'][present] is True
    assert m['patterns']['FULL_RANGE_ENGULFING']==m['patterns']['OUTSIDE_BAR']
    assert not (m['patterns']['INSIDE_BAR'] and m['patterns']['OUTSIDE_BAR'])


@pytest.mark.parametrize('bars', [[(12,17,11,15),(11,18,10,16)],[(12,17,11,15),(15,17,11,12)],[(12,17,11,12),(11,18,10,16)]])
def test_body_engulf_requires_opposite_nonzero_and_strict_extension(bars):
    assert measure(candles(bars),{})['patterns']['BODY_ENGULFING'] is False


def test_full_range_engulf_is_not_body_engulf():
    m=measure(candles([(12,17,11,15),(13,18,10,14)]),{})['patterns']
    assert m['FULL_RANGE_ENGULFING'] and not m['BODY_ENGULFING']


@pytest.mark.parametrize('n',[0,1])
def test_missing_predecessor_not_false(n):
    m=measure(window(n),{});assert m['patterns']['BODY_ENGULFING'] is None
    assert m['patterns']['INSIDE_BAR'] is None and m['patterns']['EXPANSION'] is None
    assert m['geometry_count']==n


@pytest.mark.parametrize('name',sorted(DEFERRED))
def test_deferred_label_never_invented(name):
    m=measure(candles([(1,100,1,99),(1,1000,1,999)]),{})
    assert m['patterns'][name] is None and m['reasons'][name]==DEFER


@pytest.mark.parametrize('name',['BREAK_RETEST','FAILED_BREAK'])
def test_no_barrier_no_future_confirmation(name):
    assert measure(window(12),{})['patterns'][name] is None


@pytest.mark.parametrize('v,state,event',[(8,'ENTIRELY_ABOVE_LEVEL',False),(14,'ENTIRELY_BELOW_LEVEL',False),
    (9,'INTERSECTS_LEVEL',False),(13,'INTERSECTS_LEVEL',True),(10,'INTERSECTS_LEVEL',True),(11,'INTERSECTS_LEVEL',False)])
def test_exact_level_touch_and_strict_reclaim(v,state,event):
    w=candles([(10,13,9,11)]);r,_=level_context(w,[level(w,v)])
    assert r['PDH']['state']==state
    # Any strict breach and close across the level is geometry, never a sweep label.
    expected=(9<v and 11>v) or (13>v and 11<v)
    assert (r['PDH']['breach_below_reclaim'] or r['PDH']['breach_above_return'])==expected


def test_incomplete_level_set_does_not_establish_absence():
    w=window(1);assert level_context(w,[level(w,100)])[1] is None
    assert level_context(w,[level(w,100,k) for k in ('PDH','PDL','CPR_LOWER','CPR_UPPER','PIVOT')])[1] is False


@pytest.mark.parametrize('change',[dict(subject='FOREIGN'),dict(session='FOREIGN'),dict(boundary=window(1).boundary+timedelta(seconds=1)),
                                    dict(available_at=window(1).boundary)])
def test_level_source_temporal_rejection(change):
    w=window(1)
    with pytest.raises(ResearchError):level_context(w,[level(w,**change)])


@pytest.mark.parametrize('change',[dict(value=D('NaN')),dict(value=D('-1')),dict(name='GUESS_BREAKOUT'),dict(source=''),dict(available_at=None)])
def test_malformed_levels_fail_closed(change):
    with pytest.raises(ResearchError):level(window(1),**change)


def test_duplicate_levels_fail_closed():
    w=window(1)
    with pytest.raises(ResearchError):level_context(w,[level(w),level(w)])


@pytest.mark.parametrize('variant',['gap','duplicate','reverse','future','subject','timeframe','operation','session','integrity'])
def test_source_integrity_time_and_coverage(variant):
    w=window();cs=w.candles
    if variant in {'gap','duplicate','reverse'}:
        cs={'gap':cs[1:],'duplicate':cs+(cs[-1],),'reverse':tuple(reversed(cs))}[variant]
    elif variant in {'session','integrity'}:
        bad=copy.copy(cs[-1]);object.__setattr__(bad,'market_session_identity' if variant=='session' else 'close','FOREIGN' if variant=='session' else D(999));cs=cs[:-1]+(bad,)
    changes={'future':dict(boundary=w.boundary-timedelta(seconds=1)),'subject':dict(subject='FOREIGN'),
             'timeframe':dict(timeframe=TF.FIFTEEN_MINUTES),'operation':dict(operation='FOREIGN')}.get(variant,{})
    with pytest.raises(ValueError):measure(replace(w,candles=cs,**changes),{})


def test_native_same_contract_source_required():
    w=window(subject='MCX-SUBJECT-CRUDE')
    assert measure(w,{})['latest'] is None
    good=measure(w,native_index(w.candles));assert good['latest']['native']['state']=='AVAILABLE'
    assert good['latest']['native']['contract']


def test_native_contract_transition_not_silently_stitched():
    w=window(subject='MCX-SUBJECT-CRUDE')
    idx=native_index(w.candles)
    c=w.candles[1];idx[(c.canonical_subject_identity,'OP',c.timeframe,c.candle_start,c.candle_end)]=[native(c,canonical_contract_identity='MCX-FUT-FOREIGN')]
    assert measure(w,idx)['latest'] is None


def test_geometry_deterministic_under_decimal_context_and_no_mutation():
    w=candles([(10,13,9,11),(9,13,8,12)]);before=copy.deepcopy(w)
    a=measure(w,{})
    with localcontext() as ctx:
        ctx.prec=5;b=measure(w,{})
    assert a==b and w==before and a['consequence']=='NONE'


@pytest.mark.parametrize('bad',[{},dict(research_identity='FOREIGN'),dict(research_identity='WO06F-RESEARCH-415176852e5b3e9e493af5db6259419babbea6b6fc7dac7c610d9cf04926ada3',rows=[])])
def test_upstream_tampering_rejects_before_evidence_read(bad,tmp_path):
    with pytest.raises(ResearchError):verify_input(bad)


def test_projection_requires_original_fact_and_mapping():
    f=SimpleNamespace(canonical_subject_identity='X',observation_boundary=window().boundary)
    m=SimpleNamespace(canonical_subject_identity='Y',analysis_boundary=window().boundary)
    with pytest.raises(ResearchError):project(f,m,{}, {})


def row(subject='X',session='S',eligible=True,admitted=False,shadow=False):
    r=dict(subject=subject,session=session,eligible=eligible,phase='OPENING',direction='LONG',subject_type='NSE_EQUITY',narrow=True,
           baseline=dict(state='LONG_PROBABLE' if admitted else 'NOT_ADMITTED'),counterfactual=dict(state='LONG_PROBABLE' if shadow or admitted else 'NOT_ADMITTED'))
    r['cohort']=cohort(r)
    if eligible:r['candles']={tf:measure(window(),{}) for tf in ('5M','15M','1H')}
    return r


def test_all_population_not_only_admissions_and_unknown_not_zero():
    rows=[row(admitted=True),row(shadow=True),row(),row(eligible=False)]
    s=summarize(rows);assert (s['raw'],s['eligible'],s['unavailable'])==(4,3,1)
    for tf in s['timeframes'].values():
        assert tf['patterns']['HERO_BAHUBALI']==dict(total=3,evaluable=0,unavailable=3,present=0,absent=0)
    assert [r['cohort'] for r in rows]==['A_PRODUCTION_ADMISSION','B_CPR_SOLE_BLOCKED_SHADOW','OTHER','OTHER']


def test_dependence_repeated_subject_session_not_independent():
    rows=[row(),row(),row(subject='Y')];d=dependence(rows)
    assert d['subject_session_groups']==2 and d['raw_observations']==3
    assert d['timeframes']['5M']['OPEN_EQUALS_CLOSE']['evaluable_weight']=='2'
    assert d['independent_outcomes']==NE


def test_mask_truth_table_and_missing_context():
    assert mask_counts([True,False,None])==dict(total=3,evaluable=2,unavailable=1,present=1,absent=1)
    assert strata(row())['vwap_5m']==NE


def level_facts():
    from intraday.test_historical_qualification import _session, _schedule, PREVIOUS_DATE, TARGET_DATE, PREVIOUS_CLOSE, BOUNDARY
    from kronos.intraday.historical_qualification import reconstruct_previous_session_facts
    start=_schedule(PREVIOUS_DATE).windows[0].opens_at
    d=payload(canonical_subject_identity='RELIANCE',exchange='NSE',market_identity='NSE',
        market_session_identity=_schedule(PREVIOUS_DATE).session_id,timeframe=TF.DAILY,candle_start=start,candle_end=PREVIOUS_CLOSE,
        open=D(1380),high=D(1400),low=D(1370),close=D(1390),volume=10,observation_boundary=BOUNDARY,
        provider_source_identity='EXACT-TEST',source_operation_identity='OP',provenance=('TEST',))
    p=reconstruct_previous_session_facts(canonical_identity='RELIANCE',session=_session(),
        previous_daily_candle_identity=d.candle_identity,completed_at=PREVIOUS_CLOSE,high=d.high,low=d.low,close=d.close,
        source_integrity_identity=d.integrity_identity,provenance=('TEST',))
    return SimpleNamespace(previous_session_facts=p,previous_daily=(d,),canonical_subject_identity='RELIANCE',
        current_schedule=_schedule(TARGET_DATE),previous_schedule=_schedule(PREVIOUS_DATE),observation_boundary=BOUNDARY)


def test_level_adapter_reuses_exact_persisted_values_not_new_cpr():
    from kronos.application.intraday_candle_research import levels
    f=level_facts();r={x.name:x for x in levels(f)}
    assert r['PDH'].value==1400 and r['PDL'].value==1370
    assert r['CPR_LOWER'].value==f.previous_session_facts.narrow_cpr.cpr_bottom
    assert r['PIVOT'].source==f.previous_session_facts.narrow_cpr.fact_identity


@pytest.mark.parametrize('variant',['subject','session','boundary','missing_daily','foreign_daily','tampered_previous','tampered_cpr'])
def test_level_adapter_exact_source_proof(variant):
    from kronos.application.intraday_candle_research import levels
    f=level_facts()
    if variant=='subject':f.canonical_subject_identity='FOREIGN'
    if variant=='session':f.current_schedule=f.previous_schedule
    if variant=='boundary':f.observation_boundary+=timedelta(seconds=1)
    if variant=='missing_daily':f.previous_daily=()
    if variant=='foreign_daily':f.previous_daily=(window(1).candles[0],)
    if variant=='tampered_previous':
        p=copy.copy(f.previous_session_facts);object.__setattr__(p,'high',D(9999));f.previous_session_facts=p
    if variant=='tampered_cpr':
        p=copy.deepcopy(f.previous_session_facts);object.__setattr__(p.narrow_cpr,'pivot',D(9999));f.previous_session_facts=p
    from kronos.intraday.historical_qualification import HistoricalQualificationError
    with pytest.raises((ValueError,HistoricalQualificationError)):levels(f)
