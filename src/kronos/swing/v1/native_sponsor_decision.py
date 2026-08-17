"""Frozen Step-32 Sponsor decision/initiation for Native Step-31 plans."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock

from kronos.instrument.facts import CanonicalInstrumentContext, InstrumentContextStatus
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.trade_construction import TradeCandidateIntegrity
from kronos.swing.v1.native_trade_construction import TradePlanRecord, TradePlanStatus
from kronos.swing.v1.step32 import (
    BUSINESS_JUDGMENT_CONTRACT_ID,
    CONTRACT_VERSION,
    RISK_APPROVAL_CONTRACT_ID,
    BusinessJudgment,
    Freshness,
    RiskApproval,
    RiskConstraints,
    RiskState,
)


SPONSOR_TRADE_DECISION_POLICY_ID = "SWING-V1-SPONSOR-TRADE-DECISION-V0"
SPONSOR_TRADE_DECISION_POLICY_VERSION = "0"
SPONSOR_TRADE_DECISION_POLICY_STATUS = "FROZEN"
SPONSOR_TRADE_DECISION_CONTRACT_ID = "KRONOS-SWING-V1-SPONSOR-TRADE-DECISION-V0"
SPONSOR_POSITION_CONTRACT_ID = "KRONOS-SWING-V1-SPONSOR-POSITION-V0"
SPONSOR_DECISION_STORE_SCHEMA = "KRONOS-SWING-V1-SPONSOR-DECISION-STORE-V0"
SPONSOR_DECISION_AUTHORITY = "SPONSOR_INITIATION_ONLY_NO_GEOMETRY_MONITORING_OR_BROKER_AUTHORITY"


class SponsorTradeChoice(StrEnum):
    PAPER = "PAPER"
    LIVE = "LIVE"
    IGNORE = "IGNORE"


class SponsorExecutionMode(StrEnum):
    MANUAL_SPONSOR_EXECUTION = "MANUAL_SPONSOR_EXECUTION"
    BROKER_MANAGED_EXECUTION = "BROKER_MANAGED_EXECUTION"


class SponsorInitiationState(StrEnum):
    PAPER_ARMED = "PAPER_ARMED"
    PAPER_ACTIVE = "PAPER_ACTIVE"
    LIVE_ACTIVE = "LIVE_ACTIVE"
    IGNORED = "IGNORED"
    WAITING_FOR_RISK = "WAITING_FOR_RISK"
    DECISION_UNAVAILABLE = "DECISION_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class SponsorTradeDecisionRecord:
    decision_id: str
    trade_plan_id: str
    trade_plan_integrity_hash: str
    business_judgment_id: str
    business_judgment_hash: str
    risk_id: str
    risk_hash: str
    native_run_identity: str
    opportunity_identity: str
    canonical_instrument: str
    direction: V1Direction
    decision: SponsorTradeChoice
    execution_mode: SponsorExecutionMode
    decision_timestamp: datetime
    go_timestamp: datetime | None
    model_entry: Decimal
    stop: Decimal
    invalidation: Decimal
    target: Decimal
    model_risk_reward: Decimal
    risk_state: RiskState
    risk_constraints: RiskConstraints
    provenance: tuple[str, ...]
    integrity_hash: str
    contract_identity: str = SPONSOR_TRADE_DECISION_CONTRACT_ID
    contract_version: str = "0"
    policy_identity: str = SPONSOR_TRADE_DECISION_POLICY_ID
    policy_version: str = SPONSOR_TRADE_DECISION_POLICY_VERSION
    policy_status: str = SPONSOR_TRADE_DECISION_POLICY_STATUS
    authority: str = SPONSOR_DECISION_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not _identity(self.decision_id) or not _identity(self.trade_plan_id)
            or not _digest(self.trade_plan_integrity_hash)
            or not _identity(self.business_judgment_id) or not _digest(self.business_judgment_hash)
            or not _identity(self.risk_id) or not _digest(self.risk_hash)
            or not self.native_run_identity or not self.opportunity_identity
            or not self.canonical_instrument or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or type(self.decision) is not SponsorTradeChoice
            or self.execution_mode is not SponsorExecutionMode.MANUAL_SPONSOR_EXECUTION
            or not _aware(self.decision_timestamp)
            or (self.go_timestamp is not None and not _aware(self.go_timestamp))
            or any(not _positive_decimal(value) for value in (
                self.model_entry, self.stop, self.invalidation, self.target, self.model_risk_reward
            ))
            or type(self.risk_state) is not RiskState or type(self.risk_constraints) is not RiskConstraints
            or not self.provenance or self.contract_identity != SPONSOR_TRADE_DECISION_CONTRACT_ID
            or self.contract_version != "0" or self.policy_identity != SPONSOR_TRADE_DECISION_POLICY_ID
            or self.policy_version != SPONSOR_TRADE_DECISION_POLICY_VERSION
            or self.policy_status != SPONSOR_TRADE_DECISION_POLICY_STATUS
            or self.authority != SPONSOR_DECISION_AUTHORITY
            or not _digest(self.integrity_hash) or self.integrity_hash != _record_digest(self)
        ):
            raise ValueError("SPONSOR_TRADE_DECISION_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorPositionRecord:
    position_id: str
    decision_id: str
    trade_plan_id: str
    mode: SponsorTradeChoice
    state: SponsorInitiationState
    canonical_instrument: str
    direction: V1Direction
    lots: int
    lot_size: int
    underlying_quantity: int
    actual_entry: Decimal | None
    entry_timestamp: datetime | None
    model_entry: Decimal
    stop: Decimal
    invalidation: Decimal
    target: Decimal
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_hash: str
    contract_identity: str = SPONSOR_POSITION_CONTRACT_ID
    contract_version: str = "0"
    authority: str = "SPONSOR_TRACKING_ONLY_NO_BROKER_OR_EXIT_AUTHORITY"

    def __post_init__(self) -> None:
        paper = self.mode is SponsorTradeChoice.PAPER
        if (
            not _identity(self.position_id) or not _identity(self.decision_id)
            or not _identity(self.trade_plan_id) or self.mode not in {SponsorTradeChoice.PAPER, SponsorTradeChoice.LIVE}
            or self.state not in {SponsorInitiationState.PAPER_ARMED, SponsorInitiationState.PAPER_ACTIVE, SponsorInitiationState.LIVE_ACTIVE}
            or not self.canonical_instrument or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or type(self.lots) is not int or self.lots <= 0
            or type(self.lot_size) is not int or self.lot_size <= 0
            or self.underlying_quantity != self.lots * self.lot_size
            or (self.actual_entry is not None and not _positive_decimal(self.actual_entry))
            or (self.entry_timestamp is not None and not _aware(self.entry_timestamp))
            or any(not _positive_decimal(value) for value in (self.model_entry, self.stop, self.invalidation, self.target))
            or (paper and self.state is SponsorInitiationState.PAPER_ARMED and (self.actual_entry is not None or self.entry_timestamp is not None))
            or (self.state is SponsorInitiationState.LIVE_ACTIVE and (self.actual_entry is None or self.entry_timestamp is None))
            or not _aware(self.created_at) or not self.provenance
            or self.contract_identity != SPONSOR_POSITION_CONTRACT_ID or self.contract_version != "0"
            or self.authority != "SPONSOR_TRACKING_ONLY_NO_BROKER_OR_EXIT_AUTHORITY"
            or not _digest(self.integrity_hash) or self.integrity_hash != _record_digest(self)
        ):
            raise ValueError("SPONSOR_POSITION_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorInitiationResult:
    state: SponsorInitiationState
    reason: str
    decision: SponsorTradeDecisionRecord | None = None
    position: SponsorPositionRecord | None = None


def create_trade_plan_business_judgment(
    plan: TradePlanRecord, *, validation_identity: str, created_at: datetime
) -> BusinessJudgment:
    if plan.geometry_viability is not TradePlanStatus.TRADE_PLAN_READY:
        raise ValueError("TRADE_PLAN_NOT_READY")
    return BusinessJudgment(
        BUSINESS_JUDGMENT_CONTRACT_ID, CONTRACT_VERSION,
        _id("BUSINESS-JUDGMENT", plan.trade_plan_id, validation_identity),
        plan.trade_plan_id, plan.contract_identity, plan.contract_version,
        plan.integrity_hash, validation_identity, plan.readiness_record_identity,
        plan.native_run_identity, plan.observation_boundary, Freshness.CURRENT,
        TradeCandidateIntegrity.VALID, created_at,
        (plan.trade_plan_id, validation_identity, "DOMAIN-003"),
        plan.canonical_instrument, None, plan.setup_identity.value, plan.native_direction.value,
    )


def record_trade_plan_risk_result(
    plan: TradePlanRecord, judgment: BusinessJudgment, state: RiskState, *,
    reason: str, evaluated_at: datetime, constraints: RiskConstraints | None = None,
    valid_until: datetime | None = None,
) -> RiskApproval:
    _require_judgment(plan, judgment)
    actual = constraints or RiskConstraints()
    if (state is RiskState.CONSTRAINED) != actual.present:
        raise ValueError("RISK_CONSTRAINT_BINDING_INVALID")
    return RiskApproval(
        RISK_APPROVAL_CONTRACT_ID, CONTRACT_VERSION,
        _id("RISK-RESULT", judgment.business_judgment_id, state.value, evaluated_at.isoformat()),
        plan.trade_plan_id, plan.integrity_hash, judgment.business_judgment_id,
        plan.native_run_identity, state, actual, reason, evaluated_at, valid_until,
        (judgment.business_judgment_id, plan.trade_plan_id, "DOMAIN-007"),
        TradeCandidateIntegrity.VALID,
    )


def initiate_sponsor_decision(
    plan: TradePlanRecord,
    judgment: BusinessJudgment,
    risk: RiskApproval,
    execution_context: CanonicalInstrumentContext,
    choice: SponsorTradeChoice,
    *,
    current_trade_plan_id: str,
    decided_at: datetime,
    actual_live_entry: Decimal | None = None,
    live_lots: int | None = None,
    paper_lots: int | None = None,
    execution_mode: SponsorExecutionMode = SponsorExecutionMode.MANUAL_SPONSOR_EXECUTION,
) -> SponsorInitiationResult:
    """Record Sponsor intent and initiation; never place an order or monitor Entry."""

    unavailable = _gate(plan, judgment, risk, execution_context, current_trade_plan_id, decided_at)
    if unavailable is not None:
        return unavailable
    if execution_mode is not SponsorExecutionMode.MANUAL_SPONSOR_EXECUTION:
        return SponsorInitiationResult(SponsorInitiationState.DECISION_UNAVAILABLE, "BROKER_MANAGED_EXECUTION_RESERVED")
    if risk.state is RiskState.UNAVAILABLE:
        return SponsorInitiationResult(SponsorInitiationState.WAITING_FOR_RISK, "RISK_UNAVAILABLE")
    if risk.state is RiskState.REJECTED:
        return SponsorInitiationResult(SponsorInitiationState.DECISION_UNAVAILABLE, "RISK_REJECTED")
    assert execution_context.lot_size is not None
    if choice is SponsorTradeChoice.PAPER:
        if paper_lots is not None and paper_lots != 1:
            return SponsorInitiationResult(SponsorInitiationState.DECISION_UNAVAILABLE, "PAPER_QUANTITY_LOCKED_TO_ONE_LOT")
        lots, actual_entry, entry_time = 1, None, None
        state = SponsorInitiationState.PAPER_ARMED
    elif choice is SponsorTradeChoice.LIVE:
        if not _positive_decimal(actual_live_entry):
            return SponsorInitiationResult(SponsorInitiationState.DECISION_UNAVAILABLE, "LIVE_ACTUAL_ENTRY_REQUIRED")
        if type(live_lots) is not int or live_lots <= 0:
            return SponsorInitiationResult(SponsorInitiationState.DECISION_UNAVAILABLE, "LIVE_POSITIVE_INTEGER_LOTS_REQUIRED")
        lots, actual_entry, entry_time = live_lots, actual_live_entry, decided_at
        state = SponsorInitiationState.LIVE_ACTIVE
    else:
        lots, actual_entry, entry_time = 0, None, None
        state = SponsorInitiationState.IGNORED

    if choice is not SponsorTradeChoice.IGNORE:
        reason = _constraint_failure(plan, risk.constraints, lots, execution_context.lot_size, actual_entry)
        if reason is not None:
            return SponsorInitiationResult(SponsorInitiationState.DECISION_UNAVAILABLE, reason)

    decision_id = _id(
        "SPONSOR-DECISION", plan.trade_plan_id, judgment.business_judgment_id,
        risk.risk_result_id, choice.value,
        str(actual_entry) if actual_entry is not None else "NONE", str(lots),
    )
    decision_fields = dict(
        decision_id=decision_id, trade_plan_id=plan.trade_plan_id,
        trade_plan_integrity_hash=plan.integrity_hash,
        business_judgment_id=judgment.business_judgment_id,
        business_judgment_hash=_object_digest(judgment), risk_id=risk.risk_result_id,
        risk_hash=_object_digest(risk), native_run_identity=plan.native_run_identity,
        opportunity_identity=plan.native_opportunity_identity.value,
        canonical_instrument=plan.canonical_instrument, direction=plan.native_direction,
        decision=choice, execution_mode=execution_mode,
        decision_timestamp=decided_at,
        go_timestamp=None if choice is SponsorTradeChoice.IGNORE else decided_at,
        model_entry=plan.entry, stop=plan.stop, invalidation=plan.invalidation_reference,
        target=plan.canonical_target, model_risk_reward=plan.risk_reward_ratio,
        risk_state=risk.state, risk_constraints=risk.constraints,
        provenance=(plan.trade_plan_id, judgment.business_judgment_id, risk.risk_result_id, "SPONSOR_ATTESTATION"),
    )
    decision = _decision_record(decision_fields)
    if choice is SponsorTradeChoice.IGNORE:
        return SponsorInitiationResult(state, "SPONSOR_IGNORED_EXACT_TRADE_PLAN", decision, None)
    position_fields = dict(
        position_id=_id("SPONSOR-POSITION", decision_id), decision_id=decision_id,
        trade_plan_id=plan.trade_plan_id, mode=choice, state=state,
        canonical_instrument=plan.canonical_instrument, direction=plan.native_direction,
        lots=lots, lot_size=execution_context.lot_size,
        underlying_quantity=lots * execution_context.lot_size,
        actual_entry=actual_entry, entry_timestamp=entry_time,
        model_entry=plan.entry, stop=plan.stop, invalidation=plan.invalidation_reference,
        target=plan.canonical_target, created_at=decided_at,
        provenance=(decision_id, plan.trade_plan_id, execution_context.identity),
    )
    position = _position_record(position_fields)
    reason = "WAITING_FOR_ENTRY" if state is SponsorInitiationState.PAPER_ARMED else "SPONSOR_ATTESTED_LIVE_POSITION_REGISTERED"
    return SponsorInitiationResult(state, reason, decision, position)


def validate_step32_inputs(
    plan: TradePlanRecord,
    judgment: BusinessJudgment,
    risk: RiskApproval,
    execution_context: CanonicalInstrumentContext,
    *,
    current_trade_plan_id: str,
    validated_at: datetime,
) -> None:
    result = _gate(
        plan, judgment, risk, execution_context, current_trade_plan_id, validated_at
    )
    if result is not None:
        raise ValueError(result.reason)
    if risk.state not in {RiskState.APPROVED, RiskState.CONSTRAINED}:
        raise ValueError(risk.state.value)


class LocalSponsorDecisionStore:
    """One immutable Sponsor decision per exact Trade Plan, restart-safe."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("SPONSOR_DECISION_STORE_INVALID")
        self._lock = RLock()

    def retain(self, result: SponsorInitiationResult) -> SponsorInitiationResult:
        if result.decision is None:
            return result
        plan_dir = self.root / result.decision.native_run_identity / result.decision.trade_plan_id
        decision_path = plan_dir / "decision.json"
        position_path = plan_dir / "position.json"
        payload = {"schema": SPONSOR_DECISION_STORE_SCHEMA, "record": _primitive(result.decision)}
        position_payload = None if result.position is None else {
            "schema": SPONSOR_DECISION_STORE_SCHEMA, "record": _primitive(result.position)
        }
        with self._lock:
            if decision_path.exists():
                restored = self.load_plan(result.decision.native_run_identity, result.decision.trade_plan_id)
                if restored != result:
                    raise ValueError("SPONSOR_DECISION_ALREADY_FINAL")
                return restored
            _atomic(decision_path, payload)
            if position_payload is not None:
                _atomic(position_path, position_payload)
        return result

    def load_plan(self, run_id: str, trade_plan_id: str) -> SponsorInitiationResult:
        root = self.root / run_id / trade_plan_id
        decision_payload = _read(root / "decision.json")
        decision = _decision_from_dict(decision_payload.get("record"))
        position = None
        if (root / "position.json").exists():
            position = _position_from_dict(_read(root / "position.json").get("record"))
        state = SponsorInitiationState.IGNORED if position is None else position.state
        reason = "SPONSOR_IGNORED_EXACT_TRADE_PLAN" if position is None else (
            "WAITING_FOR_ENTRY" if state is SponsorInitiationState.PAPER_ARMED else "SPONSOR_ATTESTED_LIVE_POSITION_REGISTERED"
        )
        return SponsorInitiationResult(state, reason, decision, position)

    def load_for_plans(self, plans: tuple[TradePlanRecord, ...]) -> tuple[SponsorInitiationResult, ...]:
        values = []
        for plan in plans:
            path = self.root / plan.native_run_identity / plan.trade_plan_id / "decision.json"
            if path.exists():
                result = self.load_plan(plan.native_run_identity, plan.trade_plan_id)
                if result.decision is None or result.decision.trade_plan_integrity_hash != plan.integrity_hash:
                    raise ValueError("SPONSOR_DECISION_RESTART_BINDING_INVALID")
                values.append(result)
        return tuple(values)


