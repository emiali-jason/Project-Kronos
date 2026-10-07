"""Current/historical Review truth using isolated owning fixtures only."""
from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import pytest

from kronos.browser.views import _receipt_native_review, _review_compact_style
from tests.unit.browser.test_swing_review_intake_binding import (
    native_intake, _current_twelve,
)
from tests.unit.application.test_swing_bulk_import import _owner, EXPECTED, PDF
from tests.unit.swing.v1.test_mcx_supporting_context import _inventory
from tests.unit.browser.test_swing_review_intake_binding import _review_content_metadata

OLD = 'SWING-RUN-3FFDD15932FF45C5AC371BF411AB5202'
PACK = 'KRONOS-V3-REVIEW-CD8078DA0F4541059A874879CE7E774D'

def population():
    run='SWING-RUN-'+'D'*32
    return dict(rows=(), packages=[], error=None, workspace=dict(
        run_identity=run, state='CURRENT', eligible=18, population=18, nse=16,
        mcx=2, excluded=0, analysis_time=datetime(2026,10,5,9,37,tzinfo=UTC),manifest='a'*64))

def batch(state='COMPLETED',run=OLD,pack=PACK):
    return dict(batch_identity='BATCH-OLD',run_identity=run,request_identity='REQUEST-OLD',
        review_pack_identity=pack,received_at='2026-09-25T09:59:24.148041+00:00',state=state,
        failure=None,candidates=[dict(canonical_instrument='INFY',state='SUCCEEDED',
        downstream_state='SUCCEEDED',failure=None)],status_location='/swing/v1/bulk-import-status?batch=BATCH-OLD')

def package(run=OLD,pack=PACK,expected=None):
    return dict(market='NSE',identity='PUBLICATION-OLD',run_identity=run,
        request_identity='REQUEST-OLD',review_pack_identity=pack,question_filename=pack+'_QUESTIONS.pdf',
        answer_filename=pack+'_ANSWERS.pdf',expected=expected)

def test_current_18_and_historical_success_do_not_imply_current_success():
    projection=population();projection['packages']=[package()]
    html=_receipt_native_review(projection,bulk_import=batch())
    assert html.index('Current Review workspace')<html.index('Current Review operation')<html.index('Historical Review activity')
    visible,history=html.split('<details class="review-history">')
    assert '18 eligible / 18 current' in visible and 'NSE 16 · MCX 2' in visible
    assert 'No verified import batch for the current run and Question Pack' in visible
    assert 'BULK ANSWER IMPORT' not in visible and 'COMPLETED' not in visible
    assert 'BULK ANSWER IMPORT' in history and 'COMPLETED' in history and OLD in history and PACK in history
    assert 'RETAINED REVIEW PACK · STALE' in history and '<details class="review-history" open' not in html

@pytest.mark.parametrize('changed',['run','request','pack','stale'])
def test_current_import_requires_all_current_bindings(changed):
    projection=population();value=batch(run=projection['workspace']['run_identity'])
    p=package(run=value['run_identity'],expected={'bound':True});projection['packages']=[p]
    if changed=='run': value['run_identity']=OLD
    elif changed=='request':value['request_identity']='OTHER'
    elif changed=='pack':value['review_pack_identity']='OTHER'
    else:p['expected']=None
    html=_receipt_native_review(projection,bulk_import=value)
    assert 'No verified import batch' in html and 'CURRENT RUN / PACK' not in html

def test_current_batch_remains_visible_and_bound():
    projection=population();value=batch(run=projection['workspace']['run_identity'])
    projection['packages']=[package(run=value['run_identity'],expected={'bound':True})]
    html=_receipt_native_review(projection,bulk_import=value)
    assert 'CURRENT RUN / PACK' in html and 'BULK ANSWER IMPORT' in html
    assert 'No verified import batch' not in html and 'Historical Review activity' not in html
    assert value['run_identity'] in html and value['request_identity'] in html and PACK in html

