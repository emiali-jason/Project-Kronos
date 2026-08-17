from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.native_discovery import Native1HState, Native4HState
from kronos.swing.v1.native_readiness import (
    ConditionEvidence,
    DeterministicExtensionEvidence,
    DeterministicObstacleEvidence,
    DeterministicRetestEvidence,
    DeteriorationCondition,
    EvidenceCompleteness,
    ExtensionCondition,
    FailureCondition,
    LevelAvailability,
    NATIVE_LAYER2_CONDITION_POLICY_ID,
    NATIVE_READINESS_POLICY_ID,
    NativeConditionInputs,
    NativeLayer2Conditions,
    NativeLayer2ReadinessStore,
    NativeReadinessState,
    NextConditionEvidence,
    NextConditionState,
    ObstacleCondition,
    PineCondition,
    PullbackCondition,
    ReferenceCondition,
    RetestCondition,
    ThesisIntact,
    build_native_layer2_conditions,
    create_native_readiness_record,
    resolve_native_readiness,
)
from kronos.swing.v1.native_review import (
    McxReferenceEvidenceState,
    NativeLayer2EvidenceState,
    NativeReviewEvidenceStore,
    bind_mcx_reference_evidence,
    build_native_review_requirements,
    unavailable_mcx_reference,
)
from kronos.swing.v1.pine_evidence import build_pine_layer2_handoff
from kronos.swing.v1.visual_evidence_v2 import (
    VisualObservationStatus,
    VisualQuestionRouting,
    VisualQuestionV2,
    VisualTimeframe,
    build_visual_evidence_v2_request,
    visual_question_routing,
)
from tests.fixtures.swing_v1_pine_evidence import MCX_PRODUCTION_COMPLETED, MCX_REGISTRY
from tests.unit.swing.v1.test_native_review import _evidence_run, _layer2
from tests.unit.swing.v1.test_native_review_mcx_reference import _run_with_probables
from tests.unit.swing.v1.test_visual_evidence_v2 import IMAGE, _observation, _request, _response


NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def _complete_visual():  # type: ignore[no-untyped-def]
    values = []
    for timeframe in VisualTimeframe:
        request = _request(timeframe=timeframe)
        replacements = {}
        for question, routing in visual_question_routing(timeframe):
            if routing is VisualQuestionRouting.YES:
                replacements[question] = _observation(
                    request,
                    question,
                    status=VisualObservationStatus.OBSERVED,
                    observation="VISIBLE FACT",
                )
        values.append(_response(request, replacements))
    return tuple(values)


def _complete_visual_pairs():  # type: ignore[no-untyped-def]
    values = []
    for timeframe in VisualTimeframe:
        request = _request(timeframe=timeframe)
        replacements = {
            question: _observation(
                request,
                question,
                status=VisualObservationStatus.OBSERVED,
                observation="VISIBLE FACT",
            )
            for question, routing in visual_question_routing(timeframe)
            if routing is VisualQuestionRouting.YES
        }
        values.append((request, _response(request, replacements)))
    return tuple(values)


def _complete_visual_for(requirement):  # type: ignore[no-untyped-def]
    values = []
    for timeframe in VisualTimeframe:
        fact = next(item for item in requirement.thesis.timeframe_facts if item.timeframe.value == timeframe.value)
        request = build_visual_evidence_v2_request(
            requirement,
            timeframe=timeframe,
            observation_boundary=fact.observation_boundary,
            chart_identity=requirement.canonical_instrument,
            content_type="image/png",
            original_image=IMAGE,
            request_timestamp=NOW,
        )
        replacements = {
            question: _observation(
                request, question,
                status=VisualObservationStatus.OBSERVED,
                observation="VISIBLE FACT",
            )
            for question, routing in visual_question_routing(timeframe)
            if routing is VisualQuestionRouting.YES
        }
        values.append(_response(request, replacements))
    return tuple(values)


def _requirement():  # type: ignore[no-untyped-def]
    facts, run, _ = _evidence_run()
    return build_native_review_requirements(run, facts)[0]


def _condition_evidence(identity: str = "STRUCTURAL_CONTEXT") -> ConditionEvidence:
    requirement = _requirement()
    return ConditionEvidence(
        identity,
        (requirement.thesis.native_assessment_sha256,),
        FactualTimeframe.FOUR_HOUR,
        requirement.thesis.operative_anchor_identity,
        LevelAvailability.AVAILABLE,
        requirement.thesis.operative_anchor_price,
        None,
        None,
        requirement.thesis.operative_anchor_boundary,
        f"{identity}_AUTHORITATIVE",
        requirement.thesis.provider_provenance,
    )


