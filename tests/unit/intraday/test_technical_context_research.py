"""WO-06F isolated arithmetic, chronology, source integrity and authority tests."""
from dataclasses import replace, asdict
from datetime import datetime, timedelta
from decimal import Decimal as D, localcontext
from zoneinfo import ZoneInfo
import copy
import json
import pytest

from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.intraday.historical_semantic import create_governed_historical_candle_payload as payload
from kronos.intraday.mcx_history import RetainedMcxContractCandle, MCX_HISTORY_AUTHORITY, _identity
from kronos.intraday.technical_context_research import (
    Window, TF, ResearchError, NE, sma, vwap, volume, movement, native_binding, joined, comparison,
)
from kronos.application.intraday_technical_research import verify_original, EXPECTED, summarize, features
from kronos.intraday.population_measurement import identity

T = datetime(2026, 9, 8, tzinfo=ZoneInfo('UTC'))


def window(n=3, *, day=0, prices=None, volumes=None, subject='NSE-EQ-X', tf=TF.FIVE_MINUTES):
    start = T+timedelta(days=day)
    end = start+timedelta(minutes=5*max(n, 1))
    schedule = MarketDaySchedule('NSE', start.date(), 'SESSION-'+str(day), 'UTC',
                                TradingDayStatus.TRADING, (MarketWindow(start, end),), 'FIXTURE', '1')
    boundary = end if n else start
    cs = tuple(payload(canonical_subject_identity=subject, exchange='NSE', market_identity='NSE',
                       market_session_identity=schedule.session_id, timeframe=tf,
                       candle_start=start+timedelta(minutes=5*i), candle_end=start+timedelta(minutes=5*(i+1)),
                       open=D(str(prices[i] if prices else i+10)), high=D(str(prices[i] if prices else i+10))+1,
                       low=D(str(prices[i] if prices else i+10))-1, close=D(str(prices[i] if prices else i+10)),
                       volume=volumes[i] if volumes else 10, observation_boundary=boundary,
                       provider_source_identity='EXACT-FIXTURE', source_operation_identity='OP', provenance=('FIXTURE',))
               for i in range(n))
    return Window(subject, tf, boundary, 'OP', schedule, cs)


@pytest.mark.parametrize('n', [0, 1, 19, 20, 21, 24, 25, 49, 50, 54, 55, 199, 200, 204, 205])
def test_exact_sma_lookback_and_five_bar_slope(n):
    result = sma([window(n)])
    for p in (20, 50, 200):
        actual = result['periods'][str(p)]
        assert (actual['value'] is not None) == (n >= p)
        assert (actual['slope_delta'] is not None) == (n >= p+5)
        if n >= p: assert D(actual['value']) == D(10+n-p+10+n-1)/2
        if n >= p+5: assert D(actual['slope_delta']) == 5
    if n >= 200: assert result['strict_stack'] == 'STRICT_BULLISH'


@pytest.mark.parametrize('prices,stack,side', [([300-i for i in range(205)], 'STRICT_BEARISH','BELOW'),
                                              ([20]*205,'MIXED_OR_EQUAL','AT')])
def test_symmetry_and_equality(prices,stack,side):
    result=sma([window(205,prices=prices)])
    assert result['strict_stack']==stack
    assert result['periods']['20']['price_side']==side


def test_typical_price_weighting_independent_oracle():
    w=window(2,prices=[9,15],volumes=[1,3])
    r=vwap(w,volume_bearing=True)
    assert D(r['value'])==D('13.5')
    assert D(r['slope_delta'])==D('4.5')
    assert D(r['distance'])==D('1.5')
    assert r['side']=='ABOVE'
    assert r['volume']==4
    assert r['tick_vwap_equivalence']=='NONE'


def test_typical_price_is_not_close_only():
    w=window(1)
    c=w.candles[0]
    c=payload(canonical_subject_identity=c.canonical_subject_identity,exchange=c.exchange,market_identity=c.market_identity,
              market_session_identity=c.market_session_identity,timeframe=c.timeframe,candle_start=c.candle_start,
              candle_end=c.candle_end,open=D(10),high=D(19),low=D(7),close=D(10),volume=10,
              observation_boundary=c.observation_boundary,provider_source_identity=c.provider_source_identity,
              source_operation_identity=c.source_operation_identity,provenance=c.provenance)
    r=vwap(replace(w,candles=(c,)),volume_bearing=True)
    assert D(r['value'])==12
    assert r['slope']==NE


