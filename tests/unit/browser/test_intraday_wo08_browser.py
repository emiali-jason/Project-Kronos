"""New machine Review and retired visual routes preserve immutable history."""
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_wo08 import (
    IntradayWo08Projection, IntradayVisualHistory, WO08_STATUS_ROUTE,
    HISTORY_ROUTE, HISTORY_ARTIFACT_ROUTE, RETIREMENT_REASON,
)
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.intraday.visual_reconciliation_v2_persistence import VisualReconciliationStore
from kronos.intraday.review_v2 import REVIEW_V2_CHART_ROUTE, REVIEW_V2_ANSWER_IMPORT_ROUTE
from kronos.intraday.review_v2_transport import REVIEW_V2_QUESTION_TRANSPORT_ROUTE
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.browser.test_intraday_review_v2_control import _control, _payload, _Workstation
from tests.unit.intraday.test_review import _application, _png
from tests.unit.intraday.test_probables import _member, _run as _run_v1
from tests.unit.intraday.test_wo08_assessment import publish


def _bytes(root):
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


def _routes(tmp_path, projection, run=None, **kwargs):
    legacy = _application(tmp_path/'legacy', [_run_v1((_member('V1-FIXTURE'),))])
    return IntradayBrowserRoutes(_Workstation(run), review=legacy, wo08_projection=projection, **kwargs)


def _projection(tmp_path):
    run, mapping, native, owner, records = publish(tmp_path)
    probables = ProbablesV2Store(tmp_path)
    probables.retain_complete(run=run, mappings=mapping.member_evidence)
    return run, IntradayWo08Projection(owner.store, probables)


@pytest.mark.parametrize('route', [
    '/control/intraday-review/v2', REVIEW_V2_CHART_ROUTE,
    REVIEW_V2_QUESTION_TRANSPORT_ROUTE, REVIEW_V2_ANSWER_IMPORT_ROUTE,
    '/intraday/review/start', '/intraday/review/chart', '/intraday/review/question-pack',
    '/intraday/review/question-packs', '/intraday/review/answer', '/intraday/review/answers',
    '/intraday/review/reconcile', '/intraday/review/reconcile-all',
])
def test_retired_visual_mutations_are_owned_and_denied_before_body_or_legacy_dispatch(tmp_path, route):
    routes = _routes(tmp_path, SimpleNamespace())
    before = _bytes(tmp_path)
    response = routes.handle_post(BrowserPostRequest(route, {'cycle':['OLD']}, 'application/json', b'{'), _snapshot)
    assert routes.owns_post(route) and response.status.value == 409
    assert json.loads(response.body)['failure_reason'] == RETIREMENT_REASON
    assert _bytes(tmp_path) == before
    assert not routes.owns_post('/swing/review/answers')


def test_machine_review_is_current_inert_and_has_no_visual_actions(tmp_path):
    run, projection = _projection(tmp_path)
    routes = _routes(tmp_path, projection, run)
    before = _bytes(tmp_path)
    response = routes.handle_get(BrowserGetRequest('/intraday/review', {}), _snapshot)
    assert response.status.value == 200
    assert 'MACHINE WO08 ASSESSMENT' in response.body and 'NOT_COMMISSIONED' in response.body
    assert 'Chart Analyst is not required' in response.body
    assert 'LOAD FRESH REVIEW' not in response.body and 'action="/intraday/review/' not in response.body
    assert 'CREATE ALL REVIEW PDF' not in response.body
    document = json.loads(routes.handle_get(BrowserGetRequest(WO08_STATUS_ROUTE, {}), _snapshot).body)
    assert document['currentness'] == 'SOURCE_LINEAGE_CURRENT' and len(document['assessments']) == 98
    assert document['provider_calls'] == document['calculations'] == 0
    assert 'source_document' not in document['assessments'][0]
    assert _bytes(tmp_path) == before


