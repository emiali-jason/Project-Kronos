import copy
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from kronos.application.swing_visual_v3 import (
    SwingVisualV3ReviewCycle,
    chart_inputs_from_requirement,
)
from kronos.swing.v1.native_readiness import EvidenceCompleteness
from kronos.swing.v1.native_readiness_v3 import (
    NativeLayer2ReadinessV3Store,
    build_native_layer2_conditions_v3,
    evaluate_v3_evidence_gate,
)
from kronos.swing.v1.native_review import (
    NativeLayer2EvidenceState,
    build_native_review_requirements,
)
from kronos.swing.v1.reference_facts import (
    SwingReferenceAvailability,
    SwingReferenceChartTimeframe,
    SwingReferencePeriodType,
    SwingReferenceUnavailableReason,
    machine_fact_integrity_sha256,
)
from kronos.swing.v1.visual_evidence_v2 import (
    VISUAL_QUESTION_SET_V2_ID,
    VisualObservationStatus,
    VisualTimeframe,
)
from kronos.swing.v1.visual_evidence_v3 import (
    FROZEN_VISUAL_QUESTION_SET_V3,
    LocalVisualEvidenceV3Store,
    VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_VERSION,
    VisualClusteringState,
    VisualComponentType,
    VisualEvidenceV3Response,
    VisualInteraction,
    VisualPriceRelationship,
    VisualQuestionV3,
    VisualReferenceRelationship,
    VisualStructurePresence,
    VisualV3ClusteringObservation,
    VisualV3CprObservation,
    VisualV3LevelObservation,
    VisualV3QualitativeObservation,
    VisualV3ReferenceObservation,
    build_visual_evidence_v3_request,
    visual_evidence_v3_answer_contract,
)
from tests.unit.swing.v1.test_native_review import _evidence_run, _layer2
from tests.unit.swing.v1.test_visual_evidence_v2 import (
    _request as _v2_request,
    _response as _v2_response,
)


NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _context():  # type: ignore[no-untyped-def]
    facts, run, _ = _evidence_run()
    return facts, build_native_review_requirements(run, facts)[0]


def _request(timeframe: VisualTimeframe = VisualTimeframe.DAILY):  # type: ignore[no-untyped-def]
    facts, requirement = _context()
    boundary = next(
        item.observation_boundary
        for item in requirement.thesis.timeframe_facts
        if item.timeframe.value == timeframe.value
    )
    image = f"controlled-{timeframe.value}".encode()
    return build_visual_evidence_v3_request(
        requirement,
        facts,
        timeframe=timeframe,
        observation_boundary=boundary,
        chart_identity=requirement.canonical_instrument,
        content_type="image/png",
        original_image=image,
        request_timestamp=NOW,
    )


def _base(request, question):  # type: ignore[no-untyped-def]
    return {
        "question_id": question,
        "timeframe": request.timeframe,
        "observation_status": VisualObservationStatus.OBSERVED,
        "visible_basis": "VISIBLE CONTROLLED CHART FACT",
        "confidence_in_extraction": "HIGH",
        "ambiguity_reason": "",
        "source_chart_identity": request.chart_identity,
        "source_chart_revision": request.chart_revision_sha256,
    }


