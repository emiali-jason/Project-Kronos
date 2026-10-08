"""WO-16 historical composition, separate from operational V2 completeness."""
from dataclasses import replace, asdict
from datetime import datetime
from zoneinfo import ZoneInfo
import json

from kronos.browser.reports import HistoricalReportRecord, ReportFamily, ReportsEvidenceUnavailable
from kronos.swing.v1.native_trade_journal import JournalRecordType

_IST = ZoneInfo('Asia/Kolkata')


def _facts(**values):
    return tuple((key, 'UNAVAILABLE' if value is None else str(value)) for key, value in values.items())


def _market(instrument):
    # Exact MCX family authority comes only from the dedicated retained plan.
    families = {'GOLDM', 'SILVERM', 'COPPER', 'CRUDEOIL', 'NATURALGAS'}
    unresolved = (instrument == 'MCX' or instrument in families
                  or (instrument.endswith('FUT') and any(instrument.startswith(family) for family in families)))
    return 'UNRESOLVED' if unresolved else 'NSE'


def _v1_record(item):
    record, source = item.record, item.source
    when = record.decision_timestamp
    objective = tuple(link for link in item.links
                      if link.kind.value == 'OBJECTIVE_MODEL_OUTCOME')
    if len(objective) > 1:
        raise ReportsEvidenceUnavailable('REPORTS_AMBIGUOUS_OBJECTIVE_OUTCOME')
    return HistoricalReportRecord(
        record.record_identity, record.decision_identity, when.astimezone(_IST).date(), when,
        record.canonical_instrument, source.snapshot.direction, ReportFamily.NONE,
        source.activation.disposition.value, None, None, None, source.snapshot.target,
        source.snapshot.stop, 'UNAVAILABLE', 'OPTIONAL_MISSING',
        'UNAVAILABLE' if not objective else objective[0].source_state, 'UNAVAILABLE' if source.snapshot.step31_severity is None else source.snapshot.step31_severity.value,
        source.snapshot.risk_state, source.activation.disposition.value,
        record.contract_identity, record.contract_version,
        market=_market(record.canonical_instrument),
        population_kind='SPONSOR_DECISION', completed=False,
        relationship_state='VALID_V1_ONLY_V2_ABSENT',
        source_facts=_facts(
            record_sha256=record.integrity_sha256, v1_contract=record.contract_identity,
            v1_version=record.contract_version, run=record.native_run_identity,
            assessment_sha256=record.native_assessment_sha256,
            snapshot=record.snapshot_identity, snapshot_sha256=record.snapshot_sha256,
            decision_sha256=record.decision_sha256, activation=record.activation_identity,
            position=source.activation.sponsor_position_identity,
            activation_sha256=record.activation_sha256, choice=record.choice.value,
            visual_evidence=source.snapshot.visual_evidence_identity,
            visual_evidence_sha256=source.snapshot.visual_evidence_sha256,
            step31_observation=source.snapshot.step31_observation_identity,
            step31_observation_sha256=source.snapshot.step31_observation_sha256,
            source_timestamp=when.isoformat(), timestamp_kind='DECISION',
            v2='OPTIONAL_MISSING', track='OPTIONAL_MISSING',
            relationships=json.dumps([(link.kind.value, link.source_record_identity,
                                       link.source_integrity_sha256, link.source_contract_identity,
                                       link.source_contract_version, link.source_state,
                                       link.source_timestamp.isoformat()) for link in item.links]),
        ),
    )


