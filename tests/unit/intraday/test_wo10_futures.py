"""Isolated successor programme qualification. No production roots or calls."""
from dataclasses import asdict, replace
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal as D
from zoneinfo import ZoneInfo
import json

import pytest

from kronos.intraday.wo10_futures_contract import record, Record, require
from kronos.intraday.wo10_construction import adapt_wo09, validate_intake, construct_plan
from kronos.intraday.wo10_futures_market import select_future, build_snapshot, map_future
from kronos.intraday.wo10_futures_risk import risk_configuration, assess_risk
from kronos.intraday.wo10_futures_store import FuturesStore
from kronos.application.intraday_futures import IntradayFuturesApplication
from kronos.intraday.wo09_persistence import Wo09Store
from kronos.application.intraday_wo09 import IntradayWo09Application
from kronos.intraday.wo09_readiness import evaluate_readiness, CurrentnessState
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo13_pullback import construct_wo13_pullback_geometry
from kronos.intraday.wo13_targets import create_wo13_target_constraint_population
from kronos.provider.instrument_master import create_provider_instrument_snapshot, ProviderAcquisitionOutcome
from kronos.provider.contracts.instrument_master import ProviderInstrumentMasterSourceRecord
from kronos.provider.adapters.kite.full_quote import normalize_full_quotes
from kronos.instrument.runtime import create_canonical_instrument, create_provider_assertion, create_provider_binding_directive, publish_runtime_instruments
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus, MarketSessionService, InMemoryMarketScheduleSource
from tests.unit.intraday.test_wo09_readiness import source, evidence
from tests.unit.intraday.test_wo13_pullback import _evidence, _fact

NOW = datetime(2026, 9, 11, 5, 0, tzinfo=timezone.utc)
IST = ZoneInfo("Asia/Kolkata")


def session(now=NOW, exchange="NSE"):
    local = now.astimezone(IST)
    schedule = MarketDaySchedule(exchange, local.date(), "NSE-2026-09-11", "Asia/Kolkata", TradingDayStatus.TRADING,
                                  (MarketWindow(local.replace(hour=9, minute=15), local.replace(hour=15, minute=30)),), "DOMAIN008_TEST", "1")
    return MarketSessionService(InMemoryMarketScheduleSource((schedule,))).facts(exchange=exchange, trading_date=local.date(), observed_at=now)


def intake(tmp_path, direction="LONG", subject="NSE-EQ-LUPIN", **changes):
    r, req = evaluate_readiness(source(subject=subject, direction=direction),
                                evidence(subject=subject, direction=direction, **changes), created_at=NOW)
    store = Wo09Store(tmp_path / "wo09")
    store.retain(r, req)
    h = IntradayWo09Application(store).create_handoff(r, created_at=NOW, first_five_of_five_at=NOW)
    return store, r, h


def master(subject="NSE-EQ-LUPIN", *, expiries=None):
    sym = subject.removeprefix("NSE-EQ-").removeprefix("NSE-INDEX-")
    visible = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK"}.get(sym, sym)
    rows = [ProviderInstrumentMasterSourceRecord("KITE", 1, None, visible, visible, None, None, None, D("0.05"), 1, "EQ", "NSE", "NSE")]
    for i, expiry in enumerate(expiries or (date(2026, 9, 29), date(2026, 10, 27))):
        rows.append(ProviderInstrumentMasterSourceRecord("KITE", 2+i, None, sym+str(i)+"FUT", sym, None, expiry, None, D("0.05"), 100, "FUT", "NFO-FUT", "NFO"))
    m = create_provider_instrument_snapshot(records=tuple(rows), provider="KITE", dataset_identity="TEST-MASTER", operation_identity="TEST-MASTER-OP",
                                           source_boundary=NOW, request_started_at=NOW, response_received_at=NOW, acquired_at=NOW, acquisition_effective_at=NOW,
                                           authenticated_context_identity="test-context", authorized_operation_identity="test-master", component_identities=("ALL",),
                                           acquisition_outcome=ProviderAcquisitionOutcome.COMPLETE, provenance=("TEST",))
    canonical = create_canonical_instrument(canonical_instrument_id=subject, exchange="NSE", segment="NSE", instrument_type="EQ",
                                             canonical_tick_size=D("0.05"), canonical_lot_size=1, canonical_source_identity="TEST-CATALOGUE", source_boundary=NOW, valid_through=NOW+timedelta(hours=8))
    assertion = create_provider_assertion(provider="KITE", provider_symbol=visible, provider_instrument_token=1, exchange="NSE", segment="NSE", instrument_type="EQ",
                                          asserted_tick_size=D("0.05"), asserted_lot_size=1, binding_source_identity="TEST-BINDING", source_boundary=NOW, valid_through=NOW+timedelta(hours=8))
    directive = create_provider_binding_directive(canonical_instrument_id=subject, provider="KITE", provider_symbol=visible, directive_source_identity="TEST-DIRECTIVE")
    u = publish_runtime_instruments(canonical_instruments=(canonical,), provider_assertions=(assertion,), binding_directives=(directive,), observed_at=NOW).lookup(subject)
    return m, u


