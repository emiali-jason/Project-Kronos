"""Isolated Sponsor definitions, no market acquisition or production writes."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from kronos.intraday.cpr_context_research import (
    Band, PriceInterval, CprContextError, NOT_ESTABLISHED as NE,
    band_context, price_location, virgin, multi_day_narrow, width_range_statistics,
)
from kronos.application.intraday_cpr_context_research import missing_context

T = datetime(2026, 9, 8, 4, tzinfo=timezone.utc)

def band(low='10', high='20', **kw):
    return Band(**dict(dict(subject='NSE-EQ-X', session='CURRENT', source='SOURCE-C',
                           available_at=T, lower=D(low), upper=D(high)), **kw))

def context(low, high):
    return band_context(band(low, high), band(session='PREVIOUS', source='SOURCE-P'),
                        previous_session='PREVIOUS', boundary=T)

@pytest.mark.parametrize('lo,hi,direction,states', [
    ('11','21','ASCENDING',('OVERLAPPING',)),
    ('9','19','DESCENDING',('OVERLAPPING',)),
    ('21','22','ASCENDING',('NON_OVERLAPPING_ABOVE',)),
    ('8','9','DESCENDING',('NON_OVERLAPPING_BELOW',)),
    ('11','19','MIXED_OR_NOT_DIRECTIONAL',('CURRENT_INSIDE_PREVIOUS',)),
    ('9','21','MIXED_OR_NOT_DIRECTIONAL',('CURRENT_CONTAINS_PREVIOUS',)),
    ('10','20','MIXED_OR_NOT_DIRECTIONAL',('CURRENT_INSIDE_PREVIOUS','CURRENT_CONTAINS_PREVIOUS')),
    ('20','30','ASCENDING',('OVERLAPPING',)),
    ('0','10','DESCENDING',('OVERLAPPING',)),
    ('10','19','MIXED_OR_NOT_DIRECTIONAL',('CURRENT_INSIDE_PREVIOUS',)),
    ('11','20','MIXED_OR_NOT_DIRECTIONAL',('CURRENT_INSIDE_PREVIOUS',)),
    ('10','21','MIXED_OR_NOT_DIRECTIONAL',('CURRENT_CONTAINS_PREVIOUS',)),
])
def test_geometry_and_strict_both_bound_direction(lo, hi, direction, states):
    assert context(lo, hi) == dict(direction=direction, relationships=states)

@pytest.mark.parametrize('changes', [dict(subject='FOREIGN'), dict(session='WRONG'),
                                    dict(available_at=T+timedelta(seconds=1))])
def test_foreign_prior_or_future_rejected(changes):
    with pytest.raises(CprContextError):
        band_context(band(), band(**dict(dict(session='PREVIOUS'), **changes)),
                     previous_session='PREVIOUS', boundary=T)

def test_missing_prior_is_unknown():
    assert band_context(band(), None, previous_session='PREVIOUS', boundary=T)['direction'] == NE

@pytest.mark.parametrize('low,high', [('20','10'),('NaN','20'),('-1','20')])
def test_bad_band(low,high):
    with pytest.raises(CprContextError):band(low,high)

@pytest.mark.parametrize('lo,hi,expected', [
    ('ABOVE','ABOVE','ABOVE'),('BELOW','BELOW','BELOW'),('ABOVE','BELOW','INSIDE'),
    ('AT','BELOW','INSIDE'),('ABOVE','AT','INSIDE'),('AT','AT','INSIDE'),(None,None,NE)])
def test_existing_price_relationship_only(lo,hi,expected):
    assert price_location(lower_relationship=lo,upper_relationship=hi)==expected

@pytest.mark.parametrize('lo,hi',[('BELOW','ABOVE'),('AT','ABOVE'),('LTP','ABOVE')])
def test_invalid_price_relationship(lo,hi):
    with pytest.raises(CprContextError):price_location(lower_relationship=lo,upper_relationship=hi)

def bars(low='21',high='23'):
    return [PriceInterval('NSE-EQ-X','P1',T,T+timedelta(minutes=5),D(low),D(high))]

def virgin_result(prices, windows=None):
    return virgin(band(),active_at=T,boundary=T+timedelta(minutes=5),
                  windows=windows if windows is not None else [(T,T+timedelta(minutes=5))],prices=prices)

@pytest.mark.parametrize('low,high,expected',[('21','23','YES'),('20','23','NO'),
                                            ('0','10','NO'),('0','30','NO'),('11','12','NO')])
def test_virgin_touch_cross_and_no_touch(low,high,expected):
    assert virgin_result(bars(low,high))==expected

def test_missing_coverage_not_false_even_with_touch():
    assert virgin_result([])==NE
    p=replace(bars('11','12')[0],end=T+timedelta(minutes=4))
    assert virgin_result([p])==NE

def test_future_bar_rejected_before_range_access():
    p=replace(bars()[0],end=T+timedelta(minutes=6),high=None)
    with pytest.raises(CprContextError,match='CHRONOLOGY'):virgin_result([p])

@pytest.mark.parametrize('change',[dict(subject='FOREIGN'),dict(source=''),dict(low=D('NaN'))])
def test_virgin_source_invalid(change):
    with pytest.raises(CprContextError):virgin_result([replace(bars()[0],**change)])

def test_virgin_gap_overlap_duplicate_and_governed_break():
    first=replace(bars()[0],end=T+timedelta(minutes=2))
    last=replace(bars()[0],source='P2',start=T+timedelta(minutes=3))
    assert virgin_result([first,last])==NE
    assert virgin_result([first,last],[(T,first.end),(last.start,last.end)])=='YES'
    with pytest.raises(CprContextError):virgin_result([first,first])
    with pytest.raises(CprContextError):virgin_result(bars(),[(T,T+timedelta(minutes=6))])

def sequence():
    # Exact IDs can span an exchange holiday/weekend; dates are not adjacency.
    return {'TUE':('TUE','FRI','X',T,True,'A'),
            'FRI':('FRI','THU','X',T-timedelta(days=4),True,'B'),
            'THU':('THU','WED','X',T-timedelta(days=5),True,'C')}

@pytest.mark.parametrize('sessions',[('TUE','FRI'),('TUE','FRI','THU')])
def test_governed_consecutive_holiday_gap(sessions):
    assert multi_day_narrow(sessions=sessions,evidence=sequence(),subject='X',boundary=T)=='YES'

def test_multiday_missing_not_false():
    e=sequence();del e['THU'];e['TUE']=(*e['TUE'][:4],False,'A')
    assert multi_day_narrow(sessions=('TUE','FRI','THU'),evidence=e,subject='X',boundary=T)==NE
    assert multi_day_narrow(sessions=('TUE','FRI'),evidence=e,subject='X',boundary=T)=='NO'

@pytest.mark.parametrize('index,value',[(1,'WRONG'),(2,'FOREIGN'),(3,T+timedelta(seconds=1)),(4,None),(5,'')])
def test_multiday_binding_and_future(index,value):
    e=sequence();v=list(e['TUE']);v[index]=value;e['TUE']=tuple(v)
    with pytest.raises(CprContextError):multi_day_narrow(sessions=('TUE','FRI'),evidence=e,subject='X',boundary=T)

def test_normalization_ties_zero_variance_and_distinct_concepts():
    rows=[dict(total_width_pct=str(x),prior_range_pct=str(y)) for x,y in [(0,1),(0,10),(2,20)]]
    s=width_range_statistics(rows)
    assert s['count']==3 and 0<s['pearson']<1 and s['spearman']==pytest.approx(.866025403784)
    assert width_range_statistics(rows[:2])['pearson'] is None
    assert width_range_statistics([])['spearman'] is None

@pytest.mark.parametrize('phase',['OPENING','STRUCTURE','ESTABLISHED'])
@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_missing_inventory_preserves_phase_direction_and_source(phase,direction):
    m=NS(canonical_subject_identity='X',analysis_boundary=T,phase=phase,direction=direction,
         semantic_evidence=NS(facts=[NS(family='1D_CONTEXT')]))
    f=NS(canonical_subject_identity='X',observation_boundary=T,previous_daily=(object(),))
    result=missing_context(m,f)
    assert all(v['value']==NE for v in result.values())
    assert (m.phase,m.direction)==(phase,direction)
    f.canonical_subject_identity='FOREIGN'
    with pytest.raises(CprContextError):missing_context(m,f)

def test_expanded_history_and_unexpected_semantics_require_review():
    m=NS(canonical_subject_identity='X',analysis_boundary=T,semantic_evidence=NS(facts=[]))
    f=NS(canonical_subject_identity='X',observation_boundary=T,previous_daily=(1,2))
    with pytest.raises(CprContextError):missing_context(m,f)
    f.previous_daily=(1,);m.semantic_evidence.facts=[NS(family='CPR_LOCATION')]
    with pytest.raises(CprContextError):missing_context(m,f)


def test_virgin_active_boundary_and_generator():
    assert virgin_result(iter(bars())) == 'YES'
    with pytest.raises(CprContextError, match='ACTIVE_BOUNDARY'):
        virgin(band(), active_at=T, boundary=T+timedelta(minutes=5),
               windows=[(T+timedelta(minutes=1), T+timedelta(minutes=5))], prices=[])
    assert virgin(band(), active_at=None, boundary=T, windows=[(T,T)], prices=[]) == NE
