"""Exact control -> route conflict transport; no analytical or market authority."""
import json
from types import SimpleNamespace
import pytest
from kronos.browser.intraday_futures_control import IntradayFuturesControl
from kronos.browser.intraday_lifecycle_control import IntradayLifecycleControl
from kronos.browser.product_routes import BrowserPostRequest
from kronos.intraday.wo09_persistence import Wo09PublicationConflict
from kronos.intraday.evidence_currentness import NewWorkNotEligible, EligibilityReason, NewWorkAction
from tests.unit.browser.test_intraday_review_workflow import _routes, _fingerprints
from tests.unit.browser.test_product_route_isolation import _snapshot

CASES = (
    ('/control/intraday-futures/construction', {'handoff_identity':'h','request_identity':'r'}),
    ('/control/intraday-futures/selection', {'comparison_identity':'c','choice':'SELECTED_FUTURE','lots':1,'action_identity':'s'}),
    ('/control/intraday-lifecycle/v1', {'handoff_identity':'h','action':'OBSERVE','action_identity':'a'}),
)

@pytest.mark.parametrize('path,payload', CASES)
@pytest.mark.parametrize('error,status,stage', [
    (Wo09PublicationConflict(),409,'PUBLICATION_CONFLICT'),
    (ValueError('INTEGRITY_INVALID'),400,None),
    (OSError('STORAGE_FAILED'),400,None),
    (NewWorkNotEligible(EligibilityReason.ELIGIBILITY_AUTHORITY_UNAVAILABLE, action=NewWorkAction.LIFECYCLE_PRE_ENTRY),400,'NEW_WORK_ELIGIBILITY'),
])
def test_typed_handler_precedence_and_no_writes(tmp_path,path,payload,error,status,stage):
    def fail(*args,**kwargs):raise error
    app=SimpleNamespace(construct_current=fail,select=fail,action=fail,
        store=SimpleNamespace(load=lambda _:SimpleNamespace(data={'subject':'NSE-EQ-LUPIN'})),clock=lambda:None)
    *_,routes=_routes(tmp_path)
    routes._futures_control=IntradayFuturesControl(app,lambda *_:None)
    routes._lifecycle_control=IntradayLifecycleControl(app)
    before=_fingerprints(tmp_path)
    response=routes.handle_post(BrowserPostRequest(path,{},'application/json',json.dumps(payload).encode()),_snapshot)
    result=json.loads(response.body)
    assert response.status==status and result['outcome']=='REJECTED'
    assert result.get('failure_stage')==stage
    if stage=='PUBLICATION_CONFLICT':
        assert result['reason']==result['failure_reason']=='WO09_PUBLICATION_EXPECTATION_CHANGED'
    assert _fingerprints(tmp_path)==before

@pytest.mark.parametrize('path,payload', CASES)
def test_invalid_payload_is_still_400(tmp_path,path,payload):
    def unreachable(*args,**kwargs):pytest.fail('invalid payload must not reach application')
    app=SimpleNamespace(construct_current=unreachable,select=unreachable,action=unreachable)
    *_,routes=_routes(tmp_path)
    routes._futures_control=IntradayFuturesControl(app,unreachable)
    routes._lifecycle_control=IntradayLifecycleControl(app)
    response=routes.handle_post(BrowserPostRequest(path,{},'application/json',b'{"extra":"invalid"}'),_snapshot)
    assert response.status==400
