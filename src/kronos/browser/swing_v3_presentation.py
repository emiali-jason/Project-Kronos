"""Sponsor-safe projection of governed Swing Visual V3 evidence.

This module formats already-authoritative facts.  It never calculates a
reference level, readiness outcome, progression threshold, or trade action.
Historical Visual V2 cycles remain on their existing presentation path.
"""

from __future__ import annotations

from dataclasses import dataclass

from kronos.application.swing_visual_v3 import CompletedVisualV3Review
from kronos.swing.v1.native_readiness import (
    EvidenceCompleteness,
    NativeReadinessState,
)
from kronos.swing.v1.reference_facts import (
    SwingReferenceAvailability,
    SwingReferenceCprMachineFact,
    SwingReferenceUnavailableReason,
)
from kronos.swing.v1.visual_evidence_v2 import VisualObservationStatus
from kronos.swing.v1.visual_evidence_v3 import (
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_LEGACY_VERSION,
    VISUAL_QUESTION_SET_V3_VERSION,
    VisualClusteringState,
    VisualEvidenceV3Response,
    VisualQuestionV3,
    VisualStructurePresence,
    VisualV3ClusteringObservation,
    VisualV3CprObservation,
    VisualV3ReferenceObservation,
)


@dataclass(frozen=True, slots=True)
class V3MachineFactPresentation:
    timeframe: str
    reference_period_identity: str
    reference_period: str
    availability: str
    unavailable_explanation: str | None
    bc: str | None
    cp: str | None
    tc: str | None
    reference_high: str | None
    reference_low: str | None
    integrity_sha256: str


@dataclass(frozen=True, slots=True)
class V3VisualFactPresentation:
    timeframe: str
    cpr_observation: str
    reference_observation: str
    clustering_observation: str
    clustering_components: tuple[str, ...]
    evidence_sha256: str


@dataclass(frozen=True, slots=True)
class V3SponsorEvidencePresentation:
    run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    question_set_identity: str
    question_set_version: str
    machine_facts: tuple[V3MachineFactPresentation, ...]
    visual_facts: tuple[V3VisualFactPresentation, ...]
    sponsor_status: str
    readiness: str
    readiness_reason: str
    next_step: str
    readiness_identity: str
    review_pack_identity: str | None

    def machine_for(self, timeframe: str) -> V3MachineFactPresentation:
        return next(item for item in self.machine_facts if item.timeframe == timeframe)

    def visual_for(self, timeframe: str) -> V3VisualFactPresentation:
        return next(item for item in self.visual_facts if item.timeframe == timeframe)


def present_visual_v3_review(
    review: CompletedVisualV3Review,
) -> V3SponsorEvidencePresentation:
    """Fail closed unless the selected persisted cycle is explicitly V3."""

    if type(review) is not CompletedVisualV3Review:
        raise TypeError("VISUAL_V3_SPONSOR_PRESENTATION_INVALID")
    readiness = review.readiness
    if (
        readiness.question_set_identity != VISUAL_QUESTION_SET_V3_ID
        or readiness.question_set_version not in {
            VISUAL_QUESTION_SET_V3_LEGACY_VERSION,
            VISUAL_QUESTION_SET_V3_VERSION,
        }
        or any(
            item.question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or item.question_set_version != readiness.question_set_version
            for item in review.responses
        )
    ):
        raise ValueError("VISUAL_V3_PRESENTATION_VERSION_MISMATCH")
    machine = review.mtf_snapshot.instrument(
        review.requirement.canonical_instrument
    ).reference_facts
    return V3SponsorEvidencePresentation(
        run_identity=readiness.run_identity,
        canonical_instrument=readiness.canonical_instrument,
        native_assessment_sha256=readiness.native_assessment_sha256,
        question_set_identity=readiness.question_set_identity,
        question_set_version=readiness.question_set_version,
        machine_facts=tuple(_machine(item) for item in machine),
        visual_facts=tuple(_visual(item) for item in review.responses),
        sponsor_status=_status(review),
        readiness=readiness.readiness.value,
        readiness_reason=_plain(readiness.primary_reason),
        next_step=_next_step(review),
        readiness_identity=readiness.result_sha256,
        review_pack_identity=(
            review.review_pack.review_pack_id if review.review_pack is not None else None
        ),
    )


