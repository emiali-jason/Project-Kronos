"""Contract-bound MCX plan and isolated Sponsor admission.

This module deliberately has no Browser or production composition ingress.
The only currently supported qualification origin is an explicit isolated
fixture; ``MCX_STEP31_NOT_COMMISSIONED`` remains the production gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.swing.v1.mcx_contract_profile import McxFamily, mcx_unit_profile
from kronos.swing.v1.mcx_quantity import (
    McxQuantityProofOrigin, McxTypedQuantity, quantity_from_dict,
)
from kronos.swing.v1.mcx_prepared_plan_store import McxPreparedPlanEvidence
from kronos.swing.v1.mcx_step31_construction import (
    McxContractProofPrerequisites, McxOneHourGeometry, McxPendingPlan,
    McxProofOrigin, McxQuantitySemantics,
)
from kronos.swing.v1.mcx_step31_prepared_handoff import McxStep31PreparedHandoff
from kronos.swing.v1.mcx_contract_selection import McxSponsorContractSelection
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_discovery import NativeOpportunityIdentity
from kronos.swing.v1.native_trade_construction import TradePlanStatus
from kronos.swing.v1.native_sponsor_decision import (
    LocalSponsorDecisionStore, SponsorInitiationResult, SponsorInitiationState,
    SponsorExecutionMode, SponsorTradeChoice, _decision_record, _id,
    _object_digest, _position_record,
    _require_judgment, _require_risk,
)
from kronos.swing.v1.step32 import BusinessJudgment, RiskApproval, RiskState


MCX_TRADE_PLAN_CONTRACT = "KRONOS-SWING-MCX-TRADE-PLAN-V1"
MCX_TRADE_PLAN_AUTHORITY = "ISOLATED_FIXTURE_ONLY_NO_PRODUCTION_ENTRY"
MCX_V1_ADVISORY_AUTHORITY = "MCX_V1_ADVISORY_NO_BROKER_AUTHORITY"


class McxTradeSetup(StrEnum):
    ONE_HOUR_RESUMPTION = "MCX_ONE_HOUR_RESUMPTION"


def _primitive(value: object) -> object:
    if is_dataclass(value):
        return _primitive(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {key: _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _digest(fields: dict[str, object]) -> str:
    return sha256(json.dumps(_primitive(fields), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class McxIsolatedAdmissionFacts:
    """Explicit fixture adapter for unavailable external and policy facts."""

    effective_specification_sha256: str
    quote_quantity_per_lot: Decimal
    provider_quantity_semantics: McxQuantitySemantics
    expiry_session_identity: str
    entry_blackout_policy_identity: str
    one_hour_invalidation_policy_identity: str
    sponsor_risk_policy_identity: str
    paper_choice_policy_identity: str
    maximum_stop_risk: Decimal
    margin_policy_identity: str
    quantity: McxTypedQuantity
    origin: McxProofOrigin = McxProofOrigin.ISOLATED_FIXTURE

    def __post_init__(self) -> None:
        if (
            self.origin is not McxProofOrigin.ISOLATED_FIXTURE
            or len(self.effective_specification_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.effective_specification_sha256)
            or type(self.provider_quantity_semantics) is not McxQuantitySemantics
            or self.provider_quantity_semantics is McxQuantitySemantics.UNKNOWN
            or any(not value for value in (
                self.expiry_session_identity, self.entry_blackout_policy_identity,
                self.one_hour_invalidation_policy_identity,
                self.sponsor_risk_policy_identity, self.paper_choice_policy_identity,
                self.margin_policy_identity,
            ))
            or type(self.quote_quantity_per_lot) is not Decimal
            or self.quote_quantity_per_lot <= 0
            or self.quote_quantity_per_lot != self.quote_quantity_per_lot.to_integral_value()
            or type(self.maximum_stop_risk) is not Decimal
            or self.maximum_stop_risk <= 0
            or type(self.quantity) is not McxTypedQuantity
            or self.quantity.proof_origin is not McxQuantityProofOrigin.ISOLATED_FIXTURE
            or self.quantity.rupees_per_price_point_per_lot != self.quote_quantity_per_lot
            or self.quantity.provider_order_unit != self.provider_quantity_semantics.value
        ):
            raise ValueError("MCX_ISOLATED_ADMISSION_FACTS_INVALID")


@dataclass(frozen=True, slots=True)
class McxTradePlanRecord:
    """Durable Trade Plan, distinct from the non-actionable prepared proposal."""

    trade_plan_id: str
    native_run_identity: str
    native_opportunity_identity: NativeOpportunityIdentity
    canonical_instrument: str
    native_direction: V1Direction
    readiness_record_identity: str
    observation_boundary: datetime
    setup_identity: McxTradeSetup
    entry: Decimal
    stop: Decimal
    invalidation_reference: Decimal
    invalidation_condition: str
    canonical_target: Decimal
    risk_reward_ratio: Decimal
    execution_context_identity: str
    family: McxFamily
    contract_symbol: str
    expiry: str
    entry_eligibility_boundary: datetime
    manifest_sha256: str
    assessment_sha256: str
    selection_sha256: str
    handoff_integrity_sha256: str
    receipt_integrity_sha256: str
    promotion_integrity_sha256: str
    completed_one_hour_sha256: str
    provider_record_identity: str
    provider_snapshot_identity: str
    normalized_instrument_sha256: str
    effective_specification_sha256: str | None
    quote_quantity_per_lot: Decimal | None
    quantity: McxTypedQuantity | None
    provider_quantity_semantics: McxQuantitySemantics
    expiry_session_identity: str
    entry_blackout_policy_identity: str
    one_hour_invalidation_policy_identity: str
    sponsor_risk_policy_identity: str
    paper_choice_policy_identity: str
    maximum_stop_risk: Decimal | None
    margin_policy_identity: str
    created_at: datetime
    integrity_hash: str
    contract_identity: str = MCX_TRADE_PLAN_CONTRACT
    contract_version: str = "1"
    authority: str = MCX_TRADE_PLAN_AUTHORITY

    @property
    def geometry_viability(self) -> TradePlanStatus:
        return TradePlanStatus.TRADE_PLAN_READY

    def __post_init__(self) -> None:
        fields = asdict(self)
        fields["integrity_hash"] = ""
        id_fields = dict(fields)
        id_fields["trade_plan_id"] = ""
        common_invalid = (
            self.contract_identity != MCX_TRADE_PLAN_CONTRACT
            or self.contract_version != "1"
            or self.authority not in {MCX_TRADE_PLAN_AUTHORITY, MCX_V1_ADVISORY_AUTHORITY}
            or self.canonical_instrument != self.family.value
            or self.native_direction not in (V1Direction.LONG, V1Direction.SHORT)
            or self.invalidation_reference != self.stop
            or not self.invalidation_condition.startswith("COMPLETED_MCX_1H_CLOSE_")
            or not self.one_hour_invalidation_policy_identity
            or self.observation_boundary.tzinfo is None
            or self.entry_eligibility_boundary.tzinfo is None
            or self.entry_eligibility_boundary.date() > date.fromisoformat(self.expiry)
            or self.created_at.tzinfo is None
            or self.created_at >= self.entry_eligibility_boundary
            or self.created_at.date() > date.fromisoformat(self.expiry)
            or type(self.provider_quantity_semantics) is not McxQuantitySemantics
            or any(len(value) != 64 for value in (
                self.manifest_sha256, self.assessment_sha256,
                self.selection_sha256, self.handoff_integrity_sha256,
                self.receipt_integrity_sha256, self.promotion_integrity_sha256,
                self.completed_one_hour_sha256, self.normalized_instrument_sha256,
            ))
            or self.integrity_hash != _digest(fields)
            or self.trade_plan_id != "MCX-TRADE-PLAN-" + _digest(id_fields)
        )
        strict_invalid = False
        if self.authority == MCX_TRADE_PLAN_AUTHORITY:
            strict_invalid = (
                type(self.quote_quantity_per_lot) is not Decimal
                or self.quote_quantity_per_lot <= 0
                or type(self.quantity) is not McxTypedQuantity
                or self.quantity.rupees_per_price_point_per_lot != self.quote_quantity_per_lot
                or self.quantity.lots != 1
                or self.quantity.proof_origin is not McxQuantityProofOrigin.ISOLATED_FIXTURE
                or self.quantity.provider_order_unit != self.provider_quantity_semantics.value
                or self.quantity.physical_quantity_per_lot != mcx_unit_profile(self.family).trading_quantity
                or self.quantity.physical_unit != mcx_unit_profile(self.family).trading_unit
                or self.quantity.quotation_base_quantity != mcx_unit_profile(self.family).quotation_quantity
                or self.quantity.quotation_unit != mcx_unit_profile(self.family).quotation_unit
                or type(self.maximum_stop_risk) is not Decimal
                or self.maximum_stop_risk <= 0
                or self.effective_specification_sha256 is None
                or len(self.effective_specification_sha256) != 64
            )
        else:
            strict_invalid = (
                self.quantity is not None
                or self.quote_quantity_per_lot is not None
                or self.maximum_stop_risk is not None
                or self.effective_specification_sha256 is not None
                or self.provider_quantity_semantics is not McxQuantitySemantics.UNKNOWN
                or self.entry_blackout_policy_identity != "UNKNOWN"
                or self.margin_policy_identity != "UNKNOWN"
            )
        if common_invalid or strict_invalid:
            raise ValueError("MCX_TRADE_PLAN_INVALID")


class LocalMcxTradePlanStore:
    """Append-only, restart-verifiable contract-bound Trade Plans."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("MCX_TRADE_PLAN_STORE_INVALID")
        self._lock = RLock()

    def _path(self, record: McxTradePlanRecord) -> Path:
        if any("/" in value or ".." in value for value in (
            record.native_run_identity, record.contract_symbol,
        )):
            raise ValueError("MCX_TRADE_PLAN_PATH_INVALID")
        return (self.root / record.native_run_identity / record.family.value
                / (record.trade_plan_id + ".json"))

    def retain(self, record: McxTradePlanRecord) -> Path:
        if type(record) is not McxTradePlanRecord:
            raise TypeError("MCX_TRADE_PLAN_INVALID")
        path = self._path(record)
        payload = (json.dumps({"schema": MCX_TRADE_PLAN_CONTRACT,
                              "record": _primitive(asdict(record))},
                              sort_keys=True, separators=(",", ":")) + "\n").encode()
        with self._lock:
            if path.exists():
                if path.is_symlink() or path.read_bytes() != payload:
                    raise ValueError("MCX_TRADE_PLAN_IMMUTABLE")
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            if any(parent.is_symlink() for parent in (
                self.root, self.root / record.native_run_identity, path.parent,
            )):
                raise ValueError("MCX_TRADE_PLAN_STORE_INVALID")
            temporary = path.parent / ("." + record.trade_plan_id + "." + uuid4().hex + ".pending")
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary, path, follow_symlinks=False)
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary.unlink(missing_ok=True)
        return path

    def load(self, path: Path) -> McxTradePlanRecord:
        path = Path(path)
        if (not path.is_relative_to(self.root)
                or any(parent.is_symlink() for parent in (
                    self.root, path.parent.parent, path.parent, path,
                ))):
            raise ValueError("MCX_TRADE_PLAN_INTEGRITY_INVALID")
        try:
            value = json.loads(path.read_bytes())
            if value["schema"] != MCX_TRADE_PLAN_CONTRACT:
                raise ValueError
            data = value["record"]
            for name in ("entry", "stop", "invalidation_reference", "canonical_target",
                         "risk_reward_ratio", "quote_quantity_per_lot", "maximum_stop_risk"):
                if data[name] is not None:
                    data[name] = Decimal(data[name])
            for name in ("observation_boundary", "entry_eligibility_boundary", "created_at"):
                data[name] = datetime.fromisoformat(data[name])
            data["native_opportunity_identity"] = NativeOpportunityIdentity(data["native_opportunity_identity"])
            data["native_direction"] = V1Direction(data["native_direction"])
            data["setup_identity"] = McxTradeSetup(data["setup_identity"])
            data["family"] = McxFamily(data["family"])
            data["provider_quantity_semantics"] = McxQuantitySemantics(data["provider_quantity_semantics"])
            if data["quantity"] is not None:
                data["quantity"] = quantity_from_dict(data["quantity"])
            record = McxTradePlanRecord(**data)
            if path != self._path(record):
                raise ValueError
            return record
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise ValueError("MCX_TRADE_PLAN_INTEGRITY_INVALID") from error


