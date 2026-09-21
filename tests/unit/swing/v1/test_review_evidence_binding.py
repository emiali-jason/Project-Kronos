"""WO-07 Slice 1: immutable contracts and observational state projection."""
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import json

import pytest

from kronos.swing.v1.review_evidence_binding import (
    ReviewAcceptanceReceipt, ReviewEvidenceBinding, ReviewEvidenceError,
    ReviewEvidenceState, ReviewMutationPrecondition, PRECONDITION_FIELDS,
    canonical, project_review_evidence_state, strict_json, timestamp,
)


def binding_value():
    return {
        "market": "NSE", "analytical_run_identity": "SWING-RUN-" + "A" * 32,
        "committed_run_manifest_identity": "MANIFEST-A", "candidate_identity": "CANDIDATE-A",
        "canonical_instrument": "CANBK", "native_assessment_sha256": "a" * 64,
        "review_cycle_identity": "CYCLE-A", "request_identity": "REQUEST-A",
        "request_timestamp": "2026-09-15T00:00:00.000000Z",
        "review_pack_identity": "PACK-A", "review_pack_sha256": "b" * 64,
    }


def receipt_body():
    return {
        "scope": "NATIVE_REVIEW", "binding": binding_value(),
        "contracts": [{"role": "NATIVE_NSE", "question_contract_identity": "QUESTIONS",
            "question_contract_version": "3.1", "answer_contract_identity": "ANSWERS",
            "answer_contract_version": "3.1", "structured_evidence_schema": "EVIDENCE",
            "structured_evidence_version": "3.1"}],
        "chart_revisions": [{"role": "NATIVE_NSE", "subject_identity": "CANBK",
            "reference_market": None, "reference_symbol": None,
            "timeframe_or_panel_identity": "1D", "revision_identity": "REV-A",
            "sha256": "c" * 64, "retained_relative_path": "charts/" + "c" * 64 + ".png"}],
        "answer": {"answer_identity": "ANSWER-A", "pdf_sha256": "d" * 64,
            "byte_length": 1024, "retained_relative_path": "answers/" + "d" * 64 + ".pdf"},
        "structured_evidence": [{"role": "NATIVE_NSE", "subject_identity": "CANBK",
            "timeframe_or_family_identity": "1D", "schema": "EVIDENCE", "version": "3.1",
            "sha256": "e" * 64, "retained_relative_path": "structured/" + "e" * 64 + ".json"}],
        "accepted_at": "2026-09-15T00:01:00.000000Z", "predecessor_receipt_id": None,
    }


def test_identical_receipt_replay_has_identical_bytes_and_identity():
    body = receipt_body()
    receipt = ReviewAcceptanceReceipt.create(body)
    assert receipt == ReviewAcceptanceReceipt.create(deepcopy(body))
    assert receipt.receipt_id == "SWING-REVIEW-RECEIPT-" + sha256(canonical(body)).hexdigest()
    assert receipt == ReviewAcceptanceReceipt(receipt.payload)
    body["binding"]["canonical_instrument"] = "SBIN"
    extracted = receipt.body
    extracted["binding"]["canonical_instrument"] = "SBIN"
    assert receipt.body["binding"]["canonical_instrument"] == "CANBK"


def test_v2_receipt_keeps_comparison_separate_from_six_bindings():
    body = receipt_body()
    body["binding"].update(market="MCX", canonical_instrument="GOLDM", candidate_identity="CANDIDATE-GOLDM")
    comparison = dict(schema="KRONOS-SWING-MCX-PAIR-COMPARISON-EVIDENCE-V1", version="1.0",
        native_candidate_reference="CANDIDATE-GOLDM", pair_binding_sha256="f" * 64,
        native_request_identity="NATIVE-REQUEST", native_request_sha256="a" * 64,
        reference_request_identity="REFERENCE-REQUEST", reference_request_sha256="b" * 64,
        answer_identity=body["answer"]["answer_identity"], answer_pdf_sha256=body["answer"]["pdf_sha256"],
        sha256="e" * 64, retained_relative_path="comparison/e.json")
    body["comparison_evidence"] = comparison
    receipt = ReviewAcceptanceReceipt.create(body)
    assert (receipt.value["schema"], receipt.value["version"]) == (
        "KRONOS-SWING-REVIEW-EVIDENCE-RECEIPT-V2", "2.0")
    assert len(receipt.body["chart_revisions"]) == len(body["chart_revisions"])
    assert receipt == ReviewAcceptanceReceipt(receipt.payload)
    changed = deepcopy(body)
    changed["comparison_evidence"]["answer_identity"] = "DIFFERENT"
    with pytest.raises(ReviewEvidenceError):
        ReviewAcceptanceReceipt.create(changed)
    changed = deepcopy(body)
    changed["comparison_evidence"]["path_escape"] = "../../"
    with pytest.raises(ReviewEvidenceError):
        ReviewAcceptanceReceipt.create(changed)