def _machine(value: SwingReferenceCprMachineFact) -> V3MachineFactPresentation:
    available = value.availability is SwingReferenceAvailability.AVAILABLE
    return V3MachineFactPresentation(
        timeframe=value.chart_timeframe.value,
        reference_period_identity=value.reference_period_type.value,
        reference_period=_plain(value.reference_period_type.value),
        availability=value.availability.value,
        unavailable_explanation=(
            None if available else _unavailable(value.unavailable_reason)
        ),
        bc=_price(value.bc) if available else None,
        cp=_price(value.cp) if available else None,
        tc=_price(value.tc) if available else None,
        reference_high=_price(value.reference_high) if available else None,
        reference_low=_price(value.reference_low) if available else None,
        integrity_sha256=value.integrity_sha256,
    )


def _visual(value: VisualEvidenceV3Response) -> V3VisualFactPresentation:
    by_question = {item.question_id: item for item in value.observations}
    cpr = by_question[VisualQuestionV3.CPR_VISUAL_RELATIONSHIP]
    reference = by_question[VisualQuestionV3.GOVERNED_REFERENCE_VISUAL_CONTEXT]
    clustering = by_question[VisualQuestionV3.VISUAL_COMPONENT_CLUSTERING]
    if (
        type(cpr) is not VisualV3CprObservation
        or type(reference) is not VisualV3ReferenceObservation
        or type(clustering) is not VisualV3ClusteringObservation
    ):
        raise ValueError("VISUAL_V3_PRESENTATION_OBSERVATION_INVALID")
    return V3VisualFactPresentation(
        timeframe=value.timeframe.value,
        cpr_observation=_cpr(cpr),
        reference_observation=_reference(reference),
        clustering_observation=_clustering(clustering),
        clustering_components=tuple(_plain(item.value) for item in clustering.components),
        evidence_sha256=value.evidence_sha256,
    )


def _cpr(value: VisualV3CprObservation) -> str:
    if value.observation_status is not VisualObservationStatus.OBSERVED:
        return _missing_visual(
            value.ambiguity_reason,
            "The chart does not reliably show whether price is above, inside or below the governed CPR structure.",
        )
    if value.presence is not VisualStructurePresence.PRESENT:
        return "The governed CPR structure is not reliably identifiable on the chart."
    relationship = _plain(value.price_relationship.value).lower()
    interaction = _plain(value.interaction.value).lower()
    result = f"Price is visibly {relationship} CPR."
    if value.interaction.value != "NONE":
        result += f" CPR {interaction} is visible."
    return result


def _reference(value: VisualV3ReferenceObservation) -> str:
    if value.observation_status is not VisualObservationStatus.OBSERVED:
        return _missing_visual(
            value.ambiguity_reason,
            "The chart does not reliably establish price interaction with the governed reference structure.",
        )
    if value.presence is not VisualStructurePresence.PRESENT:
        return "The governed reference structure is not reliably identifiable on the chart."
    relationship = _plain(value.relationship.value).lower()
    interaction = _plain(value.interaction.value).lower()
    result = f"Price is visibly {relationship}."
    if value.interaction.value != "NONE":
        result += f" A {interaction} interaction is visible."
    return result


