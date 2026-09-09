"""WO-07D compact current-only workspace presentation matrix."""
from dataclasses import replace
from html import unescape
from html.parser import HTMLParser
import pytest
from kronos.browser.intraday_views import _review_v2_candidate, _review_v2_projection
from tests.unit.browser.test_intraday_review_workflow import _routes, _fingerprints
from tests.unit.browser.test_intraday_review_v2_control import _payload
from tests.unit.browser.test_product_route_isolation import _snapshot
from kronos.browser.product_routes import BrowserGetRequest


@pytest.fixture
def workspace(tmp_path):
    run, app, control, routes = _routes(tmp_path)
    control.execute_document(_payload(run))
    return run, app.snapshot(), control.status_document(), routes


@pytest.mark.parametrize('count',[0,1,4,8,9,15])
@pytest.mark.parametrize('state',['REVIEW_CURRENT','REVIEW_ABSENT','NEW_PROBABLES_AVAILABLE'])
def test_population_and_bulk_are_current_only(workspace, count, state):
    run, snapshot, status, _ = workspace
    candidates = tuple(replace(snapshot.candidates[0], sponsor_label=f'Candidate {i}',
        probable_result_identity=f'RESULT-{i}',cycle_identity=f'CYCLE-{i}') for i in range(count))
    snapshot = replace(snapshot, candidates=candidates)
    status = dict(status, currentness_state=state, current_review_candidate_count=count)
    page = _review_v2_projection(snapshot, run, status)
    assert page.count('<article class="intraday-review-v2-card"') == (count if state=='REVIEW_CURRENT' else 0)
    assert page.count('data-current-review-bulk="true"') == (1 if state=='REVIEW_CURRENT' else 0)
    assert ('LOAD FRESH REVIEW</button>' in page) == (state!='REVIEW_CURRENT')
    if state=='NEW_PROBABLES_AVAILABLE': assert 'REVIEW NON-CURRENT' in page
    if state=='REVIEW_ABSENT': assert 'NO REVIEW LOADED' in page


@pytest.mark.parametrize('label',['M&M','NIFTY','BANKNIFTY','LONG DISPLAY NAME '*12,'<script>&exact'])
@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_identity_direction_and_collapsed_lineage(workspace,label,direction):
    _, snapshot, _, _ = workspace
    candidate = replace(snapshot.candidates[0],sponsor_label=label,direction=direction)
    html = _review_v2_candidate(candidate,1)
    assert label in unescape(html) and direction in html
    assert '<script>' not in html
    assert '<details class="intraday-review-diagnostics"><summary>V2 LINEAGE</summary>' in html
    assert html.index('intraday-card-state') < html.index('Canonical subject')
    assert candidate.cycle_identity in html


@pytest.mark.parametrize('chart,transport,answer,action',[
    ('CHART_REQUIRED',None,'NOT_IMPORTED','Choose File'),
    ('CHART_READY',None,'NOT_IMPORTED','CREATE REVIEW PDF'),
    ('CHART_READY','TRANSPORT','NOT_IMPORTED','IMPORT EXPECTED ANSWER'),
    ('CHART_READY','TRANSPORT','RECEIVED','IMPORT EXPECTED ANSWER'),
    ('CHART_READY','TRANSPORT','REJECTED','IMPORT EXPECTED ANSWER'),
    ('CHART_READY','TRANSPORT','IMPORTED','ANSWER IMPORTED'),
    ('INVALID_UNUSABLE',None,'NOT_IMPORTED','INVALID UNUSABLE'),
    ('REPLACEMENT_REQUIRED',None,'NOT_IMPORTED','REPLACEMENT REQUIRED'),
])
def test_card_state_primary_action(workspace,chart,transport,answer,action):
    run,snapshot,_,_=workspace
    candidate=replace(snapshot.candidates[0],chart_state=chart,
        chart_revision_identity=None if chart=='CHART_REQUIRED' else 'CHART-EXACT',
        chart_revision_ordinal=None if chart=='CHART_REQUIRED' else 3,
        question_transport_identity=transport,question_filename='EXACT-QUESTION.pdf',
        expected_answer_filename='EXACT-ANSWER.json',answer_state=answer)
    html=_review_v2_candidate(candidate,1,run.run_identity)
    assert action in html
    if answer=='IMPORTED': assert 'IMPORT EXPECTED ANSWER</button>' not in html
    if transport:
        assert 'EXACT-ANSWER.json' in html
        assert '<summary>Expected Question / Answer filenames</summary>' in html
    if chart not in {'CHART_REQUIRED','CHART_READY'}: assert 'CREATE REVIEW PDF' not in html
    if chart!='CHART_REQUIRED':
        assert 'CHART-EXACT' in html and 'Open original' in html
        assert 'receipt alone is not visual or temporal validation' in html


@pytest.mark.parametrize('lawful',[True,False])
def test_mcx_selector_feedback_never_fabricates_options(workspace,lawful):
    _,snapshot,_,_=workspace
    candidate=replace(snapshot.candidates[0],canonical_subject_identity='MCX-SUBJECT-CRUDE',
        native_contract_identity='EXACT-NATIVE' if lawful else None,
        native_binding_identity='EXACT-BINDING' if lawful else None,
        reference_context_identity='NYMEX:CL1!' if lawful else None)
    html=_review_v2_candidate(candidate,1)
    assert ('NO GOVERNED CONTRACT AVAILABLE' in html)==(not lawful)
    assert ('NO GOVERNED REFERENCE CONTEXT AVAILABLE' in html)==(not lawful)
    assert ('value="EXACT-NATIVE"' in html)==lawful
    assert ('value="NYMEX:CL1!"' in html)==lawful


def test_get_has_no_mutation_or_auto_intake(workspace,tmp_path):
    _,_,_,routes=workspace
    before=_fingerprints(tmp_path)
    page=routes.handle_get(BrowserGetRequest('/intraday/review',{}),_snapshot).body
    assert before==_fingerprints(tmp_path)
    assert 'b.addEventListener("click"' in page
    assert page.count('data-current-review-bulk="true"')==1


@pytest.mark.parametrize('ready,imported,rejected', [(0,0,0),(1,0,0),(4,0,0),(4,2,1),(4,4,0)])
def test_bulk_counts_and_available_actions(workspace,ready,imported,rejected):
    run,snapshot,status,_=workspace
    members=tuple(replace(snapshot.candidates[0],cycle_identity=f'CYCLE-{i}',probable_result_identity=f'RESULT-{i}',
        chart_state='CHART_READY' if i<ready else 'CHART_REQUIRED',
        question_transport_identity='TRANSPORT' if i<ready else None,
        answer_state='IMPORTED' if i<imported else 'REJECTED' if i<imported+rejected else 'NOT_IMPORTED')
        for i in range(4))
    page=_review_v2_projection(replace(snapshot,candidates=members),run,status)
    assert page.count('data-current-review-bulk="true"')==1
    assert f'Questions ready: {ready}' in page
    assert f'Answers rejected: {rejected}' in page
    assert f'Answer ready: {imported} / 4' in page
    assert ('disabled>IMPORT ALL EXPECTED ANSWERS' in page)==(ready==0 or imported==4)
