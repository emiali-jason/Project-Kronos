"""Sponsor-approved 2026-10-11 prospective experimental PAPER method 0.1.0.

All arithmetic is replayed from retained owner-validated Native source. Completed
means the existing governed schedule/candle contract; no official revision/as-of
finality, price execution or predictive utility is asserted by this experiment.
"""
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
import json

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe as TF
from kronos.intraday.native_pullback_decision import decode_source, validate_decision_source
from kronos.intraday.native_pullback_policy import confirmed_pivots
from kronos.intraday.native_structural_selection import create_native_selection
from kronos.intraday.probables_v2_persistence import _from_wire, _to_wire
from kronos.intraday.wo08_assessment import _assessment_values, canonical, digest, moment
from kronos.intraday.wo10_futures_contract import normalize

SCHEMA = 'KRONOS-INTRADAY-WO08-EXPERIMENTAL-ASSESSMENT-V1'
VERSION = '0.1.0'
METHODOLOGY = 'KRONOS-INTRADAY-WO08-EXPERIMENTAL-PULLBACK-PAPER'
CHECKSUM = 'eddf2365be3c22825ccd5b9d1bdb1cb41a91d3a06912ff72e5d72dec6f004b68'
AUTHORITY = 'EXPERIMENTAL_PAPER_ONLY'
METHOD = (METHODOLOGY, VERSION, CHECKSUM)
RULES = {
    'I1': 'ADR0038_EXACT_COMPLETED_1H_AND_NORMAL_15M_DIRECTION_SUPPORT',
    'I2': 'LATEST_TWO_CONSECUTIVE_COMPLETED_5M_POST_Q_STRICT_FOLLOW_THROUGH',
    'I3': 'COMPLETE_FINITE_MODEL_OBSTACLE_CENSUS_STRICT_FORWARD_CORRIDOR',
    'I4': 'EVERY_COMPLETED_15M_AFTER_PULLBACK_RIGHT_CONFIRMATION_STRICTLY_INTACT',
    'I5': 'LATEST_COMPLETED_5M_CLOSE_STRICTLY_INSIDE_SELECTED_PULLBACK_IMPULSE_RANGE',
}
CLASSES = ('PDH_PDL', 'CLASSIC_PIVOTS', 'CPR', 'CURRENT_SESSION_EXTREMES', 'CONFIRMED_15M_PIVOTS')


def _candle(c):
    return dict(identity=c.candle_identity, integrity=c.integrity_identity,
        start=c.candle_start.isoformat(), end=c.candle_end.isoformat(),
        high=str(c.high), low=str(c.low), close=str(c.close),
        source_operation_identity=c.source_operation_identity)


def _coverage(facts, candles, timeframe, *, after=None):
    """Actual DOMAIN008 slots, including shortened final bars; never infer gaps."""
    expected = tuple(b for b in expected_candle_boundaries(facts.current_schedule, timeframe)
        if b.end <= facts.observation_boundary and (after is None or b.start >= after))
    all_slots = {(b.start, b.end) for b in expected_candle_boundaries(facts.current_schedule, timeframe)}
    for c in candles:
        c.__post_init__()
        if (c.canonical_subject_identity != facts.canonical_subject_identity
                or c.market_session_identity != facts.current_schedule.session_id
                or c.timeframe is not timeframe or c.observation_boundary != facts.observation_boundary
                or c.candle_end > facts.observation_boundary or (c.candle_start, c.candle_end) not in all_slots):
            raise ValueError('WO08_EXPERIMENTAL_CANDLE_BINDING_INVALID')
    if (tuple(sorted(candles, key=lambda c:c.candle_start)) != tuple(candles)
            or len({(c.candle_start,c.candle_end) for c in candles}) != len(candles)):
        raise ValueError('WO08_EXPERIMENTAL_CANDLE_POPULATION_INVALID')
    population = {(c.candle_start,c.candle_end):c for c in candles}
    missing = [dict(start=b.start.isoformat(),end=b.end.isoformat()) for b in expected if (b.start,b.end) not in population]
    retained = tuple(population[b.start,b.end] for b in expected if (b.start,b.end) in population)
    return retained, dict(timeframe=timeframe.value, schedule_identity=facts.current_schedule.session_id,
        schedule_source=facts.current_schedule.source_identity, schedule_version=facts.current_schedule.source_version,
        expected_count=len(expected), present_count=len(retained), missing=missing, complete=not missing,
        required_after=None if after is None else after.isoformat())