def construct_isolated_mcx_trade_plan(
    prepared: McxPreparedPlanEvidence, pending: McxPendingPlan,
    handoff: McxStep31PreparedHandoff, geometry: McxOneHourGeometry,
    proof: McxContractProofPrerequisites, facts: McxIsolatedAdmissionFacts,
    *, selection_sha256: str, opportunity: NativeOpportunityIdentity,
    created_at: datetime,
) -> McxTradePlanRecord:
    """Build a real plan only from a complete, exact isolated read set."""

    bound = handoff.bound
    if (
        type(prepared) is not McxPreparedPlanEvidence
        or type(pending) is not McxPendingPlan
        or type(handoff) is not McxStep31PreparedHandoff
        or type(geometry) is not McxOneHourGeometry
        or type(proof) is not McxContractProofPrerequisites
        or type(facts) is not McxIsolatedAdmissionFacts
        or type(opportunity) is not NativeOpportunityIdentity
        or proof.origin is not McxProofOrigin.ISOLATED_FIXTURE
        or proof.missing
        or proof.effective_specification_sha256 != facts.effective_specification_sha256
        or proof.quantity_semantics is not facts.provider_quantity_semantics
        or proof.expiry_session_identity != facts.expiry_session_identity
        or proof.entry_blackout_policy_identity != facts.entry_blackout_policy_identity
        or proof.expiry_eligibility_boundary is None
        or created_at >= proof.expiry_eligibility_boundary
        or created_at.date() > date.fromisoformat(proof.expiry)
        or proof.expiry_eligibility_boundary.date() > date.fromisoformat(proof.expiry)
        or pending.run_identity != bound.run_identity
        or pending.handoff_integrity_sha256 != handoff.integrity_sha256
        or prepared.plan_id != McxPreparedPlanEvidence.create(pending, handoff).plan_id
        or (prepared.family, prepared.contract_symbol, prepared.expiry)
           != (proof.family, proof.trading_symbol, proof.expiry)
        or geometry.completed_one_hour_sha256 != bound.completed_one_hour_sha256
        or geometry.completed_one_hour_boundary != bound.completed_one_hour_boundary
        or pending.risk.quote_quantity_per_lot != facts.quote_quantity_per_lot
        or pending.risk.maximum_stop_risk != facts.maximum_stop_risk
        or pending.risk.stop_risk > facts.maximum_stop_risk
        or pending.risk.stop_risk != abs(geometry.entry - geometry.stop) * facts.quote_quantity_per_lot
        or pending.risk.notional != geometry.entry * facts.quote_quantity_per_lot
        or pending.risk.lots != 1
        or pending.risk.physical_quantity != facts.quantity.physical_quantity
        or pending.risk.physical_unit != facts.quantity.physical_unit
        or pending.risk.quotation_base_quantity != facts.quantity.quotation_base_quantity
        or pending.risk.quotation_unit != facts.quantity.quotation_unit
        or pending.risk.price_to_rupee_multiplier != facts.quantity.price_to_rupee_multiplier
        or facts.quantity.lots != pending.risk.lots
        or facts.quantity.physical_quantity_per_lot != mcx_unit_profile(bound.family).trading_quantity
        or facts.quantity.physical_unit != mcx_unit_profile(bound.family).trading_unit
        or facts.quantity.quotation_base_quantity != mcx_unit_profile(bound.family).quotation_quantity
        or facts.quantity.quotation_unit != mcx_unit_profile(bound.family).quotation_unit
        or facts.quantity.provider_order_unit != proof.quantity_semantics.value
        or len(selection_sha256) != 64
    ):
        raise ValueError("MCX_TRADE_PLAN_QUALIFICATION_INVALID")
    direction = V1Direction(bound.direction)
    risk = abs(geometry.entry - geometry.stop)
    reward = abs(geometry.target - geometry.entry)
    values = dict(
        native_run_identity=bound.run_identity, native_opportunity_identity=opportunity,
        canonical_instrument=bound.family.value, native_direction=direction,
        readiness_record_identity=bound.promotion_identity,
        observation_boundary=bound.completed_one_hour_boundary,
        setup_identity=McxTradeSetup.ONE_HOUR_RESUMPTION,
        entry=geometry.entry, stop=geometry.stop,
        invalidation_reference=geometry.stop,
        invalidation_condition="COMPLETED_MCX_1H_CLOSE_BEYOND_STOP",
        canonical_target=geometry.target, risk_reward_ratio=reward / risk,
        execution_context_identity=proof.provider_record_identity,
        family=bound.family, contract_symbol=bound.derivative_symbol,
        expiry=bound.derivative_expiry, manifest_sha256=bound.manifest_sha256,
        entry_eligibility_boundary=proof.expiry_eligibility_boundary,
        assessment_sha256=bound.assessment_sha256,
        selection_sha256=selection_sha256,
        handoff_integrity_sha256=handoff.integrity_sha256,
        receipt_integrity_sha256=bound.receipt_integrity_sha256,
        promotion_integrity_sha256=bound.promotion_integrity_sha256,
        completed_one_hour_sha256=bound.completed_one_hour_sha256,
        provider_record_identity=proof.provider_record_identity,
        provider_snapshot_identity=proof.provider_snapshot_identity,
        normalized_instrument_sha256=proof.normalized_instrument_sha256,
        effective_specification_sha256=facts.effective_specification_sha256,
        quote_quantity_per_lot=facts.quote_quantity_per_lot,
        quantity=facts.quantity,
        provider_quantity_semantics=facts.provider_quantity_semantics,
        expiry_session_identity=facts.expiry_session_identity,
        entry_blackout_policy_identity=facts.entry_blackout_policy_identity,
        one_hour_invalidation_policy_identity=facts.one_hour_invalidation_policy_identity,
        sponsor_risk_policy_identity=facts.sponsor_risk_policy_identity,
        paper_choice_policy_identity=facts.paper_choice_policy_identity,
        maximum_stop_risk=facts.maximum_stop_risk,
        margin_policy_identity=facts.margin_policy_identity,
        created_at=created_at,
    )
    unsigned = dict(values, contract_identity=MCX_TRADE_PLAN_CONTRACT,
                    contract_version="1", authority=MCX_TRADE_PLAN_AUTHORITY,
                    integrity_hash="", trade_plan_id="")
    # The plan ID is not included in the content digest; it is derived from it.
    values["trade_plan_id"] = "MCX-TRADE-PLAN-" + _digest(unsigned)
    unsigned["trade_plan_id"] = values["trade_plan_id"]
    values["integrity_hash"] = _digest(unsigned)
    # A stable plan identifier and digest must not recursively depend on each other.
    return McxTradePlanRecord(**values)