def test_identity_covers_every_body_field_and_detects_tampering():
    receipt = ReviewAcceptanceReceipt.create(receipt_body())
    value = receipt.value
    value["body"]["binding"]["request_identity"] = "OTHER"
    with pytest.raises(ReviewEvidenceError, match="REVIEW_RECEIPT_INTEGRITY_INVALID"):
        ReviewAcceptanceReceipt(canonical(value))
    assert ReviewAcceptanceReceipt.create(value["body"]).receipt_id != receipt.receipt_id


@pytest.mark.parametrize("field", ["schema", "version", "integrity_sha256", "receipt_id"])
def test_receipt_envelope_fails_closed(field):
    value = ReviewAcceptanceReceipt.create(receipt_body()).value
    value[field] = 1
    with pytest.raises(ReviewEvidenceError):
        ReviewAcceptanceReceipt(canonical(value))


@pytest.mark.parametrize("payload,code", [
    ('{"a":1,"a":2}', "REVIEW_DUPLICATE_KEY"),
    ('{"a":{"b":1,"b":2}}', "REVIEW_DUPLICATE_KEY"),
    ('{"a":NaN}', "REVIEW_JSON_INVALID"),
    ('{"a":Infinity}', "REVIEW_JSON_INVALID"),
    ('[]', "REVIEW_JSON_INVALID"), ('{', "REVIEW_JSON_INVALID"),
])
def test_strict_json_rejects_ambiguous_input(payload, code):
    with pytest.raises(ReviewEvidenceError, match=code):
        strict_json(payload)


def test_receipt_requires_canonical_serialization():
    receipt = ReviewAcceptanceReceipt.create(receipt_body())
    with pytest.raises(ReviewEvidenceError, match="REVIEW_RECEIPT_INTEGRITY_INVALID"):
        ReviewAcceptanceReceipt(json.dumps(receipt.value, indent=2).encode())


@pytest.mark.parametrize("field", sorted(binding_value()))
def test_each_binding_field_participates_in_exact_applicability(field):
    receipt = ReviewAcceptanceReceipt.create(receipt_body())
    value = binding_value()
    if field == "market":
        value[field] = "MCX"
    elif field.endswith("sha256"):
        value[field] = "f" * 64
    elif field == "request_timestamp":
        value[field] = "2026-09-15T00:01:00.000000Z"
    else:
        value[field] += "-OTHER"
    assert project_review_evidence_state(receipt, ReviewEvidenceBinding.create("NATIVE_REVIEW", value)) == ReviewEvidenceState.STALE


def test_pure_state_projection_preserves_immutable_acceptance():
    receipt = ReviewAcceptanceReceipt.create(receipt_body())
    original = receipt.payload
    assert project_review_evidence_state(None, None) == ReviewEvidenceState.MISSING
    assert project_review_evidence_state(receipt, receipt.binding) == ReviewEvidenceState.ACCEPTED
    assert project_review_evidence_state(receipt, None) == ReviewEvidenceState.STALE
    assert project_review_evidence_state(receipt, receipt.binding, integrity_valid=False) == ReviewEvidenceState.INVALID
    successor_body = receipt_body()
    successor_body["predecessor_receipt_id"] = receipt.receipt_id
    successor_body["binding"]["review_cycle_identity"] = "CYCLE-B"
    successor = ReviewAcceptanceReceipt.create(successor_body)
    assert project_review_evidence_state(receipt, None, committed_successor=successor) == ReviewEvidenceState.REPLACED
    assert project_review_evidence_state(receipt, None, committed_successor=successor, integrity_valid=False) == ReviewEvidenceState.INVALID
    assert receipt.payload == original


