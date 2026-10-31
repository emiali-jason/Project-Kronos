"""Shared runtime authority qualification with fake Providers and isolated stores."""
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock
import json
import time
import pytest

@pytest.fixture(autouse=True)
def preparatory_pin_disposable_binding(monkeypatch):
    from tests.unit.tools.test_place_release_pair import assert_actual_preparatory_source
    assert_actual_preparatory_source()
    from kronos.common import release_admission as admission
    monkeypatch.setattr(admission,'PERSISTENT_ANCHOR_BINDING',None)


from kronos.browser.runtime_state import complete_startup as actual_complete_startup, decorate_html, status_document
from kronos.browser.server import KronosBrowserServer
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.application.housekeeping import BoundedHousekeeping, HousekeepingLimits
from kronos.application.swing_opportunities import ProviderConnectionState
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from tests.unit.provider.test_connection_governance import governance, GENERATION
from tests.unit.application.test_shared_monitoring import Capability, Consumer, ONE, TWO, tick
from tests.unit.browser.test_sph_controls import running, request
from tests.unit.intraday.test_live_shadow import service
from tests.unit.intraday.test_live_shadow_epochs import restart, inventory
from tests.unit.intraday.test_live_shadow_epoch_deterministic_digest import production_case, retain_equivalence, corrected_restart


def complete_startup(server, shadow):
    # Explicit healthy owner results for standalone shared-startup fixtures.
    return actual_complete_startup(server, shadow,
        swing_outcomes=tuple((key, "FAILED" if key == "V3_RECORDS" and server.visual_v3_live.restoration_error else "SUCCESS")
            for key in ("LEGACY_MTF", "LEGACY_NATIVE", "NATIVE_REVIEW", "V3_RECORDS", "V3_RESTORE", "TRADE_WINDOW")),
        wo11=SimpleNamespace(last_failure=None),
        wo17=dict(restoration_state="NOT_YET_RUN", failure_stage=None, failure_reason=None, current_positions=[]))


def server_for(g):
    return SimpleNamespace(connection_governance=g, provider_runtime=SimpleNamespace(read_only_status=lambda:dict(capability_state="ABSENT")), trade_window=SimpleNamespace(paper_observation_projections=lambda:()), visual_v3_live=SimpleNamespace(restoration_error=None),
        application=SimpleNamespace(authenticated_read_only_capability=lambda:None,
            snapshot=lambda:SimpleNamespace(provider_state=SimpleNamespace(value='DISCONNECTED'))),
        swing_monitoring_hub=SharedSwingMonitoringHub(),
        request_capacity_status=lambda: {
            "state": "AVAILABLE", "active": 0, "maximum": 32, "refusals": 0,
        })


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
            drain=d['maintenance_drain']
            assert drain['state']=='OPEN' and drain['generation'] is None
            assert drain['failure'] is None
            # The separately admitted server pulse may overlap this status GET.
            # No other domain owner may be admitted by the observational read.
            assert drain['owners'] in ({}, {'SERVER_PULSE': 1})
            assert d['maintenance']['active'] and d['rest_authentication']=='DISCONNECTED'
            assert d['rest_capability']=='NOT_EXPOSED' and d['monitoring']['transport_state']=='IDLE'  # legacy fixture lacks the pure Provider projection
            assert d['browser_requests']['maximum']==32
    assert p.begin_count==0 and calls==[]
    assert inventory(root)==before


@pytest.mark.parametrize('configured', [False, True])
def test_runtime_status_exposes_experimental_memory_only(running, monkeypatch, configured):
    from kronos.application.intraday_experimental_watch import GovernedExperimentalWatchCoordinator
    from kronos.intraday.wo08_experimental import METHOD

    server, _, provider, calls, root = running

    class ForbiddenStore:
        def __getattr__(self, name):
            raise AssertionError('runtime status accessed persisted store: ' + name)

    # Construct the ordinary coordinator first, then prohibit every store API.
    from tests.unit.application.test_intraday_experimental_watch import setup_watch, canonical_adapter
    watch, _, _, _, clock, _, _, _ = setup_watch(root / 'experimental')
    coordinator = canonical_adapter(watch, clock)
    assert isinstance(coordinator, GovernedExperimentalWatchCoordinator)
    monkeypatch.setattr(coordinator, 'store', ForbiddenStore())
    monkeypatch.setattr(coordinator.wo09, 'store', ForbiddenStore())
    coordinator.restore = Mock(side_effect=AssertionError('GET restored watches'))
    coordinator.current_binding = Mock(side_effect=AssertionError('GET replayed sources'))
    coordinator.capability_supplier = Mock(side_effect=AssertionError('GET acquired Provider capability')) if configured else None
    coordinator.hub = object() if configured else None
    coordinator.instrument_source = object() if configured else None
    coordinator.maintenance = server.maintenance_admission if configured else None
    coordinator.registrations = {'binding': SimpleNamespace(read_only_active=configured,
        advisory_failure='ADVISORY_CALLBACK_FAILED' if configured else None,
        disconnect=Mock())}
    coordinator._queue = {'instrument': object()} if configured else {}
    coordinator._worker_thread = object() if configured else None
    coordinator._queue_coalesced = 7 if configured else 0
    coordinator._queue_closed = configured
    coordinator._queue_failure = 'WO09_ADVISORY_WORK_FAILED' if configured else None
    server.intraday_experimental_watches = coordinator
    before = inventory(root)
    try:
        for _ in range(2):
            code, body = request(server, '/runtime/status')
            assert code == 200
            status = json.loads(body)['intraday_experimental_paper']
            assert status['method'] == dict(identity=METHOD[0], version=METHOD[1], checksum=METHOD[2])
            assert status['authority'] == 'EXPERIMENTAL_PAPER_ADVISORY_ONLY'
            assert status['configuration'] == dict(method_available=True, watch_path_available=True,
                persistence_configured=True, source_validation_configured=configured,
                monitoring_configured=configured, maintenance_admission_configured=configured)
            assert status['work'] == dict(pending=int(configured), running=configured,
                coalesced=7 if configured else 0, closed=configured,
                failure='WO09_ADVISORY_WORK_FAILED' if configured else None)
            assert status['attached_observers'] == int(configured)
            assert status['advisory_callback_failures'] == ([dict(binding_identity='binding',
                failure='ADVISORY_CALLBACK_FAILED')] if configured else [])
            assert status['last_failure'] == ('WO09_ADVISORY_WORK_FAILED' if configured else None)
            assert not status['automatic_provider_acquisition'] and not status['websocket_can_promote']
            assert 'persisted_bindings' not in status and 'pending_hints' not in status
        assert inventory(root) == before
        assert provider.begin_count == 0 and calls == []
        coordinator.restore.assert_not_called()
        coordinator.current_binding.assert_not_called()
        if configured:
            coordinator.capability_supplier.assert_not_called()
    finally:
        coordinator._queue.clear()
        coordinator._worker_thread = None
        del server.intraday_experimental_watches


def test_service_loop_admits_intraday_pulse_without_executing_it_inline():
    server=object.__new__(KronosBrowserServer)
    server.maintenance_admission=MaintenanceAdmissionCoordinator()
    server._next_lifecycle_pulse=0.0
    server._next_swing_journal_reconciliation=float('inf')
    lifecycle=SimpleNamespace(
        request_pulse=Mock(return_value=True),
        pulse=Mock(side_effect=AssertionError('service loop executed Intraday work')),
        last_failure=None,
    )
    server.intraday_lifecycle=lifecycle
    server.service_actions()
    lifecycle.request_pulse.assert_called_once_with()
    lifecycle.pulse.assert_not_called()


def test_repeated_service_iterations_do_not_add_extra_intraday_pulses():
    server=object.__new__(KronosBrowserServer)
    server.maintenance_admission=MaintenanceAdmissionCoordinator()
    server._next_lifecycle_pulse=0.0
    server._next_swing_journal_reconciliation=float('inf')
    server.intraday_lifecycle=SimpleNamespace(
        request_pulse=Mock(return_value=True),last_failure=None)
    for _ in range(5):
        server.service_actions()
    server.intraday_lifecycle.request_pulse.assert_called_once_with()
    assert server.maintenance_admission.snapshot()['owners']=={}


def test_service_loop_only_triggers_owned_housekeeping_boundary():
    server=object.__new__(KronosBrowserServer)
    server.maintenance_admission=MaintenanceAdmissionCoordinator()
    server._next_lifecycle_pulse=0.0
    server._next_swing_journal_reconciliation=float('inf')
    housekeeping=SimpleNamespace(
        trigger_periodic=Mock(return_value="DISABLED"),
        record_trigger_failure=Mock(),
    )
    server.housekeeping=housekeeping
    server.service_actions()
    housekeeping.trigger_periodic.assert_called_once_with()
    housekeeping.record_trigger_failure.assert_not_called()


def test_server_close_shuts_housekeeping_before_other_owned_lifecycles(monkeypatch):
    server=object.__new__(KronosBrowserServer)
    from threading import Lock
    server._domain_close_lock=Lock()
    server._domain_closed=False
    server._monitoring_quiesced=False
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    server.maintenance_admission=MaintenanceAdmissionCoordinator()
    events=[]
    server.housekeeping=SimpleNamespace(shutdown=lambda:events.append("housekeeping"))
    server.bulk_import=SimpleNamespace(close=lambda:events.append("bulk-import"))
    server.intraday_notifications=SimpleNamespace(close=lambda:events.append("notifications"))
    server.intraday_lifecycle=SimpleNamespace(shutdown=lambda:events.append("intraday"))
    server.intraday_wo17_monitoring=SimpleNamespace(shutdown=lambda:events.append("wo17"))
    server.application=SimpleNamespace(close=lambda:events.append("application"))
    server.refresh_reminders=SimpleNamespace(close=lambda:events.append("reminders"))
    server.ux10_notifications=SimpleNamespace(close=lambda:events.append("ux10"))
    server.progression_watches=SimpleNamespace(close_monitoring=lambda:events.append("progression"))
    server.native_review=SimpleNamespace(close=lambda:events.append("native"))
    server.trade_window=SimpleNamespace(close_monitoring=lambda:events.append("trade"))
    server.swing_monitoring_hub=SimpleNamespace(close=lambda:events.append("monitoring"))
    server.step32_workflow=SimpleNamespace(close=lambda:events.append("step32"))
    server.swing_research_control=SimpleNamespace(
        close=lambda:events.append("research"))
    server._research_owner_bindings=[
        (SimpleNamespace(clear_research_capture=lambda callback:
                         events.append(("unbind-first", callback))), "first"),
        (SimpleNamespace(clear_research_capture=lambda callback:
                         events.append(("unbind-second", callback))), "second"),
    ]
    server.restart_control=None
    from kronos.browser.server import _StartupCleanup
    server._startup_cleanup = _StartupCleanup()
    # Pure ordering doubles, not resource/custody proof. Actual workers and
    # descriptors are exercised by test_r1_actual_partial_startup_cleanup.
    rows = (("housekeeping", server.housekeeping, "shutdown"),
        ("bulk", server.bulk_import, "close"),
        ("notifications", server.intraday_notifications, "close"),
        ("lifecycle", server.intraday_lifecycle, "shutdown"),
        ("wo17", server.intraday_wo17_monitoring, "shutdown"),
        ("application", server.application, "close"),
        ("reminders", server.refresh_reminders, "close"),
        ("ux10", server.ux10_notifications, "close"),
        ("progression", server.progression_watches, "close_monitoring"),
        ("native", server.native_review, "close"),
        ("trade", server.trade_window, "close_monitoring"),
        ("monitoring", server.swing_monitoring_hub, "close"),
        ("step32", server.step32_workflow, "close"),
        ("research", server.swing_research_control, "close"))
    for name, owner, method in rows:
        callback = getattr(owner, method)
        owner.fixture_completed = False
        def complete(o=owner, operation=callback):
            operation()
            o.fixture_completed = True
        setattr(owner, method, complete)
        server._startup_cleanup.own(name, owner, method, lambda o: o.fixture_completed)
    server._startup_cleanup.own("research_bindings", server, "_clear_startup_research_bindings",
        lambda o: not o._research_owner_bindings)
    server.fixture_socket_closed = False
    def close_socket(_server):
        events.append("socket")
        _server.fixture_socket_closed = True
    server._startup_cleanup.own("listener", server, "_close_startup_listener",
        lambda o: o.fixture_socket_closed)
    monkeypatch.setattr("socketserver.TCPServer.server_close", close_socket)

    server.server_close()

    assert events[0] == "housekeeping"
    assert events[1] == "bulk-import"
    assert events[-1] == "socket"
    assert events[-4:] == ["research", ("unbind-second", "second"),
                           ("unbind-first", "first"), "socket"]


def test_status_surfaces_tracked_bulk_worker_without_waiting_for_application_work(running):
    server,_,provider,calls,root=running
    bulk={"state":"RUNNING","owned_workers":1,
          "latest_batch_identity":"SWING-BULK-ANSWER-"+"A"*64,
          "latest_batch_state":"DOWNSTREAM_RUNNING"}
    server.bulk_import=SimpleNamespace(work_status=lambda:dict(bulk),close=lambda:None)
    before=inventory(root)
    for route in ("/status","/runtime/status"):
        code,body=request(server,route)
        assert code==200
        assert json.loads(body)["swing_bulk_import"]==bulk
    assert inventory(root)==before and provider.begin_count==0 and calls==[]


def test_housekeeping_status_remains_responsive_during_blocked_cleanup(running):
    server,_,provider,calls,root=running
    entered,release=Event(),Event()

    class BlockedScope:
        def clean(self,_owner,_budget):
            entered.set()
            assert release.wait(5)

    worker=BoundedHousekeeping(
        (BlockedScope(),),
        limits=HousekeepingLimits(max_elapsed_seconds=5),
        production_activation=True,
        interval_seconds=1,
    )
    server.housekeeping=worker
    assert worker.trigger_periodic(now=10**9)=="SCHEDULED"
    assert entered.wait(2)
    before=inventory(root)
    started=time.monotonic()
    for route in ("/status","/runtime/status"):
        code,body=request(server,route)
        assert code==200
        status=json.loads(body)["housekeeping"]
        assert status["lifecycle_state"]=="RUNNING"
        assert status["owned_workers"]==1 and status["pass_active"] is True
    assert time.monotonic()-started<1
    assert inventory(root)==before and provider.begin_count==0 and calls==[]
    release.set()
    deadline=time.monotonic()+2
    while worker.status_document()["owned_workers"] and time.monotonic()<deadline:
        time.sleep(0.01)
    assert worker.status_document()["lifecycle_state"]=="IDLE"


def test_status_surfaces_bounded_intraday_owners_without_writes(running):
    server,_,provider,calls,root=running
    wo11_status={'state':'RUNNING','owned_workers':1,'queued_items':2}
    wo17_status={'state':'FAILED','owned_workers':0,'queued_items':0,
                 'failure':'WO17_MONITORING_STORE_FAILED'}
    server.intraday_lifecycle=SimpleNamespace(
        request_pulse=lambda:True,work_status=lambda:dict(wo11_status),
        shutdown=lambda:None,last_failure=None)
    server.intraday_wo17_monitoring=SimpleNamespace(
        work_status=lambda:dict(wo17_status),shutdown=lambda:None)
    before=inventory(root)
    for route in ('/status','/runtime/status'):
        code,body=request(server,route)
        assert code==200
        document=json.loads(body)
        assert document['intraday_wo11_work']==wo11_status
        assert document['intraday_wo17_work']==wo17_status
        if route == '/runtime/status':
            assert document['analysis_work'] == server.application.analysis_work_status()
            assert document['analysis_execution'] == server.application.analysis_execution_status()
    assert inventory(root)==before
    assert provider.begin_count==0 and calls==[]


def test_swing_gets_remain_responsive_during_actual_blocked_intraday_worker(
    running,tmp_path,monkeypatch
):
    from decimal import Decimal
    from tests.unit.intraday.test_wo11_lifecycle_application import (
        fixture as wo11_fixture,_wait_for_work,
    )
    from kronos.application.intraday_lifecycle_intake import instrument_record
    from kronos.provider.contracts.monitoring import ProviderMarketTick
    server,governance,provider,calls,root=running
    assert governance.exit_maintenance(
        governance.action_reference('MAINTENANCE_EXIT')
    )
    app,h,_,_,clock,cap,_=wo11_fixture(
        tmp_path/'wo11',monkeypatch,
        background_runner=lambda operation,name:Thread(
            target=operation,name=name,daemon=True
        ).start())
    app.bind_monitoring(server.swing_monitoring_hub,lambda:cap)
    current=app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='PF06-HTTP')
    _wait_for_work(app,'IDLE')
    server.intraday_lifecycle=app
    entered,release=Event(),Event()
    original=app._tick
    def blocked(track,tick):
        entered.set();assert release.wait(10);return original(track,tick)
    monkeypatch.setattr(app,'_tick',blocked)
    fact=ProviderMarketTick(instrument_record(current.data['intake']['future']),Decimal('100'),
        clock[0],clock[0],'KITE_CONNECT_WEBSOCKET','PF06-HTTP',1,True,True,True)
    server.swing_monitoring_hub.on_market_tick(fact)
    try:
        assert entered.wait(5)
        before=inventory(root)
        for route in ('/status','/runtime/status','/swing/opportunities','/intraday'):
            assert request(server,route)[0]==200
        assert inventory(root)==before
        assert app.work_status()['owned_workers']==1
        assert provider.begin_count==0 and calls==[]
    finally:
        release.set()
    _wait_for_work(app,'IDLE')


def test_rest_connected_does_not_imply_websocket_live(tmp_path):
    s=server_for(governance(tmp_path));cap=Capability()
    s.application.authenticated_read_only_capability=Mock(side_effect=AssertionError('getter must not run'))
    s.provider_runtime.read_only_status=lambda:dict(capability_state='RETAINED_UNEXPIRED')
    s.application.snapshot=lambda:SimpleNamespace(provider_state=SimpleNamespace(value='CONNECTED'))
    d=status_document(s)
    assert d['rest_capability']=='RETAINED_UNEXPIRED' and d['monitoring']['transport_state']=='IDLE'
    assert d['maintenance']['state']=='INACTIVE'
    assert d['restoration_readiness']['state']=='NOT_EXPOSED'
    assert not d['restoration_readiness']['ready']


def test_runtime_status_exposes_failed_completion_without_writes_or_restoration(
    tmp_path, monkeypatch
):
    from kronos.browser.server import create_browser_server
    from tests.unit.tools.test_provider_foundation_v2_authentication import (
        _timed_production_connection,
    )

    case = _timed_production_connection(tmp_path, monkeypatch)
    completion_attempts = []
    original_result = case.governance.store.result

    def fail_completion(request_value, phase, state, at):
        if phase == 'completion':
            completion_attempts.append(state)
            raise OSError('INJECTED-COMPLETION-WRITE-FAILURE')
        return original_result(request_value, phase, state, at)

    monkeypatch.setattr(case.governance.store, 'result', fail_completion)
    server = create_browser_server(case.app, port=0)
    server.provider_runtime = case.shared
    serving = Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        assert case.app.connect_provider()
        case.jobs.pop(0)[1]()
        before = inventory(case.governance.store.root)
        code, body = request(server, '/runtime/status')
        assert code == 200
        document = json.loads(body)
        assert document['rest_authentication'] == 'ERROR'
        assert document['connection_attempt']['durable_completion'] == {
            'state': 'FAILED', 'disposition': 'SUCCESS', 'generation': 1,
        }
        assert document['connection_attempt']['cleanup_state'] == 'PENDING'
        assert document['restoration_readiness']['state'] == 'STALE'
        assert not document['restoration_readiness']['ready']
        assert inventory(case.governance.store.root) == before
        assert completion_attempts == ['SUCCESS']
    finally:
        server.shutdown(); server.server_close(); serving.join(2); case.app.close()


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


def test_status_routes_respond_while_sponsor_restoration_is_blocked(running):
    server, governance, provider, calls, root = running
    assert governance.exit_maintenance(
        governance.action_reference('MAINTENANCE_EXIT')
    )
    entered, release = Event(), Event()

    def blocked_restorer(capability):
        assert capability is not None
        entered.set()
        assert release.wait(5)

    server.application.register_sponsor_operability_restorer(blocked_restorer)
    result = []
    thread = Thread(target=lambda: result.append(server.application.connect_provider()))
    thread.start()
    try:
        assert entered.wait(5)
        assert server.application.snapshot().provider_state is ProviderConnectionState.CONNECTED
        request_identity = next(
            path.name
            for path in governance.store.root.iterdir()
            if len(path.name) == 32
            and all(character in "0123456789abcdef" for character in path.name)
        )
        assert governance.store.read(request_identity)['completion']['state'] == 'SUCCESS'
        before = inventory(root)
        assert request(server, '/status')[0] == 200
        assert request(server, '/runtime/status')[0] == 200
        assert inventory(root) == before
        assert server.application.sponsor_operability_restoration_status()['state'] == 'RUNNING'
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert result == [True]
    assert server.application.sponsor_operability_restoration_status()['state'] == 'SUCCEEDED'


def test_blocked_publication_read_does_not_hold_status_lock_and_stale_result_fails_closed(running):
    server, governance, provider, calls, root = running
    entered, release = Event(), Event()
    status_calls = []

    def publication_status():
        status_calls.append(1)
        if len(status_calls) == 1:
            entered.set()
            assert release.wait(5)
        return {'current_manifest': None, 'latest_attempt': None}

    publication = SimpleNamespace(status=publication_status)
    application_lock = server.application._SwingOpportunitiesApplication__lock
    with application_lock:
        server.application._SwingOpportunitiesApplication__publication = publication
    result = []
    thread = Thread(
        target=lambda: result.append(
            server.application.opportunities_bundle_projection()
        )
    )
    thread.start()
    try:
        assert entered.wait(5)
        before = inventory(root)
        assert server.application.snapshot() is not None
        assert request(server, '/status')[0] == 200
        assert request(server, '/runtime/status')[0] == 200
        assert inventory(root) == before
        with application_lock:
            server.application._SwingOpportunitiesApplication__analysis_request_result = 'AUTHORITY_CHANGED'
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert len(status_calls) >= 2
    _, native, continuity, publication_result = result[0]
    assert native is None and continuity is None
    assert publication_result['request_result'] == 'PUBLICATION_UNAVAILABLE'
    assert publication_result['reconciliation_unavailable'] is True


def test_status_and_intraday_respond_during_compact_tick_publication(running, tmp_path, monkeypatch):
    from datetime import timedelta
    from kronos.swing.v1 import paper_observation_track as domain
    from tests.unit.application.test_paper_observation_tracking import _compact_started, _tick, NOW, _inventory
    server, governance, provider, calls, root = running
    workflow, store, started, instrument = _compact_started(tmp_path / 'compact')
    server.trade_window._paper_observation_tracking = workflow
    identity, entry = started.track.track_identity, started.track.observation_entry_reference
    entered, release = Event(), Event()
    original = domain._atomic_encoded
    writes, failures = [], []
    def delayed(path, encoded):
        if path.name == 'current-state.json':
            writes.append(1)
            if len(writes) == 500:
                entered.set()
                assert release.wait(10)
        return original(path, encoded)
    monkeypatch.setattr(domain, '_atomic_encoded', delayed)
    def work():
        try:
            for sequence in range(1000):
                workflow.observe_tick(identity, _tick(instrument, entry - 1, sequence,
                    NOW + timedelta(microseconds=sequence)))
        except Exception as error:
            failures.append(error)
    worker = Thread(target=work)
    worker.start()
    try:
        assert entered.wait(10)
        before = _inventory(store.root)
        for route in ('/status', '/runtime/status', '/intraday'):
            assert request(server, route)[0] == 200
        assert _inventory(store.root) == before
        assert workflow.compact_status()['ordinary_ticks_accepted'] == 499
        assert worker.is_alive()
    finally:
        release.set()
        worker.join(15)
    assert not worker.is_alive() and not failures
    assert len(writes) == 1000
    assert len(_inventory(store.root)) == 4
    assert provider.begin_count == 0 and calls == []


def test_status_and_intraday_are_observational_during_inflight_detach(running,tmp_path,monkeypatch):
    from tests.unit.application.test_paper_observation_tracking import _registered_compact,_inventory,PaperObservationMonitoringApplicabilityState
    server,governance,provider,calls,root=running
    workflow,store,started,instrument,hub,capability,consumer=_registered_compact(tmp_path/'detach')
    server.trade_window._paper_observation_tracking=workflow
    server.swing_monitoring_hub=hub
    entered,release=Event(),Event()
    original=capability.sessions[0].unsubscribe
    errors=[]
    def blocked(values):
        entered.set();assert release.wait(10);return original(values)
    monkeypatch.setattr(capability.sessions[0],'unsubscribe',blocked)
    def detach():
        try:workflow.change_monitoring_applicability(started.track.track_identity,
            PaperObservationMonitoringApplicabilityState.SUSPENDED,'SPONSOR_STOPPED_MONITORING')
        except Exception as error:errors.append(error)
    worker=Thread(target=detach);worker.start()
    try:
        assert entered.wait(5)
        before=_inventory(store.root)
        for route in ('/status','/runtime/status','/intraday'):
            assert request(server,route)[0]==200
        assert _inventory(store.root)==before
        assert workflow.detachment_status()['active_owners']==0
        assert worker.is_alive()
    finally:release.set();worker.join(5)
    assert not worker.is_alive() and not errors
    assert capability.sessions[0].disconnections==1
    assert provider.begin_count==0 and calls==[]


@pytest.fixture
def intraday_books_owner(running, tmp_path):
    """Canonical WO14/15/16 owners with real, empty isolated source stores."""
    from datetime import datetime, timezone
    from kronos.application.intraday_books import IntradayBooks
    from kronos.application.intraday_journal import IntradayJournalApplication
    from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
    from kronos.application.intraday_futures import IntradayFuturesApplication
    from kronos.intraday.wo09_persistence import Wo09Store
    from kronos.intraday.wo10_futures_store import FuturesStore
    from kronos.intraday.wo11_lifecycle_store import LifecycleStore
    from kronos.intraday.wo12_research_store import ResearchStore
    from kronos.intraday.wo14_journal_store import JournalStore

    server = running[0]
    root = tmp_path / "intraday-owned"
    futures = FuturesStore(root / "futures")
    futures_application = IntradayFuturesApplication(
        futures, Wo09Store(root / "wo09"),
        operational_guard=lambda: not server.connection_governance.maintenance_active)
    research = ResearchStore(root / "research")
    def unexpected(*_args, **_kwargs):
        pytest.fail("read-only empty Books fixture requested operational evidence")
    lifecycle = IntradayLifecycleApplication(
        futures=futures_application, store=LifecycleStore(root / "lifecycle"),
        clock=lambda: datetime(2026, 8, 28, tzinfo=timezone.utc),
        session_source=unexpected, timing_source=unexpected,
        operational_guard=lambda: not server.connection_governance.maintenance_active)
    lifecycle.bind_maintenance_admission(server.maintenance_admission)
    lifecycle.bind_monitoring(server.swing_monitoring_hub, server.application.authenticated_read_only_capability)
    journal = IntradayJournalApplication(
        research=research, futures=futures, lifecycle=lifecycle,
        store=JournalStore(root / "journal"))
    journal.bind()
    books = IntradayBooks(research=journal.research, futures=journal.futures, lifecycle=lifecycle)
    books.bind()
    server.intraday_lifecycle = lifecycle
    server.intraday_journal = journal
    server.intraday_books = books
    try:
        yield books
    finally:
        # Dispose only this fixture's process-local projections and bindings.
        server._close_domain_owners()
        assert lifecycle.work_status()["owned_workers"] == 0
        assert lifecycle.work_status()["queued_items"] == 0
        for owner, name, callback in (
            (futures, "book_listener", books.consume_source),
            (lifecycle.store, "book_listener", books.consume_source),
            (futures, "journal_listener", journal.consume_source),
            (lifecycle.store, "journal_listener", journal.consume_source)):
            assert getattr(owner, name) == callback
            delattr(owner, name)
        del server.intraday_books
        assert not hasattr(server, "intraday_books")


def test_slice8_compact_history_real_http_consumers_are_read_only(running, tmp_path, monkeypatch, intraday_books_owner):
    from datetime import timedelta
    from tests.unit.swing.v1.test_observation_research_ledger_v2 import _selected_history_service, NOW
    from kronos.application.paper_observation_tracking import PaperObservationTrackingWorkflow
    server, governance, provider, calls, root = running
    service, paper, track = _selected_history_service(tmp_path / 'selected')
    server.trade_window._observation_research_v2 = service
    # Reports independently reads the exact V1 owner as well as prospective V2.
    server.trade_window._observation_research = service.v1
    from tests.unit.browser.test_browser_reports import _empty_mcx_reports_owner
    server.mcx_v1_control = _empty_mcx_reports_owner(tmp_path/'empty-mcx',server.native_review)
    server.trade_window._paper_observation_tracking = PaperObservationTrackingWorkflow(paper)
    assert server.intraday_books is intraday_books_owner
    monkeypatch.setattr(server.application, 'current_swing_trading_date', lambda: NOW.date())
    monkeypatch.setattr(server.application, 'swing_trading_date_for', lambda timestamp: timestamp.date())
    for name in ('facts', '_load_fact', 'prepare_historical_consolidation', 'publish_historical_consolidation'):
        monkeypatch.setattr(paper, name, lambda *_a, **_k: pytest.fail('GET invoked raw history or maintenance'))
    original_read = Path.read_bytes
    def no_raw_read(path):
        assert path.parent.name != 'facts', 'compact GET reconstructed raw facts'
        return original_read(path)
    monkeypatch.setattr(Path, 'read_bytes', no_raw_read)
    before = inventory(root), inventory(tmp_path / 'selected')
    paths = (
        '/journal?product=SWING&record=' + track.sponsor_decision_identity,
        '/reports?product=SWING&record=' + track.track_identity,
        '/reports/export.json?product=SWING',
        '/reports/export.csv?product=SWING',
    )
    for path in paths:
        code, body = request(server, path)
        assert code == 200
        assert 'COMPACT_HISTORICAL' in body and 'HISTORICAL_DETAIL_UNAVAILABLE' in body
        assert (NOW + timedelta(seconds=1)).isoformat() in body
    for path in ('/status', '/runtime/status', '/journal?product=INTRADAY',
                 '/reports?product=INTRADAY', '/reports/export.json?product=INTRADAY'):
        code, body = request(server, path)
        assert code == 200
        if 'INTRADAY' in path:
            assert 'COMPACT_HISTORICAL' not in body and 'paper_history_representation' not in body
    assert (inventory(root), inventory(tmp_path / 'selected')) == before
    assert provider.begin_count == 0 and calls == []


# Reuse the owning production-factory fixture: this is a native browser route
# test with actual factory/runtime/application and isolated external boundaries.
from tests.unit.tools.test_provider_foundation_v2_authentication import (
    _timed_production_connection,
)

@pytest.mark.parametrize("product_route", ["/swing/opportunities", "/intraday"])
def test_both_product_controls_share_production_deadline_and_inert_status(
    tmp_path, monkeypatch, product_route
):
    import json
    from threading import Event, Thread
    from kronos.browser.server import create_browser_server
    from tests.unit.browser.test_sph_controls import request

    entered, release = Event(), Event()

    def block_configuration():
        entered.set()
        assert release.wait(5), "test configuration boundary was not released"

    case = _timed_production_connection(
        tmp_path, monkeypatch, configuration_hook=block_configuration
    )
    server = create_browser_server(case.app, port=0)
    server.provider_runtime = case.shared
    serving = Thread(target=server.serve_forever, daemon=True)
    serving.start()
    worker = None
    errors = []
    try:
        code, page = request(server, product_route)
        assert code == 200
        assert 'action="/provider/connect"' in page
        reference = case.governance.action_reference("HEADER")
        assert reference in page
        assert case.events == []
        code, _ = request(
            server, "/provider/connect", method="POST", fields={"action_reference": reference}
        )
        assert code == 303
        assert case.app.snapshot().provider_state.value == "CONNECTING"
        assert len(case.jobs) == 1
        name, authenticate = case.jobs.pop(0)
        assert name == "kronos-browser-auth"

        def work():
            try:
                authenticate()
            except BaseException as error:
                errors.append(error)

        worker = Thread(target=work)
        worker.start()
        assert entered.wait(2)
        identity = case.app.connection_attempt_status()["request_identity"]
        case.monotonic_now[0] = 10.0
        case.timers[-1].fire()
        before = {
            path.relative_to(case.governance.store.root): path.read_bytes()
            for path in case.governance.store.root.rglob("*.json")
        }
        for route in ("/runtime/status", "/status", "/runtime/status"):
            code, body = request(server, route)
            assert code == 200
            data = json.loads(body)
            if route == "/runtime/status":
                assert data["rest_authentication"] == "ERROR"
                assert data["connection_attempt"]["state"] == "TIMED_OUT"
                assert data["connection_attempt"]["cleanup_state"] == "PENDING"
        assert {
            path.relative_to(case.governance.store.root): path.read_bytes()
            for path in case.governance.store.root.rglob("*.json")
        } == before
        assert worker.is_alive()
        assert case.governance.store.read(identity)["completion"]["state"] == "FAILURE"
        assert case.events == ["configuration"]
        release.set()
        worker.join(2)
        assert not worker.is_alive() and not errors
        assert case.app.authenticated_read_only_capability() is None
        assert case.jobs == []
    finally:
        release.set()
        if worker is not None:
            worker.join(2)
        server.shutdown()
        server.server_close()
        serving.join(2)
        case.app.close()


@pytest.mark.parametrize("stage", ["server_bind", "server_activate"])
def test_socket_startup_failure_closes_installed_research_and_bindings(
    monkeypatch, stage,
):
    from tests.unit.application.test_swing_opportunities import _Provider
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.browser.server import create_browser_server
    observed = []

    def fail(server):
        observed.append(server)
        assert server.swing_research_control is not None
        assert server._research_owner_bindings
        raise OSError("isolated socket startup failure")

    monkeypatch.setattr("socketserver.TCPServer." + stage, fail)
    with pytest.raises(OSError, match="isolated socket startup failure"):
        create_browser_server(SwingOpportunitiesApplication(_Provider), port=0)
    assert len(observed) == 1
    failed = observed[0]
    assert failed.socket.fileno() == -1
    assert failed.swing_research_control._worker_closed
    assert failed.application._SwingOpportunitiesApplication__research_capture is None
    assert all(owner._research_capture is None
               for owner, _callback in failed._research_owner_bindings
               if owner is not failed.application)
    assert failed.maintenance_admission.snapshot()["owners"] == {}


@pytest.mark.parametrize("fault", ["wo11", "wo17-corrupt", "wo17-failure", "wo17-missing",
    "wo11-missing", "swing-missing", "swing-failed", "swing-incomplete", "wo17-empty-inconsistent"])
def test_r4_required_owner_results_block_before_success_receipt(tmp_path, fault):
    server = server_for(governance(tmp_path, maintenance=GENERATION))
    shadow = SimpleNamespace(status=lambda: dict(failure=None, window=None, runtime_accepted=False))
    swing = tuple((key, "SUCCESS") for key in ("LEGACY_MTF", "LEGACY_NATIVE", "NATIVE_REVIEW",
        "V3_RECORDS", "V3_RESTORE", "TRADE_WINDOW"))
    wo11 = SimpleNamespace(last_failure=None, work_status=lambda: dict(state="IDLE", continuity="COMPLETE", failure=None))
    wo17 = dict(restoration_state="NOT_YET_RUN", failure_stage=None, failure_reason=None, current_positions=[])
    if fault == "wo11": wo11.last_failure = "WO11_RESTORATION_FAILED"
    if fault == "wo17-corrupt": wo17["restoration_state"] = "CORRUPT"
    if fault == "wo17-failure": wo17["failure_reason"] = "WO17_RESTORATION_FAILED"
    if fault == "wo17-missing": wo17 = None
    if fault == "wo11-missing": wo11 = None
    if fault == "swing-missing": swing = None
    if fault == "swing-incomplete": swing = swing[:-1]
    if fault == "swing-failed": swing = tuple((key, "FAILED" if key == "V3_RESTORE" else state) for key,state in swing)
    if fault == "wo17-empty-inconsistent": wo17["current_positions"] = [{}]
    actual_complete_startup(server, shadow, swing_outcomes=swing, wo11=wo11, wo17=wo17)
    assert server.connection_governance.startup_state == "BLOCKED"
    assert server.connection_governance.maintenance_active
    assert not list((tmp_path/'audit').rglob('*-startup.json'))


@pytest.mark.parametrize("owner,expected", [
    ("NATIVE_REVIEW", "READY"), ("V3_RESTORE", "BLOCKED"),
    ("LEGACY_NATIVE", "BLOCKED"), ("TRADE_WINDOW", "BLOCKED"),
])
def test_native_legacy_ambiguity_is_bounded_to_its_owner(tmp_path, owner, expected):
    server = server_for(governance(tmp_path, maintenance=GENERATION))
    outcomes = tuple((key, "APPLICABILITY_NOT_ESTABLISHED" if key == owner else "SUCCESS")
        for key in ("LEGACY_MTF", "LEGACY_NATIVE", "NATIVE_REVIEW",
                    "V3_RECORDS", "V3_RESTORE", "TRADE_WINDOW"))
    actual_complete_startup(server,
        SimpleNamespace(status=lambda: dict(failure=None, window=None, runtime_accepted=False)),
        swing_outcomes=outcomes, wo11=SimpleNamespace(last_failure=None),
        wo17=dict(restoration_state="NOT_YET_RUN", failure_stage=None,
                  failure_reason=None, current_positions=[]))
    assert server.connection_governance.startup_state == expected
    assert server.connection_governance.maintenance_active == (expected == "BLOCKED")


@pytest.mark.parametrize("route", [
    "/reports?product=INTRADAY", "/reports/export.json?product=INTRADAY",
    "/portfolio?product=INTRADAY"])
def test_runtime_missing_intraday_books_is_unavailable_without_swing_substitution(running, route):
    server, _, provider, calls, root = running
    assert getattr(server, "intraday_books", None) is None
    before = inventory(root)
    code, body = request(server, route)
    assert code == 503 and "unavailable" in body.lower()
    assert inventory(root) == before
    assert provider.begin_count == 0 and calls == []