def _criterion(which, state, *, reasons=(), value=None, evidence=None, coverage=None, sources=()):
    sources=tuple(sources)
    return dict(criterion_id=which, state=state, current_value=(None if value is None else value if type(value) is str else canonical(normalize(value)).decode()), reason_codes=list(reasons),
        rule=RULES[which], source_fact_identities=[s[0] for s in sources],
        source_fact_integrities=[s[1] for s in sources], evidence=normalize(evidence or {}),
        coverage=normalize(coverage or {}), next_reassessment_event='NEXT_LAWFUL_COMPLETED_ORDINARY_ANALYSIS')


def _obstacles(facts, candles, coverage, native):
    """Enumerate every model class before corridor inspection; keep coincidence."""
    previous = facts.previous_session_facts
    previous.__post_init__()
    daily = facts.previous_daily
    valid = (len(daily)==1 and daily[0].market_session_identity==facts.previous_schedule.session_id
        and previous.previous_daily_candle_identity==daily[0].candle_identity
        and previous.target_session_identity==facts.current_schedule.session_id
        and previous.previous_session_identity==facts.previous_schedule.session_id
        and (daily[0].high,daily[0].low,daily[0].close)==(previous.high,previous.low,previous.close))
    if daily:
        daily[0].__post_init__()
    levels = []
    def add(group, name, price, sources):
        row=dict(source_class=group,name=name,price=str(price),sources=sources)
        levels.append(dict(row,identity='WO08-MODEL-LEVEL-'+digest(row)))
    status = {name:'COMPLETE' for name in CLASSES}
    if not valid:
        for group in CLASSES[:3]: status[group]='UNAVAILABLE'
    else:
        day=daily[0]
        sources=[dict(identity=day.candle_identity,integrity=day.integrity_identity),
                 dict(identity=previous.facts_identity,integrity=previous.integrity_identity)]
        add('PDH_PDL','PDH',day.high,sources); add('PDH_PDL','PDL',day.low,sources)
        # The exact Native arithmetic is already checked by its source validator.
        for row in native['target_manifest']['rows']:
            if row['source_class']=='CLASSIC_PIVOTS' and row['reference'] is not None:
                ref=row['reference']; add('CLASSIC_PIVOTS',ref['field'],Decimal(ref['price']),sources)
        if {x['name'] for x in levels if x['source_class']=='CLASSIC_PIVOTS'} != {'R1','R2','R3','R4','S1','S2','S3','S4'}:
            status['CLASSIC_PIVOTS']='UNAVAILABLE'
        p=(previous.high+previous.low+previous.close)/Decimal(3)
        bc=(previous.high+previous.low)/Decimal(2); tc=Decimal(2)*p-bc
        for name,price in (('CPR_PIVOT',p),('CPR_LOWER',min(bc,tc)),('CPR_UPPER',max(bc,tc))):
            add('CPR',name,price,sources)
    if not coverage['complete'] or not candles:
        for group in CLASSES[3:]: status[group]='UNAVAILABLE'
    else:
        for name,field,price in (('SESSION_HIGH','high',max(c.high for c in candles)),
                                 ('SESSION_LOW','low',min(c.low for c in candles))):
            add('CURRENT_SESSION_EXTREMES',name,price,[_candle(c) for c in candles if getattr(c,field)==price])
        pivots=confirmed_pivots(candles)
        for p in pivots:
            triple=candles[p.index-1:p.index+2]
            # Neighbours separated by a scheduled break cannot confirm a pivot.
            if triple[0].candle_end != triple[1].candle_start or triple[1].candle_end != triple[2].candle_start:
                continue
            add('CONFIRMED_15M_PIVOTS',p.kind,p.price,[_candle(c) for c in triple])
        if not any(x['source_class']=='CONFIRMED_15M_PIVOTS' for x in levels):
            status['CONFIRMED_15M_PIVOTS']='COMPLETE_EMPTY'
    return dict(classes=status,levels=levels,coverage=coverage,
                complete=all(v in {'COMPLETE','COMPLETE_EMPTY'} for v in status.values()))