def test_successor_cannot_rebind_another_run_or_candidate():
    receipt = ReviewAcceptanceReceipt.create(receipt_body())
    for field in ("analytical_run_identity", "candidate_identity", "canonical_instrument", "native_assessment_sha256"):
        body = receipt_body()
        body["predecessor_receipt_id"] = receipt.receipt_id
        body["binding"][field] = "f" * 64 if field.endswith("sha256") else "OTHER"
        with pytest.raises(ReviewEvidenceError, match="REVIEW_PREDECESSOR_INVALID"):
            project_review_evidence_state(receipt, None, committed_successor=ReviewAcceptanceReceipt.create(body))


@pytest.mark.parametrize("bad_path", ["/absolute", "../escape", "a/../escape", "a\\b", "a//b", ".", "a/./b", "a\x00b"])
def test_retained_paths_cannot_escape_evidence_root(bad_path):
    body = receipt_body()
    body["answer"]["retained_relative_path"] = bad_path
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ARTIFACT_REFERENCE_INVALID"):
        ReviewAcceptanceReceipt.create(body)


def test_closed_contracts_and_explicit_nulls_are_required():
    body = receipt_body()
    body["binding"]["extra"] = "untrusted"
    with pytest.raises(ReviewEvidenceError, match="REVIEW_UNKNOWN_FIELD"):
        ReviewAcceptanceReceipt.create(body)
    body = receipt_body()
    del body["chart_revisions"][0]["reference_symbol"]
    with pytest.raises(ReviewEvidenceError, match="REVIEW_REQUIRED_FIELD_MISSING"):
        ReviewAcceptanceReceipt.create(body)


def test_context_binding_has_no_fabricated_native_run_and_slot_is_exact():
    value = {"trading_date": "2026-09-15", "slot": "MORNING", "context_cycle_identity": "MCX-CYCLE",
        "request_identity": "MCX-REQUEST", "request_timestamp": "2026-09-15T00:00:00.000000Z",
        "question_pack_identity": "MCX-PACK", "question_pack_sha256": "a" * 64,
        "families": ["METALS", "ENERGY"]}
    morning = ReviewEvidenceBinding.create("MCX_SUPPORTING_CONTEXT", value)
    value["slot"] = "EVENING"
    evening = ReviewEvidenceBinding.create("MCX_SUPPORTING_CONTEXT", value)
    assert morning.lineage_key != evening.lineage_key
    value["analytical_run_identity"] = "SWING-RUN"
    with pytest.raises(ReviewEvidenceError, match="REVIEW_UNKNOWN_FIELD"):
        ReviewEvidenceBinding.create("MCX_SUPPORTING_CONTEXT", value)


def test_null_preconditions_are_not_wildcards_and_missing_is_not_null():
    values = dict.fromkeys(PRECONDITION_FIELDS)
    values["mutation_identity"] = "MUTATION-1"
    precondition = ReviewMutationPrecondition.create(values)
    current = {key: item for key, item in values.items() if key != "mutation_identity"}
    precondition.validate(current)
    changed = dict(current, expected_run_identity="NEW-RUN")
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        precondition.validate(changed)
    del current["expected_run_identity"]
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        precondition.validate(current)


def test_utc_microsecond_timestamp_is_canonical():
    assert timestamp(datetime(2026, 9, 15, tzinfo=UTC)) == "2026-09-15T00:00:00.000000Z"
    value = binding_value()
    value["request_timestamp"] = "2026-09-15T00:00:00+00:00"
    with pytest.raises(ReviewEvidenceError, match="REVIEW_TIMESTAMP_INVALID"):
        ReviewEvidenceBinding.create("NATIVE_REVIEW", value)


def nse_mapping(instrument="M&M"):
    from kronos.swing.v1.review_evidence_binding import NseReviewRequestMapping, NSE_REQUEST_SCHEMA, NSE_ANSWER_SCHEMA
    value = {"schema": NSE_REQUEST_SCHEMA, "version": "1.0", "request_identity": "NSE-REQUEST-1",
        "request_sha256": "0" * 64, "review_pack_identity": "PACK-1", "review_pack_sha256": "b" * 64,
        "native_run_identity": "SWING-RUN-" + "A" * 32, "committed_run_manifest_identity": "MANIFEST-1",
        "question_set_identity": "SWING-V1-VISUAL-QUESTION-SET-V3", "question_set_version": "3.1",
        "answer_schema": NSE_ANSWER_SCHEMA, "answer_version": "1.0", "request_timestamp": "2026-09-15T00:00:00.000000Z",
        "subjects": [{"subject_reference": "NSE-SUBJECT-1", "canonical_instrument": instrument,
            "native_assessment_sha256": "a" * 64, "chart_revision_sha256": "c" * 64,
            "responses": [{"timeframe": tf, "expected_chart_identity": instrument, "chart_revision_sha256": "c" * 64,
                "machine_fact_integrity_sha256": str(index + 1) * 64,
                "observation_boundary": "2026-09-14T15:30:00+05:30", "analysis_boundary": "2026-09-14T15:30:00+05:30"}
                for index, tf in enumerate(("1W", "1D", "4H", "1H"))]}]}
    return NseReviewRequestMapping.create(value)


