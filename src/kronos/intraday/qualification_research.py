"""WO-06 Part-2 deterministic Probables-methodology research contracts.

The contracts in this module compare explicit, versioned qualification
variants.  They never emit a production Discovery candidate, rank a member,
or create trading, Risk, execution, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from statistics import median
from typing import Iterable, Mapping

from kronos.intraday.qualification import (
    QualificationCorpus,
    QualificationError,
    QualificationEvidenceSource,
    QualificationEvidenceSufficiency,
    QualificationFailure,
)


METHODOLOGY_RESEARCH_IDENTITY = (
    "KRONOS-INTRADAY-PROBABLES-METHODOLOGY-RESEARCH-V0"
)
METHODOLOGY_VARIANT_IDENTITY = (
    "KRONOS-INTRADAY-PROBABLES-METHODOLOGY-VARIANT-V0"
)
RESEARCH_RESULT_IDENTITY = "KRONOS-INTRADAY-PROBABLE-RESEARCH-RESULT-V0"
COMPARISON_REPORT_IDENTITY = (
    "KRONOS-INTRADAY-METHODOLOGY-COMPARISON-REPORT-V0"
)
OUTCOME_MEASUREMENT_IDENTITY = (
    "KRONOS-INTRADAY-QUALIFICATION-OUTCOME-MEASUREMENT-V0"
)
REAL_CORPUS_BINDING_IDENTITY = (
    "KRONOS-INTRADAY-REAL-DISCOVERY-CORPUS-BINDING-V0"
)
PART2_CONTRACT_VERSION = "0.1.0"


class ResearchStage(StrEnum):
    FACTUAL_ELIGIBILITY = "STAGE_0_FACTUAL_ELIGIBILITY"
    COMPRESSION_CONTEXT = "STAGE_1_COMPRESSION_CONTEXT"
    HIGHER_TIMEFRAME_REGIME = "STAGE_2_HIGHER_TIMEFRAME_REGIME"
    DEVELOPING_STRUCTURE = "STAGE_3_DEVELOPING_INTRADAY_STRUCTURE"
    PARTICIPATION = "STAGE_4_PARTICIPATION"
    PATH_EXTENSION = "STAGE_5_PATH_EXTENSION"
    DIRECTIONAL_QUALIFICATION = "STAGE_6_DIRECTIONAL_QUALIFICATION"
    RESEARCH_OUTPUT = "STAGE_7_PROBABLE_RESEARCH_OUTPUT"


STAGE_ORDER = tuple(ResearchStage)


class HypothesisFamily(StrEnum):
    NARROW_CPR = "NARROW_CPR"
    DAILY_CONTEXT = "1D_CONTEXT"
    HOURLY_REGIME = "1H_REGIME"
    FIFTEEN_MINUTE_STRUCTURE = "15M_STRUCTURE"
    FIVE_MINUTE_PROGRESSION = "5M_PROGRESSION"
    PDH_PDL = "PDH_PDL"
    CPR_LOCATION = "CPR_LOCATION"
    CLASSIC_PIVOT = "CLASSIC_PIVOT"
    STRUCTURAL_BARRIER = "STRUCTURAL_BARRIER"
    VOLUME_PARTICIPATION = "VOLUME_PARTICIPATION"
    PATH_ROOM = "PATH_ROOM"
    EXTENSION = "EXTENSION"


class EvidenceRole(StrEnum):
    MANDATORY = "MANDATORY"
    SUPPORTING = "SUPPORTING"
    VETO = "VETO"
    INFORMATIONAL = "INFORMATIONAL"


class HypothesisResult(StrEnum):
    MATCH = "HYPOTHESIS_MATCH"
    NO_MATCH = "HYPOTHESIS_NO_MATCH"
    UNAVAILABLE = "HYPOTHESIS_UNAVAILABLE"
    FACTUAL_FAILURE = "HYPOTHESIS_FACTUAL_FAILURE"


class DirectionContribution(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class ResearchDirection(StrEnum):
    LONG_HYPOTHESIS = "LONG_HYPOTHESIS"
    SHORT_HYPOTHESIS = "SHORT_HYPOTHESIS"
    NON_DIRECTIONAL = "NON_DIRECTIONAL"
    DIRECTION_CONFLICTING = "DIRECTION_CONFLICTING"
    UNAVAILABLE = "UNAVAILABLE"


class ResearchDisposition(StrEnum):
    QUALIFICATION_WOULD_PASS = "QUALIFICATION_WOULD_PASS"
    QUALIFICATION_WOULD_FAIL = "QUALIFICATION_WOULD_FAIL"
    QUALIFICATION_UNAVAILABLE = "QUALIFICATION_UNAVAILABLE"


class ResearchReason(StrEnum):
    MANDATORY_MATCH = "MANDATORY_EVIDENCE_MATCH"
    MANDATORY_NO_MATCH = "MANDATORY_EVIDENCE_NO_MATCH"
    MANDATORY_UNAVAILABLE = "MANDATORY_EVIDENCE_UNAVAILABLE"
    SUPPORT_SUFFICIENT = "SUPPORTING_EVIDENCE_SUFFICIENT"
    SUPPORT_INSUFFICIENT = "SUPPORTING_EVIDENCE_INSUFFICIENT"
    VETO_CLEAR = "VETO_EVIDENCE_CLEAR"
    VETO_MATCH = "VETO_EVIDENCE_MATCH"
    INFORMATION_RECORDED = "INFORMATIONAL_EVIDENCE_RECORDED"
    FACTUAL_FAILURE = "FACTUAL_EVIDENCE_FAILURE"
    STAGE_SURVIVED = "STAGE_SURVIVED"
    RESEARCH_ONLY = "RESEARCH_ONLY_NOT_PRODUCTION_PROBABLE"


class PopulationWarning(StrEnum):
    NONE = "NO_POPULATION_WARNING"
    STARVATION_RISK = "STARVATION_RISK"
    FLOODING_RISK = "FLOODING_RISK"
    STARVATION_AND_FLOODING_RISK = "STARVATION_AND_FLOODING_RISK"


class ResearchConclusion(StrEnum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONTINUE_QUALIFICATION = "CONTINUE_QUALIFICATION"
    PROMISING_FOR_REVIEW = "PROMISING_FOR_REVIEW"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    REQUIRES_MACHINE_FACT_ENHANCEMENT = "REQUIRES_MACHINE_FACT_ENHANCEMENT"
    READY_FOR_METHODOLOGY_FREEZE_REVIEW = "READY_FOR_METHODOLOGY_FREEZE_REVIEW"


class OutcomeDefinitionFamily(StrEnum):
    EXPANSION = "SUBSEQUENT_RANGE_EXPANSION"
    DIRECTIONAL = "SUBSEQUENT_DIRECTIONAL_MOVEMENT"


@dataclass(frozen=True, slots=True)
class ResearchHypothesis:
    hypothesis_identity: str
    hypothesis_version: str
    family: HypothesisFamily
    stage: ResearchStage
    role: EvidenceRole
    direction_contribution: DirectionContribution
    required_fact_families: tuple[str, ...]
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        if (
            not self.hypothesis_identity.startswith("INTRADAY-RESEARCH-HYPOTHESIS-")
            or not _text(self.hypothesis_version)
            or type(self.family) is not HypothesisFamily
            or type(self.stage) is not ResearchStage
            or type(self.role) is not EvidenceRole
            or type(self.direction_contribution) is not DirectionContribution
            or not _texts(self.required_fact_families)
            or not _texts(self.provenance)
            or (
                self.family is HypothesisFamily.NARROW_CPR
                and self.direction_contribution is not DirectionContribution.NONE
            )
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        _verify(self, "INTRADAY-RESEARCH-HYPOTHESIS-", "INTEGRITY-RESEARCH-HYPOTHESIS-")


def create_research_hypothesis(
    *,
    hypothesis_version: str,
    family: HypothesisFamily,
    stage: ResearchStage,
    role: EvidenceRole,
    direction_contribution: DirectionContribution,
    required_fact_families: tuple[str, ...],
    provenance: tuple[str, ...],
) -> ResearchHypothesis:
    if any(callable(value) for value in required_fact_families):
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    payload = {
        "hypothesis_version": hypothesis_version,
        "family": family,
        "stage": stage,
        "role": role,
        "direction_contribution": direction_contribution,
        "required_fact_families": required_fact_families,
        "provenance": provenance,
    }
    return ResearchHypothesis(
        hypothesis_identity=_identity("INTRADAY-RESEARCH-HYPOTHESIS-", payload),
        integrity_identity=_identity("INTEGRITY-RESEARCH-HYPOTHESIS-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class MethodologyVariant:
    variant_identity: str
    variant_version: str
    methodology_identity: str
    methodology_version: str
    corpus_identity: str
    hypotheses: tuple[ResearchHypothesis, ...]
    minimum_supporting_matches: tuple[tuple[ResearchStage, int], ...]
    outcome_definition_identity: str
    outcome_definition_version: str
    population_diagnostic_version: str
    combination_semantics: str
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = METHODOLOGY_VARIANT_IDENTITY
    schema_version: str = PART2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.variant_identity.startswith("INTRADAY-METHODOLOGY-VARIANT-")
            or not _text(self.variant_version)
            or self.methodology_identity != METHODOLOGY_RESEARCH_IDENTITY
            or self.methodology_version != PART2_CONTRACT_VERSION
            or not _text(self.corpus_identity)
            or not self.hypotheses
            or any(type(item) is not ResearchHypothesis for item in self.hypotheses)
            or len({item.hypothesis_identity for item in self.hypotheses}) != len(self.hypotheses)
            or any(
                type(stage) is not ResearchStage or type(count) is not int or count < 0
                for stage, count in self.minimum_supporting_matches
            )
            or len({stage for stage, _ in self.minimum_supporting_matches})
            != len(self.minimum_supporting_matches)
            or not _text(self.outcome_definition_identity)
            or not _text(self.outcome_definition_version)
            or not _text(self.population_diagnostic_version)
            or self.combination_semantics
            != "EXPLICIT_ALL_MANDATORY_ANY_BOUNDED_SUPPORT_EXPLICIT_VETO"
            or not _texts(self.provenance)
            or self.schema_identity != METHODOLOGY_VARIANT_IDENTITY
            or self.schema_version != PART2_CONTRACT_VERSION
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        support_by_stage = dict(self.minimum_supporting_matches)
        for stage, minimum in support_by_stage.items():
            available = sum(
                item.stage is stage and item.role is EvidenceRole.SUPPORTING
                for item in self.hypotheses
            )
            if minimum > available:
                raise QualificationError(QualificationFailure.INPUT_INVALID)
        _verify(self, "INTRADAY-METHODOLOGY-VARIANT-", "INTEGRITY-METHODOLOGY-VARIANT-")


def create_methodology_variant(
    *,
    variant_version: str,
    corpus_identity: str,
    hypotheses: tuple[ResearchHypothesis, ...],
    minimum_supporting_matches: tuple[tuple[ResearchStage, int], ...],
    outcome_definition_identity: str,
    outcome_definition_version: str,
    population_diagnostic_version: str,
    provenance: tuple[str, ...],
) -> MethodologyVariant:
    payload = {
        "variant_version": variant_version,
        "methodology_identity": METHODOLOGY_RESEARCH_IDENTITY,
        "methodology_version": PART2_CONTRACT_VERSION,
        "corpus_identity": corpus_identity,
        "hypotheses": hypotheses,
        "minimum_supporting_matches": minimum_supporting_matches,
        "outcome_definition_identity": outcome_definition_identity,
        "outcome_definition_version": outcome_definition_version,
        "population_diagnostic_version": population_diagnostic_version,
        "combination_semantics": "EXPLICIT_ALL_MANDATORY_ANY_BOUNDED_SUPPORT_EXPLICIT_VETO",
        "provenance": provenance,
        "schema_identity": METHODOLOGY_VARIANT_IDENTITY,
        "schema_version": PART2_CONTRACT_VERSION,
    }
    return MethodologyVariant(
        variant_identity=_identity("INTRADAY-METHODOLOGY-VARIANT-", payload),
        integrity_identity=_identity("INTEGRITY-METHODOLOGY-VARIANT-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HypothesisEvidence:
    hypothesis_identity: str
    result: HypothesisResult
    evidence_identities: tuple[str, ...]
    available_at: datetime
    source: QualificationEvidenceSource
    outcome_evidence: bool = False

    def __post_init__(self) -> None:
        if (
            not _text(self.hypothesis_identity)
            or type(self.result) is not HypothesisResult
            or not _texts(self.evidence_identities)
            or not _aware(self.available_at)
            or type(self.source) is not QualificationEvidenceSource
            or type(self.outcome_evidence) is not bool
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)


@dataclass(frozen=True, slots=True)
class StageProgress:
    stage: ResearchStage
    survived: bool
    unavailable: bool
    reasons: tuple[ResearchReason, ...]


@dataclass(frozen=True, slots=True)
class ProbableResearchResult:
    result_identity: str
    canonical_subject_identity: str
    market_session_identity: str
    variant_identity: str
    observation_boundary: datetime
    stage_progression: tuple[StageProgress, ...]
    hypothesis_evidence: tuple[HypothesisEvidence, ...]
    direction: ResearchDirection
    disposition: ResearchDisposition
    research_qualified: bool
    reason_codes: tuple[ResearchReason, ...]
    input_evidence_identities: tuple[str, ...]
    subsequent_outcome_identity: str | None
    evidence_source: QualificationEvidenceSource
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = RESEARCH_RESULT_IDENTITY
    schema_version: str = PART2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.result_identity.startswith("INTRADAY-PROBABLE-RESEARCH-RESULT-")
            or not _text(self.canonical_subject_identity)
            or not _text(self.market_session_identity)
            or not _text(self.variant_identity)
            or not _aware(self.observation_boundary)
            or not self.stage_progression
            or any(type(item) is not StageProgress for item in self.stage_progression)
            or not self.hypothesis_evidence
            or any(type(item) is not HypothesisEvidence for item in self.hypothesis_evidence)
            or any(item.available_at > self.observation_boundary for item in self.hypothesis_evidence)
            or any(item.outcome_evidence for item in self.hypothesis_evidence)
            or type(self.direction) is not ResearchDirection
            or type(self.disposition) is not ResearchDisposition
            or type(self.research_qualified) is not bool
            or not self.reason_codes
            or any(type(item) is not ResearchReason for item in self.reason_codes)
            or not _texts(self.input_evidence_identities)
            or self.subsequent_outcome_identity is not None
            and not _text(self.subsequent_outcome_identity)
            or type(self.evidence_source) is not QualificationEvidenceSource
            or any(item.source is not self.evidence_source for item in self.hypothesis_evidence)
            or not _texts(self.provenance)
            or self.research_qualified
            != (self.disposition is ResearchDisposition.QUALIFICATION_WOULD_PASS)
            or self.schema_identity != RESEARCH_RESULT_IDENTITY
            or self.schema_version != PART2_CONTRACT_VERSION
        ):
            failure = (
                QualificationFailure.LOOK_AHEAD
                if any(
                    item.available_at > self.observation_boundary or item.outcome_evidence
                    for item in self.hypothesis_evidence
                )
                else QualificationFailure.INPUT_INVALID
            )
            raise QualificationError(failure)
        _verify(self, "INTRADAY-PROBABLE-RESEARCH-RESULT-", "INTEGRITY-PROBABLE-RESEARCH-RESULT-")


def evaluate_methodology_variant(
    *,
    canonical_subject_identity: str,
    market_session_identity: str,
    observation_boundary: datetime,
    variant: MethodologyVariant,
    evidence: tuple[HypothesisEvidence, ...],
    provenance: tuple[str, ...],
) -> ProbableResearchResult:
    if type(variant) is not MethodologyVariant or not _aware(observation_boundary):
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    expected = {item.hypothesis_identity for item in variant.hypotheses}
    supplied = {item.hypothesis_identity for item in evidence}
    if len(supplied) != len(evidence) or supplied != expected:
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    if any(item.available_at > observation_boundary or item.outcome_evidence for item in evidence):
        raise QualificationError(QualificationFailure.LOOK_AHEAD)
    sources = {item.source for item in evidence}
    if len(sources) != 1:
        raise QualificationError(QualificationFailure.EVIDENCE_AUTHORITY)
    evidence_by_id = {item.hypothesis_identity: item for item in evidence}
    support_minimum = dict(variant.minimum_supporting_matches)
    progression: list[StageProgress] = []
    all_reasons: list[ResearchReason] = []
    alive = True
    unavailable = False
    for stage in STAGE_ORDER:
        definitions = tuple(item for item in variant.hypotheses if item.stage is stage)
        reasons: list[ResearchReason] = []
        stage_unavailable = False
        if alive and definitions:
            values = tuple((item, evidence_by_id[item.hypothesis_identity]) for item in definitions)
            if any(value.result is HypothesisResult.FACTUAL_FAILURE for _, value in values):
                alive = False
                reasons.append(ResearchReason.FACTUAL_FAILURE)
            mandatory = tuple(value for item, value in values if item.role is EvidenceRole.MANDATORY)
            if alive and any(value.result is HypothesisResult.UNAVAILABLE for value in mandatory):
                alive = False
                unavailable = True
                stage_unavailable = True
                reasons.append(ResearchReason.MANDATORY_UNAVAILABLE)
            elif alive and any(value.result is not HypothesisResult.MATCH for value in mandatory):
                alive = False
                reasons.append(ResearchReason.MANDATORY_NO_MATCH)
            elif mandatory:
                reasons.append(ResearchReason.MANDATORY_MATCH)
            vetoes = tuple(value for item, value in values if item.role is EvidenceRole.VETO)
            if alive and any(value.result is HypothesisResult.MATCH for value in vetoes):
                alive = False
                reasons.append(ResearchReason.VETO_MATCH)
            elif vetoes:
                reasons.append(ResearchReason.VETO_CLEAR)
            supporting = tuple(value for item, value in values if item.role is EvidenceRole.SUPPORTING)
            required_support = support_minimum.get(stage, 0)
            matched_support = sum(value.result is HypothesisResult.MATCH for value in supporting)
            if alive and matched_support < required_support:
                alive = False
                if any(value.result is HypothesisResult.UNAVAILABLE for value in supporting):
                    unavailable = True
                    stage_unavailable = True
                reasons.append(ResearchReason.SUPPORT_INSUFFICIENT)
            elif supporting:
                reasons.append(ResearchReason.SUPPORT_SUFFICIENT)
            if any(item.role is EvidenceRole.INFORMATIONAL for item, _ in values):
                reasons.append(ResearchReason.INFORMATION_RECORDED)
            if alive:
                reasons.append(ResearchReason.STAGE_SURVIVED)
        progression.append(
            StageProgress(
                stage=stage,
                survived=alive,
                unavailable=stage_unavailable,
                reasons=tuple(reasons),
            )
        )
        all_reasons.extend(reasons)
    matched_directions = {
        item.direction_contribution
        for item in variant.hypotheses
        if evidence_by_id[item.hypothesis_identity].result is HypothesisResult.MATCH
        and item.direction_contribution is not DirectionContribution.NONE
    }
    directional_definitions = tuple(
        item for item in variant.hypotheses
        if item.direction_contribution is not DirectionContribution.NONE
    )
    if directional_definitions and all(
        evidence_by_id[item.hypothesis_identity].result is HypothesisResult.UNAVAILABLE
        for item in directional_definitions
    ):
        direction = ResearchDirection.UNAVAILABLE
    elif matched_directions == {DirectionContribution.LONG}:
        direction = ResearchDirection.LONG_HYPOTHESIS
    elif matched_directions == {DirectionContribution.SHORT}:
        direction = ResearchDirection.SHORT_HYPOTHESIS
    elif matched_directions == {DirectionContribution.LONG, DirectionContribution.SHORT}:
        direction = ResearchDirection.DIRECTION_CONFLICTING
    else:
        direction = ResearchDirection.NON_DIRECTIONAL
    disposition = (
        ResearchDisposition.QUALIFICATION_WOULD_PASS
        if alive
        else ResearchDisposition.QUALIFICATION_UNAVAILABLE
        if unavailable
        else ResearchDisposition.QUALIFICATION_WOULD_FAIL
    )
    all_reasons.append(ResearchReason.RESEARCH_ONLY)
    input_identities = tuple(
        identity for item in evidence for identity in item.evidence_identities
    )
    payload = {
        "canonical_subject_identity": canonical_subject_identity,
        "market_session_identity": market_session_identity,
        "variant_identity": variant.variant_identity,
        "observation_boundary": observation_boundary,
        "stage_progression": tuple(progression),
        "hypothesis_evidence": evidence,
        "direction": direction,
        "disposition": disposition,
        "research_qualified": alive,
        "reason_codes": tuple(dict.fromkeys(all_reasons)),
        "input_evidence_identities": input_identities,
        "subsequent_outcome_identity": None,
        "evidence_source": next(iter(sources)),
        "provenance": provenance,
        "schema_identity": RESEARCH_RESULT_IDENTITY,
        "schema_version": PART2_CONTRACT_VERSION,
    }
    return ProbableResearchResult(
        result_identity=_identity("INTRADAY-PROBABLE-RESEARCH-RESULT-", payload),
        integrity_identity=_identity("INTEGRITY-PROBABLE-RESEARCH-RESULT-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class StagePopulationDiagnostic:
    stage: ResearchStage
    starting_count: int
    survivor_count: int
    rejected_count: int
    unavailable_count: int
    retention_percentage: Decimal
    attrition_percentage: Decimal
    cumulative_retention_percentage: Decimal


@dataclass(frozen=True, slots=True)
class SessionVariantResult:
    session_result_identity: str
    market_session_identity: str
    variant_identity: str
    factual_population_count: int
    unavailable_member_identities: tuple[str, ...]
    member_results: tuple[ProbableResearchResult, ...]
    stage_diagnostics: tuple[StagePopulationDiagnostic, ...]
    qualified_count: int
    long_count: int
    short_count: int
    non_directional_count: int
    conflicting_count: int
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        counts = (
            self.factual_population_count,
            self.qualified_count,
            self.long_count,
            self.short_count,
            self.non_directional_count,
            self.conflicting_count,
        )
        if (
            not self.session_result_identity.startswith("INTRADAY-SESSION-VARIANT-RESULT-")
            or not _text(self.market_session_identity)
            or not _text(self.variant_identity)
            or any(type(value) is not int or value < 0 for value in counts)
            or not self.member_results
            or any(type(item) is not ProbableResearchResult for item in self.member_results)
            or self.factual_population_count != len(self.member_results)
            or any(item.variant_identity != self.variant_identity for item in self.member_results)
            or any(item.market_session_identity != self.market_session_identity for item in self.member_results)
            or not self.stage_diagnostics
            or any(type(item) is not StagePopulationDiagnostic for item in self.stage_diagnostics)
            or self.qualified_count != sum(item.research_qualified for item in self.member_results)
            or not _texts(self.provenance)
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        _verify(self, "INTRADAY-SESSION-VARIANT-RESULT-", "INTEGRITY-SESSION-VARIANT-RESULT-")


def create_session_variant_result(
    *,
    market_session_identity: str,
    variant: MethodologyVariant,
    member_results: tuple[ProbableResearchResult, ...],
    unavailable_member_identities: tuple[str, ...],
    provenance: tuple[str, ...],
) -> SessionVariantResult:
    if not member_results or any(not _text(item) for item in unavailable_member_identities):
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    initial = len(member_results)
    diagnostics: list[StagePopulationDiagnostic] = []
    previous = initial
    for index, stage in enumerate(STAGE_ORDER):
        progress = tuple(item.stage_progression[index] for item in member_results)
        survivor = sum(item.survived for item in progress)
        unavailable = sum(item.unavailable for item in progress if not item.survived)
        rejected = previous - survivor
        retention = _percentage(survivor, previous)
        diagnostics.append(
            StagePopulationDiagnostic(
                stage=stage,
                starting_count=previous,
                survivor_count=survivor,
                rejected_count=rejected,
                unavailable_count=unavailable,
                retention_percentage=retention,
                attrition_percentage=Decimal(100) - retention if previous else Decimal(0),
                cumulative_retention_percentage=_percentage(survivor, initial),
            )
        )
        previous = survivor
    qualified = tuple(item for item in member_results if item.research_qualified)
    payload = {
        "market_session_identity": market_session_identity,
        "variant_identity": variant.variant_identity,
        "factual_population_count": initial,
        "unavailable_member_identities": unavailable_member_identities,
        "member_results": member_results,
        "stage_diagnostics": tuple(diagnostics),
        "qualified_count": len(qualified),
        "long_count": sum(item.direction is ResearchDirection.LONG_HYPOTHESIS for item in qualified),
        "short_count": sum(item.direction is ResearchDirection.SHORT_HYPOTHESIS for item in qualified),
        "non_directional_count": sum(item.direction is ResearchDirection.NON_DIRECTIONAL for item in qualified),
        "conflicting_count": sum(item.direction is ResearchDirection.DIRECTION_CONFLICTING for item in qualified),
        "provenance": provenance,
    }
    return SessionVariantResult(
        session_result_identity=_identity("INTRADAY-SESSION-VARIANT-RESULT-", payload),
        integrity_identity=_identity("INTEGRITY-SESSION-VARIANT-RESULT-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HypothesisPopulationEffect:
    hypothesis_identity: str
    family: HypothesisFamily
    observation_count: int
    match_count: int
    non_match_count: int
    unavailable_count: int
    factual_failure_count: int
    match_percentage: Decimal
    final_qualified_match_count: int

    def __post_init__(self) -> None:
        counts = (
            self.observation_count,
            self.match_count,
            self.non_match_count,
            self.unavailable_count,
            self.factual_failure_count,
            self.final_qualified_match_count,
        )
        if (
            not _text(self.hypothesis_identity)
            or type(self.family) is not HypothesisFamily
            or any(type(value) is not int or value < 0 for value in counts)
            or sum(counts[1:5]) != self.observation_count
            or self.final_qualified_match_count > self.match_count
            or type(self.match_percentage) is not Decimal
            or not self.match_percentage.is_finite()
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)


@dataclass(frozen=True, slots=True)
class VariantPopulationSummary:
    summary_identity: str
    variant_identity: str
    session_result_identities: tuple[str, ...]
    sessions_evaluated: int
    observations_evaluated: int
    real_observation_count: int
    synthetic_observation_count: int
    unavailable_member_count: int
    mean_survivors: Decimal
    median_survivors: Decimal
    minimum_survivors: int
    maximum_survivors: int
    zero_frequency: int
    over_ten_frequency: int
    over_fifteen_frequency: int
    twenty_or_more_frequency: int
    retention_percentage: Decimal
    long_count: int
    short_count: int
    non_directional_count: int
    conflicting_count: int
    hypothesis_population_effects: tuple[HypothesisPopulationEffect, ...]
    warning: PopulationWarning
    outcome_available: bool
    outcome_metrics: tuple[tuple[str, Decimal], ...]
    conclusion: ResearchConclusion
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        if (
            not self.summary_identity.startswith("INTRADAY-VARIANT-POPULATION-SUMMARY-")
            or not _text(self.variant_identity)
            or not _texts(self.session_result_identities)
            or not _texts(self.provenance)
            or any(
                type(item) is not HypothesisPopulationEffect
                for item in self.hypothesis_population_effects
            )
            or type(self.warning) is not PopulationWarning
            or self.outcome_available != bool(self.outcome_metrics)
            or any(
                not _text(name) or type(value) is not Decimal or not value.is_finite()
                for name, value in self.outcome_metrics
            )
            or type(self.conclusion) is not ResearchConclusion
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        _verify(self, "INTRADAY-VARIANT-POPULATION-SUMMARY-", "INTEGRITY-VARIANT-POPULATION-SUMMARY-")


def summarize_variant_population(
    *,
    variant: MethodologyVariant,
    sessions: tuple[SessionVariantResult, ...],
    evidence_sufficiency: QualificationEvidenceSufficiency,
    provenance: tuple[str, ...],
    outcome_metrics: tuple[tuple[str, Decimal], ...] = (),
) -> VariantPopulationSummary:
    if not sessions or any(item.variant_identity != variant.variant_identity for item in sessions):
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    populations = tuple(item.qualified_count for item in sessions)
    observations = tuple(result for session in sessions for result in session.member_results)
    real = sum(
        item.evidence_source is QualificationEvidenceSource.REAL_GOVERNED_MARKET_EVIDENCE
        for item in observations
    )
    zero = sum(value == 0 for value in populations)
    flood = sum(value > 10 for value in populations)
    warning = (
        PopulationWarning.STARVATION_AND_FLOODING_RISK if zero and flood
        else PopulationWarning.STARVATION_RISK if zero
        else PopulationWarning.FLOODING_RISK if flood
        else PopulationWarning.NONE
    )
    conclusion = (
        ResearchConclusion.INSUFFICIENT_EVIDENCE
        if real == 0
        or evidence_sufficiency
        in {
            QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
            QualificationEvidenceSufficiency.EVIDENCE_INSUFFICIENT,
        }
        else ResearchConclusion.CONTINUE_QUALIFICATION
    )
    effects = tuple(
        _hypothesis_population_effect(hypothesis, observations)
        for hypothesis in variant.hypotheses
    )
    payload = {
        "variant_identity": variant.variant_identity,
        "session_result_identities": tuple(item.session_result_identity for item in sessions),
        "sessions_evaluated": len(sessions),
        "observations_evaluated": len(observations),
        "real_observation_count": real,
        "synthetic_observation_count": len(observations) - real,
        "unavailable_member_count": sum(
            len(item.unavailable_member_identities) for item in sessions
        ),
        "mean_survivors": Decimal(sum(populations)) / Decimal(len(populations)),
        "median_survivors": Decimal(median(populations)),
        "minimum_survivors": min(populations),
        "maximum_survivors": max(populations),
        "zero_frequency": zero,
        "over_ten_frequency": sum(value > 10 for value in populations),
        "over_fifteen_frequency": sum(value > 15 for value in populations),
        "twenty_or_more_frequency": sum(value >= 20 for value in populations),
        "retention_percentage": _percentage(sum(populations), sum(item.factual_population_count for item in sessions)),
        "long_count": sum(item.long_count for item in sessions),
        "short_count": sum(item.short_count for item in sessions),
        "non_directional_count": sum(item.non_directional_count for item in sessions),
        "conflicting_count": sum(item.conflicting_count for item in sessions),
        "hypothesis_population_effects": effects,
        "warning": warning,
        "outcome_available": bool(outcome_metrics),
        "outcome_metrics": outcome_metrics,
        "conclusion": conclusion,
        "provenance": provenance,
    }
    return VariantPopulationSummary(
        summary_identity=_identity("INTRADAY-VARIANT-POPULATION-SUMMARY-", payload),
        integrity_identity=_identity("INTEGRITY-VARIANT-POPULATION-SUMMARY-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class AblationComparison:
    comparison_identity: str
    base_variant_identity: str
    ablated_variant_identity: str
    removed_hypothesis_identities: tuple[str, ...]
    base_summary_identity: str
    ablated_summary_identity: str
    survivor_difference: Decimal
    outcome_comparison_available: bool
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        if not _texts(self.removed_hypothesis_identities) or not _texts(self.provenance):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        _verify(self, "INTRADAY-ABLATION-COMPARISON-", "INTEGRITY-ABLATION-COMPARISON-")


def compare_ablation(
    *,
    base_variant: MethodologyVariant,
    ablated_variant: MethodologyVariant,
    base_summary: VariantPopulationSummary,
    ablated_summary: VariantPopulationSummary,
    provenance: tuple[str, ...],
) -> AblationComparison:
    if (
        base_summary.variant_identity != base_variant.variant_identity
        or ablated_summary.variant_identity != ablated_variant.variant_identity
    ):
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    base_ids = {item.hypothesis_identity for item in base_variant.hypotheses}
    ablated_ids = {item.hypothesis_identity for item in ablated_variant.hypotheses}
    removed = tuple(sorted(base_ids - ablated_ids))
    if not removed or not ablated_ids.issubset(base_ids):
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    payload = {
        "base_variant_identity": base_variant.variant_identity,
        "ablated_variant_identity": ablated_variant.variant_identity,
        "removed_hypothesis_identities": removed,
        "base_summary_identity": base_summary.summary_identity,
        "ablated_summary_identity": ablated_summary.summary_identity,
        "survivor_difference": ablated_summary.mean_survivors - base_summary.mean_survivors,
        "outcome_comparison_available": base_summary.outcome_available and ablated_summary.outcome_available,
        "provenance": provenance,
    }
    return AblationComparison(
        comparison_identity=_identity("INTRADAY-ABLATION-COMPARISON-", payload),
        integrity_identity=_identity("INTEGRITY-ABLATION-COMPARISON-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class MethodologyComparisonReport:
    report_identity: str
    report_version: str
    corpus_identity: str
    variant_summaries: tuple[VariantPopulationSummary, ...]
    ablation_comparisons: tuple[AblationComparison, ...]
    evidence_sufficiency: QualificationEvidenceSufficiency
    market_condition_coverage: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    conclusion: ResearchConclusion
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = COMPARISON_REPORT_IDENTITY
    schema_version: str = PART2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.report_identity.startswith("INTRADAY-METHODOLOGY-COMPARISON-REPORT-")
            or not _text(self.report_version)
            or not _text(self.corpus_identity)
            or not self.variant_summaries
            or any(type(item) is not VariantPopulationSummary for item in self.variant_summaries)
            or any(type(item) is not AblationComparison for item in self.ablation_comparisons)
            or type(self.evidence_sufficiency) is not QualificationEvidenceSufficiency
            or not _texts(self.market_condition_coverage)
            or not _texts(self.missing_evidence)
            or type(self.conclusion) is not ResearchConclusion
            or not _texts(self.provenance)
            or (
                sum(item.real_observation_count for item in self.variant_summaries) == 0
                and self.conclusion is not ResearchConclusion.INSUFFICIENT_EVIDENCE
            )
            or self.schema_identity != COMPARISON_REPORT_IDENTITY
            or self.schema_version != PART2_CONTRACT_VERSION
        ):
            raise QualificationError(QualificationFailure.EVIDENCE_AUTHORITY)
        _verify(self, "INTRADAY-METHODOLOGY-COMPARISON-REPORT-", "INTEGRITY-METHODOLOGY-COMPARISON-REPORT-")


def create_methodology_comparison_report(
    *,
    report_version: str,
    corpus_identity: str,
    variant_summaries: tuple[VariantPopulationSummary, ...],
    ablation_comparisons: tuple[AblationComparison, ...],
    evidence_sufficiency: QualificationEvidenceSufficiency,
    market_condition_coverage: tuple[str, ...],
    missing_evidence: tuple[str, ...],
    conclusion: ResearchConclusion,
    provenance: tuple[str, ...],
) -> MethodologyComparisonReport:
    payload = {
        "report_version": report_version,
        "corpus_identity": corpus_identity,
        "variant_summaries": variant_summaries,
        "ablation_comparisons": ablation_comparisons,
        "evidence_sufficiency": evidence_sufficiency,
        "market_condition_coverage": market_condition_coverage,
        "missing_evidence": missing_evidence,
        "conclusion": conclusion,
        "provenance": provenance,
        "schema_identity": COMPARISON_REPORT_IDENTITY,
        "schema_version": PART2_CONTRACT_VERSION,
    }
    return MethodologyComparisonReport(
        report_identity=_identity("INTRADAY-METHODOLOGY-COMPARISON-REPORT-", payload),
        integrity_identity=_identity("INTEGRITY-METHODOLOGY-COMPARISON-REPORT-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class OutcomeMeasurementDefinition:
    definition_identity: str
    definition_version: str
    family: OutcomeDefinitionFamily
    measure_names: tuple[str, ...]
    normalization_options: tuple[str, ...]
    threshold: Decimal | None
    threshold_status: str
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        banned = {"ENTRY", "FILL", "QUANTITY", "PNL", "REALISED_R", "STOP", "TARGET"}
        if (
            not self.definition_identity.startswith("INTRADAY-OUTCOME-MEASUREMENT-DEFINITION-")
            or not _text(self.definition_version)
            or type(self.family) is not OutcomeDefinitionFamily
            or not _texts(self.measure_names)
            or any(any(word in name.upper() for word in banned) for name in self.measure_names)
            or not _texts(self.normalization_options)
            or self.threshold is not None
            or self.threshold_status != "UNRESOLVED_PENDING_EVIDENCE_AND_APPROVAL"
            or not _texts(self.provenance)
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        _verify(self, "INTRADAY-OUTCOME-MEASUREMENT-DEFINITION-", "INTEGRITY-OUTCOME-MEASUREMENT-DEFINITION-")


def create_outcome_measurement_definition(
    *,
    definition_version: str,
    family: OutcomeDefinitionFamily,
    measure_names: tuple[str, ...],
    normalization_options: tuple[str, ...],
    provenance: tuple[str, ...],
) -> OutcomeMeasurementDefinition:
    payload = {
        "definition_version": definition_version,
        "family": family,
        "measure_names": measure_names,
        "normalization_options": normalization_options,
        "threshold": None,
        "threshold_status": "UNRESOLVED_PENDING_EVIDENCE_AND_APPROVAL",
        "provenance": provenance,
    }
    return OutcomeMeasurementDefinition(
        definition_identity=_identity("INTRADAY-OUTCOME-MEASUREMENT-DEFINITION-", payload),
        integrity_identity=_identity("INTEGRITY-OUTCOME-MEASUREMENT-DEFINITION-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class OutcomeMeasurement:
    measurement_identity: str
    definition_identity: str
    definition_version: str
    source_result_identity: str
    observation_boundary: datetime
    measured_at: datetime
    measures: tuple[tuple[str, Decimal], ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = OUTCOME_MEASUREMENT_IDENTITY
    schema_version: str = PART2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.measurement_identity.startswith("INTRADAY-OUTCOME-MEASUREMENT-")
            or not _text(self.definition_identity)
            or not _text(self.definition_version)
            or not _text(self.source_result_identity)
            or not _aware(self.observation_boundary)
            or not _aware(self.measured_at)
            or self.measured_at <= self.observation_boundary
            or not self.measures
            or any(not _text(name) or type(value) is not Decimal or not value.is_finite() for name, value in self.measures)
            or not _texts(self.provenance)
            or self.schema_identity != OUTCOME_MEASUREMENT_IDENTITY
            or self.schema_version != PART2_CONTRACT_VERSION
        ):
            raise QualificationError(QualificationFailure.LOOK_AHEAD)
        _verify(self, "INTRADAY-OUTCOME-MEASUREMENT-", "INTEGRITY-OUTCOME-MEASUREMENT-")


def create_outcome_measurement(
    *,
    definition: OutcomeMeasurementDefinition,
    source_result: ProbableResearchResult,
    measured_at: datetime,
    measures: tuple[tuple[str, Decimal], ...],
    provenance: tuple[str, ...],
) -> OutcomeMeasurement:
    if tuple(name for name, _ in measures) != definition.measure_names:
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    payload = {
        "definition_identity": definition.definition_identity,
        "definition_version": definition.definition_version,
        "source_result_identity": source_result.result_identity,
        "observation_boundary": source_result.observation_boundary,
        "measured_at": measured_at,
        "measures": measures,
        "provenance": provenance,
        "schema_identity": OUTCOME_MEASUREMENT_IDENTITY,
        "schema_version": PART2_CONTRACT_VERSION,
    }
    return OutcomeMeasurement(
        measurement_identity=_identity("INTRADAY-OUTCOME-MEASUREMENT-", payload),
        integrity_identity=_identity("INTEGRITY-OUTCOME-MEASUREMENT-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class RealDiscoveryCorpusBinding:
    binding_identity: str
    discovery_run_identity: str
    universe_publication_identity: str
    reconciliation_publication_identity: str
    observation_boundary: datetime
    machine_fact_bundle_identities: tuple[str, ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = REAL_CORPUS_BINDING_IDENTITY
    schema_version: str = PART2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        identities = (
            self.discovery_run_identity,
            self.universe_publication_identity,
            self.reconciliation_publication_identity,
            *self.machine_fact_bundle_identities,
        )
        if (
            not self.binding_identity.startswith("INTRADAY-REAL-CORPUS-BINDING-")
            or not _texts(identities)
            or any(value.upper() in {"LATEST", "NEWEST", "CURRENT"} for value in identities)
            or not _aware(self.observation_boundary)
            or not _texts(self.provenance)
            or self.schema_identity != REAL_CORPUS_BINDING_IDENTITY
            or self.schema_version != PART2_CONTRACT_VERSION
        ):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        _verify(self, "INTRADAY-REAL-CORPUS-BINDING-", "INTEGRITY-REAL-CORPUS-BINDING-")


def create_real_discovery_corpus_binding(
    *,
    discovery_run_identity: str,
    universe_publication_identity: str,
    reconciliation_publication_identity: str,
    observation_boundary: datetime,
    machine_fact_bundle_identities: tuple[str, ...],
    provenance: tuple[str, ...],
) -> RealDiscoveryCorpusBinding:
    payload = {
        "discovery_run_identity": discovery_run_identity,
        "universe_publication_identity": universe_publication_identity,
        "reconciliation_publication_identity": reconciliation_publication_identity,
        "observation_boundary": observation_boundary,
        "machine_fact_bundle_identities": machine_fact_bundle_identities,
        "provenance": provenance,
        "schema_identity": REAL_CORPUS_BINDING_IDENTITY,
        "schema_version": PART2_CONTRACT_VERSION,
    }
    return RealDiscoveryCorpusBinding(
        binding_identity=_identity("INTRADAY-REAL-CORPUS-BINDING-", payload),
        integrity_identity=_identity("INTEGRITY-REAL-CORPUS-BINDING-", payload),
        **payload,
    )


def bind_real_corpus(
    corpus: QualificationCorpus, binding: RealDiscoveryCorpusBinding
) -> tuple[str, ...]:
    """Bind exact real-run coordinates; no filesystem or latest-file lookup."""
    if type(corpus) is not QualificationCorpus or type(binding) is not RealDiscoveryCorpusBinding:
        raise QualificationError(QualificationFailure.INPUT_INVALID)
    matching = tuple(
        session.session_record_identity
        for session in corpus.sessions
        if session.discovery_run_identity == binding.discovery_run_identity
        and session.universe_publication_identity == binding.universe_publication_identity
        and session.reconciliation_publication_identity
        == binding.reconciliation_publication_identity
        and session.observation_boundary == binding.observation_boundary
        and set(binding.machine_fact_bundle_identities).issubset(
            set(session.factual_evidence_identities)
        )
    )
    if not matching:
        raise QualificationError(QualificationFailure.EVIDENCE_AUTHORITY)
    return matching


def research_artifact_document(value: object) -> dict[str, object]:
    identity = _artifact_identity(value)
    artifact_type = type(value).__name__
    artifact = _normalize(value)
    core = {
        "artifact_type": artifact_type,
        "artifact_identity": identity,
        "artifact": artifact,
    }
    return {**core, "document_integrity": _identity("INTEGRITY-RESEARCH-DOCUMENT-", core)}


def research_artifact_bytes(value: object) -> bytes:
    return _encode(research_artifact_document(value)) + b"\n"


def verify_research_artifact_document(document: Mapping[str, object]) -> None:
    core = {name: document.get(name) for name in ("artifact_type", "artifact_identity", "artifact")}
    if document.get("document_integrity") != _identity("INTEGRITY-RESEARCH-DOCUMENT-", core):
        raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def _artifact_identity(value: object) -> str:
    names = {
        MethodologyVariant: "variant_identity",
        ProbableResearchResult: "result_identity",
        SessionVariantResult: "session_result_identity",
        VariantPopulationSummary: "summary_identity",
        AblationComparison: "comparison_identity",
        MethodologyComparisonReport: "report_identity",
        OutcomeMeasurementDefinition: "definition_identity",
        OutcomeMeasurement: "measurement_identity",
        RealDiscoveryCorpusBinding: "binding_identity",
    }
    for kind, name in names.items():
        if type(value) is kind:
            return getattr(value, name)
    raise QualificationError(QualificationFailure.INPUT_INVALID)


def _verify(value: object, identity_prefix: str, integrity_prefix: str) -> None:
    # Content identity binds all fields except itself and integrity.  Reference
    # identities remain included because only the object's own identity is
    # removed explicitly below.
    own_identity_name = next(
        key for key in asdict(value)
        if key.endswith("_identity") and str(getattr(value, key)).startswith(identity_prefix)
    )
    full_payload = asdict(value)
    full_payload.pop(own_identity_name)
    full_payload.pop("integrity_identity")
    if getattr(value, own_identity_name) != _identity(identity_prefix, full_payload):
        raise QualificationError(QualificationFailure.INTEGRITY_INVALID)
    if getattr(value, "integrity_identity") != _identity(integrity_prefix, full_payload):
        raise QualificationError(QualificationFailure.INTEGRITY_INVALID)


def _percentage(numerator: int, denominator: int) -> Decimal:
    return Decimal(0) if denominator == 0 else Decimal(numerator) / Decimal(denominator) * Decimal(100)


def _hypothesis_population_effect(
    hypothesis: ResearchHypothesis,
    observations: tuple[ProbableResearchResult, ...],
) -> HypothesisPopulationEffect:
    pairs = tuple(
        (
            result,
            next(
                item
                for item in result.hypothesis_evidence
                if item.hypothesis_identity == hypothesis.hypothesis_identity
            ),
        )
        for result in observations
    )
    matches = sum(item.result is HypothesisResult.MATCH for _, item in pairs)
    return HypothesisPopulationEffect(
        hypothesis_identity=hypothesis.hypothesis_identity,
        family=hypothesis.family,
        observation_count=len(pairs),
        match_count=matches,
        non_match_count=sum(
            item.result is HypothesisResult.NO_MATCH for _, item in pairs
        ),
        unavailable_count=sum(
            item.result is HypothesisResult.UNAVAILABLE for _, item in pairs
        ),
        factual_failure_count=sum(
            item.result is HypothesisResult.FACTUAL_FAILURE for _, item in pairs
        ),
        match_percentage=_percentage(matches, len(pairs)),
        final_qualified_match_count=sum(
            result.research_qualified and item.result is HypothesisResult.MATCH
            for result, item in pairs
        ),
    )


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _normalize(item) for key, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Iterable[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(value) for value in retained)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "COMPARISON_REPORT_IDENTITY", "METHODOLOGY_RESEARCH_IDENTITY",
    "METHODOLOGY_VARIANT_IDENTITY", "OUTCOME_MEASUREMENT_IDENTITY",
    "PART2_CONTRACT_VERSION", "REAL_CORPUS_BINDING_IDENTITY",
    "RESEARCH_RESULT_IDENTITY", "AblationComparison", "DirectionContribution",
    "EvidenceRole", "HypothesisEvidence", "HypothesisFamily",
    "HypothesisPopulationEffect", "HypothesisResult",
    "MethodologyComparisonReport", "MethodologyVariant", "OutcomeDefinitionFamily",
    "OutcomeMeasurement", "OutcomeMeasurementDefinition", "PopulationWarning",
    "ProbableResearchResult", "RealDiscoveryCorpusBinding", "ResearchConclusion",
    "ResearchDirection", "ResearchDisposition", "ResearchHypothesis", "ResearchReason",
    "ResearchStage", "STAGE_ORDER", "SessionVariantResult", "StagePopulationDiagnostic",
    "VariantPopulationSummary", "bind_real_corpus", "compare_ablation",
    "create_methodology_comparison_report", "create_methodology_variant",
    "create_outcome_measurement", "create_outcome_measurement_definition",
    "create_real_discovery_corpus_binding", "create_research_hypothesis",
    "create_session_variant_result", "evaluate_methodology_variant",
    "research_artifact_bytes", "research_artifact_document",
    "summarize_variant_population", "verify_research_artifact_document",
]
