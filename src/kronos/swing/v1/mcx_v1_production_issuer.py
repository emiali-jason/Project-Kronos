"""Exact-contract completed-hour ADVISORY; never a P32-002 trade outcome.

Consecutive hourly observations establish candle continuity only. Intrabar
trade continuity is UNVERIFIED. Composition retains the commissioning hold.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Callable

from kronos.application.swing_mcx_evidence import read_retained_mcx_master_match
from kronos.market.schedule import MarketSchedule
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle, HistoricalCandleRequest, HistoricalInterval,
)
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore
from kronos.provider.kite.marketdata.kite_market_data_provider import KiteMarketDataProvider
from kronos.swing.v1.mcx_contract_profile import (
    _digest as mcx_digest, mcx_lineage_matches_completed_facts,
)
from kronos.swing.v1.mcx_kr380_issuer import McxCurrentAuthority, McxKr380Rejected
from kronos.swing.v1.mcx_step31_construction import McxOwnerSelectedHandoff
from kronos.swing.v1.mcx_trade_plan import MCX_V1_ADVISORY_AUTHORITY, McxTradePlanRecord
from kronos.swing.v1.mtf_facts import FactualTimeframe, MtfFactEvidenceStore
from kronos.swing.v1.step32 import RiskApproval, RiskState
from kronos.swing.v1.mcx_v1_advisory import (
    ADVISORY_RULE_ID, LocalMcxV1AdvisoryStore, McxAdvisoryState,
    McxV1AdvisoryOutcome,
)


_SOURCE = "KITE_AUTHENTICATED_HISTORICAL_1H"


def _positive(value: object) -> bool:
    return type(value) is Decimal and value.is_finite() and value > 0


def _read_completed_source(
    plan: McxTradePlanRecord, instrument: InstrumentRecord,
    provider: KiteMarketDataProvider, mtf: MtfFactEvidenceStore,
    schedule: MarketSchedule, *, evaluated_at: datetime,
) -> tuple[object, ...]:
    snapshot = mtf.load(plan.native_run_identity)
    matches = tuple(item for item in snapshot.instruments
                    if item.canonical_instrument == plan.family.value)
    if (snapshot.run_identity != plan.native_run_identity
            or len(matches) != 1 or matches[0].mcx_request_lineage is None):
        raise McxKr380Rejected("MCX_V1_RETAINED_1H_UNAVAILABLE")
    subject = matches[0]
    lineage = subject.mcx_request_lineage
    anchor = subject.fact(FactualTimeframe.ONE_HOUR)
    if not mcx_lineage_matches_completed_facts(
        lineage, run_identity=plan.native_run_identity,
        canonical_instrument=plan.family.value, current_instrument=instrument,
        completed_facts=(subject.fact(FactualTimeframe.DAILY),
                         subject.fact(FactualTimeframe.FOUR_HOUR), anchor),
        completed_series=subject.completed_series,
    ):
        raise McxKr380Rejected("MCX_V1_RETAINED_MTF_CHANGED")
    if (lineage.trading_symbol != instrument.trading_symbol
            or lineage.expiry != instrument.expiry.isoformat()
            or lineage.normalized_instrument_sha256 != mcx_digest(asdict(instrument))
            or lineage.completed_1h_sha256 != plan.completed_one_hour_sha256
            or mcx_digest(asdict(anchor)) != plan.completed_one_hour_sha256
            or anchor.observation_boundary != plan.observation_boundary
            or anchor.session_identity != schedule.session_identity
            or plan.expiry_session_identity != schedule.session_identity
            or anchor.source_timestamp + timedelta(hours=1) != anchor.observation_boundary
            or evaluated_at < anchor.observation_boundary + timedelta(hours=1)):
        raise McxKr380Rejected("MCX_V1_RETAINED_1H_CHANGED")
    start = anchor.source_timestamp
    window = schedule.window_at(start)
    if (window is None
            or schedule.window_at(anchor.observation_boundary) != window
            or schedule.window_at(
                anchor.observation_boundary + timedelta(hours=1)
                - timedelta(microseconds=1)) != window):
        raise McxKr380Rejected("MCX_V1_COMPLETED_SESSION_UNAVAILABLE")
    # Advance only by whole completed hours from the retained exact-run anchor.
    # The first call sees the original pair; later calls may see further pairs
    # in the same eligible session while the immutable plan remains current.
    latest = min(evaluated_at, plan.entry_eligibility_boundary,
                 window.window_close)
    completed_hours = int((latest - start) // timedelta(hours=1))
    if completed_hours < 2:
        raise McxKr380Rejected("MCX_V1_COMPLETED_SESSION_UNAVAILABLE")
    end = start + timedelta(hours=completed_hours)
    hourly_response = provider.historical_candles(HistoricalCandleRequest(
        instrument, start, end, HistoricalInterval.SIXTY_MINUTE))
    hours = tuple(item for item in hourly_response if start <= item.timestamp < end)
    expected = tuple(start + timedelta(hours=index)
                     for index in range(completed_hours))
    if (type(hours) is not tuple or len(hours) != completed_hours
            or tuple(item.timestamp for item in hours) != expected
            or any(type(item) is not HistoricalCandle for item in hours)
            or any(getattr(hours[0], field) != getattr(anchor, field)
                   for field in ("open", "high", "low", "close", "volume"))):
        raise McxKr380Rejected("MCX_V1_HOURLY_SOURCE_CHANGED")
    if any(schedule.window_at(item.timestamp) != window
           or schedule.window_at(item.timestamp + timedelta(hours=1)
                                 - timedelta(microseconds=1)) != window
           for item in hours):
        raise McxKr380Rejected("MCX_V1_SESSION_BREAK")
    # No claim about trades inside these bars. The close-cross predicate below
    # independently rejects an opening gap across Entry.
    interval_sha = mcx_digest((start.isoformat(), end.isoformat(),
                              schedule.session_identity,
                              "ELIGIBLE_CONSECUTIVE_COMPLETED_1H"))
    return (mcx_digest(asdict(snapshot)), mcx_digest([asdict(item) for item in hours]),
            interval_sha, *hours)


def issue_v1_production_signal(
    *, plan: McxTradePlanRecord, risk: RiskApproval,
    instrument: InstrumentRecord, master: ProviderInstrumentSnapshotStore,
    provider: KiteMarketDataProvider, mtf: MtfFactEvidenceStore,
    schedule: MarketSchedule, owner: McxOwnerSelectedHandoff,
    current_plan: Callable[[], McxTradePlanRecord],
    monitoring_binding_identity: str, evaluated_at: datetime,
    store: LocalMcxV1AdvisoryStore,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> McxV1AdvisoryOutcome:
    """Issue once after two identical authenticated reads and final owner fence.

    The retained master supplies exact historical token identity only. It is
    never treated as a fresh master, specification, monetary or broker proof.
    """
    if (type(plan) is not McxTradePlanRecord
            or plan.authority != MCX_V1_ADVISORY_AUTHORITY
            or type(risk) is not RiskApproval
            or type(instrument) is not InstrumentRecord
            or type(master) is not ProviderInstrumentSnapshotStore
            or type(provider) is not KiteMarketDataProvider
            or type(mtf) is not MtfFactEvidenceStore
            or type(schedule) is not MarketSchedule
            or type(owner) is not McxOwnerSelectedHandoff
            or type(store) is not LocalMcxV1AdvisoryStore
            or not callable(current_plan)
            or not callable(clock)
            or not monitoring_binding_identity
            or evaluated_at.tzinfo is None or not _positive(plan.entry)):
        raise McxKr380Rejected("MCX_V1_PRODUCTION_ISSUER_INVALID")
    if (instrument.provider != "KITE" or instrument.exchange != "MCX"
            or instrument.segment != "MCX-FUT" or instrument.instrument_type != "FUT"
            or instrument.expiry is None
            or not _positive(instrument.tick_size)
            or instrument.name != plan.family.value
            or plan.normalized_instrument_sha256 != mcx_digest(asdict(instrument))
            or (instrument.trading_symbol, instrument.expiry.isoformat())
               != (plan.contract_symbol, plan.expiry)
            or schedule.exchange != "MCX"
            or evaluated_at >= plan.entry_eligibility_boundary
            or evaluated_at.date() > instrument.expiry
            or risk.state is RiskState.REJECTED or risk.constraints.present
            or (risk.candidate_id, risk.candidate_digest, risk.run_id)
               != (plan.trade_plan_id, plan.integrity_hash,
                   plan.native_run_identity)
            or (risk.valid_until is not None and evaluated_at >= risk.valid_until)):
        raise McxKr380Rejected("MCX_V1_PRODUCTION_BINDING_INVALID")
    match = read_retained_mcx_master_match(
        master, snapshot_identity=plan.provider_snapshot_identity,
        record_identity=plan.provider_record_identity, family=plan.family,
        normalized_contract=instrument, observed_at=evaluated_at)
    bound = owner.prepared.bound
    authority = McxCurrentAuthority(
        bound.run_identity, bound.derivative_symbol, bound.derivative_expiry,
        match.provider_instrument_token, plan.selection_sha256,
        bound.receipt_identity, bound.receipt_integrity_sha256,
        bound.promotion_identity, bound.promotion_integrity_sha256,
        bound.request_bound_lineage_sha256,
    )
    owner.fence.check()
    if (current_plan() != plan
            or (bound.family, bound.manifest_sha256,
                bound.assessment_sha256, bound.receipt_integrity_sha256,
                bound.promotion_integrity_sha256)
               != (plan.family, plan.manifest_sha256,
                   plan.assessment_sha256, plan.receipt_integrity_sha256,
                   plan.promotion_integrity_sha256)
            or (authority.run_identity, authority.contract_symbol,
                authority.expiry, authority.provider_token,
                authority.selection_sha256, authority.receipt_sha256,
                authority.v2_sha256)
               != (plan.native_run_identity, plan.contract_symbol, plan.expiry,
                   match.provider_instrument_token, plan.selection_sha256,
                   plan.receipt_integrity_sha256,
                   plan.promotion_integrity_sha256)):
        raise McxKr380Rejected("MCX_V1_CURRENT_REVIEW_CHANGED")
    first = _read_completed_source(plan, instrument, provider, mtf, schedule,
                                   evaluated_at=evaluated_at)
    second = _read_completed_source(plan, instrument, provider, mtf, schedule,
                                    evaluated_at=evaluated_at)
    if first != second:
        raise McxKr380Rejected("MCX_V1_COMPLETED_1H_REVISED")
    owner.fence.check()
    _, hour_sha, interval_sha, *hours = first
    prices = tuple(Decimal(str(value)) for candle in hours
                   for value in (candle.open, candle.close))
    if any(value / instrument.tick_size !=
           (value / instrument.tick_size).to_integral_value()
           for value in (plan.entry, plan.stop, plan.canonical_target,
                         *prices)):
        raise McxKr380Rejected("MCX_V1_COMPLETED_PRICE_OFF_TICK")
    direction = plan.native_direction.value
    selected = None
    for index, (previous, current) in enumerate(zip(hours, hours[1:])):
        p, opening, c = (Decimal(str(previous.close)),
                         Decimal(str(current.open)),
                         Decimal(str(current.close)))
        crossed = ((p < plan.entry and opening < plan.entry and c >= plan.entry)
                   if direction == "LONG" else
                   (p > plan.entry and opening > plan.entry and c <= plan.entry))
        if crossed:
            selected = (index, previous, current)
            break
    if selected is None:
        raise McxKr380Rejected("MCX_V1_COMPLETED_CLOSE_NOT_TRIGGERED")
    pair_index, previous, current = selected
    pair_boundary = current.timestamp + timedelta(hours=1)
    identity = mcx_digest((
        plan.integrity_hash, match.snapshot_file_sha256,
        asdict(authority), first[:3], asdict(previous), asdict(current),
        monitoring_binding_identity,
    ))
    state = (McxAdvisoryState.LONG_CONFIRMED if direction == "LONG" else
             McxAdvisoryState.SHORT_CONFIRMED)
    retained_before = store.load_for_plan(plan.trade_plan_id)
    values = dict(
        advisory_id="MCX-ADVISORY-" + identity,
        contract_symbol=plan.contract_symbol, expiry=plan.expiry,
        provider_token=match.provider_instrument_token,
        session_identity=schedule.session_identity,
        native_run_identity=plan.native_run_identity,
        canonical_instrument=plan.family.value, direction=direction,
        kr370_source_identity=plan.readiness_record_identity,
        trade_plan_id=plan.trade_plan_id, trade_plan_sha256=plan.integrity_hash,
        risk_result_id=risk.risk_result_id,
        monitoring_binding_id=monitoring_binding_identity,
        observation_boundary=pair_boundary,
        source_observation_ids=("MCX-1H-P-" + mcx_digest(asdict(previous)),
                                "MCX-1H-C-" + mcx_digest(asdict(current))),
        source_sequence=(pair_index, pair_index + 1), state=state,
        occurred_at=pair_boundary,
        confirmed_at=(retained_before.confirmed_at if retained_before else evaluated_at),
        provenance=(ADVISORY_RULE_ID, _SOURCE, "RESPONSE_ORDINALS_NOT_TICK_SEQUENCE",
                    plan.integrity_hash, plan.selection_sha256,
                    plan.receipt_integrity_sha256,
                    plan.promotion_integrity_sha256,
                    match.snapshot_file_sha256,
                    plan.completed_one_hour_sha256, hour_sha, interval_sha,
                    mcx_digest(asdict(current)), "INTRABAR_TRADE_CONTINUITY_UNVERIFIED"),
    )
    final_source = _read_completed_source(
        plan, instrument, provider, mtf, schedule, evaluated_at=evaluated_at)
    if final_source != first:
        raise McxKr380Rejected("MCX_V1_COMPLETED_1H_REVISED")
    with owner.final_fence():
        confirmed_at = clock()
        if (current_plan() != plan
                or confirmed_at.tzinfo is None
                or confirmed_at < evaluated_at
                or confirmed_at >= plan.entry_eligibility_boundary
                or (risk.valid_until is not None and confirmed_at >= risk.valid_until)
                or mcx_digest(asdict(mtf.load(plan.native_run_identity))) != first[0]
                or read_retained_mcx_master_match(
                    master, snapshot_identity=plan.provider_snapshot_identity,
                    record_identity=plan.provider_record_identity,
                    family=plan.family, normalized_contract=instrument,
                    observed_at=evaluated_at) != match):
            raise McxKr380Rejected("MCX_V1_SIGNAL_COMMIT_FENCE_CHANGED")
        values["confirmed_at"] = (retained_before.confirmed_at
                                   if retained_before else confirmed_at)
        outcome = McxV1AdvisoryOutcome.create(**values)
        retained = store.load_for_plan(plan.trade_plan_id)
        if retained is not None:
            if retained != outcome:
                raise McxKr380Rejected("MCX_V1_SIGNAL_REPLAY_CONFLICT")
            return retained
        store.retain_current(outcome)
        return outcome