def _operational_record(row, *, primary=None):
    track = row.paper_track_identity is not None
    position = row.sponsor_position_identity is not None and row.sponsor_position_state != 'UNAVAILABLE'
    complete = row.completion_timestamp is not None
    family = (ReportFamily.PAPER_OBSERVATION if track else ReportFamily(row.mode.value)
              if position else ReportFamily.NONE)
    when = row.completion_timestamp or row.decision_timestamp
    return HistoricalReportRecord(
        primary or row.sponsor_position_identity or row.paper_track_identity or row.decision_identity,
        row.decision_identity, when.astimezone(_IST).date(), when, row.instrument,
        row.direction, family,
        (row.paper_track_state if track else row.sponsor_position_state if position
         else row.activation_disposition.value),
        None if track else row.entry, None if track else row.exit, None if track else row.position_gross_pnl,
        row.target, row.stop,
        ('NOT_APPLICABLE' if track else 'CLOSED' if complete and position
         else row.sponsor_position_state if position else 'OPTIONAL_MISSING'),
        row.paper_track_outcome if track else 'OPTIONAL_MISSING', row.objective_outcome,
        'UNAVAILABLE' if row.step31_severity is None else row.step31_severity.value,
        row.risk_state, row.activation_disposition.value,
        row.projection_contract_identity, row.projection_contract_version,
        paper_history_representation=row.paper_history_representation,
        paper_raw_detail_availability=row.paper_raw_detail_availability,
        paper_first_observation_at=row.paper_first_observation_at,
        paper_last_observation_at=row.paper_last_observation_at,
        paper_fact_count=row.paper_fact_count, paper_source_count=row.paper_source_count,
        paper_consolidation_identity=row.paper_consolidation_identity,
        paper_history_detail_reason=row.paper_history_detail_reason,
        market=_market(row.instrument), population_kind='SPONSOR_DECISION' if primary else 'POSITION',
        completed=complete,
        source_facts=_facts(run=row.native_run_identity, assessment_sha256=row.native_assessment_sha256,
                            plan=row.trade_plan_identity, plan_sha256=row.trade_plan_sha256,
                            position=row.sponsor_position_identity, track=row.paper_track_identity,
                            operational_route=row.operational_route.value,
                            observation_entry_reference=row.entry if track else None,
                            position_state=row.sponsor_position_state,
                            prior_state=row.sponsor_position_prior_state,
                            timestamp_kind='COMPLETION' if complete else 'DECISION',
                            actual_entry_at=row.actual_entry_at.isoformat() if row.actual_entry_at else None,
                            source_events=json.dumps(row.source_events),
                            source_versions=json.dumps(row.source_versions)),
    )


