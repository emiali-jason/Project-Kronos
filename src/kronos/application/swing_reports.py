"""Observational Swing historical evidence boundary (WO-16).

Independent V1 history does not require a prospective V2 counterpart. This
reader does not invoke the complete operational handoff or any reconciliation.
It validates retained relationships, and its immutable result is rechecked
before a response. No current run, Provider capability or market acquisition.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json

from kronos.application.swing_mcx_journal import mcx_journal_handoffs
from kronos.swing.v1.observation_research_ledger import _validate_kind
from kronos.swing.v1.observation_research_ledger_v2 import (
    PaperObservationLinkKind, _operational_handoff, with_completion_trading_dates,
)
from kronos.swing.v1.mcx_trade_plan import MCX_V1_ADVISORY_AUTHORITY


@dataclass(frozen=True, slots=True)
class SwingReportsSources:
    v1: tuple
    v2: tuple
    operational: tuple
    journal: object
    mcx_plans: tuple
    mcx_positions: tuple
    mcx_bindings: tuple
    mcx_lifecycle: object
    generation: int = 0
    mcx_owner_available: bool = False
    mcx_fill_facts: tuple = ()
    position_facts: tuple = ()


def _unique(items, identity):
    keys = tuple(identity(item) for item in items)
    if len(keys) != len(set(keys)):
        raise ValueError('SWING_REPORTS_AMBIGUOUS_SOURCE')


def read_swing_reports_sources(window, native_review, mcx_control, governed_date: date, completion_date_resolver=None):
    """Read validated immutable owners; caller checks retained owner health.

    Optional absent downstream records are disclosed, never fabricated. Retained
    orphaned or changed links are unavailable rather than silently ignored.
    """
    generation = window.reports_generation()
    v1 = window.observation_research_snapshot()
    ledger = window._observation_research_v2
    v2 = ledger.snapshot(_sources=v1)
    _unique(v1, lambda item: item.record.record_identity)
    _unique(v2, lambda item: item.record.record_identity)
    _unique(v1, lambda item: item.record.decision_identity)
    _unique(v2, lambda item: item.record.decision_identity)
    v1_ids = {item.record.record_identity for item in v1}
    if any(link.record_identity not in v1_ids for link in window._observation_research.store.load_links()):
        raise ValueError('SWING_REPORTS_ORPHAN_V1_LINK')
    v2_ids = {item.record.record_identity for item in v2}
    if any(link.record_identity not in v2_ids for link in ledger.store.load_links()):
        raise ValueError('SWING_REPORTS_ORPHAN_V2_LINK')
    for item in v1:
        for link in item.links:
            snapshot = item.source.snapshot
            if (link.native_run_identity != snapshot.native_run_identity
                    or link.canonical_instrument != snapshot.canonical_instrument
                    or link.native_assessment_sha256 != snapshot.native_assessment_sha256
                    or link.trade_plan_identity != snapshot.conventional_trade_plan_identity
                    or link.trade_plan_sha256 != snapshot.conventional_trade_plan_sha256):
                raise ValueError('SWING_REPORTS_V1_LINK_BINDING_INVALID')
            _validate_kind(link.kind, item.source, link.source_contract_identity,
                           link.source_contract_version, link.source_state,
                           link.sponsor_position_identity)
    for item in v2:
        for link in item.paper_links:
            track = ledger.paper.load_track(link.track_identity)
            ledger._validate_track(item.source, track)
            if link.kind is PaperObservationLinkKind.TRACK:
                expected = ledger._link_for_track(item.record, track)
            else:
                matches = tuple(event for event in ledger.paper.events(track.track_identity)
                                if event.event_identity == link.source_identity)
                if len(matches) != 1:
                    raise ValueError('SWING_REPORTS_PAPER_EVENT_UNAVAILABLE')
                expected = ledger._link_for_event(item.record, track, matches[0], kind=link.kind)
            if link != expected:
                raise ValueError('SWING_REPORTS_PAPER_LINK_BINDING_INVALID')
    state, positions = window.reports_position_facts()
    if positions:
        lifecycle = native_review._active_lifecycle.snapshot()
        current_positions = {item.position_id: item for item in lifecycle.positions}
        closures = {item.position_id: item for item in lifecycle.closures}
        for fact in positions.values():
            position = current_positions.get(fact.sponsor_position_identity)
            closure = closures.get(fact.sponsor_position_identity)
            retained = position if closure is None else closure
            if (retained is None or fact.source_integrity_sha256 != retained.integrity_hash
                    or fact.mode is not retained.mode):
                raise ValueError('SWING_REPORTS_POSITION_FACT_CHANGED')
    operational = tuple(_operational_handoff(
        item, None, governed_date, None, state,
        positions.get(item.record.decision_identity)) for item in v2)
    if completion_date_resolver is not None:
        operational = with_completion_trading_dates(operational, governed_date, completion_date_resolver)
    journal = native_review.reports_journal_snapshot()
    _unique(journal.records, lambda item: item.journal_record_id)
    plans, mcx, bindings, lifecycle, fill_facts = (), (), (), None, []
    if mcx_control is not None:
        lifecycle = mcx_control.lifecycle.snapshot()
        retained = mcx_control.lifecycle.store.load()
        for name,identity in (('positions','position_id'),('events','event_id'),
                              ('closures','closure_id')):
            if ({getattr(item,identity):item for item in getattr(retained,name)}
                    != {getattr(item,identity):item for item in getattr(lifecycle,name)}):
                raise ValueError('SWING_REPORTS_MCX_RETAINED_SOURCE_CHANGED')
        plans = tuple(mcx_control.plans.load(path)
                      for path in sorted(mcx_control.plans.root.glob('*/*/*.json')))
        _unique(plans, lambda item: item.trade_plan_id)
        if any(plan.authority != MCX_V1_ADVISORY_AUTHORITY for plan in plans):
            raise ValueError('SWING_REPORTS_MCX_AUTHORITY_UNSUPPORTED')
        mcx = mcx_journal_handoffs(mcx_control, governed_date)
        bindings = tuple(mcx_control.bound.bindings.load(item.sponsor_position_identity)
                         for item in mcx)
        if mcx_control.lifecycle.snapshot() != lifecycle:
            raise ValueError('SWING_REPORTS_MCX_CHANGED_DURING_READ')
        # The historical instrument contains no current-contract substitution.
        by_plan = {plan.trade_plan_id: plan for plan in plans}
        for row, binding in zip(mcx, bindings, strict=True):
            plan = by_plan[row.trade_plan_identity]
            if (binding.trade_plan_hash != plan.integrity_hash
                    or binding.decision_id != row.decision_identity
                    or binding.family is not plan.family
                    or binding.instrument.expiry.isoformat() != plan.expiry
                    or binding.instrument.name != plan.family.value):
                raise ValueError('SWING_REPORTS_MCX_BINDING_INVALID')
            position = next(item for item in lifecycle.positions if item.position_id == binding.position_id)
            for event in lifecycle.events:
                if event.position_id == position.position_id and (
                        event.trade_plan_id != plan.trade_plan_id
                        or event.trade_plan_hash != plan.integrity_hash
                        or event.instrument != plan.family.value
                        or event.decision_id != position.decision_id):
                    raise ValueError('SWING_REPORTS_MCX_EVENT_BINDING_INVALID')
            if position.mode.value == 'LIVE':
                entry = mcx_control.live_attestations.load(plan.trade_plan_id)
                capture = _retained_fill_capture(mcx_control, position, entry)
                mcx_control.broker_evidence.verify(capture, entry, position, binding)
                fill_facts.append((position.position_id, 'ENTRY', entry.integrity_sha256,
                                   entry.broker_evidence_sha256, entry.model_relation,
                                   entry.fill_price, entry.fill_at, entry.attested_at))
                closure = next((item for item in lifecycle.closures
                                if item.position_id == position.position_id), None)
                if closure is not None:
                    exit_fill = mcx_control.live_attestations.load_exit(position.position_id)
                    capture = _retained_fill_capture(mcx_control, position, exit_fill)
                    mcx_control.broker_evidence.verify_exit(capture, exit_fill, closure, binding)
                    fill_facts.append((position.position_id, 'EXIT', exit_fill.integrity_sha256,
                                       exit_fill.broker_evidence_sha256, exit_fill.model_relation,
                                       exit_fill.fill_price, exit_fill.fill_at, exit_fill.attested_at))

    if window.reports_generation() != generation:
        raise ValueError('SWING_REPORTS_GENERATION_CHANGED')
    return SwingReportsSources(v1, v2, operational, journal, plans, mcx, bindings, lifecycle,
                              generation, mcx_control is not None, tuple(fill_facts), tuple(sorted(positions.items())))


def _retained_fill_capture(control, position, attestation):
    from kronos.swing.v1.mcx_broker_fill_evidence import McxBrokerFillCapture, SCHEMA
    # Capture identity is checked by the existing store verifier. No broker
    # payload is returned to Reports and no current admission checks are applied.
    root = control.broker_evidence.root / position.position_id
    path = root / (attestation.broker_evidence_id + '.json')
    if any(parent.is_symlink() for parent in (control.broker_evidence.root, root, path)):
        raise ValueError('SWING_REPORTS_BROKER_EVIDENCE_INVALID')
    from kronos.swing.v1.mcx_broker_fill_evidence import MAX_BYTES
    with path.open('rb') as source:
        payload = source.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError('SWING_REPORTS_BROKER_EVIDENCE_INVALID')
    fields = json.loads(payload)
    if fields.pop('schema', None) != SCHEMA:
        raise ValueError('SWING_REPORTS_BROKER_EVIDENCE_INVALID')
    fields['fill_price'] = Decimal(fields['fill_price'])
    fields['fill_at'] = datetime.fromisoformat(fields['fill_at'])
    return McxBrokerFillCapture(**fields)
