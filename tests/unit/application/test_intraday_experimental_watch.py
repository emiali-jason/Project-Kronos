"""Production-shaped completed evidence and zero-acquisition advisory watches."""
from datetime import timedelta
from dataclasses import replace
from decimal import Decimal

import pytest

from kronos.application.intraday_experimental_watch import (
    IntradayExperimentalWatchCoordinator, ExperimentalWatchStore, BINDING, HINT, watch_eligible,
)
from kronos.application.intraday_wo09 import IntradayWo09Application
from kronos.intraday.wo09_experimental import evaluate_experimental_readiness
from kronos.intraday.wo09_persistence import Wo09Store
from kronos.intraday.wo09_watch import WatchState
from kronos.intraday.wo12_research_contract import opportunity_origin
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import ProviderMarketTick, MonitoringConnectionState
from tests.unit.intraday.test_wo08_experimental import experimental_fixture
from tests.unit.application.test_shared_monitoring import Capability, Consumer, ONE, TWO, tick
from kronos.application.shared_monitoring import SharedSwingMonitoringHub


def setup_watch(tmp_path, direction='LONG', *, kind='I2', **fixture):
    if kind == 'I2':
        fixture.setdefault('five_rows', [(108,102,106)]*25+[(115,110,113),(117,114,116)])
    if kind == 'I3':
        fixture.setdefault('daily', (116,85,100.5))
    *_, assessment = experimental_fixture(direction, **fixture)
    d = assessment.data
    at = __import__('datetime').datetime.fromisoformat(d['created_at'])
    origin = opportunity_origin(canonical_subject_identity=d['subject'],market_family=d['market_family'],
        session_identity=d['session_identity'],origin_at=at,
        probable_result_identity=d['probable_result_identity'],probables_run_identity=d['run_identity'])
    readiness, requirements = evaluate_experimental_readiness(assessment, observed_at=at, origin=origin)
    store = Wo09Store(tmp_path)
    store.retain(readiness, requirements, expected=store.expectation(d['subject']))
    app = IntradayWo09Application(store)
    clock = [at]
    current = [True]
    watch = IntradayExperimentalWatchCoordinator(app, clock=lambda: clock[0],current_binding=lambda _: current[0])
    instrument = InstrumentRecord('KITE','NSE','NSE','TEST','TEST','EQ',None,Decimal('0.05'),1)
    expiry = at + timedelta(hours=1)
    bindings = watch.synchronize(readiness,requirements,session_expires_at=expiry,instrument=instrument)
    return watch, readiness, requirements, bindings, clock, current, instrument, expiry


@pytest.mark.parametrize('direction',['LONG','SHORT'])
@pytest.mark.parametrize('kind',['I2','I3'])
def test_selective_watch_advisory_coalescing_restart_and_expiry(tmp_path,direction,kind):
    watch,r,req,bindings,clock,current,instrument,expiry = setup_watch(tmp_path,direction,kind=kind)
    assert watch_eligible(r) and len(bindings)==1
    b = bindings[0]
    assert b['missing_criterion']==kind and b['opportunity_identity']==r.opportunity_identity
    assert b['assessment_identity']==r.wo08_identity
    price = Decimal(b['hint_levels'][kind]) + (Decimal('.1') if direction=='LONG' else Decimal('-.1'))
    clock[0] += timedelta(seconds=1)
    t = ProviderMarketTick(instrument,price,clock[0],clock[0],'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True)
    hint = watch.on_tick(t)
    assert len(hint)==1 and hint[0]['state']=='ADVISORY_WAKE_HINT'
    assert watch.wo09.store.load_readiness(r.readiness_identity)==r
    assert watch.wo09.store.load_notifications()==()
    clock[0] += timedelta(seconds=1)
    assert watch.on_tick(replace(t,observed_at=clock[0],received_at=clock[0],source_sequence=2))==hint
    restored = IntradayExperimentalWatchCoordinator(IntradayWo09Application(Wo09Store(tmp_path)),
        clock=lambda: clock[0], current_binding=lambda _: current[0])
    assert restored.restore()==bindings
    assert restored.synchronize(r,req,session_expires_at=expiry,instrument=instrument)==bindings
    assert len(restored.store.records(HINT))==1 and len(restored.wo09.store.load_watches())==1
    clock[0]=expiry
    assert restored.restore()==()
    assert restored.wo09.store.load_watches()[0].state is WatchState.STALE
    assert restored.on_tick(replace(t,observed_at=clock[0],received_at=clock[0]))==()


@pytest.mark.parametrize('fixture',[
    dict(five_rows=[(108,102,106)]*25+[(115,110,113),(121,114,120)]), # I2+I5
    dict(missing_five=(26,)), # unavailable
    dict(daily=(116,85,100)), # exact nonadmission hard gate
    dict(five_rows=[(108,102,106)]*25+[(115,110,114),(121,114,120)]), # I5
])
def test_noneligible_populations_never_watch(tmp_path,fixture):
    watch,r,_,bindings,*_ = setup_watch(tmp_path,**fixture)
    assert not watch_eligible(r) and bindings==()
    assert watch.wo09.store.load_watches()==()


@pytest.mark.parametrize('change',[dict(recovered=True),dict(session_continuous=False),
    dict(previous_interval_available=False),dict(ordering_deterministic=False)])
def test_gap_and_recovered_ticks_stale_without_hint(tmp_path,change):
    watch,r,req,b,clock,current,instrument,expiry=setup_watch(tmp_path)
    clock[0]+=timedelta(seconds=1)
    t=ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True)
    assert watch.on_tick(replace(t,**change))==()
    assert watch.wo09.store.load_watches()[0].state is WatchState.STALE
    assert watch.synchronize(r,req,session_expires_at=expiry,instrument=instrument)==()


