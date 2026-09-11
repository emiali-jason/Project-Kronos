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
        app.wo09.mark_currentness(h.canonical_subject_identity,CurrentnessState.REASSESSMENT_DUE,updated_at=NOW+timedelta(seconds=1))
    if stage=="plan":
        import kronos.application.intraday_futures as module
        original=module.construct_plan
        def changed(*args,**kwargs):
            p=original(*args,**kwargs);supersede();return p
        monkeypatch.setattr(module,"construct_plan",changed)
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
    h2=IntradayWo09Application(app.wo09).create_handoff(r,created_at=NOW+timedelta(seconds=1),first_five_of_five_at=NOW)
    app.clock=lambda:NOW+timedelta(seconds=1)
    with pytest.raises(ValueError,match="IDEMPOTENCY_CONFLICT"):app.construct_current(handoff_identity=h2.handoff_identity,request_identity="ONCE")
    assert len(kw["provider"].calls)==1
