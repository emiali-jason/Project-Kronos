"""Step 33 immutable Native trade journal and factual V0 analytics.

Lifecycle facts are consumed exactly as retained by Steps 31, 32 and 32-L.
This module has no market-data, analytical-gate, OpenAI, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock

from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveTradeLifecycleSnapshot,
    LifecycleEventType,
    TradeClosureRecord,
    TradeExitReason,
)
from kronos.swing.v1.native_readiness import NativeLayer2ReadinessRecord
from kronos.swing.v1.native_readiness_v3 import NativeLayer2ReadinessRecordV3
from kronos.swing.v1.native_sponsor_decision import (
    SponsorInitiationResult,
    SponsorTradeChoice,
    SponsorTradeDecisionRecord,
)
from kronos.swing.v1.native_trade_construction import TradePlanRecord


TRADE_JOURNAL_CONTRACT_ID = "KRONOS-SWING-V1-TRADE-JOURNAL-V1"
TRADE_JOURNAL_CONTRACT_VERSION = "1"
TRADE_JOURNAL_POLICY_ID = "SWING-V1-TRADE-JOURNAL-ANALYTICS-V0"
TRADE_JOURNAL_POLICY_VERSION = "0"
TRADE_JOURNAL_STORE_SCHEMA = "KRONOS-SWING-V1-TRADE-JOURNAL-STORE-V0"
TRADE_JOURNAL_AUTHORITY = "DOWNSTREAM_FACTUAL_EVIDENCE_ONLY_NO_TRADING_AUTHORITY"


class JournalRecordType(StrEnum):
    TRADE = "TRADE"
    IGNORED_OPPORTUNITY = "IGNORED_OPPORTUNITY"


class FactualOutcome(StrEnum):
    POSITIVE_PNL = "POSITIVE_PNL"
    NEGATIVE_PNL = "NEGATIVE_PNL"
    FLAT_PNL = "FLAT_PNL"
    OUTCOME_UNRESOLVED = "OUTCOME_UNRESOLVED"
    OUTCOME_UNAVAILABLE = "OUTCOME_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class TradeJournalRecord:
    journal_record_id: str
    record_type: JournalRecordType
    mode: SponsorTradeChoice
    instrument: str
    direction: V1Direction
    native_run_identity: str
    opportunity_identity: str
    native_assessment_sha256: str
    readiness_record_identity: str
    readiness_record_sha256: str
    readiness_state: str
    trade_plan_id: str
    trade_plan_sha256: str
    sponsor_decision_id: str
    sponsor_decision_sha256: str
    sponsor_position_id: str | None
    sponsor_position_sha256: str | None
    trade_closure_id: str | None
    trade_closure_sha256: str | None
    setup_identity: str
    model_entry: Decimal
    model_stop: Decimal
    analytical_invalidation: Decimal
    model_target: Decimal
    model_risk_reward: Decimal
    actual_entry: Decimal | None
    actual_exit: Decimal | None
    lots: int | None
    underlying_quantity: int | None
    entry_timestamp: datetime | None
    exit_timestamp: datetime | None
    holding_duration_seconds: int | None
    exit_reason: str | None
    gross_pnl: Decimal | None
    percentage_result: Decimal | None
    realised_r: Decimal | None
    outcome: FactualOutcome
    observed_events: tuple[LifecycleEventType, ...]
    lifecycle_event_ids: tuple[str, ...]
    lifecycle_event_hashes: tuple[str, ...]
    accounting_basis: str
    commentary: str
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_hash: str
    contract_identity: str = TRADE_JOURNAL_CONTRACT_ID
    contract_version: str = TRADE_JOURNAL_CONTRACT_VERSION
    policy_identity: str = TRADE_JOURNAL_POLICY_ID
    policy_version: str = TRADE_JOURNAL_POLICY_VERSION
    authority: str = TRADE_JOURNAL_AUTHORITY
    cost_model: str = "GROSS_PNL_NO_FEES_TAXES_BROKERAGE_OR_SLIPPAGE_V0"

    def __post_init__(self) -> None:
        for name in (
            "model_entry", "model_stop", "analytical_invalidation",
            "model_target", "model_risk_reward",
        ):
            object.__setattr__(self, name, _positive(getattr(self, name)))
        for name in ("actual_entry", "actual_exit"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive(value))
        for name in ("gross_pnl", "percentage_result", "realised_r"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(value))
        trade = self.record_type is JournalRecordType.TRADE
        ignored = self.record_type is JournalRecordType.IGNORED_OPPORTUNITY
        if (
            self.contract_identity != TRADE_JOURNAL_CONTRACT_ID
            or self.contract_version != TRADE_JOURNAL_CONTRACT_VERSION
            or self.policy_identity != TRADE_JOURNAL_POLICY_ID
            or self.policy_version != TRADE_JOURNAL_POLICY_VERSION
            or self.authority != TRADE_JOURNAL_AUTHORITY
            or self.cost_model != "GROSS_PNL_NO_FEES_TAXES_BROKERAGE_OR_SLIPPAGE_V0"
            or not all(_identity(value) for value in (
                self.journal_record_id, self.native_run_identity,
                self.opportunity_identity, self.readiness_record_identity,
                self.trade_plan_id, self.sponsor_decision_id,
            ))
            or not all(_digest(value) for value in (
                self.native_assessment_sha256, self.readiness_record_sha256,
                self.trade_plan_sha256, self.sponsor_decision_sha256,
            ))
            or not self.instrument or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not self.readiness_state or not self.setup_identity
            or type(self.mode) is not SponsorTradeChoice
            or not _aware(self.created_at) or not self.provenance
            or any(type(item) is not LifecycleEventType for item in self.observed_events)
            or any(not _identity(item) for item in self.lifecycle_event_ids)
            or any(not _digest(item) for item in self.lifecycle_event_hashes)
            or len(self.lifecycle_event_ids) != len(self.lifecycle_event_hashes)
            or not self.accounting_basis or not self.commentary
            or (trade and self.mode not in {SponsorTradeChoice.PAPER, SponsorTradeChoice.LIVE})
            or (ignored and self.mode is not SponsorTradeChoice.IGNORE)
            or (trade and any(value is None for value in (
                self.sponsor_position_id, self.sponsor_position_sha256,
                self.trade_closure_id, self.trade_closure_sha256,
                self.actual_entry, self.actual_exit, self.lots,
                self.underlying_quantity, self.entry_timestamp, self.exit_timestamp,
                self.holding_duration_seconds, self.gross_pnl,
                self.percentage_result, self.realised_r,
            )))
            or (trade and (not self.lifecycle_event_ids or self.outcome not in {
                FactualOutcome.POSITIVE_PNL, FactualOutcome.NEGATIVE_PNL,
                FactualOutcome.FLAT_PNL,
            }))
            or (ignored and any(value is not None for value in (
                self.sponsor_position_id, self.sponsor_position_sha256,
                self.trade_closure_id, self.trade_closure_sha256,
                self.actual_entry, self.actual_exit, self.lots,
                self.underlying_quantity, self.entry_timestamp, self.exit_timestamp,
                self.holding_duration_seconds, self.exit_reason, self.gross_pnl,
                self.percentage_result, self.realised_r,
            )))
            or (ignored and (self.lifecycle_event_ids or self.lifecycle_event_hashes
                             or self.observed_events
                             or self.outcome is not FactualOutcome.OUTCOME_UNAVAILABLE))
            or (self.entry_timestamp is not None and not _aware(self.entry_timestamp))
            or (self.exit_timestamp is not None and not _aware(self.exit_timestamp))
            or (self.holding_duration_seconds is not None
                and (type(self.holding_duration_seconds) is not int
                     or self.holding_duration_seconds < 0))
            or not _digest(self.integrity_hash)
            or self.integrity_hash != _record_digest(self)
        ):
            raise ValueError("TRADE_JOURNAL_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class JournalBreakdown:
    dimension: str
    value: str
    sample_size: int
    positive_results: int
    negative_results: int
    flat_results: int
    total_gross_pnl: Decimal
    average_realised_r: Decimal | None


@dataclass(frozen=True, slots=True)
class TradeJournalAnalytics:
    total_completed_trades: int
    paper_trades: int
    live_trades: int
    ignored_opportunities: int
    positive_results: int
    negative_results: int
    flat_results: int
    unresolved_results: int
    win_rate: Decimal | None
    total_gross_pnl: Decimal
    average_gross_pnl: Decimal | None
    total_realised_r: Decimal
    average_realised_r: Decimal | None
    average_holding_duration_seconds: Decimal | None
    target_hit_closures: int
    stop_hit_closures: int
    sponsor_manual_exits: int
    invalidation_observed_before_closure: int
    monitoring_unavailable_count: int
    event_unresolved_count: int
    breakdowns: tuple[JournalBreakdown, ...]


@dataclass(frozen=True, slots=True)
class JournalValidationAnalytics:
    opportunities_reviewed: int
    ready_for_trade_construction: int
    trade_plans_produced: int
    paper_decisions: int
    live_decisions: int
    ignore_decisions: int
    paper_entries_triggered: int
    paper_trades_closed: int
    live_trades_closed: int
    unresolved_lifecycle_events: int
    monitoring_outages: int
    completed_gross_pnl_sample: tuple[Decimal, ...]
    completed_realised_r_sample: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class TradeJournalSnapshot:
    records: tuple[TradeJournalRecord, ...]
    analytics: TradeJournalAnalytics
    validation: JournalValidationAnalytics


class LocalTradeJournalStore:
    """Append-only immutable Step-33 journal persistence."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("TRADE_JOURNAL_STORE_INVALID")
        self._lock = RLock()

    def retain(self, record: TradeJournalRecord) -> None:
        path = self.root / f"{record.journal_record_id}.json"
        payload = {"schema": TRADE_JOURNAL_STORE_SCHEMA, "record": _primitive(record)}
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("TRADE_JOURNAL_RECORD_IMMUTABLE")
                return
            _atomic(path, payload)

    def load(self) -> tuple[TradeJournalRecord, ...]:
        if not self.root.exists():
            return ()
        return tuple(_record_from_dict(_read(path)["record"]) for path in sorted(self.root.glob("*.json")))