def raw_quotes(instruments, *, oi=1000, bid=102, ask=102.1, skew=0, now=NOW):
    raw = {}
    for i, item in enumerate(instruments):
        raw[f"{item.exchange}:{item.trading_symbol}"] = dict(instrument_token=item.provider_instrument_token,
            timestamp=now-timedelta(seconds=skew*i), last_trade_time=now, last_price=100 if i == 0 else 102,
            volume=10000, buy_quantity=300, sell_quantity=400, oi=oi,
            ohlc=dict(open=99, high=105, low=98, close=100),
            depth=dict(buy=[] if bid is None else [dict(price=bid, quantity=100, orders=1)],
                       sell=[] if ask is None else [dict(price=ask, quantity=100, orders=1)]))
    return raw


class Provider:
    def __init__(self, **changes):
        self.calls = []; self.changes = changes
    def full_quotes(self, instruments, *, request_identity, timeout):
        self.calls.append((instruments, request_identity, timeout))
        return normalize_full_quotes(raw_quotes(instruments, **self.changes), instruments)


def config(**changes):
    values = dict(currency="INR", risk_reference_amount="2000",
                  source_identity="SPONSOR-TEST-CONFIG", effective_at=NOW, expires_at=NOW+timedelta(hours=1))
    values.update(changes)
    return risk_configuration(**values)


def fixture(tmp_path, direction="LONG", subject="NSE-EQ-LUPIN"):
    store, readiness, h = intake(tmp_path, direction, subject)
    a = adapt_wo09(h, readiness, store.load_pointer(subject), now=NOW, session_identity=h.session_identity,
                   setup_family=Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION, setup_evidence_identity="machine", instrument_identity=subject)
    # Exact existing geometry evidence helpers; no fake historical handoff.
    roles = __import__("kronos.intraday.wo13_geometry", fromlist=["Wo13StructuralRole"]).Wo13StructuralRole
    long = direction == "LONG"
    facts = [_fact(a, price, role, session=h.session_identity) for price, role in (
        ("100", roles.QUALIFICATION_CANDLE_HIGH if long else roles.QUALIFICATION_CANDLE_LOW),
        ("96" if long else "104", roles.PULLBACK_STRUCTURAL_LOW if long else roles.PULLBACK_STRUCTURAL_HIGH),
        ("112" if long else "88", roles.PRIOR_IMPULSE_HIGH if long else roles.PRIOR_IMPULSE_LOW))]
    e = _evidence(a, qualification=(facts[0],), pullback=(facts[1],), impulse=(facts[2],), session=h.session_identity)
    g = construct_wo13_pullback_geometry(e)
    population = create_wo13_target_constraint_population(setup_geometry=g)
    m, u = master(subject)
    app = IntradayFuturesApplication(FuturesStore(tmp_path/"futures"), store, clock=lambda: NOW, operational_guard=lambda: True)
    kwargs = dict(request_identity="test-operation", adapter=a, geometry_evidence=e, target_population=population,
                  master=m, provider=Provider(), session_source=session, underlying=u, configuration=config())
    return app, kwargs


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("subject", ["NSE-EQ-LUPIN", "NSE-EQ-M&M", "NSE-INDEX-NIFTY", "NSE-INDEX-BANKNIFTY"])
def test_complete_future_journey(tmp_path, direction, subject):
    app, kwargs = fixture(tmp_path, direction, subject)
    comparison = app.evaluate(**kwargs)
    assert comparison.data["executability"] == "EXECUTABLE"
    expression = app.store.load(comparison.data["expression_identity"]).data
    assert D(expression["entry"]) == D("102")
    assert expression["model_rr"] == "3"
    advisory = app.store.load(comparison.data["advisory_identity"]).data
    assert advisory["risk_reference_lots"] == 5 and advisory["risk_warning_state"] == "QUANTITY_NOT_SELECTED"
    selected = app.select(comparison.identity, choice="SELECTED_FUTURE", lots=1, session=session(), action_identity="sponsor-1")
    assert selected.data["sponsor_selected_lots"] == 1
    assert len(app.store.records("WO10_SELECTED_TRADE_HANDOFF_V1")) == 1
    assert len(kwargs["provider"].calls) == 1


@pytest.mark.parametrize("lots", [1, 2, 4, 5, 6, 100])
def test_sponsor_selects_below_at_or_above_reference(tmp_path, lots):
    app, kw = fixture(tmp_path); c = app.evaluate(**kw)
    assert app.select(c.identity, choice="SELECTED_FUTURE", lots=lots, session=session(), action_identity="s").data["sponsor_selected_lots"] == lots


@pytest.mark.parametrize("lots", [0, -1, True, 1.5, "1", None])
def test_invalid_quantity_rejected(tmp_path, lots):
    app, kw = fixture(tmp_path); c = app.evaluate(**kw)
    with pytest.raises(ValueError, match="NOT_PERMITTED"):
        app.select(c.identity, choice="SELECTED_FUTURE", lots=lots, session=session(), action_identity="s")


