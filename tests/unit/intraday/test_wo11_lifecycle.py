"""Prospective one-lot model truth; synthetic fixtures, no operational authority."""
from dataclasses import replace
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal as D
import pytest
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import ProviderMarketTick
from kronos.intraday.wo11_lifecycle_contract import *
from kronos.intraday.wo11_lifecycle import arm, timing, observe, request_close, boundary, gap, metrics, research_handoff

NOW = datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc)
FUTURE = InstrumentRecord("KITE", "NFO", "NFO-FUT", "LUPIN26SEPFUT", "LUPIN", "FUT", date(2026, 9, 29), D("0.05"), 100)


def tick(*, seconds=2, value="103", lag=0, **kw):
    at = NOW + timedelta(seconds=seconds)
    return ProviderMarketTick(FUTURE, D(value), at, at + timedelta(seconds=lag),
        "KITE_CONNECT_WEBSOCKET", "connection-1", kw.pop("source_sequence", None),
        kw.pop("previous_interval_available", True), kw.pop("session_continuous", True),
        kw.pop("ordering_deterministic", True), kw.pop("recovered", False), **kw)


def observation(track, t, **kw):
    values = dict(authorization_identity=track.data["authorization_identity"], instrument=FUTURE,
        session_identity="test-session", expected_session_identity="test-session",
        causal_at=NOW, decision_at=max(NOW, t.received_at) if t.received_at else NOW)
    values.update(kw)
    return websocket_observation(t, **values)


def track(truth="PAPER_POSITION", direction="LONG", **kw):
    data = dict(selected_at=NOW, session_close=NOW+timedelta(hours=5), entry_cutoff=NOW+timedelta(hours=4),
        subject="NSE-EQ-LUPIN", direction=direction, entry="102", stop="98" if direction=="LONG" else "106",
        target="114" if direction=="LONG" else "90", opportunity_identity="test-opportunity", semantic_expression="test-expression",
        selected_lots=25, monetary_units="100", planned_rr="3")
    data.update(kw)
    return arm(record("WO11_INTAKE_V1", **data), truth_class=truth, action_identity="sponsor-test", action_at=NOW).current


def qualified(truth="PAPER_POSITION", direction="LONG", **kw):
    s=track(truth, direction, **kw)
    q=record("WO11_TIMING_V1", authorization_identity=s.data["authorization_identity"],
        completed_at=NOW+timedelta(seconds=1), qualified_at=NOW+timedelta(seconds=1), qualified=True)
    return timing(s,q).current


def active(truth="PAPER_POSITION", direction="LONG", **kw):
    s=qualified(truth,direction,**kw)
    t=tick(value="103" if direction=="LONG" else "101")
    return observe(s,observation(s,t)).current


@pytest.mark.parametrize("lag,eligible", [(0,True),(1,True),(4.999999,True),(5,True),(5.000001,False),(10,False)])
def test_exact_lateness(lag,eligible):
    s=track(); o=observation(s,tick(lag=lag))
    assert o.data["eligible"] is eligible
    assert o.data["lateness_microseconds"] == round(lag*1_000_000)
    assert o.data["lateness_identity"] == LATENESS
    assert o.data["lateness_checksum"] == LATENESS_CHECKSUM
    assert o.data["reason"] == ("ELIGIBLE" if eligible else "WEBSOCKET_OBSERVATION_STALE")


@pytest.mark.parametrize("truth",["PAPER_POSITION","PAPER_OBSERVATION"])
@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_exact_price_one_lot_and_truth(truth,direction):
    s=active(truth,direction)
    assert s.data["lots"]==1 and s.data["intake"]["selected_lots"]==25
    assert s.data["entry"]["price"]==("103" if direction=="LONG" else "101")
    assert s.data["display_state"] == ("ACTIVE" if truth=="PAPER_POSITION" else "OBSERVING_ACTIVE")


