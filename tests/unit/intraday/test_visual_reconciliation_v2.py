from dataclasses import replace
from datetime import datetime, timezone

import pytest

from kronos.intraday.review import ObservationStatus
from kronos.intraday.visual_contract_v2 import MCX_QUESTIONS, NSE_QUESTIONS, VisualObservationV2
from kronos.intraday.visual_reconciliation_v2 import (
    AnchorState,
    DownstreamEligibility,
    GovernedAnchorContext,
    NativeMarketAuthority,
    Q10Classification,
    ReconciliationPrerequisites,
    VisualReconciliationInput,
    VisualReconciliationOutcome,
    create_reconciliation_record,
    evaluate_visual_reconciliation,
    input_identity,
    record_from_bytes,
    artifact_bytes,
)


_POSITIVE = {
    "Q1": "SUPPORTIVE",
    "Q2": "CLEAN_DIRECTIONAL_STRUCTURE",
    "Q3": "CLEAR_BASE_OR_CONSOLIDATION",
    "Q4": "CLEAR_FOLLOW_THROUGH",
    "Q5": "ORDERLY",
    "Q6": "NOT_OBSERVABLE",
    "Q7": "CLEAR_SPACE",
    "Q8": "NOT_VISIBLY_EXTENDED",
    "Q9": "NOT_OBSERVABLE",
    "Q10": "NONE",
    "M1": "SUPPORTIVE",
    "M2": "CLEAN_DIRECTIONAL_STRUCTURE",
    "M3": "CLEAR_FOLLOW_THROUGH",
    "M4": "ORDERLY",
    "M5": "NOT_OBSERVABLE",
    "R1": "OPPOSING",
    "R2": "MIXED_STRUCTURE",
    "R3": "WEAK_OR_MIXED_BASE",
    "R4": "MIXED",
    "R5": "UNCLEAR",
    "X1": "CONFIRMS_REFERENCE",
    "X2": "MOVING_TOGETHER",
    "X3": "CONFIRMED",
    "X4": "NO_MATERIAL_DIVERGENCE_VISIBLE",
    "X5": "NONE",
}


def _observation(question_id, answer=None, *, status=ObservationStatus.OBSERVED):
    question = next(
        item for item in NSE_QUESTIONS + MCX_QUESTIONS if item.question_id == question_id
    )
    answer = _POSITIVE[question_id] if answer is None else answer
    return VisualObservationV2(
        question_id=question_id,
        observation_status=status,
        answer=answer if status in {ObservationStatus.OBSERVED, ObservationStatus.PARTIAL} else None,
        visible_timeframes=question.timeframe_scope if status is ObservationStatus.OBSERVED else question.timeframe_scope[:1] if status is ObservationStatus.PARTIAL else (),
        visible_basis="visible" if status in {ObservationStatus.OBSERVED, ObservationStatus.PARTIAL} else None,
        status_detail="partial" if status is ObservationStatus.PARTIAL else "not visible" if status is ObservationStatus.NOT_VISIBLE else None,
        why_not_covered_elsewhere=(
            "bounded residual condition"
            if question_id in {"Q10", "X5"} and answer == "MATERIAL_OBSERVATION"
            else None
        ),
    )


def _input(*, direction="LONG", answers=None, prerequisites=None, anchor=None, q10=None):
    values = dict(_POSITIVE)
    values.update(answers or {})
    return VisualReconciliationInput(
        canonical_subject_identity="NSE-EQ-TEST",
        proposed_direction=direction,
        probables_run_identity="run",
        probable_result_identity="result",
        review_cycle_identity="cycle",
        review_pack_identity="pack",
        chart_revision_identity="chart",
        answer_pack_identity="answer",
        answer_source_sha256="a" * 64,
        visual_evidence_identity="visual",
        correspondence_identity="correspondence",
        machine_evidence_identities=("machine",),
        observations=tuple(_observation(f"Q{i}", values[f"Q{i}"]) for i in range(1, 11)),
        prerequisites=prerequisites or ReconciliationPrerequisites(),
        anchor=anchor or GovernedAnchorContext(),
        q10_classification=q10 or Q10Classification.NOT_APPLICABLE,
    )