def test_runtime_complete_books_bindings_are_inert_product_local_and_clean(running, intraday_books_owner):
    server, _, provider, calls, root = running
    books = intraday_books_owner
    assert books.research is server.intraday_journal.research
    assert books.futures is server.intraday_journal.futures
    assert books.lifecycle is server.intraday_lifecycle.store
    assert books.lifecycle is not server.trade_window
    assert books.futures.book_listener == books.consume_source
    assert books.futures.journal_listener == server.intraday_journal.consume_source
    before = inventory(root)
    for route in ("/journal?product=INTRADAY", "/reports?product=INTRADAY",
                  "/reports/export.json?product=INTRADAY", "/portfolio?product=INTRADAY"):
        assert request(server, route)[0] == 200
    assert inventory(root) == before
    assert books.snapshot() == ()
    work = server.intraday_lifecycle.work_status()
    assert work["owned_workers"] == work["queued_items"] == 0 and work["failure"] is None
    assert server.swing_monitoring_hub.active_session_count == server.swing_monitoring_hub.subscription_count == 0
    assert server.request_capacity_status()["active"] == 0
    assert "HTTP_REQUEST" not in server.maintenance_admission.snapshot()["owners"]
    assert provider.begin_count == 0 and calls == []


@pytest.mark.parametrize('fault', [None, 'failed', 'missing', 'duplicate', 'unknown', 'malformed', 'mutable'])
def test_iwo07r3_frozen_owner_projection_is_inert(tmp_path, fault):
    from kronos.browser.runtime_state import _swing_restoration_failure
    s = server_for(governance(tmp_path, maintenance=GENERATION))
    outcomes = tuple((owner, 'SUCCESS') for owner in
        ('LEGACY_MTF', 'LEGACY_NATIVE', 'NATIVE_REVIEW', 'V3_RECORDS', 'V3_RESTORE', 'TRADE_WINDOW'))
    if fault == 'failed': outcomes = tuple((k, 'FAILED' if k == 'V3_RECORDS' else v) for k, v in outcomes)
    elif fault == 'missing': outcomes = outcomes[:-1]
    elif fault == 'duplicate': outcomes = outcomes[:-1] + (outcomes[0],)
    elif fault == 'unknown': outcomes = outcomes[:-1] + (('OTHER', 'SUCCESS'),)
    elif fault == 'malformed': outcomes = outcomes[:-1] + (([], 'SUCCESS'),)
    elif fault == 'mutable': outcomes = list(outcomes)
    s.startup_restoration_outcomes = lambda: outcomes
    before = inventory(tmp_path)
    result = status_document(s)['startup_restoration_outcomes']
    assert inventory(tmp_path) == before
    assert s.connection_governance.startup_state != 'READY'
    if fault in (None, 'failed'):
        assert result == [list(row) for row in outcomes]
        assert _swing_restoration_failure(outcomes) is (fault == 'failed')
        result[0][1] = 'OTHER'
        assert status_document(s)['startup_restoration_outcomes'][0][1] == 'SUCCESS'
    else:
        assert result is None


def test_slice22_operational_custody_precedes_capture_and_startup_effects():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[3]/'tools/kronos_browser.py').read_text()
    assert source.index('_ADMISSION = _admission_bootstrap.adopt_from_launcher()')<source.index('with _Capture(')
    assert source.index('_pinned_admission[1] != _ADMISSION_PAYLOAD')<source.index('from kronos.application.')
    main=source.split('def main(',1)[1]
    assert main.index('_check_admission()')<main.index('qualify_startup(')<main.index('consume_startup_context(')
    activation=source.split('def _activate_canonical_notifications(',1)[1].split('def _parser(',1)[0]
    assert activation.index('custody_type.release_ready(custody, server)')<activation.index('ux10.activate_delivery()')<activation.index('notifications._activate_replay()')<activation.index('reminders._activate_execution()')
    assert main.index('_activate_canonical_notifications(server)')<main.index('webbrowser.open_new_tab(')<main.index('serve_forever(')
    cleanup=main.split('    finally:',1)[1]
    assert cleanup.index('begin()')<cleanup.index('cleanup.cleanup(deadline=deadline)')
    assert cleanup.index('cleanup.cleanup(deadline=deadline)')<cleanup.index('server._maintenance_final_owner_proof()')<cleanup.index('completed_failure_cleanup()')
    assert 'cleanup.construct("provider"' in main and '"end_kronos_session"' in main
    from kronos.browser.server import _StartupCleanup
    assert _StartupCleanup._order.index('provider')<_StartupCleanup._order.index('control')
    assert 'complete and proof and not _validation_cleanup_unresolved()' in cleanup


