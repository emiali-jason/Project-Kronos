"""Exact current WO-10 graph admission, with no quote or geometry acquisition."""
from dataclasses import fields
from datetime import date
from zoneinfo import ZoneInfo
from kronos.intraday.wo10_futures_contract import require as wo10_require
from kronos.intraday.wo11_lifecycle_contract import record, instant, price, digest
from kronos.provider.contracts.instrument import InstrumentRecord


def instrument_record(data):
    values = {f.name: data[f.name] for f in fields(InstrumentRecord)}
    values["expiry"] = None if values["expiry"] is None else date.fromisoformat(values["expiry"])
    return InstrumentRecord(**values)


def load_intake(application, identity, *, session, now, arming=True):
    h = application.store.load(identity)
    hd = wo10_require(h, "WO10_SELECTED_TRADE_HANDOFF_V1")
    s = application.store.load(hd["selection_identity"])
    sd = wo10_require(s, "WO10_SPONSOR_SELECTION_V1")
    if sd != hd["selection"] or sd["choice"] != "SELECTED_FUTURE" or hd["authority"] != "SELECTED_TRADE_ONLY_NO_ACTIVATION":
        raise ValueError("WO11_SELECTED_FUTURE_REQUIRED")
    c = application.store.load(sd["comparison_identity"])
    cd = wo10_require(c, "WO10_SPONSOR_COMPARISON_V1")
    if sd["comparison"] != cd or application.store.current(cd["subject"]) != c:
        raise ValueError("WO11_HANDOFF_SUPERSEDED")
    for name, schema in (("plan", "WO10_CANONICAL_TRADE_PLAN_V1"),
                         ("snapshot", "WO10_FUTURES_MARKET_SNAPSHOT_V1"),
                         ("expression", "WO10_FUTURE_EXPRESSION_V1")):
        retained = application.store.load(cd[name + "_identity"])
        if wo10_require(retained, schema) != hd[name]:
            raise ValueError("WO11_HANDOFF_GRAPH_MISMATCH")
    advisory = application.store.load(sd["risk_advisory_identity"])
    if advisory.data != sd["advisory_risk"] or advisory.data != hd["advisory_risk"]:
        raise ValueError("WO11_ADVISORY_LINEAGE_MISMATCH")
    wo09 = application.wo09.load_handoff(cd["handoff_identity"])
    pointer = application.wo09.load_pointer(cd["subject"])
    if (pointer is None or pointer.currentness.value != "CURRENT"
            or pointer.readiness_identity != cd["readiness_identity"]
            or pointer.integrity_identity != wo09.current_pointer_integrity):
        raise ValueError("WO11_UPSTREAM_SUPERSEDED")
    if application.structural_loader is None:
        raise ValueError("WO11_NATIVE_SOURCE_LOADER_REQUIRED")
    native = application.structural_loader.load(wo09, now=now)
    nd = native.data
    if nd.get("result") != "PULLBACK":
        raise ValueError("WO11_COMMISSIONED_PULLBACK_REQUIRED")
    p, e, snapshot = hd["plan"], hd["expression"], hd["snapshot"]
    if p["adapter"]["native_selection"]["identity"] != native.identity:
        raise ValueError("WO11_NATIVE_SELECTION_MISMATCH")
    contract = snapshot["contract"]
    for body in (p, e, contract):
        if body["subject"] != cd["subject"] or body["direction"] != cd["direction"]:
            raise ValueError("WO11_SUBJECT_DIRECTION_MISMATCH")
    if e["future"] != contract["future"] or e["plan_identity"] != cd["plan_identity"] or e["snapshot_identity"] != cd["snapshot_identity"]:
        raise ValueError("WO11_EXPRESSION_LINEAGE_MISMATCH")
    if instant(sd["selected_at"]) != instant(hd["selected_at"]) or instant(hd["selected_at"]) > now:
        raise ValueError("WO11_SELECTION_TIME_INVALID")
    if arming and application.decision_state(c, now=now, session=session) != "EXECUTABLE":
        raise ValueError("WO11_HANDOFF_NOT_CURRENT_EXECUTABLE")
    from kronos.intraday.wo10_futures_market import require_session
    require_session(session, now, exchange="MCX" if contract["active_mcx"] else "NSE")
    if session.schedule.session_id != contract["session_identity"] or session.trading_date.isoformat() != contract["trading_date"]:
        raise ValueError("WO11_SESSION_MISMATCH")
    opportunity = application.store.load(cd["opportunity_identity"])
    od = wo10_require(opportunity, "WO10_OPPORTUNITY_V1")
    if od["readiness_identity"] != cd["readiness_identity"] or od["subject"] != cd["subject"]:
        raise ValueError("WO11_OPPORTUNITY_MISMATCH")
    future = instrument_record(e["future"])
    if future.expiry < session.trading_date:
        raise ValueError("WO11_CONTRACT_EXPIRED")
    end = max(w.closes_at for w in session.schedule.windows)
    local = now.astimezone(ZoneInfo("Asia/Kolkata"))
    cutoff = min(end, local.replace(hour=23 if contract["active_mcx"] else 15, minute=0, second=0, microsecond=0))
    money = e["monetary_economics"]
    return record("WO11_INTAKE_V1", handoff_identity=h.identity, selection_identity=s.identity,
        comparison_identity=c.identity, opportunity_identity=opportunity.identity,
        native_selection_identity=native.identity, native_selection=nd, plan_identity=cd["plan_identity"],
        snapshot_identity=cd["snapshot_identity"], expression_identity=cd["expression_identity"],
        wo09_identity=wo09.handoff_identity, subject=cd["subject"], direction=cd["direction"],
        future=e["future"], contract=contract, session_identity=contract["session_identity"],
        session_close=end, contract_boundary=None if not contract["active_mcx"] else contract["active_mcx"]["expiry_eligibility_boundary"],
        entry_cutoff=cutoff, entry=e["entry"], stop=e["stop"], target=e["target"],
        canonical_entry=p["entry"], invalidation=p["invalidation"], planned_rr=e["model_rr"],
        selected_lots=sd["sponsor_selected_lots"], selected_at=sd["selected_at"], advisory=advisory.data,
        monetary_units=money.get("rupees_per_quoted_point"),
        semantic_expression=digest(dict(future=e["future"], direction=cd["direction"], plan_identity=cd["plan_identity"])))