@pytest.mark.parametrize("amount,lots,reference_lots,state", [
    ("2000",1,5,"WITHIN_REFERENCE"), ("2000",5,5,"WITHIN_REFERENCE"),
    ("2000",6,5,"ABOVE_REFERENCE"), ("399",1,0,"ABOVE_REFERENCE"),
    ("1000",2,2,"WITHIN_REFERENCE"), ("1000",3,2,"ABOVE_REFERENCE"),
])
def test_risk_reference_is_advisory(tmp_path, amount, lots, reference_lots, state):
    app, kw = fixture(tmp_path); kw["configuration"] = config(risk_reference_amount=amount); c = app.evaluate(**kw)
    selected = app.select(c.identity,choice="SELECTED_FUTURE",lots=lots,session=session(),action_identity="s")
    advisory = selected.data["advisory_risk"]
    assert advisory["risk_reference_lots"] == reference_lots
    assert advisory["risk_warning_state"] == state
    assert D(advisory["selected_monetary_risk"]) == D(400)*lots
    assert "maximum_permitted_lots" not in selected.payload_json


@pytest.mark.parametrize("field", ["margin_per_lot", "available_margin", "buying_power", "broker_funds", "SPAN"])
def test_broker_fields_not_accepted(field):
    with pytest.raises(ValueError, match="FIELDS_INVALID"):
        config(**{field:1000})


@pytest.mark.parametrize("value", [-1, "NaN", "Infinity", True])
def test_invalid_risk_config(value):
    with pytest.raises(ValueError):
        config(risk_reference_amount=value)


def test_missing_risk_configuration(tmp_path):
    app, kw = fixture(tmp_path); kw["configuration"] = None; c = app.evaluate(**kw)
    assert app.store.load(c.data["advisory_identity"]).data["risk_warning_state"] == "REFERENCE_NOT_CONFIGURED"
    assert c.data["executability"] == "EXECUTABLE"
    assert app.select(c.identity,choice="SELECTED_FUTURE",lots=100,session=session(),action_identity="missing-reference").data["sponsor_selected_lots"] == 100


@pytest.mark.parametrize("quote_changes,state", [
    ({"bid":None}, "MARKET_NOT_EXECUTABLE"), ({"ask":None}, "MARKET_NOT_EXECUTABLE"),
    ({"bid":103}, "MARKET_NOT_EXECUTABLE"), ({"bid":102.1}, "EXECUTABLE"),
    ({"bid":0}, "MARKET_NOT_EXECUTABLE"), ({"oi":None}, "EXECUTABLE"),
    ({"skew":5}, "EXECUTABLE"), ({"skew":6}, "MARKET_NOT_EXECUTABLE"),
    ({"skew":31}, "STALE"),
])
def test_market_factual_boundaries(tmp_path, quote_changes, state):
    app, kw = fixture(tmp_path); kw["provider"] = Provider(**quote_changes); c = app.evaluate(**kw)
    assert c.data["executability"] == state


def test_none_has_no_downstream_handoff(tmp_path):
    app, kw = fixture(tmp_path); c = app.evaluate(**kw)
    s = app.select(c.identity, choice="NONE", lots=None, session=session(), action_identity="none")
    assert s.data["choice"] == "NONE"
    assert app.store.records("WO10_SELECTED_TRADE_HANDOFF_V1") == ()


def test_restart_preserves_records_not_executability(tmp_path):
    app, kw = fixture(tmp_path); c = app.evaluate(**kw)
    restored = IntradayFuturesApplication(app.store, app.wo09, clock=lambda:NOW, operational_guard=lambda:True)
    assert restored.restore() == (c,)
    assert restored.decision_state(c, now=NOW, session=session()) == "HISTORICAL_REACQUISITION_REQUIRED"
    with pytest.raises(ValueError, match="NOT_PERMITTED"):
        restored.select(c.identity, choice="SELECTED_FUTURE", lots=1, session=session(), action_identity="s")


def test_idempotence_and_conflict(tmp_path):
    app, kw = fixture(tmp_path); c = app.evaluate(**kw)
    assert app.evaluate(**kw) == c and len(kw["provider"].calls) == 1
    kw["configuration"] = config(risk_reference_amount="400")
    with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
        app.evaluate(**kw)


def test_supersession(tmp_path):
    app, kw = fixture(tmp_path); c = app.evaluate(**kw)
    app.wo09.mark_currentness("NSE-EQ-LUPIN", CurrentnessState.REASSESSMENT_DUE, updated_at=NOW+timedelta(seconds=1))
    assert app.decision_state(c, now=NOW, session=session()) == "SUPERSEDED"


@pytest.mark.parametrize("delay", [31, 301])
def test_stale_selection(tmp_path, delay):
    app, kw = fixture(tmp_path); c = app.evaluate(**kw)
    now = NOW+timedelta(seconds=delay)
    app.clock = lambda:now
    with pytest.raises(ValueError, match="NOT_PERMITTED"):
        app.select(c.identity, choice="SELECTED_FUTURE", lots=1, session=session(now), action_identity="s")