@pytest.mark.parametrize("direction,value,reason",[("LONG","97","STOP_LOSS"),("LONG","116","TARGET"),("SHORT","107","STOP_LOSS"),("SHORT","89","TARGET"),
    ("LONG","98","STOP_LOSS"),("LONG","114","TARGET"),("SHORT","106","STOP_LOSS"),("SHORT","90","TARGET")])
def test_exit_actual_ltp(direction,value,reason):
    s=active(direction=direction); t=tick(seconds=3,value=value)
    result=observe(s,observation(s,t)); d=result.current.data
    assert d["state"]=="CLOSED" and d["exit"]["price"]==value and d["exit"]["reason"]==reason
    assert d["exit_reason"]==reason and d["terminal_status"]=="CLOSED"
    m=next(x for x in result.evidence if x.schema=="WO11_METRICS_V1")
    assert D(m.data["gross_model_result"])==D(m.data["points"])*100
    h=research_handoff(result.current,retained_metrics=m)
    assert h.data["denominator"]==1 and h.data["lots"]==1


@pytest.mark.parametrize("value",["97","116","105"])
def test_late_exit_and_metric_inert(value):
    s=active(); t=tick(seconds=3,value=value,lag=5.000001)
    result=observe(s,observation(s,t))
    assert result.current.data["state"]=="ACTIVE"
    assert result.current.data["entry"]==s.data["entry"]
    assert result.current.data["samples"]==s.data["samples"]
    assert result.evidence[0].schema=="WO11_MARKET_OBSERVATION_V1"


def test_late_entry_inert():
    s=qualified(); t=tick(lag=10)
    assert observe(s,observation(s,t)).current.data["entry"] is None


@pytest.mark.parametrize("field",["previous_interval_available","session_continuous","ordering_deterministic","recovered"])
def test_gap_or_recovery_ineligible(field):
    s=qualified(); t=tick(**{field:field=="recovered"})
    assert not observation(s,t).data["eligible"]
    assert observe(s,observation(s,t)).current.data["entry"] is None


def test_no_pre_timing_entry():
    s=track(); t=tick()
    assert observe(s,observation(s,t)).current.data["entry"] is None


def test_no_pre_arm_entry():
    s=qualified(); t=tick(seconds=0)
    assert observation(s,t).data["reason"]=="WEBSOCKET_CAUSAL_PREREQUISITE_NOT_SATISFIED"


@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_exact_entry_threshold(direction):
    s=qualified(direction=direction); t=tick(value="102")
    assert observe(s,observation(s,t)).current.data["entry"]["price"]=="102"


def test_manual_close_causal_and_no_manual_price():
    s=active(); s=request_close(s,at=NOW+timedelta(seconds=4),reason="SPONSOR_EXIT",source_identity="sponsor-close").current
    t=tick(seconds=3,value="104")
    assert observe(s,observation(s,t)).current.data["exit"] is None
    late=tick(seconds=5,value="106",lag=6)
    assert observe(s,observation(s,late)).current.data["exit"] is None
    t=tick(seconds=6,value="105")
    result=observe(s,observation(s,t)).current
    assert result.data["exit"]["price"]=="105" and result.data["exit_reason"]=="SPONSOR_EXIT"


@pytest.mark.parametrize("truth",["PAPER_POSITION","PAPER_OBSERVATION"])
def test_cancel_before_entry_no_results(truth):
    s=request_close(track(truth),at=NOW,reason="SPONSOR_EXIT",source_identity="cancel").current
    assert s.data["state"]=="CANCELLED_BEFORE_ENTRY" and s.data["entry"] is None and metrics(s.data) is None
    expected="CANCELLED_BEFORE_ENTRY" if truth=="PAPER_POSITION" else "OBSERVATION_STOPPED_BEFORE_ENTRY"
    assert s.data["exit_reason"] is None and s.data["terminal_status"]==expected


def test_equal_time_conflicting_stop_target_remains_ambiguous():
    s=active(); t=tick(seconds=3,value="97")
    s=observe(s,observation(s,t)).current
    t=tick(seconds=3,value="116")
    s=observe(s,observation(s,t)).current
    assert s.data["state"]=="OUTCOME_AMBIGUOUS"
    assert s.data["exit_reason"] is None and s.data["terminal_status"]=="OUTCOME_AMBIGUOUS"