def _observations(request, *, q9=VisualClusteringState.CLUSTERED):  # type: ignore[no-untyped-def]
    values = []
    for question in FROZEN_VISUAL_QUESTION_SET_V3:
        base = _base(request, question)
        if question is VisualQuestionV3.CPR_VISUAL_RELATIONSHIP:
            item = VisualV3CprObservation(
                **base,
                presence=VisualStructurePresence.PRESENT,
                price_relationship=VisualPriceRelationship.ABOVE,
                interaction=VisualInteraction.HOLD,
            )
        elif question is VisualQuestionV3.GOVERNED_REFERENCE_VISUAL_CONTEXT:
            item = VisualV3ReferenceObservation(
                **base,
                presence=VisualStructurePresence.PRESENT,
                relationship=VisualReferenceRelationship.ABOVE_REFERENCE_RANGE,
                interaction=VisualInteraction.RECLAIM,
            )
        elif question is VisualQuestionV3.VISUAL_COMPONENT_CLUSTERING:
            components = (
                (VisualComponentType.CPR, VisualComponentType.SMA20)
                if q9 is VisualClusteringState.CLUSTERED
                else (VisualComponentType.CPR,)
                if q9 is VisualClusteringState.PARTIAL_COMPONENT_IDENTITY
                else ()
            )
            item = VisualV3ClusteringObservation(
                **base, clustering=q9, components=components
            )
        elif question in {
            VisualQuestionV3.VISUAL_SUPPORT_RESISTANCE_GAP,
            VisualQuestionV3.VISUAL_OBSTACLE_EVIDENCE,
        }:
            item = VisualV3LevelObservation(
                **base, finding="VISIBLE LEVEL", point_price=101.0
            )
        else:
            finding = (
                "NONE"
                if question
                is VisualQuestionV3.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS
                else "VISIBLE FACT"
            )
            item = VisualV3QualitativeObservation(**base, finding=finding)
        values.append(item)
    return tuple(values)


def _response(request, *, q9=VisualClusteringState.CLUSTERED):  # type: ignore[no-untyped-def]
    return VisualEvidenceV3Response(
        provider_identity="CONTROLLED_FIXTURE",
        model_identity="NO_MODEL_CALL",
        request_timestamp=request.request_timestamp,
        native_run_identity=request.requirement.native_run_identity,
        native_assessment_sha256=request.requirement.thesis.native_assessment_sha256,
        native_canonical_instrument=request.requirement.canonical_instrument,
        timeframe=request.timeframe,
        observation_boundary=request.observation_boundary,
        analysis_boundary=request.analysis_boundary,
        chart_identity=request.chart_identity,
        chart_revision_sha256=request.chart_revision_sha256,
        machine_fact_integrity_sha256=request.machine_fact.integrity_sha256,
        observations=_observations(request, q9=q9),
        source_provenance=("CONTROLLED_V3_FIXTURE",),
    )


def _visual():  # type: ignore[no-untyped-def]
    return tuple(_response(_request(item)) for item in VisualTimeframe)


def _visual_for(facts, requirement):  # type: ignore[no-untyped-def]
    values = []
    for timeframe in VisualTimeframe:
        boundary = next(
            item.observation_boundary
            for item in requirement.thesis.timeframe_facts
            if item.timeframe.value == timeframe.value
        )
        image = f"changed-{timeframe.value}".encode()
        request = build_visual_evidence_v3_request(
            requirement,
            facts,
            timeframe=timeframe,
            observation_boundary=boundary,
            chart_identity=requirement.canonical_instrument,
            content_type="image/png",
            original_image=image,
            request_timestamp=NOW,
        )
        values.append(_response(request))
    return tuple(values)


def test_v3_is_explicit_and_does_not_redefine_v2() -> None:
    assert VISUAL_QUESTION_SET_V3_ID == "SWING-V1-VISUAL-QUESTION-SET-V3"
    assert VISUAL_QUESTION_SET_V3_VERSION == "3.0"
    assert VISUAL_QUESTION_SET_V2_ID != VISUAL_QUESTION_SET_V3_ID
    assert visual_evidence_v3_answer_contract()["schema"] == VISUAL_EVIDENCE_V3_ANSWER_SCHEMA


def test_question_pack_context_is_visual_only_and_never_discloses_machine_values() -> None:
    request = _request()
    context = request.analyst_context()
    assert "machine_fact" not in context
    assert "machine_values" not in context
    assert all(
        key not in context
        for key in ("reference_high", "reference_low", "cp", "bc", "tc")
    )
    assert context["authority"] == "INDEPENDENT_VISUAL_OBSERVATION_ONLY"


def test_machine_owns_cpr_and_visual_cannot_manufacture_it() -> None:
    request = _request()
    assert request.machine_fact.cp is not None
    q2 = _observations(request)[1]
    assert isinstance(q2, VisualV3CprObservation)
    assert not any(hasattr(q2, name) for name in ("cp", "bc", "tc"))
    assert not any(
        name in VisualV3CprObservation.__dataclass_fields__
        for name in ("cp", "bc", "tc")
    )


