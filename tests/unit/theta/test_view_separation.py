"""TE-01A navigation/presentation, with immutable intake and forecast semantics."""

import ast
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from kronos.browser.product_routes import BrowserGetRequest
from kronos.browser.theta_charts import chart_script
from kronos.browser.theta_routes import ThetaBrowserRoutes
from kronos.theta.contracts import SUBJECTS, digest
from tests.unit.theta.test_browser import snapshot
from tests.unit.theta.test_chart_intake import empty, inventory, receive, role
from tests.unit.theta.test_rehearsal import request, running
from tests.unit.theta.test_workflow import NOW, accepted, workflow


class Elements(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.elements = []
        self.feed(body)
    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def page(workflow, path='/theta-earners'):
    return ThetaBrowserRoutes(workflow).handle_get(BrowserGetRequest(path, {}), snapshot).body


def assert_outlook_only(body):
    elements = Elements(body).elements
    assert not any('data-upload-url' in attrs for _, attrs in elements)
    assert not any(attrs.get('action', '').startswith('/theta-earners/') for tag, attrs in elements if tag == 'form')
    assert not any(attrs.get('type') == 'file' for tag, attrs in elements if tag == 'input')
    assert 'Manual research workflow' not in body and 'Question outbox:' not in body
    assert 'Answer intake:' not in body
    assert '/private/var/folders/' not in body and '/private/tmp/' not in body


def test_default_outlook_clean_empty_state_and_distinct_navigation(empty):
    before = empty.chart_workspace()
    body = page(empty)
    assert body.count('NO CURRENT THETA ANALYSIS AVAILABLE') == 1
    assert '<a class="active" aria-current="page" href="/theta-earners">OUTLOOK</a>' in body
    assert '<a class="" href="/theta-earners/new-analysis">NEW ANALYSIS</a>' in body
    assert 'href="/theta-earners/new-analysis">START NEW ANALYSIS</a>' in body
    assert '<table class="theta-summary"' not in body
    assert 'CHART_REQUIRED' not in body and 'NOT_ESTABLISHED' not in body
    assert_outlook_only(body)
    assert empty.chart_workspace() == before


def test_new_analysis_keeps_all_six_roles_without_forecast_table_or_paths(empty):
    body = page(empty, '/theta-earners/new-analysis')
    assert '<a class="active" aria-current="page" href="/theta-earners/new-analysis">NEW ANALYSIS</a>' in body
    assert body.count('data-upload-url=') == 6 and body.count('Choose File') == 6
    assert 'GLOBAL MACRO CONTEXT' in body and 'COMMODITY CHARTS READY: 0 / 5' in body
    assert 'QUESTION PACKS: 0 / 5' in body and 'ANSWERS ACCEPTED: 0 / 5' in body
    assert '<table class="theta-summary"' not in body
    assert 'Question outbox:' not in body and 'Answer intake:' not in body
    assert str(empty.inbox) not in body and str(empty.outbox) not in body
    assert 'Manual research workflow' not in body and 'QUESTION PACK: NOT CREATED' in body
    assert 'id="theta-chart-refresh" hidden>Chart selection changed. <a href="/theta-earners/new-analysis"' in body


def test_five_accepted_outlook_exact_ranges_confidence_dates_local_timestamp_and_links(workflow):
    identity, answer, _ = accepted(workflow)
    before = inventory(workflow)
    body = page(workflow)
    assert_outlook_only(body)
    assert 'NO CURRENT THETA ANALYSIS AVAILABLE' not in body
    assert body.count('Confidence: 78.00%') == 10
    assert '03:30 PM IST' in body and '11 Oct 2026' in body
    assert body.count('datetime="2026-10-11T10:00:00+00:00"') == 5
    assert body.count('25 Oct 2026') == 5 and body.count('25 Nov 2026') == 5
    assert 'ACCEPTED_EXTERNAL_EVIDENCE' not in body
    for subject in SUBJECTS:
        # TE-06A adds decorative local symbols and an independently coloured arrow.
        assert f'<span>{subject}</span><span class="theta-drill-arrow" aria-hidden="true">→</span></a>' in body
        for forecast in [f for f in answer['forecasts'] if f['target']['subject'] == subject]:
            assert f'{forecast["lower"]} – {forecast["upper"]}</strong>' in body
            assert f'title="{forecast["target"]["option_expiry"]}"' in body
        address = urlsplit('/theta-earners/detail?' + urlencode(dict(question=identity, subject=subject)))
        detail = ThetaBrowserRoutes(workflow).handle_get(BrowserGetRequest(address.path, parse_qs(address.query)), snapshot)
        assert detail.status == 200 and '<a href="/theta-earners">← BACK TO OUTLOOK</a>' in detail.body
        assert 'data:image/png;base64,' in detail.body and 'SYNTHETIC-MCX-' + subject in detail.body
        assert 'data-upload-url=' not in detail.body
    assert inventory(workflow) == before


@pytest.mark.parametrize('state', ['chart_only', 'pending', 'expired', 'authority_stale', 'corrupt'])
def test_noncurrent_states_never_fabricate_outlook_forecasts(workflow, state):
    if state == 'pending':
        workflow.create_question(SUBJECTS)
    elif state != 'chart_only':
        identity, _, _ = accepted(workflow)
        if state == 'expired':
            workflow.clock = lambda: NOW + timedelta(days=20)
        elif state == 'authority_stale':
            workflow.clock = lambda: NOW + timedelta(days=60)
        else:
            (workflow.store.root / 'accepted' / (identity + '.json')).write_bytes(b'corrupt synthetic receipt')
    body = page(workflow)
    assert body.count('NO CURRENT THETA ANALYSIS AVAILABLE') == 1
    assert '<table class="theta-summary"' not in body and 'Confidence: 78.00%' not in body
    assert_outlook_only(body)


def test_partial_current_outlook_never_reuses_replaced_subject_forecast(workflow):
    accepted(workflow)
    receive(workflow, 'COPPER')
    body = page(workflow)
    assert body.count('Confidence: 78.00%') == 8
    assert 'COPPER</td><td colspan="3" class="theta-muted">No current forecast</td>' in body
    assert 'subject=COPPER' not in body and 'CHART_REQUIRED' not in body
    assert_outlook_only(body)


def test_qualified_card_renderer_script_and_question_transport_are_not_redesigned():
    source = Path('src/kronos/browser/theta_charts.py').read_text()
    tree = ast.parse(source)
    card = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'chart_card')
    # TE-02 commissions Macro inclusion/gating. TE-06A adds only the explicit
    # V3-current projection parameter; upload controls/state machine stay exact.
    card_source = ast.get_source_segment(source, card)
    assert card_source.count('no sixth forecast / required for TE-02 Question packs') == 1
    legacy_card_source = card_source.replace('no sixth forecast / required for TE-02 Question packs',
                                           'no sixth forecast / no new Question gate')
    assert digest(legacy_card_source.encode()) == 'd326cfecc034b441bcde6ada57fe092cefd0f3fa01f73f8925aab815aaf12a8d'
    assert digest(chart_script().encode()) == '140bf11966235bf650b56329132464aa7b8fb755d80ec3113fb8a9d954379e2a'
    for path, expected in {
        # TE-02 is authorized to extend workflow/store and version temporal
        # contracts. The historical renderer and qualified chart mechanics stay.
        'src/kronos/theta/transport.py': 'fff0e43071605e15a5e58ff98c16d423f5c0f4ce40b069ba4d970b7fbd681dd8',
    }.items():
        assert digest(Path(path).read_bytes()) == expected


