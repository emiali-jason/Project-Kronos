"""WO-06H adapts frozen WO-06E/F/G functions; no new analytical formula."""
from dataclasses import replace
from kronos.intraday.live_shadow import COHORT_A,COHORT_B,NE,FEATURES,CANDLE_FIELDS,ShadowError
from kronos.intraday.population_measurement import MeasurementPopulation,ADMITTED,identity
from kronos.intraday.cpr_counterfactual_research import _decision,_validate_cpr,Decision,REVIEWED_EVALUATOR_SHA256
from kronos.intraday.probables_v2 import _evaluate_member
from kronos.intraday.technical_context_research import Window,TF,native_binding,sma,vwap,POLICY,VWAP_POLICY
from kronos.intraday.candle_pattern_research import measure,POLICY as GEOMETRY_POLICY

DEFINITIONS={'technical':POLICY,'vwap':VWAP_POLICY,'geometry':GEOMETRY_POLICY,'selection':'WO06H-MINIMUM-SHADOW-V1'}


def classify(run,mappings,assessment,facts):
    population=MeasurementPopulation(run,tuple(mappings),assessment)
    if run.methodology.methodology_version!='2.2.0':raise ShadowError('SHADOW_METHODOLOGY_UNSUPPORTED')
    mapped={m.mapping_identity:m for m in population.mappings};selected=[];failed=[]
    for result in run.results:
        if result.state in ADMITTED:selected.append((result,COHORT_A));continue
        if result.source_mapping_identity is None or result.state.value=='UNAVAILABLE':continue
        m=mapped[result.source_mapping_identity]
        try:
            _validate_cpr(m,facts[result.canonical_subject_identity])
            before=_decision(m,require_cpr=True);actual=_evaluate_member(m)
            baseline=Decision(result.state,result.direction,result.reasons)
            if before!=baseline or Decision(actual.state,actual.direction,actual.reasons)!=baseline:
                raise ShadowError('SHADOW_BASELINE_MISMATCH')
            after=_decision(m,require_cpr=False)
            if after.admitted and not before.admitted and not m.semantic_evidence.narrow_cpr_qualified:
                if after.direction!=result.direction:raise ShadowError('SHADOW_DIRECTION_MISMATCH')
                selected.append((result,COHORT_B))
        except Exception:failed.append(result.result_identity)
    return tuple(selected),tuple(failed)


def snapshot(facts,mapping,retained):
    values=dict(sma20_side=NE,sma50_side=NE,vwap_side=NE,nifty_relationship=NE,local_structure=NE)
    for tf in ('5M','15M'):values[tf]={k:NE if k=='pair_range' else None for k in CANDLE_FIELDS}
    sources={};unavailable=[];native={'state':NE}
    if facts is None:
        unavailable=['FACTS_NOT_RETAINED']
    else:
        try:
            replace(facts);replace(mapping)
            if (facts.canonical_subject_identity!=mapping.canonical_subject_identity or facts.observation_boundary!=mapping.analysis_boundary):
                raise ShadowError('SHADOW_FEATURE_BINDING_INVALID')
            exact={c.candle_identity:c for name in ('previous_daily','previous_one_hour','current_one_hour','current_fifteen_minute','current_five_minute') for c in getattr(facts,name)}
            if any(exact.get(x.candle.candle_identity)!=x.candle for x in mapping.completed_evidence.selected_candles):
                raise ShadowError('SHADOW_SELECTED_FACTS_MISMATCH')
            operation='INTRADAY-DISCOVERY-V2-SEMANTIC:'+facts.discovery_bundle_identity
            if mapping.nifty_relative is not None:values['nifty_relationship']=str(mapping.nifty_relative.relationship)
            try:values['local_structure']=mapping.semantic_evidence.fact('15M_STRUCTURE').direction.value
            except Exception:unavailable.append('LOCAL_STRUCTURE_NOT_ESTABLISHED')
            for tf,frame,cs in [('5M',TF.FIVE_MINUTES,facts.current_five_minute),('15M',TF.FIFTEEN_MINUTES,facts.current_fifteen_minute)]:
                try:
                    w=Window(facts.canonical_subject_identity,frame,facts.observation_boundary,operation,facts.current_schedule,tuple(cs))
                    m=measure(w,retained);sources[tf]=m['binding'];native=m['native'] if tf=='5M' else native
                    if m['latest']:
                        g=m['latest']
                        if g['range']=='0':unavailable.append(tf+'_ZERO_RANGE')
                        values[tf]={k:g.get(k,m['ratios'].get(k)) for k in CANDLE_FIELDS[:-1]}
                        ps=m['patterns'];values[tf]['pair_range']=('INSIDE' if ps['INSIDE_BAR'] else 'OUTSIDE' if ps['OUTSIDE_BAR'] else 'EQUAL' if ps['EQUAL_RANGE'] else 'OTHER' if ps['INSIDE_BAR'] is not None else NE)
                    else:unavailable.append(tf+'_GEOMETRY_NOT_ESTABLISHED')
                    if tf=='5M' and native['state']!=NE:
                        try:
                            s=sma([w]);values['sma20_side']=s['periods']['20']['price_side'];values['sma50_side']=s['periods']['50']['price_side']
                        except Exception:unavailable.append('SMA_NOT_ESTABLISHED')
                        try:
                            v=vwap(w,volume_bearing=not facts.canonical_subject_identity.startswith('NSE-INDEX-'));values['vwap_side']=v.get('side',NE)
                        except Exception:unavailable.append('VWAP_NOT_ESTABLISHED')
                except Exception:unavailable.append(tf+'_SOURCE_NOT_ESTABLISHED')
        except Exception:unavailable.append('FEATURE_BINDING_NOT_ESTABLISHED')
    availability={name:('AVAILABLE' if value!=NE else NE) if not isinstance(value,dict) else {k:('AVAILABLE' if v is not None and v!=NE else NE) for k,v in value.items()} for name,value in values.items()}
    body=dict(definitions=DEFINITIONS,values=values,availability=availability,sources=sources,unavailable=sorted(unavailable))
    return dict(identity=identity('WO06H-FEATURE-',body),**body),native
