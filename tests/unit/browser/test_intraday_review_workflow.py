from dataclasses import replace
import hashlib
from pathlib import Path

import pytest

from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_views import _probable_v2_card, _intraday_tabs
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.review_v2_operation import REVIEW_V2_CREATE_ROUTE
from tests.unit.browser.test_intraday_review_v2_control import _control, _payload, _Workstation
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_probables import _member, _run as _run_v1
from tests.unit.intraday.test_review import _application
from tests.unit.intraday.test_review_v2 import _retain_later_current_run
import json


def _routes(tmp_path):
    run, app, control = _control(tmp_path / "v2")
    v1 = _application(tmp_path / "v1", [_run_v1((_member("V1-FIXTURE"),))])
    return run, app, control, IntradayBrowserRoutes(_Workstation(run), review=v1, review_v2_control=control)


def _fingerprints(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def _page(routes, candidate):
    response = routes.handle_get(BrowserGetRequest("/intraday/review", {"candidate": [candidate]}), _snapshot)
    assert response.status == 200
    return response.body


def test_sponsor_navigation_has_one_review_and_no_operational_review():
    for active in ("opportunities", "review", "wo-b", "wo10", "wo17"):
        nav = _intraday_tabs(False, active=active)
        assert 'href="/intraday/operational-review"' not in nav
        assert nav.count('href="/intraday/review"') == 1


def test_opportunity_link_and_missing_current_review_focus_are_inert(tmp_path):
    run, app, control, routes = _routes(tmp_path)
    result = run.results[0]
    before = _fingerprints(tmp_path)
    assert routes._opportunity_review_snapshot() is None
    card = _probable_v2_card(result, "RELIANCE")
    assert 'Review · <strong>NOT LOADED</strong>' in card
    assert f'/intraday/review?candidate={result.result_identity}#review-candidate-{result.result_identity}' in card
    assert 'Open Native Review' in card
    page = _page(routes, result.result_identity)
    assert 'Candidate is in latest Probables but not current Review. Load Fresh Review required.' in page
    assert page.index('LOAD FRESH REVIEW') < page.index('intraday-review-v2-grid', page.index('<section class="intraday-review-v2"'))
    assert _fingerprints(tmp_path) == before
    assert not app.snapshot().candidates


def test_current_review_focus_and_status_use_exact_current_population(tmp_path):
    run, app, control, routes = _routes(tmp_path)
    control.execute_document(_payload(run))
    candidate = app.snapshot().candidates[0]
    before = _fingerprints(tmp_path)
    snapshot = routes._opportunity_review_snapshot()
    card = _probable_v2_card(run.results[0], "RELIANCE", snapshot)
    assert 'CHART REQUIRED' in card
    page = _page(routes, candidate.probable_result_identity)
    assert f'id="review-candidate-{candidate.probable_result_identity}"' in page
    assert 'Load Fresh Review required.' not in page
    assert 'Zero current Review candidates' not in page
    assert 'REVIEW CURRENT</button>' in page
    assert 'LOAD FRESH REVIEW</button>' not in page
    assert _fingerprints(tmp_path) == before
    later = _retain_later_current_run(app)
    assert later.run_identity != run.run_identity
    assert routes._opportunity_review_snapshot() is None
    assert 'NOT LOADED' in _probable_v2_card(later.results[0], "RELIANCE", routes._opportunity_review_snapshot())
    assert 'Load Fresh Review required.' in _page(routes, later.results[0].result_identity)


@pytest.mark.parametrize('chart,question,answer,expected', [
    ('CHART_REQUIRED','ABSENT','NOT_IMPORTED','CHART REQUIRED'),
    ('CHART_READY','ABSENT','NOT_IMPORTED','CHART READY · ANSWER NOT IMPORTED'),
    ('CHART_READY','TRANSPORT_READY','NOT_IMPORTED','CHART READY · QUESTION PACK TRANSPORT READY · ANSWER NOT IMPORTED'),
    ('CHART_READY','TRANSPORT_READY','IMPORTED','CHART READY · QUESTION PACK TRANSPORT READY · ANSWER IMPORTED'),
])
def test_opportunity_status_preserves_review_owned_facts(tmp_path, chart, question, answer, expected):
    run, app, control = _control(tmp_path)
    control.execute_document(_payload(run))
    snapshot = app.snapshot()
    candidate = replace(snapshot.candidates[0], chart_state=chart, question_pack_state=question, answer_state=answer)
    card = _probable_v2_card(run.results[0], 'RELIANCE', replace(snapshot, candidates=(candidate,)))
    assert expected in card
    assert 'TRADE_READY' not in card
    foreign = replace(candidate, probable_result_identity='OTHER-RESULT')
    assert 'NOT LOADED' in _probable_v2_card(run.results[0], 'RELIANCE', replace(snapshot, candidates=(foreign,)))


def test_unknown_focus_does_not_reflect_input_or_create_cycle(tmp_path):
    _, app, _, routes = _routes(tmp_path)
    before = _fingerprints(tmp_path)
    attack = '<img src=x onerror=alert(1)>'
    page = _page(routes, attack)
    assert attack not in page
    assert 'Requested candidate is not in latest Probables or current Review.' in page
    assert not app.snapshot().candidates
    assert before == _fingerprints(tmp_path)


def test_load_fresh_uses_governed_control_and_preserves_focus_on_success(tmp_path, monkeypatch):
    run, app, control, routes = _routes(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('No analytical or external operation is allowed')
    import socket
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(routes._review, 'create_question_batch', forbidden, raising=False)
    page = _page(routes, run.results[0].result_identity)
    for value in (run.run_identity, run.methodology.methodology_identity, run.methodology.methodology_version,
                  run.methodology.publication_identity, run.methodology.payload_checksum):
        assert value in page
    assert 'location.reload()' in page
    request = BrowserPostRequest(REVIEW_V2_CREATE_ROUTE, {}, 'application/json', json.dumps(_payload(run)).encode())
    first = routes.handle_post(request, _snapshot)
    assert json.loads(first.body)['currentization_state'] == 'CURRENTIZED'
    cycles = _fingerprints(app.review_store.root / 'cycles')
    request = replace(request, body=json.dumps(_payload(run, 'REVIEW-V2-REQUEST-SECOND')).encode())
    second = routes.handle_post(request, _snapshot)
    assert json.loads(second.body)['currentization_state'] == 'ALREADY_CURRENT'
    assert cycles == _fingerprints(app.review_store.root / 'cycles')
    assert len(app.snapshot().candidates) == 1


@pytest.mark.parametrize("revision", [None, 1])
def test_chart_intake_compacts_only_missing_evidence_and_preserves_file_binding(tmp_path, revision):
    from html.parser import HTMLParser
    from kronos.browser.intraday_views import _review_v2_candidate

    class IntakeParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.elements = [], []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            self.elements.append((tag, attrs, tuple(self.stack)))
            if tag not in {"input", "br"}:
                self.stack.append(attrs.get("class", ""))

        def handle_endtag(self, tag):
            if self.stack:
                self.stack.pop()

    run, app, control = _control(tmp_path)
    control.execute_document(_payload(run))
    candidate = replace(app.snapshot().candidates[0], chart_revision_ordinal=revision)
    before = _fingerprints(tmp_path)
    html = _review_v2_candidate(candidate, 1)
    parsed = IntakeParser()
    parsed.feed(html)
    labels = [(attrs, parents) for tag, attrs, parents in parsed.elements if tag == "label"]
    inputs = [attrs for tag, attrs, _ in parsed.elements if tag == "input"]
    assert len(labels) == len(inputs) == 1
    assert labels[0][0]["for"] == inputs[0]["id"] == "intraday-v2-chart-file-1"
    assert inputs[0]["data-target"] == "intraday-v2-chart-slot-1"
    assert inputs[0]["accept"] == "image/png,image/jpeg"
    assert "Choose File" in html
    if revision is None:
        assert any("intraday-drop-empty" in parent for parent in labels[0][1])
        assert "PASTE TRADINGVIEW CHART" in html
        assert "Cmd+V / Ctrl+V · ONE COMPOSITE" in html
        assert 'data-review-v2-chart="true"' in html
        assert "Replace</button>" not in html
    else:
        assert "intraday-drop-empty" not in html
        assert 'class="intraday-drop received"' in html
        assert "TRADINGVIEW COMPOSITE · RECEIVED" in html
        assert "Chart Revision · REV 001" in html
        assert "Replace</button>" in html
    assert _fingerprints(tmp_path) == before
