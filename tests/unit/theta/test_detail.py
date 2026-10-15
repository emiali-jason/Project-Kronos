"""TE-07 read-only original evidence and documentary Detail qualification."""
from copy import deepcopy
from datetime import timedelta
from html import escape
import json
from urllib.parse import urlencode

import pytest

from kronos.browser.theta_detail import CRITERION_LABELS, public_url, locator
from kronos.theta.assessment import ThetaAssessmentEngine
from kronos.theta.contracts import SUBJECTS
from kronos.theta.orchestration import ThetaSponsorWorkflow
from kronos.theta.producer_v3 import V3QuestionProducer
from kronos.theta.store import ThetaStore, sealed
from kronos.theta.workflow import ThetaWorkflow
from tests.unit.theta.test_assessment import limited_c3, empty_events
from tests.unit.theta.test_combined_intake import snapshot
from tests.unit.theta.test_methodology_publication import publication
from tests.unit.theta.test_outlook import page
from tests.unit.theta.test_rehearsal import request
from tests.unit.theta.test_sponsor_workflow import fixture, create, answer_for, running
from tests.unit.theta.test_workflow import chart


def detail_fixture(root, *, missing=False, private=False, readable=False):
    app, producer, clock = fixture(root)
    if readable:
        from tests.unit.theta.test_question_packs import composite
        for role in (*SUBJECTS, 'GLOBAL_MACRO'):
            app.workflow.intake_chart(subject=role, label='SYNTHETIC TE-07 ' + role,
                media_type='image/png', information_cutoff=clock[0].isoformat(), payload=composite(role))
    create(app)
    answer, _ = answer_for(producer, clock)
    for subject, child in answer['answers'].items():
        if readable:
            samples = {'GOLDM': ('119000.00', '126500.00'), 'SILVERM': ('145000.00', '162500.00'),
                'COPPER': ('910.50', '985.750'), 'CRUDEOIL': ('5700.00', '6450.00'), 'NATURALGAS': ('255.50', '315.250')}
            for h, forecast in child['forecasts'].items():
                forecast['lower'], forecast['upper'] = samples[subject]
                forecast['confidence_pct'] = '82.00' if h == 'E1' else '78.25'
        if subject == 'SILVERM': limited_c3(child, 'E2')
        if subject == 'COPPER': empty_events(child)
        if subject == 'CRUDEOIL':
            child['research']['relationships'].append({
                'relation_id': 'REL-E1-UNRESOLVED', 'references': [
                    {'kind': 'FORECAST', 'identity': 'E1'},
                    {'kind': 'EVIDENCE', 'identity': 'CLAIM-E1-OPPOSE'}],
                'relationship_type': 'UNRESOLVED_CONTRADICTION', 'horizons': ['E1'],
                'explanation': 'Declared unresolved synthetic contradiction',
                'unresolved_limitation': 'Synthetic disagreement unresolved at T0',
                'limitation_ids': ['LIMITATION-E1']})
        if missing and subject == 'COPPER':
            child['research'].update(assumptions=[], limitations=[])
            for claim in child['research']['evidence_items']: claim['assumption_ids'] = []
            for relation in child['research']['relationships']: relation['limitation_ids'] = []
            for forecast in child['forecasts'].values(): forecast.update(assumption_ids=[], limitation_ids=[])
        if private and subject == 'GOLDM':
            source = child['research']['sources'][0]
            source.update(url='https://research.internal/theta',
                archive_version_locator='https://example.com/private/archive',
                title='<img src=x onerror=alert(1)> Synthetic source title')
    raw = json.dumps(answer, ensure_ascii=False, indent=2).encode() + b'\n'
    batch_id = producer.selected()['batch_id']
    (app.workflow.inbox / (batch_id + '_ANSWERS.json')).write_bytes(raw)
    operation = app.import_astra_answers(batch_id)
    assert operation['result']['intake']['package_status'] == 'COMPLETE'
    # One integrity-valid synthetic retained record isolates horizon projection.
    identity = operation['result']['assessments']['NATURALGAS']['assessment_id']
    record = deepcopy(app.assessment.restore_assessment(identity)['assessment'])
    record['horizons']['E2']['result'] = 'NOT_EVALUABLE'
    for c in record['horizons']['E2']['criteria']:
        c.update(result='NOT_EVALUABLE', reason_code='THETA_ASSESSMENT_SYNTHETIC_HORIZON_UNAVAILABLE')
    (app.store.root / 'v3-assessments' / (identity + '.json')).write_bytes(sealed(record))
    return app, producer, clock, answer, operation


