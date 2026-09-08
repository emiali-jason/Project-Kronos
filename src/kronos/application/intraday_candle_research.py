"""Offline WO-06G projection over sealed WO-06F rows; no runtime/write seam."""
from collections import Counter, defaultdict
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from itertools import combinations
from pathlib import Path
from statistics import median
from kronos.application.intraday_population_measurement import IntradayPopulationMeasurement
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.probables_v2_diagnostics_persistence import ProbablesV2DiagnosticsStore
from kronos.intraday.mcx_history import parse_retained_mcx_candle
from kronos.intraday.population_measurement import identity
from kronos.intraday.technical_context_research import Window, TF, ResearchError, decimal_policy
from kronos.intraday.candle_pattern_research import POLICY, NE, PATTERNS, CONTINUOUS, ResearchLevel, measure, cohort

ACCEPTED = 'WO06F-RESEARCH-415176852e5b3e9e493af5db6259419babbea6b6fc7dac7c610d9cf04926ada3'
TIMEFRAMES = ('5M','15M','1H')


def verify_input(original):
    body=dict(original);key=body.pop('research_identity',None)
    if key!=ACCEPTED or key!=identity('WO06F-RESEARCH-',body):
        raise ResearchError('TECHNICAL_INPUT_INTEGRITY_INVALID')
    rows=original['rows']
    if (len(rows)!=882 or len({r['source_result'] for r in rows})!=882
            or sum(r['eligible'] for r in rows)!=572
            or Counter(cohort(r) for r in rows)!=dict(A_PRODUCTION_ADMISSION=33,B_CPR_SOLE_BLOCKED_SHADOW=74,OTHER=775)):
        raise ResearchError('TECHNICAL_COHORT_INVALID')
    return key


def levels(facts):
    """Exact same replay previous-session facts; no independent level reconstruction."""
    p=facts.previous_session_facts;n=p.narrow_cpr
    replace(p);replace(n)
    daily=tuple(facts.previous_daily)
    if len(daily)!=1:raise ResearchError('LEVEL_DAILY_SOURCE_REQUIRED')
    d=daily[0];replace(d)
    if (p.canonical_identity!=facts.canonical_subject_identity or n.canonical_subject_identity!=p.canonical_identity
            or p.target_session_identity!=facts.current_schedule.session_id
            or n.observation_session_identity!=p.target_session_identity
            or p.previous_session_identity!=facts.previous_schedule.session_id
            or n.previous_session_identity!=p.previous_session_identity
            or p.observation_boundary!=facts.observation_boundary or n.observation_boundary!=p.observation_boundary
            or p.previous_daily_candle_identity!=d.candle_identity or n.source_daily_candle_identity!=d.candle_identity
            or p.completed_at!=d.candle_end or (p.high,p.low,p.close)!=(d.high,d.low,d.close)
            or (n.previous_daily_high,n.previous_daily_low,n.previous_daily_close)!=(d.high,d.low,d.close)):
        raise ResearchError('LEVEL_SOURCE_BINDING_INVALID')
    return tuple(ResearchLevel(k,p.canonical_identity,p.target_session_identity,v,
                              p.facts_identity if k in {'PDH','PDL'} else n.fact_identity,p.completed_at,p.observation_boundary)
                 for k,v in [('PDH',p.high),('PDL',p.low),('CPR_LOWER',n.cpr_bottom),('CPR_UPPER',n.cpr_top),('PIVOT',n.pivot)])