def _gate(plan, judgment, risk, context, current_plan_id, now):  # type: ignore[no-untyped-def]
    if type(plan) is not TradePlanRecord or plan.geometry_viability is not TradePlanStatus.TRADE_PLAN_READY:
        return SponsorInitiationResult(SponsorInitiationState.DECISION_UNAVAILABLE, "TRADE_PLAN_NOT_READY")
    if current_plan_id != plan.trade_plan_id:
        return SponsorInitiationResult(SponsorInitiationState.DECISION_UNAVAILABLE, "TRADE_PLAN_SUPERSEDED")
    try:
        _require_judgment(plan, judgment)
        _require_risk(plan, judgment, risk, now)
    except ValueError as error:
        return SponsorInitiationResult(SponsorInitiationState.DECISION_UNAVAILABLE, str(error))
    if (
        type(context) is not CanonicalInstrumentContext
        or context.status is not InstrumentContextStatus.COMPLETE
        or context.identity != plan.execution_context_identity
        or context.canonical_instrument != plan.canonical_instrument
        or context.lot_size is None or context.lot_size <= 0
        or context.tick_size != plan.tick_size or context.price_precision != plan.price_precision
    ):
        return SponsorInitiationResult(SponsorInitiationState.DECISION_UNAVAILABLE, "EXECUTION_CONTEXT_INCOMPLETE")
    return None