class TradeJournalService:
    """Idempotently integrate exact closure/decision chains into Step 33."""

    def __init__(self, store: LocalTradeJournalStore) -> None:
        self.store = store
        restored = store.load()
        self._records = {item.journal_record_id: item for item in restored}
        self._validation = _empty_validation()
        self._lock = RLock()

    def reconcile(
        self,
        plans: tuple[TradePlanRecord, ...],
        readiness: tuple[NativeLayer2ReadinessRecord, ...],
        initiations: tuple[SponsorInitiationResult, ...],
        lifecycle: ActiveTradeLifecycleSnapshot,
    ) -> TradeJournalSnapshot:
        plan_by_id = {item.trade_plan_id: item for item in plans}
        readiness_by_id = {item.result_sha256: item for item in readiness}
        events = {item.event_id: item for item in lifecycle.events}
        positions = {item.position_id: item for item in lifecycle.positions}
        decisions = {
            item.decision.trade_plan_id: item for item in initiations
            if item.decision is not None
        }
        closures = {item.trade_plan_id: item for item in lifecycle.closures}
        with self._lock:
            for trade_plan_id, initiation in decisions.items():
                plan = plan_by_id.get(trade_plan_id)
                if plan is None or initiation.decision is None:
                    raise ValueError("JOURNAL_UNAVAILABLE:TRADE_PLAN_BINDING_INVALID")
                ready = readiness_by_id.get(plan.readiness_record_sha256)
                if (
                    ready is None
                    or ready.result_sha256 != plan.readiness_record_sha256
                    or plan.readiness_record_identity != _readiness_identity(ready)
                    or ready.run_identity != plan.native_run_identity
                    or ready.canonical_instrument != plan.canonical_instrument
                    or ready.native_assessment_sha256 != plan.native_assessment_sha256
                ):
                    raise ValueError("JOURNAL_UNAVAILABLE:READINESS_BINDING_INVALID")
                decision = initiation.decision
                if decision.decision is SponsorTradeChoice.IGNORE:
                    record = _ignored_record(plan, ready, decision)
                else:
                    closure = closures.get(trade_plan_id)
                    if closure is None:
                        continue
                    position = positions.get(closure.position_id)
                    if position is None or initiation.position is None:
                        raise ValueError("JOURNAL_UNAVAILABLE:POSITION_BINDING_INVALID")
                    bound_events = tuple(events.get(item) for item in closure.lifecycle_event_ids)
                    if any(item is None for item in bound_events):
                        raise ValueError("JOURNAL_UNAVAILABLE:LIFECYCLE_EVENT_BINDING_INVALID")
                    record = _trade_record(
                        plan, ready, decision, initiation, position, closure,
                        tuple(item for item in bound_events if item is not None),
                    )
                current = self._records.get(record.journal_record_id)
                if current is not None and current != record:
                    raise ValueError("JOURNAL_UNAVAILABLE:IMMUTABLE_RECORD_CONFLICT")
                self.store.retain(record)
                self._records[record.journal_record_id] = record
            self._validation = _validation_analytics(
                readiness, plans, initiations, lifecycle,
                tuple(self._records.values()),
            )
            return self.snapshot()

    def snapshot(self) -> TradeJournalSnapshot:
        with self._lock:
            records = tuple(sorted(
                self._records.values(),
                key=lambda item: (item.created_at, item.journal_record_id),
            ))
            return TradeJournalSnapshot(
                records, calculate_journal_analytics(records), self._validation,
            )