def project(facts,mapping,retained,upstream):
    if (facts.canonical_subject_identity!=mapping.canonical_subject_identity
            or facts.observation_boundary!=mapping.analysis_boundary
            or facts.facts_identity!=upstream['facts_identity'] or facts.integrity_identity!=upstream['facts_integrity']
            or mapping.mapping_identity!=upstream['source_mapping']):
        raise ResearchError('FACT_MAPPING_TECHNICAL_BINDING_INVALID')
    replace(facts);replace(mapping)
    operation='INTRADAY-DISCOVERY-V2-SEMANTIC:'+facts.discovery_bundle_identity
    ls=levels(facts)
    out={}
    for key,tf,cs in [('5M',TF.FIVE_MINUTES,facts.current_five_minute),
                      ('15M',TF.FIFTEEN_MINUTES,facts.current_fifteen_minute),('1H',TF.ONE_HOUR,facts.current_one_hour)]:
        w=Window(facts.canonical_subject_identity,tf,facts.observation_boundary,operation,facts.current_schedule,tuple(cs))
        out[key]=measure(w,retained,ls)
    return out


def strata(row):
    t=row.get('context',{});periods=t.get('sma',{}).get('5M',{}).get('periods',{})
    return dict(phase=row['phase'],direction=str(row['direction']),subject_type=row['subject_type'],cohort=row['cohort'],
                narrow=str(row.get('narrow')),sma20_5m=periods.get('20',{}).get('price_side',NE),
                sma50_5m=periods.get('50',{}).get('price_side',NE),vwap_5m=t.get('vwap',{}).get('side',NE),
                volume_5m=t.get('volume',{}).get('normalization',NE))


def mask_counts(values):
    return dict(total=len(values),evaluable=sum(v is not None for v in values),
                unavailable=sum(v is None for v in values),present=sum(v is True for v in values),absent=sum(v is False for v in values))


@decimal_policy
def summarize(rows):
    rs=[r for r in rows if r['eligible']]
    result=dict(raw=len(rows),eligible=len(rs),unavailable=len(rows)-len(rs),timeframes={})
    for tf in TIMEFRAMES:
        ms=[r['candles'][tf] for r in rs]
        patterns={k:mask_counts([m['patterns'][k] for m in ms]) for k in PATTERNS}
        distributions={}
        for field in CONTINUOUS:
            values=[(m['latest'] or {}).get(field,m['ratios'].get(field)) for m in ms]
            ds=sorted(Decimal(v) for v in values if v is not None)
            distributions[field]=dict(available=len(ds),unavailable=len(ms)-len(ds),
                minimum=str(ds[0]) if ds else None,median=str(median(ds)) if ds else None,maximum=str(ds[-1]) if ds else None)
        result['timeframes'][tf]=dict(geometry_evaluable=sum(m['latest'] is not None for m in ms),
            geometry_unavailable=sum(m['latest'] is None for m in ms),completed_candles=sum(m['geometry_count'] for m in ms),
            zero_range=sum(bool(m['latest'] and m['latest']['zero_range']) for m in ms),patterns=patterns,continuous=distributions)
    return result


def dependence(rows):
    rs=[r for r in rows if r['eligible']];groups=Counter((r['subject'],r['session']) for r in rs)
    out=dict(subject_session_groups=len(groups),raw_observations=len(rs),independent_outcomes=NE,timeframes={})
    for tf in TIMEFRAMES:
        out['timeframes'][tf]={k:dict(present_weight=str(sum((Fraction(1,groups[(r['subject'],r['session'])])
            for r in rs if r['candles'][tf]['patterns'][k] is True),Fraction())),
            evaluable_weight=str(sum((Fraction(1,groups[(r['subject'],r['session'])])
            for r in rs if r['candles'][tf]['patterns'][k] is not None),Fraction()))) for k in PATTERNS}
    return out


