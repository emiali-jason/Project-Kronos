"""PLC-02 negative composition and production-shaped disposable assurance."""
from http import HTTPStatus
from http.client import HTTPConnection
from threading import Thread
from urllib.parse import urlencode
import json
import pytest

from tools import kronos_browser
from kronos.browser.product_routes import (
    BrowserGetRequest,BrowserPostRequest,ProductBrowserRoutes,BrowserRouteResponse,
)
from kronos.browser.theta_composition import compose_theta_browser_routes
from kronos.swing.v1.mcx_contract_profile import McxFamily
from tests.unit.tools.test_kronos_browser import (
    isolated_composition_authority,
    test_launcher_uses_loopback_server_and_opens_swing_workspace as canonical_scenario,
)


def test_theta_setup_failure_does_not_suppress_canonical_existing_products(monkeypatch,tmp_path):
    def unavailable():
        raise ValueError('CONTROLLED_SYNTHETIC_THETA_SETUP_FAILURE')
    monkeypatch.setattr(kronos_browser,'compose_theta_sponsor_workflow',unavailable)
    canonical_scenario(monkeypatch,tmp_path,McxFamily.CRUDEOIL)


@pytest.mark.parametrize('failure',[OSError,ValueError,RuntimeError])
def test_theta_failure_is_visible_bounded_and_never_reconstructs_other_owner(failure):
    class Existing:
        def handle_get(self,request,snapshot):
            return BrowserRouteResponse('EXISTING') if request.path=='/intraday' else None
    owner=Existing();existing=ProductBrowserRoutes((owner,));calls=[]
    def unavailable():
        calls.append('Theta');raise failure('SYNTHETIC sensitive failure text must not escape')
    combined=compose_theta_browser_routes(existing,factory=unavailable)
    assert combined._routes[0] is owner and existing._routes==(owner,) and calls==['Theta']
    def forbidden_snapshot():raise AssertionError('No other product snapshot on Theta failure')
    assert combined.dispatch_get(BrowserGetRequest('/intraday',{}),forbidden_snapshot).body=='EXISTING'
    for path in ('/theta-earners','/theta-earners/new-analysis','/theta-earners/detail'):
        response=combined.dispatch_get(BrowserGetRequest(path,{}),forbidden_snapshot)
        assert response.status==HTTPStatus.SERVICE_UNAVAILABLE
        assert 'THETA_SPONSOR_WORKFLOW_UNAVAILABLE' in response.body
        assert 'sensitive' not in response.body
    for path in ('/theta-earners/chart','/theta-earners/question','/theta-earners/import'):
        response=combined.dispatch_post(BrowserPostRequest(path,{},'application/json',b'{}'),forbidden_snapshot)
        assert response.status==HTTPStatus.SERVICE_UNAVAILABLE
    assert not combined.owns_post('/orders') and not combined.owns_post('/swing/analysis')
    assert combined.dispatch_get(BrowserGetRequest('/foreign',{}),forbidden_snapshot) is None
    with pytest.raises(ValueError,match='ALREADY_REGISTERED'):
        compose_theta_browser_routes(combined,factory=unavailable)
    assert calls==['Theta']


@pytest.mark.parametrize('owner',['Swing','Intraday'])
def test_other_product_failure_does_not_mask_the_theta_failure(owner):
    class Existing:
        def handle_get(self,request,snapshot):
            if request.path=='/'+owner.lower():raise ValueError('CONTROLLED_OWNED_FAILURE')
    def unavailable():raise ValueError('CONTROLLED_THETA_FAILURE')
    registry=compose_theta_browser_routes(ProductBrowserRoutes((Existing(),)),factory=unavailable)
    with pytest.raises(ValueError,match='CONTROLLED_OWNED_FAILURE'):
        registry.dispatch_get(BrowserGetRequest('/'+owner.lower(),{}),lambda:None)
    assert registry.dispatch_get(BrowserGetRequest('/theta-earners',{}),lambda:None).status==HTTPStatus.SERVICE_UNAVAILABLE