def _require_judgment(plan: TradePlanRecord, judgment: BusinessJudgment) -> None:
    if (
        type(judgment) is not BusinessJudgment or judgment.candidate_id != plan.trade_plan_id
        or judgment.candidate_contract_identity != plan.contract_identity
        or judgment.candidate_contract_version != plan.contract_version
        or judgment.candidate_digest != plan.integrity_hash
        or judgment.readiness_identity != plan.readiness_record_identity
        or judgment.run_id != plan.native_run_identity
        or judgment.market_data_boundary != plan.observation_boundary
        or judgment.freshness is not Freshness.CURRENT
        or judgment.integrity is not TradeCandidateIntegrity.VALID
        or judgment.canonical_instrument_echo != plan.canonical_instrument
        or judgment.setup_echo != plan.setup_identity.value
        or judgment.direction_echo != plan.native_direction.value
    ):
        raise ValueError("BUSINESS_JUDGMENT_BINDING_INVALID")


def _require_risk(plan: TradePlanRecord, judgment: BusinessJudgment, risk: RiskApproval, now: datetime) -> None:
    if (
        type(risk) is not RiskApproval or risk.candidate_id != plan.trade_plan_id
        or risk.candidate_digest != plan.integrity_hash
        or risk.business_judgment_id != judgment.business_judgment_id
        or risk.run_id != plan.native_run_identity
        or risk.integrity is not TradeCandidateIntegrity.VALID
        or (risk.valid_until is not None and risk.valid_until < now)
    ):
        raise ValueError("RISK_BINDING_INVALID")


