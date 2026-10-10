"""WO12 observes exact WO08 / original 02A lineage without live control."""
from datetime import timedelta
from types import SimpleNamespace
import pytest

from kronos.application.intraday_research import IntradayResearchApplication, OPPORTUNITY_COLUMNS
from kronos.application.intraday_wo08_research import SCHEMA
from kronos.intraday.wo12_research_store import ResearchStore
from kronos.intraday.wo08_assessment import assess
from kronos.intraday.native_pullback_decision import build_decision
from kronos.intraday.wo08_shadow_persistence import Wo08ShadowStore
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from tests.unit.intraday.test_wo08_shadow_contract import handoff, fixture, outcome
from tests.unit.application.test_intraday_research import _EmptyStore, _Lifecycle


def application(tmp_path, *, retain_t0=True):
    source, facts, mapping, run = fixture(0)
    native = build_decision(source, created_at=run.analysis_boundary)
    assessment = assess(run_identity=run.run_identity, run_integrity=run.integrity_identity,
        result=run.results[0], mapping=mapping, native=native, created_at=run.analysis_boundary)
    probables = ProbablesV2Store(tmp_path/'probables')
    probables.retain_complete(run=run, mappings=(mapping,))
    shadow = Wo08ShadowStore(tmp_path)
    if retain_t0:
        shadow.retain_handoff(handoff())
    wo09 = SimpleNamespace(readiness=tmp_path/'readiness')
    app = IntradayResearchApplication(probables=probables, wo09=wo09, futures=_EmptyStore(),
        lifecycle=_Lifecycle(), store=ResearchStore(tmp_path/'research'),
        publication_root=tmp_path/'Statistics', clock=lambda:run.analysis_boundary,
        wo08=SimpleNamespace(records=lambda:(assessment,)), wo08_shadow=shadow)
    return app, assessment, shadow, run


def test_projection_reads_original_t0_without_writes_and_explicit_update_retains_association(tmp_path):
    app, assessment, shadow, run = application(tmp_path)
    original = {str(p):p.read_bytes() for p in shadow.root.rglob('*.json')}
    projection = app.project()
    assert not app.store.root.exists()
    assert not app.publication_root.exists()
    assert dict((row[0], row[1]) for row in projection.analysis)['WO08 population audit assessment count'] == 1
    result = app.update(operation_identity='WO08-EXPLICIT-RESEARCH')
    assert result.workbook_path.is_file()
    association, = app.store.records(SCHEMA)
    assert association.data['assessment_identity'] == assessment.identity
    assert association.data['assessment_integrity'] == assessment.integrity
    assert association.data['t0_state'] == 'EXACT_ORIGINAL_T0'
    assert association.data['t0_references'][0]['identity'] == handoff().samples[0].identity
    assert association.data['live_control_authority'] == 'NONE'
    assert association.data['outcomes'] == []
    assert original == {str(p):p.read_bytes() for p in shadow.root.rglob('*.json')}


def test_later_outcome_appends_new_association_without_changing_assessment_or_t0(tmp_path):
    app, assessment, shadow, run = application(tmp_path)
    app.project(ensure_origins=True)
    initial, = app.store.records(SCHEMA)
    initial_payload = initial.payload_json
    shadow.retain(outcome(handoff().samples[0]))
    app.project(ensure_origins=True)
    associations = app.store.records(SCHEMA)
    assert len(associations) == 2
    later = next(item for item in associations if item.identity != initial.identity)
    assert len(later.data['outcomes']) == 1
    assert later.data['outcomes'][0]['state'] == 'UNAVAILABLE'
    assert later.data['assessment_identity'] == assessment.identity
    assert app.store.load(initial.identity).payload_json == initial_payload
    assert app.wo08.records() == (assessment,)


def test_missing_original_research_is_unavailable_and_never_reconstructed(tmp_path):
    app, assessment, shadow, run = application(tmp_path, retain_t0=False)
    app.project(ensure_origins=True)
    association, = app.store.records(SCHEMA)
    assert association.data['t0_state'] == 'ORIGINAL_T0_UNAVAILABLE'
    assert association.data['t0_references'] == []
    assert not shadow.root.exists()
    assert assessment.data['criteria'][1]['state'] == 'NOT_COMMISSIONED'


