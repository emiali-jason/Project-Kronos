"""Prospective contract/composition qualification, not Native policy commissioning."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path

import pytest

from kronos.intraday.wo10_futures_contract import PROGRAMME, digest, normalize
from kronos.intraday.native_structural_selection import (
    NativeStructuralSelection, NativeStructuralStore, NativeStructuralLoader, create_native_selection,
    APPROVED_NATIVE_SELECTION_POLICIES, UNAVAILABLE)
from kronos.intraday.wo10_native_adapter import adapt_native
from kronos.intraday.wo10_construction import construct_plan
from kronos.intraday.wo09_readiness import CurrentnessState
from kronos.browser.intraday_futures_control import IntradayFuturesControl, render_futures
from tests.unit.intraday.test_wo10_futures import fixture, NOW, session

POLICY = ("ISOLATED_TEST_NATIVE_SELECTION", "1.0.0", "a" * 64)


def native(tmp_path, direction="LONG", family="PULLBACK", *, targets=False):
    app, kw = fixture(tmp_path, direction)
    h = kw["adapter"].wo09
    source = dict(identity="EXACT-SOURCE", subject=h.canonical_subject_identity, direction=direction,
        analysis_cycle="EXACT-NATIVE-CYCLE", analysis_boundary=normalize(h.analysis_boundary),
        session=h.session_identity, trading_date="2026-09-11", exact_contract=None, roll_lineage=None,
        machine_identity="machine", machine_integrity=h.machine_evidence_integrity, candles={})
    def ref(name, high, low, side, structure="machine"):
        c = dict(subject=h.canonical_subject_identity, session=h.session_identity, trading_date="2026-09-11",
            start=normalize(h.analysis_boundary-timedelta(minutes=15)), end=normalize(h.analysis_boundary),
            completion="COMPLETE", available_at=normalize(h.analysis_boundary), timeframe="15M", HIGH=str(high), LOW=str(low))
        source["candles"][name] = c
        return dict(source_identity=source["identity"], candle_identity=name, candle_integrity=digest(c),
            field=side, price=c[side], structure_identity=structure, timeframe="15M")
    roles = dict(QUALIFICATION_CANDLE_HIGH=ref("QUALIFICATION", 100 if direction == "LONG" else 102, 98 if direction == "LONG" else 100, "HIGH"),
                 QUALIFICATION_CANDLE_LOW=ref("QUALIFICATION", 100 if direction == "LONG" else 102, 98 if direction == "LONG" else 100, "LOW"))
    if family == "PULLBACK":
        if direction == "LONG":
            roles.update(PULLBACK_STRUCTURAL_LOW=ref("PULLBACK",98,96,"LOW"), PRIOR_IMPULSE_HIGH=ref("IMPULSE",112,105,"HIGH"))
        else:
            roles.update(PULLBACK_STRUCTURAL_HIGH=ref("PULLBACK",104,102,"HIGH"), PRIOR_IMPULSE_LOW=ref("IMPULSE",95,88,"LOW"))
    else:
        roles.update(RANGE_HIGH=ref("RANGE",100,90,"HIGH", "RANGE-1"), RANGE_LOW=ref("RANGE",100,90,"LOW", "RANGE-1"))
        if direction == "SHORT":
            roles["QUALIFICATION_CANDLE_HIGH"] = ref("QUALIFICATION",92,90,"HIGH")
            roles["QUALIFICATION_CANDLE_LOW"] = ref("QUALIFICATION",92,90,"LOW")
    constraints = [dict(role="SESSION_STRUCTURAL_HIGH" if direction == "LONG" else "SESSION_STRUCTURAL_LOW",
        reference=ref("CONSTRAINT", 107,93,"HIGH" if direction == "LONG" else "LOW"))] if targets else []
    values = dict(programme_identity=PROGRAMME, contract_version="1.0.0", policy_identity=POLICY[0], policy_version=POLICY[1], policy_checksum=POLICY[2],
        subject=h.canonical_subject_identity, direction=direction, setup_family=family, setup_identity="machine", analysis_cycle=source["analysis_cycle"],
        analysis_boundary=source["analysis_boundary"], session=h.session_identity, trading_date="2026-09-11", machine_identity="machine",
        machine_integrity=h.machine_evidence_integrity, instrument_identity=h.canonical_subject_identity, exact_contract=None, roll_lineage=None,
        created_at=normalize(NOW), sources={source["identity"]:digest(source)}, roles=roles,
        original_range_identity="RANGE-1" if family == "BREAKOUT" else None, target_population_identity="EXACT-TARGET-POPULATION",
        target_completeness="COMPLETE_WITH_TARGETS" if targets else "COMPLETE_NO_APPLICABLE_FORWARD_TARGETS", targets=constraints)
    store = NativeStructuralStore(tmp_path / "native")
    loader = NativeStructuralLoader(store, lambda identity: source if identity == source["identity"] else None, approved_policies={POLICY})
    app.structural_loader = loader
    return app, kw, values, source


def retain(app, values):
    selected = create_native_selection(**values)
    app.structural_loader.store.retain(selected, approved_policies={POLICY}, cycle_identity=values["analysis_cycle"])
    return selected


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("family", ["PULLBACK", "BREAKOUT"])
@pytest.mark.parametrize("targets", [False, True])
def test_exact_retained_selection_to_existing_geometry(tmp_path, direction, family, targets):
    app, kw, values, source = native(tmp_path, direction, family, targets=targets)
    selected = retain(app, values); h = kw["adapter"].wo09
    assert app.structural_loader.load(h, now=NOW) == selected
    a,e,p = adapt_native(selected,h,*app._intake(h,NOW),now=NOW)
    plan=construct_plan(a,e,p,now=NOW)
    assert plan.data["state"] == "AVAILABLE"
    assert selected.data["roles"]["QUALIFICATION_CANDLE_HIGH"] and selected.data["roles"]["QUALIFICATION_CANDLE_LOW"]


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_identity_only_controller_full_journey(tmp_path, direction):
    app, kw, values, source = native(tmp_path,direction)
    selected=retain(app,values)
    inputs={k:v for k,v in kw.items() if k not in {"request_identity","adapter","geometry_evidence","target_population"}}
    inputs["authority_source"]=lambda:{k:inputs.get(k) for k in ("master","underlying","active_mcx","economics","configuration")}
    app.acquisition_source=lambda handoff,plan: inputs
    control=IntradayFuturesControl(app,lambda subject,now:session(now))
    h=kw["adapter"].wo09
    result=control.construct_document(dict(handoff_identity=h.handoff_identity,request_identity="EXPLICIT"))
    assert result["outcome"] == "RETAINED" and result["state"] == "EXECUTABLE"
    comparison=app.store.load(result["result_identity"])
    assert len(kw["provider"].calls)==1
    decision=control.execute_document(dict(comparison_identity=comparison.identity,choice="SELECTED_FUTURE",lots=1,action_identity="SELECT"))
    assert decision["outcome"] == "RETAINED"
    assert len(app.store.records("WO10_SELECTED_TRADE_HANDOFF_V1"))==1
    assert control.status_document()["cards"][0]["selection_state"]=="FUTURE_SELECTED"
    assert app.store.records("WO10_CONSTRUCTION_OPERATION_V1")[0].data["native_selection_identity"]==selected.identity
    assert control.construct_document(dict(handoff_identity=h.handoff_identity,request_identity="EXPLICIT"))==result
    assert len(kw["provider"].calls)==1


def test_uncommissioned_policy_never_becomes_production_authority(tmp_path):
    app,kw,values,source=native(tmp_path);retain(app,values)
    app.structural_loader=NativeStructuralLoader(app.structural_loader.store,lambda _:source)
    assert POLICY not in APPROVED_NATIVE_SELECTION_POLICIES
    result=app.construct_current(handoff_identity=kw["adapter"].wo09.handoff_identity,request_identity="MISSING")
    assert result.data["state"]=="TRADE_PLAN_UNAVAILABLE" and result.data["reason"]==UNAVAILABLE
    assert not kw["provider"].calls
    assert app.wo09.restore_current()[0][1].satisfied_count==5
    assert not app.store.records("WO10_FUTURES_MARKET_SNAPSHOT_V1")


@pytest.mark.parametrize("field", ["setup_family","setup_identity","analysis_cycle","session","subject","direction","target_population_identity"])
def test_required_authority_not_invented(tmp_path,field):
    app,kw,values,_=native(tmp_path);values[field]=""
    with pytest.raises(ValueError): create_native_selection(**values)


@pytest.mark.parametrize("direction", ["LONG","SHORT"])
@pytest.mark.parametrize("family", ["PULLBACK","BREAKOUT"])
def test_every_required_role_is_mandatory(tmp_path,direction,family):
    _,_,values,_=native(tmp_path,direction,family)
    for role in values["roles"]:
        v=deepcopy(values);del v["roles"][role]
        with pytest.raises(ValueError,match="REQUIRED_ROLE"):create_native_selection(**v)


@pytest.mark.parametrize("change", ["missing_range","setup","qualification","field","direction","completeness","empty_complete","false_empty"])
def test_structural_contract_conflicts(tmp_path,change):
    _,_,v,_=native(tmp_path,family="BREAKOUT")
    if change=="missing_range":v["original_range_identity"]=None
    if change=="setup":v["roles"]["RANGE_HIGH"]["structure_identity"]="OTHER"
    if change=="qualification":v["roles"]["QUALIFICATION_CANDLE_LOW"]["candle_identity"]="OTHER"
    if change=="field":v["roles"]["QUALIFICATION_CANDLE_HIGH"]["field"]="LOW"
    if change=="direction":v["direction"]="MIXED"
    if change=="completeness":v["target_completeness"]=""
    if change=="empty_complete":v["target_completeness"]="COMPLETE_WITH_TARGETS"
    if change=="false_empty":v["targets"]=[dict(role="SESSION_STRUCTURAL_HIGH",reference=v["roles"]["RANGE_HIGH"])]
    with pytest.raises(ValueError):create_native_selection(**v)


@pytest.mark.parametrize("field", ["subject","direction","analysis_cycle","analysis_boundary","session","trading_date","exact_contract","roll_lineage"])
def test_source_context_mismatch(tmp_path,field):
    app,kw,v,src=native(tmp_path);src[field]="FOREIGN";v["sources"][src["identity"]]=digest(src);retain(app,v)
    with pytest.raises(ValueError,match="SOURCE_.*_MISMATCH"):app.structural_loader.load(kw["adapter"].wo09,now=NOW)


@pytest.mark.parametrize("change", ["future","forming","wrong_session","wrong_subject","wrong_date","wrong_timeframe","wrong_price","corrupt","missing"])
def test_exact_candle_validation(tmp_path,change):
    app,kw,v,src=native(tmp_path);c=src["candles"]["QUALIFICATION"]
    if change=="corrupt":c["HIGH"]="998"
    if change=="future":c["end"]=normalize(NOW+timedelta(minutes=1))
    if change=="forming":c["completion"]="FORMING"
    if change=="wrong_session":c["session"]="OTHER"
    if change=="wrong_subject":c["subject"]="NSE-EQ-OTHER"
    if change=="wrong_date":c["trading_date"]="2026-09-10"
    if change=="wrong_timeframe":c["timeframe"]="5M"
    if change=="wrong_price":c["HIGH"]="999"
    if change!="corrupt":
        for key in ("QUALIFICATION_CANDLE_HIGH","QUALIFICATION_CANDLE_LOW"):v["roles"][key]["candle_integrity"]=digest(c)
    if change=="missing":del src["candles"]["QUALIFICATION"]
    v["sources"][src["identity"]]=digest(src);retain(app,v)
    with pytest.raises((ValueError,KeyError)):app.structural_loader.load(kw["adapter"].wo09,now=NOW)


def test_incomplete_target_population_retained_unavailable(tmp_path):
    app,kw,v,_=native(tmp_path);v["target_completeness"]="INCOMPLETE";retain(app,v)
    result=app.construct_current(handoff_identity=kw["adapter"].wo09.handoff_identity,request_identity="INCOMPLETE")
    assert result.data["reason"]=="TARGET_POPULATION_INCOMPLETE"
    assert app.wo09.restore_current()[0][1].satisfied_count==5


def test_binding_collision_cannot_choose_latest(tmp_path):
    app,kw,v,_=native(tmp_path);retain(app,v);v["target_population_identity"]="OTHER"
    with pytest.raises(RuntimeError):retain(app,v)


def test_corrupt_retained_bytes_rejected(tmp_path):
    app,kw,v,_=native(tmp_path);s=retain(app,v)
    path=app.structural_loader.store.root/"records"/(s.identity+".json")
    doc=json.loads(path.read_text());doc["integrity"]="bad";path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):app.structural_loader.load(kw["adapter"].wo09,now=NOW)


def test_no_approved_producer_and_no_historical_backfill(tmp_path):
    app,kw,v,_=native(tmp_path);selection=create_native_selection(**v)
    with pytest.raises(ValueError,match=UNAVAILABLE):
        app.structural_loader.store.retain(selection,approved_policies=APPROVED_NATIVE_SELECTION_POLICIES,cycle_identity=v["analysis_cycle"])
    with pytest.raises(ValueError,match=UNAVAILABLE):
        app.structural_loader.store.retain(selection,approved_policies={POLICY},cycle_identity="ANOTHER-CYCLE")
    assert not app.structural_loader.store.root.exists()


@pytest.mark.parametrize("when", ["before","after"])
def test_readiness_supersession_at_structural_load(tmp_path,when):
    app,kw,v,_=native(tmp_path);retain(app,v);h=kw["adapter"].wo09
    def supersede():app.wo09.mark_currentness(h.canonical_subject_identity,CurrentnessState.REASSESSMENT_DUE,updated_at=NOW+timedelta(seconds=1))
    if when=="before":supersede()
    else:
        load=app.structural_loader.load
        def changed(*args,**kwargs):
            item=load(*args,**kwargs);supersede();return item
        app.structural_loader.load=changed
    with pytest.raises(ValueError):app.construct_current(handoff_identity=h.handoff_identity,request_identity="RACE")
    assert not app.store.records("WO10_CANONICAL_TRADE_PLAN_V1") and not kw["provider"].calls


def test_page_get_inert_unavailable_and_explicit_retention(tmp_path):
    from tests.unit.browser.test_product_route_isolation import _snapshot
    app,kw,v,_=native(tmp_path);app.structural_loader=NativeStructuralLoader(app.structural_loader.store)
    control=IntradayFuturesControl(app,lambda subject,now:session(now))
    before=sorted(str(p) for p in tmp_path.rglob("*"))
    status=control.status_document();html=render_futures(_snapshot(),status)
    assert "TRADE PLAN UNAVAILABLE" in html and UNAVAILABLE in html
    assert len(status["cards"])==1
    assert sorted(str(p) for p in tmp_path.rglob("*"))==before
    request=dict(handoff_identity=kw["adapter"].wo09.handoff_identity,request_identity="RETAIN-FAILURE")
    assert control.construct_document(request)["outcome"]=="RETAINED"
    assert len(app.store.records("WO10_CONSTRUCTION_UNAVAILABLE_V1"))==1
    assert control.construct_document(request)["outcome"]=="RETAINED"
    assert len(app.store.records("WO10_CONSTRUCTION_UNAVAILABLE_V1"))==1
    assert not kw["provider"].calls


@pytest.mark.parametrize("field", ["roles","setup_family","geometry","master","configuration","lots"])
def test_browser_cannot_supply_authority(tmp_path,field):
    app,kw,_,_=native(tmp_path);control=IntradayFuturesControl(app,lambda *_:session())
    payload=dict(handoff_identity=kw["adapter"].wo09.handoff_identity,request_identity="BAD",**{field:"INVENTED"})
    assert control.construct_document(payload)["outcome"]=="REJECTED"
    assert not app.store.root.exists()


def test_selection_cannot_be_backfilled_after_handoff(tmp_path):
    app,kw,v,_=native(tmp_path);v["created_at"]=normalize(NOW+timedelta(seconds=1));retain(app,v)
    with pytest.raises(ValueError,match="SOURCE_BINDING_INVALID"):
        app.structural_loader.load(kw["adapter"].wo09,now=NOW+timedelta(seconds=2))


def test_late_candle_availability_is_not_repaired(tmp_path):
    app,kw,v,src=native(tmp_path)
    c=src["candles"]["QUALIFICATION"];c["available_at"]=normalize(NOW+timedelta(minutes=1))
    for key in ("QUALIFICATION_CANDLE_HIGH","QUALIFICATION_CANDLE_LOW"):v["roles"][key]["candle_integrity"]=digest(c)
    v["sources"][src["identity"]]=digest(src);retain(app,v)
    with pytest.raises(ValueError,match="CANDLE_NOT_COMPLETED"):
        app.structural_loader.load(kw["adapter"].wo09,now=NOW)