@pytest.mark.parametrize("expiries,expected", [
    ((date(2026,9,11), date(2026,10,27)), "2026-10-27"),
    ((date(2026,9,29), date(2026,10,27)), "2026-09-29"),
])
def test_expiry_day_roll(tmp_path, expiries, expected):
    _, _, h = intake(tmp_path); m,u = master(expiries=expiries)
    c,_ = select_future(m,h,session(),now=NOW,underlying=u)
    assert c.data["future"]["expiry"] == expected


def test_duplicate_minimum_contract(tmp_path):
    _,_,h = intake(tmp_path); m,u = master(expiries=(date(2026,9,29), date(2026,9,29)))
    with pytest.raises(ValueError, match="CONFLICT"):
        select_future(m,h,session(),now=NOW,underlying=u)


def test_oi_baseline_and_delta(tmp_path):
    app,kw = fixture(tmp_path); first = app.evaluate(**kw)
    assert app.store.load(first.data["snapshot_identity"]).data["delta_oi"] is None
    later = NOW+timedelta(seconds=2); app.clock=lambda:later
    kw.update(request_identity="second", provider=Provider(oi=1050,now=later))
    second = app.evaluate(**kw)
    assert app.store.load(second.data["snapshot_identity"]).data["delta_oi"] == 50
    assert len(app.store.records("WO10_OPPORTUNITY_V1")) == 1
    assert len(app.store.records("SESSION_FIRST_OBSERVED_OI_BASELINE_V1")) == 1


def test_record_tamper_detected(tmp_path):
    store = FuturesStore(tmp_path)
    item = record("WO10_OPPORTUNITY_V1", subject="LUPIN")
    store.retain(item); assert store.load(item.identity) == item
    path = tmp_path/"records"/(item.identity+".json")
    data=json.loads(path.read_text()); data["payload_json"] = '{"subject":"OTHER"}'; path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="INTEGRITY"):
        store.load(item.identity)


def test_composition_is_inert(tmp_path):
    app = IntradayFuturesApplication(FuturesStore(tmp_path/"new"), Wo09Store(tmp_path/"wo09"))
    assert app.restore() == () and not (tmp_path/"new").exists()


@pytest.mark.parametrize("family", ["CRUDE", "COPPER", "GOLDM", "SILVERM"])
@pytest.mark.parametrize("monetary",["available","missing","stale","inconsistent"])
def test_mcx_exact_native_contract_authority(tmp_path, family, monetary):
    from tests.unit.instrument.test_active_derivative_selection import _snapshot, CATALOGUE
    from kronos.instrument.active_derivative import GovernedActiveDerivativeResolver
    from kronos.market.calendar import MarketCalendarPublisher
    from kronos.intraday.wo14 import create_wo14_instrument_economics
    from kronos.browser.intraday_futures_control import domain008_session
    master_snapshot = _snapshot(NOW)
    resolved = GovernedActiveDerivativeResolver(catalogue=CATALOGUE, provider_snapshot=master_snapshot,
                                                calendar_publisher=MarketCalendarPublisher()).resolve_all(NOW)
    active = resolved.for_subject(family).binding
    assert active is not None
    contract_id = active.active_binding.derivative_contract_id
    subject = active.canonical_subject_id
    future_row = next(x for x in master_snapshot.records if x.provider_record_identity == active.provider_record_identity)
    native_session = domain008_session(MarketCalendarPublisher(), subject, NOW,
                                       contract={"name":future_row.name,"expiry":future_row.expiry.isoformat()})
    store,r,h = intake(tmp_path, subject=subject, market_family="MCX", exact_mcx_contract_identity=contract_id,
                       exact_mcx_roll_lineage=active.binding_identity, session_identity=native_session.schedule.session_id)
    econ = create_wo14_instrument_economics(economics_version="1.0.0", canonical_subject_identity=subject,
        instrument_identity=contract_id, actual_contract_identity=contract_id, roll_lineage_identity=active.binding_identity,
        lot_size=active.lot_size, contract_multiplier=D(1), tick_size=active.tick_size, tick_value=None,
        observed_at=NOW, source_identities=(active.binding_identity,), source_integrities=(active.integrity_identity,))
    valid_econ = econ
    if monetary == "missing":econ=None
    elif monetary != "available":
        args={k:v for k,v in asdict(econ).items() if k not in {"economics_identity","economics_integrity","unit_semantics"}}
        if monetary=="stale":args['observed_at']=NOW-timedelta(days=1)
        else:args['tick_value']=D('999999')
        econ=create_wo14_instrument_economics(**args)
    c, rows = select_future(master_snapshot,h,native_session,now=NOW,active_mcx=active,economics=econ)
    assert len(rows) == 1 and rows[0] == future_row and c.data["underlying"] is None
    snap, baseline = build_snapshot(c, normalize_full_quotes(raw_quotes(rows),rows),operation_identity="test-op",
                                   request_identity="test-q", received_at=NOW,session=native_session)
    assert snap.data["basis"] is None and snap.data["basis_state"] == "NOT_APPLICABLE"
    assert baseline is not None
    adapter=adapt_wo09(h,r,store.load_pointer(subject),now=NOW,session_identity=h.session_identity,
                       setup_family=Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION,setup_evidence_identity="machine",instrument_identity=contract_id)
    from kronos.intraday.wo13_geometry import Wo13StructuralRole as Role
    facts=[_fact(adapter,price,role,session=h.session_identity) for price,role in (
        ("100",Role.QUALIFICATION_CANDLE_HIGH),("96",Role.PULLBACK_STRUCTURAL_LOW),("112",Role.PRIOR_IMPULSE_HIGH))]
    ev=_evidence(adapter,qualification=(facts[0],),pullback=(facts[1],),impulse=(facts[2],),session=h.session_identity)
    population=create_wo13_target_constraint_population(setup_geometry=construct_wo13_pullback_geometry(ev))
    app=IntradayFuturesApplication(FuturesStore(tmp_path/"mcx-futures"),store,clock=lambda:NOW,operational_guard=lambda:True)
    comparison=app.evaluate(request_identity="mcx-test",adapter=adapter,geometry_evidence=ev,target_population=population,
        master=master_snapshot,provider=Provider(),session_source=lambda now:domain008_session(MarketCalendarPublisher(),subject,now,contract=c.data["future"]),
        active_mcx=active,economics=econ,configuration=config(risk_reference_amount="1000000"))
    assert comparison.data["executability"]=="EXECUTABLE"
    fact=app.store.load(comparison.data['risk_fact_identity']).data
    assert fact['state']==('AVAILABLE' if monetary=='available' else 'RISK_FACT_UNAVAILABLE')
    if monetary=='available':assert D(fact['risk_per_lot'])==D(4)*active.lot_size
    else:assert fact['risk_per_lot'] is None
    assert app.select(comparison.identity,choice="SELECTED_FUTURE",lots=1,session=native_session,action_identity="mcx-sponsor").data["sponsor_selected_lots"]==1
    with pytest.raises(ValueError,match="LINEAGE|ECONOMICS_INVALID"):
        from kronos.intraday.wo10_futures_market import select_future as select
        wrong = replace(valid_econ, actual_contract_identity="other")
        select(master_snapshot,h,native_session,now=NOW,active_mcx=active,economics=wrong)