def test_corrupt_current_machine_evidence_is_unavailable_not_analytical_negative(tmp_path):
    run, projection = _projection(tmp_path)
    (projection.store.root/'current.json').write_text('{}')
    routes = _routes(tmp_path, projection, run)
    response = routes.handle_get(BrowserGetRequest(WO08_STATUS_ROUTE, {}), _snapshot)
    assert response.status.value == 503
    assert json.loads(response.body)['failure_stage'] == 'READ_ONLY_PROJECTION'


def test_historical_question_answer_chart_survive_corrupt_current_pointer(tmp_path):
    from tests.unit.intraday.chart_input_fixtures import retain_current_fixture_receipts
    from tests.unit.intraday.test_review_v2 import _completed_batch_payload
    run, app, control = _control(tmp_path/'historical')
    control.execute_document(_payload(run))
    cycle = app.snapshot().candidates[0].cycle_identity
    app.upload_chart(cycle, media_type='image/png', payload=_png(93))
    retain_current_fixture_receipts(app, 'Reliance Industries Ltd')
    transport = app.create_combined_question_transport()
    answer = _completed_batch_payload(transport.answer_template_path, 'Reliance Industries Ltd')
    (app._transport.answer_inbox/transport.transport.expected_answer_filename).write_bytes(answer)
    app.import_all_expected_answers()
    candidate = app.snapshot().candidates[0]
    # Historic reads must not use any mutable current pointer as authority.
    for path in (app.review_store.root/'current').glob('*.json'):
        path.write_text('{}')
    history = IntradayVisualHistory(app.review_store,
        IntradayMcxPairedReviewStore(tmp_path/'mcx'), VisualReconciliationStore(tmp_path/'reconciliations'))
    before = _bytes(tmp_path)
    pdf = history.artifact({'kind':['nse-question-pdf'], 'identity':[transport.transport.transport_identity]})
    chart = history.artifact({'kind':['nse-chart'], 'identity':[candidate.chart_revision_identity]})
    visual = history.artifact({'kind':['nse-visual'], 'identity':[candidate.visual_evidence_identity]})
    assert pdf.body.startswith(b'%PDF') and chart.body == _png(93)
    assert json.loads(visual.body)['answer_pack_identity'] == candidate.answer_pack_identity
    assert 'nse-question-pdf' in history.render(_snapshot())
    assert _bytes(tmp_path) == before


def test_startup_ignores_historical_visual_pointer_and_never_backfills_wo08(tmp_path):
    from kronos.application.intraday_runtime import create_intraday_runtime
    from tests.unit.application.test_intraday_discovery_operation import _configured_shared, OBSERVED
    shared, _, factories, requests = _configured_shared()
    directory = tmp_path/'review-v2'/'current'
    directory.mkdir(parents=True)
    (directory/'CURRENT-REVIEW-V2-POINTER.json').write_text('{}')
    runtime = create_intraday_runtime(shared, evidence_root=tmp_path, clock=lambda:OBSERVED)
    assert runtime.wo08_store.current_run() == ()
    assert runtime.discovery_v2_operation.wo08_publication is runtime.wo08_publication
    assert runtime.review_v2_current is None and runtime.review_v2_application._prepare_pages is False
    assert not runtime.wo08_store.root.exists() and factories == [] and requests == [0]


def test_machine_statistics_keep_explicit_history_failure_and_do_not_require_visual_evidence(tmp_path):
    from kronos.application.intraday_statistics import IntradayStatisticsApplication
    from kronos.intraday.review import ReviewError, ReviewFailure
    run, projection = _projection(tmp_path)
    def broken_visual():
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    app = IntradayStatisticsApplication(current_probables=lambda:run, current_review=broken_visual,
        operational_readiness=lambda:{'reviews':()}, machine_assessment=projection.status_document,
        clock=lambda:run.analysis_boundary)
    result = app.project()
    metrics = {m.metric:m for m in result.metrics}
    assert metrics['WO08 currentness'].value == 'SOURCE_LINEAGE_CURRENT'
    assert metrics['Historical visual evidence'].state.startswith('HISTORICAL_READ_UNAVAILABLE:')
    assert len([m for m in result.metrics if m.metric.startswith('WO08 NSE-')]) == 98
    assert all(row.values[11] == 'HISTORICAL_ONLY_NO_WO08_BLOCKING_AUTHORITY' for row in result.stages)