def _constraint_failure(plan, constraints, lots, lot_size, actual_entry):  # type: ignore[no-untyped-def]
    quantity = Decimal(lots * lot_size)
    entry = actual_entry if actual_entry is not None else plan.entry
    if constraints.maximum_lots is not None and lots > constraints.maximum_lots:
        return "RISK_MAXIMUM_LOTS_EXCEEDED"
    if constraints.maximum_quantity is not None and quantity > constraints.maximum_quantity:
        return "RISK_MAXIMUM_QUANTITY_EXCEEDED"
    if constraints.maximum_notional is not None and entry * quantity > constraints.maximum_notional:
        return "RISK_MAXIMUM_NOTIONAL_EXCEEDED"
    risk_per_unit = abs(entry - plan.stop)
    if constraints.maximum_capital_at_risk is not None and risk_per_unit * quantity > constraints.maximum_capital_at_risk:
        return "RISK_MAXIMUM_CAPITAL_AT_RISK_EXCEEDED"
    if any(value is not None for value in (
        constraints.maximum_margin, constraints.maximum_exposure, constraints.maximum_concentration
    )):
        return "RISK_CONSTRAINT_REQUIRES_UNAVAILABLE_PORTFOLIO_FACT"
    return None


def _decision_record(fields):  # type: ignore[no-untyped-def]
    fields = {
        **fields,
        "contract_identity": SPONSOR_TRADE_DECISION_CONTRACT_ID,
        "contract_version": "0",
        "policy_identity": SPONSOR_TRADE_DECISION_POLICY_ID,
        "policy_version": SPONSOR_TRADE_DECISION_POLICY_VERSION,
        "policy_status": SPONSOR_TRADE_DECISION_POLICY_STATUS,
        "authority": SPONSOR_DECISION_AUTHORITY,
    }
    return SponsorTradeDecisionRecord(
        integrity_hash=sha256(_canonical({**_primitive(fields), "integrity_hash": ""})).hexdigest(), **fields
    )


