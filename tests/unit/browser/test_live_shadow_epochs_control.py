"""Actual isolated HTTP boundary to real commissioning; no operational service calls."""
from http.client import HTTPConnection
from types import SimpleNamespace
from dataclasses import replace
import json
import pytest

from tests.unit.browser.test_sph_controls import running, request
from tests.unit.intraday.test_live_shadow_epochs import service, restart, authorize, inventory
from kronos.application.intraday_shadow_epochs import commission, ROUTE
from kronos.browser.product_routes import ProductBrowserRoutes
from kronos.browser.intraday_routes import IntradayBrowserRoutes


def post(server,payload,*,origin=None,path=ROUTE):
    host=f'127.0.0.1:{server.server_port}'
    conn=HTTPConnection('127.0.0.1',server.server_port,timeout=10)
    conn.request('POST',path,json.dumps(payload),{'Host':host,'Origin':origin or f'http://{host}','Content-Type':'application/json'})
    result=conn.getresponse();body=result.read();code=result.status;conn.close()
    return code,body


@pytest.mark.parametrize('fault',[None,'outside_maintenance','other_request','provider_connecting','ordinary_accept','cross_origin','self_asserted','query','missing_authority'])
def test_real_http_maintenance_contract(running,tmp_path,fault):
    server,g,p,calls,_=running
    root=tmp_path/'shadow';old,_,_=service(root);s=restart(root,old);payload=authorize(s)
    class Route:
        def handle_get(self,*args):return None
        def commission_shadow_successor(self,payload,**conditions):
            return commission(s,payload,repository=lambda *a:True,**conditions)
    server.product_routes=ProductBrowserRoutes((Route(),))
    if fault=='outside_maintenance':g.maintenance_active=False
    if fault=='other_request':server._active_sponsor_work=1
    if fault=='provider_connecting':
        from kronos.application.swing_opportunities import ProviderConnectionState
        snapshot=server.application.snapshot
        server.application.snapshot=lambda:replace(snapshot(),provider_state=ProviderConnectionState.CONNECTING)
    if fault=='self_asserted':payload['authorized']=True
    if fault=='missing_authority':payload['authorization_identity']='WO06H-AUTHORIZATION-'+'0'*64
    if fault=='ordinary_accept':code,_=request(server,'/intraday/live-shadow/accept-runtime',method='POST')
    else:code,_=post(server,payload,origin='http://foreign.invalid' if fault=='cross_origin' else None,path=ROUTE+'?x=1' if fault=='query' else ROUTE)
    if fault is None:
        assert code==200 and len(s.status()['epochs'])==2
        assert g.maintenance_active
    else:
        assert code>=400 and s._epochs.pointer() is None
    assert calls==[] and p.begin_count==0
    assert not s._epochs.raw.all('observation') and not s._epochs.raw.all('outcome')


@pytest.mark.parametrize('active',['review','discovery'])
def test_intraday_product_quiescence_reaches_real_gate(tmp_path,active):
    old,_,_=service(tmp_path);s=restart(tmp_path,old);payload=authorize(s)
    route=SimpleNamespace(_probables_v2_control=SimpleNamespace(operation_service=SimpleNamespace(live_shadow=s,active_operation_identity='X' if active=='discovery' else None)),
        _review_v2_control=SimpleNamespace(status_document=lambda:{'active_operation_identity':'X' if active=='review' else None}))
    with pytest.raises(ValueError,match='QUIESCENCE'):
        IntradayBrowserRoutes.commission_shadow_successor(route,payload,maintenance=True,idle=True)
    assert s._epochs.pointer() is None