def nse_answer(mapping):
    from kronos.swing.v1.visual_evidence_v3 import VisualQuestionV3
    value = mapping.value
    subject = value["subjects"][0]
    responses = []
    for requested in subject["responses"]:
        observations = []
        for index, question in enumerate(VisualQuestionV3):
            extra = {"finding": "NONE"}
            if index == 1:
                extra = {"presence": "NOT_PRESENT", "price_relationship": "NOT_OBSERVABLE", "interaction": "NOT_OBSERVABLE"}
            elif index == 3:
                extra = {"presence": "NOT_IDENTIFIABLE", "relationship": "NOT_OBSERVABLE", "interaction": "NOT_OBSERVABLE"}
            elif index == 4:
                extra = {"setup_quality": "NOT_OBSERVABLE", "finding": "NONE"}
            elif index == 8:
                extra = {"clustering": "NOT_OBSERVABLE", "components": []}
            observations.append({"question_id": question.value, "timeframe": requested["timeframe"], "observation_status": "OBSERVED",
                "visible_basis": "Synthetic chart", "confidence_in_extraction": "Readable", "ambiguity_reason": "",
                "source_chart_identity": subject["canonical_instrument"], "source_chart_revision": "c" * 64,
                "why_not_covered_elsewhere": None, **extra})
        responses.append({"model_identity": "SYNTHETIC", "timeframe": requested["timeframe"],
            "chart_identity": subject["canonical_instrument"], "chart_revision_sha256": "c" * 64,
            "observations": observations, "question_set_identity": value["question_set_identity"], "question_set_version": "3.1"})
    return {"schema": value["answer_schema"], "version": "1.0", "request_reference": mapping.request_reference,
        "answer_identity": "NSE-ANSWER-1", "subjects": [{"subject_reference": subject["subject_reference"],
            "canonical_instrument": subject["canonical_instrument"], "observed_chart_instrument": subject["canonical_instrument"], "responses": responses}]}


def nse_v2_mapping(instrument="M&M"):
    from kronos.swing.v1.review_evidence_binding import (
        NseReviewRequestMapping, NSE_REQUEST_SCHEMA_V2, NSE_ANSWER_SCHEMA_V2,
    )
    value = nse_mapping(instrument).value
    value.update(schema=NSE_REQUEST_SCHEMA_V2, version="2.0", question_set_version="3.2",
                 answer_schema=NSE_ANSWER_SCHEMA_V2, answer_version="2.0")
    return NseReviewRequestMapping.create(value)


def nse_v2_answer(mapping):
    answer = nse_answer(mapping)
    answer["version"] = "2.0"
    answer["subjects"][0].pop("observed_chart_instrument")
    for response in answer["subjects"][0]["responses"]:
        response["question_set_version"] = "3.2"
        questions = response["observations"]
        questions[0].update(observed_instrument="M and M Ltd", observed_market="NSE",
                            observed_timeframe=response["timeframe"], readability="READABLE",
                            identity_correspondence="MATCHED")
        questions[2]["question_id"] = "VISIBLE_STRUCTURAL_SUPPORT_RESISTANCE"
        questions[9]["question_id"] = "ADDITIONAL_MATERIAL_VISIBLE_FACT"
        questions[7]["observation_status"] = "NOT_VISIBLE"
    return answer


