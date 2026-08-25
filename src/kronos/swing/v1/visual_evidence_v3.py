"""Swing Visual V3: independent chart facts bound to KRONOS machine facts.

V3 deliberately separates deterministic numerical authority from independent
visual observation.  It does not reinterpret or mutate historical Visual V2.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock

from kronos.swing.v1.mtf_facts import SameRunMtfFactSnapshot
from kronos.swing.v1.native_review import NativeReviewRequirement
from kronos.swing.v1.reference_facts import (
    CPR_CALCULATION_POLICY_IDENTITY,
    CPR_CALCULATION_POLICY_VERSION,
    REFERENCE_POLICY_IDENTITY,
    REFERENCE_POLICY_VERSION,
    SwingReferenceAvailability,
    SwingReferenceChartTimeframe,
    SwingReferenceCprMachineFact,
    machine_fact_integrity_sha256,
)
from kronos.swing.v1.visual_evidence_v2 import (
    VisualEvidenceSubjectKind,
    VisualObservationStatus,
    VisualQuestionRouting,
    VisualTimeframe,
)


VISUAL_QUESTION_SET_V3_ID = "SWING-V1-VISUAL-QUESTION-SET-V3"
VISUAL_QUESTION_SET_V3_LEGACY_VERSION = "3.0"
VISUAL_QUESTION_SET_V3_VERSION = "3.1"
VISUAL_EVIDENCE_V3_LEGACY_SCHEMA = "KRONOS-SWING-V1-VISUAL-EVIDENCE-V3"
VISUAL_EVIDENCE_V3_SCHEMA = "KRONOS-SWING-V1-VISUAL-EVIDENCE-V3.1"
VISUAL_EVIDENCE_V3_LEGACY_ANSWER_SCHEMA = "KRONOS-SWING-V1-VISUAL-ANSWER-V3"
VISUAL_EVIDENCE_V3_ANSWER_SCHEMA = "KRONOS-SWING-V1-VISUAL-ANSWER-V3.1"
VISUAL_EVIDENCE_V3_AUTHORITY = "INDEPENDENT_VISUAL_OBSERVATION_ONLY"
MACHINE_FACT_AUTHORITY = "DETERMINISTIC_NUMERICAL_FACT_ONLY"
DEFAULT_VISUAL_EVIDENCE_V3_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "swing-v1"
    / "visual-v3"
)


class VisualQuestionV3(StrEnum):
    VISUAL_CHART_VALIDATION = "VISUAL_CHART_VALIDATION"
    CPR_VISUAL_RELATIONSHIP = "CPR_VISUAL_RELATIONSHIP"
    VISUAL_SUPPORT_RESISTANCE_GAP = "VISUAL_SUPPORT_RESISTANCE_GAP"
    GOVERNED_REFERENCE_VISUAL_CONTEXT = "GOVERNED_REFERENCE_VISUAL_CONTEXT"
    PRICE_ACTION_QUALITY = "PRICE_ACTION_QUALITY"
    VISUAL_OBSTACLE_EVIDENCE = "VISUAL_OBSTACLE_EVIDENCE"
    MATURITY_AND_CHASE_CONTEXT = "MATURITY_AND_CHASE_CONTEXT"
    PINE_VISIBLE_EVIDENCE = "PINE_VISIBLE_EVIDENCE"
    VISUAL_COMPONENT_CLUSTERING = "VISUAL_COMPONENT_CLUSTERING"
    VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS = "VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS"


FROZEN_VISUAL_QUESTION_SET_V3 = tuple(VisualQuestionV3)

VISUAL_QUESTION_SEMANTICS_V3: dict[VisualQuestionV3, str] = {
    VisualQuestionV3.VISUAL_CHART_VALIDATION:
        "Validate visible chart identity, timeframe, readability, and revision.",
    VisualQuestionV3.CPR_VISUAL_RELATIONSHIP:
        "Observe CPR presence, price relationship, and visible interaction without transcribing CP/BC/TC.",
    VisualQuestionV3.VISUAL_SUPPORT_RESISTANCE_GAP:
        "Extract material visible support/resistance absent from supplied deterministic evidence.",
    VisualQuestionV3.GOVERNED_REFERENCE_VISUAL_CONTEXT:
        "Observe the governed previous-week/month reference structure without calling it PDH/PDL or transcribing levels.",
    VisualQuestionV3.PRICE_ACTION_QUALITY:
        "Classify bounded visible price-action quality relative to the supplied Native direction and explain the visible basis without analytical consequence.",
    VisualQuestionV3.VISUAL_OBSTACLE_EVIDENCE:
        "Extract factual visible obstacle evidence.",
    VisualQuestionV3.MATURITY_AND_CHASE_CONTEXT:
        "Describe visible maturity, extension, or chase context without consequence.",
    VisualQuestionV3.PINE_VISIBLE_EVIDENCE:
        "Transcribe only what the visible Pine panel displays.",
    VisualQuestionV3.VISUAL_COMPONENT_CLUSTERING:
        "Observe whether identifiable plotted structures visibly cluster near active price; do not create a numerical zone.",
    VisualQuestionV3.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS:
        "Strict escape hatch for clear material facts not covered by Q1-Q9; NONE is valid.",
}


VISUAL_TIMEFRAME_ROUTING_V3: dict[
    VisualQuestionV3, dict[VisualTimeframe, VisualQuestionRouting]
] = {
    question: dict.fromkeys(VisualTimeframe, VisualQuestionRouting.YES)
    for question in VisualQuestionV3
}
VISUAL_TIMEFRAME_ROUTING_V3[VisualQuestionV3.PINE_VISIBLE_EVIDENCE] = (
    dict.fromkeys(VisualTimeframe, VisualQuestionRouting.IF_SHOWN)
)
VISUAL_TIMEFRAME_ROUTING_V3[
    VisualQuestionV3.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS
] = dict.fromkeys(VisualTimeframe, VisualQuestionRouting.ESCAPE_HATCH)


class VisualPriceRelationship(StrEnum):
    ABOVE = "ABOVE"
    INSIDE = "INSIDE"
    BELOW = "BELOW"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"


class VisualInteraction(StrEnum):
    HOLD = "HOLD"
    RECLAIM = "RECLAIM"
    REJECTION = "REJECTION"
    BREAK = "BREAK"
    NONE = "NONE"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"


class VisualStructurePresence(StrEnum):
    PRESENT = "PRESENT"
    NOT_PRESENT = "NOT_PRESENT"
    NOT_IDENTIFIABLE = "NOT_IDENTIFIABLE"


class VisualReferenceRelationship(StrEnum):
    ABOVE_REFERENCE_RANGE = "ABOVE_REFERENCE_RANGE"
    INSIDE_REFERENCE_RANGE = "INSIDE_REFERENCE_RANGE"
    BELOW_REFERENCE_RANGE = "BELOW_REFERENCE_RANGE"
    INTERACTING_WITH_REFERENCE_HIGH = "INTERACTING_WITH_REFERENCE_HIGH"
    INTERACTING_WITH_REFERENCE_LOW = "INTERACTING_WITH_REFERENCE_LOW"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"


class VisualClusteringState(StrEnum):
    CLUSTERED = "CLUSTERED"
    NOT_CLUSTERED = "NOT_CLUSTERED"
    PARTIAL_COMPONENT_IDENTITY = "PARTIAL_COMPONENT_IDENTITY"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"


class VisualComponentType(StrEnum):
    CPR = "CPR"
    GOVERNED_REFERENCE_HIGH = "GOVERNED_REFERENCE_HIGH"
    GOVERNED_REFERENCE_LOW = "GOVERNED_REFERENCE_LOW"
    SMA20 = "SMA20"
    SMA50 = "SMA50"
    SMA200 = "SMA200"
    STRUCTURAL_PIVOT = "STRUCTURAL_PIVOT"
    OPERATIVE_ANCHOR = "OPERATIVE_ANCHOR"
    RANGE_BOUNDARY = "RANGE_BOUNDARY"
    BREAK_BOUNDARY = "BREAK_BOUNDARY"
    UNIDENTIFIED_PLOTTED_STRUCTURE = "UNIDENTIFIED_PLOTTED_STRUCTURE"


class VisualSetupQuality(StrEnum):
    CLEAN_DIRECTIONAL = "CLEAN_DIRECTIONAL"
    HEALTHY_CONSOLIDATION = "HEALTHY_CONSOLIDATION"
    HEALTHY_COMPRESSION = "HEALTHY_COMPRESSION"
    ORDERLY_PULLBACK = "ORDERLY_PULLBACK"
    MESSY_CHOPPY = "MESSY_CHOPPY"
    CONFLICTING = "CONFLICTING"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"


VISUAL_SETUP_QUALITY_DEFINITIONS: dict[VisualSetupQuality, str] = {
    VisualSetupQuality.CLEAN_DIRECTIONAL:
        "Visible price action is orderly and progressing consistently in the supplied Native direction.",
    VisualSetupQuality.HEALTHY_CONSOLIDATION:
        "Price is pausing or moving sideways in an orderly manner without visibly damaging the directional structure; this is not automatically negative.",
    VisualSetupQuality.HEALTHY_COMPRESSION:
        "Price is visibly compressing or tightening in an orderly structure without obvious directional failure; this is not automatically negative.",
    VisualSetupQuality.ORDERLY_PULLBACK:
        "Price is retracing against the supplied Native direction in an orderly manner while the broader visible structure remains intact; this is not automatically negative.",
    VisualSetupQuality.MESSY_CHOPPY:
        "Price action is visibly disorganized or choppy with repeated conflicting movement and no clean directional structure.",
    VisualSetupQuality.CONFLICTING:
        "Visible price action materially conflicts with the supplied Native direction.",
    VisualSetupQuality.NOT_OBSERVABLE:
        "The supplied chart does not allow a reliable price-action-quality classification.",
}


@dataclass(frozen=True, slots=True)
class VisualV3BaseObservation:
    question_id: VisualQuestionV3
    timeframe: VisualTimeframe
    observation_status: VisualObservationStatus
    visible_basis: str
    confidence_in_extraction: str
    ambiguity_reason: str
    source_chart_identity: str
    source_chart_revision: str

    def __post_init__(self) -> None:
        if (
            type(self.question_id) is not VisualQuestionV3
            or type(self.timeframe) is not VisualTimeframe
            or type(self.observation_status) is not VisualObservationStatus
            or not _text(self.visible_basis, 512)
            or not _text(self.confidence_in_extraction, 64)
            or type(self.ambiguity_reason) is not str
            or len(self.ambiguity_reason) > 512
            or not _text(self.source_chart_identity, 256)
            or re.fullmatch(r"[0-9a-f]{64}", self.source_chart_revision) is None
            or (
                self.observation_status
                in {
                    VisualObservationStatus.PARTIAL,
                    VisualObservationStatus.UNAVAILABLE,
                    VisualObservationStatus.INVALID,
                }
                and not self.ambiguity_reason.strip()
            )
        ):
            raise ValueError("VISUAL_V3_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class VisualV3QualitativeObservation(VisualV3BaseObservation):
    finding: str
    why_not_covered_elsewhere: str | None = None

    def __post_init__(self) -> None:
        super(VisualV3QualitativeObservation, self).__post_init__()
        q10 = (
            self.question_id
            is VisualQuestionV3.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS
        )
        if (
            self.question_id
            in {
                VisualQuestionV3.CPR_VISUAL_RELATIONSHIP,
                VisualQuestionV3.GOVERNED_REFERENCE_VISUAL_CONTEXT,
                VisualQuestionV3.VISUAL_COMPONENT_CLUSTERING,
            }
            or not _text(self.finding, 512)
            or (
                q10
                and self.finding != "NONE"
                and not _text(self.why_not_covered_elsewhere, 512)
            )
            or (q10 and self.finding == "NONE" and self.why_not_covered_elsewhere is not None)
            or (not q10 and self.why_not_covered_elsewhere is not None)
        ):
            raise ValueError("VISUAL_V3_QUALITATIVE_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class VisualV3SetupQualityObservation(VisualV3BaseObservation):
    setup_quality: VisualSetupQuality
    finding: str

    def __post_init__(self) -> None:
        super(VisualV3SetupQualityObservation, self).__post_init__()
        if (
            self.question_id is not VisualQuestionV3.PRICE_ACTION_QUALITY
            or type(self.setup_quality) is not VisualSetupQuality
            or not _text(self.finding, 512)
        ):
            raise ValueError("VISUAL_V3_SETUP_QUALITY_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class VisualV3LevelObservation(VisualV3BaseObservation):
    """A visible point or zone retained only for Q3/Q6 factual extraction."""

    finding: str
    point_price: float | None = None
    zone_low: float | None = None
    zone_high: float | None = None

    def __post_init__(self) -> None:
        super(VisualV3LevelObservation, self).__post_init__()
        point = self.point_price is not None
        zone = self.zone_low is not None or self.zone_high is not None
        if (
            self.question_id
            not in {
                VisualQuestionV3.VISUAL_SUPPORT_RESISTANCE_GAP,
                VisualQuestionV3.VISUAL_OBSTACLE_EVIDENCE,
            }
            or not _text(self.finding, 512)
            or point == zone
            or (
                point
                and (
                    type(self.point_price) is not float
                    or not _finite_nonnegative(self.point_price)
                )
            )
            or (
                zone
                and (
                    type(self.zone_low) is not float
                    or type(self.zone_high) is not float
                    or not _finite_nonnegative(self.zone_low)
                    or not _finite_nonnegative(self.zone_high)
                    or self.zone_low > self.zone_high
                )
            )
        ):
            raise ValueError("VISUAL_V3_LEVEL_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class VisualV3CprObservation(VisualV3BaseObservation):
    presence: VisualStructurePresence
    price_relationship: VisualPriceRelationship
    interaction: VisualInteraction

    def __post_init__(self) -> None:
        super(VisualV3CprObservation, self).__post_init__()
        if (
            self.question_id is not VisualQuestionV3.CPR_VISUAL_RELATIONSHIP
            or type(self.presence) is not VisualStructurePresence
            or type(self.price_relationship) is not VisualPriceRelationship
            or type(self.interaction) is not VisualInteraction
            or (
                self.presence is not VisualStructurePresence.PRESENT
                and (
                    self.price_relationship
                    is not VisualPriceRelationship.NOT_OBSERVABLE
                    or self.interaction is not VisualInteraction.NOT_OBSERVABLE
                )
            )
        ):
            raise ValueError("VISUAL_V3_CPR_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class VisualV3ReferenceObservation(VisualV3BaseObservation):
    presence: VisualStructurePresence
    relationship: VisualReferenceRelationship
    interaction: VisualInteraction

    def __post_init__(self) -> None:
        super(VisualV3ReferenceObservation, self).__post_init__()
        if (
            self.question_id
            is not VisualQuestionV3.GOVERNED_REFERENCE_VISUAL_CONTEXT
            or type(self.presence) is not VisualStructurePresence
            or type(self.relationship) is not VisualReferenceRelationship
            or type(self.interaction) is not VisualInteraction
            or (
                self.presence is not VisualStructurePresence.PRESENT
                and (
                    self.relationship
                    is not VisualReferenceRelationship.NOT_OBSERVABLE
                    or self.interaction is not VisualInteraction.NOT_OBSERVABLE
                )
            )
        ):
            raise ValueError("VISUAL_V3_REFERENCE_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class VisualV3ClusteringObservation(VisualV3BaseObservation):
    clustering: VisualClusteringState
    components: tuple[VisualComponentType, ...]

    def __post_init__(self) -> None:
        super(VisualV3ClusteringObservation, self).__post_init__()
        if (
            self.question_id is not VisualQuestionV3.VISUAL_COMPONENT_CLUSTERING
            or type(self.clustering) is not VisualClusteringState
            or type(self.components) is not tuple
            or len(set(self.components)) != len(self.components)
            or any(type(item) is not VisualComponentType for item in self.components)
            or (
                self.clustering is VisualClusteringState.CLUSTERED
                and len(self.components) < 2
            )
            or (
                self.clustering
                in {
                    VisualClusteringState.NOT_CLUSTERED,
                    VisualClusteringState.NOT_OBSERVABLE,
                }
                and self.components
            )
        ):
            raise ValueError("VISUAL_V3_CLUSTERING_OBSERVATION_INVALID")


VisualV3Observation = (
    VisualV3QualitativeObservation
    | VisualV3SetupQualityObservation
    | VisualV3LevelObservation
    | VisualV3CprObservation
    | VisualV3ReferenceObservation
    | VisualV3ClusteringObservation
)


@dataclass(frozen=True, slots=True)
class VisualEvidenceV3Request:
    requirement: NativeReviewRequirement
    subject_kind: VisualEvidenceSubjectKind
    timeframe: VisualTimeframe
    observation_boundary: datetime
    analysis_boundary: datetime
    chart_identity: str
    chart_revision_sha256: str
    content_type: str
    original_image: bytes
    request_timestamp: datetime
    machine_fact: SwingReferenceCprMachineFact
    routing: tuple[tuple[VisualQuestionV3, VisualQuestionRouting], ...]
    question_set_identity: str = VISUAL_QUESTION_SET_V3_ID
    question_set_version: str = VISUAL_QUESTION_SET_V3_VERSION

    def __post_init__(self) -> None:
        expected_timeframe = SwingReferenceChartTimeframe(self.timeframe.value)
        if (
            type(self.requirement) is not NativeReviewRequirement
            or self.subject_kind is not VisualEvidenceSubjectKind.NATIVE
            or type(self.timeframe) is not VisualTimeframe
            or not _aware(self.observation_boundary)
            or not _aware(self.analysis_boundary)
            or not _text(self.chart_identity, 256)
            or re.fullmatch(r"[0-9a-f]{64}", self.chart_revision_sha256) is None
            or self.content_type not in {"image/png", "image/jpeg", "image/webp"}
            or type(self.original_image) is not bytes
            or not self.original_image
            or sha256(self.original_image).hexdigest() != self.chart_revision_sha256
            or not _aware(self.request_timestamp)
            or type(self.machine_fact) is not SwingReferenceCprMachineFact
            or self.machine_fact.run_identity != self.requirement.native_run_identity
            or self.machine_fact.canonical_instrument
            != self.requirement.canonical_instrument
            or self.machine_fact.chart_timeframe is not expected_timeframe
            or self.machine_fact.analysis_boundary != self.analysis_boundary
            or self.machine_fact.integrity_sha256
            != machine_fact_integrity_sha256(self.machine_fact)
            or self.machine_fact.reference_policy_identity
            != REFERENCE_POLICY_IDENTITY
            or self.machine_fact.reference_policy_version
            != REFERENCE_POLICY_VERSION
            or self.machine_fact.calculation_policy_identity
            != CPR_CALCULATION_POLICY_IDENTITY
            or self.machine_fact.calculation_policy_version
            != CPR_CALCULATION_POLICY_VERSION
            or self.routing != visual_question_routing_v3(self.timeframe)
            or self.question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or self.question_set_version not in _SUPPORTED_VISUAL_V3_VERSIONS
        ):
            raise ValueError("VISUAL_V3_REQUEST_BINDING_INVALID")

    def analyst_context(self) -> dict[str, object]:
        """Return unbiased visual-only context with no machine numerical values."""

        return {
            "question_set_identity": self.question_set_identity,
            "question_set_version": self.question_set_version,
            "canonical_instrument": self.requirement.canonical_instrument,
            "native_direction": self.requirement.thesis.direction.value,
            "timeframe": self.timeframe.value,
            "chart_identity": self.chart_identity,
            "chart_revision_sha256": self.chart_revision_sha256,
            "authority": VISUAL_EVIDENCE_V3_AUTHORITY,
            "instruction": (
                "Answer only from the supplied chart. KRONOS maintains separate "
                "deterministic facts; do not transcribe or infer their values."
            ),
            "questions": [
                {
                    "question_id": question.value,
                    "semantics": VISUAL_QUESTION_SEMANTICS_V3[question],
                    "routing": routing.value,
                }
                for question, routing in self.routing
            ],
        }


@dataclass(frozen=True, slots=True)
class VisualEvidenceV3Response:
    provider_identity: str
    model_identity: str
    request_timestamp: datetime
    native_run_identity: str
    native_assessment_sha256: str
    native_canonical_instrument: str
    timeframe: VisualTimeframe
    observation_boundary: datetime
    analysis_boundary: datetime
    chart_identity: str
    chart_revision_sha256: str
    machine_fact_integrity_sha256: str
    observations: tuple[VisualV3Observation, ...]
    source_provenance: tuple[str, ...]
    question_set_identity: str = VISUAL_QUESTION_SET_V3_ID
    question_set_version: str = VISUAL_QUESTION_SET_V3_VERSION
    schema: str = VISUAL_EVIDENCE_V3_SCHEMA
    authority: str = VISUAL_EVIDENCE_V3_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not _text(self.provider_identity, 128)
            or not _text(self.model_identity, 128)
            or not _aware(self.request_timestamp)
            or not self.native_run_identity
            or re.fullmatch(r"[0-9a-f]{64}", self.native_assessment_sha256) is None
            or not self.native_canonical_instrument
            or type(self.timeframe) is not VisualTimeframe
            or not _aware(self.observation_boundary)
            or not _aware(self.analysis_boundary)
            or not _text(self.chart_identity, 256)
            or re.fullmatch(r"[0-9a-f]{64}", self.chart_revision_sha256) is None
            or re.fullmatch(r"[0-9a-f]{64}", self.machine_fact_integrity_sha256)
            is None
            or type(self.observations) is not tuple
            or tuple(item.question_id for item in self.observations)
            != FROZEN_VISUAL_QUESTION_SET_V3
            or any(item.timeframe is not self.timeframe for item in self.observations)
            or any(item.source_chart_identity != self.chart_identity for item in self.observations)
            or any(item.source_chart_revision != self.chart_revision_sha256 for item in self.observations)
            or not self.source_provenance
            or self.question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or not _response_contract_matches(
                self.question_set_version, self.schema, self.observations
            )
            or self.authority != VISUAL_EVIDENCE_V3_AUTHORITY
        ):
            raise ValueError("VISUAL_V3_RESPONSE_INVALID")

    @property
    def evidence_sha256(self) -> str:
        return sha256(_canonical(_primitive(self))).hexdigest()

    def validate_binding(self, request: VisualEvidenceV3Request) -> None:
        if (
            type(request) is not VisualEvidenceV3Request
            or self.request_timestamp != request.request_timestamp
            or self.native_run_identity != request.requirement.native_run_identity
            or self.native_assessment_sha256
            != request.requirement.thesis.native_assessment_sha256
            or self.native_canonical_instrument
            != request.requirement.canonical_instrument
            or self.timeframe is not request.timeframe
            or self.observation_boundary != request.observation_boundary
            or self.analysis_boundary != request.analysis_boundary
            or self.chart_identity != request.chart_identity
            or self.chart_revision_sha256 != request.chart_revision_sha256
            or self.machine_fact_integrity_sha256
            != request.machine_fact.integrity_sha256
            or self.question_set_identity != request.question_set_identity
            or self.question_set_version != request.question_set_version
        ):
            raise ValueError("VISUAL_V3_BINDING_INVALID")


def visual_question_routing_v3(
    timeframe: VisualTimeframe,
) -> tuple[tuple[VisualQuestionV3, VisualQuestionRouting], ...]:
    if type(timeframe) is not VisualTimeframe:
        raise ValueError("VISUAL_V3_TIMEFRAME_INVALID")
    return tuple(
        (question, VISUAL_TIMEFRAME_ROUTING_V3[question][timeframe])
        for question in VisualQuestionV3
    )


def build_visual_evidence_v3_request(
    requirement: NativeReviewRequirement,
    mtf_snapshot: SameRunMtfFactSnapshot,
    *,
    timeframe: VisualTimeframe,
    observation_boundary: datetime,
    chart_identity: str,
    content_type: str,
    original_image: bytes,
    request_timestamp: datetime,
    question_set_version: str = VISUAL_QUESTION_SET_V3_VERSION,
) -> VisualEvidenceV3Request:
    if (
        type(requirement) is not NativeReviewRequirement
        or type(mtf_snapshot) is not SameRunMtfFactSnapshot
        or mtf_snapshot.run_identity != requirement.native_run_identity
    ):
        raise ValueError("VISUAL_V3_MACHINE_SNAPSHOT_BINDING_INVALID")
    instrument = mtf_snapshot.instrument(requirement.canonical_instrument)
    machine_fact = instrument.reference_fact(
        SwingReferenceChartTimeframe(timeframe.value)
    )
    return VisualEvidenceV3Request(
        requirement=requirement,
        subject_kind=VisualEvidenceSubjectKind.NATIVE,
        timeframe=timeframe,
        observation_boundary=observation_boundary,
        analysis_boundary=machine_fact.analysis_boundary,
        chart_identity=chart_identity,
        chart_revision_sha256=sha256(original_image).hexdigest(),
        content_type=content_type,
        original_image=original_image,
        request_timestamp=request_timestamp,
        machine_fact=machine_fact,
        routing=visual_question_routing_v3(timeframe),
        question_set_version=question_set_version,
    )


def visual_evidence_v3_answer_contract() -> dict[str, object]:
    """Return the governed versioned Answer contract without machine numbers."""

    return {
        "schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
        "question_set_identity": VISUAL_QUESTION_SET_V3_ID,
        "question_set_version": VISUAL_QUESTION_SET_V3_VERSION,
        "authority": VISUAL_EVIDENCE_V3_AUTHORITY,
        "questions": [item.value for item in FROZEN_VISUAL_QUESTION_SET_V3],
        "response_fields": [
            "model_identity",
            "timeframe",
            "chart_identity",
            "chart_revision_sha256",
            "observations",
            "question_set_identity",
            "question_set_version",
        ],
        "common_observation_fields": [
            "question_id",
            "timeframe",
            "observation_status",
            "visible_basis",
            "confidence_in_extraction",
            "ambiguity_reason",
            "source_chart_identity",
            "source_chart_revision",
        ],
        "observation_status": [item.value for item in VisualObservationStatus],
        "qualitative_questions": [
            VisualQuestionV3.VISUAL_CHART_VALIDATION.value,
            VisualQuestionV3.VISUAL_SUPPORT_RESISTANCE_GAP.value,
            VisualQuestionV3.VISUAL_OBSTACLE_EVIDENCE.value,
            VisualQuestionV3.MATURITY_AND_CHASE_CONTEXT.value,
            VisualQuestionV3.PINE_VISIBLE_EVIDENCE.value,
            VisualQuestionV3.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS.value,
        ],
        "qualitative_result_field": "finding",
        "qualitative_optional_field": "why_not_covered_elsewhere",
        "setup_quality_observation": {
            "question": VisualQuestionV3.PRICE_ACTION_QUALITY.value,
            "classification_field": "setup_quality",
            "finding_field": "finding",
            "values": [item.value for item in VisualSetupQuality],
            "definitions": {
                item.value: VISUAL_SETUP_QUALITY_DEFINITIONS[item]
                for item in VisualSetupQuality
            },
            "direction_binding": (
                "CLASSIFY_RELATIVE_TO_SUPPLIED_NATIVE_DIRECTION;_DO_NOT_CHOOSE_DIRECTION"
            ),
            "volume_rule": "VOLUME_IS_SUPPORTING_ONLY_NOT_CLASSIFICATION_AUTHORITY",
            "illustrative_example": {
                "setup_quality": VisualSetupQuality.HEALTHY_CONSOLIDATION.value,
                "finding": (
                    "Illustrative only: price pauses sideways in an orderly range "
                    "while the supplied Native direction remains visibly intact."
                ),
            },
        },
        "level_observation": {
            "questions": [
                VisualQuestionV3.VISUAL_SUPPORT_RESISTANCE_GAP.value,
                VisualQuestionV3.VISUAL_OBSTACLE_EVIDENCE.value,
            ],
            "point_field": "point_price",
            "zone_fields": ["zone_low", "zone_high"],
        },
        "observable_fields": {
            VisualQuestionV3.CPR_VISUAL_RELATIONSHIP.value: {
                "presence": [item.value for item in VisualStructurePresence],
                "price_relationship": [
                    item.value for item in VisualPriceRelationship
                ],
                "interaction": [item.value for item in VisualInteraction],
            },
            VisualQuestionV3.GOVERNED_REFERENCE_VISUAL_CONTEXT.value: {
                "presence": [item.value for item in VisualStructurePresence],
                "relationship": [
                    item.value for item in VisualReferenceRelationship
                ],
                "interaction": [item.value for item in VisualInteraction],
            },
            VisualQuestionV3.VISUAL_COMPONENT_CLUSTERING.value: {
                "clustering": [item.value for item in VisualClusteringState],
                "components": [item.value for item in VisualComponentType],
            },
        },
        "rules": {
            "question_order": "EXACTLY_ONCE_IN_PUBLISHED_ORDER",
            "finding_field": "USE_FINDING_NOT_LEGACY_OBSERVATION",
            "q2_non_present": (
                "NOT_PRESENT_OR_NOT_IDENTIFIABLE_REQUIRES_NOT_OBSERVABLE_"
                "PRICE_RELATIONSHIP_AND_INTERACTION"
            ),
            "q4_non_present": (
                "NOT_PRESENT_OR_NOT_IDENTIFIABLE_REQUIRES_NOT_OBSERVABLE_"
                "RELATIONSHIP_AND_INTERACTION"
            ),
            "q3_q6_level": (
                "OPTIONAL_SINGLE_NONNEGATIVE_FLOAT_POINT_PRICE_OR_COMPLETE_"
                "NONNEGATIVE_FLOAT_ZONE; QUALITATIVE_FINDING_WITHOUT_LEVEL_IS_VALID"
            ),
            "q9_clustered": "CLUSTERED_REQUIRES_AT_LEAST_TWO_UNIQUE_COMPONENTS",
            "q9_not_clustered_or_unobservable": "COMPONENTS_MUST_BE_EMPTY",
            "q10_none": "FINDING_NONE_REQUIRES_WHY_NOT_COVERED_ELSEWHERE_NULL",
            "q10_non_none": (
                "NON_NONE_FINDING_REQUIRES_BOUNDED_WHY_NOT_COVERED_ELSEWHERE"
            ),
            "q1_to_q9_why": "WHY_NOT_COVERED_ELSEWHERE_MUST_BE_NULL",
            "non_observed_status": "PARTIAL_UNAVAILABLE_OR_INVALID_REQUIRES_AMBIGUITY_REASON",
        },
        "kronos_owned_fields": [
            "provider_identity",
            "request_timestamp",
            "native_run_identity",
            "native_assessment_sha256",
            "native_canonical_instrument",
            "observation_boundary",
            "analysis_boundary",
            "machine_fact_integrity_sha256",
            "source_provenance",
            "schema",
            "authority",
        ],
        "forbidden_numeric_transcription": [
            "CP",
            "BC",
            "TC",
            "reference_high",
            "reference_low",
            "confluence_zone_low",
            "confluence_zone_high",
        ],
    }


class LocalVisualEvidenceV3Store:
    """Immutable V3 evidence store, isolated from historical Visual V2."""

    def __init__(self, root: Path = DEFAULT_VISUAL_EVIDENCE_V3_ROOT) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("VISUAL_V3_STORE_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(
        self, request: VisualEvidenceV3Request, response: VisualEvidenceV3Response
    ) -> Path:
        response.validate_binding(request)
        path = (
            self._root
            / response.native_run_identity
            / _safe(response.native_canonical_instrument)
            / response.timeframe.value
            / f"{response.chart_revision_sha256}--{response.evidence_sha256}.json"
        )
        payload = {
            "schema": response.schema,
            "evidence_sha256": response.evidence_sha256,
            "response": _primitive(response),
        }
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("VISUAL_V3_EVIDENCE_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load_for_request(
        self, request: VisualEvidenceV3Request
    ) -> tuple[VisualEvidenceV3Response, ...]:
        """Restore only evidence bound to this exact V3 request identity."""

        root = (
            self._root
            / request.requirement.native_run_identity
            / _safe(request.requirement.canonical_instrument)
            / request.timeframe.value
        )
        if not root.exists():
            return ()
        values = []
        for path in sorted(root.glob(f"{request.chart_revision_sha256}--*.json")):
            payload = _read(path)
            if payload.get("schema") not in _SUPPORTED_VISUAL_V3_EVIDENCE_SCHEMAS:
                raise ValueError("VISUAL_V3_RESTART_SCHEMA_INVALID")
            response = visual_evidence_v3_response_from_dict(payload.get("response"))
            if payload.get("evidence_sha256") != response.evidence_sha256:
                raise ValueError("VISUAL_V3_RESTART_INTEGRITY_INVALID")
            # One immutable chart revision may legitimately be reviewed more than
            # once.  The governed request timestamp identifies that exact Review
            # Pack cycle; historical cycles remain retained but are not candidates
            # for the current restoration.
            if response.request_timestamp != request.request_timestamp:
                continue
            response.validate_binding(request)
            values.append(response)
        return tuple(values)


def visual_evidence_v3_response_from_dict(
    value: object,
) -> VisualEvidenceV3Response:
    """Restore a V3 response without accepting V2 schema or question identity."""

    if type(value) is not dict:
        raise ValueError("VISUAL_V3_RESPONSE_INVALID")
    try:
        version = value["question_set_version"]
        observations = tuple(
            _observation_from_dict(item, version) for item in value["observations"]
        )
        return VisualEvidenceV3Response(
            provider_identity=value["provider_identity"],
            model_identity=value["model_identity"],
            request_timestamp=datetime.fromisoformat(value["request_timestamp"]),
            native_run_identity=value["native_run_identity"],
            native_assessment_sha256=value["native_assessment_sha256"],
            native_canonical_instrument=value["native_canonical_instrument"],
            timeframe=VisualTimeframe(value["timeframe"]),
            observation_boundary=datetime.fromisoformat(value["observation_boundary"]),
            analysis_boundary=datetime.fromisoformat(value["analysis_boundary"]),
            chart_identity=value["chart_identity"],
            chart_revision_sha256=value["chart_revision_sha256"],
            machine_fact_integrity_sha256=value["machine_fact_integrity_sha256"],
            observations=observations,
            source_provenance=tuple(value["source_provenance"]),
            question_set_identity=value["question_set_identity"],
            question_set_version=value["question_set_version"],
            schema=value["schema"],
            authority=value["authority"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("VISUAL_V3_"):
            raise
        raise ValueError("VISUAL_V3_RESPONSE_INVALID") from error


def _observation_from_dict(
    value: object, question_set_version: object
) -> VisualV3Observation:
    if type(value) is not dict:
        raise ValueError("VISUAL_V3_OBSERVATION_INVALID")
    try:
        common = {
            "question_id": VisualQuestionV3(value["question_id"]),
            "timeframe": VisualTimeframe(value["timeframe"]),
            "observation_status": VisualObservationStatus(
                value["observation_status"]
            ),
            "visible_basis": value["visible_basis"],
            "confidence_in_extraction": value["confidence_in_extraction"],
            "ambiguity_reason": value["ambiguity_reason"],
            "source_chart_identity": value["source_chart_identity"],
            "source_chart_revision": value["source_chart_revision"],
        }
        question = common["question_id"]
        if (
            question is VisualQuestionV3.PRICE_ACTION_QUALITY
            and question_set_version == VISUAL_QUESTION_SET_V3_VERSION
        ):
            return VisualV3SetupQualityObservation(
                **common,
                setup_quality=VisualSetupQuality(value["setup_quality"]),
                finding=value["finding"],
            )
        if question is VisualQuestionV3.CPR_VISUAL_RELATIONSHIP:
            return VisualV3CprObservation(
                **common,
                presence=VisualStructurePresence(value["presence"]),
                price_relationship=VisualPriceRelationship(
                    value["price_relationship"]
                ),
                interaction=VisualInteraction(value["interaction"]),
            )
        if question is VisualQuestionV3.GOVERNED_REFERENCE_VISUAL_CONTEXT:
            return VisualV3ReferenceObservation(
                **common,
                presence=VisualStructurePresence(value["presence"]),
                relationship=VisualReferenceRelationship(value["relationship"]),
                interaction=VisualInteraction(value["interaction"]),
            )
        if question is VisualQuestionV3.VISUAL_COMPONENT_CLUSTERING:
            return VisualV3ClusteringObservation(
                **common,
                clustering=VisualClusteringState(value["clustering"]),
                components=tuple(
                    VisualComponentType(item) for item in value["components"]
                ),
            )
        if question in {
            VisualQuestionV3.VISUAL_SUPPORT_RESISTANCE_GAP,
            VisualQuestionV3.VISUAL_OBSTACLE_EVIDENCE,
        } and any(
            value.get(item) is not None
            for item in ("point_price", "zone_low", "zone_high")
        ):
            return VisualV3LevelObservation(
                **common,
                finding=value["finding"],
                point_price=value.get("point_price"),
                zone_low=value.get("zone_low"),
                zone_high=value.get("zone_high"),
            )
        return VisualV3QualitativeObservation(
            **common,
            finding=value["finding"],
            why_not_covered_elsewhere=value.get("why_not_covered_elsewhere"),
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("VISUAL_V3_"):
            raise
        raise ValueError("VISUAL_V3_OBSERVATION_INVALID") from error


_SUPPORTED_VISUAL_V3_VERSIONS = {
    VISUAL_QUESTION_SET_V3_LEGACY_VERSION,
    VISUAL_QUESTION_SET_V3_VERSION,
}
_SUPPORTED_VISUAL_V3_EVIDENCE_SCHEMAS = {
    VISUAL_EVIDENCE_V3_LEGACY_SCHEMA,
    VISUAL_EVIDENCE_V3_SCHEMA,
}


def _response_contract_matches(
    version: str, schema: str, observations: tuple[VisualV3Observation, ...]
) -> bool:
    q5 = next(
        (item for item in observations if item.question_id is VisualQuestionV3.PRICE_ACTION_QUALITY),
        None,
    )
    if version == VISUAL_QUESTION_SET_V3_LEGACY_VERSION:
        return (
            schema == VISUAL_EVIDENCE_V3_LEGACY_SCHEMA
            and type(q5) is VisualV3QualitativeObservation
        )
    if version == VISUAL_QUESTION_SET_V3_VERSION:
        return (
            schema == VISUAL_EVIDENCE_V3_SCHEMA
            and type(q5) is VisualV3SetupQualityObservation
        )
    return False


def _safe(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9&._-]", "_", value)
    if not result:
        raise ValueError("VISUAL_V3_PATH_IDENTITY_INVALID")
    return result


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("VISUAL_V3_EVIDENCE_INVALID") from error
    if type(value) is not dict:
        raise ValueError("VISUAL_V3_EVIDENCE_INVALID")
    return value


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _primitive(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _primitive(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        _primitive(value), sort_keys=True, separators=(",", ":")
    ).encode()


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object, maximum: int) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def _finite_nonnegative(value: float) -> bool:
    return value == value and value not in {float("inf"), float("-inf")} and value >= 0.0


__all__ = [
    "DEFAULT_VISUAL_EVIDENCE_V3_ROOT",
    "FROZEN_VISUAL_QUESTION_SET_V3",
    "LocalVisualEvidenceV3Store",
    "MACHINE_FACT_AUTHORITY",
    "VISUAL_EVIDENCE_V3_ANSWER_SCHEMA",
    "VISUAL_EVIDENCE_V3_AUTHORITY",
    "VISUAL_EVIDENCE_V3_SCHEMA",
    "VISUAL_EVIDENCE_V3_LEGACY_ANSWER_SCHEMA",
    "VISUAL_EVIDENCE_V3_LEGACY_SCHEMA",
    "VISUAL_QUESTION_SEMANTICS_V3",
    "VISUAL_QUESTION_SET_V3_ID",
    "VISUAL_QUESTION_SET_V3_LEGACY_VERSION",
    "VISUAL_QUESTION_SET_V3_VERSION",
    "VisualClusteringState",
    "VisualComponentType",
    "VisualEvidenceV3Request",
    "VisualEvidenceV3Response",
    "VisualInteraction",
    "VisualPriceRelationship",
    "VisualQuestionV3",
    "VisualReferenceRelationship",
    "VisualStructurePresence",
    "VisualSetupQuality",
    "VisualV3BaseObservation",
    "VisualV3ClusteringObservation",
    "VisualV3CprObservation",
    "VisualV3LevelObservation",
    "VisualV3Observation",
    "VisualV3QualitativeObservation",
    "VisualV3ReferenceObservation",
    "VisualV3SetupQualityObservation",
    "VISUAL_SETUP_QUALITY_DEFINITIONS",
    "build_visual_evidence_v3_request",
    "visual_evidence_v3_answer_contract",
    "visual_evidence_v3_response_from_dict",
    "visual_question_routing_v3",
]
