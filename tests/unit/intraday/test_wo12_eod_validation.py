"""Terminal match policy: no path/price substitution or trading authority."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import pytest

from kronos.intraday.wo12_eod_validation import consideration, evaluate, metrics, COHORT, OUTCOME
from kronos.intraday.wo12_research_contract import record
from kronos.intraday.wo12_research_store import ResearchStore
from kronos.intraday.historical_semantic import create_governed_historical_candle_payload
from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe as TF
from kronos.intraday.wo09_machine_readiness import evaluate_machine_readiness
from tests.unit.application.test_intraday_wo08_research import application, fixture
from tests.unit.intraday.test_assessment_observation import manifest, positive
from kronos.intraday.assessment_observation import create_missing_assessment_observations


def setup(tmp_path, direction='LONG', price='100'):
    app, assessment, shadow, run = application(tmp_path)
    original = create_missing_assessment_observations(run).observations[0]
    from tests.unit.intraday.test_assessment_observation import proof_for
    observed = positive(original, proof_for(original, price=D(price))) if price is not None else original
    # The ordinary producer's validated companion is the sole baseline source.
    app.probables.load_assessment_observations = lambda _: manifest(run, (observed,))
    readiness, _ = evaluate_machine_readiness(assessment, created_at=run.analysis_boundary)
    app._readiness_history_by_result = lambda: {run.results[0].result_identity: (readiness,)}
    app.project(ensure_origins=True)
    from kronos.application.intraday_wo08_research import SCHEMA
    association, = app.store.records(SCHEMA)
    facts = fixture(0)[1]
    c = consideration(association, app.probables, facts.current_schedule)
    if direction == 'SHORT':
        d = c.data
        d['original_prediction']['direction'] = direction
        d['direction'] = direction
        observed = replace(observed, direction=direction)
        from kronos.intraday.probables_v2_persistence import _to_wire
        d['original_assessment'] = _to_wire(observed)
        # Isolated policy symmetry probe; production never changes the frozen direction.
        c = record(COHORT, **d)
    return app, c, observed, facts.current_schedule


def terminal(schedule, subject, close='110', **changes):
    b = expected_candle_boundaries(schedule, TF.FIVE_MINUTES)[-1]
    values = dict(canonical_subject_identity=subject, exchange=schedule.exchange, market_identity=schedule.exchange,
        market_session_identity=schedule.session_id, timeframe=TF.FIVE_MINUTES,
        candle_start=b.start, candle_end=b.end, open=D(close), high=D(close)+1,
        low=D(close)-1, close=D(close), volume=10, observation_boundary=b.end,
        provider_source_identity='ISOLATED-RETAINED-EVIDENCE', source_operation_identity='ISOLATED-EOD',
        provenance=('ISOLATED_PROVIDER_FREE',))
    values.update(changes)
    return create_governed_historical_candle_payload(**values)


@pytest.mark.parametrize('direction,close,match,reason', [
    ('LONG','110','MATCHED','POSITIVE_DIRECTIONAL_MOVE'),
    ('LONG','90','NOT_MATCHED','NEGATIVE_DIRECTIONAL_MOVE'),
    ('LONG','100','NOT_MATCHED','FLAT_DIRECTIONAL_MOVE'),
    ('SHORT','90','MATCHED','POSITIVE_DIRECTIONAL_MOVE'),
    ('SHORT','110','NOT_MATCHED','NEGATIVE_DIRECTIONAL_MOVE'),
    ('SHORT','100','NOT_MATCHED','FLAT_DIRECTIONAL_MOVE'),
    ('LONG','100.000001','MATCHED','POSITIVE_DIRECTIONAL_MOVE')])
def test_exact_terminal_classification_no_magnitude_threshold(tmp_path, direction, close, match, reason):
    app, c, observed, schedule = setup(tmp_path, direction)
    candle = terminal(schedule, c.data['subject'], close)
    result = evaluate(c, assessment=observed, schedule=schedule, candle=candle,
        now=candle.candle_end, source=source_ref(candle))
    assert result.data['prediction_match'] == match
    assert result.data['reason'] == reason
    assert result.data['interpretation'] == 'DIRECTION_AT_SESSION_ENDPOINT_ONLY'
    app.store.retain(c); app.store.retain(result)
    assert ResearchStore(app.store.root).load(result.identity) == result


@pytest.mark.parametrize('missing', ['price','candle','schedule','subject','future','nonterminal','mcx'])
def test_unavailable_does_not_become_analytical_failure(tmp_path, missing):
    app, c, observed, schedule = setup(tmp_path, price=None if missing=='price' else '100')
    candle = terminal(schedule, c.data['subject'])
    now = candle.candle_end
    if missing == 'candle': candle = None
    if missing == 'schedule': schedule = None
    if missing == 'subject': candle = terminal(schedule, 'NSE-EQ-FOREIGN')
    if missing == 'future': now -= timedelta(microseconds=1)
    if missing == 'nonterminal':
        candle = terminal(schedule, c.data['subject'], candle_start=candle.candle_start-timedelta(minutes=5),
            candle_end=candle.candle_end-timedelta(minutes=5))
    if missing == 'mcx':
        d = c.data; d['market'] = 'MCX'; c = record(COHORT, **d)
    value = evaluate(c, assessment=observed, schedule=schedule, candle=candle, now=now)
    assert value.data['prediction_match'] == 'NOT_EVALUABLE'
    assert value.data['directional_move_pct'] is None


def test_changed_baseline_and_corrupt_candle_raise(tmp_path):
    app, c, observed, schedule = setup(tmp_path)
    from tests.unit.intraday.test_assessment_observation import proof_for
    changed = positive(observed, proof_for(observed, price=D('101')))
    with pytest.raises(ValueError, match='ORIGINAL_ASSESSMENT_CHANGED'):
        evaluate(c, assessment=changed, schedule=schedule, now=schedule.windows[-1].closes_at)
    candle = terminal(schedule, c.data['subject'])
    object.__setattr__(candle, 'integrity_identity', 'CORRUPTED')
    with pytest.raises(ValueError):
        evaluate(c, assessment=observed, schedule=schedule, candle=candle, now=candle.candle_end)


def test_zero_denominator_and_progression_levels_remain_distinct(tmp_path):
    app, c, observed, schedule = setup(tmp_path)
    candle = terminal(schedule, c.data['subject'], '90')
    o = evaluate(c, assessment=observed, schedule=schedule, candle=candle, now=candle.candle_end,
        source=source_ref(candle))
    rows = metrics((c,), (o,), {c.identity: ({'count':4},)})
    three = next(r for r in rows if '3/5 false advance' in r[0])
    four = next(r for r in rows if '4/5 false advance' in r[0])
    five = next(r for r in rows if '5/5 false advance' in r[0])
    assert three[1:4] == four[1:4] == (1, 1, 1)
    assert five[1:4] == (0, 0, None)
    assert metrics((), (), {}) == ()


def test_rehashed_false_success_rejected_on_retention(tmp_path):
    app, c, observed, schedule = setup(tmp_path)
    candle = terminal(schedule, c.data['subject'], '90')
    value = evaluate(c, assessment=observed, schedule=schedule, candle=candle,
        now=candle.candle_end, source=source_ref(candle))
    d = value.data; d['prediction_match'] = 'MATCHED'
    app.store.retain(c)
    with pytest.raises(ValueError, match='CLASSIFICATION_INVALID'):
        app.store.retain(record(OUTCOME, **d))


@pytest.mark.parametrize('family', ['CRUDE','COPPER','GOLDM','NATGAS','SILVERM'])
def test_exact_native_contract_endpoint_and_foreign_contract_denial(tmp_path, family):
    from kronos.intraday.probables_v2_persistence import _to_wire
    from tests.unit.intraday.test_technical_context_research import native_index
    from tests.unit.intraday.test_assessment_observation import proof_for
    app, c, observed, schedule = setup(tmp_path)
    subject = 'MCX-SUBJECT-'+family
    # Synthetic fixture changes subject consistently, without claiming production
    # lineage or commissioning NATGAS. No shared/operational state is changed.
    base = replace(observed, canonical_subject_identity=subject,
        classification=observed.classification.PRICE_NOT_RETAINED,
        assessment_price=None, assessment_time=None, assessment_source_identity=None, proof=None)
    observed = positive(base, proof_for(base, price=D('100')))
    d = c.data; d.update(subject=subject, market='MCX', exact_contract='MCX-FUT-X-2026', roll_lineage='EXACT-ORIGINAL-ROLL')
    d['original_assessment'] = _to_wire(observed)
    c = record(COHORT, **d)
    candle = terminal(schedule, subject, source_operation_identity='OP')
    native = native_index((candle,))
    o = evaluate(c, assessment=observed, schedule=schedule, candle=candle,
        native=native, now=candle.candle_end, source=source_ref(candle))
    assert o.data['prediction_match'] == 'MATCHED'
    app.store.retain(c); app.store.retain(o)
    assert ResearchStore(app.store.root).load(o.identity) == o
    foreign = native_index((candle,), {'canonical_contract_identity':'MCX-FUT-FOREIGN-EXPIRY'})
    bad = evaluate(c, assessment=observed, schedule=schedule, candle=candle,
        native=foreign, now=candle.candle_end, source=source_ref(candle))
    assert bad.data['prediction_match'] == 'NOT_EVALUABLE'
    assert bad.data['reason'] == 'EXACT_CONTRACT_AUTHORITY_NOT_ESTABLISHED'


def test_rehashed_unknown_reason_and_revised_endpoint_rejected(tmp_path):
    app, c, observed, schedule = setup(tmp_path)
    app.store.retain(c)
    unavailable = evaluate(c, assessment=observed, schedule=schedule, now=schedule.windows[-1].closes_at)
    d = unavailable.data; d['reason'] = 'ARBITRARY_HINDSIGHT'
    with pytest.raises(ValueError, match='CLASSIFICATION_INVALID'):
        app.store.retain(record(OUTCOME, **d))
    candle = terminal(schedule, c.data['subject'])
    good = evaluate(c, assessment=observed, schedule=schedule, candle=candle,
        now=candle.candle_end, source=source_ref(candle))
    d = good.data; d['terminal_price'] = '111'
    with pytest.raises(ValueError, match='CLASSIFICATION_INVALID'):
        app.store.retain(record(OUTCOME, **d))


def test_terminal_revision_conflict_and_missing_later_source_does_not_erase_success(tmp_path):
    from kronos.application.intraday_wo12_eod import latest_outcomes
    app, c, observed, schedule = setup(tmp_path)
    candle = terminal(schedule, c.data['subject'])
    good = evaluate(c, assessment=observed, schedule=schedule, candle=candle,
        now=candle.candle_end, source=source_ref(candle))
    missing = evaluate(c, assessment=observed, schedule=schedule, now=candle.candle_end+timedelta(seconds=1))
    assert latest_outcomes((good, missing)) == (good,)
    revised = terminal(schedule, c.data['subject'], '111')
    other = evaluate(c, assessment=observed, schedule=schedule, candle=revised,
        now=candle.candle_end, source=source_ref(revised))
    with pytest.raises(ValueError, match='PUBLICATION_CONFLICT'):
        latest_outcomes((good, other))


def source_ref(candle):
    return dict(envelope_identity='ISOLATED-ENVELOPE', envelope_integrity='ISOLATED-ENVELOPE-INTEGRITY',
        facts_identity='ISOLATED-FACTS', facts_integrity='ISOLATED-FACTS-INTEGRITY')


def test_missing_original_prediction_keeps_actual_wo09_entrant(tmp_path):
    from kronos.application.intraday_wo08_research import SCHEMA
    from kronos.intraday.probables_v2_persistence import _to_wire
    app, c, observed, schedule = setup(tmp_path)
    association, = app.store.records(SCHEMA)
    d = association.data
    d.update(original_prediction=None, original_run_identity=None, original_methodology=None, original_source=None)
    absent = consideration(record(SCHEMA, **d), app.probables, None)
    assert absent.data['wo09_entry'] == c.data['wo09_entry']
    assert absent.data['original_prediction'] is None
    value = evaluate(absent, assessment=None, schedule=None, now=schedule.windows[-1].closes_at)
    assert value.data['prediction_match'] == 'NOT_EVALUABLE'
    assert value.data['reason'] == 'ORIGINAL_PREDICTION_NOT_RETAINED'
    app.store.retain(absent); app.store.retain(value)
    rows = metrics((absent,), (value,), {})
    assert next(r for r in rows if r[0].endswith(' considered'))[1] == 1


def test_same_contract_different_operation_binding_preserved(tmp_path):
    from kronos.intraday.probables_v2_persistence import _to_wire
    from tests.unit.intraday.test_technical_context_research import native_index
    from tests.unit.intraday.test_assessment_observation import proof_for
    app, c, observed, schedule = setup(tmp_path)
    subject='MCX-SUBJECT-COPPER'
    missing=replace(observed,canonical_subject_identity=subject,classification=observed.classification.PRICE_NOT_RETAINED,
        assessment_price=None,assessment_time=None,assessment_source_identity=None,proof=None)
    observed=positive(missing,proof_for(missing,price=D('100')))
    d=c.data;d.update(subject=subject,market='MCX',exact_contract='MCX-FUT-X-2026',roll_lineage='ORIGINAL-OPERATION-BINDING',original_assessment=_to_wire(observed))
    c=record(COHORT,**d); candle=terminal(schedule,subject,source_operation_identity='OP')
    native=native_index((candle,),{'historical_binding_identity':'LATER-OPERATION-BINDING'})
    value=evaluate(c,assessment=observed,schedule=schedule,candle=candle,native=native,now=candle.candle_end,source=source_ref(candle))
    assert value.data['prediction_match']=='MATCHED'
    assert c.data['roll_lineage']=='ORIGINAL-OPERATION-BINDING'
    assert value.data['native_evidence'][0]['historical_binding_identity']=='LATER-OPERATION-BINDING'


@pytest.mark.parametrize('fault', ['missing','envelope_integrity','facts_identity','facts_integrity','foreign_candle','late_publication'])
def test_pinned_source_resolution_rejects_missing_or_foreign_authority(tmp_path, monkeypatch, fault):
    from types import SimpleNamespace
    from kronos.application.intraday_wo12_eod import verify_sources
    from kronos.intraday.probables_v2_diagnostics_persistence import ProbablesV2DiagnosticsStore
    app,c,observed,schedule=setup(tmp_path)
    candle=terminal(schedule,c.data['subject'])
    ref=source_ref(candle)
    o=evaluate(c,assessment=observed,schedule=schedule,candle=candle,now=candle.candle_end,source=ref)
    facts=SimpleNamespace(facts_identity=ref['facts_identity'],integrity_identity=ref['facts_integrity'],
        canonical_subject_identity=c.data['subject'],current_five_minute=(candle,),__post_init__=lambda:None)
    envelope=SimpleNamespace(integrity_identity=ref['envelope_integrity'],analysis_boundary=candle.candle_end,
        created_at=candle.candle_end,probables_v2_facts=(facts,))
    def load(_, identity):
        assert identity==ref['envelope_identity']
        return envelope
    monkeypatch.setattr(ProbablesV2DiagnosticsStore,'load_envelope',load)
    verify_sources((o,),app.probables,candle.candle_end)
    if fault=='missing':
        def absent(*args):raise FileNotFoundError('exact source')
        monkeypatch.setattr(ProbablesV2DiagnosticsStore,'load_envelope',absent)
    elif fault=='envelope_integrity':envelope.integrity_identity='WRONG'
    elif fault=='facts_identity':facts.facts_identity='OTHER'
    elif fault=='facts_integrity':facts.integrity_identity='WRONG'
    elif fault=='foreign_candle':facts.current_five_minute=(terminal(schedule,'NSE-EQ-FOREIGN'),)
    elif fault=='late_publication':envelope.created_at+=timedelta(microseconds=1)
    with pytest.raises(ValueError,match='TERMINAL_SOURCE_(UNAVAILABLE|BINDING_INVALID)'):
        verify_sources((o,),app.probables,candle.candle_end)


@pytest.mark.parametrize('price', ['0','-1'])
def test_invalid_original_price_is_unavailable_without_substitution(tmp_path, price):
    app,c,observed,schedule=setup(tmp_path,price=price)
    candle=terminal(schedule,c.data['subject'])
    o=evaluate(c,assessment=observed,schedule=schedule,candle=candle,now=candle.candle_end,source=source_ref(candle))
    assert o.data['prediction_match']=='NOT_EVALUABLE'
    assert o.data['reason']=='ORIGINAL_ASSESSMENT_PRICE_INVALID'
    assert o.data['original_assessment_price']==price
    assert o.data['directional_move_pct'] is None


def test_storage_failure_remains_exception_and_does_not_rewrite_original(tmp_path, monkeypatch):
    import os
    app,c,observed,schedule=setup(tmp_path)
    app.store.retain(c)
    original=(app.store.root/'records'/f'{c.identity}.json').read_bytes()
    candle=terminal(schedule,c.data['subject'])
    o=evaluate(c,assessment=observed,schedule=schedule,candle=candle,now=candle.candle_end,source=source_ref(candle))
    def denied(*args,**kwargs):raise OSError('ISOLATED_STORAGE_FAILURE')
    monkeypatch.setattr(os,'link',denied)
    with pytest.raises(OSError,match='ISOLATED_STORAGE_FAILURE'):app.store.retain(o)
    assert original==(app.store.root/'records'/f'{c.identity}.json').read_bytes()
    assert not (app.store.root/'records'/f'{o.identity}.json').exists()