def test_nse_v2_raw_visible_company_name_and_closed_identity():
    from kronos.swing.v1.visual_evidence_v3 import validate_nse_successor_answer
    mapping = nse_v2_mapping()
    answer = nse_v2_answer(mapping)
    responses = validate_nse_successor_answer(canonical(answer), mapping)[0]
    assert len(responses) == 4 and all(item.question_set_version == "3.2" for item in responses)
    assert responses[0].observations[0].observed_instrument == "M and M Ltd"
    for field, replacement in (("identity_correspondence", "UNDETERMINED"),
                               ("observed_market", "MCX"), ("observed_timeframe", "1D")):
        changed = deepcopy(answer)
        changed["subjects"][0]["responses"][0]["observations"][0][field] = replacement
        with pytest.raises(ReviewEvidenceError):
            validate_nse_successor_answer(canonical(changed), mapping)
    changed = deepcopy(answer)
    changed["subjects"][0]["responses"][0]["observations"][4]["observation_status"] = "INVALID"
    with pytest.raises(ReviewEvidenceError):
        validate_nse_successor_answer(canonical(changed), mapping)
    assert nse_mapping().value["version"] == "1.0"


def test_nse_v2_93_member_supported_population_fits_extracted_json_ceiling():
    from kronos.swing.v1.review_evidence_binding import NseReviewRequestMapping
    from kronos.swing.v1.visual_evidence_v3 import validate_nse_successor_answer
    # The immutable Phase 1 universe has 91 equities and two indices; MCX's
    # five members use their separate paired request/Answer contract.
    mapping = nse_v2_mapping()
    template = mapping.value["subjects"][0]
    value = mapping.value
    value["subjects"] = []
    for index in range(93):
        subject = deepcopy(template)
        subject["subject_reference"] = f"SYNTHETIC-SUBJECT-{index:03d}"
        subject["canonical_instrument"] = f"SYNTHETIC-{index:03d}"
        for response in subject["responses"]:
            response["expected_chart_identity"] = subject["canonical_instrument"]
        value["subjects"].append(subject)
    mapping = NseReviewRequestMapping.create(value)
    answer = nse_v2_answer(mapping)
    template_answer = answer["subjects"][0]
    answer["subjects"] = []
    for subject in mapping.value["subjects"]:
        item = deepcopy(template_answer)
        item["subject_reference"] = subject["subject_reference"]
        item["canonical_instrument"] = subject["canonical_instrument"]
        for response in item["responses"]:
            response["chart_identity"] = subject["canonical_instrument"]
            response["observations"][0]["observed_instrument"] = subject["canonical_instrument"]
            for observation in response["observations"]:
                observation["source_chart_identity"] = subject["canonical_instrument"]
                observation["visible_basis"] = "X" * 512
        answer["subjects"].append(item)
    payload = canonical(answer)
    assert len(payload) < 8 * 1024 * 1024
    assert len(validate_nse_successor_answer(payload, mapping)) == 93
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ACCEPTANCE_INCOMPLETE"):
        validate_nse_successor_answer(b" " * (8 * 1024 * 1024 + 1), mapping)


def test_nse_pre_render_hash_excludes_exactly_two_fields():
    from kronos.swing.v1.review_evidence_binding import nse_pre_render_digest
    value = nse_mapping().value
    initial = nse_pre_render_digest(value)
    assert initial == value["request_sha256"]
    for key in value:
        changed = deepcopy(value)
        changed[key] = "different" if type(changed[key]) is str else []
        assert (nse_pre_render_digest(changed) == initial) == (key in {"request_sha256", "review_pack_sha256"}), key


def test_nse_mapping_validates_immutable_digest_and_exact_response_binding():
    from kronos.swing.v1.review_evidence_binding import NseReviewRequestMapping
    mapping = nse_mapping()
    value = mapping.value
    value["subjects"][0]["native_assessment_sha256"] = "f" * 64
    with pytest.raises(ReviewEvidenceError, match="REVIEW_REQUEST_MISMATCH"):
        NseReviewRequestMapping(canonical(value))
    value = mapping.value
    value["subjects"][0]["responses"].reverse()
    with pytest.raises(ReviewEvidenceError, match="REVIEW_REQUEST_MISMATCH"):
        NseReviewRequestMapping.create(value)


def test_nse_successor_produces_original_domain_types_and_preserves_observed_identity():
    from kronos.swing.v1.visual_evidence_v3 import validate_nse_successor_answer, VisualEvidenceV3Response
    mapping = nse_mapping()
    answer = nse_answer(mapping)
    original = deepcopy(answer)
    result = validate_nse_successor_answer(canonical(answer), mapping)
    assert len(result) == 1 and len(result[0]) == 4
    assert all(type(response) is VisualEvidenceV3Response for response in result[0])
    assert [response.timeframe.value for response in result[0]] == ["1W", "1D", "4H", "1H"]
    assert all(response.native_canonical_instrument == "M&M" for response in result[0])
    assert answer == original
    answer["subjects"][0]["observed_chart_instrument"] = "M&M;"
    with pytest.raises(ReviewEvidenceError, match="CHART_IDENTITY_MISMATCH"):
        validate_nse_successor_answer(canonical(answer), mapping)
    assert answer["subjects"][0]["observed_chart_instrument"] == "M&M;"


