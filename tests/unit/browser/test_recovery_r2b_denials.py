"""Concrete existing route/control/render paths with injected typed denials."""
from http import HTTPStatus
import json
import pytest
from kronos.browser.product_routes import BrowserPostRequest
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.intraday.evidence_currentness import NewWorkNotEligible,EligibilityReason,NewWorkAction
from tests.unit.browser.test_intraday_review_v2_control import _control,_payload,_Workstation,_snapshot
from tests.unit.intraday.test_review import _application
from tests.unit.intraday.test_probables import _member,_run as _run_v1


def denial(*args,**kwargs):
    raise NewWorkNotEligible(EligibilityReason.HISTORICAL_SESSION,action=NewWorkAction.READINESS_HANDOFF)


def fixture(tmp_path):
    run,app,control=_control(tmp_path/'v2')
    v1=_application(tmp_path/'v1',[_run_v1((_member('V1-FIXTURE'),))])
    routes=IntradayBrowserRoutes(_Workstation(run),review=v1,review_v2_control=control)
    return run,app,control,routes


def test_review_control_denial_keeps_exact_reason_and_creates_no_audit(tmp_path,monkeypatch):
    run,app,control,routes=fixture(tmp_path)
    monkeypatch.setattr(app,'currentize_eligible_cycles_for_run_identity',denial)
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    response=routes.handle_post(BrowserPostRequest('/control/intraday-review/v2',{},'application/json',json.dumps(_payload(run)).encode()),_snapshot)
    assert response.status is HTTPStatus.CONFLICT
    d=json.loads(response.body)
    assert d['failure_reason']=='HISTORICAL_SESSION' and d['failure_stage']=='NEW_WORK_ELIGIBILITY'
    assert d['provenance_identity'] is None and d['currentization_state']=='NOT_CURRENTIZED'
    assert {str(p):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('path,method',[
    ('/intraday/review/question-packs','create_all_question_transports'),
    ('/intraday/review/answers','import_all_expected_answers'),
    ('/intraday/review/reconcile-all','reconcile_current_ready'),
])
def test_ordinary_form_denial_renders_readable_history(tmp_path,monkeypatch,path,method):
    run,app,control,routes=fixture(tmp_path);monkeypatch.setattr(app,method,denial)
    response=routes.handle_post(BrowserPostRequest(path,{},'',b''),_snapshot)
    assert response.status is HTTPStatus.CONFLICT
    assert response.content_type.startswith('text/html')
    assert '<aside role="alert">' in response.body and 'HISTORICAL_SESSION' in response.body
    assert 'Retained dated evidence remains readable' in response.body and run.run_identity in response.body


def test_json_denial_is_client_visible(tmp_path,monkeypatch):
    run,app,control,routes=fixture(tmp_path);monkeypatch.setattr(app,'import_all_expected_answers',denial)
    response=routes.handle_post(BrowserPostRequest('/intraday/review/answers',{},'application/json',b''),_snapshot)
    assert response.status is HTTPStatus.CONFLICT
    assert json.loads(response.body)['reason']=='HISTORICAL_SESSION'


def test_genuine_schema_failure_remains_bad_request(tmp_path,monkeypatch):
    run,app,control,routes=fixture(tmp_path)
    def bad(*args,**kwargs):raise ValueError('GENUINE_SCHEMA_FAILURE')
    monkeypatch.setattr(app,'create_all_question_transports',bad)
    response=routes.handle_post(BrowserPostRequest('/intraday/review/question-packs',{},'',b''),_snapshot)
    assert response.status is HTTPStatus.BAD_REQUEST and 'HISTORICAL_SESSION' not in response.body
