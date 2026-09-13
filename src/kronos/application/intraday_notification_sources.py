"""Typed WO-09/10/11 to shared Notifications adapters; no upstream calculation."""
from zoneinfo import ZoneInfo
from kronos.intraday.notification_policy import (
    POLICY_IDENTITY, POLICY_VERSION, POLICY_CHECKSUM, ACTION_REASONS, aware, validate,
)
from kronos.intraday.wo12_research_contract import require as research
from kronos.intraday.wo10_futures_contract import require as futures
from kronos.intraday.wo11_lifecycle_contract import require as lifecycle
from kronos.intraday.wo09_readiness import ReadinessRecord, CurrentnessState
from kronos.intraday.wo11_lifecycle import TERMINAL


def base(origin, *, subject, direction, session, source_identity, source_integrity, at):
    d = research(origin,"WO12_OPPORTUNITY_ORIGIN_V1")
    if (d["canonical_subject_identity"] != subject or d["market_session_identity"] != session
        or aware(d["origin_at"]) > aware(at)):
        raise ValueError("WO13_OPPORTUNITY_SOURCE_BINDING_INVALID")
    return dict(opportunity_id=d["opportunity_id"], opportunity_identity=d["opportunity_identity"],
        subject=subject,direction=direction,market_family=d["market_family"],session_identity=session,
        trading_date=aware(d["origin_at"]).astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat(),
        source_identity=source_identity,source_integrity=source_integrity,event_identity=source_identity,
        event_at=aware(at).isoformat(),policy_identity=POLICY_IDENTITY,
        policy_version=POLICY_VERSION,policy_checksum=POLICY_CHECKSUM)


def ready(origin, record):
    if type(record) is not ReadinessRecord:
        raise ValueError("WO13_READINESS_RECORD_REQUIRED")
    record.__post_init__()
    if record.currentness is not CurrentnessState.CURRENT or record.satisfied_count not in {4,5} or record.hard_gate.value != "NONE":
        return None
    # The approved immutable readiness contract supplies its first event time;
    # centre deduplication preserves that timestamp across semantic successors.
    d = base(origin,subject=record.canonical_subject_identity,direction=record.direction,
        session=record.session_identity,source_identity=record.readiness_identity,
        source_integrity=record.integrity_identity,at=record.created_at)
    d.update(family="READY_FIVE" if record.satisfied_count==5 else "READY_FOUR",
        semantic_transition="FIRST_REACHED",readiness_count=record.satisfied_count,
        criteria=", ".join(c.criterion_id.value+":"+c.state.value for c in record.criteria))
    validate(d)
    return d


def trade_candidate(origin, comparison, expression, plan, advisory):
    c=futures(comparison,"WO10_SPONSOR_COMPARISON_V1")
    e=futures(expression,"WO10_FUTURE_EXPRESSION_V1")
    p=futures(plan,"WO10_CANONICAL_TRADE_PLAN_V1")
    if c["expression_identity"]!=expression.identity or c["plan_identity"]!=plan.identity or c["advisory_identity"]!=advisory.identity:
        raise ValueError("WO13_TRADE_SOURCE_BINDING_INVALID")
    advisory.__post_init__()
    if p["state"]!="AVAILABLE" or e["state"]!="EXECUTABLE" or c["executability"]!="EXECUTABLE":
        return None
    d=base(origin,subject=c["subject"],direction=c["direction"],session=p["session_identity"],
        source_identity=comparison.identity,source_integrity=comparison.integrity,at=c["created_at"])
    d.update(family="TRADE_CANDIDATE",semantic_transition="AVAILABLE:"+e["future"]["trading_symbol"],
        contract=e["future"]["trading_symbol"],expiry=e["future"]["expiry"],executability=c["executability"],
        risk_advisory=str(advisory.data.get("state","UNAVAILABLE")))
    for k in ("entry","stop","target","model_rr"):
        if e.get(k) is not None:d[k]=str(e[k])
    validate(d)
    return d


