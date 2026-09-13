"""Shared runtime authority qualification with fake Providers and isolated stores."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest

from kronos.browser.runtime_state import complete_startup, decorate_html, status_document
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from tests.unit.provider.test_connection_governance import governance, GENERATION
from tests.unit.application.test_shared_monitoring import Capability, Consumer, ONE, TWO, tick
from tests.unit.browser.test_sph_controls import running, request
from tests.unit.intraday.test_live_shadow import service
from tests.unit.intraday.test_live_shadow_epochs import restart, inventory
from tests.unit.intraday.test_live_shadow_epoch_deterministic_digest import production_case, retain_equivalence, corrected_restart


def server_for(g):
    return SimpleNamespace(connection_governance=g, provider_runtime=SimpleNamespace(read_only_status=lambda:dict(capability_state="ABSENT")), trade_window=SimpleNamespace(paper_observation_projections=lambda:()), visual_v3_live=SimpleNamespace(restoration_error=None),
        application=SimpleNamespace(authenticated_read_only_capability=lambda:None,
            snapshot=lambda:SimpleNamespace(provider_state=SimpleNamespace(value='DISCONNECTED'))),
        swing_monitoring_hub=SharedSwingMonitoringHub())


def test_exact_automatic_restoration_and_maintenance_exit(tmp_path):
    old,_,_=service(tmp_path/'shadow')
    before=inventory(tmp_path/'shadow')
    current=restart(tmp_path/'shadow',old,changed=False)
    s=server_for(governance(tmp_path, maintenance=GENERATION));complete_startup(s,current)
    assert s.connection_governance.startup_state=='READY'
    assert not s.connection_governance.maintenance_active
    assert current.status()['acceptance_disposition']=='EXISTING_ACCEPTANCE_RESTORED'
    assert inventory(tmp_path/'shadow')==before
    after=inventory(tmp_path);complete_startup(s,current);assert inventory(tmp_path)==after


def test_existing_compatible_startup_restores_without_manual_request(production_case,tmp_path):
    retain_equivalence(production_case)
    before=inventory(production_case._epochs.raw.root)
    current=corrected_restart(production_case._epochs.raw.root.parent,production_case)
    s=server_for(governance(tmp_path/'governance',maintenance=GENERATION));complete_startup(s,current)
    assert current.status()['enabled']
    assert s.connection_governance.startup_state=='READY'
    assert current.status()['window']==production_case.status()['window']
    assert inventory(production_case._epochs.raw.root)==before


@pytest.mark.parametrize('fault',['epoch','acceptance','window','historical','corrected','diagnosis','sponsor','evidence'])
def test_wrong_compatibility_stays_failed_active(production_case,tmp_path,fault):
    retain_equivalence(production_case,fault=fault)
    current=corrected_restart(production_case._epochs.raw.root.parent,production_case)
    s=server_for(governance(tmp_path/'governance',maintenance=GENERATION));complete_startup(s,current)
    assert s.connection_governance.maintenance_status()['state']=='FAILED_ACTIVE'
    assert not current.status()['runtime_accepted']


def test_material_capability_change_never_exits_maintenance(tmp_path):
    old,_,_=service(tmp_path/'shadow');current=restart(tmp_path/'shadow',old,changed=True)
    s=server_for(governance(tmp_path,maintenance=GENERATION));complete_startup(s,current)
    assert s.connection_governance.maintenance_status()['state']=='FAILED_ACTIVE'
    assert not list((tmp_path/'audit').rglob('*.json'))


@pytest.mark.parametrize('fault',['shadow','swing','provider','transport','write'])
def test_health_gate_failures_remain_visible(tmp_path,fault,monkeypatch):
    s=server_for(governance(tmp_path,maintenance=GENERATION))
    shadow=SimpleNamespace(status=lambda:dict(failure=None,window=None,runtime_accepted=False))
    if fault=='shadow': shadow.status=Mock(side_effect=ValueError('incomplete'))
    if fault=='swing': s.visual_v3_live.restoration_error='CORRUPT'
    if fault=='provider': s.provider_runtime.read_only_status=lambda:dict(capability_state='RETAINED_UNEXPIRED')
    if fault=='transport': s.swing_monitoring_hub._session=object()
    if fault=='write': monkeypatch.setattr('kronos.common.connection_governance.immutable_write',Mock(side_effect=OSError()))
    complete_startup(s,shadow)
    assert s.connection_governance.maintenance_status()['state']=='FAILED_ACTIVE'


@pytest.mark.parametrize('product',['Swing','Intraday','Settings','Notifications','Trading Journal','Portfolio','Reports'])
@pytest.mark.parametrize('active',[False,True])
def test_all_html_products_share_one_maintenance_authority(tmp_path,product,active):
    g=governance(tmp_path,maintenance=GENERATION if active else None)
    html=decorate_html('<html><body><h1>'+product+'</h1></body></html>',g)
    assert ('END MAINTENANCE' in html)==active
    assert '/runtime/status' in html and 'visibilitychange' in html and 'pageshow' in html
    assert 'setInterval' not in html


def test_browser_status_is_inert_and_cross_product_truth_consistent(running):
    server,g,p,calls,root=running
    before=inventory(root)
    for path in ['/runtime/status','/status','/swing/opportunities','/intraday','/settings','/runtime/status']:
        code,body=request(server,path)
        if path=='/runtime/status':
            assert code==200
            d=json.loads(body)
            assert d['maintenance']['active'] and d['rest_authentication']=='DISCONNECTED'
            assert d['rest_capability']=='NOT_EXPOSED' and d['monitoring']['transport_state']=='IDLE'  # legacy fixture lacks the pure Provider projection
    assert p.begin_count==0 and calls==[]
    assert inventory(root)==before


def test_rest_connected_does_not_imply_websocket_live(tmp_path):
    s=server_for(governance(tmp_path));cap=Capability()
    s.application.authenticated_read_only_capability=Mock(side_effect=AssertionError('getter must not run'))
    s.provider_runtime.read_only_status=lambda:dict(capability_state='RETAINED_UNEXPIRED')
    s.application.snapshot=lambda:SimpleNamespace(provider_state=SimpleNamespace(value='CONNECTED'))
    d=status_document(s)
    assert d['rest_capability']=='RETAINED_UNEXPIRED' and d['monitoring']['transport_state']=='IDLE'
    assert d['maintenance']['state']=='INACTIVE'


def test_monitoring_status_owner_subscriptions_continuity_and_inertness():
    h=SharedSwingMonitoringHub();c=Capability();owners=[]
    for i in (ONE,TWO):
        reg=h.open(c,Consumer());reg.subscribe((i,));reg.connect();owners.append(reg)
    assert h.status_document()['transport_state']=='CONNECTING'
    h.on_connection_state(MonitoringConnectionState.CONNECTED);h.on_market_tick(tick(ONE))
    before=(len(c.sessions),c.sessions[0].connections,len(c.sessions[0].subscribed))
    for _ in range(10):
        d=h.status_document();assert d['owner_count']==2 and d['subscription_count']==2
        assert d['owners'][0]['instruments'][0]['latest_observation']['session_continuous'] is True
        assert d['owners'][1]['instruments'][0]['latest_observation'] is None
    assert (len(c.sessions),c.sessions[0].connections,len(c.sessions[0].subscribed))==before
    h.on_connection_state(MonitoringConnectionState.DISCONNECTED)
    assert h.status_document()['last_interruption']=='DISCONNECTED'
    for owner in owners:owner.disconnect()
    assert h.status_document()['owner_count']==0
    assert h.status_document()['last_interruption']=='DISCONNECTED'
    assert SharedSwingMonitoringHub().status_document()['owners']==[]


@pytest.mark.parametrize('state',['absent','active','expired','invalid_clock'])
def test_provider_projection_never_synchronizes_or_acquires_leases(state):
    from datetime import timedelta
    from kronos.provider.runtime import SharedAuthenticatedProviderRuntime, SharedProviderRuntimeLifecycle
    from tests.unit.provider.test_connection_governance import NOW
    runtime=SharedAuthenticatedProviderRuntime(Mock(side_effect=AssertionError('factory')),provider_identity='KITE',clock=lambda:NOW)
    runtime._SharedAuthenticatedProviderRuntime__provider=SimpleNamespace(session_status=Mock(side_effect=AssertionError('session synchronization')))
    if state!='absent':
        runtime._SharedAuthenticatedProviderRuntime__capability=object()
        runtime._SharedAuthenticatedProviderRuntime__lifecycle=SharedProviderRuntimeLifecycle.ACTIVE
        runtime._SharedAuthenticatedProviderRuntime__valid_through=NOW+timedelta(seconds=-1 if state=='expired' else 1)
        runtime._SharedAuthenticatedProviderRuntime__leases={'retained':object()}
    if state=='invalid_clock':runtime._SharedAuthenticatedProviderRuntime__clock=lambda:NOW.replace(tzinfo=None)
    before=(runtime._SharedAuthenticatedProviderRuntime__lifecycle,runtime._SharedAuthenticatedProviderRuntime__capability,dict(runtime._SharedAuthenticatedProviderRuntime__leases))
    for _ in range(10):d=runtime.read_only_status()
    assert d['capability_state']=={'absent':'ABSENT','active':'RETAINED_UNEXPIRED','expired':'EXPIRED','invalid_clock':'UNAVAILABLE_CLOCK'}[state]
    assert (runtime._SharedAuthenticatedProviderRuntime__lifecycle,runtime._SharedAuthenticatedProviderRuntime__capability,runtime._SharedAuthenticatedProviderRuntime__leases)==before
    runtime._SharedAuthenticatedProviderRuntime__provider.session_status.assert_not_called()


def test_failed_startup_cannot_be_retried_into_automatic_exit(tmp_path):
    g=governance(tmp_path,maintenance=GENERATION)
    g.complete_startup('ACCEPTANCE_RESTORATION_NOT_ESTABLISHED');g.complete_startup()
    assert g.maintenance_status()['state']=='FAILED_ACTIVE'
    assert not list((tmp_path/'audit').rglob('*.json'))