def _mcx_input(*, native=None, reference=None, held=False, q10=None):
    native_values = dict(_POSITIVE)
    native_values.update(native or {})
    reference_values = dict(_POSITIVE)
    reference_values.update(reference or {})
    return VisualReconciliationInput(
        canonical_subject_identity="MCX-SUBJECT-NATGAS" if held else "MCX-SUBJECT-CRUDE",
        proposed_direction="SHORT",
        probables_run_identity="run",
        probable_result_identity="result",
        review_cycle_identity="cycle",
        review_pack_identity="pack",
        chart_revision_identity="chart",
        answer_pack_identity="answer",
        answer_source_sha256="b" * 64,
        visual_evidence_identity="visual",
        correspondence_identity="native-source",
        machine_evidence_identities=("machine", "contract", "binding"),
        observations=tuple(_observation(f"M{i}", native_values[f"M{i}"]) for i in range(1, 6)),
        native_market=NativeMarketAuthority.MCX,
        supporting_reference_observations=(
            tuple(_observation(f"R{i}", reference_values[f"R{i}"]) for i in range(1, 6))
            + tuple(_observation(f"X{i}", reference_values[f"X{i}"]) for i in range(1, 6))
        ),
        supporting_reference_authority="SUPPORTING_VISUAL_CONTEXT_ONLY",
        supporting_reference_independence="NOT_INDEPENDENTLY_ESTABLISHED",
        natgas_commissioning_state="HELD" if held else None,
        q10_classification=q10 or Q10Classification.NOT_APPLICABLE,
    )


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_clean_direction_is_confirmed_and_eligible(direction):
    decision = evaluate_visual_reconciliation(_input(direction=direction))
    assert decision.outcome is VisualReconciliationOutcome.CONFIRMED
    assert decision.reasons == ()
    assert decision.downstream_eligibility is DownstreamEligibility.ELIGIBLE_FOR_WO10_EVALUATION


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_opposing_broader_context_is_conditional_for_both_directions(direction):
    decision = evaluate_visual_reconciliation(
        _input(direction=direction, answers={"Q1": "OPPOSING"})
    )
    assert decision.outcome is VisualReconciliationOutcome.CONDITIONAL
    assert [item.reason_code for item in decision.reasons] == ["Q1_OPPOSING"]


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("Q1", "OPPOSING"),
        ("Q2", "MIXED_STRUCTURE"),
        ("Q2", "CONGESTED_STRUCTURE"),
        ("Q3", "WEAK_OR_MIXED_BASE"),
        ("Q3", "NO_CLEAR_BASE"),
        ("Q4", "WEAK_OR_STALLING"),
        ("Q4", "MIXED"),
        ("Q5", "MIXED"),
        ("Q5", "DISORDERLY"),
        ("Q5", "NO_CLEAR_PULLBACK_OR_PROGRESSION"),
        ("Q7", "LIMITED_SPACE"),
        ("Q7", "OBSTACLE_CLOSE"),
        ("Q8", "VISIBLY_EXTENDED"),
        ("Q8", "MIXED"),
    ],
)
def test_each_degradation_is_conditional(question, answer):
    decision = evaluate_visual_reconciliation(_input(answers={question: answer}))
    assert decision.outcome is VisualReconciliationOutcome.CONDITIONAL
    assert [item.reason_code for item in decision.reasons] == [f"{question}_{answer}"]


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_q4_failure_is_direction_aware_hard_contradiction(direction):
    decision = evaluate_visual_reconciliation(
        _input(direction=direction, answers={"Q4": "FAILED_OR_RETURNED_THROUGH"})
    )
    assert decision.outcome is VisualReconciliationOutcome.CONTRADICTED
    assert decision.reasons[0].reason_code == "SETUP_FAILED_OR_RETURNED_THROUGH"
    assert direction in decision.reasons[0].detail


def test_missing_anchor_makes_q6_q9_not_observable_neutral():
    decision = evaluate_visual_reconciliation(_input())
    assert decision.outcome is VisualReconciliationOutcome.CONFIRMED


def test_governed_anchor_invalidation_is_hard_contradiction():
    anchor = GovernedAnchorContext(
        AnchorState.ESTABLISHED,
        "anchor",
        (("Q9", "CLEAR_RETURN_THROUGH"),),
    )
    decision = evaluate_visual_reconciliation(
        _input(answers={"Q9": "CLEAR_RETURN_THROUGH"}, anchor=anchor)
    )
    assert decision.outcome is VisualReconciliationOutcome.CONTRADICTED
    assert decision.reasons[0].reason_code == "GOVERNED_ANCHOR_INVALIDATES_DIRECTION"


def test_partial_and_unclear_required_evidence_are_insufficient():
    value = _input()
    observations = tuple(
        _observation("Q7", status=ObservationStatus.PARTIAL)
        if item.question_id == "Q7"
        else _observation("Q8", "UNCLEAR")
        if item.question_id == "Q8"
        else item
        for item in value.observations
    )
    decision = evaluate_visual_reconciliation(replace(value, observations=observations))
    assert decision.outcome is VisualReconciliationOutcome.INSUFFICIENT
    assert [item.question_id for item in decision.reasons] == ["Q7", "Q8"]


