"""Offline retained-source rehearsal. Fake transport only; no Provider or Telegram network."""
from datetime import timedelta
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from hashlib import sha256
import json
import os

from kronos.browser.intraday_wo08 import IntradayWo08Projection, render_machine_review
from kronos.browser.intraday_wo09_control import IntradayWo09Projection
from kronos.browser.dashboard import project_intraday_dashboard, project_sponsor_dashboard
from kronos.browser.views import render_dashboard, render_notifications, NotificationProduct, render_reports, render_settings
from kronos.application.notifications import NotificationWorkspaceSnapshot
from tests.unit.browser.test_product_route_isolation import _snapshot


def test_retained_98_source_graph_and_sponsor_surfaces(tmp_path,monkeypatch):
    from kronos.market.calendar import MarketCalendarPublisher
    from kronos.browser.intraday_futures_control import domain008_session
    from kronos.intraday.probables_v2 import ProbablesUnavailableMemberV2, ProbableReasonV2, evaluate_probables_v2_run
    from kronos.intraday.probables_v2_persistence import ProbablesV2Store
    from kronos.application.intraday_native_selection import NativePullbackPublication
    from kronos.intraday.native_structural_selection import NativeStructuralStore
    from kronos.application.intraday_wo08 import Wo08Publication
    from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
    from kronos.intraday.wo09_persistence import Wo09Store
    from kronos.intraday.wo12_research_store import ResearchStore
    from kronos.application.intraday_experimental_watch import GovernedExperimentalWatchCoordinator
    from kronos.application.intraday_wo09 import IntradayWo09Application
    from kronos.application.shared_monitoring import SharedSwingMonitoringHub
    from kronos.provider.contracts.instrument import InstrumentRecord
    from kronos.provider.contracts.monitoring import MonitoringConnectionState
    from tests.unit.application.test_shared_monitoring import Capability, Consumer
    from tests.unit.intraday.test_wo08_wo09_integration import graph
    from tests.unit.intraday.test_wo08_experimental import experimental_fixture, START
    from tests.unit.intraday.test_wo09_experimental import publish, origin_for
    import time
    started=time.monotonic()
    destination=os.environ.get('IWO_INT_REHEARSAL_OUTPUT')
    def progress(stage, **values):
        if destination:
            out=Path(destination);out.mkdir(parents=True,exist_ok=True)
            with (out/'progress.jsonl').open('a') as log:log.write(json.dumps(dict(stage=stage,seconds=time.monotonic()-started,**values),default=str)+'\n')
    calendar=MarketCalendarPublisher(); now=START+timedelta(minutes=135)
    session=domain008_session(calendar,'NSE-EQ-SAIL',now).schedule.session_id
    mappings=[];facts=[]
    catalogue=json.loads((Path(__file__).resolve().parents[3]/'data/intraday/KRONOS-INTRADAY-CANONICAL-RUNTIME-RECONCILIATION-V1/1.0.0.json').read_text())['members']
    subjects=[m['canonical_identity'] for m in catalogue if m['market_family']=='NSE_EQUITY']
    first=['NSE-EQ-SAIL','NSE-EQ-BAJAJ-AUTO','RELIANCE','NSE-EQ-INFY']
    subjects=first+[s for s in subjects if s not in first]
    assert len(subjects)==91
    for i,subject in enumerate(subjects):
        options = {}
        if i == 0: options['five_rows']=[(108,102,106)]*25+[(115,110,113),(117,114,116)]
        elif i == 1: options['daily']=(116,85,100.5)  # lawful I3-only outstanding
        elif i in (3,4):
            options.update(five_rows=[(108,102,106)]*25+[(115,110,113),(117,114,116)],daily=(118,92,105))  # I2 + I3 outstanding
        elif i == 5:
            options.update(five_rows=[(108,102,106)]*25+[(115,110,113),(117,114,116)],daily=(116,85,100.5))
        elif i >= 11: options['rows']=[(110,100,105)]*9  # no directional 15M qualification
        _,f,m,original,_,_=experimental_fixture('SHORT',subject=subject,
            session=domain008_session(calendar,subject,now).schedule.session_id,member='MEMBER'+str(i),**options)
        facts.append(f);mappings.append(m)
    missing=tuple(ProbablesUnavailableMemberV2('MISSING'+str(i),m['canonical_identity'],session,now,
        ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE,'DISCOVERY',('OFFLINE_REHEARSAL',))
        for i,m in enumerate(catalogue) if m['canonical_identity'] not in subjects)
    run=evaluate_probables_v2_run(source_discovery_run_identity='DISCOVERY',universe_identity='UNIVERSE',universe_version='1',
        reconciliation_identity='RECONCILIATION',reconciliation_version='1',market_session_identity=session,
        analysis_boundary=now,member_evidence=tuple(mappings),unavailable_members=missing,provenance=('OFFLINE_REHEARSAL',))
    progress('probables', counts=run.aggregate_counts if hasattr(run,'aggregate_counts') else [(r.canonical_subject_identity,r.state.value) for r in run.results])
    native=NativePullbackPublication(NativeStructuralStore(tmp_path/'native'),clock=lambda:now,commissioned_at=now)
    native.publish(run,tuple(mappings),facts=tuple(facts),newly_published=True)
    machine=Wo08Publication(Wo08AssessmentStore(tmp_path/'machine'))
    assessments=machine.publish_run(run=run,mapping=tuple(mappings),native_publication=native,published_at=now)
    progress('machine', count=len(assessments))
    probables=ProbablesV2Store(tmp_path/'probables');probables.retain_complete(run=run,mappings=tuple(mappings))
    _,_,boundary,_=graph(tmp_path/'boundary')
    store=Wo09Store(tmp_path/'wo09');research=ResearchStore(tmp_path/'research')
    boundary.wo09,boundary.probables,boundary.wo08,boundary.native=store,probables,machine.store,native.store
    boundary.calendar,boundary.clock,boundary.research=calendar,lambda:now,research
    app=IntradayWo09Application(store,eligibility=boundary)
    # Exercise the real shared lease; only the Provider transport is a fixture.
    from tests.unit.provider.test_shared_provider_runtime import _shared, _authenticate
    from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
    provider,provider_backend,_=_shared()
    wire=Capability()
    provider_backend.capability.open_monitoring_session=wire.open_monitoring_session
    _authenticate(provider)
    capability=provider.acquire_lease(consumer_identity='INTRADAY_REHEARSAL',
        operations=frozenset({ReadOnlyProviderOperation.MONITORING}))
    hub=SharedSwingMonitoringHub()
    def instrument(record):
        return InstrumentRecord('KITE','NSE','NSE',record.canonical_subject_identity.removeprefix('NSE-EQ-'),'REHEARSAL','EQ',None,Decimal('.05'),1),None
    watch=GovernedExperimentalWatchCoordinator(app,boundary=boundary,factual_source=None,clock=lambda:now,instrument_source=instrument)
    watch.hub,watch.capability_supplier=hub,lambda:capability
    records=[];origins={}
    for assessment in assessments:
        origin=origin_for(assessment) if assessment.data['probables_state'] in {'LONG_PROBABLE','SHORT_PROBABLE'} else None
        if origin is not None: research.retain(origin);origins[assessment.data['subject']]=origin
        record,requirements=publish(store,assessment,origin,now)
        records.append(record)
        if record.satisfied_count==4:watch.after_analysis(record,requirements)
    progress('readiness',count=len(records))
    sail=next(r for r in records if r.canonical_subject_identity=='NSE-EQ-SAIL')
    bajaj=next(r for r in records if r.canonical_subject_identity=='NSE-EQ-BAJAJ-AUTO')
    assert sail.satisfied_count==bajaj.satisfied_count==4
    assert watch.monitoring_projection(sail.readiness_identity)['state']=='UNAVAILABLE'
    live_instrument=instrument(bajaj)[0]
    owner=hub.open(capability,Consumer());owner.subscribe((live_instrument,));owner.connect()
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    watch.after_analysis(bajaj,store.load_requirements(bajaj.readiness_identity))
    assert watch.monitoring_projection(bajaj.readiness_identity)['state']=='ACTIVE'
    summary=lambda:project_intraday_dashboard(store,boundary,monitoring_projection=watch.monitoring_projection)
    readiness=IntradayWo09Projection(store,machine_successor=True,operational_summary=summary,monitoring_projection=watch.monitoring_projection)
    before={str(p.relative_to(tmp_path)):sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*.json')}
    status=IntradayWo08Projection(machine.store,probables).status_document()
    progress('before-projection')
    import time
    started=time.perf_counter()
    doc=readiness.status_document();html=render_machine_review(_snapshot(),status,doc)
    measured=[time.perf_counter()-started]
    if os.environ.get('IWO06C_OUTPUT'):
        from kronos.browser.intraday_wo08 import render_sponsor_opportunities
        timings={'review_first_seconds':measured[0],'scope':'Disposable real 98-member exact source/session/readiness stores; not production timing'}
        for surface,render in [('review',render_machine_review),('opportunities',render_sponsor_opportunities)]:
            samples=[]
            for _ in range(2):
                started=time.perf_counter()
                fresh_status=IntradayWo08Projection(machine.store,probables).status_document()
                fresh_readiness=readiness.status_document()
                render(_snapshot(),fresh_status,fresh_readiness)
                samples.append(time.perf_counter()-started)
            timings[surface+'_repeated_seconds']=samples
        (Path(os.environ['IWO06C_OUTPUT'])/'store-read-timings.json').write_text(json.dumps(timings,indent=2))
    progress('projection',summary=doc['operational_summary'],admitted=[(r['subject'],r['probables_state']) for r in status['assessments'] if r['probables_state'] in {'LONG_PROBABLE','SHORT_PROBABLE'}])
    if destination:(Path(destination)/'machine-review-production-shaped.html').write_text(html)
    assert 'Analysed</span><strong>98' in html and 'Considered</span><strong>11' in html, doc['operational_summary']
    assert 'Not Admitted</span><strong>80' in html and 'Unavailable</span><strong>7' in html
    assert '3/5' in html and 'READY' in html and 'NOW' in html and '5/5' in html
    base=project_sponsor_dashboard(_snapshot(),None,(),NotificationWorkspaceSnapshot(()))
    pages={'machine-review-production-shaped':html,'dashboard-production-shaped':render_dashboard(_snapshot(),replace(base,intraday=summary()))}
    after={str(p.relative_to(tmp_path)):sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*.json')}
    assert before==after
    from kronos.application.intraday_notification_sources import ready
    from kronos.application.intraday_notifications import IntradayNotifications
    from kronos.application.notification_centre import project_sponsor_notifications,SponsorNotificationQuery
    from tests.unit.intraday.test_wo13_notifications import centre, _NotificationSourceStore
    messages=[]
    transport=SimpleNamespace(status=lambda:SimpleNamespace(private_chat_configured=True,delivery_enabled=True),
        send=lambda text:(messages.append(text) or SimpleNamespace(state=SimpleNamespace(value='SENT'))))
    shared=centre(tmp_path/'notifications',now)
    notifications=IntradayNotifications(centre=shared,research=SimpleNamespace(store=research),wo09=store,
        futures=_NotificationSourceStore(),lifecycle=_NotificationSourceStore(),telegram=transport,background=False,
        monitoring_projection=watch.monitoring_projection)
    for record in (sail,bajaj):notifications._emit(ready(origins[record.canonical_subject_identity],record))
    for record in (sail,bajaj):notifications._emit(ready(origins[record.canonical_subject_identity],record))
    assert len(messages)==2 and 'Monitoring: ACTIVE' in messages[1] and 'Monitoring: UNAVAILABLE' in messages[0]
    centre_snapshot=shared.snapshot(product='INTRADAY')
    projection=project_sponsor_notifications(centre_snapshot,SponsorNotificationQuery())
    indicators={r.notification_identity:notifications.indicator(json.loads(r.intraday_details)) for r in centre_snapshot.records}
    pages['notifications-production-shaped']=render_notifications(_snapshot(),NotificationWorkspaceSnapshot(()),
        selected_product=NotificationProduct.INTRADAY,operational=projection,intraday_indicators=indicators)
    # Canonical GET seams must be observational even if action-time validation
    # would discover an expired Provider session and revoke shared leases.
    from tests.unit.browser.test_browser_swing_notifications_correction import browser,inventory
    from tests.unit.browser.test_browser_server import _request
    from tests.unit.browser.test_intraday_wo08_browser import _routes
    from kronos.browser.product_routes import ProductBrowserRoutes
    from kronos.provider.models.authentication import AuthenticatedContextState
    from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
    import kronos.application.intraday_evidence_currentness as boundary_module
    import kronos.intraday.wo09_experimental as experimental_module
    import kronos.intraday.wo09_machine_readiness as machine_module
    calls=[]
    http_routes=[]
    def forbidden(*args,**kwargs):
        calls.append('FORBIDDEN_PROVIDER_OR_EVALUATOR_CALL')
        raise AssertionError('status GET invoked Provider synchronization or readiness evaluation')
    provider_backend.context_state=AuthenticatedContextState.EXPIRED
    with browser(tmp_path/'http') as (server,_,_):
        server.product_routes=ProductBrowserRoutes((_routes(tmp_path/'routes',
            IntradayWo08Projection(machine.store,probables),run,wo09_projection=readiness),))
        server.intraday_dashboard_summary=summary
        server.notification_centre=shared
        server.intraday_notifications=notifications
        server.swing_monitoring_hub=hub
        server.provider_runtime=provider
        sources_before=inventory(tmp_path)
        provider_before=provider.read_only_status()
        owners_before=hub.status_document()
        with monkeypatch.context() as guard:
            guard.setattr(boundary,'_source',forbidden)
            guard.setattr(boundary,'_machine_source',forbidden)
            guard.setattr(boundary_module,'evaluate_experimental_readiness',forbidden)
            guard.setattr(boundary_module,'evaluate_readiness',forbidden)
            guard.setattr(experimental_module,'evaluate_experimental_readiness',forbidden)
            guard.setattr(machine_module,'evaluate_machine_readiness',forbidden)
            guard.setattr(provider_backend,'session_status',forbidden)
            guard.setattr(SharedAuthenticatedProviderRuntime,'_SharedAuthenticatedProviderRuntime__synchronize_locked',forbidden)
            guard.setattr(SharedAuthenticatedProviderRuntime,'_SharedAuthenticatedProviderRuntime__revoke_locked',forbidden)
            def get(route):
                http_routes.append(route)
                from http.client import HTTPConnection
                connection=HTTPConnection('127.0.0.1',server.server_port,timeout=30)
                connection.request('GET',route)
                response=connection.getresponse()
                page=response.read().decode()
                connection.close()
                assert response.status==200,(route,response.status)
                return page
            for route in ('/dashboard','/intraday','/intraday/review','/intraday/wo09',
                          '/notifications/intraday','/notifications/status?product=INTRADAY')*2:
                page=get(route)
                if route in {'/dashboard','/intraday','/intraday/review','/notifications/intraday'}:
                    assert 'ACTIVE' in page and 'UNAVAILABLE' in page
            assert watch.monitoring_projection(bajaj.readiness_identity)['state']=='ACTIVE'
            assert watch.runtime_status_document()['attached_observers']==1
            assert provider.read_only_status()==provider_before
            # The Native record/current binding alone cannot establish exact
            # source authority. Reproduce the reviewer's complete98 corruption
            # probe under a real owner + passive observer, with all GET traps on.
            live_native=native.store.load(bajaj.assessment_document['native_decision_identity'])
            companion=native.store.root/'sources'/(live_native.data['native_source_identity']+'.json')
            original_companion=companion.read_bytes()
            other_native=native.store.load(sail.assessment_document['native_decision_identity'])
            other_companion=native.store.root/'sources'/(other_native.data['native_source_identity']+'.json')
            wrong_companion=other_companion.read_bytes()
            assert wrong_companion!=original_companion
            native_failures=[]
            for fault in ('corrupt','missing','wrong_valid_source'):
                try:
                    if fault=='missing': companion.unlink()
                    else: companion.write_bytes(b'{}' if fault=='corrupt' else wrong_companion)
                    damaged_before=inventory(tmp_path)
                    failed=watch.monitoring_projection(bajaj.readiness_identity)
                    assert (failed['state'],failed['reason_code'])==('UNAVAILABLE','WATCH_AUTHORITY_UNAVAILABLE'),(fault,failed)
                    for route in ('/dashboard','/intraday/review','/notifications/status?product=INTRADAY'):
                        get(route)
                    assert watch.monitoring_projection(bajaj.readiness_identity)['state']=='UNAVAILABLE'
                    assert provider.read_only_status()==provider_before
                    assert hub.status_document()==owners_before
                    assert inventory(tmp_path)==damaged_before
                    native_failures.append(fault)
                finally:
                    companion.write_bytes(original_companion)
                assert watch.monitoring_projection(bajaj.readiness_identity)['state']=='ACTIVE'
                assert inventory(tmp_path)==sources_before
            from tests.unit.provider.test_shared_provider_runtime import VALID_THROUGH
            original_clock=provider._SharedAuthenticatedProviderRuntime__clock
            for lease_clock in (VALID_THROUGH,VALID_THROUGH.replace(tzinfo=None)):
                guard.setattr(provider,'_SharedAuthenticatedProviderRuntime__clock',lambda:lease_clock)
                retained_before=provider.read_only_status()
                assert retained_before['retained_lease_count']==1
                for route in ('/dashboard','/intraday/review','/notifications/status?product=INTRADAY')*2:
                    get(route)
                    assert watch.monitoring_projection(bajaj.readiness_identity)['state']=='UNAVAILABLE'
                    assert watch.runtime_status_document()['attached_observers']==0
                assert provider.read_only_status()==retained_before
                assert hub.status_document()==owners_before
                assert inventory(tmp_path)==sources_before
            guard.setattr(provider,'_SharedAuthenticatedProviderRuntime__clock',original_clock)
            assert provider.read_only_status()==provider_before
            assert hub.status_document()==owners_before
            assert inventory(tmp_path)==sources_before
        assert calls==[]
    from tests.unit.intraday.test_wo1516_books import fixture,projection as reports_projection
    books,*_=fixture(tmp_path/'books');pages['reports-paper']=render_reports(_snapshot(),reports_projection(books))
    assert 'Live trading is not enabled' in pages['reports-paper']
    from kronos.configuration.openai_chart_analyst import ChartAnalystConnectionStatus,ChartAnalystV2ActivationStatus
    from kronos.application.live_monitoring_e2e import LiveMonitoringTestResult,LiveMonitoringTestState
    pages['settings']=render_settings(_snapshot(),ChartAnalystConnectionStatus.NOT_CONFIGURED,ChartAnalystV2ActivationStatus.DISABLED,
        LiveMonitoringTestResult(LiveMonitoringTestState.PASS,instrument='SAIL',market_data_received=True,domain_002_accepted=True,observed_at=now))
    assert 'does not establish an active opportunity watch' in pages['settings']
    destination=os.environ.get('IWO_INT_REHEARSAL_OUTPUT')
    if destination:
        out=Path(destination);out.mkdir(parents=True,exist_ok=True)
        for name,page in pages.items():(out/(name+'.html')).write_text(page)
        (out/'intercepted-telegram.txt').write_text('\n\n'.join(messages))
        (out/'rehearsal.json').write_text(json.dumps(dict(population=98,considered=11,not_admitted=80,unavailable=7,
            now=summary().now,ready=summary().ready,states=['ACTIVE','INACTIVE','UNAVAILABLE'],
            telegram_intercepted=len(messages),real_telegram=0,provider_acquisition=0,historical_source_bytes_unchanged=before==after,
            actual_shared_provider_lease=True,inert_http_gets=len(http_routes),provider_status_sync_revoke_calls=len(calls),
            native_source_fail_closed_cases=native_failures,
            expired_and_unavailable_gets_preserve_lease_and_owners=True),indent=2))
    assert not capability.active  # unchanged action-time expiry/revocation
    assert not capability.read_only_active
    notifications.close();watch.shutdown();owner.disconnect()


def test_rehearsal_nonadmission_fixture():
    from tests.unit.intraday.test_wo08_experimental import experimental_fixture
    sample=experimental_fixture('SHORT',rows=[(110,100,105)]*9)
    assert sample[3].results[0].state.value=='NOT_ADMITTED',sample[3].results[0].state
    three=experimental_fixture('SHORT',five_rows=[(108,102,106)]*25+[(115,110,113),(117,114,116)],daily=(116,85,100.5))[-1]
    assert sum(c['state']=='SATISFIED' for c in three.data['criteria'])==3