def test_natgas_commissioning_remains_held(tmp_path):
    with pytest.raises(ValueError):
        store,r,h = intake(tmp_path, subject="MCX-SUBJECT-NATGAS", market_family="MCX", exact_mcx_contract_identity="natgas", exact_mcx_roll_lineage="roll",natgas_commissioning_state="HELD")
        validate_intake(h,r,store.load_pointer(r.canonical_subject_identity),now=NOW,session_identity=r.session_identity)


@pytest.mark.parametrize("field,value", [("direction","SHORT"),("canonical_subject_identity","NSE-EQ-OTHER"),
    ("current_pointer_integrity","wrong"),("readiness_identity","wrong"),("integrity_identity","wrong"),
    ("satisfied_count",4),("satisfied_count",3),("session_identity","foreign")])
def test_corrupt_handoff_rejected_including_count(tmp_path,field,value):
    store,r,h=intake(tmp_path)
    object.__setattr__(h,field,value)
    with pytest.raises(ValueError):
        validate_intake(h,r,store.load_pointer(r.canonical_subject_identity),now=NOW,session_identity=r.session_identity)


@pytest.mark.parametrize("changes", [{"space":"OBSTACLE_CLOSE"},{"space":"OBSTACLE_CLOSE","follow":"WEAK_OR_STALLING"},
                                     {"fifteen":"SHORT"},{"one_hour":"SHORT"}])
def test_actual_non_now_readiness_cannot_create_handoff(tmp_path,changes):
    with pytest.raises(ValueError):
        intake(tmp_path,**changes)


def test_closed_session_no_quote(tmp_path):
    app,kw=fixture(tmp_path)
    kw["session_source"]=lambda now: session(now.replace(hour=15))
    with pytest.raises(ValueError,match="SESSION"):
        app.evaluate(**kw)
    assert kw["provider"].calls == []


def test_acquisition_failure_no_retry_and_retained(tmp_path):
    app,kw=fixture(tmp_path)
    class Failure:
        calls=0
        def full_quotes(self,*a,**k):
            self.calls+=1
            raise RuntimeError("private provider error")
    provider=Failure();kw["provider"]=provider
    with pytest.raises(ValueError,match="ACQUISITION_OR_CONSTRUCTION_FAILED"):
        app.evaluate(**kw)
    with pytest.raises(ValueError):
        app.evaluate(**kw)
    assert provider.calls==1
    operations=app.store.records("WO10_ACQUISITION_OPERATION_V1")
    assert any(x.data["state"]=="FAILED" for x in operations)
    assert "private provider error" not in str(operations)


