"""Immutable Intraday WO-16 Sponsor-decision contract foundation.

This module defines values and canonical identities only. It intentionally
contains no application service, persistence, runtime, Browser, Provider,
position, execution, monitoring, closure, notification, P&L, or broker logic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import Wo13GeometryAvailability
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo14 import Wo14ObservationState
from kronos.intraday.wo15 import Wo15QualificationPath, Wo15TimingState
from kronos.market.schedule import MarketSessionState


WO16_CONTRACT_VERSION = "1.0.0"
WO16_AUTHORITY = "EXPLICIT_SPONSOR_DECISION_AND_FACTUAL_LIFECYCLE_ADMISSION_ONLY"
WO16_POLICY_IDENTITY = (
    "KRONOS-INTRADAY-WO16-SPONSOR-DECISION-LIFECYCLE-ADMISSION-POLICY-V1"
)
WO16_POLICY_VERSION = "1.0.0"
WO16_POLICY_CHECKSUM = (
    "f9ab891659500abad755cdd272527bfd6e406422042b825b209620d934a3ce9c"
)

WO16_SNAPSHOT_IDENTITY = "KRONOS-INTRADAY-WO16-SPONSOR-DECISION-SNAPSHOT-V1"
WO16_DECISION_IDENTITY = "KRONOS-INTRADAY-WO16-SPONSOR-DECISION-V1"
WO16_ADMISSION_IDENTITY = "KRONOS-INTRADAY-WO16-LIFECYCLE-ADMISSION-V1"
WO16_INVALID_OPERATION_IDENTITY = "KRONOS-INTRADAY-WO16-INVALID-OPERATION-V1"
WO16_CURRENT_DECISION_IDENTITY = "KRONOS-INTRADAY-CURRENT-WO16-DECISION-V1"

WO16_WO13_BINDING_IDENTITY = "KRONOS-INTRADAY-WO16-WO13-TRADE-PLAN-BINDING-V1"
WO16_WO14_BINDING_IDENTITY = (
    "KRONOS-INTRADAY-WO16-WO14-RISK-OBSERVATION-BINDING-V1"
)
WO16_WO15_BINDING_IDENTITY = (
    "KRONOS-INTRADAY-WO16-WO15-TIMING-HANDOFF-BINDING-V1"
)
WO16_SESSION_BINDING_IDENTITY = (
    "KRONOS-INTRADAY-WO16-DOMAIN-008-SESSION-FACT-BINDING-V1"
)
WO16_UPSTREAM_LINEAGE_IDENTITY = "KRONOS-INTRADAY-WO16-UPSTREAM-LINEAGE-V1"
WO16_SUCCESSOR_LINEAGE_IDENTITY = "KRONOS-INTRADAY-WO16-SUCCESSOR-LINEAGE-V1"


class Wo16ContractError(ValueError):
    """Sanitized WO-16 contract failure."""


class Wo16SponsorDecision(StrEnum):
    PAPER = "PAPER"
    LIVE = "LIVE"
    IGNORE = "IGNORE"


class Wo16LifecycleAdmissionDisposition(StrEnum):
    PENDING_POSITION_EVIDENCE = "PENDING_POSITION_EVIDENCE"
    NOT_APPLICABLE_IGNORE = "NOT_APPLICABLE_IGNORE"


class Wo16DecisionSource(StrEnum):
    LOCAL_SPONSOR_BROWSER_ACTION = "LOCAL_SPONSOR_BROWSER_ACTION"


class Wo16FactAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class Wo16AdmissionReason(StrEnum):
    PAPER_INTENT_RECORDED = "PAPER_INTENT_RECORDED"
    LIVE_INTENT_RECORDED = "LIVE_INTENT_RECORDED"
    EXACT_LINEAGE_IGNORED = "EXACT_LINEAGE_IGNORED"


class Wo16SuccessorTrigger(StrEnum):
    WO13_PLAN = "WO13_PLAN"
    WO15_TIMING_HANDOFF = "WO15_TIMING_HANDOFF"
    MARKET_SESSION = "MARKET_SESSION"
    MCX_ACTIVE_CONTRACT_OR_ROLL_LINEAGE = "MCX_ACTIVE_CONTRACT_OR_ROLL_LINEAGE"


@dataclass(frozen=True, slots=True)
class Wo16PolicyBinding:
    policy_identity: str = WO16_POLICY_IDENTITY
    policy_version: str = WO16_POLICY_VERSION
    policy_checksum: str = WO16_POLICY_CHECKSUM
    authority: str = WO16_AUTHORITY
    market_analysis_authority: bool = False
    trade_plan_geometry_authority: bool = False
    risk_permission_authority: bool = False
    risk_veto_authority: bool = False
    entry_timing_authority: bool = False
    provider_acquisition_authority: bool = False
    position_authority: bool = False
    quantity_authority: bool = False
    paper_simulation_authority: bool = False
    live_execution_authority: bool = False
    broker_authority: bool = False
    monitoring_authority: bool = False
    closure_authority: bool = False
    notification_authority: bool = False
    journal_analytics_authority: bool = False
    pnl_authority: bool = False
    realised_r_authority: bool = False

    def __post_init__(self) -> None:
        if (
            self.policy_identity != WO16_POLICY_IDENTITY
            or self.policy_version != WO16_POLICY_VERSION
            or self.policy_checksum != WO16_POLICY_CHECKSUM
            or self.authority != WO16_AUTHORITY
            or any(
                value
                for name, value in asdict(self).items()
                if name.endswith("_authority")
            )
        ):
            raise Wo16ContractError("WO16_POLICY_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16TradePlanBinding:
    binding_identity: str
    binding_integrity: str
    current_pointer_identity: str
    current_pointer_integrity: str
    trade_plan_identity: str
    trade_plan_integrity: str
    source_handoff_identity: str
    source_handoff_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    direction: SemanticDirection
    setup_family: Wo13SetupFamily
    instrument_identity: str
    actual_contract_identity: str | None
    contract_expiry: date | None
    roll_lineage_identity: str | None
    geometry_availability: Wo13GeometryAvailability
    entry_reference: Decimal
    entry_condition: str
    stop: Decimal
    thesis_invalidation_reference: Decimal
    thesis_invalidation_event: str
    canonical_target: Decimal
    risk_distance: Decimal
    reward_distance: Decimal
    model_rr: Decimal
    wo13_policy_identity: str
    wo13_policy_version: str
    wo13_policy_checksum: str
    source_evidence_identities: tuple[str, ...]
    source_evidence_integrities: tuple[str, ...]
    provenance: tuple[str, ...]
    schema_identity: str = WO16_WO13_BINDING_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION
    geometry_authority: bool = False
    risk_authority: bool = False
    timing_authority: bool = False
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        _reject_non_decimal(
            self.entry_reference,
            self.stop,
            self.thesis_invalidation_reference,
            self.canonical_target,
            self.risk_distance,
            self.reward_distance,
            self.model_rr,
        )
        values = _without(self, "binding_identity", "binding_integrity")
        mcx = self.market_family is IntradayMarketFamily.MCX
        mcx_values = (
            self.actual_contract_identity,
            self.contract_expiry,
            self.roll_lineage_identity,
        )
        if (
            not _texts(
                (
                    self.current_pointer_identity,
                    self.current_pointer_integrity,
                    self.trade_plan_identity,
                    self.trade_plan_integrity,
                    self.source_handoff_identity,
                    self.source_handoff_integrity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.entry_condition,
                    self.thesis_invalidation_event,
                    self.wo13_policy_identity,
                    self.wo13_policy_version,
                    self.wo13_policy_checksum,
                    *self.source_evidence_identities,
                    *self.source_evidence_integrities,
                    *self.provenance,
                )
            )
            or type(self.market_family) is not IntradayMarketFamily
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.setup_family) is not Wo13SetupFamily
            or self.geometry_availability
            is not Wo13GeometryAvailability.GEOMETRY_COMPLETE
            or mcx != all(value is not None for value in mcx_values)
            or (not mcx and any(value is not None for value in mcx_values))
            or len(self.source_evidence_identities)
            != len(self.source_evidence_integrities)
            or self.schema_identity != WO16_WO13_BINDING_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or any(
                (
                    self.geometry_authority,
                    self.risk_authority,
                    self.timing_authority,
                    self.sponsor_decision_authority,
                    self.execution_authority,
                    self.broker_authority,
                )
            )
            or self.binding_identity != _identity("INTRADAY-WO16-WO13-BINDING-", values)
            or self.binding_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-WO13-BINDING-", values)
        ):
            raise Wo16ContractError("WO16_WO13_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16RiskObservationBinding:
    binding_identity: str
    binding_integrity: str
    current_pointer_identity: str
    current_pointer_integrity: str
    observation_identity: str
    observation_integrity: str
    trade_plan_identity: str
    trade_plan_integrity: str
    state: Wo14ObservationState
    calculation_provenance_integrity: str
    wo14_policy_identity: str
    wo14_policy_version: str
    wo14_policy_checksum: str
    provenance: tuple[str, ...]
    schema_identity: str = WO16_WO14_BINDING_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION
    authority: str = "RISK_OBSERVATION_ONLY"
    trade_permission_authority: bool = False
    trade_veto_authority: bool = False
    timing_authority: bool = False
    sizing_authority: bool = False
    final_quantity_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "binding_identity", "binding_integrity")
        if (
            not _texts(
                (
                    self.current_pointer_identity,
                    self.current_pointer_integrity,
                    self.observation_identity,
                    self.observation_integrity,
                    self.trade_plan_identity,
                    self.trade_plan_integrity,
                    self.calculation_provenance_integrity,
                    self.wo14_policy_identity,
                    self.wo14_policy_version,
                    self.wo14_policy_checksum,
                    *self.provenance,
                )
            )
            or type(self.state) is not Wo14ObservationState
            or self.authority != "RISK_OBSERVATION_ONLY"
            or any(
                (
                    self.trade_permission_authority,
                    self.trade_veto_authority,
                    self.timing_authority,
                    self.sizing_authority,
                    self.final_quantity_authority,
                    self.execution_authority,
                )
            )
            or self.schema_identity != WO16_WO14_BINDING_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or self.binding_identity != _identity("INTRADAY-WO16-WO14-BINDING-", values)
            or self.binding_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-WO14-BINDING-", values)
        ):
            raise Wo16ContractError("WO16_WO14_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16TimingHandoffBinding:
    binding_identity: str
    binding_integrity: str
    current_pointer_identity: str
    current_pointer_integrity: str
    handoff_identity: str
    handoff_integrity: str
    trade_plan_identity: str
    trade_plan_integrity: str
    timing_cycle_identity: str
    timing_cycle_integrity: str
    timing_observation_identity: str
    timing_observation_integrity: str
    timing_transition_identity: str
    timing_transition_integrity: str
    prior_state: Wo15TimingState
    current_state: Wo15TimingState
    transition_cause: str
    qualification_path: Wo15QualificationPath
    completed_five_minute_evidence_identity: str
    completed_five_minute_evidence_integrity: str
    evidence_boundary: datetime
    session_identity: str
    calendar_identity: str
    calendar_version: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    wo15_policy_identity: str
    wo15_policy_version: str
    wo15_policy_checksum: str
    wo14_observation_identity: str | None
    wo14_observation_integrity: str | None
    predecessor_handoff_identity: str | None
    supersession_lineage_identity: str | None
    provenance: tuple[str, ...]
    schema_identity: str = WO16_WO15_BINDING_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION
    timing_evidence_authority: bool = False
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "binding_identity", "binding_integrity")
        mcx_values = (self.actual_contract_identity, self.roll_lineage_identity)
        risk_values = (self.wo14_observation_identity, self.wo14_observation_integrity)
        if (
            not _texts(
                (
                    self.current_pointer_identity,
                    self.current_pointer_integrity,
                    self.handoff_identity,
                    self.handoff_integrity,
                    self.trade_plan_identity,
                    self.trade_plan_integrity,
                    self.timing_cycle_identity,
                    self.timing_cycle_integrity,
                    self.timing_observation_identity,
                    self.timing_observation_integrity,
                    self.timing_transition_identity,
                    self.timing_transition_integrity,
                    self.transition_cause,
                    self.completed_five_minute_evidence_identity,
                    self.completed_five_minute_evidence_integrity,
                    self.session_identity,
                    self.calendar_identity,
                    self.calendar_version,
                    self.instrument_identity,
                    self.wo15_policy_identity,
                    self.wo15_policy_version,
                    self.wo15_policy_checksum,
                    *self.provenance,
                )
            )
            or type(self.prior_state) is not Wo15TimingState
            or self.current_state is not Wo15TimingState.TIMING_QUALIFIED
            or type(self.qualification_path) is not Wo15QualificationPath
            or not _aware(self.evidence_boundary)
            or not (all(value is None for value in risk_values) or _texts(risk_values))
            or not (all(value is None for value in mcx_values) or _texts(mcx_values))
            or not _optional_text(self.predecessor_handoff_identity)
            or not _optional_text(self.supersession_lineage_identity)
            or self.schema_identity != WO16_WO15_BINDING_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or any(
                (
                    self.timing_evidence_authority,
                    self.sponsor_decision_authority,
                    self.execution_authority,
                    self.broker_authority,
                )
            )
            or self.binding_identity != _identity("INTRADAY-WO16-WO15-BINDING-", values)
            or self.binding_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-WO15-BINDING-", values)
        ):
            raise Wo16ContractError("WO16_WO15_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16SessionFactBinding:
    binding_identity: str
    binding_integrity: str
    wo15_session_binding_identity: str
    wo15_session_binding_integrity: str
    exchange: str
    trading_date: date
    session_identity: str
    calendar_identity: str
    calendar_version: str
    market_session_state: MarketSessionState
    active_window_opens_at: datetime
    active_window_closes_at: datetime
    observed_at: datetime
    availability: Wo16FactAvailability
    session_open: bool
    session_end: bool
    source_identity: str
    source_version: str
    provenance: tuple[str, ...]
    schema_identity: str = WO16_SESSION_BINDING_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "binding_identity", "binding_integrity")
        if (
            not _texts(
                (
                    self.wo15_session_binding_identity,
                    self.wo15_session_binding_integrity,
                    self.exchange,
                    self.session_identity,
                    self.calendar_identity,
                    self.calendar_version,
                    self.source_identity,
                    self.source_version,
                    *self.provenance,
                )
            )
            or type(self.trading_date) is not date
            or self.market_session_state is not MarketSessionState.OPEN
            or not all(
                _aware(value)
                for value in (
                    self.active_window_opens_at,
                    self.active_window_closes_at,
                    self.observed_at,
                )
            )
            or self.active_window_opens_at >= self.active_window_closes_at
            or not (
                self.active_window_opens_at
                <= self.observed_at.astimezone(self.active_window_opens_at.tzinfo)
                < self.active_window_closes_at
            )
            or self.availability is not Wo16FactAvailability.AVAILABLE
            or self.session_open is not True
            or self.session_end is not False
            or self.schema_identity != WO16_SESSION_BINDING_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or self.binding_identity != _identity("INTRADAY-WO16-SESSION-BINDING-", values)
            or self.binding_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-SESSION-BINDING-", values)
        ):
            raise Wo16ContractError("WO16_SESSION_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16UpstreamLineage:
    lineage_identity: str
    lineage_integrity: str
    trade_plan: Wo16TradePlanBinding
    risk_observation: Wo16RiskObservationBinding
    timing_handoff: Wo16TimingHandoffBinding
    session: Wo16SessionFactBinding
    policy: Wo16PolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO16_UPSTREAM_LINEAGE_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "lineage_identity", "lineage_integrity")
        if (
            type(self.trade_plan) is not Wo16TradePlanBinding
            or type(self.risk_observation) is not Wo16RiskObservationBinding
            or type(self.timing_handoff) is not Wo16TimingHandoffBinding
            or type(self.session) is not Wo16SessionFactBinding
            or type(self.policy) is not Wo16PolicyBinding
            or not _texts(self.provenance)
            or self.schema_identity != WO16_UPSTREAM_LINEAGE_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or self.lineage_identity != _identity("INTRADAY-WO16-UPSTREAM-LINEAGE-", values)
            or self.lineage_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-UPSTREAM-LINEAGE-", values)
        ):
            raise Wo16ContractError("WO16_UPSTREAM_LINEAGE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16SponsorDecisionSnapshot:
    snapshot_identity: str
    snapshot_integrity: str
    upstream_lineage: Wo16UpstreamLineage
    decision_eligible_observed_at: datetime
    snapshot_timestamp: datetime
    policy: Wo16PolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO16_SNAPSHOT_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION
    geometry_authority: bool = False
    risk_authority: bool = False
    timing_authority: bool = False
    position_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "snapshot_identity", "snapshot_integrity")
        if (
            type(self.upstream_lineage) is not Wo16UpstreamLineage
            or not _aware(self.decision_eligible_observed_at)
            or not _aware(self.snapshot_timestamp)
            or self.decision_eligible_observed_at > self.snapshot_timestamp
            or type(self.policy) is not Wo16PolicyBinding
            or self.policy != self.upstream_lineage.policy
            or not _texts(self.provenance)
            or self.schema_identity != WO16_SNAPSHOT_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or any(
                (
                    self.geometry_authority,
                    self.risk_authority,
                    self.timing_authority,
                    self.position_authority,
                    self.execution_authority,
                    self.broker_authority,
                )
            )
            or self.snapshot_identity != _identity("INTRADAY-WO16-SNAPSHOT-", values)
            or self.snapshot_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-SNAPSHOT-", values)
        ):
            raise Wo16ContractError("WO16_SPONSOR_DECISION_SNAPSHOT_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16SponsorDecisionRecord:
    decision_identity: str
    decision_integrity: str
    request_identity: str
    request_integrity: str
    snapshot_identity: str
    snapshot_integrity: str
    timing_handoff_identity: str
    choice: Wo16SponsorDecision
    source: Wo16DecisionSource
    decision_timestamp: datetime
    predecessor_decision_identity: str | None
    supersession_lineage_identity: str | None
    policy: Wo16PolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO16_DECISION_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION
    position_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "decision_identity", "decision_integrity")
        if (
            not _texts(
                (
                    self.request_identity,
                    self.request_integrity,
                    self.snapshot_identity,
                    self.snapshot_integrity,
                    self.timing_handoff_identity,
                    *self.provenance,
                )
            )
            or type(self.choice) is not Wo16SponsorDecision
            or self.source is not Wo16DecisionSource.LOCAL_SPONSOR_BROWSER_ACTION
            or not _aware(self.decision_timestamp)
            or not _optional_text(self.predecessor_decision_identity)
            or not _optional_text(self.supersession_lineage_identity)
            or (self.predecessor_decision_identity is None)
            != (self.supersession_lineage_identity is None)
            or type(self.policy) is not Wo16PolicyBinding
            or self.schema_identity != WO16_DECISION_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or any(
                (self.position_authority, self.execution_authority, self.broker_authority)
            )
            or self.decision_identity != _identity("INTRADAY-WO16-DECISION-", values)
            or self.decision_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-DECISION-", values)
        ):
            raise Wo16ContractError("WO16_SPONSOR_DECISION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16LifecycleAdmissionRecord:
    admission_identity: str
    admission_integrity: str
    decision_identity: str
    decision_integrity: str
    disposition: Wo16LifecycleAdmissionDisposition
    recorded_at: datetime
    reason: Wo16AdmissionReason
    policy: Wo16PolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO16_ADMISSION_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION
    position_consequence: str = "NONE"
    position_authority: bool = False
    fill_authority: bool = False
    quantity_authority: bool = False
    monitoring_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "admission_identity", "admission_integrity")
        if (
            not _texts((self.decision_identity, self.decision_integrity, *self.provenance))
            or type(self.disposition) is not Wo16LifecycleAdmissionDisposition
            or not _aware(self.recorded_at)
            or type(self.reason) is not Wo16AdmissionReason
            or type(self.policy) is not Wo16PolicyBinding
            or self.schema_identity != WO16_ADMISSION_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or self.position_consequence != "NONE"
            or any(
                (
                    self.position_authority,
                    self.fill_authority,
                    self.quantity_authority,
                    self.monitoring_authority,
                    self.execution_authority,
                    self.broker_authority,
                )
            )
            or self.admission_identity != _identity("INTRADAY-WO16-ADMISSION-", values)
            or self.admission_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-ADMISSION-", values)
        ):
            raise Wo16ContractError("WO16_LIFECYCLE_ADMISSION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo16SuccessorLineage:
    lineage_identity: str
    lineage_integrity: str
    predecessor_decision_identity: str
    predecessor_decision_integrity: str
    successor_snapshot_identity: str
    successor_snapshot_integrity: str
    trigger: Wo16SuccessorTrigger
    prior_record_mutation: str
    policy: Wo16PolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO16_SUCCESSOR_LINEAGE_IDENTITY
    schema_version: str = WO16_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "lineage_identity", "lineage_integrity")
        if (
            not _texts(
                (
                    self.predecessor_decision_identity,
                    self.predecessor_decision_integrity,
                    self.successor_snapshot_identity,
                    self.successor_snapshot_integrity,
                    *self.provenance,
                )
            )
            or type(self.trigger) is not Wo16SuccessorTrigger
            or self.prior_record_mutation != "PROHIBITED"
            or type(self.policy) is not Wo16PolicyBinding
            or self.schema_identity != WO16_SUCCESSOR_LINEAGE_IDENTITY
            or self.schema_version != WO16_CONTRACT_VERSION
            or self.lineage_identity != _identity("INTRADAY-WO16-SUCCESSOR-", values)
            or self.lineage_integrity
            != _identity("INTEGRITY-INTRADAY-WO16-SUCCESSOR-", values)
        ):
            raise Wo16ContractError("WO16_SUCCESSOR_LINEAGE_INVALID")


def create_wo16_upstream_lineage(
    *,
    trade_plan: Wo16TradePlanBinding,
    risk_observation: Wo16RiskObservationBinding,
    timing_handoff: Wo16TimingHandoffBinding,
    session: Wo16SessionFactBinding,
    provenance: tuple[str, ...] = ("ADR-0026",),
) -> Wo16UpstreamLineage:
    policy = Wo16PolicyBinding()
    values = {
        "trade_plan": trade_plan,
        "risk_observation": risk_observation,
        "timing_handoff": timing_handoff,
        "session": session,
        "policy": policy,
        "provenance": provenance,
        "schema_identity": WO16_UPSTREAM_LINEAGE_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
    }
    return Wo16UpstreamLineage(
        lineage_identity=_identity("INTRADAY-WO16-UPSTREAM-LINEAGE-", values),
        lineage_integrity=_identity(
            "INTEGRITY-INTRADAY-WO16-UPSTREAM-LINEAGE-", values
        ),
        **values,
    )


def create_wo16_sponsor_decision_snapshot(
    *,
    upstream_lineage: Wo16UpstreamLineage,
    snapshot_timestamp: datetime,
    provenance: tuple[str, ...] = ("ADR-0026",),
) -> Wo16SponsorDecisionSnapshot:
    values = {
        "upstream_lineage": upstream_lineage,
        "decision_eligible_observed_at": upstream_lineage.session.observed_at,
        "snapshot_timestamp": snapshot_timestamp,
        "policy": upstream_lineage.policy,
        "provenance": provenance,
        "schema_identity": WO16_SNAPSHOT_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
        "geometry_authority": False,
        "risk_authority": False,
        "timing_authority": False,
        "position_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo16SponsorDecisionSnapshot(
        snapshot_identity=_identity("INTRADAY-WO16-SNAPSHOT-", values),
        snapshot_integrity=_identity("INTEGRITY-INTRADAY-WO16-SNAPSHOT-", values),
        **values,
    )


def create_wo16_sponsor_decision_record(
    *,
    snapshot: Wo16SponsorDecisionSnapshot,
    request_identity: str,
    request_integrity: str,
    choice: Wo16SponsorDecision,
    decision_timestamp: datetime,
    predecessor_decision_identity: str | None = None,
    supersession_lineage_identity: str | None = None,
    provenance: tuple[str, ...] = ("ADR-0026",),
) -> Wo16SponsorDecisionRecord:
    """Construct one immutable value; perform no Sponsor operation."""

    if type(snapshot) is not Wo16SponsorDecisionSnapshot:
        raise Wo16ContractError("WO16_SPONSOR_DECISION_SNAPSHOT_INVALID")
    values = {
        "request_identity": request_identity,
        "request_integrity": request_integrity,
        "snapshot_identity": snapshot.snapshot_identity,
        "snapshot_integrity": snapshot.snapshot_integrity,
        "timing_handoff_identity": (
            snapshot.upstream_lineage.timing_handoff.handoff_identity
        ),
        "choice": choice,
        "source": Wo16DecisionSource.LOCAL_SPONSOR_BROWSER_ACTION,
        "decision_timestamp": decision_timestamp,
        "predecessor_decision_identity": predecessor_decision_identity,
        "supersession_lineage_identity": supersession_lineage_identity,
        "policy": snapshot.policy,
        "provenance": provenance,
        "schema_identity": WO16_DECISION_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
        "position_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo16SponsorDecisionRecord(
        decision_identity=_identity("INTRADAY-WO16-DECISION-", values),
        decision_integrity=_identity("INTEGRITY-INTRADAY-WO16-DECISION-", values),
        **values,
    )


def disposition_for_decision(
    choice: Wo16SponsorDecision,
) -> tuple[Wo16LifecycleAdmissionDisposition, Wo16AdmissionReason]:
    if type(choice) is not Wo16SponsorDecision:
        raise Wo16ContractError("WO16_SPONSOR_DECISION_INVALID")
    return {
        Wo16SponsorDecision.PAPER: (
            Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE,
            Wo16AdmissionReason.PAPER_INTENT_RECORDED,
        ),
        Wo16SponsorDecision.LIVE: (
            Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE,
            Wo16AdmissionReason.LIVE_INTENT_RECORDED,
        ),
        Wo16SponsorDecision.IGNORE: (
            Wo16LifecycleAdmissionDisposition.NOT_APPLICABLE_IGNORE,
            Wo16AdmissionReason.EXACT_LINEAGE_IGNORED,
        ),
    }[choice]


def create_wo16_lifecycle_admission_record(
    *,
    decision: Wo16SponsorDecisionRecord,
    recorded_at: datetime,
    provenance: tuple[str, ...] = ("ADR-0026",),
) -> Wo16LifecycleAdmissionRecord:
    """Create the factual disposition value without creating a position."""

    if type(decision) is not Wo16SponsorDecisionRecord:
        raise Wo16ContractError("WO16_SPONSOR_DECISION_INVALID")
    disposition, reason = disposition_for_decision(decision.choice)
    values = {
        "decision_identity": decision.decision_identity,
        "decision_integrity": decision.decision_integrity,
        "disposition": disposition,
        "recorded_at": recorded_at,
        "reason": reason,
        "policy": decision.policy,
        "provenance": provenance,
        "schema_identity": WO16_ADMISSION_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
        "position_consequence": "NONE",
        "position_authority": False,
        "fill_authority": False,
        "quantity_authority": False,
        "monitoring_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo16LifecycleAdmissionRecord(
        admission_identity=_identity("INTRADAY-WO16-ADMISSION-", values),
        admission_integrity=_identity("INTEGRITY-INTRADAY-WO16-ADMISSION-", values),
        **values,
    )


def create_wo16_successor_lineage(
    *,
    predecessor: Wo16SponsorDecisionRecord,
    successor_snapshot: Wo16SponsorDecisionSnapshot,
    trigger: Wo16SuccessorTrigger,
    provenance: tuple[str, ...] = ("ADR-0026",),
) -> Wo16SuccessorLineage:
    if (
        type(predecessor) is not Wo16SponsorDecisionRecord
        or type(successor_snapshot) is not Wo16SponsorDecisionSnapshot
    ):
        raise Wo16ContractError("WO16_SUCCESSOR_LINEAGE_INPUT_INVALID")
    values = {
        "predecessor_decision_identity": predecessor.decision_identity,
        "predecessor_decision_integrity": predecessor.decision_integrity,
        "successor_snapshot_identity": successor_snapshot.snapshot_identity,
        "successor_snapshot_integrity": successor_snapshot.snapshot_integrity,
        "trigger": trigger,
        "prior_record_mutation": "PROHIBITED",
        "policy": successor_snapshot.policy,
        "provenance": provenance,
        "schema_identity": WO16_SUCCESSOR_LINEAGE_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
    }
    return Wo16SuccessorLineage(
        lineage_identity=_identity("INTRADAY-WO16-SUCCESSOR-", values),
        lineage_integrity=_identity("INTEGRITY-INTRADAY-WO16-SUCCESSOR-", values),
        **values,
    )


def canonical_document_bytes(value: object) -> bytes:
    """Return deterministic governed bytes and reject floats/naive datetimes."""

    try:
        return json.dumps(
            _normalize(value), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except Wo16ContractError:
        raise
    except (TypeError, ValueError) as error:
        raise Wo16ContractError("WO16_CANONICAL_DOCUMENT_INVALID") from error


def canonical_sha256(value: object) -> str:
    return sha256(canonical_document_bytes(value)).hexdigest()


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_document_bytes(value)).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        if not _aware(value):
            raise Wo16ContractError("WO16_TIMESTAMP_TIMEZONE_REQUIRED")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise Wo16ContractError("WO16_DECIMAL_INVALID")
        return format(value, "f")
    if isinstance(value, float):
        raise Wo16ContractError("WO16_FLOAT_PROHIBITED")
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise Wo16ContractError("WO16_CANONICAL_KEY_INVALID")
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if value is None or type(value) in {str, int, bool}:
        return value
    raise Wo16ContractError("WO16_CANONICAL_VALUE_INVALID")


def _reject_non_decimal(*values: object) -> None:
    if any(type(value) is not Decimal or not value.is_finite() for value in values):
        raise Wo16ContractError("WO16_DECIMAL_INVALID")


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(value) for value in values)


def _optional_text(value: object) -> bool:
    return value is None or _text(value)


__all__ = [
    name
    for name in globals()
    if name.startswith(("WO16_", "Wo16", "create_", "canonical_", "disposition_"))
]