def _conditions(**changes):  # type: ignore[no-untyped-def]
    values = dict(
        thesis_intact=ThesisIntact.YES,
        pullback_condition=PullbackCondition.NONE,
        retest_condition=RetestCondition.NONE,
        extension_condition=ExtensionCondition.NONE,
        deterioration_condition=DeteriorationCondition.NONE,
        failure_condition=FailureCondition.NONE,
        obstacle_condition=ObstacleCondition.NONE,
        pine_condition=PineCondition.SUPPORTS,
        reference_condition=ReferenceCondition.NOT_APPLICABLE,
        evidence_completeness=EvidenceCompleteness.COMPLETE,
        next_condition_state=NextConditionState.NONE,
        next_condition=None,
        evidence=(),
    )
    values.update(changes)
    return NativeLayer2Conditions(**values)


@pytest.mark.parametrize(
    ("changes", "expected"),
    (
        ({"evidence_completeness": EvidenceCompleteness.INCOMPLETE, "failure_condition": FailureCondition.AFFIRMATIVE_FAILURE}, NativeReadinessState.CONTEXT_INCOMPLETE),
        ({"failure_condition": FailureCondition.AFFIRMATIVE_FAILURE, "extension_condition": ExtensionCondition.MATERIAL_EXTENSION}, NativeReadinessState.INVALIDATED),
        ({"extension_condition": ExtensionCondition.MATERIAL_EXTENSION, "deterioration_condition": DeteriorationCondition.MEANINGFUL_DETERIORATION}, NativeReadinessState.EXTENDED_DO_NOT_CHASE),
        ({"deterioration_condition": DeteriorationCondition.MEANINGFUL_DETERIORATION, "pullback_condition": PullbackCondition.DEVELOPING}, NativeReadinessState.WEAKENING),
        ({"pullback_condition": PullbackCondition.DEVELOPING, "retest_condition": RetestCondition.DEVELOPING}, NativeReadinessState.WAIT_PULLBACK_DEVELOPING),
        ({"retest_condition": RetestCondition.DEVELOPING, "obstacle_condition": ObstacleCondition.ADVERSE_BLOCKING}, NativeReadinessState.WAIT_RETEST_DEVELOPING),
        ({"obstacle_condition": ObstacleCondition.ADVERSE_BLOCKING}, NativeReadinessState.WAIT_OBSTACLE_CLEARANCE),
        ({}, NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION),
    ),
)
def test_exact_frozen_precedence(changes, expected) -> None:  # type: ignore[no-untyped-def]
    assert resolve_native_readiness(_conditions(**changes))[0] is expected


def test_native_pullback_deterioration_and_failure_own_conditions() -> None:
    requirement = _requirement()
    evidence = _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    pullback = replace(requirement, thesis=replace(requirement.thesis, four_hour_state=Native4HState.DEVELOPING_PULLBACK))
    result = build_native_layer2_conditions(pullback, evidence, _complete_visual())
    assert result.pullback_condition is PullbackCondition.DEVELOPING
    assert result.next_condition is not None

    deteriorating = replace(requirement, thesis=replace(requirement.thesis, four_hour_state=Native4HState.DETERIORATING))
    assert build_native_layer2_conditions(deteriorating, evidence, _complete_visual()).deterioration_condition is DeteriorationCondition.MEANINGFUL_DETERIORATION

    local = replace(requirement, thesis=replace(requirement.thesis, one_hour_state=Native1HState.DETERIORATING))
    assert build_native_layer2_conditions(local, evidence, _complete_visual()).deterioration_condition is DeteriorationCondition.MEANINGFUL_DETERIORATION

    failed = replace(requirement, thesis=replace(requirement.thesis, four_hour_state=Native4HState.FAILED))
    failed_result = build_native_layer2_conditions(failed, evidence, _complete_visual())
    assert failed_result.failure_condition is FailureCondition.AFFIRMATIVE_FAILURE
    assert failed_result.thesis_intact is ThesisIntact.NO