@pytest.mark.parametrize("delta", [-1,31])
def test_quote_timestamp_future_or_stale(tmp_path,delta):
    app,kw=fixture(tmp_path);kw["provider"]=Provider(now=NOW-timedelta(seconds=delta))
    c=app.evaluate(**kw)
    assert c.data["executability"]=="STALE"


def test_oi_roll_baseline_mismatch_rejected(tmp_path):
    app,kw=fixture(tmp_path);c=app.evaluate(**kw)
    snap=app.store.load(c.data["snapshot_identity"])
    contract=app.store.load(snap.data["contract_identity"])
    baseline=app.store.records("SESSION_FIRST_OBSERVED_OI_BASELINE_V1")[0]
    b=baseline.data;b["key"]["contract_record"]="foreign"
    wrong=record("SESSION_FIRST_OBSERVED_OI_BASELINE_V1",**b)
    _,rows=select_future(kw["master"],kw["adapter"].wo09,session(),now=NOW,underlying=kw["underlying"])
    with pytest.raises(ValueError,match="BASELINE_LINEAGE"):
        build_snapshot(contract,normalize_full_quotes(raw_quotes(rows),rows),operation_identity="x",request_identity="x",received_at=NOW,session=session(),baseline=wrong)


@pytest.mark.parametrize("direction,basis,expected", [
    ("LONG","2.031",("102.05","98.00","114.00")),
    ("SHORT","2.031",("102.00","106.05","90.05")),
])
def test_conservative_tick_mapping_keeps_canonical_geometry(tmp_path,direction,basis,expected):
    app,kw=fixture(tmp_path,direction);c=app.evaluate(**kw)
    plan=app.store.load(c.data["plan_identity"]); original=plan.payload_json
    snap=app.store.load(c.data["snapshot_identity"]);data=snap.data;data["basis"]=basis
    mapped=map_future(plan,record("WO10_FUTURES_MARKET_SNAPSHOT_V1",**data))
    assert tuple(D(mapped.data[k]) for k in ("entry","stop","target")) == tuple(D(x) for x in expected)
    assert plan.payload_json == original


def test_browser_projection_and_selection(tmp_path):
    from kronos.browser.intraday_futures_control import IntradayFuturesControl, render_futures
    from tests.unit.browser.test_product_route_isolation import _snapshot
    app,kw=fixture(tmp_path);c=app.evaluate(**kw)
    control=IntradayFuturesControl(app,lambda subject,now:session(now))
    status=control.status_document();html=render_futures(_snapshot(),status)
    assert "SELECT FUTURE" in html and "VIEW ANALYSIS DETAILS" in html
    assert "NOT_COMMISSIONED_V1" in html and "provider_instrument_token" not in html
    assert status["calculations"] == status["provider_calls"] == 0
    assert control.execute_document(dict(comparison_identity=c.identity,choice="NONE",lots=None,action_identity="browser"))["outcome"] == "RETAINED"


def test_scope_has_no_option_pricing_or_margin_permission():
    from pathlib import Path
    repo=Path(__file__).resolve().parents[3]
    text="\n".join(x.read_text() for x in (repo/"src/kronos/intraday").glob("wo10_futures*.py"))
    assert "BlackScholes" not in text and "implied_volatility" not in text
    assert "margin_per_lot" not in text and "margin_capacity_lots" not in text


@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_breakout_reuses_same_existing_engine(tmp_path,direction):
    from tests.unit.intraday.test_wo13_breakout import _evidence as breakout_evidence, _fact as breakout_fact
    from kronos.intraday.wo13_breakout import construct_wo13_breakout_geometry
    from kronos.intraday.wo13_geometry import Wo13StructuralRole as Role
    app,kw=fixture(tmp_path,direction)
    h=kw["adapter"].wo09;r=app.wo09.load_readiness(h.readiness_identity)
    a=adapt_wo09(h,r,app.wo09.load_pointer(h.canonical_subject_identity),now=NOW,session_identity=h.session_identity,
        setup_family=Wo13SetupFamily.INTRADAY_RANGE_BREAKOUT,setup_evidence_identity="machine",instrument_identity=h.canonical_subject_identity)
    # Existing test helper uses its historical session label; supply exact successor session on all facts.
    from tests.unit.intraday.test_wo13_breakout import _facts
    facts=_facts(a)
    def move(f):
        from kronos.intraday.wo13_geometry import create_wo13_structural_price_fact
        from dataclasses import asdict
        d=asdict(f);d.pop("fact_identity");d.pop("fact_integrity");d.pop("schema_identity");d.pop("schema_version")
        d["market_session_identity"]=h.session_identity
        return create_wo13_structural_price_fact(**d)
    facts=tuple(move(f) for f in facts)
    ev=breakout_evidence(a,range_high=facts[:1],range_low=facts[1:2],qualification=facts[2:],session=h.session_identity)
    g=construct_wo13_breakout_geometry(ev)
    kw.update(adapter=a,geometry_evidence=ev,target_population=create_wo13_target_constraint_population(setup_geometry=g))
    c=app.evaluate(**kw)
    assert c.data["executability"]=="EXECUTABLE"


