"""Commissioned PULLBACK policy tests use isolated, owner-sealed candles."""
from datetime import datetime, timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo
from dataclasses import replace
import pytest
from kronos.intraday.contracts import IntradayTimeframe as TF
from kronos.intraday.historical_semantic import create_governed_historical_candle_payload
from kronos.intraday.native_pullback_policy import select_cycle, confirmed_pivots, Reason, RULES

START=datetime(2026,9,11,9,15,tzinfo=ZoneInfo('Asia/Kolkata'))
BOUNDARY=START+timedelta(hours=6)
SUBJECT='NSE-EQ-LUPIN'
SESSION='NSE-2026-09-11'
# Strict origin L0 at 1; impulse H1 at 3; pullback L2 at 5;
# confirmation at 6; Q at 7. Q's high remains below native H1.
BARS=((104,98,102),(103,90,99),(112,96,110),(120,106,112),
      (114,103,106),(110,99,104),(109,102,106),(113,104,111))

def candles(rows=BARS, direction='LONG', **changes):
    values=[]
    for i,(h,l,c) in enumerate(rows):
        if direction=='SHORT':h,l,c=300-l,300-h,300-c
        kw=dict(canonical_subject_identity=SUBJECT,exchange='NSE',market_identity='NSE',market_session_identity=SESSION,
            timeframe=TF.FIFTEEN_MINUTES,candle_start=START+timedelta(minutes=15*i),
            candle_end=START+timedelta(minutes=15*(i+1)),open=D(c),high=D(h),low=D(l),close=D(c),volume=100,
            observation_boundary=BOUNDARY,provider_source_identity='ISOLATED_PROVIDER_FIXTURE',
            source_operation_identity='ISOLATED_NATIVE_POLICY_TEST',provenance=('ISOLATED',))
        kw.update(changes);values.append(create_governed_historical_candle_payload(**kw))
    return tuple(values)

def select(cs, direction='LONG', **changes):
    kw=dict(subject=SUBJECT,direction=direction,session=SESSION,boundary=BOUNDARY);kw.update(changes)
    return select_cycle(cs,**kw)

@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_complete_cycle_selects_exact_roles_and_first_qualification(direction):
    cs=candles(direction=direction);cycle,reasons=select(cs,direction)
    assert not reasons
    assert [cycle.origin.index,cycle.impulse.index,cycle.pullback.index,cycle.qualification_index]==[1,3,5,7]
    assert cycle.pullback.confirmation_identity==cs[6].candle_identity
    assert cycle.qualification_identity==cs[7].candle_identity
    assert select(cs,direction)==(cycle,reasons)

@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_equal_neighbour_not_a_pivot(direction):
    rows=list(BARS);rows[0]=(104,90,102)
    cs=candles(rows,direction)
    assert not any(p.index==1 for p in confirmed_pivots(cs) if p.kind==('LOW' if direction=='LONG' else 'HIGH'))

@pytest.mark.parametrize('length',range(8))
@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_no_qualification_before_right_confirmation_and_later_q(length,direction):
    cycle,reasons=select(candles(direction=direction)[:length],direction)
    assert cycle is None and reasons

@pytest.mark.parametrize('low',[90,89])
@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_origin_equality_or_breach_through_q_invalidates(low,direction):
    rows=list(BARS);rows[7]=(113,low,111)
    cycle,reasons=select(candles(rows,direction),direction)
    assert cycle is None and Reason.INVALIDATED in reasons

@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_q_requires_strict_previous_extreme_cross(direction):
    rows=list(BARS);rows[7]=(113,104,109)
    cycle,reasons=select(candles(rows,direction),direction)
    assert cycle is None and Reason.RESUMPTION in reasons

@pytest.mark.parametrize('name,value,reason',[
    ('subject','NSE-EQ-OTHER',Reason.INTEGRITY),('session','OTHER',Reason.SESSION),
    ('direction','NON_DIRECTIONAL',Reason.DIRECTION),('boundary',BOUNDARY-timedelta(minutes=1),Reason.BOUNDARY)])
def test_wrong_authority_fails_closed(name,value,reason):
    assert select(candles(),**{name:value})==(None,(reason.value,))

@pytest.mark.parametrize('field,value',[('high',D(999)),('completion_state','FORMING'),('integrity_identity','tampered')])
def test_tampered_payload_fails_closed(field,value):
    cs=list(candles());c=object.__new__(type(cs[0]))
    for f in cs[0].__dataclass_fields__:object.__setattr__(c,f,getattr(cs[0],f))
    object.__setattr__(c,field,value);cs[0]=c
    assert select(cs)==(None,(Reason.INTEGRITY.value,))

@pytest.mark.parametrize('transform',[lambda cs:cs+(cs[-1],),lambda cs:cs[:2]+cs[3:],lambda cs:tuple(reversed(cs))])
def test_duplicate_gap_or_reverse_sources_rejected(transform):
    assert select(transform(candles()))==(None,(Reason.INTEGRITY.value,))

def test_breakout_is_uncommissioned():
    assert RULES['outputs']==['PULLBACK','NOT_ESTABLISHED']
    assert RULES['breakout']=='NOT_COMMISSIONED_V1'

@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_distinct_origins_same_qualification_fail_closed(direction):
    rows=((104,98,102),(103,90,99),(110,98,104),(108,95,103),
          (115,99,110),(120,108,112),(114,104,107),(110,100,104),(109,103,106),(113,105,111))
    assert select(candles(rows,direction),direction)==(None,(Reason.AMBIGUOUS.value,))

@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_newest_full_cycle_not_most_attractive_geometry(direction):
    rows=BARS+((110,97,102),(103,85,97),(114,96,110),(125,107,115),
        (115,103,108),(111,98,104),(110,102,107),(114,105,112))
    c,reasons=select(candles(rows,direction),direction)
    assert not reasons and c.origin.index==9 and c.qualification_index==15

@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_first_q_not_later_more_attractive_q(direction):
    cs=candles(BARS+((119,108,118),),direction)
    c,reasons=select(cs,direction)
    assert not reasons and c.qualification_index==7

@pytest.mark.parametrize('field,value',[('timeframe',TF.FIVE_MINUTES),('market_session_identity','ANOTHER')])
def test_owner_valid_wrong_context(field,value):
    cs=candles(**{field:value})
    assert select(cs)[0] is None