def _readiness_identity(
    record: NativeLayer2ReadinessRecord | NativeLayer2ReadinessRecordV3,
) -> str:
    if type(record) is NativeLayer2ReadinessRecordV3:
        return f"NATIVE-V3-READINESS-{record.result_sha256}"
    if type(record) is NativeLayer2ReadinessRecord:
        return f"NATIVE-READINESS-{record.result_sha256}"
    raise ValueError("JOURNAL_UNAVAILABLE:READINESS_VERSION_UNSUPPORTED")


def calculate_journal_analytics(records: tuple[TradeJournalRecord, ...]) -> TradeJournalAnalytics:
    trades = tuple(item for item in records if item.record_type is JournalRecordType.TRADE)
    ignored = tuple(item for item in records if item.record_type is JournalRecordType.IGNORED_OPPORTUNITY)
    positive = sum(item.outcome is FactualOutcome.POSITIVE_PNL for item in trades)
    negative = sum(item.outcome is FactualOutcome.NEGATIVE_PNL for item in trades)
    flat = sum(item.outcome is FactualOutcome.FLAT_PNL for item in trades)
    unresolved = len(trades) - positive - negative - flat
    denominator = positive + negative + flat
    pnls = tuple(item.gross_pnl for item in trades if item.gross_pnl is not None)
    realised = tuple(item.realised_r for item in trades if item.realised_r is not None)
    durations = tuple(Decimal(item.holding_duration_seconds) for item in trades if item.holding_duration_seconds is not None)
    return TradeJournalAnalytics(
        len(trades), sum(item.mode is SponsorTradeChoice.PAPER for item in trades),
        sum(item.mode is SponsorTradeChoice.LIVE for item in trades), len(ignored),
        positive, negative, flat, unresolved,
        None if denominator == 0 else Decimal(positive) / Decimal(denominator) * Decimal("100"),
        sum(pnls, Decimal(0)), None if not pnls else sum(pnls, Decimal(0)) / len(pnls),
        sum(realised, Decimal(0)), None if not realised else sum(realised, Decimal(0)) / len(realised),
        None if not durations else sum(durations, Decimal(0)) / len(durations),
        sum(item.exit_reason in {TradeExitReason.PAPER_TARGET_HIT.value, TradeExitReason.SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION.value} for item in trades),
        sum(item.exit_reason in {TradeExitReason.PAPER_STOP_HIT.value, TradeExitReason.SPONSOR_EXIT_AFTER_STOP_NOTIFICATION.value} for item in trades),
        sum(item.exit_reason == TradeExitReason.SPONSOR_MANUAL_EXIT.value for item in trades),
        sum(LifecycleEventType.INVALIDATION_OBSERVED in item.observed_events for item in trades),
        sum(LifecycleEventType.MONITORING_UNAVAILABLE in item.observed_events for item in trades),
        sum(LifecycleEventType.EVENT_UNRESOLVED in item.observed_events for item in trades),
        _breakdowns(trades),
    )


