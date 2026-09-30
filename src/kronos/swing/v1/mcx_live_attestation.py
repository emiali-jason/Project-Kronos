"""Fixture-only, exact-contract Sponsor fill evidence for isolated MCX admission.

No Browser or production composition installs this owner. A retained attestation
precedes, and cannot by itself create, a LIVE Sponsor position or broker order.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_trade_plan import (
    MCX_V1_ADVISORY_AUTHORITY, McxTradePlanRecord,
)
from kronos.swing.v1.mcx_quantity import McxQuantityProofOrigin
from kronos.swing.v1.native_entry_timing import (
    Kr380EntryOutcomeV2, Kr380V2State, LocalKr380V2Store,
)
from kronos.swing.v1.native_sponsor_decision import (
    LocalSponsorDecisionStore, SponsorInitiationResult, SponsorInitiationState,
    SponsorExecutionMode, SponsorTradeChoice, _decision_record, _id,
    _object_digest, _position_record, _require_judgment, _require_risk,
)
from kronos.swing.v1.step32 import BusinessJudgment, RiskApproval, RiskState
from kronos.swing.v1.mcx_v1_advisory import (
    ADVISORY_RULE_ID, McxAdvisoryState, McxV1AdvisoryOutcome,
    LocalMcxV1AdvisoryStore,
)


SCHEMA = "KRONOS-SWING-MCX-LIVE-FILL-ATTESTATION-V1"
EXIT_INTENT_SCHEMA = "KRONOS-SWING-MCX-LIVE-EXIT-INTENT-V1"


def _payload(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class McxLiveFillAttestation:
    plan_id: str
    plan_sha256: str
    run_identity: str
    family: McxFamily
    contract_symbol: str
    expiry: str
    lots: int
    provider_order_quantity: int | None
    entry_outcome_id: str | None
    entry_outcome_sha256: str | None
    entry_outcome_at: datetime | None
    fill_price: Decimal
    fill_at: datetime
    broker_evidence_id: str
    broker_evidence_sha256: str
    attested_at: datetime
    integrity_sha256: str
    v1_manual: bool = False
    model_relation: str = "LEGACY_KR380"

    def __post_init__(self) -> None:
        if (
            not self.plan_id or "/" in self.plan_id or ".." in self.plan_id
            or len(self.plan_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.plan_sha256)
            or type(self.family) is not McxFamily
            or not self.run_identity or not self.contract_symbol
            or type(self.lots) is not int or self.lots <= 0
            or type(self.v1_manual) is not bool
            or (self.v1_manual and self.provider_order_quantity is not None)
            or (not self.v1_manual and (
                type(self.provider_order_quantity) is not int
                or self.provider_order_quantity <= 0))
            or self.model_relation not in {
                "LEGACY_KR380", "ADVISORY_CONFIRMED", "SPONSOR_DIRECTED_OUTSIDE_MODEL"}
            or (self.model_relation != "LEGACY_KR380" and not self.v1_manual)
            or (self.model_relation == "SPONSOR_DIRECTED_OUTSIDE_MODEL" and
                any(item is not None for item in (self.entry_outcome_id,
                    self.entry_outcome_sha256, self.entry_outcome_at)))
            or (self.model_relation != "SPONSOR_DIRECTED_OUTSIDE_MODEL" and (
                not self.entry_outcome_id or not self.entry_outcome_sha256
                or len(self.entry_outcome_sha256) != 64
                or self.entry_outcome_at is None
                or self.entry_outcome_at.tzinfo is None
                or self.fill_at <= self.entry_outcome_at))
            or type(self.fill_price) is not Decimal
            or not self.fill_price.is_finite() or self.fill_price <= 0
            or self.fill_at.tzinfo is None or self.attested_at.tzinfo is None
            or self.fill_at > self.attested_at
            or not self.broker_evidence_id or "/" in self.broker_evidence_id
            or len(self.broker_evidence_sha256) != 64
            or any(char not in "0123456789abcdef"
                   for char in self.broker_evidence_sha256)
            or self.integrity_sha256 != self.digest()
        ):
            raise ValueError("MCX_LIVE_FILL_ATTESTATION_INVALID")

    def digest(self) -> str:
        fields = {key: getattr(self, key) for key in self.__dataclass_fields__
                  if key != "integrity_sha256"
                  and (key != "v1_manual" or self.v1_manual)
                  and (key != "model_relation" or self.model_relation != "LEGACY_KR380")}
        fields["family"] = self.family.value
        fields["fill_price"] = str(self.fill_price)
        fields["fill_at"] = self.fill_at.isoformat()
        fields["entry_outcome_at"] = (self.entry_outcome_at.isoformat()
                                      if self.entry_outcome_at else None)
        fields["attested_at"] = self.attested_at.isoformat()
        return sha256(_payload({"schema": SCHEMA, **fields})).hexdigest()

    @classmethod
    def create(cls, plan: McxTradePlanRecord, *, contract_symbol: str,
               expiry: str, lots: int, provider_order_quantity: int | None,
               entry_outcome: Kr380EntryOutcomeV2 | McxV1AdvisoryOutcome | None,
               fill_price: Decimal, fill_at: datetime,
               broker_evidence_id: str, broker_evidence_sha256: str,
               attested_at: datetime,
               v1_manual: bool = False) -> "McxLiveFillAttestation":
        if entry_outcome is None and not v1_manual:
            raise ValueError("MCX_LIVE_FILL_SIGNAL_REQUIRED")
        relation = ("SPONSOR_DIRECTED_OUTSIDE_MODEL" if entry_outcome is None else
                    "ADVISORY_CONFIRMED" if type(entry_outcome) is McxV1AdvisoryOutcome
                    else "LEGACY_KR380")
        fields = dict(plan_id=plan.trade_plan_id, plan_sha256=plan.integrity_hash,
                      run_identity=plan.native_run_identity, family=plan.family,
                      contract_symbol=contract_symbol, expiry=expiry, lots=lots,
                      provider_order_quantity=provider_order_quantity,
                      entry_outcome_id=entry_outcome.entry_outcome_id if entry_outcome else None,
                      entry_outcome_sha256=entry_outcome.integrity_sha256 if entry_outcome else None,
                      entry_outcome_at=entry_outcome.occurred_at if entry_outcome else None,
                      fill_price=fill_price, fill_at=fill_at,
                      broker_evidence_id=broker_evidence_id,
                      broker_evidence_sha256=broker_evidence_sha256,
                      attested_at=attested_at, v1_manual=v1_manual,
                      model_relation=relation)
        provisional = object.__new__(cls)
        for name, value in fields.items():
            object.__setattr__(provisional, name, value)
        return cls(**fields, integrity_sha256=provisional.digest())

    def validate_plan(self, plan: McxTradePlanRecord, decided_at: datetime) -> None:
        v1 = plan.authority == MCX_V1_ADVISORY_AUTHORITY
        if (
            type(plan) is not McxTradePlanRecord
            or (self.plan_id, self.plan_sha256, self.run_identity,
                self.family, self.contract_symbol, self.expiry)
               != (plan.trade_plan_id, plan.integrity_hash,
                   plan.native_run_identity, plan.family,
                   plan.contract_symbol, plan.expiry)
            or self.v1_manual != v1
            or (v1 and (self.provider_order_quantity is not None
                        or type(self.lots) is not int or self.lots <= 0))
            or (not v1 and (
                self.lots != plan.quantity.lots
                or self.provider_order_quantity
                   != plan.quantity.provider_order_quantity))
            or self.fill_at < plan.created_at
            or self.fill_at >= plan.entry_eligibility_boundary
            or self.attested_at > decided_at
            or decided_at >= plan.entry_eligibility_boundary
            or (not v1 and plan.quantity.stop_risk(self.fill_price, plan.stop)
                > plan.maximum_stop_risk)
            or (plan.native_direction.value == "LONG" and not
                plan.stop < self.fill_price < plan.canonical_target)
            or (plan.native_direction.value == "SHORT" and not
                plan.canonical_target < self.fill_price < plan.stop)
        ):
            raise ValueError("MCX_LIVE_FILL_PLAN_MISMATCH")


class LocalMcxLiveFillAttestationStore:
    """Immutable evidence retained before the corresponding Sponsor position."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("MCX_LIVE_FILL_STORE_INVALID")
        self._lock = RLock()

    def _path(self, plan_id: str) -> Path:
        if not plan_id or "/" in plan_id or ".." in plan_id:
            raise ValueError("MCX_LIVE_FILL_PLAN_ID_INVALID")
        return self.root / (plan_id + ".json")

    def _retain(self, path: Path, attestation: McxLiveFillAttestation) -> Path:
        if type(attestation) is not McxLiveFillAttestation:
            raise TypeError("MCX_LIVE_FILL_ATTESTATION_INVALID")
        fields = asdict(attestation)
        if not attestation.v1_manual:
            fields.pop("v1_manual")
        if attestation.model_relation == "LEGACY_KR380":
            fields.pop("model_relation")
        fields["family"] = attestation.family.value
        fields["fill_price"] = str(attestation.fill_price)
        fields["fill_at"] = attestation.fill_at.isoformat()
        fields["entry_outcome_at"] = (attestation.entry_outcome_at.isoformat()
                                      if attestation.entry_outcome_at else None)
        fields["attested_at"] = attestation.attested_at.isoformat()
        payload = _payload({"schema": SCHEMA, **fields})
        with self._lock:
            if path.exists():
                if path.is_symlink() or path.read_bytes() != payload:
                    raise ValueError("MCX_LIVE_FILL_ATTESTATION_IMMUTABLE")
                return path
            if self.root.is_symlink():
                raise ValueError("MCX_LIVE_FILL_STORE_INVALID")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.parent / ("." + attestation.plan_id + "." + uuid4().hex + ".pending")
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

    def retain(self, attestation: McxLiveFillAttestation) -> Path:
        return self._retain(self._path(attestation.plan_id), attestation)

    def retain_exit(self, position_id: str, attestation: McxLiveFillAttestation) -> Path:
        if not position_id or "/" in position_id or ".." in position_id:
            raise ValueError("MCX_LIVE_FILL_POSITION_ID_INVALID")
        return self._retain(self.root / (position_id + ".exit.json"), attestation)

    def retain_exit_intent(self, position_id: str,
                           attestation: McxLiveFillAttestation,
                           reason: str) -> Path:
        """Retain the immutable reason before exit evidence and lifecycle writes.

        This fixture-only journal permits one bounded restart reconciliation;
        it grants no broker or MCX production authority.
        """
        if (not position_id or "/" in position_id or ".." in position_id
                or type(attestation) is not McxLiveFillAttestation
                or not reason or "/" in reason):
            raise ValueError("MCX_LIVE_EXIT_INTENT_INVALID")
        path = self.root / (position_id + ".exit-intent.json")
        payload = _payload({"schema": EXIT_INTENT_SCHEMA,
                            "position_id": position_id,
                            "attestation_sha256": attestation.integrity_sha256,
                            "reason": reason})
        with self._lock:
            if path.exists():
                if path.is_symlink() or path.read_bytes() != payload:
                    raise ValueError("MCX_LIVE_EXIT_INTENT_IMMUTABLE")
                return path
            if self.root.is_symlink():
                raise ValueError("MCX_LIVE_FILL_STORE_INVALID")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.parent / ("." + position_id + "." + uuid4().hex + ".pending")
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

    def load_exit_intent(self, position_id: str) -> tuple[str, str]:
        if not position_id or "/" in position_id or ".." in position_id:
            raise ValueError("MCX_LIVE_EXIT_INTENT_INVALID")
        path = self.root / (position_id + ".exit-intent.json")
        if path.is_symlink():
            raise ValueError("MCX_LIVE_EXIT_INTENT_INVALID")
        try:
            original = path.read_bytes()
            fields = json.loads(original)
            if (original != _payload(fields)
                    or fields.get("schema") != EXIT_INTENT_SCHEMA
                    or fields.get("position_id") != position_id
                    or set(fields) != {"schema", "position_id",
                                       "attestation_sha256", "reason"}
                    or not isinstance(fields["reason"], str)
                    or not isinstance(fields["attestation_sha256"], str)):
                raise ValueError
            return fields["attestation_sha256"], fields["reason"]
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ValueError("MCX_LIVE_EXIT_INTENT_INVALID") from error

    def _load(self, path: Path) -> McxLiveFillAttestation:
        if path.is_symlink():
            raise ValueError("MCX_LIVE_FILL_ATTESTATION_INVALID")
        try:
            original = path.read_bytes()
            fields = json.loads(original)
            if original != _payload(fields):
                raise ValueError
            if fields.pop("schema") != SCHEMA:
                raise ValueError
            fields["family"] = McxFamily(fields["family"])
            fields["fill_price"] = Decimal(fields["fill_price"])
            fields["fill_at"] = datetime.fromisoformat(fields["fill_at"])
            fields["entry_outcome_at"] = (datetime.fromisoformat(fields["entry_outcome_at"])
                                           if fields["entry_outcome_at"] else None)
            fields["attested_at"] = datetime.fromisoformat(fields["attested_at"])
            return McxLiveFillAttestation(**fields)
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise ValueError("MCX_LIVE_FILL_ATTESTATION_INVALID") from error

    def load(self, plan_id: str) -> McxLiveFillAttestation:
        return self._load(self._path(plan_id))

    def load_exit(self, position_id: str) -> McxLiveFillAttestation:
        if not position_id or "/" in position_id or ".." in position_id:
            raise ValueError("MCX_LIVE_FILL_POSITION_ID_INVALID")
        return self._load(self.root / (position_id + ".exit.json"))


