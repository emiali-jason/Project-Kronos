"""Observational Journal projection of the existing MCX V1 record owners.

This is not an admission or reconciliation owner. Historical positions remain
readable without a current run, Provider capability or another acquisition.
"""
from datetime import date
from zoneinfo import ZoneInfo

from kronos.swing.v1.mcx_trade_plan import MCX_V1_ADVISORY_AUTHORITY
from kronos.swing.v1.observation_research_ledger_v2 import (
    ObservationOperationalHandoffV2, ObservationOperationalRoute,
    ObservationProduct, ObservationMode, WebSocketPresentationState,
)
from kronos.swing.v1.sponsor_observation_decision import SponsorActivationDisposition


def mcx_journal_handoffs(control, governed_date: date):
    """Join retained exact plan/position/contract; missing evidence is an error."""
    snapshot = control.lifecycle.snapshot()
    closures = {item.position_id: item for item in snapshot.closures}
    rows = []
    for position in snapshot.positions:
        if position.mcx_v1_contract_symbol is None:
            continue
        binding, bound_position = control.bound._bound_position(position.position_id)
        paths = tuple(control.plans.root.glob('*/*/' + position.trade_plan_id + '.json'))
        if len(paths) != 1 or bound_position != position:
            raise ValueError('MCX_JOURNAL_EXACT_PLAN_UNAVAILABLE')
        plan = control.plans.load(paths[0])
        if (plan.authority != MCX_V1_ADVISORY_AUTHORITY
                or (plan.trade_plan_id, plan.integrity_hash, plan.family.value,
                    plan.contract_symbol, plan.expiry, plan.native_direction)
                != (position.trade_plan_id, position.trade_plan_hash,
                    position.canonical_instrument, position.mcx_v1_contract_symbol,
                    binding.instrument.expiry.isoformat(), position.direction)
                or binding.instrument.trading_symbol != plan.contract_symbol):
            raise ValueError('MCX_JOURNAL_EXACT_CONTRACT_CHANGED')
        if (position.model_entry, position.stop, position.target) != (
                plan.entry, plan.stop, plan.canonical_target):
            raise ValueError('MCX_JOURNAL_PLAN_GEOMETRY_CHANGED')
        closure = closures.get(position.position_id)
        completed = None if closure is None else closure.exit_timestamp
        route = (ObservationOperationalRoute.ACTIVE if closure is None else
                 ObservationOperationalRoute.COMPLETED_CURRENT_TRADING_DAY
                 if completed.astimezone(ZoneInfo('Asia/Kolkata')).date() == governed_date
                 else ObservationOperationalRoute.HISTORICAL)
        monitoring, session, observation = control.native_review.journal_position_monitoring_evidence(position.position_id)
        latest = control.native_review._active_lifecycle_monitoring.latest_mcx_observation(position.position_id)
        tick = None if latest is None else latest[0]
        cmp = None if tick is None else tick.last_price
        sign = 1 if position.direction.value == 'LONG' else -1
        rows.append(ObservationOperationalHandoffV2(
            product=ObservationProduct.SWING, mode=ObservationMode(position.mode.value),
            instrument=plan.contract_symbol, direction=position.direction,
            decision_identity=position.decision_id, decision_timestamp=position.created_at,
            step31_severity=None, step31_warnings=(),
            risk_state='ADVISORY_MONETARY_FACTS_UNKNOWN',
            activation_disposition=SponsorActivationDisposition.ACTIVATED,
            sponsor_position_identity=position.position_id,
            sponsor_position_state=position.state.value,
            sponsor_position_prior_state=None if position.prior_state is None else position.prior_state.value,
            paper_track_identity=None, paper_track_state='NOT_APPLICABLE',
            paper_track_latest_event='NOT_APPLICABLE', paper_track_outcome='NOT_APPLICABLE',
            monitoring_state=monitoring, monitoring_session_identity=session,
            monitoring_observation_identity=observation,
            objective_state='UNAVAILABLE', objective_outcome='UNAVAILABLE',
            entry=position.actual_entry, exit=None if closure is None else closure.actual_exit,
            position_gross_pnl=None if closure is None else closure.gross_pnl,
            stop=position.stop, target=position.target, current_ltp=cmp,
            current_ltp_observed_at=None if tick is None else tick.observed_at,
            distance_to_target=None if cmp is None else sign*(position.target-cmp),
            distance_to_stop=None if cmp is None else sign*(cmp-position.stop),
            distance_to_target_state='UNAVAILABLE' if cmp is None else 'AVAILABLE',
            distance_to_stop_state='UNAVAILABLE' if cmp is None else 'AVAILABLE',
            monetary_pnl_state='UNKNOWN', completion_timestamp=completed,
            operational_route=route, websocket_state=WebSocketPresentationState.IDLE,
            native_run_identity=plan.native_run_identity,
            native_assessment_sha256=plan.assessment_sha256,
            trade_plan_identity=plan.trade_plan_id, trade_plan_sha256=plan.integrity_hash,
            activation_identity=position.mcx_activation_outcome_sha256,
            source_events=(('EXACT_CONTRACT', binding.integrity_sha256, '1'),
                           ('REVIEW_RECEIPT', plan.receipt_integrity_sha256, '1'),
                           ('V2', plan.promotion_integrity_sha256, '2')),
            source_versions=((plan.contract_identity, plan.contract_version),),
            exact_contract_expiry=plan.expiry, position_lots=position.lots,
            actual_entry_at=position.entry_timestamp,
        ))
    if control.lifecycle.snapshot() != snapshot:
        raise ValueError('MCX_JOURNAL_POSITION_CHANGED_DURING_READ')
    return tuple(rows)
