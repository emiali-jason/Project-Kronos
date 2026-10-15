"""TE-06A theme isolation and read-only rendering regression."""

from pathlib import Path

import pytest

from kronos.browser.product_routes import BrowserGetRequest
from kronos.browser.theta_routes import ThetaBrowserRoutes
from kronos.browser.theta_theme import THEME_STYLES, commodity_symbol
from kronos.browser.views import render_browser_page
from kronos.theta.contracts import SUBJECTS, digest
from tests.unit.theta.test_browser import snapshot
from tests.unit.theta.test_chart_intake import empty, inventory
from tests.unit.theta.test_view_separation import Elements, page
from tests.unit.theta.test_workflow import accepted, workflow


@pytest.mark.parametrize('subject', SUBJECTS)
def test_commodity_symbols_are_small_local_decorations(subject):
    mark = commodity_symbol(subject)
    assert len(mark) < 750
    elements = Elements(mark).elements
    assert elements[0] == ('span', {'class': 'theta-commodity-symbol',
                                   'data-commodity': subject, 'aria-hidden': 'true'})
    assert any(tag == 'svg' and attrs['focusable'] == 'false' for tag, attrs in elements)
    assert all(tag in {'span', 'svg', 'path', 'ellipse'} for tag, _ in elements)
    assert not any('href' in attrs or 'src' in attrs for _, attrs in elements)


def test_empty_theme_does_not_invent_market_evidence(empty):
    empty.chart_workspace()  # Existing store lock is initialized by the read seam.
    before = inventory(empty)
    body = page(empty)
    assert '<div class="theta-theme">' in body and THEME_STYLES in body
    assert 'NO CURRENT THETA ANALYSIS AVAILABLE' in body
    assert 'START NEW ANALYSIS' in body
    assert '<svg ' not in body and '<table class="theta-summary"' not in body
    assert 'sparkline' not in body.lower() and '<canvas' not in body
    assert inventory(empty) == before


def test_narrow_theme_preserves_date_time_break_and_compact_symbols():
    assert '.theta-summary td:last-child>br{display:none}' in THEME_STYLES
    assert '.theta-summary td:last-child br{display:none}' not in THEME_STYLES
    assert '.theta-summary td:last-child time{display:inline-block;vertical-align:middle}' in THEME_STYLES
    assert '.theta-commodity-symbol{flex-basis:32px;width:32px;height:32px}' in THEME_STYLES


def test_populated_theme_keeps_exact_values_currentness_and_detail(workflow):
    identity, answer, raw = accepted(workflow)
    before = inventory(workflow)
    body = page(workflow)
    assert body.count('<svg ') == 5 and body.count('Confidence: 78.00%') == 10
    assert body.count('<span class="theta-current">Current</span>') == 5
    for subject in SUBJECTS:
        assert commodity_symbol(subject) in body
        for forecast in (f for f in answer['forecasts'] if f['target']['subject'] == subject):
            assert f'{forecast["lower"]} – {forecast["upper"]}</strong>' in body
        response = ThetaBrowserRoutes(workflow).handle_get(
            BrowserGetRequest('/theta-earners/detail', {'question': [identity], 'subject': [subject]}), snapshot)
        assert response.status == 200 and commodity_symbol(subject) in response.body
        assert digest(raw) in response.body and 'BACK TO OUTLOOK' in response.body
    assert inventory(workflow) == before


def test_new_analysis_theme_preserves_all_six_intake_bindings(empty):
    empty.chart_workspace()
    before = inventory(empty)
    body = page(empty, '/theta-earners/new-analysis')
    targets = [attrs for _, attrs in Elements(body).elements if 'data-upload-url' in attrs]
    assert [a['data-subject'] for a in targets] == [*SUBJECTS, 'GLOBAL_MACRO']
    assert all(a['data-cycle'] == 'UNSTARTED' and a['data-revision'] == 'MISSING' for a in targets)
    assert body.count('Choose File') == 6 and 'CREATE THETA QUESTION PACK' in body
    assert '.theta-theme .chart-paste-target:focus' in THEME_STYLES
    assert 'color:var(--green)' in THEME_STYLES
    assert inventory(empty) == before


def test_shared_browser_shell_does_not_emit_theta_theme():
    body = render_browser_page(title='Swing', subtitle='Unchanged shell', snapshot=snapshot(),
        active_nav='Swing', active_tab='', body='<p>Existing product content</p>')
    assert THEME_STYLES not in body and '<div class="theta-theme">' not in body
    assert '.nav a.active[href="/theta-earners"]' not in body


def test_te02_analytical_and_intake_bytes_remain_unchanged():
    for path, sha in {
        # PLC-01 reconciles the retained local PRG seam and additive Theta
        # registration with current develop; pure Theta pins below stay exact.
        'src/kronos/browser/product_routes.py': '55f7a17ca8d1307b2fae836df2c798e8100d4773533a6d186bddde8d9d0f30b7',
        # TE-06A projects retained V3 pack/acceptance counters without changing intake.
        'src/kronos/browser/theta_charts.py': 'a0d9871e937d73ea20cef88ca1bb1fff0bff0762afcae2784d2c0280a048ba34',
        'src/kronos/theta/contracts.py': '33f0eddfa31985ba14690c2d69aac37140679c7152ed2f07e465a70808d0dfdf',
        'src/kronos/theta/store.py': 'eae369a3945d4c54b7a3999ac71dcd2bb0286b5e33331f4c25dda110475a9580',
        'src/kronos/theta/workflow.py': '2bf31e5224cbf47ac5d307e5ccb0342e38c0c729eb56261fd3a027b5eb662d96',
        'src/kronos/theta/transport.py': 'fff0e43071605e15a5e58ff98c16d423f5c0f4ce40b069ba4d970b7fbd681dd8',
        # TE-03A preserves distinct owner/methodology failures at commissioning.
        # All other retained TE-02 analytical/intake bytes remain pinned here.
        'src/kronos/theta/packs.py': '11e785d92ad17c72f12ce0bb181ad1004372b2e8abdeb9d86b5ce22ed99f4a28',
        # TE-04C adds an explicit V3 presentation projection; unchanged default
        # rendering is byte-compared against all five retained TE-02 PDFs.
        'src/kronos/theta/question_pack.py': '8333262dc66e54acaaddb27867603ee5e306202638870abd59cce2001eaf81d4',
    }.items():
        assert digest(Path(path).read_bytes()) == sha, path
