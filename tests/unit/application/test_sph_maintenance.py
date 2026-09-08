from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path

import pytest

from kronos.application.swing_opportunities import SwingOpportunitiesApplication, ProviderConnectionState
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.common.connection_governance import ConnectionGovernanceError
from kronos.common.maintenance import expected_transport_close
from kronos.provider.runtime import SharedAuthenticatedProviderRuntime, SharedProviderRuntimeLifecycle
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.contracts.monitoring import MonitoringConnectionState as State
from tests.unit.provider.test_connection_governance import governance, GENERATION
from tests.unit.provider.test_shared_provider_runtime import _Runtime, NOW
from tests.unit.application.test_swing_ux10 import ux10, Telegram
from tests.unit.application.test_shared_monitoring import Capability, Consumer, ONE, tick


def composed(tmp_path, *, maintenance=None, provider=None, runner=lambda job,name:job()):
    g=governance(tmp_path,maintenance=maintenance)
    provider=provider or _Runtime()
    factory_calls=[]
    def factory():factory_calls.append(1);return provider
    shared=SharedAuthenticatedProviderRuntime(factory,provider_identity='KITE',clock=lambda:NOW,
        connection_governance=g)
    app=SwingOpportunitiesApplication(lambda:shared.compatibility_facade(
        consumer_identity='SWING',operations=frozenset(ReadOnlyProviderOperation)),
        connection_governance=g,background_runner=runner)
    return g,shared,app,provider,factory_calls


def test_guarded_startup_and_status_never_authenticate_restore_or_acquire(tmp_path):
    g,shared,app,p,calls=composed(tmp_path,maintenance=GENERATION)
    restored=[];app.register_sponsor_operability_restorer(restored.append)
    for _ in range(3):
        assert app.snapshot().provider_state is ProviderConnectionState.DISCONNECTED
        assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.ABSENT
    assert not app.connect_provider()
    with pytest.raises(ConnectionGovernanceError):shared.begin_login()
    assert p.begin_count==0 and calls==[] and restored==[]
    assert shared.active_lease_count==0


def test_explicit_post_maintenance_connect_and_normal_restoration(tmp_path):
    g,shared,app,p,calls=composed(tmp_path,maintenance=GENERATION)
    restored=[];app.register_sponsor_operability_restorer(restored.append)
    assert g.exit_maintenance(g.action_reference('MAINTENANCE_EXIT'))
    assert calls==[] and p.begin_count==0
    assert app.connect_provider(action_reference=g.action_reference('HEADER'))
    assert p.begin_count==1 and len(restored)==1
    assert app.snapshot().provider_state is ProviderConnectionState.CONNECTED
    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.ACTIVE
    assert not app.connect_provider()
    states=[g.store.read(d.name)['admission']['state'] for d in g.store.root.iterdir() if d.name!='maintenance']
    assert sorted(states)==['ACCEPTED','ALREADY_CONNECTED']
    app.close()


def test_queued_authentication_invalidated_before_dispatch(tmp_path):
    queued=[]
    g,shared,app,p,calls=composed(tmp_path,runner=lambda job,name:queued.append(job))
    app.connect_provider();app.enter_controlled_maintenance(GENERATION);queued[0]()
    assert p.begin_count==0 and calls==[]
    records=[g.store.read(d.name) for d in g.store.root.iterdir()]
    assert records[0]['completion']['state']=='UNFINISHED'


def test_callback_inflight_cannot_publish_active_after_maintenance(tmp_path):
    started,release=Event(),Event()
    class Provider(_Runtime):
        def complete_callback(self,attempt):
            started.set();assert release.wait(5)
            return super().complete_callback(attempt)
    p=Provider();pool=ThreadPoolExecutor(1);jobs=[]
    g,shared,app,p,calls=composed(tmp_path,provider=p,runner=lambda job,name:jobs.append(pool.submit(job)))
    restored=[];app.register_sponsor_operability_restorer(restored.append)
    app.connect_provider();assert started.wait(5)
    app.enter_controlled_maintenance(GENERATION);release.set();jobs[0].result(5)
    assert shared.lifecycle_state is not SharedProviderRuntimeLifecycle.ACTIVE
    assert app.snapshot().provider_state is not ProviderConnectionState.CONNECTED
    assert restored==[] and p.end_count>=1
    pool.shutdown()


def test_failed_authentication_sanitized_and_correlated(tmp_path):
    class Provider(_Runtime):
        def begin_login(self):raise RuntimeError('secret-access-token-DO-NOT-LOG')
    g,shared,app,p,calls=composed(tmp_path,provider=Provider())
    assert app.connect_provider()
    assert app.snapshot().provider_state is ProviderConnectionState.ERROR
    records=[g.store.read(d.name) for d in g.store.root.iterdir()]
    assert records[0]['completion']['state']=='FAILURE'
    assert all(b'secret-access-token' not in f.read_bytes() for f in g.store.root.rglob('*.json'))