def compose_swing_reports(sources):
    rows = {}
    by_decision = {}
    by_position = {}
    v2 = {item.record.decision_identity: item for item in sources.v2}
    op = {item.decision_identity: item for item in sources.operational}
    for source in sources.v1:
        base = _v1_record(source)
        decision = base.decision_identity
        position = dict(sources.position_facts).get(decision)
        if position is not None:
            if (position.sponsor_position_identity != source.source.activation.sponsor_position_identity
                    or position.mode is not source.source.decision.choice):
                raise ReportsEvidenceUnavailable('REPORTS_V1_POSITION_BINDING_INVALID')
            when = position.completion_timestamp or source.record.decision_timestamp
            base = replace(base, family=ReportFamily(position.mode.value), status=position.state,
                           entry=position.actual_entry, exit=position.actual_exit, pnl=position.gross_pnl,
                           relevant_timestamp=when, record_date=when.astimezone(_IST).date(),
                           completed=position.completion_timestamp is not None,
                           sponsor_position_outcome=position.state,
                           source_facts=base.source_facts+_facts(
                               position=position.sponsor_position_identity,
                               position_sha256=position.source_integrity_sha256,
                               timestamp_kind='COMPLETION' if position.completion_timestamp else 'DECISION'))
        if decision in op:
            linked = _operational_record(op[decision], primary=base.record_identity)
            v2_source = v2[decision]
            base = replace(linked, market=base.market,
                           relationship_state='VALID_V2',
                           source_facts=base.source_facts + linked.source_facts + _facts(
                               v2=v2_source.record.record_identity,
                               v2_sha256=v2_source.record.integrity_sha256,
                               v2_contract=v2_source.record.contract_identity,
                               v2_version=v2_source.record.contract_version,
                               paper_links=json.dumps([(link.link_identity, link.integrity_sha256,
                                                        link.source_identity, link.source_integrity_sha256)
                                                       for link in v2_source.paper_links])))
        rows[base.record_identity] = base
        by_decision[decision] = base.record_identity
        sponsor_id = source.source.activation.existing_sponsor_decision_identity
        if sponsor_id:
            if sponsor_id in by_decision:
                raise ReportsEvidenceUnavailable('REPORTS_AMBIGUOUS_SPONSOR_RELATIONSHIP')
            by_decision[sponsor_id] = base.record_identity
        pos = source.source.activation.sponsor_position_identity
        if pos:
            if pos in by_position:
                raise ReportsEvidenceUnavailable('REPORTS_AMBIGUOUS_POSITION_RELATIONSHIP')
            by_position[pos] = base.record_identity
    seen_step33 = set()
    for item in sources.journal.records:
        key = item.sponsor_position_id or item.sponsor_decision_id
        if key in seen_step33:
            raise ReportsEvidenceUnavailable('REPORTS_AMBIGUOUS_STEP33_RELATIONSHIP')
        seen_step33.add(key)
        ignored = item.record_type is JournalRecordType.IGNORED_OPPORTUNITY
        facts = _facts(step33=item.journal_record_id, step33_sha256=item.integrity_hash,
                       step33_contract=item.contract_identity, step33_version=item.contract_version,
                       run=item.native_run_identity, assessment_sha256=item.native_assessment_sha256,
                       plan=item.trade_plan_id, plan_sha256=item.trade_plan_sha256,
                       sponsor_decision=item.sponsor_decision_id,
                       sponsor_decision_sha256=item.sponsor_decision_sha256,
                       position=item.sponsor_position_id, position_sha256=item.sponsor_position_sha256,
                       closure=item.trade_closure_id, closure_sha256=item.trade_closure_sha256,
                       lots=item.lots, underlying_quantity=item.underlying_quantity,
                       accounting_basis=item.accounting_basis,
                       lifecycle_events=json.dumps(list(zip(item.lifecycle_event_ids, item.lifecycle_event_hashes))),
                       timestamp_kind='DECISION' if ignored else 'COMPLETION')
        when = item.exit_timestamp or item.created_at
        candidate = HistoricalReportRecord(
            item.journal_record_id, item.sponsor_decision_id, when.astimezone(_IST).date(), when,
            item.instrument, item.direction,
            ReportFamily.DO_NOTHING if ignored else ReportFamily(item.mode.value),
            'IGNORED_OPPORTUNITY' if ignored else 'EXITED',
            item.actual_entry, item.actual_exit, item.gross_pnl, item.model_target, item.model_stop,
            'NOT_APPLICABLE' if ignored else item.exit_reason or item.outcome.value,
            'NOT_APPLICABLE', 'UNAVAILABLE', 'UNAVAILABLE', 'UNAVAILABLE',
            'NOT_APPLICABLE' if ignored else 'ACTIVATED', item.contract_identity, item.contract_version,
            market=_market(item.instrument), population_kind='STEP33_'+item.record_type.value,
            completed=not ignored, source_facts=facts)
        linked_id = by_decision.get(item.sponsor_decision_id)
        if item.sponsor_position_id in by_position:
            pos_link = by_position[item.sponsor_position_id]
            if linked_id is not None and pos_link != linked_id:
                raise ReportsEvidenceUnavailable('REPORTS_CONFLICTING_POSITION_RELATIONSHIP')
            linked_id = pos_link
        if linked_id is not None:
            base = rows[linked_id]
            src = dict(base.source_facts)
            if (base.instrument != item.instrument or base.direction is not item.direction
                    or src.get('run') != item.native_run_identity
                    or src.get('assessment_sha256') != item.native_assessment_sha256
                    or (src.get('plan') not in (None, 'UNAVAILABLE', item.trade_plan_id))
                    or (src.get('plan_sha256') not in (None, 'UNAVAILABLE', item.trade_plan_sha256))
                    or (not ignored and src.get('position') != item.sponsor_position_id)
                    or (base.exit is not None and base.exit != item.actual_exit)):
                raise ReportsEvidenceUnavailable('REPORTS_STEP33_BINDING_INVALID')
            candidate = replace(candidate, record_identity=base.record_identity,
                                decision_identity=base.decision_identity,
                                population_kind=base.population_kind,
                                relationship_state=base.relationship_state,
                                step31_severity=base.step31_severity, risk_state=base.risk_state,
                                objective_outcome=base.objective_outcome,
                                source_facts=base.source_facts+facts)
        if candidate.record_identity in rows and linked_id is None:
            raise ReportsEvidenceUnavailable('REPORTS_DUPLICATE_PRIMARY')
        rows[candidate.record_identity] = candidate
    plan_positions = {}
    for op_row, binding in zip(sources.mcx_positions, sources.mcx_bindings, strict=True):
        plan = next(plan for plan in sources.mcx_plans if plan.trade_plan_id == op_row.trade_plan_identity)
        row = _operational_record(op_row)
        position = next(item for item in sources.mcx_lifecycle.positions
                        if item.position_id == op_row.sponsor_position_identity)
        closure = next((item for item in sources.mcx_lifecycle.closures
                        if item.position_id == position.position_id), None)
        plan_positions.setdefault(plan.trade_plan_id, []).append(position.position_id)
        quantity = getattr(position, 'mcx_quantity', None)
        row = replace(row, market='MCX', contract_family=plan.family.value,
                      source_facts=row.source_facts + _facts(
                          plan_contract=plan.contract_identity, plan_version=plan.contract_version,
                          plan_sha256=plan.integrity_hash, receipt_sha256=plan.receipt_integrity_sha256,
                          v2_sha256=plan.promotion_integrity_sha256,
                          selected_contract=plan.contract_symbol, expiry=plan.expiry,
                          provider_record_identity=plan.provider_record_identity,
                          provider_snapshot=plan.provider_snapshot_identity,
                          normalized_instrument_sha256=plan.normalized_instrument_sha256,
                          binding_sha256=binding.integrity_sha256,
                          position_sha256=position.integrity_hash, lots=position.lots,
                          quantity='UNKNOWN' if quantity is None else json.dumps({
                              key: str(value) for key,value in asdict(quantity).items()}),
                          monetary_multiplier='UNKNOWN' if quantity is None else quantity.rupees_per_price_point_per_lot,
                          entry_at=position.entry_timestamp,
                          last_observation_id=position.last_observation_id,
                          last_observed_at=position.last_observed_at,
                          activation_outcome_sha256=position.mcx_activation_outcome_sha256,
                          lifecycle_events=json.dumps([(event.event_id, event.integrity_hash,
                                                        event.event_type.value,
                                                        event.event_timestamp.isoformat())
                                                       for event in sources.mcx_lifecycle.events
                                                       if event.position_id == position.position_id]),
                          closure_sha256=None if closure is None else closure.integrity_hash,
                          closure_at=None if closure is None else closure.exit_timestamp,
                          cmp_observations=json.dumps(_cmp_facts(sources.mcx_lifecycle, position.position_id)),
                          live_broker_evidence_origin='SPONSOR_SUBMITTED_UNVERIFIED',
                          live_attestations=json.dumps([(kind, digest, broker_hash, relation, str(price),
                                                          fill_at.isoformat(), attested_at.isoformat())
                                                         for pos,kind,digest,broker_hash,relation,price,fill_at,attested_at
                                                         in sources.mcx_fill_facts if pos==position.position_id]),
                          costs='UNKNOWN', net_pnl='UNKNOWN',
                      ))
        # A Step-33 counterpart is an append-only relationship, not a second
        # position. Join only its exact retained position and plan identities.
        linked = tuple(existing for existing in rows.values()
                       if dict(existing.source_facts).get('position') == position.position_id)
        if len(linked) > 1:
            raise ReportsEvidenceUnavailable('REPORTS_DUPLICATE_MCX_POSITION')
        if linked:
            existing = linked[0]
            facts = dict(existing.source_facts)
            if (facts.get('run') != plan.native_run_identity
                    or facts.get('plan') != plan.trade_plan_id
                    or facts.get('plan_sha256') != plan.integrity_hash
                    or existing.direction is not plan.native_direction
                    or existing.entry != row.entry or existing.exit != row.exit):
                raise ReportsEvidenceUnavailable('REPORTS_MCX_STEP33_BINDING_INVALID')
            row = replace(row, record_identity=existing.record_identity,
                          source_facts=existing.source_facts + row.source_facts)
        elif row.record_identity in rows:
            raise ReportsEvidenceUnavailable('REPORTS_DUPLICATE_MCX_POSITION')
        rows[row.record_identity] = row
    for plan in sources.mcx_plans:
        if plan.trade_plan_id in plan_positions:
            continue
        when = plan.created_at
        row = HistoricalReportRecord(
            plan.trade_plan_id, 'NOT_APPLICABLE', when.astimezone(_IST).date(), when,
            plan.contract_symbol, plan.native_direction, ReportFamily.NONE, 'ADVISORY_PLAN_ONLY',
            None, None, None, plan.canonical_target, plan.stop, 'OPTIONAL_MISSING',
            'NOT_APPLICABLE', 'NOT_APPLICABLE', 'UNAVAILABLE', 'ADVISORY_MONETARY_FACTS_UNKNOWN',
            'NOT_ADMITTED', plan.contract_identity, plan.contract_version,
            market='MCX', contract_family=plan.family.value, population_kind='ADVISORY_PLAN', completed=False,
            source_facts=_facts(plan=plan.trade_plan_id, plan_sha256=plan.integrity_hash,
                               run=plan.native_run_identity, assessment_sha256=plan.assessment_sha256,
                               receipt_sha256=plan.receipt_integrity_sha256,
                               v2_sha256=plan.promotion_integrity_sha256,
                               selected_contract=plan.contract_symbol, expiry=plan.expiry,
                               advisory_entry_threshold=plan.entry,
                               provider_record_identity=plan.provider_record_identity,
                               provider_snapshot=plan.provider_snapshot_identity,
                               timestamp_kind='PLAN_CREATED'))
        if row.record_identity in rows:
            raise ReportsEvidenceUnavailable('REPORTS_DUPLICATE_PRIMARY')
        rows[row.record_identity] = row
    coverage = (
        ('V1', 'VALID_EMPTY' if not sources.v1 else 'VALID_HISTORY', len(sources.v1)),
        ('V2', 'VALID_EMPTY' if not sources.v2 else 'VALID_HISTORY', len(sources.v2)),
        ('V1_ONLY_V2_ABSENT', 'INDEPENDENT_HISTORY_NOT_OPERATIONAL_COMPLETENESS',
         len(sources.v1)-len(sources.v2)),
        ('STEP33', 'VALID_EMPTY' if not sources.journal.records else 'VALID_HISTORY', len(sources.journal.records)),
        ('MCX_PLANS', ('OWNER_NOT_INSTALLED' if not sources.mcx_owner_available else 'VALID_EMPTY' if not sources.mcx_plans else 'VALID_HISTORY'), len(sources.mcx_plans)),
        ('MCX_POSITIONS', ('OWNER_NOT_INSTALLED' if not sources.mcx_owner_available else 'VALID_EMPTY' if not sources.mcx_positions else 'VALID_HISTORY'), len(sources.mcx_positions)),
        ('UNRESOLVED_MCX', 'UNRESOLVED_FAMILY_AND_FUTURE', sum(row.market=='UNRESOLVED' for row in rows.values())),
    )
    return tuple(rows.values()), coverage


