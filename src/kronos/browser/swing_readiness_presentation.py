"""Sponsor presentation for persisted Native Readiness evidence."""

from __future__ import annotations

from dataclasses import dataclass

from kronos.swing.v1.native_readiness import (
    EvidenceCompleteness,
    NativeLayer2ReadinessRecord,
    NativeReadinessState,
    ReferenceCondition,
    ThesisIntact,
    sponsor_status,
)
from kronos.swing.v1.native_review import NativeReviewRequirement
from kronos.swing.v1.visual_evidence_v2 import (
    VisualEvidenceSubjectKind,
    VisualEvidenceV2Response,
    VisualObservationStatus,
    VisualQuestionRouting,
    VisualQuestionV2,
    visual_question_routing,
)


@dataclass(frozen=True, slots=True)
class SponsorReadinessPresentation:
    """Read-only Sponsor wording derived from one governed evidence cycle."""

    status: str
    missing_evidence: tuple[str, ...]
    blocker_details: tuple[str, ...]
    internal_readiness: NativeReadinessState


_QUESTION_NUMBER = {
    VisualQuestionV2.VISUAL_CHART_VALIDATION: "Q1",
    VisualQuestionV2.CPR_CONTEXT: "Q2",
    VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP: "Q3",
    VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT: "Q4",
    VisualQuestionV2.PRICE_ACTION_QUALITY: "Q5",
    VisualQuestionV2.VISUAL_OBSTACLE_EVIDENCE: "Q6",
    VisualQuestionV2.MATURITY_AND_CHASE_CONTEXT: "Q7",
    VisualQuestionV2.PINE_VISIBLE_EVIDENCE: "Q8",
    VisualQuestionV2.VISUAL_CONFLUENCE: "Q9",
    VisualQuestionV2.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS: "Q10",
}

_GENERIC_LABEL = {
    VisualQuestionV2.VISUAL_CHART_VALIDATION: "Chart Validation",
    VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP: "Additional Support/Resistance",
    VisualQuestionV2.PRICE_ACTION_QUALITY: "Price-action Quality",
    VisualQuestionV2.VISUAL_OBSTACLE_EVIDENCE: "Visual Obstacles",
    VisualQuestionV2.MATURITY_AND_CHASE_CONTEXT: "Maturity/Chase Context",
}

_LEVEL_QUESTIONS = {
    VisualQuestionV2.CPR_CONTEXT,
    VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT,
    VisualQuestionV2.VISUAL_CONFLUENCE,
}


def present_native_readiness(
    record: NativeLayer2ReadinessRecord,
    requirement: NativeReviewRequirement,
    visual: tuple[VisualEvidenceV2Response, ...],
) -> SponsorReadinessPresentation:
    """Translate persisted Readiness without changing its governed meaning."""

    _validate_binding(record, requirement, visual)
    if record.readiness is not NativeReadinessState.CONTEXT_INCOMPLETE:
        return SponsorReadinessPresentation(
            sponsor_status(record.readiness), (), (), record.readiness
        )

    blockers = _mandatory_visual_blockers(requirement, visual)
    categories = _collapsed_categories(blockers)
    details = tuple(_blocker_detail(*item) for item in blockers)
    non_chart_categories: list[str] = []
    conditions = record.conditions
    if conditions.thesis_intact is ThesisIntact.UNAVAILABLE:
        non_chart_categories.append("Native Thesis Evidence")
    if conditions.reference_condition in {
        ReferenceCondition.UNAVAILABLE,
        ReferenceCondition.INVALID,
    }:
        non_chart_categories.append("Reference Market Evidence")
    if conditions.evidence_completeness is EvidenceCompleteness.INVALID:
        non_chart_categories.append("Invalid Review Evidence")

    missing = tuple(dict.fromkeys((*categories, *non_chart_categories)))
    chart_level_only = (
        bool(blockers)
        and all(question in _LEVEL_QUESTIONS for _, question, _, _ in blockers)
        and all(
            status in {
                VisualObservationStatus.PARTIAL,
                VisualObservationStatus.NOT_VISIBLE,
                VisualObservationStatus.UNAVAILABLE,
            }
            for _, _, status, _ in blockers
        )
        and not non_chart_categories
        and conditions.thesis_intact is ThesisIntact.YES
        and conditions.evidence_completeness is EvidenceCompleteness.INCOMPLETE
    )
    if chart_level_only:
        status = "CHART LEVELS NOT CONFIRMED"
    else:
        status = "MORE REVIEW EVIDENCE REQUIRED"
        if not missing:
            missing = ("Required Review Evidence",)
    return SponsorReadinessPresentation(
        status, missing, details, record.readiness
    )