@pytest.mark.parametrize("relationship", tuple(VisualPriceRelationship))
def test_q2_supports_bounded_relationships(relationship: VisualPriceRelationship) -> None:
    request = _request()
    presence = (
        VisualStructurePresence.NOT_IDENTIFIABLE
        if relationship is VisualPriceRelationship.NOT_OBSERVABLE
        else VisualStructurePresence.PRESENT
    )
    result = VisualV3CprObservation(
        **_base(request, VisualQuestionV3.CPR_VISUAL_RELATIONSHIP),
        presence=presence,
        price_relationship=relationship,
        interaction=(
            VisualInteraction.NOT_OBSERVABLE
            if relationship is VisualPriceRelationship.NOT_OBSERVABLE
            else VisualInteraction.NONE
        ),
    )
    assert result.price_relationship is relationship


@pytest.mark.parametrize("interaction", tuple(VisualInteraction))
def test_q2_supports_interaction_and_no_forced_interaction(interaction: VisualInteraction) -> None:
    request = _request()
    result = VisualV3CprObservation(
        **_base(request, VisualQuestionV3.CPR_VISUAL_RELATIONSHIP),
        presence=(
            VisualStructurePresence.NOT_IDENTIFIABLE
            if interaction is VisualInteraction.NOT_OBSERVABLE
            else VisualStructurePresence.PRESENT
        ),
        price_relationship=(
            VisualPriceRelationship.NOT_OBSERVABLE
            if interaction is VisualInteraction.NOT_OBSERVABLE
            else VisualPriceRelationship.INSIDE
        ),
        interaction=interaction,
    )
    assert result.interaction is interaction


@pytest.mark.parametrize("status", (VisualObservationStatus.UNAVAILABLE, VisualObservationStatus.INVALID))
def test_q2_unavailable_or_invalid_remains_fail_closed(status: VisualObservationStatus) -> None:
    request = _request()
    base = _base(request, VisualQuestionV3.CPR_VISUAL_RELATIONSHIP)
    base.update(observation_status=status, ambiguity_reason="CHART DOES NOT ESTABLISH CPR")
    observation = VisualV3CprObservation(
        **base,
        presence=VisualStructurePresence.NOT_IDENTIFIABLE,
        price_relationship=VisualPriceRelationship.NOT_OBSERVABLE,
        interaction=VisualInteraction.NOT_OBSERVABLE,
    )
    observations = list(_observations(request))
    observations[1] = observation
    response = replace(_response(request), observations=tuple(observations))
    facts, requirement = _context()
    gate = evaluate_v3_evidence_gate(requirement, facts, (response,))
    assert gate.incomplete or gate.invalid


@pytest.mark.parametrize(
    ("timeframe", "expected"),
    (
        (VisualTimeframe.WEEKLY, SwingReferencePeriodType.PREVIOUS_MONTH),
        (VisualTimeframe.DAILY, SwingReferencePeriodType.PREVIOUS_MONTH),
        (VisualTimeframe.FOUR_HOUR, SwingReferencePeriodType.PREVIOUS_MONTH),
        (VisualTimeframe.ONE_HOUR, SwingReferencePeriodType.PREVIOUS_WEEK),
    ),
)
def test_q4_machine_reference_period_routing_is_exact(
    timeframe: VisualTimeframe, expected: SwingReferencePeriodType
) -> None:
    request = _request(timeframe)
    assert request.machine_fact.reference_period_type is expected
    q4 = _observations(request)[3]
    assert isinstance(q4, VisualV3ReferenceObservation)
    assert not any(hasattr(q4, item) for item in ("reference_high", "reference_low"))