@pytest.mark.parametrize('vols,status', [([0,0,0],'ZERO_TOTAL_VOLUME'),([0,0,1],'AVAILABLE'),([1,0,0],'AVAILABLE')])
def test_zero_volume_not_missing_and_no_fabricated_denominator(vols,status):
    r=vwap(window(3,volumes=vols),volume_bearing=True)
    assert r['availability']==status


@pytest.mark.parametrize('subject', ['NSE-INDEX-NIFTY','NSE-INDEX-BANKNIFTY'])
def test_index_meaningful_volume_not_invented(subject):
    w=window(subject=subject)
    assert vwap(w,volume_bearing=False)['availability']=='MEANINGFUL_TRADED_VOLUME_NOT_ESTABLISHED'
    assert volume(w,volume_bearing=False)['change']==NE


def test_vwap_resets_daily_without_previous_session_contamination():
    previous=vwap(window(prices=[100,100,100]),volume_bearing=True)
    current=vwap(window(day=1,prices=[10,10,10]),volume_bearing=True)
    assert previous['value']=='100' and current['value']=='10'


@pytest.mark.parametrize('variant', ['missing_first','missing_middle','missing_last','duplicate','reverse','future'])
def test_bad_coverage_rejected(variant):
    w=window()
    cs=w.candles
    cs={'missing_first':cs[1:],'missing_middle':cs[:1]+cs[2:], 'missing_last':cs[:-1],
        'duplicate':cs+(cs[-1],), 'reverse':tuple(reversed(cs)), 'future':cs}[variant]
    with pytest.raises(ResearchError):
        replace(w,candles=cs,boundary=w.boundary-timedelta(minutes=1) if variant=='future' else w.boundary)


@pytest.mark.parametrize('changes', [dict(subject='FOREIGN'),dict(operation='FOREIGN'),dict(timeframe=TF.FIFTEEN_MINUTES),
                                     dict(boundary=T+timedelta(hours=2))])
def test_cross_binding_rejected(changes):
    with pytest.raises(ResearchError): replace(window(),**changes)


def test_integrity_tampering_rejected():
    w=window()
    bad=copy.copy(w.candles[0]);object.__setattr__(bad,'close',D(999))
    with pytest.raises(ValueError):replace(w,candles=(bad,)+w.candles[1:])


def test_cross_series_and_duplicate_join_rejected():
    with pytest.raises(ResearchError):joined([window(),window(subject='FOREIGN')])
    with pytest.raises(ResearchError):joined([window(),window()])


def test_volume_normalization_uses_prior20_excludes_current():
    r=volume(window(21,volumes=[10]*20+[40]),volume_bearing=True)
    assert r['rolling_mean']=='10' and r['ratio']=='4' and r['change']=='ABOVE'
    assert r['consequence']=='NONE'
    assert volume(window(20),volume_bearing=True)['normalization']=='INSUFFICIENT_POSITIVE_PRIOR_20'
    assert volume(window(21,volumes=[0]+[10]*20),volume_bearing=True)['ratio'] is None


def test_movement_only_immediate_neighbour():
    assert movement(window())['direction']=='LONG'
    assert movement(window(prices=[30,20,10]))['direction']=='SHORT'
    assert movement(window(prices=[10,10,10]))['direction']=='NON_DIRECTIONAL'
    assert movement(window(1))['direction']==NE


def native(c, **changes):
    values=dict(canonical_subject_identity=c.canonical_subject_identity,canonical_contract_identity='MCX-FUT-X-2026',
                provider_record_identity='PROVIDER-INSTRUMENT-RECORD-X',historical_binding_identity='EXACT-HISTORICAL-BINDING',
                domain008_session_identity=c.market_session_identity,calendar_identity='FIXTURE',calendar_version='1',
                timeframe=c.timeframe,source_timestamp=c.candle_start,candle_start=c.candle_start,candle_end=c.candle_end,
                completion_boundary=c.candle_end,open=c.open,high=c.high,low=c.low,close=c.close,volume=c.volume,
                observation_boundary=c.observation_boundary,source_operation_identity='OP',provider_source_identity='EXACT-NATIVE',
                provenance=('FIXTURE',),authority=MCX_HISTORY_AUTHORITY)
    values.update(changes)
    from kronos.intraday.mcx_history import MCX_HISTORY_CANDLE_IDENTITY, MCX_HISTORY_CANDLE_VERSION
    values.update(contract_identity=MCX_HISTORY_CANDLE_IDENTITY,contract_version=MCX_HISTORY_CANDLE_VERSION)
    return RetainedMcxContractCandle(candle_identity=_identity('INTRADAY-MCX-CONTRACT-CANDLE-',values),
                                   integrity_identity=_identity('INTEGRITY-INTRADAY-MCX-CONTRACT-CANDLE-',values),**values)