def test_wrong_contract_equal_time_and_source_generation_fail_closed(tmp_path):
    watch,r,req,b,clock,current,instrument,expiry=setup_watch(tmp_path)
    t=ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True)
    assert watch.on_tick(t)==()
    clock[0]+=timedelta(seconds=1)
    assert watch.on_tick(replace(t,instrument=replace(instrument,trading_symbol='WRONG'),observed_at=clock[0],received_at=clock[0]))==()
    current[0]=False
    assert watch.restore()==()
    current[0]=True
    assert watch.restore()==() # no resurrection


def test_watch_bytes_tampering_fails_closed(tmp_path):
    watch,*_=setup_watch(tmp_path)
    p=next((watch.store.root/'binding').glob('*.json'))
    p.write_text(p.read_text().replace('ADVISORY_ONLY','POSITIVE'))
    with pytest.raises(ValueError,match='INTEGRITY'):
        watch.restore()


def test_passive_shared_observer_never_connects_or_keeps_transport_alive():
    hub,capability=SharedSwingMonitoringHub(),Capability()
    with pytest.raises(ValueError,match='EXISTING_SUBSCRIPTION_REQUIRED'):
        hub.observe_existing(capability,Consumer(),(ONE,))
    assert capability.sessions==[]
    owner=hub.open(capability,Consumer());owner.subscribe((ONE,));owner.connect()
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    consumer=Consumer();observer=hub.observe_existing(capability,consumer,(ONE,))
    session=capability.sessions[0]
    assert observer.active and session.connections==1 and session.subscribed==[(ONE,)]
    assert hub.subscription_reference_count(ONE)==1
    hub.on_market_tick(tick(ONE));assert len(consumer.ticks)==1
    with pytest.raises(ValueError,match='CONNECT_FORBIDDEN'): observer.connect()
    with pytest.raises(ValueError,match='IMMUTABLE'): observer.subscribe((TWO,))
    owner.disconnect()
    assert session.disconnections==1 and not observer.active
    observer.disconnect()
    assert session.disconnections==1 and len(capability.sessions)==1


def test_passive_shared_observer_does_not_restore_after_disconnect():
    hub,capability=SharedSwingMonitoringHub(),Capability()
    owner=hub.open(capability,Consumer());owner.subscribe((ONE,));owner.connect()
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    consumer=Consumer();observer=hub.observe_existing(capability,consumer,(ONE,))
    hub.on_connection_state(MonitoringConnectionState.DISCONNECTED)
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    hub.on_market_tick(tick(ONE))
    assert not observer.active and consumer.ticks==[]


def test_equal_time_stale_wins_and_cannot_restore(tmp_path):
    watch,r,req,bindings,clock,current,instrument,expiry=setup_watch(tmp_path)
    watch.on_disconnect(at=clock[0])
    assert watch.wo09.store.load_watches()[0].state is WatchState.STALE
    assert watch.restore()==()
    assert watch.synchronize(r,req,session_expires_at=expiry,instrument=instrument)==()


def canonical_adapter(watch,clock):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from kronos.application.intraday_experimental_watch import GovernedExperimentalWatchCoordinator
    boundary=SimpleNamespace(_sources=lambda r:nullcontext(),_source=lambda r,op:None,
        _session=lambda r,op:None,retained_monitoring_source=lambda r:None)
    return GovernedExperimentalWatchCoordinator(watch.wo09,boundary=boundary,
        factual_source=None,clock=lambda:clock[0])


def test_maintenance_fence_blocks_all_passive_writes(tmp_path):
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    watch,r,req,bindings,clock,current,instrument,expiry=setup_watch(tmp_path)
    adapter=canonical_adapter(watch,clock)
    adapter.maintenance=MaintenanceAdmissionCoordinator()
    assert adapter.maintenance.claim('a'*64)
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    clock[0]+=timedelta(seconds=1)
    t=ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True)
    assert adapter.on_tick(t)==adapter.on_disconnect()==adapter.restore()==()
    assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}


