"""PLC-01 three-product rehearsal. Kernel-guarded disposable stores only."""
from contextlib import contextmanager
from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode

import pytest

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.intraday_runtime import create_intraday_workstation
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import ProductBrowserRoutes, with_theta_routes
from kronos.browser.server import create_browser_server
from kronos.theta.composition import compose_theta_sponsor_workflow
from kronos.theta.operational import admit_originals
from tests.unit.theta.test_operational_trial import originals,synthetic_answer
from tests.unit.theta.test_combined_intake import snapshot


def configured(root):
    inbox=root/'answers';outbox=root/'questions'
    inbox.mkdir();outbox.mkdir()
    return compose_theta_sponsor_workflow(root=root/'theta',inbox=inbox,outbox=outbox)


def test_prospective_composition_is_offline_and_does_not_create_a_store(tmp_path):
    app=configured(tmp_path)
    assert not app.workflow.qualification_mode and not app.store.root.exists()
    assert not list(app.workflow.inbox.iterdir()) and not list(app.workflow.outbox.iterdir())
    assert app.producer.published_methodology is not None
    assert app.producer.target_authority.owner.review is not None


def test_append_preserves_current_intraday_owner_and_rejects_duplicate_theta(tmp_path):
    app=configured(tmp_path);owner=IntradayBrowserRoutes(create_intraday_workstation())
    original=ProductBrowserRoutes((owner,));combined=with_theta_routes(original,
        theta_workflow=app.workflow,theta_sponsor_workflow=app)
    assert combined._routes[0] is owner and original._routes==(owner,)
    assert len(combined._routes)==2
    with pytest.raises(ValueError,match='ALREADY_REGISTERED'):with_theta_routes(combined)
    for path in ('/swing/analysis','/intraday/review/load','/orders','/provider/connect'):
        assert not combined._routes[1].owns_post(path)


def test_portable_rehearsal_answer_uses_source_fixture_without_old_output():
    from kronos.theta.contracts_v3 import combined_answer_template
    from tests.unit.theta.v3_fixture import synthetic_contracts
    from tools.theta_trial_rehearsal import answer
    questions,batch,_=synthetic_contracts()
    template=combined_answer_template(batch,questions)
    completed=json.loads(answer(template,questions))
    assert completed['answer_package_id']=='SYNTHETIC-TE09R-COMPLETE'
    for subject,child in completed['answers'].items():
        assert child['binding']==template['answers'][subject]['binding']
        assert 'SYNTHETIC' in child['analyst']['provenance']
        assert all('SYNTHETIC' in source['title'] for source in child['research']['sources'])
        for horizon in ('E1','E2'):
            assert child['forecasts'][horizon]['target']==template['answers'][subject]['forecasts'][horizon]['target']


@contextmanager
def server(app,calls):
    def forbidden():calls.append('Provider');raise AssertionError('PLC01_PROVIDER_FORBIDDEN')
    registry=with_theta_routes(ProductBrowserRoutes((IntradayBrowserRoutes(create_intraday_workstation()),)),
                              theta_workflow=app.workflow,theta_sponsor_workflow=app)
    current=create_browser_server(SwingOpportunitiesApplication(forbidden),port=0,product_routes=registry)
    current.service_actions=lambda:None
    thread=Thread(target=current.serve_forever,daemon=True);thread.start()
    try:yield current
    finally:current.shutdown();current.server_close();thread.join(timeout=5);assert not thread.is_alive()


def get(server,path):
    c=HTTPConnection('127.0.0.1',server.server_port,timeout=20)
    try:c.request('GET',path);r=c.getresponse();return r.status,r.read()
    finally:c.close()


def test_three_product_http_and_disposable_restart_preserve_theta_evidence(tmp_path):
    app=configured(tmp_path);admit_originals(app,originals(),sponsor_confirmed=True)
    batch=app.create_question_pack(app.input_state_sha256())['result']['batch_id']
    descriptor,questions=app.intake._batch(batch)
    raw=synthetic_answer(descriptor,questions)
    (app.workflow.inbox/(batch+'_ANSWERS.json')).write_bytes(raw)
    result=app.import_astra_answers(batch)['result'];assert result['intake']['package_status']=='COMPLETE'
    before=snapshot(app.store.root);calls=[]
    for restarted in (False,True):
        if restarted:app=compose_theta_sponsor_workflow(root=app.store.root,inbox=app.workflow.inbox,outbox=app.workflow.outbox)
        with server(app,calls) as runtime:
            assert runtime.server_port not in {8947,8948,8968,8970}
            for path,label in (('/swing/opportunities',b'Swing'),('/intraday',b'Intraday'),('/theta-earners',b'Theta')):
                status,body=get(runtime,path);assert status==200 and label in body,(path,status)
                if path!='/theta-earners':assert b'ASTRA FORECAST' not in body
            status,analysis=get(runtime,'/theta-earners/new-analysis')
            assert status==200 and analysis.count(b'CREATE THETA QUESTION PACK')==1
            assert analysis.count(b'IMPORT ASTRA ANSWERS')==1
            for sub,q in questions.items():
                status,body=get(runtime,'/theta-earners/detail?'+urlencode({'subject':sub,'question':q['question_id']}))
                assert status==200 and sub.encode() in body
            assert snapshot(app.store.root)==before
    assert calls==[]
    restored=app.restore_status()['import_operation']['result']
    assert restored['intake']['package_status']=='COMPLETE'
    assert {s:r['receipt_id'] for s,r in restored['intake']['children'].items()}=={s:r['receipt_id'] for s,r in result['intake']['children'].items()}