def unavailable(origin, source, session):
    d=futures(source,"WO10_CONSTRUCTION_UNAVAILABLE_V1")
    if d["reason"] not in ACTION_REASONS:return None
    notice=base(origin,subject=d["subject"],direction=d["direction"],session=session,
        source_identity=source.identity,source_integrity=source.integrity,at=d["created_at"])
    notice.update(family="ACTION_REQUIRED",semantic_transition=d["reason"],reason=d["reason"])
    validate(notice)
    return notice


def track_events(origin, current, *, event=None, metrics=None, gap_record=None):
    d=lifecycle(current,"WO11_TRACK_V1");i=d["intake"]
    if d["truth_class"] not in {"PAPER_POSITION","PAPER_OBSERVATION"} or d["lots"]!=1:
        raise ValueError("WO13_TRACK_TRUTH_INVALID")
    if event is not None:
        e=lifecycle(event,"WO11_EVENT_V1")
        if event.identity!=d["event_identity"] or e["track_identity"]!=d["track_identity"] or e["to_state"]!=d["state"]:
            raise ValueError("WO13_LIFECYCLE_EVENT_BINDING_INVALID")
    common=base(origin,subject=i["subject"],direction=i["direction"],session=i["session_identity"],
        source_identity=current.identity,source_integrity=current.integrity,at=d["updated_at"])
    common.update(track_identity=d["track_identity"],truth_class=d["truth_class"],lots=1,
        owner_identity="INTRADAY-WO11-LIFECYCLE:"+d["track_identity"],contract=i["future"]["trading_symbol"],
        expiry=i["future"]["expiry"],stop=str(i["stop"]),target=str(i["target"]))
    results=[]
    if d["entry"] is not None:
        entry=d["entry"]
        results.append(dict(common,family="PAPER_ENTRY" if d["truth_class"]=="PAPER_POSITION" else "OBSERVATION_ENTRY",
            event_identity=entry["identity"],event_at=entry["at"],semantic_transition="MODEL_ENTRY",
            entry=str(entry["price"]),pricing_identity=entry["pricing_identity"]))
    if d["exit"] is not None and d["exit_reason"] in {"TARGET","STOP_LOSS","SPONSOR_EXIT"} and d["terminal_status"]=="CLOSED":
        x=d["exit"]
        if x["reason"]!=d["exit_reason"] or d["entry"] is None:
            raise ValueError("WO13_EXIT_BINDING_INVALID")
        notice=dict(common,family=d["exit_reason"],event_identity=x["identity"],event_at=x["at"],
            semantic_transition="MODEL_EXIT",entry=str(d["entry"]["price"]),exit=str(x["price"]),
            pricing_identity=x["pricing_identity"],action_identity=x.get("close_request"))
        if metrics is not None:
            md=lifecycle(metrics,"WO11_METRICS_V1")
            if metrics.identity!=d["metrics"]:raise ValueError("WO13_METRIC_BINDING_INVALID")
            for src,dest in (("points","model_points"),("model_r","model_rr"),("gross_model_result","one_lot_result")):
                if md.get(src) is not None:notice[dest]=str(md[src])
        results.append(notice)
    if d["monitoring"]=="INTERRUPTED" and d["gaps"] and d["state"] not in TERMINAL:
        if gap_record is None or gap_record.identity != d["gaps"][-1]:
            raise ValueError("WO13_GAP_BINDING_INVALID")
        gap=lifecycle(gap_record,"WO11_GAP_V1") | {"identity":gap_record.identity}
        results.append(dict(common,family="MONITORING_INTERRUPTED",semantic_transition=gap["identity"],
            gap_identity=gap["identity"],event_identity=gap["identity"],event_at=gap["started_at"]))
    for result in results:validate(result)
    return tuple(results)


def monitoring_indicator(details, owner_states, *, terminal=False):
    """Exact owner projection supplied by lifecycle, never inferred from REST."""
    if terminal or details["family"] in {"TARGET","STOP_LOSS","SPONSOR_EXIT"}:
        return "NOT_REQUIRED"
    owner=details.get("owner_identity")
    if owner is None:return "NOT_REQUIRED" if details["family"] in {"TRADE_CANDIDATE","ACTION_REQUIRED"} else "UNAVAILABLE"
    state=owner_states.get(owner)
    return state if state in {"LIVE","INTERRUPTED","IDLE","NOT_REQUIRED","UNAVAILABLE"} else "UNAVAILABLE"
