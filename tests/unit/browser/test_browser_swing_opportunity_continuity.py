"""Distinct basename required by the repository's pytest import mode."""
from dataclasses import replace

import pytest

from kronos.browser.views import render_opportunities
from kronos.swing.v1 import opportunity_continuity as c
from tests.unit.swing.v1.test_opportunity_continuity import scenario, commit, later, row
from tests.unit.application.test_swing_opportunities import _ready


def page(bundle, committed=None):
    workspace = replace(_ready(), swing_analysis_run_identity=bundle.native_run.run_identity)
    return render_opportunities(workspace, bundle.native_run, committed_continuity=committed)


def test_C08_page_reload_presents_only_committed_data(scenario, tmp_path):
    snapshot, bindings = scenario
    first = c.prepare_continuity(snapshot, bindings)
    assert 'First admitted' not in page(first)
    with pytest.raises(ValueError, match='PRESENTATION_BINDING'):
        page(first, first)
    committed = commit(first, snapshot)
    before = tuple(tmp_path.iterdir())
    a = page(first, committed)
    assert a == page(first, committed)
    assert tuple(tmp_path.iterdir()) == before
    for label in ('Opportunity ID', 'First admitted', 'Latest material evidence', 'Last analysis checked'):
        assert label in a
    current = later(snapshot)
    second = c.prepare_continuity(current, bindings, predecessor=committed)
    assert 'NO MATERIAL CHANGE' in page(second, commit(second, current))
    with pytest.raises(ValueError, match='PRESENTATION_BINDING'):
        page(second, committed)


def test_C11_manual_review_retains_origin_without_successor(scenario):
    snapshot, bindings = scenario
    first = c.prepare_continuity(snapshot, bindings)
    changed = tuple(replace(b, expiry='2027-01-01') if b.canonical_instrument == 'GOLDM' else b for b in bindings)
    current = later(snapshot)
    second = c.prepare_continuity(current, changed, predecessor=commit(first, snapshot))
    html = page(second, commit(second, current))
    assert 'MANUAL REVIEW REQUIRED' in html
    assert row(first).opportunity_id in html
    assert 'SOURCE OR CONTRACT BREAK' in html
