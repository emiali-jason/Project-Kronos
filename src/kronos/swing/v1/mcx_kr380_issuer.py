"""Isolated completed-MCX-1H KR-380 signal issuer.

The Sponsor-approved close-cross predicate is a signal rule, not a fill rule.
This adapter accepts only explicit isolated-fixture authority. No production
composition or Browser route calls it; MCX_STEP31_NOT_COMMISSIONED remains.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Callable

from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_production_entry import McxExactContractProof
from kronos.swing.v1.native_entry_timing import (
    EcpcV2Outcome, Kr380EntryOutcomeV2, Kr380V2State,
    LocalKr380V2Store, NativeEcpcV2Context, _values_digest,
    KR380_CONTRACT_ID, KR380_CONTRACT_VERSION, KR380_POLICY_ID,
    KR380_POLICY_VERSION, NO_BROKER_AUTHORITY,
)
from kronos.swing.v1.step32 import RiskApproval


RULE_ID = "SWING-MCX-KR380-COMPLETED-1H-CLOSE-CROSS-V1"
FIXTURE_ORIGIN = "ISOLATED_FIXTURE_ONLY"


class McxKr380Rejected(ValueError):
    """Sanitized fail-closed result before any durable admission."""


def _sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None


def _price(value: object) -> bool:
    return type(value) is Decimal and value.is_finite() and value > 0


def _digest(value: object) -> str:
    def plain(item: object) -> object:
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, Enum):
            return item.value
        if hasattr(item, "__dataclass_fields__"):
            return {name: plain(getattr(item, name)) for name in item.__dataclass_fields__}
        if isinstance(item, (tuple, list)):
            return [plain(value) for value in item]
        if isinstance(item, dict):
            return {name: plain(value) for name, value in item.items()}
        return item
    return sha256(json.dumps(plain(value), sort_keys=True,
                             separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class McxOneHourCandle:
    run_identity: str
    family: McxFamily
    trading_symbol: str
    expiry: str
    provider_token: int
    session_identity: str
    candle_identity: str
    revision: int
    source_sequence: int
    source_sha256: str
    opened_at: datetime
    closed_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    confirmed_complete: bool

    def __post_init__(self) -> None:
        if (not self.run_identity or type(self.family) is not McxFamily
                or not self.trading_symbol or not self.expiry
                or type(self.provider_token) is not int or self.provider_token <= 0
                or not self.session_identity or not self.candle_identity
                or type(self.revision) is not int or self.revision < 1
                or type(self.source_sequence) is not int or self.source_sequence < 0
                or not _sha(self.source_sha256)
                or not _aware(self.opened_at) or not _aware(self.closed_at)
                or self.opened_at >= self.closed_at
                or self.closed_at - self.opened_at != timedelta(hours=1)
                or any(not _price(value) for value in
                       (self.open, self.high, self.low, self.close))
                or self.low > min(self.open, self.close)
                or self.high < max(self.open, self.close)
                or self.low > self.high
                or type(self.confirmed_complete) is not bool):
            raise McxKr380Rejected("MCX_1H_CANDLE_INVALID")


@dataclass(frozen=True, slots=True)
class McxContinuityProof:
    previous_identity: str
    previous_revision: int
    previous_sha256: str
    current_identity: str
    current_revision: int
    current_sha256: str
    session_identity: str
    intervals_consecutive: bool
    no_missing_interval: bool
    no_entry_spanning_gap: bool
    source_identity: str
    source_sha256: str
    origin: str = FIXTURE_ORIGIN

    def __post_init__(self) -> None:
        if (not self.previous_identity or not self.current_identity
                or type(self.previous_revision) is not int or self.previous_revision < 1
                or type(self.current_revision) is not int or self.current_revision < 1
                or not _sha(self.previous_sha256) or not _sha(self.current_sha256)
                or not self.session_identity or not self.source_identity
                or not _sha(self.source_sha256)
                or any(type(value) is not bool for value in (
                    self.intervals_consecutive, self.no_missing_interval,
                    self.no_entry_spanning_gap))
                or self.origin != FIXTURE_ORIGIN):
            raise McxKr380Rejected("MCX_1H_CONTINUITY_PROOF_INVALID")


@dataclass(frozen=True, slots=True)
class McxIsolatedEntryPolicy:
    policy_identity: str
    policy_sha256: str
    maximum_gross_stop_risk_rupees: Decimal
    valid_until: datetime
    entry_cutoff: datetime
    exchange_cutoff_sha256: str
    broker_cutoff_sha256: str
    origin: str = FIXTURE_ORIGIN

    def __post_init__(self) -> None:
        if (not self.policy_identity or not _sha(self.policy_sha256)
                or not _price(self.maximum_gross_stop_risk_rupees)
                or not _aware(self.valid_until) or not _aware(self.entry_cutoff)
                or not _sha(self.exchange_cutoff_sha256)
                or not _sha(self.broker_cutoff_sha256)
                or self.origin != FIXTURE_ORIGIN):
            raise McxKr380Rejected("MCX_1H_POLICY_INVALID")


@dataclass(frozen=True, slots=True)
class McxCurrentAuthority:
    """Current owner observations, independently read from the retained proof."""

    run_identity: str
    contract_symbol: str
    expiry: str
    provider_token: int
    selection_sha256: str
    receipt_identity: str
    receipt_sha256: str
    v2_identity: str
    v2_sha256: str
    proof_read_set_sha256: str

    def __post_init__(self) -> None:
        if (not self.run_identity or not self.contract_symbol or not self.expiry
                or type(self.provider_token) is not int or self.provider_token <= 0
                or not self.receipt_identity or not self.v2_identity
                or any(not _sha(value) for value in (
                    self.selection_sha256, self.receipt_sha256,
                    self.v2_sha256, self.proof_read_set_sha256))):
            raise McxKr380Rejected("MCX_1H_CURRENT_AUTHORITY_INVALID")


@dataclass(frozen=True, slots=True)
class McxKr380ReadSet:
    proof: McxExactContractProof
    risk: RiskApproval
    context: NativeEcpcV2Context
    previous: McxOneHourCandle
    current: McxOneHourCandle
    continuity: McxContinuityProof
    policy: McxIsolatedEntryPolicy
    current_authority: McxCurrentAuthority
    plan_identity: str
    plan_sha256: str
    kr370_source_identity: str
    monitoring_binding_identity: str
    direction: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    tick_size: Decimal
    origin: str = FIXTURE_ORIGIN


def _validated(read: McxKr380ReadSet, *, evaluated_at: datetime) -> Kr380EntryOutcomeV2:
    if (type(read) is not McxKr380ReadSet or not _aware(evaluated_at)
            or read.origin != FIXTURE_ORIGIN
            or type(read.proof) is not McxExactContractProof
            or type(read.risk) is not RiskApproval
            or type(read.context) is not NativeEcpcV2Context
            or type(read.previous) is not McxOneHourCandle
            or type(read.current) is not McxOneHourCandle
            or type(read.continuity) is not McxContinuityProof
            or type(read.policy) is not McxIsolatedEntryPolicy
            or type(read.current_authority) is not McxCurrentAuthority
            or not read.plan_identity or not _sha(read.plan_sha256)
            or not read.kr370_source_identity or not read.monitoring_binding_identity
            or type(read.direction) is not str
            or read.direction not in {"LONG", "SHORT"}
            or any(not _price(value) for value in
                   (read.entry, read.stop, read.target, read.tick_size))):
        raise McxKr380Rejected("MCX_1H_READ_SET_INVALID")
    p, c, proof, continuity = read.previous, read.current, read.proof, read.continuity
    authority = read.current_authority
    if (proof.missing_authority
            or type(proof.missing_authority) is not tuple
            or not proof.review_receipt_identity or not proof.v2_identity
            or not proof.master_snapshot_identity or not proof.master_record_identity
            or not _sha(proof.read_set_sha256)
            or not _sha(proof.selection_sha256)
            or not _sha(proof.handoff_sha256)
            or not _sha(proof.review_receipt_sha256)
            or not _sha(proof.v2_sha256)
            or not _sha(proof.master_file_sha256)
            or not _sha(proof.specification_sha256)
            or not _sha(proof.conversion_sha256)
            or not _sha(proof.exchange_cutoff_sha256)
            or not _sha(proof.broker_cutoff_sha256)
            or proof.exchange_cutoff_sha256 != read.policy.exchange_cutoff_sha256
            or proof.broker_cutoff_sha256 != read.policy.broker_cutoff_sha256
            or not _sha(proof.completed_daily_sha256)
            or not _sha(proof.completed_four_hour_sha256)
            or not _sha(proof.completed_one_hour_sha256)
            or not _sha(proof.completed_series_sha256)
            or type(proof.master_token) is not int or proof.master_token <= 0
            or (proof.run_identity, proof.selected_contract,
                proof.selected_expiry, proof.master_token,
                proof.selection_sha256, proof.review_receipt_identity,
                proof.review_receipt_sha256, proof.v2_identity,
                proof.v2_sha256, proof.read_set_sha256)
               != (authority.run_identity, authority.contract_symbol,
                   authority.expiry, authority.provider_token,
                   authority.selection_sha256, authority.receipt_identity,
                   authority.receipt_sha256, authority.v2_identity,
                   authority.v2_sha256, authority.proof_read_set_sha256)
            or type(proof.lots) is not int or proof.lots <= 0
            or type(proof.provider_order_quantity) is not int
            or proof.provider_order_quantity <= 0
            or not all(_price(value) for value in (
                proof.physical_quantity, proof.price_to_rupee_multiplier,
                proof.gross_notional, proof.rupees_per_tick, proof.gross_stop_risk))
            or not proof.physical_unit or not proof.provider_order_unit
            or proof.fees is not None or proof.margin is not None
            or not _aware(proof.completed_daily_boundary)
            or not _aware(proof.completed_four_hour_boundary)
            or not _aware(proof.completed_one_hour_boundary)
            or proof.run_identity != p.run_identity or proof.run_identity != c.run_identity
            or proof.family is not p.family or proof.family is not c.family
            or (proof.selected_contract, proof.selected_expiry, proof.master_token)
               != (p.trading_symbol, p.expiry, p.provider_token)
            or (p.trading_symbol, p.expiry, p.provider_token)
               != (c.trading_symbol, c.expiry, c.provider_token)
            or proof.completed_one_hour_sha256 != p.source_sha256
            or proof.completed_one_hour_boundary != p.closed_at
            or proof.gross_notional != read.entry * proof.price_to_rupee_multiplier
            or proof.rupees_per_tick != read.tick_size * proof.price_to_rupee_multiplier
            or proof.gross_stop_risk != abs(read.entry - read.stop)
               * proof.price_to_rupee_multiplier
            or proof.gross_stop_risk > read.policy.maximum_gross_stop_risk_rupees):
        raise McxKr380Rejected("MCX_1H_EXACT_PROOF_INCOMPLETE_OR_CHANGED")
    if (read.direction == "LONG" and not read.stop < read.entry < read.target
            or read.direction == "SHORT" and not read.target < read.entry < read.stop
            or any(value / read.tick_size != (value / read.tick_size).to_integral_value()
                   for value in (read.entry, read.stop, read.target,
                                 p.open, p.close, c.open, c.close))):
        raise McxKr380Rejected("MCX_1H_GEOMETRY_INVALID")
    risk, context = read.risk, read.context
    if (not risk.permits_entry or risk.run_id != proof.run_identity
            or risk.candidate_id != read.plan_identity
            or risk.candidate_digest != read.plan_sha256
            or risk.valid_until is not None and evaluated_at >= risk.valid_until
            or context.outcome is not EcpcV2Outcome.QUALIFIED
            or context.native_run_identity != proof.run_identity
            or context.canonical_instrument != proof.family.value
            or context.direction != read.direction
            or context.trade_plan_id != read.plan_identity
            or context.trade_plan_sha256 != read.plan_sha256
            or context.risk_result_id != risk.risk_result_id
            or context.monitoring_binding_id != read.monitoring_binding_identity
            or context.session_identity != c.session_identity
            or context.observation_boundary != c.closed_at):
        raise McxKr380Rejected("MCX_1H_RISK_OR_CONTEXT_INVALID")
    if (not p.confirmed_complete or not c.confirmed_complete
            or p.session_identity != c.session_identity
            or p.closed_at != c.opened_at
            or p.source_sequence >= c.source_sequence
            or evaluated_at < c.closed_at
            or evaluated_at >= read.policy.valid_until
            or evaluated_at >= read.policy.entry_cutoff
            or continuity.session_identity != c.session_identity
            or (continuity.previous_identity, continuity.previous_revision,
                continuity.previous_sha256) !=
               (p.candle_identity, p.revision, p.source_sha256)
            or (continuity.current_identity, continuity.current_revision,
                continuity.current_sha256) !=
               (c.candle_identity, c.revision, c.source_sha256)
            or not continuity.intervals_consecutive
            or not continuity.no_missing_interval
            or not continuity.no_entry_spanning_gap):
        raise McxKr380Rejected("MCX_1H_CONTINUITY_OR_CUTOFF_INVALID")
    if read.direction == "LONG":
        crossed = p.close < read.entry and c.open < read.entry and c.close >= read.entry
        consistent = c.high >= read.entry
        state = Kr380V2State.LONG_ENTRY_TRIGGERED
    else:
        crossed = p.close > read.entry and c.open > read.entry and c.close <= read.entry
        consistent = c.low <= read.entry
        state = Kr380V2State.SHORT_ENTRY_TRIGGERED
    if not crossed or not consistent:
        raise McxKr380Rejected("MCX_1H_COMPLETED_CLOSE_NOT_TRIGGERED")
    read_set_sha = _digest(read)
    values = dict(
        entry_outcome_id="KR380-V2-MCX-" + read_set_sha,
        native_run_identity=proof.run_identity,
        canonical_instrument=proof.family.value,
        direction=read.direction,
        kr370_source_identity=read.kr370_source_identity,
        trade_plan_id=read.plan_identity,
        trade_plan_sha256=read.plan_sha256,
        risk_result_id=risk.risk_result_id,
        ecpc_context_identity=context.context_identity,
        monitoring_binding_id=read.monitoring_binding_identity,
        observation_boundary=c.closed_at,
        source_observation_ids=(p.candle_identity, c.candle_identity),
        source_sequence=(p.source_sequence, c.source_sequence),
        state=state, reason="MCX_COMPLETED_1H_CLOSE_CROSS",
        occurred_at=c.closed_at,
        provenance=(RULE_ID, proof.read_set_sha256, proof.review_receipt_sha256,
                    proof.v2_sha256, read.policy.policy_sha256,
                    continuity.source_sha256, p.source_sha256, c.source_sha256),
        contract_identity=KR380_CONTRACT_ID,
        contract_version=KR380_CONTRACT_VERSION, owner_identity="KR-380",
        state_family_identity="KR380_ENTRY_OUTCOME",
        policy_identity=KR380_POLICY_ID,
        policy_version=KR380_POLICY_VERSION, broker_authority=NO_BROKER_AUTHORITY,
    )
    return Kr380EntryOutcomeV2(integrity_sha256=_values_digest(values), **values)


def issue_isolated_mcx_kr380(
    current: Callable[[], McxKr380ReadSet], *, evaluated_at: datetime,
    store: LocalKr380V2Store,
    commit_guard: Callable[[], AbstractContextManager[object]],
    guarded_recheck: Callable[[str], bool],
) -> Kr380EntryOutcomeV2:
    """Validate twice, then fence exact bytes and retain at most one outcome.

    The owner prepares the read set outside business locks. guarded_recheck
    performs only a captured-byte/current-pointer comparison under its existing
    WO-05 -> WO-07 guard. The isolated outcome store is the only write here.
    """

    if (not callable(current) or type(store) is not LocalKr380V2Store
            or not callable(commit_guard) or not callable(guarded_recheck)):
        raise McxKr380Rejected("MCX_1H_ISSUER_INPUT_INVALID")
    first = current()
    outcome = _validated(first, evaluated_at=evaluated_at)
    second = current()
    if first != second or outcome != _validated(second, evaluated_at=evaluated_at):
        raise McxKr380Rejected("MCX_1H_READ_SET_CHANGED")
    with commit_guard():
        if guarded_recheck(_digest(first)) is not True:
            raise McxKr380Rejected("MCX_1H_COMMIT_FENCE_CHANGED")
        retained = store.load_for_plan(first.plan_identity)
        if retained is not None:
            if retained != outcome:
                raise McxKr380Rejected("MCX_1H_REPLAY_CONFLICT")
            return retained
        store.retain_current(outcome)
        return outcome


__all__ = ["McxContinuityProof", "McxCurrentAuthority", "McxIsolatedEntryPolicy", "McxKr380ReadSet",
           "McxKr380Rejected", "McxOneHourCandle", "RULE_ID",
           "issue_isolated_mcx_kr380"]
