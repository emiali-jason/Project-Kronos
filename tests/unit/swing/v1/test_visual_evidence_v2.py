from dataclasses import fields, replace
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path

import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.integrations.openai_chart_analyst import (
    OpenAIVisualEvidenceV2Config,
    OpenAIVisualEvidenceV2Provider,
    _visual_v2_payload,
)
from kronos.swing.v1.chart_evidence import CHART_QUESTION_SET_V1_ID, FROZEN_CHART_QUESTION_SET_V1
from kronos.swing.v1.native_review import NativeReviewEvidenceStore, build_native_review_requirements
from kronos.swing.v1.native_readiness import _visual_completeness
from kronos.swing.v1.visual_evidence_v2 import (
    FROZEN_VISUAL_QUESTION_SET_V2,
    LocalVisualEvidenceV2Store,
    VISUAL_EVIDENCE_V2_AUTHORITY,
    VISUAL_QUESTION_SEMANTICS_V2,
    VISUAL_QUESTION_SET_V2_ID,
    VISUAL_QUESTION_SET_V2_VERSION,
    VisualEvidenceSubjectKind,
    VisualEvidenceV2Observation,
    VisualEvidenceV2Response,
    VisualLevelAvailability,
    VisualObservationStatus,
    VisualQuestionRouting,
    VisualQuestionV2,
    VisualTimeframe,
    build_visual_evidence_v2_request,
    validate_visual_evidence_v2_provider_value,
    visual_evidence_v2_provider_schema,
    visual_question_routing,
)
from tests.unit.swing.v1.test_native_review import _evidence_run
from tests.unit.swing.v1.test_native_review_mcx_reference import _run_with_probables


NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)
IMAGE = b"\x89PNG\r\n\x1a\nvisual-evidence-v2"


class _Transport:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def create_response(self, payload, *, timeout_seconds):  # type: ignore[no-untyped-def]
        del timeout_seconds
        self.calls.append(payload)
        return self.result


def _request(
    *,
    timeframe: VisualTimeframe = VisualTimeframe.DAILY,
    reference: bool = False,
    known: tuple[tuple[str, float, float | None], ...] = (),
):  # type: ignore[no-untyped-def]
    if reference:
        facts, run = _run_with_probables("GOLDM")
    else:
        facts, run, _ = _evidence_run()
    requirement = build_native_review_requirements(run, facts)[0]
    boundary = next(
        item.observation_boundary
        for item in requirement.thesis.timeframe_facts
        if item.timeframe.value == timeframe.value
    )
    return build_visual_evidence_v2_request(
        requirement,
        timeframe=timeframe,
        observation_boundary=boundary,
        chart_identity="COMEX:GC1!" if reference else requirement.canonical_instrument,
        content_type="image/png",
        original_image=IMAGE,
        request_timestamp=NOW,
        subject_kind=(
            VisualEvidenceSubjectKind.REFERENCE
            if reference else VisualEvidenceSubjectKind.NATIVE
        ),
        known_reference_levels=known,
    )


def _observation(
    request, question: VisualQuestionV2,  # type: ignore[no-untyped-def]
    *,
    status: VisualObservationStatus = VisualObservationStatus.NOT_VISIBLE,
    observation: str = "NO ADDITIONAL VISIBLE EVIDENCE",
    level: VisualLevelAvailability = VisualLevelAvailability.NOT_APPLICABLE,
    price: float | None = None,
    zone_low: float | None = None,
    zone_high: float | None = None,
    why: str | None = None,
):
    if question is VisualQuestionV2.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS:
        status = VisualObservationStatus.OBSERVED
        observation = "NONE"
    if dict(request.routing)[question] is VisualQuestionRouting.NO:
        status = VisualObservationStatus.NOT_APPLICABLE
        observation = "QUESTION NOT APPLICABLE"
    return VisualEvidenceV2Observation(
        question_id=question,
        timeframe=request.timeframe,
        observation_status=status,
        observation=observation,
        level_availability=level,
        price=price,
        zone_low=zone_low,
        zone_high=zone_high,
        visible_basis="DIRECTLY VISIBLE CHART EVIDENCE",
        source_chart_identity=request.chart_identity,
        source_chart_revision=request.chart_revision_sha256,
        confidence_in_extraction="HIGH",
        ambiguity_reason=(
            "CHART PARTIALLY UNREADABLE"
            if status in {VisualObservationStatus.PARTIAL, VisualObservationStatus.UNAVAILABLE, VisualObservationStatus.INVALID}
            else ""
        ),
        provenance=("FIXTURE", VISUAL_QUESTION_SET_V2_ID),
        why_not_covered_elsewhere=why,
    )