def construct_v1_mcx_advisory_plan(
    handoff: McxStep31PreparedHandoff,
    selection: McxSponsorContractSelection,
    geometry: McxOneHourGeometry,
    *, opportunity: NativeOpportunityIdentity,
    provider_snapshot_identity: str,
    provider_record_identity: str,
    normalized_instrument_sha256: str,
    session_identity: str,
    entry_session_until: datetime,
    created_at: datetime,
) -> McxTradePlanRecord:
    """Construct exact-contract price advice with unknown monetary fields.

    This consumes the already validated Review/V2 handoff. Its caller must
    re-read and compare that handoff under the Review owner's final fence
    immediately before retention. A plan alone never commissions an endpoint.
    """
    if (type(handoff) is not McxStep31PreparedHandoff
            or type(selection) is not McxSponsorContractSelection
            or type(geometry) is not McxOneHourGeometry
            or type(opportunity) is not NativeOpportunityIdentity):
        raise ValueError("MCX_V1_PLAN_INPUT_INVALID")
    bound = handoff.bound
    if ((selection.run_identity, selection.family,
         selection.trading_symbol, selection.expiry)
        != (bound.run_identity, bound.family,
            bound.derivative_symbol, bound.derivative_expiry)
            or bound.promotion_state not in {"BUY_NOW", "SELL_NOW"}
            or bound.direction not in {"LONG", "SHORT"}
            or geometry.completed_one_hour_sha256 != bound.completed_one_hour_sha256
            or geometry.completed_one_hour_boundary != bound.completed_one_hour_boundary
            or not all(len(value) == 64 for value in (
                selection.integrity_sha256, normalized_instrument_sha256))
            or not provider_snapshot_identity or not provider_record_identity
            or not session_identity
            or created_at.tzinfo is None or entry_session_until.tzinfo is None
            or created_at >= entry_session_until
            or created_at.date() > date.fromisoformat(bound.derivative_expiry)
            or not all(type(value) is Decimal and value.is_finite() and value > 0
                       for value in (geometry.entry, geometry.stop, geometry.target))
            or (bound.direction == "LONG" and not geometry.stop < geometry.entry < geometry.target)
            or (bound.direction == "SHORT" and not geometry.target < geometry.entry < geometry.stop)):
        raise ValueError("MCX_V1_PLAN_BINDING_INVALID")
    risk = abs(geometry.entry - geometry.stop)
    reward = abs(geometry.target - geometry.entry)
    values = dict(
        native_run_identity=bound.run_identity,
        native_opportunity_identity=opportunity,
        canonical_instrument=bound.family.value,
        native_direction=V1Direction(bound.direction),
        readiness_record_identity=bound.promotion_identity,
        observation_boundary=bound.completed_one_hour_boundary,
        setup_identity=McxTradeSetup.ONE_HOUR_RESUMPTION,
        entry=geometry.entry, stop=geometry.stop,
        invalidation_reference=geometry.stop,
        invalidation_condition="COMPLETED_MCX_1H_CLOSE_BEYOND_STOP",
        canonical_target=geometry.target, risk_reward_ratio=reward / risk,
        execution_context_identity=provider_record_identity,
        family=bound.family, contract_symbol=bound.derivative_symbol,
        expiry=bound.derivative_expiry, entry_eligibility_boundary=entry_session_until,
        manifest_sha256=bound.manifest_sha256,
        assessment_sha256=bound.assessment_sha256,
        selection_sha256=selection.integrity_sha256,
        handoff_integrity_sha256=handoff.integrity_sha256,
        receipt_integrity_sha256=bound.receipt_integrity_sha256,
        promotion_integrity_sha256=bound.promotion_integrity_sha256,
        completed_one_hour_sha256=bound.completed_one_hour_sha256,
        provider_record_identity=provider_record_identity,
        provider_snapshot_identity=provider_snapshot_identity,
        normalized_instrument_sha256=normalized_instrument_sha256,
        effective_specification_sha256=None,
        quote_quantity_per_lot=None, quantity=None,
        provider_quantity_semantics=McxQuantitySemantics.UNKNOWN,
        expiry_session_identity=session_identity,
        entry_blackout_policy_identity="UNKNOWN",
        one_hour_invalidation_policy_identity="MCX_COMPLETED_1H",
        sponsor_risk_policy_identity="MCX_V1_ADVISORY_NO_NUMERIC_CEILING",
        paper_choice_policy_identity="ONE_VERIFIED_CONTRACT_LOT",
        maximum_stop_risk=None, margin_policy_identity="UNKNOWN",
        created_at=created_at,
    )
    unsigned = dict(values, contract_identity=MCX_TRADE_PLAN_CONTRACT,
        contract_version="1", authority=MCX_V1_ADVISORY_AUTHORITY,
        integrity_hash="", trade_plan_id="")
    values["trade_plan_id"] = "MCX-TRADE-PLAN-" + _digest(unsigned)
    unsigned["trade_plan_id"] = values["trade_plan_id"]
    values["integrity_hash"] = _digest(unsigned)
    return McxTradePlanRecord(**values, authority=MCX_V1_ADVISORY_AUTHORITY)