def test_historical_controls_retired_in_successor_routes(tmp_path):
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    from kronos.browser.product_routes import BrowserPostRequest
    from tests.unit.browser.test_product_route_isolation import _snapshot
    from kronos.application.intraday_runtime import create_intraday_workstation
    routes=IntradayBrowserRoutes(create_intraday_workstation(),prospective_programme_v2=True)
    # Ownership test does not invoke a historical engine.
    for route in ("/control/intraday-wo13","/control/intraday-wo14"):
        request=BrowserPostRequest(route,{},"application/json",b"{}")
        result=routes.handle_post(request,_snapshot)
        assert "RETIRED_PROSPECTIVE_AUTHORITY" in result.body


@pytest.mark.parametrize("native",["100","99"])
def test_invalid_native_target_is_unavailable_without_shopping(tmp_path,native):
    from kronos.intraday.wo13_geometry import Wo13StructuralRole as Role
    app,kw=fixture(tmp_path);a=kw["adapter"]
    old=kw["geometry_evidence"]
    bad=_fact(a,native,Role.PRIOR_IMPULSE_HIGH,session=a.wo09.session_identity)
    ev=_evidence(a,qualification=old.qualification_candles,pullback=old.governing_pullback_structures,
                 impulse=(bad,),session=a.wo09.session_identity)
    kw.update(geometry_evidence=ev,target_population=create_wo13_target_constraint_population(setup_geometry=construct_wo13_pullback_geometry(ev)))
    with pytest.raises(ValueError,match="TRADE_PLAN_UNAVAILABLE"):
        app.evaluate(**kw)
    plans=app.store.records("WO10_CANONICAL_TRADE_PLAN_V1")
    assert len(plans)==1 and plans[0].data["state"]=="TRADE_PLAN_UNAVAILABLE"
    assert kw["provider"].calls==[]


def test_interrupted_selection_never_reports_complete_handoff(tmp_path,monkeypatch):
    app,kw=fixture(tmp_path);c=app.evaluate(**kw)
    original=app.store.retain
    def fail_handoff(item):
        if item.schema=="WO10_SELECTED_TRADE_HANDOFF_V1":
            raise OSError("simulated interruption")
        return original(item)
    monkeypatch.setattr(app.store,"retain",fail_handoff)
    with pytest.raises(OSError):
        app.select(c.identity,choice="SELECTED_FUTURE",lots=1,session=session(),action_identity="interrupt")
    monkeypatch.setattr(app.store,"retain",original)
    with pytest.raises(ValueError,match="WO10_SELECTION_HANDOFF_INCOMPLETE"):
        app.select(c.identity,choice="SELECTED_FUTURE",lots=1,session=session(),action_identity="interrupt")
    assert app.store.records("WO10_SELECTED_TRADE_HANDOFF_V1")==()


def test_optional_daily_master_is_one_operation_before_one_quote(tmp_path):
    app,kw=fixture(tmp_path); retained=kw["master"];calls=[]
    def acquire(**arguments):
        calls.append(arguments)
        return retained
    kw.update(master=None,acquire_master=acquire)
    c=app.evaluate(**kw)
    assert len(calls)==len(kw["provider"].calls)==1
    assert calls[0]==dict(request_identity="test-operation:MASTER",timeout=7)
    done=[x.data for x in app.store.records("WO10_ACQUISITION_OPERATION_V1") if x.data["state"]=="COMPLETED"]
    assert done[0]["request_attempts"]==2
    assert c.data["executability"]=="EXECUTABLE"


def test_master_failure_does_not_quote_or_retry(tmp_path):
    app,kw=fixture(tmp_path);calls=[]
    def acquire(**arguments):
        calls.append(arguments)
        raise RuntimeError("fixture master failure")
    kw.update(master=None,acquire_master=acquire)
    for _ in range(2):
        with pytest.raises(ValueError,match="ACQUISITION_OR_CONSTRUCTION_FAILED"):
            app.evaluate(**kw)
    assert len(calls)==1 and kw["provider"].calls==[]


def test_quote_completion_rechecks_actual_readiness_pointer(tmp_path,monkeypatch):
    app,kw=fixture(tmp_path); original=kw["provider"].full_quotes
    def changed(*args,**kwargs):
        result=original(*args,**kwargs)
        monkeypatch.setattr(app.wo09,"load_pointer",lambda subject:None)
        return result
    monkeypatch.setattr(kw["provider"],"full_quotes",changed)
    with pytest.raises(ValueError,match="EXACT_WO09_TYPES_REQUIRED"):
        app.evaluate(**kw)
    assert app.restore()==() and len(kw["provider"].calls)==1
    received=[x.data for x in app.store.records("WO10_ACQUISITION_OPERATION_V1") if x.data["state"]=="QUOTE_RECEIVED"]
    assert len(received)==1 and len(received[0]["quotes"])==2
    assert received[0]["authority"]=="FACTS_ONLY_NOT_CURRENT_SNAPSHOT"