def _evaluate(facts, native):
    long=native['direction']=='LONG'
    cycle=native['cycle']; cs=facts.current_fifteen_minute
    q=next(c for c in cs if c.candle_identity==cycle['qualification_identity'])
    b=Decimal(cycle['pullback']['price']); t=Decimal(cycle['impulse']['price'])
    c15,coverage15=_coverage(facts,cs,TF.FIFTEEN_MINUTES)
    c5,coverage5=_coverage(facts,facts.current_five_minute,TF.FIVE_MINUTES)
    scheduled=[x for x in expected_candle_boundaries(facts.current_schedule,TF.FIVE_MINUTES) if x.end<=facts.observation_boundary]
    latest=scheduled[-2:]
    population={(c.candle_start,c.candle_end):c for c in c5}
    follow=tuple(population[x.start,x.end] for x in latest if (x.start,x.end) in population)
    post=[x for x in scheduled if x.start>=q.candle_end]
    base=dict(qualification=_candle(q),pullback=native['roles']['PULLBACK_STRUCTURAL_LOW' if long else 'PULLBACK_STRUCTURAL_HIGH'],
        impulse=native['roles']['PRIOR_IMPULSE_HIGH' if long else 'PRIOR_IMPULSE_LOW'])
    sources=[(native['native_source_identity'],native['source_integrity'])]
    i2_evidence=dict(base,follow_through=[_candle(c) for c in follow])
    if len(post)<2:
        i2=_criterion('I2','OUTSTANDING',reasons=['POST_QUALIFICATION_COMPLETION_PENDING'],evidence=i2_evidence,coverage=coverage5,sources=sources)
    elif len(latest)<2 or len(follow)!=2:
        i2=_criterion('I2','UNAVAILABLE',reasons=['REQUIRED_COMPLETED_5M_COVERAGE_MISSING'],evidence=i2_evidence,coverage=coverage5,sources=sources)
    else:
        f1,f2=follow
        predicates=dict(F1_AFTER_Q=f1.candle_start>=q.candle_end,CONSECUTIVE=f1.candle_end==f2.candle_start,
            F1_BEYOND_Q=f1.close>q.high if long else f1.close<q.low,
            F2_CONTINUES=f2.close>f1.close if long else f2.close<f1.close,
            F2_INSIDE_PULLBACK=f2.low>b if long else f2.high<b)
        failed=[k for k,v in predicates.items() if not v]
        i2=_criterion('I2','OUTSTANDING' if failed else 'SATISFIED',reasons=failed,value=predicates,evidence=i2_evidence,coverage=coverage5,sources=sources)
    # P is F2, the latest scheduled completed close. A missing latest slot never
    # falls back to an older available candle and never replaces Assessment Price.
    final=population.get((scheduled[-1].start,scheduled[-1].end)) if scheduled else None
    p=None if final is None else final.close
    measurement=None if final is None else dict(_candle(final),kind='ANALYTICAL_COMPLETED_CLOSE_MEASUREMENT',price=str(p))
    census=_obstacles(facts,c15,coverage15,native)
    blockers=[]
    if p is not None:
        blockers=[x for x in census['levels'] if (p<=Decimal(x['price'])<t if long else t<Decimal(x['price'])<=p)]
    forward=p is not None and (p<t if long else p>t)
    i3_evidence=dict(base,measurement=measurement,obstacle_census=census,blocking_levels=blockers)
    if not census['complete'] or p is None:
        i3=_criterion('I3','UNAVAILABLE',reasons=['MODEL_OBSTACLE_POPULATION_INCOMPLETE' if not census['complete'] else 'MEASUREMENT_PRICE_UNAVAILABLE'],evidence=i3_evidence,coverage=coverage15,sources=sources)
    else:
        reasons=(['PRIOR_IMPULSE_NOT_FORWARD'] if not forward else [])+(['MODEL_CORRIDOR_OBSTRUCTED'] if blockers else [])
        i3=_criterion('I3','OUTSTANDING' if reasons else 'SATISFIED',reasons=reasons,value=dict(P=str(p),T=str(t)),evidence=i3_evidence,coverage=coverage15,sources=sources)
    after=moment(cycle['pullback']['confirmation_end'])
    retained,quality_coverage=_coverage(facts,cs,TF.FIFTEEN_MINUTES,after=after)
    breached=[c for c in retained if (c.low<=b if long else c.high>=b)]
    state='OUTSTANDING' if breached else 'SATISFIED' if quality_coverage['complete'] else 'UNAVAILABLE'
    reasons=['SELECTED_PULLBACK_STRUCTURE_BREACHED'] if breached else [] if quality_coverage['complete'] else ['REQUIRED_COMPLETED_15M_COVERAGE_MISSING']
    i4=_criterion('I4',state,reasons=reasons,evidence=dict(base,candles=[_candle(c) for c in retained],breaches=[_candle(c) for c in breached]),coverage=quality_coverage,sources=sources)
    inside=p is not None and (b<p<t if long else t<p<b)
    i5=_criterion('I5','UNAVAILABLE' if p is None else 'SATISFIED' if inside else 'OUTSTANDING',
        reasons=['MEASUREMENT_PRICE_UNAVAILABLE'] if p is None else [] if inside else ['SELECTED_PULLBACK_IMPULSE_RANGE_EXCEEDED_OR_TOUCHED'],
        value=dict(B=str(b),P=None if p is None else str(p),T=str(t)),evidence=dict(base,measurement=measurement),sources=sources)
    return [i2,i3,i4,i5],measurement


