"""Phase-aware Intraday Probables V2 contracts and deterministic evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.completed_evidence import (
    CompletedEvidenceSelection,
    EvidenceSessionRole,
    IntradayAnalysisPhase,
    is_completed_evidence_selection,
)
from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    SemanticDirection,
)
from kronos.intraday.nifty_relative_context import (
    NiftyApplicability,
    NiftyRelationship,
    NiftyRelativeContextEvidence,
)
from kronos.intraday.opening_semantic import (
    OpeningRelationship,
    OpeningSemanticEvidence,
)
from kronos.intraday.probables import (
    FactualSourceKind,
    PopulationBucket,
    ProbableState,
)
from kronos.intraday.qualification import NarrowCprFact
from kronos.intraday.mcx_commissioning import (
    McxCommissioningState,
    load_mcx_commissioning_publication,
)


PROBABLES_V2_METHODOLOGY_IDENTITY = "KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V2"
PROBABLES_V2_METHODOLOGY_VERSION = "2.0.0"
PROBABLES_V2_PUBLICATION_IDENTITY = (
    "INTRADAY-PROBABLES-METHODOLOGY-V2-PUBLICATION-"
    "7B75EE711558F706CFB97B4548952B8924A8CBD8E519EFEEE61B53828FDD9F89"
)
PROBABLES_V2_METHODOLOGY_CHECKSUM = (
    "7b75ee711558f706cfb97b4548952b8924a8cbd8e519efeee61b53828fdd9f89"
)
PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION = "2.1.0"
PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM = (
    "32012713c2b43212bea6af3bace0fbd2491176cb0a1cb7aaf88f8de77c1e8932"
)
PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY = (
    "INTRADAY-PROBABLES-METHODOLOGY-V2-PUBLICATION-"
    "32012713C2B43212BEA6AF3BACE0FBD2491176CB0A1CB7AAF88F8DE77C1E8932"
)
SEMANTIC_FACT_V2_IDENTITY = "KRONOS-INTRADAY-SEMANTIC-QUALIFICATION-FACT-V2"
SEMANTIC_EVIDENCE_V2_IDENTITY = (
    "KRONOS-INTRADAY-SEMANTIC-QUALIFICATION-EVIDENCE-V2"
)
DISCOVERY_PROBABLES_EVIDENCE_V2_IDENTITY = (
    "KRONOS-INTRADAY-DISCOVERY-PROBABLES-EVIDENCE-V2"
)
DISCOVERY_PROBABLES_MAPPER_V2_IDENTITY = (
    "KRONOS-INTRADAY-DISCOVERY-PROBABLES-EVIDENCE-MAPPER-V2"
)
PROBABLE_V2_IDENTITY = "KRONOS-INTRADAY-PROBABLE-V2"
POPULATION_DIAGNOSTICS_V2_IDENTITY = (
    "KRONOS-INTRADAY-PROBABLES-POPULATION-DIAGNOSTICS-V2"
)
PROBABLES_RUN_V2_IDENTITY = "KRONOS-INTRADAY-PROBABLES-RUN-V2"
V2_CONTRACT_VERSION = "2.0.0"


class ProbablesV2Error(ValueError):
    """Sanitized V2 contract, linkage, or integrity failure."""


class SemanticEvidenceRoleV2(StrEnum):
    MANDATORY_INFORMATIONAL = "MANDATORY_AVAILABILITY_INFORMATIONAL_CONSEQUENCE"
    MANDATORY_DIRECTIONAL = "MANDATORY_DIRECTIONAL_COHERENCE"
    OPENING_DIRECTIONAL = "OPENING_DIRECTIONAL"
    OPENING_CONFLICT_INPUT = "OPENING_CONFLICT_INPUT"
    SUPPORTING_NON_BLOCKING = "SUPPORTING_NON_BLOCKING"
    INFORMATIONAL = "INFORMATIONAL"
    HISTORICAL_LINEAGE_ONLY = "HISTORICAL_LINEAGE_ONLY"


class ProbableReasonV2(StrEnum):
    V2_CONDITIONS_SATISFIED = "V2_CONDITIONS_SATISFIED"
    NARROW_CPR_NOT_SATISFIED = "NARROW_CPR_NOT_SATISFIED"
    OPENING_NON_DIRECTIONAL = "OPENING_NON_DIRECTIONAL"
    OPENING_5M_NOT_SUPPORTING = "OPENING_5M_NOT_SUPPORTING"
    PRIOR_1H_CONFLICTING_NO_DIRECTION_FLIP = (
        "PRIOR_1H_CONFLICTING_BLOCKING_NOT_ADMITTED_NO_DIRECTION_FLIP"
    )
    NIFTY_CONTEXT_CONFLICTING_NO_DIRECTION_FLIP = (
        "NIFTY_CONTEXT_CONFLICTING_BLOCKING_NOT_ADMITTED_NO_DIRECTION_FLIP"
    )
    OPENING_RELATIONSHIP_NOT_SUPPORTING = "OPENING_RELATIONSHIP_NOT_SUPPORTING"
    ONE_HOUR_NON_DIRECTIONAL = "ONE_HOUR_NON_DIRECTIONAL"
    FIFTEEN_MINUTE_NON_DIRECTIONAL = "FIFTEEN_MINUTE_NON_DIRECTIONAL"
    DIRECTION_CONFLICTING = "DIRECTION_CONFLICTING"
    MANDATORY_EVIDENCE_UNAVAILABLE = "MANDATORY_EVIDENCE_UNAVAILABLE"
    NIFTY_CONTEXT_UNAVAILABLE = "NIFTY_CONTEXT_UNAVAILABLE"
    MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED = (
        "MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED"
    )
    SOURCE_DISCOVERY_UNAVAILABLE = "SOURCE_DISCOVERY_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ProbablesMethodologyV2:
    methodology_identity: str
    methodology_version: str
    publication_identity: str
    payload_checksum: str
    phase_family: tuple[IntradayAnalysisPhase, ...]
    authority: str
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("integrity_identity")
        if (
            not probables_v2_methodology_binding_supported(
                self.methodology_identity,
                self.methodology_version,
                self.publication_identity,
                self.payload_checksum,
            )
            or self.phase_family != tuple(IntradayAnalysisPhase)
            or self.authority != "ANALYTICAL_ADMISSION_FOR_DEEPER_REVIEW_ONLY"
            or not _texts(self.provenance)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-PROBABLES-METHODOLOGY-V2-", values)
        ):
            raise ProbablesV2Error("PROBABLES_V2_METHODOLOGY_INVALID")


def probables_v2_methodology_binding_supported(
    identity: str,
    version: str,
    publication: str,
    checksum: str,
) -> bool:
    return (
        identity == PROBABLES_V2_METHODOLOGY_IDENTITY
        and (version, publication, checksum) in {
            (
                PROBABLES_V2_METHODOLOGY_VERSION,
                PROBABLES_V2_PUBLICATION_IDENTITY,
                PROBABLES_V2_METHODOLOGY_CHECKSUM,
            ),
            (
                PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION,
                PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY,
                PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM,
            ),
        }
    )


def create_probables_v2_methodology(
    *, legacy: bool = False,
) -> ProbablesMethodologyV2:
    version, publication, checksum = (
        (
            PROBABLES_V2_METHODOLOGY_VERSION,
            PROBABLES_V2_PUBLICATION_IDENTITY,
            PROBABLES_V2_METHODOLOGY_CHECKSUM,
        )
        if legacy
        else (
            PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION,
            PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY,
            PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM,
        )
    )
    values = {
        "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
        "methodology_version": version,
        "publication_identity": publication,
        "payload_checksum": checksum,
        "phase_family": tuple(IntradayAnalysisPhase),
        "authority": "ANALYTICAL_ADMISSION_FOR_DEEPER_REVIEW_ONLY",
        "provenance": (
            "KRONOS-WO-06E-FREEZE" if legacy else "KRONOS-MCX-SUBJECT-COMMISSIONING-V1",
            publication,
        ),
    }
    return ProbablesMethodologyV2(
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-PROBABLES-METHODOLOGY-V2-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class SemanticQualificationFactV2:
    fact_identity: str
    family: str
    canonical_subject_identity: str
    analysis_boundary: datetime
    phase: IntradayAnalysisPhase
    availability: str
    direction: SemanticDirection
    evidence_role: SemanticEvidenceRoleV2
    source_evidence_identities: tuple[str, ...]
    attributes: tuple[tuple[str, str], ...]
    integrity_identity: str
    schema_identity: str = SEMANTIC_FACT_V2_IDENTITY
    schema_version: str = V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("fact_identity")
        values.pop("integrity_identity")
        if (
            not self.fact_identity.startswith("INTRADAY-SEMANTIC-V2-FACT-")
            or not _texts((self.family, self.canonical_subject_identity, self.availability))
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or self.availability not in {"AVAILABLE", "UNAVAILABLE"}
            or type(self.direction) is not SemanticDirection
            or type(self.evidence_role) is not SemanticEvidenceRoleV2
            or not _texts(self.source_evidence_identities)
            or tuple(sorted(self.attributes)) != self.attributes
            or len({name for name, _ in self.attributes}) != len(self.attributes)
            or any(not _texts(item) for item in self.attributes)
            or self.schema_identity != SEMANTIC_FACT_V2_IDENTITY
            or self.schema_version != V2_CONTRACT_VERSION
            or self.fact_identity != _identity("INTRADAY-SEMANTIC-V2-FACT-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-SEMANTIC-V2-FACT-", values)
        ):
            raise ProbablesV2Error("SEMANTIC_V2_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class SemanticQualificationEvidenceV2:
    evidence_identity: str
    canonical_subject_identity: str
    analysis_boundary: datetime
    phase: IntradayAnalysisPhase
    completed_evidence_selection_identity: str
    narrow_cpr_fact_identity: str
    narrow_cpr_qualified: bool
    facts: tuple[SemanticQualificationFactV2, ...]
    opening_semantic_evidence_identity: str | None
    nifty_relative_evidence_identity: str | None
    nifty_applicability: NiftyApplicability | None
    participation_state: str
    reference_fact_identities: tuple[tuple[str, str], ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = SEMANTIC_EVIDENCE_V2_IDENTITY
    schema_version: str = V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("evidence_identity")
        values.pop("integrity_identity")
        families = tuple(item.family for item in self.facts)
        required = _required_families(self.phase)
        if (
            not self.evidence_identity.startswith("INTRADAY-SEMANTIC-V2-EVIDENCE-")
            or not _texts((
                self.canonical_subject_identity,
                self.completed_evidence_selection_identity,
                self.narrow_cpr_fact_identity,
                self.participation_state,
            ))
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or type(self.narrow_cpr_qualified) is not bool
            or any(type(item) is not SemanticQualificationFactV2 for item in self.facts)
            or families != required
            or any(
                item.canonical_subject_identity != self.canonical_subject_identity
                or item.analysis_boundary != self.analysis_boundary
                or item.phase is not self.phase
                for item in self.facts
            )
            or (
                self.phase is IntradayAnalysisPhase.OPENING
                and (
                    not _text(self.opening_semantic_evidence_identity)
                    or not _text(self.nifty_relative_evidence_identity)
                    or type(self.nifty_applicability) is not NiftyApplicability
                )
            )
            or (
                self.phase is not IntradayAnalysisPhase.OPENING
                and self.opening_semantic_evidence_identity is not None
            )
            or tuple(sorted(self.reference_fact_identities))
            != self.reference_fact_identities
            or not _texts(self.provenance)
            or self.schema_identity != SEMANTIC_EVIDENCE_V2_IDENTITY
            or self.schema_version != V2_CONTRACT_VERSION
            or self.evidence_identity
            != _identity("INTRADAY-SEMANTIC-V2-EVIDENCE-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-SEMANTIC-V2-EVIDENCE-", values)
        ):
            raise ProbablesV2Error("SEMANTIC_V2_EVIDENCE_INVALID")

    def fact(self, family: str) -> SemanticQualificationFactV2:
        try:
            return next(item for item in self.facts if item.family == family)
        except StopIteration as error:
            raise ProbablesV2Error("SEMANTIC_V2_FACT_UNAVAILABLE") from error


def build_semantic_qualification_evidence_v2(
    *,
    selection: CompletedEvidenceSelection,
    narrow_cpr_fact: NarrowCprFact,
    opening_semantic: OpeningSemanticEvidence | None = None,
    nifty_relative: NiftyRelativeContextEvidence | None = None,
    reference_fact_identities: tuple[tuple[str, str], ...] = (),
    participation_state: str = "UNAVAILABLE",
    provenance: tuple[str, ...],
) -> SemanticQualificationEvidenceV2:
    """Adapt exact selected candles into phase-specific V2 semantic facts."""

    if (
        not is_completed_evidence_selection(selection)
        or type(narrow_cpr_fact) is not NarrowCprFact
        or narrow_cpr_fact.canonical_subject_identity
        != selection.canonical_subject_identity
        or narrow_cpr_fact.observation_boundary > selection.analysis_boundary
        or not _text(participation_state)
        or not _texts(provenance)
    ):
        raise ProbablesV2Error("SEMANTIC_V2_INPUT_INVALID")
    facts: list[SemanticQualificationFactV2] = []
    daily = selection.candles(_daily(), EvidenceSessionRole.PREVIOUS_SESSION_DAILY)
    facts.append(_fact(
        family="1D_CONTEXT",
        selection=selection,
        direction=SemanticDirection.NON_DIRECTIONAL,
        role=SemanticEvidenceRoleV2.MANDATORY_INFORMATIONAL,
        sources=tuple(item.candle_identity for item in daily),
        attributes=(("consequence", "INFORMATIONAL"),),
    ))
    if selection.phase is IntradayAnalysisPhase.OPENING:
        if (
            type(opening_semantic) is not OpeningSemanticEvidence
            or type(nifty_relative) is not NiftyRelativeContextEvidence
            or opening_semantic.fact.completed_evidence_selection_identity
            != selection.selection_identity
            or nifty_relative.fact.analysis_boundary != selection.analysis_boundary
        ):
            raise ProbablesV2Error("SEMANTIC_V2_OPENING_INPUT_INVALID")
        opening = opening_semantic.fact
        facts.extend((
            _fact(
                family="1H_REGIME", selection=selection,
                direction=opening.prior_one_hour_direction,
                role=SemanticEvidenceRoleV2.OPENING_CONFLICT_INPUT,
                sources=opening.prior_one_hour_candle_identities,
                attributes=(("relationship", opening.prior_one_hour_relationship.value),),
            ),
            _fact(
                family="OPENING_15M", selection=selection,
                direction=opening.opening_direction,
                role=SemanticEvidenceRoleV2.OPENING_DIRECTIONAL,
                sources=(opening.opening_candle_identity,),
                attributes=(("normal_15m_structure", "DEFERRED_IN_OPENING"),),
            ),
            _fact(
                family="5M_PROGRESSION", selection=selection,
                direction=opening.five_minute_progression,
                role=SemanticEvidenceRoleV2.OPENING_CONFLICT_INPUT,
                sources=opening.opening_5m_candle_identities,
                attributes=(("relationship", opening.five_minute_relationship.value),),
            ),
            _fact(
                family="DIRECTIONAL_COHERENCE", selection=selection,
                direction=(
                    opening.opening_direction
                    if opening_semantic.combined_relationship is OpeningRelationship.SUPPORTING
                    else SemanticDirection.CONFLICTING
                    if opening_semantic.combined_relationship is OpeningRelationship.CONFLICTING
                    else SemanticDirection.NON_DIRECTIONAL
                ),
                role=SemanticEvidenceRoleV2.MANDATORY_DIRECTIONAL,
                sources=(opening_semantic.evidence_identity,),
                attributes=(("combined_relationship", opening_semantic.combined_relationship.value),),
            ),
            _fact(
                family="NIFTY_RELATIVE_CONTEXT", selection=selection,
                direction=SemanticDirection.NON_DIRECTIONAL,
                role=SemanticEvidenceRoleV2.OPENING_CONFLICT_INPUT,
                sources=(nifty_relative.evidence_identity,),
                attributes=(("applicability", nifty_relative.fact.applicability.value), ("relationship", nifty_relative.relationship.value)),
            ),
        ))
        opening_identity = opening_semantic.evidence_identity
        nifty_identity = nifty_relative.evidence_identity
        nifty_applicability = nifty_relative.fact.applicability
    else:
        prior = selection.candles(_hour(), EvidenceSessionRole.PRIOR_SESSION_1H_CONTEXT)
        current_hour = selection.candles(_hour(), EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY)
        fifteen = selection.candles(_fifteen(), EvidenceSessionRole.CURRENT_SESSION_15M)
        five = selection.candles(_five(), EvidenceSessionRole.CURRENT_SESSION_5M)
        if selection.phase is IntradayAnalysisPhase.STRUCTURE:
            hourly_direction = _movement(prior[-2], prior[-1])
            hourly_sources = tuple(item.candle_identity for item in prior[-2:])
            hourly_role = "PRIOR_SESSION_CONTEXT"
        elif selection.phase is IntradayAnalysisPhase.FIRST_CURRENT_SESSION_1H:
            hourly_direction = _movement(prior[-1], current_hour[0])
            hourly_sources = (prior[-1].candle_identity, current_hour[0].candle_identity)
            hourly_role = "CROSS_SESSION_TRANSITION_CURRENT_PRIMARY"
        else:
            hourly_direction = _movement(current_hour[-2], current_hour[-1])
            hourly_sources = tuple(item.candle_identity for item in current_hour[-2:])
            hourly_role = "LATEST_TWO_CURRENT_SESSION"
        fifteen_direction = _movement(fifteen[-2], fifteen[-1])
        coherence = (
            hourly_direction
            if hourly_direction in {SemanticDirection.LONG, SemanticDirection.SHORT}
            and hourly_direction is fifteen_direction
            else SemanticDirection.CONFLICTING
            if hourly_direction in {SemanticDirection.LONG, SemanticDirection.SHORT}
            and fifteen_direction in {SemanticDirection.LONG, SemanticDirection.SHORT}
            else SemanticDirection.NON_DIRECTIONAL
        )
        five_direction = (
            _movement(five[-2], five[-1]) if len(five) >= 2 else SemanticDirection.UNAVAILABLE
        )
        facts.extend((
            _fact(
                family="1H_REGIME", selection=selection,
                direction=hourly_direction,
                role=SemanticEvidenceRoleV2.MANDATORY_DIRECTIONAL,
                sources=hourly_sources,
                attributes=(("one_hour_role", hourly_role),),
            ),
            _fact(
                family="15M_STRUCTURE", selection=selection,
                direction=fifteen_direction,
                role=SemanticEvidenceRoleV2.MANDATORY_DIRECTIONAL,
                sources=tuple(item.candle_identity for item in fifteen[-2:]),
                attributes=(("structure", "LATEST_TWO_CURRENT_SESSION"),),
            ),
            _fact(
                family="5M_PROGRESSION", selection=selection,
                direction=five_direction,
                role=SemanticEvidenceRoleV2.INFORMATIONAL,
                sources=(
                    tuple(item.candle_identity for item in five[-2:])
                    if five else (selection.selection_identity,)
                ),
                attributes=(("consequence", "INFORMATIONAL"),),
            ),
            _fact(
                family="DIRECTIONAL_COHERENCE", selection=selection,
                direction=coherence,
                role=SemanticEvidenceRoleV2.MANDATORY_DIRECTIONAL,
                sources=hourly_sources + tuple(item.candle_identity for item in fifteen[-2:]),
                attributes=(("coherence", coherence.value),),
            ),
        ))
        opening_identity = None
        nifty_identity = None if nifty_relative is None else nifty_relative.evidence_identity
        nifty_applicability = None if nifty_relative is None else nifty_relative.fact.applicability
    values = {
        "canonical_subject_identity": selection.canonical_subject_identity,
        "analysis_boundary": selection.analysis_boundary,
        "phase": selection.phase,
        "completed_evidence_selection_identity": selection.selection_identity,
        "narrow_cpr_fact_identity": narrow_cpr_fact.fact_identity,
        "narrow_cpr_qualified": narrow_cpr_fact.narrow_cpr_kgs_v0,
        "facts": tuple(facts),
        "opening_semantic_evidence_identity": opening_identity,
        "nifty_relative_evidence_identity": nifty_identity,
        "nifty_applicability": nifty_applicability,
        "participation_state": participation_state,
        "reference_fact_identities": tuple(sorted(reference_fact_identities)),
        "provenance": provenance,
        "schema_identity": SEMANTIC_EVIDENCE_V2_IDENTITY,
        "schema_version": V2_CONTRACT_VERSION,
    }
    return SemanticQualificationEvidenceV2(
        evidence_identity=_identity("INTRADAY-SEMANTIC-V2-EVIDENCE-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-SEMANTIC-V2-EVIDENCE-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class DiscoveryProbablesEvidenceV2:
    mapping_identity: str
    universe_member_identity: str
    canonical_subject_identity: str
    source_discovery_run_identity: str
    source_discovery_member_identity: str
    market_session_identity: str
    analysis_boundary: datetime
    methodology_identity: str
    methodology_version: str
    methodology_publication_identity: str
    methodology_checksum: str
    phase: IntradayAnalysisPhase
    completed_evidence: CompletedEvidenceSelection
    semantic_evidence: SemanticQualificationEvidenceV2
    opening_semantic: OpeningSemanticEvidence | None
    nifty_relative: NiftyRelativeContextEvidence | None
    provenance: tuple[str, ...]
    integrity_identity: str
    mapper_identity: str = DISCOVERY_PROBABLES_MAPPER_V2_IDENTITY
    mapper_version: str = V2_CONTRACT_VERSION
    schema_identity: str = DISCOVERY_PROBABLES_EVIDENCE_V2_IDENTITY
    schema_version: str = V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("mapping_identity")
        values.pop("integrity_identity")
        if (
            not self.mapping_identity.startswith("INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-")
            or not _texts((
                self.universe_member_identity,
                self.canonical_subject_identity,
                self.source_discovery_run_identity,
                self.source_discovery_member_identity,
                self.market_session_identity,
            ))
            or not _aware(self.analysis_boundary)
            or not probables_v2_methodology_binding_supported(
                self.methodology_identity,
                self.methodology_version,
                self.methodology_publication_identity,
                self.methodology_checksum,
            )
            or type(self.phase) is not IntradayAnalysisPhase
            or not is_completed_evidence_selection(self.completed_evidence)
            or type(self.semantic_evidence) is not SemanticQualificationEvidenceV2
            or self.completed_evidence.canonical_subject_identity != self.canonical_subject_identity
            or self.completed_evidence.analysis_boundary != self.analysis_boundary
            or self.completed_evidence.phase is not self.phase
            or self.semantic_evidence.canonical_subject_identity != self.canonical_subject_identity
            or self.semantic_evidence.analysis_boundary != self.analysis_boundary
            or self.semantic_evidence.phase is not self.phase
            or self.semantic_evidence.completed_evidence_selection_identity
            != self.completed_evidence.selection_identity
            or (
                self.phase is IntradayAnalysisPhase.OPENING
                and (
                    type(self.opening_semantic) is not OpeningSemanticEvidence
                    or type(self.nifty_relative) is not NiftyRelativeContextEvidence
                    or self.semantic_evidence.opening_semantic_evidence_identity
                    != self.opening_semantic.evidence_identity
                    or self.semantic_evidence.nifty_relative_evidence_identity
                    != self.nifty_relative.evidence_identity
                )
            )
            or not _texts(self.provenance)
            or self.mapper_identity != DISCOVERY_PROBABLES_MAPPER_V2_IDENTITY
            or self.mapper_version != V2_CONTRACT_VERSION
            or self.schema_identity != DISCOVERY_PROBABLES_EVIDENCE_V2_IDENTITY
            or self.schema_version != V2_CONTRACT_VERSION
            or self.mapping_identity
            != _identity("INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-", values)
        ):
            raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_MAPPING_INVALID")


def create_discovery_probables_evidence_v2(
    *,
    universe_member_identity: str,
    source_discovery_run_identity: str,
    source_discovery_member_identity: str,
    market_session_identity: str,
    completed_evidence: CompletedEvidenceSelection,
    semantic_evidence: SemanticQualificationEvidenceV2,
    opening_semantic: OpeningSemanticEvidence | None,
    nifty_relative: NiftyRelativeContextEvidence | None,
    provenance: tuple[str, ...],
    methodology: ProbablesMethodologyV2 | None = None,
) -> DiscoveryProbablesEvidenceV2:
    selected_methodology = methodology or create_probables_v2_methodology()
    if type(selected_methodology) is not ProbablesMethodologyV2:
        raise ProbablesV2Error("PROBABLES_V2_METHODOLOGY_INVALID")
    values = {
        "universe_member_identity": universe_member_identity,
        "canonical_subject_identity": completed_evidence.canonical_subject_identity,
        "source_discovery_run_identity": source_discovery_run_identity,
        "source_discovery_member_identity": source_discovery_member_identity,
        "market_session_identity": market_session_identity,
        "analysis_boundary": completed_evidence.analysis_boundary,
        "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
        "methodology_version": selected_methodology.methodology_version,
        "methodology_publication_identity": selected_methodology.publication_identity,
        "methodology_checksum": selected_methodology.payload_checksum,
        "phase": completed_evidence.phase,
        "completed_evidence": completed_evidence,
        "semantic_evidence": semantic_evidence,
        "opening_semantic": opening_semantic,
        "nifty_relative": nifty_relative,
        "provenance": provenance,
        "mapper_identity": DISCOVERY_PROBABLES_MAPPER_V2_IDENTITY,
        "mapper_version": V2_CONTRACT_VERSION,
        "schema_identity": DISCOVERY_PROBABLES_EVIDENCE_V2_IDENTITY,
        "schema_version": V2_CONTRACT_VERSION,
    }
    return DiscoveryProbablesEvidenceV2(
        mapping_identity=_identity(
            "INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-", values
        ),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class ProbablesUnavailableMemberV2:
    universe_member_identity: str
    canonical_subject_identity: str
    market_session_identity: str
    analysis_boundary: datetime
    reason: ProbableReasonV2
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
            or not _aware(self.analysis_boundary)
            or self.reason not in {
                ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE,
                ProbableReasonV2.SOURCE_DISCOVERY_UNAVAILABLE,
            }
            or not _texts(self.provenance)
        ):
            raise ProbablesV2Error("PROBABLES_V2_UNAVAILABLE_MEMBER_INVALID")


@dataclass(frozen=True, slots=True)
class ProbableMemberResultV2:
    result_identity: str
    universe_member_identity: str
    canonical_subject_identity: str
    market_session_identity: str
    analysis_boundary: datetime
    phase: IntradayAnalysisPhase | None
    state: ProbableState
    direction: SemanticDirection | None
    reasons: tuple[ProbableReasonV2, ...]
    completed_evidence_selection_identity: str | None
    semantic_evidence_identity: str | None
    opening_semantic_evidence_identity: str | None
    nifty_relative_evidence_identity: str | None
    nifty_applicability: NiftyApplicability | None
    nifty_relationship: NiftyRelationship | None
    source_mapping_identity: str | None
    source_discovery_run_identity: str
    source_discovery_member_identity: str
    methodology_identity: str
    methodology_version: str
    methodology_publication_identity: str
    methodology_checksum: str
    participation_state: str
    execution_eligibility: str
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = PROBABLE_V2_IDENTITY
    schema_version: str = V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("result_identity")
        values.pop("integrity_identity")
        admitted = self.state in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
        mapped_unavailable = (
            self.state is ProbableState.UNAVAILABLE
            and self.source_mapping_identity is not None
        )
        pre_mapping_unavailable = (
            self.state is ProbableState.UNAVAILABLE
            and self.source_mapping_identity is None
        )
        mapped_unavailable_reasons = {
            ProbableReasonV2.NIFTY_CONTEXT_UNAVAILABLE,
            ProbableReasonV2.MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED,
        }
        pre_mapping_unavailable_reasons = {
            ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE,
            ProbableReasonV2.SOURCE_DISCOVERY_UNAVAILABLE,
        }
        if (
            not self.result_identity.startswith("INTRADAY-PROBABLE-V2-RESULT-")
            or not _texts((
                self.universe_member_identity,
                self.canonical_subject_identity,
                self.market_session_identity,
                self.source_discovery_run_identity,
                self.source_discovery_member_identity,
                self.participation_state,
            ))
            or not _aware(self.analysis_boundary)
            or self.phase is not None and type(self.phase) is not IntradayAnalysisPhase
            or type(self.state) is not ProbableState
            or self.direction is not None and type(self.direction) is not SemanticDirection
            or self.nifty_relationship is not None
            and type(self.nifty_relationship) is not NiftyRelationship
            or self.nifty_applicability is not None
            and type(self.nifty_applicability) is not NiftyApplicability
            or (
                self.state is not ProbableState.UNAVAILABLE
                and not _text(self.source_mapping_identity)
            )
            or (
                mapped_unavailable
                and (
                    not _text(self.source_mapping_identity)
                    or len(self.reasons) != 1
                    or self.reasons[0] not in mapped_unavailable_reasons
                    or any(item is None for item in (
                        self.phase,
                        self.completed_evidence_selection_identity,
                        self.semantic_evidence_identity,
                    ))
                )
            )
            or (
                pre_mapping_unavailable
                and (
                    len(self.reasons) != 1
                    or self.reasons[0] not in pre_mapping_unavailable_reasons
                    or any(item is not None for item in (
                        self.phase,
                        self.completed_evidence_selection_identity,
                        self.semantic_evidence_identity,
                        self.opening_semantic_evidence_identity,
                        self.nifty_relative_evidence_identity,
                        self.nifty_applicability,
                        self.nifty_relationship,
                    ))
                )
            )
            or (
                self.reasons
                == (ProbableReasonV2.MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED,)
                and (
                    not mapped_unavailable
                    or self.nifty_applicability is not NiftyApplicability.NOT_APPLICABLE
                    or self.nifty_relationship is not NiftyRelationship.NOT_APPLICABLE
                )
            )
            or not self.reasons
            or any(type(item) is not ProbableReasonV2 for item in self.reasons)
            or not probables_v2_methodology_binding_supported(
                self.methodology_identity,
                self.methodology_version,
                self.methodology_publication_identity,
                self.methodology_checksum,
            )
            or self.execution_eligibility != "NOT_ESTABLISHED"
            or (
                self.state is ProbableState.LONG_PROBABLE
                and self.direction is not SemanticDirection.LONG
            )
            or (
                self.state is ProbableState.SHORT_PROBABLE
                and self.direction is not SemanticDirection.SHORT
            )
            or (
                self.state is ProbableState.UNAVAILABLE
                and self.direction is not None
            )
            or (
                admitted
                and self.direction
                not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            )
            or (admitted and any(item is None for item in (
                self.phase,
                self.completed_evidence_selection_identity,
                self.semantic_evidence_identity,
            )))
            or not _texts(self.provenance)
            or self.schema_identity != PROBABLE_V2_IDENTITY
            or self.schema_version != V2_CONTRACT_VERSION
            or self.result_identity != _identity("INTRADAY-PROBABLE-V2-RESULT-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-PROBABLE-V2-RESULT-", values)
        ):
            raise ProbablesV2Error("PROBABLES_V2_RESULT_INVALID")


@dataclass(frozen=True, slots=True)
class ProbablesPopulationDiagnosticsV2:
    diagnostics_identity: str
    starting_population: int
    evaluable_count: int
    unavailable_count: int
    long_probables: int
    short_probables: int
    total_probables: int
    not_admitted_count: int
    conflicting_count: int
    phase_counts: tuple[tuple[IntradayAnalysisPhase, int], ...]
    population_bucket: PopulationBucket
    integrity_identity: str
    schema_identity: str = POPULATION_DIAGNOSTICS_V2_IDENTITY
    schema_version: str = V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("diagnostics_identity")
        values.pop("integrity_identity")
        counts = (
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
            not self.diagnostics_identity.startswith("INTRADAY-PROBABLES-V2-DIAGNOSTICS-")
            or any(type(item) is not int or item < 0 for item in counts)
            or self.starting_population != self.evaluable_count + self.unavailable_count
            or self.evaluable_count != self.total_probables + self.not_admitted_count
            or self.total_probables != self.long_probables + self.short_probables
            or tuple(phase for phase, _ in self.phase_counts) != tuple(IntradayAnalysisPhase)
            or any(type(count) is not int or count < 0 for _, count in self.phase_counts)
            or type(self.population_bucket) is not PopulationBucket
            or self.schema_identity != POPULATION_DIAGNOSTICS_V2_IDENTITY
            or self.schema_version != V2_CONTRACT_VERSION
            or self.diagnostics_identity
            != _identity("INTRADAY-PROBABLES-V2-DIAGNOSTICS-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-PROBABLES-V2-DIAGNOSTICS-", values)
        ):
            raise ProbablesV2Error("PROBABLES_V2_DIAGNOSTICS_INVALID")


@dataclass(frozen=True, slots=True)
class ProbablesRunV2:
    run_identity: str
    source_kind: FactualSourceKind
    source_discovery_run_identity: str
    universe_identity: str
    universe_version: str
    reconciliation_identity: str
    reconciliation_version: str
    market_session_identity: str
    analysis_boundary: datetime
    methodology: ProbablesMethodologyV2
    results: tuple[ProbableMemberResultV2, ...]
    diagnostics: ProbablesPopulationDiagnosticsV2
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = PROBABLES_RUN_V2_IDENTITY
    schema_version: str = V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("run_identity")
        values.pop("integrity_identity")
        if (
            not self.run_identity.startswith("INTRADAY-PROBABLES-V2-RUN-")
            or type(self.source_kind) is not FactualSourceKind
            or not _texts((
                self.source_discovery_run_identity,
                self.universe_identity,
                self.universe_version,
                self.reconciliation_identity,
                self.reconciliation_version,
                self.market_session_identity,
            ))
            or not _aware(self.analysis_boundary)
            or type(self.methodology) is not ProbablesMethodologyV2
            or not self.results
            or any(type(item) is not ProbableMemberResultV2 for item in self.results)
            or tuple(sorted(self.results, key=lambda item: item.universe_member_identity))
            != self.results
            or len({item.universe_member_identity for item in self.results})
            != len(self.results)
            or any(
                item.analysis_boundary != self.analysis_boundary
                or item.source_discovery_run_identity != self.source_discovery_run_identity
                or item.methodology_identity != self.methodology.methodology_identity
                or item.methodology_version != self.methodology.methodology_version
                or item.methodology_publication_identity
                != self.methodology.publication_identity
                or item.methodology_checksum != self.methodology.payload_checksum
                for item in self.results
            )
            or type(self.diagnostics) is not ProbablesPopulationDiagnosticsV2
            or self.diagnostics.starting_population != len(self.results)
            or not _texts(self.provenance)
            or self.schema_identity != PROBABLES_RUN_V2_IDENTITY
            or self.schema_version != V2_CONTRACT_VERSION
            or self.run_identity != _identity("INTRADAY-PROBABLES-V2-RUN-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-PROBABLES-V2-RUN-", values)
        ):
            raise ProbablesV2Error("PROBABLES_V2_RUN_INVALID")


def evaluate_probables_v2_run(
    *,
    source_discovery_run_identity: str,
    universe_identity: str,
    universe_version: str,
    reconciliation_identity: str,
    reconciliation_version: str,
    market_session_identity: str,
    analysis_boundary: datetime,
    member_evidence: Sequence[DiscoveryProbablesEvidenceV2],
    unavailable_members: Sequence[ProbablesUnavailableMemberV2],
    provenance: tuple[str, ...],
    methodology: ProbablesMethodologyV2 | None = None,
) -> ProbablesRunV2:
    selected_methodology = methodology or create_probables_v2_methodology()
    if (
        not _texts((
            source_discovery_run_identity,
            universe_identity,
            universe_version,
            reconciliation_identity,
            reconciliation_version,
            market_session_identity,
        ))
        or not _aware(analysis_boundary)
        or not _texts(provenance)
        or type(selected_methodology) is not ProbablesMethodologyV2
    ):
        raise ProbablesV2Error("PROBABLES_V2_RUN_INPUT_INVALID")
    evidence = tuple(member_evidence)
    unavailable = tuple(unavailable_members)
    identities = tuple(item.universe_member_identity for item in (*evidence, *unavailable))
    if (
        not identities
        or len(set(identities)) != len(identities)
        or any(
            type(item) is not DiscoveryProbablesEvidenceV2
            or item.source_discovery_run_identity != source_discovery_run_identity
            or item.analysis_boundary != analysis_boundary
            or item.methodology_identity != selected_methodology.methodology_identity
            or item.methodology_version != selected_methodology.methodology_version
            or item.methodology_publication_identity
            != selected_methodology.publication_identity
            or item.methodology_checksum != selected_methodology.payload_checksum
            for item in evidence
        )
        or any(
            type(item) is not ProbablesUnavailableMemberV2
            or item.analysis_boundary != analysis_boundary
            or item.source_identity != source_discovery_run_identity
            for item in unavailable
        )
    ):
        raise ProbablesV2Error("PROBABLES_V2_POPULATION_INVALID")
    mapped_results = tuple(_evaluate_member(item) for item in evidence)
    if any(
        not _mapped_result_lineage_valid(result, source)
        for result, source in zip(mapped_results, evidence, strict=True)
    ):
        raise ProbablesV2Error("PROBABLES_V2_RESULT_MAPPING_INVALID")
    results = tuple(sorted(
        (*mapped_results, *(
            _unavailable_result(item, selected_methodology) for item in unavailable
        )),
        key=lambda item: item.universe_member_identity,
    ))
    diagnostics = _diagnostics(results)
    values = {
        "source_kind": FactualSourceKind.NATIVE_DISCOVERY,
        "source_discovery_run_identity": source_discovery_run_identity,
        "universe_identity": universe_identity,
        "universe_version": universe_version,
        "reconciliation_identity": reconciliation_identity,
        "reconciliation_version": reconciliation_version,
        "market_session_identity": market_session_identity,
        "analysis_boundary": analysis_boundary,
        "methodology": selected_methodology,
        "results": results,
        "diagnostics": diagnostics,
        "provenance": provenance,
        "schema_identity": PROBABLES_RUN_V2_IDENTITY,
        "schema_version": V2_CONTRACT_VERSION,
    }
    return ProbablesRunV2(
        run_identity=_identity("INTRADAY-PROBABLES-V2-RUN-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-PROBABLES-V2-RUN-", values),
        **values,
    )


def _evaluate_member(value: DiscoveryProbablesEvidenceV2) -> ProbableMemberResultV2:
    semantic = value.semantic_evidence
    if value.completed_evidence.market_identity == "MCX":
        commissioning = load_mcx_commissioning_publication().subject(
            value.canonical_subject_identity
        )
        if commissioning.state is McxCommissioningState.HELD:
            return _result(
                value, ProbableState.UNAVAILABLE, None,
                (ProbableReasonV2.MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED,),
            )
    if value.phase is IntradayAnalysisPhase.OPENING:
        assert value.opening_semantic is not None and value.nifty_relative is not None
        opening = value.opening_semantic.fact
        direction = opening.opening_direction
        if (
            value.nifty_relative.fact.applicability is NiftyApplicability.APPLICABLE
            and value.nifty_relative.relationship is NiftyRelationship.UNAVAILABLE
        ):
            return _result(
                value, ProbableState.UNAVAILABLE, None,
                (ProbableReasonV2.NIFTY_CONTEXT_UNAVAILABLE,),
            )
        if not semantic.narrow_cpr_qualified:
            return _result(
                value, ProbableState.NOT_ADMITTED, direction,
                (ProbableReasonV2.NARROW_CPR_NOT_SATISFIED,),
            )
        if direction is SemanticDirection.NON_DIRECTIONAL:
            return _result(
                value, ProbableState.NOT_ADMITTED, direction,
                (ProbableReasonV2.OPENING_NON_DIRECTIONAL,),
            )
        reasons: list[ProbableReasonV2] = []
        if opening.prior_one_hour_relationship is OpeningRelationship.CONFLICTING:
            reasons.append(ProbableReasonV2.PRIOR_1H_CONFLICTING_NO_DIRECTION_FLIP)
        if opening.five_minute_relationship is not OpeningRelationship.SUPPORTING:
            reasons.append(ProbableReasonV2.OPENING_5M_NOT_SUPPORTING)
        if value.nifty_relative.relationship is NiftyRelationship.CONFLICTING:
            reasons.append(ProbableReasonV2.NIFTY_CONTEXT_CONFLICTING_NO_DIRECTION_FLIP)
        if not reasons and value.opening_semantic.combined_relationship is not OpeningRelationship.SUPPORTING:
            reasons.append(ProbableReasonV2.OPENING_RELATIONSHIP_NOT_SUPPORTING)
        if reasons:
            return _result(value, ProbableState.NOT_ADMITTED, direction, tuple(reasons))
        state = (
            ProbableState.LONG_PROBABLE
            if direction is SemanticDirection.LONG
            else ProbableState.SHORT_PROBABLE
        )
        return _result(
            value, state, direction,
            (ProbableReasonV2.V2_CONDITIONS_SATISFIED,),
        )
    hourly = semantic.fact("1H_REGIME")
    fifteen = semantic.fact("15M_STRUCTURE")
    if not semantic.narrow_cpr_qualified:
        return _result(
            value, ProbableState.NOT_ADMITTED, _coherent_direction(hourly.direction, fifteen.direction),
            (ProbableReasonV2.NARROW_CPR_NOT_SATISFIED,),
        )
    if hourly.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}:
        return _result(
            value, ProbableState.NOT_ADMITTED, hourly.direction,
            (ProbableReasonV2.ONE_HOUR_NON_DIRECTIONAL,),
        )
    if fifteen.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}:
        return _result(
            value, ProbableState.NOT_ADMITTED, fifteen.direction,
            (ProbableReasonV2.FIFTEEN_MINUTE_NON_DIRECTIONAL,),
        )
    if hourly.direction is not fifteen.direction:
        return _result(
            value, ProbableState.NOT_ADMITTED, SemanticDirection.CONFLICTING,
            (ProbableReasonV2.DIRECTION_CONFLICTING,),
        )
    state = (
        ProbableState.LONG_PROBABLE
        if hourly.direction is SemanticDirection.LONG
        else ProbableState.SHORT_PROBABLE
    )
    return _result(
        value, state, hourly.direction,
        (ProbableReasonV2.V2_CONDITIONS_SATISFIED,),
    )


def _mapped_result_lineage_valid(
    result: ProbableMemberResultV2,
    source: DiscoveryProbablesEvidenceV2,
) -> bool:
    mapping_values = asdict(source)
    mapping_values.pop("mapping_identity")
    mapping_values.pop("integrity_identity")
    return (
        source.mapping_identity
        == _identity("INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-", mapping_values)
        and source.integrity_identity
        == _identity(
            "INTEGRITY-INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-",
            mapping_values,
        )
        and result.source_mapping_identity == source.mapping_identity
        and result.universe_member_identity == source.universe_member_identity
        and result.canonical_subject_identity == source.canonical_subject_identity
        and result.source_discovery_run_identity
        == source.source_discovery_run_identity
        and result.source_discovery_member_identity
        == source.source_discovery_member_identity
        and result.market_session_identity == source.market_session_identity
        and result.analysis_boundary == source.analysis_boundary
        and result.phase is source.phase
        and result.completed_evidence_selection_identity
        == source.completed_evidence.selection_identity
        and result.semantic_evidence_identity
        == source.semantic_evidence.evidence_identity
        and result.methodology_identity == source.methodology_identity
        and result.methodology_version == source.methodology_version
        and result.methodology_publication_identity
        == source.methodology_publication_identity
        and result.methodology_checksum == source.methodology_checksum
    )


def _result(
    source: DiscoveryProbablesEvidenceV2,
    state: ProbableState,
    direction: SemanticDirection | None,
    reasons: tuple[ProbableReasonV2, ...],
) -> ProbableMemberResultV2:
    mcx_mapped_unavailable = (
        state is ProbableState.UNAVAILABLE
        and reasons
        == (ProbableReasonV2.MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED,)
    )
    values = {
        "universe_member_identity": source.universe_member_identity,
        "canonical_subject_identity": source.canonical_subject_identity,
        "market_session_identity": source.market_session_identity,
        "analysis_boundary": source.analysis_boundary,
        "phase": source.phase,
        "state": state,
        "direction": direction,
        "reasons": reasons,
        "completed_evidence_selection_identity": source.completed_evidence.selection_identity,
        "semantic_evidence_identity": source.semantic_evidence.evidence_identity,
        "opening_semantic_evidence_identity": (
            None if source.opening_semantic is None else source.opening_semantic.evidence_identity
        ),
        "nifty_relative_evidence_identity": (
            None if source.nifty_relative is None else source.nifty_relative.evidence_identity
        ),
        "nifty_applicability": (
            NiftyApplicability.NOT_APPLICABLE
            if mcx_mapped_unavailable
            else None
            if source.nifty_relative is None
            else source.nifty_relative.fact.applicability
        ),
        "nifty_relationship": (
            NiftyRelationship.NOT_APPLICABLE
            if mcx_mapped_unavailable
            else None
            if source.nifty_relative is None
            else source.nifty_relative.relationship
        ),
        "source_mapping_identity": source.mapping_identity,
        "source_discovery_run_identity": source.source_discovery_run_identity,
        "source_discovery_member_identity": source.source_discovery_member_identity,
        "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
        "methodology_version": source.methodology_version,
        "methodology_publication_identity": source.methodology_publication_identity,
        "methodology_checksum": source.methodology_checksum,
        "participation_state": source.semantic_evidence.participation_state,
        "execution_eligibility": "NOT_ESTABLISHED",
        "provenance": source.provenance + _mcx_commissioning_provenance(source),
        "schema_identity": PROBABLE_V2_IDENTITY,
        "schema_version": V2_CONTRACT_VERSION,
    }
    return ProbableMemberResultV2(
        result_identity=_identity("INTRADAY-PROBABLE-V2-RESULT-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-PROBABLE-V2-RESULT-", values),
        **values,
    )


def _coherent_direction(
    hourly: SemanticDirection,
    fifteen: SemanticDirection,
) -> SemanticDirection:
    if hourly is fifteen:
        return hourly
    if hourly in {SemanticDirection.LONG, SemanticDirection.SHORT} and fifteen in {
        SemanticDirection.LONG,
        SemanticDirection.SHORT,
    }:
        return SemanticDirection.CONFLICTING
    return SemanticDirection.NON_DIRECTIONAL


def _unavailable_result(
    value: ProbablesUnavailableMemberV2,
    methodology: ProbablesMethodologyV2,
) -> ProbableMemberResultV2:
    values = {
        "universe_member_identity": value.universe_member_identity,
        "canonical_subject_identity": value.canonical_subject_identity,
        "market_session_identity": value.market_session_identity,
        "analysis_boundary": value.analysis_boundary,
        "phase": None,
        "state": ProbableState.UNAVAILABLE,
        "direction": None,
        "reasons": (value.reason,),
        "completed_evidence_selection_identity": None,
        "semantic_evidence_identity": None,
        "opening_semantic_evidence_identity": None,
        "nifty_relative_evidence_identity": None,
        "nifty_applicability": None,
        "nifty_relationship": None,
        "source_mapping_identity": None,
        "source_discovery_run_identity": value.source_identity,
        "source_discovery_member_identity": value.source_identity,
        "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
        "methodology_version": methodology.methodology_version,
        "methodology_publication_identity": methodology.publication_identity,
        "methodology_checksum": methodology.payload_checksum,
        "participation_state": "UNAVAILABLE",
        "execution_eligibility": "NOT_ESTABLISHED",
        "provenance": value.provenance,
        "schema_identity": PROBABLE_V2_IDENTITY,
        "schema_version": V2_CONTRACT_VERSION,
    }
    return ProbableMemberResultV2(
        result_identity=_identity("INTRADAY-PROBABLE-V2-RESULT-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-PROBABLE-V2-RESULT-", values),
        **values,
    )


def _mcx_commissioning_provenance(
    source: DiscoveryProbablesEvidenceV2,
) -> tuple[str, ...]:
    if source.completed_evidence.market_identity != "MCX":
        return ()
    publication = load_mcx_commissioning_publication()
    entry = publication.subject(source.canonical_subject_identity)
    return (
        publication.publication_identity,
        publication.integrity_identity,
        entry.qualification_evidence_identity,
        entry.qualification_integrity_identity,
        entry.family_expiry_evidence_identity,
        entry.family_expiry_evidence_integrity,
        f"MCX_COMMISSIONING_STATE:{entry.state.value}",
    )


def _diagnostics(
    results: tuple[ProbableMemberResultV2, ...],
) -> ProbablesPopulationDiagnosticsV2:
    unavailable = sum(item.state is ProbableState.UNAVAILABLE for item in results)
    long_count = sum(item.state is ProbableState.LONG_PROBABLE for item in results)
    short_count = sum(item.state is ProbableState.SHORT_PROBABLE for item in results)
    not_admitted = sum(item.state is ProbableState.NOT_ADMITTED for item in results)
    total = long_count + short_count
    conflicts = sum(
        any("CONFLICT" in reason.value for reason in item.reasons)
        for item in results
    )
    values = {
        "starting_population": len(results),
        "evaluable_count": len(results) - unavailable,
        "unavailable_count": unavailable,
        "long_probables": long_count,
        "short_probables": short_count,
        "total_probables": total,
        "not_admitted_count": not_admitted,
        "conflicting_count": conflicts,
        "phase_counts": tuple(
            (phase, sum(item.phase is phase for item in results))
            for phase in IntradayAnalysisPhase
        ),
        "population_bucket": _population_bucket(total),
        "schema_identity": POPULATION_DIAGNOSTICS_V2_IDENTITY,
        "schema_version": V2_CONTRACT_VERSION,
    }
    return ProbablesPopulationDiagnosticsV2(
        diagnostics_identity=_identity("INTRADAY-PROBABLES-V2-DIAGNOSTICS-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-PROBABLES-V2-DIAGNOSTICS-", values
        ),
        **values,
    )


def _fact(
    *,
    family: str,
    selection: CompletedEvidenceSelection,
    direction: SemanticDirection,
    role: SemanticEvidenceRoleV2,
    sources: tuple[str, ...],
    attributes: tuple[tuple[str, str], ...],
) -> SemanticQualificationFactV2:
    values = {
        "family": family,
        "canonical_subject_identity": selection.canonical_subject_identity,
        "analysis_boundary": selection.analysis_boundary,
        "phase": selection.phase,
        "availability": "AVAILABLE" if direction is not SemanticDirection.UNAVAILABLE else "UNAVAILABLE",
        "direction": direction,
        "evidence_role": role,
        "source_evidence_identities": sources,
        "attributes": tuple(sorted(attributes)),
        "schema_identity": SEMANTIC_FACT_V2_IDENTITY,
        "schema_version": V2_CONTRACT_VERSION,
    }
    return SemanticQualificationFactV2(
        fact_identity=_identity("INTRADAY-SEMANTIC-V2-FACT-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-SEMANTIC-V2-FACT-", values),
        **values,
    )


def _required_families(phase: IntradayAnalysisPhase) -> tuple[str, ...]:
    if phase is IntradayAnalysisPhase.OPENING:
        return (
            "1D_CONTEXT",
            "1H_REGIME",
            "OPENING_15M",
            "5M_PROGRESSION",
            "DIRECTIONAL_COHERENCE",
            "NIFTY_RELATIVE_CONTEXT",
        )
    return (
        "1D_CONTEXT",
        "1H_REGIME",
        "15M_STRUCTURE",
        "5M_PROGRESSION",
        "DIRECTIONAL_COHERENCE",
    )


def _movement(
    previous: GovernedHistoricalCandlePayload,
    current: GovernedHistoricalCandlePayload,
) -> SemanticDirection:
    if current.high > previous.high and current.low > previous.low and current.close > previous.close:
        return SemanticDirection.LONG
    if current.high < previous.high and current.low < previous.low and current.close < previous.close:
        return SemanticDirection.SHORT
    return SemanticDirection.NON_DIRECTIONAL


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


def _daily():  # type: ignore[no-untyped-def]
    from kronos.intraday.contracts import IntradayTimeframe
    return IntradayTimeframe.DAILY


def _hour():  # type: ignore[no-untyped-def]
    from kronos.intraday.contracts import IntradayTimeframe
    return IntradayTimeframe.ONE_HOUR


def _fifteen():  # type: ignore[no-untyped-def]
    from kronos.intraday.contracts import IntradayTimeframe
    return IntradayTimeframe.FIFTEEN_MINUTES


def _five():  # type: ignore[no-untyped-def]
    from kronos.intraday.contracts import IntradayTimeframe
    return IntradayTimeframe.FIVE_MINUTES


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


__all__ = [
    "DISCOVERY_PROBABLES_EVIDENCE_V2_IDENTITY",
    "DISCOVERY_PROBABLES_MAPPER_V2_IDENTITY",
    "POPULATION_DIAGNOSTICS_V2_IDENTITY",
    "PROBABLES_RUN_V2_IDENTITY",
    "PROBABLES_V2_METHODOLOGY_CHECKSUM",
    "PROBABLES_V2_METHODOLOGY_IDENTITY",
    "PROBABLES_V2_METHODOLOGY_VERSION",
    "PROBABLES_V2_PUBLICATION_IDENTITY",
    "PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM",
    "PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION",
    "PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY",
    "PROBABLE_V2_IDENTITY",
    "SEMANTIC_EVIDENCE_V2_IDENTITY",
    "SEMANTIC_FACT_V2_IDENTITY",
    "DiscoveryProbablesEvidenceV2",
    "ProbableMemberResultV2",
    "ProbableReasonV2",
    "ProbablesMethodologyV2",
    "ProbablesPopulationDiagnosticsV2",
    "ProbablesRunV2",
    "ProbablesUnavailableMemberV2",
    "ProbablesV2Error",
    "SemanticEvidenceRoleV2",
    "SemanticQualificationEvidenceV2",
    "SemanticQualificationFactV2",
    "build_semantic_qualification_evidence_v2",
    "create_discovery_probables_evidence_v2",
    "create_probables_v2_methodology",
    "evaluate_probables_v2_run",
    "probables_v2_methodology_binding_supported",
]