def _response(request, replacements=None):  # type: ignore[no-untyped-def]
    replacements = replacements or {}
    observations = tuple(
        replacements.get(question, _observation(request, question))
        for question in VisualQuestionV2
    )
    return VisualEvidenceV2Response(
        provider_identity="FIXTURE_VISUAL_PROVIDER",
        model_identity="fixture-model",
        request_timestamp=request.request_timestamp,
        native_run_identity=request.requirement.native_run_identity,
        native_assessment_sha256=request.requirement.thesis.native_assessment_sha256,
        native_canonical_instrument=request.requirement.canonical_instrument,
        subject_kind=request.subject_kind,
        subject_identity=request.subject_identity,
        reference_market=request.reference_market,
        reference_symbol=request.reference_symbol,
        timeframe=request.timeframe,
        observation_boundary=request.observation_boundary,
        chart_identity=request.chart_identity,
        chart_revision_sha256=request.chart_revision_sha256,
        observations=observations,
        source_provenance=("FIXTURE",),
    )


def _raw(response: VisualEvidenceV2Response) -> dict[str, object]:
    observations = []
    for item in response.observations:
        observations.append({
            "question_id": item.question_id.value,
            "observation_status": item.observation_status.value,
            "observation": item.observation,
            "level_availability": item.level_availability.value,
            "price": item.price,
            "zone_low": item.zone_low,
            "zone_high": item.zone_high,
            "visible_basis": item.visible_basis,
            "confidence_in_extraction": item.confidence_in_extraction,
            "ambiguity_reason": item.ambiguity_reason,
            "why_not_covered_elsewhere": item.why_not_covered_elsewhere,
        })
    return {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps({"observations": observations})}
    ]}]}


def _provider_value(response: VisualEvidenceV2Response) -> dict[str, object]:
    raw = _raw(response)
    return json.loads(raw["output"][0]["content"][0]["text"])


def test_v1_is_unchanged_and_v2_has_exact_frozen_identity_and_questions() -> None:
    assert CHART_QUESTION_SET_V1_ID == "SWING-V1-CHART-QUESTION-SET-V1"
    assert len(FROZEN_CHART_QUESTION_SET_V1) == 16
    assert VISUAL_QUESTION_SET_V2_ID == "SWING-V1-VISUAL-QUESTION-SET-V2"
    assert VISUAL_QUESTION_SET_V2_VERSION == "2.0"
    assert tuple(item.value for item in FROZEN_VISUAL_QUESTION_SET_V2) == (
        "VISUAL_CHART_VALIDATION", "CPR_CONTEXT", "VISUAL_SUPPORT_RESISTANCE_GAP",
        "PDH_PDL_REFERENCE_CONTEXT", "PRICE_ACTION_QUALITY", "VISUAL_OBSTACLE_EVIDENCE",
        "MATURITY_AND_CHASE_CONTEXT", "PINE_VISIBLE_EVIDENCE", "VISUAL_CONFLUENCE",
        "VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS",
    )
    assert set(VISUAL_QUESTION_SEMANTICS_V2) == set(VisualQuestionV2)


def test_exact_timeframe_routing_and_strict_provider_schema() -> None:
    assert dict(visual_question_routing(VisualTimeframe.WEEKLY))[VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT] is VisualQuestionRouting.NO
    assert dict(visual_question_routing(VisualTimeframe.DAILY))[VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT] is VisualQuestionRouting.USUALLY_NO
    assert dict(visual_question_routing(VisualTimeframe.FOUR_HOUR))[VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT] is VisualQuestionRouting.IF_RELEVANT
    assert dict(visual_question_routing(VisualTimeframe.ONE_HOUR))[VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT] is VisualQuestionRouting.YES
    assert all(len(visual_question_routing(item)) == 10 for item in VisualTimeframe)
    schema = visual_evidence_v2_provider_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["observations"]["minItems"] == 10
    assert '"pattern"' not in json.dumps(schema)


