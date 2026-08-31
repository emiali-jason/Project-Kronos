"""Immutable Intraday WO-13 Step-31 contract foundation.

Slice 1 defines contracts and invariants only.  It intentionally contains no
pullback/range constructor, geometry arithmetic engine, persistence, runtime,
Browser control, Risk decision, 5M timing, Sponsor decision, or execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13_handoff import (
    WO13_AUTHORITY,
    WO13_CONTRACT_VERSION,
    WO13_POLICY_CHECKSUM,
    WO13_POLICY_IDENTITY,
    WO13_POLICY_VERSION,
    Wo13SetupFamily,
    Wo13Step31Handoff,
)


WO13_REQUEST_IDENTITY = "KRONOS-INTRADAY-WO13-TRADE-CONSTRUCTION-REQUEST-V1"
WO13_TRADE_PLAN_IDENTITY = "KRONOS-INTRADAY-WO13-TRADE-PLAN-V1"
WO13_FIELD_AVAILABILITY_IDENTITY = (
    "KRONOS-INTRADAY-WO13-FIELD-AVAILABILITY-V1"
)
WO13_OPERATION_PROVENANCE_IDENTITY = (
    "KRONOS-INTRADAY-WO13-OPERATION-PROVENANCE-V1"
)
WO13_SUPERSESSION_REFERENCE_IDENTITY = (
    "KRONOS-INTRADAY-WO13-SUPERSESSION-REFERENCE-V1"
)
WO13_SUPERSESSION_LINEAGE_IDENTITY = (
    "KRONOS-INTRADAY-WO13-SUPERSESSION-LINEAGE-V1"
)


class Wo13ContractError(ValueError):
    """Sanitized WO-13 contract validation failure."""


class Wo13GeometryAvailability(StrEnum):
    GEOMETRY_COMPLETE = "GEOMETRY_COMPLETE"
    GEOMETRY_PARTIAL = "GEOMETRY_PARTIAL"
    GEOMETRY_UNAVAILABLE = "GEOMETRY_UNAVAILABLE"


class Wo13FieldAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    AMBIGUOUS = "AMBIGUOUS"
    INCOMPLETE = "INCOMPLETE"


class Wo13GeometryField(StrEnum):
    ENTRY_REFERENCE = "ENTRY_REFERENCE"
    ENTRY_CONDITION = "ENTRY_CONDITION"
    STOP = "STOP"
    STOP_STRUCTURAL_BASIS = "STOP_STRUCTURAL_BASIS"
    THESIS_INVALIDATION_REFERENCE = "THESIS_INVALIDATION_REFERENCE"
    THESIS_INVALIDATION_EVENT = "THESIS_INVALIDATION_EVENT"
    SETUP_NATIVE_TARGET = "SETUP_NATIVE_TARGET"
    CANONICAL_TARGET = "CANONICAL_TARGET"
    TARGET_STRUCTURAL_BASIS = "TARGET_STRUCTURAL_BASIS"
    CONSTRAINING_OBJECTIVE = "CONSTRAINING_OBJECTIVE"
    RISK_DISTANCE = "RISK_DISTANCE"
    REWARD_DISTANCE = "REWARD_DISTANCE"
    MODEL_RR = "MODEL_RR"


class Wo13WarningCode(StrEnum):
    NON_POSITIVE_RISK = "NON_POSITIVE_RISK"
    NON_POSITIVE_REWARD = "NON_POSITIVE_REWARD"
    INVALID_DIRECTIONAL_GEOMETRY = "INVALID_DIRECTIONAL_GEOMETRY"
    NON_FINITE_VALUE = "NON_FINITE_VALUE"
    TICK_NORMALIZATION_FAILURE = "TICK_NORMALIZATION_FAILURE"


class Wo13OperationStage(StrEnum):
    REQUEST_VALIDATION = "REQUEST_VALIDATION"
    HANDOFF_VALIDATION = "HANDOFF_VALIDATION"
    SOURCE_RELOAD = "SOURCE_RELOAD"
    GEOMETRY_ASSEMBLY = "GEOMETRY_ASSEMBLY"
    CONSTRUCTION = "CONSTRUCTION"
    CALCULATION = "CALCULATION"
    PERSISTENCE = "PERSISTENCE"
    POINTER_PUBLICATION = "POINTER_PUBLICATION"


class Wo13OperationOutcome(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Wo13SupersessionReason(StrEnum):
    NEW_EXACT_ELIGIBLE_WO12_CYCLE = "NEW_EXACT_ELIGIBLE_WO12_CYCLE"
    GOVERNED_STRUCTURE_CHANGED = "GOVERNED_STRUCTURE_CHANGED"
    GOVERNED_ACTIVE_CONTRACT_ROLLED = "GOVERNED_ACTIVE_CONTRACT_ROLLED"


@dataclass(frozen=True, slots=True)
class Wo13PolicyBinding:
    policy_identity: str = WO13_POLICY_IDENTITY
    policy_version: str = WO13_POLICY_VERSION
    policy_checksum: str = WO13_POLICY_CHECKSUM
    authority: str = WO13_AUTHORITY
    geometry_frame: str = "15M"
    one_hour_authority: str = "CONTEXT_ONLY"
    five_minute_authority: str = "WO15_KR380_ONLY"
    model_rr_gate: str = "NONE"
    target_count: int = 1

    def __post_init__(self) -> None:
        if (
            self.policy_identity != WO13_POLICY_IDENTITY
            or self.policy_version != WO13_POLICY_VERSION
            or self.policy_checksum != WO13_POLICY_CHECKSUM
            or self.authority != WO13_AUTHORITY
            or self.geometry_frame != "15M"
            or self.one_hour_authority != "CONTEXT_ONLY"
            or self.five_minute_authority != "WO15_KR380_ONLY"
            or self.model_rr_gate != "NONE"
            or self.target_count != 1
        ):
            raise Wo13ContractError("WO13_POLICY_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo13FieldAvailabilityRecord:
    field: Wo13GeometryField
    availability: Wo13FieldAvailability
    reason: str
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    schema_identity: str = WO13_FIELD_AVAILABILITY_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.field) is not Wo13GeometryField
            or type(self.availability) is not Wo13FieldAvailability
            or not _code(self.reason)
            or len(self.source_identities) != len(self.source_integrities)
            or any(not _text(item) for item in (*self.source_identities, *self.source_integrities))
            or self.schema_identity != WO13_FIELD_AVAILABILITY_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
        ):
            raise Wo13ContractError("WO13_FIELD_AVAILABILITY_INVALID")


def create_wo13_field_availability(
    field: Wo13GeometryField,
    availability: Wo13FieldAvailability,
    *,
    reason: str,
    source_identities: tuple[str, ...] = (),
    source_integrities: tuple[str, ...] = (),
) -> Wo13FieldAvailabilityRecord:
    return Wo13FieldAvailabilityRecord(
        field=field,
        availability=availability,
        reason=reason,
        source_identities=source_identities,
        source_integrities=source_integrities,
    )


@dataclass(frozen=True, slots=True)
class Wo13ConstructionRequest:
    request_identity: str
    request_integrity: str
    handoff: Wo13Step31Handoff
    policy: Wo13PolicyBinding
    sponsor_operation_identity: str
    requested_at: datetime
    provenance: tuple[str, ...]
    schema_identity: str = WO13_REQUEST_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    provider_acquisition_authority: bool = False
    latest_resolution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "request_identity", "request_integrity")
        if (
            type(self.handoff) is not Wo13Step31Handoff
            or type(self.policy) is not Wo13PolicyBinding
            or not _texts((self.sponsor_operation_identity, *self.provenance))
            or not _aware(self.requested_at)
            or self.schema_identity != WO13_REQUEST_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.provider_acquisition_authority
            or self.latest_resolution_authority
            or self.request_identity != _identity("INTRADAY-WO13-REQUEST-", values)
            or self.request_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-REQUEST-", values)
        ):
            raise Wo13ContractError("WO13_REQUEST_INVALID")


def create_wo13_construction_request(
    *,
    handoff: Wo13Step31Handoff,
    sponsor_operation_identity: str,
    requested_at: datetime,
    provenance: tuple[str, ...],
) -> Wo13ConstructionRequest:
    values = {
        "handoff": handoff,
        "policy": Wo13PolicyBinding(),
        "sponsor_operation_identity": sponsor_operation_identity,
        "requested_at": requested_at,
        "provenance": provenance,
        "schema_identity": WO13_REQUEST_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "provider_acquisition_authority": False,
        "latest_resolution_authority": False,
    }
    return Wo13ConstructionRequest(
        request_identity=_identity("INTRADAY-WO13-REQUEST-", values),
        request_integrity=_identity("INTEGRITY-INTRADAY-WO13-REQUEST-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13SupersessionReference:
    predecessor_trade_plan_identity: str
    predecessor_trade_plan_integrity: str
    source_wo12_request_identity: str
    source_wo12_result_identity: str
    reason: Wo13SupersessionReason
    supersession_boundary: datetime
    schema_identity: str = WO13_SUPERSESSION_REFERENCE_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not _texts((self.predecessor_trade_plan_identity,
                        self.predecessor_trade_plan_integrity,
                        self.source_wo12_request_identity,
                        self.source_wo12_result_identity))
            or type(self.reason) is not Wo13SupersessionReason
            or not _aware(self.supersession_boundary)
            or self.schema_identity != WO13_SUPERSESSION_REFERENCE_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
        ):
            raise Wo13ContractError("WO13_SUPERSESSION_REFERENCE_INVALID")


def create_wo13_supersession_reference(
    *,
    predecessor_trade_plan_identity: str,
    predecessor_trade_plan_integrity: str,
    source_wo12_request_identity: str,
    source_wo12_result_identity: str,
    reason: Wo13SupersessionReason,
    supersession_boundary: datetime,
) -> Wo13SupersessionReference:
    return Wo13SupersessionReference(
        predecessor_trade_plan_identity=predecessor_trade_plan_identity,
        predecessor_trade_plan_integrity=predecessor_trade_plan_integrity,
        source_wo12_request_identity=source_wo12_request_identity,
        source_wo12_result_identity=source_wo12_result_identity,
        reason=reason,
        supersession_boundary=supersession_boundary,
    )


@dataclass(frozen=True, slots=True)
class Wo13TradePlan:
    trade_plan_identity: str
    trade_plan_integrity: str
    request_identity: str
    request_integrity: str
    source_handoff_identity: str
    source_handoff_integrity: str
    source_wo12_result_identity: str
    source_wo12_result_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    direction: SemanticDirection
    setup_family: Wo13SetupFamily
    analysis_boundary: datetime
    phase: IntradayAnalysisPhase
    instrument_identity: str
    actual_contract_identity: str | None
    entry_reference: Decimal | None
    entry_condition: str | None
    stop: Decimal | None
    stop_structural_basis: str | None
    thesis_invalidation_reference: Decimal | None
    thesis_invalidation_event: str | None
    setup_native_target: Decimal | None
    canonical_target: Decimal | None
    target_structural_basis: str | None
    constraining_objective: Decimal | None
    risk_distance: Decimal | None
    reward_distance: Decimal | None
    model_rr: Decimal | None
    geometry_availability: Wo13GeometryAvailability
    field_availability: tuple[Wo13FieldAvailabilityRecord, ...]
    warnings: tuple[Wo13WarningCode, ...]
    policy: Wo13PolicyBinding
    source_evidence_identities: tuple[str, ...]
    source_evidence_integrities: tuple[str, ...]
    supersession: Wo13SupersessionReference | None
    provenance: tuple[str, ...]
    schema_identity: str = WO13_TRADE_PLAN_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    authority: str = WO13_AUTHORITY
    analytical_promotion_authority: bool = False
    risk_authority: bool = False
    position_sizing_authority: bool = False
    entry_timing_authority: bool = False
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        numeric_names = (
            "entry_reference", "stop", "thesis_invalidation_reference",
            "setup_native_target", "canonical_target", "constraining_objective",
            "risk_distance", "reward_distance", "model_rr",
        )
        for name in numeric_names:
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(value))
        values = _without(self, "trade_plan_identity", "trade_plan_integrity")
        availability = {item.field: item for item in self.field_availability}
        field_values: dict[Wo13GeometryField, object | None] = {
            Wo13GeometryField.ENTRY_REFERENCE: self.entry_reference,
            Wo13GeometryField.ENTRY_CONDITION: self.entry_condition,
            Wo13GeometryField.STOP: self.stop,
            Wo13GeometryField.STOP_STRUCTURAL_BASIS: self.stop_structural_basis,
            Wo13GeometryField.THESIS_INVALIDATION_REFERENCE: self.thesis_invalidation_reference,
            Wo13GeometryField.THESIS_INVALIDATION_EVENT: self.thesis_invalidation_event,
            Wo13GeometryField.SETUP_NATIVE_TARGET: self.setup_native_target,
            Wo13GeometryField.CANONICAL_TARGET: self.canonical_target,
            Wo13GeometryField.TARGET_STRUCTURAL_BASIS: self.target_structural_basis,
            Wo13GeometryField.CONSTRAINING_OBJECTIVE: self.constraining_objective,
            Wo13GeometryField.RISK_DISTANCE: self.risk_distance,
            Wo13GeometryField.REWARD_DISTANCE: self.reward_distance,
            Wo13GeometryField.MODEL_RR: self.model_rr,
        }
        required = tuple(
            item for item in Wo13GeometryField
            if item is not Wo13GeometryField.CONSTRAINING_OBJECTIVE
        )
        available_required = sum(
            availability.get(item) is not None
            and availability[item].availability is Wo13FieldAvailability.AVAILABLE
            for item in required
        )
        expected_geometry = (
            Wo13GeometryAvailability.GEOMETRY_COMPLETE
            if available_required == len(required)
            else Wo13GeometryAvailability.GEOMETRY_UNAVAILABLE
            if available_required == 0
            else Wo13GeometryAvailability.GEOMETRY_PARTIAL
        )
        if (
            not _texts((self.request_identity, self.request_integrity,
                        self.source_handoff_identity, self.source_handoff_integrity,
                        self.source_wo12_result_identity,
                        self.source_wo12_result_integrity,
                        self.canonical_subject_identity, self.instrument_identity,
                        *self.provenance))
            or type(self.market_family) is not IntradayMarketFamily
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.setup_family) is not Wo13SetupFamily
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or (self.market_family is IntradayMarketFamily.MCX)
            != (self.actual_contract_identity is not None)
            or tuple(item.field for item in self.field_availability)
            != tuple(Wo13GeometryField)
            or any(type(item) is not Wo13FieldAvailabilityRecord for item in self.field_availability)
            or any(
                (availability[field].availability is Wo13FieldAvailability.AVAILABLE)
                != (value is not None)
                for field, value in field_values.items()
            )
            or self.geometry_availability is not expected_geometry
            or tuple(sorted(set(self.warnings), key=lambda item: tuple(Wo13WarningCode).index(item)))
            != self.warnings
            or any(type(item) is not Wo13WarningCode for item in self.warnings)
            or type(self.policy) is not Wo13PolicyBinding
            or len(self.source_evidence_identities) != len(self.source_evidence_integrities)
            or not _texts(self.source_evidence_identities)
            or not _texts(self.source_evidence_integrities)
            or self.supersession is not None
            and type(self.supersession) is not Wo13SupersessionReference
            or self.schema_identity != WO13_TRADE_PLAN_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.authority != WO13_AUTHORITY
            or any((self.analytical_promotion_authority, self.risk_authority,
                    self.position_sizing_authority, self.entry_timing_authority,
                    self.sponsor_decision_authority, self.execution_authority,
                    self.broker_authority))
            or self.trade_plan_identity != _identity("INTRADAY-WO13-TRADE-PLAN-", values)
            or self.trade_plan_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-TRADE-PLAN-", values)
        ):
            raise Wo13ContractError("WO13_TRADE_PLAN_INVALID")


def create_wo13_trade_plan_contract(
    *,
    request: Wo13ConstructionRequest,
    entry_reference: Decimal | None,
    entry_condition: str | None,
    stop: Decimal | None,
    stop_structural_basis: str | None,
    thesis_invalidation_reference: Decimal | None,
    thesis_invalidation_event: str | None,
    setup_native_target: Decimal | None,
    canonical_target: Decimal | None,
    target_structural_basis: str | None,
    constraining_objective: Decimal | None,
    risk_distance: Decimal | None,
    reward_distance: Decimal | None,
    model_rr: Decimal | None,
    geometry_availability: Wo13GeometryAvailability,
    field_availability: tuple[Wo13FieldAvailabilityRecord, ...],
    warnings: tuple[Wo13WarningCode, ...],
    supersession: Wo13SupersessionReference | None,
    provenance: tuple[str, ...],
) -> Wo13TradePlan:
    """Materialize validated contract content; performs no geometry calculation."""

    if type(request) is not Wo13ConstructionRequest:
        raise Wo13ContractError("WO13_TRADE_PLAN_REQUEST_INVALID")
    handoff = request.handoff
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "source_handoff_identity": handoff.handoff_identity,
        "source_handoff_integrity": handoff.handoff_integrity,
        "source_wo12_result_identity": handoff.wo12_result_identity,
        "source_wo12_result_integrity": handoff.wo12_result_integrity,
        "canonical_subject_identity": handoff.canonical_subject_identity,
        "market_family": handoff.market_family,
        "direction": handoff.inherited_direction,
        "setup_family": handoff.setup_family,
        "analysis_boundary": handoff.analysis_boundary,
        "phase": handoff.phase,
        "instrument_identity": handoff.instrument_identity,
        "actual_contract_identity": handoff.actual_contract_identity,
        "entry_reference": entry_reference,
        "entry_condition": entry_condition,
        "stop": stop,
        "stop_structural_basis": stop_structural_basis,
        "thesis_invalidation_reference": thesis_invalidation_reference,
        "thesis_invalidation_event": thesis_invalidation_event,
        "setup_native_target": setup_native_target,
        "canonical_target": canonical_target,
        "target_structural_basis": target_structural_basis,
        "constraining_objective": constraining_objective,
        "risk_distance": risk_distance,
        "reward_distance": reward_distance,
        "model_rr": model_rr,
        "geometry_availability": geometry_availability,
        "field_availability": field_availability,
        "warnings": warnings,
        "policy": request.policy,
        "source_evidence_identities": handoff.source_identities,
        "source_evidence_integrities": handoff.source_integrities,
        "supersession": supersession,
        "provenance": provenance,
        "schema_identity": WO13_TRADE_PLAN_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "authority": WO13_AUTHORITY,
        "analytical_promotion_authority": False,
        "risk_authority": False,
        "position_sizing_authority": False,
        "entry_timing_authority": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    normalized = {key: _decimal(value) if key in {
        "entry_reference", "stop", "thesis_invalidation_reference",
        "setup_native_target", "canonical_target", "constraining_objective",
        "risk_distance", "reward_distance", "model_rr",
    } and value is not None else value for key, value in values.items()}
    return Wo13TradePlan(
        trade_plan_identity=_identity("INTRADAY-WO13-TRADE-PLAN-", normalized),
        trade_plan_integrity=_identity("INTEGRITY-INTRADAY-WO13-TRADE-PLAN-", normalized),
        **normalized,
    )


@dataclass(frozen=True, slots=True)
class Wo13SupersessionLineage:
    lineage_identity: str
    lineage_integrity: str
    predecessor_trade_plan_identity: str
    predecessor_trade_plan_integrity: str
    successor_trade_plan_identity: str
    successor_trade_plan_integrity: str
    source_wo12_request_identity: str
    source_wo12_result_identity: str
    reason: Wo13SupersessionReason
    supersession_boundary: datetime
    schema_identity: str = WO13_SUPERSESSION_LINEAGE_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "lineage_identity", "lineage_integrity")
        if (
            not _texts((self.predecessor_trade_plan_identity,
                        self.predecessor_trade_plan_integrity,
                        self.successor_trade_plan_identity,
                        self.successor_trade_plan_integrity,
                        self.source_wo12_request_identity,
                        self.source_wo12_result_identity))
            or self.predecessor_trade_plan_identity == self.successor_trade_plan_identity
            or type(self.reason) is not Wo13SupersessionReason
            or not _aware(self.supersession_boundary)
            or self.schema_identity != WO13_SUPERSESSION_LINEAGE_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.lineage_identity != _identity("INTRADAY-WO13-SUPERSESSION-", values)
            or self.lineage_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-SUPERSESSION-", values)
        ):
            raise Wo13ContractError("WO13_SUPERSESSION_LINEAGE_INVALID")


def create_wo13_supersession_lineage(
    *,
    predecessor_trade_plan_identity: str,
    predecessor_trade_plan_integrity: str,
    successor_trade_plan_identity: str,
    successor_trade_plan_integrity: str,
    source_wo12_request_identity: str,
    source_wo12_result_identity: str,
    reason: Wo13SupersessionReason,
    supersession_boundary: datetime,
) -> Wo13SupersessionLineage:
    values = {
        "predecessor_trade_plan_identity": predecessor_trade_plan_identity,
        "predecessor_trade_plan_integrity": predecessor_trade_plan_integrity,
        "successor_trade_plan_identity": successor_trade_plan_identity,
        "successor_trade_plan_integrity": successor_trade_plan_integrity,
        "source_wo12_request_identity": source_wo12_request_identity,
        "source_wo12_result_identity": source_wo12_result_identity,
        "reason": reason,
        "supersession_boundary": supersession_boundary,
        "schema_identity": WO13_SUPERSESSION_LINEAGE_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13SupersessionLineage(
        lineage_identity=_identity("INTRADAY-WO13-SUPERSESSION-", values),
        lineage_integrity=_identity("INTEGRITY-INTRADAY-WO13-SUPERSESSION-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13OperationProvenance:
    operation_identity: str
    operation_integrity: str
    request_identity: str
    request_integrity: str
    stage: Wo13OperationStage
    outcome: Wo13OperationOutcome
    started_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    trade_plan_identity: str | None
    failure_reason: str | None
    provenance: tuple[str, ...]
    schema_identity: str = WO13_OPERATION_PROVENANCE_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "operation_identity", "operation_integrity")
        completed = self.outcome is Wo13OperationOutcome.COMPLETED
        failed = self.outcome is Wo13OperationOutcome.FAILED
        if (
            not _texts((self.request_identity, self.request_integrity, *self.provenance))
            or type(self.stage) is not Wo13OperationStage
            or type(self.outcome) is not Wo13OperationOutcome
            or not _aware(self.started_at)
            or completed != (self.completed_at is not None)
            or completed != (self.trade_plan_identity is not None)
            or failed != (self.failed_at is not None)
            or failed != (self.failure_reason is not None)
            or self.completed_at is not None and not _aware(self.completed_at)
            or self.failed_at is not None and not _aware(self.failed_at)
            or self.failure_reason is not None and not _code(self.failure_reason)
            or self.schema_identity != WO13_OPERATION_PROVENANCE_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.operation_identity != _identity("INTRADAY-WO13-OPERATION-", values)
            or self.operation_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-OPERATION-", values)
        ):
            raise Wo13ContractError("WO13_OPERATION_PROVENANCE_INVALID")


def create_wo13_operation_provenance(
    *,
    request: Wo13ConstructionRequest,
    stage: Wo13OperationStage,
    outcome: Wo13OperationOutcome,
    started_at: datetime,
    completed_at: datetime | None = None,
    failed_at: datetime | None = None,
    trade_plan: Wo13TradePlan | None = None,
    failure_reason: str | None = None,
    provenance: tuple[str, ...],
) -> Wo13OperationProvenance:
    if type(request) is not Wo13ConstructionRequest:
        raise Wo13ContractError("WO13_OPERATION_REQUEST_INVALID")
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "stage": stage,
        "outcome": outcome,
        "started_at": started_at,
        "completed_at": completed_at,
        "failed_at": failed_at,
        "trade_plan_identity": (
            None if trade_plan is None else trade_plan.trade_plan_identity
        ),
        "failure_reason": failure_reason,
        "provenance": provenance,
        "schema_identity": WO13_OPERATION_PROVENANCE_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13OperationProvenance(
        operation_identity=_identity("INTRADAY-WO13-OPERATION-", values),
        operation_integrity=_identity("INTEGRITY-INTRADAY-WO13-OPERATION-", values),
        **values,
    )


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    material = json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode()
    return prefix + sha256(material).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise Wo13ContractError("WO13_NUMERIC_VALUE_INVALID")
    try:
        retained = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise Wo13ContractError("WO13_NUMERIC_VALUE_INVALID") from exc
    if not retained.is_finite():
        raise Wo13ContractError("WO13_NUMERIC_VALUE_INVALID")
    return retained


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(item) for item in values)


def _code(value: object) -> bool:
    return _text(value) and all(item.isupper() or item.isdigit() or item == "_" for item in value)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [name for name in globals() if name.startswith("WO13_") or name.startswith("Wo13") or name.startswith("create_wo13")]
