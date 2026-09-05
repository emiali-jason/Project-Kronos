"""The V2 current pointer is the only Sponsor population and bulk authority."""
from dataclasses import replace
import json
import pytest
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.browser.intraday_views import render_intraday_review
from tests.unit.browser.test_intraday_review_workflow import _routes, _fingerprints
from tests.unit.browser.test_intraday_review_v2_control import _payload
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_review_v2 import _retain_later_current_run
from tests.unit.intraday.test_review import _png


def test_current_only_one_top_strip_and_no_get_gc(tmp_path, monkeypatch):
    run, app, control, routes = _routes(tmp_path)
    control.execute_document(_payload(run))
    monkeypatch.setattr(app, 'maintain_current_review', lambda: pytest.fail('GET GC'))
    before = _fingerprints(tmp_path)
    page = routes.handle_get(BrowserGetRequest('/intraday/review', {}), _snapshot).body
    assert page.count('data-current-review-bulk="true"') == 1
    assert page.index('REVIEW CURRENT') < page.index('data-current-review-bulk') < page.index('<div class="intraday-review-v2-grid">')
    assert page.count('CREATE ALL REVIEW PDF') == 1
    assert '<div class="intraday-review-list">' not in page
    assert page.count('<article class="intraday-review-v2-card"') == 1
    assert 'Chart ready: 0 / 1' in page
    assert before == _fingerprints(tmp_path)


def test_old_ready_transport_does_not_satisfy_current_or_legacy_bulk(tmp_path, monkeypatch):
    run, app, control, routes = _routes(tmp_path)
    control.execute_document(_payload(run))
    old = app.snapshot().candidates[0]
    app.upload_chart(old.cycle_identity, media_type='image/png', payload=_png(1))
    old_batch = app.create_combined_question_transport()
    later = _retain_later_current_run(app)
    control.execute_document(_payload(later, 'REVIEW-V2-REQUEST-SECOND'))
    monkeypatch.setattr(routes._review, 'create_all_question_packs', lambda: pytest.fail('Historical fallback'))
    before = _fingerprints(tmp_path)
    result = routes.handle_post(BrowserPostRequest('/intraday/review/question-packs', {}, '', b''), _snapshot)
    assert result.status >= 400
    assert _fingerprints(tmp_path) == before
    current = app.snapshot().candidates[0]
    app.upload_chart(current.cycle_identity, media_type='image/png', payload=_png(2))
    batch = app.create_combined_question_transport()
    assert batch.batch.review_cycle_identities == (current.cycle_identity,)
    assert old.cycle_identity not in batch.batch.review_cycle_identities
    assert batch.batch.batch_identity != old_batch.batch.batch_identity


def test_zero_ready_reconciliation_is_gated_without_legacy_or_wo10(tmp_path, monkeypatch):
    run, app, control, routes = _routes(tmp_path)
    control.execute_document(_payload(run))
    monkeypatch.setattr(routes._reconciliation, 'reconcile_all_ready', lambda: pytest.fail('Historical authority'))
    result = routes.handle_post(BrowserPostRequest('/intraday/review/reconcile-all', {}, '', b''), _snapshot)
    assert result.status == 409
    value = json.loads(result.body)
    assert value['candidate_count'] == 1
    assert value['current_review_pointer'] == app.snapshot().current_pointer_identity
    assert value['outcome'] == 'GATED'
    assert value['invocation_count'] == 0
    assert value['not_dispatched_count'] == 0