@pytest.mark.parametrize(
    ("index", "observation", "why", "valid"),
    (
        (0, "VISIBLE", "EXTRA", False),
        (0, "VISIBLE", None, True),
        (9, "NONE", None, True),
        # Advanced negative-lookahead regex is intentionally not sent to the
        # provider; this exact semantic remains frozen in the domain validator.
        (9, "NONE", "EXTRA", True),
        (9, "VISIBLE EVENT", None, False),
        (9, "VISIBLE EVENT", "NOT REPRESENTED BY Q1-Q9", True),
    ),
)
def test_provider_schema_encodes_frozen_q10_reason_variants(
    index: int,
    observation: str,
    why: str | None,
    valid: bool,
) -> None:
    value = _provider_value(_response(_request()))
    value["observations"][index]["observation"] = observation
    value["observations"][index]["why_not_covered_elsewhere"] = why
    if valid:
        validate_visual_evidence_v2_provider_value(value)
    else:
        with pytest.raises(ValueError, match="PROVIDER_SCHEMA_VALUE_INVALID"):
            validate_visual_evidence_v2_provider_value(value)


@pytest.mark.parametrize(
    "changes",
    (
        {
            "observation_status": "OBSERVED",
            "level_availability": "AVAILABLE",
            "price": None,
            "zone_low": None,
            "zone_high": None,
        },
        {
            "observation_status": "OBSERVED",
            "level_availability": "AVAILABLE",
            "price": 100.0,
            "zone_low": 99.0,
            "zone_high": 101.0,
        },
        {
            "observation_status": "OBSERVED",
            "level_availability": "LEVEL_UNAVAILABLE",
            "price": 100.0,
        },
        {
            "observation_status": "PARTIAL",
            "level_availability": "LEVEL_UNAVAILABLE",
            "ambiguity_reason": "",
        },
    ),
)
def test_provider_schema_rejects_known_numeric_and_ambiguity_invariant_gaps(
    changes: dict[str, object],
) -> None:
    value = _provider_value(_response(_request()))
    value["observations"][0].update(changes)
    with pytest.raises(ValueError, match="PROVIDER_SCHEMA_VALUE_INVALID"):
        validate_visual_evidence_v2_provider_value(value)


def test_request_injects_only_factual_native_context_and_preserves_binding() -> None:
    request = _request()
    facts = request.deterministic_context.timeframe_facts
    assert request.requirement.thesis.direction.value in {"LONG", "SHORT"}
    assert facts.close >= 0
    assert facts.sma20 is not None
    assert facts.sma50 is not None
    assert type(facts.pivots) is tuple
    assert not hasattr(request, "readiness")
    assert not hasattr(request, "accept")
    assert not hasattr(request, "risk_reward")


@pytest.mark.parametrize("status", (VisualObservationStatus.PARTIAL, VisualObservationStatus.INVALID))
def test_unreadable_chart_is_bounded_and_requires_ambiguity(status) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    item = _observation(
        request, VisualQuestionV2.VISUAL_CHART_VALIDATION,
        status=status, observation="CHART NOT RELIABLY READABLE",
        level=VisualLevelAvailability.LEVEL_UNAVAILABLE,
    )
    assert item.ambiguity_reason
    with pytest.raises(ValueError, match="OBSERVATION_INVALID"):
        replace(item, ambiguity_reason="")


def test_unreadable_numeric_level_is_level_unavailable_and_exact_zone_is_preserved() -> None:
    request = _request()
    unreadable = _observation(
        request, VisualQuestionV2.CPR_CONTEXT,
        status=VisualObservationStatus.OBSERVED, observation="CPR VISIBLE; VALUE UNREADABLE",
        level=VisualLevelAvailability.LEVEL_UNAVAILABLE,
    )
    zone = _observation(
        request, VisualQuestionV2.VISUAL_CONFLUENCE,
        status=VisualObservationStatus.OBSERVED, observation="VISIBLE CLUSTER",
        level=VisualLevelAvailability.AVAILABLE, zone_low=100.0, zone_high=101.0,
    )
    assert unreadable.price is None
    assert (zone.zone_low, zone.zone_high) == (100.0, 101.0)


def test_q3_duplicate_is_rejected_distinct_gap_is_allowed_and_empty_is_valid() -> None:
    request = _request(known=(("DETERMINISTIC_RESISTANCE", 100.0, None),))
    duplicate = _observation(
        request, VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP,
        status=VisualObservationStatus.OBSERVED, observation="VISIBLE RESISTANCE",
        level=VisualLevelAvailability.AVAILABLE, price=100.0,
    )
    with pytest.raises(ValueError, match="DUPLICATES"):
        _response(request, {VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP: duplicate}).validate_binding(request)

    distinct = replace(duplicate, price=110.0)
    _response(request, {VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP: distinct}).validate_binding(request)
    _response(request).validate_binding(request)


