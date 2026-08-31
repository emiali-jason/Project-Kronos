"""Exact 15M Pullback-Continuation geometry for Intraday WO-13 Slice 3.

This module consumes one immutable WO-12 -> WO-13 handoff and explicitly
bound governed 15M structural facts.  It derives Pullback Entry, Stop,
invalidation and setup-native Target without selecting the later Slice-5
canonical Target.  It owns no persistence, runtime, Risk, 5M timing, Sponsor,
execution, Provider, or broker authority.
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
    Wo13StructuralPriceFact,
    Wo13StructuralPriceField,
    Wo13StructuralRole,
    Wo13TargetCandidate,
    Wo13TargetCandidateKind,
    Wo13ThesisInvalidationEvent,
    calculate_wo13_geometry,
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


WO13_PULLBACK_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-WO13-PULLBACK-GEOMETRY-EVIDENCE-V1"
)
WO13_PULLBACK_FACT_REFERENCE_IDENTITY = (
    "KRONOS-INTRADAY-WO13-PULLBACK-FACT-REFERENCE-V1"
)
WO13_PULLBACK_ENTRY_CONDITION_IDENTITY = (
    "KRONOS-INTRADAY-WO13-PULLBACK-ENTRY-CONDITION-V1"
)
WO13_PULLBACK_GEOMETRY_IDENTITY = (
    "KRONOS-INTRADAY-WO13-PULLBACK-GEOMETRY-V1"
)


class Wo13PullbackFailure(StrEnum):
    SETUP_FAMILY_UNSUPPORTED = "SETUP_FAMILY_UNSUPPORTED"
    EVIDENCE_CONTRACT_INVALID = "EVIDENCE_CONTRACT_INVALID"
    FACT_REFERENCE_INVALID = "FACT_REFERENCE_INVALID"
    FACT_BINDING_MISMATCH = "FACT_BINDING_MISMATCH"
    FACT_ROLE_MISMATCH = "FACT_ROLE_MISMATCH"
    FACT_TIMEFRAME_MISMATCH = "FACT_TIMEFRAME_MISMATCH"
    FACT_CONTEXT_MISMATCH = "FACT_CONTEXT_MISMATCH"
    FACT_CYCLE_MISMATCH = "FACT_CYCLE_MISMATCH"
    FACT_SESSION_MISMATCH = "FACT_SESSION_MISMATCH"
    GEOMETRY_CONTRACT_INVALID = "GEOMETRY_CONTRACT_INVALID"


class Wo13PullbackRejected(ValueError):
    """Sanitized Pullback trust-boundary failure."""

    def __init__(self, failure: Wo13PullbackFailure) -> None:
        if type(failure) is not Wo13PullbackFailure:
            raise ValueError("WO13_PULLBACK_FAILURE_INVALID")
        self.failure = failure
        super().__init__(failure.value)


class Wo13PullbackEntryConditionCode(StrEnum):
    DIRECTIONAL_INTERACTION_ABOVE_ENTRY_REFERENCE = (
        "DIRECTIONAL_INTERACTION_ABOVE_ENTRY_REFERENCE"
    )
    DIRECTIONAL_INTERACTION_BELOW_ENTRY_REFERENCE = (
        "DIRECTIONAL_INTERACTION_BELOW_ENTRY_REFERENCE"
    )


class Wo13PullbackInvalidationCode(StrEnum):
    COMPLETED_GOVERNED_15M_FAILURE_BELOW_PULLBACK_LOW = (
        "COMPLETED_GOVERNED_15M_FAILURE_BELOW_PULLBACK_LOW"
    )
    COMPLETED_GOVERNED_15M_FAILURE_ABOVE_PULLBACK_HIGH = (
        "COMPLETED_GOVERNED_15M_FAILURE_ABOVE_PULLBACK_HIGH"
    )


@dataclass(frozen=True, slots=True)
class Wo13PullbackFactReference:
    reference_identity: str
    reference_integrity: str
    fact_identity: str
    fact_integrity: str
    source_evidence_identity: str
    source_evidence_integrity: str
    structural_role: Wo13StructuralRole
    structure_identity: str
    schema_identity: str = WO13_PULLBACK_FACT_REFERENCE_IDENTITY
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
            ))
            or type(self.structural_role) is not Wo13StructuralRole
            or self.schema_identity != WO13_PULLBACK_FACT_REFERENCE_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.reference_identity
            != _identity("INTRADAY-WO13-PULLBACK-FACT-REFERENCE-", values)
            or self.reference_integrity
            != _identity(
                "INTEGRITY-INTRADAY-WO13-PULLBACK-FACT-REFERENCE-", values
            )
        ):
            raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_REFERENCE_INVALID)


def create_wo13_pullback_fact_reference(
    fact: Wo13StructuralPriceFact,
) -> Wo13PullbackFactReference:
    if type(fact) is not Wo13StructuralPriceFact:
        raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_REFERENCE_INVALID)
    values = {
        "fact_identity": fact.fact_identity,
        "fact_integrity": fact.fact_integrity,
        "source_evidence_identity": fact.source_evidence_identity,
        "source_evidence_integrity": fact.source_evidence_integrity,
        "structural_role": fact.structural_role,
        "structure_identity": fact.structure_identity,
        "schema_identity": WO13_PULLBACK_FACT_REFERENCE_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
    }
    return Wo13PullbackFactReference(
        reference_identity=_identity(
            "INTRADAY-WO13-PULLBACK-FACT-REFERENCE-", values
        ),
        reference_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-PULLBACK-FACT-REFERENCE-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13PullbackGeometryEvidence:
    evidence_identity: str
    evidence_integrity: str
    handoff: Wo13Step31Handoff
    market_session_identity: str
    qualification_references: tuple[Wo13PullbackFactReference, ...]
    qualification_candles: tuple[Wo13StructuralPriceFact, ...]
    pullback_references: tuple[Wo13PullbackFactReference, ...]
    governing_pullback_structures: tuple[Wo13StructuralPriceFact, ...]
    prior_impulse_references: tuple[Wo13PullbackFactReference, ...]
    prior_impulse_extremes: tuple[Wo13StructuralPriceFact, ...]
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    policy_identity: str = WO13_POLICY_IDENTITY
    policy_version: str = WO13_POLICY_VERSION
    policy_checksum: str = WO13_POLICY_CHECKSUM
    schema_identity: str = WO13_PULLBACK_EVIDENCE_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    provider_acquisition_authority: bool = False
    latest_resolution_authority: bool = False
    risk_authority: bool = False
    entry_timing_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        _validate_evidence_content(self)
        values = _without(self, "evidence_identity", "evidence_integrity")
        if (
            self.policy_identity != WO13_POLICY_IDENTITY
            or self.policy_version != WO13_POLICY_VERSION
            or self.policy_checksum != WO13_POLICY_CHECKSUM
            or self.schema_identity != WO13_PULLBACK_EVIDENCE_IDENTITY
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
            != _identity("INTRADAY-WO13-PULLBACK-EVIDENCE-", values)
            or self.evidence_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-PULLBACK-EVIDENCE-", values)
        ):
            raise Wo13PullbackRejected(
                Wo13PullbackFailure.EVIDENCE_CONTRACT_INVALID
            )


def create_wo13_pullback_geometry_evidence(
    *,
    handoff: Wo13Step31Handoff,
    market_session_identity: str,
    qualification_references: Sequence[Wo13PullbackFactReference] = (),
    qualification_candles: Sequence[Wo13StructuralPriceFact] = (),
    pullback_references: Sequence[Wo13PullbackFactReference] = (),
    governing_pullback_structures: Sequence[Wo13StructuralPriceFact] = (),
    prior_impulse_references: Sequence[Wo13PullbackFactReference] = (),
    prior_impulse_extremes: Sequence[Wo13StructuralPriceFact] = (),
) -> Wo13PullbackGeometryEvidence:
    if type(handoff) is not Wo13Step31Handoff:
        raise Wo13PullbackRejected(Wo13PullbackFailure.EVIDENCE_CONTRACT_INVALID)
    if handoff.setup_family is not Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION:
        raise Wo13PullbackRejected(Wo13PullbackFailure.SETUP_FAMILY_UNSUPPORTED)
    references = tuple(
        _ordered_references(items)
        for items in (
            qualification_references,
            pullback_references,
            prior_impulse_references,
        )
    )
    facts = tuple(
        _ordered_facts(items)
        for items in (
            qualification_candles,
            governing_pullback_structures,
            prior_impulse_extremes,
        )
    )
    pairs = [
        (handoff.handoff_identity, handoff.handoff_integrity),
        *(
            (item.reference_identity, item.reference_integrity)
            for group in references
            for item in group
        ),
        *(
            (item.fact_identity, item.fact_integrity)
            for group in facts
            for item in group
        ),
    ]
    ordered_sources = _unique_pairs(pairs)
    values = {
        "handoff": handoff,
        "market_session_identity": market_session_identity,
        "qualification_references": references[0],
        "qualification_candles": facts[0],
        "pullback_references": references[1],
        "governing_pullback_structures": facts[1],
        "prior_impulse_references": references[2],
        "prior_impulse_extremes": facts[2],
        "source_identities": tuple(item[0] for item in ordered_sources),
        "source_integrities": tuple(item[1] for item in ordered_sources),
        "policy_identity": WO13_POLICY_IDENTITY,
        "policy_version": WO13_POLICY_VERSION,
        "policy_checksum": WO13_POLICY_CHECKSUM,
        "schema_identity": WO13_PULLBACK_EVIDENCE_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "provider_acquisition_authority": False,
        "latest_resolution_authority": False,
        "risk_authority": False,
        "entry_timing_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo13PullbackGeometryEvidence(
        evidence_identity=_identity("INTRADAY-WO13-PULLBACK-EVIDENCE-", values),
        evidence_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-PULLBACK-EVIDENCE-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo13PullbackEntryCondition:
    condition_identity: str
    condition_integrity: str
    entry_reference_identity: str
    entry_reference_integrity: str
    direction: SemanticDirection
    condition_code: Wo13PullbackEntryConditionCode
    schema_identity: str = WO13_PULLBACK_ENTRY_CONDITION_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    trigger_evaluation_performed: bool = False
    entry_timing_authority: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "condition_identity", "condition_integrity")
        expected = (
            Wo13PullbackEntryConditionCode.DIRECTIONAL_INTERACTION_ABOVE_ENTRY_REFERENCE
            if self.direction is SemanticDirection.LONG
            else Wo13PullbackEntryConditionCode.DIRECTIONAL_INTERACTION_BELOW_ENTRY_REFERENCE
        )
        if (
            not _texts((
                self.entry_reference_identity,
                self.entry_reference_integrity,
            ))
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or self.condition_code is not expected
            or self.schema_identity != WO13_PULLBACK_ENTRY_CONDITION_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.trigger_evaluation_performed
            or self.entry_timing_authority
            or self.execution_authority
            or self.condition_identity
            != _identity("INTRADAY-WO13-PULLBACK-ENTRY-CONDITION-", values)
            or self.condition_integrity
            != _identity(
                "INTEGRITY-INTRADAY-WO13-PULLBACK-ENTRY-CONDITION-", values
            )
        ):
            raise Wo13PullbackRejected(
                Wo13PullbackFailure.GEOMETRY_CONTRACT_INVALID
            )


@dataclass(frozen=True, slots=True)
class Wo13PullbackGeometry:
    geometry_identity: str
    geometry_integrity: str
    evidence: Wo13PullbackGeometryEvidence
    entry_reference: Wo13StructuralPriceField
    entry_condition: Wo13PullbackEntryCondition | None
    stop: Wo13StructuralPriceField
    thesis_invalidation_reference: Wo13StructuralPriceField
    thesis_invalidation_event: Wo13ThesisInvalidationEvent | None
    prior_impulse_target: Wo13StructuralPriceField
    native_target_candidate: Wo13TargetCandidate | None
    setup_native_target: Wo13StructuralPriceField
    canonical_target: Wo13StructuralPriceField
    calculation: Wo13GeometryCalculation
    target_constraint_selection_pending: bool
    schema_identity: str = WO13_PULLBACK_GEOMETRY_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    range_breakout_authority: bool = False
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
            type(self.evidence) is not Wo13PullbackGeometryEvidence
            or (
                self.entry_reference,
                self.entry_condition,
                self.stop,
                self.thesis_invalidation_reference,
                self.thesis_invalidation_event,
                self.prior_impulse_target,
                self.native_target_candidate,
                self.setup_native_target,
                self.canonical_target,
                self.calculation,
            )
            != expected
            or not self.target_constraint_selection_pending
            or self.calculation.geometry_availability
            is Wo13GeometryAvailability.GEOMETRY_COMPLETE
            or self.schema_identity != WO13_PULLBACK_GEOMETRY_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or any((
                self.range_breakout_authority,
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
            != _identity("INTRADAY-WO13-PULLBACK-GEOMETRY-", values)
            or self.geometry_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-PULLBACK-GEOMETRY-", values)
        ):
            raise Wo13PullbackRejected(
                Wo13PullbackFailure.GEOMETRY_CONTRACT_INVALID
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


def construct_wo13_pullback_geometry(
    evidence: Wo13PullbackGeometryEvidence,
) -> Wo13PullbackGeometry:
    if type(evidence) is not Wo13PullbackGeometryEvidence:
        raise Wo13PullbackRejected(Wo13PullbackFailure.EVIDENCE_CONTRACT_INVALID)
    assembled = _assemble(evidence)
    values = {
        "evidence": evidence,
        "entry_reference": assembled[0],
        "entry_condition": assembled[1],
        "stop": assembled[2],
        "thesis_invalidation_reference": assembled[3],
        "thesis_invalidation_event": assembled[4],
        "prior_impulse_target": assembled[5],
        "native_target_candidate": assembled[6],
        "setup_native_target": assembled[7],
        "canonical_target": assembled[8],
        "calculation": assembled[9],
        "target_constraint_selection_pending": True,
        "schema_identity": WO13_PULLBACK_GEOMETRY_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "range_breakout_authority": False,
        "target_constraint_selection_authority": False,
        "persistence_authority": False,
        "runtime_authority": False,
        "risk_authority": False,
        "entry_timing_authority": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo13PullbackGeometry(
        geometry_identity=_identity("INTRADAY-WO13-PULLBACK-GEOMETRY-", values),
        geometry_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-PULLBACK-GEOMETRY-", values
        ),
        **values,
    )


def _assemble(
    evidence: Wo13PullbackGeometryEvidence,
) -> tuple[
    Wo13StructuralPriceField,
    Wo13PullbackEntryCondition | None,
    Wo13StructuralPriceField,
    Wo13StructuralPriceField,
    Wo13ThesisInvalidationEvent | None,
    Wo13StructuralPriceField,
    Wo13TargetCandidate | None,
    Wo13StructuralPriceField,
    Wo13StructuralPriceField,
    Wo13GeometryCalculation,
]:
    direction = evidence.handoff.inherited_direction
    entry = _derived_field(
        Wo13GeometryField.ENTRY_REFERENCE,
        evidence.qualification_candles,
        evidence.qualification_references,
        Wo13StructuralRole.ENTRY_REFERENCE_SOURCE,
    )
    stop = _derived_field(
        Wo13GeometryField.STOP,
        evidence.governing_pullback_structures,
        evidence.pullback_references,
        Wo13StructuralRole.STOP_REFERENCE_SOURCE,
    )
    invalidation = _derived_field(
        Wo13GeometryField.THESIS_INVALIDATION_REFERENCE,
        evidence.governing_pullback_structures,
        evidence.pullback_references,
        Wo13StructuralRole.THESIS_INVALIDATION_REFERENCE,
    )
    prior_impulse = _derived_field(
        Wo13GeometryField.SETUP_NATIVE_TARGET,
        evidence.prior_impulse_extremes,
        evidence.prior_impulse_references,
        Wo13StructuralRole.SETUP_NATIVE_TARGET,
    )
    entry_fact = entry.selected_fact
    stop_fact = stop.selected_fact
    invalidation_fact = invalidation.selected_fact
    impulse_fact = prior_impulse.selected_fact
    entry_condition = (
        _entry_condition(direction, entry_fact) if entry_fact is not None else None
    )
    invalidation_event = (
        create_wo13_thesis_invalidation_event(
            reference=invalidation_fact,
            event_code=(
                Wo13PullbackInvalidationCode.COMPLETED_GOVERNED_15M_FAILURE_BELOW_PULLBACK_LOW.value
                if direction is SemanticDirection.LONG
                else Wo13PullbackInvalidationCode.COMPLETED_GOVERNED_15M_FAILURE_ABOVE_PULLBACK_HIGH.value
            ),
            source_evidence_identity=invalidation_fact.source_evidence_identity,
            source_evidence_integrity=invalidation_fact.source_evidence_integrity,
        )
        if invalidation_fact is not None
        else None
    )
    native_candidate = (
        create_wo13_target_candidate(
            entry_reference=entry_fact,
            candidate=impulse_fact,
            direction=direction,
            kind=Wo13TargetCandidateKind.SETUP_NATIVE_OBJECTIVE,
        )
        if entry_fact is not None and impulse_fact is not None
        else None
    )
    native_forward = (
        native_candidate is None
        or native_candidate.forward_state is Wo13ForwardTargetState.FORWARD
    )
    native_target = (
        prior_impulse
        if native_forward
        else resolve_wo13_structural_price_field(
            Wo13GeometryField.SETUP_NATIVE_TARGET,
            expected_sources=_source_pairs(evidence.prior_impulse_references),
        )
    )
    canonical_target = resolve_wo13_structural_price_field(
        Wo13GeometryField.CANONICAL_TARGET
    )
    calculation = calculate_wo13_geometry(
        direction=direction,
        entry_reference=entry,
        stop=stop,
        thesis_invalidation_reference=invalidation,
        thesis_invalidation_event=invalidation_event,
        target=canonical_target,
    )
    return (
        entry,
        entry_condition,
        stop,
        invalidation,
        invalidation_event,
        prior_impulse,
        native_candidate,
        native_target,
        canonical_target,
        calculation,
    )


def _entry_condition(
    direction: SemanticDirection,
    entry: Wo13StructuralPriceFact,
) -> Wo13PullbackEntryCondition:
    code = (
        Wo13PullbackEntryConditionCode.DIRECTIONAL_INTERACTION_ABOVE_ENTRY_REFERENCE
        if direction is SemanticDirection.LONG
        else Wo13PullbackEntryConditionCode.DIRECTIONAL_INTERACTION_BELOW_ENTRY_REFERENCE
    )
    values = {
        "entry_reference_identity": entry.fact_identity,
        "entry_reference_integrity": entry.fact_integrity,
        "direction": direction,
        "condition_code": code,
        "schema_identity": WO13_PULLBACK_ENTRY_CONDITION_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "trigger_evaluation_performed": False,
        "entry_timing_authority": False,
        "execution_authority": False,
    }
    return Wo13PullbackEntryCondition(
        condition_identity=_identity(
            "INTRADAY-WO13-PULLBACK-ENTRY-CONDITION-", values
        ),
        condition_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-PULLBACK-ENTRY-CONDITION-", values
        ),
        **values,
    )


def _derived_field(
    field: Wo13GeometryField,
    sources: Sequence[Wo13StructuralPriceFact],
    references: Sequence[Wo13PullbackFactReference],
    role: Wo13StructuralRole,
) -> Wo13StructuralPriceField:
    derived = tuple(_derived_fact(item, role) for item in sources)
    return resolve_wo13_structural_price_field(
        field,
        facts=derived,
        expected_sources=_source_pairs(references),
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


def _validate_evidence_content(evidence: Wo13PullbackGeometryEvidence) -> None:
    handoff = evidence.handoff
    if type(handoff) is not Wo13Step31Handoff:
        raise Wo13PullbackRejected(Wo13PullbackFailure.EVIDENCE_CONTRACT_INVALID)
    if handoff.setup_family is not Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION:
        raise Wo13PullbackRejected(Wo13PullbackFailure.SETUP_FAMILY_UNSUPPORTED)
    if not _text(evidence.market_session_identity):
        raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_SESSION_MISMATCH)
    expected_roles = (
        (
            Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH,
            Wo13StructuralRole.PULLBACK_STRUCTURAL_LOW,
            Wo13StructuralRole.PRIOR_IMPULSE_HIGH,
        )
        if handoff.inherited_direction is SemanticDirection.LONG
        else (
            Wo13StructuralRole.QUALIFICATION_CANDLE_LOW,
            Wo13StructuralRole.PULLBACK_STRUCTURAL_HIGH,
            Wo13StructuralRole.PRIOR_IMPULSE_LOW,
        )
    )
    groups = (
        (evidence.qualification_references, evidence.qualification_candles),
        (evidence.pullback_references, evidence.governing_pullback_structures),
        (evidence.prior_impulse_references, evidence.prior_impulse_extremes),
    )
    for (references, facts), role in zip(groups, expected_roles, strict=True):
        _validate_component(
            handoff,
            evidence.market_session_identity,
            references,
            facts,
            role,
        )
    expected_sources = _unique_pairs([
        (handoff.handoff_identity, handoff.handoff_integrity),
        *(
            (item.reference_identity, item.reference_integrity)
            for references, _ in groups
            for item in references
        ),
        *(
            (item.fact_identity, item.fact_integrity)
            for _, facts in groups
            for item in facts
        ),
    ])
    if (
        evidence.source_identities != tuple(item[0] for item in expected_sources)
        or evidence.source_integrities != tuple(item[1] for item in expected_sources)
    ):
        raise Wo13PullbackRejected(Wo13PullbackFailure.EVIDENCE_CONTRACT_INVALID)


def _validate_component(
    handoff: Wo13Step31Handoff,
    market_session_identity: str,
    references: Sequence[Wo13PullbackFactReference],
    facts: Sequence[Wo13StructuralPriceFact],
    role: Wo13StructuralRole,
) -> None:
    if tuple(references) != _ordered_references(references):
        raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_REFERENCE_INVALID)
    if tuple(facts) != _ordered_facts(facts):
        raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_BINDING_MISMATCH)
    if any(item.structural_role is not role for item in references):
        raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_ROLE_MISMATCH)
    reference_by_fact = {item.fact_identity: item for item in references}
    if len(reference_by_fact) != len(references):
        raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_REFERENCE_INVALID)
    for fact in facts:
        if type(fact) is not Wo13StructuralPriceFact:
            raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_BINDING_MISMATCH)
        if fact.structural_role is not role:
            raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_ROLE_MISMATCH)
        if fact.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES:
            raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_TIMEFRAME_MISMATCH)
        if fact.structure_identity != handoff.setup_evidence_identity:
            raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_CYCLE_MISMATCH)
        if fact.market_session_identity != market_session_identity:
            raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_SESSION_MISMATCH)
        if not _matches_handoff(fact, handoff):
            raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_CONTEXT_MISMATCH)
        reference = reference_by_fact.get(fact.fact_identity)
        if reference is None or (
            reference.fact_integrity != fact.fact_integrity
            or reference.source_evidence_identity != fact.source_evidence_identity
            or reference.source_evidence_integrity != fact.source_evidence_integrity
            or reference.structure_identity != fact.structure_identity
        ):
            raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_BINDING_MISMATCH)
    if any(item.structure_identity != handoff.setup_evidence_identity for item in references):
        raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_CYCLE_MISMATCH)


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


def _source_pairs(
    references: Sequence[Wo13PullbackFactReference],
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (
                (item.source_evidence_identity, item.source_evidence_integrity)
                for item in references
            ),
            key=lambda item: item[0],
        )
    )


def _ordered_references(
    values: Sequence[Wo13PullbackFactReference],
) -> tuple[Wo13PullbackFactReference, ...]:
    if any(type(item) is not Wo13PullbackFactReference for item in values):
        raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_REFERENCE_INVALID)
    return tuple(sorted(values, key=lambda item: item.reference_identity))


def _ordered_facts(
    values: Sequence[Wo13StructuralPriceFact],
) -> tuple[Wo13StructuralPriceFact, ...]:
    if any(type(item) is not Wo13StructuralPriceFact for item in values):
        raise Wo13PullbackRejected(Wo13PullbackFailure.FACT_BINDING_MISMATCH)
    return tuple(sorted(values, key=lambda item: item.fact_identity))


def _unique_pairs(
    pairs: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    retained: dict[str, str] = {}
    for identity, integrity in pairs:
        if not _texts((identity, integrity)):
            raise Wo13PullbackRejected(
                Wo13PullbackFailure.EVIDENCE_CONTRACT_INVALID
            )
        previous = retained.get(identity)
        if previous is not None and previous != integrity:
            raise Wo13PullbackRejected(
                Wo13PullbackFailure.EVIDENCE_CONTRACT_INVALID
            )
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
