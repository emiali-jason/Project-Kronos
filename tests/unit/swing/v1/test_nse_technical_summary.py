"""Synthetic completed owner facts only; no analytical/production acceptance."""
from copy import deepcopy
from dataclasses import replace

import pytest

from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.native_review import build_native_review_requirements
from kronos.swing.v1.nse_technical_summary import build_nse_technical_summary
from tests.unit.swing.v1.test_native_review import _evidence_run


def _inputs():
    facts, native, _ = _evidence_run()
    return build_native_review_requirements(native, facts)[0], native, facts


def _numbers(*, direction=V1Direction.LONG, zero=False, missing=False):
    requirement, native, facts = _inputs()
    instrument = facts.instrument(requirement.canonical_instrument)
    frames = []
    for f in instrument.timeframes:
        ma = replace(f.moving_averages, sma20=None if missing else (0.0 if zero else 100.0),
            sma50=None if missing else (0.0 if zero else 110.0), sma200=None if missing else (0.0 if zero else 120.0),
            prior_sma20_5bars=None if missing else (0.0 if zero else 90.0),
            prior_sma50_5bars=None if missing else (0.0 if zero else 110.0),
            prior_sma200_5bars=None if missing else (0.0 if zero else 130.0))
        vol = replace(f.volume_facts, prior_20_mean=None if missing else (0.0 if zero else 150.0))
        frames.append(replace(f, open=0.0 if zero else 100.0, high=0.0 if zero else 120.0,
            low=0.0 if zero else 90.0, close=0.0 if zero else 110.0, volume=0 if zero else 200,
            moving_averages=ma, volume_facts=vol))
    instrument = replace(instrument, timeframes=tuple(frames), one_hour_atr=None)
    facts = replace(facts, instruments=tuple(instrument if x.canonical_instrument == instrument.canonical_instrument else x
                                            for x in facts.instruments))
    native = replace(native, assessments=tuple(replace(a, direction=direction) if a.canonical_instrument == instrument.canonical_instrument else a
                                              for a in native.assessments))
    return build_native_review_requirements(native, facts)[0], native, facts


@pytest.mark.parametrize('direction', [V1Direction.LONG, V1Direction.SHORT])
def test_exact_four_timeframe_numerical_relationships_without_directional_vote(direction):
    requirement, native, facts = _numbers(direction=direction)
    report = build_nse_technical_summary(requirement, native, facts, 'a'*64)
    assert [f['timeframe'] for f in report['frames']] == ['1W','1D','4H','1H']
    for f in report['frames']:
        assert {k:v['state'] for k,v in f['comparisons'].items()} == {
            'close_sma20':'ABOVE','sma20_change':'RISING','close_sma50':'EQUAL',
            'sma50_change':'UNCHANGED','close_sma200':'BELOW','sma200_change':'FALLING',
            'volume_reference':'ABOVE','candle_direction':'UP'}
        assert f['visual'] == {q:{'state':'UNKNOWN','reason':'METHOD_NOT_APPROVED'} for q in ('Q3','Q5','Q10')}
        assert f['calendar_identity'] and f['provider_identity'] and f['source_timestamp']
    assert report['binding']['direction'] == direction.value
    assert report['independence']=='NOT_ESTABLISHED'
    assert report['authority']=='FACTUAL_EXPLANATORY_ONLY'
    assert not {'score','probability','confirmation','criteria','promotion','readiness','receipt','position'} & report.keys()


def test_zero_values_are_retained_and_compared_not_treated_as_missing():
    report=build_nse_technical_summary(*_numbers(zero=True),'b'*64)
    for f in report['frames']:
        assert f['values']['close']==0.0 and f['values']['volume']==0
        assert f['comparisons']['close_sma20']['state']=='EQUAL'
        assert f['comparisons']['volume_reference']['state']=='EQUAL'
        assert f['comparisons']['candle_direction']['state']=='UNCHANGED'