def test_empty_machine_store_does_not_promote_existing_probables_or_manufacture_evidence(tmp_path):
    from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
    run, historical, _control_owner = _control(tmp_path/'probables')
    store = Wo08AssessmentStore(tmp_path/'machine')
    projection = IntradayWo08Projection(store, historical.probables_store)
    status = projection.status_document()
    assert status['currentness'] == 'NOT_YET_ASSESSED' and status['assessments'] == ()
    assert not store.root.exists()


def test_machine_wo09_projection_keeps_visual_history_separate_and_counts_unavailable(tmp_path):
    from kronos.intraday.wo09_machine_readiness import evaluate_machine_readiness
    from kronos.browser.intraday_wo09_control import project_card, project_analysis_details
    run, _mapping, _native, _owner, records = publish(tmp_path)
    readiness, requirements = evaluate_machine_readiness(records[0], created_at=run.analysis_boundary)
    card = project_card(readiness, requirements)
    detail = project_analysis_details(readiness, requirements)
    assert card.source_authority == 'WO08' and card.score == 'NOT_APPLICABLE'
    assert card.assessment_state == records[0].data['disposition']
    assert detail['A. MACHINE WO08 ASSESSMENT']['identity'] == records[0].identity
    assert 'B. WHAT CHART ANALYST SAYS' not in detail


def test_mcx_historical_pdf_and_chart_use_retained_native_identity_and_hash(tmp_path):
    from tests.unit.intraday.test_review_mcx_paired import _foundation
    from kronos.intraday.review_mcx_paired_transport import create_paired_transport
    from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
    cycle, active, native, reference, chart, ref_chart, bundle, pack = _foundation(tmp_path/'source')
    store = IntradayMcxPairedReviewStore(tmp_path/'paired')
    store.retain_chart(chart, native)
    transport, pdf, template = create_paired_transport(pack=pack, bundle=bundle,
        native_chart_payload=native, reference_chart_payload=reference, generated_at=pack.created_at)
    store.retain_transport(transport, pdf, template)
    history = IntradayVisualHistory(IntradayReviewV2Store(tmp_path/'review-v2'), store,
        VisualReconciliationStore(tmp_path/'wo07f'))
    before = _bytes(tmp_path)
    assert history.artifact({'kind':['mcx-chart'], 'identity':[chart.chart_revision_identity]}).body == native
    assert history.artifact({'kind':['mcx-question-pdf'], 'identity':[transport.transport_identity]}).body == pdf
    assert _bytes(tmp_path) == before
    (store.root/'question-pdfs'/(transport.transport_identity+'.pdf')).write_bytes(b'CORRUPT')
    with pytest.raises(Exception, match='INTEGRITY'):
        history.artifact({'kind':['mcx-question-pdf'], 'identity':[transport.transport_identity]})