def test_equal_timestamp_price_receipt_does_not_invent_conflict():
    s=active(); t=tick(seconds=3,value="105")
    s=observe(s,observation(s,t)).current
    t=tick(seconds=3,value="105",lag=1)
    assert observe(s,observation(s,t)).current.data["state"]=="ACTIVE"


def test_first_post_gap_is_baseline_and_metrics_incomplete():
    s=gap(active(),at=NOW+timedelta(seconds=3),reason="DISCONNECTED").current
    t=tick(seconds=4,value="116")
    s=observe(s,observation(s,t)).current
    assert s.data["state"]=="ACTIVE"
    t=tick(seconds=5,value="106")
    s=observe(s,observation(s,t)).current
    m=metrics(s.data)
    assert m.data["complete"] is False and m.data["full_path_mfe"] is None
    assert m.data["coverage_label"]=="COVERED_SEGMENTS_ONLY"


@pytest.mark.parametrize("entered",[True,False])
def test_final_session_no_cached_or_next_day_price(entered):
    s=active() if entered else qualified()
    result=boundary(s,at=NOW+timedelta(hours=5)).current
    assert result.data["state"]==("CLOSED_OUTCOME_UNAVAILABLE" if entered else "EXPIRED_BEFORE_ENTRY")
    assert result.data["exit"] is None
    assert result.data["exit_reason"] is None
    assert result.data["terminal_status"]==("SESSION_ENDED" if entered else "EXPIRED_BEFORE_ENTRY")


def test_missing_monetary_is_not_points_veto():
    s=active(monetary_units=None); t=tick(seconds=3,value="116")
    result=observe(s,observation(s,t))
    m=next(x for x in result.evidence if x.schema=="WO11_METRICS_V1")
    assert m.data["points"]=="13" and m.data["gross_model_result"] is None


def test_observation_counterfactual_label():
    s=active("PAPER_OBSERVATION")
    assert metrics(s.data).data["result_label"]=="COUNTERFACTUAL GROSS MODEL P&L — 1 LOT"


@pytest.mark.parametrize("truth",["LIVE_POSITION","SPONSOR_ATTESTED_LIVE_FACTS",None])
def test_live_uncommissioned(truth):
    with pytest.raises(ValueError,match="LIVE_POSITION_NOT_COMMISSIONED_V1"):
        track(truth)


def test_no_quantity_argument():
    with pytest.raises(TypeError):
        arm(record("WO11_INTAKE_V1"),truth_class="PAPER_POSITION",action_identity="x",action_at=NOW,lots=10)


def test_contract_tampering_rejects():
    s=track()
    with pytest.raises(ValueError,match="INTEGRITY"):
        replace(s,payload_json=s.payload_json.replace('"lots":1','"lots":2'))


def test_foreign_contract_and_session_rejected():
    s=track(); t=tick()
    assert observation(s,t,instrument=replace(FUTURE,expiry=date(2026,10,27))).data["reason"]=="WEBSOCKET_CONTRACT_MISMATCH"
    assert observation(s,t,session_identity="wrong").data["reason"]=="WEBSOCKET_SESSION_MISMATCH"


def test_future_received_time_rejected():
    s=track(); t=tick()
    assert observation(s,t,decision_at=NOW).data["reason"]=="WEBSOCKET_FUTURE_OBSERVATION"


@pytest.mark.parametrize("value",[None,datetime(2026,9,14),NOW+timedelta(seconds=100)])
def test_invalid_observed_timestamp_unavailable(value):
    s=track(); t=tick()
    object.__setattr__(t,"observed_at",value)
    assert not observation(s,t).data["eligible"]


def test_replay_same_fact_inert():
    s=active(); t=tick(seconds=3,value="105"); o=observation(s,t)
    s=observe(s,o).current
    assert observe(s,o).evidence==()