def detail_page(app, question_id, subject):
    return page(app, '/theta-earners/detail', {'question': [question_id], 'subject': [subject]})


def test_all_five_exact_forecasts_criteria_reasons_and_references(tmp_path, monkeypatch):
    app, producer, _, answers, _ = detail_fixture(tmp_path.resolve())
    import kronos.theta.assessment as engine
    def forbidden(*args, **kwargs): raise AssertionError('Detail must not mutate or evaluate')
    monkeypatch.setattr(engine, '_evaluate', forbidden)
    monkeypatch.setattr(app.assessment, 'assess_accepted_theta_answer', forbidden)
    monkeypatch.setattr(app.intake, 'import_combined_astra_answer', forbidden)
    before = snapshot(app.store.root)
    for subject, selected_id in producer.store.current()['v3_questions'].items():
        detail = app.detail(selected_id, subject)
        response = detail_page(app, selected_id, subject)
        assert response.status == 200
        body = response.body
        assert 'SYNTHETIC — NOT FOR GENUINE FORECASTING' in body
        assert 'ASTRA FORECAST' in body and 'KRONOS DOCUMENTARY ASSESSMENT' in body
        assert detail['answer'] == answers['answers'][subject]
        for h in ('E1', 'E2'):
            forecast = detail['answer']['forecasts'][h]
            target = detail['question']['targets'][h]
            assert f'data-lower="{forecast["lower"]}" data-upper="{forecast["upper"]}"' in body
            assert 'Confidence: ' + forecast['confidence_pct'] + '%' in body
            assert target['option_expiry'] in body and target['underlying_future'] in body
            assert target['settlement_reference'] in body and target['price_unit'] in body
            for c in detail['assessment']['horizons'][h]['criteria']:
                assert c['reason_code'] in body and CRITERION_LABELS[c['criterion_id']] in body
                for ids in c['references'].values():
                    assert all(escape(identity) in body for identity in ids)
            for key in ('rationale', 'counterevidence', 'uncertainty', 'path_risk', 'confidence_justification'):
                assert escape(forecast[key]['text']) in body
        assert body.count('data-criterion=') == 18
        assert all(value in body for value in ('INFORMATION SET CUTOFF / T0', 'ANALYSIS COMPLETED', 'ANSWER ACCEPTED', 'ASSESSMENT CREATED'))
        for value in (detail['question']['information_cutoff'], detail['answer']['analyzed_at'],
                      detail['receipt']['accepted_at'], detail['assessment']['assessed_at']):
            assert f'datetime="{escape(value, quote=True)}"' in body
        for value in (selected_id, detail['answer']['answer_id'], detail['receipt']['acceptance_id'],
                      detail['receipt']['raw_child_sha256'], detail['receipt']['canonical_child_sha256'],
                      detail['question']['binding']['commodity_chart']['sha256'], detail['question']['binding']['macro_chart']['sha256']):
            assert value in body
        assert '<summary>TECHNICAL INTEGRITY / PROVENANCE</summary>' in body
    assert snapshot(app.store.root) == before


def test_mixed_states_and_unresolved_contradiction_do_not_change_forecast(tmp_path):
    app, producer, _, answers, _ = detail_fixture(tmp_path.resolve())
    results = {}
    for s, qid in producer.store.current()['v3_questions'].items():
        d = app.detail(qid, s)
        results[s] = tuple(d['assessment']['horizons'][h]['result'] for h in ('E1', 'E2'))
        assert d['answer']['forecasts'] == answers['answers'][s]['forecasts']
    assert results == {'GOLDM': ('DOCUMENTED', 'DOCUMENTED'), 'SILVERM': ('DOCUMENTED', 'LIMITED'),
        'COPPER': ('LIMITED', 'LIMITED'), 'CRUDEOIL': ('LIMITED', 'DOCUMENTED'),
        'NATURALGAS': ('DOCUMENTED', 'NOT_EVALUABLE')}
    body = detail_page(app, producer.store.current()['v3_questions']['CRUDEOIL'], 'CRUDEOIL').body
    assert 'UNRESOLVED_CONTRADICTION RECORDED' in body
    assert 'Declared unresolved synthetic contradiction' in body
    assert 'THETA_ASSESSMENT_C9_DECLARED_UNRESOLVED_CONTRADICTION' in body
    assert 'FORECAST REJECTED' not in body and 'TRADE SCORE' not in body