@pytest.mark.parametrize('explicit_restore', [False, True])
def test_empty_denied_startup_allows_fresh_analysis_after_admission_resumes(tmp_path, explicit_restore):
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    watch,r,req,_,clock,_,instrument,expiry=setup_watch(tmp_path/'seed')
    empty=IntradayExperimentalWatchCoordinator(IntradayWo09Application(Wo09Store(tmp_path/'empty')),
        clock=lambda:clock[0],current_binding=lambda _:True)
    adapter=canonical_adapter(empty,clock)
    adapter._session_instrument=lambda _: (expiry,instrument)
    fenced=MaintenanceAdmissionCoordinator()
    assert fenced.claim('a'*64)
    assert adapter.bind_monitoring(None,None,fenced)==()
    assert adapter._interrupted and adapter.store.records(BINDING)==()
    # The resumed runtime supplies its open admission owner; no maintenance
    # internals or persisted watch authority are reset by this transition.
    adapter.maintenance=MaintenanceAdmissionCoordinator()
    if explicit_restore:
        assert adapter.restore()==() and not adapter._interrupted
    adapter.wo09.store.retain(r,req,expected=adapter.wo09.store.expectation(r.canonical_subject_identity))
    created=adapter.after_analysis(r,req)
    assert len(created)==1 and not adapter._interrupted
    assert adapter.wo09.store.load_watches()[0].state is WatchState.ACTIVE
    assert adapter.restore()==created


def test_subject_restore_after_gap_retires_all_subjects_before_fresh_analysis(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    from kronos.intraday.wo09_experimental import origin_from
    watch,first,req1,b1,clock,_,instrument,expiry=setup_watch(tmp_path)
    _,second,req2,b2,*_=setup_watch(tmp_path,subject='NSE-EQ-RELIANCE')
    adapter=canonical_adapter(watch,clock)
    adapter._session_instrument=lambda _: (expiry,instrument)
    registrations={b['identity']:SimpleNamespace(active=True,advisory_failure=None,disconnect=Mock())
        for b in b1+b2}
    adapter.registrations=dict(registrations)
    adapter._queue_instruments={identity:instrument for identity in registrations}
    adapter.maintenance=MaintenanceAdmissionCoordinator()
    assert adapter.maintenance.claim('b'*64)
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    assert adapter.restore(subject=first.canonical_subject_identity)==()
    assert adapter._interrupted
    assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    adapter.maintenance=MaintenanceAdmissionCoordinator()
    clock[0]+=timedelta(seconds=1)
    assert adapter.restore(subject=first.canonical_subject_identity)==()
    assert not adapter._interrupted and not adapter.registrations and not adapter._queue_instruments
    assert {w.state for w in adapter.wo09.store.load_watches()}=={WatchState.STALE}
    assert len(adapter.wo09.store.load_watches())==2
    for registration in registrations.values():
        registration.disconnect.assert_called_once_with()
    assert adapter.after_analysis(first,req1)==adapter.after_analysis(second,req2)==()
    assert adapter.restore()==()  # neither old subject regains authority
    assessment=experimental_fixture(five_rows=[(108,102,106)]*25+[(115,110,113),(117,114,116.5)])[-1]
    successor,requirements=evaluate_experimental_readiness(assessment,observed_at=clock[0],
        origin=origin_from(first.origin_document))
    adapter.wo09.store.retain(successor,requirements,
        expected=adapter.wo09.store.expectation(successor.canonical_subject_identity))
    created=adapter.after_analysis(successor,requirements)
    assert len(created)==1 and created[0]['readiness_identity']==successor.readiness_identity
    assert len([w for w in adapter.wo09.store.load_watches() if w.state is WatchState.ACTIVE])==1
    assert all(w.state is WatchState.STALE for w in adapter.wo09.store.load_watches(second.readiness_identity))


def test_noneligible_after_analysis_does_not_require_open_global_market(tmp_path):
    watch,r,req,bindings,clock,*_=setup_watch(tmp_path,missing_five=(26,))
    adapter=canonical_adapter(watch,clock)
    def forbidden(*args): raise AssertionError('Noneligible member requested source/session authority')
    adapter.boundary._session=forbidden
    adapter.boundary._source=forbidden
    assert adapter.after_analysis(r,req)==()


def test_governed_reassessment_retains_old_watch_history_without_notification(tmp_path):
    from kronos.intraday.wo09_experimental import origin_from
    watch,r,req,bindings,clock,*_=setup_watch(tmp_path)
    adapter=canonical_adapter(watch,clock)
    successor_assessment=experimental_fixture()[-1]
    clock[0]+=timedelta(seconds=1)
    successor,_=evaluate_experimental_readiness(successor_assessment,observed_at=clock[0],origin=origin_from(r.origin_document))
    events=adapter.before_analysis(successor)
    assert len(events)==1 and events[0].state is WatchState.TRIGGERED
    assert events[0].reacquisition_identity==successor.wo08_identity
    assert watch.wo09.store.load_readiness(r.readiness_identity)==r
    assert watch.wo09.store.load_notifications()==()
    assert len(watch.store.watch_history())==2
    assert adapter.before_analysis(successor)==()


def test_wo12_association_retains_exact_watch_hint_and_positive_metrics(tmp_path):
    from types import SimpleNamespace
    from kronos.intraday.wo09_experimental import origin_from, assessment_from
    from kronos.application.intraday_wo08_research import associate_assessments, research_metrics
    from tests.unit.application.test_intraday_research import _EmptyStore,_Lifecycle
    watch,r,req,bindings,clock,current,instrument,expiry=setup_watch(tmp_path)
    source,facts,mapping,run,native,assessment=experimental_fixture(
        five_rows=[(108,102,106)]*25+[(115,110,113),(117,114,116)])
    assert assessment.identity==r.wo08_identity
    clock[0]+=timedelta(seconds=1)
    t=ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True)
    hint=watch.on_tick(t)[0]
    watch.on_disconnect(at=clock[0])
    associations=associate_assessments(assessments=SimpleNamespace(records=lambda:(assessment,)),shadow=None,
        probables=SimpleNamespace(load_run=lambda _:run,load_result=lambda _:run.results[0]),
        origins=(origin_from(r.origin_document),),readiness={'result':(r,)},
        futures=_EmptyStore(),lifecycle=_Lifecycle(),watch_store=watch.wo09.store)
    a=associations[0]
    assert a.schema=='WO12_WO08_EXPERIMENTAL_ASSOCIATION_V1'
    assert a.data['methodology_version']=='0.1.0'
    assert len(a.data['selective_watch_history'])==2
    assert a.data['advisory_wake_hints'][0]['identity']==hint['identity']
    assert a.data['criteria']==assessment.data['criteria']
    assert a.data['original_prediction']['assessment_identity']==assessment.identity
    metrics={m[0]:m for m in research_metrics(associations)}
    assert metrics['WO08 I1 established rate'][1]==1
    assert metrics['WO08 I2 established rate'][1]==0


