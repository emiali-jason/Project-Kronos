"""Held MCX V1 completed-hour signal issuer; no Browser admission or broker API.

The isolated continuity adapter is deliberately incapable of commissioning a
production route. It proves the approved close-cross arithmetic and fences an
exact current read set before retaining an immutable outcome.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable
from kronos.market.schedule import MarketSchedule

from kronos.swing.v1.mcx_kr380_issuer import (
    FIXTURE_ORIGIN, McxContinuityProof, McxCurrentAuthority,
    McxKr380Rejected, McxOneHourCandle, _digest,
)
from kronos.swing.v1.mcx_trade_plan import (
    MCX_V1_ADVISORY_AUTHORITY, McxTradePlanRecord,
)
from kronos.swing.v1.step32 import RiskApproval, RiskState
from kronos.swing.v1.mcx_v1_advisory import (
    ADVISORY_RULE_ID, LocalMcxV1AdvisoryStore, McxAdvisoryState,
    McxV1AdvisoryOutcome,
)


@dataclass(frozen=True, slots=True)
class McxV1SignalReadSet:
    plan: McxTradePlanRecord
    risk: RiskApproval
    previous: McxOneHourCandle
    current: McxOneHourCandle
    continuity: McxContinuityProof
    authority: McxCurrentAuthority
    schedule: MarketSchedule
    monitoring_binding_identity: str
    tick_size: Decimal
    origin: str = FIXTURE_ORIGIN


def validate_v1_signal(read: McxV1SignalReadSet,
                       *, evaluated_at: datetime) -> McxV1AdvisoryOutcome:
    if (type(read) is not McxV1SignalReadSet
            or read.origin != FIXTURE_ORIGIN
            or type(read.plan) is not McxTradePlanRecord
            or read.plan.authority != MCX_V1_ADVISORY_AUTHORITY
            or type(read.risk) is not RiskApproval
            or type(read.previous) is not McxOneHourCandle
            or type(read.current) is not McxOneHourCandle
            or type(read.continuity) is not McxContinuityProof
            or type(read.authority) is not McxCurrentAuthority
            or type(read.schedule) is not MarketSchedule
            or not read.monitoring_binding_identity
            or type(read.tick_size) is not Decimal
            or not read.tick_size.is_finite() or read.tick_size <= 0
            or evaluated_at.tzinfo is None):
        raise McxKr380Rejected("MCX_V1_SIGNAL_READ_SET_INVALID")
    plan, p, c, continuity, authority = (
        read.plan, read.previous, read.current, read.continuity, read.authority)
    if (read.risk.state is RiskState.REJECTED
            or read.risk.constraints.present
            or read.risk.candidate_id != plan.trade_plan_id
            or read.risk.candidate_digest != plan.integrity_hash
            or read.risk.run_id != plan.native_run_identity
            or (read.risk.valid_until is not None
                and evaluated_at >= read.risk.valid_until)
            or (authority.run_identity, authority.contract_symbol,
                authority.expiry, authority.selection_sha256,
                authority.receipt_sha256, authority.v2_sha256)
               != (plan.native_run_identity, plan.contract_symbol,
                   plan.expiry, plan.selection_sha256,
                   plan.receipt_integrity_sha256,
                   plan.promotion_integrity_sha256)
            or (p.run_identity, p.family, p.trading_symbol, p.expiry,
                p.provider_token, p.session_identity)
               != (c.run_identity, c.family, c.trading_symbol, c.expiry,
                   c.provider_token, c.session_identity)
            or (p.run_identity, p.family, p.trading_symbol, p.expiry)
               != (plan.native_run_identity, plan.family,
                   plan.contract_symbol, plan.expiry)
            or p.provider_token != authority.provider_token
            or p.session_identity != plan.expiry_session_identity
            or read.schedule.exchange != "MCX"
            or read.schedule.session_identity != p.session_identity
            or read.schedule.window_at(p.opened_at) is None
            or read.schedule.window_at(p.closed_at - timedelta(microseconds=1)) is None
            or read.schedule.window_at(c.opened_at) is None
            or read.schedule.window_at(c.closed_at - timedelta(microseconds=1)) is None
            or p.source_sha256 != plan.completed_one_hour_sha256
            or p.closed_at != plan.observation_boundary
            or not p.confirmed_complete or not c.confirmed_complete
            or p.closed_at != c.opened_at
            or p.closed_at - p.opened_at != timedelta(hours=1)
            or c.closed_at - c.opened_at != timedelta(hours=1)
            or read.schedule.window_at(p.opened_at) != read.schedule.window_at(c.closed_at - timedelta(microseconds=1))
            or p.source_sequence >= c.source_sequence
            or (continuity.previous_identity, continuity.previous_revision,
                continuity.previous_sha256, continuity.current_identity,
                continuity.current_revision, continuity.current_sha256,
                continuity.session_identity)
               != (p.candle_identity, p.revision, p.source_sha256,
                   c.candle_identity, c.revision, c.source_sha256,
                   c.session_identity)
            or not all((continuity.intervals_consecutive,
                        continuity.no_missing_interval))
            or evaluated_at < c.closed_at
            or evaluated_at >= plan.entry_eligibility_boundary
            or any(value / read.tick_size !=
                   (value / read.tick_size).to_integral_value()
                   for value in (plan.entry, plan.stop, plan.canonical_target,
                                 p.open, p.close, c.open, c.close))):
        raise McxKr380Rejected("MCX_V1_SIGNAL_BINDING_OR_CONTINUITY_INVALID")
    if plan.native_direction.value == "LONG":
        crossed = p.close < plan.entry and c.open < plan.entry and c.close >= plan.entry
        state = McxAdvisoryState.LONG_CONFIRMED
    else:
        crossed = p.close > plan.entry and c.open > plan.entry and c.close <= plan.entry
        state = McxAdvisoryState.SHORT_CONFIRMED
    if not crossed:
        raise McxKr380Rejected("MCX_V1_COMPLETED_CLOSE_NOT_TRIGGERED")
    values = dict(
        advisory_id="MCX-ADVISORY-" + _digest(read),
        contract_symbol=plan.contract_symbol, expiry=plan.expiry,
        provider_token=authority.provider_token,
        session_identity=c.session_identity,
        native_run_identity=plan.native_run_identity,
        canonical_instrument=plan.family.value,
        direction=plan.native_direction.value,
        kr370_source_identity=plan.readiness_record_identity,
        trade_plan_id=plan.trade_plan_id,
        trade_plan_sha256=plan.integrity_hash,
        risk_result_id=read.risk.risk_result_id,
        monitoring_binding_id=read.monitoring_binding_identity,
        observation_boundary=c.closed_at,
        source_observation_ids=(p.candle_identity, c.candle_identity),
        source_sequence=(p.source_sequence, c.source_sequence),
        state=state,
        occurred_at=c.closed_at,
        confirmed_at=evaluated_at,
        provenance=(ADVISORY_RULE_ID, plan.integrity_hash, plan.selection_sha256,
                    plan.receipt_integrity_sha256,
                    plan.promotion_integrity_sha256,
                    continuity.source_identity, continuity.source_sha256,
                    p.source_sha256, c.source_sha256,
                    "ISOLATED_NO_PRODUCTION_AUTHORITY"),
    )
    return McxV1AdvisoryOutcome.create(**values)


def issue_v1_isolated_signal(
    current: Callable[[], McxV1SignalReadSet], *, evaluated_at: datetime,
    store: LocalMcxV1AdvisoryStore,
    commit_guard: Callable[[], AbstractContextManager[object]],
    guarded_recheck: Callable[[str], bool],
) -> McxV1AdvisoryOutcome:
    if (not callable(current) or type(store) is not LocalMcxV1AdvisoryStore
            or not callable(commit_guard) or not callable(guarded_recheck)):
        raise McxKr380Rejected("MCX_V1_SIGNAL_ISSUER_INVALID")
    first = current()
    outcome = validate_v1_signal(first, evaluated_at=evaluated_at)
    second = current()
    if first != second or outcome != validate_v1_signal(second,
                                                        evaluated_at=evaluated_at):
        raise McxKr380Rejected("MCX_V1_SIGNAL_READ_SET_CHANGED")
    with commit_guard():
        if guarded_recheck(_digest(first)) is not True:
            raise McxKr380Rejected("MCX_V1_SIGNAL_COMMIT_FENCE_CHANGED")
        retained = store.load_for_plan(first.plan.trade_plan_id)
        if retained is not None:
            if retained != outcome:
                raise McxKr380Rejected("MCX_V1_SIGNAL_REPLAY_CONFLICT")
            return retained
        store.retain_current(outcome)
        return outcome
