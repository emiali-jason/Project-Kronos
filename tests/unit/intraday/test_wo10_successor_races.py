"""Successor currentness, failure retention and selection race qualification."""
from copy import deepcopy
from datetime import timedelta
from dataclasses import replace

import pytest

from kronos.intraday.wo09_readiness import CurrentnessState
from kronos.intraday.wo10_futures_contract import digest, normalize
from tests.unit.intraday.test_wo10_futures import NOW, fixture, session, master, config
from tests.unit.intraday.test_wo10_native_composition import native, retain


def wired(tmp_path):
    app,kw,v,src=native(tmp_path);retain(app,v)
    inputs={k:x for k,x in kw.items() if k not in {"request_identity","adapter","geometry_evidence","target_population"}}
    authority={k:inputs.get(k) for k in ("master","underlying","active_mcx","economics","configuration")}
    inputs["authority_source"]=lambda:authority
    app.acquisition_source=lambda h,p:inputs
    return app,kw,inputs,authority


@pytest.mark.parametrize("stage",["plan","acquisition","comparison","selection"])
def test_exact_pointer_rechecked_at_each_prospective_stage(tmp_path,monkeypatch,stage):
    app,kw,inputs,authority=wired(tmp_path);h=kw["adapter"].wo09
    def supersede():
        app.wo09.mark_currentness(h.canonical_subject_identity,CurrentnessState.REASSESSMENT_DUE,updated_at=NOW+timedelta(seconds=1), expected=app.wo09.expectation(h.canonical_subject_identity))
    if stage=="plan":
        import kronos.intraday.wo10_native_adapter as module
        original=module.adapt_native
        def changed(*args,**kwargs):
            adapted=original(*args,**kwargs);supersede();return adapted
        monkeypatch.setattr(module,"adapt_native",changed)
    if stage=="acquisition":
        def changed(h,p):supersede();return inputs
        app.acquisition_source=changed
    if stage=="comparison":
        original=kw["provider"].full_quotes
        def changed(*args,**kwargs):
            quotes=original(*args,**kwargs);supersede();return quotes
        kw["provider"].full_quotes=changed
    if stage=="selection":
        c=app.construct_current(handoff_identity=h.handoff_identity,request_identity="BEFORE-SELECTION")
        supersede()
        with pytest.raises(ValueError):app.select(c.identity,choice="SELECTED_FUTURE",lots=1,session=session(),action_identity="STALE")
        assert not app.store.records("WO10_SELECTED_TRADE_HANDOFF_V1")
    else:
        with pytest.raises(ValueError):app.construct_current(handoff_identity=h.handoff_identity,request_identity="RACE")
        assert not app.store.records("WO10_SPONSOR_COMPARISON_V1")
        if stage=="plan":assert not app.store.records("WO10_CANONICAL_TRADE_PLAN_V1")
        assert len(kw["provider"].calls)==(1 if stage=="comparison" else 0)


@pytest.mark.parametrize("field",["master","underlying","active_mcx"])
@pytest.mark.parametrize("stage",["quote_return","selection"])
def test_exact_current_market_input_change_blocks_progression(tmp_path,field,stage):
    app,kw,inputs,authority=wired(tmp_path);h=kw["adapter"].wo09
    def change():authority[field]="CHANGED-AUTHORITY"
    if stage=="quote_return":
        original=kw["provider"].full_quotes
        def changed(*args,**kwargs):
            quotes=original(*args,**kwargs);change();return quotes
        kw["provider"].full_quotes=changed
        result=app.construct_current(handoff_identity=h.handoff_identity,request_identity="MARKET-RACE")
        assert result.data["state"]=="FUTURE_SNAPSHOT_UNAVAILABLE"
        assert not app.store.records("WO10_SPONSOR_COMPARISON_V1")
        assert len([r for r in app.store.records("WO10_ACQUISITION_OPERATION_V1") if r.data["state"]=="QUOTE_RECEIVED"])==1
    else:
        c=app.construct_current(handoff_identity=h.handoff_identity,request_identity="MARKET-RACE")
        change()
        assert app.decision_state(c,now=NOW,session=session())=="SUPERSEDED"
        with pytest.raises(ValueError):app.select(c.identity,choice="SELECTED_FUTURE",lots=1,session=session(),action_identity="STALE-MARKET")
        assert not app.store.records("WO10_SELECTED_TRADE_HANDOFF_V1")


