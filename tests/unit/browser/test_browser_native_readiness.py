from dataclasses import replace

import pytest

from kronos.browser.views import _native_one_minute_review
from kronos.swing.v1.native_discovery import Native4HState
from kronos.swing.v1.native_readiness import (
    DeterministicExtensionEvidence,
    DeterministicObstacleEvidence,
    DeterministicRetestEvidence,
    NativeConditionInputs,
    NativeReadinessState,
    create_native_readiness_record,
    sponsor_status,
)
from kronos.swing.v1.native_review import NativeLayer2EvidenceState
from kronos.swing.v1.visual_evidence_v2 import VisualQuestionV2, VisualTimeframe
from tests.unit.swing.v1.test_native_readiness import (
    NOW,
    _complete_visual,
    _condition_evidence,
    _requirement,
)
from tests.unit.swing.v1.test_native_review import _layer2


def _visual_with(*, extended: bool = False, obstacle: bool = False):  # type: ignore[no-untyped-def]
    values = list(_complete_visual())
    response = next(item for item in values if item.timeframe is VisualTimeframe.FOUR_HOUR)
    observations = tuple(
        replace(item, observation="VISIBLY_EXTENDED")
        if extended and item.question_id is VisualQuestionV2.MATURITY_AND_CHASE_CONTEXT
        else replace(item, observation="VISIBLE RESISTANCE")
        if obstacle and item.question_id is VisualQuestionV2.VISUAL_OBSTACLE_EVIDENCE
        else item
        for item in response.observations
    )
    values[values.index(response)] = replace(response, observations=observations)
    return tuple(values)


def _record(state: NativeReadinessState):  # type: ignore[no-untyped-def]
    requirement = _requirement()
    visual = _complete_visual()
    inputs = NativeConditionInputs()
    if state is NativeReadinessState.CONTEXT_INCOMPLETE:
        visual = ()
    elif state is NativeReadinessState.INVALIDATED:
        requirement = replace(requirement, thesis=replace(requirement.thesis, four_hour_state=Native4HState.FAILED))
    elif state is NativeReadinessState.EXTENDED_DO_NOT_CHASE:
        visual = _visual_with(extended=True)
        inputs = NativeConditionInputs(extension=DeterministicExtensionEvidence(_condition_evidence(), True))
    elif state is NativeReadinessState.WEAKENING:
        requirement = replace(requirement, thesis=replace(requirement.thesis, four_hour_state=Native4HState.DETERIORATING))
    elif state is NativeReadinessState.WAIT_PULLBACK_DEVELOPING:
        requirement = replace(requirement, thesis=replace(requirement.thesis, four_hour_state=Native4HState.DEVELOPING_PULLBACK))
    elif state is NativeReadinessState.WAIT_RETEST_DEVELOPING:
        inputs = NativeConditionInputs(retest=DeterministicRetestEvidence(_condition_evidence("RETEST_REFERENCE"), True, True, False, False, False))
    elif state is NativeReadinessState.WAIT_OBSTACLE_CLEARANCE:
        visual = _visual_with(obstacle=True)
        inputs = NativeConditionInputs(
            obstacle=DeterministicObstacleEvidence(_condition_evidence("OBSTACLE"), True, True)
        )
    evidence = _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    record = create_native_readiness_record(
        requirement, evidence, visual, created_at=NOW, inputs=inputs,
    )
    assert record.readiness is state
    return record, requirement, visual


@pytest.mark.parametrize("state", tuple(NativeReadinessState))
def test_all_eight_states_render_one_minute_sponsor_surface(state: NativeReadinessState) -> None:
    record, requirement, visual = _record(state)
    assert record.step31_eligible is (
        state is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION
    )
    html = _native_one_minute_review(record, requirement, visual, None)
    expected_status = (
        "MORE REVIEW EVIDENCE REQUIRED"
        if state is NativeReadinessState.CONTEXT_INCOMPLETE
        else sponsor_status(state)
    )
    assert expected_status in html
    if state is NativeReadinessState.CONTEXT_INCOMPLETE:
        assert "Required Review Evidence" in html
        assert "CONTEXT_INCOMPLETE" in html
    assert "WHY THIS TRADE?" in html
    assert html.count("one-minute-fact") >= 3
    assert "ANALYSIS DETAILS" in html
    assert record.result_sha256 in html
    wait = state in {
        NativeReadinessState.WAIT_PULLBACK_DEVELOPING,
        NativeReadinessState.WAIT_RETEST_DEVELOPING,
        NativeReadinessState.WAIT_OBSTACLE_CLEARANCE,
        NativeReadinessState.EXTENDED_DO_NOT_CHASE,
        NativeReadinessState.WEAKENING,
    }
    assert ("WHAT AM I WAITING FOR?" in html) is wait
    assert "Entry</span>" not in html
    assert "Stop</span>" not in html
    assert "Target</span>" not in html
    assert "R:R" not in html