def analyze(root:Path, original:dict):
    key=verify_input(original)
    populations=IntradayPopulationMeasurement(ProbablesV2Store(root)).history()
    if {p.run.run_identity for p in populations}!={r['run'] for r in original['rows']}:
        raise ResearchError('SOURCE_RUN_MEMBERSHIP_CHANGED')
    envelopes=[ProbablesV2DiagnosticsStore(root).load_envelope(p.stem)
               for p in sorted((root/'refresh-v2/diagnostics/replay-envelopes').glob('*.json'))]
    retained=defaultdict(list)
    for path in sorted((root/'mcx-contract-history-v1').rglob('*.json')):
        m=parse_retained_mcx_candle(path.read_bytes())
        retained[(m.canonical_subject_identity,m.source_operation_identity,m.timeframe,m.candle_start,m.candle_end)].append(m)
    originals={r['source_result']:r for r in original['rows']};rows=[]
    for population in populations:
        run=population.run
        matches=[e for e in envelopes if e.discovery_run.run_identity==run.source_discovery_run_identity
                 and e.methodology_version==run.methodology.methodology_version]
        if len(matches)>1:raise ResearchError('REPLAY_AMBIGUOUS')
        facts={f.canonical_subject_identity:f for f in matches[0].probables_v2_facts} if matches else {}
        if matches and len(facts)!=len(matches[0].probables_v2_facts):raise ResearchError('FACT_DUPLICATE')
        mappings={m.mapping_identity:m for m in population.mappings}
        for source in run.results:
            r=originals.get(source.result_identity)
            if (r is None or r['run']!=run.run_identity or r['subject']!=source.canonical_subject_identity
                    or r['source_mapping']!=source.source_mapping_identity or r['baseline']['state']!=source.state.value
                    or r['boundary']!=source.analysis_boundary.isoformat()):raise ResearchError('SOURCE_RESULT_BINDING_INVALID')
            output={k:r[k] for k in ('run','source_result','subject','session','boundary','phase','direction','methodology',
                                      'subject_type','baseline','counterfactual','eligible','narrow','source_mapping','classification') if k in r}
            output.update(upstream_row_identity=identity('WO06G-UPSTREAM-',r),cohort=cohort(r))
            if r['eligible']:
                f=facts.get(r['subject'])
                if f is None or f.previous_session_facts.narrow_cpr.fact_identity!=r['cpr_fact']:
                    raise ResearchError('CPR_FACT_BINDING_INVALID')
                output['context']={k:r['technical'][k] for k in ('sma','vwap','volume','nifty_relationship','published_participation','structure_15m')}
                output['cpr_context']={k:r[k] for k in ('narrow','cpr_fact','half_width_pct','total_width_pct','prior_range_pct')}
                output['candles']=project(f,mappings[r['source_mapping']],retained,r['technical'])
            rows.append(output)
    if len(rows)!=882 or len({r['source_result'] for r in rows})!=882:raise ResearchError('DENOMINATOR_CHANGED')
    rows.sort(key=lambda r:(r['boundary'],r['run'],r['subject']))
    eligible=[r for r in rows if r['eligible']]
    subsets=dict(all=rows,baseline=[r for r in rows if r['cohort']=='A_PRODUCTION_ADMISSION'],
                 sole_blockers=[r for r in rows if r['cohort']=='B_CPR_SOLE_BLOCKED_SHADOW'],
                 no_cpr=[r for r in rows if r['cohort']!='OTHER'])
    tables={}
    for dimension in strata(eligible[0]):
        tables[dimension]={v:summarize([r for r in eligible if strata(r)[dimension]==v])
                           for v in sorted({strata(r)[dimension] for r in eligible})}
    overlap={tf:{a+' / '+b:sum(r['candles'][tf]['patterns'][a] is True and r['candles'][tf]['patterns'][b] is True for r in eligible)
                 for a,b in combinations(PATTERNS,2)} for tf in TIMEFRAMES}
    result=dict(policy=POLICY,authority='RESEARCH_ONLY',upstream=key,original_counts=original['original_counts'],
                groups={k:summarize(v) for k,v in subsets.items()},strata=tables,overlap=overlap,
                dependence=dependence(rows),rows=rows,predictive_value=NE,assessment_price_backfills=0,
                shadow_assessment_authority_required=True,production_authority='NONE')
    result['research_identity']=identity('WO06G-RESEARCH-',result)
    return result