def test_r32_reconciles_bootstrap_and_pinned_admission_classes(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from tools import kronos_browser as entry
    from tests.unit.tools.test_place_release_pair import assert_actual_preparatory_source
    binding = assert_actual_preparatory_source()
    source = Path(__file__).resolve().parents[3] / 'src/kronos/common/release_admission.py'
    payload = source.read_bytes()
    bootstrap_custody = type('BootstrapCustody', (), {})
    bootstrap_budget = type('BootstrapBudget', (), {})
    pinned = SimpleNamespace(__file__=str(source), PERSISTENT_ANCHOR_BINDING=binding,
        AdmissionCustody=type('PinnedCustody', (), {}),
        ValidationBudget=type('PinnedBudget', (), {}))
    bootstrap = SimpleNamespace(PERSISTENT_ANCHOR_BINDING=binding, AdmissionCustody=bootstrap_custody,
        ValidationBudget=bootstrap_budget)
    monkeypatch.setattr(entry, '_ADMISSION_PAYLOAD', payload)
    monkeypatch.setattr(entry, '_admission_bootstrap', bootstrap)
    monkeypatch.setattr(entry, '_pinned_release_admission', pinned)
    entry._reconcile_admission_module_identity()
    assert pinned.AdmissionCustody is bootstrap_custody
    assert pinned.ValidationBudget is bootstrap_budget


@pytest.mark.parametrize('capture_digest', (None, 'not-a-full-capture-digest'))
def test_c02_missing_or_invalid_capture_is_already_denied_by_startup_evidence(capture_digest):
    from dataclasses import replace
    from tools import kronos_browser as entry
    # This is the actual immutable evidence predicate, not a successful source
    # qualification stub. Missing capture cannot reach canonical dispatch.
    assert entry._STARTUP_EVIDENCE.source_snapshot_digest
    with pytest.raises(ValueError, match='INTRADAY_STARTUP_EVIDENCE'):
        replace(entry._STARTUP_EVIDENCE, source_snapshot_digest=capture_digest)


def test_c02_actual_startup_capture_mapping_in_fresh_process(tmp_path):
    """Actual StartupCapture bytes and package-name mapping, isolated from imports."""
    import subprocess
    import sys
    repository = tmp_path / 'capture-repository'
    (repository / 'src/kronos').mkdir(parents=True)
    (repository / 'tools').mkdir()
    (repository / 'src/kronos/__init__.py').write_bytes(b'')
    (repository / 'src/kronos/probe.py').write_bytes(b'VALUE = 7\n')
    (repository / 'tools/__init__.py').write_bytes(b'')
    subprocess.run(['/usr/bin/git', 'init', '-q'], cwd=repository, check=True)
    subprocess.run(['/usr/bin/git', 'add', '--all'], cwd=repository, check=True)
    subprocess.run(['/usr/bin/git', '-c', 'user.name=KRONOS Fixture',
        '-c', 'user.email=fixture@example.invalid', 'commit', '-q', '-m', 'capture'],
        cwd=repository, check=True)
    code = r'''import hashlib,json,sys
from pathlib import Path
from kronos.intraday.runtime_identity import StartupCapture,canonical
root=Path(sys.argv[1])
with StartupCapture(root) as capture:
 import kronos.probe
 assert kronos.probe.VALUE==7
 evidence=capture.finish()
 rows=sorted((name,Path(item[0]).relative_to(root).as_posix(),
              hashlib.sha256(item[1]).hexdigest())
             for name,item in capture._sources.items())
 pairs=[[name,digest] for name,path,digest in rows]
 assert evidence.source_snapshot_digest==hashlib.sha256(canonical(pairs)).hexdigest()
 assert evidence.load_verification=='PINNED_STARTUP_IMPORTS'
 assert evidence.loaded_modules==(('kronos.probe',rows[1][2]),)
 print(json.dumps({'rows':rows,'loaded_modules':evidence.loaded_modules,
                   'pinned_capture_sha256':evidence.source_snapshot_digest},sort_keys=True))
'''
    result = subprocess.run([sys.executable, '-B', '-c', code, str(repository)],
        cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True,
        timeout=30)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert [row[0] for row in observed['rows']] == ['kronos', 'kronos.probe', 'tools']
    assert observed['loaded_modules'][0][0] == 'kronos.probe'
    assert len(observed['pinned_capture_sha256']) == 64


@pytest.mark.parametrize('selection', ('valid', 'missing-selected-capture', 'mismatched-selected-capture'))
def test_c03_f02_original_capture_lifetime_in_fresh_entry(tmp_path, record_property, selection):
    _restoration_fresh_entry_case(tmp_path, record_property, selection)


@pytest.mark.parametrize('fault', ('healthy', 'completion-expiry'))
def test_r32_final_integration_in_fresh_entry(tmp_path, record_property, fault):
    """Original capture through real READY/release or expiry and actual cleanup."""
    _restoration_fresh_entry_case(tmp_path, record_property, 'integrated-' + fault)


def test_r33_actual_precompletion_cleanup_facts(tmp_path,record_property):
    _restoration_fresh_entry_case(tmp_path,record_property,'integrated-pre-completion-failure')


@pytest.mark.parametrize('terminal', ('and-restoration','ready-failure','ambiguous-completion'))
def test_r33_native_original_failure_and_restoration_child(tmp_path,record_property,terminal):
    _restoration_fresh_entry_case(tmp_path,record_property,'native-original-'+terminal)



@pytest.mark.parametrize('boundary',('integrated','native'))
def test_s3_01_real_current_theta_authority_validates_settled_continuity(tmp_path,record_property,boundary):
    selection=('integrated-pre-completion-current-authority-denial' if boundary=='integrated'
               else 'native-original-current-authority-denial')
    _restoration_fresh_entry_case(tmp_path,record_property,selection)


def _restoration_fresh_entry_case(tmp_path, record_property, selection):
    """Real __main__ adoption/capture/imports/dispatch; no capture reinjection."""
    import os
    import shutil
    import stat
    import subprocess
    import sys
    from hashlib import sha256
    from tests.unit.common import test_failed_successor_restore as fixture
    from tests.unit.common import test_legacy_bootstrap as setup
    from tests.unit.common.test_release_admission import available
    from kronos.common import legacy_bootstrap as bootstrap
    from kronos.common.release_admission import ValidationBudget, monotonic_ns
    source_root = Path(__file__).resolve().parents[3]
    native = selection.startswith('native-original-')
    integrated = selection.startswith('integrated-')
    evidence = (source_root.parent / 'qualification' /
                ('r33-native-child-evidence' if native else 'r32-final-integration-evidence' if integrated else 'c03-f02-lifetime-evidence') /
                tmp_path.parents[1].name / tmp_path.name)
    evidence.mkdir(parents=True)
    case = fixture._make_case(tmp_path / 'authority',
        budget=ValidationBudget(monotonic_ns() + 120_000_000_000))
    if integrated or native:
        # Certify the actual EMPTY notification reference estate used by the
        # established composition fixture; keep historical parent/V2 evidence.
        settled = json.loads(case.settled_path.read_bytes())
        settled['notification_checkpoint'] = dict(state='EMPTY', pending_count=0,
                                                  sha256=sha256(b'').hexdigest())
        raw = fixture._put(case.settled_path, settled)
        reference = fixture._ref(case.settled_path, settled['settled_state_id'], raw)
        failure = json.loads(case.failure_path.read_bytes()); failure['settled_state'] = reference
        raw = fixture._put(case.failure_path, failure)
        permit = json.loads(case.permit_path.read_bytes())
        permit.update(settled_state=reference,
            failure_cleanup=fixture._ref(case.failure_path, failure['failure_cleanup_id'], raw))
        fixture._put(case.permit_path, permit)
        reservation = json.loads(case.reservation_path.read_bytes()); reservation['settled_state'] = reference
        fixture._put(case.reservation_path, reservation)
    installation = json.loads(case.permit_path.read_bytes())['installation']
    repository, bundle = Path(installation['repository_path']), Path(installation['bundle_path'])
    try:
        shutil.copytree(source_root, repository, ignore=shutil.ignore_patterns(
            '.git', '.pytest_cache', '__pycache__', '*.pyc', '*.pyo'))
        def git(*args):
            return subprocess.run(['/usr/bin/git', *args], cwd=repository,
                check=True, capture_output=True).stdout
        git('init', '-q')
        git('checkout', '-q', '-b', 'maintenance/release-b-swing-ux')
        git('remote', 'add', 'origin', 'git@github.com:imran/Project-Kronos.git')
        git('add', '--force', '--all')
        git('-c', 'user.name=KRONOS Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-q', '-m', 'exact disposable restoration entry')
        revision, tree = git('rev-parse', 'HEAD').decode().strip(), git('rev-parse', 'HEAD^{tree}').decode().strip()
        tracked = []
        for row in git('ls-files', '-s', '-z').split(b'\0'):
            if row:
                metadata, path = row.split(b'\t', 1); relative = path.decode()
                tracked.append(dict(path=relative, mode=metadata.split()[0].decode(),
                    sha256=sha256((repository / relative).read_bytes()).hexdigest()))
        tracked.sort(key=lambda row: row['path'])
        # This is a selected-document roster derived from the Git source bytes,
        # not a StartupCapture instance or fabricated StartupEvidence.
        capture_rows = []
        for prefix, package in (('src/kronos', 'kronos'), ('tools', 'tools')):
            for path in (repository / prefix).rglob('*.py'):
                parts = list(path.relative_to(repository / prefix).with_suffix('').parts)
                if parts[-1] == '__init__': parts.pop()
                capture_rows.append(dict(module='.'.join([package, *parts]),
                    path=path.relative_to(repository).as_posix(),
                    sha256=sha256(path.read_bytes()).hexdigest()))
        capture_rows.sort(key=lambda row: row['module'])
        pinned_digest = sha256(bootstrap._canonical(
            [[row['module'], row['sha256']] for row in capture_rows])).hexdigest()
        selected_capture = [dict(row) for row in capture_rows]
        if selection == 'missing-selected-capture': selected_capture.pop()
        if selection == 'mismatched-selected-capture': selected_capture[0]['sha256'] = '9' * 64
        source_document = dict(schema='KRONOS_RESTORATION_SOURCE_MANIFEST_V1',
            origin_url='git@github.com:imran/Project-Kronos.git',
            source_ref='refs/heads/maintenance/release-b-swing-ux', revision=revision,
            git_tree_oid=tree, files=tracked, capture=selected_capture)
        source_manifest = case.root / 'source-manifest.json'
        fixture._put(source_manifest, source_document)
        for relative in ('Contents/Info.plist', 'Contents/Resources/KRONOS.icns',
                         'Contents/Resources/KRONOS.png'):
            path = bundle / relative; path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repository / 'tools/macos/KRONOS.app' / relative, path)
        for relative, raw in (('Contents/MacOS/KRONOS', b'F02 disposable launcher signature seam\n'),
                              ('Contents/_CodeSignature/CodeResources', b'F02 synthetic signature\n')):
            path = bundle / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        bundle.chmod(0o755)
        for path in bundle.rglob('*'):
            path.chmod(0o755 if path.is_dir() or path.relative_to(bundle).as_posix() == 'Contents/MacOS/KRONOS' else 0o644)
        if native:
            isolation=json.loads(Path(os.environ['KRONOS_TEST_ISOLATION_MANIFEST']).read_text())
            port=isolation['allowed_ports'][0]
            _r33_compile_lifecycle_parent(source_root,bundle,evidence,port)
        rows = setup._c02_bundle_manifest(bundle)
        file_map = {row['path']: row['sha256'] for row in tracked}
        binary = sha256((bundle / 'Contents/MacOS/KRONOS').read_bytes()).hexdigest()
        artifact_document = dict(schema='KRONOS_LAUNCHER_PACKAGE_V1', source_revision=revision,
            source_state='CLEAN_COMMIT', source_launcher_sha256=file_map['tools/macos/kronos_launcher.c'],
            previous_tracked_binary_sha256=file_map['tools/macos/KRONOS.app/Contents/MacOS/KRONOS'],
            built_binary_sha256=binary, signed_binary_sha256=binary,
            procedure_sha256=file_map['tools/macos/package_launcher.py'],
            compiler_flags=['-Wall', '-Wextra', '-Werror', '-O2', '-mmacosx-version-min=13.0'],
            compiler=('R33 disposable component compilation; see retained compile-result.json; package publication/signing metadata synthetic' if native else 'F02 synthetic build seam; no build execution'),
            signing='AD_HOC; timestamp=none; no entitlements; resources sealed',
            strict_verification='PASS', isolated_execution='PASS',
            bundle_identity=sha256(bootstrap._canonical(rows)).hexdigest(), bundle_manifest=rows,
            archive_sha256=sha256(b'F02 synthetic archive').hexdigest())
        artifact_manifest = case.root / 'artifact-manifest.json'
        artifact_manifest.write_bytes(bootstrap._canonical(artifact_document) + b'\n'); artifact_manifest.chmod(0o600)
        target = dict(revision=revision, tree_sha256=sha256(bootstrap._canonical(tracked)).hexdigest(),
            pinned_capture_sha256=pinned_digest, origin_url=source_document['origin_url'],
            source_ref=source_document['source_ref'])
        if native:
            return _r33_native_lifecycle(case,repository,bundle,source_manifest,artifact_manifest,
                dict(target,source_manifest_sha256=sha256(source_manifest.read_bytes()).hexdigest(),
                    artifact_manifest_sha256=sha256(artifact_manifest.read_bytes()).hexdigest()),
                capture_rows,evidence,port,record_property,selection)
        parent_birth, _ = setup._c02_kernel_birth(os.getpid())
        reservation = json.loads(case.reservation_path.read_bytes())
        reservation['parent'].update(pid=os.getpid(), kernel_birth=parent_birth)
        fixture._put(case.reservation_path, reservation)
        env = dict(KRONOS_LAUNCH_MODE=bootstrap.RESTORATION_MODE,
            KRONOS_RESTORATION_ORIGINAL_ATTEMPT_ID=json.loads(case.incident_path.read_bytes())['original_attempt_id'],
            KRONOS_RESTORATION_PERMIT_PATH=str(case.permit_path),
            KRONOS_RESTORATION_PERMIT_ID=case.selected_permit.permit_id,
            KRONOS_RESTORATION_RESERVATION_PATH=str(case.reservation_path),
            KRONOS_RESTORATION_RESERVATION_ID=case.selected_reservation.reservation_id,
            KRONOS_RESTORATION_SOURCE_MANIFEST_PATH=str(source_manifest),
            KRONOS_RESTORATION_ARTIFACT_MANIFEST_PATH=str(artifact_manifest))
        setup._c02_refresh(case, env, source_manifest=source_manifest,
            artifact_manifest=artifact_manifest, target_values=target, parent_birth=parent_birth)
        # R3.3 regression context: the parent fixture supplies native provenance
        # at the real post-spawn observation boundary. This is explicitly NOT a
        # native orchestration qualification; no capture/context is injected.
        reservation_raw = case.reservation_path.read_bytes()
        selected_attempt = fixture._ref(case.reservation_path,case.selected_reservation.reservation_id,reservation_raw)
        fixture._put(case.reservation_path.parent / (selected_attempt['identity'] + '.json'),
            json.loads(reservation_raw))
        head = json.loads(case.head_path.read_bytes())
        activation = bootstrap._native_phase('activation-regression-fixture','NATIVE_ACTIVATED',
            original='activation-regression-fixture',installation=installation,
            parent=json.loads(reservation_raw)['parent'],selected=None,predecessor=None,
            previous=None,details={},now=case.now)
        activation_raw = fixture._put(case.head_path.parent / (activation['identity'] + '.json'),activation)
        first = dict(head,sequence=1,state='NATIVE_ACTIVATED',incident_id=None,
            active_reservation_id=activation['identity'],active_reservation_sha256=sha256(activation_raw).hexdigest(),
            previous_head_sha256='0'*64,recorded_at=case.now.isoformat())
        first_raw = fixture._put(case.head_path.parent / 'head-1.json',first)
        head.update(sequence=2,previous_head_sha256=sha256(first_raw).hexdigest(),recorded_at=case.now.isoformat())
        fixture._put(case.head_path,head)
        fixture._put(case.head_path.parent / 'head-2.json',head)
        fixture._s304_admit_fixture(case.head_path.parent,installation)
        env.update(KRONOS_NATIVE_ATTEMPT_PATH=selected_attempt['path'],
            KRONOS_NATIVE_ATTEMPT_BYTES=str(selected_attempt['bytes']),
            KRONOS_NATIVE_ATTEMPT_SHA256=selected_attempt['sha256'],
            KRONOS_NATIVE_ATTEMPT_ID=selected_attempt['identity'],
            KRONOS_NATIVE_HEAD_SHA256=sha256(case.head_path.read_bytes()).hexdigest())
        identified_path = case.reservation_path.parent / (selected_attempt['identity'] + '.identified.json')
        payload = dict(repository=str(repository), anchor=installation['anchor_path'],
            image=str(bundle / 'Contents/MacOS/KRONOS'), environment=env,
            now=case.now.isoformat(), claim_path=str(case.claim_path),
            expected_capture=capture_rows, expected_pinned_digest=pinned_digest,
            selection=selection, evidence=str(evidence), integrated=integrated,
            deadline_ns=case.custody.budget.deadline_ns,identified_path=str(identified_path),
            checkpoint=json.loads(case.settled_path.read_bytes())['notification_checkpoint'])
        (evidence / 'fixture-input.json').write_text(json.dumps(payload, indent=2) + '\n')
        for name, path in dict(source_manifest=source_manifest, artifact_manifest=artifact_manifest,
                permit=case.permit_path, reservation=case.reservation_path,
                incident=case.incident_path, cleanup=case.failure_path,
                settled=case.settled_path, head=case.head_path).items():
            (evidence / (name + '.json')).write_bytes(path.read_bytes())
        executed = {}
        for relative in ('tools/kronos_browser.py', 'src/kronos/intraday/runtime_identity.py',
                         'src/kronos/common/release_admission.py',
                         'src/kronos/common/legacy_bootstrap.py',
                         'src/kronos/common/failed_successor_restore.py'):
            path = repository / relative
            retained = evidence / 'executed-source' / relative
            retained.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, retained)
            executed[relative] = dict(sha256=sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size, mode=oct(stat.S_IMODE(path.stat().st_mode)))
        (evidence / 'executed-source-identity.json').write_text(json.dumps(dict(
            repository=str(repository), revision=revision, tree=tree, files=tracked,
            retained_exact_files=executed), indent=2) + '\n')
        driver = evidence / 'fresh-entry-driver.py'; driver.write_text(_C03_F02_FRESH_ENTRY_DRIVER)
        child_env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (
            source_root / 'tools/testing/bootstrap', repository / 'src', repository))))
        command = [sys.executable, '-B', str(driver),
            str(evidence / 'fixture-input.json'), str(case.custody.descriptor)]
        process = subprocess.Popen(command,cwd=repository,env=child_env,
            pass_fds=(case.custody.descriptor,),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            child_birth, _ = setup._c02_kernel_birth(process.pid)
            identified = dict(schema='KRONOS_NATIVE_CHILD_IDENTIFIED_V1',selected=selected_attempt,
                parent=json.loads(reservation_raw)['parent'],child=dict(pid=process.pid,kernel_birth=child_birth))
            fixture._put(identified_path,identified)
            stdout,stderr = process.communicate(timeout=100)
            result = subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
        finally:
            if process.poll() is None:
                process.kill();process.communicate()
        (evidence / 'stdout.log').write_text(result.stdout)
        (evidence / 'stderr.log').write_text(result.stderr)
        (evidence / 'process-exit.json').write_text(json.dumps(dict(actual_exit=result.returncode,
            waited=True, parent_reference_still_held=True), indent=2) + '\n')
        assert result.returncode == 0, result.stderr
        observed = json.loads((evidence / 'observations.json').read_text())
        native_facts={}
        for path in case.reservation_path.parent.glob(selected_attempt['identity'] + '.*.json'):
            directory=evidence/'native-facts';directory.mkdir(exist_ok=True)
            (directory/path.name).write_bytes(path.read_bytes())
            native_facts[path.name.removeprefix(selected_attempt['identity']+'.').removesuffix('.json')]=json.loads(path.read_bytes())
        record_property('fresh_entry_observations', json.dumps(observed, sort_keys=True))
        assert observed['entry_exit'] == (0 if selection == 'integrated-healthy' else 78)
        assert observed['capture_instances'] == 1
        assert observed['original_capture_retained']
        assert observed['actual_bootstrap_adoption'] and observed['same_original_budget']
        assert observed['original_deadline_preserved']
        assert observed['actual_pinned_evidence'] and observed['loaded_module_subset']
        assert observed['capture_reinjected'] is False
        assert observed['actual_source_validator_calls'] >= 1
        assert not available(case.custody.binding)  # Parent reference excludes teardown authority.
        if integrated:
            if selection in {'integrated-pre-completion-failure','integrated-pre-completion-current-authority-denial'}:
                assert observed['actual_consumer_calls']==observed['claim_writes']==1
                assert observed['actual_capture_calls']==3
                assert observed['original_failure']=='RuntimeError'
                assert observed['events']==['CONSUMED','RETAIN_RECHECK','PRE_COMPLETION_RECHECK','EXPLICIT_PRE_COMPLETION_FAULT']
                assert not observed['successful_ready_release'] and observed['failure_cleanup_started']
                assert observed['application_cleanup_complete'] and observed['custody_released']
                cleanup=native_facts['cleanup-observed']['payload']
                assert cleanup['complete'] and cleanup['final_owner_proof'] and not cleanup['helpers_unresolved']
                assert not cleanup['completion_entered'] and not cleanup['ready_observed']
                assert cleanup['ready_evidence']==dict(ready_or_receipt=False,receipt_proven_absent=True)
                assert native_facts['cleanup-acknowledged']['payload']==dict(cleanup_started=True,cleanup_complete=True,custody_released=True)
                if selection.endswith('current-authority-denial'):
                    assert observed['theta_fixture_clock']=='ACTUAL_CURRENT_UTC_UNCHANGED'
                    assert observed['theta_review_seam']=='SYNTHETIC-S3-01-TEST-REVIEW-NOT-OWNER-APPROVAL'
                    assert cleanup['settled_continuity']=='VALIDATED_CURRENT'
                    assert 'continuity-unavailable' not in native_facts
                    assert 'settled-state-files' in native_facts
                else:
                    assert observed['theta_fixture_clock']=='2026-10-28T08:30:00+00:00'
                    assert cleanup['settled_continuity']=='VALIDATED_CURRENT',native_facts.get('continuity-unavailable')
                assert observed['claim_unchanged_after_consumption']
                return observed
            assert observed['actual_consumer_calls'] == observed['claim_writes'] == 1
            assert observed['actual_capture_calls'] == 4
            assert observed['same_capture_mapping_and_custody']
            assert observed['bootstrap_pinned_classes_reconciled']
            assert observed['accepted_checkpoint'] == payload['checkpoint']
            assert observed['actual_main_calls'] == 1
            assert observed['fixture_v2_substitution_blocked']
            assert observed['ready_at_completion'] == observed['final_startup_state'] == 'READY'
            assert observed['receipt_preserved'] and observed['committed_records_preserved']
            assert observed['application_outcomes_recorded_before_fixture_teardown']
            assert observed['socket_closed_by_application']
            assert observed['application_domain_closed']
            assert observed['same_owner_activation']
            if selection == 'integrated-healthy':
                assert observed['events'] == ['CONSUMED', 'RETAIN_RECHECK',
                    'PRE_COMPLETION_RECHECK', 'READY_RECEIPT', 'POST_COMPLETION_RECHECK',
                    'READY_RELEASE', 'UX10', 'WO13', 'K5', 'SERVE']
                assert observed['main_returned'] == 0
                assert observed['original_failure'] == 'NoneType'
                assert not observed['failure_cleanup_started']
                assert observed['successful_ready_release'] and observed['custody_released']
            else:
                assert observed['events'] == ['CONSUMED', 'RETAIN_RECHECK',
                    'PRE_COMPLETION_RECHECK', 'READY_RECEIPT', 'POST_COMPLETION_DENIED']
                assert observed['original_failure'] == 'BootstrapError'
                assert observed['failure_cleanup_started']
                assert not observed['successful_ready_release']
                if observed['application_cleanup_complete']:
                    assert observed['custody_released']
                else:
                    assert not observed['custody_released']
            claim = json.loads(case.claim_path.read_bytes())
            assert claim['child']['pid'] == observed['process_id']
            assert claim['parent']['pid'] == os.getpid()
            assert claim['claimed_at'] == case.now.isoformat()
            assert observed['claim_unchanged_after_consumption']
            (evidence / 'spent-claim.json').write_bytes(case.claim_path.read_bytes())
            return observed
        assert observed['application_cleanup_complete'] and observed['custody_released']
        if selection == 'valid':
            assert observed['original_failure'] == 'F02BoundaryComplete'
            assert observed['actual_consumer_calls'] == observed['claim_writes'] == 1
            assert observed['actual_capture_calls'] == 2  # Initial capture and retained-attempt recheck.
            assert observed['same_capture_mapping_and_custody']
            assert observed['bootstrap_pinned_classes_reconciled']
            claim = json.loads(case.claim_path.read_bytes())
            assert claim['child']['pid'] == observed['process_id']
            assert claim['parent']['pid'] == os.getpid()
            assert claim['claimed_at'] == case.now.isoformat()
            (evidence / 'spent-claim.json').write_bytes(case.claim_path.read_bytes())
        else:
            assert observed['original_failure'] == 'BootstrapError'
            assert 'SOURCE_INVALID' in observed['failure_message']
            assert observed['actual_consumer_calls'] == observed['claim_writes'] == 0
            assert not case.claim_path.exists()
    finally:
        case.close()
        (evidence / ('outer-fixture-teardown.json' if native else 'test-teardown.json')).write_text(json.dumps(dict(
            parent_reference_closed=case.custody.released, application_cleanup_claimed=False,
            claim_deleted_or_repaired=False), indent=2) + '\n')


def _r33_compile_lifecycle_parent(source_root,bundle,evidence,port,policy=None):
    import subprocess,shutil
    from hashlib import sha256
    source=(source_root/'tools/macos/kronos_launcher.c').read_text()
    if policy is not None:
        source=source.replace('approved_initialization_disposition = NULL;',
            'approved_initialization_disposition = '+json.dumps(policy.decode())+';')
    source=source.replace('int main(void) {','int preserved_operational_main(void) {')
    source=source.replace('static const dev_t approved_admission_device = 16777232;','static dev_t approved_admission_device = 0;')
    source=source.replace('static const ino_t approved_admission_inode = 694844364;','static ino_t approved_admission_inode = 0;')
    source=source.replace('8947',str(port))
    source+=r'''
int main(int argc,char **argv) {
 if(argc!=11)return 90;
 struct stat st;if(stat(argv[1],&st)!=0)return 91;
 admission_anchor=argv[1];approved_admission_device=st.st_dev;approved_admission_inode=st.st_ino;
 canonical_bundle=argv[3];canonical_executable=argv[0];
 admission_descriptor=acquire_installation_admission(argv[1],st.st_dev,st.st_ino);
 if(admission_descriptor<0)return 92;
 validation_deadline_ns=validation_now_ns()+120000000000LL;
 int original=!strcmp(argv[5],"T");
 if(!native_gate(argv[2],argv[4],original?"GOVERNED_REPLACEMENT":"FAILED_SUCCESSOR_RESTORATION"))return 93;
 const char *home=getenv("HOME");char control[PATH_MAX],entry[PATH_MAX],path[PATH_MAX*2];
 snprintf(control,sizeof(control),"%s/Library/Application Support/KRONOS/runtime/browser-backend-v1.control",home);
 snprintf(entry,sizeof(entry),"%s/tools/kronos_browser.py",argv[2]);
 snprintf(path,sizeof(path),"%s/src:%s",argv[2],argv[2]);
 pid_t predecessor=(pid_t)atoi(argv[6]);
 if(original) {
  if(!native_original_reserve(predecessor) || !native_dispatch_intent(control,argv[7]))return 94;
  /* Synthetic predecessor shutdown seam: establish the SAME existing stop
   * and handoff windows at dispatch, as request_graceful_shutdown does. */
  long long dispatch_now=validation_now_ns();if(!dispatch_now)return 95;
  stop_deadline_ns=dispatch_now+15000000000LL;
  handoff_deadline_ns=dispatch_now+45000000000LL;
  int effect=open(argv[9],O_WRONLY|O_CREAT|O_EXCL,0600);
  if(effect<0 || write(effect,"D",1)!=1 || fsync(effect)!=0)return 95;
  close(effect);puts("ACTUAL_DISPATCH_INTENT_READ_BACK_BEFORE_FIXTURE_PREDECESSOR_RETIREMENT");fflush(stdout);
  if(!wait_for_backend_stop(predecessor) ||
     !verify_v2_handoff(argv[2],argv[4],path,control,argv[7],predecessor,argv[10],argv[8]) ||
     !native_retired(home,argv[7]))return 96;
 } else {
  native_startup.restoration=1;
  if(!native_select_environment() || !native_validation("restoration-reserve","","{}",1) || !native_apply_proposal())return 97;
 }
 BackendStartResult result=start_backend(argv[2],argv[4],entry,path,
     original?predecessor:0,original?argv[8]:"",original?argv[7]:"",original?argv[10]:"");
 if(original && result==BACKEND_START_CHILD_EXITED && native_terminal_cleanup()) {
  printf("ACTUAL_ORIGINAL_TERMINAL=%s\n",native_journal.state);fflush(stdout);finish_admission();return 78;
 }
 if(!original && result==BACKEND_START_READY) {
  printf("ACTUAL_RESTORATION_TERMINAL=%s\n",native_journal.state);fflush(stdout);finish_admission();
  /* Test-only cooperative teardown AFTER the application/native outcome.
   * Keep this native fixture parent alive to reap its exact service child. */
  int status=0;pid_t reaped;do{reaped=waitpid(admission_child,&status,0);}while(reaped<0 && errno==EINTR);
  if(reaped!=admission_child)return 98;
  printf("DISPOSABLE_R_CHILD_REAPED=%d\n",status);fflush(stdout);
  return WIFEXITED(status) && WEXITSTATUS(status)==0 ? 0:99;
 }
 fprintf(stderr,"R33_DISPOSABLE_RESULT_UNRESOLVED result=%d child=%ld observed=%d status=%d\n",
     result,(long)admission_child,admission_child_observed,admission_child_status);fflush(stderr);
 finish_admission();return 79;
}
'''
    label='native-lifecycle' if policy is None else 'admitted-native-lifecycle'
    unit=evidence/(label+'.c');unit.write_text(source)
    binary=bundle/'Contents/MacOS/KRONOS'
    command=['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)]
    result=subprocess.run(command,capture_output=True,text=True)
    (evidence/(label+'.clang.stdout.log')).write_text(result.stdout);(evidence/(label+'.clang.stderr.log')).write_text(result.stderr)
    (evidence/(label+'.compile-result.json')).write_text(json.dumps(dict(command=command,actual_exit=result.returncode,
        source_sha256=sha256((source_root/'tools/macos/kronos_launcher.c').read_bytes()).hexdigest(),
        compiled_unit_sha256=sha256(unit.read_bytes()).hexdigest(),
        binary_sha256=sha256(binary.read_bytes()).hexdigest() if result.returncode==0 else None,
        seams='DISPOSABLE_BINDING_CANONICAL_PATH_AND_PORT; COMPONENT_MAIN_CALLS_ACTUAL_NATIVE_GATE_RESERVATION_DISPATCH_START_MONITOR_AND_TERMINAL; NO_B_APPLICATION_REHEARSAL'),indent=2)+'\n')
    assert result.returncode==0,result.stderr
    binary.chmod(0o755);shutil.copy2(binary,evidence/label)


def _r33_native_lifecycle(case,repository,bundle,source_manifest,artifact_manifest,target,capture_rows,evidence,port,record_property,selection):
    import os,sys,subprocess,threading,shutil,signal
    from datetime import datetime,UTC,timedelta
    from hashlib import sha256
    from kronos.common import legacy_bootstrap as b,maintenance
    from tests.unit.common import test_failed_successor_restore as fixture
    source_root=Path(__file__).resolve().parents[3]
    case.close()
    for name,path in (('selected-source-manifest.json',source_manifest),
                      ('selected-artifact-manifest.json',artifact_manifest)):
        shutil.copy2(path,evidence/name)
    anchor=Path.home()/'Library/Application Support/KRONOS/runtime'
    anchor.mkdir(mode=0o700,parents=True,exist_ok=True);anchor.chmod(0o700)
    journal=anchor/'failed-successor-restore-v1';journal.mkdir(mode=0o700)
    metadata=anchor.stat()
    core=dict(anchor_path=str(anchor),device=metadata.st_dev,inode=metadata.st_ino,owner=os.getuid(),
        bundle_id='com.project-kronos.browser-v1',bundle_path=str(bundle),repository_path=str(repository))
    installation=dict(identity=sha256(b._canonical(core)).hexdigest(),**core)
    now=datetime.now(UTC);generation=sha256(b'R33-SYNTHETIC-PREDECESSOR-DRAIN').hexdigest()
    token=sha256(b'R33-NONSECRET-FIXTURE-PROOF').hexdigest()
    request_path=evidence/'fixture-retirement.request';marker=evidence/'cooperative-r-teardown.request'
    binary=bundle/'Contents/MacOS/KRONOS';control_path=anchor/'browser-backend-v1.control'
    maintenance_root=anchor/'maintenance';maintenance_root.mkdir(mode=0o700)
    b_runtime=sha256(b'EXPLICIT-SYNTHETIC-B-RUNTIME-IDENTITY').hexdigest();prior_revision='a'*40
    drain={key:0 for key in maintenance._DRAIN_ZERO_FIELDS}
    drain['notification_checkpoint']=dict(state='EMPTY',pending_count=0,sha256=sha256(b'').hexdigest())
    predecessor_data=dict(request=str(request_path),control=str(control_path),root=str(maintenance_root),
        generation=generation,proof=token,runtime=b_runtime,revision=prior_revision,drain=drain,
        teardown=str(marker))
    pd=evidence/'synthetic-predecessor.json';pd.write_text(json.dumps(predecessor_data,indent=2)+'\n')
    predecessor_driver=evidence/'synthetic-predecessor.py'
    predecessor_driver.write_text('''import json,os,sys,time
from pathlib import Path
from datetime import datetime,UTC
from kronos.common.maintenance import publish_drain_handoff
d=json.loads(Path(sys.argv[1]).read_text())
p=Path(d['control']);temporary=p.with_name(p.name+'.tmp')
fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
raw=('KRONOS_BROWSER_BACKEND_CONTROL_V1\\n'+str(os.getpid())+'\\n'+d['proof']+'\\n').encode()
os.write(fd,raw);os.fsync(fd);os.close(fd);os.replace(temporary,p)
directory=os.open(p.parent,os.O_RDONLY);os.fsync(directory);os.close(directory)
until=time.monotonic()+120
while not Path(d['request']).exists():
 if Path(d['teardown']).exists():raise SystemExit(0)
 if time.monotonic()>=until:raise RuntimeError('FIXTURE_DISPATCH_NOT_OBSERVED')
 time.sleep(.002)
publish_drain_handoff(Path(d['root']),generation=d['generation'],parent_pid=os.getpid(),proof=d['proof'],runtime_identity=d['runtime'],loaded_revision=d['revision'],drain=d['drain'],now=datetime.now(UTC))
p.unlink()
''')
    predecessor_out=(evidence/'synthetic-predecessor.stdout.log').open('w')
    predecessor_err=(evidence/'synthetic-predecessor.stderr.log').open('w')
    predecessor=subprocess.Popen([sys.executable,'-B',str(predecessor_driver),str(pd)],
        stdout=predecessor_out,stderr=predecessor_err,text=True)
    owned=[];teardowns=[]
    predecessor_done=threading.Event()
    predecessor_result={}
    predecessor_deadline=time.monotonic()+120
    def reap_predecessor():
        # This thread is the sole wait owner, including failed fixture teardown.
        try:
            code=predecessor.wait(timeout=max(0,predecessor_deadline-time.monotonic()))
            predecessor_result.update(actual_exit=code,waited=True)
        except subprocess.TimeoutExpired:
            predecessor.kill()
            predecessor_result.update(actual_exit=predecessor.wait(),waited=True,
                forced_test_teardown=True,reason='SYNTHETIC_PREDECESSOR_FIXTURE_DEADLINE')
        except BaseException as error:
            predecessor_result.update(waited=False,error=type(error).__name__)
        finally:
            predecessor_result.update(pid=predecessor.pid,sole_wait_owner='predecessor-reaper',
                synthetic_product_drain_not_application_cleanup=True)
            (evidence/'synthetic-predecessor-result.json').write_text(
                json.dumps(predecessor_result,indent=2)+'\n')
            predecessor_done.set()
    reaper=threading.Thread(target=reap_predecessor,name='predecessor-reaper')
    reaper.start()
    def retain_native_state(label):
        # Preserve actual bytes before harness disposal, including partial writes.
        destination=evidence/'retained-native-state'/label
        destination.mkdir(parents=True,exist_ok=False)
        rows={}
        for path in sorted(anchor.rglob('*')):
            relative=path.relative_to(anchor)
            if path.is_symlink():
                rows[str(relative)]=dict(type='symlink',target=os.readlink(path))
            elif path.is_file():
                raw=path.read_bytes();out=destination/relative
                out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
                out.chmod(path.stat().st_mode&0o7777)
                rows[str(relative)]=dict(type='file',bytes=len(raw),sha256=sha256(raw).hexdigest(),
                    mode=oct(path.stat().st_mode&0o7777))
        (destination/'INVENTORY.json').write_text(json.dumps(rows,indent=2)+'\n')
    try:
        deadline=time.monotonic()+5
        while not control_path.exists():
            assert not predecessor_done.is_set(),predecessor_result
            if time.monotonic()>=deadline:pytest.fail('synthetic predecessor control did not publish')
            time.sleep(.002)
        prior=dict(pid=predecessor.pid,kernel_birth=b._observe_process(predecessor.pid)['kernel_birth'],
            runtime_identity=b_runtime,revision=prior_revision)
        activation=b._native_phase('activation-fixture','NATIVE_ACTIVATED',original='activation-fixture',
            installation=installation,parent=prior,selected=None,predecessor=None,previous=None,
            details=dict(child=prior,scope='SYNTHETIC_PREDECESSOR_PRODUCT_DRAIN; NOT_R5_B_REHEARSAL'),now=now)
        raw=fixture._put(journal/'activation-fixture.json',activation)
        head=dict(schema='KRONOS_RESTORATION_ADMISSION_HEAD_V1',installation_identity=installation['identity'],
            sequence=1,state='NATIVE_ACTIVATED',incident_id=None,active_reservation_id='activation-fixture',
            active_reservation_sha256=sha256(raw).hexdigest(),previous_head_sha256='0'*64,recorded_at=now.isoformat())
        fixture._put(journal/'admission-head.json',head);fixture._put(journal/'head-1.json',head)
        policy=fixture._s304_admit_fixture(journal,installation)
        _r33_compile_lifecycle_parent(source_root,bundle,evidence,port,policy)
        from tests.unit.common import test_legacy_bootstrap as s304_setup
        artifact=json.loads(artifact_manifest.read_bytes());rows=s304_setup._c02_bundle_manifest(bundle)
        digest=sha256(binary.read_bytes()).hexdigest()
        artifact.update(bundle_manifest=rows,bundle_identity=sha256(b._canonical(rows)).hexdigest(),
            built_binary_sha256=digest,signed_binary_sha256=digest)
        artifact_manifest.write_bytes(b._canonical(artifact)+b'\n')
        target=dict(target,artifact_manifest_sha256=sha256(artifact_manifest.read_bytes()).hexdigest())
        decisions={}
        for label in ('sponsor','ca','pcp','product'):
            path=evidence/(label+'-synthetic-authority.txt');path.write_bytes(('SYNTHETIC ISOLATED FIXTURE ONLY: '+label).encode());path.chmod(0o600)
            decisions[label]=fixture._ref(path,label+'-synthetic-authority',path.read_bytes())
        def profile(mode,permit=None):
            value=dict(schema=b.NATIVE_SELECTION_SCHEMA,selection_id='profile-'+mode.lower().replace('_','-'),
                mode=mode,installation=installation,target=target,
                source_manifest=fixture._ref(source_manifest,'selected-source',source_manifest.read_bytes()),
                artifact_manifest=fixture._ref(artifact_manifest,'selected-artifact',artifact_manifest.read_bytes()),
                operational_order=decisions['sponsor'],decisions=decisions,permit=permit,
                valid_from=(now-timedelta(seconds=30)).isoformat(),valid_until=(now+timedelta(minutes=8)).isoformat())
            path=evidence/(value['selection_id']+'.json');fixture._put(path,value)
            return value,path
        driver=evidence/'fresh-native-entry-driver.py';driver.write_text(_C03_F02_FRESH_ENTRY_DRIVER)
        payload=evidence/'native-entry-input.json'
        data=dict(repository=str(repository),anchor=str(anchor),image=str(binary),environment={},
            now=now.isoformat(),claim_path=str(maintenance_root/(generation+'.consumed.json')),
            expected_capture=capture_rows,expected_pinned_digest=target['pinned_capture_sha256'],
            selection=('native-T-pre-completion-failure' if selection=='native-original-and-restoration' else selection.replace('native-original-','native-T-')),evidence=str(evidence/'T'),integrated=True,
            native=True,port=port,work=str(evidence/'composition'),teardown_marker=str(marker),
            checkpoint=drain['notification_checkpoint'])
        (evidence/'T').mkdir();payload.write_text(json.dumps(data,indent=2)+'\n')
        shim=evidence/'helper-and-entry-python'
        shim.write_text('#!'+sys.executable+'\n'+'''import os,runpy,sys
from pathlib import Path
'''+ 'repository='+repr(str(repository))+'\n'+
            'sys.path[:0]=[repository+"/src",repository]\n'+
            'arguments=sys.argv[1:]\n'+
            'if arguments[0:2]==["-B","-c"]:\n'+
            ' from kronos.common import legacy_bootstrap as b,release_admission as a\n'+
            ' from kronos.common import failed_successor_restore as s304_restore\n'+
            ' s304_restore.INITIALIZATION_DISPOSITION='+repr(policy)+'\n'+
            ' a.CANONICAL_PARENT='+repr(str(binary))+'\n'+
            ' b._verify_bundle_signature=lambda *_:None\n'+
            ' def record_helper_failure(frame,event,arg):\n'+
            '  if event=="exception" and frame.f_code.co_name in {"native_validation_result","native_validation_stdio"}:\n'+
            '   import json,traceback\n'+
            '   record={"exception":arg[0].__name__,"frames":[{"function":x.name,"line":x.lineno} for x in traceback.extract_tb(arg[2])][-8:]}\n'+
            '   Path('+repr(str(evidence/'helper-failure-'))+'+str(os.getpid())+".json").write_text(json.dumps(record))\n'+
            '   if frame.f_code.co_name=="native_validation_stdio" and isinstance(frame.f_locals.get("raw"),bytes):Path('+repr(str(evidence/'helper-input-'))+'+str(os.getpid())+".json").write_bytes(frame.f_locals["raw"])\n'+
            '  return record_helper_failure\n'+
            ' sys.settrace(record_helper_failure)\n'+
            ' exec(arguments[2],{"__name__":"__main__"})\n'+
            'elif arguments[0:2]==["-B","-m"]:\n'+
            ' sys.argv=arguments[2:];runpy.run_module(arguments[2],run_name="__main__")\n'+
            'elif len(arguments)>1 and arguments[1].endswith("/tools/kronos_browser.py"):\n'+
            ' sys.argv=['+repr(str(driver))+','+repr(str(payload))+',"197"]\n'+
            ' runpy.run_path('+repr(str(driver))+',run_name="__main__")\n'+
            'else:\n sys.argv=arguments[1:];runpy.run_path(sys.argv[0],run_name="__main__")\n')
        shim.chmod(0o755)
        def native_denial(label,selected,expected):
            value,path=selected
            before={p.name:p.read_bytes() for p in journal.iterdir() if p.is_file()}
            env=dict(os.environ,HOME=str(anchor.parents[3]),KRONOS_LAUNCH_MODE=value['mode'],
                KRONOS_NATIVE_SELECTION_PATH=str(path),KRONOS_NATIVE_SELECTION_BYTES=str(path.stat().st_size),
                KRONOS_NATIVE_SELECTION_SHA256=sha256(path.read_bytes()).hexdigest(),
                KRONOS_NATIVE_SELECTION_ID=value['selection_id'])
            argv=[str(binary),str(anchor),str(repository),str(bundle),str(shim),'R',
                str(prior['pid']),generation,token,str(request_path),prior_revision]
            process=subprocess.Popen(argv,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            owned.append(process)
            out,err=process.communicate(timeout=30)
            (evidence/(label+'-denial.json')).write_text(json.dumps(dict(command=argv,actual_exit=process.returncode,
                waited=True,pid=process.pid,stdout=out,stderr=err,
                selected_sha256=sha256(path.read_bytes()).hexdigest()),indent=2)+'\n')
            assert process.returncode==expected,(label,out,err)
            # Concurrent child fact publication is lawful. Existing files and
            # the selected head must stay unchanged by the denied contender.
            assert all((journal/name).read_bytes()==raw for name,raw in before.items())
            if label!='concurrent':assert set(before)=={p.name for p in journal.iterdir() if p.is_file()}
        def run_parent(stage,selected):
            value,path=selected
            env=dict(os.environ,KRONOS_LAUNCH_MODE=value['mode'],KRONOS_NATIVE_SELECTION_PATH=str(path),
                KRONOS_NATIVE_SELECTION_BYTES=str(path.stat().st_size),
                KRONOS_NATIVE_SELECTION_SHA256=sha256(path.read_bytes()).hexdigest(),KRONOS_NATIVE_SELECTION_ID=value['selection_id'])
            env['HOME']=str(anchor.parents[3])
            argv=[str(binary),str(anchor),str(repository),str(bundle),str(shim),stage,
                str(prior['pid']),generation,token,str(request_path),prior_revision]
            out=(evidence/(stage+'-native.stdout.log')).open('w');err=(evidence/(stage+'-native.stderr.log')).open('w')
            process=subprocess.Popen(argv,env=env,stdout=out,stderr=err,text=True);owned.append(process)
            code=None;failure=None;concurrent_checked=False
            try:
                until=time.monotonic()+110
                while process.poll() is None:
                    # This is an observed application/native denial, not a
                    # timeout or substitute cleanup proof. Preserve it before
                    # separate fixture teardown stops the retaining parent.
                    if any(word in (evidence/(stage+'-native.stderr.log')).read_text() for word in ('ACTUAL_CHILD_FACTS_UNRESOLVED','DIRECT_CHILD_FAILURE')):
                        retain_native_state('native-unresolved-'+stage)
                        pytest.fail('actual native child facts unresolved; retained before test teardown')
                    if stage=='R':
                        selected_head=json.loads((journal/'admission-head.json').read_bytes())
                        if selected_head['state']=='RESTORATION_RESERVED' and not concurrent_checked:
                            native_denial('concurrent',selected,92);concurrent_checked=True
                        if selected_head['state']=='READY_COMPLETE':
                            assert concurrent_checked
                            accepted=json.loads((journal/(selected_head['active_reservation_id']+'.json')).read_bytes())
                            actual=accepted['details']['child']
                            assert b._observe_process(actual['pid'])['kernel_birth']==actual['kernel_birth']
                            # Validate genuine existing facts while this exact
                            # disposable process is still alive, before teardown.
                            capture_path=next(p for p in journal.glob('*.capture.json')
                                if json.loads(p.read_bytes())['child']==actual)
                            enrollment_checks=object.__new__(b._NativeReadOnlyChecks)
                            enrollment_checks.parent_pid=os.getppid()
                            enrollment_checks.parent_birth=b._observe_process(os.getppid())['kernel_birth']
                            enrollment_checks.budget=case.custody.budget
                            capture_ref=fixture._ref(capture_path,'genuine-disposable-capture',capture_path.read_bytes())
                            assert b._native_initialization_enrollment(capture_ref,enrollment_checks,installation=installation)==actual
                            record_property('s304_enrollment_format','ACTUAL LIVE DISPOSABLE CAPTURE/SUCCESS/RELEASE RECORDS; RETAINED RELEASE B EVIDENCE STILL UNAVAILABLE')
                            assert {p.name:p.read_bytes() for p in maintenance_root.iterdir()}==v2_before
                            assert all(Path(path).read_bytes()==raw for path,raw in protected_before.items())
                            (evidence/'application-before-fixture-teardown.json').write_text(json.dumps(dict(
                                native_ready_complete=True,actual_child=actual,child_still_live=True,
                                original_v2_preserved=True,retained_product_bytes_preserved=True,
                                synthetic_predecessor_product_drain_not_r5=True,production_authority=False),indent=2)+'\n')
                            marker.write_text('COOPERATIVE_TEST_TEARDOWN_ONLY\n');break
                    if time.monotonic()>=until:pytest.fail('native outcome did not settle')
                    time.sleep(.01)
                code=process.wait(timeout=115)
            except BaseException as error:
                failure=dict(type=type(error).__name__,message=str(error));raise
            finally:
                out.close();err.close()
                (evidence/(stage+'-native-command-result.json')).write_text(json.dumps(dict(command=argv,
                    actual_exit=code,waited=code is not None,owned_pid=process.pid,exception=failure,
                    executable_sha256=sha256(binary.read_bytes()).hexdigest()),indent=2)+'\n')
            return code
        t_code=run_parent('T',profile('GOVERNED_REPLACEMENT'))
        reaper.join(timeout=min(5,max(0,predecessor_deadline-time.monotonic())))
        assert predecessor_done.is_set() and not reaper.is_alive(),predecessor_result
        assert predecessor_result.get('waited') and predecessor_result['actual_exit']==0,predecessor_result
        retain_native_state('after-T-native-outcome')
        assert t_code==78,(evidence/'T-native.stderr.log').read_text()
        head=json.loads((journal/'admission-head.json').read_bytes())
        if selection=='native-original-current-authority-denial':
            assert head['state']=='INCIDENT_OPEN',(head,(evidence/'T-native.stderr.log').read_text())
            terminal=json.loads((journal/(head['active_reservation_id']+'.json')).read_bytes())
            assert terminal['details']['eligible_restoration'] is True
            observed=json.loads((evidence/'T/observations.json').read_text())
            assert observed['theta_fixture_clock']=='ACTUAL_CURRENT_UTC_UNCHANGED'
            assert observed['theta_review_seam']=='SYNTHETIC-S3-01-TEST-REVIEW-NOT-OWNER-APPROVAL'
            assert observed['custody_released'] and list(journal.glob('*.settled-state-files.json'))
            assert not list(journal.glob('*.continuity-unavailable.json'))
            assert observed['entry_exit']==78 and observed['application_cleanup_complete']
            assert observed['failure_cleanup_started'] and not observed['successful_ready_release']
            assert not any(event in observed['events'] for event in ('READY_RELEASE','READY_RECEIPT','UX10','WO13','K5'))
            assert not list(journal.glob('*.child-claimed.json'))
            record_property('native_terminal_disposition','INCIDENT_OPEN; RESTORATION_ELIGIBLE; ACTUAL_COMPLETION_AND_CLEANUP; NO_RESTORATION_CHILD_LAUNCHED')
            return
        if selection!='native-original-and-restoration':
            expected='READY_OUTSIDE_PERMIT' if selection.endswith('ready-failure') else 'UNRESOLVED'
            assert head['state']==expected,(head,(evidence/'T-native.stderr.log').read_text())
            terminal=json.loads((journal/(head['active_reservation_id']+'.json')).read_bytes())
            assert terminal['details']['eligible_restoration'] is False
            observed=json.loads((evidence/'T/observations.json').read_text())
            assert observed['entry_exit']==78 and observed['application_cleanup_complete']
            assert observed['failure_cleanup_started'] and not observed['successful_ready_release']
            assert not any(event in observed['events'] for event in ('READY_RELEASE','UX10','WO13','K5'))
            if expected=='READY_OUTSIDE_PERMIT':
                assert observed['receipt_preserved'] and 'READY_RECEIPT' in observed['events']
            else:assert 'READY_RECEIPT' not in observed['events']
            native_denial('terminal-blocked',profile('FAILED_SUCCESSOR_RESTORATION'),93)
            assert not list(journal.glob('*.child-claimed.json'))
            record_property('native_terminal_exclusion',expected+'; ACTUAL_COMPLETION_AND_CLEANUP; SYNTHETIC_FAULT_AT_COMPLETION_BOUNDARY')
            return
        assert head['state']=='INCIDENT_OPEN',(evidence/'T-native.stderr.log').read_text()
        phase=json.loads((journal/(head['active_reservation_id']+'.json')).read_bytes())
        assert phase['details']['eligible_restoration'] is True
        observed_t=json.loads((evidence/'T/observations.json').read_text())
        assert observed_t['entry_exit']==78 and observed_t['application_cleanup_complete'] and observed_t['custody_released']
        assert observed_t['failure_cleanup_started'] and not observed_t['successful_ready_release']
        v2_before={path.name:path.read_bytes() for path in maintenance_root.iterdir()}
        product_root=Path.home()/'Library/Application Support/KRONOS/evidence'
        protected_before={str(path):path.read_bytes() for root in (product_root,evidence/'composition/historical') for path in root.rglob('*') if path.is_file()}
        details=phase['details']
        permit_id='permit-r33-explicit-isolated-fixture'
        authority={}
        for label,prefix in (('sponsor','sponsor_order'),('ca','ca_decision'),('pcp','pcp_decision'),('product','product_decision')):
            authority[prefix+'_identity']=decisions[label]['identity'];authority[prefix+'_sha256']=decisions[label]['sha256']
        later=datetime.now(UTC)
        permit=dict(schema='KRONOS_FAILED_SUCCESSOR_RESTORATION_PERMIT_V1',permit_id=permit_id,
            installation=installation,incident=details['incident'],failure_cleanup=details['failure_cleanup'],
            settled_state=details['settled_state'],restoration_target=target,authority=authority,
            created_at=later.isoformat(),approved_at=later.isoformat(),valid_from=later.isoformat(),
            valid_until=(now+timedelta(minutes=8)).isoformat(),maximum_children=1,operation_scope='ONE_FAILED_SUCCESSOR_RESTORATION_START')
        permit_path=evidence/'explicit-synthetic-restoration-permit.json';raw=fixture._put(permit_path,permit)
        permit_ref=fixture._ref(permit_path,permit_id,raw)
        (evidence/'R').mkdir();data.update(selection='native-R-healthy',evidence=str(evidence/'R'),claim_path='RESOLVED_FROM_ACTUAL_NATIVE_RESERVATION')
        payload.write_text(json.dumps(data,indent=2)+'\n')
        restoration_profile=profile('FAILED_SUCCESSOR_RESTORATION',permit_ref)
        expired=dict(restoration_profile[0],selection_id='expired-selection-fixture',
            valid_until=(datetime.now(UTC)-timedelta(seconds=1)).isoformat())
        expired_path=evidence/'expired-selection.json';fixture._put(expired_path,expired)
        native_denial('expired-selection',(expired,expired_path),97)
        r_code=run_parent('R',restoration_profile)
        assert r_code==0,(evidence/'R-native.stderr.log').read_text()
        native_denial('repeated-restoration',restoration_profile,93)
        renamed=dict(permit,permit_id='renamed-permit-same-incident')
        renamed_path=evidence/'renamed-permit.json';renamed_raw=fixture._put(renamed_path,renamed)
        renamed_profile=dict(restoration_profile[0],selection_id='renamed-selection',
            permit=fixture._ref(renamed_path,renamed['permit_id'],renamed_raw))
        renamed_selection=evidence/'renamed-selection.json';fixture._put(renamed_selection,renamed_profile)
        native_denial('renamed-permit-second-child',(renamed_profile,renamed_selection),93)
        final=json.loads((journal/'admission-head.json').read_bytes());assert final['state']=='READY_COMPLETE'
        final_record=json.loads((journal/(final['active_reservation_id']+'.json')).read_bytes())
        actual_child=final_record['details']['child']
        assert len(list(journal.glob('*.child-claimed.json')))==1
        claims=list(journal.glob('*.child-claimed.json'));claim_before=claims[0].read_bytes()
        assert json.loads(claim_before)['child']==actual_child
        assert {p.name:p.read_bytes() for p in maintenance_root.iterdir()}==v2_before
        assert all(Path(path).read_bytes()==raw for path,raw in protected_before.items())
        # Observe the native acceptance and exact retained bytes before test
        # teardown asks the still-running disposable service to exit.
        assert json.loads((evidence/'application-before-fixture-teardown.json').read_text())['child_still_live']
        marker.write_text('COOPERATIVE_TEST_TEARDOWN_ONLY\n')
        until=time.monotonic()+15
        while not (evidence/'R/observations.json').exists():
            if time.monotonic()>=until:pytest.fail('restoration child did not finish cooperative teardown')
            time.sleep(.01)
        r_observed=json.loads((evidence/'R/observations.json').read_text())
        assert r_observed['entry_exit']==0 and r_observed['actual_consumer_calls']==r_observed['claim_writes']==1
        assert r_observed['actual_main_calls']==1 and r_observed['successful_ready_release']
        assert r_observed['same_original_budget'] and r_observed['original_deadline_preserved']
        assert r_observed['receipt_preserved'] and r_observed['claim_unchanged_after_consumption']
        assert claims[0].read_bytes()==claim_before
        for path in journal.iterdir():
            directory=evidence/'retained-native-journal';directory.mkdir(exist_ok=True);shutil.copy2(path,directory/path.name)
        record_property('native_original_and_restoration','ACTUAL_NATIVE_WRITER_AND_DISPATCH; ACTUAL_CHILD_CAPTURE_CUSTODY_CONSUMER_READY_RECEIPT_RELEASE_ACTIVATION; SYNTHETIC_B_PRODUCT_DRAIN_AND_AUTHORITY; NOT_R5')
    finally:
        retention_errors=[]
        try: retain_native_state('before-fixture-teardown')
        except BaseException as error:retention_errors.append(dict(stage='before',error=repr(error)))
        marker.write_text('COOPERATIVE_TEST_TEARDOWN_ONLY\n')
        reaper.join(timeout=min(5,max(0,predecessor_deadline-time.monotonic())))
        predecessor_out.close();predecessor_err.close()
        for process in owned:
            if process.poll() is None:
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate();process.wait();teardowns.append(dict(pid=process.pid,kind='NATIVE_FIXTURE_PARENT'))
        # Exact child PIDs come only from retained native post-fork observations.
        # A forced fixture teardown never supplies application cleanup evidence.
        for path in journal.glob('*.identified.json'):
            identity=json.loads(path.read_bytes())['child'];pid=identity['pid']
            try:observed=b._observe_process(pid)
            except (ValueError,OSError):continue
            if observed['kernel_birth']==identity['kernel_birth']:
                os.kill(pid,signal.SIGTERM);teardowns.append(dict(pid=pid,kind='IDENTIFIED_APPLICATION_CHILD_TEST_TEARDOWN'))
        try:retain_native_state('after-fixture-teardown')
        except BaseException as error:retention_errors.append(dict(stage='after',error=repr(error)))
        (evidence/'native-fixture-teardown.json').write_text(json.dumps(dict(forced_test_teardown=teardowns,
            application_cleanup_claimed=False,predecessor_reaper_joined=not reaper.is_alive(),
            predecessor_result=predecessor_result,evidence_retention_errors=retention_errors,
            owned_parent_final_exits=[dict(pid=p.pid,actual_exit=p.returncode) for p in owned],
            all_directly_owned_parents_waited=all(p.poll() is not None for p in owned)),indent=2)+'\n')
        assert not reaper.is_alive(),'predecessor reaper did not join within the existing fixture deadline'
        assert not retention_errors,retention_errors



_C03_F02_FRESH_ENTRY_DRIVER = r'''
import json,os,runpy,sys,time
from datetime import datetime,timedelta
from hashlib import sha256
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text());root=Path(data['repository'])
fd=int(sys.argv[2]);os.dup2(fd,197,inheritable=True)
if fd!=197:os.close(fd)
if not data.get('native'):os.environ.update(data['environment'])
os.environ['KRONOS_VALIDATION_CLOCK']='CLOCK_MONOTONIC'
deadline=int(os.environ['KRONOS_VALIDATION_DEADLINE_NS']) if data.get('native') else data['deadline_ns']
os.environ['KRONOS_VALIDATION_DEADLINE_NS']=str(deadline)
if not data.get('native'):
 while not Path(data['identified_path']).exists():
  if time.clock_gettime_ns(time.CLOCK_MONOTONIC)>=deadline:raise RuntimeError('FIXTURE_IDENTIFICATION_TIMEOUT')
  time.sleep(.001)
elif os.environ.get('KRONOS_LAUNCH_MODE')=='FAILED_SUCCESSOR_RESTORATION':
 data['claim_path']=json.loads(Path(os.environ['KRONOS_RESTORATION_RESERVATION_PATH']).read_bytes())['claim_path']
sys.argv=[str(root/'tools/kronos_browser.py'),'--no-browser']
from kronos.intraday.runtime_identity import StartupCapture
state=dict(process_id=os.getpid(),capture_instances=0,actual_consumer_calls=0,
    claim_writes=0,actual_capture_calls=0,actual_source_validator_calls=0,
    capture_reinjected=False,seams='DISPOSABLE_AUTHORITY_BINDING_PARENT_IMAGE_PATH_SIGNATURE_AND_PUBLICATION_GATE; REAL_ENTRY_CAPTURE_PINNING_CUSTODY_BUDGET_VALIDATORS_AND_R31_CONSUMER; STOP_BEFORE_PRODUCT_COMPOSITION')
references={}
utc={'now':datetime.fromisoformat(data['now'])}
real_init,real_finish=StartupCapture.__init__,StartupCapture.finish
def init(self,*args,**kwargs):
 real_init(self,*args,**kwargs);state['capture_instances']+=1;references['capture']=self
def finish(self):
 evidence=real_finish(self);references['evidence']=evidence
 state['actual_pinned_evidence']=evidence is self._finished and evidence.load_verification=='PINNED_STARTUP_IMPORTS' and evidence.source_state=='CLEAN_COMMIT'
 return evidence
StartupCapture.__init__,StartupCapture.finish=init,finish
class F02BoundaryComplete(BaseException):pass
class Clock(datetime):
 @classmethod
 def now(cls,tz=None):
  return datetime.now(tz) if data.get('native') else cls.fromisoformat(utc['now'].isoformat())
def configure_integration(g,b,pinned,custody,evidence):
 # Fixture imports refer to this actual __main__ module. No second entry import
 # or capture is performed; every call below reaches the original main once.
 module=sys.modules['__main__'];assert module.__dict__ is g
 sys.modules['tools.kronos_browser']=module
 import tools
 tools.kronos_browser=module
 sys.path.insert(0,str(root/'tests/unit'))
 import pytest
 from tests.unit.tools import test_kronos_browser as composition
 from kronos.browser import runtime_state
 from kronos.application.intraday_notifications import IntradayNotifications
 from kronos.application.swing_ux10 import SwingUx10NotificationService
 from kronos.application.swing_refresh_reminder import SwingK5RefreshReminderWorkflow
 patch=pytest.MonkeyPatch();events=[];state['events']=events
 # Test-only exact-byte review. This is explicitly not Instrument, Market or
 # CA approval and cannot commission the publication outside this child.
 from kronos.theta import composition as theta_composition
 from tests.unit.theta.test_operational_trial import synthetic_candidate_owner
 synthetic_owner=synthetic_candidate_owner()
 patch.setattr(theta_composition,'reviewed_owner',lambda:synthetic_owner)
 state['theta_review_seam']='SYNTHETIC-S3-01-TEST-REVIEW-NOT-OWNER-APPROVAL'
 # Only the disposable actual Theta workflow receives this explicit fixture clock.
 # Native/admission UTC, custody, validation budget and absolute deadline stay real.
 actual_theta_factory=g['compose_theta_sponsor_workflow']
 def theta_fixture(*args,**kwargs):
  from datetime import timezone
  from kronos.theta.workflow import ThetaWorkflow
  app=actual_theta_factory(*args,**kwargs)
  assert type(app.workflow) is ThetaWorkflow and not app.workflow.qualification_mode
  if data['selection'].endswith('current-authority-denial'):
   before=datetime.now(timezone.utc);observed=app.workflow.now()
   assert before<=observed<=datetime.now(timezone.utc)
   state['theta_fixture_clock']='ACTUAL_CURRENT_UTC_UNCHANGED'
   state['theta_actual_UTC_observed']=observed.isoformat()
  else:
   # The inherited October-26 clock predates the approved S3.01 publication.
   # Only this synthetic positive Theta fixture uses its accepted valid window.
   at=datetime(2026,10,28,8,30,tzinfo=timezone.utc)
   app.workflow.clock=lambda:at
   assert app.workflow.now()==at
   state['theta_fixture_clock']=at.isoformat()
  return app
 patch.setattr(module,'compose_theta_sponsor_workflow',theta_fixture)
 state['seams']=state['seams'].replace('STOP_BEFORE_PRODUCT_COMPOSITION','ACTUAL_COMPOSITION_READY_RELEASE_ACTIVATION; DISPOSABLE_STORES_AND_EXTERNAL_SERVICE_BOUNDARY')
 state.update(actual_main_calls=0,fixture_v2_substitution_blocked=False,
     successful_ready_release=False,same_owner_activation=True,
     integrated_fixture='REAL_COMPOSITION_WITH_RETAINED_PRE_MCX_STORES; SYNTHETIC_EXTERNAL_AUTHORITY_PARENT_IMAGE_SIGNATURE_PUBLICATION; PROVIDER_ACQUISITION_FORBIDDEN')
 actual_checker_factory=g['_compose_mcx_official_check']
 def isolated_official_checker(server):
  from tests.unit.application.test_mcx_official_check import FixtureTransport
  checker=actual_checker_factory(server);checker.transport=FixtureTransport();return checker
 patch.setattr(module,'_compose_mcx_official_check',isolated_official_checker)
 work=Path(data['work']) if data.get('native') else Path(data['claim_path']).parents[2]/'composition'
 actual_main,actual_create=g['main'],g['create_browser_server']
 actual_complete,actual_recheck=runtime_state.complete_startup,b.revalidate_restoration_context
 references['ready']=False;references['rechecks']=0
 if data.get('native') and data['selection'].startswith('native-T-'):
  from kronos.common.legacy_bootstrap import NativeStartupFacts
  actual_composed=NativeStartupFacts.composition_returned
  def composed(owner,*args,**kwargs):
   actual_composed(owner,*args,**kwargs);events.append('EXPLICIT_PRE_COMPLETION_FAULT')
   raise RuntimeError('EXPLICIT_DISPOSABLE_PRE_COMPLETION_FAULT')
  if data['selection'] in {'native-T-pre-completion-failure','native-T-current-authority-denial'}:patch.setattr(NativeStartupFacts,'composition_returned',composed)
  actual_consume=g['consume_startup_context']
  def original_consume(*args,**kwargs):
   def disposable_port_free():
    import socket
    with socket.socket() as probe:
     probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
     probe.bind(('127.0.0.1',data['port']))
    state['actual_v2_port_absence']=data['port'];return True
   result=actual_consume(*args,port_free=disposable_port_free,**kwargs)
   from kronos.common.maintenance import DrainStartupContext
   assert type(result) is DrainStartupContext
   state['actual_v2_consumer_calls']=state.get('actual_v2_consumer_calls',0)+1
   state['accepted_checkpoint']=result.notification_checkpoint();events.append('CONSUMED_V2')
   references['claim_raw']=Path(data['claim_path']).read_bytes()
   return result
  patch.setattr(module,'consume_startup_context',original_consume)
 def recheck(*args,**kwargs):
  references['rechecks']+=1
  assert kwargs['custody'] is custody and kwargs['attempt'].budget is references['budget']
  phase='POST_COMPLETION' if references['ready'] else ('RETAIN' if references['rechecks']==1 else 'PRE_COMPLETION')
  try:result=actual_recheck(*args,**kwargs)
  except BaseException:
   events.append(phase+'_DENIED');raise
  assert result.budget is references['budget'] and result.deadline_ns==deadline
  events.append(phase+'_RECHECK')
  if data['selection'] in {'integrated-pre-completion-failure','integrated-pre-completion-current-authority-denial'} and phase=='PRE_COMPLETION':
   events.append('EXPLICIT_PRE_COMPLETION_FAULT');raise RuntimeError('EXPLICIT_DISPOSABLE_PRE_COMPLETION_FAULT')
  return result
 patch.setattr(b,'revalidate_restoration_context',recheck)
 def create(*args,**kwargs):
  server=actual_create(*args,**kwargs);references['server']=server;return server
 patch.setattr(module,'create_browser_server',create)
 def committed():
  rows={}
  for label,base in [('historical',work/'historical'),('application-evidence',Path.home()/'Library/Application Support/KRONOS/evidence')]:
   for path in base.rglob('*.json'):
    rows[label+'/'+path.relative_to(base).as_posix()]=(path,path.read_bytes())
  return rows
 def completed(server,*args,**kwargs):
  if data['selection']=='native-T-ambiguous-completion':
   events.append('EXPLICIT_AMBIGUOUS_COMPLETION_FAULT');raise RuntimeError('EXPLICIT_AMBIGUOUS_COMPLETION_FAULT')
  result=actual_complete(server,*args,**kwargs)
  assert server is references['server']
  assert server.connection_governance.startup_state=='READY'
  checkpoint=server.intraday_notifications.checkpoint(certify_durable=True)
  assert checkpoint==data['checkpoint']==state['accepted_checkpoint']
  identity=server.connection_governance.process.runtime_identity
  receipt=server.connection_governance.store.root/'maintenance'/(identity+'-startup.json')
  references['receipt']=(receipt,receipt.read_bytes())
  Path(data['evidence'],'ready-receipt-before.json').write_bytes(receipt.read_bytes())
  references['committed']=committed()
  for name,(path,raw) in references['committed'].items():
   retained=Path(data['evidence'],'committed-before',name);retained.parent.mkdir(parents=True,exist_ok=True);retained.write_bytes(raw)
  references['owners']={'UX10':server.ux10_notifications,'WO13':server.intraday_notifications,'K5':server.refresh_reminders}
  state.update(ready_at_completion=server.connection_governance.startup_state,
      certified_checkpoint=checkpoint,committed_record_count=len(references['committed']),
      composition_owner_ids={name:id(owner) for name,owner in references['owners'].items()})
  references['ready']=True;events.append('READY_RECEIPT')
  if data['selection']=='native-T-ready-failure':
   events.append('EXPLICIT_AFTER_READY_FAULT');raise RuntimeError('EXPLICIT_AFTER_READY_FAULT')
  if data['selection']=='integrated-completion-expiry':utc['now']+=timedelta(minutes=6)
  return result
 for cls,name,label in (
     (g['_admission_bootstrap'].AdmissionCustody,'release_ready','READY_RELEASE'),
     (SwingUx10NotificationService,'activate_delivery','UX10'),
     (IntradayNotifications,'_activate_replay','WO13'),
     (SwingK5RefreshReminderWorkflow,'_activate_execution','K5')):
  real=getattr(cls,name)
  def activated(owner,*args,_real=real,_label=label,**kwargs):
   if _label=='READY_RELEASE':
    assert owner is custody and args[0] is references['server']
    assert events[-1]=='POST_COMPLETION_RECHECK'
   else:
    assert owner is references['owners'][_label]
    assert custody.released and not custody.cleanup_started
   result=_real(owner,*args,**kwargs)
   if _label=='READY_RELEASE':state['successful_ready_release']=True
   events.append(_label);return result
  patch.setattr(cls,name,activated)
 class CompositionPatch:
  def __getattr__(self,name):return getattr(patch,name)
  def setattr(self,*args,**kwargs):
   if len(args)==3 and args[0] is module and args[1]=='consume_startup_context':
    # Keep actual restoration authority. The older fixture's synthetic V2
    # context is never installed or used for this integrated restoration.
    state['fixture_v2_substitution_blocked']=True;return None
   if len(args)==2 and args[0]=='kronos.browser.runtime_state.complete_startup':
    return patch.setattr(args[0],completed)
   if len(args)==3 and args[1]=='serve_forever':
    original=args[2]
    def served(server,**options):
     from tests.unit.browser.test_runtime01 import _s303_observe_checker_termination
     state['checker_before_legacy_zero_owner_assertion']=_s303_observe_checker_termination(server,custody.budget)
     result=original(server,**options);events.append('SERVE');return result
    return patch.setattr(args[0],args[1],served)
   return patch.setattr(*args,**kwargs)
 def application_main(args=None):
  state['actual_main_calls']+=1
  try:
   result=actual_main(args);state['main_returned']=result;return result
  finally:
   cleanup=g['_LAST_STARTUP_CLEANUP'];server=cleanup.server
   import traceback
   if cleanup.original_failure is not None:
    Path(data['evidence'],'original-failure-traceback.log').write_text(''.join(traceback.format_exception(cleanup.original_failure)))
   receipt,raw=references.get('receipt',(None,None))
   state.update(original_failure=type(cleanup.original_failure).__name__,
       failure_message=str(cleanup.original_failure),failure_cleanup_started=custody.cleanup_started,
       application_cleanup_complete=custody.cleanup_complete,custody_released=custody.released,
       final_startup_state=None if server is None else server.connection_governance.startup_state,
       receipt_preserved=receipt is not None and receipt.is_file() and receipt.read_bytes()==raw,
       committed_records_preserved=all(path.is_file() and path.read_bytes()==before for path,before in references.get('committed',{}).values()),
       socket_closed_by_application=server is not None and server.socket.fileno()==-1,
       application_domain_closed=server is not None and server._domain_closed,
       application_outcomes_recorded_before_fixture_teardown=True,
       application_cleanup_errors=[name+':'+type(error).__name__ for name,error in cleanup.errors])
   if receipt is not None and receipt.is_file():Path(data['evidence'],'ready-receipt-after.json').write_bytes(receipt.read_bytes())
   Path(data['evidence'],'committed-records.json').write_text(json.dumps({name:{'sha256':sha256(raw).hexdigest(),'preserved':path.is_file() and path.read_bytes()==raw} for name,(path,raw) in references.get('committed',{}).items()},indent=2)+'\n')
   Path(data['evidence'],'application-before-fixture-teardown.json').write_text(json.dumps(state,indent=2)+'\n')
 def integrated_main(args=None):
  patch.setattr(module,'main',application_main)
  try:
   if data.get('native') and data['selection']=='native-R-healthy':
    from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
    from kronos.swing.v1.native_discovery import NativeDiscoveryEvidenceStore
    from kronos.swing.v1.relative_context import RelativeContextEvidenceStore
    from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
    from kronos.browser.server import KronosBrowserServer
    for name,owner in [('MtfFactEvidenceStore',MtfFactEvidenceStore(work/'historical/mtf')),
        ('NativeDiscoveryEvidenceStore',NativeDiscoveryEvidenceStore(work/'historical/native')),
        ('RelativeContextEvidenceStore',RelativeContextEvidenceStore(work/'historical/relative')),
        ('LocalSwingRunProvenanceStore',LocalSwingRunProvenanceStore(work/'historical/provenance'))]:
     patch.setattr(module,name,lambda *_a,_owner=owner,**_k:_owner)
    patch.setattr(module,'_build_provider',lambda **_k:pytest.fail('native startup acquired Provider data'))
    patch.setattr(runtime_state,'complete_startup',completed)
    def serve(server,**_kwargs):
     assert server.connection_governance.startup_state=='READY'
     server.timeout=.05;events.append('ACTUAL_HTTP_SERVICE')
     while not Path(data['teardown_marker']).exists():server.handle_request()
     events.append('COOPERATIVE_TEST_TEARDOWN')
    patch.setattr(KronosBrowserServer,'serve_forever',serve)
    return application_main(['--port',str(data['port']),'--no-browser'])
   composition.test_canonical_startup_restores_pre_mcx_continuity_without_rewriting_it(work,CompositionPatch(),True,None)
   return state['main_returned']
  finally:
   Path(data['evidence'],'composition-fixture-teardown.json').write_text(json.dumps(dict(
       defensive_server_close_after_application_observation=True,application_cleanup_claimed=False),indent=2)+'\n')
   patch.undo()
 g['main']=integrated_main
def trace(frame,event,arg):
 name=frame.f_code.co_name;g=frame.f_globals
 if event=='call' and name=='adopt_from_launcher' and g.get('__name__')=='_kronos_admission_bootstrap':
  anchor=Path(data['anchor']);st=anchor.stat()
  assert sha256(g['PERSISTENT_ANCHOR_BINDING']).hexdigest()=='85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891'
  state['actual_preparatory_pin_verified_before_fixture_binding']=True
  g['PERSISTENT_ANCHOR_BINDING']=None
  g['APPROVED_BINDING']=g['AnchorBinding'](anchor,st.st_dev,st.st_ino,os.getuid())
  g['PRODUCTION_ANCHOR']=anchor;g['CANONICAL_PARENT']=data['image']
  state['actual_kernel_parent_image']=g['_parent_image'](os.getppid())
  def image(pid):
   assert pid==os.getppid()
   if data.get('native'):
    observed=g['_parent_image'](pid);assert observed==data['image'];return observed
   return data['image']
  g['AdmissionCustody'].__init__.__kwdefaults__['parent_image']=image
 if event=='call' and name=='_canonical_entry':
  sys.settrace(None);references['entry']=g
  custody=g['_ADMISSION'];references['custody']=custody;references['budget']=custody.budget
  capture=references['capture'];evidence=references['evidence']
  state['original_capture_retained']=g.get('_startup_capture') is capture
  state['actual_bootstrap_adoption']=type(custody) is g['_admission_bootstrap'].AdmissionCustody
  state['original_deadline_preserved']=custody.budget.deadline_ns==deadline
  actual=tuple(sorted((name,Path(row[0]).relative_to(root).as_posix(),sha256(row[1]).hexdigest()) for name,row in capture._sources.items()))
  expected=tuple((r['module'],r['path'],r['sha256']) for r in data['expected_capture'])
  assert actual==expected
  assert evidence is g['_STARTUP_EVIDENCE'] and evidence.source_snapshot_digest==data['expected_pinned_digest']
  state['loaded_module_subset']=0<len(evidence.loaded_modules)<len(actual) and all((name,digest) in tuple((n,d) for n,p,d in actual) for name,digest in evidence.loaded_modules)
  from kronos.common import legacy_bootstrap as b,release_admission as pinned
  real_facts_init=b.NativeStartupFacts.__init__
  def facts_init(self,*args,**kwargs):
   # Bind only after the entry's real module-class reconciliation. Importing
   # R3.1 before that boundary would pin the wrong AdmissionCustody class.
   from kronos.common import failed_successor_restore as s304_restore
   s304_restore.INITIALIZATION_DISPOSITION=(Path(data['anchor'])/'failed-successor-restore-v1/s304-fixture-disposition.json').read_bytes()
   state['initialization_authority_seam']='SYNTHETIC DISPOSABLE EXACT DISPOSITION; PRODUCTION DEFAULT REMAINS NULL'
   return real_facts_init(self,*args,**kwargs)
  b.NativeStartupFacts.__init__=facts_init
  import tools.runtime_source_gate as gate
  assert sha256(Path(pinned.__file__).read_bytes()).hexdigest()==sha256((root/'src/kronos/common/release_admission.py').read_bytes()).hexdigest()
  pinned.PERSISTENT_ANCHOR_BINDING=g['_admission_bootstrap'].PERSISTENT_ANCHOR_BINDING
  pinned.CANONICAL_PARENT=data['image']
  if not data.get('native'):
   g['datetime']=Clock;b.datetime=Clock
  if not data.get('native'):
   os.environ['KRONOS_RESTORATION_CHILD_KERNEL_BIRTH']=b._observe_process(os.getpid())['kernel_birth']
   os.environ['KRONOS_RESTORATION_PARENT_KERNEL_BIRTH']=b._observe_process(os.getppid())['kernel_birth']
  def qualify(repository,observed):
   assert repository==root and observed is evidence and state['actual_pinned_evidence']
  gate.qualify_startup=qualify
  b._verify_bundle_signature=lambda *_:None
  real_capture,real_source=b.capture_restoration_child,b._validate_source_manifest
  def capture_child(*args,**kwargs):
   state['actual_capture_calls']+=1
   if state['actual_capture_calls']==1:record_consumer()
   assert kwargs['captured_sources']==actual and kwargs['loaded_modules']==evidence.loaded_modules
   assert kwargs['custody'] is custody and kwargs['custody'].budget is references['budget']
   result=real_capture(*args,**kwargs)
   assert result.captured_sources==actual and result.loaded_modules==evidence.loaded_modules
   state['same_capture_mapping_and_custody']=True
   return result
  def source(*args,**kwargs):
   state['actual_source_validator_calls']+=1
   assert args[2] is custody and kwargs['captured_sources']==actual
   return real_source(*args,**kwargs)
  b.capture_restoration_child,b._validate_source_manifest=capture_child,source
  def record_consumer():
   from kronos.common import failed_successor_restore as restore
   real_consume,real_write=restore.consume_failed_successor_restore,restore._write_claim
   def consume(*args,**kwargs):
    state['actual_consumer_calls']+=1
    assert kwargs['custody'] is custody and type(custody) is restore.AdmissionCustody
    assert custody.budget is references['budget'] and type(custody.budget) is pinned.ValidationBudget
    state['bootstrap_pinned_classes_reconciled']=restore.AdmissionCustody is g['_admission_bootstrap'].AdmissionCustody and pinned.ValidationBudget is g['_admission_bootstrap'].ValidationBudget
    result=real_consume(*args,**kwargs)
    if data.get('integrated'):
     state['events'].append('CONSUMED');state['accepted_checkpoint']=result.notification_checkpoint()
     references['claim_raw']=Path(data['claim_path']).read_bytes()
    return result
   def write(*args,**kwargs):
    state['claim_writes']+=1
    assert kwargs['custody'] is custody
    return real_write(*args,**kwargs)
   restore.consume_failed_successor_restore,restore._write_claim=consume,write
  if data.get('integrated'):configure_integration(g,b,pinned,custody,evidence)
  else:
   def stop(*args,**kwargs):raise F02BoundaryComplete()
   g['ConnectionGovernance']=stop
 return trace
sys.settrace(trace)
try:
 runpy.run_path(str(root/'tools/kronos_browser.py'),run_name='__main__')
except SystemExit as error:state['entry_exit']=error.code
finally:
 sys.settrace(None)
 g=references['entry'];custody=references['custody'];cleanup=g['_LAST_STARTUP_CLEANUP']
 if not data.get('integrated'):
  state.update(original_failure=type(cleanup.original_failure).__name__,failure_message=str(cleanup.original_failure),
      application_cleanup_complete=custody.cleanup_started and custody.cleanup_complete,custody_released=custody.released)
 state.update(same_original_budget=custody.budget is references['budget'],
     original_deadline_preserved=custody.budget.deadline_ns==deadline,
     claim_exists=Path(data['claim_path']).exists(),parent_reference_teardown_not_yet_run=True,
     claim_unchanged_after_consumption=Path(data['claim_path']).is_file() and Path(data['claim_path']).read_bytes()==references.get('claim_raw'))
 Path(data['evidence'],'observations.json').write_text(json.dumps(state,indent=2)+'\n')
if data.get('native'):raise SystemExit(state.get('entry_exit',79))
'''


@pytest.mark.parametrize('fault', ('valid', 'completion-expiry', 'completion-source-change'))
def test_c03_actual_entry_final_boundary(tmp_path, monkeypatch, record_property, fault):
    """Actual library entry, R3.1 consumer, READY/receipt and deferred owners."""
    import os
    from datetime import datetime, timedelta
    from dataclasses import replace
    from hashlib import sha256
    from tests.unit.common.test_release_admission import fork_result
    from tests.unit.common import test_legacy_bootstrap as setup
    from tests.unit.common import test_failed_successor_restore as fixture
    from tests.unit.tools import test_kronos_browser as composition
    from kronos.common import legacy_bootstrap as bootstrap
    from kronos.common import release_admission as admission
    from tools import kronos_browser as entry
    evidence = (Path(__file__).resolve().parents[4] / 'qualification' /
                'c03-entry-evidence' / tmp_path.parents[1].name / tmp_path.name)
    evidence.mkdir(parents=True)
    def child():
        composition.isolated_composition_authority.__wrapped__(monkeypatch)
        control = setup._c02_dispatch_case(tmp_path, monkeypatch)
        case = control['case']
        # Coherent certified EMPTY checkpoint for this real empty notification
        # store, before any consumption; historical original-parent facts stay.
        settled = json.loads(case.settled_path.read_bytes())
        settled['notification_checkpoint'] = dict(state='EMPTY', pending_count=0,
                                                   sha256=sha256(b'').hexdigest())
        raw = fixture._put(case.settled_path, settled)
        settled_ref = fixture._ref(case.settled_path, settled['settled_state_id'], raw)
        failure = json.loads(case.failure_path.read_bytes()); failure['settled_state'] = settled_ref
        raw = fixture._put(case.failure_path, failure)
        failure_ref = fixture._ref(case.failure_path, failure['failure_cleanup_id'], raw)
        permit = json.loads(case.permit_path.read_bytes())
        permit.update(settled_state=settled_ref, failure_cleanup=failure_ref)
        fixture._put(case.permit_path, permit)
        reservation = json.loads(case.reservation_path.read_bytes()); reservation['settled_state'] = settled_ref
        fixture._put(case.reservation_path, reservation)
        setup._c02_refresh(case, control['env'], source_manifest=control['source_manifest'],
            artifact_manifest=control['artifact_manifest'], target_values=control['target'],
            parent_birth=control['env']['KRONOS_RESTORATION_PARENT_KERNEL_BIRTH'])
        clock = {'now': case.now}
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromisoformat(clock['now'].isoformat())
        monkeypatch.setattr(entry, 'datetime', Clock)
        monkeypatch.setattr(bootstrap, 'datetime', Clock)
        monkeypatch.setattr(bootstrap, '_verify_bundle_signature', lambda *_: None)
        monkeypatch.setattr(entry, '_ADMISSION', case.custody)
        monkeypatch.setattr(entry, '_admission_bootstrap', admission)
        monkeypatch.setattr(entry, '_pinned_release_admission', admission)
        monkeypatch.setattr(entry, '_ADMISSION_PAYLOAD', Path(admission.__file__).read_bytes())
        monkeypatch.setattr(entry, '__file__', str(control['repository'] / 'tools/kronos_browser.py'))
        monkeypatch.setattr(entry, '_startup_capture', control['startup_capture'], raising=False)
        from kronos.intraday.runtime_identity import _startup
        control['loaded_modules'] = ((control['captured_sources'][0][0],
                                      control['captured_sources'][0][2]),)
        startup_evidence = _startup(
            process_id=os.getpid(), process_nonce='c' * 32,
            python_runtime=entry._STARTUP_EVIDENCE.python_runtime,
            branch='maintenance/release-b-swing-ux',
            startup_boundary_at=case.now, source_revision=control['target']['revision'],
            source_state='CLEAN_COMMIT', source_snapshot_digest=control['pinned_digest'],
            loaded_modules=control['loaded_modules'], load_verification='PINNED_STARTUP_IMPORTS')
        runtime_identity = sha256(startup_evidence.evidence_identity.encode()).hexdigest()
        case.child = replace(case.child, runtime_identity=runtime_identity)
        monkeypatch.setattr(entry, '_STARTUP_EVIDENCE', startup_evidence)
        for name, value in control['env'].items(): monkeypatch.setenv(name, value)
        events, observed = [], {'fault': fault}
        original_main = entry.main
        IntradayNotifications = composition.IntradayNotifications
        from kronos.application.swing_ux10 import SwingUx10NotificationService
        from kronos.application.swing_refresh_reminder import SwingK5RefreshReminderWorkflow
        for cls, name, label in (
            (admission.AdmissionCustody, 'release_ready', 'READY_RELEASE'),
            (SwingUx10NotificationService, 'activate_delivery', 'UX10'),
            (IntradayNotifications, '_activate_replay', 'WO13'),
            (SwingK5RefreshReminderWorkflow, '_activate_execution', 'K5')):
            real = getattr(cls, name)
            def recorded(owner, *args, _real=real, _label=label, **kwargs):
                result = _real(owner, *args, **kwargs)
                events.append(_label)
                return result
            monkeypatch.setattr(cls, name, recorded)
        def consume(*args, **kwargs):
            kwargs['restoration_clock'] = Clock.now
            return bootstrap.consume_startup_context(*args, **kwargs)
        def completed(server, *args, **kwargs):
            result = actual_complete_startup(server, *args, **kwargs)
            receipt = server.connection_governance.store.root / 'maintenance' / (runtime_identity + '-startup.json')
            observed['ready_at_completion'] = server.connection_governance.startup_state
            observed['receipt_before_denial'] = receipt.read_text()
            observed['selectors_present_at_completion'] = 'KRONOS_RESTORATION_PERMIT_PATH' in os.environ
            (evidence / 'ready-receipt-before.json').write_bytes(receipt.read_bytes())
            # Legitimate composition output must survive final revalidation.
            (case.root / 'legitimate-reconciliation.json').write_bytes(b'{"startup_reconciled":true}\n')
            if fault == 'completion-expiry': clock['now'] += timedelta(minutes=6)
            if fault == 'completion-source-change':
                control['source_manifest'].write_bytes(control['source_manifest'].read_bytes() + b' ')
            return result
        class CompositionPatch:
            def __getattr__(self, name): return getattr(monkeypatch, name)
            def setattr(self, *args, **kwargs):
                if len(args) == 3 and args[0] is entry and args[1] == 'consume_startup_context':
                    return monkeypatch.setattr(entry, 'consume_startup_context', consume)
                if len(args) == 2 and args[0] == 'kronos.browser.runtime_state.complete_startup':
                    return monkeypatch.setattr(args[0], completed)
                return monkeypatch.setattr(*args, **kwargs)
        def main(args):
            try:
                result = original_main(args)
                observed['main_returned'] = result
                return result
            except BaseException as error:
                observed['error'] = type(error).__name__ + ':' + str(error)
                raise
            finally:
                cleanup = entry._LAST_STARTUP_CLEANUP
                server = cleanup.server
                observed.update(events=events, custody_released=case.custody.released,
                    cleanup_started=case.custody.cleanup_started,
                    cleanup_complete=case.custody.cleanup_complete,
                    original_failure=type(cleanup.original_failure).__name__,
                    claim_exists=case.claim_path.exists(),
                    parent_reference_teardown_not_yet_run=True)
                if server is not None:
                    observed['final_startup_state'] = server.connection_governance.startup_state
                    receipt = server.connection_governance.store.root / 'maintenance' / (runtime_identity + '-startup.json')
                    observed['receipt_preserved'] = receipt.is_file() and receipt.read_text() == observed.get('receipt_before_denial')
                    observed['socket_closed_by_application'] = server.socket.fileno() == -1
                observed['legitimate_reconciliation_preserved'] = (case.root / 'legitimate-reconciliation.json').is_file()
                (evidence / 'application-observations.json').write_text(json.dumps(observed, indent=2) + '\n')
                if case.claim_path.exists(): (evidence / 'spent-claim.json').write_bytes(case.claim_path.read_bytes())
        original_checker_factory = entry._compose_mcx_official_check
        def isolated_checker(server):
            from tests.unit.application.test_mcx_official_check import FixtureTransport
            checker = original_checker_factory(server)
            checker.transport = FixtureTransport()  # Synthetic HTTP; actual owner and worker.
            return checker
        monkeypatch.setattr(entry, '_compose_mcx_official_check', isolated_checker)
        original_patch_setattr = CompositionPatch.setattr
        def coordinated_setattr(self, *args, **kwargs):
            if len(args) == 3 and args[0] is KronosBrowserServer and args[1] == 'serve_forever':
                original_serve = args[2]
                def observed_serve(server, **options):
                    budget = case.custody.budget
                    original_deadline = budget.deadline_ns
                    observation = _s303_observe_checker_termination(server, budget)
                    assert case.custody.budget is budget and budget.deadline_ns == original_deadline
                    budget.check()
                    (evidence / 'checker-before-legacy-assertion.json').write_text(json.dumps(dict(
                        worker_observation=observation, same_original_budget=True,
                        original_deadline_ns=original_deadline, final_deadline_ns=budget.deadline_ns,
                        worker_completion_is_not_application_cleanup=True,
                        worker_completion_is_not_fixture_teardown=True,
                        transport='SYNTHETIC_HTTP_FIXTURE; NO LIVE MCX ACCESS'), indent=2) + '\n')
                    budget.check()
                    return original_serve(server, **options)
                return monkeypatch.setattr(args[0], args[1], observed_serve)
            return original_patch_setattr(self, *args, **kwargs)
        CompositionPatch.setattr = coordinated_setattr
        monkeypatch.setattr(entry, 'main', main)
        try:
            if fault == 'valid':
                composition.test_canonical_startup_restores_pre_mcx_continuity_without_rewriting_it(
                    tmp_path, CompositionPatch(), True, None)
                assert events == ['READY_RELEASE', 'UX10', 'WO13', 'K5']
                assert not case.custody.cleanup_started
            else:
                with pytest.raises(bootstrap.BootstrapError, match='RESTORATION'):
                    composition.test_canonical_startup_restores_pre_mcx_continuity_without_rewriting_it(
                        tmp_path, CompositionPatch(), True, None)
                assert events == []
                assert case.custody.cleanup_started and case.custody.cleanup_complete and case.custody.released
            assert observed['ready_at_completion'] == observed['final_startup_state'] == 'READY'
            assert observed['receipt_preserved'] and observed['claim_exists']
            assert observed['legitimate_reconciliation_preserved']
            return observed
        finally:
            case.close()
            (evidence / 'test-teardown.json').write_text(json.dumps({
                'fixture_custody_closed': case.custody.released,
                'application_cleanup_claimed_from_teardown': False,
                'claim_deleted_or_repaired': False,
                'seams': 'LIBRARY_MODE_PARENT_IMAGE_PATH_SIGNATURE_SOURCE_AUTHORITY_AND_CLOCK; REAL_ENTRY_CONSUMER_READY_RECEIPT_AND_OWNERS'}, indent=2) + '\n')
    result = fork_result(child)
    (evidence / 'fork-result.json').write_text(json.dumps(result, indent=2) + '\n')
    record_property('fork_result', json.dumps(result, sort_keys=True))
    assert 'error' not in result, result


def test_slice22_parent_failure_blocks_before_source_or_consumption(monkeypatch):
    from tools import kronos_browser
    from kronos.common.release_admission import ValidationBudget, monotonic_ns
    deadline_ns = monotonic_ns() + 120_000_000_000
    budget = ValidationBudget(deadline_ns)
    def fail():raise ValueError('PARENT_LOST')
    owner = SimpleNamespace(check=fail, budget=budget)
    monkeypatch.setattr(kronos_browser,'_ADMISSION',owner)
    monkeypatch.setattr('tools.runtime_source_gate.qualify_startup',
                        lambda *_:pytest.fail('source helper ran after parent failure'))
    with pytest.raises(ValueError,match='PARENT_LOST'):kronos_browser.main(['--no-browser'])
    assert owner.budget is budget and budget.deadline_ns == deadline_ns


def test_slice22_missing_binding_denies_before_capture_or_helpers(tmp_path):
    import subprocess,sys
    from pathlib import Path
    source_root=Path(__file__).resolve().parents[3]
    root=tmp_path/'missing-binding';(root/'tools').mkdir(parents=True)
    admission_path=root/'src/kronos/common/release_admission.py'
    admission_path.parent.mkdir(parents=True)
    admission_path.write_text((source_root/'src/kronos/common/release_admission.py').read_text()
                              + '\nAPPROVED_BINDING = None\n')
    entry=root/'tools/kronos_browser.py'
    entry.write_bytes((source_root/'tools/kronos_browser.py').read_bytes())
    code='''import os,runpy,subprocess,sys
# Supply an inherited descriptor so the actual bootstrap reaches its explicit
# missing-binding guard. No admission lock or production path is opened.
fd=os.open(os.devnull,os.O_RDONLY)
os.dup2(fd,197,inheritable=True)
if fd!=197:os.close(fd)
calls=[]
def forbidden_helper(*args,**kwargs):
 calls.append(True)
 raise AssertionError('helper execution')
subprocess.Popen=forbidden_helper
try:runpy.run_path(sys.argv[1],run_name='__main__')
except SystemExit as error:
 assert error.code==79
 assert calls==[]
 print('UNAPPROVED_BINDING_DENIED_BEFORE_CAPTURE')
else:raise SystemExit(9)
'''
    result=subprocess.run([sys.executable,'-B','-c',code,str(entry)],capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='UNAPPROVED_BINDING_DENIED_BEFORE_CAPTURE'


def test_slice22_bootstrap_exact_bytes_preserve_original_capture_predicates(tmp_path):
    import subprocess,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    code='''import sys,types
from pathlib import Path
from kronos.intraday.runtime_identity import StartupCapture
root=Path(sys.argv[1]);path=root/'src/kronos/common/release_admission.py';raw=path.read_bytes()
m=types.ModuleType('_fixture_admission_bootstrap');sys.modules[m.__name__]=m
exec(compile(raw,str(path),'exec'),m.__dict__)
with StartupCapture(root) as capture:
 assert capture._sources['kronos.common.release_admission'][1]==raw
 from kronos.common import release_admission
 proof=capture.finish()
 assert proof.load_verification=='PINNED_STARTUP_IMPORTS',proof
 assert any(name=='kronos.common.release_admission' for name,digest in proof.loaded_modules)
 print('BOOTSTRAP_AND_PINNED_SOURCE_AGREE')
'''
    result=subprocess.run([sys.executable,'-B','-c',code,str(root)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='BOOTSTRAP_AND_PINNED_SOURCE_AGREE'


@pytest.mark.parametrize('stage,cleanup_complete',[(None,True),('housekeeping',False),('ready',True)])
def test_slice22_actual_failed_composition_retains_or_closes_custody(
        tmp_path,monkeypatch,stage,cleanup_complete,record_property):
    import os
    from tests.unit.common.test_release_admission import held,fork_result,available
    from kronos.common import release_admission as admission
    from tests.unit.tools import test_kronos_browser as original
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700);st=anchor.stat()
    binding=admission.AnchorBinding(anchor,st.st_dev,st.st_ino,os.getuid());fd=held(binding)
    deadline_ns=admission.monotonic_ns()+120_000_000_000
    budget=admission.ValidationBudget(deadline_ns)
    evidence=(Path(__file__).resolve().parents[4]/'qualification'/'cleanup-case-evidence'
              /tmp_path.parents[1].name/tmp_path.name)
    evidence.mkdir(parents=True)
    observed=None
    try:
        def child():
            from tools import kronos_browser
            owner=admission.AdmissionCustody(fd,binding,os.getppid(),
                parent_image=lambda _pid:admission.CANONICAL_PARENT,budget=budget)
            original.isolated_composition_authority.__wrapped__(monkeypatch)
            monkeypatch.setattr(kronos_browser,'_ADMISSION',owner)
            # Library-mode fixture binding only: this actual module constructed
            # owner. It does not prove bootstrap/pinned reconciliation or full
            # restoration startup, and the canonical replay guard stays real.
            monkeypatch.setattr(kronos_browser, '_admission_bootstrap', admission)
            actual_checker_factory=kronos_browser._compose_mcx_official_check
            def isolated_checker(server):
                from tests.unit.application.test_mcx_official_check import FixtureTransport
                checker=actual_checker_factory(server)
                checker.transport=FixtureTransport()  # Synthetic HTTP; actual owner and approved authority.
                return checker
            monkeypatch.setattr(kronos_browser,'_compose_mcx_official_check',isolated_checker)
            class ObservedLegacyPatch:
                def __getattr__(self,name):return getattr(monkeypatch,name)
                def setattr(self,*args,**kwargs):
                    if len(args)==3 and args[1]=='serve_forever':
                        original_serve=args[2]
                        def observed_serve(server,**options):
                            observation=_s303_observe_checker_termination(server,budget)
                            (evidence/'checker-before-legacy-assertion.json').write_text(json.dumps(observation,indent=2)+'\n')
                            return original_serve(server,**options)
                        return monkeypatch.setattr(args[0],args[1],observed_serve)
                    return monkeypatch.setattr(*args,**kwargs)
            try:
                original.test_canonical_startup_restores_pre_mcx_continuity_without_rewriting_it(
                    tmp_path,ObservedLegacyPatch(),True,stage)
            finally:
                (evidence/'application-observations.json').write_text(json.dumps(dict(
                    stage=stage,custody_released=owner.released,
                    cleanup_started=owner.cleanup_started,cleanup_complete=owner.cleanup_complete,
                    original_deadline_ns=deadline_ns,final_deadline_ns=owner.budget.deadline_ns,
                    same_budget=owner.budget is budget,
                    library_mode_bootstrap_binding=kronos_browser._admission_bootstrap is admission,
                    parent_image='SYNTHETIC_CANONICAL_PARENT_FIXTURE',
                    observation_precedes_fork_helper_exit=True),indent=2)+'\n')
            assert owner.budget is budget and budget.deadline_ns==deadline_ns
            assert owner.released is cleanup_complete
            if stage is None:
                assert owner.released
                assert not owner.cleanup_started
                assert not owner.cleanup_complete
            if not cleanup_complete:
                os.fstat(fd)
                assert owner.cleanup_started
            return owner.released
        observed=fork_result(child)
        (evidence/'fork-result.json').write_text(json.dumps(observed,indent=2)+'\n')
        record_property('fork_helper_result',json.dumps(observed,sort_keys=True))
        record_property('original_deadline_ns',deadline_ns)
        assert observed=={'result':cleanup_complete}
        assert not available(binding)
    finally:
        os.close(fd)
        (evidence/'test-teardown.json').write_text(json.dumps(dict(
            parent_descriptor_closed=True,anchor_available_after_parent_close=available(binding),
            fork_result_helper_waited_for_direct_child=observed is not None,
            child_wrapper_exit=0 if observed is not None else None,
            application_cleanup_claimed_from_test_teardown=False),indent=2)+'\n')


@pytest.mark.parametrize('completed,expected',[(False,79),(True,78)])
def test_slice22_canonical_exit_acknowledges_only_completed_cleanup(monkeypatch,completed,expected):
    from tools import kronos_browser
    def failed():raise RuntimeError('retained isolated failure')
    monkeypatch.setattr(kronos_browser,'main',failed)
    monkeypatch.setattr(kronos_browser,'_ADMISSION',SimpleNamespace(cleanup_complete=completed,released=True))
    monkeypatch.setattr(kronos_browser,'_CUSTODY_ADOPTED',True)
    monkeypatch.setattr(kronos_browser,'_admission_bootstrap',SimpleNamespace(validation_unresolved=lambda:False,report_validation=lambda *args:None))
    monkeypatch.setattr(kronos_browser,'_pinned_release_admission',None)
    assert kronos_browser._canonical_entry()==expected


def test_slice23_entry_capture_adapter_preserves_arguments_and_raw_bytes(monkeypatch,tmp_path):
    from tools import kronos_browser
    calls=[]
    def output(args,**kwargs):calls.append((args,kwargs));return b'exact\x00bytes\n'
    budget=object()
    monkeypatch.setattr(kronos_browser,'_ADMISSION',SimpleNamespace(check=lambda:None,budget=budget))
    monkeypatch.setattr(kronos_browser,'_admission_bootstrap',SimpleNamespace(validation_output=output),raising=False)
    capture=object.__new__(kronos_browser._EntryStartupCapture);capture._root=tmp_path
    assert capture._git('ls-tree','-z','HEAD')==b'exact\x00bytes\n'
    args,kwargs=calls[0]
    assert args==['git','ls-tree','-z','HEAD'] and kwargs['cwd']==tmp_path
    assert kwargs['ceiling']==10 and kwargs['budget'] is budget


def test_slice23_unresolved_helper_cannot_issue_cleanup_ack(monkeypatch):
    from tools import kronos_browser
    budget=SimpleNamespace(deadline_ns=123)
    monkeypatch.setattr(kronos_browser,'_ADMISSION',SimpleNamespace(cleanup_complete=True,released=True,budget=budget))
    monkeypatch.setattr(kronos_browser,'_CUSTODY_ADOPTED',True)
    monkeypatch.setattr(kronos_browser,'_admission_bootstrap',SimpleNamespace(validation_unresolved=lambda:True),raising=False)
    def failure():raise ValueError('isolated helper failure')
    monkeypatch.setattr(kronos_browser,'main',failure)
    assert kronos_browser._canonical_entry()==79


def test_slice23_expired_startup_cannot_consume_or_compose(monkeypatch):
    from tools import kronos_browser
    from kronos.common.release_admission import ValidationBudget
    budget=ValidationBudget(1)
    monkeypatch.setattr(kronos_browser,'_ADMISSION',SimpleNamespace(check=budget.check,budget=budget))
    monkeypatch.setattr(kronos_browser,'consume_startup_context',
        lambda *_args,**_kwargs:pytest.fail('consumption after expiry'))
    monkeypatch.setattr(kronos_browser,'create_intraday_runtime',
        lambda *_args,**_kwargs:pytest.fail('composition after expiry'))
    with pytest.raises(ValueError,match='DEADLINE'):kronos_browser.main(['--no-browser'])


def test_slice23_ready_releases_attempt_stderr_without_waiting_for_runtime_exit():
    import subprocess,sys
    code='''import time
from tools import kronos_browser as b
b._ADMISSION_PAYLOAD=b'fixture'
b._release_startup_output()
print('SERVICE_STILL_ALIVE',flush=True)
time.sleep(.4)
'''
    process=subprocess.Popen([sys.executable,'-B','-c',code],stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True)
    try:
        assert process.stdout.readline()=='SERVICE_STILL_ALIVE\n'
        assert process.stderr.read()==''
        assert process.poll() is None
        assert process.wait(timeout=2)==0
    finally:
        if process.poll() is None:process.terminate()
        process.wait(timeout=2)


# F01: exercise the actual canonical file from adoption through pre-main failure.
def _early_entry_fixture(tmp_path, fault):
    from pathlib import Path
    import os, subprocess, sys
    root=tmp_path/'entry';(root/'tools').mkdir(parents=True)
    for name in ['kronos','kronos/common','kronos/intraday']:
        directory=root/'src'/name;directory.mkdir(parents=True,exist_ok=True)
        (directory/'__init__.py').write_text('')
    source_root=Path(__file__).resolve().parents[3]
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700);st=anchor.stat()
    marker=tmp_path/'forbidden-main'
    entry=(source_root/'tools/kronos_browser.py').read_text()
    import re
    entry=re.sub(r'(?m)^( *)def main\(argv: Sequence\[str\] \| None = None\) -> int:\n',
        lambda m:m.group(0)+m.group(1)+'    Path('+repr(str(marker))+').write_text("FORBIDDEN_MAIN")\n'+m.group(1)+'    raise AssertionError("FORBIDDEN_MAIN")\n',entry,count=1)
    (root/'tools/kronos_browser.py').write_text(entry)
    (root/'src/kronos/intraday/runtime_identity.py').write_bytes(
        (source_root/'src/kronos/intraday/runtime_identity.py').read_bytes())
    admission=(source_root/'src/kronos/common/release_admission.py').read_text()
    from tests.unit.tools.test_place_release_pair import assert_actual_preparatory_source
    assert_actual_preparatory_source()
    admission+='\nfrom hashlib import sha256\nassert sha256(PERSISTENT_ANCHOR_BINDING).hexdigest()==\"85ea2fa04da20f40377b242d71db96762020e77042a7b4923c331c6f82ab7891\"\nPERSISTENT_ANCHOR_BINDING=None\n'
    admission+='\nimport signal\nsignal.signal(signal.SIGALRM, lambda *_: os._exit(91))\nsignal.alarm(5)\n'
    admission+='APPROVED_BINDING = AnchorBinding(Path('+repr(str(anchor))+'),'+str(st.st_dev)+','+str(st.st_ino)+',os.getuid())\n'
    admission+='PRODUCTION_ANCHOR = Path('+repr(str(anchor))+')\n'
    # The unchanged isolation bootstrap strips incoming KRONOS_* values. This
    # private fixture supplies only its disposable monotonic context afterward.
    admission+='os.environ["KRONOS_VALIDATION_CLOCK"]="CLOCK_MONOTONIC"\nos.environ["KRONOS_VALIDATION_DEADLINE_NS"]=str(monotonic_ns()+1000000000)\n'
    admission+='CANONICAL_PARENT = str(Path(sys.executable).resolve())\n_actual_adopt = adopt_from_launcher\n'
    if fault=='capture-timeout':
        admission+='''_actual_output = validation_output
def validation_output(arguments, **kwargs):
    if arguments[0]=='git':arguments=[sys.executable,'-B','-c','import time;time.sleep(6)']
    return _actual_output(arguments,**kwargs)
'''
    if fault=='partial-pinned':admission+='report_validation = None\n'
    admission+='def adopt_from_launcher():\n'
    if fault=='adoption-denial':admission+='    raise ValueError("FIXTURE_ADOPTION_DENIED")\n'
    else:
        admission+='    owner=_actual_adopt()\n    print("ADOPTED",flush=True)\n'
        if fault=='parent-loss':
            admission+='    parent=os.getppid()\n    while os.getppid()==parent:time.sleep(.005)\n'
        if fault=='partial-pinned':
            admission+='    def fail():raise ValueError("FIXTURE_PRE_CAPTURE_FAILURE")\n    owner.check=fail\n'
        admission+='    return owner\n'
    (root/'src/kronos/common/release_admission.py').write_text(admission)
    env=dict(os.environ,HOME=str(tmp_path),PYTHONPATH=str(root/'src')+':'+str(root),
        GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull)
    for args in [('init','-q'),('config','user.email','fixture@example.invalid'),('config','user.name','Fixture'),('add','.'),('commit','-qm','isolated early-entry fixture')]:
        subprocess.run(['/usr/bin/git',*args],cwd=root,env=env,check=True,capture_output=True)
    driver='''import os,sys,fcntl,signal,time
from pathlib import Path
path=Path(sys.argv[1]);root=Path(sys.argv[2]);fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
child=os.fork()
if child==0:
 os.dup2(fd,197,inheritable=True)
 if fd!=197:os.close(fd)
 os.environ['KRONOS_VALIDATION_CLOCK']='CLOCK_MONOTONIC'
 os.environ['KRONOS_VALIDATION_DEADLINE_NS']=str(time.clock_gettime_ns(time.CLOCK_MONOTONIC)+1000000000)
 os.chdir(root)
 os.execv(sys.executable,[sys.executable,'-B',str(root/'tools/kronos_browser.py')])
print('BACKEND_PID '+str(child),flush=True)
reaped=False
for command in sys.stdin:
 if command.strip()=='DIE':os._exit(0)
 if command.strip()=='WAIT':
  _,status=os.waitpid(child,0);reaped=True
  print('NATURAL_EXIT '+str(os.waitstatus_to_exitcode(status)),flush=True)
 if command.strip()=='DROP':
  if fd>=0:os.close(fd);fd=-1
  print('REFERENCE_DROPPED',flush=True)
 if command.strip()=='STOP':
  if not reaped:
   try:os.kill(child,signal.SIGTERM)
   except ProcessLookupError:pass
   _,status=os.waitpid(child,0)
   print('CHILD_EXIT '+str(os.waitstatus_to_exitcode(status)),flush=True)
  break
if fd>=0:os.close(fd)
'''
    process=subprocess.Popen([sys.executable,'-B','-c',driver,str(anchor),str(root)],
        env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    return process,anchor,marker


def _fixture_line(stream, buffers, timeout=3):
    import os,select,time
    fd=stream.fileno();pending=buffers.setdefault(fd,bytearray());end=time.monotonic()+timeout
    while b'\n' not in pending:
        remaining=end-time.monotonic()
        if remaining<=0 or not select.select([fd],[],[],remaining)[0]:raise AssertionError('fixture line deadline')
        raw=os.read(fd,65536)
        if not raw:raise AssertionError('fixture EOF before required outcome: '+repr(bytes(pending)))
        pending.extend(raw)
    line,_,rest=pending.partition(b'\n');buffers[fd]=bytearray(rest)
    return line.decode()


@pytest.mark.parametrize('fault',['capture-timeout','parent-loss','partial-pinned','pinned-import','adoption-denial'])
def test_slice23_f01_actual_early_entry_retains_and_reports(tmp_path,fault):
    import os,json,time
    from kronos.common.release_admission import AnchorBinding,open_anchor
    import fcntl
    process,anchor,marker=_early_entry_fixture(tmp_path,fault);buffers={};parent_dead=False
    try:
        assert _fixture_line(process.stdout,buffers).startswith('BACKEND_PID ')
        if fault!='adoption-denial':
            try:assert _fixture_line(process.stdout,buffers)=='ADOPTED'
            except AssertionError:
                import select
                detail=os.read(process.stderr.fileno(),65536).decode() if select.select([process.stderr],[],[],0)[0] else 'no stderr'
                raise AssertionError('fixture adoption failed: '+detail)
        if fault=='parent-loss':
            process.stdin.write(b'DIE\n');process.stdin.flush();process.wait(timeout=2);parent_dead=True
        # Earlier helper diagnostics may precede the canonical failure decision.
        records=[];end=time.monotonic()+3
        while True:
            line=_fixture_line(process.stderr,buffers,max(.01,end-time.monotonic()))
            try:record=json.loads(line)
            except ValueError:continue
            records.append(record)
            if record.get('phase','').startswith('CANONICAL_'):break
        assert record['cleanup']=='CLEANUP_UNRESOLVED'
        assert not marker.exists()
        if fault=='adoption-denial':
            process.stdin.write(b'WAIT\n');process.stdin.flush()
            assert _fixture_line(process.stdout,buffers)=='NATURAL_EXIT 79'
        if not parent_dead:
            process.stdin.write(b'DROP\n');process.stdin.flush()
            assert _fixture_line(process.stdout,buffers)=='REFERENCE_DROPPED'
        st=anchor.stat();probe=open_anchor(AnchorBinding(anchor,st.st_dev,st.st_ino,os.getuid()))
        try:
            if fault=='adoption-denial':fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
            else:
                with pytest.raises(BlockingIOError):fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(probe)
    finally:
        if process.poll() is None:
            process.stdin.write(b'STOP\n');process.stdin.flush();process.wait(timeout=3)
        if parent_dead:
            # Only this disposable orphan has a fixture-only five-second alarm.
            # Wait for that bound rather than signal an unrelated/reused PID.
            end=time.monotonic()+6
            while time.monotonic()<end:
                st=anchor.stat();probe=open_anchor(AnchorBinding(anchor,st.st_dev,st.st_ino,os.getuid()))
                try:
                    try:fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                    except BlockingIOError:time.sleep(.02)
                finally:os.close(probe)
            else:raise AssertionError('disposable early-entry child did not end')


@pytest.mark.parametrize('partial',['absent','noncallable','raises','unadopted'])
def test_slice23_f01_partial_failure_state_denies_without_secondary_exception(monkeypatch,capfd,partial):
    from tools import kronos_browser as b
    def broken(*args):raise RuntimeError('fixture partial state')
    monkeypatch.setattr(b,'_ADMISSION',None)
    monkeypatch.setattr(b,'_CUSTODY_ADOPTED',False)
    monkeypatch.setattr(b,'_pinned_release_admission',None)
    module=None
    if partial=='noncallable':module=SimpleNamespace(report_validation=None,validation_unresolved=None)
    if partial=='raises':module=SimpleNamespace(report_validation=broken,validation_unresolved=broken)
    if partial=='unadopted':
        monkeypatch.setattr(b,'_ADMISSION',SimpleNamespace(released=True,cleanup_complete=True))
        module=SimpleNamespace(report_validation=None,validation_unresolved=lambda:False)
    monkeypatch.setattr(b,'_admission_bootstrap',module)
    assert b._handle_canonical_failure()==79
    import json
    record=json.loads(capfd.readouterr().err.strip().splitlines()[-1])
    assert record['cleanup']=='CLEANUP_UNRESOLVED'
    assert record['observed_result']=='STARTUP_FAILURE'


# CA R1: actual isolated canonical-entry regression and retained failure evidence.
from pathlib import Path
import fcntl
import json
import os
import select
import signal
import socket
import sys
import threading
import time
import traceback

import pytest




def _r4_exec_fresh_library_fixture(case, anchor, descriptor, output, mode):
    """Exec the already-forked child: same PID/OFD, fresh original capture.

    Source is an exact disposable Git-backed copy. Native selection/head and
    package metadata are explicit synthetic fixture authority, not orchestration.
    The existing mandatory kernel/Python isolation bootstrap remains installed.
    """
    import hashlib
    import shutil
    import subprocess
    source = Path(__file__).resolve().parents[3]
    repository = anchor.parent / 'r4-fixture-source'
    deadline = time.clock_gettime_ns(time.CLOCK_MONOTONIC) + 120_000_000_000
    shutil.copytree(source, repository, ignore=shutil.ignore_patterns(
        '.git', '.pytest_cache', '__pycache__', '*.pyc', '*.pyo'))
    def git(*args):
        return subprocess.run(['/usr/bin/git', *args], cwd=repository,
            check=True, capture_output=True).stdout
    git('init', '-q', '-b', 'r4-library-fixture')
    git('remote', 'add', 'origin', 'https://example.invalid/kronos-r4-fixture.git')
    git('add', '--force', '--all')
    git('-c', 'user.name=KRONOS Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-q', '-m', 'exact R4 disposable fixture source')
    rows = []
    for row in git('ls-files', '-s', '-z').split(b'\0'):
        if row:
            metadata, name = row.split(b'\t', 1)
            path = name.decode(); raw = (repository / path).read_bytes()
            assert raw == (source / path).read_bytes()
            rows.append(dict(path=path, mode=metadata.split()[0].decode(),
                             sha256=hashlib.sha256(raw).hexdigest()))
    revision = git('rev-parse', 'HEAD').decode().strip()
    assert not git('status', '--porcelain=v1', '--untracked-files=all')
    payload = dict(case=case, anchor=str(anchor), descriptor=descriptor,
        output=str(output), mode=mode, repository=str(repository),
        deadline_ns=deadline, original_child_pid=os.getpid(), parent_pid=os.getppid(),
        revision=revision, tracked_files=rows,
        seams='EXACT_DISPOSABLE_GIT_SOURCE; SYNTHETIC_NATIVE_SELECTION_HEAD_AND_PACKAGE_AUTHORITY; ACTUAL_LIBRARY_CAPTURE_CUSTODY_NATIVE_FACTS_AND_CLEANUP; NO_NATIVE_ORCHESTRATION')
    selected = output.with_suffix('.fresh-fixture-input.json')
    selected.write_text(json.dumps(payload, indent=2) + '\n')
    driver = anchor.parent / 'r4-fresh-library-driver.py'
    driver.write_text("""import json,os,sys,traceback
from pathlib import Path
payload=json.loads(Path(sys.argv[1]).read_text())
try:
 root=Path(payload['repository'])
 sys.path[:0]=[str(root/'src'),str(root)]
 assert os.getpid()==payload['original_child_pid'] and os.getppid()==payload['parent_pid']
 os.environ['KRONOS_VALIDATION_CLOCK']='CLOCK_MONOTONIC'
 os.environ['KRONOS_VALIDATION_DEADLINE_NS']=str(payload['deadline_ns'])
 from tools import kronos_browser as entry
 assert Path(entry.__file__).resolve()==root/'tools/kronos_browser.py'
 assert entry._startup_capture._finished is entry._STARTUP_EVIDENCE
 assert entry._STARTUP_EVIDENCE.process_id==os.getpid()
 assert entry._STARTUP_EVIDENCE.source_revision==payload['revision']
 assert entry._STARTUP_EVIDENCE.source_state=='CLEAN_COMMIT'
 assert entry._STARTUP_EVIDENCE.load_verification=='PINNED_STARTUP_IMPORTS'
 from tests.unit.browser import test_runtime01 as fixture
 mode=payload['mode'];setup=None
 if mode['kind']=='f01':setup=fixture._r2_f01_configure
 elif mode['kind']=='s303':
  def setup(*args):
   args[4]['S303-mode']=mode['mode']
   return fixture._s303_configure(*args)
 elif mode['kind'] in {'f02','ux10'}:
  def setup(*args):
   args[4]['K5-mode' if mode['kind']=='f02' else 'UX10-mode']=mode['mode']
   return (fixture._r2_f02_configure if mode['kind']=='f02' else fixture._r2_ux10_configure)(*args)
 fixture._r1_child(payload['case'],Path(payload['anchor']),payload['descriptor'],
     Path(payload['output']),r2_setup=setup,fresh_fixture=payload)
 raise RuntimeError('Fixture child unexpectedly returned')
except BaseException:
 Path(payload['output']).with_suffix('.setup-error.txt').write_text(traceback.format_exc())
 os._exit(97)
""")
    os.set_inheritable(descriptor, True)
    # exec preserves PID, parent and shared open-file description. No second
    # child/reaper, admission acquisition, or renewed deadline is introduced.
    os.execve(sys.executable, [sys.executable, '-B', str(driver), str(selected)], dict(os.environ))


def _r4_library_native_selection(entry, admission, owner, anchor, output, fresh):
    """Supply coherent fixture records to the actual NativeStartupFacts checks."""
    from hashlib import sha256
    import shutil
    from kronos.common import legacy_bootstrap as bootstrap
    from tests.unit.common.test_legacy_bootstrap import _c02_bundle_manifest
    from tests.unit.common.test_failed_successor_restore import _put, _ref
    from datetime import datetime, UTC
    repository = Path(fresh['repository'])
    capture, evidence = entry._startup_capture, entry._STARTUP_EVIDENCE
    assert capture._finished is evidence and evidence.process_id == os.getpid()
    assert evidence.source_revision == fresh['revision']
    assert evidence.source_state == 'CLEAN_COMMIT'
    assert evidence.load_verification == 'PINNED_STARTUP_IMPORTS'
    assert owner.budget.deadline_ns == fresh['deadline_ns']
    bundle = anchor.parent / 'R4-fixture.app'
    shutil.copytree(repository / 'tools/macos/KRONOS.app', bundle)
    files = fresh['tracked_files']; file_map = {r['path']: r['sha256'] for r in files}
    capture_rows = [dict(module=name, path=Path(item[0]).relative_to(repository).as_posix(),
                        sha256=sha256(item[1]).hexdigest())
                    for name, item in sorted(capture._sources.items())]
    source_doc = dict(schema='KRONOS_RESTORATION_SOURCE_MANIFEST_V1',
        origin_url='https://example.invalid/kronos-r4-fixture.git',
        source_ref='refs/heads/r4-library-fixture', revision=evidence.source_revision,
        git_tree_oid=capture._git('rev-parse', 'HEAD^{tree}').decode().strip(),
        files=files, capture=capture_rows)
    source_path = anchor.parent / 'r4-fixture-source-manifest.json'
    source_raw = _put(source_path, source_doc)
    rows = _c02_bundle_manifest(bundle)
    binary = sha256((bundle / 'Contents/MacOS/KRONOS').read_bytes()).hexdigest()
    artifact = dict(schema='KRONOS_LAUNCHER_PACKAGE_V1',
        source_revision=evidence.source_revision, source_state='CLEAN_COMMIT',
        source_launcher_sha256=file_map['tools/macos/kronos_launcher.c'],
        previous_tracked_binary_sha256=file_map['tools/macos/KRONOS.app/Contents/MacOS/KRONOS'],
        built_binary_sha256=binary, signed_binary_sha256=binary,
        procedure_sha256=file_map['tools/macos/package_launcher.py'],
        compiler_flags=['-Wall','-Wextra','-Werror','-O2','-mmacosx-version-min=13.0'],
        compiler='R4 library fixture: copied tracked bundle; no build/signing; synthetic package authority metadata',
        signing='AD_HOC; timestamp=none; no entitlements; resources sealed',
        strict_verification='PASS', isolated_execution='PASS',
        bundle_identity=sha256(bootstrap._canonical(rows)).hexdigest(), bundle_manifest=rows,
        archive_sha256=sha256(b'R4 library fixture; no archive publication').hexdigest())
    artifact_path = anchor.parent / 'r4-fixture-artifact-manifest.json'
    artifact_raw = bootstrap._canonical(artifact) + b'\n';artifact_path.write_bytes(artifact_raw);artifact_path.chmod(0o600)
    target = dict(revision=evidence.source_revision,
        tree_sha256=sha256(bootstrap._canonical(files)).hexdigest(),
        source_manifest_sha256=sha256(source_raw).hexdigest(),
        artifact_manifest_sha256=sha256(artifact_raw).hexdigest(),
        pinned_capture_sha256=evidence.source_snapshot_digest,
        origin_url=source_doc['origin_url'], source_ref=source_doc['source_ref'])
    installation = bootstrap._native_installation(str(repository), str(bundle), str(anchor))
    observed = bootstrap._observe_process(os.getppid())
    parent = dict(pid=os.getppid(), kernel_birth=observed['kernel_birth'],
        runtime_identity=sha256(b'R4 synthetic selected parent authority').hexdigest(),
        revision=evidence.source_revision)
    journal = anchor / 'failed-successor-restore-v1';journal.mkdir(mode=0o700)
    now = datetime.now(UTC)
    original = 'R4-library-fixture-original'
    activation = bootstrap._native_phase(original, 'NATIVE_ACTIVATED', original=original,
        installation=installation,parent=parent,selected=None,predecessor=None,
        previous=None,details={},now=now)
    activation_raw = _put(journal / (original + '.json'), activation)
    from kronos.common.failed_successor_restore import HEAD_SCHEMA
    head = dict(schema=HEAD_SCHEMA, installation_identity=installation['identity'],
        sequence=1,state='NATIVE_ACTIVATED',incident_id=None,active_reservation_id=original,
        active_reservation_sha256=sha256(activation_raw).hexdigest(),previous_head_sha256='0'*64,
        recorded_at=now.isoformat())
    first_raw = _put(journal / 'head-1.json', head)
    _put(journal/'admission-head.json',head)
    from tests.unit.common import test_failed_successor_restore as s304_fixture
    s304_fixture._s304_admit_fixture(journal,installation)
    first_raw=(journal/'head-1.json').read_bytes()
    activation_raw=(journal/(original+'.json')).read_bytes()
    identifier = 'R4-library-fixture-child'
    phase = bootstrap._native_phase(identifier,'CHILD_START_RESERVED',original=original,
        installation=installation,parent=parent,selected=None,predecessor=None,
        previous=_ref(journal/(original+'.json'),original,activation_raw),details=dict(target=target),now=now)
    raw = _put(journal/(identifier+'.json'),phase)
    selected = _ref(journal/(identifier+'.json'),identifier,raw)
    head.update(sequence=2,state='CHILD_START_RESERVED',active_reservation_id=identifier,
        active_reservation_sha256=selected['sha256'],previous_head_sha256=sha256(first_raw).hexdigest())
    _put(journal/'head-2.json',head);head_raw=_put(journal/'admission-head.json',head)
    _put(journal/(identifier+'.identified.json'),dict(schema='KRONOS_NATIVE_CHILD_IDENTIFIED_V1',
        selected=selected,parent=parent,child=dict(pid=os.getpid(),kernel_birth=bootstrap._observe_process(os.getpid())['kernel_birth'])))
    for suffix,key in [('PATH','path'),('BYTES','bytes'),('SHA256','sha256'),('ID','identity')]:
        os.environ['KRONOS_NATIVE_ATTEMPT_'+suffix]=str(selected[key])
    os.environ['KRONOS_NATIVE_HEAD_SHA256']=sha256(head_raw).hexdigest()
    output.with_suffix('.capture-provenance.json').write_text(json.dumps(dict(
        original_capture_retained=True,original_evidence_retained=True,process_id=os.getpid(),
        capture_identity=id(capture),evidence_identity=evidence.evidence_identity,
        source_revision=evidence.source_revision,source_state=evidence.source_state,
        load_verification=evidence.load_verification,snapshot_digest=evidence.source_snapshot_digest,
        loaded_modules=evidence.loaded_modules,deadline_ns=owner.budget.deadline_ns,
        native_records='SYNTHETIC_LIBRARY_COMPONENT_AUTHORITY; ACTUAL_NATIVE_FACTS_VALIDATOR',
        selected=selected,head_sha256=sha256(head_raw).hexdigest()),indent=2)+'\n')
    return journal


def _r1_child(case, anchor, descriptor, output, *, r2_setup=None,
              r4_mode=None, fresh_fixture=None):
    if fresh_fixture is None:
        try:
            _r4_exec_fresh_library_fixture(case, anchor, descriptor, output,
                r4_mode or dict(kind='none'))
        except BaseException:
            output.with_suffix('.setup-error.txt').write_text(traceback.format_exc())
            os._exit(97)
    events = []
    resources = {}
    patch = pytest.MonkeyPatch()

    def event(name, **data):
        events.append(dict(name=name, **data))

    def wrapped_method(cls, name, key):
        original = getattr(cls, name)
        def observed(self, *args, **kwargs):
            event(key + '.attempted')
            try:
                result = original(self, *args, **kwargs)
            except BaseException as error:
                event(key + '.failed', error=type(error).__name__, message=str(error))
                raise
            event(key + '.completed')
            return result
        patch.setattr(cls, name, observed)

    try:
        # Library entry imports run the candidate's real source capture/imports.
        # Source-publication/signature authority is an explicit fixture seam below;
        # no Git transport or production canonical launcher is invoked.
        from tools import kronos_browser as entry
        from kronos.browser import server as browser
        from kronos.common import release_admission as admission
        from kronos.application.swing_bulk_import import SwingBulkImportOwner
        from kronos.browser.restart_control import BrowserBackendRestartControl
        from kronos.application.swing_research_control import SwingResearchControl

        # Actual kernel parent path and inherited flock, not a mocked custody check.
        from tests.unit.tools.test_place_release_pair import assert_actual_preparatory_source
        assert_actual_preparatory_source()
        patch.setattr(admission,'PERSISTENT_ANCHOR_BINDING',None)
        patch.setattr(admission, 'CANONICAL_PARENT', admission._parent_image(os.getppid()))
        st = anchor.stat()
        binding = admission.AnchorBinding(anchor, st.st_dev, st.st_ino, os.getuid())
        patch.setattr(admission, 'PRODUCTION_ANCHOR', anchor)
        patch.setattr(admission, 'APPROVED_BINDING', binding)
        patch.setattr(admission, 'ADMISSION_DESCRIPTOR', descriptor)
        os.environ['KRONOS_VALIDATION_CLOCK'] = 'CLOCK_MONOTONIC'
        assert int(os.environ['KRONOS_VALIDATION_DEADLINE_NS']) == fresh_fixture['deadline_ns']
        owner = admission.adopt_from_launcher()
        patch.setattr(entry, '_ADMISSION', owner)
        patch.setattr(entry, '_CUSTODY_ADOPTED', True)
        patch.setattr(entry, '_admission_bootstrap', admission)
        patch.setattr(entry, '_pinned_release_admission', admission)
        patch.setattr(entry, '_ADMISSION_PAYLOAD', Path(admission.__file__).read_bytes())
        original_checker = entry._compose_mcx_official_check
        def isolated_checker(server):
            from tests.unit.application.test_mcx_official_check import FixtureTransport
            result = original_checker(server)
            result.transport = FixtureTransport()  # Explicit synthetic HTTP; actual owner/authority.
            return result
        patch.setattr(entry, '_compose_mcx_official_check', isolated_checker)
        assert owner.budget.deadline_ns == fresh_fixture['deadline_ns']
        native_journal = _r4_library_native_selection(entry, admission, owner,
            anchor, output, fresh_fixture)
        event('custody.actual_adoption', fd=descriptor, parent=os.getppid(), inheritable=os.get_inheritable(descriptor))

        # This proof tests resource ownership/cleanup, not publication admission.
        # Only external/canonical authority is simulated. Cleanup proof remains real.
        def fixture_source_authority(*_args):
            event('fixture.source_authority_not_under_test')
            return entry._STARTUP_EVIDENCE.source_revision
        patch.setattr('tools.runtime_source_gate.qualify_startup', fixture_source_authority)
        def forbidden_provider(**_kwargs):
            event('FORBIDDEN_PROVIDER_CALL')
            raise AssertionError('R1 forbids Provider acquisition')
        patch.setattr(entry, '_build_provider', forbidden_provider)
        def forbidden_browser(*_args, **_kwargs):
            event('FORBIDDEN_BROWSER_OPEN')
            raise AssertionError('R1 forbids browser operations')
        patch.setattr(entry.webbrowser, 'open_new_tab', forbidden_browser)

        original_runtime = entry.create_intraday_runtime
        def observed_runtime(*args, **kwargs):
            if case == 'C01-absent-shadow':
                kwargs['wo08_shadow_factory'] = lambda: None
            result = original_runtime(*args, **kwargs)
            resources['intraday_runtime'] = result
            event('intraday_runtime.created')
            return result
        patch.setattr(entry, 'create_intraday_runtime', observed_runtime)
        original_own = browser._StartupCleanup.own
        def interrupted_registration(self, name, *args, **kwargs):
            boundary = ('lifecycle' if case == 'C01-before-registration' else
                        'wo17' if case == 'C01-mid-registration' else None)
            if name == boundary:
                assert 'intraday_runtime' in resources
                event('C01.interrupted_registration', slot=name,
                      real_returned_type=type(resources['intraday_runtime']).__name__)
                raise RuntimeError('C01_INTERRUPTED_RETURNED_COMPOSITION')
            return original_own(self, name, *args, **kwargs)
        patch.setattr(browser._StartupCleanup, 'own', interrupted_registration)
        original_provider_init = entry.SharedAuthenticatedProviderRuntime.__init__
        def observed_provider(self, *args, **kwargs):
            original_provider_init(self, *args, **kwargs)
            resources['provider'] = self
            event('provider_owner.created')
        patch.setattr(entry.SharedAuthenticatedProviderRuntime, '__init__', observed_provider)
        wrapped_method(entry.SharedAuthenticatedProviderRuntime, 'end_kronos_session', 'provider.end_session')

        original_control_create = BrowserBackendRestartControl.create.__func__
        def observed_control(cls, *args, **kwargs):
            result = original_control_create(cls, *args, **kwargs)
            resources['control'] = result
            event('control.created', path=str(result.path), exists=result.path.exists())
            return result
        patch.setattr(BrowserBackendRestartControl, 'create', classmethod(observed_control))
        wrapped_method(BrowserBackendRestartControl, 'remove', 'control.remove')

        original_server_init = browser.KronosBrowserServer.__init__
        def observed_server_init(self, *args, **kwargs):
            resources['server'] = self
            event('server.constructor_entered')
            try:
                original_server_init(self, *args, **kwargs)
            except BaseException:
                event('server.constructor_failed')
                raise
            event('server.constructor_returned')
        patch.setattr(browser.KronosBrowserServer, '__init__', observed_server_init)
        wrapped_method(browser.KronosBrowserServer, 'server_close', 'server.close')
        wrapped_method(browser.KronosBrowserServer, '_close_domain_owners', 'domain.close')
        wrapped_method(SwingBulkImportOwner, 'close', 'bulk.close')
        wrapped_method(SwingResearchControl, 'close', 'research.close')
        from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
        from kronos.application.intraday_wo17_monitoring import IntradayWo17MonitoringCoordinator
        wrapped_method(IntradayLifecycleApplication, 'shutdown', 'lifecycle.shutdown')
        wrapped_method(IntradayWo17MonitoringCoordinator, 'shutdown', 'wo17.shutdown')
        wrapped_method(entry.SwingOpportunitiesApplication, 'close', 'application.close')
        if case == 'cleanup-failure':
            original_close = SwingBulkImportOwner.close
            def fail_close(self, **kwargs):
                event('bulk.close.injected_failure')
                raise RuntimeError('R1_INJECTED_CLEANUP_FAILURE')
            patch.setattr(SwingBulkImportOwner, 'close', fail_close)


        original_proof = browser.KronosBrowserServer._maintenance_final_owner_proof
        def observed_proof(self):
            event('final_owner_proof.attempted')
            value = original_proof(self)
            event('final_owner_proof.completed', actual_result=value,
                  absent_server_attributes=[name for name in ('housekeeping', 'intraday_lifecycle',
                      'intraday_wo17_monitoring', 'intraday_notifications', 'intraday_experimental_watches')
                      if not hasattr(self, name)])
            if case == 'full-proof-denial':
                event('fault.full_owner_proof_denied', original_actual_result=value)
                return False
            return value
        patch.setattr(browser.KronosBrowserServer, '_maintenance_final_owner_proof', observed_proof)

        original_bulk_start = SwingBulkImportOwner.start
        def observed_bulk_start(self):
            resources['bulk'] = self
            original_bulk_start(self)
            event('bulk.worker_started', alive=self._thread.is_alive())
            if case == 'counted-owner':
                resources['unreleased_ticket'] = resources['server'].maintenance_admission.admit('NOTIFICATION')
                assert resources['unreleased_ticket'] is not None
                raise RuntimeError('R1_INJECTED_COUNTED_OWNER')
            if case in {'constructor', 'cleanup-failure'}:
                event('fault.injected', location='SwingBulkImportOwner.start: after real start, before server constructor returns')
                raise RuntimeError('R1_INJECTED_AFTER_OWNED_WORKER_BEFORE_SERVER_RETURN')
        patch.setattr(SwingBulkImportOwner, 'start', observed_bulk_start)

        original_create = entry.create_browser_server
        def observed_create(*args, **kwargs):
            result = original_create(*args, **kwargs)
            if case in {'post-server','C01-absent-shadow'} or case.startswith('C02-ux10-'):
                event('fault.injected', location='after actual server return, before next admission check or housekeeping entry')
                raise RuntimeError('R1_INJECTED_AFTER_SERVER_BEFORE_READY')
            return result
        patch.setattr(entry, 'create_browser_server', observed_create)
        original_housekeeping = entry._compose_housekeeping
        def observed_housekeeping(*args, **kwargs):
            event('housekeeping.factory_entered')
            if case == 'none-return':
                event('fault.injected', location='entered factory returned None without an owner')
                return None
            if case == 'unreturned':
                event('fault.injected', location='entered housekeeping factory without a returned or accounted owner')
                raise RuntimeError('R1_INJECTED_ENTERED_UNRETURNED')
            result = original_housekeeping(*args, **kwargs)
            resources['housekeeping'] = result
            return result
        patch.setattr(entry, '_compose_housekeeping', observed_housekeeping)

        def retained_inventory():
            import hashlib
            home = Path.home() / 'Library/Application Support/KRONOS'
            roots = (home / 'evidence', anchor.parent / 'synthetic-publication')
            return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                    for root in roots if root.exists() for p in root.rglob('*') if p.is_file()}
        protected_before = None
        def freeze_before():
            nonlocal protected_before
            if protected_before is None:
                protected_before = retained_inventory()
        original_start_for_freeze = SwingBulkImportOwner.start
        def freeze_then_start(self):
            freeze_before()
            return original_start_for_freeze(self)
        patch.setattr(SwingBulkImportOwner, 'start', freeze_then_start)
        def snapshot():
            # Preserve actual immutable native child facts before any fixture
            # teardown. Missing application outcomes never become cleanup proof.
            import shutil
            retained = output.parent / 'native-facts';retained.mkdir(exist_ok=True)
            for path in native_journal.iterdir():
                if path.is_file():
                    target=retained/path.name
                    if target.exists():assert target.read_bytes()==path.read_bytes()
                    else:shutil.copy2(path,target)
            assert entry._startup_capture._finished is entry._STARTUP_EVIDENCE
            assert entry._STARTUP_EVIDENCE.process_id == os.getpid()
            assert owner.budget.deadline_ns == fresh_fixture['deadline_ns']
            server = resources.get('server')
            bulk = resources.get('bulk')
            control = resources.get('control')
            created = {key: type(value).__name__ for key, value in resources.items()}
            result = dict(case=case, events=list(events), resources_created=created,
                injected_error=dict(type=type(sys.exc_info()[1]).__name__, message=str(sys.exc_info()[1])),
                exception_traceback=''.join(traceback.format_exception(*sys.exc_info())),
                custody=dict(released=owner.released, cleanup_started=owner.cleanup_started,
                    cleanup_complete=owner.cleanup_complete, fd_open=not owner.released,
                    fd_inheritable=None if owner.released else os.get_inheritable(descriptor),
                    parent_pid=owner.parent),
                cleanup_ledger=entry._LAST_STARTUP_CLEANUP.snapshot(),
                cleanup_failures=[dict(owner=name,error=type(error).__name__,message=str(error))
                    for name,error in entry._LAST_STARTUP_CLEANUP.errors],
                original_failure=None if entry._LAST_STARTUP_CLEANUP.original_failure is None else
                    str(entry._LAST_STARTUP_CLEANUP.original_failure),
                validation_unresolved=admission.validation_unresolved(),
                directly_owned_validation_helpers=[dict(pid=p.pid, returncode=p.poll()) for p in admission._OWNED_VALIDATION_HELPERS.values()],
                threads=[dict(name=t.name, alive=t.is_alive(), daemon=t.daemon) for t in threading.enumerate()],
                control=None if control is None else dict(path=str(control.path), exists=control.path.exists()),
                housekeeping=entry._LAST_STARTUP_CLEANUP.snapshot()['housekeeping']['state'],
                source_authority='SIMULATED_FIXTURE_ONLY; source capture/import and actual main/cleanup used; production admission not qualified',
                actual_entry='tools.kronos_browser._canonical_entry -> actual main -> actual cleanup/owner predicates',
                protected_before=protected_before, protected_after=retained_inventory())
            if bulk is not None:
                result['bulk'] = dict(work_status=bulk.work_status(), stop_requested=bulk._stop.is_set(),
                    thread_alive=bulk._thread is not None and bulk._thread.is_alive(),
                    completion_holds_server=getattr(bulk._completion, '__self__', None) is server)
            if server is not None:
                checker=getattr(server,'mcx_official_check',None)
                if checker is not None:
                    result['checker_application_status']=checker.status_document()
                    records={}
                    for path in checker.store_root.rglob('*') if checker.store_root.exists() else ():
                        if path.is_file():
                            raw=path.read_bytes()
                            target=output.parent/'checker-records'/path.relative_to(checker.store_root)
                            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                            records[str(path)]=__import__('hashlib').sha256(raw).hexdigest()
                    result['checker_retained_records']=records
                sock = getattr(server, 'socket', None)
                result['server'] = dict(constructor_returned=any(e['name']=='server.constructor_returned' for e in events),
                    socket_fd=None if sock is None else sock.fileno(), address=getattr(server, 'server_address', None),
                    domain_closed=getattr(server, '_domain_closed', None),
                    research_status=server.swing_research_control.work_status(),
                    maintenance=server.maintenance_admission.snapshot(),
                    bound_owner_presence={name:hasattr(server,name) for name in ('housekeeping','intraday_lifecycle','intraday_wo17_monitoring','intraday_notifications')})
                if sock is not None and sock.fileno() >= 0:
                    try:
                        result['server']['socket_accepting'] = bool(sock.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN))
                    except OSError as error:
                        # Darwin may reject this optional read. The controller's
                        # real disposable-loopback connection remains the check.
                        result['server']['socket_accepting_observer_error'] = dict(errno=error.errno, message=str(error))
            runtime = resources.get('intraday_runtime')
            if runtime is not None:
                result['outer_intraday_owners'] = {}
                for name in ['lifecycle_application','wo17_monitoring','wo08_shadow']:
                    value=getattr(runtime,name,None)
                    row={'created':value is not None,'type':None if value is None else type(value).__name__}
                    for method in ['work_status','snapshot']:
                        reader=getattr(value,method,None)
                        if callable(reader):
                            try:row[method]=reader()
                            except BaseException as error:row[method+'_error']=type(error).__name__
                    result['outer_intraday_owners'][name]=row
            if 'R2-snapshot' in resources:
                result['r2'] = resources['R2-snapshot']()
            return result

        # Valid synthetic retained publication, using existing owning fixture
        # constructors/validators. Never bypass the activation check or an owner
        # cleanup predicate; only replace the fixture store roots supplied to main.
        from kronos.swing import run_publication as publication_module
        from tests.unit.swing.v1.test_opportunity_continuity import scenario
        from tests.unit.swing.test_run_publication import make_checkpoint
        facts, bindings = scenario.__wrapped__()
        layout = anchor.parent / 'synthetic-publication'
        coordinator = publication_module.SwingRunPublication
        with pytest.MonkeyPatch.context() as fixture_layout:
            fixture_layout.setattr(publication_module, 'SwingRunPublication',
                lambda _root, **kwargs: coordinator(layout / 'run-publication-v1', **kwargs))
            publication, _, _, _ = make_checkpoint(layout, facts, bindings)
        for name, store in [('MtfFactEvidenceStore', publication.mtf_store),
                            ('NativeDiscoveryEvidenceStore', publication.native_store),
                            ('RelativeContextEvidenceStore', publication.relative_store),
                            ('LocalSwingRunProvenanceStore', publication.provenance_store)]:
            patch.setattr(entry, name, lambda *_args, _store=store, **_kwargs: _store)
        event('fixture.synthetic_retained_publication', root=str(publication.root),
              run_identity=facts.run_identity, market_evidence='SYNTHETIC_TEST_FIXTURE')

        if r2_setup is not None:
            resources['R2-case'] = case
            r2_setup(entry, browser, admission, patch, resources, event, anchor, descriptor, output)

        from kronos.browser import runtime_state
        original_complete = runtime_state.complete_startup
        if case.startswith('C03-'):
            actual_notification_proof=browser._startup_notifications_closed
            def observed_notification_proof(value):
                result=actual_notification_proof(value)
                if value is resources.get('C03-notification') and resources['C03-closed'].is_set() and not result:
                    resources['C03-first-false'].set()
                    if case=='C03-unknown':value._executor=None
                return result
            patch.setattr(browser,'_startup_notifications_closed',observed_notification_proof)
            patch.setattr(entry,'_startup_notifications_closed',observed_notification_proof)
        def observed_complete(server, *args, **kwargs):
            if case in {'attached','full-proof-denial'}:
                event('fault.injected', location='all startup bindings installed, before durable READY')
                raise RuntimeError('R1_INJECTED_FULL_COMPOSITION_BEFORE_READY')
            result = original_complete(server, *args, **kwargs)
            event('actual_complete_startup', maintenance=server.connection_governance.maintenance_status())
            return result
        patch.setattr(runtime_state, 'complete_startup', observed_complete)
        def fixture_service_return(server, **kwargs):
            event('fixture_service_after_actual_ready', maintenance=server.connection_governance.maintenance_status(),
                  custody_released=owner.released)
            if 'R2-after-ready' in resources:
                resources['R2-after-ready'](server)
            if case.startswith('C03-'):
                from http.server import ThreadingHTTPServer
                from kronos.common.maintenance import verify_drain_handoff
                notification=server.intraday_notifications
                pool=notification._executor
                entered,release,closed,first_false=(threading.Event() for _ in range(4))
                resources['C03-notification']=notification
                resources['C03-closed']=closed
                resources['C03-first-false']=first_false
                def worker_tail():
                    entered.set()
                    assert release.wait(10)
                future=pool.submit(worker_tail)
                assert entered.wait(2)
                calls=[];close=notification.close
                def observed_close(**values):
                    calls.append(dict(values))
                    value=close(**values)
                    closed.set()
                    event('C03.close_returned', worker_alive=any(t.is_alive() for t in pool._threads))
                    if case=='C03-failed':raise RuntimeError('C03_INJECTED_CLOSE_FAILURE')
                    return value
                patch.setattr(notification,'close',observed_close)
                release_thread=None
                if case=='C03-timely':
                    def finish_tail():
                        assert closed.wait(3) and first_false.wait(3)
                        release.set()
                    release_thread=threading.Thread(target=finish_tail,daemon=True);release_thread.start()
                server.service_actions=lambda:None
                serving=threading.Thread(target=lambda:ThreadingHTTPServer.serve_forever(server,poll_interval=.01),daemon=True)
                serving.start()
                shutdown=server.shutdown;shutdown_calls=[]
                def observed_shutdown():shutdown_calls.append('governed');return shutdown()
                patch.setattr(server,'shutdown',observed_shutdown)
                domain=server._close_domain_owners;deadlines=[]
                def observed_domain(*a,**kw):deadlines.append(kw.get('_deadline'));return domain(*a,**kw)
                patch.setattr(server,'_close_domain_owners',observed_domain)
                generation=__import__('hashlib').sha256(case.encode()).hexdigest()
                assert server.maintenance_replacement_idle(allow_drainable=True)
                assert server.maintenance_admission.claim(generation)
                with server._shutdown_lock:server._shutdown_started=True
                server.application.enter_controlled_maintenance(generation)
                server.maintenance_admission.draining(generation)
                budget=.25 if case=='C03-expiry' else 2.0
                started=time.monotonic();caught=None;handoff_verified=False
                try:
                    server._complete_governed_shutdown(generation,server.connection_governance.process.runtime_identity,budget)
                    if (server.restart_control.path.parent/'maintenance'/(generation+'.json')).exists():
                        from datetime import datetime,UTC
                        verified=verify_drain_handoff(server.restart_control.path.parent/'maintenance',
                            generation=generation,parent_pid=os.getpid(),proof=server.restart_control._token,
                            loaded_revision=server.connection_governance.process.loaded_revision,now=datetime.now(UTC))
                        handoff_verified=verified['schema']=='KRONOS_MAINTENANCE_HANDOFF_V2'
                except BaseException as error:caught=error
                finally:
                    finished=time.monotonic();record=server._startup_cleanup._slots['notifications']
                    output.with_suffix('.maintenance.json').write_text(json.dumps(dict(case=case,
                        state=server.maintenance_admission.snapshot(),close_calls=calls,
                        close_returned=closed.is_set(),initial_real_proof_false=first_false.is_set(),
                        worker_alive_at_disposition=any(t.is_alive() for t in pool._threads),
                        record_state=record['state'],record_deadline=record.get('observation_deadline'),
                        passed_deadline=deadlines[-1] if deadlines else None,started=started,finished=finished,
                        budget=budget,elapsed=finished-started,shutdown_calls=len(shutdown_calls),
                        handoff_exists=(server.restart_control.path.parent/'maintenance'/(generation+'.json')).exists(),
                        handoff_verified=handoff_verified,error_type=None if caught is None else type(caught).__name__,
                        protected_records_unchanged=all(retained_inventory().get(k)==v for k,v in protected_before.items()),
                        explicit_fixture_worker_release_is_not_application_cleanup=case!='C03-timely'),indent=2)+'\n')
                    release.set()
                    future.result(timeout=2)
                    for thread in tuple(pool._threads):thread.join(2);assert not thread.is_alive()
                    if release_thread is not None:release_thread.join(2)
                    if serving.is_alive():shutdown();serving.join(2)
                if caught is not None:raise caught
                if case!='C03-timely':raise RuntimeError('C03_FIXTURE_EXPECTED_DENIAL')
            if case.startswith('C02-'):
                import asyncio
                from http.server import ThreadingHTTPServer
                server.service_actions = lambda: None
                serving = threading.Thread(target=lambda: ThreadingHTTPServer.serve_forever(server, poll_interval=.01),daemon=True)
                serving.start()
                shutdown = server.shutdown
                def observed_shutdown():
                    event('governed.shutdown.called')
                    return shutdown()
                patch.setattr(server, 'shutdown', observed_shutdown)
                kind = case.removeprefix('C02-')
                error = {'runtime':RuntimeError('C02_REAL_CLEANUP_FAILURE'),
                         'keyboard':KeyboardInterrupt('C02_CANCEL'),
                         'cancelled':asyncio.CancelledError('C02_CANCEL')}[kind]
                def fail_close(**_kwargs):
                    event('C02.actual_cleanup_failed', type=type(error).__name__)
                    raise error
                patch.setattr(server.bulk_import, 'close', fail_close)
                generation = __import__('hashlib').sha256(case.encode()).hexdigest()
                assert server.maintenance_replacement_idle(allow_drainable=True)
                assert server.maintenance_admission.claim(generation)
                with server._shutdown_lock:server._shutdown_started=True
                server.application.enter_controlled_maintenance(generation)
                server.maintenance_admission.draining(generation)
                caught = None
                def leaves(exc):
                    return [type(exc).__name__] if not isinstance(exc, BaseExceptionGroup) else [v for e in exc.exceptions for v in leaves(e)]
                try:
                    server._complete_governed_shutdown(generation,server.connection_governance.process.runtime_identity,.8)
                except BaseException as failure:
                    caught=failure
                finally:
                    state=server.maintenance_admission.snapshot()
                    output.with_suffix('.maintenance.json').write_text(json.dumps(dict(
                        case=case,state=state,error_leaves=[] if caught is None else leaves(caught),
                        ledger_errors=[type(e).__name__ for _,e in server._startup_cleanup.errors],
                        handoff_exists=(server.restart_control.path.parent/'maintenance'/(generation+'.json')).exists(),
                        governed_shutdown_calls=sum(e['name']=='governed.shutdown.called' for e in events),
                        bulk_alive_before_test_teardown=server.bulk_import._thread.is_alive(),
                        protected_records_unchanged=all(retained_inventory().get(k)==v for k,v in protected_before.items()),
                        test_loop_teardown_only=True),indent=2)+'\n')
                    # Stop only this disposable loop. This is not governed
                    # shutdown success or proof of the failed bulk cleanup.
                    shutdown();serving.join(2)
                if caught is not None:raise caught
                raise RuntimeError('C02_FIXTURE_FINISHED_WITHOUT_PROPAGATION')
        patch.setattr(browser.KronosBrowserServer, 'serve_forever', fixture_service_return)
        original_handler = entry._handle_canonical_failure
        def observed_handler():
            output.write_text(json.dumps(snapshot(),indent=2,default=str)+'\n')
            return original_handler()  # Real failure reporting and retention loop.
        patch.setattr(entry, '_handle_canonical_failure', observed_handler)
        sys.argv = ['R1-disposable-entry','--port',str(resources.get('R2-port',0)),'--no-browser']
        code = entry._canonical_entry()
        output.write_text(json.dumps(snapshot(),indent=2,default=str)+'\n')
        event('canonical_entry.returned', code=code)
        output.with_suffix('.return.json').write_text(json.dumps(dict(code=code,events=events)))
        os._exit(code)
    except BaseException:
        output.with_suffix('.setup-error.txt').write_text(traceback.format_exc())
        os._exit(97)



def _s303_configure(entry, browser, admission, patch, resources, event, anchor, descriptor, output):
    """Actual fresh capture/custody/V2/R2/READY owners; synthetic external HTTP."""
    from kronos.application.mcx_official_check import McxOfficialCheckEngine
    _r2_f01_configure(entry, browser, admission, patch, resources, event, anchor, descriptor, output)
    mode = resources['S303-mode']
    custody = entry._ADMISSION
    original_capture = entry._startup_capture
    original_budget = custody.budget
    report = {'mode': mode, 'activation': [], 'close': [], 'transport_calls': []}
    actual_factory = entry._compose_mcx_official_check
    def factory(server):
        value = actual_factory(server)
        assert type(value) is McxOfficialCheckEngine
        actual_transport = value.transport
        def transport(*args, **kwargs):
            state = server.connection_governance.maintenance_status()
            assert state['startup'] == 'READY' and custody.released
            report['transport_calls'].append(args[0])
            return actual_transport(*args, **kwargs)
        value.transport = transport
        resources['S303-checker'] = value
        return value
    patch.setattr(entry, '_compose_mcx_official_check', factory)
    actual_activate = McxOfficialCheckEngine.activate_from_canonical
    def activate(owner, server, adopted):
        assert owner is resources['S303-checker']
        assert adopted is custody and adopted.budget is original_budget
        assert entry._startup_capture is original_capture
        assert original_capture._finished is entry._STARTUP_EVIDENCE
        assert server.maintenance_admission is owner._maintenance
        result = actual_activate(owner, server, adopted)
        report['activation'].append(dict(state=server.connection_governance.maintenance_status(),
            released=adopted.released, cleanup_started=adopted.cleanup_started,
            same_capture=True, same_budget=True))
        if mode == 'post-release-failure':
            raise RuntimeError('S303_INJECTED_POST_RELEASE_ACTIVATION_FAILURE')
        return result
    patch.setattr(McxOfficialCheckEngine, 'activate_from_canonical', activate)
    actual_close = McxOfficialCheckEngine.close
    def close(owner, budget):
        result = actual_close(owner, budget)
        report['close'].append(dict(state=result.state, workers=result.owned_workers,
            durable=result.unfinished_durable_writes, original_budget=budget is original_budget,
            deadline=budget.deadline_ns))
        report['application_status_before_fixture_teardown'] = owner.status_document()
        output.with_suffix('.s303.json').write_text(json.dumps(report, indent=2) + '\n')
        for path in owner.store_root.rglob('*') if owner.store_root.exists() else ():
            if path.is_file():
                target = output.parent / 'checker-records' / path.relative_to(owner.store_root)
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
        return result
    patch.setattr(McxOfficialCheckEngine, 'close', close)
    original_after = resources['R2-after-ready']
    def after_ready(server):
        original_after(server)
        checker = resources['S303-checker']
        if checker._worker_handle is not None:
            checker._worker_handle.join(3)
            assert not checker._worker_handle.is_alive()
        assert checker.status_document()['checker_state'] in {'CURRENT','UPDATE AVAILABLE'}
    resources['R2-after-ready'] = after_ready


@pytest.mark.parametrize('mode,case', [
    ('pre-ready-failure','R2-pre-ready-failure'), ('blocked','R2-blocked-completion'),
    ('absent-ready','R2-return-without-ready'), ('release-failure','R2-release-failure'),
    ('healthy','R2-healthy'), ('post-release-failure','R2-healthy')])
def test_s303_actual_canonical_checker_activation_and_cleanup(tmp_path, mode, case):
    evidence = Path(__file__).resolve().parents[4] / 'qualification/case-evidence' / tmp_path.parents[1].name / tmp_path.name
    evidence.mkdir(parents=True)
    anchor = tmp_path / 'anchor'; anchor.mkdir(mode=0o700)
    held = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    read, write = os.pipe(); output = evidence / 'S303.observations.json'
    child = os.fork()
    if child == 0:
        os.close(read); os.dup2(write,2); os.close(write)
        _r1_child(case, anchor, held, output, r4_mode=dict(kind='s303', mode=mode))
        os._exit(98)
    os.close(write); os.set_blocking(read, False); raw = bytearray(); status = None
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if select.select([read],[],[],.1)[0]:
                try: raw.extend(os.read(read,65536))
                except BlockingIOError: pass
            pid, code = os.waitpid(child, os.WNOHANG)
            if pid: status = code; break
        (evidence / 'stderr.log').write_bytes(raw)
        assert status is not None, raw.decode(errors='replace')
        assert output.exists(), output.with_suffix('.setup-error.txt').read_text() if output.with_suffix('.setup-error.txt').exists() else raw.decode(errors='replace')
        observed = json.loads(output.read_bytes())
        report = json.loads(output.with_suffix('.s303.json').read_bytes())
        expected = 0 if mode == 'healthy' else 79 if mode == 'post-release-failure' else 78
        assert os.waitstatus_to_exitcode(status) == expected, observed
        activated = mode in {'healthy','post-release-failure'}
        assert len(report['activation']) == int(activated)
        assert bool(report['transport_calls']) is (mode == 'healthy')
        assert len(report['close']) == 1 and report['close'][0]['state'] == 'CLOSED'
        if mode != 'healthy': assert report['close'][0]['original_budget']
        assert report['close'][0]['workers'] == report['close'][0]['durable'] == 0
        assert observed['r2']['current_consumption_claim']['raw'] == observed['r2']['consumption_claim']['raw']
        assert observed['r2']['source_files_unchanged']
        assert not observed['cleanup_failures']
        assert not _r1_available(anchor)
    finally:
        forced = status is None
        if forced: os.kill(child, signal.SIGTERM); _, status = os.waitpid(child,0)
        os.close(read); os.close(held)
        (evidence / 'fixture-teardown.json').write_text(json.dumps(dict(
            exit=os.waitstatus_to_exitcode(status), forced_fixture_teardown=forced,
            teardown_is_not_application_cleanup=True, anchor_available=_r1_available(anchor))) + '\n')


def _s303_observe_checker_termination(server,budget):
    """Wait for this fixture's exact checker worker under the original budget."""
    budget.check()
    checker=server.mcx_official_check
    handle=checker._worker_handle
    identity=None if handle is None else handle.ident
    if handle is not None:
        handle.join(max(0,(budget.deadline_ns-time.monotonic_ns())/1_000_000_000))
        assert not handle.is_alive()
    budget.check()
    status=checker.status_document()
    assert status['owned_workers']==status['unfinished_durable_writes']==0
    return dict(thread_identity=identity,termination_observed=True,
        original_deadline_ns=budget.deadline_ns,status=status)


def _r1_available(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return False
        return True
    finally:os.close(fd)


@pytest.mark.parametrize('case',['constructor','post-server','cleanup-failure','unreturned','none-return','attached','counted-owner','full-proof-denial','healthy','C01-absent-shadow'])
def test_r1_actual_partial_startup_cleanup(tmp_path,case):
    evidence = Path(__file__).resolve().parents[4] / 'qualification' / 'case-evidence' / tmp_path.parents[1].name / tmp_path.name
    evidence.mkdir(parents=True)
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700)
    held=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    read,write=os.pipe();output=evidence/(case+'.observations.json')
    child=os.fork()
    if child==0:
        os.close(read);os.dup2(write,2);os.close(write)
        _r1_child(case,anchor,held,output)
        os._exit(98)
    os.close(write);os.set_blocking(read,False)
    raw=bytearray();status=None;state=None
    unresolved=case in {'cleanup-failure','unreturned','none-return','counted-owner','full-proof-denial'}
    try:
        deadline=time.monotonic()+75
        while time.monotonic()<deadline:
            if select.select([read],[],[],.1)[0]:
                try:raw.extend(os.read(read,65536))
                except BlockingIOError:pass
            if output.exists() and b'STARTUP_DENIED_CUSTODY_RETAINED' in raw:
                break
            pid,value=os.waitpid(child,os.WNOHANG)
            if pid:
                status=value;break
        (evidence/(case+'.stderr.log')).write_bytes(raw)
        assert output.exists(), dict(stderr=raw.decode(errors='replace'), status=status,
            setup_error=output.with_suffix('.setup-error.txt').read_text() if output.with_suffix('.setup-error.txt').exists() else None)
        state=json.loads(output.read_text())
        assert not any(x['name'].startswith('FORBIDDEN') for x in state['events'])
        if unresolved:
            assert status is None and b'STARTUP_DENIED_CUSTODY_RETAINED' in raw
            assert state['custody']['fd_open'] and not state['custody']['released']
            assert state['custody']['cleanup_started'] and not state['custody']['cleanup_complete']
            assert not output.with_suffix('.return.json').exists()
            assert not _r1_available(anchor)
        else:
            assert status is not None and os.waitstatus_to_exitcode(status)==(0 if case=='healthy' else 78), raw.decode(errors='replace')
            assert state['custody']['released'] and not state['custody']['fd_open']
            assert state['custody']['cleanup_complete'] is (case!='healthy')
        assert state['server']['socket_fd']==-1
        probe=socket.socket();probe.settimeout(1)
        try:assert probe.connect_ex(tuple(state['server']['address']))!=0
        finally:probe.close()
        if case=='cleanup-failure':
            assert state['bulk']['thread_alive']
            assert state['control']['exists']
            assert any(e['owner']=='bulk' for e in state['cleanup_failures'])
            assert state['original_failure']=='R1_INJECTED_AFTER_OWNED_WORKER_BEFORE_SERVER_RETURN'
            assert any(e['name']=='research.close.completed' for e in state['events'])
        else:
            assert not state['bulk']['thread_alive'] and state['bulk']['stop_requested']
            assert state['server']['research_status']['closed']
            assert state['control']['exists'] is (unresolved and case!='full-proof-denial')
        if case in {'post-server','C01-absent-shadow'}:
            assert state['cleanup_ledger']['housekeeping']['state']=='NOT_CREATED'
            assert state['cleanup_ledger']['notifications']['state']=='NOT_CREATED'
        if case in {'unreturned','none-return'}:
            assert state['cleanup_ledger']['housekeeping']['state']=='CLEANUP_UNRESOLVED'
        for operation in ['provider.end_session','application.close','lifecycle.shutdown','wo17.shutdown']:
            assert sum(e['name']==operation+'.attempted' for e in state['events'])==1
            assert sum(e['name']==operation+'.completed' for e in state['events'])==1
        for name in ['lifecycle','wo17']:
            assert state['cleanup_ledger'][name]['state']=='CREATED_AND_CLEANED'
        if case=='attached':
            assert any(e['name']=='final_owner_proof.completed' and e['actual_result'] is True for e in state['events'])
        if case=='C01-absent-shadow':
            assert state['cleanup_ledger']['wo08_shadow']['state']=='NOT_CREATED'
            assert not state['outer_intraday_owners']['wo08_shadow']['created']
        if case=='counted-owner':
            assert state['cleanup_ledger']['coordinator']['state']=='CLEANUP_UNRESOLVED'
            assert state['server']['maintenance']['owners']=={'NOTIFICATION':1}
        if case=='full-proof-denial':
            assert all(row['state'] in {'NOT_CREATED','CREATED_AND_CLEANED'} for row in state['cleanup_ledger'].values())
            assert any(e['name']=='fault.full_owner_proof_denied' for e in state['events'])
        if case=='healthy':
            ready=next(e for e in state['events'] if e['name']=='fixture_service_after_actual_ready')
            assert ready['maintenance']['startup']=='READY' and not ready['maintenance']['active'] and ready['custody_released']
        # Existing committed bytes may not change. New startup/audit records are
        # enumerated separately; cleanup is never counted as history repair.
        assert state['protected_before']
        assert all(state['protected_after'].get(k)==v for k,v in state['protected_before'].items())
        allowed_new=[k for k in state['protected_after'] if k not in state['protected_before']]
        checker_records=state.get('checker_retained_records',{})
        assert all('/evidence/shared/mcx-official-check-v1/' in k and
            state['protected_after'][k]==digest for k,digest in checker_records.items())
        assert all(('/provider-connection-v1/maintenance/' in k and k.endswith('-startup.json'))
            or (k in checker_records and '/evidence/shared/mcx-official-check-v1/' in k)
            for k in allowed_new)
        (evidence/(case+'.result.json')).write_text(json.dumps(dict(case=case,passed=True,
            actual_exit=None if status is None else os.waitstatus_to_exitcode(status),
            allowed_new_cleanup_or_startup_records=allowed_new,observations=str(output)),indent=2)+'\n')
    finally:
        teardown=False
        if status is None:
            os.kill(child,signal.SIGTERM);_,status=os.waitpid(child,0);teardown=True
        os.close(read);os.close(held)
        result=dict(child=child,exit_code=os.waitstatus_to_exitcode(status),
            test_teardown_only=teardown,application_cleanup_claimed_from_teardown=False,
            anchor_available_after_fixture_references_close=_r1_available(anchor))
        (evidence/(case+'.teardown.json')).write_text(json.dumps(result,indent=2)+'\n')
        assert result['anchor_available_after_fixture_references_close']


def test_r1_committed_local_wo12_notifications_journal_books_theta_survive_cleanup(tmp_path):
    """Nonempty synthetic originals; real server cleanup, no restoration claim."""
    from tests.unit.application.test_nse_local_analysis_workflow import _rig, _refresh, _originals, _inventory
    from tests.unit.application.test_swing_daily_research import publish
    from tests.unit.browser.test_swing_local_analysis import _server
    from tests.unit.intraday.test_wo13_notifications import (
        centre, _ResearchOriginSource, _NotificationSourceStore)
    from kronos.application.intraday_notifications import IntradayNotifications
    from tests.unit.intraday.test_wo14_journal import build
    from tests.unit.intraday.test_wo1516_books import fixture as books_fixture
    from tests.unit.theta.test_plc01_integration import configured, originals, admit_originals

    rig = _rig(tmp_path / 'local')
    _refresh(rig)
    rig.research.local_history_reader = rig.owner.retained_research
    daily = publish(rig)
    original = _originals(rig)[0]
    server = _server(rig)
    try:
        shared = centre(tmp_path / 'notifications')
        stores = [_NotificationSourceStore() for _ in range(4)]
        notifications = IntradayNotifications(centre=shared, research=_ResearchOriginSource(),
            wo09=stores[0], futures=stores[1], lifecycle=stores[2], background=False)
        notifications.bind(stores[3])
        notifications.enqueue('PROBABLES', 'SYNTHETIC-RETAINED-RUN')
        checkpoint = notifications.checkpoint(certify_durable=True)
        assert checkpoint['state'] == 'VALID_PENDING' and checkpoint['pending_count'] == 1
        server.intraday_notifications = notifications
        server._startup_cleanup.own('notifications', notifications, 'close',
            lambda o: o.maintenance_status()['closed'] and not o.maintenance_status()['scheduled'])

        journal, _, _, _, _, track = build(tmp_path / 'journal')
        journal.consume_source('TRACK', track.identity)
        journal_before = journal.snapshot()
        assert journal_before.records
        books, _, _, _, _ = books_fixture(tmp_path / 'books')
        books_before = books.snapshot()
        assert books_before
        server.intraday_journal, server.intraday_books = journal, books
        theta_root = tmp_path / 'theta'; theta_root.mkdir()
        theta = configured(theta_root)
        admit_originals(theta, originals(), sponsor_confirmed=True)
        # Nonempty retained Theta bytes are included in the before/after inventory.
        # The separate existing three-product Theta HTTP test covers active routing.
        before = _inventory(tmp_path)
        server.server_close()
        assert server._startup_cleanup.complete()
        assert server.socket.fileno() == -1 and not server.bulk_import._thread.is_alive()
        assert server.swing_research_control.work_status()['closed']
        assert rig.owner.status()['state'] == 'CLOSED'
        assert _originals(rig) == (original,)
        assert rig.research.store.records('DAILY_PUBLICATION')
        assert notifications.checkpoint(certify_durable=True) == checkpoint
        assert journal.snapshot() == journal_before and books.snapshot() == books_before
        assert _inventory(tmp_path) == before
        assert daily['state'] == 'PUBLISHED'
    finally:
        if not server._startup_cleanup.complete():
            server.server_close()


def test_r1_constructor_failure_before_socket_has_exception_safe_factory(monkeypatch):
    from kronos.browser.server import create_browser_server
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from tests.unit.application.test_swing_opportunities import _Provider
    observed = []
    original = KronosBrowserServer.synchronize_swing_notifications
    def fail(server):
        original(server)
        observed.append(server)
        raise RuntimeError('R1_SYNTHETIC_BEFORE_LISTENER')
    monkeypatch.setattr(KronosBrowserServer, 'synchronize_swing_notifications', fail)
    with pytest.raises(RuntimeError, match='R1_SYNTHETIC_BEFORE_LISTENER'):
        create_browser_server(SwingOpportunitiesApplication(_Provider), port=0)
    server, = observed
    assert server._startup_cleanup.complete()
    assert server._startup_cleanup.snapshot()['listener']['state'] == 'NOT_CREATED'
    assert server.swing_research_control.work_status()['closed']
    assert server.application._SwingOpportunitiesApplication__research_capture is None
    assert not server._research_owner_bindings


def test_r1_incomplete_durable_bulk_is_not_cleanup_clearance(tmp_path, monkeypatch):
    from kronos.browser.server import _StartupCleanup, _startup_bulk_closed
    from tests.unit.application.test_swing_bulk_import import _owner, PDF, EXPECTED
    owner, intake, store = _owner(tmp_path)
    record, _ = store.admit(request_identity="REQUEST-ONE",
        review_pack_identity="KRONOS-V3-REVIEW-" + "B" * 32,
        answer=PDF, market="NSE", expected=EXPECTED,
        received_at="2026-09-22T10:00:00+00:00")
    assert store.list_incomplete() == (record["batch_identity"],)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    calls = []
    close = owner.close
    def observed():
        calls.append('close')
        close()
    monkeypatch.setattr(owner, 'close', observed)
    cleanup = _StartupCleanup()
    cleanup.own('bulk', owner, 'close', _startup_bulk_closed)
    assert cleanup.cleanup() is False
    assert cleanup.snapshot()['bulk']['state'] == 'CLEANUP_UNRESOLVED'
    assert owner.work_status()['owned_workers'] == 0
    assert cleanup.cleanup() is False and calls == ['close']
    assert intake.extractions == intake.acceptances == 0
    assert {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('fault', ['invalid-reference','directory-sync'])
def test_r1_notification_durability_failure_retains_denial_without_retry(tmp_path, monkeypatch, fault):
    from kronos.browser.server import _StartupCleanup, _startup_notifications_closed
    from kronos.application.intraday_notifications import IntradayNotifications
    from tests.unit.intraday.test_wo13_notifications import centre, _ResearchOriginSource, _NotificationSourceStore
    stores = [_NotificationSourceStore() for _ in range(4)]
    owner = IntradayNotifications(centre=centre(tmp_path),research=_ResearchOriginSource(),
        wo09=stores[0],futures=stores[1],lifecycle=stores[2],background=False)
    owner.bind(stores[3]); owner.enqueue('PROBABLES','SYNTHETIC-RETAINED')
    if fault == 'invalid-reference':
        (owner.root / '.interrupted.staged').write_bytes(b'SYNTHETIC-INCOMPLETE')
    else:
        def fail(_path):raise OSError('R1_SYNTHETIC_DIRECTORY_SYNC_FAILED')
        monkeypatch.setattr(owner,'_fsync_directory',fail)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    close = owner.close; calls = []
    def observed():calls.append('close');close()
    monkeypatch.setattr(owner,'close',observed)
    cleanup = _StartupCleanup();cleanup.own('notifications',owner,'close',_startup_notifications_closed)
    assert cleanup.cleanup() is False and owner.maintenance_status()['closed']
    assert cleanup.snapshot()['notifications']['state'] == 'CLEANUP_UNRESOLVED'
    assert len(cleanup.errors) == 1
    assert cleanup.cleanup() is False and calls == ['close']
    assert {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('case',['C01-before-registration','C01-mid-registration'])
def test_c01_returned_composition_never_clears_unregistered_owners(tmp_path,case):
    evidence=Path(__file__).resolve().parents[4]/'qualification'/'case-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700)
    held=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    read,write=os.pipe();output=evidence/(case+'.observations.json')
    child=os.fork()
    if child==0:
        os.close(read);os.dup2(write,2);os.close(write)
        _r1_child(case,anchor,held,output);os._exit(98)
    os.close(write);os.set_blocking(read,False);raw=bytearray();status=None
    try:
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            if select.select([read],[],[],.1)[0]:
                try:raw.extend(os.read(read,65536))
                except BlockingIOError:pass
            if output.exists() and b'STARTUP_DENIED_CUSTODY_RETAINED' in raw:break
            pid,value=os.waitpid(child,os.WNOHANG)
            if pid:status=value;break
        (evidence/(case+'.stderr.log')).write_bytes(raw)
        assert output.exists(), raw.decode(errors='replace')
        data=json.loads(output.read_text())
        # These are actual objects from the real returned composition. Missing
        # registration is UNKNOWN, never a claim that construction did not occur.
        assert data['outer_intraday_owners']['wo17_monitoring']['created']
        assert data['cleanup_ledger']['wo17']['state']!='NOT_CREATED'
        assert data['cleanup_ledger']['intraday_runtime']['state']=='CLEANUP_UNRESOLVED'
        assert status is None and b'STARTUP_DENIED_CUSTODY_RETAINED' in raw
        assert data['custody']['fd_open'] and not data['custody']['cleanup_complete']
        assert not data['custody']['released'] and not _r1_available(anchor)
        assert any(e['name']=='provider.end_session.completed' for e in data['events'])
        if case=='C01-mid-registration':
            assert data['outer_intraday_owners']['lifecycle_application']['work_status']['state']=='TERMINATED'
        (evidence/(case+'.result.json')).write_text(json.dumps({'passed':True,'acknowledgement':False,'actual_exit':None},indent=2)+'\n')
    finally:
        teardown=status is None
        if teardown:os.kill(child,signal.SIGTERM);_,status=os.waitpid(child,0)
        os.close(read);os.close(held)
        (evidence/(case+'.teardown.json')).write_text(json.dumps({'child':child,'exit_code':os.waitstatus_to_exitcode(status),'test_teardown_only':teardown,'application_cleanup_claimed_from_teardown':False,'anchor_available':_r1_available(anchor)},indent=2)+'\n')


def _review_terminal_child(tmp_path,case):
    evidence=Path(__file__).resolve().parents[4]/'qualification'/'case-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700)
    held=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    read,write=os.pipe();output=evidence/(case+'.observations.json');child=os.fork()
    if child==0:
        os.close(read);os.dup2(write,2);os.close(write)
        _r1_child(case,anchor,held,output);os._exit(98)
    os.close(write);os.set_blocking(read,False);raw=bytearray();status=None
    try:
        deadline=time.monotonic()+75
        while time.monotonic()<deadline:
            if select.select([read],[],[],.1)[0]:
                try:raw.extend(os.read(read,65536))
                except BlockingIOError:pass
            pid,value=os.waitpid(child,os.WNOHANG)
            if pid:status=value;break
        (evidence/(case+'.stderr.log')).write_bytes(raw)
        assert status is not None, raw.decode(errors='replace')
        detail=output.with_suffix('.maintenance.json')
        assert detail.exists(), output.with_suffix('.setup-error.txt').read_text() if output.with_suffix('.setup-error.txt').exists() else raw.decode(errors='replace')
        return json.loads(detail.read_text()),os.waitstatus_to_exitcode(status),evidence
    finally:
        teardown=status is None
        if teardown:os.kill(child,signal.SIGTERM);_,status=os.waitpid(child,0)
        os.close(read);os.close(held)
        (evidence/(case+'.teardown.json')).write_text(json.dumps(dict(child=child,exit_code=os.waitstatus_to_exitcode(status),test_teardown_only=teardown,application_cleanup_claimed_from_teardown=False),indent=2)+'\n')


@pytest.mark.parametrize('kind,leaf',[('runtime','RuntimeError'),('keyboard','KeyboardInterrupt'),('cancelled','CancelledError')])
def test_c02_real_governed_cleanup_records_failure_before_group_propagation(tmp_path,kind,leaf):
    data,code,evidence=_review_terminal_child(tmp_path,'C02-'+kind)
    assert data['state']['state']=='FAILED_FENCED',data
    assert data['state']['failure']=='CLEANUP_UNRESOLVED'
    assert leaf in data['error_leaves'] and leaf in data['ledger_errors']
    assert not data['handoff_exists'] and data['governed_shutdown_calls']==0
    assert data['bulk_alive_before_test_teardown']
    assert data['protected_records_unchanged']
    assert code==79  # Neither clean-startup acknowledgement nor restoration permission.
    (evidence/'C02.result.json').write_text(json.dumps({'passed':True,'maintenance':data},indent=2)+'\n')


@pytest.mark.parametrize('case',['C03-timely','C03-expiry','C03-failed','C03-unknown'])
def test_c03_actual_notification_completion_uses_same_operation_and_deadline(tmp_path,case):
    data,code,evidence=_review_terminal_child(tmp_path,case)
    assert data['close_calls']==[{'wait':False}],data
    assert data['close_returned'] and data['protected_records_unchanged']
    observations=json.loads((evidence/(case+'.observations.json')).read_text())
    assert sum(e['name']=='C03.close_returned' for e in observations['events'])==1
    if case=='C03-timely':
        assert data['initial_real_proof_false']
        assert data['state']['state']=='STOPPING',data
        assert data['handoff_exists'] and data['handoff_verified'] and data['shutdown_calls']==1
        assert not data['worker_alive_at_disposition'] and data['record_state']=='CREATED_AND_CLEANED'
        assert data['record_deadline']==data['passed_deadline']
        assert data['finished']<=data['passed_deadline'] and code==0
    else:
        assert data['state']['state']=='FAILED_FENCED' and data['state']['failure']=='CLEANUP_UNRESOLVED',data
        assert not data['handoff_exists'] and data['shutdown_calls']==0
        assert data['record_state']=='CLEANUP_UNRESOLVED' and code==79
        if case=='C03-expiry':
            assert data['elapsed']>=data['budget'] and data['elapsed']<data['budget']+1.5
            assert data['record_deadline']==data['passed_deadline']
            assert data['worker_alive_at_disposition']
    (evidence/'C03.result.json').write_text(json.dumps({'passed':True,'maintenance':data},indent=2)+'\n')


def test_c03_completed_close_observation_cannot_extend_deadline_or_retry(tmp_path,monkeypatch):
    from kronos.browser.server import _StartupCleanup,_startup_notifications_closed
    from kronos.application.intraday_notifications import IntradayNotifications
    from tests.unit.intraday.test_wo13_notifications import centre,_ResearchOriginSource,_NotificationSourceStore
    stores=[_NotificationSourceStore() for _ in range(4)]
    owner=IntradayNotifications(centre=centre(tmp_path),research=_ResearchOriginSource(),
        wo09=stores[0],futures=stores[1],lifecycle=stores[2],background=True)
    owner.bind(stores[3]);owner.enqueue('PROBABLES','SYNTHETIC-C03')
    entered,release=threading.Event(),threading.Event()
    def tail():entered.set();assert release.wait(3)
    future=owner._executor.submit(tail);assert entered.wait(2)
    pool=owner._executor;calls=[];close=owner.close
    def observed(**kwargs):calls.append(kwargs);return close(**kwargs)
    monkeypatch.setattr(owner,'close',observed)
    cleanup=_StartupCleanup();cleanup.own('notifications',owner,'close',_startup_notifications_closed)
    deadline=time.monotonic()+.5
    try:
        assert not cleanup.close_one('notifications',_deadline=deadline,wait=False)
        assert cleanup.snapshot()['notifications']['state']=='CLEANUP_PENDING'
        assert not cleanup.observe_one('notifications',deadline+1)
        assert cleanup.snapshot()['notifications']['state']=='CLEANUP_UNRESOLVED'
        assert not cleanup.close_one('notifications',_deadline=deadline+1,wait=False)
        assert calls==[{'wait':False}]
    finally:
        release.set();future.result(2)
        for thread in tuple(pool._threads):thread.join(2);assert not thread.is_alive()
    assert not cleanup.observe_one('notifications',deadline+1)
    assert not cleanup.complete() and calls==[{'wait':False}]


@pytest.mark.parametrize('path',['startup','maintenance'])
def test_ux10_cleanup_observes_same_cancelled_timer_before_deadline(tmp_path,monkeypatch,path):
    from threading import Timer
    from kronos.application.swing_ux10 import SwingUx10NotificationService,Ux10NotificationStore
    from kronos.browser.server import (_StartupCleanup,_startup_ux10_closed,
        KronosBrowserServer)

    entered,release,close_returned=Event(),Event(),Event()
    timers=[]
    def scheduler(delay,operation):
        def blocked_callback():
            entered.set()
            if not release.wait(3):raise RuntimeError('UX10_TIMER_FIXTURE_RELEASE_TIMEOUT')
            operation()
        timer=Timer(delay,blocked_callback);timer.daemon=True;timers.append(timer);timer.start()
        return timer
    owner=SwingUx10NotificationService(Ux10NotificationStore(tmp_path/'ux10'),
        retry_scheduler=scheduler,background_runner=lambda operation,_name:operation())
    owner._schedule_retry('no-retained-record',0.01)
    assert entered.wait(2)
    timer=timers[0]
    assert isinstance(timer,Timer) and timer.is_alive()
    cleanup=_StartupCleanup();cleanup.own('ux10',owner,'close',_startup_ux10_closed)
    calls=[];actual_close=owner.close
    def one_close():
        calls.append('close')
        actual_close()
        assert timer.is_alive()  # cancel returned while this same callback remained entered
        close_returned.set()
    monkeypatch.setattr(owner,'close',one_close)

    # This releaser only advances the entered disposable Timer callback; the
    # application cleanup path performs the bounded join/proof itself.
    def release_callback():
        assert close_returned.wait(2)
        time.sleep(0.03)
        release.set()
    releaser=Thread(target=release_callback,daemon=True);releaser.start()
    deadline=time.monotonic()+1.5
    if path=='startup':
        complete=cleanup.cleanup(deadline=deadline)
    else:
        server=object.__new__(KronosBrowserServer)
        server._startup_cleanup=cleanup
        server.ux10_notifications=owner
        server._close_domain_owners_once(1.5,True,_deadline=deadline)
        complete=cleanup.complete()
    releaser.join(2)
    assert complete
    assert calls==['close']
    assert not timer.is_alive()
    assert cleanup.snapshot()['ux10']['state']=='CREATED_AND_CLEANED'
    assert cleanup.snapshot()['ux10']['observed_completion_at'] < deadline


def test_ux10_cleanup_observes_pending_before_server_aggregate_and_control(tmp_path,monkeypatch):
    from threading import Timer
    from kronos.application.swing_ux10 import SwingUx10NotificationService,Ux10NotificationStore
    from kronos.browser.server import _StartupCleanup,_startup_ux10_closed

    entered,release,close_returned,aggregate_evaluated=Event(),Event(),Event(),Event()
    timers=[]
    def scheduler(delay,operation):
        def blocked_callback():
            entered.set()
            if not release.wait(3):
                raise RuntimeError('UX10_DEPENDENCY_FIXTURE_RELEASE_TIMEOUT')
            operation()
        timer=Timer(delay,blocked_callback);timer.daemon=True;timers.append(timer);timer.start()
        return timer
    owner=SwingUx10NotificationService(Ux10NotificationStore(tmp_path/'ux10-dependency'),
        retry_scheduler=scheduler,background_runner=lambda operation,_name:operation())
    owner._schedule_retry('no-retained-record',0.01)
    assert entered.wait(2)
    timer=timers[0]

    cleanup=_StartupCleanup();cleanup.own('ux10',owner,'close',_startup_ux10_closed)
    server_owner=object()
    dependencies=tuple(name for name in cleanup._names
        if name not in {'server','control','intraday_runtime'})
    cleanup.container('server',server_owner,dependencies)
    aggregate_proof=cleanup._slots['server']['proof']
    aggregate_saw_live_timer=[]
    def observed_aggregate(candidate):
        aggregate_saw_live_timer.append(timer.is_alive())
        aggregate_evaluated.set()
        return aggregate_proof(candidate)
    cleanup._slots['server']['proof']=observed_aggregate

    class Control:
        removed=False
        calls=0
        def remove(self):
            self.calls+=1;self.removed=True
    control=Control();cleanup.own('control',control,'remove',lambda value:value.removed)
    close_calls=[];actual_close=owner.close
    def one_close():
        close_calls.append('close');actual_close()
        assert timer.is_alive()
        close_returned.set()
    monkeypatch.setattr(owner,'close',one_close)

    # With the defective order, the dependent server proof runs immediately
    # and releases the Timer. With dependency ordering, this bounded wait
    # expires first, then the same Timer finishes within the original deadline.
    aggregate_ran_before_release=[]
    def release_callback():
        assert close_returned.wait(2)
        aggregate_ran_before_release.append(aggregate_evaluated.wait(.08))
        release.set()
    releaser=Thread(target=release_callback,daemon=True);releaser.start()
    deadline=time.monotonic()+1.5
    complete=cleanup.cleanup(deadline=deadline)
    releaser.join(2)

    snapshot=cleanup.snapshot()
    assert complete, snapshot
    assert aggregate_ran_before_release==[False]
    assert aggregate_saw_live_timer==[False]
    assert close_calls==['close'] and control.calls==1
    assert not timer.is_alive()
    assert snapshot['ux10']['state']=='CREATED_AND_CLEANED'
    assert snapshot['server']['state']=='CREATED_AND_CLEANED'
    assert snapshot['control']['state']=='CREATED_AND_CLEANED'
    assert snapshot['ux10']['observed_completion_at'] < deadline


def test_ux10_cleanup_expiry_remains_unresolved_and_does_not_close_twice(tmp_path,monkeypatch):
    from threading import Timer
    from kronos.application.swing_ux10 import SwingUx10NotificationService,Ux10NotificationStore
    from kronos.browser.server import _StartupCleanup,_startup_ux10_closed

    entered,release=Event(),Event();timers=[]
    def scheduler(delay,operation):
        def blocked_callback():
            entered.set()
            release.wait(3)
            operation()
        timer=Timer(delay,blocked_callback);timer.daemon=True;timers.append(timer);timer.start();return timer
    owner=SwingUx10NotificationService(Ux10NotificationStore(tmp_path/'ux10-expiry'),
        retry_scheduler=scheduler,background_runner=lambda operation,_name:operation())
    owner._schedule_retry('no-retained-record',0.01);assert entered.wait(2)
    timer=timers[0];cleanup=_StartupCleanup();cleanup.own('ux10',owner,'close',_startup_ux10_closed)
    cleanup.container('server',object(),tuple(name for name in cleanup._names
        if name not in {'server','control','intraday_runtime'}))
    class Control:
        removed=False
        calls=0
        def remove(self):self.calls+=1;self.removed=True
    control=Control();cleanup.own('control',control,'remove',lambda value:value.removed)
    calls=[];actual_close=owner.close
    def one_close():calls.append('close');actual_close()
    monkeypatch.setattr(owner,'close',one_close)
    deadline=time.monotonic()+0.08
    try:
        assert not cleanup.cleanup(deadline=deadline)
        assert time.monotonic()>=deadline
        assert calls==['close']
        assert timer.is_alive()
        assert cleanup.snapshot()['ux10']['state']=='CLEANUP_UNRESOLVED'
        assert cleanup.snapshot()['server']['state']=='CLEANUP_UNRESOLVED'
        assert cleanup.snapshot()['control']['state']=='CREATED' and control.calls==0
        assert not cleanup.complete()
    finally:
        # Test-resource teardown is separate and is not credited to application cleanup.
        release.set();timer.join(2)
    assert not timer.is_alive()


def test_ux10_cleanup_unknown_timer_identity_remains_unresolved(tmp_path):
    from kronos.application.swing_ux10 import SwingUx10NotificationService,Ux10NotificationStore
    from kronos.browser.server import _StartupCleanup,_startup_ux10_closed
    owner=SwingUx10NotificationService(Ux10NotificationStore(tmp_path/'ux10-unknown'))
    with owner._lock:owner._retry_handles['unknown-owned-callback']=None
    cleanup=_StartupCleanup();cleanup.own('ux10',owner,'close',_startup_ux10_closed)
    cleanup.container('server',object(),tuple(name for name in cleanup._names
        if name not in {'server','control','intraday_runtime'}))
    class Control:
        removed=False
        calls=0
        def remove(self):self.calls+=1;self.removed=True
    control=Control();cleanup.own('control',control,'remove',lambda value:value.removed)
    assert not cleanup.cleanup(deadline=time.monotonic()+1)
    assert cleanup.snapshot()['ux10']['state']=='CLEANUP_UNRESOLVED'
    assert cleanup.snapshot()['server']['state']=='CLEANUP_UNRESOLVED'
    assert cleanup.snapshot()['control']['state']=='CREATED' and control.calls==0
    assert owner.maintenance_status()=={'closed':True,'retry_callbacks':1}


def test_ux10_cleanup_substituted_timer_identity_denies_aggregate_and_control(tmp_path,monkeypatch):
    from threading import Timer
    from kronos.application.swing_ux10 import SwingUx10NotificationService,Ux10NotificationStore
    from kronos.browser.server import _StartupCleanup,_startup_ux10_closed

    entered,release=Event(),Event();timers=[]
    def scheduler(delay,operation):
        def blocked_callback():
            entered.set();release.wait(3);operation()
        timer=Timer(delay,blocked_callback);timer.daemon=True;timers.append(timer);timer.start();return timer
    owner=SwingUx10NotificationService(Ux10NotificationStore(tmp_path/'ux10-substituted'),
        retry_scheduler=scheduler,background_runner=lambda operation,_name:operation())
    owner._schedule_retry('no-retained-record',0.01);assert entered.wait(2)
    original=timers[0]
    cleanup=_StartupCleanup();cleanup.own('ux10',owner,'close',_startup_ux10_closed)
    cleanup.container('server',object(),tuple(name for name in cleanup._names
        if name not in {'server','control','intraday_runtime'}))
    class Control:
        removed=False
        calls=0
        def remove(self):self.calls+=1;self.removed=True
    control=Control();cleanup.own('control',control,'remove',lambda value:value.removed)
    deadline=time.monotonic()+1
    assert not cleanup.close_one('ux10',_deadline=deadline)
    assert cleanup.snapshot()['ux10']['state']=='CLEANUP_PENDING'
    substitute=Timer(30,lambda:None)
    with owner._lock:
        owner._retry_handles={'substituted-owner':substitute}
        owner._retry_retired_handles=[]
    try:
        assert not cleanup.cleanup(deadline=deadline)
        snapshot=cleanup.snapshot()
        assert snapshot['ux10']['state']=='CLEANUP_UNRESOLVED'
        assert snapshot['server']['state']=='CLEANUP_UNRESOLVED'
        assert snapshot['control']['state']=='CREATED' and control.calls==0
        assert any(str(error)=='ASYNC_COMPLETION_OWNER_UNKNOWN'
            for name,error in cleanup.errors if name=='ux10')
    finally:
        release.set();original.join(2)
    assert not original.is_alive()


def _r2_f01_configure(entry, browser, admission, patch, resources, event,
                      anchor, descriptor, output):
    """Actual canonical boundary checks; source/external seams remain explicit."""
    from dataclasses import asdict
    from datetime import UTC, datetime
    from hashlib import sha256
    import secrets
    from types import SimpleNamespace
    from kronos.application.intraday_notifications import IntradayNotifications
    from kronos.application.notification_centre import SponsorNotificationCentre
    from kronos.browser import runtime_state
    from kronos.common import maintenance
    from tests.unit.intraday.test_wo13_notifications import seed_r2_f01_retained_notification
    case=resources['R2-case']
    actual_complete=runtime_state.complete_startup

    def raw_files(root):
        return {str(p.relative_to(root)):dict(sha256=sha256(p.read_bytes()).hexdigest(),
                    bytes=p.stat().st_size,raw=p.read_text())
                for p in sorted(root.rglob('*')) if p.is_file()}

    centre_root=browser.NativeReviewEvidenceStore().root/'notification-centre-v1'
    seed=seed_r2_f01_retained_notification(entry.DEFAULT_INTRADAY_EVIDENCE_ROOT,centre_root)
    refs=Path(seed['reference_root'])
    state=dict(case=case,seed=seed,initial_reference_files=raw_files(refs),
        initial_centre_files=raw_files(centre_root),fake_send_calls=[],
        new_enqueues_during_canonical=[],consumed_references=[],delivery_states=[],
        activation_results=[],worker_submissions=[],complete_startup_body_executed=False,
        worker_errors=[],barriers={},seams=[
            'Retained R1 fixture: library import performs actual source capture/pinning; actual _canonical_entry/main/cleanup runs. Native launcher exec/prelude is not exercised.',
            'Retained R1 fixture: source publication/signature gate is simulated; no transport or publication authority is asserted.',
            'Retained R1 fixture: installation binding and canonical parent image use actual disposable anchor/kernel parent; production binding is not used.',
            'Retained R1 fixture: synthetic Swing publication uses actual owning stores and validators; no market acquisition.',
            'R4 fixture correction: same fork-child PID execs a fresh library import from an exact disposable clean Git source. Actual original StartupCapture/evidence, pin verification and one inherited deadline are retained. Native selection/head and package authority are synthetic component fixtures; no native orchestration qualification.',
            'R2 fixture: sign-only disposable predecessor publishes typed synthetic zero-owner attestation and a real durable WO13 checkpoint, then exits; this is not a production predecessor-drain qualification.',
            'R2 fixture: V2 port absence predicate binds the same selected ephemeral loopback port later used by canonical server, never port 8947. Predecessor absence and child identity predicates are actual.',
            'R2 fixture: _telegram_security supplies recording fake status/send; no credentials, transport or delivery.',
            'R2 fixture: worker barrier only delays actual drain. Completion health and close failure are injected only in their named cases; actual READY/receipt/release and cleanup proof are not mocked successful.'
        ])
    accepted=threading.Event();permit=threading.Event();finished=threading.Event()
    notification={}
    def export():
        value=dict(state)
        value['current_reference_files']=raw_files(refs)
        value['current_centre_files']=raw_files(centre_root)
        value['source_files_unchanged']=all(Path(p).is_file() and
            sha256(Path(p).read_bytes()).hexdigest()==digest
            for p,digest in seed['source_files'].items())
        value['barriers']=dict(accepted=accepted.is_set(),permit=permit.is_set(),finished=finished.is_set())
        if state.get('consumption_claim'):
            claim=Path(state['consumption_claim']['path'])
            value['current_consumption_claim']=dict(exists=claim.exists(),
                raw=claim.read_text() if claim.exists() else None)
        if notification:
            owner=notification['owner']
            value['notification_status']=owner.maintenance_status()
            value['notification_checkpoint']=owner.checkpoint(certify_durable=True)
            value['notification_executor_workers']=[dict(name=t.name,alive=t.is_alive()) for t in owner._executor._threads]
        return value
    resources['R2-snapshot']=export

    # Exact captured bytes remain pinned. Only publication-state authority is a
    # synthetic admission seam, recomputed through the real StartupEvidence validator.
    captured=entry._STARTUP_EVIDENCE
    state['captured_startup_source_state']=captured.source_state
    state['captured_startup_evidence']=asdict(captured)
    output.with_suffix('.fixture-pre-admission.json').write_text(json.dumps(export(),indent=2,default=str)+'\n')
    assert captured.source_revision and captured.loaded_modules and captured.source_snapshot_digest
    # The fresh fixture captures the current process and clean Git-backed
    # bytes before these test imports. Retain that exact finished object.
    assert captured is entry._startup_capture._finished
    assert captured.process_id == os.getpid()
    assert captured.source_state == 'CLEAN_COMMIT'
    assert captured.load_verification == 'PINNED_STARTUP_IMPORTS'
    state['fixture_startup_evidence']=asdict(captured)
    event('R2.fixture_publication_state',observed=captured.source_state,
          simulated=False,snapshot_digest=captured.source_snapshot_digest)

    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    assert port!=8947
    resources['R2-port']=port
    handoff_root=entry.DEFAULT_BACKEND_CONTROL_PATH.parent/'maintenance'
    generation=secrets.token_hex(32);proof=secrets.token_hex(32)
    revision='1'*40;predecessor_runtime=sha256(b'R2-disposable-signer').hexdigest()
    drain={name:0 for name in maintenance._DRAIN_ZERO_FIELDS}
    drain['notification_checkpoint']=dict(seed['checkpoint'])
    signer=os.fork()
    if signer==0:
        try:
            os.close(descriptor)  # Signer must not retain admission custody.
            maintenance.publish_drain_handoff(handoff_root,generation=generation,
                parent_pid=os.getpid(),proof=proof,runtime_identity=predecessor_runtime,
                loaded_revision=revision,drain=drain,now=datetime.now(UTC))
            os._exit(0)
        except BaseException:
            os._exit(96)
    _,signer_status=os.waitpid(signer,0)
    assert os.waitstatus_to_exitcode(signer_status)==0
    signed=handoff_root/(generation+'.json');signed_raw=signed.read_text()
    verified=maintenance.verify_drain_handoff(handoff_root,generation=generation,
        parent_pid=signer,proof=proof,loaded_revision=revision,now=datetime.now(UTC))
    assert verified['drain']['notification_checkpoint']==seed['checkpoint']
    state['signed_handoff']=dict(raw=signed_raw,sha256=sha256(signed_raw.encode()).hexdigest(),
        signer_pid=signer,signer_exit=0,signer_reaped=True,signature_verified=True,
        signing_secret_retained=False)
    os.environ.update(KRONOS_MAINTENANCE_GENERATION=generation,
        KRONOS_MAINTENANCE_PARENT=str(signer),KRONOS_MAINTENANCE_PROOF=proof,
        KRONOS_MAINTENANCE_PROTOCOL='V2',KRONOS_MAINTENANCE_REVISION=revision)
    original_context=entry.consume_startup_context
    def fixture_port_free():
        with socket.socket() as check:
            check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            check.bind(('127.0.0.1',port))
        state['fixture_port_absence']=dict(port=port,actual_bind_succeeded=True)
        return True
    def context(root,environment,**kwargs):
        result=original_context(root,environment,port_free=fixture_port_free,**kwargs)
        assert type(result) is maintenance.DrainStartupContext
        assert result.notification_checkpoint()==seed['checkpoint']
        claim=handoff_root/(generation+'.consumed.json')
        state['consumption_claim']=dict(path=str(claim),raw=claim.read_text(),sha256=sha256(claim.read_bytes()).hexdigest())
        state['consumed_context']=asdict(result)
        state['handoff_environment_removed']=all(name not in environment for name in maintenance._ENV)
        event('R2.V2_consumed',checkpoint=result.notification_checkpoint(),claim_exists=claim.exists())
        return result
    patch.setattr(entry,'consume_startup_context',context)

    class RecordingSender:
        def status(self):
            return SimpleNamespace(private_chat_configured=True,delivery_enabled=True)
        def send(self,text):
            # The real centre persistence must precede even the fake transport.
            records=resources['server'].notification_centre._store.load_current()
            intraday=[r for r in records if r.source_kind=='INTRADAY_WO13']
            assert len(intraday)==1 and intraday[0].telegram_delivery=='ATTEMPTING'
            state['fake_send_calls'].append(dict(text=text,at=datetime.now(UTC).isoformat(),
                retained_delivery=intraday[0].telegram_delivery,
                notification_identity=intraday[0].notification_identity))
            event('R2.fake_send',retained_delivery='ATTEMPTING')
            return SimpleNamespace(state=SimpleNamespace(value='SENT'))
    patch.setattr(browser,'_telegram_security',RecordingSender)

    original_enqueue=IntradayNotifications.enqueue
    def enqueue(self,kind,identity):
        state['new_enqueues_during_canonical'].append(dict(kind=kind,identity=identity))
        return original_enqueue(self,kind,identity)
    patch.setattr(IntradayNotifications,'enqueue',enqueue)
    original_schedule=IntradayNotifications._schedule
    def schedule(self):
        assert self.root==refs and self._expected_checkpoint==seed['checkpoint']
        assert self.probables.notification_listener==self.enqueue
        notification['owner']=self
        if not accepted.is_set():
            assert self.checkpoint()==seed['checkpoint']
            assert self._deferred_replay and not self._replay_active
            state['checkpoint_accepted']=dict(expected=dict(self._expected_checkpoint),
                observed=self.checkpoint(),listeners_bound=True,
                startup=resources['server'].connection_governance.maintenance_status())
            event('R2.checkpoint_accepted_before_schedule',checkpoint=self.checkpoint())
            original_submit=self._executor.submit
            def submit(*args,**kwargs):
                state['worker_submissions'].append(dict(startup=resources['server'].connection_governance.maintenance_status(),
                    custody_released=entry._ADMISSION.released))
                return original_submit(*args,**kwargs)
            patch.setattr(self._executor,'submit',submit)
            accepted.set()
        return original_schedule(self)
    patch.setattr(IntradayNotifications,'_schedule',schedule)
    original_drain=IntradayNotifications.drain
    def drain_owned_body(self):
        assert accepted.is_set()
        if not self._replay_active:
            return original_drain(self)
        event('R2.worker_waiting_for_barrier')
        assert permit.wait(8),'R2_REPLAY_PERMISSION_BARRIER_EXPIRED'
        event('R2.worker_entered_real_drain')
        return original_drain(self)
    patch.setattr(IntradayNotifications,'drain',drain_owned_body)
    original_worker=IntradayNotifications._drain_owned
    def worker(self,ticket):
        try:
            result=original_worker(self,ticket)
        except BaseException as error:
            state['worker_errors'].append(dict(type=type(error).__name__,message=str(error)))
            raise
        else:
            event('R2.actual_worker_returned_ticket_released' if threading.current_thread().name.startswith('kronos-notification')
                  else 'R2.direct_deferred_drain_returned')
            return result
        finally:
            if threading.current_thread().name.startswith('kronos-notification'):
                finished.set()
    patch.setattr(IntradayNotifications,'_drain_owned',worker)
    original_consume=IntradayNotifications._consume
    def consume(self,kind,identity):
        value=original_consume(self,kind,identity)
        state['consumed_references'].append(dict(kind=kind,identity=identity))
        return value
    patch.setattr(IntradayNotifications,'_consume',consume)
    original_delivery=SponsorNotificationCentre.record_delivery
    def delivery(self,identity,value):
        result=original_delivery(self,identity,value)
        state['delivery_states'].append(dict(identity=identity,state=value,
            retained_integrity=result.integrity_sha256))
        return result
    patch.setattr(SponsorNotificationCentre,'record_delivery',delivery)

    def boundary(server):
        receipt=server.connection_governance.store.root/'maintenance'/(server.connection_governance.process.runtime_identity+'-startup.json')
        return dict(startup=server.connection_governance.maintenance_status(),
            startup_receipt_present=receipt.exists(),receipt_path=str(receipt),
            custody_released=entry._ADMISSION.released,
            coordinator=server.maintenance_admission.snapshot(),
            checkpoint_after=notification['owner'].checkpoint(certify_durable=True),
            complete_startup_body_executed=state['complete_startup_body_executed'])
    actual_release=admission.AdmissionCustody.release_ready
    def release(custody,server):
        event('R2.actual_ready_release_entered')
        try:
            value=actual_release(custody,server)
        except BaseException as error:
            state['failure_boundary']=boundary(server)
            state['release_error']=type(error).__name__+':'+str(error)
            output.with_suffix('.maintenance.json').write_text(json.dumps(export(),indent=2,default=str)+'\n')
            raise
        event('R2.actual_ready_release_completed',released=custody.released)
        permit.set()
        return value
    patch.setattr(admission.AdmissionCustody,'release_ready',release)
    actual_close=admission.AdmissionCustody._close
    def close(custody):
        if case=='R2-release-failure' and not custody.cleanup_started:
            event('R2.injected_ready_close_failure')
            raise OSError('R2_INJECTED_READY_CLOSE_FAILURE')
        return actual_close(custody)
    patch.setattr(admission.AdmissionCustody,'_close',close)
    actual_activate=IntradayNotifications._activate_replay
    def activate(self):
        assert entry._ADMISSION.released
        assert resources['server'].connection_governance.startup_state=='READY'
        value=actual_activate(self)
        state['activation_results'].append(value)
        event('R2.replay_activation',result=value)
        return value
    patch.setattr(IntradayNotifications,'_activate_replay',activate)

    def fail_before_complete(server,*args,**kwargs):
        assert accepted.is_set() and state.get('consumption_claim')
        assert server.connection_governance.startup_state=='NOT_ASSESSED'
        state['reference_files_at_pre_ready_barrier']=raw_files(refs)
        assert state['reference_files_at_pre_ready_barrier']==state['initial_reference_files']
        event('R2.before_complete_startup_body')
        pending=notification['owner']
        # Exercise all actual callable drain/scheduling paths while deferred.
        original_drain(pending)
        pending._drain_owned(None)
        pending._schedule()
        with pytest.raises(ValueError,match='WO13_REPLAY_NOT_ACTIVE'):
            pending._consume('READINESS',seed['readiness_identity'])
        assert state['consumed_references']==[] and state['fake_send_calls']==[]
        assert state['worker_submissions']==[]
        assert state['new_enqueues_during_canonical']==[]
        if case=='R2-pre-ready-failure':
            state['failure_boundary']=boundary(server)
            state['reference_files_before_failure']=raw_files(refs)
            state['centre_files_before_failure']=raw_files(centre_root)
            event('R2.failure_injected_before_complete_startup')
            output.with_suffix('.maintenance.json').write_text(json.dumps(export(),indent=2,default=str)+'\n')
            raise RuntimeError('R2_F01_INJECTED_PRE_READY_FAILURE')
        if case=='R2-return-without-ready':
            return None  # Return alone must not satisfy the real release gate.
        state['complete_startup_body_executed']=True
        if case=='R2-blocked-completion':
            kwargs['wo17']=dict(kwargs['wo17'],restoration_state='CORRUPT',failure_reason='R2_FIXTURE_RESTORATION_FAILED')
        value=actual_complete(server,*args,**kwargs)
        state['actual_completion_boundary']=boundary(server)
        return value
    patch.setattr(runtime_state,'complete_startup',fail_before_complete)
    def after_ready(server):
        assert case=='R2-healthy'
        assert entry._ADMISSION.released and server.connection_governance.startup_state=='READY'
        assert finished.wait(8),'R2_HEALTHY_REPLAY_COMPLETION_EXPIRED'
        assert not state['worker_errors'] and len(state['fake_send_calls'])==1
        assert len(state['worker_submissions'])==1
        assert notification['owner']._activate_replay() is False
        state['healthy_boundary']=boundary(server)
        output.with_suffix('.maintenance.json').write_text(json.dumps(export(),indent=2,default=str)+'\n')
    resources['R2-after-ready']=after_ready
    output.with_suffix('.fixture.json').write_text(json.dumps(export(),indent=2,default=str)+'\n')


@pytest.mark.parametrize('case',['R2-pre-ready-failure','R2-blocked-completion',
    'R2-return-without-ready','R2-release-failure','R2-healthy'])
def test_r2_f01_canonical_replay_activation_boundary(tmp_path,case):
    """Actual signed input, READY/release checks and R1 cleanup."""
    evidence=Path(__file__).resolve().parents[4]/'qualification'/'case-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700)
    held=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    read,write=os.pipe();output=evidence/'R2-F01.observations.json';child=os.fork()
    if child==0:
        os.close(read);os.dup2(write,2);os.close(write)
        _r1_child(case,anchor,held,output,r2_setup=_r2_f01_configure,r4_mode=dict(kind='f01'))
        os._exit(98)
    os.close(write);os.set_blocking(read,False);raw=bytearray();status=None
    try:
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if select.select([read],[],[],.1)[0]:
                try:raw.extend(os.read(read,65536))
                except BlockingIOError:pass
            pid,value=os.waitpid(child,os.WNOHANG)
            if pid:status=value;break
        (evidence/'R2-F01.stderr.log').write_bytes(raw)
        assert status is not None,raw.decode(errors='replace')
        assert output.exists(), output.with_suffix('.setup-error.txt').read_text() if output.with_suffix('.setup-error.txt').exists() else raw.decode(errors='replace')
        observed=json.loads(output.read_text());proof=observed['r2']
        code=os.waitstatus_to_exitcode(status)
        healthy=case=='R2-healthy'
        assert code==(0 if healthy else 78),observed
        boundary=proof['healthy_boundary' if healthy else 'failure_boundary']
        expected=('READY' if case in {'R2-healthy','R2-release-failure'} else
                  'BLOCKED' if case=='R2-blocked-completion' else 'NOT_ASSESSED')
        assert boundary['startup']['startup']==expected
        assert boundary['startup_receipt_present'] is (expected=='READY')
        assert proof['checkpoint_accepted']['expected']==proof['seed']['checkpoint']
        assert proof['checkpoint_accepted']['observed']==proof['seed']['checkpoint']
        assert proof['barriers']==dict(accepted=True,permit=healthy,finished=healthy)
        assert proof['new_enqueues_during_canonical']==[]
        assert proof['consumed_references']==([dict(kind='READINESS',identity=proof['seed']['readiness_identity'])] if healthy else [])
        assert [r['state'] for r in proof['delivery_states']]==(['ATTEMPTING','SENT'] if healthy else [])
        assert len(proof['fake_send_calls'])==int(healthy)
        assert proof['activation_results']==([True,False] if healthy else [])
        assert len(proof['worker_submissions'])==int(healthy)
        if healthy:assert proof['worker_submissions'][0]['custody_released']
        assert proof['source_files_unchanged']
        initial=proof['initial_reference_files'];after=proof['current_reference_files']
        if healthy:
            assert proof['notification_checkpoint']['pending_count']==0
            before_name,=initial;after_name,=after
            assert after_name==before_name.removesuffix('.pending')+'.done'
            assert after[after_name]['raw']==initial[before_name]['raw']
        else:
            assert proof['notification_checkpoint']==proof['seed']['checkpoint']
            assert after==initial
            assert proof['current_centre_files']==proof['initial_centre_files']
        assert proof['consumption_claim']['sha256']
        assert proof['current_consumption_claim']['exists']
        assert proof['current_consumption_claim']['raw']==proof['consumption_claim']['raw']
        assert proof['signed_handoff']['signature_verified'] and proof['signed_handoff']['signer_reaped']
        assert observed['custody']['released']
        # READY release is distinct from acknowledged failed-start cleanup.
        assert observed['custody']['cleanup_started'] is (not healthy)
        assert observed['custody']['cleanup_complete'] is (not healthy)
        assert observed['cleanup_failures']==[] and not observed['validation_unresolved']
        assert all(not r['alive'] for r in proof['notification_executor_workers'])
        assert observed['server']['socket_fd']==-1 and not observed['control']['exists']
        assert all(row['state'] in {'NOT_CREATED','CREATED_AND_CLEANED'} for row in observed['cleanup_ledger'].values())
        assert observed['bulk']['stop_requested'] and not observed['bulk']['thread_alive']
        names=[row['name'] for row in observed['events']]
        assert names.index('R2.V2_consumed')<names.index('R2.checkpoint_accepted_before_schedule')
        if healthy:
            assert names.index('R2.actual_ready_release_completed')<names.index('R2.worker_entered_real_drain')
        else:assert 'R2.worker_entered_real_drain' not in names
        assert not any(name.startswith('FORBIDDEN_') for name in names)
        # Child's reference closed legitimately, but the parent still holds its
        # original shared custody until this fixture's teardown closes it.
        assert not _r1_available(anchor)
        (evidence/'R2-F01.result.json').write_text(json.dumps(dict(
            case=case,correction='PASS',actual_child_exit=code,
            actual_canonical_entry_invocations=1,restoration_attempts=0,
            fake_send_calls=int(healthy),real_external_calls=0,
            original_checkpoint=proof['seed']['checkpoint'],
            final_checkpoint=proof['notification_checkpoint'],
            application_cleanup_proved=True,parent_reference_still_held=True),indent=2)+'\n')
    finally:
        teardown=status is None
        if teardown:os.kill(child,signal.SIGTERM);_,status=os.waitpid(child,0)
        os.close(read);os.close(held)
        (evidence/'R2-F01.teardown.json').write_text(json.dumps(dict(child=child,
            exit_code=os.waitstatus_to_exitcode(status),test_process_termination=teardown,
            teardown_is_not_application_cleanup=True,
            fixture_anchor_available_after_parent_close=_r1_available(anchor)),indent=2)+'\n')


@pytest.mark.parametrize('authority',[None,True,SimpleNamespace(released=True)])
def test_r2_canonical_activation_rejects_missing_boolean_or_metadata_custody(
        tmp_path,monkeypatch,authority):
    from tools import kronos_browser as entry
    from kronos.common import release_admission
    calls=[]
    owner=SimpleNamespace(_activate_replay=lambda:calls.append('activated'))
    g=governance(tmp_path,maintenance=GENERATION)
    g.complete_startup()
    assert g.startup_state=='READY'
    receipt=g.store.root/'maintenance'/(g.process.runtime_identity+'-startup.json')
    assert receipt.exists()
    monkeypatch.setattr(entry,'_ADMISSION',authority)
    monkeypatch.setattr(entry,'_admission_bootstrap',release_admission)
    with pytest.raises(ValueError,match='CUSTODY_UNAVAILABLE'):
        entry._activate_canonical_notifications(SimpleNamespace(intraday_notifications=owner,connection_governance=g))
    assert calls==[]


# R2-F02: real canonical K5 owners/timers/cleanup, signed fixture-only V2 input.
def _r2_f02_configure(entry, browser, admission, patch, resources, event,
                      anchor, descriptor, output):
    from datetime import UTC, datetime, timedelta
    from hashlib import sha256
    from zoneinfo import ZoneInfo
    from kronos.application.swing_refresh_reminder import (
        K5RefreshReminderStore, SwingK5RefreshReminderWorkflow, RefreshReminderState)
    from kronos.application.swing_ux10 import Ux10NotificationType, Ux10DeliveryState
    from tests.unit.application.test_swing_refresh_reminder import _ready
    mode = resources['K5-mode']
    _r2_f01_configure(entry, browser, admission, patch, resources, event,
                      anchor, descriptor, output)
    original_export = resources['R2-snapshot']
    state = next(c.cell_contents for c in original_export.__closure__
                 if isinstance(c.cell_contents, dict) and 'seed' in c.cell_contents)
    resources['R2-shared-state'] = state
    promotion = _ready(anchor.parent / 'k5-valid-native-promotion')
    start = time.monotonic()
    base = datetime(2026, 8, 17, 10, 14, 0, tzinfo=ZoneInfo('Asia/Kolkata'))
    clock_offset = [0.0]
    clock = lambda: base + timedelta(seconds=time.monotonic() - start + clock_offset[0])
    k5_root = anchor.parent / 'k5-retained'
    store = K5RefreshReminderStore(k5_root)
    seed = SwingK5RefreshReminderWorkflow(store, clock=clock, defer_execution=True)
    pending = seed.synchronize(promotion.run_identity, (promotion,),
                              {promotion.canonical_instrument:'NSE'}).records[0]
    assert pending.state is RefreshReminderState.PENDING
    seed.close(); assert seed.cleanup_complete()
    def raw_files(root):
        return {str(p.relative_to(root)):dict(sha256=sha256(p.read_bytes()).hexdigest(),
                    bytes=p.stat().st_size,raw=p.read_text())
                for p in sorted(root.rglob('*')) if p.is_file()}
    initial = raw_files(k5_root)
    state['k5'] = dict(mode=mode,lawful_input='Actual K5 synchronize from validated retained KR370 fixture',
        seed_files=initial,reminder_identity=pending.reminder_identity,
        due=pending.next_eligible_completed_1h_boundary.isoformat(),
        fake_sends=[],callbacks=[],activation=[],before_ready=None,
        fixture_seams=[
            'Inherited R1/R2 signed-V2 fixture: actual canonical entry/main, inherited disposable anchor custody, real stores, counted owners and R1 cleanup; native launcher exec is not exercised.',
            'Source-publication/signature admission and load-verification are explicit fixture seams; source snapshot and module hashes are retained, not claimed qualified.',
            'Valid matching Native/KR370 current projection supplies synthetic source identities; real reconcile_progression and K5 synchronize execute.',
            'Fixture clock crosses the retained due boundary during this attempt; actual Timer and UX10 delivery threads execute.',
            'Only external delivery uses a recording fake; no credentials, transport or production state.',
            'Named startup completion/release/activation failures are injected; successful READY/receipt/release and cleanup are never mocked successful.'])
    k5 = state['k5']; snapshot_state = state; done = threading.Event()
    original_init = SwingK5RefreshReminderWorkflow.__init__
    def owner_init(self, *args, **kwargs):
        args = (K5RefreshReminderStore(k5_root),) + args[1:]
        kwargs['clock'] = clock
        original_init(self, *args, **kwargs)
        resources['k5_owner'] = self
    patch.setattr(SwingK5RefreshReminderWorkflow, '__init__', owner_init)
    actual_fire = SwingK5RefreshReminderWorkflow._fire
    def fire(self, identity, token=None):
        row = dict(scheduled=token is not None,identity=identity,
            startup=resources['server'].connection_governance.startup_state,
            custody_released=entry._ADMISSION.released)
        k5['callbacks'].append(row)
        event('K5.callback_entry', **row)
        return actual_fire(self, identity, token)
    patch.setattr(SwingK5RefreshReminderWorkflow, '_fire', fire)
    original_reconcile = browser.KronosBrowserServer.reconcile_progression
    def matching_projection_reconcile(self):
        assessment = SimpleNamespace(
            status=SimpleNamespace(value='PROBABLE'),
            canonical_instrument=promotion.canonical_instrument,
            product_path=Path('NSE'),
            result_sha256=promotion.native_assessment_sha256,
            factual_boundaries=promotion.observation_boundaries,
            direction=promotion.direction,
            provider_provenance=promotion.provenance,
            calendar_provenance=promotion.provenance,
            policy_identity=promotion.policy_identity,
        )
        run = SimpleNamespace(run_identity=promotion.run_identity,
            assessments=(assessment,), observed_at=promotion.analysis_boundary)
        requirement = SimpleNamespace(thesis=SimpleNamespace(
            native_assessment_sha256=promotion.native_assessment_sha256))
        review = SimpleNamespace(native_run_identity=promotion.run_identity,
            requirement_for=lambda instrument: requirement if instrument==promotion.canonical_instrument else None,
            readiness_records=(), visual_v2_results=())
        self.application.opportunities_projection = lambda: (None, run)
        self.native_review.snapshot = lambda: review
        self.visual_v3.completed_for = lambda run_id, instrument: (
            SimpleNamespace(promotion=promotion,promotion_v2=None)
            if run_id==promotion.run_identity and instrument==promotion.canonical_instrument
            else None)
        event('K5.valid_current_projection_fixture_installed',
              run_identity=run.run_identity,
              assessment_sha256=assessment.result_sha256,
              promotion_sha256=promotion.integrity_sha256)
        result = original_reconcile(self)
        snapshot_state['k5']['reconciliation'] = dict(
            actual_method='KronosBrowserServer.reconcile_progression',
            run_identity=run.run_identity,
            k5_states=[r.state.value for r in self.refresh_reminders.snapshot().records],
            current_source_match=True)
        event('K5.actual_reconciliation_returned',
              k5_states=snapshot_state['k5']['reconciliation']['k5_states'])
        return result
    patch.setattr(browser.KronosBrowserServer, 'reconcile_progression',
                  matching_projection_reconcile)


    old_sender = browser._telegram_security
    def fake_sender(*args, **kwargs):
        wo13_sender = old_sender(*args, **kwargs)
        class Sender:
            def status(self):
                return SimpleNamespace(private_chat_configured=True, delivery_enabled=True)
            def send(self, text):
                if 'REFRESH ANALYSIS REMINDER' not in text:
                    return wo13_sender.send(text)
                row = dict(at=datetime.now(UTC).isoformat(),
                    startup=resources['server'].connection_governance.startup_state,
                    custody_released=entry._ADMISSION.released)
                k5['fake_sends'].append(row); event('K5.fake_send', **row); done.set()
                from kronos.integrations.telegram import TelegramDeliveryState
                return SimpleNamespace(state=TelegramDeliveryState.SENT)
        return Sender()
    patch.setattr(browser, '_telegram_security', fake_sender)
    from kronos.browser import runtime_state
    complete = runtime_state.complete_startup
    def boundary(server):
        receipt=server.connection_governance.store.root/'maintenance'/(server.connection_governance.process.runtime_identity+'-startup.json')
        return dict(startup=server.connection_governance.startup_state,
            receipt_exists=receipt.exists(),custody_released=entry._ADMISSION.released,
            custody_cleanup_started=entry._ADMISSION.cleanup_started,
            maintenance=server.maintenance_admission.snapshot())
    def before_complete(server, *args, **kwargs):
        # Cross this fixture's due boundary at the startup barrier, independent
        # of source-capture/setup duration. The Timer itself remains real.
        clock_offset[0] += max(0.0, (pending.next_eligible_completed_1h_boundary - clock()).total_seconds()) + .001
        assert not k5['fake_sends']
        assert raw_files(k5_root) == initial
        assert not server.refresh_reminders._timers
        # Callable direct/queued callback entries cannot bypass deferred state.
        server.refresh_reminders._fire(pending.reminder_identity)
        server.refresh_reminders._fire_owned(pending.reminder_identity)
        assert raw_files(k5_root) == initial and not k5['fake_sends']
        k5['before_ready'] = boundary(server)
        if mode == 'closed-before-release':
            server.refresh_reminders.close()
        event('K5.before_complete_startup', **k5['before_ready'])
        return complete(server, *args, **kwargs)
    patch.setattr(runtime_state, 'complete_startup', before_complete)
    actual_activate = SwingK5RefreshReminderWorkflow._activate_execution
    def activate(self):
        b=boundary(resources['server'])
        assert b['startup']=='READY' and b['receipt_exists'] and b['custody_released']
        result=actual_activate(self)
        k5['activation'].append(dict(result=result,boundary=b))
        event('K5.activation', **b)
        if mode=='post-release-activation-failure':
            assert done.wait(5)
            raise RuntimeError('K5_INJECTED_POST_RELEASE_ACTIVATION_FAILURE')
        return result
    patch.setattr(SwingK5RefreshReminderWorkflow, '_activate_execution', activate)
    original_after = resources['R2-after-ready']
    def after_ready(server):
        original_after(server)  # Also verifies R2-F01's actual replay after release.
        assert done.wait(5)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            rows=server.ux10_notifications.snapshot().records
            if any(r.notification_type is Ux10NotificationType.REFRESH_ANALYSIS_REMINDER
                   and r.telegram_delivery_state is Ux10DeliveryState.SENT for r in rows):
                break
            time.sleep(.01)
        else: raise AssertionError('K5_DELIVERY_THREAD_DID_NOT_COMPLETE')
        assert len(k5['fake_sends'])==1
        assert server.refresh_reminders._activate_execution() is False
        k5['healthy_boundary']=boundary(server)
    resources['R2-after-ready']=after_ready
    def export():
        result=original_export()
        owner=resources.get('k5_owner');server=resources.get('server')
        result['k5']=dict(k5,files=raw_files(k5_root),
            records=[] if owner is None else [dict(identity=r.reminder_identity,state=r.state.value,
                notification_identity=r.notification_identity) for r in owner.snapshot().records],
            owner_status=None if owner is None else owner.maintenance_status(),
            ux10_files={} if server is None or not hasattr(server,'ux10_notifications') else raw_files(server.ux10_notifications._store.root),
            final_boundary=None if server is None else boundary(server))
        return result
    resources['R2-snapshot']=export
@pytest.mark.parametrize('mode,base_case',[
    ('pre-ready-failure','R2-pre-ready-failure'),
    ('blocked','R2-blocked-completion'),
    ('absent-ready','R2-return-without-ready'),
    ('release-failure','R2-release-failure'),
    ('closed-before-release','R2-healthy'),
    ('healthy','R2-healthy'),
    ('post-release-activation-failure','R2-healthy')])
def test_r2_f02_actual_canonical_k5_boundary_and_cleanup(tmp_path,mode,base_case):
    evidence=Path(__file__).resolve().parents[4]/'qualification'/'case-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700)
    held=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    read,write=os.pipe();output=evidence/'R2-F02.observations.json'
    def setup(*args):
        args[4]['K5-mode']=mode
        return _r2_f02_configure(*args)
    child=os.fork()
    if child==0:
        os.close(read);os.dup2(write,2);os.close(write)
        _r1_child(base_case,anchor,held,output,r2_setup=setup,r4_mode=dict(kind='f02',mode=mode))
        os._exit(98)
    os.close(write);os.set_blocking(read,False);raw=bytearray();status=None
    try:
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if select.select([read],[],[],.1)[0]:
                try:raw.extend(os.read(read,65536))
                except BlockingIOError:pass
            pid,value=os.waitpid(child,os.WNOHANG)
            if pid:status=value;break
        (evidence/'R2-F02.stderr.log').write_bytes(raw)
        assert status is not None,raw.decode(errors='replace')
        assert output.exists(),output.with_suffix('.setup-error.txt').read_text() if output.with_suffix('.setup-error.txt').exists() else raw.decode(errors='replace')
        observed=json.loads(output.read_text());proof=observed['r2'];k5=proof['k5']
        code=os.waitstatus_to_exitcode(status)
        expected_exit = 0 if mode=='healthy' else 79 if mode=='post-release-activation-failure' else 78
        assert code==expected_exit,observed
        assert k5['before_ready']['startup']=='NOT_ASSESSED'
        assert not k5['before_ready']['custody_released']
        assert not k5['before_ready']['receipt_exists']
        activated=mode in {'healthy','post-release-activation-failure'}
        assert len(k5['fake_sends'])==int(activated)
        assert sum(a['result'] is True for a in k5['activation'])==int(activated)
        assert all(a['boundary']['startup']=='READY' and a['boundary']['receipt_exists']
                   and a['boundary']['custody_released'] for a in k5['activation'])
        scheduled=[row for row in k5['callbacks'] if row['scheduled']]
        assert len(scheduled)==int(activated)
        assert all(row['startup']=='READY' and row['custody_released'] for row in scheduled)
        if not activated:
            assert k5['files']==k5['seed_files']
            assert k5['records'][0]['state']=='PENDING'
            assert not any('REFRESH_ANALYSIS_REMINDER' in v['raw'] for k,v in k5['ux10_files'].items() if k.endswith('.json'))
        else:
            assert all(k5['files'].get(k)==v for k,v in k5['seed_files'].items())
            assert k5['records'][0]['state']=='SENT'
        assert k5['owner_status']['cleanup_complete'] is True
        assert k5['owner_status']['callbacks']==0 and k5['owner_status']['live_timers']==0
        assert observed['custody']['released']
        assert observed['custody']['cleanup_complete'] is (not activated)
        assert observed['cleanup_failures']==[]
        assert all(r['state'] in {'NOT_CREATED','CREATED_AND_CLEANED'} for r in observed['cleanup_ledger'].values())
        assert proof['signed_handoff']['signature_verified'] and proof['signed_handoff']['signer_reaped']
        assert proof['current_consumption_claim']['exists']
        assert proof['current_consumption_claim']['raw']==proof['consumption_claim']['raw']
        assert proof['source_files_unchanged']
        assert observed['server']['socket_fd']==-1 and not observed['control']['exists']
        assert not _r1_available(anchor)
        assert not any(e['name'].startswith('FORBIDDEN_') for e in observed['events'])
        (evidence/'R2-F02.result.json').write_text(json.dumps(dict(mode=mode,
            correction='PASS',child_exit=code,fake_k5_sends=len(k5['fake_sends']),
            real_external_calls=0,consumed_claim_preserved=True,
            cleanup_complete=True,custody_after=observed['custody'],
            before_ready=k5['before_ready'],after=k5['final_boundary']),indent=2)+'\n')
    finally:
        teardown=status is None
        if teardown:os.kill(child,signal.SIGTERM);_,status=os.waitpid(child,0)
        os.close(read);os.close(held)
        (evidence/'R2-F02.teardown.json').write_text(json.dumps(dict(child=child,
            exit_code=os.waitstatus_to_exitcode(status),test_process_termination=teardown,
            teardown_is_not_application_cleanup=True,
            anchor_available_after_parent_close=_r1_available(anchor)),indent=2)+'\n')


def _r2_ux10_configure(entry, browser, admission, patch, resources, event,
                       anchor, descriptor, output):
    """Exercise UX10 in the real canonical owner/custody sequence.

    The eligible watch is a deliberately synthetic service input installed
    after actual constructor reconciliation. This verifies delivery gating,
    not a lawful retained Native READY-to-NOW publication chain.
    """
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from kronos.application.swing_ux10 import (
        SwingUx10NotificationService, Ux10DeliveryState,
    )
    from kronos.integrations.telegram import TelegramDeliveryState
    from tests.unit.browser.test_browser_notifications import _triggered

    resources['K5-mode'] = resources['UX10-mode']
    _r2_f02_configure(entry, browser, admission, patch, resources, event,
                      anchor, descriptor, output)
    state = resources['R2-shared-state']
    ux = state.setdefault('ux10', dict(mode=resources['UX10-mode'],
        fixture_scope='synthetic eligible watch only; no Native READY-to-NOW chain claimed',
        events=[], sends=[], activation=[], initially_deferred=False,
        before_startup=None, after_startup=None))
    actual_reconcile = browser.KronosBrowserServer.reconcile_progression

    def reconcile_with_ux10_fixture(server):
        result = actual_reconcile(server)
        owner = server.ux10_notifications
        ux['initially_deferred'] = owner.delivery_deferred
        if not ux['events']:
            record = owner.observe_progression_watch(_triggered('CANBK'))
            assert record is not None
            assert record.telegram_delivery_state is Ux10DeliveryState.PENDING
            ux['events'].append(dict(identity=record.notification_id,
                deduplication_key=record.deduplication_key,
                state=record.telegram_delivery_state.value,
                attempts=record.delivery_attempts))
            assert owner.delivery_deferred
            assert not ux['sends']
            event('UX10.synthetic_event_retained_while_deferred',
                  notification_id=record.notification_id,
                  delivery_state=record.telegram_delivery_state.value)
        return result

    patch.setattr(browser.KronosBrowserServer, 'reconcile_progression',
                  reconcile_with_ux10_fixture)

    from kronos.browser import runtime_state
    previous_complete = runtime_state.complete_startup

    def verify_deferred_before_completion(server, *args, **kwargs):
        records = server.ux10_notifications.snapshot().records
        assert len(records) == 1
        assert records[0].telegram_delivery_state is Ux10DeliveryState.PENDING
        assert records[0].delivery_attempts == 0
        assert server.ux10_notifications.delivery_deferred
        assert not ux['sends']
        ux['before_startup'] = dict(startup=server.connection_governance.startup_state,
            custody_released=entry._ADMISSION.released,
            receipt_exists=any(server.connection_governance.store.root.glob(
                'maintenance/*-startup.json')),
            state=records[0].telegram_delivery_state.value,
            attempts=records[0].delivery_attempts)
        event('UX10.deferred_before_startup_completion', **ux['before_startup'])
        return previous_complete(server, *args, **kwargs)

    patch.setattr(runtime_state, 'complete_startup', verify_deferred_before_completion)

    old_sender_factory = browser._telegram_security

    def sender_factory(*args, **kwargs):
        other_sender = old_sender_factory(*args, **kwargs)

        class RecordingUx10Sender:
            def status(self):
                return SimpleNamespace(private_chat_configured=True,
                                       delivery_enabled=True)

            def send(self, text):
                if text.startswith('KRONOS · SWING'):
                    server = resources['server']
                    row = dict(at=datetime.now(UTC).isoformat(),
                        startup=server.connection_governance.startup_state,
                        custody_released=entry._ADMISSION.released,
                        text=text)
                    ux['sends'].append(row)
                    event('UX10.recording_fake_send', startup=row['startup'],
                          custody_released=row['custody_released'])
                    if 'REFRESH ANALYSIS REMINDER' in text:
                        # Preserve the existing K5 owning fixture's delivery
                        # observation while recording the actual UX10 worker.
                        return other_sender.send(text)
                    return SimpleNamespace(state=TelegramDeliveryState.SENT)
                return other_sender.send(text)

        return RecordingUx10Sender()

    patch.setattr(browser, '_telegram_security', sender_factory)
    actual_activate = SwingUx10NotificationService.activate_delivery

    def activate(self):
        server = resources['server']
        receipt = server.connection_governance.store.root / 'maintenance' / (
            server.connection_governance.process.runtime_identity + '-startup.json')
        boundary = dict(startup=server.connection_governance.startup_state,
            receipt_exists=receipt.exists(), custody_released=entry._ADMISSION.released,
            deferred=self.delivery_deferred)
        ux['activation'].append(boundary)
        event('UX10.activation_entered', **boundary)
        assert boundary['startup'] == 'READY' and boundary['receipt_exists']
        assert boundary['custody_released'] and boundary['deferred']
        if resources['UX10-mode'] == 'activation-failure':
            raise RuntimeError('UX10_INJECTED_POST_RELEASE_ACTIVATION_FAILURE')
        result = actual_activate(self)
        ux['activation'][-1]['result'] = result
        return result

    patch.setattr(SwingUx10NotificationService, 'activate_delivery', activate)

    old_after_ready = resources['R2-after-ready']

    def after_ready(server):
        old_after_ready(server)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            records = server.ux10_notifications.snapshot().records
            if records and records[0].telegram_delivery_state is Ux10DeliveryState.SENT:
                break
            time.sleep(.01)
        else:
            raise AssertionError('UX10_CANONICAL_DELIVERY_DID_NOT_COMPLETE')
        assert len(ux['sends']) == 2  # promotion fixture plus retained K5 reminder
        record = next(r for r in server.ux10_notifications.snapshot().records
                      if r.notification_type.value == 'PROMOTION_CONDITION_MET')
        ux['after_startup'] = dict(state=record.telegram_delivery_state.value,
            attempts=record.delivery_attempts,
            startup=server.connection_governance.startup_state,
            custody_released=entry._ADMISSION.released)
        event('UX10.delivery_completed', **ux['after_startup'])

    resources['R2-after-ready'] = after_ready

    old_export = resources['R2-snapshot']

    def export():
        result = old_export()
        server = resources.get('server')
        if server is not None:
            records = server.ux10_notifications.snapshot().records
            ux['records'] = [dict(identity=r.notification_id,
                type=r.notification_type.value,
                state=r.telegram_delivery_state.value,
                attempts=r.delivery_attempts,
                deduplication_key=r.deduplication_key) for r in records]
            ux['files'] = {str(p.relative_to(server.ux10_notifications._store.root)):
                p.read_text() for p in sorted(server.ux10_notifications._store.root.rglob('*.json'))}
            ux['maintenance'] = server.ux10_notifications.maintenance_status()
            ux['workers'] = [dict(name=t.name, alive=t.is_alive())
                for t in getattr(getattr(server.ux10_notifications, '_executor', None), '_threads', ())]
        result['ux10'] = ux
        return result

    resources['R2-snapshot'] = export


@pytest.mark.parametrize('mode,base_case', [
    ('pre-ready-failure', 'R2-pre-ready-failure'),
    ('blocked', 'R2-blocked-completion'),
    ('absent-ready', 'R2-return-without-ready'),
    ('release-failure', 'R2-release-failure'),
    ('healthy', 'R2-healthy'),
    ('activation-failure', 'R2-healthy'),
])
def test_r2_ux10_canonical_delivery_starts_only_after_ready_and_release(
        tmp_path, mode, base_case):
    """Actual canonical owner, store, worker and custody boundary; fake sender only."""
    evidence=Path(__file__).resolve().parents[4]/'qualification'/'case-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    anchor=tmp_path/'anchor';anchor.mkdir(mode=0o700)
    held=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    read,write=os.pipe();output=evidence/'R2-UX10.observations.json'
    def setup(*args):
        args[4]['UX10-mode']=mode
        return _r2_ux10_configure(*args)
    child=os.fork()
    if child==0:
        os.close(read);os.dup2(write,2);os.close(write)
        _r1_child(base_case,anchor,held,output,r2_setup=setup,r4_mode=dict(kind='ux10',mode=mode))
        os._exit(98)
    os.close(write);os.set_blocking(read,False);raw=bytearray();status=None
    try:
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            if select.select([read],[],[],.1)[0]:
                try:raw.extend(os.read(read,65536))
                except BlockingIOError:pass
            pid,value=os.waitpid(child,os.WNOHANG)
            if pid:status=value;break
        (evidence/'R2-UX10.stderr.log').write_bytes(raw)
        assert status is not None,raw.decode(errors='replace')
        assert output.exists(),output.with_suffix('.setup-error.txt').read_text() if output.with_suffix('.setup-error.txt').exists() else raw.decode(errors='replace')
        observed=json.loads(output.read_text());proof=observed['r2'];ux=proof['ux10']
        code=os.waitstatus_to_exitcode(status)
        expected_exit=0 if mode=='healthy' else 79 if mode=='activation-failure' else 78
        assert code==expected_exit,observed
        assert ux['initially_deferred'] is True
        assert ux['before_startup']['startup']=='NOT_ASSESSED'
        assert not ux['before_startup']['custody_released']
        assert not ux['before_startup']['receipt_exists']
        assert ux['before_startup']['state']=='PENDING'
        assert ux['before_startup']['attempts']==0
        assert len(ux['events'])==1
        activation_expected=mode in {'healthy','activation-failure'}
        assert len(ux['activation'])==int(activation_expected)
        if activation_expected:
            assert ux['activation'][0]['startup']=='READY'
            assert ux['activation'][0]['receipt_exists']
            assert ux['activation'][0]['custody_released']
            assert ux['activation'][0]['deferred']
        assert len(ux['sends'])==2*int(mode=='healthy')
        if mode=='healthy':
            assert all(row['startup']=='READY' and row['custody_released']
                       for row in ux['sends'])
            progression, = [r for r in ux['records'] if r['type']=='PROMOTION_CONDITION_MET']
            reminder, = [r for r in ux['records'] if r['type']=='REFRESH_ANALYSIS_REMINDER']
            assert progression['state']=='SENT' and progression['attempts']==1
            assert reminder['state']=='SENT' and reminder['attempts']==1
            assert ux['activation'][0]['result'] is True
        else:
            assert all(r['state']=='PENDING' and r['attempts']==0
                       for r in ux['records'])
        assert ux['files']
        assert observed['custody']['released']
        assert observed['cleanup_failures']==[]
        assert all(row['state'] in {'NOT_CREATED','CREATED_AND_CLEANED'}
                   for row in observed['cleanup_ledger'].values())
        assert observed['server']['socket_fd']==-1 and not observed['control']['exists']
        assert proof['current_consumption_claim']['exists']
        assert proof['current_consumption_claim']['raw']==proof['consumption_claim']['raw']
        assert not _r1_available(anchor)
        names=[row['name'] for row in observed['events']]
        if mode=='healthy':
            assert names.index('R2.actual_ready_release_completed') < names.index('UX10.activation_entered')
            assert names.index('UX10.activation_entered') < names.index('UX10.recording_fake_send')
        else:
            assert 'UX10.recording_fake_send' not in names
        if mode=='activation-failure':
            assert any('UX10_INJECTED_POST_RELEASE_ACTIVATION_FAILURE' in row.get('message','')
                       for row in observed.get('failures', [])) or code==79
            assert ux['before_startup']['receipt_exists'] is False
            assert ux['activation'][0]['receipt_exists'] is True
        (evidence/'R2-UX10.result.json').write_text(json.dumps(dict(
            mode=mode,actual_child_exit=code,ux10_sends=len(ux['sends']),
            application_cleanup_proved=True,consumed_handoff_preserved=True,
            custody_released=observed['custody']['released'],
            synthetic_event_fixture=True),indent=2)+'\n')
    finally:
        teardown=status is None
        if teardown:os.kill(child,signal.SIGTERM);_,status=os.waitpid(child,0)
        os.close(read);os.close(held)
        (evidence/'R2-UX10.teardown.json').write_text(json.dumps(dict(child=child,
            exit_code=os.waitstatus_to_exitcode(status),test_process_termination=teardown,
            teardown_is_not_application_cleanup=True,
            anchor_available_after_parent_close=_r1_available(anchor)),indent=2)+'\n')



def _e02_fresh_driver():
    """Adapt only disclosed fixture bindings/observations, not the real entry."""
    driver=_C03_F02_FRESH_ENTRY_DRIVER
    driver=driver.replace(" patch=pytest.MonkeyPatch();events=[];state['events']=events",
        " patch=pytest.MonkeyPatch();events=[];state['events']=events\n from kronos.browser.server import KronosBrowserServer\n actual_error=KronosBrowserServer.handle_error\n def request_error(owner,request,address):\n  import traceback\n  Path(data['evidence'],'request-error.log').write_text(traceback.format_exc()[-8000:])\n  return actual_error(owner,request,address)\n patch.setattr(KronosBrowserServer,'handle_error',request_error)")
    driver=driver.replace("g['APPROVED_BINDING']=g['AnchorBinding'](anchor,st.st_dev,st.st_ino,os.getuid())",
        "g['PERSISTENT_ANCHOR_BINDING']=json.dumps(data['persistent'],sort_keys=True,separators=(',',':')).encode()\n  g['APPROVED_BINDING']=g['AnchorBinding'](anchor,data['installation']['device'],st.st_ino,os.getuid())")
    driver=driver.replace("from kronos.common import legacy_bootstrap as b,release_admission as pinned\n",
        "from kronos.common import legacy_bootstrap as b,release_admission as pinned\n  pinned.PERSISTENT_ANCHOR_BINDING=g['_admission_bootstrap'].PERSISTENT_ANCHOR_BINDING\n  pinned.APPROVED_BINDING=pinned.AnchorBinding(Path(data['anchor']),data['installation']['device'],data['installation']['inode'],data['installation']['owner'])\n  b.ORDINARY_RESTART_POLICY=json.dumps(data['policy'],sort_keys=True,separators=(',',':')).encode()\n")
    driver=driver.replace("assert checkpoint==data['checkpoint']==state['accepted_checkpoint']",
        "assert checkpoint==data['checkpoint']\n  state['accepted_checkpoint']=checkpoint")
    driver=driver.replace("assert events[-1]=='POST_COMPLETION_RECHECK'","assert events[-1]=='READY_RECEIPT'")
    driver=driver.replace("application_cleanup_errors=[name+':'+type(error).__name__ for name,error in cleanup.errors])",
        "application_cleanup_errors=[name+':'+type(error).__name__ for name,error in cleanup.errors],normal_stop_ledger_complete=cleanup.complete(),normal_stop_ledger=cleanup.snapshot())")
    driver=driver.replace("result=actual_main(args);state['main_returned']=result;return result",
        "result=actual_main(['--port',str(data['port']),'--no-browser']);state['main_returned']=result;return result")
    driver=driver.replace("if data.get('native') and data['selection']=='native-R-healthy':",
        "if data.get('native') and data['selection']=='e02-restart':")
    driver=driver.replace("while not Path(data['teardown_marker']).exists():server.handle_request()",
        "from http.server import ThreadingHTTPServer\n     ThreadingHTTPServer.serve_forever(server,poll_interval=.01)")
    driver=driver.replace("return patch.setattr(args[0],args[1],served)",
        "def actual_service(server,**options):\n     from http.server import ThreadingHTTPServer\n     from tests.unit.browser.test_runtime01 import _s303_observe_checker_termination\n     _s303_observe_checker_termination(server,custody.budget)\n     original(server,**options)\n     events.append('ACTUAL_HTTP_SERVICE')\n     return ThreadingHTTPServer.serve_forever(server,poll_interval=.01)\n    return patch.setattr(args[0],args[1],actual_service)")
    needle=" actual_main,actual_create=g['main'],g['create_browser_server']\n"
    driver=driver.replace(needle,needle+" if data['selection']=='e02-first-failure':\n  from kronos.common.legacy_bootstrap import NativeStartupFacts\n  original_composed=NativeStartupFacts.composition_returned\n  def failed(owner,*args,**kwargs):\n   original_composed(owner,*args,**kwargs)\n   raise RuntimeError('E02_EXPLICIT_FIRST_ORDINARY_CHILD_FAILURE')\n  patch.setattr(NativeStartupFacts,'composition_returned',failed)\n")
    driver=driver.replace("   return state['main_returned']\n  finally:",
        "   return state['main_returned']\n  except BaseException:\n   import traceback\n   Path(data['evidence'],'fixture-failure.log').write_text(traceback.format_exc()[-8000:])\n   raise\n  finally:")
    return driver


@pytest.mark.parametrize('scenario',('clean-restart','first-child-failure','late-stop-publication',
    'terminal-prefix','current-durability-failure','interrupted-new-attempt','missing-owner','stale-control'))
def test_e02_actual_fresh_entry_counted_stop_and_restart(tmp_path,monkeypatch,record_property,scenario):
    """Actual native startup/stop and actual application owners, disposable only.

    This is engineering integration with signature/publication/path/authority
    seams. Device change is simulated enrollment metadata; no OS reboot occurs.
    """
    import shutil,subprocess,sys,time,http.client,select,threading
    from contextlib import closing
    from hashlib import sha256
    from datetime import UTC,datetime
    from tests.unit.common import test_legacy_bootstrap as setup
    from tests.unit.common import test_failed_successor_restore as fixture
    from tests.unit.tools.test_canonical_launcher import _e02_compile_installed_control,_e02_helper_shim
    from kronos.common import legacy_bootstrap as adapter
    source_root=Path(__file__).resolve().parents[3]
    c=setup._e02_installed_control(tmp_path,monkeypatch,device_delta=-1,
        anchor_path=tmp_path/'e02-home/Library/Application Support/KRONOS/runtime')
    evidence=source_root.parent/'qualification/e02-full-entry-evidence'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    # The original evidence scaffolding stays preserved. Only this unexecuted
    # disposable selected repository is extended to the actual candidate tree.
    shutil.copytree(source_root,c.repository,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache','*.pyc','*.pyo'))
    def git(*args):return subprocess.run(['/usr/bin/git',*args],cwd=c.repository,check=True,capture_output=True).stdout
    git('add','--force','--all');git('-c','user.name=E02 Fixture','-c','user.email=fixture@example.invalid','commit','-q','-m','exact E02 disposable candidate')
    revision=git('rev-parse','HEAD').decode().strip();tracked=[]
    for row in git('ls-files','-s','-z').split(b'\0'):
        if row:
            meta,path=row.split(b'\t',1);relative=path.decode()
            tracked.append(dict(path=relative,mode=meta.split()[0].decode(),sha256=sha256((c.repository/relative).read_bytes()).hexdigest()))
    tracked.sort(key=lambda row:row['path']);capture=[]
    for row in tracked:
        for prefix,package in [('src/kronos/','kronos'),('tools/','tools')]:
            if row['path'].startswith(prefix) and row['path'].endswith('.py'):
                parts=list(Path(row['path'][len(prefix):]).with_suffix('').parts)
                if parts[-1]=='__init__':parts.pop()
                capture.append(dict(module='.'.join([package,*parts]),path=row['path'],sha256=row['sha256']))
    capture.sort(key=lambda row:row['module'])
    source=dict(schema='KRONOS_RESTORATION_SOURCE_MANIFEST_V1',origin_url='git@github.com:imran/Project-Kronos.git',
        source_ref='refs/heads/maintenance/release-b-swing-ux',revision=revision,git_tree_oid=git('rev-parse','HEAD^{tree}').decode().strip(),files=tracked,capture=capture)
    fixture._put(c.source_manifest,source)
    target=dict(revision=revision,tree_sha256=sha256(adapter._canonical(tracked)).hexdigest(),
        source_manifest_sha256=sha256(c.source_manifest.read_bytes()).hexdigest(),
        pinned_capture_sha256=sha256(adapter._canonical([[r['module'],r['sha256']] for r in capture])).hexdigest(),
        origin_url=source['origin_url'],source_ref=source['source_ref'],artifact_manifest_sha256='0'*64)
    c.selection['target']=target;c.selection['source_manifest']=fixture._ref(c.source_manifest,'e02-source',c.source_manifest.read_bytes())
    artifact=json.loads(c.artifact_manifest.read_bytes());files={r['path']:r['sha256'] for r in tracked}
    artifact.update(source_revision=revision,source_launcher_sha256=files['tools/macos/kronos_launcher.c'],
        previous_tracked_binary_sha256=files['tools/macos/KRONOS.app/Contents/MacOS/KRONOS'],procedure_sha256=files['tools/macos/package_launcher.py'])
    c.artifact_manifest.write_bytes(adapter._canonical(artifact)+b'\n')
    port=json.loads(Path(os.environ['KRONOS_TEST_ISOLATION_MANIFEST']).read_text())['allowed_ports'][0]
    driver=evidence/'e02-fresh-entry-driver.py';driver.write_text(_e02_fresh_driver())
    payload=evidence/'entry-input.json';shim=evidence/'helper-and-entry-python'
    helper=_e02_helper_shim(c,c.repository,shim).split('\n',1)[1]
    script='#!'+sys.executable+'\nimport sys,runpy\narguments=sys.argv[1:]\n'
    script+="if len(arguments)>=3 and arguments[:2]==['-B','-c']:\n"
    script+='\n'.join(' '+line for line in helper.splitlines())+'\n'
    script+=" exec(arguments[2],{'__name__':'__main__'})\nelse:\n"
    script+=' sys.path[:0]='+repr([str(c.repository/'src'),str(c.repository)])+'\n'
    script+=' sys.argv=['+repr(str(driver))+','+repr(str(payload))+",'197']\n"
    script+=' runpy.run_path('+repr(str(driver))+",run_name='__main__')\n"
    shim.write_text(script);shim.chmod(0o755)
    binary=_e02_compile_installed_control(c,source_root,evidence,component=False,shim=shim,port=port)
    c.custody._close()
    checkpoint=dict(state='EMPTY',pending_count=0,sha256=sha256(b'').hexdigest())
    common=dict(repository=str(c.repository),anchor=str(c.anchor),installation=c.installation,
        persistent=c.persistent,policy=c.policy,image=str(binary),environment={},now=datetime.now(UTC).isoformat(),
        claim_path=str(evidence/'no-restoration-claim'),expected_capture=capture,
        expected_pinned_digest=target['pinned_capture_sha256'],integrated=True,native=True,
        port=port,work=str(evidence/'composition'),checkpoint=checkpoint)
    environment={k:v for k,v in os.environ.items() if not k.startswith(('KRONOS_NATIVE_','KRONOS_RESTORATION_','KRONOS_ORDINARY_'))}
    environment.pop('KRONOS_LAUNCH_MODE',None)
    environment['HOME']=str(c.anchor.parents[3])
    if scenario=='late-stop-publication':environment['E02_TEST_STOP_FAULT']='late'
    if scenario=='terminal-prefix':environment['E02_TEST_STOP_FAULT']='prefix'
    processes=[];stop_events=[];finished=False
    def retain(label):
        dest=evidence/'retained-runtime'/label;dest.mkdir(parents=True,exist_ok=True)
        for p in c.anchor.rglob('*'):
            if p.is_file():
                q=dest/p.relative_to(c.anchor);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
    def launch(label):
        stage=evidence/label;stage.mkdir()
        data=dict(common,evidence=str(stage),selection='e02-first-failure' if scenario=='first-child-failure' else 'e02-restart' if label=='second' else 'e02-first')
        payload_raw=(json.dumps(data,indent=2)+'\n').encode()
        payload.write_bytes(payload_raw)
        (stage/'entry-input.json').write_bytes(payload_raw)
        out=(stage/'native.stdout.log').open('w');err=(stage/'native.stderr.log').open('w')
        launch_environment=dict(environment)
        if label=='second' and scenario=='current-durability-failure':launch_environment['E02_TEST_CURRENT_DURABILITY_FAILURE']='deny'
        if label=='second' and scenario=='interrupted-new-attempt':launch_environment['E02_TEST_STOP_AFTER_RESERVE']='yes'
        parent=subprocess.Popen([str(binary)],env=launch_environment,stdout=out,stderr=err,text=True)
        processes.append((parent,out,err,stage))
        (stage/'native-command.json').write_text(json.dumps(dict(argv=[str(binary)],cwd=str(Path.cwd()),
            actual_parent_pid=parent.pid,entry_input_sha256=sha256(payload_raw).hexdigest(),
            fixture_environment={k:v for k,v in launch_environment.items() if k=='HOME' or k.startswith('E02_TEST_')},
            remaining_environment='Inherited unchanged from the isolated harness; not a new production binding'),indent=2)+'\n')
        deadline=time.monotonic()+110
        while True:
            head=json.loads((c.journal/'admission-head.json').read_bytes())
            if head['state']=='READY_COMPLETE':return parent,stage
            if label=='second' and scenario=='interrupted-new-attempt' and head['state']=='ORIGINAL_RESERVED':return parent,stage
            if (stage/'original-failure-traceback.log').exists() and scenario!='first-child-failure':
                pytest.fail((stage/'original-failure-traceback.log').read_text())
            if parent.poll() is not None:
                if scenario=='first-child-failure' or (label=='second' and scenario=='current-durability-failure'):return parent,stage
                pytest.fail((stage/'native.stderr.log').read_text())
            if time.monotonic()>=deadline:pytest.fail('E02 startup exceeded existing fixture deadline')
            time.sleep(.01)
    def safe_exit(parent,stage):
        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
        connection.request('POST','/control/exit',body=b'',headers={'Host':f'127.0.0.1:{port}','Origin':f'http://127.0.0.1:{port}'})
        response=connection.getresponse();body=response.read();connection.close()
        assert response.status==202,body
        deadline=time.monotonic()+15;stop_pid=None
        while time.monotonic()<deadline:
            head=json.loads((c.journal/'admission-head.json').read_bytes())
            if head['state']=='ORDINARY_STOP_INTENT':
                stop=json.loads((c.journal/(head['active_reservation_id']+'.json')).read_bytes())
                stop_pid=stop['parent']['pid'];break
            time.sleep(.001)
        assert stop_pid is not None,(stage/'native.stderr.log').read_text()
        with closing(select.kqueue()) as queue:
            event=select.kevent(stop_pid,filter=select.KQ_FILTER_PROC,flags=select.KQ_EV_ADD|select.KQ_EV_ENABLE|select.KQ_EV_ONESHOT,
                fflags=select.KQ_NOTE_EXIT|getattr(select,'KQ_NOTE_EXITSTATUS',0x04000000))
            queue.control([event],0,0)
            events=queue.control(None,1,max(0,deadline-time.monotonic()))
            assert len(events)==1 and events[0].ident==stop_pid
            stop_events.append(dict(pid=stop_pid,actual_wait_status=events[0].data,fflags=events[0].fflags,
                observation='ACTUAL_KERNEL_NOTE_EXITSTATUS; NOT WAITPID ON A NONCHILD'))
            expected_stop_exit=1 if scenario in {'late-stop-publication','terminal-prefix'} else 0
            assert os.waitstatus_to_exitcode(events[0].data)==expected_stop_exit,(stage/'native.stderr.log').read_text()
        assert parent.wait(timeout=max(1,deadline-time.monotonic()))==0,(stage/'native.stderr.log').read_text()
        owners=list(c.journal.glob('stop-*.owners.json'));terminals=list(c.journal.glob('stop-*.terminal.json'))
        assert owners and len(owners)==len(terminals)
        if scenario=='terminal-prefix':assert terminals[-1].read_bytes()==b'{"chi'
        assert not (c.anchor/'browser-backend-v1.control').exists()
        retain(stage.name+'-application-stop')
    try:
        parent,stage=launch('first')
        if scenario=='first-child-failure':
            assert parent.wait(timeout=10)==78,(stage/'native.stderr.log').read_text()
            assert json.loads((c.journal/'admission-head.json').read_bytes())['state']=='STOPPED'
            before=(c.journal/'admission-head.json').read_bytes()
            denied=subprocess.run([str(binary)],env=environment,capture_output=True,text=True,timeout=20)
            assert denied.returncode==93 and (c.journal/'admission-head.json').read_bytes()==before
            (evidence/'repeated-start-denied.json').write_text(json.dumps(dict(actual_exit=denied.returncode,stdout=denied.stdout,stderr=denied.stderr),indent=2)+'\n')
            assert not list(c.journal.glob('*.child-claimed.json')) and not list(c.journal.glob('incident-*.json'))
        else:
            safe_exit(parent,stage)
            first_stop=(c.journal/'admission-head.json').read_bytes()
            if scenario in {'missing-owner','stale-control'}:
                if scenario=='missing-owner':
                    owner=c.journal/(json.loads(first_stop)['active_reservation_id']+'.owners.json')
                    owner.rename(evidence/'preserved-original-missing-owner.json')
                else:
                    stale=c.anchor/'browser-backend-v1.control'
                    stale.write_bytes(b'EXPLICIT_SYNTHETIC_STALE_CONTROL_DENIAL_INPUT\n');stale.chmod(0o600)
                denied=subprocess.run([str(binary)],env=environment,capture_output=True,text=True,timeout=30)
                assert denied.returncode==95 and (c.journal/'admission-head.json').read_bytes()==first_stop
                assert len(list(c.journal.glob('original-*.child-start-reserved.json')))==1
                (evidence/'incomplete-state-restart-denial.json').write_text(json.dumps(dict(scenario=scenario,
                    actual_exit=denied.returncode,stdout=denied.stdout,stderr=denied.stderr,
                    synthetic_negative_input=True,original_bytes_preserved=True),indent=2)+'\n')
                finished=True;return
            if scenario=='terminal-prefix':
                denied=subprocess.run([str(binary)],env=environment,capture_output=True,text=True,timeout=30)
                assert denied.returncode==95 and (c.journal/'admission-head.json').read_bytes()==first_stop
                assert len(list(c.journal.glob('original-*.child-start-reserved.json')))==1
                (evidence/'partial-terminal-restart-denial.json').write_text(json.dumps(dict(actual_exit=denied.returncode,stdout=denied.stdout,stderr=denied.stderr),indent=2)+'\n')
                finished=True;return
            # Same approved release and original installation identity. A fresh
            # operation gets its own boot-bound budget; no old attempt is resumed.
            parent,stage=launch('second');assert (c.journal/'admission-head.json').read_bytes()!=first_stop
            if scenario in {'current-durability-failure','interrupted-new-attempt'}:
                if scenario=='interrupted-new-attempt':
                    os.kill(parent.pid,9)
                    assert parent.wait(timeout=10)==-9
                else:assert parent.wait(timeout=10)==79
                spent=(c.journal/'admission-head.json').read_bytes()
                assert json.loads(spent)['state']=='ORIGINAL_RESERVED'
                assert len(list(c.journal.glob('original-*.child-start-reserved.json')))==1
                denied=subprocess.run([str(binary)],env=environment,capture_output=True,text=True,timeout=30)
                assert denied.returncode==93 and (c.journal/'admission-head.json').read_bytes()==spent
                (evidence/'new-attempt-exclusion.json').write_text(json.dumps(dict(scenario=scenario,
                    actual_new_parent_exit=parent.returncode,replay_actual_exit=denied.returncode,
                    replay_stdout=denied.stdout,replay_stderr=denied.stderr,old_stop_uncertainty_preserved=True),indent=2)+'\n')
                finished=True;return
            safe_exit(parent,stage)
            assert len(list(c.journal.glob('original-*.child-start-reserved.json')))==2
            assert not list(c.journal.glob('*.child-claimed.json'))
        finished=True
        retain('final-application-outcome')
        record_property('e02_actual_application',json.dumps(dict(scenario=scenario,actual_capture_and_custody=True,
            actual_native_start_and_stop=True,actual_owner_cleanup=True,prospective_restart_only=True,
            simulated_enrollment_device_delta=-1,host_reboot_performed=False,stop_kernel_exits=stop_events,
            production_signature_publication_authority=False)))
    finally:
        retain('before-separate-fixture-teardown')
        records=[]
        forced_children=[]
        if not finished:
            owned={}
            for path in c.journal.glob('*.identified.json'):
                value=json.loads(path.read_bytes())
                if value.get('schema')=='KRONOS_NATIVE_CHILD_IDENTIFIED_V1':owned[value['child']['pid']]=value['child']['kernel_birth']
            for path in c.journal.glob('stop-*.json'):
                try:value=json.loads(path.read_bytes())
                except (ValueError,OSError):continue
                if value.get('phase')=='ORDINARY_STOP_INTENT':owned[value['parent']['pid']]=value['parent']['kernel_birth']
            for pid,birth in owned.items():
                try:
                    observed=adapter._observe_process(pid)
                    if observed['kernel_birth']!=birth:continue
                    with closing(select.kqueue()) as queue:
                        queue.control([select.kevent(pid,filter=select.KQ_FILTER_PROC,
                            flags=select.KQ_EV_ADD|select.KQ_EV_ONESHOT,
                            fflags=select.KQ_NOTE_EXIT|getattr(select,'KQ_NOTE_EXITSTATUS',0x04000000))],0,0)
                        os.kill(pid,15)
                        ended=queue.control(None,1,10)
                        if not ended:
                            os.kill(pid,9);ended=queue.control(None,1,5)
                        assert ended,'owned fixture child did not terminate'
                        forced_children.append(dict(pid=pid,actual_wait_status=ended[0].data,separate_fixture_teardown=True))
                except (ProcessLookupError,adapter.BootstrapError):
                    if not adapter._native_observed_absent({'pid':pid}):raise
                    forced_children.append(dict(pid=pid,observed_absent=True,actual_exit='UNAVAILABLE'))
        for p,out,err,stage in processes:
            forced=False
            if p.poll() is None:
                # Separate failed-test teardown cannot supply application proof.
                p.terminate();forced=True
            code=p.wait(timeout=15);out.close();err.close()
            records.append(dict(pid=p.pid,actual_exit=code,forced_fixture_teardown=forced,application_cleanup_claimed=False))
        (evidence/'separate-fixture-teardown.json').write_text(json.dumps(dict(application_scenario_completed=finished,owned_parents=records,
            observed_stop_custodian_exits=stop_events,forced_owned_children=forced_children),indent=2)+'\n')
