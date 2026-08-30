"""Bounded Intraday evidence adapters for WO-12 criteria K1 through K5."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.probables_v2 import SemanticQualificationFactV2
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo12 import (
    WO12_MATERIAL_EXTENSION_THRESHOLD,
    Wo12ContractError,
    Wo12CriterionIdentity,
    Wo12CriterionResult,
    Wo12Handoff,
)
from kronos.validation.kr370 import Kr370CriterionState


WO12_FACT_VERSION = "1.0.0"
WO12_PATH_FACT_IDENTITY = "KRONOS-INTRADAY-WO12-15M-PATH-FACT-V1"
WO12_CPR_ACCEPTANCE_FACT_IDENTITY = "KRONOS-INTRADAY-WO12-15M-CPR-ACCEPTANCE-FACT-V1"
WO12_SETUP_QUALITY_FACT_IDENTITY = "KRONOS-INTRADAY-WO12-15M-SETUP-QUALITY-FACT-V1"
WO12_EXTENSION_MEASUREMENT_IDENTITY = "KRONOS-INTRADAY-WO12-15M-EXTENSION-MEASUREMENT-V1"
WO12_EXTENSION_CALCULATION_IDENTITY = "KRONOS-INTRADAY-15M-ATR-NORMALIZED-EXTENSION-V1"


class Wo12PathState(StrEnum):
    CLEAR = "CLEAR"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"


class Wo12SetupQualityState(StrEnum):
    ACCEPTABLE = "ACCEPTABLE"
    ADVERSE = "ADVERSE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class Wo12CprAcceptanceFact:
    fact_identity: str
    fact_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    analysis_boundary: datetime
    completed_close: Decimal | None
    cpr_lower: Decimal | None
    cpr_upper: Decimal | None
    completed_candle_identity: str | None
    cpr_evidence_identity: str | None
    source_evidence_integrities: tuple[str, ...]
    schema_identity: str = WO12_CPR_ACCEPTANCE_FACT_IDENTITY
    schema_version: str = WO12_FACT_VERSION

    def __post_init__(self) -> None:
        close = None if self.completed_close is None else _decimal(self.completed_close)
        lower = None if self.cpr_lower is None else _decimal(self.cpr_lower)
        upper = None if self.cpr_upper is None else _decimal(self.cpr_upper)
        available = all(item is not None for item in (
            close,
            lower,
            upper,
            self.completed_candle_identity,
            self.cpr_evidence_identity,
        ))
        values = _without(self, "fact_identity", "fact_integrity")
        if (
            not _text(self.canonical_subject_identity)
            or type(self.market_family) is not IntradayMarketFamily
            or not _aware(self.analysis_boundary)
            or (available and lower > upper)
            or (self.completed_candle_identity is not None and not _text(self.completed_candle_identity))
            or (self.cpr_evidence_identity is not None and not _text(self.cpr_evidence_identity))
            or not _texts(self.source_evidence_integrities)
            or self.schema_identity != WO12_CPR_ACCEPTANCE_FACT_IDENTITY
            or self.schema_version != WO12_FACT_VERSION
            or self.fact_identity != _identity("INTRADAY-WO12-CPR-FACT-", values)
            or self.fact_integrity != _identity("INTEGRITY-INTRADAY-WO12-CPR-FACT-", values)
        ):
            raise Wo12ContractError("WO12_CPR_ACCEPTANCE_FACT_INVALID")
        object.__setattr__(self, "completed_close", close)
        object.__setattr__(self, "cpr_lower", lower)
        object.__setattr__(self, "cpr_upper", upper)


def create_wo12_cpr_acceptance_fact(
    *,
    handoff: Wo12Handoff,
    completed_close: Decimal | None,
    cpr_lower: Decimal | None,
    cpr_upper: Decimal | None,
    completed_candle_identity: str | None,
    cpr_evidence_identity: str | None,
    source_evidence_integrities: tuple[str, ...],
) -> Wo12CprAcceptanceFact:
    if type(handoff) is not Wo12Handoff:
        raise Wo12ContractError("WO12_CPR_ACCEPTANCE_FACT_INPUT_INVALID")
    values = {
        "canonical_subject_identity": handoff.canonical_subject_identity,
        "market_family": handoff.market_family,
        "analysis_boundary": handoff.analysis_boundary,
        "completed_close": None if completed_close is None else _decimal(completed_close),
        "cpr_lower": None if cpr_lower is None else _decimal(cpr_lower),
        "cpr_upper": None if cpr_upper is None else _decimal(cpr_upper),
        "completed_candle_identity": completed_candle_identity,
        "cpr_evidence_identity": cpr_evidence_identity,
        "source_evidence_integrities": source_evidence_integrities,
        "schema_identity": WO12_CPR_ACCEPTANCE_FACT_IDENTITY,
        "schema_version": WO12_FACT_VERSION,
    }
    return Wo12CprAcceptanceFact(
        fact_identity=_identity("INTRADAY-WO12-CPR-FACT-", values),
        fact_integrity=_identity("INTEGRITY-INTRADAY-WO12-CPR-FACT-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo12PathClearanceFact:
    fact_identity: str
    fact_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    analysis_boundary: datetime
    state: Wo12PathState
    source_evidence_identities: tuple[str, ...]
    source_evidence_integrities: tuple[str, ...]
    predicate_identity: str
    schema_identity: str = WO12_PATH_FACT_IDENTITY
    schema_version: str = WO12_FACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "fact_identity", "fact_integrity")
        if (
            not _texts((self.canonical_subject_identity, self.predicate_identity))
            or type(self.market_family) is not IntradayMarketFamily
            or not _aware(self.analysis_boundary)
            or type(self.state) is not Wo12PathState
            or not _texts(self.source_evidence_identities)
            or not _texts(self.source_evidence_integrities)
            or len(self.source_evidence_identities) != len(self.source_evidence_integrities)
            or self.schema_identity != WO12_PATH_FACT_IDENTITY
            or self.schema_version != WO12_FACT_VERSION
            or self.fact_identity != _identity("INTRADAY-WO12-PATH-FACT-", values)
            or self.fact_integrity != _identity("INTEGRITY-INTRADAY-WO12-PATH-FACT-", values)
        ):
            raise Wo12ContractError("WO12_PATH_FACT_INVALID")


def create_wo12_path_clearance_fact(
    *,
    canonical_subject_identity: str,
    market_family: IntradayMarketFamily,
    analysis_boundary: datetime,
    state: Wo12PathState,
    source_evidence_identities: tuple[str, ...],
    source_evidence_integrities: tuple[str, ...],
    predicate_identity: str,
) -> Wo12PathClearanceFact:
    values = {
        "canonical_subject_identity": canonical_subject_identity,
        "market_family": market_family,
        "analysis_boundary": analysis_boundary,
        "state": state,
        "source_evidence_identities": source_evidence_identities,
        "source_evidence_integrities": source_evidence_integrities,
        "predicate_identity": predicate_identity,
        "schema_identity": WO12_PATH_FACT_IDENTITY,
        "schema_version": WO12_FACT_VERSION,
    }
    return Wo12PathClearanceFact(
        fact_identity=_identity("INTRADAY-WO12-PATH-FACT-", values),
        fact_integrity=_identity("INTEGRITY-INTRADAY-WO12-PATH-FACT-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo12SetupQualityFact:
    fact_identity: str
    fact_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    analysis_boundary: datetime
    state: Wo12SetupQualityState
    source_evidence_identities: tuple[str, ...]
    source_evidence_integrities: tuple[str, ...]
    adapter_identity: str
    schema_identity: str = WO12_SETUP_QUALITY_FACT_IDENTITY
    schema_version: str = WO12_FACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "fact_identity", "fact_integrity")
        if (
            not _texts((self.canonical_subject_identity, self.adapter_identity))
            or type(self.market_family) is not IntradayMarketFamily
            or not _aware(self.analysis_boundary)
            or type(self.state) is not Wo12SetupQualityState
            or not _texts(self.source_evidence_identities)
            or not _texts(self.source_evidence_integrities)
            or len(self.source_evidence_identities) != len(self.source_evidence_integrities)
            or self.schema_identity != WO12_SETUP_QUALITY_FACT_IDENTITY
            or self.schema_version != WO12_FACT_VERSION
            or self.fact_identity != _identity("INTRADAY-WO12-QUALITY-FACT-", values)
            or self.fact_integrity != _identity("INTEGRITY-INTRADAY-WO12-QUALITY-FACT-", values)
        ):
            raise Wo12ContractError("WO12_SETUP_QUALITY_FACT_INVALID")


def create_wo12_setup_quality_fact(
    *,
    canonical_subject_identity: str,
    market_family: IntradayMarketFamily,
    analysis_boundary: datetime,
    state: Wo12SetupQualityState,
    source_evidence_identities: tuple[str, ...],
    source_evidence_integrities: tuple[str, ...],
    adapter_identity: str,
) -> Wo12SetupQualityFact:
    values = {
        "canonical_subject_identity": canonical_subject_identity,
        "market_family": market_family,
        "analysis_boundary": analysis_boundary,
        "state": state,
        "source_evidence_identities": source_evidence_identities,
        "source_evidence_integrities": source_evidence_integrities,
        "adapter_identity": adapter_identity,
        "schema_identity": WO12_SETUP_QUALITY_FACT_IDENTITY,
        "schema_version": WO12_FACT_VERSION,
    }
    return Wo12SetupQualityFact(
        fact_identity=_identity("INTRADAY-WO12-QUALITY-FACT-", values),
        fact_integrity=_identity("INTEGRITY-INTRADAY-WO12-QUALITY-FACT-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo12ExtensionMeasurement:
    measurement_identity: str
    measurement_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    inherited_direction: SemanticDirection
    analysis_boundary: datetime
    structural_origin_identity: str
    structural_origin_value: Decimal
    completed_close: Decimal
    atr_value: Decimal
    atr_period: int
    atr_calculation_identity: str
    extension_atr_multiple: Decimal
    source_evidence_identities: tuple[str, ...]
    source_evidence_integrities: tuple[str, ...]
    threshold_status: str = WO12_MATERIAL_EXTENSION_THRESHOLD
    schema_identity: str = WO12_EXTENSION_MEASUREMENT_IDENTITY
    schema_version: str = WO12_FACT_VERSION

    def __post_init__(self) -> None:
        origin = _decimal(self.structural_origin_value)
        close = _decimal(self.completed_close)
        atr = _decimal(self.atr_value)
        multiple = _decimal(self.extension_atr_multiple)
        expected = (
            (close - origin) / atr
            if self.inherited_direction is SemanticDirection.LONG
            else (origin - close) / atr
        ) if atr > 0 else None
        values = _without(self, "measurement_identity", "measurement_integrity")
        if (
            not _texts((
                self.canonical_subject_identity,
                self.structural_origin_identity,
                self.atr_calculation_identity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or self.inherited_direction not in {
                SemanticDirection.LONG,
                SemanticDirection.SHORT,
            }
            or not _aware(self.analysis_boundary)
            or atr <= 0
            or type(self.atr_period) is not int
            or self.atr_period < 1
            or multiple != expected
            or not _texts(self.source_evidence_identities)
            or not _texts(self.source_evidence_integrities)
            or len(self.source_evidence_identities) != len(self.source_evidence_integrities)
            or self.threshold_status != WO12_MATERIAL_EXTENSION_THRESHOLD
            or self.schema_identity != WO12_EXTENSION_MEASUREMENT_IDENTITY
            or self.schema_version != WO12_FACT_VERSION
            or self.measurement_identity
            != _identity("INTRADAY-WO12-EXTENSION-MEASUREMENT-", values)
            or self.measurement_integrity
            != _identity("INTEGRITY-INTRADAY-WO12-EXTENSION-MEASUREMENT-", values)
        ):
            raise Wo12ContractError("WO12_EXTENSION_MEASUREMENT_INVALID")
        object.__setattr__(self, "structural_origin_value", origin)
        object.__setattr__(self, "completed_close", close)
        object.__setattr__(self, "atr_value", atr)
        object.__setattr__(self, "extension_atr_multiple", multiple)


def create_wo12_extension_measurement(
    *,
    handoff: Wo12Handoff,
    structural_origin_identity: str,
    structural_origin_value: Decimal,
    completed_close: Decimal,
    atr_value: Decimal,
    atr_period: int,
    atr_calculation_identity: str,
    source_evidence_identities: tuple[str, ...],
    source_evidence_integrities: tuple[str, ...],
) -> Wo12ExtensionMeasurement:
    if type(handoff) is not Wo12Handoff:
        raise Wo12ContractError("WO12_EXTENSION_MEASUREMENT_INPUT_INVALID")
    origin = _decimal(structural_origin_value)
    close = _decimal(completed_close)
    atr = _decimal(atr_value)
    if atr <= 0:
        raise Wo12ContractError("WO12_EXTENSION_MEASUREMENT_INPUT_INVALID")
    multiple = (
        (close - origin) / atr
        if handoff.inherited_direction is SemanticDirection.LONG
        else (origin - close) / atr
    )
    values = {
        "canonical_subject_identity": handoff.canonical_subject_identity,
        "market_family": handoff.market_family,
        "inherited_direction": handoff.inherited_direction,
        "analysis_boundary": handoff.analysis_boundary,
        "structural_origin_identity": structural_origin_identity,
        "structural_origin_value": origin,
        "completed_close": close,
        "atr_value": atr,
        "atr_period": atr_period,
        "atr_calculation_identity": atr_calculation_identity,
        "extension_atr_multiple": multiple,
        "source_evidence_identities": source_evidence_identities,
        "source_evidence_integrities": source_evidence_integrities,
        "threshold_status": WO12_MATERIAL_EXTENSION_THRESHOLD,
        "schema_identity": WO12_EXTENSION_MEASUREMENT_IDENTITY,
        "schema_version": WO12_FACT_VERSION,
    }
    return Wo12ExtensionMeasurement(
        measurement_identity=_identity("INTRADAY-WO12-EXTENSION-MEASUREMENT-", values),
        measurement_integrity=_identity(
            "INTEGRITY-INTRADAY-WO12-EXTENSION-MEASUREMENT-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo12EvidenceInputs:
    fifteen_minute_structure: SemanticQualificationFactV2
    cpr_acceptance: Wo12CprAcceptanceFact
    path_clearance: Wo12PathClearanceFact
    setup_quality: Wo12SetupQualityFact
    extension_measurement: Wo12ExtensionMeasurement | None
    governing_15m_structure_failed: bool = False
    authoritative_directional_conflict: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.fifteen_minute_structure) is not SemanticQualificationFactV2
            or type(self.cpr_acceptance) is not Wo12CprAcceptanceFact
            or type(self.path_clearance) is not Wo12PathClearanceFact
            or type(self.setup_quality) is not Wo12SetupQualityFact
            or (
                self.extension_measurement is not None
                and type(self.extension_measurement) is not Wo12ExtensionMeasurement
            )
            or type(self.governing_15m_structure_failed) is not bool
            or type(self.authoritative_directional_conflict) is not bool
        ):
            raise Wo12ContractError("WO12_EVIDENCE_INPUTS_INVALID")


def adapt_k1(
    handoff: Wo12Handoff,
    fact: SemanticQualificationFactV2,
) -> Wo12CriterionResult:
    _validate_semantic_fact(handoff, fact)
    if fact.availability != "AVAILABLE" or fact.direction in {
        SemanticDirection.UNAVAILABLE,
        SemanticDirection.CONFLICTING,
    }:
        state = Kr370CriterionState.UNAVAILABLE
        reason = "K1_EXACT_DIRECTIONAL_PROGRESSION_UNAVAILABLE"
    elif fact.direction is handoff.inherited_direction:
        state = Kr370CriterionState.SATISFIED
        reason = "K1_COMPLETED_15M_PROGRESSION_ALIGNED"
    else:
        state = Kr370CriterionState.UNSATISFIED
        reason = "K1_COMPLETED_15M_PROGRESSION_NOT_ALIGNED"
    return _criterion(
        Wo12CriterionIdentity.K1_15M_DIRECTIONAL_PROGRESSION,
        state,
        reason,
        (fact.fact_identity,),
        (fact.integrity_identity,),
    )


def adapt_k2(
    handoff: Wo12Handoff,
    fact: Wo12CprAcceptanceFact,
) -> Wo12CriterionResult:
    if (
        type(handoff) is not Wo12Handoff
        or type(fact) is not Wo12CprAcceptanceFact
        or fact.canonical_subject_identity != handoff.canonical_subject_identity
        or fact.market_family is not handoff.market_family
        or fact.analysis_boundary != handoff.analysis_boundary
    ):
        raise Wo12ContractError("WO12_K2_BINDING_INVALID")
    identities = (fact.fact_identity,)
    integrities = (fact.fact_integrity,)
    if (
        fact.completed_close is None
        or fact.cpr_lower is None
        or fact.cpr_upper is None
        or fact.completed_candle_identity is None
        or fact.cpr_evidence_identity is None
    ):
        return _criterion(
            Wo12CriterionIdentity.K2_15M_CPR_ACCEPTANCE,
            Kr370CriterionState.UNAVAILABLE,
            "K2_COMPLETED_CLOSE_OR_CPR_UNAVAILABLE",
            identities,
            integrities,
        )
    accepted = (
        fact.completed_close > fact.cpr_upper
        if handoff.inherited_direction is SemanticDirection.LONG
        else fact.completed_close < fact.cpr_lower
    )
    return _criterion(
        Wo12CriterionIdentity.K2_15M_CPR_ACCEPTANCE,
        Kr370CriterionState.SATISFIED if accepted else Kr370CriterionState.UNSATISFIED,
        "K2_COMPLETED_15M_CLOSE_ACCEPTED_CPR"
        if accepted
        else "K2_COMPLETED_15M_CLOSE_NOT_ACCEPTED_CPR",
        identities,
        integrities,
    )


def adapt_k3(
    handoff: Wo12Handoff,
    fact: Wo12PathClearanceFact,
) -> Wo12CriterionResult:
    _validate_bound_fact(handoff, fact)
    state = {
        Wo12PathState.CLEAR: Kr370CriterionState.SATISFIED,
        Wo12PathState.BLOCKED: Kr370CriterionState.UNSATISFIED,
        Wo12PathState.UNAVAILABLE: Kr370CriterionState.UNAVAILABLE,
    }[fact.state]
    reason = {
        Wo12PathState.CLEAR: "K3_EXISTING_STRUCTURE_PROVES_CLEAR",
        Wo12PathState.BLOCKED: "K3_EXISTING_STRUCTURE_PROVES_IMMEDIATE_OBSTRUCTION",
        Wo12PathState.UNAVAILABLE: "K3_NO_EXISTING_DETERMINISTIC_CONSEQUENCE",
    }[fact.state]
    return _criterion(
        Wo12CriterionIdentity.K3_15M_IMMEDIATE_PATH_CLEARANCE,
        state,
        reason,
        (fact.fact_identity, *fact.source_evidence_identities),
        (fact.fact_integrity, *fact.source_evidence_integrities),
    )


def adapt_k4(
    handoff: Wo12Handoff,
    fact: Wo12SetupQualityFact,
) -> Wo12CriterionResult:
    _validate_bound_fact(handoff, fact)
    if (
        handoff.wo10_evidence_identity,
        handoff.wo10_evidence_integrity,
    ) not in tuple(zip(
        fact.source_evidence_identities,
        fact.source_evidence_integrities,
        strict=True,
    )):
        raise Wo12ContractError("WO12_K4_WO10_EVIDENCE_BINDING_INVALID")
    state = {
        Wo12SetupQualityState.ACCEPTABLE: Kr370CriterionState.SATISFIED,
        Wo12SetupQualityState.ADVERSE: Kr370CriterionState.UNSATISFIED,
        Wo12SetupQualityState.UNAVAILABLE: Kr370CriterionState.UNAVAILABLE,
    }[fact.state]
    reason = {
        Wo12SetupQualityState.ACCEPTABLE: "K4_GOVERNED_SETUP_QUALITY_ACCEPTABLE",
        Wo12SetupQualityState.ADVERSE: "K4_GOVERNED_SETUP_QUALITY_ADVERSE",
        Wo12SetupQualityState.UNAVAILABLE: "K4_GOVERNED_SETUP_QUALITY_UNAVAILABLE",
    }[fact.state]
    return _criterion(
        Wo12CriterionIdentity.K4_15M_SETUP_QUALITY,
        state,
        reason,
        (fact.fact_identity, *fact.source_evidence_identities),
        (fact.fact_integrity, *fact.source_evidence_integrities),
    )


def adapt_k5(
    handoff: Wo12Handoff,
    measurement: Wo12ExtensionMeasurement | None,
) -> Wo12CriterionResult:
    if measurement is None:
        identities = (handoff.wo10_evidence_identity,)
        integrities = (handoff.wo10_evidence_integrity,)
        reason = "K5_STRUCTURAL_ORIGIN_OR_ATR_UNAVAILABLE"
    else:
        if (
            type(measurement) is not Wo12ExtensionMeasurement
            or measurement.canonical_subject_identity != handoff.canonical_subject_identity
            or measurement.market_family is not handoff.market_family
            or measurement.inherited_direction is not handoff.inherited_direction
            or measurement.analysis_boundary != handoff.analysis_boundary
        ):
            raise Wo12ContractError("WO12_K5_BINDING_INVALID")
        identities = (measurement.measurement_identity,)
        integrities = (measurement.measurement_integrity,)
        reason = "K5_THRESHOLD_POLICY_UNRESOLVED"
    return _criterion(
        Wo12CriterionIdentity.K5_15M_NON_EXTENSION,
        Kr370CriterionState.UNAVAILABLE,
        reason,
        identities,
        integrities,
    )


def assemble_wo12_criteria(
    handoff: Wo12Handoff,
    inputs: Wo12EvidenceInputs,
) -> tuple[Wo12CriterionResult, ...]:
    if type(inputs) is not Wo12EvidenceInputs:
        raise Wo12ContractError("WO12_EVIDENCE_INPUTS_INVALID")
    return (
        adapt_k1(handoff, inputs.fifteen_minute_structure),
        adapt_k2(handoff, inputs.cpr_acceptance),
        adapt_k3(handoff, inputs.path_clearance),
        adapt_k4(handoff, inputs.setup_quality),
        adapt_k5(handoff, inputs.extension_measurement),
    )


def _validate_semantic_fact(
    handoff: Wo12Handoff,
    fact: SemanticQualificationFactV2,
) -> None:
    if (
        type(handoff) is not Wo12Handoff
        or type(fact) is not SemanticQualificationFactV2
        or fact.family != "15M_STRUCTURE"
        or fact.canonical_subject_identity != handoff.canonical_subject_identity
        or fact.analysis_boundary != handoff.analysis_boundary
        or fact.phase is not handoff.phase
    ):
        raise Wo12ContractError("WO12_K1_BINDING_INVALID")


def _validate_bound_fact(
    handoff: Wo12Handoff,
    fact: Wo12PathClearanceFact | Wo12SetupQualityFact,
) -> None:
    if (
        type(handoff) is not Wo12Handoff
        or fact.canonical_subject_identity != handoff.canonical_subject_identity
        or fact.market_family is not handoff.market_family
        or fact.analysis_boundary != handoff.analysis_boundary
    ):
        raise Wo12ContractError("WO12_CRITERION_FACT_BINDING_INVALID")


def _criterion(
    identity: Wo12CriterionIdentity,
    state: Kr370CriterionState,
    reason: str,
    evidence_identities: tuple[str, ...],
    evidence_integrities: tuple[str, ...],
) -> Wo12CriterionResult:
    return Wo12CriterionResult(
        identity=identity,
        state=state,
        reason=reason,
        evidence_identities=evidence_identities,
        evidence_integrities=evidence_integrities,
    )


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise Wo12ContractError("WO12_DECIMAL_INVALID")
    try:
        retained = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise Wo12ContractError("WO12_DECIMAL_INVALID") from error
    if not retained.is_finite():
        raise Wo12ContractError("WO12_DECIMAL_INVALID")
    return retained


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [name for name in globals() if name.startswith("WO12_") or name.startswith("Wo12") or name.startswith("adapt_k") or name.startswith("assemble_wo12") or name.startswith("create_wo12")]