def _trade_record(plan, readiness, decision, initiation, position, closure, events):  # type: ignore[no-untyped-def]
    if (
        decision.trade_plan_id != plan.trade_plan_id
        or decision.trade_plan_integrity_hash != plan.integrity_hash
        or decision.native_run_identity != plan.native_run_identity
        or decision.canonical_instrument != plan.canonical_instrument
        or decision.direction is not plan.native_direction
        or initiation.position is None
        or initiation.position.position_id != position.position_id
        or initiation.position.decision_id != position.decision_id
        or initiation.position.trade_plan_id != position.trade_plan_id
        or initiation.position.canonical_instrument != position.canonical_instrument
        or initiation.position.direction is not position.direction
        or initiation.position.model_entry != position.model_entry
        or initiation.position.stop != position.stop
        or initiation.position.invalidation != position.invalidation
        or initiation.position.target != position.target
        or closure.trade_plan_id != plan.trade_plan_id
        or closure.trade_plan_hash != plan.integrity_hash
        or closure.decision_id != decision.decision_id
        or closure.position_id != position.position_id
        or closure.instrument != plan.canonical_instrument
        or closure.direction is not plan.native_direction
        or closure.model_entry != plan.entry or closure.stop != plan.stop
        or closure.invalidation != plan.invalidation_reference
        or closure.target != plan.canonical_target
        or tuple(item.event_id for item in events) != closure.lifecycle_event_ids
        or any(item.position_id != closure.position_id or item.trade_plan_hash != plan.integrity_hash for item in events)
    ):
        raise ValueError("JOURNAL_UNAVAILABLE:IMMUTABLE_CHAIN_MISMATCH")
    outcome = (
        FactualOutcome.POSITIVE_PNL if closure.gross_pnl > 0 else
        FactualOutcome.NEGATIVE_PNL if closure.gross_pnl < 0 else
        FactualOutcome.FLAT_PNL
    )
    values = dict(
        journal_record_id=_id("TRADE-JOURNAL", closure.closure_id),
        record_type=JournalRecordType.TRADE, mode=closure.mode,
        instrument=closure.instrument, direction=closure.direction,
        native_run_identity=plan.native_run_identity,
        opportunity_identity=plan.native_opportunity_identity.value,
        native_assessment_sha256=plan.native_assessment_sha256,
        readiness_record_identity=plan.readiness_record_identity,
        readiness_record_sha256=readiness.result_sha256,
        readiness_state=readiness.readiness.value,
        trade_plan_id=plan.trade_plan_id, trade_plan_sha256=plan.integrity_hash,
        sponsor_decision_id=decision.decision_id,
        sponsor_decision_sha256=decision.integrity_hash,
        sponsor_position_id=position.position_id,
        sponsor_position_sha256=initiation.position.integrity_hash,
        trade_closure_id=closure.closure_id,
        trade_closure_sha256=closure.integrity_hash,
        setup_identity=plan.setup_identity.value,
        model_entry=plan.entry, model_stop=plan.stop,
        analytical_invalidation=plan.invalidation_reference,
        model_target=plan.canonical_target,
        model_risk_reward=plan.risk_reward_ratio,
        actual_entry=closure.actual_entry, actual_exit=closure.actual_exit,
        lots=closure.lots, underlying_quantity=closure.underlying_quantity,
        entry_timestamp=position.entry_timestamp,
        exit_timestamp=closure.exit_timestamp,
        holding_duration_seconds=closure.holding_duration_seconds,
        exit_reason=closure.exit_reason.value, gross_pnl=closure.gross_pnl,
        percentage_result=closure.percentage_result, realised_r=closure.realised_r,
        outcome=outcome,
        observed_events=tuple(dict.fromkeys(item.event_type for item in events)),
        lifecycle_event_ids=tuple(item.event_id for item in events),
        lifecycle_event_hashes=tuple(item.integrity_hash for item in events),
        accounting_basis=(
            "OBSERVATION_BASED_PAPER_ACCOUNTING" if closure.mode is SponsorTradeChoice.PAPER
            else "SPONSOR_ATTESTED_ACTUAL_BROKER_EXECUTION"
        ),
        commentary=closure.commentary, created_at=closure.created_at,
        provenance=(
            plan.trade_plan_id, readiness.result_sha256, decision.decision_id,
            position.position_id, closure.closure_id,
            "KRONOS-SWING-V1-TRADE-OUTCOME-V1",
        ),
    )
    return _record(values)


