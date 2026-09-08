"""WO-06G deterministic candle geometry; research only, no admission authority.

Definitions are predeclared in the WO-06G research document. Named threshold-
-dependent patterns are deliberately not implemented. Source contracts and
WO-06F completed-session/native-lineage checks are reused unchanged.
"""
from dataclasses import dataclass, replace
from decimal import Decimal as D
from datetime import datetime
from kronos.intraday.technical_context_research import Window, ResearchError, native_binding, decimal_policy, side
from kronos.intraday.population_measurement import identity

POLICY = 'WO06G-COMPLETED-CANDLE-GEOMETRY-V1'
DEFER = 'DEFER_BINARY_THRESHOLD'
NE = 'NOT_ESTABLISHED'
PATTERNS = ('REJECTION', 'BODY_ENGULFING', 'BULLISH_BODY_ENGULFING', 'BEARISH_BODY_ENGULFING',
            'FULL_RANGE_ENGULFING', 'BULLISH_FULL_RANGE_ENGULFING', 'BEARISH_FULL_RANGE_ENGULFING',
            'INSIDE_BAR', 'OUTSIDE_BAR', 'EQUAL_RANGE', 'OPEN_EQUALS_CLOSE', 'INDECISION_GEOMETRY',
            'EXPANSION', 'BODY_DOMINANCE', 'MULTI_CANDLE_REVERSAL', 'CONTINUATION',
            'LEVEL_BREACH_RECLAIM', 'BREAK_RETEST', 'FAILED_BREAK', 'HERO_BAHUBALI')
DEFERRED = frozenset(('REJECTION','INDECISION_GEOMETRY','BODY_DOMINANCE','MULTI_CANDLE_REVERSAL','CONTINUATION','HERO_BAHUBALI'))
CONTINUOUS = ('range','body','upper_wick','lower_wick','body_ratio','upper_wick_ratio',
              'lower_wick_ratio','open_location','close_location','range_ratio','body_expansion_ratio')


def ratio(a, b):
    return None if not b else str(a/b)


@decimal_policy
def geometries(window: Window, retained):
    if type(window) is not Window:
        raise ResearchError('GEOMETRY_WINDOW_REQUIRED')
    replace(window)
    native = native_binding(window.candles, retained) if window.subject.startswith('MCX-') else {'state':'NOT_APPLICABLE'}
    if native['state'] == NE:
        return (), native
    records=[]
    for c in window.candles:
        width=c.high-c.low;body=abs(c.close-c.open)
        upper=c.high-max(c.open,c.close);lower=min(c.open,c.close)-c.low
        r=dict(schema=POLICY,authority='RESEARCH_ONLY',subject=c.canonical_subject_identity,
               native=native,timeframe=c.timeframe.value,session=c.market_session_identity,
               open_time=c.candle_start.isoformat(),close_time=c.candle_end.isoformat(),
               boundary=c.observation_boundary.isoformat(),source=c.candle_identity,integrity=c.integrity_identity,
               operation=c.source_operation_identity,open=str(c.open),high=str(c.high),low=str(c.low),close=str(c.close),
               volume=c.volume if not window.subject.startswith('NSE-INDEX-') else None,
               volume_authority='RAW_MEANINGFUL_VOLUME' if not window.subject.startswith('NSE-INDEX-') else NE,
               range=str(width),body=str(body),body_direction='BULLISH' if c.close>c.open else 'BEARISH' if c.close<c.open else 'FLAT',
               upper_wick=str(upper),lower_wick=str(lower),body_ratio=ratio(body,width),
               upper_wick_ratio=ratio(upper,width),lower_wick_ratio=ratio(lower,width),
               open_location=ratio(c.open-c.low,width),close_location=ratio(c.close-c.low,width),
               zero_range=width==0,price_authority='CANDLE_GEOMETRY_NOT_ASSESSMENT_PRICE')
        r['geometry_identity']=identity('WO06G-GEOMETRY-',r)
        records.append(r)
    return tuple(records),native


@dataclass(frozen=True)
class ResearchLevel:
    name: str
    subject: str
    session: str
    value: D
    source: str
    available_at: datetime
    boundary: datetime

    def __post_init__(self):
        if (self.name not in {'PDH','PDL','CPR_LOWER','CPR_UPPER','PIVOT'} or not self.subject or not self.session or not self.source
                or type(self.value) is not D or not self.value.is_finite() or self.value<0
                or not all(isinstance(t,datetime) and t.utcoffset() is not None for t in (self.available_at,self.boundary))
                or self.available_at>self.boundary):
            raise ResearchError('RESEARCH_LEVEL_INVALID')


