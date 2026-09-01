"""Intraday WO-14 advisory DOMAIN-007 loss-exposure contracts.

The module observes one immutable WO-13 Trade Plan.  It owns no permission,
timing, Sponsor-decision, quantity-selection, or broker consequence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import (
    Wo13GeometryAvailability,
    Wo13TradePlan,
)
from kronos.intraday.wo13_handoff import Wo13SetupFamily


WO14_CONTRACT_IDENTITY = "KRONOS-INTRADAY-DOMAIN-007-RISK-OBSERVATION-V1"
WO14_CONTRACT_VERSION = "1.0.0"
WO14_POLICY_IDENTITY = "KRONOS-INTRADAY-WO14-RISK-OBSERVATION-POLICY-V1"
WO14_POLICY_VERSION = "1.0.0"
WO14_POLICY_CHECKSUM = sha256(
    b"RISK_OBSERVATION_ONLY|NO_THRESHOLDS|NO_VETO|NO_WO15_BLOCK|NO_QUANTITY_SELECTION"
).hexdigest()
WO14_AUTHORITY = "RISK_OBSERVATION_ONLY"
WO14_REQUEST_IDENTITY = "KRONOS-INTRADAY-WO14-RISK-OBSERVATION-REQUEST-V1"
WO14_PLAN_BINDING_IDENTITY = "KRONOS-INTRADAY-WO14-WO13-PLAN-BINDING-V1"
WO14_FIELD_AVAILABILITY_IDENTITY = "KRONOS-INTRADAY-WO14-FIELD-AVAILABILITY-V1"
WO14_CALCULATION_PROVENANCE_IDENTITY = "KRONOS-INTRADAY-WO14-CALCULATION-PROVENANCE-V1"
WO14_OPERATION_PROVENANCE_IDENTITY = "KRONOS-INTRADAY-WO14-OPERATION-PROVENANCE-V1"
WO14_INVALID_PROVENANCE_IDENTITY = "KRONOS-INTRADAY-WO14-INVALID-PROVENANCE-V1"
WO14_SUPERSESSION_IDENTITY = "KRONOS-INTRADAY-WO14-SUPERSESSION-V1"
WO14_CURRENT_POINTER_IDENTITY = "KRONOS-INTRADAY-CURRENT-WO14-POINTER-V1"


class Wo14ContractError(ValueError):
    """Sanitized WO-14 contract or factual-calculation failure."""


class Wo14ObservationState(StrEnum):
    RISK_OBSERVED = "RISK_OBSERVED"
    RISK_ALERT = "RISK_ALERT"
    RISK_UNAVAILABLE = "RISK_UNAVAILABLE"


class Wo14AlertSeverity(StrEnum):
    UNCLASSIFIED = "UNCLASSIFIED"


class Wo14FieldAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class Wo14RiskField(StrEnum):
    STRUCTURAL_RISK_PER_PRICE_UNIT = "STRUCTURAL_RISK_PER_PRICE_UNIT"
    RISK_PER_SHARE = "RISK_PER_SHARE"
    UNDERLYING_POINT_RISK = "UNDERLYING_POINT_RISK"
    MONETARY_RISK_PER_TRADABLE_UNIT = "MONETARY_RISK_PER_TRADABLE_UNIT"
    REFERENCE_QUANTITY = "REFERENCE_QUANTITY"
    LOSS_AT_STOP = "LOSS_AT_STOP"
    REFERENCE_NOTIONAL = "REFERENCE_NOTIONAL"
    CAPITAL_REFERENCE = "CAPITAL_REFERENCE"
    CAPITAL_AT_RISK_FRACTION = "CAPITAL_AT_RISK_FRACTION"
    EXISTING_OPEN_RISK = "EXISTING_OPEN_RISK"
    AGGREGATE_OPEN_RISK_AFTER_REFERENCE = "AGGREGATE_OPEN_RISK_AFTER_REFERENCE"
    MARGIN_CONTEXT = "MARGIN_CONTEXT"


class Wo14QuantitySemantics(StrEnum):
    SPONSOR_REFERENCE_QUANTITY = "SPONSOR_REFERENCE_QUANTITY"
    AUTHORITATIVE_EXISTING_POSITION_QUANTITY = (
        "AUTHORITATIVE_EXISTING_POSITION_QUANTITY"
    )


class Wo14UnitSemantics(StrEnum):
    SHARES = "SHARES"
    LOTS = "LOTS"
    UNITS = "UNITS"


class Wo14OperationStage(StrEnum):
    REQUEST_VALIDATION = "REQUEST_VALIDATION"
    WO13_PLAN_RELOAD = "WO13_PLAN_RELOAD"
    INPUT_VALIDATION = "INPUT_VALIDATION"
    INSTRUMENT_ECONOMICS = "INSTRUMENT_ECONOMICS"
    CALCULATION = "CALCULATION"
    PERSISTENCE = "PERSISTENCE"
    POINTER_PUBLICATION = "POINTER_PUBLICATION"


class Wo14OperationOutcome(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class Wo14PolicyBinding:
    policy_identity: str = WO14_POLICY_IDENTITY
    policy_version: str = WO14_POLICY_VERSION
    policy_checksum: str = WO14_POLICY_CHECKSUM
    authority: str = WO14_AUTHORITY
    alert_predicate: str = "NONE"
    alert_severity: Wo14AlertSeverity = Wo14AlertSeverity.UNCLASSIFIED
    trade_veto_authority: bool = False
    wo15_blocking_authority: bool = False
    quantity_selection_authority: bool = False
    sponsor_decision_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        if (
            self.policy_identity != WO14_POLICY_IDENTITY
            or self.policy_version != WO14_POLICY_VERSION
            or self.policy_checksum != WO14_POLICY_CHECKSUM
            or self.authority != WO14_AUTHORITY
            or self.alert_predicate != "NONE"
            or self.alert_severity is not Wo14AlertSeverity.UNCLASSIFIED
            or any((
                self.trade_veto_authority,
                self.wo15_blocking_authority,
                self.quantity_selection_authority,
                self.sponsor_decision_authority,
                self.broker_authority,
            ))
        ):
            raise Wo14ContractError("WO14_POLICY_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo14PlanBinding:
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
    instrument_identity: str
    actual_contract_identity: str | None
    entry_reference: Decimal | None
    stop: Decimal | None
    canonical_target: Decimal | None
    risk_distance: Decimal | None
    reward_distance: Decimal | None
    model_rr: Decimal | None
    geometry_availability: Wo13GeometryAvailability
    wo13_policy_identity: str
    wo13_policy_version: str
    wo13_policy_checksum: str
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    binding_identity: str
    binding_integrity: str
    schema_identity: str = WO14_PLAN_BINDING_IDENTITY
    schema_version: str = WO14_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in (
            "entry_reference", "stop", "canonical_target", "risk_distance",
            "reward_distance", "model_rr",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(value))
        values = _without(self, "binding_identity", "binding_integrity")
        if (
            not _texts((
                self.trade_plan_identity, self.trade_plan_integrity,
                self.request_identity, self.request_integrity,
                self.source_handoff_identity, self.source_handoff_integrity,
                self.source_wo12_result_identity, self.source_wo12_result_integrity,
                self.canonical_subject_identity, self.instrument_identity,
                self.wo13_policy_identity, self.wo13_policy_version,
                self.wo13_policy_checksum,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.setup_family) is not Wo13SetupFamily
            or not _aware(self.analysis_boundary)
            or (self.market_family is IntradayMarketFamily.MCX)
            != (self.actual_contract_identity is not None)
            or len(self.source_identities) != len(self.source_integrities)
            or not _texts(self.source_identities)
            or not _texts(self.source_integrities)
            or self.schema_identity != WO14_PLAN_BINDING_IDENTITY
            or self.schema_version != WO14_CONTRACT_VERSION
            or self.binding_identity != _identity("INTRADAY-WO14-PLAN-BINDING-", values)
            or self.binding_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-PLAN-BINDING-", values)
        ):
            raise Wo14ContractError("WO14_PLAN_BINDING_INVALID")


def bind_wo13_trade_plan(plan: Wo13TradePlan) -> Wo14PlanBinding:
    if type(plan) is not Wo13TradePlan:
        raise Wo14ContractError("WO14_WO13_PLAN_INVALID")
    values = {
        "trade_plan_identity": plan.trade_plan_identity,
        "trade_plan_integrity": plan.trade_plan_integrity,
        "request_identity": plan.request_identity,
        "request_integrity": plan.request_integrity,
        "source_handoff_identity": plan.source_handoff_identity,
        "source_handoff_integrity": plan.source_handoff_integrity,
        "source_wo12_result_identity": plan.source_wo12_result_identity,
        "source_wo12_result_integrity": plan.source_wo12_result_integrity,
        "canonical_subject_identity": plan.canonical_subject_identity,
        "market_family": plan.market_family,
        "direction": plan.direction,
        "setup_family": plan.setup_family,
        "analysis_boundary": plan.analysis_boundary,
        "instrument_identity": plan.instrument_identity,
        "actual_contract_identity": plan.actual_contract_identity,
        "entry_reference": plan.entry_reference,
        "stop": plan.stop,
        "canonical_target": plan.canonical_target,
        "risk_distance": plan.risk_distance,
        "reward_distance": plan.reward_distance,
        "model_rr": plan.model_rr,
        "geometry_availability": plan.geometry_availability,
        "wo13_policy_identity": plan.policy.policy_identity,
        "wo13_policy_version": plan.policy.policy_version,
        "wo13_policy_checksum": plan.policy.policy_checksum,
        "source_identities": plan.source_evidence_identities,
        "source_integrities": plan.source_evidence_integrities,
        "schema_identity": WO14_PLAN_BINDING_IDENTITY,
        "schema_version": WO14_CONTRACT_VERSION,
    }
    return Wo14PlanBinding(
        binding_identity=_identity("INTRADAY-WO14-PLAN-BINDING-", values),
        binding_integrity=_identity(
            "INTEGRITY-INTRADAY-WO14-PLAN-BINDING-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo14ReferenceQuantity:
    snapshot_identity: str
    snapshot_integrity: str
    quantity: Decimal
    semantics: Wo14QuantitySemantics
    unit_semantics: Wo14UnitSemantics
    source_identity: str
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", _decimal(self.quantity))
        values = _without(self, "snapshot_identity", "snapshot_integrity")
        if (
            self.quantity <= 0
            or self.quantity != self.quantity.to_integral_value()
            or type(self.semantics) is not Wo14QuantitySemantics
            or type(self.unit_semantics) is not Wo14UnitSemantics
            or not _text(self.source_identity)
            or not _aware(self.observed_at)
            or self.snapshot_identity != _identity("INTRADAY-WO14-QUANTITY-", values)
            or self.snapshot_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-QUANTITY-", values)
        ):
            raise Wo14ContractError("WO14_REFERENCE_QUANTITY_INVALID")


def create_wo14_reference_quantity(
    *, quantity: Decimal, semantics: Wo14QuantitySemantics,
    unit_semantics: Wo14UnitSemantics, source_identity: str,
    observed_at: datetime,
) -> Wo14ReferenceQuantity:
    values = {
        "quantity": _decimal(quantity), "semantics": semantics,
        "unit_semantics": unit_semantics, "source_identity": source_identity,
        "observed_at": observed_at,
    }
    return Wo14ReferenceQuantity(
        snapshot_identity=_identity("INTRADAY-WO14-QUANTITY-", values),
        snapshot_integrity=_identity("INTEGRITY-INTRADAY-WO14-QUANTITY-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo14InstrumentEconomics:
    economics_identity: str
    economics_integrity: str
    economics_version: str
    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str
    roll_lineage_identity: str
    lot_size: int
    contract_multiplier: Decimal
    tick_size: Decimal
    tick_value: Decimal | None
    unit_semantics: Wo14UnitSemantics
    observed_at: datetime
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_multiplier", _decimal(self.contract_multiplier))
        object.__setattr__(self, "tick_size", _decimal(self.tick_size))
        if self.tick_value is not None:
            object.__setattr__(self, "tick_value", _decimal(self.tick_value))
        values = _without(self, "economics_identity", "economics_integrity")
        if (
            not _texts((
                self.economics_version, self.canonical_subject_identity,
                self.instrument_identity, self.actual_contract_identity,
                self.roll_lineage_identity,
            ))
            or type(self.lot_size) is not int or self.lot_size <= 0
            or self.contract_multiplier <= 0 or self.tick_size <= 0
            or self.tick_value is not None and self.tick_value <= 0
            or self.unit_semantics is not Wo14UnitSemantics.LOTS
            or not _aware(self.observed_at)
            or len(self.source_identities) != len(self.source_integrities)
            or not _texts(self.source_identities) or not _texts(self.source_integrities)
            or self.economics_identity != _identity("INTRADAY-WO14-ECONOMICS-", values)
            or self.economics_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-ECONOMICS-", values)
        ):
            raise Wo14ContractError("WO14_INSTRUMENT_ECONOMICS_INVALID")


def create_wo14_instrument_economics(
    *, economics_version: str, canonical_subject_identity: str,
    instrument_identity: str, actual_contract_identity: str,
    roll_lineage_identity: str, lot_size: int,
    contract_multiplier: Decimal, tick_size: Decimal,
    tick_value: Decimal | None, observed_at: datetime,
    source_identities: tuple[str, ...], source_integrities: tuple[str, ...],
) -> Wo14InstrumentEconomics:
    values = {
        "economics_version": economics_version,
        "canonical_subject_identity": canonical_subject_identity,
        "instrument_identity": instrument_identity,
        "actual_contract_identity": actual_contract_identity,
        "roll_lineage_identity": roll_lineage_identity,
        "lot_size": lot_size,
        "contract_multiplier": _decimal(contract_multiplier),
        "tick_size": _decimal(tick_size),
        "tick_value": None if tick_value is None else _decimal(tick_value),
        "unit_semantics": Wo14UnitSemantics.LOTS,
        "observed_at": observed_at,
        "source_identities": source_identities,
        "source_integrities": source_integrities,
    }
    return Wo14InstrumentEconomics(
        economics_identity=_identity("INTRADAY-WO14-ECONOMICS-", values),
        economics_integrity=_identity(
            "INTEGRITY-INTRADAY-WO14-ECONOMICS-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo14CapitalReference:
    snapshot_identity: str
    snapshot_integrity: str
    amount: Decimal
    currency: str
    source_identity: str
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", _decimal(self.amount))
        values = _without(self, "snapshot_identity", "snapshot_integrity")
        if (
            self.amount <= 0 or not _texts((self.currency, self.source_identity))
            or not _aware(self.observed_at)
            or self.snapshot_identity != _identity("INTRADAY-WO14-CAPITAL-", values)
            or self.snapshot_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-CAPITAL-", values)
        ):
            raise Wo14ContractError("WO14_CAPITAL_REFERENCE_INVALID")


def create_wo14_capital_reference(
    *, amount: Decimal, currency: str, source_identity: str,
    observed_at: datetime,
) -> Wo14CapitalReference:
    values = {
        "amount": _decimal(amount), "currency": currency,
        "source_identity": source_identity, "observed_at": observed_at,
    }
    return Wo14CapitalReference(
        snapshot_identity=_identity("INTRADAY-WO14-CAPITAL-", values),
        snapshot_integrity=_identity("INTEGRITY-INTRADAY-WO14-CAPITAL-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo14PortfolioRiskSnapshot:
    snapshot_identity: str
    snapshot_integrity: str
    existing_open_risk: Decimal
    currency: str
    source_identity: str
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "existing_open_risk", _decimal(self.existing_open_risk))
        values = _without(self, "snapshot_identity", "snapshot_integrity")
        if (
            self.existing_open_risk < 0
            or not _texts((self.currency, self.source_identity))
            or not _aware(self.observed_at)
            or self.snapshot_identity != _identity("INTRADAY-WO14-PORTFOLIO-", values)
            or self.snapshot_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-PORTFOLIO-", values)
        ):
            raise Wo14ContractError("WO14_PORTFOLIO_SNAPSHOT_INVALID")


def create_wo14_portfolio_snapshot(
    *, existing_open_risk: Decimal, currency: str, source_identity: str,
    observed_at: datetime,
) -> Wo14PortfolioRiskSnapshot:
    values = {
        "existing_open_risk": _decimal(existing_open_risk),
        "currency": currency, "source_identity": source_identity,
        "observed_at": observed_at,
    }
    return Wo14PortfolioRiskSnapshot(
        snapshot_identity=_identity("INTRADAY-WO14-PORTFOLIO-", values),
        snapshot_integrity=_identity(
            "INTEGRITY-INTRADAY-WO14-PORTFOLIO-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo14MarginContext:
    snapshot_identity: str
    snapshot_integrity: str
    margin_amount: Decimal
    currency: str
    source_identity: str
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "margin_amount", _decimal(self.margin_amount))
        values = _without(self, "snapshot_identity", "snapshot_integrity")
        if (
            self.margin_amount < 0
            or not _texts((self.currency, self.source_identity))
            or not _aware(self.observed_at)
            or self.snapshot_identity != _identity("INTRADAY-WO14-MARGIN-", values)
            or self.snapshot_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-MARGIN-", values)
        ):
            raise Wo14ContractError("WO14_MARGIN_CONTEXT_INVALID")


def create_wo14_margin_context(
    *, margin_amount: Decimal, currency: str, source_identity: str,
    observed_at: datetime,
) -> Wo14MarginContext:
    values = {
        "margin_amount": _decimal(margin_amount), "currency": currency,
        "source_identity": source_identity, "observed_at": observed_at,
    }
    return Wo14MarginContext(
        snapshot_identity=_identity("INTRADAY-WO14-MARGIN-", values),
        snapshot_integrity=_identity("INTEGRITY-INTRADAY-WO14-MARGIN-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo14ObservationRequest:
    request_identity: str
    request_integrity: str
    plan_binding: Wo14PlanBinding
    policy: Wo14PolicyBinding
    reference_quantity: Wo14ReferenceQuantity | None
    instrument_economics: Wo14InstrumentEconomics | None
    capital_reference: Wo14CapitalReference | None
    portfolio_snapshot: Wo14PortfolioRiskSnapshot | None
    margin_context: Wo14MarginContext | None
    sponsor_operation_identity: str
    requested_at: datetime
    evaluation_boundary: datetime
    provenance: tuple[str, ...]
    schema_identity: str = WO14_REQUEST_IDENTITY
    schema_version: str = WO14_CONTRACT_VERSION
    provider_acquisition_authority: bool = False
    geometry_mutation_authority: bool = False
    quantity_selection_authority: bool = False
    latest_resolution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "request_identity", "request_integrity")
        if (
            type(self.plan_binding) is not Wo14PlanBinding
            or type(self.policy) is not Wo14PolicyBinding
            or self.reference_quantity is not None
            and type(self.reference_quantity) is not Wo14ReferenceQuantity
            or self.instrument_economics is not None
            and type(self.instrument_economics) is not Wo14InstrumentEconomics
            or self.capital_reference is not None
            and type(self.capital_reference) is not Wo14CapitalReference
            or self.portfolio_snapshot is not None
            and type(self.portfolio_snapshot) is not Wo14PortfolioRiskSnapshot
            or self.margin_context is not None
            and type(self.margin_context) is not Wo14MarginContext
            or not _texts((self.sponsor_operation_identity, *self.provenance))
            or not _aware(self.requested_at) or not _aware(self.evaluation_boundary)
            or self.schema_identity != WO14_REQUEST_IDENTITY
            or self.schema_version != WO14_CONTRACT_VERSION
            or any((self.provider_acquisition_authority,
                    self.geometry_mutation_authority,
                    self.quantity_selection_authority,
                    self.latest_resolution_authority))
            or self.request_identity != _identity("INTRADAY-WO14-REQUEST-", values)
            or self.request_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-REQUEST-", values)
        ):
            raise Wo14ContractError("WO14_REQUEST_INVALID")


def create_wo14_observation_request(
    *, plan: Wo13TradePlan, sponsor_operation_identity: str,
    requested_at: datetime, evaluation_boundary: datetime,
    provenance: tuple[str, ...],
    reference_quantity: Wo14ReferenceQuantity | None = None,
    instrument_economics: Wo14InstrumentEconomics | None = None,
    capital_reference: Wo14CapitalReference | None = None,
    portfolio_snapshot: Wo14PortfolioRiskSnapshot | None = None,
    margin_context: Wo14MarginContext | None = None,
) -> Wo14ObservationRequest:
    values = {
        "plan_binding": bind_wo13_trade_plan(plan),
        "policy": Wo14PolicyBinding(),
        "reference_quantity": reference_quantity,
        "instrument_economics": instrument_economics,
        "capital_reference": capital_reference,
        "portfolio_snapshot": portfolio_snapshot,
        "margin_context": margin_context,
        "sponsor_operation_identity": sponsor_operation_identity,
        "requested_at": requested_at,
        "evaluation_boundary": evaluation_boundary,
        "provenance": provenance,
        "schema_identity": WO14_REQUEST_IDENTITY,
        "schema_version": WO14_CONTRACT_VERSION,
        "provider_acquisition_authority": False,
        "geometry_mutation_authority": False,
        "quantity_selection_authority": False,
        "latest_resolution_authority": False,
    }
    return Wo14ObservationRequest(
        request_identity=_identity("INTRADAY-WO14-REQUEST-", values),
        request_integrity=_identity("INTEGRITY-INTRADAY-WO14-REQUEST-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo14FieldAvailabilityRecord:
    field: Wo14RiskField
    availability: Wo14FieldAvailability
    reason: str
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    schema_identity: str = WO14_FIELD_AVAILABILITY_IDENTITY
    schema_version: str = WO14_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.field) is not Wo14RiskField
            or type(self.availability) is not Wo14FieldAvailability
            or not _code(self.reason)
            or len(self.source_identities) != len(self.source_integrities)
            or any(not _text(item) for item in (*self.source_identities, *self.source_integrities))
            or self.schema_identity != WO14_FIELD_AVAILABILITY_IDENTITY
            or self.schema_version != WO14_CONTRACT_VERSION
        ):
            raise Wo14ContractError("WO14_FIELD_AVAILABILITY_INVALID")


@dataclass(frozen=True, slots=True)
class Wo14CalculationProvenance:
    field: Wo14RiskField
    formula_identity: str
    source_values: tuple[str, ...]
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    unit_semantics: str
    evaluation_boundary: datetime
    schema_identity: str = WO14_CALCULATION_PROVENANCE_IDENTITY
    schema_version: str = WO14_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.field) is not Wo14RiskField
            or not _texts((self.formula_identity, *self.source_values,
                           *self.source_identities, *self.source_integrities,
                           self.unit_semantics))
            or len(self.source_identities) != len(self.source_integrities)
            or not _aware(self.evaluation_boundary)
            or self.schema_identity != WO14_CALCULATION_PROVENANCE_IDENTITY
            or self.schema_version != WO14_CONTRACT_VERSION
        ):
            raise Wo14ContractError("WO14_CALCULATION_PROVENANCE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo14RiskObservation:
    observation_identity: str
    observation_integrity: str
    request_identity: str
    request_integrity: str
    plan_binding: Wo14PlanBinding
    state: Wo14ObservationState
    alert_severity: Wo14AlertSeverity
    structural_risk_per_price_unit: Decimal | None
    risk_per_share: Decimal | None
    underlying_point_risk: Decimal | None
    monetary_risk_per_tradable_unit: Decimal | None
    reference_quantity: Decimal | None
    reference_quantity_semantics: Wo14QuantitySemantics | None
    loss_at_stop: Decimal | None
    reference_notional: Decimal | None
    capital_reference: Decimal | None
    capital_at_risk_fraction: Decimal | None
    existing_open_risk: Decimal | None
    aggregate_open_risk_after_reference: Decimal | None
    margin_context: Decimal | None
    currency: str | None
    field_availability: tuple[Wo14FieldAvailabilityRecord, ...]
    unavailable_reasons: tuple[str, ...]
    calculation_provenance: tuple[Wo14CalculationProvenance, ...]
    policy: Wo14PolicyBinding
    evaluated_at: datetime
    provenance: tuple[str, ...]
    schema_identity: str = WO14_CONTRACT_IDENTITY
    schema_version: str = WO14_CONTRACT_VERSION
    authority: str = WO14_AUTHORITY
    trade_permission_authority: bool = False
    wo15_blocking_authority: bool = False
    final_quantity_authority: bool = False
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        numeric = (
            "structural_risk_per_price_unit", "risk_per_share",
            "underlying_point_risk", "monetary_risk_per_tradable_unit",
            "reference_quantity", "loss_at_stop", "reference_notional",
            "capital_reference", "capital_at_risk_fraction",
            "existing_open_risk", "aggregate_open_risk_after_reference",
            "margin_context",
        )
        for name in numeric:
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(value))
        values = _without(self, "observation_identity", "observation_integrity")
        if (
            not _texts((self.request_identity, self.request_integrity, *self.provenance))
            or type(self.plan_binding) is not Wo14PlanBinding
            or type(self.state) is not Wo14ObservationState
            or self.alert_severity is not Wo14AlertSeverity.UNCLASSIFIED
            or tuple(item.field for item in self.field_availability) != tuple(Wo14RiskField)
            or any(type(item) is not Wo14FieldAvailabilityRecord for item in self.field_availability)
            or any(not _code(item) for item in self.unavailable_reasons)
            or any(type(item) is not Wo14CalculationProvenance for item in self.calculation_provenance)
            or type(self.policy) is not Wo14PolicyBinding
            or not _aware(self.evaluated_at)
            or self.schema_identity != WO14_CONTRACT_IDENTITY
            or self.schema_version != WO14_CONTRACT_VERSION
            or self.authority != WO14_AUTHORITY
            or any((self.trade_permission_authority, self.wo15_blocking_authority,
                    self.final_quantity_authority, self.sponsor_decision_authority,
                    self.execution_authority, self.broker_authority))
            or self.observation_identity
            != _identity("INTRADAY-WO14-RISK-OBSERVATION-", values)
            or self.observation_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-RISK-OBSERVATION-", values)
        ):
            raise Wo14ContractError("WO14_RISK_OBSERVATION_INVALID")


def calculate_wo14_observation(
    request: Wo14ObservationRequest,
    plan: Wo13TradePlan,
) -> Wo14RiskObservation:
    """Calculate facts only; never alter geometry or choose quantity."""

    if type(request) is not Wo14ObservationRequest or type(plan) is not Wo13TradePlan:
        raise Wo14ContractError("WO14_CALCULATION_INPUT_INVALID")
    if request.plan_binding != bind_wo13_trade_plan(plan):
        raise Wo14ContractError("WO14_WO13_PLAN_BINDING_MISMATCH")

    values: dict[Wo14RiskField, Decimal | None] = {field: None for field in Wo14RiskField}
    reasons: dict[Wo14RiskField, str] = {
        field: f"{field.value}_UNAVAILABLE" for field in Wo14RiskField
    }
    provenances: list[Wo14CalculationProvenance] = []
    unavailable: list[str] = []
    plan_sources = (
        (plan.trade_plan_identity, plan.trade_plan_integrity),
        (plan.source_handoff_identity, plan.source_handoff_integrity),
    )

    structural = _structural_risk(plan)
    structural_valid = structural is not None and structural > 0
    mismatch = structural_valid and plan.risk_distance != structural
    complete = plan.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE
    if not complete:
        unavailable.append(f"{plan.geometry_availability.value}_FULL_RISK_UNAVAILABLE")
    if structural is None or structural <= 0:
        unavailable.append("INVALID_STRUCTURAL_RISK")
        reasons[Wo14RiskField.STRUCTURAL_RISK_PER_PRICE_UNIT] = "INVALID_STRUCTURAL_RISK"
    elif mismatch:
        unavailable.append("WO13_RISK_DISTANCE_MISMATCH")
        reasons[Wo14RiskField.STRUCTURAL_RISK_PER_PRICE_UNIT] = "WO13_RISK_DISTANCE_MISMATCH"
    else:
        values[Wo14RiskField.STRUCTURAL_RISK_PER_PRICE_UNIT] = structural
        reasons[Wo14RiskField.STRUCTURAL_RISK_PER_PRICE_UNIT] = "STRUCTURAL_RISK_AVAILABLE"
        provenances.append(_calculation(
            Wo14RiskField.STRUCTURAL_RISK_PER_PRICE_UNIT,
            "WO14_LONG_ENTRY_MINUS_STOP_V1" if plan.direction is SemanticDirection.LONG
            else "WO14_SHORT_STOP_MINUS_ENTRY_V1",
            (plan.entry_reference, plan.stop), plan_sources, "PRICE_UNIT",
            request.evaluation_boundary,
        ))

    monetary_unit: Decimal | None = None
    currency: str | None = None
    if structural_valid and not mismatch:
        if plan.market_family is IntradayMarketFamily.NSE_EQUITY:
            values[Wo14RiskField.RISK_PER_SHARE] = structural
            values[Wo14RiskField.MONETARY_RISK_PER_TRADABLE_UNIT] = structural
            reasons[Wo14RiskField.RISK_PER_SHARE] = "RISK_PER_SHARE_AVAILABLE"
            reasons[Wo14RiskField.MONETARY_RISK_PER_TRADABLE_UNIT] = "RISK_PER_SHARE_AVAILABLE"
            monetary_unit = structural
            currency = "INR"
            provenances.append(_calculation(
                Wo14RiskField.RISK_PER_SHARE, "WO14_EQUITY_ABS_ENTRY_STOP_V1",
                (plan.entry_reference, plan.stop), plan_sources, "INR_PER_SHARE",
                request.evaluation_boundary,
            ))
        elif plan.market_family is IntradayMarketFamily.NSE_INDEX:
            values[Wo14RiskField.UNDERLYING_POINT_RISK] = structural
            reasons[Wo14RiskField.UNDERLYING_POINT_RISK] = "UNDERLYING_POINT_RISK_AVAILABLE"
            reasons[Wo14RiskField.MONETARY_RISK_PER_TRADABLE_UNIT] = (
                "INDEX_EXECUTION_VEHICLE_UNAVAILABLE"
            )
            unavailable.append("INDEX_EXECUTION_VEHICLE_UNAVAILABLE")
            provenances.append(_calculation(
                Wo14RiskField.UNDERLYING_POINT_RISK,
                "WO14_INDEX_UNDERLYING_ABS_ENTRY_STOP_V1",
                (plan.entry_reference, plan.stop), plan_sources, "INDEX_POINTS",
                request.evaluation_boundary,
            ))
        elif plan.market_family is IntradayMarketFamily.MCX:
            economics = request.instrument_economics
            if economics is None:
                unavailable.append("MCX_INSTRUMENT_ECONOMICS_UNAVAILABLE")
                reasons[Wo14RiskField.MONETARY_RISK_PER_TRADABLE_UNIT] = (
                    "MCX_INSTRUMENT_ECONOMICS_UNAVAILABLE"
                )
            elif (
                economics.canonical_subject_identity != plan.canonical_subject_identity
                or economics.instrument_identity != plan.instrument_identity
                or economics.actual_contract_identity != plan.actual_contract_identity
            ):
                unavailable.append("MCX_INSTRUMENT_ECONOMICS_MISMATCH")
                reasons[Wo14RiskField.MONETARY_RISK_PER_TRADABLE_UNIT] = (
                    "MCX_INSTRUMENT_ECONOMICS_MISMATCH"
                )
            else:
                monetary_unit = structural * economics.contract_multiplier * economics.lot_size
                values[Wo14RiskField.MONETARY_RISK_PER_TRADABLE_UNIT] = monetary_unit
                reasons[Wo14RiskField.MONETARY_RISK_PER_TRADABLE_UNIT] = (
                    "MCX_MONETARY_RISK_PER_LOT_AVAILABLE"
                )
                currency = "INR"
                sources = (*plan_sources, (economics.economics_identity,
                                            economics.economics_integrity))
                provenances.append(_calculation(
                    Wo14RiskField.MONETARY_RISK_PER_TRADABLE_UNIT,
                    "WO14_MCX_PRICE_RISK_X_MULTIPLIER_X_LOT_SIZE_V1",
                    (structural, economics.contract_multiplier, economics.lot_size),
                    sources, "INR_PER_LOT", request.evaluation_boundary,
                ))

    quantity = request.reference_quantity
    expected_unit = (
        Wo14UnitSemantics.SHARES
        if plan.market_family is IntradayMarketFamily.NSE_EQUITY
        else Wo14UnitSemantics.LOTS
        if plan.market_family is IntradayMarketFamily.MCX
        else None
    )
    quantity_valid = quantity is not None and quantity.unit_semantics is expected_unit
    if quantity is None:
        reasons[Wo14RiskField.REFERENCE_QUANTITY] = "REFERENCE_QUANTITY_NOT_SUPPLIED"
    elif not quantity_valid:
        reasons[Wo14RiskField.REFERENCE_QUANTITY] = "REFERENCE_QUANTITY_UNIT_MISMATCH"
        unavailable.append("REFERENCE_QUANTITY_UNIT_MISMATCH")
    else:
        values[Wo14RiskField.REFERENCE_QUANTITY] = quantity.quantity
        reasons[Wo14RiskField.REFERENCE_QUANTITY] = "REFERENCE_QUANTITY_AVAILABLE"

    loss: Decimal | None = None
    if quantity_valid and monetary_unit is not None:
        loss = monetary_unit * quantity.quantity
        values[Wo14RiskField.LOSS_AT_STOP] = loss
        reasons[Wo14RiskField.LOSS_AT_STOP] = "LOSS_AT_STOP_AVAILABLE"
        sources = (*plan_sources, (quantity.snapshot_identity, quantity.snapshot_integrity))
        provenances.append(_calculation(
            Wo14RiskField.LOSS_AT_STOP, "WO14_RISK_PER_UNIT_X_REFERENCE_QUANTITY_V1",
            (monetary_unit, quantity.quantity), sources, currency or "MONETARY",
            request.evaluation_boundary,
        ))
        if plan.entry_reference is not None:
            multiplier = Decimal(1)
            lot_size = Decimal(1)
            if plan.market_family is IntradayMarketFamily.MCX and request.instrument_economics:
                multiplier = request.instrument_economics.contract_multiplier
                lot_size = Decimal(request.instrument_economics.lot_size)
            notional = plan.entry_reference * quantity.quantity * multiplier * lot_size
            values[Wo14RiskField.REFERENCE_NOTIONAL] = notional
            reasons[Wo14RiskField.REFERENCE_NOTIONAL] = "REFERENCE_NOTIONAL_AVAILABLE"
            provenances.append(_calculation(
                Wo14RiskField.REFERENCE_NOTIONAL, "WO14_ENTRY_X_REFERENCE_UNITS_V1",
                (plan.entry_reference, quantity.quantity, multiplier, lot_size),
                sources, currency or "MONETARY", request.evaluation_boundary,
            ))

    capital = request.capital_reference
    if capital is not None:
        values[Wo14RiskField.CAPITAL_REFERENCE] = capital.amount
        reasons[Wo14RiskField.CAPITAL_REFERENCE] = "SPONSOR_CAPITAL_REFERENCE_AVAILABLE"
        if loss is not None and capital.currency == currency:
            fraction = loss / capital.amount
            values[Wo14RiskField.CAPITAL_AT_RISK_FRACTION] = fraction
            reasons[Wo14RiskField.CAPITAL_AT_RISK_FRACTION] = "CAPITAL_AT_RISK_FRACTION_AVAILABLE"
            provenances.append(_calculation(
                Wo14RiskField.CAPITAL_AT_RISK_FRACTION,
                "WO14_LOSS_AT_STOP_DIV_SPONSOR_CAPITAL_REFERENCE_V1",
                (loss, capital.amount),
                (*plan_sources, (capital.snapshot_identity, capital.snapshot_integrity)),
                "FRACTION", request.evaluation_boundary,
            ))
        elif loss is not None:
            reasons[Wo14RiskField.CAPITAL_AT_RISK_FRACTION] = (
                "CAPITAL_CURRENCY_MISMATCH"
            )
            unavailable.append("CAPITAL_CURRENCY_MISMATCH")
    else:
        reasons[Wo14RiskField.CAPITAL_REFERENCE] = "SPONSOR_CAPITAL_REFERENCE_NOT_SUPPLIED"
        reasons[Wo14RiskField.CAPITAL_AT_RISK_FRACTION] = "CAPITAL_REFERENCE_UNAVAILABLE"

    portfolio = request.portfolio_snapshot
    if portfolio is not None:
        values[Wo14RiskField.EXISTING_OPEN_RISK] = portfolio.existing_open_risk
        reasons[Wo14RiskField.EXISTING_OPEN_RISK] = "EXISTING_OPEN_RISK_AVAILABLE"
        if loss is not None and portfolio.currency == currency:
            aggregate = portfolio.existing_open_risk + loss
            values[Wo14RiskField.AGGREGATE_OPEN_RISK_AFTER_REFERENCE] = aggregate
            reasons[Wo14RiskField.AGGREGATE_OPEN_RISK_AFTER_REFERENCE] = (
                "AGGREGATE_OPEN_RISK_AVAILABLE"
            )
            provenances.append(_calculation(
                Wo14RiskField.AGGREGATE_OPEN_RISK_AFTER_REFERENCE,
                "WO14_EXISTING_OPEN_RISK_PLUS_REFERENCE_LOSS_V1",
                (portfolio.existing_open_risk, loss),
                (*plan_sources, (portfolio.snapshot_identity,
                                 portfolio.snapshot_integrity)),
                portfolio.currency, request.evaluation_boundary,
            ))
        elif loss is not None:
            reasons[Wo14RiskField.AGGREGATE_OPEN_RISK_AFTER_REFERENCE] = (
                "PORTFOLIO_CURRENCY_MISMATCH"
            )
            unavailable.append("PORTFOLIO_CURRENCY_MISMATCH")
    else:
        reasons[Wo14RiskField.EXISTING_OPEN_RISK] = "PORTFOLIO_FACTS_NOT_SUPPLIED"
        reasons[Wo14RiskField.AGGREGATE_OPEN_RISK_AFTER_REFERENCE] = (
            "PORTFOLIO_FACTS_NOT_SUPPLIED"
        )

    margin = request.margin_context
    if margin is not None:
        values[Wo14RiskField.MARGIN_CONTEXT] = margin.margin_amount
        reasons[Wo14RiskField.MARGIN_CONTEXT] = "MARGIN_CONTEXT_AVAILABLE"
    else:
        reasons[Wo14RiskField.MARGIN_CONTEXT] = "MARGIN_CONTEXT_NOT_SUPPLIED"

    core_observed = complete and structural_valid and not mismatch
    if plan.market_family is IntradayMarketFamily.NSE_INDEX:
        core_observed = False
    if plan.market_family is IntradayMarketFamily.MCX and monetary_unit is None:
        core_observed = False
    state = (
        Wo14ObservationState.RISK_OBSERVED
        if core_observed else Wo14ObservationState.RISK_UNAVAILABLE
    )
    field_records = tuple(_availability(
        field, values[field], reasons[field], plan_sources,
        invalid=reasons[field].endswith("MISMATCH")
        or reasons[field].startswith("INVALID_"),
    ) for field in Wo14RiskField)
    observation_values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "plan_binding": request.plan_binding,
        "state": state,
        "alert_severity": Wo14AlertSeverity.UNCLASSIFIED,
        "structural_risk_per_price_unit": values[Wo14RiskField.STRUCTURAL_RISK_PER_PRICE_UNIT],
        "risk_per_share": values[Wo14RiskField.RISK_PER_SHARE],
        "underlying_point_risk": values[Wo14RiskField.UNDERLYING_POINT_RISK],
        "monetary_risk_per_tradable_unit": values[Wo14RiskField.MONETARY_RISK_PER_TRADABLE_UNIT],
        "reference_quantity": values[Wo14RiskField.REFERENCE_QUANTITY],
        "reference_quantity_semantics": None if not quantity_valid else quantity.semantics,
        "loss_at_stop": values[Wo14RiskField.LOSS_AT_STOP],
        "reference_notional": values[Wo14RiskField.REFERENCE_NOTIONAL],
        "capital_reference": values[Wo14RiskField.CAPITAL_REFERENCE],
        "capital_at_risk_fraction": values[Wo14RiskField.CAPITAL_AT_RISK_FRACTION],
        "existing_open_risk": values[Wo14RiskField.EXISTING_OPEN_RISK],
        "aggregate_open_risk_after_reference": values[Wo14RiskField.AGGREGATE_OPEN_RISK_AFTER_REFERENCE],
        "margin_context": values[Wo14RiskField.MARGIN_CONTEXT],
        "currency": currency,
        "field_availability": field_records,
        "unavailable_reasons": tuple(sorted(set(unavailable))),
        "calculation_provenance": tuple(provenances),
        "policy": request.policy,
        "evaluated_at": request.evaluation_boundary,
        "provenance": (*request.provenance, "ADR-0023", "WO14_FACTUAL_OBSERVATION_V1"),
        "schema_identity": WO14_CONTRACT_IDENTITY,
        "schema_version": WO14_CONTRACT_VERSION,
        "authority": WO14_AUTHORITY,
        "trade_permission_authority": False,
        "wo15_blocking_authority": False,
        "final_quantity_authority": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo14RiskObservation(
        observation_identity=_identity(
            "INTRADAY-WO14-RISK-OBSERVATION-", observation_values
        ),
        observation_integrity=_identity(
            "INTEGRITY-INTRADAY-WO14-RISK-OBSERVATION-", observation_values
        ),
        **observation_values,
    )


@dataclass(frozen=True, slots=True)
class Wo14OperationProvenance:
    operation_identity: str
    operation_integrity: str
    request_identity: str
    request_integrity: str
    stage: Wo14OperationStage
    outcome: Wo14OperationOutcome
    started_at: datetime
    completed_at: datetime | None
    failed_at: datetime | None
    observation_identity: str | None
    failure_reason: str | None
    provenance: tuple[str, ...]
    schema_identity: str = WO14_OPERATION_PROVENANCE_IDENTITY
    schema_version: str = WO14_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "operation_identity", "operation_integrity")
        completed = self.outcome is Wo14OperationOutcome.COMPLETED
        failed = self.outcome is Wo14OperationOutcome.FAILED
        if (
            not _texts((self.request_identity, self.request_integrity, *self.provenance))
            or type(self.stage) is not Wo14OperationStage
            or type(self.outcome) is not Wo14OperationOutcome
            or not _aware(self.started_at)
            or completed != (self.completed_at is not None)
            or completed != (self.observation_identity is not None)
            or failed != (self.failed_at is not None)
            or failed != (self.failure_reason is not None)
            or self.completed_at is not None and not _aware(self.completed_at)
            or self.failed_at is not None and not _aware(self.failed_at)
            or self.failure_reason is not None and not _code(self.failure_reason)
            or self.schema_identity != WO14_OPERATION_PROVENANCE_IDENTITY
            or self.schema_version != WO14_CONTRACT_VERSION
            or self.operation_identity != _identity("INTRADAY-WO14-OPERATION-", values)
            or self.operation_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-OPERATION-", values)
        ):
            raise Wo14ContractError("WO14_OPERATION_PROVENANCE_INVALID")


def create_wo14_operation_provenance(
    *, request: Wo14ObservationRequest, stage: Wo14OperationStage,
    outcome: Wo14OperationOutcome, started_at: datetime,
    completed_at: datetime | None = None, failed_at: datetime | None = None,
    observation: Wo14RiskObservation | None = None,
    failure_reason: str | None = None, provenance: tuple[str, ...],
) -> Wo14OperationProvenance:
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "stage": stage, "outcome": outcome, "started_at": started_at,
        "completed_at": completed_at, "failed_at": failed_at,
        "observation_identity": None if observation is None else observation.observation_identity,
        "failure_reason": failure_reason, "provenance": provenance,
        "schema_identity": WO14_OPERATION_PROVENANCE_IDENTITY,
        "schema_version": WO14_CONTRACT_VERSION,
    }
    return Wo14OperationProvenance(
        operation_identity=_identity("INTRADAY-WO14-OPERATION-", values),
        operation_integrity=_identity("INTEGRITY-INTRADAY-WO14-OPERATION-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo14InvalidObservationProvenance:
    invalid_identity: str
    invalid_integrity: str
    request_identity: str
    request_integrity: str
    stage: Wo14OperationStage
    reason: str
    source_identities: tuple[str, ...]
    failed_at: datetime
    schema_identity: str = WO14_INVALID_PROVENANCE_IDENTITY
    schema_version: str = WO14_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "invalid_identity", "invalid_integrity")
        if (
            not _texts((self.request_identity, self.request_integrity,
                        *self.source_identities))
            or type(self.stage) is not Wo14OperationStage
            or not _code(self.reason) or not _aware(self.failed_at)
            or self.schema_identity != WO14_INVALID_PROVENANCE_IDENTITY
            or self.schema_version != WO14_CONTRACT_VERSION
            or self.invalid_identity != _identity("INTRADAY-WO14-INVALID-", values)
            or self.invalid_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-INVALID-", values)
        ):
            raise Wo14ContractError("WO14_INVALID_PROVENANCE_INVALID")


def create_wo14_invalid_provenance(
    *, request: Wo14ObservationRequest, stage: Wo14OperationStage,
    reason: str, source_identities: tuple[str, ...], failed_at: datetime,
) -> Wo14InvalidObservationProvenance:
    values = {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "stage": stage, "reason": reason,
        "source_identities": source_identities, "failed_at": failed_at,
        "schema_identity": WO14_INVALID_PROVENANCE_IDENTITY,
        "schema_version": WO14_CONTRACT_VERSION,
    }
    return Wo14InvalidObservationProvenance(
        invalid_identity=_identity("INTRADAY-WO14-INVALID-", values),
        invalid_integrity=_identity("INTEGRITY-INTRADAY-WO14-INVALID-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo14SupersessionLineage:
    lineage_identity: str
    lineage_integrity: str
    predecessor_observation_identity: str
    predecessor_observation_integrity: str
    successor_observation_identity: str
    successor_observation_integrity: str
    predecessor_trade_plan_identity: str
    successor_trade_plan_identity: str
    superseded_at: datetime
    schema_identity: str = WO14_SUPERSESSION_IDENTITY
    schema_version: str = WO14_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "lineage_identity", "lineage_integrity")
        if (
            not _texts((self.predecessor_observation_identity,
                        self.predecessor_observation_integrity,
                        self.successor_observation_identity,
                        self.successor_observation_integrity,
                        self.predecessor_trade_plan_identity,
                        self.successor_trade_plan_identity))
            or self.predecessor_observation_identity == self.successor_observation_identity
            or not _aware(self.superseded_at)
            or self.schema_identity != WO14_SUPERSESSION_IDENTITY
            or self.schema_version != WO14_CONTRACT_VERSION
            or self.lineage_identity != _identity("INTRADAY-WO14-SUPERSESSION-", values)
            or self.lineage_integrity
            != _identity("INTEGRITY-INTRADAY-WO14-SUPERSESSION-", values)
        ):
            raise Wo14ContractError("WO14_SUPERSESSION_INVALID")


def create_wo14_supersession(
    *, predecessor: Wo14RiskObservation, successor: Wo14RiskObservation,
    superseded_at: datetime,
) -> Wo14SupersessionLineage:
    values = {
        "predecessor_observation_identity": predecessor.observation_identity,
        "predecessor_observation_integrity": predecessor.observation_integrity,
        "successor_observation_identity": successor.observation_identity,
        "successor_observation_integrity": successor.observation_integrity,
        "predecessor_trade_plan_identity": (
            predecessor.plan_binding.trade_plan_identity
        ),
        "successor_trade_plan_identity": successor.plan_binding.trade_plan_identity,
        "superseded_at": superseded_at,
        "schema_identity": WO14_SUPERSESSION_IDENTITY,
        "schema_version": WO14_CONTRACT_VERSION,
    }
    return Wo14SupersessionLineage(
        lineage_identity=_identity("INTRADAY-WO14-SUPERSESSION-", values),
        lineage_integrity=_identity(
            "INTEGRITY-INTRADAY-WO14-SUPERSESSION-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class CurrentWo14Pointer:
    pointer_identity: str
    pointer_integrity: str
    observation_identity: str
    observation_integrity: str
    request_identity: str
    request_integrity: str
    operation_identity: str
    operation_integrity: str
    trade_plan_identity: str
    trade_plan_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    state: Wo14ObservationState
    policy: Wo14PolicyBinding
    published_at: datetime
    supersession_lineage_identity: str | None
    schema_identity: str = WO14_CURRENT_POINTER_IDENTITY
    schema_version: str = WO14_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "pointer_identity", "pointer_integrity")
        if (
            not _texts((self.observation_identity, self.observation_integrity,
                        self.request_identity, self.request_integrity,
                        self.operation_identity, self.operation_integrity,
                        self.trade_plan_identity, self.trade_plan_integrity,
                        self.canonical_subject_identity))
            or type(self.market_family) is not IntradayMarketFamily
            or type(self.state) is not Wo14ObservationState
            or type(self.policy) is not Wo14PolicyBinding
            or not _aware(self.published_at)
            or self.supersession_lineage_identity is not None
            and not _text(self.supersession_lineage_identity)
            or self.schema_identity != WO14_CURRENT_POINTER_IDENTITY
            or self.schema_version != WO14_CONTRACT_VERSION
            or self.pointer_identity != _identity("CURRENT-INTRADAY-WO14-V1-", values)
            or self.pointer_integrity
            != _identity("INTEGRITY-CURRENT-INTRADAY-WO14-V1-", values)
        ):
            raise Wo14ContractError("WO14_CURRENT_POINTER_INVALID")


def create_current_wo14_pointer(
    *, request: Wo14ObservationRequest, observation: Wo14RiskObservation,
    operation: Wo14OperationProvenance, published_at: datetime,
    supersession: Wo14SupersessionLineage | None = None,
) -> CurrentWo14Pointer:
    if (
        observation.request_identity != request.request_identity
        or operation.outcome is not Wo14OperationOutcome.COMPLETED
        or operation.observation_identity != observation.observation_identity
    ):
        raise Wo14ContractError("WO14_CURRENT_POINTER_INPUT_INVALID")
    binding = observation.plan_binding
    values = {
        "observation_identity": observation.observation_identity,
        "observation_integrity": observation.observation_integrity,
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "operation_identity": operation.operation_identity,
        "operation_integrity": operation.operation_integrity,
        "trade_plan_identity": binding.trade_plan_identity,
        "trade_plan_integrity": binding.trade_plan_integrity,
        "canonical_subject_identity": binding.canonical_subject_identity,
        "market_family": binding.market_family,
        "state": observation.state,
        "policy": request.policy,
        "published_at": published_at,
        "supersession_lineage_identity": None if supersession is None else supersession.lineage_identity,
        "schema_identity": WO14_CURRENT_POINTER_IDENTITY,
        "schema_version": WO14_CONTRACT_VERSION,
    }
    return CurrentWo14Pointer(
        pointer_identity=_identity("CURRENT-INTRADAY-WO14-V1-", values),
        pointer_integrity=_identity("INTEGRITY-CURRENT-INTRADAY-WO14-V1-", values),
        **values,
    )


def _structural_risk(plan: Wo13TradePlan) -> Decimal | None:
    if plan.entry_reference is None or plan.stop is None:
        return None
    return (
        plan.entry_reference - plan.stop
        if plan.direction is SemanticDirection.LONG
        else plan.stop - plan.entry_reference
    )


def _availability(
    field: Wo14RiskField, value: Decimal | None, reason: str,
    sources: tuple[tuple[str, str], ...], *, invalid: bool,
) -> Wo14FieldAvailabilityRecord:
    return Wo14FieldAvailabilityRecord(
        field=field,
        availability=(
            Wo14FieldAvailability.AVAILABLE if value is not None
            else Wo14FieldAvailability.INVALID if invalid
            else Wo14FieldAvailability.UNAVAILABLE
        ),
        reason=reason,
        source_identities=tuple(item[0] for item in sources),
        source_integrities=tuple(item[1] for item in sources),
    )


def _calculation(
    field: Wo14RiskField, formula: str, values: tuple[object, ...],
    sources: tuple[tuple[str, str], ...], units: str, boundary: datetime,
) -> Wo14CalculationProvenance:
    return Wo14CalculationProvenance(
        field=field, formula_identity=formula,
        source_values=tuple(format(item, "f") if isinstance(item, Decimal) else str(item) for item in values),
        source_identities=tuple(item[0] for item in sources),
        source_integrities=tuple(item[1] for item in sources),
        unit_semantics=units, evaluation_boundary=boundary,
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
        raise Wo14ContractError("WO14_NUMERIC_VALUE_INVALID")
    try:
        retained = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise Wo14ContractError("WO14_NUMERIC_VALUE_INVALID") from error
    if not retained.is_finite():
        raise Wo14ContractError("WO14_NUMERIC_VALUE_INVALID")
    return retained


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(item) for item in values)


def _code(value: object) -> bool:
    return _text(value) and all(
        item.isupper() or item.isdigit() or item == "_" for item in value
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    name for name in globals()
    if name.startswith("WO14_") or name.startswith("Wo14")
    or name.startswith("bind_wo13") or name.startswith("calculate_wo14")
    or name.startswith("create_wo14") or name.startswith("create_current_wo14")
]