def admit_isolated_mcx_paper(
    plan: McxTradePlanRecord, judgment: BusinessJudgment, risk: RiskApproval,
    sponsor_store: LocalSponsorDecisionStore, *, current_plan_id: str,
    decided_at: datetime,
) -> SponsorInitiationResult:
    """Reuse durable Sponsor records; paper only, with no broker authority."""

    if type(plan) is not McxTradePlanRecord or plan.authority != MCX_TRADE_PLAN_AUTHORITY:
        raise ValueError("MCX_SPONSOR_PLAN_UNAVAILABLE")
    if current_plan_id != plan.trade_plan_id:
        raise ValueError("MCX_SPONSOR_PLAN_STALE")
    if (decided_at >= plan.entry_eligibility_boundary
            or decided_at.date() > date.fromisoformat(plan.expiry)):
        raise ValueError("MCX_SPONSOR_ENTRY_WINDOW_CLOSED")
    _require_judgment(plan, judgment)
    _require_risk(plan, judgment, risk, decided_at)
    if risk.state is not RiskState.APPROVED or risk.constraints.present:
        raise ValueError("MCX_SPONSOR_RISK_UNAVAILABLE")
    if plan.quantity.proof_origin is not McxQuantityProofOrigin.ISOLATED_FIXTURE:
        raise ValueError("MCX_SPONSOR_QUANTITY_UNAVAILABLE")
    if plan.quantity.stop_risk(plan.entry, plan.stop) > plan.maximum_stop_risk:
        raise ValueError("MCX_SPONSOR_STOP_RISK_EXCEEDED")
    decision_id = _id("SPONSOR-DECISION", plan.trade_plan_id,
                      judgment.business_judgment_id, risk.risk_result_id,
                      SponsorTradeChoice.PAPER.value, "NONE", "1")
    decision = _decision_record(dict(
        decision_id=decision_id, trade_plan_id=plan.trade_plan_id,
        trade_plan_integrity_hash=plan.integrity_hash,
        business_judgment_id=judgment.business_judgment_id,
        business_judgment_hash=_object_digest(judgment), risk_id=risk.risk_result_id,
        risk_hash=_object_digest(risk), native_run_identity=plan.native_run_identity,
        opportunity_identity=plan.native_opportunity_identity.value,
        canonical_instrument=plan.canonical_instrument, direction=plan.native_direction,
        decision=SponsorTradeChoice.PAPER,
        execution_mode=SponsorExecutionMode.MANUAL_SPONSOR_EXECUTION,
        decision_timestamp=decided_at, go_timestamp=decided_at,
        model_entry=plan.entry, stop=plan.stop,
        invalidation=plan.invalidation_reference, target=plan.canonical_target,
        model_risk_reward=plan.risk_reward_ratio, risk_state=risk.state,
        risk_constraints=risk.constraints,
        provenance=(plan.trade_plan_id, judgment.business_judgment_id,
                    risk.risk_result_id, plan.contract_symbol, plan.expiry,
                    plan.paper_choice_policy_identity),
    ))
    position = _position_record(dict(
        position_id=_id("SPONSOR-POSITION", decision_id), decision_id=decision_id,
        trade_plan_id=plan.trade_plan_id, mode=SponsorTradeChoice.PAPER,
        state=SponsorInitiationState.PAPER_ARMED,
        canonical_instrument=plan.canonical_instrument, direction=plan.native_direction,
        lots=plan.quantity.lots, lot_size=1,
        underlying_quantity=plan.quantity.lots,
        mcx_quantity=plan.quantity,
        actual_entry=None, entry_timestamp=None, model_entry=plan.entry,
        stop=plan.stop, invalidation=plan.invalidation_reference,
        target=plan.canonical_target, created_at=decided_at,
        provenance=(decision_id, plan.trade_plan_id, plan.execution_context_identity,
                    plan.contract_symbol, plan.expiry),
    ))
    return sponsor_store.retain(SponsorInitiationResult(
        SponsorInitiationState.PAPER_ARMED, "WAITING_FOR_ENTRY", decision, position,
    ))