def native_index(cs, overrides=None):
    return {(c.canonical_subject_identity,'OP',c.timeframe,c.candle_start,c.candle_end):
            [native(c,**(overrides or {}))] for c in cs}


def test_native_exact_binding_and_no_current_contract_fallback():
    cs=window(subject='MCX-SUBJECT-X').candles
    assert native_binding(cs,{})['state']==NE
    assert native_binding(cs,native_index(cs))['state']=='AVAILABLE'
    wrong=native_index(cs,dict(volume=999))
    with pytest.raises(ResearchError,match='MISMATCH'):native_binding(cs,wrong)
    ambiguous=native_index(cs);key=next(iter(ambiguous));ambiguous[key]*=2
    with pytest.raises(ResearchError,match='AMBIGUOUS'):native_binding(cs,ambiguous)
    foreign=native_index(cs);key=next(iter(foreign));foreign[('FOREIGN',)+key[1:]]=foreign.pop(key)
    assert native_binding(cs,foreign)['state']==NE


def test_contract_transition_not_silently_joined():
    cs=window(subject='MCX-SUBJECT-X').candles; index=native_index(cs)
    key=list(index)[-1];index[key]=[native(cs[-1],canonical_contract_identity='MCX-FUT-X-OTHER')]
    assert native_binding(cs,index)['reason']=='NATIVE_CONTRACT_TRANSITION_NOT_JOINED'


def test_fixed_input_determinism_and_decimal_context_isolation():
    w=window(205)
    a=json.dumps([sma([w]),vwap(w,volume_bearing=True)],sort_keys=True)
    with localcontext() as c:
        c.prec=6
        b=json.dumps([sma([w]),vwap(w,volume_bearing=True)],sort_keys=True)
    assert a==b


@pytest.mark.parametrize('a,b,result',[('ABOVE','ABOVE','AGREE'),('ABOVE','BELOW','CONFLICT'),
                                      ('AT','BELOW','EQUALITY_OR_NON_DIRECTIONAL'),(NE,'ABOVE',NE)])
def test_agreement_does_not_force_resolution(a,b,result): assert comparison(a,b)==result


def test_original_integrity_counts_duplicate_and_no_mutation(monkeypatch):
    original=dict(counts=EXPECTED,rows=[dict(source_result=str(i)) for i in range(882)])
    original['research_identity']=identity('WO06E-RESEARCH-',original)
    monkeypatch.setattr("kronos.application.intraday_technical_research.ACCEPTED_CPR_IDENTITY", original["research_identity"])
    before=copy.deepcopy(original)
    assert verify_original(original)==original['research_identity'] and original==before
    bad=copy.deepcopy(original);bad['counts']['sole_cpr']=75
    with pytest.raises(ResearchError):verify_original(bad)
    bad.pop('research_identity');bad['research_identity']=identity('WO06E-RESEARCH-',bad)
    with pytest.raises(ResearchError):verify_original(bad)
    bad=copy.deepcopy(original);bad['rows'][-1]=bad['rows'][0];bad.pop('research_identity')
    bad['research_identity']=identity('WO06E-RESEARCH-',bad)
    with pytest.raises(ResearchError):verify_original(bad)


def test_unavailable_denominator_preserved_in_summary():
    rows=[dict(subject='X',session='S'),dict(subject='X',session='S')]
    r=summarize(rows)
    assert r['observations']==2 and r['eligible']==0 and r['subject_session_groups']==1
    assert r['independence_claim']=='NONE'
    assert all(v=={'INELIGIBLE':2} for v in r['matrices'].values())


def test_forged_native_index_does_not_confer_authority():
    cs=window(subject='MCX-SUBJECT-X').candles
    index=native_index(cs)
    key=next(iter(index))
    index[key]=[native(cs[0],canonical_subject_identity='MCX-SUBJECT-FOREIGN')]
    with pytest.raises(ResearchError,match='MISMATCH'):native_binding(cs,index)