def admit_isolated_mcx_live(
    plan: McxTradePlanRecord, judgment: BusinessJudgment, risk: RiskApproval,
    outcome: Kr380EntryOutcomeV2, outcome_store: LocalKr380V2Store,
    attestation: McxLiveFillAttestation,
    attestation_store: LocalMcxLiveFillAttestationStore,
    sponsor_store: LocalSponsorDecisionStore, *, current_plan_id: str,
    decided_at: datetime,
) -> SponsorInitiationResult:
    """Retain exact Sponsor fill proof before a fixture-only LIVE position."""

    if (type(plan) is not McxTradePlanRecord
            or plan.authority != "ISOLATED_FIXTURE_ONLY_NO_PRODUCTION_ENTRY"
            or plan.quantity.proof_origin is not McxQuantityProofOrigin.ISOLATED_FIXTURE
            or current_plan_id != plan.trade_plan_id):
        raise ValueError("MCX_LIVE_PLAN_UNAVAILABLE")
    if (type(attestation) is not McxLiveFillAttestation
            or type(attestation_store) is not LocalMcxLiveFillAttestationStore
            or type(sponsor_store) is not LocalSponsorDecisionStore):
        raise ValueError("MCX_LIVE_ATTESTATION_UNAVAILABLE")
    attestation.validate_plan(plan, decided_at)
    expected_state = (Kr380V2State.LONG_ENTRY_TRIGGERED
                      if plan.native_direction.value == "LONG"
                      else Kr380V2State.SHORT_ENTRY_TRIGGERED)
    if (type(outcome) is not Kr380EntryOutcomeV2
            or type(outcome_store) is not LocalKr380V2Store
            or outcome.state is not expected_state
            or outcome.trade_plan_id != plan.trade_plan_id
            or outcome.trade_plan_sha256 != plan.integrity_hash
            or outcome.native_run_identity != plan.native_run_identity
            or outcome.canonical_instrument != plan.family.value
            or outcome.risk_result_id != risk.risk_result_id
            or outcome_store.load_for_plan(plan.trade_plan_id) != outcome
            or (attestation.entry_outcome_id,
                attestation.entry_outcome_sha256,
                attestation.entry_outcome_at)
               != (outcome.entry_outcome_id,
                   outcome.integrity_sha256, outcome.occurred_at)):
        raise ValueError("MCX_LIVE_CONFIRMED_ENTRY_UNAVAILABLE")
    _require_judgment(plan, judgment)
    _require_risk(plan, judgment, risk, decided_at)
    if risk.state is not RiskState.APPROVED or risk.constraints.present:
        raise ValueError("MCX_LIVE_RISK_UNAVAILABLE")
    decision_id = _id("SPONSOR-DECISION", plan.trade_plan_id,
                      judgment.business_judgment_id, risk.risk_result_id,
                      SponsorTradeChoice.LIVE.value,
                      attestation.integrity_sha256)
    decision = _decision_record(dict(
        decision_id=decision_id, trade_plan_id=plan.trade_plan_id,
        trade_plan_integrity_hash=plan.integrity_hash,
        business_judgment_id=judgment.business_judgment_id,
        business_judgment_hash=_object_digest(judgment), risk_id=risk.risk_result_id,
        risk_hash=_object_digest(risk), native_run_identity=plan.native_run_identity,
        opportunity_identity=plan.native_opportunity_identity.value,
        canonical_instrument=plan.canonical_instrument,
        direction=plan.native_direction, decision=SponsorTradeChoice.LIVE,
        execution_mode=SponsorExecutionMode.MANUAL_SPONSOR_EXECUTION,
        decision_timestamp=decided_at, go_timestamp=decided_at,
        model_entry=plan.entry, stop=plan.stop,
        invalidation=plan.invalidation_reference, target=plan.canonical_target,
        model_risk_reward=plan.risk_reward_ratio, risk_state=risk.state,
        risk_constraints=risk.constraints,
        provenance=(plan.trade_plan_id, judgment.business_judgment_id,
                    risk.risk_result_id, attestation.integrity_sha256,
                    attestation.broker_evidence_id,
                    attestation.broker_evidence_sha256),
    ))
    position = _position_record(dict(
        position_id=_id("SPONSOR-POSITION", decision_id), decision_id=decision_id,
        trade_plan_id=plan.trade_plan_id, mode=SponsorTradeChoice.LIVE,
        state=SponsorInitiationState.LIVE_ACTIVE,
        canonical_instrument=plan.canonical_instrument,
        direction=plan.native_direction, lots=attestation.lots, lot_size=1,
        underlying_quantity=attestation.lots, mcx_quantity=plan.quantity,
        actual_entry=attestation.fill_price,
        entry_timestamp=attestation.fill_at, model_entry=plan.entry,
        stop=plan.stop, invalidation=plan.invalidation_reference,
        target=plan.canonical_target, created_at=decided_at,
        provenance=(decision_id, plan.trade_plan_id,
                    plan.execution_context_identity,
                    attestation.integrity_sha256, plan.contract_symbol,
                    plan.expiry),
    ))
    result = SponsorInitiationResult(
        SponsorInitiationState.LIVE_ACTIVE,
        "SPONSOR_ATTESTED_LIVE_POSITION_REGISTERED", decision, position,
    )
    # A conflicting Sponsor decision is rejected before a new attestation write.
    existing_path = (sponsor_store.root / plan.native_run_identity /
                     plan.trade_plan_id / "decision.json")
    if existing_path.exists() and sponsor_store.load_plan(
        plan.native_run_identity, plan.trade_plan_id,
    ) != result:
        raise ValueError("SPONSOR_DECISION_ALREADY_FINAL")
    attestation_store.retain(attestation)
    return sponsor_store.retain(result)