def _mandatory_visual_blockers(
    requirement: NativeReviewRequirement,
    visual: tuple[VisualEvidenceV2Response, ...],
) -> tuple[tuple[str, VisualQuestionV2, VisualObservationStatus, str], ...]:
    native = {
        item.timeframe.value: item
        for item in visual
        if item.subject_kind is VisualEvidenceSubjectKind.NATIVE
    }
    blockers: list[tuple[str, VisualQuestionV2, VisualObservationStatus, str]] = []
    for fact in requirement.thesis.timeframe_facts:
        response = native.get(fact.timeframe.value)
        if response is None:
            continue
        for question, routing in visual_question_routing(response.timeframe):
            if routing is not VisualQuestionRouting.YES:
                continue
            observation = next(
                item for item in response.observations
                if item.question_id is question
            )
            if observation.observation_status in {
                VisualObservationStatus.OBSERVED,
                VisualObservationStatus.NOT_APPLICABLE,
            }:
                continue
            blockers.append((
                response.timeframe.value,
                question,
                observation.observation_status,
                observation.level_availability.value,
            ))
    return tuple(blockers)


def _collapsed_categories(
    blockers: tuple[tuple[str, VisualQuestionV2, VisualObservationStatus, str], ...],
) -> tuple[str, ...]:
    values: list[str] = []
    for timeframe, question, _, _ in blockers:
        if question is VisualQuestionV2.CPR_CONTEXT:
            label = "CPR"
        elif question is VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT:
            label = f"{timeframe} PDH/PDL"
        elif question is VisualQuestionV2.VISUAL_CONFLUENCE:
            label = "Confluence Zone"
        else:
            label = _GENERIC_LABEL.get(
                question, question.value.replace("_", " ").title()
            )
        if label not in values:
            values.append(label)
    priority = {"CPR": 0, "Confluence Zone": 2}
    return tuple(sorted(
        values,
        key=lambda value: (
            1 if value.endswith(" PDH/PDL") else priority.get(value, 3),
            value,
        ),
    ))


def _blocker_detail(
    timeframe: str,
    question: VisualQuestionV2,
    status: VisualObservationStatus,
    level: str,
) -> str:
    return " · ".join((
        f"{_QUESTION_NUMBER[question]} {question.value.replace('_', ' ')}",
        timeframe,
        status.value,
        level,
    ))


def _validate_binding(
    record: NativeLayer2ReadinessRecord,
    requirement: NativeReviewRequirement,
    visual: tuple[VisualEvidenceV2Response, ...],
) -> None:
    if (
        type(record) is not NativeLayer2ReadinessRecord
        or type(requirement) is not NativeReviewRequirement
        or type(visual) is not tuple
        or record.run_identity != requirement.native_run_identity
        or record.canonical_instrument != requirement.canonical_instrument
        or record.native_assessment_sha256
        != requirement.thesis.native_assessment_sha256
        or any(
            item.native_run_identity != record.run_identity
            or item.native_assessment_sha256 != record.native_assessment_sha256
            or item.native_canonical_instrument != record.canonical_instrument
            for item in visual
        )
    ):
        raise ValueError("SPONSOR_READINESS_PRESENTATION_BINDING_INVALID")


__all__ = ["SponsorReadinessPresentation", "present_native_readiness"]
