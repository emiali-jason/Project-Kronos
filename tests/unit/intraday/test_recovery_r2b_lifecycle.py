"""Actual WO11 entry-only guard, final recheck, and entered safety assertions."""
from datetime import timedelta
from decimal import Decimal
import pytest
from kronos.intraday.evidence_currentness import NewWorkNotEligible
from kronos.intraday.wo09_readiness import CurrentnessState
from kronos.browser.intraday_lifecycle_control import IntradayLifecycleControl
from tests.unit.intraday.test_wo11_lifecycle_application import fixture,emit
from kronos.application.intraday_evidence_currentness import IntradayPublicationBoundary
from threading import RLock


def deny(app):
    app.eligibility=None


def enter(app,h,clock,cap):
    current=app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM')
    clock[0]+=timedelta(minutes=5);app.pulse();current=app.store.restore()[0]
    assert current.data['state']=='AWAITING_ENTRY',app.last_failure
    clock[0]+=timedelta(seconds=1)
    current=emit(app,cap,clock,current,str(Decimal(current.data['intake']['entry'])+1))
    assert current.data['state']=='ACTIVE',app.last_failure
    return current


def test_none_is_history_only_not_allow(tmp_path,monkeypatch):
    app,h,_,_,_,_,_=fixture(tmp_path,monkeypatch);app.eligibility=None
    result=IntradayLifecycleControl(app).execute_document(dict(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM'))
    assert result=={'outcome':'REJECTED','reason':'WO11_NEW_WORK_ELIGIBILITY_AUTHORITY_UNAVAILABLE',
        'failure_stage':'NEW_WORK_ELIGIBILITY','failure_reason':'ELIGIBILITY_AUTHORITY_UNAVAILABLE'}
    assert not app.store.root.exists()


def test_arm_rechecks_after_pure_preparation_before_positive_publication(tmp_path,monkeypatch):
    app,h,_,_,_,_,_=fixture(tmp_path,monkeypatch)
    import kronos.application.intraday_lifecycle as owner
    original=owner.arm
    def supersede(*args,**kwargs):
        value=original(*args,**kwargs)
        p=app.futures.wo09.load_pointer(value.current.data['intake']['subject'])
        app.futures.wo09.mark_currentness(p.canonical_subject_identity,CurrentnessState.SUPERSEDED,updated_at=p.updated_at+timedelta(seconds=1),expected=app.futures.wo09.expectation(p.canonical_subject_identity))
        return value
    monkeypatch.setattr(owner,'arm',supersede)
    with pytest.raises(__import__('kronos.intraday.wo09_persistence',fromlist=['Wo09PublicationConflict']).Wo09PublicationConflict):
        app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM')
    assert app.store.restore()==() and app.store.records('WO11_ENTRY_V1')==()
    assert app.store.records('WO11_AUTHORIZATION_V1')==()


def test_pre_entry_pulse_denial_cannot_establish_timing(tmp_path,monkeypatch):
    app,h,_,_,clock,_,_=fixture(tmp_path,monkeypatch)
    app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM')
    deny(app);clock[0]+=timedelta(minutes=5);app.pulse()
    assert not app.store.records('WO11_ENTRY_V1')
    checks=app.store.records('WO11_AUTHORITY_CHECK_V1')
    assert checks and checks[-1].data['result']=='UNAVAILABLE'
    assert checks[-1].data['reason']=='WO11_NEW_WORK_ELIGIBILITY_AUTHORITY_UNAVAILABLE'


def test_pre_entry_tick_final_recheck_after_observation_preparation(tmp_path,monkeypatch):
    app,h,_,_,clock,cap,_=fixture(tmp_path,monkeypatch)
    app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM')
    clock[0]+=timedelta(minutes=5);app.pulse();current=app.store.restore()[0]
    import kronos.application.intraday_lifecycle as owner
    original=owner.websocket_observation
    def supersede(*args,**kwargs):
        value=original(*args,**kwargs)
        p=app.futures.wo09.load_pointer(current.data['intake']['subject'])
        app.futures.wo09.mark_currentness(p.canonical_subject_identity,CurrentnessState.SUPERSEDED,updated_at=clock[0],expected=app.futures.wo09.expectation(p.canonical_subject_identity))
        return value
    monkeypatch.setattr(owner,'websocket_observation',supersede)
    clock[0]+=timedelta(seconds=1)
    current=emit(app,cap,clock,current,str(Decimal(current.data['intake']['entry'])+1))
    assert current.data['entry'] is None
    assert app.store.records('WO11_ENTRY_V1')==()
    assert app.store.records('WO11_AUTHORITY_CHECK_V1')[-1].data['result']=='UNAVAILABLE'
    assert app.store.records('WO11_AUTHORITY_CHECK_V1')[-1].data['reason']=='WO09_PUBLICATION_EXPECTATION_CHANGED'


@pytest.mark.parametrize('exit_kind',['TARGET','STOP_LOSS','SPONSOR_EXIT'])
def test_entered_exit_does_not_consult_new_work_eligibility(tmp_path,monkeypatch,exit_kind):
    app,h,_,_,clock,cap,hub=fixture(tmp_path,monkeypatch)
    current=enter(app,h,clock,cap)
    def forbidden(*args):pytest.fail('entered safety consulted analytical eligibility')
    app._pre_entry_expectation=forbidden;app.eligibility=None
    if exit_kind=='SPONSOR_EXIT':
        auth=app.store.load(current.data['authorization_identity'])
        app.close_track(claim=auth.data['claim'],action_identity='EXIT')
        price=current.data['entry']['price']
    else:
        price=str(Decimal(current.data['intake']['target'])+1) if exit_kind=='TARGET' else str(Decimal(current.data['intake']['stop'])-1)
    clock[0]+=timedelta(seconds=1);current=emit(app,cap,clock,current,price)
    assert current.data['exit_reason']==exit_kind
    assert current.data['entry'] is not None and current.data['exit'] is not None
    assert app.store.restore()==(current,)


def test_entered_pulse_and_inert_restoration_ignore_missing_eligibility(tmp_path,monkeypatch):
    app,h,_,_,clock,cap,_=fixture(tmp_path,monkeypatch);current=enter(app,h,clock,cap)
    app.eligibility=None
    clock[0]+=timedelta(seconds=1);app.pulse()
    assert app.store.restore()[0].data['entry']==current.data['entry']
    from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
    restored=IntradayLifecycleApplication(futures=app.futures,store=app.store,clock=app.clock,
        session_source=app.session_source,timing_source=app.timing_source,operational_guard=app.operational_guard)
    assert restored.projection()['cards'][0]['state']=='OBSERVING_ACTIVE'
    assert restored.store.restore()[0].data['state']=='ACTIVE'


def test_arm_pulse_entry_lock_order_and_callback_reference(tmp_path,monkeypatch):
    from contextlib import contextmanager
    from threading import Event,Thread
    app,h,_,_,clock,cap,_=fixture(tmp_path,monkeypatch)
    boundary=app.eligibility;events=[];active=[];calls=[];errors=[]
    def scope(name,original):
        @contextmanager
        def traced(*args,**kwargs):
            with original(*args,**kwargs) as value:
                if name=='wo09':assert active==['review','probables','paired','bindings','reconciliation','batch']
                if name=='futures':assert active[-1]=='wo09'
                if name=='lifecycle-file' and 'wo09' in active:assert active[-2:]==['futures','lifecycle-app']
                active.append(name);events.append(('enter',name))
                try:yield value
                finally:
                    assert active.pop()==name
                    events.append(('exit',name))
        return traced
    for name,owner in [('review',boundary.review),('probables',boundary.probables),('paired',boundary.paired),('bindings',boundary.bindings),('reconciliation',boundary.reconciliation),('batch',boundary.ordered_batch)]:
        monkeypatch.setattr(owner,'page_read_scope',scope(name,owner.page_read_scope))
    monkeypatch.setattr(boundary.wo09,'transaction',scope('wo09',boundary.wo09.transaction))
    monkeypatch.setattr(boundary.futures,'transaction',scope('futures',boundary.futures.transaction))
    monkeypatch.setattr(app.store,'transaction',scope('lifecycle-file',app.store.transaction))
    original_lock=app._lock
    class TracedApplicationLock:
        def __enter__(self):
            original_lock.acquire();active.append('lifecycle-app');events.append(('enter','lifecycle-app'));return self
        def __exit__(self,*args):
            assert active.pop()=='lifecycle-app';events.append(('exit','lifecycle-app'));original_lock.release()
    app._lock=TracedApplicationLock()
    def callback(kind,identity):
        assert active==[]
        done=Event()
        def reenter():
            try:
                with boundary._sources(),boundary.wo09.transaction(expected=boundary.wo09.expectation(h.data['selection']['comparison']['subject'])),boundary.futures.transaction(),app._lock,app.store.transaction():done.set()
            except Exception as exc:errors.append(exc)
        worker=Thread(target=reenter);worker.start();worker.join(3)
        if worker.is_alive() or not done.is_set():errors.append('LIFECYCLE_GUARD_HELD')
        calls.append((kind,identity))
    original_notice=app.store.notify_publication
    def dispatch(previous,current):
        assert active==[]
        app.store.notification_listener=lambda *args:pytest.fail('replacement listener used')
        original_notice(previous,current)
        app.store.notification_listener=callback
    app.store.notification_listener=callback
    monkeypatch.setattr(app.store,'notify_publication',dispatch)
    original_attach=app._attach;original_timing=app.timing_source
    def attach(*args,**kwargs):
        assert active==[];return original_attach(*args,**kwargs)
    def acquire(*args):
        assert active==[];return original_timing(*args)
    monkeypatch.setattr(app,'_attach',attach);app.timing_source=acquire
    current=app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM')
    clock[0]+=timedelta(minutes=5);app.pulse();current=app.store.restore()[0]
    clock[0]+=timedelta(seconds=1);current=emit(app,cap,clock,current,str(Decimal(current.data['intake']['entry'])+1))
    assert current.data['entry'] is not None and errors==[]
    assert len(calls)>=3 and len(set(calls))==len(calls)
    assert all(kind=='TRACK' and app.store.load(identity).schema=='WO11_TRACK_V1' for kind,identity in calls)
    assert calls[-1]==('TRACK',current.identity)
    # Each final publication unwinds the complete lock graph in reverse order.
    final=['review','probables','paired','bindings','reconciliation','batch','wo09','futures','lifecycle-app','lifecycle-file']
    expected=[('exit',name) for name in reversed(final)]
    assert sum(events[i:i+len(expected)]==expected for i in range(len(events)))>=3
    assert active==[] and not getattr(app.store,'notification_failure',None)


@pytest.mark.parametrize('changed',['advanced','entered'])
def test_earlier_tick_cannot_overwrite_concurrent_lifecycle_successor(tmp_path,monkeypatch,changed):
    from kronos.provider.contracts.monitoring import ProviderMarketTick
    from kronos.application.intraday_lifecycle_intake import instrument_record
    import kronos.application.intraday_lifecycle as owner
    app,h,_,_,clock,cap,_=fixture(tmp_path,monkeypatch)
    app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM')
    clock[0]+=timedelta(minutes=5);app.pulse();current=app.store.restore()[0]
    original=owner.websocket_observation;inside=False;successors=[]
    older_at=clock[0]+timedelta(seconds=1);clock[0]=older_at
    older_price=str(Decimal(current.data['intake']['entry'])+1)
    newer_price=str(Decimal(current.data['intake']['entry'])+(2 if changed=='entered' else -2))
    def advance(*args,**kwargs):
        nonlocal inside
        observed=original(*args,**kwargs)
        if not inside:
            inside=True;clock[0]=older_at+timedelta(seconds=1)
            newer=ProviderMarketTick(instrument_record(current.data['intake']['future']),Decimal(newer_price),clock[0],clock[0],
                'KITE_CONNECT_WEBSOCKET','session-test',None,True,True,True)
            app._tick(current.data['track_identity'],newer)
            successors.append(app.store.restore()[0])
        return observed
    monkeypatch.setattr(owner,'websocket_observation',advance)
    result=emit(app,cap,clock,current,older_price)
    assert result==successors[0] and result!=current
    assert (result.data['entry'] is not None)==(changed=='entered')
    if changed=='entered':assert result.data['entry']['price']==newer_price
    # Only the later tick was durably admitted; the earlier prepared tick is not replayed.
    observations=app.store.records('WO11_MARKET_OBSERVATION_V1')
    assert len(observations)==1 and __import__('datetime').datetime.fromisoformat(observations[0].data['fact']['observed_at'])==clock[0]


def test_pulse_cannot_overwrite_successor_published_during_timing_acquisition(tmp_path,monkeypatch):
    app,h,_,_,clock,_,_=fixture(tmp_path,monkeypatch)
    app.action(handoff_identity=h.identity,action='OBSERVE',action_identity='ARM')
    clock[0]+=timedelta(minutes=5);original=app.timing_source;inside=False;successors=[]
    def acquire(current):
        nonlocal inside
        qualified=original(current)
        if not inside:
            inside=True
            app._timing_boundaries.clear();app.pulse();successors.append(app.store.restore()[0])
        return qualified
    app.timing_source=acquire;app.pulse()
    assert len(successors)==1 and app.store.restore()==(successors[0],)
    assert successors[0].data['state']=='AWAITING_ENTRY'
    assert len(app.store.records('WO11_TIMING_V1'))==1


@pytest.mark.parametrize('deferred',[False,True])
def test_lifecycle_callback_default_deferral_filter_and_failure(tmp_path,monkeypatch,deferred):
    from kronos.intraday.wo11_lifecycle import arm,observe
    from kronos.intraday.wo11_lifecycle_contract import websocket_observation
    from kronos.intraday.wo11_lifecycle_store import LifecycleStore
    from kronos.application.intraday_lifecycle_intake import _load_intake_graph,instrument_record
    from kronos.provider.contracts.monitoring import ProviderMarketTick
    app,h,_,_,clock,_,_=fixture(tmp_path,monkeypatch)
    intake=_load_intake_graph(app.futures,h.identity,session=app.session_source(h.data['selection']['comparison']['subject'],clock[0]),now=clock[0])
    transition=arm(intake,truth_class='PAPER_OBSERVATION',action_identity='STORE-ONLY',action_at=clock[0])
    claim=next(r.data['claim'] for r in transition.evidence if r.schema=='WO11_AUTHORIZATION_V1')
    store=LifecycleStore(tmp_path/'callback-store');calls=[]
    for attribute in ('book_listener','notification_listener','journal_listener'):
        setattr(store,attribute,lambda *args,a=attribute:calls.append((a,args)))
    result=store.publish(transition,claim=claim,previous=None,emit_notifications=not deferred)
    if deferred:
        assert calls==[]
        for attribute in ('book_listener','notification_listener','journal_listener'):
            setattr(store,attribute,lambda *args:pytest.fail('replacement listener used'))
        store.notify_publication(None,result)
    assert calls==[(a,('TRACK',result.identity)) for a in ('book_listener','notification_listener','journal_listener')]
    # A pre-timing observation changes neither state/entry/exit/monitoring: book only.
    calls.clear()
    for attribute in ('book_listener','notification_listener','journal_listener'):
        setattr(store,attribute,lambda *args,a=attribute:calls.append((a,args)))
    intake=intake.data
    at=clock[0]+timedelta(seconds=1)
    tick=ProviderMarketTick(instrument_record(intake['future']),Decimal(intake['entry']),at,at,'KITE_CONNECT_WEBSOCKET','session-test',None,True,True,True)
    fact=websocket_observation(tick,authorization_identity=result.data['track_identity'],instrument=instrument_record(intake['future']),
        session_identity=intake['session_identity'],expected_session_identity=intake['session_identity'],causal_at=clock[0],decision_at=at)
    next_transition=observe(result,fact)
    updated=store.publish(next_transition,claim=claim,previous=result.identity,emit_notifications=not deferred)
    if deferred:store.notify_publication(result,updated)
    assert calls==[('book_listener',('TRACK',updated.identity))]
    assert store.restore()==(updated,)


@pytest.mark.parametrize('phase',['before','after','listener'])
def test_lifecycle_pointer_and_callback_fault_truth(tmp_path,monkeypatch,phase):
    from kronos.intraday.wo11_lifecycle import arm
    from kronos.intraday.wo11_lifecycle_store import LifecycleStore
    from kronos.application.intraday_lifecycle_intake import _load_intake_graph
    import kronos.intraday.wo11_lifecycle_store as owner
    app,h,_,_,clock,_,_=fixture(tmp_path,monkeypatch)
    intake=_load_intake_graph(app.futures,h.identity,session=app.session_source(h.data['selection']['comparison']['subject'],clock[0]),now=clock[0])
    transition=arm(intake,truth_class='PAPER_OBSERVATION',action_identity='FAULT-ONLY',action_at=clock[0])
    claim=next(r.data['claim'] for r in transition.evidence if r.schema=='WO11_AUTHORIZATION_V1')
    store=LifecycleStore(tmp_path/'fault-store');calls=[]
    def listener(*args):
        calls.append(args)
        if phase=='listener':raise RuntimeError('POST_COMMIT_NOTIFICATION')
    store.notification_listener=listener
    if phase!='listener':
        original=owner.os.replace
        def fail(src,dst):
            if phase=='after':original(src,dst)
            raise OSError('LIFECYCLE_REPLACE_'+phase)
        monkeypatch.setattr(owner.os,'replace',fail)
        with pytest.raises(OSError,match='LIFECYCLE_REPLACE_'+phase):
            store.publish(transition,claim=claim,previous=None,emit_notifications=False)
        assert calls==[] and store._deferred_notices=={}
        assert (store.current(claim) is None)==(phase=='before')
    else:
        result=store.publish(transition,claim=claim,previous=None,emit_notifications=False)
        assert calls==[]
        store.notify_publication(None,result)
        assert calls==[('TRACK',result.identity)]
        assert store.notification_failure=='NOTIFICATION_PROJECTION_UNAVAILABLE'
        assert store.restore()==(result,)
    assert store.load(transition.current.identity)==transition.current