@pytest.mark.parametrize("shift",["session","date"])
def test_session_and_trading_date_change_after_quote(tmp_path,shift):
    app,kw,inputs,authority=wired(tmp_path);h=kw["adapter"].wo09
    if shift=="date":
        inputs["session_source"]=lambda _:session(NOW+timedelta(days=1))
    else:
        original=inputs["session_source"]
        s=original(NOW)
        inputs["session_source"]=lambda _:replace(s,schedule=replace(s.schedule,session_id="FOREIGN"))
    result=app.construct_current(handoff_identity=h.handoff_identity,request_identity="SESSION-RACE")
    assert result.data["state"]=="FUTURE_SNAPSHOT_UNAVAILABLE"
    assert not app.store.records("WO10_SPONSOR_COMPARISON_V1")


def test_missing_current_market_adapter_prevents_quote(tmp_path):
    app,kw,inputs,authority=wired(tmp_path);inputs.pop("authority_source")
    result=app.construct_current(handoff_identity=kw["adapter"].wo09.handoff_identity,request_identity="NO-MARKET")
    assert result.data["reason"]=="WO10_CURRENT_MARKET_AUTHORITY_UNAVAILABLE"
    assert kw["provider"].calls==[]


def test_missing_config_does_not_create_default_budget(tmp_path):
    app,kw,inputs,authority=wired(tmp_path);inputs["configuration"]=authority["configuration"]=None
    c=app.construct_current(handoff_identity=kw["adapter"].wo09.handoff_identity,request_identity="NO-CONFIG")
    assert app.store.load(c.data["advisory_identity"]).data["risk_warning_state"]=="REFERENCE_NOT_CONFIGURED"
    assert c.data["executability"]=="EXECUTABLE"
    assert app.store.records("WO10_RISK_REFERENCE_V1")==()


def test_interrupted_construction_cannot_retry_itself(tmp_path,monkeypatch):
    app,kw,inputs,authority=wired(tmp_path);h=kw["adapter"].wo09
    def interrupted(*args,**kwargs):raise RuntimeError("simulated process interruption")
    monkeypatch.setattr(app.structural_loader,"load",interrupted)
    with pytest.raises(RuntimeError):app.construct_current(handoff_identity=h.handoff_identity,request_identity="ONCE")
    with pytest.raises(ValueError,match="INTERRUPTED"):app.construct_current(handoff_identity=h.handoff_identity,request_identity="ONCE")
    assert not kw["provider"].calls


def test_request_identity_does_not_cross_handoff(tmp_path):
    app,kw,inputs,authority=wired(tmp_path);h=kw["adapter"].wo09
    app.construct_current(handoff_identity=h.handoff_identity,request_identity="ONCE")
    from kronos.application.intraday_wo09 import IntradayWo09Application
    r=app.wo09.load_readiness(h.readiness_identity)
    h2=__import__("tests.unit.intraday.recovery_r2b_fixtures",fromlist=["historical_handoff"]).historical_handoff(app.wo09,r,created_at=NOW+timedelta(seconds=1),first_five_of_five_at=NOW)
    app.clock=lambda:NOW+timedelta(seconds=1)
    with pytest.raises(ValueError,match="IDEMPOTENCY_CONFLICT"):app.construct_current(handoff_identity=h2.handoff_identity,request_identity="ONCE")
    assert len(kw["provider"].calls)==1


def test_construction_reservation_prevents_duplicate_without_holding_source_guards(tmp_path):
    from threading import Event, Thread
    app,kw,inputs,authority=wired(tmp_path);h=kw['adapter'].wo09
    acquisition=Event();release=Event();errors=[];results=[]
    original=kw['provider'].full_quotes
    def held(*args,**kwargs):
        # Acquisition is outside every final publication and construction guard.
        with app.store.transaction(construction=True), app.store.transaction():
            with app.wo09.transaction(expected=app.wo09.expectation(h.canonical_subject_identity)):
                acquisition.set()
        if not release.wait(3):raise RuntimeError('TEST_ACQUISITION_RELEASE_TIMEOUT')
        return original(*args,**kwargs)
    kw['provider'].full_quotes=held
    def construct():
        try:results.append(app.construct_current(handoff_identity=h.handoff_identity,request_identity='RESERVED'))
        except Exception as exc:errors.append(exc)
    worker=Thread(target=construct);worker.start()
    try:
        assert acquisition.wait(3)
        with pytest.raises(ValueError,match='WO10_INTERRUPTED_OPERATION_REQUIRES_NEW_REQUEST'):
            app.construct_current(handoff_identity=h.handoff_identity,request_identity='RESERVED')
    finally:
        release.set();worker.join(3)
    assert not worker.is_alive() and errors==[] and len(results)==1
    assert len(kw['provider'].calls)==1
    assert app.store.current(h.canonical_subject_identity)==results[0]