def test_passive_callback_failure_does_not_break_existing_owner():
    class FailingConsumer(Consumer):
        def on_market_tick(self,tick): raise OSError('isolated advisory store unavailable')
        def on_connection_state(self,state): raise OSError('isolated advisory store unavailable')
    hub,capability=SharedSwingMonitoringHub(),Capability()
    consumer=Consumer();owner=hub.open(capability,consumer)
    owner.subscribe((ONE,));owner.connect()
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    observer=hub.observe_existing(capability,FailingConsumer(),(ONE,))
    hub.on_market_tick(tick(ONE))
    hub.on_connection_state(MonitoringConnectionState.DISCONNECTED)
    assert len(consumer.ticks)==1 and consumer.states[-1] is MonitoringConnectionState.DISCONNECTED
    assert observer.advisory_failure=='ADVISORY_CALLBACK_FAILED'


def test_advisory_callback_error_surfaces_in_canonical_status(tmp_path):
    watch,r,req,bindings,clock,*_=setup_watch(tmp_path)
    adapter=canonical_adapter(watch,clock)
    class Failed:
        active=True
        read_only_active=True
        advisory_failure='ADVISORY_CALLBACK_FAILED'
    adapter.registrations[bindings[0]['identity']]=Failed()
    status=adapter.status_document()
    assert status['last_failure']=='ADVISORY_CALLBACK_FAILED'
    assert status['advisory_callback_failures']==[dict(binding_identity=bindings[0]['identity'],failure='ADVISORY_CALLBACK_FAILED')]
    assert status['automatic_provider_acquisition'] is False


def test_original_first_five_age_prevents_late_five_four_watch(tmp_path):
    from kronos.intraday.wo09_experimental import observe_first_five, origin_from, assessment_from
    watch,r,req,bindings,clock,current,instrument,expiry=setup_watch(tmp_path)
    origin=origin_from(r.origin_document)
    first=observe_first_five(experimental_fixture()[-1],origin,observed_at=clock[0])
    from kronos.intraday.wo09_readiness import artifact_bytes
    watch.wo09.store._retain(watch.wo09.store.first_five/(first.claim_identity+'.json'),artifact_bytes(first))
    clock[0]+=timedelta(seconds=301)
    late,requirements=evaluate_experimental_readiness(assessment_from(r.assessment_document),
        observed_at=clock[0],origin=origin,first_five=first)
    watch.wo09.store.retain(late,requirements,expected=watch.wo09.store.expectation(r.canonical_subject_identity))
    assert late.satisfied_count==4 and watch_eligible(late)
    assert not watch_eligible(late,at=clock[0])
    assert watch.synchronize(late,requirements,session_expires_at=expiry,instrument=instrument)==()
    assert all(w.state is not WatchState.ACTIVE for w in watch.wo09.store.load_watches())


@pytest.mark.parametrize('field,value',[('missing_criterion','I3'),('method_version','99.0'),
    ('hint_levels',{'I2':'1','I3':None,'corridor_lower':'0','corridor_upper':'2'}),('generation','FORGED')])
def test_rehashed_binding_cannot_replace_retained_source(tmp_path,field,value):
    import json
    from kronos.application.intraday_experimental_watch import _document
    watch,*_=setup_watch(tmp_path)
    path=next((watch.store.root/'binding').glob('*.json'))
    d=json.loads(path.read_text());d.pop('identity');d.pop('integrity');d[field]=value
    path.write_text(json.dumps(_document(**d)))
    with pytest.raises(ValueError,match='SOURCE_INVALID'):
        watch.restore()


def test_rehashed_hint_cannot_replace_watch_association(tmp_path):
    import json
    from kronos.application.intraday_experimental_watch import _document
    watch,r,req,b,clock,current,instrument,expiry=setup_watch(tmp_path)
    clock[0]+=timedelta(seconds=1)
    watch.on_tick(ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],
        'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True))
    path=next((watch.store.root/'hint').glob('*.json'))
    d=json.loads(path.read_text());d.pop('identity');d.pop('integrity');d['binding_identity']='FORGED'
    path.write_text(json.dumps(_document(**d)))
    with pytest.raises(ValueError,match='HINT_BINDING_INVALID'):
        watch.restore()