def test_valid_missing_indicators_remain_explicit_and_other_findings_survive():
    report=build_nse_technical_summary(*_numbers(missing=True),'b'*64)
    assert report['coverage']=='PARTIAL'
    for f in report['frames']:
        assert f['comparisons']['close_sma20']=={'state':'UNAVAILABLE','reason':'SMA20_UNAVAILABLE'}
        assert f['comparisons']['volume_reference']['state']=='UNAVAILABLE'
        assert f['comparisons']['candle_direction']['state']=='UP'
    assert report['atr']=={'state':'UNAVAILABLE','value':None,'reason':'ATR14_NOT_RETAINED'}


@pytest.mark.parametrize('changed', ['run','provider','assessment','requirement','instrument','direction','market','timeframe','publication'])
def test_wrong_source_and_subject_bindings_reject(changed):
    requirement,native,facts=deepcopy(_inputs());publication='a'*64
    if changed=='run':object.__setattr__(facts,'run_identity','SWING-RUN-'+'F'*32)
    elif changed=='provider':object.__setattr__(facts,'provider_source_identity','KITE-MTF-FACTS-'+'f'*64)
    elif changed=='assessment':requirement=replace(requirement,thesis=replace(requirement.thesis,native_assessment_sha256='f'*64))
    elif changed=='requirement':requirement=replace(requirement,requirement_sha256='f'*64)
    elif changed=='instrument':requirement=replace(requirement,thesis=replace(requirement.thesis,canonical_instrument='FOREIGN'))
    elif changed=='direction':requirement=replace(requirement,thesis=replace(requirement.thesis,direction=V1Direction.SHORT))
    elif changed=='market':object.__setattr__(requirement.thesis,'product_path',None)
    elif changed=='timeframe':object.__setattr__(facts.instrument(requirement.canonical_instrument).timeframes[0],'timeframe',FactualTimeframe.DAILY)
    else:publication='not-a-source-digest'
    with pytest.raises(ValueError):build_nse_technical_summary(requirement,native,facts,publication)


@pytest.mark.parametrize('invalid', [float('nan'),float('inf'),True,-1.0])
def test_malformed_numeric_source_is_rejected_not_hidden_as_missing(invalid):
    requirement,native,facts=deepcopy(_inputs())
    object.__setattr__(facts.instrument(requirement.canonical_instrument).timeframes[0],'close',invalid)
    with pytest.raises(ValueError):build_nse_technical_summary(requirement,native,facts,'a'*64)


def test_actual_retained_atr_identity_and_source_are_preserved():
    requirement,native,facts=_inputs()
    report=build_nse_technical_summary(requirement,native,facts,'a'*64)
    atr=facts.instrument(requirement.canonical_instrument).one_hour_atr
    assert atr is not None
    assert report['atr']['value']==atr.value
    assert report['atr']['state']==atr.availability.value
    assert report['atr']['integrity_sha256']==atr.integrity_sha256
    assert report['atr']['observed_boundary']==atr.observation_boundary.isoformat()


@pytest.mark.parametrize('field', ['run_identity','canonical_instrument','session_identity','value'])
def test_changed_atr_rejects(field):
    requirement,native,facts=deepcopy(_inputs())
    atr=facts.instrument(requirement.canonical_instrument).one_hour_atr
    object.__setattr__(atr,field,999.0 if field=='value' else 'FOREIGN')
    with pytest.raises(ValueError):build_nse_technical_summary(requirement,native,facts,'a'*64)


def test_summary_is_deterministic_and_does_not_mutate_source():
    args=_inputs();before=deepcopy(args)
    assert build_nse_technical_summary(*args,'a'*64)==build_nse_technical_summary(*args,'a'*64)
    assert args==before


def test_atr_distinct_owner_analysis_boundary_is_not_relabelled_as_snapshot_time():
    requirement,native,facts=_inputs()
    atr=facts.instrument(requirement.canonical_instrument).one_hour_atr
    assert atr.analysis_boundary != facts.observed_at
    report=build_nse_technical_summary(requirement,native,facts,'a'*64)
    assert report['atr']['analysis_boundary']==atr.analysis_boundary.isoformat()
    assert report['analysis_time']==facts.observed_at.isoformat()