def test_all_population_and_criteria_unavailable_denominators_remain_truthful(tmp_path):
    from tests.unit.intraday.test_wo08_assessment import publish
    run, mapping, native, owner, assessments = publish(tmp_path, all_unavailable=True)
    probables = ProbablesV2Store(tmp_path/'probables')
    probables.retain_complete(run=run, mappings=())
    app = IntradayResearchApplication(probables=probables,wo09=SimpleNamespace(readiness=tmp_path/'readiness'),
        futures=_EmptyStore(),lifecycle=_Lifecycle(),store=ResearchStore(tmp_path/'research'),
        publication_root=tmp_path/'Statistics',clock=lambda:run.analysis_boundary,wo08=owner.store)
    projection = app.project(ensure_origins=True)
    metrics = {row[0]:row for row in projection.analysis}
    assert metrics['WO08 population audit assessment count'][1] == 98
    assert metrics['WO08 considered assessment count'][1] == 0
    assert metrics['WO08 considered opportunity count'][1] == 0
    assert metrics['WO08 unavailable criterion rate'][3] is None
    assert metrics['WO08 false advance rate'][3] == 'NOT_ESTABLISHED'
    assert metrics['WO08 I2 established rate'][1] == 0
    assert len(app.store.records(SCHEMA)) == 98
    assert projection.opportunities == ()
    assert not app.publication_root.exists()



def considered_application(tmp_path, *, later=False, readiness=True):
    from datetime import datetime
    from kronos.intraday.native_pullback_decision import unavailable_source
    from kronos.intraday.wo09_machine_readiness import evaluate_machine_readiness
    from tests.unit.intraday.test_probables_v2 import _opening_inputs, _later_mapping, _run, IST
    mappings = [_opening_inputs()[-1], _opening_inputs(subject="NSE-EQ-REJECTED", nifty_close="105")[-1]]
    if later:
        mappings.append(_later_mapping(4, 1, boundary=datetime(2026, 8, 28, 11, 0, tzinfo=IST)))
    probables = ProbablesV2Store(tmp_path/'probables')
    assessments, histories, runs = [], {}, []
    for mapping in mappings:
        run = _run(mapping)
        runs.append(run)
        probables.retain_complete(run=run, mappings=(mapping,))
        native = build_decision(unavailable_source(mapping, run.results[0], run.run_identity,
            'NO_CONFIRMED_STRUCTURAL_CYCLE'), created_at=run.analysis_boundary)
        assessment = assess(run_identity=run.run_identity, run_integrity=run.integrity_identity,
            result=run.results[0], mapping=mapping, native=native, created_at=run.analysis_boundary)
        assessments.append(assessment)
        if readiness:
            current, _ = evaluate_machine_readiness(assessment, created_at=run.analysis_boundary)
            histories[run.results[0].result_identity] = (current,)
    app = IntradayResearchApplication(probables=probables,
        wo09=SimpleNamespace(readiness=tmp_path/'readiness'), futures=_EmptyStore(), lifecycle=_Lifecycle(),
        store=ResearchStore(tmp_path/'research'), publication_root=tmp_path/'Statistics',
        clock=lambda:runs[-1].analysis_boundary,
        wo08=SimpleNamespace(records=lambda:tuple(assessments)))
    app._readiness_history_by_result = lambda: histories
    return app, assessments, runs


