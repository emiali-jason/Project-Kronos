"""Sponsor ADR-0046 correction and remaining lifecycle boundary qualification.

All records, market facts, requests and capabilities are isolated test evidence.
"""
from dataclasses import asdict, replace
from datetime import timedelta, date
from decimal import Decimal as D
import json
import pytest
from tests.unit.intraday.test_wo11_lifecycle import (
    NOW, FUTURE, track, qualified, active, tick, observation,
)
from tests.unit.intraday.test_wo11_lifecycle_application import fixture, emit
from kronos.intraday.wo11_lifecycle import (
    arm, observe, timing, gap, boundary, request_close, metrics, research_handoff,
    TRADING_EXIT_REASONS,
)
from kronos.intraday.wo11_lifecycle_contract import (
    record, require, LifecycleRecord, POST_ENTRY_INVALIDATION,
    FUTURE_INVALIDATION_CAPABILITY, encoded, digest,
)

THESIS = {"event_code":"COMPLETED_GOVERNED_15M_FAILURE_BELOW_PULLBACK_LOW",
          "reference":"105", "source_identity":"original-native-structure"}


@pytest.mark.parametrize("truth", ["PAPER_POSITION", "PAPER_OBSERVATION"])
def test_original_definition_is_context_not_observed_event(truth):
    s=active(truth,invalidation=THESIS)
    # Price traverses the thesis-context reference, but is inside Stop/Target.
    t=tick(seconds=3,value="104")
    s=observe(s,observation(s,t)).current
    assert s.data["state"]=="ACTIVE" and s.data["exit"] is None
    assert s.data["intake"]["invalidation"]==THESIS
    assert s.data["post_entry_analytical_invalidation"]=="NOT_COMMISSIONED_V1"
    s=request_close(s,at=NOW+timedelta(seconds=4),reason="SPONSOR_EXIT",source_identity="sponsor").current
    t=tick(seconds=5,value="104")
    result=observe(s,observation(s,t));s=result.current
    metric=next(e for e in result.evidence if e.schema=="WO11_METRICS_V1")
    handoff=research_handoff(s,retained_metrics=metric)
    assert handoff.data["original_thesis_invalidation"]==THESIS
    assert handoff.data["thesis_invalidation_role"]=="THESIS_DEFINITION_CONTEXT_ONLY"
    assert handoff.data["post_entry_analytical_invalidation"]=="NOT_COMMISSIONED_V1"
    assert handoff.data["exit_reason"]=="SPONSOR_EXIT"
    assert handoff.data["terminal_status"]=="CLOSED"
    assert handoff.data["sponsor_exit_request_identity"]==s.data["close_request"]["identity"]
    assert "NOT_INVALIDATED" not in handoff.payload_json


@pytest.mark.parametrize("entered", [False,True])
def test_no_analytical_close_api_even_with_original_definition(entered):
    s=active(invalidation=THESIS) if entered else track(invalidation=THESIS)
    with pytest.raises(ValueError,match="WO11_CLOSE_REASON_INVALID"):
        request_close(s,at=NOW+timedelta(seconds=10),reason="ANALYTICAL_INVALIDATION",source_identity="original-native-structure")


@pytest.mark.parametrize("reason", ["UPSTREAM_SUPERSEDED","CONTRACT_INVALIDATED"])
def test_currentness_cannot_be_relabelled_post_entry_analytical_close(reason):
    with pytest.raises(ValueError,match="POST_ENTRY_REASSESSMENT_NOT_COMMISSIONED"):
        request_close(active(),at=NOW+timedelta(seconds=4),reason=reason,source_identity="source")


def test_future_capability_does_not_reinterpret_v1_bytes():
    s=track(invalidation=THESIS);raw=encoded(asdict(s))
    assert FUTURE_INVALIDATION_CAPABILITY=="POST_ENTRY_ANALYTICAL_INVALIDATION_V2"
    assert LifecycleRecord(**json.loads(raw))==s
    with pytest.raises(ValueError,match="CONTRACT_INVALID"):
        record("WO11_TRACK_V1",**(s.data|{"post_entry_analytical_invalidation":"COMMISSIONED_V2"}))
    assert encoded(asdict(s))==raw and s.data["post_entry_analytical_invalidation"]==POST_ENTRY_INVALIDATION


