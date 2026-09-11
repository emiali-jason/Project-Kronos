"""Risk preview is read-only and never makes Browser arithmetic authoritative."""
import json
import pytest
from kronos.browser.intraday_futures_control import IntradayFuturesControl,render_futures,RISK_PREVIEW_ROUTE
from kronos.browser.product_routes import BrowserPostRequest
from tests.unit.intraday.test_wo10_futures import fixture,config,session
from tests.unit.intraday.test_wo10_advisory_risk import files
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.browser.test_intraday_review_workflow import _routes


def test_red_warning_and_above_reference_selection(tmp_path):
    app,kw=fixture(tmp_path/'f');c=app.evaluate(**kw);control=IntradayFuturesControl(app,lambda subject,now:session(now))
    before=files(tmp_path);preview=control.preview_document(dict(comparison_identity=c.identity,lots=6))
    assert preview['outcome']=='PREVIEW' and preview['persisted'] is False and files(tmp_path)==before
    assert preview['advisory']['risk_warning_state']=='ABOVE_REFERENCE'
    payload=dict(comparison_identity=c.identity,choice='SELECTED_FUTURE',lots=6,action_identity='s')
    assert control.execute_document(payload)['outcome']=='RETAINED'
    html=render_futures(_snapshot(),control.status_document())
    assert 'ABOVE RISK REFERENCE' in html and 'risk-above' in html and 'color:#a40000' in html
    assert '₹ excess: 400' in html and '% excess: 20' in html
    assert "max='" not in html and 'Maximum lots' not in html
    assert "value='SELECTED_FUTURE' disabled" not in html
    assert "value='6'" in html
    assert len(kw['provider'].calls)==1


def test_readonly_preview_route_has_no_source_or_persistence_authority(tmp_path):
    app,kw=fixture(tmp_path/'f');c=app.evaluate(**kw);*_,routes=_routes(tmp_path/'b')
    routes._futures_control=IntradayFuturesControl(app,lambda subject,now:session(now))
    before=files(tmp_path)
    response=routes.handle_post(BrowserPostRequest(RISK_PREVIEW_ROUTE,{},'application/json',json.dumps(dict(comparison_identity=c.identity,lots=6)).encode()),_snapshot)
    assert response.status==200 and json.loads(response.body)['outcome']=='PREVIEW'
    assert files(tmp_path)==before and len(kw['provider'].calls)==1
    invalid=routes.handle_post(BrowserPostRequest(RISK_PREVIEW_ROUTE,{},'application/json',json.dumps(dict(comparison_identity=c.identity,lots=6,risk_per_lot=1)).encode()),_snapshot)
    assert invalid.status==400
    assert files(tmp_path)==before

@pytest.mark.parametrize('lots',[True,0,-1,1.5,'6'])
def test_preview_rejects_invalid_lots_without_side_effect(tmp_path,lots):
    app,kw=fixture(tmp_path);c=app.evaluate(**kw);control=IntradayFuturesControl(app,lambda subject,now:session(now));before=files(tmp_path)
    assert control.preview_document(dict(comparison_identity=c.identity,lots=lots))['outcome']=='REJECTED'
    assert files(tmp_path)==before
