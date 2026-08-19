from dataclasses import replace

from kronos.browser.swing_readiness_presentation import present_native_readiness
from kronos.swing.v1.native_readiness import (
    NativeReadinessState,
    create_native_readiness_record,
)
from kronos.swing.v1.native_review import NativeLayer2EvidenceState
from kronos.swing.v1.visual_evidence_v2 import (
    VisualLevelAvailability,
    VisualObservationStatus,
    VisualQuestionV2,
    VisualTimeframe,
)
from tests.unit.swing.v1.test_native_readiness import (
    NOW,
    _complete_visual,
    _requirement,
)
from tests.unit.swing.v1.test_native_review import _layer2


def _with_blockers(
    *blockers: tuple[VisualTimeframe, VisualQuestionV2, VisualObservationStatus],
):  # type: ignore[no-untyped-def]
    visual = list(_complete_visual())
    for timeframe, question, status in blockers:
        response = next(item for item in visual if item.timeframe is timeframe)
        observations = tuple(
            replace(
                item,
                observation_status=status,
                observation="EVIDENCE NOT SUFFICIENTLY ESTABLISHED",
                level_availability=(
                    VisualLevelAvailability.NOT_APPLICABLE
                    if status is VisualObservationStatus.NOT_APPLICABLE
                    else VisualLevelAvailability.LEVEL_UNAVAILABLE
                ),
                price=None,
                zone_low=None,
                zone_high=None,
                ambiguity_reason=(
                    "MANDATORY EVIDENCE NOT SUFFICIENTLY ESTABLISHED"
                    if status in {
                        VisualObservationStatus.PARTIAL,
                        VisualObservationStatus.NOT_VISIBLE,
                        VisualObservationStatus.UNAVAILABLE,
                        VisualObservationStatus.INVALID,
                    }
                    else ""
                ),
            )
            if item.question_id is question else item
            for item in response.observations
        )
        visual[visual.index(response)] = replace(response, observations=observations)
    return tuple(visual)


def _presentation(visual):  # type: ignore[no-untyped-def]
    requirement = _requirement()
    record = create_native_readiness_record(
        requirement,
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS),
        visual,
        created_at=NOW,
    )
    return record, present_native_readiness(record, requirement, visual)


def test_chart_level_blockers_collapse_to_sponsor_categories_without_mutation() -> None:
    visual = _with_blockers(
        (VisualTimeframe.DAILY, VisualQuestionV2.CPR_CONTEXT, VisualObservationStatus.PARTIAL),
        (VisualTimeframe.FOUR_HOUR, VisualQuestionV2.CPR_CONTEXT, VisualObservationStatus.NOT_VISIBLE),
        (VisualTimeframe.ONE_HOUR, VisualQuestionV2.CPR_CONTEXT, VisualObservationStatus.UNAVAILABLE),
        (VisualTimeframe.ONE_HOUR, VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT, VisualObservationStatus.PARTIAL),
        (VisualTimeframe.WEEKLY, VisualQuestionV2.VISUAL_CONFLUENCE, VisualObservationStatus.PARTIAL),
        (VisualTimeframe.DAILY, VisualQuestionV2.VISUAL_CONFLUENCE, VisualObservationStatus.PARTIAL),
        (VisualTimeframe.FOUR_HOUR, VisualQuestionV2.VISUAL_CONFLUENCE, VisualObservationStatus.PARTIAL),
        (VisualTimeframe.ONE_HOUR, VisualQuestionV2.VISUAL_CONFLUENCE, VisualObservationStatus.PARTIAL),
    )
    record, presentation = _presentation(visual)

    assert record.readiness is NativeReadinessState.CONTEXT_INCOMPLETE
    assert presentation.internal_readiness is NativeReadinessState.CONTEXT_INCOMPLETE
    assert presentation.status == "CHART LEVELS NOT CONFIRMED"
    assert presentation.missing_evidence == (
        "CPR", "1H PDH/PDL", "Confluence Zone",
    )
    assert sum("Q2 CPR CONTEXT" in item for item in presentation.blocker_details) == 3
    assert sum("Q9 VISUAL CONFLUENCE" in item for item in presentation.blocker_details) == 4
    assert sum("Q4 PDH PDL REFERENCE CONTEXT" in item for item in presentation.blocker_details) == 1


def test_missing_categories_are_evidence_driven_and_q3_none_is_complete() -> None:
    visual = _with_blockers(
        (VisualTimeframe.DAILY, VisualQuestionV2.CPR_CONTEXT, VisualObservationStatus.PARTIAL),
    )
    daily = next(item for item in visual if item.timeframe is VisualTimeframe.DAILY)
    observations = tuple(
        replace(item, observation="NONE")
        if item.question_id is VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP
        else item
        for item in daily.observations
    )
    values = tuple(
        replace(item, observations=observations) if item is daily else item
        for item in visual
    )
    _, presentation = _presentation(values)

    assert presentation.status == "CHART LEVELS NOT CONFIRMED"
    assert presentation.missing_evidence == ("CPR",)
    assert all("Q3" not in item for item in presentation.blocker_details)
    assert "Additional Support/Resistance" not in presentation.missing_evidence


def test_non_level_or_not_applicable_incompleteness_uses_safe_fallback() -> None:
    non_level = _with_blockers(
        (VisualTimeframe.DAILY, VisualQuestionV2.VISUAL_CHART_VALIDATION, VisualObservationStatus.PARTIAL),
    )
    record, presentation = _presentation(non_level)
    assert record.readiness is NativeReadinessState.CONTEXT_INCOMPLETE
    assert presentation.status == "MORE REVIEW EVIDENCE REQUIRED"
    assert presentation.missing_evidence == ("Chart Validation",)

    not_applicable = _with_blockers(
        (VisualTimeframe.DAILY, VisualQuestionV2.CPR_CONTEXT, VisualObservationStatus.NOT_APPLICABLE),
    )
    _, fallback = _presentation(not_applicable)
    assert fallback.status == "MORE REVIEW EVIDENCE REQUIRED"
    assert fallback.missing_evidence == ("Required Review Evidence",)
    assert "CPR" not in fallback.missing_evidence
    assert all("NOT_APPLICABLE" not in item for item in fallback.blocker_details)


def test_ready_presentation_remains_unchanged() -> None:
    visual = _complete_visual()
    record, presentation = _presentation(visual)

    assert record.readiness is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION
    assert presentation.status == "READY FOR TRADE CONSTRUCTION"
    assert presentation.missing_evidence == ()
    assert presentation.blocker_details == ()