def admit_v1_mcx_paper(
    plan: McxTradePlanRecord, judgment: BusinessJudgment, risk: RiskApproval,
    sponsor_store: LocalSponsorDecisionStore, *, current_plan_id: str,
    decided_at: datetime,
) -> SponsorInitiationResult:
    """Arm exactly one advisory PAPER lot; a CMP cannot activate it by itself.

    The monetary risk result is retained as advice. An explicitly rejected
    result or a numeric constraint remains blocking; unavailable rupee facts
    are not silently converted to zero or an approval.
    """
    if (type(plan) is not McxTradePlanRecord
            or plan.authority != MCX_V1_ADVISORY_AUTHORITY
            or current_plan_id != plan.trade_plan_id
            or decided_at.tzinfo is None
            or decided_at < plan.created_at
            or decided_at >= plan.entry_eligibility_boundary
            or decided_at.date() > date.fromisoformat(plan.expiry)):
        raise ValueError("MCX_V1_PAPER_PLAN_UNAVAILABLE")
    _require_judgment(plan, judgment)
    _require_risk(plan, judgment, risk, decided_at)
    if risk.state is RiskState.REJECTED or risk.constraints.present:
        raise ValueError("MCX_V1_PAPER_RISK_REJECTED")
    decision_id = _id("SPONSOR-DECISION", plan.trade_plan_id,
                      judgment.business_judgment_id, risk.risk_result_id,
                      SponsorTradeChoice.PAPER.value, "MCX_V1_ONE_LOT")
    decision = _decision_record(dict(
        decision_id=decision_id, trade_plan_id=plan.trade_plan_id,
        trade_plan_integrity_hash=plan.integrity_hash,
        business_judgment_id=judgment.business_judgment_id,
        business_judgment_hash=_object_digest(judgment),
        risk_id=risk.risk_result_id, risk_hash=_object_digest(risk),
        native_run_identity=plan.native_run_identity,
        opportunity_identity=plan.native_opportunity_identity.value,
        canonical_instrument=plan.canonical_instrument,
        direction=plan.native_direction, decision=SponsorTradeChoice.PAPER,
        execution_mode=SponsorExecutionMode.MANUAL_SPONSOR_EXECUTION,
        decision_timestamp=decided_at, go_timestamp=decided_at,
        model_entry=plan.entry, stop=plan.stop,
        invalidation=plan.invalidation_reference, target=plan.canonical_target,
        model_risk_reward=plan.risk_reward_ratio, risk_state=risk.state,
        risk_constraints=risk.constraints,
        provenance=(plan.trade_plan_id, judgment.business_judgment_id,
                    risk.risk_result_id, plan.contract_symbol, plan.expiry,
                    "MCX_V1_PAPER_ONE_LOT_UNKNOWN_RUPEE_MULTIPLIER"),
    ))
    position = _position_record(dict(
        position_id=_id("SPONSOR-POSITION", decision_id),
        decision_id=decision_id, trade_plan_id=plan.trade_plan_id,
        mode=SponsorTradeChoice.PAPER,
        state=SponsorInitiationState.PAPER_ARMED,
        canonical_instrument=plan.canonical_instrument,
        direction=plan.native_direction, lots=1, lot_size=1,
        underlying_quantity=1, mcx_v1_contract_symbol=plan.contract_symbol,
        actual_entry=None, entry_timestamp=None, model_entry=plan.entry,
        stop=plan.stop, invalidation=plan.invalidation_reference,
        target=plan.canonical_target, created_at=decided_at,
        provenance=(decision_id, plan.trade_plan_id,
                    plan.execution_context_identity, plan.contract_symbol,
                    plan.expiry, "PHYSICAL_QUANTITY_UNKNOWN"),
    ))
    return sponsor_store.retain(SponsorInitiationResult(
        SponsorInitiationState.PAPER_ARMED, "WAITING_FOR_ENTRY",
        decision, position,
    ))