@pytest.mark.parametrize(
    ("price", "zone_low", "zone_high"),
    ((110.0, None, None), (None, 109.0, 111.0)),
)
def test_q3_positive_point_or_zone_is_valid(
    price: float | None, zone_low: float | None, zone_high: float | None,
) -> None:
    request = _request()
    finding = _observation(
        request,
        VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP,
        status=VisualObservationStatus.OBSERVED,
        observation="ADDITIONAL MATERIAL SUPPORT RESISTANCE",
        level=VisualLevelAvailability.AVAILABLE,
        price=price,
        zone_low=zone_low,
        zone_high=zone_high,
    )
    _response(
        request,
        {VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP: finding},
    ).validate_binding(request)


def test_q3_confident_negative_is_valid_and_complete() -> None:
    requests = tuple(_request(timeframe=timeframe) for timeframe in VisualTimeframe)
    responses = []
    for request in requests:
        observed = {
            question: _observation(
                request,
                question,
                status=VisualObservationStatus.OBSERVED,
                observation=(
                    "NONE"
                    if question is VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP
                    else "VISIBLE FACT"
                ),
                level=VisualLevelAvailability.NOT_APPLICABLE,
            )
            for question in VisualQuestionV2
        }
        response = _response(request, observed)
        response.validate_binding(request)
        responses.append(response)
    requirement = requests[0].requirement
    assert _visual_completeness(requirement, tuple(responses)) == (False, False)


def test_q3_not_visible_is_valid_but_incomplete_when_required() -> None:
    requests = tuple(_request(timeframe=timeframe) for timeframe in VisualTimeframe)
    responses = []
    for request in requests:
        observed = {
            question: _observation(
                request,
                question,
                status=VisualObservationStatus.OBSERVED,
                observation="VISIBLE FACT",
                level=VisualLevelAvailability.NOT_APPLICABLE,
            )
            for question in VisualQuestionV2
        }
        if request.timeframe is VisualTimeframe.DAILY:
            observed[VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP] = _observation(
                request,
                VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP,
                status=VisualObservationStatus.NOT_VISIBLE,
                observation="NOT RELIABLY DETERMINABLE",
                level=VisualLevelAvailability.NOT_APPLICABLE,
            )
        response = _response(request, observed)
        response.validate_binding(request)
        responses.append(response)
    assert _visual_completeness(requests[0].requirement, tuple(responses)) == (
        False,
        True,
    )


@pytest.mark.parametrize(
    ("price", "zone_low", "zone_high"),
    ((110.0, None, None), (None, 109.0, 111.0)),
)
def test_q3_confident_negative_rejects_numeric_level(
    price: float | None, zone_low: float | None, zone_high: float | None,
) -> None:
    request = _request()
    with pytest.raises(ValueError, match="VISUAL_V2_OBSERVATION_INVALID"):
        _observation(
            request,
            VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP,
            status=VisualObservationStatus.OBSERVED,
            observation="NONE",
            level=VisualLevelAvailability.NOT_APPLICABLE,
            price=price,
            zone_low=zone_low,
            zone_high=zone_high,
        )


def test_q10_none_is_success_and_material_escape_hatch_requires_reason() -> None:
    request = _request()
    result = _response(request)
    q10 = result.observations[-1]
    assert q10.observation == "NONE"
    result.validate_binding(request)
    with pytest.raises(ValueError, match="OBSERVATION_INVALID"):
        replace(q10, why_not_covered_elsewhere="EXTRA")
    with pytest.raises(ValueError, match="OBSERVATION_INVALID"):
        replace(q10, observation="VISIBLE EVENT", why_not_covered_elsewhere=None)


@pytest.mark.parametrize(
    "consequence",
    ("DISCARD", "MATERIAL BARRIER", "PATH BLOCKED", "BUY", "RISK REWARD"),
)
def test_consequence_language_is_rejected(consequence: str) -> None:
    request = _request()
    with pytest.raises(ValueError, match="OBSERVATION_INVALID"):
        _observation(
            request, VisualQuestionV2.MATURITY_AND_CHASE_CONTEXT,
            status=VisualObservationStatus.OBSERVED,
            observation=f"VISIBLY EXTENDED THEREFORE {consequence}",
        )


