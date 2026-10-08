"""WO-SWING-NEXT-15 observational Portfolio boundary.

DOMAIN-005/P32-004/S32-006 and ADR-0013 retain all position/model authority.
This reader neither reconciles presentation ledgers nor consults notification
suppression. Objective models, Sponsor positions and observations stay separate;
only known entered Sponsor quantity contributes to current exposure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from urllib.parse import urlencode

from kronos.application.swing_mcx_journal import mcx_journal_handoffs
from kronos.application.swing_reports import _retained_fill_capture
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleState, LifecycleEventType,
)
from kronos.swing.v1.native_entry_timing import LocalObjectiveModelV1Store
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.mcx_step31_construction import select_owner_current_mcx_handoff
from kronos.swing.v1.step32 import ObjectiveModelState, SponsorPositionState
from kronos.swing.v1.step32 import candidate_digest
from kronos.swing.v1.trade_construction import TradeCandidateIntegrity


_FAMILIES = frozenset(("GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"))
PORTFOLIO_FILTERS = {
    "market": frozenset(("", "NSE", "MCX", "UNRESOLVED")),
    "family": frozenset(("", "NSE", "UNRESOLVED", *_FAMILIES)),
    "mode": frozenset(("", "PAPER", "LIVE", "OBJECTIVE_MODEL", "OBSERVATION")),
    "state": frozenset(("", "WAITING", "ACTIVE", "ACTION_REQUIRED", "CLOSED")),
    "direction": frozenset(("", "LONG", "SHORT")),
    "monitoring": frozenset(("", "LIVE", "INTERRUPTED", "IDLE", "UNAVAILABLE")),
}


@dataclass(frozen=True, slots=True)
class SwingPortfolioProjection:
    available: bool
    source_status: str
    issues: tuple[str, ...]
    as_of: datetime
    positions: tuple[dict, ...] = ()
    waiting_plans: tuple[dict, ...] = ()
    objective_models: tuple[dict, ...] = ()
    observations: tuple[dict, ...] = ()
    closed_positions: tuple[dict, ...] = ()
    validation_positions: tuple[dict, ...] = ()
    exposure_groups: tuple[dict, ...] = ()
    coverage: dict | None = None


class _SourceUnavailable(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise _SourceUnavailable(reason)


def _unique(items, field):
    keys = tuple(getattr(item, field) for item in items)
    _require(len(keys) == len(set(keys)), "SWING_PORTFOLIO_AMBIGUOUS_SOURCE")


def _retained_lifecycle(owner):
    current, retained = owner.snapshot(), owner.store.load()
    for name, field in (("positions", "position_id"), ("events", "event_id"),
                        ("closures", "closure_id")):
        rows, disk = getattr(current, name), getattr(retained, name)
        _unique(rows, field)
        _unique(disk, field)
        _require({getattr(row, field): row for row in rows}
                 == {getattr(row, field): row for row in disk},
                 "SWING_PORTFOLIO_RETAINED_LIFECYCLE_CHANGED")
    positions = {item.position_id: item for item in current.positions}
    closures = {item.position_id: item for item in current.closures}
    _require(len(closures) == len(current.closures), "SWING_PORTFOLIO_AMBIGUOUS_CLOSURE")
    for item in current.positions:
        _require((item.state is ActiveLifecycleState.CLOSED) == (item.position_id in closures),
                 "SWING_PORTFOLIO_CLOSURE_UNAVAILABLE")
    for closure in current.closures:
        position = positions.get(closure.position_id)
        _require(position is not None and (
            closure.decision_id, closure.trade_plan_id, closure.trade_plan_hash,
            closure.mode, closure.direction, closure.actual_entry, closure.lots,
            closure.underlying_quantity) == (
            position.decision_id, position.trade_plan_id, position.trade_plan_hash,
            position.mode, position.direction, position.actual_entry, position.lots,
            position.underlying_quantity), "SWING_PORTFOLIO_CLOSURE_BINDING_INVALID")
    for event in current.events:
        position = positions.get(event.position_id)
        _require(position is not None and (
            event.decision_id, event.trade_plan_id, event.trade_plan_hash, event.mode,
            event.direction) == (
            position.decision_id, position.trade_plan_id, position.trade_plan_hash,
            position.mode, position.direction), "SWING_PORTFOLIO_EVENT_BINDING_INVALID")
    return current


def _native_models(window):
    """Enumerate current immutable model pointers, never old market history."""
    store = window._objective_model_store
    _require(type(store) is LocalObjectiveModelV1Store,
             "SWING_PORTFOLIO_OBJECTIVE_OWNER_UNAVAILABLE")
    pointers = store.root / "current"
    _require(not store.root.is_symlink() and not pointers.is_symlink(),
             "SWING_PORTFOLIO_OBJECTIVE_POINTER_INVALID")
    values, tokens = [], []
    for path in sorted(pointers.glob("*.json")):
        _require(not path.is_symlink(), "SWING_PORTFOLIO_OBJECTIVE_POINTER_INVALID")
        payload = path.read_bytes()
        fields = json.loads(payload)
        key = fields.get("current_key")
        record_id = fields.get("record_id")
        _require(type(key) is str and key and type(record_id) is str
                 and record_id and "/" not in record_id and "\\" not in record_id
                 and path.name == sha256(key.encode()).hexdigest() + ".json",
                 "SWING_PORTFOLIO_OBJECTIVE_POINTER_INVALID")
        model = store.load_for_plan(key)
        _require(model is not None and model.trade_plan_id == key
                 and model.model_trade_id == record_id,
                 "SWING_PORTFOLIO_OBJECTIVE_BINDING_INVALID")
        values.append(model)
        tokens.append((path.name, payload, model))
    _unique(values, "model_trade_id")
    loaded = {item.trade_plan_id: item for item in values}
    for key, reference in window._production_models.copy().items():
        model = loaded.get(key)
        _require(model is not None and model.model_trade_id == reference.model_trade_id
                 and model.integrity_sha256 == reference.source_integrity_sha256,
                 "SWING_PORTFOLIO_OBJECTIVE_CURRENT_POINTER_UNAVAILABLE")
    return tuple(values), tuple(tokens)


def _monitoring_quote(native, position, as_of):
    proof = native.journal_position_monitoring_evidence(position.position_id)
    _require(proof[0] in {"ACTIVE", "INTERRUPTED", "UNKNOWN", "NOT_REQUIRED"},
             "SWING_PORTFOLIO_MONITORING_SOURCE_INVALID")
    tick = None
    coordinator = native._active_lifecycle_monitoring
    if proof[0] == "ACTIVE":
        if position.mcx_v1_contract_symbol is not None:
            latest = coordinator.latest_mcx_observation(position.position_id)
            tick = None if latest is None else latest[0]
        else:
            # There is no public NSE quote accessor. Reuse the coordinator's
            # exact owner and subscription evidence without creating a consumer.
            with coordinator._lock:
                consumer = coordinator._consumers.get(position.position_id)
                if consumer is not None and not consumer.closed:
                    candidate = consumer.last_accepted_tick
                    read = getattr(consumer.session, "observation_context", None)
                    context = read(consumer.instrument) if callable(read) else None
                    if (candidate is not None and context is not None
                            and context.admits(candidate)):
                        tick = candidate
        if tick is not None and (
                tick.connection_id != proof[1]
                or tick.observed_at != position.last_observed_at
                or tick.last_price != position.last_observed_price
                or tick.observed_at > as_of or tick.received_at > as_of
                or not tick.session_continuous or not tick.ordering_deterministic
                or tick.recovered):
            tick = None
        if tick is None:
            proof = ("UNKNOWN", None, position.last_observation_id)
    return proof, tick


def _source_snapshot(native, step32, window, mcx, as_of):
    _require(native is not None and step32 is not None and window is not None,
             "SWING_PORTFOLIO_OWNER_UNAVAILABLE")
    generation = window.reports_generation()
    lifecycle = _retained_lifecycle(native._active_lifecycle)
    legacy = step32.snapshot()
    _require(not legacy.synchronization_failure,
             "SWING_PORTFOLIO_STEP32_SOURCE_UNAVAILABLE")
    native_models, model_tokens = _native_models(window)
    # MCX is an installed independent historical-contract owner, even when the
    # retained position book is empty. Absence cannot certify combined emptiness.
    _require(mcx is not None and mcx.lifecycle is native._active_lifecycle
             and mcx.native_review is native,
             "SWING_PORTFOLIO_MCX_OWNER_UNAVAILABLE")
    mcx_rows = mcx_journal_handoffs(mcx, as_of.date())
    _unique(mcx_rows, "sponsor_position_identity")
    by_mcx = {row.sponsor_position_identity: row for row in mcx_rows}
    # The guard checks immutable publication pointers and generation; it does
    # not acquire market data or commission an entry. Existing positions do not
    # depend on current-run availability.
    current_advisories, advisory_status = (), "UNAVAILABLE"
    workflow = getattr(mcx, "workflow", None)
    if workflow is not None:
        try:
            workflow._current()
            candidates = tuple(mcx.plans.load(path) for path in sorted(
                (mcx.plans.root / workflow.run_identity).glob("*/*.json")))
            _unique(candidates, "trade_plan_id")
            current_advisories = tuple(plan for plan in candidates
                if plan.native_run_identity == workflow.run_identity)
            # Reuse one owner-validated response across the bounded current
            # plan set. This preserves exact receipt/V2/selection fences without
            # repeatedly rebuilding a Review graph for each family.
            if current_advisories:
                with mcx.review_owner._validated_response() as (response, _):
                    selected = []
                    for plan in current_advisories:
                        instrument = mcx._selected(plan)
                        owner = select_owner_current_mcx_handoff(
                            mcx.review_owner, plan.family, instrument,
                            prepared_at=plan.created_at, _response=response)
                        selection = workflow.selections.load(
                            plan.native_run_identity, plan.family)
                        workflow._validate_v1_plan_owner(
                            plan.family, instrument, plan, mcx.plans, selection, owner)
                        selected.append(owner)
                    for owner in selected:
                        owner.fence.check()
                    mcx.review_owner.recheck_response(response)
            workflow._current()
            advisory_status = "AVAILABLE"
        except (AttributeError, ValueError, OSError, KeyError, TypeError):
            current_advisories = ()
    fill_facts = []
    for position in lifecycle.positions:
        if position.mcx_v1_contract_symbol is None:
            _require(position.mcx_quantity is None,
                     "SWING_PORTFOLIO_UNSUPPORTED_MCX_POSITION")
            continue
        _require(position.position_id in by_mcx, "SWING_PORTFOLIO_MCX_POSITION_UNAVAILABLE")
        if position.mode is SponsorTradeChoice.LIVE:
            binding = mcx.bound.bindings.load(position.position_id)
            entry = mcx.live_attestations.load(position.trade_plan_id)
            capture = _retained_fill_capture(mcx, position, entry)
            mcx.broker_evidence.verify(capture, entry, position, binding)
            fill_facts.append((position.position_id, entry))
            closure = next((item for item in lifecycle.closures
                            if item.position_id == position.position_id), None)
            if closure is not None:
                exit_fill = mcx.live_attestations.load_exit(position.position_id)
                capture = _retained_fill_capture(mcx, position, exit_fill)
                mcx.broker_evidence.verify_exit(capture, exit_fill, closure, binding)
                fill_facts.append((position.position_id, exit_fill))
    monitoring = tuple((position.position_id,
                        *_monitoring_quote(native, position, as_of))
                       for position in lifecycle.positions)
    # Source snapshots remain separate from research and presentation ledgers.
    # Immutable Track metadata suffices to establish zero position contribution.
    track_store = window._paper_observation_tracking._store
    tracks = track_store.load_all_tracks()
    _unique(tracks, "track_identity")
    track_states = tuple(track_store.restoration_projection(item.track_identity)
                         for item in tracks)
    with native._lock:
        plans = tuple(native._trade_plans.values())
    with window._projection_lock:
        window_plans = tuple(window._plans.values())
    _require(window.reports_generation() == generation,
             "SWING_PORTFOLIO_SOURCE_CHANGED")
    return (lifecycle, legacy, native_models, model_tokens, mcx_rows,
            tuple(fill_facts), monitoring, tracks, plans, window_plans, generation,
            track_states, current_advisories, advisory_status)


def _base(identity, truth, state, instrument, direction, mode, *, market=None,
          family=None):
    unresolved = (instrument == "MCX" or instrument in _FAMILIES
                  or (instrument.endswith("FUT") and any(
                      instrument.startswith(item) for item in _FAMILIES)))
    market = market or ("UNRESOLVED" if unresolved else "NSE")
    family = family or ("UNRESOLVED" if unresolved else "NSE")
    return dict(
        identity=identity, position_identity=None, truth=truth, state=state,
        instrument=instrument, contract=None, expiry=None,
        market=market, family=family, direction=direction, mode=mode,
        lots=None, units=None, quantity_provenance="UNKNOWN",
        entry=None, entry_at=None, exit=None, exit_at=None, closure_reason=None,
        model_entry=None, stop=None, target=None, invalidation=None,
        monitoring="UNAVAILABLE", source_monitoring="UNKNOWN",
        current_price=None, current_price_at=None, price_received_at=None,
        last_price=None, last_price_at=None, valuation_state="UNKNOWN",
        quote_age_seconds=None, currentness="UNVERIFIED",
        monetary_value=None, monetary_pnl=None, monetary_multiplier=None,
        monetary_basis="UNKNOWN", costs="UNKNOWN", attention="",
        plan_identity=None, plan_sha256=None, related_models=(), related_positions=(),
        evidence=(), links=(), exposure=False,
    )


def _links(decision=None, *, step33=None, instrument=None):
    values = []
    if decision is not None:
        values.append(("Trading Journal", "/journal?" + urlencode(
            {"product": "SWING", "record": decision})))
    if step33 is not None:
        values.append(("Step-33 history", "/journal?" + urlencode(
            {"product": "SWING", "view": "research", "record": step33})))
    # Reports primary identities are not interchangeable with position IDs.
    # A factual instrument search uses its existing accepted query semantics.
    values.append(("Reports", "/reports?" + urlencode(
        {"product": "SWING", **({"search": instrument} if instrument else {})})))
    return tuple(values)


def _display_monitoring(proof):
    return {"ACTIVE": "LIVE", "UNKNOWN": "UNAVAILABLE",
            "INTERRUPTED": "INTERRUPTED", "NOT_REQUIRED": "IDLE"}[proof]


def _compose(sources, as_of):
    (lifecycle, legacy, models, _, mcx_rows, fills, monitoring,
     tracks, native_plans, window_plans, _, track_states,
     current_advisories, advisory_status) = sources
    mcx = {row.sponsor_position_identity: row for row in mcx_rows}
    observed = {identity: (proof, tick) for identity, proof, tick in monitoring}
    closures = {row.position_id: row for row in lifecycle.closures}
    positions, waiting, objectives, observations, closed, validation = [], [], [], [], [], []
    by_identity = {}
    for position in lifecycle.positions:
        row = _base(position.position_id, "SPONSOR_POSITION", position.state.value,
                    position.canonical_instrument, position.direction.value,
                    position.mode.value)
        row.update(position_identity=position.position_id,
                   lots=position.lots, model_entry=position.model_entry,
                   entry=position.actual_entry, entry_at=position.entry_timestamp,
                   stop=position.stop, target=position.target,
                   invalidation=position.invalidation,
                   plan_identity=position.trade_plan_id,
                   plan_sha256=position.trade_plan_hash,
                   last_price=position.last_observed_price,
                   last_price_at=position.last_observed_at,
                   quantity_provenance="CANONICAL_SPONSOR_POSITION",
                   currentness="AUTHORITATIVE_LIFECYCLE_STATE",
                   units=position.underlying_quantity)
        exact = mcx.get(position.position_id)
        if exact is not None:
            row.update(market="MCX", family=position.canonical_instrument,
                       instrument=exact.instrument, contract=exact.instrument,
                       expiry=exact.exact_contract_expiry, units=None,
                       quantity_provenance="RETAINED_WHOLE_MCX_LOTS; PHYSICAL_UNITS_UNKNOWN")
        proof, tick = observed[position.position_id]
        row.update(source_monitoring=proof[0], monitoring=_display_monitoring(proof[0]))
        if tick is not None:
            row.update(current_price=tick.last_price, current_price_at=tick.observed_at,
                       price_received_at=tick.received_at,
                       contract=tick.instrument.trading_symbol,
                       quote_age_seconds=max(0, int((as_of - tick.observed_at).total_seconds())),
                       valuation_state="LATEST_ACCEPTED_OBSERVATION_FRESHNESS_UNKNOWN")
        elif position.last_observed_price is not None:
            row["valuation_state"] = "STALE_OR_UNAVAILABLE_CURRENT_PRICE"
        if (position.mode is SponsorTradeChoice.LIVE
                and position.state is not ActiveLifecycleState.CLOSED and any(
                event in {LifecycleEventType.STOP_HIT, LifecycleEventType.TARGET_HIT,
                          LifecycleEventType.INVALIDATION_OBSERVED}
                for event in position.observed_event_types)):
            row["attention"] = "LIVE ACTION REQUIRED — FACTUAL EXIT NOT RECORDED"
        if position.state is ActiveLifecycleState.EVENT_UNRESOLVED:
            row["attention"] = row["attention"] or "EVENT ORDERING UNRESOLVED"
        notices = []
        if proof[0] == "INTERRUPTED":
            notices.append("MONITORING INTERRUPTED; KNOWN EXPOSURE RETAINED")
        elif proof[0] == "UNKNOWN":
            notices.append("MONITORING / CURRENT PRICE UNAVAILABLE")
        if exact is not None and exact.exact_contract_expiry < as_of.date().isoformat():
            notices.append("RETAINED CONTRACT EXPIRY PASSED; NO CONTRACT ROLL")
        row["attention"] = " · ".join(filter(None, (row["attention"], *notices)))
        row["evidence"] = (
            ("Position SHA-256", position.integrity_hash),
            ("Plan", position.trade_plan_id), ("Plan SHA-256", position.trade_plan_hash),
            ("Decision", position.decision_id), ("Lifecycle", position.lifecycle_id),
            ("Prior state", None if position.prior_state is None else position.prior_state.value),
            ("Accepted observation", proof[2]), ("Monitoring session", proof[1]),
            ("Observed at", position.last_observed_at),
            ("Quantity source", row["quantity_provenance"]),
            ("Provenance", " | ".join(position.provenance)),
            ("LIVE evidence origin", "SPONSOR_SUBMITTED_UNVERIFIED"
             if position.mode is SponsorTradeChoice.LIVE else "NOT_APPLICABLE"),
        ) + (exact.source_events if exact is not None else ())
        # Normalize existing triples into labelled evidence without changing facts.
        row["evidence"] = tuple((item[0], item[1] if len(item) == 2 else
                                 " · ".join(str(value) for value in item[1:]))
                                for item in row["evidence"])
        row["links"] = _links(position.decision_id, instrument=row["instrument"])
        if exact is not None:
            row["links"] += (("Commissioned MCX workspace", "/swing/mcx-v1"),)
        else:
            row["links"] += (("Commissioned Swing management", "/swing/active"),)
        closure = closures.get(position.position_id)
        if closure is not None:
            row.update(exit=closure.actual_exit, exit_at=closure.exit_timestamp,
                       closure_reason=closure.exit_reason.value,
                       monetary_pnl=closure.gross_pnl, state="CLOSED")
            row["evidence"] += (("Closure", closure.closure_id),
                                ("Closure SHA-256", closure.integrity_hash))
            closed.append(row)
        elif position.actual_entry is not None and position.entry_timestamp is not None:
            row["exposure"] = True
            positions.append(row)
        else:
            row["active_status"] = "WAITING"
            waiting.append(row)
        by_identity[position.position_id] = row

    for model in models:
        if model.state is ObjectiveModelState.CLOSED:
            continue
        row = _base(model.model_trade_id, "OBJECTIVE_MODEL", model.state.value,
                    model.canonical_instrument, model.direction, "OBJECTIVE_MODEL")
        row.update(plan_identity=model.trade_plan_id, plan_sha256=model.trade_plan_sha256,
                   model_entry=model.entry, entry_at=model.activated_at,
                   stop=model.stop, target=model.target, invalidation=model.invalidation_reference,
                   quantity_provenance="OBJECTIVE_MODEL_HAS_NO_SPONSOR_QUANTITY",
                   authority="ADR-0013 NATIVE OBJECTIVE MODEL")
        row["evidence"] = (("Model SHA-256", model.integrity_sha256),
                           ("Run", model.native_run_identity),
                           ("Entry outcome", model.entry_outcome_id),
                           ("Risk", model.risk_result_id),
                           ("Model monitoring record", model.monitoring_state.value))
        row["links"] = _links(instrument=model.canonical_instrument)
        objectives.append(row)

    for record in legacy.records:
        candidate, model, sponsor = record.candidate, record.objective_model, record.sponsor_position
        _require(candidate.integrity_status is TradeCandidateIntegrity.VALID,
                 "SWING_PORTFOLIO_STEP32_INTEGRITY_INVALID")
        if model is not None and model.state is not ObjectiveModelState.CLOSED:
            _require(model.integrity is TradeCandidateIntegrity.VALID,
                     "SWING_PORTFOLIO_STEP32_INTEGRITY_INVALID")
            _require(model.candidate_digest == candidate_digest(candidate),
                     "SWING_PORTFOLIO_STEP32_MODEL_BINDING_INVALID")
            if any(item["identity"] == model.model_trade_id for item in objectives):
                raise _SourceUnavailable("SWING_PORTFOLIO_AMBIGUOUS_MODEL")
            row = _base(model.model_trade_id, "OBJECTIVE_MODEL", model.state.value,
                        model.canonical_instrument, model.direction, "OBJECTIVE_MODEL")
            row.update(model_entry=model.entry_price, entry_at=model.activated_at,
                       stop=model.stop_price, target=model.target_price,
                       plan_identity=candidate.candidate_id, plan_sha256=model.candidate_digest,
                       authority="HISTORICAL STEP-32 VALIDATION ONLY",
                       quantity_provenance="OBJECTIVE_MODEL_HAS_NO_SPONSOR_QUANTITY",
                       evidence=(("Candidate", candidate.candidate_id),
                                 ("Model", model.model_trade_id),
                                 ("Authority", "VALIDATION ONLY")))
            row["links"] = (("Legacy workspace", "/swing/trade-candidates/" + record.browser_key),) + _links(
                instrument=model.canonical_instrument)
            objectives.append(row)
        if sponsor is not None and sponsor.state is not SponsorPositionState.CLOSED:
            _require(sponsor.integrity is TradeCandidateIntegrity.VALID,
                     "SWING_PORTFOLIO_STEP32_INTEGRITY_INVALID")
            _require(sponsor.sponsor_position_id not in by_identity,
                     "SWING_PORTFOLIO_AMBIGUOUS_POSITION")
            row = _base(sponsor.sponsor_position_id, "SPONSOR_POSITION",
                        sponsor.state.value, candidate.canonical_instrument,
                        candidate.direction, sponsor.mode.value)
            row.update(position_identity=sponsor.sponsor_position_id,
                       units=sponsor.actual_quantity, entry=sponsor.actual_entry_price,
                       model_entry=sponsor.model_reference_entry_price,
                       plan_identity=candidate.candidate_id, plan_sha256=model.candidate_digest if model else None,
                       stop=candidate.stop_price, target=candidate.target_price,
                       authority="HISTORICAL STEP-32 VALIDATION ONLY",
                       quantity_provenance="SPONSOR_EVIDENCE" if sponsor.actual_quantity is not None else "UNKNOWN",
                       related_models=(sponsor.model_trade_id,),
                       evidence=(("Evidence", sponsor.evidence_id),
                                 ("Quantity availability", sponsor.actual_quantity_availability.value),
                                 ("Provenance", " | ".join(sponsor.provenance))))
            row["links"] = (("Legacy workspace", "/swing/trade-candidates/" + record.browser_key),) + _links(
                instrument=candidate.canonical_instrument)
            if record.action_required:
                row["attention"] = "LIVE ACTION REQUIRED — FACTUAL EXIT NOT RECORDED"
            # The historical Step-32 path is validation-only. Even explicit
            # evidence does not commission it as production Sponsor exposure.
            row["exposure"] = False
            validation.append(row)
            by_identity[sponsor.sponsor_position_id] = row

    represented = {row["plan_identity"] for row in (*positions, *waiting, *closed, *objectives)}
    plans = {}
    for plan in (*native_plans, *window_plans):
        existing = plans.get(plan.trade_plan_id)
        _require(existing is None or existing == plan, "SWING_PORTFOLIO_AMBIGUOUS_PLAN")
        plans[plan.trade_plan_id] = plan
    for plan in plans.values():
        if plan.trade_plan_id in represented:
            continue
        row = _base(plan.trade_plan_id, "PLAN_ONLY", "WAITING",
                    plan.canonical_instrument, plan.native_direction.value, "")
        row.update(plan_identity=plan.trade_plan_id, plan_sha256=plan.integrity_hash,
                   model_entry=plan.entry, stop=plan.stop, target=plan.canonical_target,
                   currentness="CURRENTNESS_UNVERIFIED; NOT READINESS OR ENTRY AUTHORITY",
                   evidence=(("Plan", plan.trade_plan_id), ("Plan SHA-256", plan.integrity_hash)),
                   links=_links(instrument=plan.canonical_instrument))
        waiting.append(row)
    represented.update(plan.trade_plan_id for plan in plans.values())
    for plan in current_advisories:
        if plan.trade_plan_id in represented:
            continue
        row = _base(plan.trade_plan_id, "ADVISORY_PLAN_ONLY", "WAITING",
                    plan.contract_symbol, plan.native_direction.value, "",
                    market="MCX", family=plan.family.value)
        row.update(contract=plan.contract_symbol, expiry=plan.expiry,
                   plan_identity=plan.trade_plan_id, plan_sha256=plan.integrity_hash,
                   model_entry=plan.entry, stop=plan.stop, target=plan.canonical_target,
                   currentness="CURRENT_RETAINED_ADVISORY; NO POSITION OR ENTRY AUTHORITY",
                   evidence=(("Plan SHA-256", plan.integrity_hash),
                             ("Run", plan.native_run_identity),
                             ("Review receipt", plan.receipt_integrity_sha256),
                             ("V2", plan.promotion_integrity_sha256)),
                   links=(("Commissioned MCX workspace", "/swing/mcx-v1"),) + _links(
                       instrument=plan.contract_symbol))
        waiting.append(row)
    for track, control in zip(tracks, track_states, strict=True):
        row = _base(track.track_identity, "PAPER_OBSERVATION",
                    "COMPLETE" if control.terminal else "OBSERVATION_OPEN",
                    track.canonical_instrument, track.direction.value, "OBSERVATION")
        row.update(model_entry=track.observation_entry_reference,
                   stop=track.stop, target=track.target, exposure=False,
                   monitoring="IDLE" if control.terminal else
                       "INTERRUPTED" if control.monitoring_state.value == "INTERRUPTED"
                       else "UNAVAILABLE",
                   quantity_provenance="NON_POSITION_OBSERVATION — ZERO POSITION EXPOSURE",
                   evidence=(("Track SHA-256", track.integrity_sha256),
                             ("Decision", track.sponsor_decision_identity),
                             ("Activation", track.activation_disposition.value),
                             ("Latest factual event", control.latest_event.value),
                             ("Monitoring evidence", control.monitoring_state.value),
                             ("Monitoring reason", control.monitoring_reason)),
                   links=_links(track.sponsor_decision_identity,
                                instrument=track.canonical_instrument))
        observations.append(row)

    # Exact plan lineage groups representations; never add model quantity to a
    # Sponsor position or deduplicate unrelated positions merely by symbol.
    for model in objectives:
        linked = tuple(row["identity"] for row in positions + waiting
                       if row["plan_identity"] == model["plan_identity"]
                       and row["plan_sha256"] == model["plan_sha256"])
        model["related_positions"] = linked
        for position in positions + waiting:
            if position["identity"] in linked:
                position["related_models"] += (model["identity"],)
    return positions, waiting, objectives, observations, closed, validation


def _matches(row, search, filters):
    if search and search.casefold() not in " ".join(str(row.get(key) or "") for key in
            ("identity", "instrument", "contract", "family", "plan_identity")).casefold():
        return False
    for key in ("market", "family", "mode", "direction", "monitoring"):
        if filters[key] and row[key] != filters[key]:
            return False
    selected = filters["state"]
    if selected:
        state = ("CLOSED" if row["state"] == "CLOSED" else "ACTION_REQUIRED"
                 if row["attention"].startswith("LIVE ACTION REQUIRED") else "ACTIVE"
                 if row["exposure"] or row["truth"] == "OBJECTIVE_MODEL" else "WAITING")
        if selected != state:
            return False
    return True


def _groups(positions):
    groups = {}
    for row in positions:
        key = (row["market"], row["family"], row["direction"], row["mode"],
               row["instrument"], row["contract"] or "UNKNOWN", row["expiry"] or "UNKNOWN",
               row["quantity_provenance"])
        group = groups.setdefault(key, dict(
            market=key[0], family=key[1], direction=key[2], mode=key[3],
            instrument=key[4], contract=key[5], expiry=key[6], quantity_basis=key[7],
            position_count=0, known_lots=0, known_units=Decimal(0),
            lots_complete=True, units_complete=True, valued_positions=0,
            monetary_value=None, monetary_pnl=None, valuation_complete=False,
            monetary_basis="UNKNOWN — NO COMMISSIONED PORTFOLIO TOTAL CONTRACT",
        ))
        group["position_count"] += 1
        if row["lots"] is None:
            group["lots_complete"] = False
        else:
            group["known_lots"] += row["lots"]
        if row["units"] is None:
            group["units_complete"] = False
        else:
            group["known_units"] += Decimal(row["units"])
        if row["current_price"] is not None:
            group["valued_positions"] += 1
    for group in groups.values():
        if not group["lots_complete"]:
            group["known_lots"] = None
        if not group["units_complete"]:
            group["known_units"] = None
    return tuple(groups[key] for key in sorted(groups))


def read_swing_portfolio(native_review, step32_workflow, *, as_of,
                         trade_window, mcx_control, search="", direction="",
                         monitoring="", market="", family="", mode="", state=""):
    """Return a stable observational book; invalid queries raise ValueError.

    Source failure returns UNAVAILABLE, never a verified empty population.
    Both reads use the same existing owners and perform no repair or retention.
    """
    if not isinstance(as_of, datetime) or as_of.tzinfo is None:
        raise ValueError("SWING_PORTFOLIO_AS_OF_INVALID")
    if not isinstance(search, str) or len(search) > 80:
        raise ValueError("SWING_PORTFOLIO_FILTER_INVALID")
    filters = dict(direction=direction, monitoring=monitoring, market=market,
                   family=family, mode=mode, state=state)
    if any(value not in PORTFOLIO_FILTERS[key] for key, value in filters.items()):
        raise ValueError("SWING_PORTFOLIO_FILTER_INVALID")
    try:
        first = _source_snapshot(native_review, step32_workflow, trade_window, mcx_control, as_of)
        positions, waiting, models, observations, closed, validation = _compose(first, as_of)
        second = _source_snapshot(native_review, step32_workflow, trade_window, mcx_control, as_of)
        _require(first == second, "SWING_PORTFOLIO_SOURCE_CHANGED")
    except (AttributeError, ValueError, OSError, KeyError, TypeError) as error:
        reason = str(error) if isinstance(error, _SourceUnavailable) else "SWING_PORTFOLIO_SOURCE_UNAVAILABLE"
        return SwingPortfolioProjection(
            False, "UNAVAILABLE", (reason,), as_of,
            coverage=dict(source_complete=False, valuation_complete=False,
                          monetary_total=None, monetary_basis="UNKNOWN"))
    select = lambda rows: tuple(row for row in rows if _matches(row, search, filters))
    selected = select(positions)
    return SwingPortfolioProjection(
        True, "AVAILABLE", (), as_of, selected, select(waiting), select(models),
        select(observations), select(closed), select(validation), _groups(selected),
        dict(source_complete=first[-1] == "AVAILABLE",
             position_sources_complete=True, current_plan_sources_complete=first[-1] == "AVAILABLE",
             valuation_complete=False,
             position_count=len(positions), filtered_position_count=len(selected),
             current_price_count=sum(row["current_price"] is not None for row in positions),
             quantity_known_count=sum(row["units"] is not None for row in positions),
             observation_count=len(observations), objective_model_count=len(models),
             validation_position_count=len(validation),
             advisory_currentness=first[-1],
             monetary_total=None, monetary_basis="UNKNOWN — NO COMMISSIONED PORTFOLIO TOTAL CONTRACT",
             observation_exposure=0, model_quantity="UNKNOWN",
             completeness=("VALID_EMPTY_POSITION_SOURCES" if not positions else
                           "COMPLETE_POSITION_SOURCES_PARTIAL_VALUATION")
                 + ("; CURRENT_ADVISORY_SUBSET_UNAVAILABLE" if first[-1] != "AVAILABLE" else "")),
    )