@pytest.mark.parametrize('readiness', [True, False])
def test_frozen_admission_cohort_includes_unavailable_and_missing_readiness(tmp_path, readiness):
    app, assessments, runs = considered_application(tmp_path, readiness=readiness)
    projection = app.project(ensure_origins=True)
    metrics = {r[0]:r for r in projection.analysis}
    assert metrics['WO08 population audit assessment count'][1] == 2
    assert metrics['WO08 considered assessment count'][1] == 1
    assert metrics['WO08 considered opportunity count'][1] == 1
    assert metrics['WO08 unavailable criterion rate'][2:4] == (1, 1)
    assert metrics['WO08 considered assessments missing WO09'][1] == (0 if readiness else 1)
    records = app.store.records(SCHEMA)
    included = next(r.data for r in records if r.data['considered_at_assessment'])
    excluded = next(r.data for r in records if not r.data['considered_at_assessment'])
    assert included['probables_state'] == 'LONG_PROBABLE'
    assert included['probable_result_integrity'] == runs[0].results[0].integrity_identity
    assert included['probables_reasons'] == [r.value for r in runs[0].results[0].reasons]
    assert included['wo09_record_state'] == ('RECORDED' if readiness else 'MISSING')
    if readiness:
        assert included['readiness_references'][0]['state'] == 'READINESS_UNAVAILABLE'
        assert len(included['readiness_references'][0]['criteria']) == 5
    assert excluded['probables_state'] == 'NOT_ADMITTED'
    assert excluded['opportunity_identity'] is None
    assert all(r[1] is not None for r in projection.events)
    row = dict(zip(OPPORTUNITY_COLUMNS, projection.opportunities[0]))
    assert row['wo08_original_assessment_identity'] == assessments[0].identity
    assert row['wo08_original_direction'] == 'LONG'
    assert row['wo08_original_probables_reasons'] == 'V2_CONDITIONS_SATISFIED'
    assert row['wo08_eod_validation_state'] == 'UNAVAILABLE_NO_GOVERNED_EOD_OUTCOME'
    assert row['wo08_eod_prediction_match'] == 'NOT_ESTABLISHED'


def test_repeated_assessment_preserves_original_prediction_and_single_opportunity(tmp_path):
    app, assessments, runs = considered_application(tmp_path, later=True)
    original_bytes = assessments[0].payload
    projection = app.project(ensure_origins=True)
    metrics = {r[0]:r for r in projection.analysis}
    assert metrics['WO08 considered opportunity count'][1] == 1
    assert metrics['WO08 considered assessment count'][1] == 2
    assert len(projection.opportunities) == 1
    bound = [r.data for r in app.store.records(SCHEMA) if r.data['opportunity_identity'] is not None]
    assert len(bound) == 2
    assert all(r['original_prediction']['assessment_identity'] == assessments[0].identity for r in bound)
    assert all(r['original_prediction']['probable_result_identity'] == runs[0].results[0].result_identity for r in bound)
    assert len([r for r in projection.events if r[3] == 'WO09_READINESS']) == 2
    assert assessments[0].payload == original_bytes
    row = dict(zip(OPPORTUNITY_COLUMNS, projection.opportunities[0]))
    assert row['wo08_assessment_identity'] == assessments[-1].identity
    assert row['wo08_original_assessment_identity'] == assessments[0].identity
    first = app.update(operation_identity='SECTION31-FIRST')
    before = {str(p):p.read_bytes() for p in app.store.root.rglob('*.json')}
    repeated = app.update(operation_identity='SECTION31-FIRST')
    assert repeated.idempotent and repeated.workbook_sha256 == first.workbook_sha256
    assert before == {str(p):p.read_bytes() for p in app.store.root.rglob('*.json')}


def test_original_prediction_missing_is_never_replaced_by_later_assessment(tmp_path):
    app, assessments, runs = considered_application(tmp_path, later=True)
    original = assessments.pop(0)
    projection = app.project(ensure_origins=True)
    bound = [r.data for r in app.store.records(SCHEMA) if r.data['opportunity_identity'] is not None]
    assert len(bound) == 1
    assert bound[0]['original_prediction'] is None
    assert bound[0]['original_prediction_state'] == 'ORIGINAL_PREDICTION_UNAVAILABLE'
    row = dict(zip(OPPORTUNITY_COLUMNS, projection.opportunities[0]))
    assert row['wo08_original_assessment_identity'] is None
    assert row['probable_result_identity'] == runs[0].results[0].result_identity


def test_legacy_association_bytes_readable_alongside_successor(tmp_path):
    from kronos.application.intraday_wo08_research import LEGACY_SCHEMA
    from kronos.intraday.wo12_research_contract import record
    app, _, _ = considered_application(tmp_path)
    old = record(LEGACY_SCHEMA, historical_association='UNCHANGED')
    app.store.retain(old)
    original_bytes = old.payload_json
    app.project(ensure_origins=True)
    assert app.store.load(old.identity).payload_json == original_bytes
    assert app.store.records(LEGACY_SCHEMA) == (old,)
    assert len(app.store.records(SCHEMA)) == 2