def test_q4_not_identifiable_requires_no_numerical_transcription() -> None:
    request = _request(VisualTimeframe.ONE_HOUR)
    result = VisualV3ReferenceObservation(
        **_base(request, VisualQuestionV3.GOVERNED_REFERENCE_VISUAL_CONTEXT),
        presence=VisualStructurePresence.NOT_IDENTIFIABLE,
        relationship=VisualReferenceRelationship.NOT_OBSERVABLE,
        interaction=VisualInteraction.NOT_OBSERVABLE,
    )
    assert result.presence is VisualStructurePresence.NOT_IDENTIFIABLE


@pytest.mark.parametrize(
    ("state", "components"),
    (
        (VisualClusteringState.CLUSTERED, (VisualComponentType.CPR, VisualComponentType.SMA20)),
        (VisualClusteringState.NOT_CLUSTERED, ()),
        (VisualClusteringState.PARTIAL_COMPONENT_IDENTITY, (VisualComponentType.CPR,)),
    ),
)
def test_q9_is_component_based_without_numeric_zone(
    state: VisualClusteringState, components: tuple[VisualComponentType, ...]
) -> None:
    request = _request()
    result = VisualV3ClusteringObservation(
        **_base(request, VisualQuestionV3.VISUAL_COMPONENT_CLUSTERING),
        clustering=state,
        components=components,
    )
    assert result.clustering is state
    assert not any(
        name in VisualV3ClusteringObservation.__dataclass_fields__
        for name in ("zone_low", "zone_high", "score", "threshold")
    )


def test_answer_contract_removes_numeric_q2_q4_q9_and_invented_confluence() -> None:
    contract = visual_evidence_v3_answer_contract()
    forbidden = contract["forbidden_numeric_transcription"]
    assert {"CP", "BC", "TC", "reference_high", "reference_low"}.issubset(forbidden)
    assert {"confluence_zone_low", "confluence_zone_high"}.issubset(forbidden)
    assert "threshold" not in repr(contract).lower()


def test_wrong_run_timeframe_and_integrity_machine_facts_are_rejected() -> None:
    request = _request()
    for attribute, value in (
        ("run_identity", "SWING-RUN-FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"),
        ("chart_timeframe", SwingReferenceChartTimeframe.ONE_HOUR),
        ("integrity_sha256", "0" * 64),
    ):
        fact = copy.deepcopy(request.machine_fact)
        object.__setattr__(fact, attribute, value)
        with pytest.raises(ValueError, match="VISUAL_V3_REQUEST_BINDING_INVALID"):
            replace(request, machine_fact=fact)


def test_machine_complete_does_not_complete_visual_and_visual_does_not_complete_machine() -> None:
    facts, requirement = _context()
    machine_only = evaluate_v3_evidence_gate(requirement, facts, ())
    assert machine_only.incomplete

    instrument = facts.instrument(requirement.canonical_instrument)
    unavailable = copy.deepcopy(instrument.reference_facts[0])
    for field in ("reference_open", "reference_high", "reference_low", "reference_close", "cp", "bc", "tc"):
        object.__setattr__(unavailable, field, None)
    object.__setattr__(unavailable, "availability", SwingReferenceAvailability.UNAVAILABLE)
    object.__setattr__(unavailable, "unavailable_reason", SwingReferenceUnavailableReason.SOURCE_FACT_UNAVAILABLE)
    object.__setattr__(unavailable, "integrity_sha256", machine_fact_integrity_sha256(unavailable))
    changed_instrument = replace(
        instrument,
        reference_facts=(unavailable, *instrument.reference_facts[1:]),
    )
    changed = replace(
        facts,
        instruments=tuple(
            changed_instrument if item is instrument else item
            for item in facts.instruments
        ),
    )
    visual_only = evaluate_v3_evidence_gate(
        requirement, changed, _visual_for(changed, requirement)
    )
    assert visual_only.incomplete
    assert not visual_only.invalid


def test_complete_v3_evidence_satisfies_only_evidence_completeness() -> None:
    facts, requirement = _context()
    layer2 = _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    conditions = build_native_layer2_conditions_v3(
        requirement, layer2, facts, _visual()
    )
    assert conditions.evidence_completeness is EvidenceCompleteness.COMPLETE
    assert evaluate_v3_evidence_gate(requirement, facts, _visual()).incomplete is False