def _values(*,run_identity,run_integrity,result,mapping,native,native_source,created_at):
    values=_assessment_values(run_identity=run_identity,run_integrity=run_integrity,result=result,mapping=mapping,native=native,created_at=created_at)
    facts=None
    if native is not None:
        if native_source is None: raise ValueError('WO08_EXPERIMENTAL_NATIVE_SOURCE_REQUIRED')
        validate_decision_source(native,native_source)
        facts,mapped,member,_=decode_source(native_source)
        if mapped!=mapping or member!=result or native_source['run_identity']!=run_identity:
            raise ValueError('WO08_EXPERIMENTAL_NATIVE_SOURCE_BINDING_INVALID')
    elif native_source is not None:
        raise ValueError('WO08_EXPERIMENTAL_UNMAPPED_SOURCE_INVALID')
    original=values['criteria'][0]
    state={'DETERMINISTICALLY_ESTABLISHED':'SATISFIED','DETERMINISTICALLY_NEGATIVE':'OUTSTANDING','UNAVAILABLE':'UNAVAILABLE'}[original['state']]
    i1=_criterion('I1',state,reasons=original['reason_codes'],value=original['current_value'],
        sources=zip(original['source_fact_identities'],original['source_fact_integrities']))
    criteria=[i1]; measurement=None
    if values['hard_gate']!='NONE':
        criteria=[_criterion('I'+str(i),'NOT_APPLICABLE',reasons=[values['hard_gate']]) for i in range(1,6)]
    elif facts is None or native.data['result']!='PULLBACK' or values['phase']=='OPENING':
        reason='NORMAL_15M_STRUCTURE_NOT_ESTABLISHED' if values['phase']=='OPENING' else 'EXACT_NATIVE_PULLBACK_NOT_ESTABLISHED'
        criteria.extend(_criterion('I'+str(i),'UNAVAILABLE',reasons=[reason]) for i in range(2,6))
    else:
        for c in (*facts.previous_daily,*facts.previous_one_hour,*facts.current_one_hour,*facts.current_fifteen_minute,*facts.current_five_minute):c.__post_init__()
        evaluated,measurement=_evaluate(facts,native.data);criteria.extend(evaluated)
    unavailable=any(c['state']=='UNAVAILABLE' for c in criteria)
    values.update(schema_identity=SCHEMA,schema_version=VERSION,methodology_identity=METHODOLOGY,
        methodology_version=VERSION,methodology_checksum=CHECKSUM,authority=AUTHORITY,experimental=True,
        predictive_usefulness='NOT_ESTABLISHED',rules_checksum=digest(RULES),criteria=criteria,
        experimental_measurement=measurement,
        disposition='HARD_GATE' if values['hard_gate']!='NONE' else 'ASSESSMENT_UNAVAILABLE' if unavailable else 'ASSESSMENT_ESTABLISHED',
        failure_stage='UPSTREAM_ADMISSION' if values['hard_gate']!='NONE' else 'SOURCE_COVERAGE' if unavailable else None,
        failure_reason=values['hard_gate'] if values['hard_gate']!='NONE' else 'REQUIRED_CRITERIA_UNAVAILABLE' if unavailable else None,
        provenance=['SPONSOR_IWO_01_02_03_20261011','ADR0038_I1_RETAINED','EXPERIMENTAL_PAPER_ONLY','NO_WO07F_AUTHORITY'])
    values['source_document']['native_source']=native_source
    watch_levels = dict(I2=None,I3=None,corridor_lower=None,corridor_upper=None)
    if measurement is not None and native is not None and native.data['result']=='PULLBACK' and values['hard_gate']=='NONE':
        nd=native.data; long=nd['direction']=='LONG'; cycle=nd['cycle']
        b,t=Decimal(cycle['pullback']['price']),Decimal(cycle['impulse']['price'])
        watch_levels['I2']=nd['roles']['QUALIFICATION_CANDLE_HIGH' if long else 'QUALIFICATION_CANDLE_LOW']['price']
        watch_levels['corridor_lower']=str(min(b,t));watch_levels['corridor_upper']=str(max(b,t))
        blockers=criteria[2]['evidence'].get('blocking_levels',[])
        if blockers: watch_levels['I3']=str((max if long else min)(Decimal(x['price']) for x in blockers))
    values['experimental_watch_levels']=watch_levels
    return values


