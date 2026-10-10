"""Exact research contracts; no operational authority or methodology choices."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import pytest
from kronos.intraday.wo08_shadow_contract import (
    SCHEMAS, ResearchRecord, Wo08ShadowHandoff, canonical, digest, record, outcome_for,
)

from functools import lru_cache
from kronos.intraday.probables_v2_persistence import _to_wire
from kronos.intraday.native_pullback_decision import build_decision
from tests.unit.intraday.test_native_pullback_decision import source_fixture
from tests.unit.intraday.test_native_pullback_policy import BOUNDARY
T = BOUNDARY.isoformat()
LATER = (BOUNDARY+timedelta(hours=1)).isoformat()


@lru_cache(maxsize=4)
def fixture(index):
    return source_fixture(subject='NSE-EQ-S'+str(index))


def sample(index=0, **changes):
    source, f, m, run = fixture(index)
    r=run.results[0];n=build_decision(source,created_at=BOUNDARY)
    raw=canonical(dict(run_reference=dict(identity=run.run_identity,integrity=run.integrity_identity,
        universe=run.universe_identity,reconciliation=run.reconciliation_identity), result=_to_wire(r),mapping=_to_wire(m),
        facts_reference=dict(identity=f.facts_identity,replay_envelope='REPLAY'), assessments=[],native=n.data,
        discovery_reference=dict(identity=run.source_discovery_run_identity,session=run.market_session_identity),bundles=[]))
    cs=[dict(timeframe=c.timeframe.value,candle_id=c.candle_identity,integrity=c.integrity_identity,
        start=c.candle_start.isoformat(),end=c.candle_end.isoformat(),completion=c.completion_state,
        source_identity=c.provider_source_identity,kronos_acquired_at=None,provider_observed_at=None,
        source_revision_id=None,kronos_published_at=None,oi=None) for c in
        (x.candle for x in m.completed_evidence.selected_candles)]
    values=dict(sample_id='WO08-SAMPLE-'+digest(index),run_id='WO08-RUN-'+digest('run'),
        analysis_operation_id='OPERATION',analysis_boundary=T,research_published_at=T,
        subject=r.canonical_subject_identity,market_family='NSE_EQUITY',instrument_family='S'+str(index),
        direction=str(r.direction),probables_state=r.state.value,discovery_id=run.source_discovery_run_identity,
        probables_run_id=run.run_identity,probables_member_id=r.result_identity,mapping_id=m.mapping_identity,
        phase=r.phase.value,session_id=r.market_session_identity,calendar_id=m.completed_evidence.calendar_identity,
        calendar_version=m.completed_evidence.calendar_version,completed_selection_id=r.completed_evidence_selection_identity,
        native_decision_id=n.identity,native_state=n.data['result'],mcx_binding_class='NOT_MCX',
        exact_contract_id=None,binding_id=None,machine_fact_ids=[f.facts_identity],candle_refs=cs,
        source_revision_status='SOURCE_REVISION_PROVENANCE_UNAVAILABLE',quality='PARTIAL',
        exclusion_reasons=[],source_artifact_refs=[dict(kind='PROBABLES_RESULT',identity=r.result_identity,
            integrity_sha256=sha256(canonical(_to_wire(r))).hexdigest()),
            dict(kind='PROBABLES_REPLAY_ENVELOPE',identity='REPLAY',integrity_sha256=digest('REPLAY'))],
        candle_supplement_identity='WO08-SUPPLEMENT-'+sha256(raw).hexdigest(),candle_supplement_sha256=sha256(raw).hexdigest())
    values.update(changes)
    return record('T0',**values),raw


def handoff(new=True, excluded=97):
    # Full operational denominator, with truthful schema-unrepresentable exclusions.
    items=[] if excluded==98 else [sample()]
    samples=tuple(x[0] for x in items)
    missing={'UNMAPPED-'+str(i):'MAPPING_UNAVAILABLE' for i in range(excluded)}
    ids=[s.data['probables_member_id'] for s in samples]+list(missing)
    manifest=record('RUN',manifest_id='WO08-RUN-'+digest('run'),analysis_operation_id='OPERATION',
        probables_run_id=fixture(0)[3].run_identity,analysis_boundary=T,run_integrity=fixture(0)[3].integrity_identity,
        universe_identity='UNIVERSE',population_total=98,all_result_ids=ids,
        selected_sample_ids=[s.identity for s in samples],excluded_result_reasons=missing,
        sampling_policy_id='FULL',sampling_seed='SOURCE_RUN',inclusion_probabilities={i:1 for i in ids},
        capture_failures=[],recorded_at=T)
    return Wo08ShadowHandoff(manifest,samples,tuple(x[1] for x in items),new)


def outcome(s, **changes):
    values=dict(outcome_id='WO08-OUTCOME-'+digest(changes), horizon='NEXT_15M', state='UNAVAILABLE',
        captured_at=LATER, source_acquisition_id=None, source_publication_id=None,
        source_revision_status='SOURCE_REVISION_PROVENANCE_UNAVAILABLE', ordered_5m_candle_ids=[], ordered_integrities=[],
        directional_return=None, mfe=None, mae=None, first_favorable_at=None, first_adverse_at=None,
        continuation_persistence=None, structural_failure=None, reason='OPTION_A_EVIDENCE_UNAVAILABLE', quality='UNAVAILABLE',
        source_artifact_refs=[], outcome_candle_supplement_identity=None, outcome_candle_supplement_sha256=None)
    values.update(changes)
    return outcome_for(s,**values)


def test_frozen_handoff_contains_only_bytes_records_tuples_and_bool():
    h=handoff();h.__post_init__()
    d=h.samples[0].data;d['trading_authority']=True
    assert h.samples[0].data['trading_authority'] is False
    assert not any(x in h.encoded() for x in (b'ProviderLease',b'callback',b'latest_pointer'))
    with pytest.raises((AttributeError, TypeError)):
        h.newly_published=False


@pytest.mark.parametrize('field,value', [('operational_authority',True),('trading_authority',True),('authority','TRADING'),
    ('extra',1),('phase','UNKNOWN'),('direction','INVALID'),('source_revision_status','VERIFIED')])
def test_no_widening_or_false_revision_claim(field,value):
    with pytest.raises(ValueError):sample(**{field:value})


@pytest.mark.parametrize('end', [LATER,T])
def test_t0_only_completed_market_candles_at_or_before_boundary(end):
    c=dict(timeframe='5M',candle_id='C',integrity='H',start=(BOUNDARY-timedelta(minutes=5)).isoformat(),end=end,
           completion='COMPLETE',source_identity='PROVIDER',kronos_acquired_at=LATER)
    if end==T:assert sample(candle_refs=[c])[0].data['source_revision_status'].endswith('UNAVAILABLE')
    else:
        with pytest.raises(ValueError,match='LOOKAHEAD'):sample(candle_refs=[c])


@pytest.mark.parametrize('binding', ['MCX_BINDING_INVALID','MCX_BINDING_UNAVAILABLE'])
def test_invalid_mcx_can_only_be_negative_and_never_complete_outcome(binding):
    values=dict(subject='MCX-SUBJECT-GOLDM',market_family='MCX_METALS',mcx_binding_class=binding,native_state='NOT_ESTABLISHED')
    s,_=sample(**values)
    assert s.data['quality']=='PARTIAL'
    with pytest.raises(ValueError,match='NEGATIVE_ONLY'):sample(**values,quality='COMPLETE')
    with pytest.raises(ValueError,match='NEGATIVE_ONLY'):outcome(s,state='COMPLETE_SAME_CONTRACT')


def test_outcomes_separate_immutable_t0_and_exact_session_subject_contract():
    s,_=sample();before=s.payload
    later=outcome(s)
    assert later.data['t0_boundary']==T and s.payload==before
    for kwargs in ({'subject':'OTHER'},{'session_id':'OTHER'},{'captured_at':T}):
        with pytest.raises(ValueError):outcome(s,**kwargs)


def test_population_lineage_and_hash_tampering_fail_closed():
    h=handoff();d=h.manifest.data;d['population_total']=97;d.pop('integrity_sha256')
    with pytest.raises(ValueError):record('RUN',**d)
    bad=h.samples[0].data;bad['subject']='OTHER'
    with pytest.raises(ValueError,match='INTEGRITY'):ResearchRecord('T0',canonical(bad))
    with pytest.raises(ValueError):Wo08ShadowHandoff(h.manifest,h.samples,h.supplements[:-1],True)


def test_reviewed_schema_required_fields_are_unique_and_shapes_preserved():
    for schema in SCHEMAS.values():
        assert schema['$schema']=='https://json-schema.org/draft/2020-12/schema'
        assert len(schema['required'])==len(set(schema['required']))
        assert schema['additionalProperties'] is False
    h=handoff()
    for r in (h.manifest,h.samples[0],outcome(h.samples[0])):r.__post_init__()
    link=record('LINK',link_id='WO08-LINK-'+digest('link'),sample_id=h.samples[0].identity,
        t0_integrity=h.samples[0].data['integrity_sha256'],outcome_ids=[],visual_reconciliation_ids=[],
        previous_sample_id=None,cluster_key_subject_session='SUBJECT:SESSION',relationship='ORIGINAL',link_created_at=LATER)
    link.__post_init__()


def test_negative_direction_cannot_claim_positive_native_state():
    with pytest.raises(ValueError,match='NEGATIVE_EVIDENCE_PROMOTION'):
        sample(direction='CONFLICTING',native_state='PULLBACK')


def test_mcx_positive_research_stays_separate_from_02b_even_with_bound_contract():
    s,_=sample(subject='MCX-SUBJECT-GOLDM',market_family='MCX_METALS',mcx_binding_class='MCX_BINDING_VALID',
        exact_contract_id='EXACT-CONTRACT',binding_id='BINDING',exclusion_reasons=['MCX_POSITIVE_METHOD_RESEARCH_NOT_COMMISSIONED'])
    with pytest.raises(ValueError,match='NEGATIVE_ONLY'):outcome(s,state='COMPLETE_SAME_CONTRACT')


def test_typed_supplement_rejects_self_consistent_wrong_member_and_native():
    from kronos.intraday.wo08_shadow_contract import validate_t0_supplement
    s,raw=sample();validate_t0_supplement(s,raw)
    for field in ('result','mapping','native'):
        other=json.loads(sample(1)[1]);bad=json.loads(raw);bad[field]=other[field]
        payload=canonical(bad);d=s.data;d.pop('integrity_sha256')
        d.update(candle_supplement_identity='WO08-SUPPLEMENT-'+sha256(payload).hexdigest(),
                 candle_supplement_sha256=sha256(payload).hexdigest())
        changed=record('T0',**d)
        with pytest.raises(ValueError):validate_t0_supplement(changed,payload)
    arbitrary=canonical({'test_governed_snapshot':0});d=s.data;d.pop('integrity_sha256')
    d.update(candle_supplement_identity='WO08-SUPPLEMENT-'+sha256(arbitrary).hexdigest(),
             candle_supplement_sha256=sha256(arbitrary).hexdigest())
    with pytest.raises(ValueError,match='SUPPLEMENT_INVALID'):
        validate_t0_supplement(record('T0',**d),arbitrary)


def test_modeled_candle_end_never_becomes_observed_acquisition_time():
    from kronos.intraday.wo08_shadow_contract import validate_t0_supplement
    s,raw=sample();assert all(c['kronos_acquired_at'] is None for c in s.data['candle_refs'])
    d=s.data;d.pop('integrity_sha256');d['candle_refs'][0]['kronos_acquired_at']=d['candle_refs'][0]['end']
    with pytest.raises(ValueError,match='CANDLE_LINEAGE'):
        validate_t0_supplement(record('T0',**d),raw)


@pytest.mark.parametrize('binding',['MCX_BINDING_INVALID','MCX_BINDING_UNAVAILABLE'])
def test_invalid_binding_rejects_positive_native_even_partial(binding):
    with pytest.raises(ValueError,match='NEGATIVE_ONLY'):
        sample(subject='MCX-SUBJECT-GOLDM',market_family='MCX_METALS',mcx_binding_class=binding,native_state='PULLBACK')


@pytest.mark.parametrize('status',['VERIFIED','OFFICIAL','KNOWN','UNKNOWN'])
def test_outcome_revision_provenance_cannot_be_invented(status):
    with pytest.raises(ValueError,match='REVISION_PROVENANCE_UNAVAILABLE'):
        outcome(sample()[0],source_revision_status=status)


def test_mcx_subject_cannot_be_reclassified_as_nse_to_bypass_negative_boundary():
    with pytest.raises(ValueError,match='MCX_CLASS_INVALID'):
        sample(subject='MCX-SUBJECT-GOLDM',market_family='NSE_EQUITY',mcx_binding_class='NOT_MCX',
               native_state='NOT_ESTABLISHED',exclusion_reasons=[])
    with pytest.raises(ValueError,match='MCX_CLASS_INVALID'):
        sample(market_family='MCX_METALS',mcx_binding_class='MCX_BINDING_UNAVAILABLE',native_state='NOT_ESTABLISHED')
