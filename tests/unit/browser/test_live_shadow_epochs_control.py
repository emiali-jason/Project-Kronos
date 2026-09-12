"""Actual isolated HTTP boundary to real commissioning; no operational service calls."""
from http.client import HTTPConnection
from types import SimpleNamespace
from dataclasses import replace
import json
import pytest

from tests.unit.browser.test_sph_controls import running, request
from tests.unit.intraday.test_live_shadow_epochs import service, restart, authorize, inventory
from kronos.application.intraday_shadow_epochs import commission, ROUTE
from kronos.application.intraday_shadow_compatibility import (
    ROUTE as RESTORATION_ROUTE,
    restoration_request,
    restore_compatible_epoch,
)
from kronos.browser.product_routes import ProductBrowserRoutes
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from tests.unit.intraday.test_live_shadow_epoch_deterministic_digest import (
    accepted_service,
    corrected_restart,
    retain_equivalence,
)


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


def compatible_case(tmp_path):
    historical = accepted_service(tmp_path)
    successor = restart(tmp_path, historical)
    commission(successor, authorize(successor), maintenance=True, idle=True, repository=lambda *args: True)
    current = corrected_restart(tmp_path, successor)
    record = retain_equivalence(current)
    epoch = current._epochs.chain()[0]
    payload = restoration_request(
        epoch_identity=epoch["identity"], acceptance_identity=epoch["body"]["acceptance"],
        window_identity=epoch["body"]["window"], current_runtime_proof=current._runtime_proof(),
        compatibility_identity=record["identity"],
        sponsor_authorization=record["body"]["sponsor_authorization"],
    )
    return current, payload


@pytest.mark.parametrize("fault", [None, "outside_maintenance", "other_request", "cross_origin", "query", "malformed"])
def test_real_http_compatibility_restoration_contract(running, tmp_path, fault):
    server, governance, provider, calls, _ = running
    shadow, payload = compatible_case(tmp_path)

    class Route:
        def handle_get(self, *args): return None
        def restore_shadow_compatibility(self, supplied, **conditions):
            return restore_compatible_epoch(shadow, supplied, **conditions)

    server.product_routes = ProductBrowserRoutes((Route(),))
    if fault == "outside_maintenance": governance.maintenance_active = False
    if fault == "other_request": server._active_sponsor_work = 1
    if fault == "malformed": payload = {"action": "RESTORE_SAME_EPOCH_COMPATIBILITY"}
    code, body = post(server, payload,
        origin="http://foreign.invalid" if fault == "cross_origin" else None,
        path=RESTORATION_ROUTE + "?x=1" if fault == "query" else RESTORATION_ROUTE)
    if fault is None:
        assert code == 200 and json.loads(body)["outcome"] == "RESTORED"
        assert shadow.status()["acceptance_disposition"] == "EXISTING_ACCEPTANCE_RESTORED"
        assert governance.maintenance_active
    else:
        assert code >= 400 and not shadow.status()["enabled"]
    assert calls == [] and provider.begin_count == 0


@pytest.mark.parametrize("active", ["review", "discovery"])
def test_intraday_product_quiescence_blocks_compatibility_restoration(tmp_path, active):
    shadow, payload = compatible_case(tmp_path)
    route = SimpleNamespace(
        _probables_v2_control=SimpleNamespace(operation_service=SimpleNamespace(
            live_shadow=shadow, active_operation_identity="X" if active == "discovery" else None)),
        _review_v2_control=SimpleNamespace(status_document=lambda: {
            "active_operation_identity": "X" if active == "review" else None}),
    )
    with pytest.raises(ValueError, match="QUIESCENCE"):
        IntradayBrowserRoutes.restore_shadow_compatibility(route, payload, maintenance=True, idle=True)
    assert not shadow.status()["enabled"]