@pytest.mark.parametrize("value,reason", [("97","STOP_LOSS"),("116","TARGET")])
def test_stop_target_do_not_manufacture_invalidation(value,reason):
    s=active(invalidation=THESIS);t=tick(seconds=3,value=value)
    result=observe(s,observation(s,t))
    assert result.current.data["exit"]["reason"]==reason
    assert all(e.data["post_entry_analytical_invalidation"]=="NOT_COMMISSIONED_V1" for e in result.evidence)
    assert not any(e.schema.startswith("WO11_ANALYTICAL") for e in result.evidence)


def test_exact_three_exit_vocabulary_and_no_fourth_authority():
    assert TRADING_EXIT_REASONS=={"STOP_LOSS","TARGET","SPONSOR_EXIT"}
    assert "ANALYTICAL_INVALIDATION" not in TRADING_EXIT_REASONS
    with pytest.raises(ValueError,match="WO11_EXIT_REASON_INVALID"):
        record("WO11_EXIT_V1",reason="ANALYTICAL_INVALIDATION")
    d=active().data
    with pytest.raises(ValueError,match="WO11_EXIT_TERMINAL_CONTRACT_INVALID"):
        record("WO11_TRACK_V1",**(d|{"exit_reason":"SESSION_ENDED","terminal_status":"CLOSED"}))


@pytest.mark.parametrize("truth", ["PAPER_POSITION","PAPER_OBSERVATION"])
def test_sponsor_exit_is_request_then_first_subsequent_eligible_ltp(truth):
    s=active(truth);request_at=NOW+timedelta(seconds=4)
    s=request_close(s,at=request_at,reason="SPONSOR_EXIT",source_identity="sponsor-request").current
    before=tick(seconds=3,value="104")
    assert observe(s,observation(s,before)).current.data["exit"] is None
    late=tick(seconds=5,value="105",lag=5.000001)
    assert observe(s,observation(s,late)).current.data["exit"] is None
    eligible=tick(seconds=6,value="106")
    result=observe(s,observation(s,eligible)).current
    assert result.data["exit_reason"]=="SPONSOR_EXIT"
    assert result.data["terminal_status"]=="CLOSED"
    assert result.data["exit"]["price"]=="106"
    assert result.data["exit"]["price_fact"]==observation(s,eligible).data["fact_identity"]


def test_terminal_and_data_status_never_become_trading_exit_reason():
    interrupted=gap(active(),at=NOW+timedelta(seconds=3),reason="DISCONNECTED").current
    assert interrupted.data["exit_reason"] is None and interrupted.data["terminal_status"] is None
    ended=boundary(interrupted,at=NOW+timedelta(hours=5)).current
    assert ended.data["exit_reason"] is None and ended.data["terminal_status"]=="SESSION_ENDED"


@pytest.mark.parametrize("entered", [False,True])
def test_pre_entry_supersession_only(tmp_path,monkeypatch,entered):
    app,h,f,provider,clock,cap,hub=fixture(tmp_path,monkeypatch)
    s=app.action(handoff_identity=h.identity,action="ACTIVATE_PAPER",action_identity="arm")
    clock[0]+=timedelta(minutes=5);app.pulse();s=app.store.restore()[0]
    if entered:
        clock[0]+=timedelta(seconds=1);s=emit(app,cap,clock,s,s.data["intake"]["entry"])
        assert s.data["entry"] is not None
    def unavailable(*a,**k):raise ValueError("WO11_UPSTREAM_SUPERSEDED")
    monkeypatch.setattr("kronos.application.intraday_lifecycle.load_intake",unavailable)
    clock[0]+=timedelta(seconds=1);app.pulse();s=app.store.restore()[0]
    if entered:
        assert s.data["state"]=="ACTIVE" and s.data["close_request"] is None
        clock[0]+=timedelta(seconds=1);s=emit(app,cap,clock,s,s.data["intake"]["target"])
        assert s.data["exit"]["reason"]=="TARGET"
    else:
        assert s.data["state"]=="INVALIDATED_BEFORE_ENTRY" and s.data["entry"] is None
        assert s.data["close_request"]["reason"]=="UPSTREAM_SUPERSEDED"