def _ignored_record(plan, readiness, decision):  # type: ignore[no-untyped-def]
    if (
        decision.trade_plan_id != plan.trade_plan_id
        or decision.trade_plan_integrity_hash != plan.integrity_hash
        or decision.native_run_identity != plan.native_run_identity
        or decision.canonical_instrument != plan.canonical_instrument
        or decision.direction is not plan.native_direction
        or decision.model_entry != plan.entry or decision.stop != plan.stop
        or decision.invalidation != plan.invalidation_reference
        or decision.target != plan.canonical_target
        or decision.model_risk_reward != plan.risk_reward_ratio
    ):
        raise ValueError("JOURNAL_UNAVAILABLE:IGNORE_BINDING_MISMATCH")
    values = dict(
        journal_record_id=_id("TRADE-JOURNAL-IGNORE", decision.decision_id),
        record_type=JournalRecordType.IGNORED_OPPORTUNITY,
        mode=SponsorTradeChoice.IGNORE, instrument=plan.canonical_instrument,
        direction=plan.native_direction, native_run_identity=plan.native_run_identity,
        opportunity_identity=plan.native_opportunity_identity.value,
        native_assessment_sha256=plan.native_assessment_sha256,
        readiness_record_identity=plan.readiness_record_identity,
        readiness_record_sha256=readiness.result_sha256,
        readiness_state=readiness.readiness.value,
        trade_plan_id=plan.trade_plan_id, trade_plan_sha256=plan.integrity_hash,
        sponsor_decision_id=decision.decision_id,
        sponsor_decision_sha256=decision.integrity_hash,
        sponsor_position_id=None, sponsor_position_sha256=None,
        trade_closure_id=None, trade_closure_sha256=None,
        setup_identity=plan.setup_identity.value,
        model_entry=plan.entry, model_stop=plan.stop,
        analytical_invalidation=plan.invalidation_reference,
        model_target=plan.canonical_target, model_risk_reward=plan.risk_reward_ratio,
        actual_entry=None, actual_exit=None, lots=None, underlying_quantity=None,
        entry_timestamp=None, exit_timestamp=None, holding_duration_seconds=None,
        exit_reason=None, gross_pnl=None, percentage_result=None, realised_r=None,
        outcome=FactualOutcome.OUTCOME_UNAVAILABLE, observed_events=(),
        lifecycle_event_ids=(), lifecycle_event_hashes=(),
        accounting_basis="NO_POSITION_NO_PNL",
        commentary="Sponsor chose IGNORE for the exact immutable Trade Plan.",
        created_at=decision.decision_timestamp,
        provenance=(plan.trade_plan_id, readiness.result_sha256, decision.decision_id),
    )
    return _record(values)


