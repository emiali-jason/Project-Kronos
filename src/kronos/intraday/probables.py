"""Governed V0 Intraday Probables methodology and immutable run contracts.

The V0 result means only that a governed Native member satisfies the frozen
conditions for deeper KRONOS review.  It is not Analytical Promotion, a trade,
Risk permission, Entry Timing, a Sponsor position, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Iterable, Mapping, Sequence

from kronos.intraday.historical_semantic import (
    SemanticAvailability,
    SemanticDirection,
    SemanticFactFamily,
    SemanticQualificationEvidence,
    SemanticQualificationFact,
)
from kronos.intraday.qualification import NarrowCprFact


PROBABLES_METHODOLOGY_IDENTITY = "KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V1"
PROBABLE_RESULT_IDENTITY = "KRONOS-INTRADAY-PROBABLE-V1"
PROBABLES_RUN_IDENTITY = "KRONOS-INTRADAY-PROBABLES-RUN-V1"
POPULATION_DIAGNOSTICS_IDENTITY = (
    "KRONOS-INTRADAY-PROBABLES-POPULATION-DIAGNOSTICS-V1"
)
PART3_CONTRACT_VERSION = "1.0.0"
VARIANT_G_EVIDENCE_IDENTITY = "KRONOS-WO-06S-VARIANT-G-REAL-EVIDENCE-FREEZE"
OUTCOME_EVIDENCE_STATE = "ABSENT_PENDING"


class ProbablesFailure(StrEnum):
    INPUT_INVALID = "PROBABLES_INPUT_INVALID"
    LOOK_AHEAD = "PROBABLES_LOOK_AHEAD_REJECTED"
    LINEAGE_INCOMPLETE = "PROBABLES_LINEAGE_INCOMPLETE"
    INTEGRITY_INVALID = "PROBABLES_INTEGRITY_INVALID"
    PERSISTENCE_CONFLICT = "PROBABLES_PERSISTENCE_CONFLICT"
    ARTIFACT_UNAVAILABLE = "PROBABLES_ARTIFACT_UNAVAILABLE"


class ProbablesError(RuntimeError):
    def __init__(self, failure: ProbablesFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class ProbablesStage(StrEnum):
    FACTUAL_ELIGIBILITY = "FACTUAL_ELIGIBILITY"
    NARROW_CPR_ADMISSION_SUPPORT = "NARROW_CPR_ADMISSION_SUPPORT"
    ONE_HOUR_DIRECTIONAL_REGIME = "ONE_HOUR_DIRECTIONAL_REGIME"
    FIFTEEN_MINUTE_DIRECTIONAL_STRUCTURE = (
        "FIFTEEN_MINUTE_DIRECTIONAL_STRUCTURE"
    )
    DIRECTION_COHERENCE = "DIRECTION_COHERENCE"
    PARTICIPATION_SUPPORT = "PARTICIPATION_SUPPORT"
    DIRECTIONAL_PROBABLE_OUTPUT = "DIRECTIONAL_PROBABLE_OUTPUT"


class ProductionEvidenceRole(StrEnum):
    ADMISSION_SUPPORT_REQUIRED = "ADMISSION_SUPPORT_REQUIRED"
    MANDATORY = "MANDATORY"
    SUPPORTING_NON_BLOCKING = "SUPPORTING_NON_BLOCKING"
    INFORMATIONAL = "INFORMATIONAL"


class ProbableState(StrEnum):
    LONG_PROBABLE = "LONG_PROBABLE"
    SHORT_PROBABLE = "SHORT_PROBABLE"
    NOT_ADMITTED = "NOT_ADMITTED"
    UNAVAILABLE = "UNAVAILABLE"


class ProbableReason(StrEnum):
    V0_CONDITIONS_SATISFIED = "V0_CONDITIONS_SATISFIED"
    NARROW_CPR_NOT_SATISFIED = "NARROW_CPR_NOT_SATISFIED"
    ONE_HOUR_NON_DIRECTIONAL = "ONE_HOUR_NON_DIRECTIONAL"
    FIFTEEN_MINUTE_NON_DIRECTIONAL = "FIFTEEN_MINUTE_NON_DIRECTIONAL"
    DIRECTION_CONFLICTING = "DIRECTION_CONFLICTING"
    DIRECTION_COHERENCE_NOT_SATISFIED = (
        "DIRECTION_COHERENCE_NOT_SATISFIED"
    )
    PREREQUISITE_UNAVAILABLE = "PREREQUISITE_UNAVAILABLE"
    PROVIDER_FACT_UNAVAILABLE = "PROVIDER_FACT_UNAVAILABLE"
    NARROW_CPR_UNAVAILABLE = "NARROW_CPR_UNAVAILABLE"
    ONE_HOUR_FACT_UNAVAILABLE = "ONE_HOUR_FACT_UNAVAILABLE"
    FIFTEEN_MINUTE_FACT_UNAVAILABLE = "FIFTEEN_MINUTE_FACT_UNAVAILABLE"
    SEMANTIC_FACT_UNAVAILABLE = "SEMANTIC_FACT_UNAVAILABLE"


class PopulationBucket(StrEnum):
    ZERO = "0"
    ONE_TO_FIVE = "1-5"
    SIX_TO_TEN = "6-10"
    ELEVEN_TO_FIFTEEN = "11-15"
    SIXTEEN_TO_NINETEEN = "16-19"
    TWENTY_PLUS = "20+"


class FactualSourceKind(StrEnum):
    NATIVE_DISCOVERY = "NATIVE_DISCOVERY"
    HISTORICAL_REPRODUCTION = "HISTORICAL_REPRODUCTION"


@dataclass(frozen=True, slots=True)
class ProbablesMethodologyPublication:
    publication_identity: str
    methodology_identity: str
    methodology_version: str
    evidence_basis_identity: str
    stages: tuple[ProbablesStage, ...]
    evidence_roles: tuple[tuple[str, ProductionEvidenceRole], ...]
    outcome_evidence_state: str
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        if (
            not self.publication_identity.startswith("INTRADAY-PROBABLES-METHODOLOGY-")
            or self.methodology_identity != PROBABLES_METHODOLOGY_IDENTITY
            or self.methodology_version != PART3_CONTRACT_VERSION
            or self.evidence_basis_identity != VARIANT_G_EVIDENCE_IDENTITY
            or self.stages != tuple(ProbablesStage)
            or self.evidence_roles != (
                ("NARROW_CPR", ProductionEvidenceRole.ADMISSION_SUPPORT_REQUIRED),
                ("1H_REGIME", ProductionEvidenceRole.MANDATORY),
                ("15M_STRUCTURE", ProductionEvidenceRole.MANDATORY),
                ("DIRECTION_COHERENCE", ProductionEvidenceRole.MANDATORY),
                ("VOLUME_PARTICIPATION", ProductionEvidenceRole.SUPPORTING_NON_BLOCKING),
                ("1D_5M_LEVEL_RELATIONSHIPS", ProductionEvidenceRole.INFORMATIONAL),
            )
            or self.outcome_evidence_state != OUTCOME_EVIDENCE_STATE
            or not _texts(self.provenance)
        ):
            raise ProbablesError(ProbablesFailure.INPUT_INVALID)
        _verify(
            self,
            "publication_identity",
            "INTRADAY-PROBABLES-METHODOLOGY-",
            "INTEGRITY-PROBABLES-METHODOLOGY-",
        )


def create_v0_probables_methodology() -> ProbablesMethodologyPublication:
    values = {
        "methodology_identity": PROBABLES_METHODOLOGY_IDENTITY,
        "methodology_version": PART3_CONTRACT_VERSION,
        "evidence_basis_identity": VARIANT_G_EVIDENCE_IDENTITY,
        "stages": tuple(ProbablesStage),
        "evidence_roles": (
            ("NARROW_CPR", ProductionEvidenceRole.ADMISSION_SUPPORT_REQUIRED),
            ("1H_REGIME", ProductionEvidenceRole.MANDATORY),
            ("15M_STRUCTURE", ProductionEvidenceRole.MANDATORY),
            ("DIRECTION_COHERENCE", ProductionEvidenceRole.MANDATORY),
            ("VOLUME_PARTICIPATION", ProductionEvidenceRole.SUPPORTING_NON_BLOCKING),
            ("1D_5M_LEVEL_RELATIONSHIPS", ProductionEvidenceRole.INFORMATIONAL),
        ),
        "outcome_evidence_state": OUTCOME_EVIDENCE_STATE,
        "provenance": (
            "KRONOS-WO-06-PART-3-VARIANT-G-FREEZE",
            "WO-06S-SESSIONS=2026-08-17..2026-08-21",
            "OUTCOME_EVIDENCE=ABSENT_PENDING",
            "PAPER_OBSERVATION_AND_DEEPER_REVIEW_ONLY",
        ),
    }
    return ProbablesMethodologyPublication(
        publication_identity=_identity("INTRADAY-PROBABLES-METHODOLOGY-", values),
        integrity_identity=_identity("INTEGRITY-PROBABLES-METHODOLOGY-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class ProbablesMemberEvidence:
    universe_member_identity: str
    canonical_subject_identity: str
    market_session_identity: str
    observation_boundary: datetime
    source_kind: FactualSourceKind
    source_run_identity: str
    source_member_identity: str
    narrow_cpr_fact: NarrowCprFact | None
    semantic_evidence: SemanticQualificationEvidence
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        facts = self.fact_map
        if (
            not _texts((
                self.universe_member_identity,
                self.canonical_subject_identity,
                self.market_session_identity,
                self.source_run_identity,
                self.source_member_identity,
            ))
            or not _aware(self.observation_boundary)
            or type(self.source_kind) is not FactualSourceKind
            or (
                self.source_kind is FactualSourceKind.NATIVE_DISCOVERY
                and (
                    not self.source_run_identity.startswith("INTRADAY-DISCOVERY-RUN-")
                    or not self.source_member_identity.startswith("INTRADAY-DISCOVERY-RESULT")
                )
            )
            or (
                self.source_kind is FactualSourceKind.HISTORICAL_REPRODUCTION
                and (
                    not self.source_run_identity.startswith(
                        "INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-"
                    )
                    or not self.source_member_identity.startswith(
                        "INTRADAY-HISTORICAL-FACT-BUNDLE-"
                    )
                )
            )
            or (
                self.narrow_cpr_fact is not None
                and type(self.narrow_cpr_fact) is not NarrowCprFact
            )
            or type(self.semantic_evidence) is not SemanticQualificationEvidence
            or self.semantic_evidence.canonical_subject_identity
            != self.canonical_subject_identity
            or self.semantic_evidence.market_session_identity
            != self.market_session_identity
            or self.semantic_evidence.observation_boundary != self.observation_boundary
            or set(facts) != set(SemanticFactFamily)
            or any(item.available_at > self.observation_boundary for item in facts.values())
            or (
                self.narrow_cpr_fact is not None
                and (
                    self.narrow_cpr_fact.canonical_subject_identity
                    != self.canonical_subject_identity
                    or self.narrow_cpr_fact.observation_boundary
                    > self.observation_boundary
                )
            )
            or not _texts(self.provenance)
        ):
            raise ProbablesError(ProbablesFailure.LOOK_AHEAD)

    @property
    def fact_map(self) -> dict[SemanticFactFamily, SemanticQualificationFact]:
        return {item.family: item for item in self.semantic_evidence.facts}


@dataclass(frozen=True, slots=True)
class ProbablesUnavailableMember:
    universe_member_identity: str
    canonical_subject_identity: str
    market_session_identity: str
    observation_boundary: datetime
    reason: ProbableReason
    source_identity: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not _texts((
                self.universe_member_identity,
                self.canonical_subject_identity,
                self.market_session_identity,
                self.source_identity,
            ))
            or not _aware(self.observation_boundary)
            or self.reason not in (
                ProbableReason.PREREQUISITE_UNAVAILABLE,
                ProbableReason.PROVIDER_FACT_UNAVAILABLE,
                ProbableReason.SEMANTIC_FACT_UNAVAILABLE,
            )
            or not _texts(self.provenance)
        ):
            raise ProbablesError(ProbablesFailure.INPUT_INVALID)


@dataclass(frozen=True, slots=True)
class ProbableEvidenceLineage:
    source_kind: FactualSourceKind
    source_run_identity: str
    source_member_identity: str
    semantic_evidence_identity: str | None
    narrow_cpr_fact_identity: str | None
    one_hour_fact_identity: str | None
    fifteen_minute_fact_identity: str | None
    coherence_fact_identity: str | None
    participation_fact_identity: str | None
    informational_fact_identities: tuple[str, ...]
    source_identity: str | None

    def __post_init__(self) -> None:
        required = (self.source_run_identity, self.source_member_identity)
        if (
            type(self.source_kind) is not FactualSourceKind
            or not _texts(required)
            or any(value is not None and not _text(value) for value in (
                self.semantic_evidence_identity,
                self.narrow_cpr_fact_identity,
                self.one_hour_fact_identity,
                self.fifteen_minute_fact_identity,
                self.coherence_fact_identity,
                self.participation_fact_identity,
                self.source_identity,
            ))
            or any(not _text(value) for value in self.informational_fact_identities)
        ):
            raise ProbablesError(ProbablesFailure.LINEAGE_INCOMPLETE)


@dataclass(frozen=True, slots=True)
class ProbableMemberResult:
    result_identity: str
    universe_member_identity: str
    canonical_subject_identity: str
    market_session_identity: str
    observation_boundary: datetime
    methodology_identity: str
    methodology_version: str
    state: ProbableState
    direction: SemanticDirection | None
    reasons: tuple[ProbableReason, ...]
    completed_stages: tuple[ProbablesStage, ...]
    participation_state: str
    lineage: ProbableEvidenceLineage
    execution_eligibility: str
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = PROBABLE_RESULT_IDENTITY
    schema_version: str = PART3_CONTRACT_VERSION

    def __post_init__(self) -> None:
        admitted = self.state in (ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE)
        if (
            not self.result_identity.startswith("INTRADAY-PROBABLE-RESULT-")
            or not _texts((
                self.universe_member_identity,
                self.canonical_subject_identity,
                self.market_session_identity,
                self.methodology_identity,
                self.methodology_version,
                self.participation_state,
            ))
            or not _aware(self.observation_boundary)
            or type(self.state) is not ProbableState
            or self.direction is not None and type(self.direction) is not SemanticDirection
            or not self.reasons
            or any(type(item) is not ProbableReason for item in self.reasons)
            or any(type(item) is not ProbablesStage for item in self.completed_stages)
            or len(set(self.completed_stages)) != len(self.completed_stages)
            or type(self.lineage) is not ProbableEvidenceLineage
            or self.execution_eligibility != "NOT_ESTABLISHED"
            or not _texts(self.provenance)
            or self.schema_identity != PROBABLE_RESULT_IDENTITY
            or self.schema_version != PART3_CONTRACT_VERSION
            or admitted != (self.direction in (SemanticDirection.LONG, SemanticDirection.SHORT))
            or (admitted and len(self.completed_stages) != len(ProbablesStage))
            or (
                admitted
                and any(value is None for value in (
                    self.lineage.semantic_evidence_identity,
                    self.lineage.narrow_cpr_fact_identity,
                    self.lineage.one_hour_fact_identity,
                    self.lineage.fifteen_minute_fact_identity,
                    self.lineage.coherence_fact_identity,
                    self.lineage.participation_fact_identity,
                ))
            )
        ):
            raise ProbablesError(ProbablesFailure.LINEAGE_INCOMPLETE)
        _verify(
            self,
            "result_identity",
            "INTRADAY-PROBABLE-RESULT-",
            "INTEGRITY-PROBABLE-RESULT-",
        )


@dataclass(frozen=True, slots=True)
class ProbablesPopulationDiagnostics:
    diagnostics_identity: str
    starting_population: int
    evaluable_count: int
    unavailable_count: int
    long_probables: int
    short_probables: int
    total_probables: int
    not_admitted_count: int
    conflicting_count: int
    retention: str
    attrition: str
    population_bucket: PopulationBucket
    stage_survivor_counts: tuple[tuple[ProbablesStage, int], ...]
    integrity_identity: str
    schema_identity: str = POPULATION_DIAGNOSTICS_IDENTITY
    schema_version: str = PART3_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = (
            self.starting_population,
            self.evaluable_count,
            self.unavailable_count,
            self.long_probables,
            self.short_probables,
            self.total_probables,
            self.not_admitted_count,
            self.conflicting_count,
        )
        if (
            not self.diagnostics_identity.startswith("INTRADAY-PROBABLES-DIAGNOSTICS-")
            or any(type(value) is not int or value < 0 for value in values)
            or self.starting_population != self.evaluable_count + self.unavailable_count
            or self.evaluable_count != self.total_probables + self.not_admitted_count
            or self.total_probables != self.long_probables + self.short_probables
            or not _text(self.retention)
            or not _text(self.attrition)
            or type(self.population_bucket) is not PopulationBucket
            or self.stage_survivor_counts
            != tuple((stage, count) for stage, count in self.stage_survivor_counts)
            or tuple(stage for stage, _ in self.stage_survivor_counts) != tuple(ProbablesStage)
            or any(type(count) is not int or count < 0 for _, count in self.stage_survivor_counts)
            or self.schema_identity != POPULATION_DIAGNOSTICS_IDENTITY
            or self.schema_version != PART3_CONTRACT_VERSION
        ):
            raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)
        _verify(
            self,
            "diagnostics_identity",
            "INTRADAY-PROBABLES-DIAGNOSTICS-",
            "INTEGRITY-PROBABLES-DIAGNOSTICS-",
        )


@dataclass(frozen=True, slots=True)
class ProbablesRun:
    run_identity: str
    methodology_publication_identity: str
    methodology_identity: str
    methodology_version: str
    source_kind: FactualSourceKind
    source_run_identity: str
    universe_identity: str
    universe_version: str
    reconciliation_identity: str
    reconciliation_version: str
    market_session_identity: str
    observation_boundary: datetime
    results: tuple[ProbableMemberResult, ...]
    diagnostics: ProbablesPopulationDiagnostics
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = PROBABLES_RUN_IDENTITY
    schema_version: str = PART3_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.run_identity.startswith("INTRADAY-PROBABLES-RUN-")
            or not _texts((
                self.methodology_publication_identity,
                self.methodology_identity,
                self.methodology_version,
                self.source_run_identity,
                self.universe_identity,
                self.universe_version,
                self.reconciliation_identity,
                self.reconciliation_version,
                self.market_session_identity,
            ))
            or type(self.source_kind) is not FactualSourceKind
            or not _aware(self.observation_boundary)
            or not self.results
            or any(type(item) is not ProbableMemberResult for item in self.results)
            or len({item.universe_member_identity for item in self.results}) != len(self.results)
            or tuple(sorted(self.results, key=lambda item: item.universe_member_identity))
            != self.results
            or any(item.observation_boundary > self.observation_boundary for item in self.results)
            or type(self.diagnostics) is not ProbablesPopulationDiagnostics
            or self.diagnostics.starting_population != len(self.results)
            or not _texts(self.provenance)
            or self.schema_identity != PROBABLES_RUN_IDENTITY
            or self.schema_version != PART3_CONTRACT_VERSION
        ):
            raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)
        _verify(
            self,
            "run_identity",
            "INTRADAY-PROBABLES-RUN-",
            "INTEGRITY-PROBABLES-RUN-",
        )


def evaluate_probables_run(
    *,
    methodology: ProbablesMethodologyPublication,
    source_kind: FactualSourceKind,
    source_run_identity: str,
    universe_identity: str,
    universe_version: str,
    reconciliation_identity: str,
    reconciliation_version: str,
    market_session_identity: str,
    observation_boundary: datetime,
    member_evidence: Sequence[ProbablesMemberEvidence],
    unavailable_members: Sequence[ProbablesUnavailableMember],
    provenance: tuple[str, ...],
) -> ProbablesRun:
    evidence = tuple(member_evidence)
    unavailable = tuple(unavailable_members)
    if (
        type(methodology) is not ProbablesMethodologyPublication
        or methodology != create_v0_probables_methodology()
        or type(source_kind) is not FactualSourceKind
        or not _texts((
            source_run_identity,
            universe_identity,
            universe_version,
            reconciliation_identity,
            reconciliation_version,
            market_session_identity,
        ))
        or not _aware(observation_boundary)
        or any(type(item) is not ProbablesMemberEvidence for item in evidence)
        or any(type(item) is not ProbablesUnavailableMember for item in unavailable)
        or any(item.source_kind is not source_kind for item in evidence)
        or any(item.source_run_identity != source_run_identity for item in evidence)
        or any(item.observation_boundary > observation_boundary for item in (*evidence, *unavailable))
        or not _texts(provenance)
    ):
        raise ProbablesError(ProbablesFailure.INPUT_INVALID)
    identities = tuple(item.universe_member_identity for item in (*evidence, *unavailable))
    canonicals = tuple(item.canonical_subject_identity for item in (*evidence, *unavailable))
    if not identities or len(set(identities)) != len(identities) or len(set(canonicals)) != len(canonicals):
        raise ProbablesError(ProbablesFailure.INPUT_INVALID)

    results = tuple(sorted(
        (
            *(_evaluate_member(methodology, item, provenance) for item in evidence),
            *(_unavailable_result(methodology, item, source_kind, source_run_identity, provenance) for item in unavailable),
        ),
        key=lambda item: item.universe_member_identity,
    ))
    diagnostics = _diagnostics(results)
    values = {
        "methodology_publication_identity": methodology.publication_identity,
        "methodology_identity": methodology.methodology_identity,
        "methodology_version": methodology.methodology_version,
        "source_kind": source_kind,
        "source_run_identity": source_run_identity,
        "universe_identity": universe_identity,
        "universe_version": universe_version,
        "reconciliation_identity": reconciliation_identity,
        "reconciliation_version": reconciliation_version,
        "market_session_identity": market_session_identity,
        "observation_boundary": observation_boundary,
        "results": results,
        "diagnostics": diagnostics,
        "provenance": provenance,
        "schema_identity": PROBABLES_RUN_IDENTITY,
        "schema_version": PART3_CONTRACT_VERSION,
    }
    return ProbablesRun(
        run_identity=_identity("INTRADAY-PROBABLES-RUN-", values),
        integrity_identity=_identity("INTEGRITY-PROBABLES-RUN-", values),
        **values,
    )


def _evaluate_member(
    methodology: ProbablesMethodologyPublication,
    item: ProbablesMemberEvidence,
    provenance: tuple[str, ...],
) -> ProbableMemberResult:
    facts = item.fact_map
    hourly = facts[SemanticFactFamily.HOURLY_REGIME]
    fifteen = facts[SemanticFactFamily.FIFTEEN_MINUTE_STRUCTURE]
    coherence = facts[SemanticFactFamily.DIRECTIONAL_COHERENCE]
    participation = facts[SemanticFactFamily.VOLUME_PARTICIPATION]
    completed = [ProbablesStage.FACTUAL_ELIGIBILITY]
    state = ProbableState.NOT_ADMITTED
    direction: SemanticDirection | None = None

    if item.narrow_cpr_fact is None:
        reason = ProbableReason.NARROW_CPR_UNAVAILABLE
        state = ProbableState.UNAVAILABLE
    elif not item.narrow_cpr_fact.narrow_cpr_kgs_v0:
        reason = ProbableReason.NARROW_CPR_NOT_SATISFIED
    else:
        completed.append(ProbablesStage.NARROW_CPR_ADMISSION_SUPPORT)
        reason, state = _direction_fact_failure(
            hourly,
            unavailable=ProbableReason.ONE_HOUR_FACT_UNAVAILABLE,
            non_directional=ProbableReason.ONE_HOUR_NON_DIRECTIONAL,
        )
        if reason is None:
            completed.append(ProbablesStage.ONE_HOUR_DIRECTIONAL_REGIME)
            reason, state = _direction_fact_failure(
                fifteen,
                unavailable=ProbableReason.FIFTEEN_MINUTE_FACT_UNAVAILABLE,
                non_directional=ProbableReason.FIFTEEN_MINUTE_NON_DIRECTIONAL,
            )
        if reason is None:
            completed.append(ProbablesStage.FIFTEEN_MINUTE_DIRECTIONAL_STRUCTURE)
            if hourly.direction is not fifteen.direction:
                reason = ProbableReason.DIRECTION_CONFLICTING
            elif coherence.availability is SemanticAvailability.UNAVAILABLE:
                reason = ProbableReason.SEMANTIC_FACT_UNAVAILABLE
                state = ProbableState.UNAVAILABLE
            elif coherence.direction is SemanticDirection.CONFLICTING:
                reason = ProbableReason.DIRECTION_CONFLICTING
            elif coherence.direction is not hourly.direction:
                reason = ProbableReason.DIRECTION_COHERENCE_NOT_SATISFIED
            else:
                completed.extend((
                    ProbablesStage.DIRECTION_COHERENCE,
                    ProbablesStage.PARTICIPATION_SUPPORT,
                    ProbablesStage.DIRECTIONAL_PROBABLE_OUTPUT,
                ))
                direction = hourly.direction
                state = (
                    ProbableState.LONG_PROBABLE
                    if direction is SemanticDirection.LONG
                    else ProbableState.SHORT_PROBABLE
                )
                reason = ProbableReason.V0_CONDITIONS_SATISFIED

    info = tuple(
        facts[family].fact_identity
        for family in (
            SemanticFactFamily.DAILY_CONTEXT,
            SemanticFactFamily.FIVE_MINUTE_PROGRESSION,
            SemanticFactFamily.PDH_PDL_RELATIONSHIP,
            SemanticFactFamily.CPR_LOCATION,
            SemanticFactFamily.CLASSIC_PIVOT_RELATIONSHIPS,
        )
    )
    lineage = ProbableEvidenceLineage(
        source_kind=item.source_kind,
        source_run_identity=item.source_run_identity,
        source_member_identity=item.source_member_identity,
        semantic_evidence_identity=item.semantic_evidence.evidence_identity,
        narrow_cpr_fact_identity=(
            None if item.narrow_cpr_fact is None else item.narrow_cpr_fact.fact_identity
        ),
        one_hour_fact_identity=hourly.fact_identity,
        fifteen_minute_fact_identity=fifteen.fact_identity,
        coherence_fact_identity=coherence.fact_identity,
        participation_fact_identity=participation.fact_identity,
        informational_fact_identities=info,
        source_identity=None,
    )
    participation_state = (
        "UNAVAILABLE"
        if participation.availability is SemanticAvailability.UNAVAILABLE
        else dict(participation.attributes).get(
            "current_vs_previous_completed_volume", "AVAILABLE"
        )
    )
    return _member_result(
        methodology=methodology,
        universe_member_identity=item.universe_member_identity,
        canonical_subject_identity=item.canonical_subject_identity,
        market_session_identity=item.market_session_identity,
        observation_boundary=item.observation_boundary,
        state=state,
        direction=direction,
        reasons=(reason,),
        completed_stages=tuple(completed),
        participation_state=participation_state,
        lineage=lineage,
        provenance=(*provenance, *item.provenance),
    )


def _direction_fact_failure(
    fact: SemanticQualificationFact,
    *,
    unavailable: ProbableReason,
    non_directional: ProbableReason,
) -> tuple[ProbableReason | None, ProbableState]:
    if fact.availability is SemanticAvailability.UNAVAILABLE:
        return unavailable, ProbableState.UNAVAILABLE
    if fact.direction not in (SemanticDirection.LONG, SemanticDirection.SHORT):
        return non_directional, ProbableState.NOT_ADMITTED
    return None, ProbableState.NOT_ADMITTED


def _unavailable_result(
    methodology: ProbablesMethodologyPublication,
    item: ProbablesUnavailableMember,
    source_kind: FactualSourceKind,
    source_run_identity: str,
    provenance: tuple[str, ...],
) -> ProbableMemberResult:
    lineage = ProbableEvidenceLineage(
        source_kind=source_kind,
        source_run_identity=source_run_identity,
        source_member_identity=item.source_identity,
        semantic_evidence_identity=None,
        narrow_cpr_fact_identity=None,
        one_hour_fact_identity=None,
        fifteen_minute_fact_identity=None,
        coherence_fact_identity=None,
        participation_fact_identity=None,
        informational_fact_identities=(),
        source_identity=item.source_identity,
    )
    return _member_result(
        methodology=methodology,
        universe_member_identity=item.universe_member_identity,
        canonical_subject_identity=item.canonical_subject_identity,
        market_session_identity=item.market_session_identity,
        observation_boundary=item.observation_boundary,
        state=ProbableState.UNAVAILABLE,
        direction=None,
        reasons=(item.reason,),
        completed_stages=(),
        participation_state="UNAVAILABLE",
        lineage=lineage,
        provenance=(*provenance, *item.provenance),
    )


def _member_result(**values: object) -> ProbableMemberResult:
    methodology = values.pop("methodology", None)
    if type(methodology) is not ProbablesMethodologyPublication:
        raise ProbablesError(ProbablesFailure.INPUT_INVALID)
    payload = {
        **values,
        "methodology_identity": methodology.methodology_identity,
        "methodology_version": methodology.methodology_version,
        "execution_eligibility": "NOT_ESTABLISHED",
        "schema_identity": PROBABLE_RESULT_IDENTITY,
        "schema_version": PART3_CONTRACT_VERSION,
    }
    return ProbableMemberResult(
        result_identity=_identity("INTRADAY-PROBABLE-RESULT-", payload),
        integrity_identity=_identity("INTEGRITY-PROBABLE-RESULT-", payload),
        **payload,
    )


def _diagnostics(results: tuple[ProbableMemberResult, ...]) -> ProbablesPopulationDiagnostics:
    long_count = sum(item.state is ProbableState.LONG_PROBABLE for item in results)
    short_count = sum(item.state is ProbableState.SHORT_PROBABLE for item in results)
    unavailable = sum(item.state is ProbableState.UNAVAILABLE for item in results)
    not_admitted = sum(item.state is ProbableState.NOT_ADMITTED for item in results)
    total = long_count + short_count
    evaluable = len(results) - unavailable
    stage_counts = tuple(
        (stage, sum(stage in item.completed_stages for item in results))
        for stage in ProbablesStage
    )
    values = {
        "starting_population": len(results),
        "evaluable_count": evaluable,
        "unavailable_count": unavailable,
        "long_probables": long_count,
        "short_probables": short_count,
        "total_probables": total,
        "not_admitted_count": not_admitted,
        "conflicting_count": sum(
            ProbableReason.DIRECTION_CONFLICTING in item.reasons for item in results
        ),
        "retention": _ratio(total, len(results)),
        "attrition": _ratio(len(results) - total, len(results)),
        "population_bucket": _population_bucket(total),
        "stage_survivor_counts": stage_counts,
        "schema_identity": POPULATION_DIAGNOSTICS_IDENTITY,
        "schema_version": PART3_CONTRACT_VERSION,
    }
    return ProbablesPopulationDiagnostics(
        diagnostics_identity=_identity("INTRADAY-PROBABLES-DIAGNOSTICS-", values),
        integrity_identity=_identity("INTEGRITY-PROBABLES-DIAGNOSTICS-", values),
        **values,
    )


def _ratio(numerator: int, denominator: int) -> str:
    return "0" if denominator == 0 else f"{numerator}/{denominator}"


def _population_bucket(count: int) -> PopulationBucket:
    if count == 0:
        return PopulationBucket.ZERO
    if count <= 5:
        return PopulationBucket.ONE_TO_FIVE
    if count <= 10:
        return PopulationBucket.SIX_TO_TEN
    if count <= 15:
        return PopulationBucket.ELEVEN_TO_FIFTEEN
    if count <= 19:
        return PopulationBucket.SIXTEEN_TO_NINETEEN
    return PopulationBucket.TWENTY_PLUS


def probables_artifact_document(value: object) -> dict[str, object]:
    artifact_identity = _artifact_identity(value)
    core = {
        "artifact_type": type(value).__name__,
        "artifact_identity": artifact_identity,
        "artifact": _normalize(value),
    }
    return {**core, "document_integrity": _identity("INTEGRITY-PROBABLES-DOCUMENT-", core)}


def probables_artifact_bytes(value: object) -> bytes:
    return _encode(probables_artifact_document(value)) + b"\n"


def probables_artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID) from error
    verify_probables_artifact_document(document)
    artifact = document.get("artifact")
    if not isinstance(artifact, Mapping):
        raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)
    artifact_type = document.get("artifact_type")
    if artifact_type == "ProbablesMethodologyPublication":
        return _methodology_from_data(artifact)
    if artifact_type == "ProbableMemberResult":
        return _result_from_data(artifact)
    if artifact_type == "ProbablesPopulationDiagnostics":
        return _diagnostics_from_data(artifact)
    if artifact_type == "ProbablesRun":
        return _run_from_data(artifact)
    raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)


def verify_probables_artifact_document(document: Mapping[str, object]) -> None:
    core = {key: document.get(key) for key in ("artifact_type", "artifact_identity", "artifact")}
    if document.get("document_integrity") != _identity("INTEGRITY-PROBABLES-DOCUMENT-", core):
        raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)


def _artifact_identity(value: object) -> str:
    if type(value) is ProbablesMethodologyPublication:
        return value.publication_identity
    if type(value) is ProbableMemberResult:
        return value.result_identity
    if type(value) is ProbablesPopulationDiagnostics:
        return value.diagnostics_identity
    if type(value) is ProbablesRun:
        return value.run_identity
    raise ProbablesError(ProbablesFailure.INPUT_INVALID)


def _methodology_from_data(data: Mapping[str, object]) -> ProbablesMethodologyPublication:
    values = dict(data)
    values["stages"] = tuple(ProbablesStage(item) for item in values["stages"])
    values["evidence_roles"] = tuple(
        (name, ProductionEvidenceRole(role)) for name, role in values["evidence_roles"]
    )
    values["provenance"] = tuple(values["provenance"])
    return ProbablesMethodologyPublication(**values)


def _lineage_from_data(data: Mapping[str, object]) -> ProbableEvidenceLineage:
    values = dict(data)
    values["source_kind"] = FactualSourceKind(values["source_kind"])
    values["informational_fact_identities"] = tuple(values["informational_fact_identities"])
    return ProbableEvidenceLineage(**values)


def _result_from_data(data: Mapping[str, object]) -> ProbableMemberResult:
    values = dict(data)
    values["observation_boundary"] = datetime.fromisoformat(str(values["observation_boundary"]))
    values["state"] = ProbableState(values["state"])
    values["direction"] = None if values["direction"] is None else SemanticDirection(values["direction"])
    values["reasons"] = tuple(ProbableReason(item) for item in values["reasons"])
    values["completed_stages"] = tuple(ProbablesStage(item) for item in values["completed_stages"])
    values["lineage"] = _lineage_from_data(values["lineage"])
    values["provenance"] = tuple(values["provenance"])
    return ProbableMemberResult(**values)


def _diagnostics_from_data(data: Mapping[str, object]) -> ProbablesPopulationDiagnostics:
    values = dict(data)
    values["population_bucket"] = PopulationBucket(values["population_bucket"])
    values["stage_survivor_counts"] = tuple(
        (ProbablesStage(stage), int(count)) for stage, count in values["stage_survivor_counts"]
    )
    return ProbablesPopulationDiagnostics(**values)


def _run_from_data(data: Mapping[str, object]) -> ProbablesRun:
    values = dict(data)
    values["source_kind"] = FactualSourceKind(values["source_kind"])
    values["observation_boundary"] = datetime.fromisoformat(str(values["observation_boundary"]))
    values["results"] = tuple(_result_from_data(item) for item in values["results"])
    values["diagnostics"] = _diagnostics_from_data(values["diagnostics"])
    values["provenance"] = tuple(values["provenance"])
    return ProbablesRun(**values)


def _verify(value: object, identity_name: str, identity_prefix: str, integrity_prefix: str) -> None:
    payload = asdict(value)
    payload.pop(identity_name)
    payload.pop("integrity_identity")
    if getattr(value, identity_name) != _identity(identity_prefix, payload):
        raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)
    if value.integrity_identity != _identity(integrity_prefix, payload):
        raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Iterable[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


__all__ = [
    "OUTCOME_EVIDENCE_STATE",
    "PART3_CONTRACT_VERSION",
    "POPULATION_DIAGNOSTICS_IDENTITY",
    "PROBABLE_RESULT_IDENTITY",
    "PROBABLES_METHODOLOGY_IDENTITY",
    "PROBABLES_RUN_IDENTITY",
    "FactualSourceKind",
    "PopulationBucket",
    "ProbableEvidenceLineage",
    "ProbableMemberResult",
    "ProbableReason",
    "ProbableState",
    "ProbablesError",
    "ProbablesFailure",
    "ProbablesMemberEvidence",
    "ProbablesMethodologyPublication",
    "ProbablesPopulationDiagnostics",
    "ProbablesRun",
    "ProbablesStage",
    "ProbablesUnavailableMember",
    "ProductionEvidenceRole",
    "create_v0_probables_methodology",
    "evaluate_probables_run",
    "probables_artifact_bytes",
    "probables_artifact_document",
    "probables_artifact_from_bytes",
    "verify_probables_artifact_document",
]