def test_supersession_between_pulse_and_entry_tick(tmp_path,monkeypatch):
    app,h,f,provider,clock,cap,hub=fixture(tmp_path,monkeypatch)
    s=app.action(handoff_identity=h.identity,action="OBSERVE",action_identity="arm")
    clock[0]+=timedelta(minutes=5);app.pulse();s=app.store.restore()[0]
    def unavailable(*a,**k):raise ValueError("WO11_HANDOFF_SUPERSEDED")
    monkeypatch.setattr("kronos.application.intraday_lifecycle.load_intake",unavailable)
    clock[0]+=timedelta(seconds=1);s=emit(app,cap,clock,s,s.data["intake"]["entry"])
    assert s.data["entry"] is None and s.data["state"]=="INVALIDATED_BEFORE_ENTRY"


@pytest.mark.parametrize("truth", ["PAPER_POSITION","PAPER_OBSERVATION"])
@pytest.mark.parametrize("seconds,enters", [(2,True),(3,False),(4,False)])
def test_entry_cutoff_equality_is_not_admitted(truth,seconds,enters):
    s=qualified(truth,entry_cutoff=NOW+timedelta(seconds=3))
    t=tick(seconds=seconds);s=observe(s,observation(s,t)).current
    assert (s.data["entry"] is not None)==enters


@pytest.mark.parametrize("truth", ["PAPER_POSITION","PAPER_OBSERVATION"])
@pytest.mark.parametrize("entered", [False,True])
@pytest.mark.parametrize("reason", ["SESSION_ENDED","CONTRACT_EXPIRED"])
def test_final_lawful_boundary_no_historical_price(truth,entered,reason):
    s=active(truth) if entered else qualified(truth)
    result=boundary(s,at=NOW+timedelta(hours=5),reason=reason)
    assert result.current.data["state"]==("CLOSED_OUTCOME_UNAVAILABLE" if entered else "EXPIRED_BEFORE_ENTRY")
    assert result.current.data["exit"] is None
    h=research_handoff(result.current)
    assert h.data["post_entry_analytical_invalidation"]=="NOT_COMMISSIONED_V1"
    t=tick(seconds=24*3600,value="116")
    assert observe(result.current,observation(result.current,t)).current.data["exit"] is None


@pytest.mark.parametrize("direction,prices,mfe,mae", [("LONG",["103","108","101"],"5","2"),("SHORT",["101","97","104"],"4","3")])
def test_directional_metrics_samples(direction,prices,mfe,mae):
    s=active(direction=direction)
    for sec,value in enumerate(prices,3):
        t=tick(seconds=sec,value=value);s=observe(s,observation(s,t)).current
    m=metrics(s.data).data
    assert D(m["mfe"])==D(mfe) and D(m["mae"])==D(mae)
    assert m["samples"]==4 and m["complete"]


def test_one_sample_and_invalid_initial_risk_are_explicit():
    s=active();m=metrics(s.data).data
    assert m["mfe"]==m["mae"]=="0" and m["samples"]==1
    d=s.data;d["intake"]["stop"]=d["entry"]["price"]
    assert metrics(d,exit_price="105").data["model_r"] is None


@pytest.mark.parametrize("units,expected", [("100","1300"),("250","3250"),(None,None)])
def test_exact_one_lot_economics_or_unavailable(units,expected):
    s=active(monetary_units=units);m=metrics(s.data,exit_price="116").data
    assert m["gross_model_result"]==expected


@pytest.mark.parametrize("first,second,reason", [("97","116","STOP_LOSS"),("116","97","TARGET")])
def test_ordered_first_terminal_event_not_replaced(first,second,reason):
    s=active();t=tick(seconds=3,value=first);s=observe(s,observation(s,t)).current
    exit_identity=s.data["exit"]["identity"]
    t=tick(seconds=4,value=second);s=observe(s,observation(s,t)).current
    assert s.data["exit"]["reason"]==reason and s.data["exit"]["identity"]==exit_identity


@pytest.mark.parametrize("first,second", [("97","116"),("116","97")])
def test_unordered_terminal_conflict_retains_original_evidence(first,second):
    s=active();t=tick(seconds=3,value=first);initial=observe(s,observation(s,t))
    raw=encoded(asdict(initial.current));s=initial.current
    t=tick(seconds=3,value=second);successor=observe(s,observation(s,t)).current
    assert successor.data["state"]=="OUTCOME_AMBIGUOUS"
    assert encoded(asdict(initial.current))==raw


@pytest.mark.parametrize("initial,second", [("ACTIVATE_PAPER","OBSERVE"),("OBSERVE","ACTIVATE_PAPER")])
def test_persistent_cross_truth_claim_both_orders(tmp_path,monkeypatch,initial,second):
    app,h,*_=fixture(tmp_path,monkeypatch)
    app.action(handoff_identity=h.identity,action=initial,action_identity="first")
    with pytest.raises(ValueError,match="ALREADY_CLAIMED"):
        app.action(handoff_identity=h.identity,action=second,action_identity="new-id")
    assert len(app.store.restore())==1