def _breakdowns(trades):  # type: ignore[no-untyped-def]
    results = []
    dimensions = {
        "SETUP": lambda item: item.setup_identity,
        "DIRECTION": lambda item: item.direction.value,
        "MODE": lambda item: item.mode.value,
        "INSTRUMENT": lambda item: item.instrument,
    }
    for dimension, getter in dimensions.items():
        for value in sorted({getter(item) for item in trades}):
            group = tuple(item for item in trades if getter(item) == value)
            realised = tuple(item.realised_r for item in group if item.realised_r is not None)
            results.append(JournalBreakdown(
                dimension, value, len(group),
                sum(item.outcome is FactualOutcome.POSITIVE_PNL for item in group),
                sum(item.outcome is FactualOutcome.NEGATIVE_PNL for item in group),
                sum(item.outcome is FactualOutcome.FLAT_PNL for item in group),
                sum((item.gross_pnl for item in group if item.gross_pnl is not None), Decimal(0)),
                None if not realised else sum(realised, Decimal(0)) / len(realised),
            ))
    return tuple(results)


def _validation_analytics(readiness, plans, initiations, lifecycle, records):  # type: ignore[no-untyped-def]
    decisions = tuple(item.decision for item in initiations if item.decision is not None)
    events = lifecycle.events
    trades = tuple(item for item in records if item.record_type is JournalRecordType.TRADE)
    return JournalValidationAnalytics(
        opportunities_reviewed=len(readiness),
        ready_for_trade_construction=sum(
            item.step31_eligible
            if type(item) is NativeLayer2ReadinessRecord
            else any(
                plan.readiness_record_sha256 == item.result_sha256
                and plan.readiness_record_identity == _readiness_identity(item)
                for plan in plans
            )
            for item in readiness
        ),
        trade_plans_produced=len(plans),
        paper_decisions=sum(item.decision is SponsorTradeChoice.PAPER for item in decisions),
        live_decisions=sum(item.decision is SponsorTradeChoice.LIVE for item in decisions),
        ignore_decisions=sum(item.decision is SponsorTradeChoice.IGNORE for item in decisions),
        paper_entries_triggered=sum(
            item.mode is SponsorTradeChoice.PAPER
            and item.event_type is LifecycleEventType.PAPER_ENTRY_CAPTURED
            for item in events
        ),
        paper_trades_closed=sum(item.mode is SponsorTradeChoice.PAPER for item in trades),
        live_trades_closed=sum(item.mode is SponsorTradeChoice.LIVE for item in trades),
        unresolved_lifecycle_events=sum(
            item.event_type in {
                LifecycleEventType.EVENT_UNRESOLVED,
                LifecycleEventType.ENTRY_EVENT_UNRESOLVED,
            } for item in events
        ),
        monitoring_outages=sum(
            item.event_type is LifecycleEventType.MONITORING_UNAVAILABLE
            for item in events
        ),
        completed_gross_pnl_sample=tuple(
            item.gross_pnl for item in trades if item.gross_pnl is not None
        ),
        completed_realised_r_sample=tuple(
            item.realised_r for item in trades if item.realised_r is not None
        ),
    )