def test_output_shape_has_no_analytical_or_downstream_authority() -> None:
    names = {item.name for item in fields(VisualEvidenceV2Response)}
    prohibited = {
        "native_direction", "weekly_state", "daily_state", "four_hour_state",
        "one_hour_state", "probable_state", "opportunity_identity", "contradiction",
        "material_barrier", "clear_air", "readiness", "accept", "wait", "discard",
        "next_required_event", "entry", "entry_zone", "stop", "invalidation",
        "target", "risk_reward", "position_size", "execution_state", "broker_state",
    }
    assert names.isdisjoint(prohibited)
    assert VISUAL_EVIDENCE_V2_AUTHORITY == "OBSERVATION_ONLY_NO_ANALYTICAL_CONSEQUENCE"


@pytest.mark.parametrize("field", ("native_run_identity", "native_assessment_sha256", "native_canonical_instrument", "timeframe", "chart_revision_sha256"))
def test_wrong_native_or_chart_binding_fails_closed(field: str) -> None:
    request = _request()
    response = _response(request)
    changes = {
        "native_run_identity": "SWING-RUN-" + "F" * 32,
        "native_assessment_sha256": "f" * 64,
        "native_canonical_instrument": "WRONG",
        "timeframe": VisualTimeframe.ONE_HOUR,
        "chart_revision_sha256": "f" * 64,
    }
    with pytest.raises(ValueError, match="(?:BINDING|RESPONSE)_INVALID"):
        replace(response, **{field: changes[field]}).validate_binding(request)


def test_mcx_reference_preserves_native_thesis_and_exact_reference_pairing() -> None:
    request = _request(reference=True)
    response = _response(request)
    response.validate_binding(request)
    assert request.subject_identity == "COMEX Gold"
    assert request.reference_market == "COMEX"
    assert request.reference_symbol == "COMEX:GC1!"
    assert response.native_canonical_instrument == "GOLDM"
    assert response.native_assessment_sha256 == request.requirement.thesis.native_assessment_sha256
    assert not hasattr(response, "native_direction")


def test_persistence_is_immutable_integrity_checked_and_restart_recoverable(tmp_path: Path) -> None:
    request = _request()
    response = _response(request)
    store = LocalVisualEvidenceV2Store(tmp_path)
    path = store.retain(request, response)
    assert store.load(request) == response
    assert store.load_for_requirements((request.requirement,)) == (response,)
    with pytest.raises(ValueError, match="IMMUTABLE"):
        store.retain(request, replace(response, model_identity="changed"))
    payload = json.loads(path.read_text())
    payload["evidence_sha256"] = "0" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="INTEGRITY"):
        store.load(request)


def test_native_review_workflow_retains_and_restores_visual_evidence(tmp_path: Path) -> None:
    facts, run, _ = _evidence_run()
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    prepared = workflow.prepare(run, facts)
    request = _request()
    assert request.requirement == prepared.requirements[0]
    response = _response(request)
    workflow.ingest_visual_v2(request, response)
    assert workflow.snapshot().visual_v2_results == (response,)
    restored = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native")).restore(run, facts)
    assert restored.visual_v2_results == (response,)


def test_existing_openai_transport_is_reused_with_neutral_strict_prompt() -> None:
    request = _request()
    expected = _response(request)
    transport = _Transport(_raw(expected))
    provider = OpenAIVisualEvidenceV2Provider(
        OpenAIVisualEvidenceV2Config(enabled=True, model_identity="gpt-test"),
        transport=transport,
    )
    result = provider.analyze(request)
    assert tuple(item.question_id for item in result.observations) == tuple(
        item.question_id for item in expected.observations
    )
    assert tuple(item.observation_status for item in result.observations) == tuple(
        item.observation_status for item in expected.observations
    )
    assert provider.request_count == 1
    payload = transport.calls[0]
    text = json.dumps(payload)
    assert VISUAL_QUESTION_SET_V2_ID in text
    assert "Do not determine validity" in text
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert "api_key" not in text.lower()


def test_payload_injects_facts_but_not_downstream_conclusions() -> None:
    request = _request()
    payload = _visual_v2_payload(request, "gpt-test")
    serialized = json.dumps(payload)
    assert "Completed close=" in serialized
    assert "Deterministic pivots already represented" in serialized
    assert request.requirement.native_run_identity not in serialized
    assert "READY" not in serialized
    assert "good R:R" not in serialized