def test_do_nothing_is_retained_without_track_or_monitor(tmp_path,monkeypatch):
    app,h,f,provider,clock,cap,hub=fixture(tmp_path,monkeypatch)
    r=app.action(handoff_identity=h.identity,action="DO_NOTHING",action_identity="none")
    assert r.schema=="WO11_ACTION_V1" and app.store.restore()==()
    assert hub.active_session_count==0 and len(provider.calls)==1


def test_sponsor_controls_show_actions_and_context_capability():
    from kronos.browser.intraday_lifecycle_control import actions_html
    html=actions_html({"selected_handoff":"exact-handoff"})
    assert all(x in html for x in ["ACTIVATE PAPER","OBSERVE","DO NOTHING","1 lot"])
    assert "INVALIDATION MONITORING ACTIVE" not in html


def test_no_analytical_producer_in_actual_runtime_composition(tmp_path):
    from kronos.application.intraday_runtime import create_intraday_runtime
    from tests.unit.provider.test_shared_provider_runtime import _shared
    shared,provider,calls=_shared();runtime=create_intraday_runtime(shared,evidence_root=tmp_path)
    app=runtime.lifecycle_application
    assert not any("invalidation" in key for key in vars(app))
    runtime.futures_application.operational_guard=lambda:True
    assert app.operational_guard() is True
    app.pulse()
    assert not app.store.root.exists() and provider.begin_count==0 and calls==[]


@pytest.mark.parametrize("family", ["CRUDE","COPPER","GOLDM","SILVERM"])
def test_actual_mcx_binding_serialization_and_timing_adapter(family,monkeypatch):
    from types import SimpleNamespace
    from tests.unit.instrument.test_active_derivative_selection import _resolve
    from tests.unit.intraday.test_wo10_futures import NOW as market_now
    from kronos.intraday.wo10_futures_contract import normalize
    from kronos.application.intraday_lifecycle_timing import GovernedLifecycleTimingSource
    resolutions=_resolve(market_now);binding=resolutions.for_subject(family).binding
    assert binding is not None
    i={"subject":binding.canonical_subject_id,"contract":{"active_mcx":normalize(binding)}}
    assert "binding_identity" not in i["contract"]["active_mcx"]
    assert i["contract"]["active_mcx"]["active_binding"]["binding_identity"]==binding.binding_identity
    captured=[]
    monkeypatch.setattr("kronos.application.intraday_lifecycle_timing.governed_market_session_identities",lambda **k:("session","boundary"))
    monkeypatch.setattr("kronos.application.intraday_lifecycle_timing.qualify_timing",lambda *a,**k:"QUALIFIED_SOURCE_RECEIVED")
    class Source:
        def acquire(self,**kwargs):
            captured.append(kwargs);return SimpleNamespace(probables_v2_facts="existing-owner-facts")
    source=GovernedLifecycleTimingSource(factory=lambda r:Source(),calendar=object(),
        reconciliation=SimpleNamespace(members=[SimpleNamespace(canonical_identity=binding.canonical_subject_id)]),
        resolutions=lambda:resolutions,clock=lambda:market_now)
    assert source(SimpleNamespace(data={"intake":i}))=="QUALIFIED_SOURCE_RECEIVED"
    assert len(captured)==1