def test_construction_callback_follows_all_source_and_construction_guard_release(tmp_path):
    from threading import Event, Thread
    app,kw,inputs,authority=wired(tmp_path);h=kw['adapter'].wo09
    notices=[];errors=[]
    def listener(kind,identity):
        done=Event()
        def inspect():
            try:
                with app.eligibility._sources():
                    with app.wo09.transaction(expected=app.wo09.expectation(h.canonical_subject_identity)):
                        with app.store.transaction(construction=True), app.store.transaction():done.set()
            except Exception as exc:errors.append(exc)
        worker=Thread(target=inspect);worker.start();worker.join(3)
        if worker.is_alive() or not done.is_set():errors.append('GUARD_NOT_RELEASED')
        notices.append((kind,identity))
    app.store.notification_listener=listener
    result=app.construct_current(handoff_identity=h.handoff_identity,request_identity='NOTICE')
    assert errors==[] and notices==[('COMPARISON',result.identity)]
    assert not getattr(app.store,'notification_failure',None)


@pytest.mark.parametrize('deferred',[False,True])
def test_comparison_callback_default_and_captured_deferral(tmp_path,deferred):
    app,kw,_,_=wired(tmp_path);h=kw['adapter'].wo09
    comparison=app.construct_current(handoff_identity=h.handoff_identity,request_identity='SOURCE')
    from kronos.intraday.wo10_futures_store import FuturesStore
    store=FuturesStore(tmp_path/'callback-store');calls=[]
    store.notification_listener=lambda *args:calls.append(('original',args))
    store.journal_listener=lambda *args:calls.append(('journal',args))
    pointer=store.publish(comparison,previous=None,emit_notifications=not deferred)
    assert store.current(comparison.data['subject'])==comparison
    assert pointer.data['comparison_identity']==comparison.identity
    if deferred:
        assert calls==[]
        store.notification_listener=lambda *args:pytest.fail('replacement listener used')
        store.journal_listener=lambda *args:pytest.fail('replacement journal used')
        store.notify_publication(comparison.identity)
    assert calls==[('original',('COMPARISON',comparison.identity)),('journal',('COMPARISON',comparison.identity))]


def test_comparison_callback_failure_preserves_commit_and_selection_journal_release(tmp_path):
    from threading import Event,Thread
    app,kw,_,_=wired(tmp_path);h=kw['adapter'].wo09
    def broken(*args):raise RuntimeError('POST_COMMIT_DELIVERY_FAILURE')
    app.store.notification_listener=broken
    comparison=app.construct_current(handoff_identity=h.handoff_identity,request_identity='SOURCE')
    assert app.store.current(comparison.data['subject'])==comparison
    assert app.store.notification_failure=='NOTIFICATION_PROJECTION_UNAVAILABLE'
    calls=[];errors=[]
    def journal(kind,identity):
        done=Event()
        def reenter():
            try:
                with app.eligibility._sources(), app.wo09.transaction(expected=app.wo09.expectation(h.canonical_subject_identity)), app.store.transaction():done.set()
            except Exception as exc:errors.append(exc)
        worker=Thread(target=reenter);worker.start();worker.join(3)
        if worker.is_alive() or not done.is_set():errors.append('SELECTION_GUARD_HELD')
        calls.append((kind,identity))
    app.store.journal_listener=journal
    selected=app.select(comparison.identity,choice='SELECTED_FUTURE',lots=1,session=session(),action_identity='SELECT')
    assert errors==[] and calls==[('SELECTION',selected.identity)]
    assert len(app.store.records('WO10_SELECTED_TRADE_HANDOFF_V1'))==1


@pytest.mark.parametrize('phase',['before','after'])
def test_comparison_pointer_fault_retains_truth_without_success(tmp_path,monkeypatch,phase):
    app,kw,_,_=wired(tmp_path);h=kw['adapter'].wo09
    comparison=app.construct_current(handoff_identity=h.handoff_identity,request_identity='SOURCE')
    from kronos.intraday.wo10_futures_store import FuturesStore
    import kronos.intraday.wo10_futures_store as owner
    store=FuturesStore(tmp_path/'fault-store');calls=[]
    store.notification_listener=lambda *args:calls.append(args)
    original=owner.os.replace
    def fail(src,dst):
        if phase=='after':original(src,dst)
        raise OSError('DOWNSTREAM_REPLACE_'+phase)
    monkeypatch.setattr(owner.os,'replace',fail)
    with pytest.raises(OSError,match='DOWNSTREAM_REPLACE_'+phase):
        store.publish(comparison,previous=None,emit_notifications=False)
    assert store.load(comparison.identity)==comparison and calls==[]
    assert (store.current(comparison.data['subject']) is None)==(phase=='before')
    assert store._deferred_notices=={}
