"""Shared runtime authority qualification with fake Providers and isolated stores."""
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest

from kronos.browser.runtime_state import complete_startup, decorate_html, status_document
from kronos.browser.server import KronosBrowserServer
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.application.swing_opportunities import ProviderConnectionState
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
            assert d['maintenance']['active'] and d['rest_authentication']=='DISCONNECTED'
            assert d['rest_capability']=='NOT_EXPOSED' and d['monitoring']['transport_state']=='IDLE'  # legacy fixture lacks the pure Provider projection
            assert d['browser_requests']['maximum']==32
    assert p.begin_count==0 and calls==[]
    assert inventory(root)==before


def test_service_loop_admits_intraday_pulse_without_executing_it_inline():
    server=object.__new__(KronosBrowserServer)
    lifecycle=SimpleNamespace(
        request_pulse=Mock(return_value=True),
        pulse=Mock(side_effect=AssertionError('service loop executed Intraday work')),
        last_failure=None,
    )
    server.intraday_lifecycle=lifecycle
    server.service_actions()
    lifecycle.request_pulse.assert_called_once_with()
    lifecycle.pulse.assert_not_called()


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


def test_slice8_compact_history_real_http_consumers_are_read_only(running, tmp_path, monkeypatch):
    from datetime import timedelta
    from tests.unit.swing.v1.test_observation_research_ledger_v2 import _selected_history_service, NOW
    from kronos.application.paper_observation_tracking import PaperObservationTrackingWorkflow
    from kronos.intraday.wo14_journal_contract import JournalSnapshot
    server, governance, provider, calls, root = running
    service, paper, track = _selected_history_service(tmp_path / 'selected')
    server.trade_window._observation_research_v2 = service
    server.trade_window._paper_observation_tracking = PaperObservationTrackingWorkflow(paper)
    server.intraday_journal = SimpleNamespace(snapshot=lambda **_: JournalSnapshot((), ()))
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