def _clustering(value: VisualV3ClusteringObservation) -> str:
    if value.observation_status is not VisualObservationStatus.OBSERVED:
        return _missing_visual(
            value.ambiguity_reason,
            "The chart does not reliably establish whether nearby structures cluster.",
        )
    mapping = {
        VisualClusteringState.CLUSTERED:
            "Multiple identified technical structures visibly cluster near price.",
        VisualClusteringState.NOT_CLUSTERED:
            "No meaningful visual clustering is observed.",
        VisualClusteringState.PARTIAL_COMPONENT_IDENTITY:
            "Multiple technical structures appear close together, but the chart does not reliably identify every participating component.",
        VisualClusteringState.NOT_OBSERVABLE:
            "The chart does not reliably establish whether nearby structures cluster.",
    }
    return mapping[value.clustering]


def _status(review: CompletedVisualV3Review) -> str:
    record = review.readiness
    if record.readiness is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION:
        return "READY FOR TRADE CONSTRUCTION"
    if record.readiness is NativeReadinessState.INVALIDATED:
        return "INVALIDATED"
    if any(
        item.availability is SwingReferenceAvailability.UNAVAILABLE
        for item in review.mtf_snapshot.instrument(
            review.requirement.canonical_instrument
        ).reference_facts
    ):
        return "REFERENCE DATA NOT AVAILABLE"
    if record.conditions.evidence_completeness is EvidenceCompleteness.INCOMPLETE:
        return "CHART CONFIRMATION REQUIRED"
    return _plain(record.readiness.value)


def _next_step(review: CompletedVisualV3Review) -> str:
    record = review.readiness
    if record.readiness is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION:
        return "The candidate is eligible for the existing Step-31 trade-construction workflow."
    if record.readiness is NativeReadinessState.INVALIDATED:
        return "The candidate is discarded from the current trade path; no further action is permitted."
    if any(
        item.availability is SwingReferenceAvailability.UNAVAILABLE
        for item in review.mtf_snapshot.instrument(
            review.requirement.canonical_instrument
        ).reference_facts
    ):
        return "A required deterministic reference fact is unavailable. No progression watch can be created from that missing fact."
    if record.conditions.evidence_completeness is EvidenceCompleteness.INCOMPLETE:
        return "A new governed chart review is required before KRONOS can reassess this evidence."
    if record.conditions.next_condition_state.value == "AVAILABLE":
        return "You may activate a KRONOS watch for the governed outstanding progression condition."
    return "KRONOS will preserve this decision until new governed evidence supports reassessment."


def _unavailable(value: SwingReferenceUnavailableReason | None) -> str:
    return {
        SwingReferenceUnavailableReason.INSUFFICIENT_CURRENT_CONTRACT_HISTORY:
            "The required completed reference period is not available from the current contract history.",
        SwingReferenceUnavailableReason.MISSING_REFERENCE_CONSTITUENTS:
            "KRONOS does not have every completed market session required to establish this reference period.",
        SwingReferenceUnavailableReason.REFERENCE_PERIOD_NOT_COMPLETE:
            "The governed reference period is not complete yet.",
        SwingReferenceUnavailableReason.CALENDAR_COMPLETION_UNAVAILABLE:
            "The governed market calendar cannot establish that this reference period is complete.",
        SwingReferenceUnavailableReason.SOURCE_FACT_UNAVAILABLE:
            "The required governed market fact is unavailable.",
        SwingReferenceUnavailableReason.INTEGRITY_FAILURE:
            "The reference fact failed integrity validation and remains unavailable.",
    }[value]


def _missing_visual(reason: str, fallback: str) -> str:
    return fallback if not reason.strip() else f"{fallback} Reason: {reason.strip()}"


def _price(value: float | None) -> str:
    if value is None:
        raise ValueError("VISUAL_V3_PRICE_UNAVAILABLE")
    return "₹" + f"{value:,.4f}".rstrip("0").rstrip(".")


def _plain(value: str) -> str:
    return value.replace("_", " ").title()


__all__ = [
    "V3MachineFactPresentation",
    "V3SponsorEvidencePresentation",
    "V3VisualFactPresentation",
    "present_visual_v3_review",
]