def test_shared_tick_worker_coalesces_and_shutdown_joins(tmp_path):
    from threading import Event
    watch,r,req,bindings,clock,current,instrument,expiry=setup_watch(tmp_path)
    adapter=canonical_adapter(watch,clock)
    adapter._queue_instruments[bindings[0]['identity']]=instrument
    entered,release=Event(),Event()
    seen=[]
    def slow(tick, **_):
        seen.append(tick.source_sequence)
        entered.set()
        assert release.wait(5)
    adapter.on_tick=slow
    clock[0]+=timedelta(seconds=1)
    tick=ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],
        'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True)
    assert adapter.on_market_tick(tick)
    assert entered.wait(2)
    worker=adapter._worker_thread
    for sequence in range(2,102):
        assert adapter.on_market_tick(replace(tick,source_sequence=sequence))
    assert len(adapter._queue)==1
    assert adapter.status_document()['work']['coalesced']==99
    release.set();worker.join(5)
    assert not worker.is_alive() and seen==[1,101]
    adapter.shutdown()
    assert not adapter.on_market_tick(tick)
    assert adapter.status_document()['work']['closed'] is True


def test_worker_source_failure_is_visible(tmp_path):
    watch,r,req,bindings,clock,current,instrument,expiry=setup_watch(tmp_path)
    adapter=canonical_adapter(watch,clock)
    adapter._queue_instruments[bindings[0]['identity']]=instrument
    def fail(tick, **_):raise ValueError('bad source')
    adapter.on_tick=fail
    clock[0]+=timedelta(seconds=1)
    tick=ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],
        'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True)
    adapter.on_market_tick(tick)
    worker=adapter._worker_thread
    if worker is not None:worker.join(5)
    assert adapter.status_document()['last_failure']=='ADVISORY_REASSESSMENT_WORK_FAILED'
    adapter.shutdown()


@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_known_i4_breach_is_never_a_recovery_watch(tmp_path,direction):
    from tests.unit.intraday.test_native_pullback_policy import BARS
    rows=list(BARS)+[(117,99,116),(118,110,117)]
    five=[(108,102,106)]*28+[(118,113,116),(119,115,117)]
    watch,r,req,bindings,*_=setup_watch(tmp_path,direction,minutes=150,rows=rows,five_rows=five)
    assert r.criteria[3].state.value=='OUTSTANDING'
    assert not watch_eligible(r) and bindings==()
    assert watch.wo09.store.load_watches()==()


@pytest.mark.parametrize('callback',['on_tick','restore','after_analysis'])
def test_canonical_analysis_and_callback_lock_order_is_source_then_watch(tmp_path,callback):
    """Force contention: Analysis owns sources while callback reaches source entry.

    Analysis must still acquire the watch lock and record the governed event.
    A callback that took watch first would fail the instrumented order check or
    block Analysis. Reentrant source scopes are allowed only for the same owner.
    """
    from contextlib import contextmanager
    from threading import Event,RLock,Thread,current_thread,local
    from kronos.intraday.wo09_experimental import origin_from
    watch,r,req,bindings,clock,current,instrument,expiry=setup_watch(tmp_path)
    adapter=canonical_adapter(watch,clock)
    clock[0]+=timedelta(seconds=1)
    successor,_=evaluate_experimental_readiness(experimental_fixture()[-1],
        observed_at=clock[0],origin=origin_from(r.origin_document))
    adapter._session_instrument=lambda _: (expiry,instrument)
    source_lock=RLock()
    original_watch_lock=adapter.store.lock
    held=local()
    analysis_entered,callback_at_source=Event(),Event()
    errors=[]
    trace=[]
    completed=[]

    @contextmanager
    def sources(_):
        name=current_thread().name
        depth=getattr(held,'sources',0)
        assert not getattr(held,'watch',0) or depth>0, 'reverse watch-to-source acquisition'
        trace.append((name,'source_request',depth))
        if name=='watch-callback' and depth==0:
            callback_at_source.set()
        assert source_lock.acquire(timeout=3), 'source lock blocked'
        held.sources=depth+1
        trace.append((name,'source_acquired',held.sources))
        try:
            yield
        finally:
            held.sources-=1
            source_lock.release()

    class SourceOrderedWatchLock:
        def __enter__(self):
            assert getattr(held,'sources',0)>0, 'watch acquired without upstream source guard'
            assert original_watch_lock.acquire(timeout=3), 'Analysis blocked on watch lock'
            held.watch=getattr(held,'watch',0)+1
            trace.append((current_thread().name,'watch_acquired',held.sources))
            return self
        def __exit__(self,*args):
            held.watch-=1
            original_watch_lock.release()

    adapter.boundary._sources=sources
    adapter.store.lock=SourceOrderedWatchLock()
    def analysis():
        try:
            with adapter.boundary._sources(r):
                analysis_entered.set()
                assert callback_at_source.wait(3), 'callback never reached source boundary'
                event=adapter.before_analysis(successor)
                assert len(event)==1 and event[0].state is WatchState.TRIGGERED
                completed.append('analysis')
        except BaseException as error:
            errors.append(error)
    def consume():
        try:
            if callback=='on_tick':
                adapter.on_tick(ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],
                    'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True))
            elif callback=='restore':
                adapter.restore()
            else:
                adapter.after_analysis(r,req)
            completed.append('callback')
        except BaseException as error:
            errors.append(error)
    producer=Thread(target=analysis,name='watch-analysis')
    consumer=Thread(target=consume,name='watch-callback')
    producer.start()
    try:
        assert analysis_entered.wait(3)
        consumer.start()
    finally:
        producer.join(5)
        if consumer.ident is not None:
            consumer.join(5)
    assert not producer.is_alive() and not consumer.is_alive(), trace
    assert not errors, (errors,trace)
    assert completed==['analysis','callback'], trace
    assert any(name=='watch-callback' and event=='watch_acquired' for name,event,_ in trace)
    assert all(depth>0 for _,event,depth in trace if event=='watch_acquired')


