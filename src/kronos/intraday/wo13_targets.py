"""Canonical target finalization for Intraday WO-13 Slice 5.

The setup-specific Slice-3/4 geometry remains immutable.  This module only
selects one canonical Target from its setup-native objective and a complete,
explicit population of already-governed structural constraints.  It owns no
market-data acquisition, persistence, runtime, Risk, timing, Sponsor,
execution, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence, TypeAlias

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import (
    WO13_POLICY_CHECKSUM,
    WO13_POLICY_IDENTITY,
    Wo13GeometryAvailability,
    Wo13GeometryField,
)
from kronos.intraday.wo13_breakout import Wo13BreakoutGeometry
from kronos.intraday.wo13_geometry import (
    Wo13ForwardTargetState,
    Wo13GeometryCalculation,
    Wo13StructuralPriceFact,
    Wo13StructuralPriceField,
    Wo13StructuralRole,
    Wo13TargetCandidate,
    Wo13TargetCandidateKind,
    calculate_wo13_geometry,
    create_wo13_structural_price_fact,
    resolve_wo13_structural_price_field,
)
from kronos.intraday.wo13_handoff import (
    WO13_CONTRACT_VERSION,
    WO13_POLICY_VERSION,
)
from kronos.intraday.wo13_pullback import Wo13PullbackGeometry


WO13_TARGET_CONSTRAINT_POPULATION_IDENTITY = (
    "KRONOS-INTRADAY-WO13-TARGET-CONSTRAINT-POPULATION-V1"
)
WO13_TARGET_SELECTION_IDENTITY = (
    "KRONOS-INTRADAY-WO13-CANONICAL-TARGET-SELECTION-V1"
)


Wo13SetupGeometry: TypeAlias = Wo13PullbackGeometry | Wo13BreakoutGeometry


class Wo13TargetPopulationCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class Wo13TargetSelectionDisposition(StrEnum):
    CONSTRAINED = "CONSTRAINED"
    SETUP_NATIVE = "SETUP_NATIVE"
    INCOMPLETE = "INCOMPLETE"


class Wo13TargetSelectionFailure(StrEnum):
    SETUP_GEOMETRY_INVALID = "SETUP_GEOMETRY_INVALID"
    POPULATION_INVALID = "POPULATION_INVALID"
    POPULATION_BINDING_MISMATCH = "POPULATION_BINDING_MISMATCH"
    CANDIDATE_CONTEXT_MISMATCH = "CANDIDATE_CONTEXT_MISMATCH"
    CANDIDATE_SOURCE_CONFLICT = "CANDIDATE_SOURCE_CONFLICT"
    NATIVE_TARGET_NOT_FORWARD = "NATIVE_TARGET_NOT_FORWARD"
    SELECTION_INTEGRITY_INVALID = "SELECTION_INTEGRITY_INVALID"


class Wo13TargetSelectionRejected(ValueError):
    """Sanitized fail-closed Slice-5 target-selection rejection."""

    def __init__(self, failure: Wo13TargetSelectionFailure) -> None:
        if type(failure) is not Wo13TargetSelectionFailure:
            raise ValueError("WO13_TARGET_SELECTION_FAILURE_INVALID")
        self.failure = failure
        super().__init__(failure.value)


WO13_ELIGIBLE_TARGET_CONSTRAINT_ROLES = (
    Wo13StructuralRole.PDH,
    Wo13StructuralRole.PDL,
    Wo13StructuralRole.SESSION_STRUCTURAL_HIGH,
    Wo13StructuralRole.SESSION_STRUCTURAL_LOW,
    Wo13StructuralRole.PIVOT_RESISTANCE,
    Wo13StructuralRole.PIVOT_SUPPORT,
    Wo13StructuralRole.GOVERNED_STRUCTURAL_BARRIER,
)

_CONSTRAINT_ROLES = frozenset(WO13_ELIGIBLE_TARGET_CONSTRAINT_ROLES)


@dataclass(frozen=True, slots=True)
class Wo13TargetConstraintPopulation:
    population_identity: str
    population_integrity: str
    setup_geometry_identity: str
    setup_geometry_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    direction: SemanticDirection
    analysis_boundary: datetime
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    candidates: tuple[Wo13TargetCandidate, ...]
    completeness: Wo13TargetPopulationCompleteness
    source_identities: tuple[str, ...]
    source_integrities: tuple[str, ...]
    policy_identity: str = WO13_POLICY_IDENTITY
    policy_version: str = WO13_POLICY_VERSION
    policy_checksum: str = WO13_POLICY_CHECKSUM
    schema_identity: str = WO13_TARGET_CONSTRAINT_POPULATION_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    acquisition_authority: bool = False
    persistence_authority: bool = False
    runtime_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "population_identity", "population_integrity")
        if (
            not _texts((
                self.setup_geometry_identity,
                self.setup_geometry_integrity,
                self.canonical_subject_identity,
                self.instrument_identity,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or (
                self.market_family is IntradayMarketFamily.MCX
            ) != (self.actual_contract_identity is not None)
            or (
                self.market_family is IntradayMarketFamily.MCX
            ) != (self.roll_lineage_identity is not None)
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or not _aware(self.analysis_boundary)
            or type(self.completeness) is not Wo13TargetPopulationCompleteness
            or self.candidates != _ordered_candidates(self.candidates)
            or len({item.candidate_identity for item in self.candidates})
            != len(self.candidates)
            or not _population_candidates_valid(self)
            or not _candidate_sources_consistent(self.candidates)
            or tuple(zip(
                self.source_identities,
                self.source_integrities,
                strict=True,
            )) != _candidate_sources(self.candidates)
            or self.policy_identity != WO13_POLICY_IDENTITY
            or self.policy_version != WO13_POLICY_VERSION
            or self.policy_checksum != WO13_POLICY_CHECKSUM
            or self.schema_identity != WO13_TARGET_CONSTRAINT_POPULATION_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or self.acquisition_authority
            or self.persistence_authority
            or self.runtime_authority
            or self.population_identity
            != _identity("INTRADAY-WO13-TARGET-POPULATION-", values)
            or self.population_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-TARGET-POPULATION-", values)
        ):
            raise Wo13TargetSelectionRejected(
                Wo13TargetSelectionFailure.POPULATION_INVALID
            )


def create_wo13_target_constraint_population(
    *,
    setup_geometry: Wo13SetupGeometry,
    candidates: Sequence[Wo13TargetCandidate] = (),
    completeness: Wo13TargetPopulationCompleteness = (
        Wo13TargetPopulationCompleteness.COMPLETE
    ),
) -> Wo13TargetConstraintPopulation:
    geometry = _require_geometry(setup_geometry)
    entry = geometry.entry_reference.selected_fact
    if entry is None:
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.SETUP_GEOMETRY_INVALID
        )
    if type(completeness) is not Wo13TargetPopulationCompleteness:
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.POPULATION_INVALID
        )
    retained: dict[str, Wo13TargetCandidate] = {}
    for item in candidates:
        if type(item) is not Wo13TargetCandidate:
            raise Wo13TargetSelectionRejected(
                Wo13TargetSelectionFailure.POPULATION_INVALID
            )
        previous = retained.get(item.candidate_identity)
        if previous is not None and previous.candidate_integrity != item.candidate_integrity:
            raise Wo13TargetSelectionRejected(
                Wo13TargetSelectionFailure.CANDIDATE_SOURCE_CONFLICT
            )
        retained[item.candidate_identity] = item
    ordered = _ordered_candidates(tuple(retained.values()))
    _reject_source_conflicts(ordered)
    geometry_identity, geometry_integrity = _geometry_identity(geometry)
    sources = _candidate_sources(ordered)
    values = {
        "setup_geometry_identity": geometry_identity,
        "setup_geometry_integrity": geometry_integrity,
        "canonical_subject_identity": entry.canonical_subject_identity,
        "market_family": entry.market_family,
        "direction": _direction(geometry),
        "analysis_boundary": entry.analysis_boundary,
        "instrument_identity": entry.instrument_identity,
        "actual_contract_identity": entry.actual_contract_identity,
        "roll_lineage_identity": entry.roll_lineage_identity,
        "candidates": ordered,
        "completeness": completeness,
        "source_identities": tuple(item[0] for item in sources),
        "source_integrities": tuple(item[1] for item in sources),
        "policy_identity": WO13_POLICY_IDENTITY,
        "policy_version": WO13_POLICY_VERSION,
        "policy_checksum": WO13_POLICY_CHECKSUM,
        "schema_identity": WO13_TARGET_CONSTRAINT_POPULATION_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "acquisition_authority": False,
        "persistence_authority": False,
        "runtime_authority": False,
    }
    population = Wo13TargetConstraintPopulation(
        population_identity=_identity("INTRADAY-WO13-TARGET-POPULATION-", values),
        population_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-TARGET-POPULATION-", values
        ),
        **values,
    )
    if not _population_matches_geometry(population, geometry):
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.CANDIDATE_CONTEXT_MISMATCH
        )
    return population


@dataclass(frozen=True, slots=True)
class Wo13CanonicalTargetSelection:
    selection_identity: str
    selection_integrity: str
    setup_geometry: Wo13SetupGeometry
    candidate_population: Wo13TargetConstraintPopulation
    entry_reference: Wo13StructuralPriceField
    setup_native_target: Wo13StructuralPriceField
    canonical_target: Wo13StructuralPriceField
    constraining_candidates: tuple[Wo13TargetCandidate, ...]
    confluence_candidates: tuple[Wo13TargetCandidate, ...]
    disposition: Wo13TargetSelectionDisposition
    calculation: Wo13GeometryCalculation
    policy_identity: str = WO13_POLICY_IDENTITY
    policy_version: str = WO13_POLICY_VERSION
    policy_checksum: str = WO13_POLICY_CHECKSUM
    schema_identity: str = WO13_TARGET_SELECTION_IDENTITY
    schema_version: str = WO13_CONTRACT_VERSION
    target_extension_authority: bool = False
    risk_authority: bool = False
    entry_timing_authority: bool = False
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        expected = _resolve_selection(
            self.setup_geometry,
            self.candidate_population,
        )
        values = _without(self, "selection_identity", "selection_integrity")
        if (
            (
                self.entry_reference,
                self.setup_native_target,
                self.canonical_target,
                self.constraining_candidates,
                self.confluence_candidates,
                self.disposition,
                self.calculation,
            ) != expected
            or self.policy_identity != WO13_POLICY_IDENTITY
            or self.policy_version != WO13_POLICY_VERSION
            or self.policy_checksum != WO13_POLICY_CHECKSUM
            or self.schema_identity != WO13_TARGET_SELECTION_IDENTITY
            or self.schema_version != WO13_CONTRACT_VERSION
            or any((
                self.target_extension_authority,
                self.risk_authority,
                self.entry_timing_authority,
                self.sponsor_decision_authority,
                self.execution_authority,
                self.broker_authority,
            ))
            or self.selection_identity
            != _identity("INTRADAY-WO13-TARGET-SELECTION-", values)
            or self.selection_integrity
            != _identity("INTEGRITY-INTRADAY-WO13-TARGET-SELECTION-", values)
        ):
            raise Wo13TargetSelectionRejected(
                Wo13TargetSelectionFailure.SELECTION_INTEGRITY_INVALID
            )

    @property
    def risk_distance(self):  # type: ignore[no-untyped-def]
        return self.calculation.risk_distance

    @property
    def reward_distance(self):  # type: ignore[no-untyped-def]
        return self.calculation.reward_distance

    @property
    def model_rr(self):  # type: ignore[no-untyped-def]
        return self.calculation.model_rr

    @property
    def geometry_availability(self) -> Wo13GeometryAvailability:
        return self.calculation.geometry_availability


def finalize_wo13_canonical_target(
    *,
    setup_geometry: Wo13SetupGeometry,
    candidate_population: Wo13TargetConstraintPopulation,
) -> Wo13CanonicalTargetSelection:
    geometry = _require_geometry(setup_geometry)
    if type(candidate_population) is not Wo13TargetConstraintPopulation:
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.POPULATION_INVALID
        )
    if not _population_matches_geometry(candidate_population, geometry):
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.POPULATION_BINDING_MISMATCH
        )
    resolved = _resolve_selection(geometry, candidate_population)
    values = {
        "setup_geometry": geometry,
        "candidate_population": candidate_population,
        "entry_reference": resolved[0],
        "setup_native_target": resolved[1],
        "canonical_target": resolved[2],
        "constraining_candidates": resolved[3],
        "confluence_candidates": resolved[4],
        "disposition": resolved[5],
        "calculation": resolved[6],
        "policy_identity": WO13_POLICY_IDENTITY,
        "policy_version": WO13_POLICY_VERSION,
        "policy_checksum": WO13_POLICY_CHECKSUM,
        "schema_identity": WO13_TARGET_SELECTION_IDENTITY,
        "schema_version": WO13_CONTRACT_VERSION,
        "target_extension_authority": False,
        "risk_authority": False,
        "entry_timing_authority": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo13CanonicalTargetSelection(
        selection_identity=_identity("INTRADAY-WO13-TARGET-SELECTION-", values),
        selection_integrity=_identity(
            "INTEGRITY-INTRADAY-WO13-TARGET-SELECTION-", values
        ),
        **values,
    )


def _resolve_selection(
    geometry: Wo13SetupGeometry,
    population: Wo13TargetConstraintPopulation,
) -> tuple[
    Wo13StructuralPriceField,
    Wo13StructuralPriceField,
    Wo13StructuralPriceField,
    tuple[Wo13TargetCandidate, ...],
    tuple[Wo13TargetCandidate, ...],
    Wo13TargetSelectionDisposition,
    Wo13GeometryCalculation,
]:
    geometry = _require_geometry(geometry)
    if not _population_matches_geometry(population, geometry):
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.POPULATION_BINDING_MISMATCH
        )
    entry = geometry.entry_reference
    native = geometry.setup_native_target
    native_candidate = geometry.native_target_candidate
    if native_candidate is not None and (
        native_candidate.forward_state is not Wo13ForwardTargetState.FORWARD
    ):
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.NATIVE_TARGET_NOT_FORWARD
        )

    canonical = _unavailable_canonical(population)
    constrained: tuple[Wo13TargetCandidate, ...] = ()
    confluence: tuple[Wo13TargetCandidate, ...] = ()
    disposition = Wo13TargetSelectionDisposition.INCOMPLETE
    entry_fact = entry.selected_fact
    native_fact = native.selected_fact
    if (
        population.completeness is Wo13TargetPopulationCompleteness.COMPLETE
        and entry_fact is not None
        and native_fact is not None
        and native_candidate is not None
        and native_candidate.forward_state is Wo13ForwardTargetState.FORWARD
        and native_candidate.directional_distance is not None
    ):
        native_distance = native_candidate.directional_distance
        inside = tuple(
            item
            for item in population.candidates
            if item.forward_state is Wo13ForwardTargetState.FORWARD
            and item.directional_distance is not None
            and item.directional_distance < native_distance
        )
        if inside:
            nearest = min(item.directional_distance for item in inside)
            constrained = tuple(
                item for item in inside if item.directional_distance == nearest
            )
            canonical = _constraint_canonical(
                entry_fact=entry_fact,
                population=population,
                candidates=constrained,
            )
            disposition = Wo13TargetSelectionDisposition.CONSTRAINED
        else:
            canonical = resolve_wo13_structural_price_field(
                Wo13GeometryField.CANONICAL_TARGET,
                facts=(native_fact,),
                expected_sources=((
                    native_fact.source_evidence_identity,
                    native_fact.source_evidence_integrity,
                ),),
            )
            disposition = Wo13TargetSelectionDisposition.SETUP_NATIVE
        selected_price = canonical.selected_fact.price
        confluence = tuple(
            item for item in population.candidates if item.price == selected_price
        )

    calculation = calculate_wo13_geometry(
        direction=_direction(geometry),
        entry_reference=geometry.entry_reference,
        stop=geometry.stop,
        thesis_invalidation_reference=geometry.thesis_invalidation_reference,
        thesis_invalidation_event=geometry.thesis_invalidation_event,
        target=canonical,
    )
    if calculation.risk_distance != geometry.calculation.risk_distance:
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.SELECTION_INTEGRITY_INVALID
        )
    return (
        entry,
        native,
        canonical,
        constrained,
        confluence,
        disposition,
        calculation,
    )


def _constraint_canonical(
    *,
    entry_fact: Wo13StructuralPriceFact,
    population: Wo13TargetConstraintPopulation,
    candidates: tuple[Wo13TargetCandidate, ...],
) -> Wo13StructuralPriceField:
    ordered = _ordered_candidates(candidates)
    prices = {item.price for item in ordered}
    if not ordered or len(prices) != 1:
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.CANDIDATE_SOURCE_CONFLICT
        )
    source_value = tuple(
        (item.candidate_identity, item.candidate_integrity) for item in ordered
    )
    fact = create_wo13_structural_price_fact(
        canonical_subject_identity=entry_fact.canonical_subject_identity,
        market_family=entry_fact.market_family,
        timeframe=entry_fact.timeframe,
        price=next(iter(prices)),
        structural_role=Wo13StructuralRole.TARGET_CONSTRAINT,
        price_authority=entry_fact.price_authority,
        structure_identity=_identity(
            "INTRADAY-WO13-TARGET-CONFLUENCE-", source_value
        ),
        source_evidence_identity=population.population_identity,
        source_evidence_integrity=population.population_integrity,
        analysis_boundary=entry_fact.analysis_boundary,
        instrument_identity=entry_fact.instrument_identity,
        actual_contract_identity=entry_fact.actual_contract_identity,
        roll_lineage_identity=entry_fact.roll_lineage_identity,
        market_session_identity=entry_fact.market_session_identity,
    )
    return resolve_wo13_structural_price_field(
        Wo13GeometryField.CANONICAL_TARGET,
        facts=(fact,),
        expected_sources=((
            population.population_identity,
            population.population_integrity,
        ),),
    )


def _unavailable_canonical(
    population: Wo13TargetConstraintPopulation,
) -> Wo13StructuralPriceField:
    return resolve_wo13_structural_price_field(
        Wo13GeometryField.CANONICAL_TARGET,
        expected_sources=((
            population.population_identity,
            population.population_integrity,
        ),),
    )


def _require_geometry(value: object) -> Wo13SetupGeometry:
    if type(value) not in {Wo13PullbackGeometry, Wo13BreakoutGeometry}:
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.SETUP_GEOMETRY_INVALID
        )
    return value  # type: ignore[return-value]


def _direction(geometry: Wo13SetupGeometry) -> SemanticDirection:
    return geometry.evidence.handoff.inherited_direction


def _geometry_identity(geometry: Wo13SetupGeometry) -> tuple[str, str]:
    return geometry.geometry_identity, geometry.geometry_integrity


def _population_matches_geometry(
    population: Wo13TargetConstraintPopulation,
    geometry: Wo13SetupGeometry,
) -> bool:
    if type(population) is not Wo13TargetConstraintPopulation:
        return False
    entry = geometry.entry_reference.selected_fact
    if entry is None:
        return False
    identity, integrity = _geometry_identity(geometry)
    return (
        population.setup_geometry_identity == identity
        and population.setup_geometry_integrity == integrity
        and population.canonical_subject_identity
        == entry.canonical_subject_identity
        and population.market_family is entry.market_family
        and population.direction is _direction(geometry)
        and population.analysis_boundary == entry.analysis_boundary
        and population.instrument_identity == entry.instrument_identity
        and population.actual_contract_identity == entry.actual_contract_identity
        and population.roll_lineage_identity == entry.roll_lineage_identity
        and all(
            item.entry_reference.fact_identity == entry.fact_identity
            and item.entry_reference.fact_integrity == entry.fact_integrity
            for item in population.candidates
        )
    )


def _population_candidates_valid(
    population: Wo13TargetConstraintPopulation,
) -> bool:
    return all(
        type(item) is Wo13TargetCandidate
        and item.kind is Wo13TargetCandidateKind.STRUCTURAL_CONSTRAINT
        and item.structural_role in _CONSTRAINT_ROLES
        and item.direction is population.direction
        and item.entry_reference.canonical_subject_identity
        == population.canonical_subject_identity
        and item.candidate.canonical_subject_identity
        == population.canonical_subject_identity
        and item.entry_reference.market_family is population.market_family
        and item.candidate.market_family is population.market_family
        and item.entry_reference.analysis_boundary == population.analysis_boundary
        and item.candidate.analysis_boundary == population.analysis_boundary
        and item.entry_reference.instrument_identity == population.instrument_identity
        and item.candidate.instrument_identity == population.instrument_identity
        and item.entry_reference.actual_contract_identity
        == population.actual_contract_identity
        and item.candidate.actual_contract_identity
        == population.actual_contract_identity
        and item.entry_reference.roll_lineage_identity
        == population.roll_lineage_identity
        and item.candidate.roll_lineage_identity
        == population.roll_lineage_identity
        and _candidate_session_valid(item)
        for item in population.candidates
    )


def _candidate_session_valid(candidate: Wo13TargetCandidate) -> bool:
    role = candidate.structural_role
    if role in {
        Wo13StructuralRole.SESSION_STRUCTURAL_HIGH,
        Wo13StructuralRole.SESSION_STRUCTURAL_LOW,
        Wo13StructuralRole.GOVERNED_STRUCTURAL_BARRIER,
    }:
        return (
            candidate.candidate.market_session_identity
            == candidate.entry_reference.market_session_identity
        )
    return candidate.candidate.market_session_identity is not None


def _reject_source_conflicts(candidates: Sequence[Wo13TargetCandidate]) -> None:
    if not _candidate_sources_consistent(candidates):
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.CANDIDATE_SOURCE_CONFLICT
        )


def _candidate_sources_consistent(
    candidates: Sequence[Wo13TargetCandidate],
) -> bool:
    seen: dict[str, tuple[str, object, object]] = {}
    for item in candidates:
        fact = item.candidate
        value = (fact.source_evidence_integrity, fact.price, fact.structural_role)
        previous = seen.get(fact.source_evidence_identity)
        if previous is not None and previous != value:
            return False
        seen[fact.source_evidence_identity] = value
    return True


def _ordered_candidates(
    values: Sequence[Wo13TargetCandidate],
) -> tuple[Wo13TargetCandidate, ...]:
    if any(type(item) is not Wo13TargetCandidate for item in values):
        raise Wo13TargetSelectionRejected(
            Wo13TargetSelectionFailure.POPULATION_INVALID
        )
    return tuple(sorted(values, key=lambda item: item.candidate_identity))


def _candidate_sources(
    candidates: Sequence[Wo13TargetCandidate],
) -> tuple[tuple[str, str], ...]:
    retained: dict[str, str] = {}
    for item in candidates:
        fact = item.candidate
        previous = retained.get(fact.source_evidence_identity)
        if previous is not None and previous != fact.source_evidence_integrity:
            raise Wo13TargetSelectionRejected(
                Wo13TargetSelectionFailure.CANDIDATE_SOURCE_CONFLICT
            )
        retained[fact.source_evidence_identity] = fact.source_evidence_integrity
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


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


__all__ = [
    "WO13_ELIGIBLE_TARGET_CONSTRAINT_ROLES",
    "WO13_TARGET_CONSTRAINT_POPULATION_IDENTITY",
    "WO13_TARGET_SELECTION_IDENTITY",
    "Wo13CanonicalTargetSelection",
    "Wo13TargetConstraintPopulation",
    "Wo13TargetPopulationCompleteness",
    "Wo13TargetSelectionDisposition",
    "Wo13TargetSelectionFailure",
    "Wo13TargetSelectionRejected",
    "create_wo13_target_constraint_population",
    "finalize_wo13_canonical_target",
]
