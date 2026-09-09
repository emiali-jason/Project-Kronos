"""WO-07D immutable preview binding, read-only behavior and containment."""
from dataclasses import replace
import pytest
from kronos.browser.product_routes import BrowserGetRequest
from kronos.browser.intraday_chart_preview import CHART_PREVIEW_ROUTE
from tests.unit.browser.test_intraday_review_workflow import _routes, _fingerprints
from tests.unit.browser.test_intraday_review_v2_control import _payload
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_review import _png
from tests.unit.intraday.test_review_v2 import _retain_later_current_run


def prepared(tmp_path):
    run, app, control, routes = _routes(tmp_path)
    control.execute_document(_payload(run))
    candidate = app.snapshot().candidates[0]
    payload = _png(21)
    app.upload_chart(candidate.cycle_identity, media_type='image/png', payload=payload)
    candidate = app.snapshot().candidates[0]
    query = {'run':[run.run_identity], 'cycle':[candidate.cycle_identity],
             'revision':[candidate.chart_revision_identity]}
    return app, routes, query, payload


def get(routes, query):
    return routes.handle_get(BrowserGetRequest(CHART_PREVIEW_ROUTE, query), _snapshot)


def test_exact_bytes_read_only_and_no_provider(tmp_path, monkeypatch):
    app, routes, query, payload = prepared(tmp_path)
    before = _fingerprints(tmp_path)
    monkeypatch.setattr(app, 'upload_chart', lambda *a, **k: pytest.fail('preview wrote chart'))
    response = get(routes, query)
    assert response.status == 200 and response.content_type == 'image/png'
    assert response.body == payload and response.filename is None
    assert _fingerprints(tmp_path) == before


@pytest.mark.parametrize('field', ['run','cycle','revision'])
@pytest.mark.parametrize('value', ['WRONG', '../foreign', '/etc/passwd', '..\\foreign', '%2e%2e%2fsecret', '<script>'])
def test_exact_id_and_traversal_rejection(tmp_path, field, value):
    app, routes, query, _ = prepared(tmp_path)
    query[field] = [value]
    before = _fingerprints(tmp_path)
    response = get(routes, query)
    assert response.status == 404
    assert response.body == 'Exact current chart preview unavailable.'
    assert _fingerprints(tmp_path) == before


@pytest.mark.parametrize('mode', ['missing','duplicate','extra'])
def test_strict_query(tmp_path, mode):
    _, routes, query, _ = prepared(tmp_path)
    if mode == 'missing': del query['revision']
    elif mode == 'duplicate': query['revision'] *= 2
    else: query['path']=['foreign.png']
    assert get(routes, query).status == 404


def test_superseded_revision_does_not_follow_current_pointer(tmp_path):
    app, routes, query, _ = prepared(tmp_path)
    app.upload_chart(query['cycle'][0], media_type='image/png', payload=_png(22))
    before = _fingerprints(tmp_path)
    assert get(routes, query).status == 404
    assert _fingerprints(tmp_path) == before


def test_producer_advance_blocks_preview_and_preserves_evidence(tmp_path):
    app, routes, query, _ = prepared(tmp_path)
    _retain_later_current_run(app)
    before = _fingerprints(tmp_path)
    assert get(routes, query).status == 404
    assert _fingerprints(tmp_path) == before


@pytest.mark.parametrize('attack', ['payload','metadata','missing','file_symlink','family_symlink','root_symlink','ancestor_symlink'])
def test_tamper_and_symlinks_fail_closed(tmp_path, attack):
    app, routes, query, _ = prepared(tmp_path)
    root = app.review_store.root
    chart = app.review_store.load_chart(query['revision'][0])
    binary = root/'chart-binaries'/(chart.chart_artifact_identity+'.png')
    if attack == 'payload': binary.write_bytes(_png(44))
    elif attack == 'metadata': (root/'chart-revisions'/(chart.chart_revision_identity+'.json')).write_text('{}')
    elif attack == 'missing': binary.unlink()
    else:
        path = {'file_symlink':binary, 'family_symlink':binary.parent,
                'root_symlink':root,'ancestor_symlink':root.parent}[attack]
        moved = path.with_name(path.name+'-moved')
        path.rename(moved)
        path.symlink_to(moved, target_is_directory=moved.is_dir())
    before = _fingerprints(tmp_path)
    assert get(routes, query).status == 404
    assert _fingerprints(tmp_path) == before


def test_missing_chart_is_not_an_implicit_selection(tmp_path):
    run, app, control, routes = _routes(tmp_path)
    control.execute_document(_payload(run))
    candidate = app.snapshot().candidates[0]
    before = _fingerprints(tmp_path)
    assert get(routes, {'run':[run.run_identity], 'cycle':[candidate.cycle_identity],
                        'revision':['CHART-MISSING']}).status == 404
    assert _fingerprints(tmp_path) == before


def test_jpeg_preview_retains_exact_media_and_payload(tmp_path):
    from PIL import Image
    from io import BytesIO
    app, routes, query, _ = prepared(tmp_path)
    output = BytesIO()
    Image.new('RGB',(80,24),(20,40,60)).save(output,format='JPEG')
    payload = output.getvalue()
    app.upload_chart(query['cycle'][0],media_type='image/jpeg',payload=payload)
    query['revision']=[app.snapshot().candidates[0].chart_revision_identity]
    before = _fingerprints(tmp_path)
    result = get(routes,query)
    assert result.status == 200 and result.content_type == 'image/jpeg'
    assert result.body == payload and _fingerprints(tmp_path) == before