def test_q9_valid_negative_is_complete_and_not_a_false_blocker() -> None:
    facts, requirement = _context()
    visual = tuple(
        _response(_request(item), q9=VisualClusteringState.NOT_CLUSTERED)
        for item in VisualTimeframe
    )
    assert evaluate_v3_evidence_gate(requirement, facts, visual).incomplete is False


def test_q3_valid_negative_and_q10_null_rule_remain_governed() -> None:
    request = _request()
    observations = list(_observations(request))
    observations[2] = VisualV3QualitativeObservation(
        **_base(request, VisualQuestionV3.VISUAL_SUPPORT_RESISTANCE_GAP),
        finding="NONE",
    )
    response = replace(_response(request), observations=tuple(observations))
    assert response.observations[2].finding == "NONE"
    q10 = response.observations[-1]
    assert isinstance(q10, VisualV3QualitativeObservation)
    assert q10.finding == "NONE"
    assert q10.why_not_covered_elsewhere is None
    with pytest.raises(ValueError, match="QUALITATIVE_OBSERVATION_INVALID"):
        replace(q10, finding="NEW FACT", why_not_covered_elsewhere=None)


def test_v3_store_and_application_cycle_are_isolated_and_immutable(tmp_path: Path) -> None:
    facts, requirement = _context()
    evidence = LocalVisualEvidenceV3Store((tmp_path / "v3").resolve())
    readiness = NativeLayer2ReadinessV3Store((tmp_path / "readiness").resolve())
    cycle = SwingVisualV3ReviewCycle(evidence, readiness)
    charts = chart_inputs_from_requirement(
        requirement,
        chart_identity=requirement.canonical_instrument,
        content_type="image/png",
        images=tuple(f"cycle-{item.value}".encode() for item in VisualTimeframe),
    )
    requests = cycle.prepare(requirement, facts, charts, request_timestamp=NOW)
    responses = tuple(_response(request) for request in requests)
    for request, response in zip(requests, responses, strict=True):
        cycle.retain(request, response)
        cycle.retain(request, response)
    record = cycle.complete(
        requirement,
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS),
        facts,
        responses,
        created_at=NOW,
    )
    assert len(tuple((tmp_path / "v3").rglob("*.json"))) == 4
    assert len(tuple((tmp_path / "readiness").rglob("*.json"))) == 1
    assert record.question_set_identity == VISUAL_QUESTION_SET_V3_ID
    restored = LocalVisualEvidenceV3Store((tmp_path / "v3").resolve())
    assert restored.load_for_request(requests[0]) == (responses[0],)


def test_v2_answer_identity_cannot_satisfy_v3_and_v3_is_not_v2() -> None:
    response = _response(_request())
    with pytest.raises(ValueError, match="VISUAL_V3_RESPONSE_INVALID"):
        replace(response, question_set_identity=VISUAL_QUESTION_SET_V2_ID)
    assert response.question_set_identity != VISUAL_QUESTION_SET_V2_ID
    historical_v2 = _v2_response(_v2_request())
    with pytest.raises(ValueError, match="VISUAL_V2_RESPONSE_INVALID"):
        replace(historical_v2, question_set_identity=VISUAL_QUESTION_SET_V3_ID)


def test_q3_and_q6_preserve_individual_visible_level_intent_only() -> None:
    request = _request()
    point = VisualV3LevelObservation(
        **_base(request, VisualQuestionV3.VISUAL_SUPPORT_RESISTANCE_GAP),
        finding="VISIBLE SUPPORT",
        point_price=99.5,
    )
    zone = VisualV3LevelObservation(
        **_base(request, VisualQuestionV3.VISUAL_OBSTACLE_EVIDENCE),
        finding="VISIBLE OBSTACLE",
        zone_low=103.0,
        zone_high=104.0,
    )
    assert point.point_price == 99.5
    assert zone.zone_low == 103.0
    with pytest.raises(ValueError, match="LEVEL_OBSERVATION_INVALID"):
        replace(point, question_id=VisualQuestionV3.CPR_VISUAL_RELATIONSHIP)