@pytest.mark.parametrize('path', ['/theta-earners', '/theta-earners/new-analysis'])
def test_view_route_rejects_uncommissioned_query_and_claims_no_mutation(workflow, path):
    routes = ThetaBrowserRoutes(workflow)
    assert routes.handle_get(BrowserGetRequest(path, {'view': ['unexpected']}), snapshot).status == 409
    assert not routes.owns_post(path)


def test_real_http_navigation_accepted_details_and_readonly_view_switch(workflow):
    identity, _, raw = accepted(workflow)
    before = inventory(workflow)
    with running(workflow) as server:
        status, _, outlook = request(server, 'GET', '/theta-earners')
        assert status == 200 and outlook.count(b'Confidence: 78.00%') == 10
        assert_outlook_only(outlook.decode())
        status, _, intake = request(server, 'GET', '/theta-earners/new-analysis')
        assert status == 200 and intake.count(b'data-upload-url=') == 6
        assert b'QUESTION PACKS: 5 / 5' in intake and b'ANSWERS ACCEPTED: 5 / 5' in intake
        for subject in SUBJECTS:
            status, _, detail = request(server, 'GET', '/theta-earners/detail?' + urlencode(dict(question=identity, subject=subject)))
            assert status == 200 and b'BACK TO OUTLOOK' in detail and digest(raw).encode() in detail
        assert request(server, 'GET', '/theta-earners')[2] == outlook
    assert inventory(workflow) == before