def test_expected_disconnect_suppresses_both_deliveries_but_retains_truth(tmp_path):
    g=governance(tmp_path);tg=Telegram();service=ux10(tmp_path/'notifications',tg)
    service.observe_connection_state('WATCH','VBL',State.CONNECTED)
    g.enter_maintenance(GENERATION)
    with expected_transport_close(g):
        assert service.observe_connection_state('WATCH','VBL',State.DISCONNECTED) is None
    assert service._connection_state['WATCH'][0] is State.DISCONNECTED
    assert service.snapshot().records==() and tg.messages==[]
    evidence=list((g.store.root/'maintenance').glob('*disconnect.json'))
    assert len(evidence)==1 and b'DISCONNECTED' in evidence[0].read_bytes()


@pytest.mark.parametrize('state',[State.DISCONNECTED,State.RECONNECTING,State.CONTEXT_INCOMPLETE])
def test_unexpected_incident_outside_close_still_alerts_during_maintenance(tmp_path,state):
    g=governance(tmp_path);tg=Telegram();service=ux10(tmp_path/'notifications',tg)
    g.enter_maintenance(GENERATION)
    result=service.observe_connection_state('WATCH','VBL',state)
    assert result is not None and len(tg.messages)==1
    assert result.browser_delivery_state.value=='SENT'
    assert service.snapshot().records[0].telegram_delivery_state.value=='SENT'


def test_failed_controlled_transport_close_does_not_suppress_failure(tmp_path):
    g=governance(tmp_path);tg=Telegram();service=ux10(tmp_path/'notifications',tg)
    g.enter_maintenance(GENERATION)
    with pytest.raises(RuntimeError):
        with expected_transport_close(g):
            service.observe_connection_state('WATCH','VBL',State.DISCONNECTED)
            raise RuntimeError('bounded test failure')
    assert len(service.snapshot().records)==1 and len(tg.messages)==1


def test_monitoring_consumers_interrupted_without_new_facts(tmp_path):
    g=governance(tmp_path);hub=SharedSwingMonitoringHub();hub.maintenance_governance=g
    capability=Capability();consumer=Consumer();registration=hub.open(capability,consumer)
    registration.subscribe((ONE,));registration.connect()
    g.enter_maintenance(GENERATION)
    hub.on_market_tick(tick(ONE));hub.close()
    assert consumer.ticks==[] and consumer.states==[State.DISCONNECTED]
    assert hub.active_session_count==0 and hub.subscription_count==0
    with pytest.raises(ConnectionGovernanceError):hub.open(capability,Consumer())


def test_no_wo06h_activation_or_window_creation(tmp_path):
    from tests.unit.intraday.test_live_shadow import service
    shadow,clock,manifest=service(tmp_path/'shadow',accept=False)
    composed(tmp_path/'shared',maintenance=GENERATION)
    assert not shadow.status()['enabled'] and shadow.status()['window'] is None
    assert not list((tmp_path/'shadow').rglob('*.json'))


@pytest.mark.parametrize('close_code,alerts', [(1000,0),(1006,1)])
@pytest.mark.parametrize('asynchronous', [False,True])
def test_async_socket_close_ack_preserves_exact_maintenance_cause(tmp_path, close_code, alerts, asynchronous):
    from threading import Thread
    from kronos.provider.adapters.kite.monitoring import KiteReadOnlyMonitoringSession
    from tests.unit.provider.test_kite_websocket_monitoring import _Socket, _NSE
    g=governance(tmp_path);tg=Telegram();service=ux10(tmp_path/'notifications',tg)
    class Observer(Consumer):
        def on_connection_state(self,state):
            super().on_connection_state(state)
            service.observe_connection_state('WATCH','VBL',state)
    observer=Observer()
    class Socket(_Socket):
        def close(self):
            if not asynchronous:
                self.on_close(self,close_code,'bounded fixture')
                return
            thread=Thread(target=lambda:self.on_close(self,close_code,'bounded fixture'))
            thread.start();thread.join(5)
            assert not thread.is_alive()
    socket=Socket()
    session=KiteReadOnlyMonitoringSession(api_key='fixture',access_token='fixture',
        token_resolver=lambda _:1,consumer=observer,socket_factory=lambda *args:socket)
    session.subscribe((_NSE,));session.connect();g.enter_maintenance(GENERATION)
    with expected_transport_close(g):session.disconnect()
    assert observer.states[-1] is State.DISCONNECTED
    assert session.last_disconnect is not None
    assert len(service.snapshot().records)==alerts and len(tg.messages)==alerts