def test_retest_chronology_is_typed_and_completion_never_auto_readies() -> None:
    requirement = _requirement()
    evidence = _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    reference = _condition_evidence("RETEST_REFERENCE")
    developing = DeterministicRetestEvidence(reference, True, True, False, False, False)
    conditions = build_native_layer2_conditions(
        requirement, evidence, _complete_visual(),
        inputs=NativeConditionInputs(retest=developing),
    )
    assert conditions.retest_condition is RetestCondition.DEVELOPING
    complete = replace(developing, outcome_resolved=True, accepted_away_in_native_direction=True)
    completed = build_native_layer2_conditions(
        requirement, evidence, _complete_visual(),
        inputs=NativeConditionInputs(retest=complete),
    )
    assert completed.retest_condition is RetestCondition.COMPLETE
    assert resolve_native_readiness(completed)[0] is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION

    tolerance_required = replace(developing, requires_unapproved_tolerance=True)
    unavailable = build_native_layer2_conditions(
        requirement, evidence, _complete_visual(),
        inputs=NativeConditionInputs(retest=tolerance_required),
    )
    assert unavailable.retest_condition is RetestCondition.UNAVAILABLE
    assert resolve_native_readiness(unavailable)[0] is NativeReadinessState.CONTEXT_INCOMPLETE


def test_visual_language_alone_has_no_condition_authority() -> None:
    requirement = _requirement()
    evidence = _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    visual = list(_complete_visual())
    response = next(item for item in visual if item.timeframe is VisualTimeframe.FOUR_HOUR)
    observations = tuple(
        replace(item, observation="VISIBLY_EXTENDED")
        if item.question_id is VisualQuestionV2.MATURITY_AND_CHASE_CONTEXT
        else replace(item, observation="ORDERLY_PULLBACK")
        if item.question_id is VisualQuestionV2.PRICE_ACTION_QUALITY
        else item
        for item in response.observations
    )
    visual[visual.index(response)] = replace(response, observations=observations)
    conditions = build_native_layer2_conditions(requirement, evidence, tuple(visual))
    assert conditions.extension_condition is ExtensionCondition.NONE
    assert conditions.pullback_condition is PullbackCondition.NONE
    assert conditions.retest_condition is RetestCondition.NONE
    assert conditions.failure_condition is FailureCondition.NONE


def test_extension_and_obstacle_require_visual_and_deterministic_evidence() -> None:
    requirement = _requirement()
    evidence = _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    visual = list(_complete_visual())
    response = next(item for item in visual if item.timeframe is VisualTimeframe.FOUR_HOUR)
    observations = tuple(
        replace(item, observation="VISIBLY_EXTENDED")
        if item.question_id is VisualQuestionV2.MATURITY_AND_CHASE_CONTEXT
        else replace(item, observation="VISIBLE RESISTANCE")
        if item.question_id is VisualQuestionV2.VISUAL_OBSTACLE_EVIDENCE
        else item
        for item in response.observations
    )
    visual[visual.index(response)] = replace(response, observations=observations)
    extension = DeterministicExtensionEvidence(_condition_evidence(), True)
    obstacle = DeterministicObstacleEvidence(_condition_evidence("OBSTACLE"), True, True)
    conditions = build_native_layer2_conditions(
        requirement, evidence, tuple(visual),
        inputs=NativeConditionInputs(extension=extension, obstacle=obstacle),
    )
    assert conditions.extension_condition is ExtensionCondition.MATERIAL_EXTENSION
    assert conditions.obstacle_condition is ObstacleCondition.ADVERSE_BLOCKING


def test_naked_pine_contradiction_does_not_block_ready() -> None:
    requirement = _requirement()
    evidence = replace(
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS),
        pine_state=NativeLayer2EvidenceState.CONTRADICTS_NATIVE_THESIS,
    )
    conditions = build_native_layer2_conditions(requirement, evidence, _complete_visual())
    assert conditions.pine_condition is PineCondition.CONTRADICTS
    assert resolve_native_readiness(conditions)[0] is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION


@pytest.mark.parametrize(
    ("reference_state", "expected", "readiness"),
    (
        (McxReferenceEvidenceState.SUPPORTS, ReferenceCondition.SUPPORTS, NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION),
        (McxReferenceEvidenceState.NEUTRAL, ReferenceCondition.NEUTRAL, NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION),
        (McxReferenceEvidenceState.CONTRADICTS, ReferenceCondition.CONTRADICTS, NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION),
    ),
)
def test_mcx_reference_state_is_preserved_without_direct_readiness_authority(
    reference_state, expected, readiness  # type: ignore[no-untyped-def]
) -> None:
    facts, run = _run_with_probables("GOLDM")
    requirement = build_native_review_requirements(run, facts)[0]
    evidence = _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    handoff = build_pine_layer2_handoff(MCX_PRODUCTION_COMPLETED, MCX_REGISTRY)
    result = bind_mcx_reference_evidence(
        requirement, handoff,
        native_run_identity=run.run_identity,
        mcx_canonical_instrument="GOLDM",
        chart_revision_sha256="d" * 64,
        expected_chart_revision_sha256="d" * 64,
        expected_timeframe=handoff.timeframe,
        evidence_state=reference_state,
    )
    conditions = build_native_layer2_conditions(
        requirement, evidence, _complete_visual_for(requirement), reference=result,
    )
    assert conditions.reference_condition is expected
    assert resolve_native_readiness(conditions)[0] is readiness


def test_mcx_unavailable_or_invalid_required_reference_is_context_incomplete() -> None:
    facts, run = _run_with_probables("GOLDM")
    requirement = build_native_review_requirements(run, facts)[0]
    evidence = _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    visual = _complete_visual_for(requirement)
    missing = build_native_layer2_conditions(
        requirement, evidence, visual, reference=unavailable_mcx_reference(requirement),
    )
    assert missing.reference_condition is ReferenceCondition.UNAVAILABLE
    assert resolve_native_readiness(missing)[0] is NativeReadinessState.CONTEXT_INCOMPLETE

    handoff = build_pine_layer2_handoff(MCX_PRODUCTION_COMPLETED, MCX_REGISTRY)
    invalid_result = bind_mcx_reference_evidence(
        requirement, handoff,
        native_run_identity=run.run_identity,
        mcx_canonical_instrument="GOLDM",
        chart_revision_sha256="d" * 64,
        expected_chart_revision_sha256="e" * 64,
        expected_timeframe=handoff.timeframe,
        evidence_state=McxReferenceEvidenceState.SUPPORTS,
    )
    invalid = build_native_layer2_conditions(
        requirement, evidence, visual, reference=invalid_result,
    )
    assert invalid.reference_condition is ReferenceCondition.INVALID
    assert invalid.evidence_completeness is EvidenceCompleteness.INVALID
    assert resolve_native_readiness(invalid)[0] is NativeReadinessState.CONTEXT_INCOMPLETE


def test_combined_record_is_policy_bound_integrity_checked_and_restart_safe(tmp_path: Path) -> None:
    requirement = _requirement()
    evidence = _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    record = create_native_readiness_record(
        requirement, evidence, _complete_visual(), created_at=NOW,
    )
    assert record.conditions.condition_policy_identity == NATIVE_LAYER2_CONDITION_POLICY_ID
    assert record.readiness_policy_identity == NATIVE_READINESS_POLICY_ID
    assert record.step31_eligible
    assert len(record.visual_evidence_hashes) == 4
    assert record.result_sha256 != "0" * 64
    store = NativeLayer2ReadinessStore(tmp_path)
    store.retain(record)
    assert store.load_for_requirements((requirement,)) == (record,)

    wrong = replace(requirement, thesis=replace(requirement.thesis, native_assessment_sha256="f" * 64))
    with pytest.raises(ValueError, match="BINDING"):
        store.load_for_requirements((wrong,))

    with pytest.raises(ValueError, match="RECORD_INVALID"):
        replace(
            record,
            visual_bindings=(
                (*record.visual_bindings[0][:2], "f" * 64),
                *record.visual_bindings[1:],
            ),
        )


def test_workflow_publishes_ready_only_eligibility_and_restores_combined_record(
    tmp_path: Path,
) -> None:
    facts, run, _ = _evidence_run()
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path))
    prepared = workflow.prepare(run, facts)
    for request, response in _complete_visual_pairs():
        workflow.ingest_visual_v2(request, response)
    requirement = prepared.requirements[0]
    evidence = _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    record = workflow.ingest_readiness(evidence, created_at=NOW)
    assert workflow.snapshot().readiness_records == (record,)
    assert workflow.step31_eligible_readiness() == (record,)

    restored = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path)).restore(run, facts)
    assert restored.readiness_records == (record,)


def test_review_contract_contains_no_trade_geometry() -> None:
    prohibited = {"entry", "entry_zone", "stop", "invalidation", "target", "risk_reward"}
    assert prohibited.isdisjoint(NativeLayer2Conditions.__dataclass_fields__)
    assert prohibited.isdisjoint(NextConditionEvidence.__dataclass_fields__)