def _cmp_facts(lifecycle, position_id):
    """Allowlisted factual quote provenance; missing fields remain unavailable.

    V1 capture stores the source, physical connection and actual observed and
    received times in its lifecycle event. No free-form Provider context leaks.
    """
    values = []
    for event in lifecycle.events:
        if event.position_id != position_id:
            continue
        provenance = event.provider_provenance
        cmp_id = next((value for value in provenance if value.startswith('MCX-CMP-')), None)
        if cmp_id is None or 'KITE_CONNECT_WEBSOCKET' not in provenance:
            continue
        if event.event_type.value == 'PAPER_ENTRY_CAPTURED':
            source_index = provenance.index('KITE_CONNECT_WEBSOCKET')
            times = provenance[source_index+3:source_index+5]
        else:
            cmp_index = provenance.index(cmp_id)
            times = provenance[cmp_index+3:cmp_index+5]
        if len(times) != 2:
            continue
        try:
            observed,received = tuple(datetime.fromisoformat(value) for value in times)
        except ValueError:
            continue  # Retained reference alone is not a timestamped price source.
        if any(value.tzinfo is None for value in (observed,received)):
            continue
        values.append((event.event_id,event.integrity_hash,event.event_type.value,
                       cmp_id,'KITE_CONNECT_WEBSOCKET',str(event.observed_price),
                       observed.isoformat(),received.isoformat()))
    return values