@pytest.mark.parametrize('machine_published', [False, True])
def test_successor_projects_visual_buy_now_as_dated_history_on_every_readiness_page(tmp_path, machine_published):
    """Old CURRENT pointers remain immutable history before and after new Analysis."""
    from kronos.browser.intraday_wo09_control import IntradayWo09Projection
    from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
    from kronos.intraday.wo09_machine_readiness import evaluate_machine_readiness
    from kronos.intraday.wo09_persistence import Wo09Store
    from tests.unit.intraday.test_wo09_readiness import evaluated

    store = Wo09Store(tmp_path/'wo09')
    old, requirements = evaluated()
    store.retain(old, requirements, expected=store.expectation(old.canonical_subject_identity))
    if machine_published:
        run, mapping, _native, owner, assessments = publish(tmp_path/'machine')
        probables = ProbablesV2Store(tmp_path/'probables')
        probables.retain_complete(run=run, mappings=mapping.member_evidence)
        machine, requirements = evaluate_machine_readiness(assessments[0], created_at=run.analysis_boundary)
        store.retain(machine, requirements, expected=store.expectation(machine.canonical_subject_identity))
        machine_projection = IntradayWo08Projection(owner.store, probables)
    else:
        # A retained Probables run with no WO08 publication also models a failed
        # refresh that has not produced any replacement machine authority.
        run, historical, _control_owner = _control(tmp_path/'probables')
        machine_projection = IntradayWo08Projection(Wo08AssessmentStore(tmp_path/'machine'), historical.probables_store)
    projection = IntradayWo09Projection(store, machine_successor=True)
    from kronos.application.intraday_runtime import _create_discovery_application
    from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
    from kronos.intraday.discovery_persistence import NativeDiscoveryStore
    workstation = _create_discovery_application(store=NativeDiscoveryStore(tmp_path/'discovery'),
        probables_v2=IntradayProbablesV2Application(store=machine_projection.probables))
    routes = IntradayBrowserRoutes(workstation, wo08_projection=machine_projection, wo09_projection=projection)
    before = _bytes(tmp_path)
    status = projection.status_document()
    assert all(card.source_authority == 'WO08' for card in status['cards'])
    assert all(card.source_authority == 'WO08' for card in status['active_attention'])
    assert len(status['cards']) == int(machine_published)
    historical_card, = status['historical_cards']
    assert historical_card.readiness_identity == old.readiness_identity
    assert historical_card.readiness_state == 'BUY_NOW' and historical_card.score == '5 / 5'
    assert historical_card.monitorability_state == 'HISTORICAL_ONLY'
    assert historical_card.attention_state == 'NONE'
    assert historical_card.next_action == 'HISTORICAL_EVIDENCE_ONLY'
    assert historical_card.analysis_boundary == old.analysis_boundary.isoformat()
    assert historical_card.created_at == old.created_at.isoformat()
    assert old.readiness_identity not in status['analysis_details']
    assert status['historical_analysis_details'][old.readiness_identity]['F. WHAT HAPPENS NEXT'] == 'HISTORICAL_EVIDENCE_ONLY'
    for path in ('/intraday', '/intraday/review', '/intraday/wo09'):
        response = routes.handle_get(BrowserGetRequest(path, {}), _snapshot)
        assert response.status.value == 200
        assert 'Historical visual-era readiness' in response.body
        assert 'Original visual-era readiness: BUY NOW' in response.body
        assert old.analysis_boundary.isoformat() in response.body
        assert old.created_at.isoformat() in response.body
        assert 'NEXT_WO_HANDOFF_AVAILABLE' not in response.body
        # The persistent workflow navigation remains available; the readiness
        # card must not expose the distinct handoff action anchor.
        assert '<a href="/intraday/trade-candidates">TRADE CANDIDATES</a>' not in response.body
    assert store.load_pointer(old.canonical_subject_identity).currentness.value == 'CURRENT'
    assert _bytes(tmp_path) == before


def test_legacy_wo09_projection_retains_original_current_attention_contract(tmp_path):
    from kronos.browser.intraday_wo09_control import IntradayWo09Projection
    from kronos.browser.intraday_views import _readiness_body
    from kronos.intraday.wo09_persistence import Wo09Store
    from tests.unit.intraday.test_wo09_readiness import evaluated
    store = Wo09Store(tmp_path/'wo09')
    record, requirements = evaluated()
    store.retain(record, requirements, expected=store.expectation(record.canonical_subject_identity))
    before = _bytes(tmp_path)
    status = IntradayWo09Projection(store).status_document()
    card, = status['active_attention']
    assert card.next_action == 'NEXT_WO_HANDOFF_AVAILABLE'
    assert card.monitorability_state == 'CURRENT'
    assert status['historical_cards'] == ()
    assert 'href="/intraday/trade-candidates"' in _readiness_body(status)
    assert _bytes(tmp_path) == before