def _empty_validation() -> JournalValidationAnalytics:
    return JournalValidationAnalytics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, (), ())


def _record(values: dict[str, object]) -> TradeJournalRecord:
    complete = {
        **values, "contract_identity": TRADE_JOURNAL_CONTRACT_ID,
        "contract_version": TRADE_JOURNAL_CONTRACT_VERSION,
        "policy_identity": TRADE_JOURNAL_POLICY_ID,
        "policy_version": TRADE_JOURNAL_POLICY_VERSION,
        "authority": TRADE_JOURNAL_AUTHORITY,
        "cost_model": "GROSS_PNL_NO_FEES_TAXES_BROKERAGE_OR_SLIPPAGE_V0",
    }
    return TradeJournalRecord(**complete, integrity_hash=_digest_payload(complete))  # type: ignore[arg-type]


def _record_from_dict(value: object) -> TradeJournalRecord:
    try:
        data = dict(value)  # type: ignore[arg-type]
        data["record_type"] = JournalRecordType(data["record_type"])
        data["mode"] = SponsorTradeChoice(data["mode"])
        data["direction"] = V1Direction(data["direction"])
        data["outcome"] = FactualOutcome(data["outcome"])
        for name in (
            "model_entry", "model_stop", "analytical_invalidation", "model_target",
            "model_risk_reward", "actual_entry", "actual_exit", "gross_pnl",
            "percentage_result", "realised_r",
        ):
            data[name] = None if data[name] is None else Decimal(data[name])
        for name in ("entry_timestamp", "exit_timestamp", "created_at"):
            data[name] = None if data[name] is None else datetime.fromisoformat(data[name])
        data["observed_events"] = tuple(LifecycleEventType(item) for item in data["observed_events"])
        for name in ("lifecycle_event_ids", "lifecycle_event_hashes", "provenance"):
            data[name] = tuple(data[name])
        return TradeJournalRecord(**data)
    except Exception as error:
        raise ValueError("TRADE_JOURNAL_STORED_RECORD_INVALID") from error


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum): return value.value
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, datetime): return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict): return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)): return [_primitive(item) for item in value]
    return value


