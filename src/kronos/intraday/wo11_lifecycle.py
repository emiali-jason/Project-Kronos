"""Pure prospective lifecycle transitions; no acquisition, clocks, or filesystem.

Every result contains immutable successor records. Browser and monitoring code
must persist the complete graph before exposing a new current pointer.
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from kronos.intraday.wo11_lifecycle_contract import (
    record, require, instant, price, digest, TRADING_EXIT_REASONS,
)

D = Decimal
TERMINAL = frozenset({"CLOSED", "CANCELLED_BEFORE_ENTRY", "INVALIDATED_BEFORE_ENTRY",
    "EXPIRED_BEFORE_ENTRY", "CLOSED_OUTCOME_UNAVAILABLE", "OUTCOME_AMBIGUOUS"})
OBSERVATION_STATES = {
    "PAPER_ARMED": "OBSERVATION_ARMED", "AWAITING_TIMING": "AWAITING_TIMING",
    "AWAITING_ENTRY": "AWAITING_MODEL_ENTRY", "ACTIVE": "OBSERVING_ACTIVE",
    "EXIT_PENDING": "OBSERVATION_CLOSE_PENDING", "CLOSED": "OBSERVATION_CLOSED",
    "CANCELLED_BEFORE_ENTRY": "OBSERVATION_STOPPED_BEFORE_ENTRY",
    "INVALIDATED_BEFORE_ENTRY": "OBSERVATION_INVALIDATED_BEFORE_ENTRY",
    "EXPIRED_BEFORE_ENTRY": "OBSERVATION_EXPIRED_BEFORE_ENTRY",
    "CLOSED_OUTCOME_UNAVAILABLE": "OBSERVATION_OUTCOME_UNAVAILABLE",
    "OUTCOME_AMBIGUOUS": "OBSERVATION_OUTCOME_AMBIGUOUS",
}


@dataclass(frozen=True)
class Transition:
    current: object
    evidence: tuple


def _successor(previous, state, at, reason, extras=(), **changes):
    old = require(previous, "WO11_TRACK_V1")
    new = dict(old, state=state, updated_at=instant(at), **changes)
    new["display_state"] = OBSERVATION_STATES[state] if old["truth_class"] == "PAPER_OBSERVATION" else state
    event = record("WO11_EVENT_V1", track_identity=old["track_identity"],
        authorization_identity=old["authorization_identity"], predecessor=previous.identity,
        from_state=old["state"], to_state=state, reason=reason, at=instant(at),
        evidence=[r.identity for r in extras])
    new.update(predecessor=previous.identity, event_identity=event.identity)
    current = record("WO11_TRACK_V1", **new)
    return Transition(current, (*extras, event, current))


def arm(intake, *, truth_class, action_identity, action_at):
    data = require(intake, "WO11_INTAKE_V1")
    now = instant(action_at)
    if truth_class not in {"PAPER_POSITION", "PAPER_OBSERVATION"}:
        raise ValueError("LIVE_POSITION_NOT_COMMISSIONED_V1")
    if not isinstance(action_identity, str) or not action_identity.strip():
        raise ValueError("WO11_SPONSOR_ACTION_REQUIRED")
    if not instant(data["selected_at"]) <= now < instant(data["session_close"]):
        raise ValueError("WO11_AUTHORIZATION_TIME_INVALID")
    if data["subject"] in {"MCX-NATGAS", "MCX-SUBJECT-NATGAS"}:
        raise ValueError("NATGAS_COMMISSIONING_HELD")
    for key in ("entry", "stop", "target"):
        price(data[key])
    if not ((price(data["stop"]) < price(data["entry"]) < price(data["target"]))
            if data["direction"] == "LONG" else
            (price(data["target"]) < price(data["entry"]) < price(data["stop"]))):
        raise ValueError("WO11_IMMUTABLE_GEOMETRY_INVALID")
    action = record("WO11_ACTION_V1", action_identity=action_identity, action_at=now,
        action="ACTIVATE_PAPER" if truth_class == "PAPER_POSITION" else "OBSERVE",
        intake_identity=intake.identity)
    auth = record("WO11_AUTHORIZATION_V1", intake_identity=intake.identity,
        intake=data, action_identity=action.identity, armed_at=now, truth_class=truth_class,
        lots=1, exposure_class="MODEL_EXPOSURE" if truth_class == "PAPER_POSITION" else "NON_EXPOSURE_COUNTERFACTUAL",
        claim=digest([data["opportunity_identity"], data["semantic_expression"]]))
    current = record("WO11_TRACK_V1", track_identity=auth.identity,
        authorization_identity=auth.identity, truth_class=truth_class, lots=1,
        state="AWAITING_TIMING", display_state="AWAITING_TIMING", intake=data,
        armed_at=now, updated_at=now, predecessor=None, event_identity=None,
        timing_identity=None, timing_at=None, entry=None, exit=None, close_request=None,
        exit_reason=None, terminal_status=None,
        monitoring="UNATTACHED", gaps=[], samples=[], observations=[],
        last_observed_at=None, last_sequence=None, last_connection=None,
        last_fact_identity=None, last_price=None, baseline_required=False, metrics=None)
    return Transition(current, (intake, action, auth, current))


def timing(current, qualification):
    d = require(current, "WO11_TRACK_V1")
    q = require(qualification, "WO11_TIMING_V1")
    if d["state"] not in {"AWAITING_TIMING", "AWAITING_ENTRY"}:
        raise ValueError("WO11_TIMING_STATE_INVALID")
    if (q["authorization_identity"] != d["authorization_identity"]
            or instant(q["completed_at"]) <= instant(d["armed_at"])
            or instant(q["qualified_at"]) < instant(q["completed_at"])):
        raise ValueError("WO11_TIMING_BINDING_INVALID")
    if not q["qualified"]:
        return _successor(current, d["state"], q["qualified_at"], "TIMING_NOT_QUALIFIED", (qualification,))
    return _successor(current, "AWAITING_ENTRY", q["qualified_at"], "TIMING_QUALIFIED", (qualification,),
        timing_identity=qualification.identity, timing_at=q["qualified_at"])


def gap(current, *, at, reason):
    d = require(current, "WO11_TRACK_V1")
    item = record("WO11_GAP_V1", authorization_identity=d["authorization_identity"],
        started_at=instant(at), reason=reason, previous_fact=d["last_fact_identity"])
    return _successor(current, d["state"], at, "MONITORING_INTERRUPTED", (item,),
        monitoring="INTERRUPTED", baseline_required=True, gaps=[*d["gaps"], item.identity])


def request_close(current, *, at, reason, source_identity):
    d = require(current, "WO11_TRACK_V1")
    if d["state"] in TERMINAL:
        raise ValueError("WO11_TRACK_TERMINAL")
    if reason not in {"SPONSOR_EXIT", "UPSTREAM_SUPERSEDED", "CONTRACT_INVALIDATED"}:
        raise ValueError("WO11_CLOSE_REASON_INVALID")
    if d["entry"] is not None and reason != "SPONSOR_EXIT":
        raise ValueError("WO11_POST_ENTRY_REASSESSMENT_NOT_COMMISSIONED_V1")
    if not source_identity or instant(at) < instant(d["armed_at"]):
        raise ValueError("WO11_CLOSE_SOURCE_REQUIRED")
    request = record("WO11_CLOSE_REQUEST_V1", authorization_identity=d["authorization_identity"],
        at=instant(at), reason=reason, source_identity=source_identity)
    if d["entry"] is not None:
        state, terminal_status = "EXIT_PENDING", None
    elif reason == "SPONSOR_EXIT":
        state = "CANCELLED_BEFORE_ENTRY"
        terminal_status = ("OBSERVATION_STOPPED_BEFORE_ENTRY"
            if d["truth_class"] == "PAPER_OBSERVATION" else "CANCELLED_BEFORE_ENTRY")
    else:
        state, terminal_status = "INVALIDATED_BEFORE_ENTRY", "UPSTREAM_SUPERSEDED"
    return _successor(current, state, at, reason, (request,),
        close_request=request.data | {"identity": request.identity},
        exit_reason=None, terminal_status=terminal_status)


def terminal_at(current):
    i = require(current, "WO11_TRACK_V1")["intake"]
    end = instant(i["session_close"])
    return min(end, instant(i["contract_boundary"])) if i.get("contract_boundary") else end


def boundary(current, *, at, reason="SESSION_ENDED", contract_evidence=None):
    d = require(current, "WO11_TRACK_V1")
    if d["state"] in TERMINAL:
        return Transition(current, ())
    prerequisite = d["entry"]["at"] if d["entry"] is not None else d["armed_at"]
    if instant(at) < instant(prerequisite):
        raise ValueError("WO11_BOUNDARY_CAUSAL_PREREQUISITE_NOT_SATISFIED")
    extras = ()
    if contract_evidence is not None:
        from kronos.instrument.active_derivative import ActiveDerivativeBindingArtifact
        if type(contract_evidence) is not ActiveDerivativeBindingArtifact:
            raise ValueError("WO11_EXACT_CONTRACT_BOUNDARY_SOURCE_REQUIRED")
        contract_evidence.__post_init__()
        previous = d["intake"]["contract"]["active_mcx"]
        if (previous is None or contract_evidence.canonical_subject_id != d["intake"]["subject"]
                or contract_evidence.observation_boundary > instant(at)
                or contract_evidence.active_binding.derivative_contract_id == previous["active_binding"]["derivative_contract_id"]):
            raise ValueError("WO11_CONTRACT_ROLL_NOT_ESTABLISHED")
        extras = (record("WO11_CONTRACT_BOUNDARY_V1", authorization_identity=d["authorization_identity"],
                         source=contract_evidence, at=instant(at), reason="CONTRACT_ROLLED"),)
        reason = "CONTRACT_ROLLED"
    elif instant(at) < terminal_at(current):
        raise ValueError("WO11_BOUNDARY_NOT_REACHED")
    elif d["intake"].get("contract_boundary") and instant(at) >= instant(d["intake"]["contract_boundary"]):
        reason = "CONTRACT_EXPIRED"
    # No cached mark or subsequent-session price can close at this boundary.
    state = "EXPIRED_BEFORE_ENTRY" if d["entry"] is None else "CLOSED_OUTCOME_UNAVAILABLE"
    terminal_status = "EXPIRED_BEFORE_ENTRY" if d["entry"] is None else (
        "CONTRACT_ENDED" if reason in {"CONTRACT_ROLLED", "CONTRACT_EXPIRED"} else "SESSION_ENDED")
    return _successor(current, state, at, reason, extras, monitoring="SESSION_ENDED",
        exit_reason=None, terminal_status=terminal_status)


def metrics(data, *, exit_price=None):
    entry = data["entry"]
    if entry is None:
        return None
    p0 = price(entry["price"])
    sign = D(1) if data["intake"]["direction"] == "LONG" else D(-1)
    values = [sign * (price(s["price"]) - p0) for s in data["samples"]]
    mfe = max([D(0), *values]); mae = max([D(0), *[-x for x in values]])
    risk = sign * (p0 - price(data["intake"]["stop"]))
    points = None if exit_price is None else sign * (price(exit_price) - p0)
    units = data["intake"].get("monetary_units")
    monetary = None if units is None or points is None else points * price(units)
    return record("WO11_METRICS_V1", authorization_identity=data["authorization_identity"], lots=1,
        samples=len(data["samples"]), source_facts=[s["fact_identity"] for s in data["samples"]],
        coverage_start=entry["at"], coverage_end=data["samples"][-1]["at"] if data["samples"] else entry["at"],
        gaps=data["gaps"], complete=not data["gaps"],
        coverage_label="COVERED_SEGMENTS_ONLY" if data["gaps"] else "ELIGIBLE_OBSERVATIONS",
        mfe=mfe, mae=mae, full_path_mfe=None if data["gaps"] else mfe,
        full_path_mae=None if data["gaps"] else mae, points=points,
        model_r=None if risk <= 0 or points is None else points / risk,
        planned_rr=data["intake"].get("planned_rr"), gross_model_result=monetary,
        result_label="COUNTERFACTUAL GROSS MODEL P&L — 1 LOT" if data["truth_class"] == "PAPER_OBSERVATION" else "GROSS MODEL P&L — 1 LOT")


def observe(current, observation):
    d = require(current, "WO11_TRACK_V1")
    o = require(observation, "WO11_MARKET_OBSERVATION_V1")
    if o["authorization_identity"] != d["authorization_identity"]:
        raise ValueError("WO11_OBSERVATION_AUTHORIZATION_MISMATCH")
    if o["fact_identity"] in d["observations"]:
        return Transition(current, ())
    if not o["eligible"]:
        # Facts remain retained without influencing price, event order or metrics.
        return _successor(current, d["state"], o["decision_at"], o["reason"], (observation,),
            observations=[*d["observations"], o["fact_identity"]])
    f = o["fact"]; now = instant(f["observed_at"]); p = price(f["last_price"])
    ids = [*d["observations"], o["fact_identity"]]
    previous_time = None if d["last_observed_at"] is None else instant(d["last_observed_at"])
    same_connection = d["last_connection"] == f["connection_id"]
    sequence = f["source_sequence"]; old_sequence = d["last_sequence"]
    duplicate_time = previous_time == now
    lawful_sequence = (same_connection and sequence is not None and old_sequence is not None and sequence > old_sequence)
    unordered = (previous_time is not None and now < previous_time) or (
        duplicate_time and not lawful_sequence and str(p) != d["last_price"])
    if same_connection and sequence is not None and old_sequence is not None and sequence <= old_sequence:
        unordered = True
    if unordered:
        # A terminal outcome is never silently rewritten: retain an ambiguity successor.
        return _successor(current, "OUTCOME_AMBIGUOUS", o["decision_at"], "OBSERVATION_ORDER_NOT_ESTABLISHED",
            (observation,), observations=ids, monitoring="INTERRUPTED", baseline_required=True,
            exit=None, exit_reason=None, terminal_status="OUTCOME_AMBIGUOUS", metrics=None)
    if d["state"] in TERMINAL:
        return Transition(current, (observation,))
    if now >= terminal_at(current):
        closed = boundary(current, at=now)
        return Transition(closed.current, (observation, *closed.evidence))
    base = dict(observations=ids, last_observed_at=now, last_sequence=sequence,
        last_connection=f["connection_id"], last_fact_identity=o["fact_identity"], last_price=str(p))
    if d["baseline_required"] or (d["last_connection"] is not None and not same_connection):
        return _successor(current, d["state"], o["decision_at"], "FRESH_BASELINE_ESTABLISHED", (observation,),
            **base, baseline_required=False, monitoring="AVAILABLE")
    if d["entry"] is None:
        if d["timing_at"] is None or now <= instant(d["timing_at"]) or now <= instant(d["armed_at"]):
            return _successor(current, d["state"], o["decision_at"], "AWAITING_TIMING", (observation,), **base)
        if now >= instant(d["intake"]["entry_cutoff"]):
            return _successor(current, "EXPIRED_BEFORE_ENTRY", o["decision_at"], "ENTRY_CUTOFF_REACHED", (observation,), **base)
        crossed = p >= price(d["intake"]["entry"]) if d["intake"]["direction"] == "LONG" else p <= price(d["intake"]["entry"])
        if not crossed:
            return _successor(current, d["state"], o["decision_at"], "AWAITING_ENTRY", (observation,), **base)
        entry = record("WO11_ENTRY_V1", authorization_identity=d["authorization_identity"],
            price=p, at=now, trigger_fact=o["fact_identity"], price_fact=o["fact_identity"],
            observation_identity=observation.identity, timing_identity=d["timing_identity"],
            pricing_identity=o["pricing_identity"], lots=1)
        return _successor(current, "ACTIVE", o["decision_at"], "MODEL_ENTRY", (observation, entry),
            **base, entry=entry.data | {"identity": entry.identity},
            samples=[dict(price=str(p), at=now.isoformat(), fact_identity=o["fact_identity"])])
    if now <= instant(d["entry"]["at"]):
        return _successor(current, "OUTCOME_AMBIGUOUS", o["decision_at"], "ENTRY_EVENT_ORDER_UNAVAILABLE", (observation,), **base)
    samples = [*d["samples"], dict(price=str(p), at=now.isoformat(), fact_identity=o["fact_identity"])]
    reason = None
    if d["close_request"] is not None and now > instant(d["close_request"]["at"]):
        reason = "SPONSOR_EXIT"
    elif d["intake"]["direction"] == "LONG":
        reason = "STOP_LOSS" if p <= price(d["intake"]["stop"]) else "TARGET" if p >= price(d["intake"]["target"]) else None
    else:
        reason = "STOP_LOSS" if p >= price(d["intake"]["stop"]) else "TARGET" if p <= price(d["intake"]["target"]) else None
    metric = metrics(dict(d, samples=samples), exit_price=p if reason else None)
    if reason is None:
        return _successor(current, d["state"], o["decision_at"], "ELIGIBLE_OBSERVATION", (observation, metric),
            **base, samples=samples, metrics=metric.identity)
    exit_record = record("WO11_EXIT_V1", authorization_identity=d["authorization_identity"],
        at=now, price=p, reason=reason, trigger_fact=o["fact_identity"], price_fact=o["fact_identity"],
        observation_identity=observation.identity, pricing_identity=o["pricing_identity"],
        close_request=None if d["close_request"] is None else d["close_request"]["identity"])
    return _successor(current, "CLOSED", o["decision_at"], reason, (observation, exit_record, metric),
        **base, samples=samples, metrics=metric.identity,
        exit=exit_record.data | {"identity": exit_record.identity},
        exit_reason=reason, terminal_status="CLOSED")


def research_handoff(current, *, retained_metrics=None):
    d = require(current, "WO11_TRACK_V1")
    if d["state"] not in TERMINAL:
        raise ValueError("WO11_CLOSED_TRACK_REQUIRED")
    return record("WO11_WO12_HANDOFF_V1", track_identity=d["track_identity"], current_identity=current.identity,
        opportunity_identity=d["intake"]["opportunity_identity"], denominator=1,
        truth_class=d["truth_class"], lots=1, intake=d["intake"], timing_identity=d["timing_identity"],
        entry=d["entry"], exit=d["exit"], closure_state=d["display_state"],
        exit_reason=d["exit_reason"], terminal_status=d["terminal_status"],
        sponsor_exit_request_identity=(d["close_request"]["identity"]
            if d["close_request"] is not None and d["close_request"]["reason"] == "SPONSOR_EXIT" else None),
        gaps=d["gaps"], metrics=None if retained_metrics is None else retained_metrics.data,
        original_thesis_invalidation=d["intake"].get("invalidation"),
        thesis_invalidation_role="THESIS_DEFINITION_CONTEXT_ONLY",
        observation_exposure=False, wo10_selected_lots_context=d["intake"]["selected_lots"])