def test_exact_contract_roll_is_separate_from_analytical_invalidation():
    from tests.unit.instrument.test_active_derivative_selection import _resolve,IST
    from kronos.market.calendar import MarketCalendarPublisher
    from kronos.intraday.wo10_futures_contract import normalize
    from datetime import datetime
    at=datetime(2026,8,31,12,tzinfo=IST)
    cutoff=MarketCalendarPublisher().mcx_contract_session_profile(contract_family="COPPER",contract_expiry=at.date(),trading_date=at.date(),observed_at=at).expiry_eligibility_boundary
    before=_resolve(cutoff).for_subject("COPPER").binding
    after=_resolve(cutoff+timedelta(microseconds=1),previous={before.canonical_subject_id:before}).for_subject("COPPER").binding
    s=active();d=s.data;d["intake"]["subject"]=before.canonical_subject_id
    d["intake"]["contract"]={"active_mcx":normalize(before)}
    d["intake"]["session_close"]=(cutoff+timedelta(hours=1)).isoformat()
    s=record("WO11_TRACK_V1",**d)
    with pytest.raises(ValueError,match="BOUNDARY_CAUSAL_PREREQUISITE_NOT_SATISFIED"):
        boundary(s,at=cutoff+timedelta(microseconds=1),contract_evidence=after)
    # The valid unit scenario is armed and entered before the governed roll.
    d["armed_at"]=(cutoff-timedelta(seconds=10)).isoformat()
    d["entry"]["at"]=(cutoff-timedelta(seconds=8)).isoformat()
    d["updated_at"]=d["entry"]["at"]
    s=record("WO11_TRACK_V1",**d)
    result=boundary(s,at=cutoff+timedelta(microseconds=1),contract_evidence=after)
    assert result.current.data["state"]=="CLOSED_OUTCOME_UNAVAILABLE"
    e=next(x for x in result.evidence if x.schema=="WO11_CONTRACT_BOUNDARY_V1")
    assert e.data["source"]["integrity_identity"]==after.integrity_identity
    assert e.data["reason"]=="CONTRACT_ROLLED" and e.data["post_entry_analytical_invalidation"]=="NOT_COMMISSIONED_V1"
    with pytest.raises(ValueError,match="ROLL_NOT_ESTABLISHED"):
        boundary(s,at=cutoff,contract_evidence=before)


def test_earlier_retained_contract_boundary_is_terminal():
    s=active(contract_boundary=NOW+timedelta(seconds=4))
    result=boundary(s,at=NOW+timedelta(seconds=4))
    assert result.current.data["state"]=="CLOSED_OUTCOME_UNAVAILABLE"
    event=next(e for e in result.evidence if e.schema=="WO11_EVENT_V1")
    assert event.data["reason"]=="CONTRACT_EXPIRED"


@pytest.mark.parametrize("subject", ["MCX-NATGAS","MCX-SUBJECT-NATGAS"])
def test_natgas_hold_is_not_lifecycle_commissioning(subject):
    with pytest.raises(ValueError,match="NATGAS_COMMISSIONING_HELD"):
        track(subject=subject)


def test_deleted_ancestor_observation_cannot_restore_current(tmp_path,monkeypatch):
    app,h,f,provider,clock,cap,hub=fixture(tmp_path,monkeypatch)
    s=app.action(handoff_identity=h.identity,action="ACTIVATE_PAPER",action_identity="arm")
    clock[0]+=timedelta(minutes=5);app.pulse();s=app.store.restore()[0]
    for n in range(5):
        clock[0]+=timedelta(seconds=1);s=emit(app,cap,clock,s,s.data["intake"]["entry"])
    observations=app.store.records("WO11_MARKET_OBSERVATION_V1")
    first=min(observations,key=lambda r:r.data["decision_at"])
    (app.store.root/"records"/(first.identity+".json")).unlink()
    with pytest.raises(FileNotFoundError):app.store.restore()


def test_compare_and_swap_and_interrupted_orphan_do_not_replace_current(tmp_path,monkeypatch):
    from kronos.intraday.wo11_lifecycle import gap
    app,h,*_=fixture(tmp_path,monkeypatch)
    s=app.action(handoff_identity=h.identity,action="OBSERVE",action_identity="arm")
    a=app.store.load(s.data["authorization_identity"])
    successor=gap(s,at=app.clock()+timedelta(seconds=1),reason="isolated-interruption")
    for e in successor.evidence:app.store.retain(e)
    assert app.store.restore()==(s,)
    with app.store.transaction():
        with pytest.raises(ValueError,match="POINTER_CHANGED"):
            app.store.publish(successor,claim=a.data["claim"],previous="wrong-predecessor")
    assert app.store.restore()==(s,)


def test_different_governed_opportunity_has_distinct_claim():
    first=track(opportunity_identity="opportunity-A")
    second=track(opportunity_identity="opportunity-B")
    assert first.data["track_identity"]!=second.data["track_identity"]


@pytest.mark.parametrize("missing", [None,"invalid",123])
def test_invalid_received_timestamp_is_unavailable(missing):
    s=track();t=tick();object.__setattr__(t,"received_at",missing)
    from kronos.intraday.wo11_lifecycle_contract import websocket_observation
    o=websocket_observation(t,authorization_identity=s.data["authorization_identity"],instrument=FUTURE,
        session_identity="session",expected_session_identity="session",causal_at=NOW,decision_at=NOW+timedelta(seconds=3))
    assert not o.data["eligible"] and o.data["reason"]=="WEBSOCKET_TIMESTAMP_UNAVAILABLE"


