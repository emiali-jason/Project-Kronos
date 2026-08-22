"""ADR-0013 Native DOMAIN-007, ECPC V2, KR-380 V2, and KR-390 records.

The module is objective-model only.  It has no Sponsor-position, order, fill,
Telegram, OpenAI, Pine, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.swing.v1.kr370_step31_handoff import Kr370Step31EligibilityHandoff
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_trade_construction import (
    TradePlanRecord,
    TradePlanStatus,
)
from kronos.swing.v1.step32 import (
    MonitoringObservation,
    MonitoringSubmissionType,
    ObjectiveModelState,
    RiskState,
)


PORTFOLIO_STATE_CONTRACT_ID = "KRONOS-SWING-PORTFOLIO-STATE-V1"
PORTFOLIO_STATE_VERSION = "1"
RISK_PERMISSION_CONTRACT_ID = "KRONOS-SWING-V1-RISK-APPROVAL-V1"
RISK_POLICY_ID = "KRONOS-SWING-DOMAIN-007-RISK-PERMISSION-V1"
RISK_POLICY_VERSION = "1"
ECPC_CONTRACT_ID = "ECPC-001"
ECPC_VERSION = "2.0"
KR380_CONTRACT_ID = "KRONOS-KR-380-ENTRY-OUTCOME-V2"
KR380_CONTRACT_VERSION = "2"
KR380_POLICY_ID = "KRONOS-KR-380-ENTRY-TIMING-V2"
KR380_POLICY_VERSION = "2"
OBJECTIVE_MODEL_CONTRACT_ID = "KRONOS-SWING-OBJECTIVE-MODEL-TRADE-V1"
OBJECTIVE_MODEL_CONTRACT_VERSION = "1"
NO_BROKER_AUTHORITY = "NONE"


class PortfolioExposureKind(StrEnum):
    OBJECTIVE_MODEL = "OBJECTIVE_MODEL"
    SPONSOR_LIVE = "SPONSOR_LIVE"
    SPONSOR_PAPER = "SPONSOR_PAPER"


class PortfolioRuleDisposition(StrEnum):
    CONSTRAINT = "CONSTRAINT"
    HARD_PROHIBITION = "HARD_PROHIBITION"


class EcpcV2Outcome(StrEnum):
    PENDING = "PENDING"
    QUALIFIED = "QUALIFIED"
    EXTENDED = "EXTENDED"
    FAILED = "FAILED"


class EcpcV2Blocker(StrEnum):
    REQUIRED_DATA_PENDING = "REQUIRED_DATA_PENDING"
    ELIGIBLE_EXECUTION_CONTEXT_PENDING = "ELIGIBLE_EXECUTION_CONTEXT_PENDING"
    DIRECTIONAL_ALIGNMENT_PENDING = "DIRECTIONAL_ALIGNMENT_PENDING"
    PRICE_ACCEPTANCE_PENDING = "PRICE_ACCEPTANCE_PENDING"
    EXPANSION_PENDING = "EXPANSION_PENDING"
    MOMENTUM_PENDING = "MOMENTUM_PENDING"
    CONFIDENCE_PENDING = "CONFIDENCE_PENDING"
    OPPORTUNITY_PENDING = "OPPORTUNITY_PENDING"
    EXECUTION_CONFIRMATION_PENDING = "EXECUTION_CONFIRMATION_PENDING"
    PRICE_EXTENDED = "PRICE_EXTENDED"
    EXECUTION_SETUP_FAILED = "EXECUTION_SETUP_FAILED"


class Kr380V2State(StrEnum):
    NO_TRIGGER = "NO_TRIGGER"
    FORMING = "FORMING"
    LONG_ENTRY_TRIGGERED = "LONG_ENTRY_TRIGGERED"
    SHORT_ENTRY_TRIGGERED = "SHORT_ENTRY_TRIGGERED"
    EXTENDED = "EXTENDED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class PortfolioExposureFact:
    exposure_identity: str
    kind: PortfolioExposureKind
    canonical_instrument: str
    direction: str
    lifecycle_identity: str
    source_record_identity: str

    def __post_init__(self) -> None:
        if (
            not all((self.exposure_identity, self.canonical_instrument,
                     self.lifecycle_identity, self.source_record_identity))
            or type(self.kind) is not PortfolioExposureKind
            or self.direction not in {"LONG", "SHORT"}
        ):
            raise ValueError("PORTFOLIO_EXPOSURE_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class PortfolioRuleFact:
    rule_identity: str
    disposition: PortfolioRuleDisposition
    reason_code: str
    source_identity: str

    def __post_init__(self) -> None:
        if (
            not all((self.rule_identity, self.reason_code, self.source_identity))
            or type(self.disposition) is not PortfolioRuleDisposition
        ):
            raise ValueError("PORTFOLIO_RULE_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class PortfolioStateV1:
    portfolio_state_identity: str
    cycle_identity: str
    as_of_boundary: datetime
    objective_exposures: tuple[PortfolioExposureFact, ...]
    sponsor_exposures: tuple[PortfolioExposureFact, ...]
    rule_facts: tuple[PortfolioRuleFact, ...]
    source_identities: tuple[str, ...]
    sources_complete: bool
    provenance: tuple[str, ...]
    integrity_sha256: str
    contract_identity: str = PORTFOLIO_STATE_CONTRACT_ID
    contract_version: str = PORTFOLIO_STATE_VERSION

    def __post_init__(self) -> None:
        if (
            not all((self.portfolio_state_identity, self.cycle_identity))
            or not _aware(self.as_of_boundary)
            or any(type(item) is not PortfolioExposureFact for item in self.objective_exposures)
            or any(type(item) is not PortfolioExposureFact for item in self.sponsor_exposures)
            or any(type(item) is not PortfolioRuleFact for item in self.rule_facts)
            or type(self.sources_complete) is not bool
            or not self.source_identities
            or not self.provenance
            or self.contract_identity != PORTFOLIO_STATE_CONTRACT_ID
            or self.contract_version != PORTFOLIO_STATE_VERSION
            or not _digest(self.integrity_sha256)
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("PORTFOLIO_STATE_INVALID")


@dataclass(frozen=True, slots=True)
class RiskPermissionV1:
    risk_result_id: str
    candidate_id: str
    candidate_digest: str
    native_run_identity: str
    canonical_instrument: str
    kr370_source_identity: str
    kr370_source_sha256: str
    handoff_identity: str
    trade_plan_id: str
    trade_plan_sha256: str
    portfolio_state_identity: str | None
    portfolio_state_sha256: str | None
    portfolio_cycle_identity: str | None
    evaluation_boundary: datetime
    evaluated_at: datetime
    state: RiskState
    reason_codes: tuple[str, ...]
    constraints: tuple[str, ...]
    provenance: tuple[str, ...]
    integrity_sha256: str
    current: bool = True
    contract_identity: str = RISK_PERMISSION_CONTRACT_ID
    contract_version: str = "1"
    policy_identity: str = RISK_POLICY_ID
    policy_version: str = RISK_POLICY_VERSION
    broker_authority: str = NO_BROKER_AUTHORITY

    def __post_init__(self) -> None:
        portfolio_fields = (
            self.portfolio_state_identity,
            self.portfolio_state_sha256,
            self.portfolio_cycle_identity,
        )
        if (
            not all((self.risk_result_id, self.candidate_id, self.native_run_identity,
                     self.canonical_instrument, self.kr370_source_identity,
                     self.handoff_identity, self.trade_plan_id))
            or not all(_digest(item) for item in (
                self.candidate_digest, self.kr370_source_sha256,
                self.trade_plan_sha256, self.integrity_sha256,
            ))
            or any(item is None for item in portfolio_fields)
               and self.state is not RiskState.UNAVAILABLE
            or self.portfolio_state_sha256 is not None
               and not _digest(self.portfolio_state_sha256)
            or not _aware(self.evaluation_boundary)
            or not _aware(self.evaluated_at)
            or type(self.state) is not RiskState
            or not self.reason_codes
            or type(self.current) is not bool
            or (self.state is RiskState.CONSTRAINED) != bool(self.constraints)
            or (self.state is not RiskState.CONSTRAINED and self.constraints)
            or self.contract_identity != RISK_PERMISSION_CONTRACT_ID
            or self.contract_version != "1"
            or self.policy_identity != RISK_POLICY_ID
            or self.policy_version != RISK_POLICY_VERSION
            or self.broker_authority != NO_BROKER_AUTHORITY
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("RISK_PERMISSION_V1_INVALID")

    @property
    def run_id(self) -> str:
        return self.native_run_identity

    @property
    def permits_entry(self) -> bool:
        return self.current and self.state in {RiskState.APPROVED, RiskState.CONSTRAINED}


@dataclass(frozen=True, slots=True)
class NativeEcpcV2Context:
    context_identity: str
    native_run_identity: str
    canonical_instrument: str
    direction: str
    trade_plan_id: str
    trade_plan_sha256: str
    risk_result_id: str
    monitoring_binding_id: str
    session_identity: str
    observation_boundary: datetime
    outcome: EcpcV2Outcome
    blockers: tuple[EcpcV2Blocker, ...]
    provenance: tuple[str, ...]
    integrity_sha256: str
    contract_identity: str = ECPC_CONTRACT_ID
    contract_version: str = ECPC_VERSION

    def __post_init__(self) -> None:
        expected_blocker = {
            EcpcV2Outcome.QUALIFIED: None,
            EcpcV2Outcome.EXTENDED: EcpcV2Blocker.PRICE_EXTENDED,
            EcpcV2Outcome.FAILED: EcpcV2Blocker.EXECUTION_SETUP_FAILED,
        }.get(self.outcome)
        if (
            not all((self.context_identity, self.native_run_identity,
                     self.canonical_instrument, self.trade_plan_id,
                     self.risk_result_id, self.monitoring_binding_id,
                     self.session_identity))
            or self.direction not in {"LONG", "SHORT"}
            or not _digest(self.trade_plan_sha256)
            or not _aware(self.observation_boundary)
            or type(self.outcome) is not EcpcV2Outcome
            or len(self.blockers) > 3
            or len(set(self.blockers)) != len(self.blockers)
            or (self.outcome is EcpcV2Outcome.QUALIFIED and self.blockers)
            or (self.outcome is EcpcV2Outcome.PENDING and not self.blockers)
            or (expected_blocker is not None and (
                not self.blockers or self.blockers[0] is not expected_blocker
            ))
            or self.contract_identity != ECPC_CONTRACT_ID
            or self.contract_version != ECPC_VERSION
            or not self.provenance
            or not _digest(self.integrity_sha256)
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("NATIVE_ECPC_V2_CONTEXT_INVALID")


@dataclass(frozen=True, slots=True)
class Kr380EntryOutcomeV2:
    entry_outcome_id: str
    native_run_identity: str
    canonical_instrument: str
    direction: str
    kr370_source_identity: str
    trade_plan_id: str
    trade_plan_sha256: str
    risk_result_id: str
    ecpc_context_identity: str | None
    monitoring_binding_id: str | None
    observation_boundary: datetime
    source_observation_ids: tuple[str, ...]
    source_sequence: tuple[int, ...]
    state: Kr380V2State
    reason: str
    occurred_at: datetime
    provenance: tuple[str, ...]
    integrity_sha256: str
    contract_identity: str = KR380_CONTRACT_ID
    contract_version: str = KR380_CONTRACT_VERSION
    owner_identity: str = "KR-380"
    state_family_identity: str = "KR380_ENTRY_OUTCOME"
    policy_identity: str = KR380_POLICY_ID
    policy_version: str = KR380_POLICY_VERSION
    broker_authority: str = NO_BROKER_AUTHORITY

    def __post_init__(self) -> None:
        triggered = self.state in {
            Kr380V2State.LONG_ENTRY_TRIGGERED,
            Kr380V2State.SHORT_ENTRY_TRIGGERED,
        }
        if (
            not all((self.entry_outcome_id, self.native_run_identity,
                     self.canonical_instrument, self.kr370_source_identity,
                     self.trade_plan_id, self.risk_result_id, self.reason))
            or self.direction not in {"LONG", "SHORT"}
            or not _digest(self.trade_plan_sha256)
            or not _aware(self.observation_boundary)
            or not _aware(self.occurred_at)
            or type(self.state) is not Kr380V2State
            or triggered and (
                not self.ecpc_context_identity or not self.monitoring_binding_id
                or len(self.source_observation_ids) != 2
            )
            or len(self.source_sequence) != len(self.source_observation_ids)
            or self.contract_identity != KR380_CONTRACT_ID
            or self.contract_version != KR380_CONTRACT_VERSION
            or self.owner_identity != "KR-380"
            or self.state_family_identity != "KR380_ENTRY_OUTCOME"
            or self.policy_identity != KR380_POLICY_ID
            or self.policy_version != KR380_POLICY_VERSION
            or self.broker_authority != NO_BROKER_AUTHORITY
            or not self.provenance
            or not _digest(self.integrity_sha256)
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("KR380_ENTRY_OUTCOME_V2_INVALID")


@dataclass(frozen=True, slots=True)
class ObjectiveModelRecordV1:
    model_trade_id: str
    native_run_identity: str
    canonical_instrument: str
    direction: str
    trade_plan_id: str
    trade_plan_sha256: str
    risk_result_id: str
    entry_outcome_id: str
    entry: Decimal
    stop: Decimal
    target: Decimal
    invalidation_reference: Decimal
    state: ObjectiveModelState
    monitoring_state: MonitoringConnectionState
    activated_at: datetime
    source_observation_ids: tuple[str, ...]
    provenance: tuple[str, ...]
    integrity_sha256: str
    contract_identity: str = OBJECTIVE_MODEL_CONTRACT_ID
    contract_version: str = OBJECTIVE_MODEL_CONTRACT_VERSION
    sponsor_position_identity: str | None = None
    broker_authority: str = NO_BROKER_AUTHORITY

    def __post_init__(self) -> None:
        for name in ("entry", "stop", "target", "invalidation_reference"):
            object.__setattr__(self, name, Decimal(getattr(self, name)))
        if (
            not all((self.model_trade_id, self.native_run_identity,
                     self.canonical_instrument, self.trade_plan_id,
                     self.risk_result_id, self.entry_outcome_id))
            or self.direction not in {"LONG", "SHORT"}
            or not _digest(self.trade_plan_sha256)
            or type(self.state) is not ObjectiveModelState
            or type(self.monitoring_state) is not MonitoringConnectionState
            or not _aware(self.activated_at)
            or not self.source_observation_ids
            or not self.provenance
            or self.contract_identity != OBJECTIVE_MODEL_CONTRACT_ID
            or self.contract_version != OBJECTIVE_MODEL_CONTRACT_VERSION
            or self.sponsor_position_identity is not None
            or self.broker_authority != NO_BROKER_AUTHORITY
            or not _digest(self.integrity_sha256)
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("OBJECTIVE_MODEL_RECORD_V1_INVALID")


def create_portfolio_state_v1(
    *, cycle_identity: str, as_of_boundary: datetime,
    objective_exposures: tuple[PortfolioExposureFact, ...],
    sponsor_exposures: tuple[PortfolioExposureFact, ...],
    rule_facts: tuple[PortfolioRuleFact, ...] = (),
    source_identities: tuple[str, ...], sources_complete: bool,
    provenance: tuple[str, ...],
) -> PortfolioStateV1:
    if not sources_complete:
        raise ValueError("PORTFOLIO_STATE_SOURCES_INCOMPLETE")
    values: dict[str, Any] = dict(
        portfolio_state_identity="PORTFOLIO-STATE-" + sha256(
            _canonical((cycle_identity, as_of_boundary, source_identities))
        ).hexdigest(),
        cycle_identity=cycle_identity, as_of_boundary=as_of_boundary,
        objective_exposures=objective_exposures, sponsor_exposures=sponsor_exposures,
        rule_facts=rule_facts, source_identities=source_identities,
        sources_complete=True, provenance=provenance,
        contract_identity=PORTFOLIO_STATE_CONTRACT_ID,
        contract_version=PORTFOLIO_STATE_VERSION,
    )
    return PortfolioStateV1(integrity_sha256=_values_digest(values), **values)


def evaluate_risk_permission_v1(
    plan: TradePlanRecord,
    handoff: Kr370Step31EligibilityHandoff,
    *, kr370_source_identity: str, kr370_source_sha256: str,
    portfolio_state: PortfolioStateV1 | None,
    current_trade_plan_id: str, current_portfolio_cycle_identity: str | None,
    evaluated_at: datetime,
) -> RiskPermissionV1:
    reasons: tuple[str, ...]
    constraints: tuple[str, ...] = ()
    state = RiskState.UNAVAILABLE
    if (
        type(plan) is not TradePlanRecord
        or plan.geometry_viability is not TradePlanStatus.TRADE_PLAN_READY
        or plan.trade_plan_id != current_trade_plan_id
        or handoff.native_run_identity != plan.native_run_identity
        or handoff.canonical_instrument != plan.canonical_instrument
        or handoff.handoff_identity not in plan.provenance
        or handoff.integrity_sha256 not in plan.provenance
    ):
        reasons = ("CURRENT_STEP31_BINDING_UNAVAILABLE",)
    elif not _digest(kr370_source_sha256):
        reasons = ("KR370_SOURCE_INTEGRITY_UNAVAILABLE",)
    elif portfolio_state is None:
        reasons = ("PORTFOLIO_STATE_UNAVAILABLE",)
    elif (
        not portfolio_state.sources_complete
        or portfolio_state.cycle_identity != current_portfolio_cycle_identity
    ):
        reasons = ("PORTFOLIO_STATE_STALE_OR_INCOMPLETE",)
    else:
        hard = tuple(
            item.reason_code for item in portfolio_state.rule_facts
            if item.disposition is PortfolioRuleDisposition.HARD_PROHIBITION
        )
        constrained = tuple(
            item.reason_code for item in portfolio_state.rule_facts
            if item.disposition is PortfolioRuleDisposition.CONSTRAINT
        )
        if hard:
            state, reasons = RiskState.REJECTED, hard
        elif constrained:
            state, reasons, constraints = RiskState.CONSTRAINED, constrained, constrained
        else:
            state, reasons = RiskState.APPROVED, ("NO_GOVERNED_PROHIBITION",)
    values: dict[str, Any] = dict(
        risk_result_id="RISK-PERMISSION-" + sha256(_canonical((
            plan.trade_plan_id, plan.integrity_hash,
            None if portfolio_state is None else portfolio_state.cycle_identity,
            state.value, reasons, evaluated_at,
        ))).hexdigest(),
        candidate_id=plan.trade_plan_id, candidate_digest=plan.integrity_hash,
        native_run_identity=plan.native_run_identity,
        canonical_instrument=plan.canonical_instrument,
        kr370_source_identity=kr370_source_identity,
        kr370_source_sha256=kr370_source_sha256,
        handoff_identity=handoff.handoff_identity,
        trade_plan_id=plan.trade_plan_id, trade_plan_sha256=plan.integrity_hash,
        portfolio_state_identity=(None if portfolio_state is None else portfolio_state.portfolio_state_identity),
        portfolio_state_sha256=(None if portfolio_state is None else portfolio_state.integrity_sha256),
        portfolio_cycle_identity=(None if portfolio_state is None else portfolio_state.cycle_identity),
        evaluation_boundary=plan.observation_boundary, evaluated_at=evaluated_at,
        state=state, reason_codes=reasons, constraints=constraints,
        provenance=tuple(dict.fromkeys((
            plan.trade_plan_id, plan.integrity_hash, handoff.handoff_identity,
            kr370_source_identity,
            *(portfolio_state.provenance if portfolio_state is not None else ("PORTFOLIO_STATE_UNAVAILABLE",)),
            "ADR-0013", "DOMAIN-007",
        ))),
        current=True, contract_identity=RISK_PERMISSION_CONTRACT_ID,
        contract_version="1", policy_identity=RISK_POLICY_ID,
        policy_version=RISK_POLICY_VERSION, broker_authority=NO_BROKER_AUTHORITY,
    )
    return RiskPermissionV1(integrity_sha256=_values_digest(values), **values)


def produce_native_ecpc_v2(
    plan: TradePlanRecord,
    risk: RiskPermissionV1,
    *, monitoring_binding_id: str, session_identity: str,
    observation_boundary: datetime, outcome: EcpcV2Outcome,
    blockers: tuple[EcpcV2Blocker, ...],
) -> NativeEcpcV2Context:
    if (
        not risk.permits_entry
        or risk.trade_plan_id != plan.trade_plan_id
        or risk.trade_plan_sha256 != plan.integrity_hash
        or risk.native_run_identity != plan.native_run_identity
        or risk.canonical_instrument != plan.canonical_instrument
    ):
        raise ValueError("NATIVE_ECPC_V2_RISK_BINDING_INVALID")
    values: dict[str, Any] = dict(
        context_identity="ECPC-V2-" + sha256(_canonical((
            plan.trade_plan_id, risk.risk_result_id, monitoring_binding_id,
            observation_boundary, outcome.value, blockers,
        ))).hexdigest(),
        native_run_identity=plan.native_run_identity,
        canonical_instrument=plan.canonical_instrument,
        direction=plan.native_direction.value,
        trade_plan_id=plan.trade_plan_id, trade_plan_sha256=plan.integrity_hash,
        risk_result_id=risk.risk_result_id,
        monitoring_binding_id=monitoring_binding_id,
        session_identity=session_identity,
        observation_boundary=observation_boundary, outcome=outcome,
        blockers=blockers,
        provenance=(plan.trade_plan_id, risk.risk_result_id, plan.execution_context_identity,
                    "ADR-0013", "KR-380A"),
        contract_identity=ECPC_CONTRACT_ID, contract_version=ECPC_VERSION,
    )
    return NativeEcpcV2Context(integrity_sha256=_values_digest(values), **values)


def evaluate_kr380_v2(
    plan: TradePlanRecord,
    risk: RiskPermissionV1,
    context: NativeEcpcV2Context | None,
    *, kr370_source_identity: str,
    previous: MonitoringObservation | None,
    current: MonitoringObservation | None,
    evaluated_at: datetime,
) -> Kr380EntryOutcomeV2:
    state = Kr380V2State.NO_TRIGGER
    reason = "UPSTREAM_PATH_NOT_PERMITTED"
    observations: tuple[MonitoringObservation, ...] = tuple(
        item for item in (previous, current) if item is not None
    )
    if (
        not risk.permits_entry
        or risk.trade_plan_id != plan.trade_plan_id
        or risk.trade_plan_sha256 != plan.integrity_hash
        or risk.kr370_source_identity != kr370_source_identity
    ):
        pass
    elif context is None:
        state, reason = Kr380V2State.NO_TRIGGER, "EXECUTION_CONTEXT_UNAVAILABLE"
    elif not _ecpc_binding(plan, risk, context):
        state, reason = Kr380V2State.NO_TRIGGER, "EXECUTION_CONTEXT_BINDING_INVALID"
    elif context.outcome is EcpcV2Outcome.PENDING:
        state, reason = Kr380V2State.FORMING, "EXECUTION_CONTEXT_PENDING"
    elif context.outcome is EcpcV2Outcome.EXTENDED:
        state, reason = (
            (Kr380V2State.FORMING, "EXECUTION_CONTEXT_EXTENDED_NOT_FINAL")
            if current is None
            else (Kr380V2State.EXTENDED, "EXECUTION_CONTEXT_EXTENDED")
        )
    elif context.outcome is EcpcV2Outcome.FAILED:
        state, reason = (
            (Kr380V2State.FORMING, "EXECUTION_CONTEXT_FAILED_NOT_FINAL")
            if current is None
            else (Kr380V2State.FAILED, "EXECUTION_CONTEXT_FAILED")
        )
    elif current is None:
        state, reason = Kr380V2State.FORMING, "ENTRY_OBSERVATION_PENDING"
    else:
        state, reason = _entry_state(plan, context, previous, current)
    source_ids = tuple(item.observation_id for item in observations)
    sequences = tuple(
        -1 if item.source_sequence is None else item.source_sequence
        for item in observations
    )
    values: dict[str, Any] = dict(
        entry_outcome_id="KR380-V2-" + sha256(_canonical((
            plan.trade_plan_id, risk.risk_result_id,
            None if context is None else context.context_identity,
            source_ids, state.value, reason,
        ))).hexdigest(),
        native_run_identity=plan.native_run_identity,
        canonical_instrument=plan.canonical_instrument,
        direction=plan.native_direction.value,
        kr370_source_identity=kr370_source_identity,
        trade_plan_id=plan.trade_plan_id,
        trade_plan_sha256=plan.integrity_hash,
        risk_result_id=risk.risk_result_id,
        ecpc_context_identity=None if context is None else context.context_identity,
        monitoring_binding_id=None if context is None else context.monitoring_binding_id,
        observation_boundary=(
            plan.observation_boundary if current is None else current.boundary
        ),
        source_observation_ids=source_ids, source_sequence=sequences,
        state=state, reason=reason, occurred_at=evaluated_at,
        provenance=tuple(dict.fromkeys((
            plan.trade_plan_id, risk.risk_result_id, kr370_source_identity,
            *(source_ids or ("NO_OBSERVATION",)), "ADR-0013", "KR-380",
        ))),
        contract_identity=KR380_CONTRACT_ID,
        contract_version=KR380_CONTRACT_VERSION,
        owner_identity="KR-380", state_family_identity="KR380_ENTRY_OUTCOME",
        policy_identity=KR380_POLICY_ID, policy_version=KR380_POLICY_VERSION,
        broker_authority=NO_BROKER_AUTHORITY,
    )
    return Kr380EntryOutcomeV2(integrity_sha256=_values_digest(values), **values)


def activate_objective_model_v1(
    plan: TradePlanRecord,
    outcome: Kr380EntryOutcomeV2,
    *, monitoring_state: MonitoringConnectionState,
) -> ObjectiveModelRecordV1:
    expected = (
        Kr380V2State.LONG_ENTRY_TRIGGERED
        if plan.native_direction is V1Direction.LONG
        else Kr380V2State.SHORT_ENTRY_TRIGGERED
    )
    if (
        outcome.state is not expected
        or outcome.trade_plan_id != plan.trade_plan_id
        or outcome.trade_plan_sha256 != plan.integrity_hash
        or outcome.native_run_identity != plan.native_run_identity
        or outcome.canonical_instrument != plan.canonical_instrument
        or any(item is None for item in (
            plan.entry, plan.stop, plan.canonical_target, plan.invalidation_reference,
        ))
    ):
        raise ValueError("KR390_V2_HANDOFF_INVALID")
    values: dict[str, Any] = dict(
        model_trade_id="OBJECTIVE-MODEL-" + sha256(_canonical((
            plan.trade_plan_id, outcome.entry_outcome_id,
        ))).hexdigest(),
        native_run_identity=plan.native_run_identity,
        canonical_instrument=plan.canonical_instrument,
        direction=plan.native_direction.value,
        trade_plan_id=plan.trade_plan_id,
        trade_plan_sha256=plan.integrity_hash,
        risk_result_id=outcome.risk_result_id,
        entry_outcome_id=outcome.entry_outcome_id,
        entry=plan.entry, stop=plan.stop, target=plan.canonical_target,
        invalidation_reference=plan.invalidation_reference,
        state=ObjectiveModelState.ACTIVE,
        monitoring_state=monitoring_state,
        activated_at=outcome.occurred_at,
        source_observation_ids=outcome.source_observation_ids,
        provenance=(outcome.entry_outcome_id, plan.trade_plan_id, "ADR-0013", "KR-390"),
        contract_identity=OBJECTIVE_MODEL_CONTRACT_ID,
        contract_version=OBJECTIVE_MODEL_CONTRACT_VERSION,
        sponsor_position_identity=None, broker_authority=NO_BROKER_AUTHORITY,
    )
    return ObjectiveModelRecordV1(integrity_sha256=_values_digest(values), **values)


class _ImmutableCurrentStore:
    def __init__(self, root: Path, record_type: type, decoder) -> None:  # type: ignore[no-untyped-def]
        self.root = Path(root).expanduser()
        if not self.root.is_absolute() or self.root == Path("/"):
            raise ValueError("NATIVE_PRODUCTION_STORE_ROOT_INVALID")
        self._record_type = record_type
        self._decoder = decoder
        self._lock = RLock()

    def retain(self, record: object, *, current_key: str) -> Path:
        if type(record) is not self._record_type or not current_key:
            raise ValueError("NATIVE_PRODUCTION_RECORD_INVALID")
        record_id = _record_identity(record)
        payload = {"record_type": self._record_type.__name__, "record": _primitive(record)}
        payload["envelope_sha256"] = sha256(_canonical(payload)).hexdigest()
        path = self.root / "records" / f"{record_id}.json"
        pointer = self.root / "current" / f"{sha256(current_key.encode()).hexdigest()}.json"
        with self._lock:
            _atomic_json(path, payload, immutable=True)
            _atomic_json(pointer, {"record_id": record_id, "current_key": current_key}, immutable=False)
        return path

    def load_current(self, current_key: str):  # type: ignore[no-untyped-def]
        pointer = self.root / "current" / f"{sha256(current_key.encode()).hexdigest()}.json"
        if not pointer.exists():
            return None
        reference = json.loads(pointer.read_text(encoding="utf-8"))
        if reference.get("current_key") != current_key:
            raise ValueError("NATIVE_PRODUCTION_POINTER_INVALID")
        path = self.root / "records" / f"{reference.get('record_id')}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        envelope = dict(payload)
        expected = envelope.pop("envelope_sha256", None)
        if (
            payload.get("record_type") != self._record_type.__name__
            or not _digest(expected)
            or sha256(_canonical(envelope)).hexdigest() != expected
        ):
            raise ValueError("NATIVE_PRODUCTION_STORED_INTEGRITY_INVALID")
        return self._decoder(payload.get("record"))


class LocalPortfolioStateV1Store(_ImmutableCurrentStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root, PortfolioStateV1, _portfolio_from_dict)

    def retain_current(self, record: PortfolioStateV1) -> Path:
        return self.retain(record, current_key="CURRENT_PORTFOLIO_STATE")

    def load_current_state(self) -> PortfolioStateV1 | None:
        return self.load_current("CURRENT_PORTFOLIO_STATE")


class LocalRiskPermissionV1Store(_ImmutableCurrentStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root, RiskPermissionV1, _risk_from_dict)

    def retain_current(self, record: RiskPermissionV1) -> Path:
        return self.retain(record, current_key=record.trade_plan_id)

    def load_for_plan(self, trade_plan_id: str) -> RiskPermissionV1 | None:
        return self.load_current(trade_plan_id)


class LocalKr380V2Store(_ImmutableCurrentStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root, Kr380EntryOutcomeV2, _kr380_from_dict)

    def retain_current(self, record: Kr380EntryOutcomeV2) -> Path:
        return self.retain(record, current_key=record.trade_plan_id)

    def load_for_plan(self, trade_plan_id: str) -> Kr380EntryOutcomeV2 | None:
        return self.load_current(trade_plan_id)


class LocalObjectiveModelV1Store(_ImmutableCurrentStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root, ObjectiveModelRecordV1, _model_from_dict)

    def retain_current(self, record: ObjectiveModelRecordV1) -> Path:
        return self.retain(record, current_key=record.trade_plan_id)

    def load_for_plan(self, trade_plan_id: str) -> ObjectiveModelRecordV1 | None:
        return self.load_current(trade_plan_id)


def _entry_state(
    plan: TradePlanRecord, context: NativeEcpcV2Context,
    previous: MonitoringObservation | None, current: MonitoringObservation,
) -> tuple[Kr380V2State, str]:
    if (
        current.candidate_id != plan.trade_plan_id
        or current.monitoring_binding_id != context.monitoring_binding_id
        or current.observation_type not in {
            MonitoringSubmissionType.FACTUAL_MARKET_TICK,
            MonitoringSubmissionType.ENTRY_LEVEL_CROSSED,
        }
        or current.observed_price is None
    ):
        return Kr380V2State.FAILED, "ENTRY_OBSERVATION_BINDING_INVALID"
    entry = plan.entry
    assert entry is not None
    beyond = (
        current.observed_price >= entry
        if plan.native_direction is V1Direction.LONG
        else current.observed_price <= entry
    )
    if previous is None:
        return (
            (Kr380V2State.FAILED, "RECONCILIATION_REQUIRED_PRE_ENTRY")
            if beyond else
            (Kr380V2State.FORMING, "ENTRY_NOT_TRIGGERED")
        )
    if (
        previous.candidate_id != current.candidate_id
        or previous.monitoring_binding_id != current.monitoring_binding_id
        or previous.observation_type not in {
            MonitoringSubmissionType.FACTUAL_MARKET_TICK,
            MonitoringSubmissionType.ENTRY_LEVEL_CROSSED,
        }
        or previous.observed_price is None
    ):
        return Kr380V2State.FAILED, "ENTRY_OBSERVATION_BINDING_INVALID"
    ordered = previous.observed_at < current.observed_at and (
        previous.source_sequence is None or current.source_sequence is None
        or previous.source_sequence < current.source_sequence
    )
    continuous = current.previous_interval_available and current.session_continuous
    deterministic = previous.ordering_deterministic and current.ordering_deterministic and ordered
    if not continuous or not deterministic:
        return Kr380V2State.FAILED, "RECONCILIATION_REQUIRED_PRE_ENTRY"
    previous_pre_side = (
        previous.observed_price < entry
        if plan.native_direction is V1Direction.LONG
        else previous.observed_price > entry
    )
    if beyond and not previous_pre_side:
        return Kr380V2State.FAILED, "RECONCILIATION_REQUIRED_PRE_ENTRY"
    if previous_pre_side and beyond:
        return (
            Kr380V2State.LONG_ENTRY_TRIGGERED
            if plan.native_direction is V1Direction.LONG
            else Kr380V2State.SHORT_ENTRY_TRIGGERED,
            "CONSECUTIVE_ACCEPTED_OBSERVATIONS_PROVE_ENTRY",
        )
    return Kr380V2State.FORMING, "ENTRY_NOT_TRIGGERED"


def _ecpc_binding(plan: TradePlanRecord, risk: RiskPermissionV1, context: NativeEcpcV2Context) -> bool:
    return (
        context.native_run_identity == plan.native_run_identity
        and context.canonical_instrument == plan.canonical_instrument
        and context.direction == plan.native_direction.value
        and context.trade_plan_id == plan.trade_plan_id
        and context.trade_plan_sha256 == plan.integrity_hash
        and context.risk_result_id == risk.risk_result_id
    )


def _record_identity(record: object) -> str:
    identity_field = {
        PortfolioStateV1: "portfolio_state_identity",
        RiskPermissionV1: "risk_result_id",
        Kr380EntryOutcomeV2: "entry_outcome_id",
        ObjectiveModelRecordV1: "model_trade_id",
    }.get(type(record))
    if identity_field is None:
        raise ValueError("NATIVE_PRODUCTION_RECORD_ID_UNAVAILABLE")
    for name in (identity_field,):
        value = getattr(record, name, None)
        if isinstance(value, str) and value:
            return value
    raise ValueError("NATIVE_PRODUCTION_RECORD_ID_UNAVAILABLE")


def _record_digest(record: object) -> str:
    payload = _primitive(record)
    payload["integrity_sha256"] = ""  # type: ignore[index]
    return sha256(_canonical(payload)).hexdigest()


def _values_digest(values: dict[str, Any]) -> str:
    return sha256(_canonical({**values, "integrity_sha256": ""})).hexdigest()


def _primitive(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(_primitive(value), sort_keys=True, separators=(",", ":")).encode()


def _atomic_json(path: Path, payload: dict[str, Any], *, immutable: bool) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and immutable:
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError("NATIVE_PRODUCTION_IMMUTABLE_CONFLICT")
        return
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(encoded, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _portfolio_from_dict(value: Any) -> PortfolioStateV1:
    data = dict(value)
    data["as_of_boundary"] = datetime.fromisoformat(data["as_of_boundary"])
    data["objective_exposures"] = tuple(PortfolioExposureFact(
        item["exposure_identity"], PortfolioExposureKind(item["kind"]),
        item["canonical_instrument"], item["direction"], item["lifecycle_identity"],
        item["source_record_identity"],
    ) for item in data["objective_exposures"])
    data["sponsor_exposures"] = tuple(PortfolioExposureFact(
        item["exposure_identity"], PortfolioExposureKind(item["kind"]),
        item["canonical_instrument"], item["direction"], item["lifecycle_identity"],
        item["source_record_identity"],
    ) for item in data["sponsor_exposures"])
    data["rule_facts"] = tuple(PortfolioRuleFact(
        item["rule_identity"], PortfolioRuleDisposition(item["disposition"]),
        item["reason_code"], item["source_identity"],
    ) for item in data["rule_facts"])
    for name in ("source_identities", "provenance"):
        data[name] = tuple(data[name])
    return PortfolioStateV1(**data)


def _risk_from_dict(value: Any) -> RiskPermissionV1:
    data = dict(value)
    data["evaluation_boundary"] = datetime.fromisoformat(data["evaluation_boundary"])
    data["evaluated_at"] = datetime.fromisoformat(data["evaluated_at"])
    data["state"] = RiskState(data["state"])
    for name in ("reason_codes", "constraints", "provenance"):
        data[name] = tuple(data[name])
    return RiskPermissionV1(**data)


def _kr380_from_dict(value: Any) -> Kr380EntryOutcomeV2:
    data = dict(value)
    data["observation_boundary"] = datetime.fromisoformat(data["observation_boundary"])
    data["occurred_at"] = datetime.fromisoformat(data["occurred_at"])
    data["state"] = Kr380V2State(data["state"])
    for name in ("source_observation_ids", "source_sequence", "provenance"):
        data[name] = tuple(data[name])
    return Kr380EntryOutcomeV2(**data)


def _model_from_dict(value: Any) -> ObjectiveModelRecordV1:
    data = dict(value)
    for name in ("entry", "stop", "target", "invalidation_reference"):
        data[name] = Decimal(data[name])
    data["state"] = ObjectiveModelState(data["state"])
    data["monitoring_state"] = MonitoringConnectionState(data["monitoring_state"])
    data["activated_at"] = datetime.fromisoformat(data["activated_at"])
    for name in ("source_observation_ids", "provenance"):
        data[name] = tuple(data[name])
    return ObjectiveModelRecordV1(**data)


__all__ = [
    "EcpcV2Blocker", "EcpcV2Outcome", "Kr380EntryOutcomeV2", "Kr380V2State",
    "LocalKr380V2Store", "LocalObjectiveModelV1Store", "LocalPortfolioStateV1Store",
    "LocalRiskPermissionV1Store", "NativeEcpcV2Context", "ObjectiveModelRecordV1",
    "PortfolioExposureFact", "PortfolioExposureKind", "PortfolioRuleDisposition",
    "PortfolioRuleFact", "PortfolioStateV1", "RiskPermissionV1",
    "activate_objective_model_v1", "create_portfolio_state_v1",
    "evaluate_kr380_v2", "evaluate_risk_permission_v1", "produce_native_ecpc_v2",
]
