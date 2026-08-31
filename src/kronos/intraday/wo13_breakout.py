"""Exact 15M Range-Breakout geometry for Intraday WO-13 Slice 4.

This module consumes one immutable WO-12 -> WO-13 handoff, one original
governed 15M range, and one exact completed qualification candle.  It derives
the range Entry, qualification-candle Stop, range-boundary invalidation and
one-range-width setup-native Target.  Canonical target constraint selection,
persistence, runtime, Risk, 5M timing, Sponsor, execution and broker authority
remain deliberately absent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo13 import (
    WO13_POLICY_CHECKSUM,
    WO13_POLICY_IDENTITY,
    Wo13FieldAvailability,
    Wo13GeometryAvailability,
    Wo13GeometryField,
)
from kronos.intraday.wo13_geometry import (
    Wo13ForwardTargetState,
    Wo13GeometryCalculation,
    Wo13PriceAuthority,
    Wo13RangeWidthMeasurement,
    Wo13StructuralPriceFact,
    Wo13StructuralPriceField,
    Wo13StructuralRole,
    Wo13TargetCandidate,
    Wo13TargetCandidateKind,
    Wo13ThesisInvalidationEvent,
    calculate_wo13_geometry,
    calculate_wo13_range_width,
    create_wo13_structural_price_fact,
    create_wo13_target_candidate,
    create_wo13_thesis_invalidation_event,
    resolve_wo13_structural_price_field,
)
from kronos.intraday.wo13_handoff import (
    WO13_CONTRACT_VERSION,
    WO13_POLICY_VERSION,
    Wo13SetupFamily,
    Wo13Step31Handoff,
)


WO13_BREAKOUT_FACT_REFERENCE_IDENTITY = (
    "KRONOS-INTRADAY-WO13-BREAKOUT-FACT-REFERENCE-V1"
)
WO13_BREAKOUT_FACT_RESOLUTION_IDENTITY = (
    "KRONOS-INTRADAY-WO13-BREAKOUT-FACT-RESOLUTION-V1"
)
WO13_BREAKOUT_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-WO13-RANGE-BREAKOUT-GEOMETRY-EVIDENCE-V1"
)
WO13_BREAKOUT_ENTRY_CONDITION_IDENTITY = (
    "KRONOS-INTRADAY-WO13-RANGE-BREAKOUT-ENTRY-CONDITION-V1"
)
WO13_BREAKOUT_GEOMETRY_IDENTITY = (
    "KRONOS-INTRADAY-WO13-RANGE-BREAKOUT-GEOMETRY-V1"
)


class Wo13BreakoutFailure(StrEnum):
    SETUP_FAMILY_UNSUPPORTED = "SETUP_FAMILY_UNSUPPORTED"
    EVIDENCE_CONTRACT_INVALID = "EVIDENCE_CONTRACT_INVALID"
    FACT_REFERENCE_INVALID = "FACT_REFERENCE_INVALID"
    FACT_BINDING_MISMATCH = "FACT_BINDING_MISMATCH"
    FACT_ROLE_MISMATCH = "FACT_ROLE_MISMATCH"
    FACT_TIMEFRAME_MISMATCH = "FACT_TIMEFRAME_MISMATCH"
    FACT_CONTEXT_MISMATCH = "FACT_CONTEXT_MISMATCH"
    FACT_CYCLE_MISMATCH = "FACT_CYCLE_MISMATCH"
    FACT_SESSION_MISMATCH = "FACT_SESSION_MISMATCH"
    ORIGINAL_RANGE_IDENTITY_MISMATCH = "ORIGINAL_RANGE_IDENTITY_MISMATCH"
    BREAKOUT_DIRECTION_MISMATCH = "BREAKOUT_DIRECTION_MISMATCH"
    RANGE_INVALID = "RANGE_INVALID"
    GEOMETRY_CONTRACT_INVALID = "GEOMETRY_CONTRACT_INVALID"


class Wo13BreakoutRejected(ValueError):
    """Sanitized Range-Breakout trust-boundary failure."""

    def __init__(self, failure: Wo13BreakoutFailure) -> None:
        if type(failure) is not Wo13BreakoutFailure:
            raise ValueError("WO13_BREAKOUT_FAILURE_INVALID")
        self.failure = failure
        super().__init__(failure.value)


class Wo13BreakoutEntryConditionCode(StrEnum):
    DIRECTIONAL_BREAKOUT_ABOVE_ORIGINAL_RANGE_HIGH = (
        "DIRECTIONAL_BREAKOUT_ABOVE_ORIGINAL_RANGE_HIGH"
    )
    DIRECTIONAL_BREAKOUT_BELOW_ORIGINAL_RANGE_LOW = (
        "DIRECTIONAL_BREAKOUT_BELOW_ORIGINAL_RANGE_LOW"
    )


class Wo13BreakoutInvalidationCode(StrEnum):
    COMPLETED_GOVERNED_15M_CLOSE_BACK_AT_OR_INSIDE_LONG_RANGE = (
        "COMPLETED_GOVERNED_15M_CLOSE_BACK_AT_OR_INSIDE_LONG_RANGE"
    )
    COMPLETED_GOVERNED_15M_CLOSE_BACK_AT_OR_INSIDE_SHORT_RANGE = (
        "COMPLETED_GOVERNED_15M_CLOSE_BACK_AT_OR_INSIDE_SHORT_RANGE"
    )


@dataclass(frozen=True, slots=True)
class Wo13BreakoutFactReference:
    reference_identity: str
    reference_integrity: str
    fact_identity: str
    fact_integrity: str
    source_evidence_identity: str
    source_evidence_integrity: str
    structural_role: Wo13StructuralRole
    structure_identity: str
    breakout_cycle_identity: str
    breakout_direction: SemanticDirection
    schema_identity: str = WO13_BREAKOUT_FACT_REFERENCE_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "reference_identity", "reference_integrity")
        if (
            not _texts((
                self.fact_identity,
                self.fact_integrity,
                self.source_evidence_identity,
                self.source_evidence_integrity,
                self.structure_identity,
                self.breakout_cycle_identity,
            ))
            or type(self.structural_role) is not Wo13StructuralRole
            or self.breakout_direction
            not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or self.schema_identity != WO13_BREAKOUT_FACT_REFERENCE_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.reference_identity
            != _identity("INTRADAY-WO13-BREAKOUT-FACT-REFERENCE-", values)
            or self.reference_integrity
            != _identity(
                "INTEGRITY-INTRADAY-WO13-BREAKOUT-FACT-REFERENCE-", values
            )
        ):
            raise Wo13BreakoutRejected(
                Wo13BreakoutFailure.FACT_REFERENCE_INVALID
            )


def create_wo13_breakout_fact_reference(
    *,
    fact: Wo13StructuralPriceFact,
    breakout_cycle_identity: str,
    breakout_direction: SemanticDirection,
) -> Wo13BreakoutFactReference:
    if (
        type(fact) is not Wo13StructuralPriceFact
        or not _text(breakout_cycle_identity)
        or breakout_direction
        not in {SemanticDirection.LONG, SemanticDirection.SHORT}
    ):
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_REFERENCE_INVALID)
    values = {
        "fact_identity": fact.fact_identity,
        "fact_integrity": fact.fact_integrity,
        "source_evidence_identity": fact.source_evidence_identity,
        "source_evidence_integrity": fact.source_evidence_integrity,
        "structural_role": fact.structural_role,
        "structure_identity": fact.structure_identity,
        "breakout_cycle_identity": breakout_cycle_identity,
        "breakout_direction": breakout_direction,
        "schema_identity": WO13_BREAKOUT_FACT_REFERENCE_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13BreakoutFactReference(
        reference_identity=_identity(
            "INTRADAY-WO13-BREAKOUT-FACT-REFERENCE-", values
        ),
        reference_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-BREAKOUT-FACT-REFERENCE-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13BreakoutFactResolution:
    resolution_identity: str
    resolution_integrity: str
    structural_role: Wo13StructuralRole
    references: tuple[Wo13BreakoutFactReference, ...]
    facts: tuple[Wo13StructuralPriceFact, ...]
    availability: Wo13FieldAvailability
    schema_identity: str = WO13_BREAKOUT_FACT_RESOLUTION_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "resolution_identity", "resolution_integrity")
        expected = _availability(self.references, self.facts)
        if (
            type(self.structural_role) is not Wo13StructuralRole
            or any(item.structural_role is not self.structural_role for item in self.references)
            or any(item.structural_role is not self.structural_role for item in self.facts)
            or self.references != _ordered_references(self.references)
            or self.facts != _ordered_facts(self.facts)
            or self.availability is not expected
            or self.schema_identity != WO13_BREAKOUT_FACT_RESOLUTION_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.resolution_identity
            != _identity("INTRADAY-WO13-BREAKOUT-FACT-RESOLUTION-", values)
            or self.resolution_integrity
            != _identity(
                "INTEGRITY-INTRADAY-WO13-BREAKOUT-FACT-RESOLUTION-", values
            )
        ):
            raise Wo13BreakoutRejected(
                Wo13BreakoutFailure.GEOMETRY_CONTRACT_INVALID
            )

    @property
    def selected_fact(self) -> Wo13StructuralPriceFact | None:
        return self.facts[0] if self.availability is Wo13FieldAvailability.AVAILABLE else None


@dataclass(frozen=True, slots=True)
class Wo13BreakoutGeometryEvidence:
    evidence_identity: str
    evidence_integrity: str
    handoff: Wo13Step31Handoff
    breakout_direction: SemanticDirection
    market_session_identity: str
    original_range_identity: str
    range_high_references: tuple[Wo13BreakoutFactReference, ...]
    range_high_facts: tuple[Wo13StructuralPriceFact, ...]
    range_low_references: tuple[Wo13BreakoutFactReference, ...]
    range_low_facts: tuple[Wo13StructuralPriceFact, ...]
    qualification_references: tuple[Wo13BreakoutFactReference, ...]
    qualification_candles: tuple[Wo13StructuralPriceFact, ...]
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    policy_identity: str = WO13_POLICY_IDENTITY
    policy_version: str = WO13_POLICY_VERSION
    policy_checksum: str = WO13_POLICY_CHECKSUM
    schema_identity: str = WO13_BREAKOUT_EVIDENCE_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    provider_acquisition_authority: bool = False
    latest_resolution_authority: bool = False
    risk_authority: bool = False
    entry_timing_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        _validate_evidence(self)
        values = _without(self, "evidence_identity", "evidence_integrity")
        if (
            self.policy_identity != WO13_POLICY_IDENTITY
            or self.policy_version != WO13_POLICY_VERSION
            or self.policy_checksum != WO13_POLICY_CHECKSUM
            or self.schema_identity != WO13_BREAKOUT_EVIDENCE_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or any((
                self.provider_acquisition_authority,
                self.latest_resolution_authority,
                self.risk_authority,
                self.entry_timing_authority,
                self.execution_authority,
                self.broker_authority,
            ))
            or self.evidence_identity
            != _identity("INTRADAY-WO13-BREAKOUT-EVIDENCE-", values)
            or self.evidence_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-BREAKOUT-EVIDENCE-", values)
        ):
            raise Wo13BreakoutRejected(
                Wo13BreakoutFailure.EVIDENCE_CONTRACT_INVALID
            )


def create_wo13_breakout_geometry_evidence(
    *,
    handoff: Wo13Step31Handoff,
    breakout_direction: SemanticDirection,
    market_session_identity: str,
    original_range_identity: str,
    range_high_references: Sequence[Wo13BreakoutFactReference] = (),
    range_high_facts: Sequence[Wo13StructuralPriceFact] = (),
    range_low_references: Sequence[Wo13BreakoutFactReference] = (),
    range_low_facts: Sequence[Wo13StructuralPriceFact] = (),
    qualification_references: Sequence[Wo13BreakoutFactReference] = (),
    qualification_candles: Sequence[Wo13StructuralPriceFact] = (),
) -> Wo13BreakoutGeometryEvidence:
    if type(handoff) is not Wo13Step31Handoff:
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.EVIDENCE_CONTRACT_INVALID)
    if handoff.setup_family is not Wo13SetupFamily.INTRADAY_RANGE_BREAKOUT:
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.SETUP_FAMILY_UNSUPPORTED)
    if breakout_direction is not handoff.inherited_direction:
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.BREAKOUT_DIRECTION_MISMATCH)
    reference_groups = tuple(
        _ordered_references(items)
        for items in (
            range_high_references,
            range_low_references,
            qualification_references,
        )
    )
    fact_groups = tuple(
        _ordered_facts(items)
        for items in (range_high_facts, range_low_facts, qualification_candles)
    )
    pairs = [
        (handoff.handoff_identity, handoff.handoff_integrity),
        *(
            (item.reference_identity, item.reference_integrity)
            for group in reference_groups
            for item in group
        ),
        *(
            (item.fact_identity, item.fact_integrity)
            for group in fact_groups
            for item in group
        ),
    ]
    sources = _unique_pairs(pairs)
    values = {
        "handoff": handoff,
        "breakout_direction": breakout_direction,
        "market_session_identity": market_session_identity,
        "original_range_identity": original_range_identity,
        "range_high_references": reference_groups[0],
        "range_high_facts": fact_groups[0],
        "range_low_references": reference_groups[1],
        "range_low_facts": fact_groups[1],
        "qualification_references": reference_groups[2],
        "qualification_candles": fact_groups[2],
        "source_identities": tuple(item[0] for item in sources),
        "source_integrities": tuple(item[1] for item in sources),
        "policy_identity": WO13_POLICY_IDENTITY,
        "policy_version": WO13_POLICY_VERSION,
        "policy_checksum": WO13_POLICY_CHECKSUM,
        "schema_identity": WO13_BREAKOUT_EVIDENCE_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "provider_acquisition_authority": False,
        "latest_resolution_authority": False,
        "risk_authority": False,
        "entry_timing_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo13BreakoutGeometryEvidence(
        evidence_identity=_identity("INTRADAY-WO13-BREAKOUT-EVIDENCE-", values),
        evidence_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-BREAKOUT-EVIDENCE-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13BreakoutEntryCondition:
    condition_identity: str
    condition_integrity: str
    entry_reference_identity: str
    entry_reference_integrity: str
    direction: SemanticDirection
    condition_code: Wo13BreakoutEntryConditionCode
    schema_identity: str = WO13_BREAKOUT_ENTRY_CONDITION_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    trigger_evaluation_performed: bool = False
    retest_required: bool = False
    entry_timing_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "condition_identity", "condition_integrity")
        expected = (
            Wo13BreakoutEntryConditionCode.DIRECTIONAL_BREAKOUT_ABOVE_ORIGINAL_RANGE_HIGH
            if self.direction is SemanticDirection.LONG
            else Wo13BreakoutEntryConditionCode.DIRECTIONAL_BREAKOUT_BELOW_ORIGINAL_RANGE_LOW
        )
        if (
            not _texts((self.entry_reference_identity, self.entry_reference_integrity))
            or self.condition_code is not expected
            or self.schema_identity != WO13_BREAKOUT_ENTRY_CONDITION_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.trigger_evaluation_performed
            or self.retest_required
            or self.entry_timing_authority
            or self.execution_authority
            or self.condition_identity
            != _identity("INTRADAY-WO13-BREAKOUT-ENTRY-CONDITION-", values)
            or self.condition_integrity
            != _identity(
                "INTEGRITY-INTRADAY-WO13-BREAKOUT-ENTRY-CONDITION-", values
            )
        ):
            raise Wo13BreakoutRejected(
                Wo13BreakoutFailure.GEOMETRY_CONTRACT_INVALID
            )


@dataclass(frozen=True, slots=True)
class Wo13BreakoutGeometry:
    geometry_identity: str
    geometry_integrity: str
    evidence: Wo13BreakoutGeometryEvidence
    range_high: Wo13BreakoutFactResolution
    range_low: Wo13BreakoutFactResolution
    qualification_candle: Wo13BreakoutFactResolution
    range_width: Wo13RangeWidthMeasurement | None
    range_failure: Wo13BreakoutFailure | None
    entry_reference: Wo13StructuralPriceField
    entry_condition: Wo13BreakoutEntryCondition | None
    stop: Wo13StructuralPriceField
    thesis_invalidation_reference: Wo13StructuralPriceField
    thesis_invalidation_event: Wo13ThesisInvalidationEvent | None
    setup_native_target: Wo13StructuralPriceField
    native_target_candidate: Wo13TargetCandidate | None
    canonical_target: Wo13StructuralPriceField
    calculation: Wo13GeometryCalculation
    target_constraint_selection_pending: bool
    schema_identity: str = WO13_BREAKOUT_GEOMETRY_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    pullback_authority: bool = False
    target_constraint_selection_authority: bool = False
    persistence_authority: bool = False
    runtime_authority: bool = False
    risk_authority: bool = False
    entry_timing_authority: bool = False
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        expected = _assemble(self.evidence)
        values = _without(self, "geometry_identity", "geometry_integrity")
        if (
            type(self.evidence) is not Wo13BreakoutGeometryEvidence
            or (
                self.range_high,
                self.range_low,
                self.qualification_candle,
                self.range_width,
                self.range_failure,
                self.entry_reference,
                self.entry_condition,
                self.stop,
                self.thesis_invalidation_reference,
                self.thesis_invalidation_event,
                self.setup_native_target,
                self.native_target_candidate,
                self.canonical_target,
                self.calculation,
            )
            != expected
            or not self.target_constraint_selection_pending
            or self.calculation.geometry_availability
            is Wo13GeometryAvailability.GEOMETRY_COMPLETE
            or self.schema_identity != WO13_BREAKOUT_GEOMETRY_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or any((
                self.pullback_authority,
                self.target_constraint_selection_authority,
                self.persistence_authority,
                self.runtime_authority,
                self.risk_authority,
                self.entry_timing_authority,
                self.sponsor_decision_authority,
                self.execution_authority,
                self.broker_authority,
            ))
            or self.geometry_identity
            != _identity("INTRADAY-WO13-BREAKOUT-GEOMETRY-", values)
            or self.geometry_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-BREAKOUT-GEOMETRY-", values)
        ):
            raise Wo13BreakoutRejected(
                Wo13BreakoutFailure.GEOMETRY_CONTRACT_INVALID
            )

    @property
    def geometry_availability(self) -> Wo13GeometryAvailability:
        return self.calculation.geometry_availability

    @property
    def risk_distance(self):  # type: ignore[no-untyped-def]
        return self.calculation.risk_distance

    @property
    def reward_distance(self):  # type: ignore[no-untyped-def]
        return self.calculation.reward_distance

    @property
    def model_rr(self):  # type: ignore[no-untyped-def]
        return self.calculation.model_rr


def construct_wo13_breakout_geometry(
    evidence: Wo13BreakoutGeometryEvidence,
) -> Wo13BreakoutGeometry:
    if type(evidence) is not Wo13BreakoutGeometryEvidence:
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.EVIDENCE_CONTRACT_INVALID)
    assembled = _assemble(evidence)
    values = {
        "evidence": evidence,
        "range_high": assembled[0],
        "range_low": assembled[1],
        "qualification_candle": assembled[2],
        "range_width": assembled[3],
        "range_failure": assembled[4],
        "entry_reference": assembled[5],
        "entry_condition": assembled[6],
        "stop": assembled[7],
        "thesis_invalidation_reference": assembled[8],
        "thesis_invalidation_event": assembled[9],
        "setup_native_target": assembled[10],
        "native_target_candidate": assembled[11],
        "canonical_target": assembled[12],
        "calculation": assembled[13],
        "target_constraint_selection_pending": True,
        "schema_identity": WO13_BREAKOUT_GEOMETRY_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "pullback_authority": False,
        "target_constraint_selection_authority": False,
        "persistence_authority": False,
        "runtime_authority": False,
        "risk_authority": False,
        "entry_timing_authority": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo13BreakoutGeometry(
        geometry_identity=_identity("INTRADAY-WO13-BREAKOUT-GEOMETRY-", values),
        geometry_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-BREAKOUT-GEOMETRY-", values
        ),
        **values,
    )


def _assemble(evidence: Wo13BreakoutGeometryEvidence):  # type: ignore[no-untyped-def]
    direction = evidence.breakout_direction
    range_high = _resolution(
        Wo13StructuralRole.RANGE_HIGH,
        evidence.range_high_references,
        evidence.range_high_facts,
    )
    range_low = _resolution(
        Wo13StructuralRole.RANGE_LOW,
        evidence.range_low_references,
        evidence.range_low_facts,
    )
    qualification_role = (
        Wo13StructuralRole.QUALIFICATION_CANDLE_LOW
        if direction is SemanticDirection.LONG
        else Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH
    )
    qualification = _resolution(
        qualification_role,
        evidence.qualification_references,
        evidence.qualification_candles,
    )
    high = range_high.selected_fact
    low = range_low.selected_fact
    candle = qualification.selected_fact
    width: Wo13RangeWidthMeasurement | None = None
    range_failure: Wo13BreakoutFailure | None = None
    if high is not None and low is not None:
        if high.price <= low.price:
            range_failure = Wo13BreakoutFailure.RANGE_INVALID
        else:
            width = calculate_wo13_range_width(high, low)
    boundary = high if direction is SemanticDirection.LONG else low
    entry = _derived_field(
        Wo13GeometryField.ENTRY_REFERENCE,
        boundary,
        Wo13StructuralRole.ENTRY_REFERENCE_SOURCE,
        _boundary_sources(evidence, direction),
        enabled=width is not None,
    )
    invalidation = _derived_field(
        Wo13GeometryField.THESIS_INVALIDATION_REFERENCE,
        boundary,
        Wo13StructuralRole.THESIS_INVALIDATION_REFERENCE,
        _boundary_sources(evidence, direction),
        enabled=width is not None,
    )
    stop = _derived_field(
        Wo13GeometryField.STOP,
        candle,
        Wo13StructuralRole.STOP_REFERENCE_SOURCE,
        _source_pairs(evidence.qualification_references),
        enabled=True,
    )
    entry_fact = entry.selected_fact
    invalidation_fact = invalidation.selected_fact
    entry_condition = (
        _entry_condition(direction, entry_fact) if entry_fact is not None else None
    )
    invalidation_event = (
        create_wo13_thesis_invalidation_event(
            reference=invalidation_fact,
            event_code=(
                Wo13BreakoutInvalidationCode.COMPLETED_GOVERNED_15M_CLOSE_BACK_AT_OR_INSIDE_LONG_RANGE.value
                if direction is SemanticDirection.LONG
                else Wo13BreakoutInvalidationCode.COMPLETED_GOVERNED_15M_CLOSE_BACK_AT_OR_INSIDE_SHORT_RANGE.value
            ),
            source_evidence_identity=invalidation_fact.source_evidence_identity,
            source_evidence_integrity=invalidation_fact.source_evidence_integrity,
        )
        if invalidation_fact is not None
        else None
    )
    native_fact = (
        _measured_target_fact(evidence, width, high, low)
        if width is not None and high is not None and low is not None
        else None
    )
    native_target = resolve_wo13_structural_price_field(
        Wo13GeometryField.SETUP_NATIVE_TARGET,
        facts=() if native_fact is None else (native_fact,),
        expected_sources=(
            ()
            if native_fact is None
            else ((native_fact.source_evidence_identity, native_fact.source_evidence_integrity),)
        ),
    )
    candidate = (
        create_wo13_target_candidate(
            entry_reference=entry_fact,
            candidate=native_fact,
            direction=direction,
            kind=Wo13TargetCandidateKind.SETUP_NATIVE_OBJECTIVE,
        )
        if entry_fact is not None and native_fact is not None
        else None
    )
    if candidate is not None and candidate.forward_state is not Wo13ForwardTargetState.FORWARD:
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.RANGE_INVALID)
    canonical = resolve_wo13_structural_price_field(
        Wo13GeometryField.CANONICAL_TARGET
    )
    calculation = calculate_wo13_geometry(
        direction=direction,
        entry_reference=entry,
        stop=stop,
        thesis_invalidation_reference=invalidation,
        thesis_invalidation_event=invalidation_event,
        target=canonical,
    )
    return (
        range_high,
        range_low,
        qualification,
        width,
        range_failure,
        entry,
        entry_condition,
        stop,
        invalidation,
        invalidation_event,
        native_target,
        candidate,
        canonical,
        calculation,
    )


def _resolution(
    role: Wo13StructuralRole,
    references: Sequence[Wo13BreakoutFactReference],
    facts: Sequence[Wo13StructuralPriceFact],
) -> Wo13BreakoutFactResolution:
    references = _ordered_references(references)
    facts = _ordered_facts(facts)
    values = {
        "structural_role": role,
        "references": references,
        "facts": facts,
        "availability": _availability(references, facts),
        "schema_identity": WO13_BREAKOUT_FACT_RESOLUTION_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13BreakoutFactResolution(
        resolution_identity=_identity(
            "INTRADAY-WO13-BREAKOUT-FACT-RESOLUTION-", values
        ),
        resolution_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-BREAKOUT-FACT-RESOLUTION-", values
        ),
        **values,
    )


def _availability(
    references: Sequence[Wo13BreakoutFactReference],
    facts: Sequence[Wo13StructuralPriceFact],
) -> Wo13FieldAvailability:
    if len(facts) > 1 or len(references) > 1:
        return Wo13FieldAvailability.AMBIGUOUS
    if len(facts) == 1 and len(references) == 1:
        reference = references[0]
        fact = facts[0]
        return (
            Wo13FieldAvailability.AVAILABLE
            if reference.fact_identity == fact.fact_identity
            and reference.fact_integrity == fact.fact_integrity
            else Wo13FieldAvailability.INCOMPLETE
        )
    return (
        Wo13FieldAvailability.INCOMPLETE
        if references or facts
        else Wo13FieldAvailability.UNAVAILABLE
    )


def _derived_field(
    field: Wo13GeometryField,
    source: Wo13StructuralPriceFact | None,
    role: Wo13StructuralRole,
    expected_sources: Sequence[tuple[str, str]],
    *,
    enabled: bool,
) -> Wo13StructuralPriceField:
    fact = _derived_fact(source, role) if source is not None and enabled else None
    return resolve_wo13_structural_price_field(
        field,
        facts=() if fact is None else (fact,),
        expected_sources=expected_sources,
    )


def _derived_fact(
    source: Wo13StructuralPriceFact,
    role: Wo13StructuralRole,
) -> Wo13StructuralPriceFact:
    return create_wo13_structural_price_fact(
        canonical_subject_identity=source.canonical_subject_identity,
        market_family=source.market_family,
        timeframe=source.timeframe,
        price=source.price,
        structural_role=role,
        price_authority=source.price_authority,
        structure_identity=source.structure_identity,
        source_evidence_identity=source.source_evidence_identity,
        source_evidence_integrity=source.source_evidence_integrity,
        analysis_boundary=source.analysis_boundary,
        instrument_identity=source.instrument_identity,
        actual_contract_identity=source.actual_contract_identity,
        roll_lineage_identity=source.roll_lineage_identity,
        market_session_identity=source.market_session_identity,
    )


def _measured_target_fact(
    evidence: Wo13BreakoutGeometryEvidence,
    width: Wo13RangeWidthMeasurement,
    high: Wo13StructuralPriceFact,
    low: Wo13StructuralPriceFact,
) -> Wo13StructuralPriceFact:
    price = (
        high.price + width.range_width
        if evidence.breakout_direction is SemanticDirection.LONG
        else low.price - width.range_width
    )
    if price <= 0:
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.RANGE_INVALID)
    return create_wo13_structural_price_fact(
        canonical_subject_identity=high.canonical_subject_identity,
        market_family=high.market_family,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        price=price,
        structural_role=Wo13StructuralRole.SETUP_NATIVE_TARGET,
        price_authority=high.price_authority,
        structure_identity=evidence.original_range_identity,
        source_evidence_identity=width.measurement_identity,
        source_evidence_integrity=width.measurement_integrity,
        analysis_boundary=high.analysis_boundary,
        instrument_identity=high.instrument_identity,
        actual_contract_identity=high.actual_contract_identity,
        roll_lineage_identity=high.roll_lineage_identity,
        market_session_identity=evidence.market_session_identity,
    )


def _entry_condition(
    direction: SemanticDirection,
    entry: Wo13StructuralPriceFact,
) -> Wo13BreakoutEntryCondition:
    code = (
        Wo13BreakoutEntryConditionCode.DIRECTIONAL_BREAKOUT_ABOVE_ORIGINAL_RANGE_HIGH
        if direction is SemanticDirection.LONG
        else Wo13BreakoutEntryConditionCode.DIRECTIONAL_BREAKOUT_BELOW_ORIGINAL_RANGE_LOW
    )
    values = {
        "entry_reference_identity": entry.fact_identity,
        "entry_reference_integrity": entry.fact_integrity,
        "direction": direction,
        "condition_code": code,
        "schema_identity": WO13_BREAKOUT_ENTRY_CONDITION_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "trigger_evaluation_performed": False,
        "retest_required": False,
        "entry_timing_authority": False,
        "execution_authority": False,
    }
    return Wo13BreakoutEntryCondition(
        condition_identity=_identity(
            "INTRADAY-WO13-BREAKOUT-ENTRY-CONDITION-", values
        ),
        condition_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-BREAKOUT-ENTRY-CONDITION-", values
        ),
        **values,
    )


def _validate_evidence(evidence: Wo13BreakoutGeometryEvidence) -> None:
    handoff = evidence.handoff
    if type(handoff) is not Wo13Step31Handoff:
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.EVIDENCE_CONTRACT_INVALID)
    if handoff.setup_family is not Wo13SetupFamily.INTRADAY_RANGE_BREAKOUT:
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.SETUP_FAMILY_UNSUPPORTED)
    if evidence.breakout_direction is not handoff.inherited_direction:
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.BREAKOUT_DIRECTION_MISMATCH)
    if not _texts((evidence.market_session_identity, evidence.original_range_identity)):
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.EVIDENCE_CONTRACT_INVALID)
    qualification_role = (
        Wo13StructuralRole.QUALIFICATION_CANDLE_LOW
        if evidence.breakout_direction is SemanticDirection.LONG
        else Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH
    )
    groups = (
        (evidence.range_high_references, evidence.range_high_facts, Wo13StructuralRole.RANGE_HIGH),
        (evidence.range_low_references, evidence.range_low_facts, Wo13StructuralRole.RANGE_LOW),
        (evidence.qualification_references, evidence.qualification_candles, qualification_role),
    )
    for references, facts, role in groups:
        _validate_component(evidence, references, facts, role)
    sources = _unique_pairs([
        (handoff.handoff_identity, handoff.handoff_integrity),
        *((item.reference_identity, item.reference_integrity) for refs, _, _ in groups for item in refs),
        *((item.fact_identity, item.fact_integrity) for _, facts, _ in groups for item in facts),
    ])
    if (
        evidence.source_identities != tuple(item[0] for item in sources)
        or evidence.source_integrities != tuple(item[1] for item in sources)
    ):
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.EVIDENCE_CONTRACT_INVALID)


def _validate_component(
    evidence: Wo13BreakoutGeometryEvidence,
    references: Sequence[Wo13BreakoutFactReference],
    facts: Sequence[Wo13StructuralPriceFact],
    role: Wo13StructuralRole,
) -> None:
    if tuple(references) != _ordered_references(references):
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_REFERENCE_INVALID)
    if tuple(facts) != _ordered_facts(facts):
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_BINDING_MISMATCH)
    if any(item.structural_role is not role for item in references):
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_ROLE_MISMATCH)
    by_fact = {item.fact_identity: item for item in references}
    if len(by_fact) != len(references):
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_REFERENCE_INVALID)
    for reference in references:
        if reference.breakout_cycle_identity != evidence.handoff.setup_evidence_identity:
            raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_CYCLE_MISMATCH)
        if reference.breakout_direction is not evidence.breakout_direction:
            raise Wo13BreakoutRejected(Wo13BreakoutFailure.BREAKOUT_DIRECTION_MISMATCH)
        expected_structure = (
            evidence.original_range_identity
            if role in {Wo13StructuralRole.RANGE_HIGH, Wo13StructuralRole.RANGE_LOW}
            else evidence.handoff.setup_evidence_identity
        )
        if reference.structure_identity != expected_structure:
            raise Wo13BreakoutRejected(
                Wo13BreakoutFailure.ORIGINAL_RANGE_IDENTITY_MISMATCH
                if role in {Wo13StructuralRole.RANGE_HIGH, Wo13StructuralRole.RANGE_LOW}
                else Wo13BreakoutFailure.FACT_CYCLE_MISMATCH
            )
    for fact in facts:
        if type(fact) is not Wo13StructuralPriceFact:
            raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_BINDING_MISMATCH)
        if fact.structural_role is not role:
            raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_ROLE_MISMATCH)
        if fact.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES:
            raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_TIMEFRAME_MISMATCH)
        if fact.market_session_identity != evidence.market_session_identity:
            raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_SESSION_MISMATCH)
        if not _matches_handoff(fact, evidence.handoff):
            raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_CONTEXT_MISMATCH)
        expected_structure = (
            evidence.original_range_identity
            if role in {Wo13StructuralRole.RANGE_HIGH, Wo13StructuralRole.RANGE_LOW}
            else evidence.handoff.setup_evidence_identity
        )
        if fact.structure_identity != expected_structure:
            raise Wo13BreakoutRejected(
                Wo13BreakoutFailure.ORIGINAL_RANGE_IDENTITY_MISMATCH
                if role in {Wo13StructuralRole.RANGE_HIGH, Wo13StructuralRole.RANGE_LOW}
                else Wo13BreakoutFailure.FACT_CYCLE_MISMATCH
            )
        reference = by_fact.get(fact.fact_identity)
        if reference is None or (
            reference.fact_integrity != fact.fact_integrity
            or reference.source_evidence_identity != fact.source_evidence_identity
            or reference.source_evidence_integrity != fact.source_evidence_integrity
        ):
            raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_BINDING_MISMATCH)


def _matches_handoff(
    fact: Wo13StructuralPriceFact,
    handoff: Wo13Step31Handoff,
) -> bool:
    return (
        fact.canonical_subject_identity == handoff.canonical_subject_identity
        and fact.market_family is handoff.market_family
        and fact.analysis_boundary == handoff.analysis_boundary
        and fact.instrument_identity == handoff.instrument_identity
        and fact.actual_contract_identity == handoff.actual_contract_identity
        and fact.roll_lineage_identity == handoff.roll_lineage_identity
        and fact.price_authority is _authority(handoff)
    )


def _authority(handoff: Wo13Step31Handoff) -> Wo13PriceAuthority:
    return {
        "NSE_EQUITY": Wo13PriceAuthority.NSE_EQUITY_UNDERLYING,
        "NSE_INDEX": Wo13PriceAuthority.NSE_INDEX_UNDERLYING,
        "MCX": Wo13PriceAuthority.MCX_ACTIVE_CONTRACT,
    }[handoff.market_family.value]


def _boundary_sources(
    evidence: Wo13BreakoutGeometryEvidence,
    direction: SemanticDirection,
) -> tuple[tuple[str, str], ...]:
    return _source_pairs(
        evidence.range_high_references
        if direction is SemanticDirection.LONG
        else evidence.range_low_references
    )


def _source_pairs(
    references: Sequence[Wo13BreakoutFactReference],
) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(
        ((item.source_evidence_identity, item.source_evidence_integrity) for item in references),
        key=lambda item: item[0],
    ))


def _ordered_references(
    values: Sequence[Wo13BreakoutFactReference],
) -> tuple[Wo13BreakoutFactReference, ...]:
    if any(type(item) is not Wo13BreakoutFactReference for item in values):
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_REFERENCE_INVALID)
    return tuple(sorted(values, key=lambda item: item.reference_identity))


def _ordered_facts(
    values: Sequence[Wo13StructuralPriceFact],
) -> tuple[Wo13StructuralPriceFact, ...]:
    if any(type(item) is not Wo13StructuralPriceFact for item in values):
        raise Wo13BreakoutRejected(Wo13BreakoutFailure.FACT_BINDING_MISMATCH)
    return tuple(sorted(values, key=lambda item: item.fact_identity))


def _unique_pairs(
    pairs: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    retained: dict[str, str] = {}
    for identity, integrity in pairs:
        if not _texts((identity, integrity)):
            raise Wo13BreakoutRejected(Wo13BreakoutFailure.EVIDENCE_CONTRACT_INVALID)
        previous = retained.get(identity)
        if previous is not None and previous != integrity:
            raise Wo13BreakoutRejected(Wo13BreakoutFailure.EVIDENCE_CONTRACT_INVALID)
        retained[identity] = integrity
    return tuple(sorted(retained.items()))


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    encoded = json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return f"{prefix}{sha256(encoded).hexdigest().upper()}"


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value) if hasattr(value, "as_tuple") else value


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(item) for item in values)