def _position_record(fields):  # type: ignore[no-untyped-def]
    fields = {
        **fields,
        "contract_identity": SPONSOR_POSITION_CONTRACT_ID,
        "contract_version": "0",
        "authority": "SPONSOR_TRACKING_ONLY_NO_BROKER_OR_EXIT_AUTHORITY",
    }
    return SponsorPositionRecord(
        integrity_hash=sha256(_canonical({**_primitive(fields), "integrity_hash": ""})).hexdigest(), **fields
    )


def _record_digest(record) -> str:  # type: ignore[no-untyped-def]
    payload = _primitive(record); payload["integrity_hash"] = ""
    return sha256(_canonical(payload)).hexdigest()


def _object_digest(value: object) -> str:
    return sha256(_canonical(_primitive(value))).hexdigest()


def _id(prefix: str, *parts: str) -> str:
    return prefix + "-" + sha256("|".join(parts).encode()).hexdigest()


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum): return value.value
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, datetime): return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict): return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)): return [_primitive(item) for item in value]
    return value


def _decision_from_dict(value):  # type: ignore[no-untyped-def]
    try:
        data = dict(value)
        for name in ("model_entry", "stop", "invalidation", "target", "model_risk_reward"):
            data[name] = Decimal(data[name])
        data["direction"] = V1Direction(data["direction"]); data["decision"] = SponsorTradeChoice(data["decision"])
        data["execution_mode"] = SponsorExecutionMode(data["execution_mode"]); data["risk_state"] = RiskState(data["risk_state"])
        data["decision_timestamp"] = datetime.fromisoformat(data["decision_timestamp"])
        data["go_timestamp"] = None if data["go_timestamp"] is None else datetime.fromisoformat(data["go_timestamp"])
        data["provenance"] = tuple(data["provenance"]); data["risk_constraints"] = RiskConstraints(**data["risk_constraints"])
        return SponsorTradeDecisionRecord(**data)
    except Exception as error: raise ValueError("SPONSOR_DECISION_STORED_RECORD_INVALID") from error