def test_research_observations_events_context_and_sources_exact_and_horizon_scoped(tmp_path):
    app, producer, _, answers, _ = detail_fixture(tmp_path.resolve())
    qid = producer.store.current()['v3_questions']['GOLDM']
    body = detail_page(app, qid, 'GOLDM').body
    child = answers['answers']['GOLDM']
    for family in ('chart_assessment', 'reference_mcx_assessment', 'commodity_research',
                   'macro_fundamental_research', 'bullish_evidence', 'bearish_evidence',
                   'counterevidence', 'reconciliation', 'uncertainty'):
        assert escape(child['research'][family]['text']) in body
    for family, text in (('evidence_items', 'statement'), ('chart_observations', 'observation_text'),
                         ('relationships', 'explanation'), ('scheduled_events', 'description'),
                         ('assumptions', 'statement'), ('limitations', 'statement')):
        for v in child['research'][family]:
            assert escape(v[text]) in body
            assert 'APPLIES TO: ' + ' · '.join(v['horizons']) in body
    for source in child['research']['sources']:
        for key in ('publisher', 'title', 'source_kind', 'available_at', 'accessed_at', 'relevance'):
            assert escape(source[key]) in body
        assert f'href="{escape(source["url"], quote=True)}"' in body
    assert 'AVAILABLE BY T0' in body and 'RETRIEVED LATER' in body
    assert 'ASTRA CHART OBSERVATION' in body and 'Daily Settlement Price' in body
    assert 'criterion pass/fail' not in body


def test_empty_documentary_families_are_honest(tmp_path):
    app, producer, _, _, _ = detail_fixture(tmp_path.resolve(), missing=True)
    body = detail_page(app, producer.store.current()['v3_questions']['COPPER'], 'COPPER').body
    assert body.count('NO DOCUMENTED EVENT RECORDS') == 2
    assert body.count('NO DOCUMENTED ITEMS') >= 4
    assert 'NONE EXIST' not in body


@pytest.mark.parametrize('state', ['missing', 'corrupt'])
def test_missing_assessment_preserves_accepted_answer_and_does_not_invent_criteria(tmp_path, state):
    app, producer, _, _, op = detail_fixture(tmp_path.resolve())
    aid = op['result']['assessments']['GOLDM']['assessment_id']
    path = app.store.root / 'v3-assessments' / (aid + '.json')
    if state == 'missing': path.rename(path.with_suffix('.unavailable-fixture'))
    else: path.write_bytes(b'corrupt synthetic assessment')
    before = snapshot(app.store.root)
    body = detail_page(app, producer.store.current()['v3_questions']['GOLDM'], 'GOLDM').body
    assert body.count('RETAINED ASSESSMENT NOT EVALUABLE') == 2
    assert 'data-criterion=' not in body and 'Confidence:' in body
    assert 'KRONOS verified the integrity and required documentary relationships' not in body
    assert snapshot(app.store.root) == before


@pytest.mark.parametrize('state', ['STALE', 'SUPERSEDED', 'HISTORICAL'])
def test_history_and_original_chart_remain_exact_after_replacement(tmp_path, state):
    app, producer, clock, _, _ = detail_fixture(tmp_path.resolve())
    qid = producer.store.current()['v3_questions']['GOLDM']
    old = app.detail(qid, 'GOLDM')
    if state == 'HISTORICAL':
        selection = app.store.current(); selection['v3_questions'].pop('GOLDM'); app.store.select(selection)
    else:
        app.workflow.intake_chart(subject='GOLDM', label='SYNTHETIC successor', media_type='image/png',
            information_cutoff=clock[0].isoformat(), payload=chart())
        if state == 'SUPERSEDED': clock[0] += timedelta(minutes=1); create(app)
    before = snapshot(app.store.root)
    restored = app.detail(qid, 'GOLDM')
    assert restored['currentness'] == state and restored['raw'] == old['raw']
    body = detail_page(app, qid, 'GOLDM').body
    assert 'HISTORICAL EVIDENCE · ' + state in body
    for role, binding in (('COMMODITY', 'commodity_chart'), ('GLOBAL_MACRO', 'macro_chart')):
        response = page(app, '/theta-earners/detail-chart', {'question': [qid], 'subject': ['GOLDM'], 'role': [role]})
        assert response.status == 200
        assert response.body == app.store.load_blob(old['question']['binding'][binding]['sha256'])
    assert snapshot(app.store.root) == before