@pytest.mark.parametrize(
    "field",
    [
        "machine_review_current",
        "answer_accepted",
        "identity_bound",
        "chart_bound",
        "correspondence_confirmed",
        "machine_sources_bound",
    ],
)
def test_each_failed_upstream_prerequisite_is_not_reconcilable(field):
    prerequisites = replace(ReconciliationPrerequisites(), **{field: False})
    decision = evaluate_visual_reconciliation(_input(prerequisites=prerequisites))
    assert decision.outcome is VisualReconciliationOutcome.NOT_RECONCILABLE
    assert decision.downstream_eligibility is DownstreamEligibility.NOT_ELIGIBLE_FOR_WO10_EVALUATION


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("machine_review_current", "MACHINE_REVIEW_NOT_CURRENT"),
        ("answer_accepted", "ANSWER_NOT_ACCEPTED"),
        ("identity_bound", "VISUAL_IDENTITY_NOT_BOUND"),
        ("chart_bound", "CHART_REVISION_NOT_BOUND"),
        ("correspondence_confirmed", "CORRESPONDENCE_NOT_CONFIRMED"),
        ("machine_sources_bound", "MACHINE_EVIDENCE_NOT_BOUND"),
    ],
)
def test_upstream_failure_reason_codes_cover_wrong_review_answer_chart_identity_and_sources(field, code):
    prerequisites = replace(ReconciliationPrerequisites(), **{field: False})
    decision = evaluate_visual_reconciliation(_input(prerequisites=prerequisites))
    assert decision.reasons[0].reason_code == code


def test_q10_requires_predeclared_deterministic_classification():
    value = _input(
        answers={"Q10": "MATERIAL_OBSERVATION"},
        q10=Q10Classification.NOT_DETERMINISTICALLY_CLASSIFIABLE,
    )
    assert evaluate_visual_reconciliation(value).outcome is VisualReconciliationOutcome.INSUFFICIENT
    assert evaluate_visual_reconciliation(replace(value, q10_classification=Q10Classification.CONDITIONAL_REASON)).outcome is VisualReconciliationOutcome.CONDITIONAL
    assert evaluate_visual_reconciliation(replace(value, q10_classification=Q10Classification.CONTRADICTION_REASON)).outcome is VisualReconciliationOutcome.CONTRADICTED


def test_q10_none_has_no_effect():
    decision = evaluate_visual_reconciliation(_input())
    assert decision.outcome is VisualReconciliationOutcome.CONFIRMED
    assert all(item.question_id != "Q10" for item in decision.reasons)


def test_reference_cannot_confirm_contradict_or_rescue_native_mcx():
    confirmed = evaluate_visual_reconciliation(_mcx_input())
    assert confirmed.outcome is VisualReconciliationOutcome.CONFIRMED
    conflict = evaluate_visual_reconciliation(
        _mcx_input(reference={"X1": "CONFLICTS_WITH_REFERENCE"})
    )
    assert conflict.outcome is VisualReconciliationOutcome.CONDITIONAL
    native_failure = evaluate_visual_reconciliation(
        _mcx_input(native={"M3": "FAILED_OR_RETURNED_THROUGH"})
    )
    assert native_failure.outcome is VisualReconciliationOutcome.CONTRADICTED
    partial = _mcx_input()
    partial = replace(
        partial,
        observations=tuple(
            _observation("M2", status=ObservationStatus.PARTIAL)
            if item.question_id == "M2"
            else item
            for item in partial.observations
        ),
    )
    assert evaluate_visual_reconciliation(partial).outcome is VisualReconciliationOutcome.INSUFFICIENT


def test_wrong_exact_mcx_contract_is_not_reconcilable():
    value = _mcx_input()
    value = replace(
        value,
        prerequisites=replace(
            value.prerequisites, native_mcx_contract_bound=False
        ),
    )
    decision = evaluate_visual_reconciliation(value)
    assert decision.outcome is VisualReconciliationOutcome.NOT_RECONCILABLE
    assert decision.reasons[0].reason_code == "NATIVE_MCX_CONTRACT_NOT_BOUND"


def test_natural_gas_hold_blocks_downstream_without_changing_analysis():
    decision = evaluate_visual_reconciliation(_mcx_input(held=True))
    assert decision.outcome is VisualReconciliationOutcome.CONFIRMED
    assert decision.downstream_eligibility is DownstreamEligibility.NOT_ELIGIBLE_FOR_WO10_EVALUATION


def test_record_round_trip_is_canonical_and_integrity_checked():
    record = create_reconciliation_record(
        _input(), created_at=datetime(2026, 9, 11, tzinfo=timezone.utc)
    )
    payload = artifact_bytes(record)
    assert record_from_bytes(payload) == record
    assert artifact_bytes(record_from_bytes(payload)) == payload
    with pytest.raises(ValueError, match="WO07F_RECORD"):
        record_from_bytes(payload.replace(b'"CONFIRMED"', b'"CONDITIONAL"'))


def test_same_exact_inputs_and_policy_have_same_input_identity_and_result():
    first = _input()
    second = _input()
    assert input_identity(first) == input_identity(second)
    assert evaluate_visual_reconciliation(first) == evaluate_visual_reconciliation(second)