def level_context(window, levels):
    if not window.candles or levels is None:
        return {},None
    c=window.candles[-1]
    if len({x.name for x in levels})!=len(levels):raise ResearchError('LEVEL_DUPLICATE')
    result={}
    for level in levels:
        replace(level)
        if (level.subject!=window.subject or level.session!=window.schedule.session_id
                or level.boundary!=window.boundary or level.available_at>c.candle_start):
            raise ResearchError('LEVEL_SOURCE_SESSION_TIME_MISMATCH')
        v=level.value
        result[level.name]=dict(source=level.source,value=str(v),available_at=level.available_at.isoformat(),
            state='ENTIRELY_ABOVE_LEVEL' if c.low>v else 'ENTIRELY_BELOW_LEVEL' if c.high<v else 'INTERSECTS_LEVEL',
            breach_below_reclaim=c.low<v and c.close>v,
            breach_above_return=c.high>v and c.close<v,
            close_distance=str(c.close-v),authority='PRICE_GEOMETRY_NOT_GOVERNED_BREAKOUT')
    any_event=any(v['breach_below_reclaim'] or v['breach_above_return'] for v in result.values())
    complete=set(result)=={'PDH','PDL','CPR_LOWER','CPR_UPPER','PIVOT'}
    return result, True if any_event else False if complete else None


@decimal_policy
def measure(window, retained, levels=None):
    gs,native=geometries(window,retained)
    masks={k:None for k in PATTERNS}
    reasons={k:DEFER if k in DEFERRED else NE for k in PATTERNS}
    result=dict(policy=POLICY,binding=window.binding(),native=native,geometry_count=len(gs),
                geometry_set_identity=identity('WO06G-GEOMETRY-SET-',[g['geometry_identity'] for g in gs]),
                latest=gs[-1] if gs else None,patterns=masks,reasons=reasons,
                ratios={'range_ratio':None,'body_expansion_ratio':None},level_context={},
                previous_close_relation=NE,consequence='NONE')
    if not gs:return result
    c=window.candles[-1]
    masks['OPEN_EQUALS_CLOSE']=c.open==c.close
    lc,event=level_context(window,levels);result['level_context']=lc;masks['LEVEL_BREACH_RECLAIM']=event
    if len(gs)>=2:
        p=window.candles[-2]
        equal=c.high==p.high and c.low==p.low
        inside=c.high<=p.high and c.low>=p.low and not equal
        outside=c.high>=p.high and c.low<=p.low and not equal
        clo,chi=sorted((c.open,c.close));plo,phi=sorted((p.open,p.close))
        opposite=(c.close-c.open)*(p.close-p.open)<0
        body=opposite and clo<=plo and chi>=phi and (clo<plo or chi>phi)
        masks.update(BODY_ENGULFING=body,BULLISH_BODY_ENGULFING=body and c.close>c.open,
                     BEARISH_BODY_ENGULFING=body and c.close<c.open,FULL_RANGE_ENGULFING=outside,
                     BULLISH_FULL_RANGE_ENGULFING=outside and c.close>c.open,
                     BEARISH_FULL_RANGE_ENGULFING=outside and c.close<c.open,
                     INSIDE_BAR=inside,OUTSIDE_BAR=outside,EQUAL_RANGE=equal,EXPANSION=c.high-c.low>p.high-p.low)
        result['ratios']={'range_ratio':ratio(c.high-c.low,p.high-p.low),
                          'body_expansion_ratio':ratio(abs(c.close-c.open),abs(p.close-p.open))}
        result['previous_close_relation']=side(c.close,p.close)
        result['previous_source']=p.candle_identity
    for k,v in masks.items():
        if v is not None:reasons[k]='AVAILABLE'
    return result


def cohort(row):
    """Historical descriptive membership only; no new candidate factory."""
    if row['baseline']['state'].endswith('_PROBABLE'):return 'A_PRODUCTION_ADMISSION'
    if row['eligible'] and row['counterfactual']['state'].endswith('_PROBABLE'):return 'B_CPR_SOLE_BLOCKED_SHADOW'
    return 'OTHER'