def test_nse_every_object_closed_and_provenance_rejected():
    from kronos.swing.v1.visual_evidence_v3 import validate_nse_successor_answer
    from swing.v1.test_mcx_native_visual_contract import object_paths, at
    mapping = nse_mapping()
    original = nse_answer(mapping)
    for path in object_paths(original):
        for field, code in (("extra", "REVIEW_UNKNOWN_FIELD"), ("provider_identity", "REVIEW_PROVENANCE_FORBIDDEN")):
            answer = deepcopy(original)
            at(answer, path)[field] = "forged"
            with pytest.raises(ReviewEvidenceError, match=code):
                validate_nse_successor_answer(canonical(answer), mapping)
        answer = deepcopy(original)
        obj = at(answer, path)
        key = "why_not_covered_elsewhere" if "question_id" in obj else next(iter(obj))
        del obj[key]
        with pytest.raises(ReviewEvidenceError):
            validate_nse_successor_answer(canonical(answer), mapping)


@pytest.mark.parametrize("index", range(9))
def test_nse_q1_q9_explanation_never_silently_dropped(index):
    from kronos.swing.v1.visual_evidence_v3 import validate_nse_successor_answer
    mapping = nse_mapping()
    answer = nse_answer(mapping)
    answer["subjects"][0]["responses"][0]["observations"][index]["why_not_covered_elsewhere"] = "extra"
    with pytest.raises(ReviewEvidenceError, match="VISUAL_V3_OBSERVATION_INVALID"):
        validate_nse_successor_answer(canonical(answer), mapping)


@pytest.mark.parametrize("point,valid", [(100.0, True), (100, False), (True, False), ("100", False)])
def test_nse_retains_float_only_numeric_domain(point, valid):
    from kronos.swing.v1.visual_evidence_v3 import validate_nse_successor_answer
    mapping = nse_mapping()
    answer = nse_answer(mapping)
    answer["subjects"][0]["responses"][0]["observations"][2].update(finding="Visible support", point_price=point)
    if valid:
        validate_nse_successor_answer(canonical(answer), mapping)
    else:
        with pytest.raises(ReviewEvidenceError):
            validate_nse_successor_answer(canonical(answer), mapping)


@pytest.mark.parametrize("finding,why,valid", [("NONE", None, True), ("NONE", "why", False),
    ("Visible annotation", "Not addressed by Q1-Q9", True), ("Visible annotation", None, False)])
def test_nse_q10_branches(finding, why, valid):
    from kronos.swing.v1.visual_evidence_v3 import validate_nse_successor_answer
    mapping = nse_mapping()
    answer = nse_answer(mapping)
    answer["subjects"][0]["responses"][0]["observations"][9].update(finding=finding, why_not_covered_elsewhere=why)
    if valid:
        validate_nse_successor_answer(canonical(answer), mapping)
    else:
        with pytest.raises(ReviewEvidenceError):
            validate_nse_successor_answer(canonical(answer), mapping)


@pytest.mark.parametrize("mode", ["three_frames", "mcx_role", "mcx_result", "wrong_request", "wrong_subject", "reordered"])
def test_nse_does_not_alias_mcx_or_resolve_independent_latest(mode):
    from kronos.swing.v1.visual_evidence_v3 import validate_nse_successor_answer
    mapping = nse_mapping()
    answer = nse_answer(mapping)
    subject = answer["subjects"][0]
    if mode == "three_frames":
        subject["responses"].pop(0)
    elif mode == "mcx_role":
        subject["role"] = "NATIVE_MCX"
    elif mode == "mcx_result":
        subject["responses"][0]["observations"][0]["result"] = {"finding": "NONE"}
    elif mode == "wrong_request":
        answer["request_reference"]["request_sha256"] = "f" * 64
    elif mode == "wrong_subject":
        subject["subject_reference"] = "M&M"
    else:
        subject["responses"].reverse()
    with pytest.raises(ReviewEvidenceError):
        validate_nse_successor_answer(canonical(answer), mapping)