def _position_from_dict(value):  # type: ignore[no-untyped-def]
    try:
        data = dict(value)
        for name in ("actual_entry", "model_entry", "stop", "invalidation", "target"):
            data[name] = None if data[name] is None else Decimal(data[name])
        data["mode"] = SponsorTradeChoice(data["mode"]); data["state"] = SponsorInitiationState(data["state"])
        data["direction"] = V1Direction(data["direction"])
        for name in ("entry_timestamp", "created_at"):
            data[name] = None if data[name] is None else datetime.fromisoformat(data[name])
        data["provenance"] = tuple(data["provenance"])
        return SponsorPositionRecord(**data)
    except Exception as error: raise ValueError("SPONSOR_POSITION_STORED_RECORD_INVALID") from error


def _read(path: Path) -> dict[str, object]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error: raise ValueError("SPONSOR_DECISION_STORED_RECORD_INVALID") from error
    if type(value) is not dict or value.get("schema") != SPONSOR_DECISION_STORE_SCHEMA:
        raise ValueError("SPONSOR_DECISION_STORED_RECORD_INVALID")
    return value


def _atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally: temporary.unlink(missing_ok=True)


def _canonical(value: object) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
def _identity(value: object) -> bool: return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:@|+/-]{1,512}", value) is not None
def _digest(value: object) -> bool: return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None
def _aware(value: object) -> bool: return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
def _positive_decimal(value: object) -> bool:
    try: actual = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError): return False
    return actual.is_finite() and actual > 0


__all__ = [
    "LocalSponsorDecisionStore", "SPONSOR_TRADE_DECISION_POLICY_ID",
    "SponsorExecutionMode", "SponsorInitiationResult", "SponsorInitiationState",
    "SponsorPositionRecord", "SponsorTradeChoice", "SponsorTradeDecisionRecord",
    "create_trade_plan_business_judgment", "initiate_sponsor_decision",
    "record_trade_plan_risk_result", "validate_step32_inputs",
]