def _digest_payload(value: object) -> str:
    return sha256(_canonical({**_primitive(value), "integrity_hash": ""})).hexdigest()  # type: ignore[arg-type]


def _record_digest(record: TradeJournalRecord) -> str:
    value = _primitive(record); value["integrity_hash"] = ""  # type: ignore[index]
    return sha256(_canonical(value)).hexdigest()


def _id(prefix: str, *parts: str) -> str:
    return prefix + "-" + sha256("|".join(parts).encode()).hexdigest()


def _read(path: Path) -> dict[str, object]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error: raise ValueError("TRADE_JOURNAL_STORED_RECORD_INVALID") from error
    if type(value) is not dict or value.get("schema") != TRADE_JOURNAL_STORE_SCHEMA or type(value.get("record")) is not dict:
        raise ValueError("TRADE_JOURNAL_STORED_RECORD_INVALID")
    return value


def _atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _identity(value: object) -> bool:
    return type(value) is str and 1 <= len(value) <= 512 and all(character.isalnum() or character in "_.:@|+/-&" for character in value)


def _digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _decimal(value: object) -> Decimal:
    try: actual = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error: raise ValueError("TRADE_JOURNAL_DECIMAL_INVALID") from error
    if not actual.is_finite(): raise ValueError("TRADE_JOURNAL_DECIMAL_INVALID")
    return actual


def _positive(value: object) -> Decimal:
    actual = _decimal(value)
    if actual <= 0: raise ValueError("TRADE_JOURNAL_POSITIVE_DECIMAL_REQUIRED")
    return actual


__all__ = [
    "FactualOutcome", "JournalBreakdown", "JournalRecordType",
    "JournalValidationAnalytics",
    "LocalTradeJournalStore", "TRADE_JOURNAL_CONTRACT_ID",
    "TRADE_JOURNAL_POLICY_ID", "TradeJournalAnalytics",
    "TradeJournalRecord", "TradeJournalService", "TradeJournalSnapshot",
    "calculate_journal_analytics",
]