def test_restore_resumes_with_existing_capability_and_fresh_baseline(tmp_path,monkeypatch):
    from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
    from kronos.intraday.wo11_lifecycle_store import LifecycleStore
    app,h,f,provider,clock,cap,hub=fixture(tmp_path,monkeypatch)
    s=app.action(handoff_identity=h.identity,action="ACTIVATE_PAPER",action_identity="arm")
    clock[0]+=timedelta(minutes=5);app.pulse();s=app.store.restore()[0]
    clock[0]+=timedelta(seconds=1);s=emit(app,cap,clock,s,s.data["intake"]["entry"])
    app.shutdown()
    restored=IntradayLifecycleApplication(futures=app.futures,store=LifecycleStore(app.store.root),clock=app.clock,
        session_source=app.session_source,timing_source=app.timing_source,operational_guard=app.operational_guard)
    restored.bind_monitoring(hub,lambda:cap)
    clock[0]+=timedelta(seconds=1);restored.pulse();s=restored.store.restore()[0]
    assert s.data["baseline_required"]
    clock[0]+=timedelta(seconds=1);s=emit(restored,cap,clock,s,s.data["intake"]["target"])
    assert s.data["state"]=="ACTIVE" and s.data["exit"] is None
    assert len(provider.calls)==1


def test_actual_runtime_application_accepts_exact_handoff_with_governed_guard(tmp_path,monkeypatch):
    from kronos.application.intraday_runtime import create_intraday_runtime
    from tests.unit.provider.test_shared_provider_runtime import _shared
    from kronos.application.shared_monitoring import SharedSwingMonitoringHub
    isolated,h,f,provider,clock,cap,hub=fixture(tmp_path,monkeypatch)
    shared,backend,calls=_shared();runtime=create_intraday_runtime(shared,evidence_root=tmp_path/"runtime",clock=lambda:clock[0])
    # Retained stores and lawful isolated source adapters replace external I/O.
    # The production-composed lifecycle owner and operational guard are retained.
    runtime.futures_application.__dict__.update(isolated.futures.__dict__)
    app=runtime.lifecycle_application
    app.session_source=isolated.session_source;app.timing_source=isolated.timing_source
    app.bind_monitoring(SharedSwingMonitoringHub(),lambda:cap)
    s=app.action(handoff_identity=h.identity,action="OBSERVE",action_identity="runtime-arm")
    clock[0]+=timedelta(minutes=5);app.pulse();s=app.store.restore()[0]
    clock[0]+=timedelta(seconds=1);s=emit(app,cap,clock,s,s.data["intake"]["entry"])
    clock[0]+=timedelta(seconds=1);s=emit(app,cap,clock,s,s.data["intake"]["target"])
    assert s.data["state"]=="CLOSED" and app.store.records("WO11_WO12_HANDOFF_V1")
    assert backend.begin_count==0 and calls==[]


@pytest.mark.parametrize("via_tick", [False,True])
@pytest.mark.parametrize("error", [FileNotFoundError("missing"),ValueError("WO11_HANDOFF_GRAPH_MISMATCH")])
def test_missing_or_corrupt_currentness_is_not_proven_supersession(tmp_path,monkeypatch,via_tick,error):
    app,h,f,provider,clock,cap,hub=fixture(tmp_path,monkeypatch)
    s=app.action(handoff_identity=h.identity,action="ACTIVATE_PAPER",action_identity="arm")
    clock[0]+=timedelta(minutes=5);app.pulse();s=app.store.restore()[0]
    def unavailable(*a,**k):raise error
    monkeypatch.setattr("kronos.application.intraday_lifecycle.load_intake",unavailable)
    clock[0]+=timedelta(seconds=1)
    if via_tick:s=emit(app,cap,clock,s,s.data["intake"]["entry"])
    else:app.pulse();s=app.store.restore()[0]
    assert s.data["entry"] is None and s.data["close_request"] is None
    assert s.data["monitoring"]=="INTERRUPTED" and s.data["baseline_required"]
    check=app.store.records("WO11_AUTHORITY_CHECK_V1")[-1]
    assert check.data["result"]=="UNAVAILABLE"