@pytest.mark.parametrize('url', ['file:///private/tmp/x', 'javascript:alert(1)', 'https://user:password@example.com/a',
    'http://127.0.0.1/a', 'http://2130706433/a', 'https://localhost/a', 'https://reports.internal/a',
    'https://example.com/a?access_token=sensitive', 'https://example.com/private/a', 'https://example.com/a?sessionCookie=sensitive'])
def test_unsafe_locators_are_not_links_or_visible_private_locators(url):
    assert public_url(url) is None
    assert '<a ' not in locator(url) and url not in locator(url)


def test_source_links_and_markup_fail_closed_at_presentation(tmp_path):
    app, producer, _, _, _ = detail_fixture(tmp_path.resolve(), private=True)
    body = detail_page(app, producer.store.current()['v3_questions']['GOLDM'], 'GOLDM').body
    assert 'research.internal' not in body and 'https://example.com/private/archive' not in body
    assert 'private or unsafe locator withheld' in body
    assert '<img src=x onerror=' not in body and '&lt;img src=x onerror=alert(1)&gt;' in body
    assert 'referrerpolicy="no-referrer"' not in body  # Suppressed source URL has no external anchor.


def test_actual_http_detail_charts_exact_child_and_wrong_binding_rejection(tmp_path):
    app, producer, _, _, _ = detail_fixture(tmp_path.resolve())
    qid = producer.store.current()['v3_questions']['GOLDM']
    d = app.detail(qid, 'GOLDM')
    before = snapshot(app.store.root)
    with running(app) as server:
        for s, identity in producer.store.current()['v3_questions'].items():
            assert request(server, 'GET', '/theta-earners/detail?' + urlencode({'question': identity, 'subject': s}))[0] == 200
        raw = request(server, 'GET', '/theta-earners/answer?' + urlencode({'question': qid}))[2]
        assert raw == d['raw']
        for role in ('COMMODITY', 'GLOBAL_MACRO'):
            status, headers, binary = request(server, 'GET', '/theta-earners/detail-chart?' + urlencode({'question': qid, 'subject': 'GOLDM', 'role': role}))
            assert status == 200 and headers['Content-Type'] == 'image/png'
            assert binary == app.detail_chart(qid, 'GOLDM', role)[1]
        assert request(server, 'GET', '/theta-earners/detail?' + urlencode({'question': qid, 'subject': 'COPPER'}))[0] == 409
        assert request(server, 'GET', '/theta-earners/detail-chart?' + urlencode({'question': qid, 'subject': 'GOLDM', 'role': 'FOREIGN'}))[0] == 409
    assert snapshot(app.store.root) == before


def test_outlook_new_analysis_and_restart_remain_exact_without_reevaluation(tmp_path, monkeypatch):
    app, producer, clock, _, _ = detail_fixture(tmp_path.resolve())
    qid = producer.store.current()['v3_questions']['SILVERM']
    outlook, analysis = page(app).body, page(app, '/theta-earners/new-analysis').body
    before, original = snapshot(app.store.root), detail_page(app, qid, 'SILVERM').body
    wf = ThetaWorkflow(ThetaStore(app.store.root), inbox=app.workflow.inbox, outbox=app.workflow.outbox,
        clock=lambda: clock[0], qualification_mode=True)
    p = V3QuestionProducer(wf, producer.target_authority, published_methodology=publication())
    restored = ThetaSponsorWorkflow(p, ThetaAssessmentEngine(p.intake, publication()))
    monkeypatch.setattr(restored.assessment, 'assess_accepted_theta_answer', lambda *_: pytest.fail('GET evaluated'))
    assert detail_page(restored, qid, 'SILVERM').body == original
    assert page(restored).body == outlook and page(restored, '/theta-earners/new-analysis').body == analysis
    assert snapshot(app.store.root) == before
