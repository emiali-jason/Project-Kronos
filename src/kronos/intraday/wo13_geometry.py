"""Setup-agnostic Intraday WO-13 geometry and arithmetic foundation.

This Slice-2 module owns immutable structural-price facts, factual target
candidate measurements, range-width arithmetic, independent risk/reward
calculation, Model R:R, and derived availability only.  It deliberately owns
no setup-family construction, target selection, persistence, runtime, Risk,
5M timing, Sponsor decision, execution, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
from typing import Iterable, Mapping, Sequence

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import (
    Wo13FieldAvailability,
    Wo13FieldAvailabilityRecord,
    Wo13GeometryAvailability,
    Wo13GeometryField,
    Wo13WarningCode,
    create_wo13_field_availability,
)
from kronos.intraday.wo13_handoff import WO13_CONTRACT_VERSION


WO13_STRUCTURAL_PRICE_FACT_IDENTITY = (
    "KRONOS-INTRADAY-WO13-STRUCTURAL-PRICE-FACT-V1"
)
WO13_STRUCTURAL_PRICE_FIELD_IDENTITY = (
    "KRONOS-INTRADAY-WO13-STRUCTURAL-PRICE-FIELD-V1"
)
WO13_INVALIDATION_EVENT_IDENTITY = (
    "KRONOS-INTRADAY-WO13-THESIS-INVALIDATION-EVENT-V1"
)
WO13_TARGET_CANDIDATE_IDENTITY = (
    "KRONOS-INTRADAY-WO13-TARGET-CANDIDATE-V1"
)
WO13_RANGE_WIDTH_IDENTITY = "KRONOS-INTRADAY-WO13-RANGE-WIDTH-V1"
WO13_GEOMETRY_MEASUREMENT_IDENTITY = (
    "KRONOS-INTRADAY-WO13-GEOMETRY-MEASUREMENT-V1"
)
WO13_GEOMETRY_CALCULATION_IDENTITY = (
    "KRONOS-INTRADAY-WO13-GEOMETRY-CALCULATION-V1"
)


class Wo13GeometryFailure(StrEnum):
    PRICE_VALUE_INVALID = "PRICE_VALUE_INVALID"
    NON_FINITE_VALUE = "NON_FINITE_VALUE"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    SUBJECT_FAMILY_MISMATCH = "SUBJECT_FAMILY_MISMATCH"
    SOURCE_AUTHORITY_PROHIBITED = "SOURCE_AUTHORITY_PROHIBITED"
    TIMEFRAME_AUTHORITY_INVALID = "TIMEFRAME_AUTHORITY_INVALID"
    SOURCE_INTEGRITY_INVALID = "SOURCE_INTEGRITY_INVALID"
    TRUST_CONTEXT_MISMATCH = "TRUST_CONTEXT_MISMATCH"
    STRUCTURAL_ROLE_INVALID = "STRUCTURAL_ROLE_INVALID"
    FIELD_RESOLUTION_INVALID = "FIELD_RESOLUTION_INVALID"
    INVALIDATION_EVENT_INVALID = "INVALIDATION_EVENT_INVALID"
    TARGET_CANDIDATE_INVALID = "TARGET_CANDIDATE_INVALID"
    RANGE_IDENTITY_MISMATCH = "RANGE_IDENTITY_MISMATCH"
    RANGE_WIDTH_NON_POSITIVE = "RANGE_WIDTH_NON_POSITIVE"
    GEOMETRY_CALCULATION_INVALID = "GEOMETRY_CALCULATION_INVALID"


class Wo13GeometryRejected(ValueError):
    """Sanitized hard trust/contract rejection, distinct from math warnings."""

    def __init__(self, failure: Wo13GeometryFailure) -> None:
        if type(failure) is not Wo13GeometryFailure:
            raise ValueError("WO13_GEOMETRY_FAILURE_INVALID")
        self.failure = failure
        super().__init__(failure.value)


class Wo13StructuralRole(StrEnum):
    ENTRY_REFERENCE_SOURCE = "ENTRY_REFERENCE_SOURCE"
    STOP_REFERENCE_SOURCE = "STOP_REFERENCE_SOURCE"
    THESIS_INVALIDATION_REFERENCE = "THESIS_INVALIDATION_REFERENCE"
    SETUP_NATIVE_TARGET = "SETUP_NATIVE_TARGET"
    TARGET_CONSTRAINT = "TARGET_CONSTRAINT"
    RANGE_HIGH = "RANGE_HIGH"
    RANGE_LOW = "RANGE_LOW"
    QUALIFICATION_CANDLE_HIGH = "QUALIFICATION_CANDLE_HIGH"
    QUALIFICATION_CANDLE_LOW = "QUALIFICATION_CANDLE_LOW"
    PULLBACK_STRUCTURAL_HIGH = "PULLBACK_STRUCTURAL_HIGH"
    PULLBACK_STRUCTURAL_LOW = "PULLBACK_STRUCTURAL_LOW"
    PRIOR_IMPULSE_HIGH = "PRIOR_IMPULSE_HIGH"
    PRIOR_IMPULSE_LOW = "PRIOR_IMPULSE_LOW"
    SESSION_STRUCTURAL_HIGH = "SESSION_STRUCTURAL_HIGH"
    SESSION_STRUCTURAL_LOW = "SESSION_STRUCTURAL_LOW"
    PDH = "PDH"
    PDL = "PDL"
    PIVOT_RESISTANCE = "PIVOT_RESISTANCE"
    PIVOT_SUPPORT = "PIVOT_SUPPORT"
    GOVERNED_STRUCTURAL_BARRIER = "GOVERNED_STRUCTURAL_BARRIER"


class Wo13PriceAuthority(StrEnum):
    NSE_EQUITY_UNDERLYING = "NSE_EQUITY_UNDERLYING"
    NSE_INDEX_UNDERLYING = "NSE_INDEX_UNDERLYING"
    MCX_ACTIVE_CONTRACT = "MCX_ACTIVE_CONTRACT"
    OPTION_PREMIUM = "OPTION_PREMIUM"
    SMA_CONTEXT = "SMA_CONTEXT"
    COMEX_REFERENCE = "COMEX_REFERENCE"
    NYMEX_REFERENCE = "NYMEX_REFERENCE"
    USDINR_REFERENCE = "USDINR_REFERENCE"


class Wo13TargetCandidateKind(StrEnum):
    SETUP_NATIVE_OBJECTIVE = "SETUP_NATIVE_OBJECTIVE"
    STRUCTURAL_CONSTRAINT = "STRUCTURAL_CONSTRAINT"


class Wo13ForwardTargetState(StrEnum):
    FORWARD = "FORWARD"
    AT_ENTRY = "AT_ENTRY"
    BEHIND_ENTRY = "BEHIND_ENTRY"


_ALLOWED_PRICE_AUTHORITY = {
    IntradayMarketFamily.NSE_EQUITY: Wo13PriceAuthority.NSE_EQUITY_UNDERLYING,
    IntradayMarketFamily.NSE_INDEX: Wo13PriceAuthority.NSE_INDEX_UNDERLYING,
    IntradayMarketFamily.MCX: Wo13PriceAuthority.MCX_ACTIVE_CONTRACT,
}

_FIELD_ROLES = {
    Wo13GeometryField.ENTRY_REFERENCE: {
        Wo13StructuralRole.ENTRY_REFERENCE_SOURCE,
    },
    Wo13GeometryField.STOP: {
        Wo13StructuralRole.STOP_REFERENCE_SOURCE,
    },
    Wo13GeometryField.THESIS_INVALIDATION_REFERENCE: {
        Wo13StructuralRole.THESIS_INVALIDATION_REFERENCE,
    },
    Wo13GeometryField.CANONICAL_TARGET: {
        Wo13StructuralRole.SETUP_NATIVE_TARGET,
        Wo13StructuralRole.TARGET_CONSTRAINT,
        Wo13StructuralRole.RANGE_HIGH,
        Wo13StructuralRole.RANGE_LOW,
        Wo13StructuralRole.PULLBACK_STRUCTURAL_HIGH,
        Wo13StructuralRole.PULLBACK_STRUCTURAL_LOW,
        Wo13StructuralRole.PRIOR_IMPULSE_HIGH,
        Wo13StructuralRole.PRIOR_IMPULSE_LOW,
        Wo13StructuralRole.SESSION_STRUCTURAL_HIGH,
        Wo13StructuralRole.SESSION_STRUCTURAL_LOW,
        Wo13StructuralRole.PDH,
        Wo13StructuralRole.PDL,
        Wo13StructuralRole.PIVOT_RESISTANCE,
        Wo13StructuralRole.PIVOT_SUPPORT,
        Wo13StructuralRole.GOVERNED_STRUCTURAL_BARRIER,
    },
}

_CONSTRAINT_ROLES = _FIELD_ROLES[Wo13GeometryField.CANONICAL_TARGET] - {
    Wo13StructuralRole.SETUP_NATIVE_TARGET,
}

_CALCULATION_FIELDS = (
    Wo13GeometryField.ENTRY_REFERENCE,
    Wo13GeometryField.STOP,
    Wo13GeometryField.THESIS_INVALIDATION_REFERENCE,
    Wo13GeometryField.THESIS_INVALIDATION_EVENT,
    Wo13GeometryField.CANONICAL_TARGET,
    Wo13GeometryField.RISK_DISTANCE,
    Wo13GeometryField.REWARD_DISTANCE,
    Wo13GeometryField.MODEL_RR,
)


@dataclass(frozen=True, slots=True)
class Wo13StructuralPriceFact:
    fact_identity: str
    fact_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    timeframe: IntradayTimeframe
    price: Decimal
    structural_role: Wo13StructuralRole
    price_authority: Wo13PriceAuthority
    structure_identity: str
    source_evidence_identity: str
    source_evidence_integrity: str
    analysis_boundary: datetime
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    market_session_identity: str | None
    schema_identity: str = WO13_STRUCTURAL_PRICE_FACT_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "fact_identity", "fact_integrity")
        mcx = self.market_family is IntradayMarketFamily.MCX
        if (
            not _texts((
                self.canonical_subject_identity,
                self.structure_identity,
                self.source_evidence_identity,
                self.source_evidence_integrity,
                self.instrument_identity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or _market_family(self.canonical_subject_identity) is not self.market_family
            or type(self.timeframe) is not IntradayTimeframe
            or self.timeframe not in {
                IntradayTimeframe.DAILY,
                IntradayTimeframe.FIFTEEN_MINUTES,
            }
            or type(self.price) is not Decimal
            or not self.price.is_finite()
            or self.price <= 0
            or type(self.structural_role) is not Wo13StructuralRole
            or type(self.price_authority) is not Wo13PriceAuthority
            or self.price_authority is not _ALLOWED_PRICE_AUTHORITY[self.market_family]
            or not _aware(self.analysis_boundary)
            or (self.market_session_identity is not None and not _text(self.market_session_identity))
            or mcx != (self.actual_contract_identity is not None)
            or mcx != (self.roll_lineage_identity is not None)
            or self.actual_contract_identity is not None
            and not _text(self.actual_contract_identity)
            or self.roll_lineage_identity is not None
            and not _text(self.roll_lineage_identity)
            or self.schema_identity != WO13_STRUCTURAL_PRICE_FACT_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.fact_identity != _identity("INTRADAY-WO13-PRICE-", values)
            or self.fact_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-PRICE-", values)
        ):
            raise Wo13GeometryRejected(Wo13GeometryFailure.SOURCE_INTEGRITY_INVALID)


def create_wo13_structural_price_fact(
    *,
    canonical_subject_identity: str,
    market_family: IntradayMarketFamily,
    timeframe: IntradayTimeframe,
    price: object,
    structural_role: Wo13StructuralRole,
    price_authority: Wo13PriceAuthority,
    structure_identity: str,
    source_evidence_identity: str,
    source_evidence_integrity: str,
    analysis_boundary: datetime,
    instrument_identity: str,
    actual_contract_identity: str | None = None,
    roll_lineage_identity: str | None = None,
    market_session_identity: str | None = None,
) -> Wo13StructuralPriceFact:
    if type(market_family) is not IntradayMarketFamily or (
        _market_family(canonical_subject_identity) is not market_family
    ):
        raise Wo13GeometryRejected(Wo13GeometryFailure.SUBJECT_FAMILY_MISMATCH)
    if type(timeframe) is not IntradayTimeframe or timeframe not in {
        IntradayTimeframe.DAILY,
        IntradayTimeframe.FIFTEEN_MINUTES,
    }:
        raise Wo13GeometryRejected(Wo13GeometryFailure.TIMEFRAME_AUTHORITY_INVALID)
    if (
        type(price_authority) is not Wo13PriceAuthority
        or price_authority is not _ALLOWED_PRICE_AUTHORITY[market_family]
    ):
        raise Wo13GeometryRejected(Wo13GeometryFailure.SOURCE_AUTHORITY_PROHIBITED)
    retained_price = _price(price)
    values = {
        "canonical_subject_identity": canonical_subject_identity,
        "market_family": market_family,
        "timeframe": timeframe,
        "price": retained_price,
        "structural_role": structural_role,
        "price_authority": price_authority,
        "structure_identity": structure_identity,
        "source_evidence_identity": source_evidence_identity,
        "source_evidence_integrity": source_evidence_integrity,
        "analysis_boundary": analysis_boundary,
        "instrument_identity": instrument_identity,
        "actual_contract_identity": actual_contract_identity,
        "roll_lineage_identity": roll_lineage_identity,
        "market_session_identity": market_session_identity,
        "schema_identity": WO13_STRUCTURAL_PRICE_FACT_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13StructuralPriceFact(
        fact_identity=_identity("INTRADAY-WO13-PRICE-", values),
        fact_integrity=_identity("INTEGRITY-INTRADAY-WO13-PRICE-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13StructuralPriceField:
    resolution_identity: str
    resolution_integrity: str
    field: Wo13GeometryField
    facts: tuple[Wo13StructuralPriceFact, ...]
    expected_source_identities: tuple[str, ...]
    expected_source_integrities: tuple[str, ...]
    availability: Wo13FieldAvailability
    schema_identity: str = WO13_STRUCTURAL_PRICE_FIELD_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "resolution_identity", "resolution_integrity")
        expected = _derive_field_availability(
            self.facts,
            self.expected_source_identities,
        )
        if (
            self.field not in _FIELD_ROLES
            or any(type(item) is not Wo13StructuralPriceFact for item in self.facts)
            or any(item.structural_role not in _FIELD_ROLES[self.field] for item in self.facts)
            or tuple(sorted(self.facts, key=lambda item: item.fact_identity)) != self.facts
            or len({item.fact_identity for item in self.facts}) != len(self.facts)
            or len(self.expected_source_identities) != len(self.expected_source_integrities)
            or tuple(sorted(zip(
                self.expected_source_identities,
                self.expected_source_integrities,
                strict=True,
            ))) != tuple(zip(
                self.expected_source_identities,
                self.expected_source_integrities,
                strict=True,
            ))
            or any(
                not _texts(pair)
                for pair in zip(
                    self.expected_source_identities,
                    self.expected_source_integrities,
                    strict=True,
                )
            )
            or len(set(self.expected_source_identities)) != len(self.expected_source_identities)
            or self.facts and not _facts_share_context(self.facts)
            or self.facts
            and any(
                (item.source_evidence_identity, item.source_evidence_integrity)
                not in set(zip(
                    self.expected_source_identities,
                    self.expected_source_integrities,
                    strict=True,
                ))
                for item in self.facts
            )
            or self.availability is not expected
            or self.schema_identity != WO13_STRUCTURAL_PRICE_FIELD_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.resolution_identity
            != _identity("INTRADAY-WO13-PRICE-FIELD-", values)
            or self.resolution_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-PRICE-FIELD-", values)
        ):
            raise Wo13GeometryRejected(Wo13GeometryFailure.FIELD_RESOLUTION_INVALID)

    @property
    def selected_fact(self) -> Wo13StructuralPriceFact | None:
        return self.facts[0] if self.availability is Wo13FieldAvailability.AVAILABLE else None

    @property
    def availability_record(self) -> Wo13FieldAvailabilityRecord:
        return create_wo13_field_availability(
            self.field,
            self.availability,
            reason=f"{self.field.value}_{self.availability.value}",
            source_identities=self.expected_source_identities,
            source_integrities=self.expected_source_integrities,
        )


def resolve_wo13_structural_price_field(
    field: Wo13GeometryField,
    *,
    facts: Sequence[Wo13StructuralPriceFact] = (),
    expected_sources: Sequence[tuple[str, str]] = (),
) -> Wo13StructuralPriceField:
    if field not in _FIELD_ROLES:
        raise Wo13GeometryRejected(Wo13GeometryFailure.FIELD_RESOLUTION_INVALID)
    retained: dict[str, Wo13StructuralPriceFact] = {}
    for item in facts:
        if type(item) is not Wo13StructuralPriceFact:
            raise Wo13GeometryRejected(Wo13GeometryFailure.FIELD_RESOLUTION_INVALID)
        previous = retained.get(item.fact_identity)
        if previous is not None and previous.fact_integrity != item.fact_integrity:
            raise Wo13GeometryRejected(Wo13GeometryFailure.SOURCE_INTEGRITY_INVALID)
        retained[item.fact_identity] = item
    ordered_facts = tuple(sorted(retained.values(), key=lambda item: item.fact_identity))
    source_pairs = list(expected_sources)
    if ordered_facts and not source_pairs:
        source_pairs = [
            (item.source_evidence_identity, item.source_evidence_integrity)
            for item in ordered_facts
        ]
    ordered_sources = _unique_pairs(source_pairs)
    availability = _derive_field_availability(
        ordered_facts,
        tuple(item[0] for item in ordered_sources),
    )
    values = {
        "field": field,
        "facts": ordered_facts,
        "expected_source_identities": tuple(item[0] for item in ordered_sources),
        "expected_source_integrities": tuple(item[1] for item in ordered_sources),
        "availability": availability,
        "schema_identity": WO13_STRUCTURAL_PRICE_FIELD_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13StructuralPriceField(
        resolution_identity=_identity("INTRADAY-WO13-PRICE-FIELD-", values),
        resolution_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-PRICE-FIELD-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13ThesisInvalidationEvent:
    event_identity: str
    event_integrity: str
    reference_fact_identity: str
    reference_fact_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    analysis_boundary: datetime
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    event_code: str
    source_evidence_identity: str
    source_evidence_integrity: str
    schema_identity: str = WO13_INVALIDATION_EVENT_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "event_identity", "event_integrity")
        if (
            not _texts((
                self.reference_fact_identity,
                self.reference_fact_integrity,
                self.canonical_subject_identity,
                self.instrument_identity,
                self.event_code,
                self.source_evidence_identity,
                self.source_evidence_integrity,
            ))
            or not _code(self.event_code)
            or type(self.market_family) is not IntradayMarketFamily
            or not _aware(self.analysis_boundary)
            or self.schema_identity != WO13_INVALIDATION_EVENT_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.event_identity != _identity("INTRADAY-WO13-INVALIDATION-", values)
            or self.event_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-INVALIDATION-", values)
        ):
            raise Wo13GeometryRejected(Wo13GeometryFailure.INVALIDATION_EVENT_INVALID)


def create_wo13_thesis_invalidation_event(
    *,
    reference: Wo13StructuralPriceFact,
    event_code: str,
    source_evidence_identity: str,
    source_evidence_integrity: str,
) -> Wo13ThesisInvalidationEvent:
    if (
        type(reference) is not Wo13StructuralPriceFact
        or reference.structural_role
        is not Wo13StructuralRole.THESIS_INVALIDATION_REFERENCE
    ):
        raise Wo13GeometryRejected(Wo13GeometryFailure.INVALIDATION_EVENT_INVALID)
    values = {
        "reference_fact_identity": reference.fact_identity,
        "reference_fact_integrity": reference.fact_integrity,
        "canonical_subject_identity": reference.canonical_subject_identity,
        "market_family": reference.market_family,
        "analysis_boundary": reference.analysis_boundary,
        "instrument_identity": reference.instrument_identity,
        "actual_contract_identity": reference.actual_contract_identity,
        "roll_lineage_identity": reference.roll_lineage_identity,
        "event_code": event_code,
        "source_evidence_identity": source_evidence_identity,
        "source_evidence_integrity": source_evidence_integrity,
        "schema_identity": WO13_INVALIDATION_EVENT_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13ThesisInvalidationEvent(
        event_identity=_identity("INTRADAY-WO13-INVALIDATION-", values),
        event_integrity=_identity("INTEGRITY-INTRADAY-WO13-INVALIDATION-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13TargetCandidate:
    candidate_identity: str
    candidate_integrity: str
    entry_reference: Wo13StructuralPriceFact
    candidate: Wo13StructuralPriceFact
    direction: SemanticDirection
    kind: Wo13TargetCandidateKind
    forward_state: Wo13ForwardTargetState
    directional_distance: Decimal | None
    schema_identity: str = WO13_TARGET_CANDIDATE_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "candidate_identity", "candidate_integrity")
        expected_state, expected_distance = _target_state(
            self.direction,
            self.entry_reference.price,
            self.candidate.price,
        )
        if (
            type(self.entry_reference) is not Wo13StructuralPriceFact
            or type(self.candidate) is not Wo13StructuralPriceFact
            or self.entry_reference.structural_role
            is not Wo13StructuralRole.ENTRY_REFERENCE_SOURCE
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.kind) is not Wo13TargetCandidateKind
            or not _same_context(self.entry_reference, self.candidate)
            or self.kind is Wo13TargetCandidateKind.SETUP_NATIVE_OBJECTIVE
            and self.candidate.structural_role is not Wo13StructuralRole.SETUP_NATIVE_TARGET
            or self.kind is Wo13TargetCandidateKind.STRUCTURAL_CONSTRAINT
            and self.candidate.structural_role not in _CONSTRAINT_ROLES
            or self.forward_state is not expected_state
            or self.directional_distance != expected_distance
            or self.schema_identity != WO13_TARGET_CANDIDATE_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.candidate_identity != _identity("INTRADAY-WO13-TARGET-", values)
            or self.candidate_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-TARGET-", values)
        ):
            raise Wo13GeometryRejected(Wo13GeometryFailure.TARGET_CANDIDATE_INVALID)

    @property
    def price(self) -> Decimal:
        return self.candidate.price

    @property
    def structural_role(self) -> Wo13StructuralRole:
        return self.candidate.structural_role


def create_wo13_target_candidate(
    *,
    entry_reference: Wo13StructuralPriceFact,
    candidate: Wo13StructuralPriceFact,
    direction: SemanticDirection,
    kind: Wo13TargetCandidateKind,
) -> Wo13TargetCandidate:
    if (
        type(entry_reference) is not Wo13StructuralPriceFact
        or type(candidate) is not Wo13StructuralPriceFact
        or direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
    ):
        raise Wo13GeometryRejected(Wo13GeometryFailure.TARGET_CANDIDATE_INVALID)
    if not _same_context(entry_reference, candidate):
        raise Wo13GeometryRejected(Wo13GeometryFailure.TRUST_CONTEXT_MISMATCH)
    state, distance = _target_state(direction, entry_reference.price, candidate.price)
    values = {
        "entry_reference": entry_reference,
        "candidate": candidate,
        "direction": direction,
        "kind": kind,
        "forward_state": state,
        "directional_distance": distance,
        "schema_identity": WO13_TARGET_CANDIDATE_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13TargetCandidate(
        candidate_identity=_identity("INTRADAY-WO13-TARGET-", values),
        candidate_integrity=_identity("INTEGRITY-INTRADAY-WO13-TARGET-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13RangeWidthMeasurement:
    measurement_identity: str
    measurement_integrity: str
    range_high: Wo13StructuralPriceFact
    range_low: Wo13StructuralPriceFact
    range_width: Decimal
    schema_identity: str = WO13_RANGE_WIDTH_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "measurement_identity", "measurement_integrity")
        if (
            type(self.range_high) is not Wo13StructuralPriceFact
            or type(self.range_low) is not Wo13StructuralPriceFact
            or self.range_high.structural_role is not Wo13StructuralRole.RANGE_HIGH
            or self.range_low.structural_role is not Wo13StructuralRole.RANGE_LOW
            or not _same_context(self.range_high, self.range_low)
            or self.range_high.structure_identity != self.range_low.structure_identity
            or self.range_high.timeframe is not self.range_low.timeframe
            or self.range_high.market_session_identity
            != self.range_low.market_session_identity
            or self.range_width != self.range_high.price - self.range_low.price
            or self.range_width <= 0
            or self.schema_identity != WO13_RANGE_WIDTH_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.measurement_identity != _identity("INTRADAY-WO13-RANGE-WIDTH-", values)
            or self.measurement_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-RANGE-WIDTH-", values)
        ):
            raise Wo13GeometryRejected(Wo13GeometryFailure.RANGE_IDENTITY_MISMATCH)


def calculate_wo13_range_width(
    range_high: Wo13StructuralPriceFact,
    range_low: Wo13StructuralPriceFact,
) -> Wo13RangeWidthMeasurement:
    if (
        type(range_high) is not Wo13StructuralPriceFact
        or type(range_low) is not Wo13StructuralPriceFact
        or not _same_context(range_high, range_low)
        or range_high.structure_identity != range_low.structure_identity
        or range_high.timeframe is not range_low.timeframe
        or range_high.market_session_identity != range_low.market_session_identity
    ):
        raise Wo13GeometryRejected(Wo13GeometryFailure.RANGE_IDENTITY_MISMATCH)
    width = range_high.price - range_low.price
    if width <= 0:
        raise Wo13GeometryRejected(Wo13GeometryFailure.RANGE_WIDTH_NON_POSITIVE)
    values = {
        "range_high": range_high,
        "range_low": range_low,
        "range_width": width,
        "schema_identity": WO13_RANGE_WIDTH_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13RangeWidthMeasurement(
        measurement_identity=_identity("INTRADAY-WO13-RANGE-WIDTH-", values),
        measurement_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-RANGE-WIDTH-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13GeometryMeasurement:
    measurement_identity: str
    measurement_integrity: str
    field: Wo13GeometryField
    direction: SemanticDirection
    value: Decimal | None
    availability: Wo13FieldAvailabilityRecord
    warnings: tuple[Wo13WarningCode, ...]
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    schema_identity: str = WO13_GEOMETRY_MEASUREMENT_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "measurement_identity", "measurement_integrity")
        if (
            self.field not in {
                Wo13GeometryField.RISK_DISTANCE,
                Wo13GeometryField.REWARD_DISTANCE,
                Wo13GeometryField.MODEL_RR,
            }
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or self.availability.field is not self.field
            or (
                self.availability.availability
                is Wo13FieldAvailability.AVAILABLE
            )
            != (self.value is not None)
            or self.value is not None
            and (type(self.value) is not Decimal or not self.value.is_finite() or self.value <= 0)
            or len(self.source_identities) != len(self.source_integrities)
            or any(
                not _texts(pair)
                for pair in zip(
                    self.source_identities,
                    self.source_integrities,
                    strict=True,
                )
            )
            or tuple(
                item for item in Wo13WarningCode if item in set(self.warnings)
            )
            != self.warnings
            or self.schema_identity != WO13_GEOMETRY_MEASUREMENT_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.measurement_identity
            != _identity("INTRADAY-WO13-MEASUREMENT-", values)
            or self.measurement_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-MEASUREMENT-", values)
        ):
            raise Wo13GeometryRejected(
                Wo13GeometryFailure.GEOMETRY_CALCULATION_INVALID
            )


def calculate_wo13_risk_distance(
    *,
    direction: SemanticDirection,
    entry_reference: Wo13StructuralPriceField,
    stop: Wo13StructuralPriceField,
) -> Wo13GeometryMeasurement:
    _require_measurement_inputs(
        direction,
        (entry_reference, Wo13GeometryField.ENTRY_REFERENCE),
        (stop, Wo13GeometryField.STOP),
    )
    entry_fact = entry_reference.selected_fact
    stop_fact = stop.selected_fact
    value: Decimal | None = None
    warnings: set[Wo13WarningCode] = set()
    if entry_fact is not None and stop_fact is not None:
        value = (
            entry_fact.price - stop_fact.price
            if direction is SemanticDirection.LONG
            else stop_fact.price - entry_fact.price
        )
        if not value.is_finite():
            value = None
            warnings.add(Wo13WarningCode.NON_FINITE_VALUE)
        elif value <= 0:
            value = None
            warnings.update({
                Wo13WarningCode.NON_POSITIVE_RISK,
                Wo13WarningCode.INVALID_DIRECTIONAL_GEOMETRY,
            })
    return _create_measurement(
        field=Wo13GeometryField.RISK_DISTANCE,
        direction=direction,
        value=value,
        inputs=(entry_reference, stop),
        warnings=warnings,
        failure_reason=(
            "NON_POSITIVE_RISK"
            if Wo13WarningCode.NON_POSITIVE_RISK in warnings
            else None
        ),
    )


def calculate_wo13_reward_distance(
    *,
    direction: SemanticDirection,
    entry_reference: Wo13StructuralPriceField,
    target: Wo13StructuralPriceField,
) -> Wo13GeometryMeasurement:
    _require_measurement_inputs(
        direction,
        (entry_reference, Wo13GeometryField.ENTRY_REFERENCE),
        (target, Wo13GeometryField.CANONICAL_TARGET),
    )
    entry_fact = entry_reference.selected_fact
    target_fact = target.selected_fact
    value: Decimal | None = None
    warnings: set[Wo13WarningCode] = set()
    if entry_fact is not None and target_fact is not None:
        value = (
            target_fact.price - entry_fact.price
            if direction is SemanticDirection.LONG
            else entry_fact.price - target_fact.price
        )
        if not value.is_finite():
            value = None
            warnings.add(Wo13WarningCode.NON_FINITE_VALUE)
        elif value <= 0:
            value = None
            warnings.update({
                Wo13WarningCode.NON_POSITIVE_REWARD,
                Wo13WarningCode.INVALID_DIRECTIONAL_GEOMETRY,
            })
    return _create_measurement(
        field=Wo13GeometryField.REWARD_DISTANCE,
        direction=direction,
        value=value,
        inputs=(entry_reference, target),
        warnings=warnings,
        failure_reason=(
            "NON_POSITIVE_REWARD"
            if Wo13WarningCode.NON_POSITIVE_REWARD in warnings
            else None
        ),
    )


def calculate_wo13_model_rr(
    *,
    risk: Wo13GeometryMeasurement,
    reward: Wo13GeometryMeasurement,
) -> Wo13GeometryMeasurement:
    if (
        type(risk) is not Wo13GeometryMeasurement
        or type(reward) is not Wo13GeometryMeasurement
        or risk.field is not Wo13GeometryField.RISK_DISTANCE
        or reward.field is not Wo13GeometryField.REWARD_DISTANCE
        or risk.direction is not reward.direction
    ):
        raise Wo13GeometryRejected(
            Wo13GeometryFailure.GEOMETRY_CALCULATION_INVALID
        )
    value: Decimal | None = None
    warnings: set[Wo13WarningCode] = set()
    if risk.value is not None and reward.value is not None:
        value = reward.value / risk.value
        if not value.is_finite():
            value = None
            warnings.add(Wo13WarningCode.NON_FINITE_VALUE)
    sources = (
        (risk.measurement_identity, risk.measurement_integrity),
        (reward.measurement_identity, reward.measurement_integrity),
    )
    availability = _derived_availability(
        Wo13GeometryField.MODEL_RR,
        value,
        (risk.availability.availability, reward.availability.availability),
        sources,
        "MODEL_RR_INPUT_UNAVAILABLE",
    )
    return _materialize_measurement(
        field=Wo13GeometryField.MODEL_RR,
        direction=risk.direction,
        value=value,
        availability=availability,
        warnings=warnings,
        sources=sources,
    )


@dataclass(frozen=True, slots=True)
class Wo13GeometryCalculation:
    calculation_identity: str
    calculation_integrity: str
    direction: SemanticDirection
    entry_reference: Wo13StructuralPriceField
    stop: Wo13StructuralPriceField
    thesis_invalidation_reference: Wo13StructuralPriceField
    thesis_invalidation_event: Wo13ThesisInvalidationEvent | None
    target: Wo13StructuralPriceField
    risk_measurement: Wo13GeometryMeasurement
    reward_measurement: Wo13GeometryMeasurement
    model_rr_measurement: Wo13GeometryMeasurement
    risk_distance: Decimal | None
    reward_distance: Decimal | None
    model_rr: Decimal | None
    field_availability: tuple[Wo13FieldAvailabilityRecord, ...]
    geometry_availability: Wo13GeometryAvailability
    warnings: tuple[Wo13WarningCode, ...]
    schema_identity: str = WO13_GEOMETRY_CALCULATION_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    tick_normalization_applied: bool = False
    risk_authority: bool = False
    entry_timing_authority: bool = False
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "calculation_identity", "calculation_integrity")
        expected = _calculate_geometry_values(
            direction=self.direction,
            entry_reference=self.entry_reference,
            stop=self.stop,
            thesis_invalidation_reference=self.thesis_invalidation_reference,
            thesis_invalidation_event=self.thesis_invalidation_event,
            target=self.target,
        )
        if (
            self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or tuple(item.field for item in self.field_availability) != _CALCULATION_FIELDS
            or (
                self.risk_distance,
                self.reward_distance,
                self.model_rr,
                self.risk_measurement,
                self.reward_measurement,
                self.model_rr_measurement,
                self.field_availability,
                self.geometry_availability,
                self.warnings,
            )
            != expected
            or self.schema_identity != WO13_GEOMETRY_CALCULATION_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or any((
                self.tick_normalization_applied,
                self.risk_authority,
                self.entry_timing_authority,
                self.sponsor_decision_authority,
                self.execution_authority,
                self.broker_authority,
            ))
            or self.calculation_identity
            != _identity("INTRADAY-WO13-GEOMETRY-CALCULATION-", values)
            or self.calculation_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-GEOMETRY-CALCULATION-", values)
        ):
            raise Wo13GeometryRejected(
                Wo13GeometryFailure.GEOMETRY_CALCULATION_INVALID
            )


def calculate_wo13_geometry(
    *,
    direction: SemanticDirection,
    entry_reference: Wo13StructuralPriceField,
    stop: Wo13StructuralPriceField,
    thesis_invalidation_reference: Wo13StructuralPriceField,
    thesis_invalidation_event: Wo13ThesisInvalidationEvent | None,
    target: Wo13StructuralPriceField,
) -> Wo13GeometryCalculation:
    if direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}:
        raise Wo13GeometryRejected(
            Wo13GeometryFailure.GEOMETRY_CALCULATION_INVALID
        )
    calculated = _calculate_geometry_values(
        direction=direction,
        entry_reference=entry_reference,
        stop=stop,
        thesis_invalidation_reference=thesis_invalidation_reference,
        thesis_invalidation_event=thesis_invalidation_event,
        target=target,
    )
    (
        risk,
        reward,
        model_rr,
        risk_measurement,
        reward_measurement,
        model_rr_measurement,
        availability,
        geometry,
        warnings,
    ) = calculated
    values = {
        "direction": direction,
        "entry_reference": entry_reference,
        "stop": stop,
        "thesis_invalidation_reference": thesis_invalidation_reference,
        "thesis_invalidation_event": thesis_invalidation_event,
        "target": target,
        "risk_measurement": risk_measurement,
        "reward_measurement": reward_measurement,
        "model_rr_measurement": model_rr_measurement,
        "risk_distance": risk,
        "reward_distance": reward,
        "model_rr": model_rr,
        "field_availability": availability,
        "geometry_availability": geometry,
        "warnings": warnings,
        "schema_identity": WO13_GEOMETRY_CALCULATION_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "tick_normalization_applied": False,
        "risk_authority": False,
        "entry_timing_authority": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo13GeometryCalculation(
        calculation_identity=_identity(
            "INTRADAY-WO13-GEOMETRY-CALCULATION-", values
        ),
        calculation_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-GEOMETRY-CALCULATION-", values
        ),
        **values,
    )


def _calculate_geometry_values(
    *,
    direction: SemanticDirection,
    entry_reference: Wo13StructuralPriceField,
    stop: Wo13StructuralPriceField,
    thesis_invalidation_reference: Wo13StructuralPriceField,
    thesis_invalidation_event: Wo13ThesisInvalidationEvent | None,
    target: Wo13StructuralPriceField,
) -> tuple[
    Decimal | None,
    Decimal | None,
    Decimal | None,
    Wo13GeometryMeasurement,
    Wo13GeometryMeasurement,
    Wo13GeometryMeasurement,
    tuple[Wo13FieldAvailabilityRecord, ...],
    Wo13GeometryAvailability,
    tuple[Wo13WarningCode, ...],
]:
    fields = (entry_reference, stop, thesis_invalidation_reference, target)
    if (
        any(type(item) is not Wo13StructuralPriceField for item in fields)
        or tuple(item.field for item in fields)
        != (
            Wo13GeometryField.ENTRY_REFERENCE,
            Wo13GeometryField.STOP,
            Wo13GeometryField.THESIS_INVALIDATION_REFERENCE,
            Wo13GeometryField.CANONICAL_TARGET,
        )
    ):
        raise Wo13GeometryRejected(
            Wo13GeometryFailure.GEOMETRY_CALCULATION_INVALID
        )
    selected = tuple(
        item.selected_fact for item in fields if item.selected_fact is not None
    )
    if selected and not _facts_share_context(selected):
        raise Wo13GeometryRejected(Wo13GeometryFailure.TRUST_CONTEXT_MISMATCH)
    invalidation_fact = thesis_invalidation_reference.selected_fact
    if thesis_invalidation_event is not None and (
        type(thesis_invalidation_event) is not Wo13ThesisInvalidationEvent
        or invalidation_fact is None
        or thesis_invalidation_event.reference_fact_identity
        != invalidation_fact.fact_identity
        or thesis_invalidation_event.reference_fact_integrity
        != invalidation_fact.fact_integrity
    ):
        raise Wo13GeometryRejected(Wo13GeometryFailure.INVALIDATION_EVENT_INVALID)

    risk_measurement = calculate_wo13_risk_distance(
        direction=direction,
        entry_reference=entry_reference,
        stop=stop,
    )
    reward_measurement = calculate_wo13_reward_distance(
        direction=direction,
        entry_reference=entry_reference,
        target=target,
    )
    model_rr_measurement = calculate_wo13_model_rr(
        risk=risk_measurement,
        reward=reward_measurement,
    )
    risk = risk_measurement.value
    reward = reward_measurement.value
    model_rr = model_rr_measurement.value
    warning_set = {
        *risk_measurement.warnings,
        *reward_measurement.warnings,
        *model_rr_measurement.warnings,
    }
    event_availability = (
        Wo13FieldAvailability.AVAILABLE
        if thesis_invalidation_event is not None
        else Wo13FieldAvailability.INCOMPLETE
        if thesis_invalidation_reference.availability
        is Wo13FieldAvailability.AVAILABLE
        else thesis_invalidation_reference.availability
    )
    event_sources = (
        ()
        if thesis_invalidation_event is None
        else (thesis_invalidation_event.source_evidence_identity,)
    )
    event_integrities = (
        ()
        if thesis_invalidation_event is None
        else (thesis_invalidation_event.source_evidence_integrity,)
    )
    event_record = create_wo13_field_availability(
        Wo13GeometryField.THESIS_INVALIDATION_EVENT,
        event_availability,
        reason=f"THESIS_INVALIDATION_EVENT_{event_availability.value}",
        source_identities=event_sources,
        source_integrities=event_integrities,
    )
    records = (
        entry_reference.availability_record,
        stop.availability_record,
        thesis_invalidation_reference.availability_record,
        event_record,
        target.availability_record,
        risk_measurement.availability,
        reward_measurement.availability,
        model_rr_measurement.availability,
    )
    available_count = sum(
        item.availability is Wo13FieldAvailability.AVAILABLE for item in records
    )
    geometry = (
        Wo13GeometryAvailability.GEOMETRY_COMPLETE
        if available_count == len(records)
        else Wo13GeometryAvailability.GEOMETRY_UNAVAILABLE
        if available_count == 0
        else Wo13GeometryAvailability.GEOMETRY_PARTIAL
    )
    warning_order = tuple(Wo13WarningCode)
    warnings = tuple(item for item in warning_order if item in warning_set)
    return (
        risk,
        reward,
        model_rr,
        risk_measurement,
        reward_measurement,
        model_rr_measurement,
        records,
        geometry,
        warnings,
    )


def _require_measurement_inputs(
    direction: SemanticDirection,
    *inputs: tuple[Wo13StructuralPriceField, Wo13GeometryField],
) -> None:
    if direction not in {SemanticDirection.LONG, SemanticDirection.SHORT} or any(
        type(item) is not Wo13StructuralPriceField or item.field is not expected
        for item, expected in inputs
    ):
        raise Wo13GeometryRejected(
            Wo13GeometryFailure.GEOMETRY_CALCULATION_INVALID
        )
    selected = tuple(
        item.selected_fact for item, _ in inputs if item.selected_fact is not None
    )
    if selected and not _facts_share_context(selected):
        raise Wo13GeometryRejected(Wo13GeometryFailure.TRUST_CONTEXT_MISMATCH)


def _create_measurement(
    *,
    field: Wo13GeometryField,
    direction: SemanticDirection,
    value: Decimal | None,
    inputs: Sequence[Wo13StructuralPriceField],
    warnings: set[Wo13WarningCode],
    failure_reason: str | None,
) -> Wo13GeometryMeasurement:
    sources = tuple(
        (item.resolution_identity, item.resolution_integrity) for item in inputs
    )
    availability = _derived_availability(
        field,
        value,
        tuple(item.availability for item in inputs),
        sources,
        failure_reason or f"{field.value}_SOURCE_UNAVAILABLE",
    )
    return _materialize_measurement(
        field=field,
        direction=direction,
        value=value,
        availability=availability,
        warnings=warnings,
        sources=sources,
    )


def _derived_availability(
    field: Wo13GeometryField,
    value: Decimal | None,
    input_states: Sequence[Wo13FieldAvailability],
    sources: Sequence[tuple[str, str]],
    failure_reason: str,
) -> Wo13FieldAvailabilityRecord:
    if value is not None:
        state = Wo13FieldAvailability.AVAILABLE
        reason = f"{field.value}_CALCULATED"
    elif Wo13FieldAvailability.AMBIGUOUS in input_states:
        state = Wo13FieldAvailability.AMBIGUOUS
        reason = f"{field.value}_SOURCE_AMBIGUOUS"
    elif Wo13FieldAvailability.INCOMPLETE in input_states:
        state = Wo13FieldAvailability.INCOMPLETE
        reason = f"{field.value}_SOURCE_INCOMPLETE"
    else:
        state = Wo13FieldAvailability.UNAVAILABLE
        reason = failure_reason
    return create_wo13_field_availability(
        field,
        state,
        reason=reason,
        source_identities=tuple(item[0] for item in sources),
        source_integrities=tuple(item[1] for item in sources),
    )


def _materialize_measurement(
    *,
    field: Wo13GeometryField,
    direction: SemanticDirection,
    value: Decimal | None,
    availability: Wo13FieldAvailabilityRecord,
    warnings: set[Wo13WarningCode],
    sources: Sequence[tuple[str, str]],
) -> Wo13GeometryMeasurement:
    ordered_warnings = tuple(item for item in Wo13WarningCode if item in warnings)
    values = {
        "field": field,
        "direction": direction,
        "value": value,
        "availability": availability,
        "warnings": ordered_warnings,
        "source_identities": tuple(item[0] for item in sources),
        "source_integrities": tuple(item[1] for item in sources),
        "schema_identity": WO13_GEOMETRY_MEASUREMENT_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13GeometryMeasurement(
        measurement_identity=_identity("INTRADAY-WO13-MEASUREMENT-", values),
        measurement_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-MEASUREMENT-", values
        ),
        **values,
    )


def _target_state(
    direction: SemanticDirection,
    entry: Decimal,
    target: Decimal,
) -> tuple[Wo13ForwardTargetState, Decimal | None]:
    difference = (
        target - entry
        if direction is SemanticDirection.LONG
        else entry - target
    )
    if difference > 0:
        return Wo13ForwardTargetState.FORWARD, difference
    if difference == 0:
        return Wo13ForwardTargetState.AT_ENTRY, None
    return Wo13ForwardTargetState.BEHIND_ENTRY, None


def _derive_field_availability(
    facts: Sequence[Wo13StructuralPriceFact],
    expected_source_identities: Sequence[str],
) -> Wo13FieldAvailability:
    if len(facts) > 1:
        return Wo13FieldAvailability.AMBIGUOUS
    if len(facts) == 1:
        source_ids = {item.source_evidence_identity for item in facts}
        if set(expected_source_identities) != source_ids:
            return Wo13FieldAvailability.INCOMPLETE
        return Wo13FieldAvailability.AVAILABLE
    return (
        Wo13FieldAvailability.INCOMPLETE
        if expected_source_identities
        else Wo13FieldAvailability.UNAVAILABLE
    )


def _facts_share_context(facts: Sequence[Wo13StructuralPriceFact]) -> bool:
    if not facts:
        return True
    first = facts[0]
    return all(_same_context(first, item) for item in facts[1:])


def _same_context(
    left: Wo13StructuralPriceFact,
    right: Wo13StructuralPriceFact,
) -> bool:
    return (
        left.canonical_subject_identity == right.canonical_subject_identity
        and left.market_family is right.market_family
        and left.analysis_boundary == right.analysis_boundary
        and left.instrument_identity == right.instrument_identity
        and left.actual_contract_identity == right.actual_contract_identity
        and left.roll_lineage_identity == right.roll_lineage_identity
    )


def _market_family(identity: object) -> IntradayMarketFamily | None:
    if type(identity) is not str:
        return None
    if identity.startswith("NSE-EQ-"):
        return IntradayMarketFamily.NSE_EQUITY
    if identity.startswith("NSE-INDEX-"):
        return IntradayMarketFamily.NSE_INDEX
    if identity.startswith("MCX-SUBJECT-"):
        return IntradayMarketFamily.MCX
    return None


def _price(value: object) -> Decimal:
    if isinstance(value, bool):
        raise Wo13GeometryRejected(Wo13GeometryFailure.PRICE_VALUE_INVALID)
    try:
        retained = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise Wo13GeometryRejected(
            Wo13GeometryFailure.PRICE_VALUE_INVALID
        ) from exc
    if not retained.is_finite():
        raise Wo13GeometryRejected(Wo13GeometryFailure.NON_FINITE_VALUE)
    if retained <= 0:
        raise Wo13GeometryRejected(Wo13GeometryFailure.NON_POSITIVE_PRICE)
    return retained


def _unique_pairs(
    pairs: Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    retained: dict[str, str] = {}
    for identity, integrity in pairs:
        if not _texts((identity, integrity)):
            raise Wo13GeometryRejected(Wo13GeometryFailure.SOURCE_INTEGRITY_INVALID)
        if identity in retained and retained[identity] != integrity:
            raise Wo13GeometryRejected(Wo13GeometryFailure.SOURCE_INTEGRITY_INVALID)
        retained[identity] = integrity
    return tuple(sorted(retained.items()))


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
    name
    for name in globals()
    if name.startswith("WO13_")
    or name.startswith("Wo13")
    or name.startswith("calculate_wo13")
    or name.startswith("create_wo13")
    or name.startswith("resolve_wo13")
]