@pytest.mark.parametrize('interruption', ['connection', 'subscription'])
def test_shared_disconnect_callback_fences_without_store_or_source_wait_and_drains_owned_cleanup(tmp_path, interruption):
    from contextlib import contextmanager
    from threading import Event, Thread, current_thread
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    watch,r,req,bindings,clock,_,instrument,expiry=setup_watch(tmp_path)
    adapter=canonical_adapter(watch,clock)
    adapter._session_instrument=lambda _: (expiry,instrument)
    adapter.maintenance=MaintenanceAdmissionCoordinator()
    hub,capability=SharedSwingMonitoringHub(),Capability()
    hub.bind_maintenance_admission(adapter.maintenance)
    ordinary=Consumer()
    owner=hub.open(capability,ordinary);owner.subscribe((instrument,));owner.connect()
    other_consumer=Consumer()
    other=hub.open(capability,other_consumer);other.subscribe((TWO,));other.connect()
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    adapter.hub=hub
    adapter.capability_supplier=lambda:capability
    adapter.after_analysis(r,req)
    observer=adapter.registrations[bindings[0]['identity']]
    entered,release,callback_done,shutdown_started,shutdown_done=Event(),Event(),Event(),Event(),Event()
    errors=[]
    replacements=[]
    @contextmanager
    def blocked_sources(_):
        assert current_thread().name=='Intraday experimental advisory watch'
        assert not adapter._queue_lock._is_owned(), 'queue lock held across source acquisition'
        entered.set()
        assert release.wait(5), 'source release not signalled'
        yield
    adapter.boundary._sources=blocked_sources
    clock[0]+=timedelta(seconds=1)
    market_tick=ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],
        'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True)
    def callback():
        try:
            if interruption=='connection':
                for _ in range(4):
                    hub.on_connection_state(MonitoringConnectionState.DISCONNECTED)
            else:
                owner.disconnect()
                replacement=hub.open(capability,Consumer())
                replacement.subscribe((instrument,));replacement.connect()
                replacements.append(replacement)
                hub.on_market_tick(market_tick)
                hub.on_market_tick(tick(TWO))
        except BaseException as error:
            errors.append(error)
        finally:
            callback_done.set()
    def shutdown():
        shutdown_started.set()
        try:
            adapter.shutdown()
        except BaseException as error:
            errors.append(error)
        finally:
            shutdown_done.set()
    callback_thread=Thread(target=callback,name='shared-provider-callback')
    shutdown_thread=Thread(target=shutdown)
    before={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
    try:
        with adapter.store.lock:
            assert adapter.on_market_tick(market_tick)
            assert entered.wait(3)
            assert adapter.on_market_tick(replace(market_tick,source_sequence=2))
            old_epoch=adapter._queue_epoch
            callback_thread.start()
            assert callback_done.wait(3), 'shared callback waited on a source/watch lock'
            assert not errors
            if interruption=='connection':
                assert adapter._interrupted and adapter._queue_epoch>old_epoch
            else:
                assert not adapter._interrupted and bindings[0]['identity'] in adapter._binding_interruptions
            assert not adapter._queue and not adapter._queue_instruments and not observer.active
            assert adapter.runtime_status_document()['work']['pending']==1
            assert adapter.runtime_status_document()['work']['coalesced']==(3 if interruption=='connection' else 0)
            assert adapter.maintenance.snapshot()['owners']=={'PROGRESSION':3}
            if interruption=='connection':
                assert ordinary.states[-4:]==[MonitoringConnectionState.DISCONNECTED]*4
                assert other_consumer.states[-4:]==[MonitoringConnectionState.DISCONNECTED]*4
            else:
                assert other.active and replacements[0].active and len(other_consumer.ticks)==1
                assert len(capability.sessions)==1 and capability.sessions[0].connections==1
            assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
            assert not adapter.on_market_tick(market_tick)
            shutdown_thread.start()
            assert shutdown_started.wait(3) and not shutdown_done.is_set()
            release.set()
    finally:
        release.set()
        if callback_thread.ident is not None:callback_thread.join(5)
        if shutdown_thread.ident is not None:shutdown_thread.join(5)
        else:adapter.shutdown()
    assert not errors and shutdown_done.is_set()
    assert adapter.maintenance.snapshot()['owners']=={}
    assert adapter._worker_thread is None and adapter._disconnect_pending is None
    assert adapter._queue_failure is None
    assert all(w.state is WatchState.STALE for w in adapter.wo09.store.load_watches())
    assert adapter.store.records(HINT)==()
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    assert not observer.active
    owner.disconnect()
    for replacement in replacements:replacement.disconnect()
    other.disconnect()


def independent_watch_case(tmp_path, second_market='MCX'):
    """Two source-valid watches sharing one ordinary-owned physical session."""
    from dataclasses import fields
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    watch,first,req1,b1,clock,_,instrument,expiry=setup_watch(tmp_path/'main')
    if second_market=='MCX':
        from tests.unit.instrument.test_active_derivative_selection import _resolve,_snapshot
        from tests.unit.intraday.test_discovery_runtime import _publications,_bundle
        from kronos.intraday.discovery_runtime import DiscoveryRunBoundary
        from kronos.intraday.discovery import create_machine_fact_bundle
        subject='MCX-SUBJECT-GOLDM'
        binding=_resolve(clock[0]).for_subject(subject).binding
        _,reconciliation=_publications()
        member=next(m for m in reconciliation.members if m.canonical_identity==subject)
        bundle=_bundle(member,DiscoveryRunBoundary(clock[0],binding.domain008_session_identity,'BOUNDARY'),reconciliation)
        values={f.name:getattr(bundle,f.name) for f in fields(bundle) if f.name!='bundle_identity'}
        values['source_identities']+=(binding.binding_identity,binding.provider_snapshot_identity)
        values['provenance']+=(binding.integrity_identity,binding.domain008_session_identity)
        bundle=create_machine_fact_bundle(**values)
        assessment=experimental_fixture(subject=subject,session=binding.domain008_session_identity,
            binding=binding,bundle=bundle,
            five_rows=[(108,102,106)]*25+[(115,110,113),(117,114,116)])[-1]
        data=assessment.data
        origin=opportunity_origin(canonical_subject_identity=subject,market_family='MCX',
            session_identity=data['session_identity'],origin_at=clock[0],
            probable_result_identity=data['probable_result_identity'],probables_run_identity=data['run_identity'])
        second,req2=evaluate_experimental_readiness(assessment,observed_at=clock[0],origin=origin)
        row=next(r for r in _snapshot(clock[0]).records if r.provider_record_identity==binding.provider_record_identity)
        other_instrument=InstrumentRecord(**{name:getattr(row,name) for name in (
            'provider','exchange','segment','trading_symbol','name','instrument_type','expiry','tick_size','lot_size')})
    else:
        _,second,req2,*_=setup_watch(tmp_path/'seed',subject='NSE-EQ-RELIANCE')
        other_instrument=TWO
    watch.wo09.store.retain(second,req2,expected=watch.wo09.store.expectation(second.canonical_subject_identity))
    adapter=canonical_adapter(watch,clock)
    instruments={first.canonical_subject_identity:instrument,second.canonical_subject_identity:other_instrument}
    adapter._session_instrument=lambda r:(expiry,instruments[r.canonical_subject_identity])
    adapter.maintenance=MaintenanceAdmissionCoordinator()
    hub,capability=SharedSwingMonitoringHub(),Capability()
    hub.bind_maintenance_admission(adapter.maintenance)
    owners=[]
    for value in instruments.values():
        owner=hub.open(capability,Consumer());owner.subscribe((value,));owner.connect();owners.append(owner)
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    adapter.hub=hub
    adapter.capability_supplier=lambda:capability
    first_bindings=adapter.after_analysis(first,req1)
    second_bindings=adapter.after_analysis(second,req2)
    assert len(first_bindings)==len(second_bindings)==1
    return adapter,(first,second),(first_bindings[0],second_bindings[0]),clock,instruments,hub,capability,owners


@pytest.mark.parametrize('second_market',['NSE','MCX'])
@pytest.mark.parametrize('lost_index',[0,1])
def test_subscription_gap_preserves_unrelated_watch_and_advisory_delivery(tmp_path,second_market,lost_index):
    adapter,readiness,bindings,clock,instruments,hub,capability,owners=independent_watch_case(tmp_path,second_market)
    other_index=1-lost_index
    old_observer=adapter.registrations[bindings[lost_index]['identity']]
    other_observer=adapter.registrations[bindings[other_index]['identity']]
    try:
        owners[lost_index].disconnect()
        worker=adapter._worker_thread
        if worker is not None:worker.join(5);assert not worker.is_alive()
        states={w.canonical_subject_identity:w.state for w in adapter.wo09.store.load_watches()}
        assert states[readiness[lost_index].canonical_subject_identity] is WatchState.STALE
        assert states[readiness[other_index].canonical_subject_identity] is WatchState.ACTIVE
        assert not old_observer.active and other_observer.active and owners[other_index].active
        assert set(adapter.registrations)=={bindings[other_index]['identity']}
        assert not adapter._interrupted and not adapter._binding_interruptions
        clock[0]+=timedelta(seconds=1)
        other_instrument=instruments[readiness[other_index].canonical_subject_identity]
        threshold=Decimal(bindings[other_index]['hint_levels']['I2'])
        hub.on_market_tick(ProviderMarketTick(other_instrument,threshold+Decimal('.1'),clock[0],clock[0],
            'KITE_CONNECT_WEBSOCKET','ONE',1,True,True,True))
        worker=adapter._worker_thread
        if worker is not None:worker.join(5);assert not worker.is_alive()
        assert [h['binding_identity'] for h in adapter.store.records(HINT)]==[bindings[other_index]['identity']]
        assert len(capability.sessions)==1 and capability.sessions[0].disconnections==0
        assert adapter.maintenance.snapshot()['owners']=={}
        hub.on_connection_state(MonitoringConnectionState.DISCONNECTED)
        worker=adapter._worker_thread
        if worker is not None:worker.join(5);assert not worker.is_alive()
        assert all(w.state is WatchState.STALE for w in adapter.wo09.store.load_watches())
        assert not adapter.registrations and not other_observer.active
    finally:
        adapter.shutdown()
        for owner in owners:owner.disconnect()


def test_delayed_old_observer_cleanup_cannot_retire_same_instrument_successor(tmp_path):
    from contextlib import contextmanager
    from threading import Event,current_thread
    from kronos.intraday.wo09_experimental import origin_from
    adapter,readiness,bindings,clock,instruments,hub,capability,owners=independent_watch_case(tmp_path)
    first,other=readiness
    old_binding=bindings[0]
    old_observer=adapter.registrations[old_binding['identity']]
    old_consumer=old_observer._consumer
    entered,release=Event(),Event()
    original_sources=adapter.boundary._sources
    @contextmanager
    def delayed_sources(record):
        if current_thread().name=='Intraday experimental advisory watch' and not release.is_set():
            assert not adapter._queue_lock._is_owned()
            entered.set()
            assert release.wait(5), 'delayed cleanup never released'
        with original_sources(record):yield
    adapter.boundary._sources=delayed_sources
    replacement=None
    try:
        owners[0].disconnect()
        assert entered.wait(3)
        worker=adapter._worker_thread
        assert old_binding['identity'] in adapter._binding_interruptions and not adapter._interrupted
        replacement=hub.open(capability,Consumer())
        instrument=instruments[first.canonical_subject_identity]
        replacement.subscribe((instrument,));replacement.connect()
        clock[0]+=timedelta(seconds=1)
        assessment=experimental_fixture(five_rows=[(108,102,106)]*25+[(115,110,113),(117,114,116.5)])[-1]
        successor,requirements=evaluate_experimental_readiness(assessment,observed_at=clock[0],origin=origin_from(first.origin_document))
        with adapter.boundary._sources(successor):
            adapter.before_analysis(successor)
            adapter.wo09.store.retain(successor,requirements,
                expected=adapter.wo09.store.expectation(first.canonical_subject_identity))
        new_bindings=adapter.after_analysis(successor,requirements)
        assert len(new_bindings)==1 and new_bindings[0]['identity']!=old_binding['identity']
        new_observer=adapter.registrations[new_bindings[0]['identity']]
        assert new_observer.active and not old_observer.active
        old_consumer.on_subscription_lost()  # delayed old registration callback
        assert not old_consumer.on_market_tick(ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],
            'KITE_CONNECT_WEBSOCKET','ONE',9,True,True,True))
        release.set();worker.join(5);assert not worker.is_alive()
        assert adapter._queue_failure is None and not adapter._binding_interruptions
        assert adapter.wo09.store.load_watches(successor.readiness_identity)[0].state is WatchState.ACTIVE
        assert adapter.wo09.store.load_watches(other.readiness_identity)[0].state is WatchState.ACTIVE
        assert new_observer.active and set(adapter.registrations)=={new_bindings[0]['identity'],bindings[1]['identity']}
        assert adapter.store.records(HINT)==()
        clock[0]+=timedelta(seconds=1)
        hub.on_market_tick(ProviderMarketTick(instrument,Decimal('119'),clock[0],clock[0],
            'KITE_CONNECT_WEBSOCKET','ONE',10,True,True,True))
        worker=adapter._worker_thread
        if worker is not None:worker.join(5);assert not worker.is_alive()
        assert [h['binding_identity'] for h in adapter.store.records(HINT)]==[new_bindings[0]['identity']]
        assert len(capability.sessions)==1 and adapter.maintenance.snapshot()['owners']=={}
    finally:
        release.set()
        adapter.shutdown()
        for owner in owners:owner.disconnect()
        if replacement is not None:replacement.disconnect()


def test_scoped_cleanup_denied_by_maintenance_preserves_global_interruption(tmp_path):
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    adapter,readiness,bindings,clock,instruments,hub,capability,owners=independent_watch_case(tmp_path,'NSE')
    try:
        assert adapter.maintenance.claim('c'*64)
        before={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
        owners[0].disconnect()
        assert adapter._interrupted and adapter._worker_thread is None
        assert bindings[0]['identity'] in adapter._binding_interruptions
        assert before=={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
        assert all(w.state is WatchState.ACTIVE for w in adapter.wo09.store.load_watches())
        adapter.maintenance=MaintenanceAdmissionCoordinator()
        assert adapter.restore()==()
        assert all(w.state is WatchState.STALE for w in adapter.wo09.store.load_watches())
        assert not adapter.registrations and not adapter._interrupted
    finally:
        adapter.shutdown()
        for owner in owners:owner.disconnect()