def test_three_product_current_composition_navigation_restart_and_private_shutdown(tmp_path):
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.application.intraday_runtime import create_intraday_runtime
    from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    from kronos.browser.intraday_wo08 import IntradayWo08Projection,IntradayVisualHistory
    from kronos.browser.restart_control import BrowserBackendRestartControl
    from kronos.browser.server import create_browser_server
    from kronos.theta.composition import compose_theta_sponsor_workflow
    from kronos.theta.operational import admit_originals
    from tests.unit.theta.test_plc01_integration import configured
    from tests.unit.theta.test_operational_trial import originals,synthetic_answer
    from tests.unit.theta.test_combined_intake import snapshot
    app=configured(tmp_path);admit_originals(app,originals(),sponsor_confirmed=True)
    batch=app.create_question_pack(app.input_state_sha256())['result']['batch_id']
    descriptor,questions=app.intake._batch(batch)
    (app.workflow.inbox/(batch+'_ANSWERS.json')).write_bytes(synthetic_answer(descriptor,questions))
    accepted=app.import_astra_answers(batch)['result'];before=snapshot(app.store.root);calls=[]
    def forbidden(*_,**__):calls.append('FORBIDDEN');raise AssertionError('PLC02_PROVIDER_FORBIDDEN')
    for iteration in range(2):
        if iteration:app=compose_theta_sponsor_workflow(root=app.store.root,inbox=app.workflow.inbox,outbox=app.workflow.outbox)
        shared=SharedAuthenticatedProviderRuntime(forbidden,provider_identity='KITE')
        intraday=create_intraday_runtime(shared,evidence_root=tmp_path/'intraday')
        owner=IntradayBrowserRoutes(intraday.discovery_v2_application,
            wo08_projection=IntradayWo08Projection(intraday.wo08_store,intraday.probables_v2_store),
            visual_history=IntradayVisualHistory(intraday.review_v2_store,intraday.mcx_paired_review_store,
                                                intraday.visual_reconciliation_v2_store),
            prospective_programme_v2=True,review_workstation=intraday.discovery_application)
        registry=compose_theta_browser_routes(ProductBrowserRoutes((owner,)),factory=lambda:app)
        # Same visibly synthetic preview wrapper as the qualified trial fixture;
        # do not relabel genuine authority/Question bindings or alter production UX.
        theta=registry._routes[-1];render=theta._page
        def synthetic_page(snapshot,body,**kwargs):
            return render(snapshot,'<p>SYNTHETIC — NOT FOR GENUINE FORECASTING</p>'+body,**kwargs)
        theta._page=synthetic_page
        # Synthetic private control only; never an existing runtime credential.
        token='a'*64;control=BrowserBackendRestartControl.create(tmp_path/f'control-{iteration}',process_id=4242,token=token)
        server=create_browser_server(SwingOpportunitiesApplication(forbidden),port=0,product_routes=registry,restart_control=control)
        server.service_actions=lambda:None
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(path,method='GET',headers=None):
            c=HTTPConnection('127.0.0.1',server.server_port,timeout=20)
            try:
                c.request(method,path,headers=headers or {});r=c.getresponse();return r.status,r.read()
            finally:c.close()
        try:
            assert server.server_port not in {8947,8948,8968,8970}
            for path in ('/swing/opportunities','/intraday','/intraday/review','/theta-earners','/theta-earners/new-analysis'):
                status,body=request(path);assert status==200,(path,status)
            status,outlook=request('/theta-earners');assert outlook.count(b'data-theta-subject=')==5
            assert b'SYNTHETIC' in outlook and b'OUTLOOK' in outlook
            status,analysis=request('/theta-earners/new-analysis')
            assert analysis.count(b'CREATE THETA QUESTION PACK')==1 and analysis.count(b'IMPORT ASTRA ANSWERS')==1
            assert analysis.count(b'data-upload-url=')==6
            for subject,q in questions.items():
                assert request('/theta-earners/detail?'+urlencode({'subject':subject,'question':q['question_id']}))[0]==200
            assert snapshot(app.store.root)==before
            assert server.maintenance_admission.snapshot()['owners']=={}
            headers={'Host':f'127.0.0.1:{server.server_port}','X-Kronos-Backend-Pid':'4242',
                     'X-Kronos-Restart-Token':token,'Content-Length':'0'}
            assert request('/control/shutdown','POST',dict(headers,**{'X-Kronos-Restart-Token':'b'*64}))[0]==403
            assert snapshot(app.store.root)==before
            status,body=request('/control/shutdown','POST',headers)
            assert status==202 and token.encode() not in body
            thread.join(timeout=5);assert not thread.is_alive()
        finally:
            if thread.is_alive():server.shutdown();thread.join(5)
            server.server_close();shared.end_kronos_session()
        assert not control.path.exists() and snapshot(app.store.root)==before
    restored=app.restore_status()['import_operation']['result']
    assert restored['intake']==accepted['intake'] and restored['assessments']==accepted['assessments']
    assert calls==[]