def test_reacquisition_does_not_duplicate_opportunity_denominator(tmp_path):
    app,kw=fixture(tmp_path);app.evaluate(**kw)
    kw["request_identity"]="second-observation"
    app.evaluate(**kw)
    assert len(app.store.records("WO10_OPPORTUNITY_V1"))==1
    assert len(app.restore())==2


@pytest.mark.parametrize("family,expiry",[("GOLDM",date(2026,9,4)),("SILVERM",date(2026,8,31)),("COPPER",date(2026,8,31)),("CRUDE",date(2026,9,21))])
def test_mcx_expiry_day_preserves_existing_domain008_authority(family,expiry):
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo
    from tests.unit.instrument.test_active_derivative_selection import _snapshot, CATALOGUE
    from kronos.instrument.active_derivative import GovernedActiveDerivativeResolver
    from kronos.market.calendar import MarketCalendarPublisher
    from kronos.intraday.wo14 import create_wo14_instrument_economics
    from kronos.browser.intraday_futures_control import domain008_session
    now=datetime.combine(expiry,datetime.min.time(),ZoneInfo("Asia/Kolkata"))+timedelta(hours=12)
    m=_snapshot(now);publisher=MarketCalendarPublisher()
    active=GovernedActiveDerivativeResolver(catalogue=CATALOGUE,provider_snapshot=m,calendar_publisher=publisher).resolve_all(now).for_subject(family).binding
    row=next(x for x in m.records if x.provider_record_identity==active.provider_record_identity)
    assert row.expiry==expiry
    sess=domain008_session(publisher,active.canonical_subject_id,now,contract={"name":row.name,"expiry":row.expiry.isoformat()})
    h=SimpleNamespace(market_family="MCX",canonical_subject_identity=active.canonical_subject_id,direction="LONG",session_identity=sess.schedule.session_id,
        exact_mcx_contract_identity=active.active_binding.derivative_contract_id,exact_mcx_roll_lineage=active.binding_identity,handoff_identity="isolated-selector-input",readiness_identity="isolated-readiness")
    econ=create_wo14_instrument_economics(economics_version="1.0.0",canonical_subject_identity=h.canonical_subject_identity,
        instrument_identity=h.exact_mcx_contract_identity,actual_contract_identity=h.exact_mcx_contract_identity,roll_lineage_identity=active.binding_identity,
        lot_size=active.lot_size,contract_multiplier=D(1),tick_size=active.tick_size,tick_value=None,observed_at=now,
        source_identities=(active.binding_identity,),source_integrities=(active.integrity_identity,))
    _,rows=select_future(m,h,sess,now=now,active_mcx=active,economics=econ)
    assert rows==(row,)


def test_current_oi_is_retained_independently_of_bid_ask_permission(tmp_path):
    app,kw=fixture(tmp_path);kw["provider"]=Provider(bid=None)
    first=app.evaluate(**kw);snapshot=app.store.load(first.data["snapshot_identity"])
    assert snapshot.data["state"]=="MARKET_NOT_EXECUTABLE"
    baseline=app.store.records("SESSION_FIRST_OBSERVED_OI_BASELINE_V1")[0]
    assert snapshot.data["baseline_identity"]==baseline.identity
    assert snapshot.data["baseline_integrity"]==baseline.integrity
    assert snapshot.data["delta_oi"] is None
    app.clock=lambda:NOW+timedelta(seconds=1)
    kw.update(request_identity="later-oi",provider=Provider(bid=None,oi=1200,now=app.clock()))
    second=app.evaluate(**kw);snapshot=app.store.load(second.data["snapshot_identity"])
    assert snapshot.data["delta_oi"]==200 and snapshot.data["state"]=="MARKET_NOT_EXECUTABLE"


@pytest.mark.parametrize("identity",[None,False,1,[],{}," "])
def test_request_and_risk_source_identities_are_text(tmp_path,identity):
    with pytest.raises(ValueError):config(source_identity=identity)
    app,kw=fixture(tmp_path);c=app.evaluate(**kw)
    with pytest.raises(ValueError,match="SPONSOR_ACTION_INVALID"):
        app.select(c.identity,choice="NONE",lots=None,session=session(),action_identity=identity)


def test_completion_write_failure_cannot_leave_executable_authority(tmp_path,monkeypatch):
    app,kw=fixture(tmp_path);original=app.store.retain
    def fail_completion(item):
        if item.schema=="WO10_ACQUISITION_OPERATION_V1" and item.data["state"]=="COMPLETED":
            raise OSError("isolated completion write failure")
        return original(item)
    monkeypatch.setattr(app.store,"retain",fail_completion)
    with pytest.raises(ValueError):app.evaluate(**kw)
    current=app.store.current(kw["adapter"].canonical_subject_identity)
    assert current is not None
    assert app.decision_state(current,now=NOW,session=session())!="EXECUTABLE"
    with pytest.raises(ValueError):
        app.select(current.identity,choice="SELECTED_FUTURE",lots=1,session=session(),action_identity="after-failure")