@pytest.mark.parametrize('state',['ADMITTED','VALIDATING','DOWNSTREAM_RUNNING','FAILED','COMPLETED_WITH_FAILURE','VALIDATION_FAILED'])
def test_pending_and_failed_retained_batches_are_never_collapsed(state):
    html=_receipt_native_review(population(),bulk_import=batch(state))
    assert 'BULK ANSWER IMPORT' in html and 'NOT VERIFIED FOR CURRENT PACK' in html
    assert 'Historical Review activity' not in html

def test_unavailable_evidence_remains_visible_without_history_fallback():
    projection=population();projection['error']='REVIEW_BINDING_STALE';projection['packages']=[package()]
    html=_receipt_native_review(projection,bulk_import={'unavailable':True})
    assert 'REVIEW BINDING UNAVAILABLE' in html and 'IMPORT STATUS UNAVAILABLE' in html
    assert 'Historical Review activity' not in html

def test_bulk_owner_exposes_retained_run_only_and_gets_are_write_free(tmp_path):
    owner,intake,store=_owner(tmp_path);value,_=owner.admit('NSE',EXPECTED,PDF)
    before=_review_content_metadata(tmp_path)
    shown=owner.presentation(value['batch_identity'])
    assert shown['run_identity']==EXPECTED['ONE']['expected_run_identity']
    assert shown['request_identity']==value['request_identity'] and shown['review_pack_identity']==value['review_pack_identity']
    assert 'expected' not in shown and 'answer_sha256' not in shown and 'answer_relative_path' not in shown
    assert _review_content_metadata(tmp_path)==before

@pytest.mark.parametrize('native_intake',['NSE'],indirect=True)
def test_actual_intake_projection_preserves_current_18_and_stale_pack_metadata(native_intake,tmp_path):
    from tests.unit.swing.v1.test_native_review import _evidence_run
    from kronos.swing.v1.native_discovery import NativeProductPath
    facts,base,probable=_evidence_run()
    names=tuple(a.canonical_instrument for a in base.assessments if a.product_path is NativeProductPath.NSE)[:16]+('GOLDM','CRUDEOIL')
    assert len(names)==18
    _current_twelve(native_intake,candidate_names=names)
    before=_review_content_metadata(tmp_path)
    projection=native_intake.snapshot()
    assert projection['workspace']['eligible']==18 and projection['workspace']['nse']==16 and projection['workspace']['mcx']==2
    html=_receipt_native_review(projection,bulk_import=batch())
    assert '18 eligible / 18 current' in html and len(projection['rows'])==18
    assert _review_content_metadata(tmp_path)==before

def test_compact_style_is_scoped_to_swing_review_and_wraps_metadata():
    css=_review_compact_style()
    assert 'font-size:12px' in css and 'overflow-wrap:anywhere' in css
    assert '@media(max-width:760px)' in css and '.swing-review-compact' in css

@pytest.mark.parametrize('native_intake',['NSE'],indirect=True)
def test_actual_review_get_reports_unavailable_import_and_preserves_metadata(native_intake,tmp_path):
    from threading import Thread
    from types import SimpleNamespace
    from tests.unit.browser.test_swing_review_intake_binding import _page_load_server
    from tests.unit.browser.test_browser_server import _request
    state,names=_current_twelve(native_intake)
    server=_page_load_server(native_intake,state)
    def unavailable(*args): raise ValueError('ISOLATED_RETAINED_STATUS_INVALID')
    server.bulk_import=SimpleNamespace(presentation=unavailable,close=lambda:None)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        before=_review_content_metadata(tmp_path)
        status,headers,body=_request(server,'GET','/swing/v1-review')
        assert status==200 and 'IMPORT STATUS UNAVAILABLE' in body
        assert 'ISOLATED_RETAINED_STATUS_INVALID' not in body
        assert _review_content_metadata(tmp_path)==before
    finally:
        server.shutdown();server.server_close();thread.join(5)
        assert not thread.is_alive()