@lru_cache(maxsize=256)
def _identity_metadata(payload):
    # Payload bytes are immutable and fully validated by the assessment type.
    # Cache only two strings; .data remains a fresh detached projection.
    data = json.loads(payload)
    return data['assessment_identity'], data['integrity_sha256']


@lru_cache(maxsize=256)
def _validate_payload(payload):
    # Pure replay of the complete immutable document. Current owner pointers,
    # session eligibility, first-five claims and clocks are checked elsewhere
    # on every use and are never inputs to this cache.
    d=json.loads(payload)
    if canonical(d)!=payload: raise ValueError('WO08_EXPERIMENTAL_NOT_CANONICAL')
    source=d['source_document']
    if set(source)!={'result','mapping','native','native_source'}: raise ValueError('WO08_EXPERIMENTAL_SOURCE_FIELDS_INVALID')
    expected=_values(run_identity=d['run_identity'],run_integrity=d['run_integrity'],result=_from_wire(source['result']),
        mapping=None if source['mapping'] is None else _from_wire(source['mapping']),
        native=None if source['native'] is None else create_native_selection(**source['native']),
        native_source=source['native_source'],created_at=d['created_at'])
    integrity=digest(expected)
    if d!=dict(expected,assessment_identity='WO08-ASSESSMENT-'+integrity,integrity_sha256=integrity):
        raise ValueError('WO08_EXPERIMENTAL_INTEGRITY_INVALID')


@dataclass(frozen=True,slots=True)
class ExperimentalWo08Assessment:
    payload: bytes

    def __post_init__(self):
        if type(self.payload) is not bytes:
            raise ValueError('WO08_EXPERIMENTAL_NOT_FROZEN')
        _validate_payload(self.payload)

    @property
    def data(self): return json.loads(self.payload)
    @property
    def identity(self): return _identity_metadata(self.payload)[0]
    @property
    def integrity(self): return _identity_metadata(self.payload)[1]


def assess_experimental(**kwargs):
    values=_values(**kwargs);integrity=digest(values)
    return ExperimentalWo08Assessment(canonical(dict(values,assessment_identity='WO08-ASSESSMENT-'+integrity,integrity_sha256=integrity)))