def admit_v1_mcx_manual_live(
    plan: McxTradePlanRecord, judgment: BusinessJudgment, risk: RiskApproval,
    outcome: McxV1AdvisoryOutcome | None, outcome_store: LocalMcxV1AdvisoryStore,
    attestation: McxLiveFillAttestation,
    attestation_store: LocalMcxLiveFillAttestationStore,
    broker_store: object, broker_bytes: bytes,
    sponsor_store: LocalSponsorDecisionStore, *, current_plan_id: str,
    decided_at: datetime,
) -> SponsorInitiationResult:
    """Record Sponsor-executed LIVE lots only after immutable fill evidence.

    No Provider order is placed or inferred. The caller holds the exact-current
    Review/plan fence through this function and lifecycle registration.
    """
    from kronos.swing.v1.mcx_broker_fill_evidence import (
        LocalMcxBrokerFillEvidenceStore, McxBrokerFillCapture,
    )
    from kronos.swing.v1.mcx_kr380_issuer import RULE_ID

    if (type(plan) is not McxTradePlanRecord
            or plan.authority != MCX_V1_ADVISORY_AUTHORITY
            or current_plan_id != plan.trade_plan_id
            or type(attestation) is not McxLiveFillAttestation
            or not attestation.v1_manual
            or type(attestation_store) is not LocalMcxLiveFillAttestationStore
            or type(broker_store) is not LocalMcxBrokerFillEvidenceStore
            or type(broker_bytes) is not bytes
            or type(sponsor_store) is not LocalSponsorDecisionStore):
        raise ValueError("MCX_V1_LIVE_ADMISSION_UNAVAILABLE")
    attestation.validate_plan(plan, decided_at)
    _require_judgment(plan, judgment)
    _require_risk(plan, judgment, risk, decided_at)
    if risk.state is RiskState.REJECTED or risk.constraints.present:
        raise ValueError("MCX_V1_LIVE_RISK_REJECTED")
    expected = (McxAdvisoryState.LONG_CONFIRMED
                if plan.native_direction.value == "LONG" else
                McxAdvisoryState.SHORT_CONFIRMED)
    if type(outcome_store) is not LocalMcxV1AdvisoryStore:
        raise ValueError("MCX_V1_LIVE_SIGNAL_CHANGED")
    stored = outcome_store.load_for_plan(plan.trade_plan_id)
    # A later confirmation cannot be retrospectively attached to a real fill.
    qualifying = stored if stored is not None and stored.confirmed_at < attestation.fill_at else None
    if qualifying != outcome:
        raise ValueError("MCX_V1_LIVE_SIGNAL_CHANGED")
    if outcome is None:
        if attestation.model_relation != "SPONSOR_DIRECTED_OUTSIDE_MODEL":
            raise ValueError("MCX_V1_LIVE_OUTSIDE_MODEL_LABEL_REQUIRED")
    elif (type(outcome) is not McxV1AdvisoryOutcome
            or attestation.model_relation != "ADVISORY_CONFIRMED"
            or outcome.state is not expected
            or (outcome.contract_symbol, outcome.expiry) != (plan.contract_symbol, plan.expiry)
            or outcome.trade_plan_id != plan.trade_plan_id
            or outcome.trade_plan_sha256 != plan.integrity_hash
            or outcome.native_run_identity != plan.native_run_identity
            or outcome.canonical_instrument != plan.family.value
            or outcome.risk_result_id != risk.risk_result_id
            or outcome.kr370_source_identity != plan.readiness_record_identity
            or outcome.reason != "MCX_COMPLETED_1H_ADVISORY_CLOSE_CROSS"
            or ADVISORY_RULE_ID not in outcome.provenance
            or plan.receipt_integrity_sha256 not in outcome.provenance
            or plan.promotion_integrity_sha256 not in outcome.provenance
            or (attestation.entry_outcome_id,
                attestation.entry_outcome_sha256,
                attestation.entry_outcome_at)
               != (outcome.entry_outcome_id, outcome.integrity_sha256,
                   outcome.occurred_at)):
        raise ValueError("MCX_V1_LIVE_SIGNAL_UNAVAILABLE")
    decision_id = _id("SPONSOR-DECISION", plan.trade_plan_id,
                      judgment.business_judgment_id, risk.risk_result_id,
                      SponsorTradeChoice.LIVE.value,
                      attestation.integrity_sha256)
    decision = _decision_record(dict(
        decision_id=decision_id, trade_plan_id=plan.trade_plan_id,
        trade_plan_integrity_hash=plan.integrity_hash,
        business_judgment_id=judgment.business_judgment_id,
        business_judgment_hash=_object_digest(judgment),
        risk_id=risk.risk_result_id, risk_hash=_object_digest(risk),
        native_run_identity=plan.native_run_identity,
        opportunity_identity=plan.native_opportunity_identity.value,
        canonical_instrument=plan.canonical_instrument,
        direction=plan.native_direction, decision=SponsorTradeChoice.LIVE,
        execution_mode=SponsorExecutionMode.MANUAL_SPONSOR_EXECUTION,
        decision_timestamp=decided_at, go_timestamp=decided_at,
        model_entry=plan.entry, stop=plan.stop,
        invalidation=plan.invalidation_reference, target=plan.canonical_target,
        model_risk_reward=plan.risk_reward_ratio, risk_state=risk.state,
        risk_constraints=risk.constraints,
        provenance=(plan.trade_plan_id, risk.risk_result_id,
                    outcome.integrity_sha256 if outcome else "SPONSOR-DIRECTED / OUTSIDE MODEL",
                    attestation.model_relation, attestation.integrity_sha256,
                    attestation.broker_evidence_id,
                    attestation.broker_evidence_sha256,
                    "MANUAL_BROKER_EXECUTION_ONLY"),
    ))
    position_id = _id("SPONSOR-POSITION", decision_id)
    position = _position_record(dict(
        position_id=position_id, decision_id=decision_id,
        trade_plan_id=plan.trade_plan_id, mode=SponsorTradeChoice.LIVE,
        state=SponsorInitiationState.LIVE_ACTIVE,
        canonical_instrument=plan.canonical_instrument,
        direction=plan.native_direction, lots=attestation.lots, lot_size=1,
        underlying_quantity=attestation.lots,
        mcx_v1_contract_symbol=plan.contract_symbol,
        actual_entry=attestation.fill_price,
        entry_timestamp=attestation.fill_at, model_entry=plan.entry,
        stop=plan.stop, invalidation=plan.invalidation_reference,
        target=plan.canonical_target, created_at=decided_at,
        provenance=(decision_id, plan.trade_plan_id,
                    plan.execution_context_identity,
                    attestation.integrity_sha256, plan.contract_symbol,
                    plan.expiry, "PHYSICAL_QUANTITY_UNKNOWN",
                    "ADVISORY CONFIRMED" if outcome else "SPONSOR-DIRECTED / OUTSIDE MODEL"),
    ))
    result = SponsorInitiationResult(
        SponsorInitiationState.LIVE_ACTIVE,
        "SPONSOR_ATTESTED_LIVE_POSITION_REGISTERED", decision, position)
    capture = McxBrokerFillCapture.from_attestation(position_id,
                                                      attestation,
                                                      broker_bytes)
    if capture.evidence_sha256 != attestation.broker_evidence_sha256:
        raise ValueError("MCX_V1_BROKER_EVIDENCE_MISMATCH")
    existing = (sponsor_store.root / plan.native_run_identity /
                plan.trade_plan_id / "decision.json")
    if existing.exists() and sponsor_store.load_plan(
            plan.native_run_identity, plan.trade_plan_id) != result:
        raise ValueError("SPONSOR_DECISION_ALREADY_FINAL")
    attestation_store.retain(attestation)
    broker_store.capture(capture, broker_bytes)
    return sponsor_store.retain(result)
