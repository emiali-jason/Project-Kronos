"""WO-07 independent MCX annex: extraction and identity, never reconciliation."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from kronos.swing.v1 import mcx_native_visual_contract as mcx
from kronos.swing.v1.native_review import MCX_REFERENCE_MAPPINGS
from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError, canonical


def _complete_successor_answer(native, reference):
    """The retained helper builds one leg subject; assemble every supplied pair."""
    answer = successor_answer(native, reference)
    for index in range(1, len(native.value["subjects"])):
        pair = []
        for mapping in (native, reference):
            value = mapping.value
            value["subjects"] = [value["subjects"][index]]
            pair.append(type(mapping).create(value))
        single = successor_answer(*pair)
        answer["subjects"].extend(single["subjects"])
        answer["supporting_reference_answer"]["subjects"].extend(single["supporting_reference_answer"]["subjects"])
    return answer


def _rendered_successor_contract(monkeypatch):
    """Inspect declarations actually supplied to the PDF renderer."""
    from io import BytesIO
    from PIL import Image
    from kronos.swing.v1 import pdf_visual_review_v3_live as producer

    image = BytesIO()
    Image.new("RGB", (32, 24), "white").save(image, format="PNG")
    payload = image.getvalue()
    revision = sha256(payload).hexdigest()
    mappings = []
    for mapping in successor_mappings(("CRUDEOIL", "NATURALGAS")):
        value = mapping.value
        for subject in value["subjects"]:
            for chart in subject["responses"]:
                chart["chart_revision_sha256"] = revision
        mappings.append(type(mapping).create(value))
    blocks = []
    original = producer.contract_block

    def record(text):
        try:
            blocks.append(json.loads(text))
        except json.JSONDecodeError:
            pass
        return original(text)

    monkeypatch.setattr(producer, "contract_block", record)
    native, reference, pdf = producer.render_mcx_successor_question_pdf(
        *mappings, {revision: payload})
    shape = next(block for block in blocks if "root_fields" in block)
    return shape, native, reference, pdf


def test_generated_mcx_pdf_defines_exact_response_question_sets(monkeypatch):
    from io import BytesIO
    from pypdf import PdfReader

    shape, native, reference, pdf = _rendered_successor_contract(monkeypatch)
    request = mcx.mcx_question_pack_from_mappings(native, reference).value
    expected = {
        mcx.NATIVE_ROLE: {"question_set_identity": request["schema"],
                          "question_set_version": request["version"]},
        mcx.REFERENCE_ROLE: {
            "question_set_identity": request["supporting_reference_pack"]["schema"],
            "question_set_version": request["supporting_reference_pack"]["version"]},
    }
    assert shape["response_question_sets"] == expected
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
    assert '"response_question_sets"' in text
    answer = _complete_successor_answer(native, reference)
    for root, role in ((answer, mcx.NATIVE_ROLE),
                       (answer["supporting_reference_answer"], mcx.REFERENCE_ROLE)):
        for subject in root["subjects"]:
            for response in subject["responses"]:
                response.update(shape["response_question_sets"][role])
    assert mcx.validate_mcx_answer(canonical(answer),
                                 mcx.mcx_question_pack_from_mappings(native, reference)) == answer
    # A retained request-mapping schema or Answer schema is not a question set.
    for wrong in (native.value["schema"], mcx.NATIVE_ANSWER_V2):
        changed = deepcopy(answer)
        changed["subjects"][0]["responses"][0]["question_set_identity"] = wrong
        with pytest.raises(ReviewEvidenceError):
            mcx.validate_mcx_answer(canonical(changed),
                                   mcx.mcx_question_pack_from_mappings(native, reference))


def test_generated_mcx_pdf_defines_closed_comparison_observations(monkeypatch):
    from io import BytesIO
    from pypdf import PdfReader

    shape, native, reference, pdf = _rendered_successor_contract(monkeypatch)
    comparison = shape["comparison_contract"]
    assert set(comparison["observation_fields"]) == {
        "question_id", "observation_status", "visible_basis", "confidence_in_extraction",
        "ambiguity_reason", "result"}
    assert comparison["m2_by_timeframe"] == {
        "type": "array", "exact_length": 3, "ordered_timeframes": ["1D", "4H", "1H"],
        "row_fields": ["timeframe", "relationship", "finding"],
        "additional_fields": "FORBIDDEN", "nullable": False}
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
    for phrase in ('"observation_fields"', '"m2_by_timeframe"',
                   '"exact_length": 3', "MISMATCHED", "NOT_COMPARABLE"):
        assert phrase in text
    assert comparison["accepted_statuses"] == ["OBSERVED", "PARTIAL", "UNAVAILABLE"]
    assert comparison["null_fields"] == []
    assert comparison["additional_fields"] == "FORBIDDEN_AT_EVERY_LEVEL"


@pytest.mark.parametrize("mutation", ["object", "order", "null", "extra_observation",
                                      "extra_row", "invalid", "mismatched", "missing_field",
                                      "wrong_subject", "wrong_pair", "request_swap"])
def test_mcx_comparison_contract_rejects_malformed_or_rebound_data(mutation):
    native, reference = successor_mappings(("CRUDEOIL", "NATURALGAS"))
    answer = _complete_successor_answer(native, reference)
    assert mcx.validate_mcx_answer(canonical(answer), mcx.mcx_question_pack_from_mappings(native, reference)) == answer
    subject = answer["comparison_answer"]["subjects"][0]
    observation = subject["observations"][1]
    rows = observation["result"]["by_timeframe"]
    if mutation == "object": observation["result"]["by_timeframe"] = {r["timeframe"]: r for r in rows}
    elif mutation == "order": rows.reverse()
    elif mutation == "null": rows[0]["finding"] = None
    elif mutation == "extra_observation": observation["timeframe"] = "1H"
    elif mutation == "extra_row": rows[0]["price"] = 100
    elif mutation == "invalid": observation["observation_status"] = "INVALID"
    elif mutation == "mismatched": subject["observations"][0]["result"]["mapping_state"] = "MISMATCHED"
    elif mutation == "missing_field": observation.pop("ambiguity_reason")
    elif mutation == "wrong_subject": subject["reference_subject_reference"] = "FOREIGN"
    elif mutation == "wrong_pair": subject["pair_binding_sha256"] = "f" * 64
    else: answer["comparison_answer"]["request_references"]["native"] = answer["comparison_answer"]["request_references"]["reference"]
    with pytest.raises(ReviewEvidenceError):
        mcx.validate_mcx_answer(canonical(answer), mcx.mcx_question_pack_from_mappings(native, reference))


def retained_mappings(families=("GOLDM",), bundle="BUNDLE-1"):
    values = []
    for native in (True, False):
        value = {"schema": mcx.NATIVE_REQUEST_SCHEMA if native else mcx.REFERENCE_REQUEST_SCHEMA,
            "version": "1.0", "request_bundle_identity": bundle,
            "request_identity": bundle + ("-NATIVE" if native else "-REFERENCE"), "request_sha256": "0" * 64,
            "review_pack_identity": bundle + "-PACK", "review_pack_sha256": "0" * 64,
            "native_run_identity": "SYNTHETIC-RUN", "committed_run_manifest_identity": "SYNTHETIC-MANIFEST",
            "review_cycle_identity": bundle + "-CYCLE",
            "question_contract_identity": mcx.NATIVE_QUESTIONS if native else mcx.REFERENCE_QUESTIONS,
            "question_contract_version": "1.0", "answer_contract_identity": mcx.NATIVE_ANSWER if native else mcx.REFERENCE_ANSWER,
            "answer_contract_version": "1.0", "request_timestamp": "2026-09-15T00:00:00.000000Z", "subjects": []}
        for family in families:
            label, market, symbol = MCX_REFERENCE_MAPPINGS[family]
            subject = {"subject_reference": family + ("-N" if native else "-R"),
                "native_candidate_reference": "CANDIDATE-" + family, "native_assessment_sha256": "a" * 64,
                "supplied_native_direction": "LONG", "responses": []}
            if native:
                subject["canonical_instrument"] = family
            else:
                subject.update(native_canonical_instrument=family, reference_subject_identity=label,
                               reference_market=market.value, reference_symbol=symbol)
            for tf in ("1D", "4H", "1H"):
                response = {"timeframe": tf, "expected_chart_identity": family if native else symbol,
                    "chart_revision_identity": family + ("-N-" if native else "-R-") + tf,
                    "chart_revision_sha256": ("b" if native else "c") * 64}
                if native:
                    response.update(native_machine_fact_integrity_sha256="d" * 64,
                        governed_reference_period="PREVIOUS_WEEK" if tf == "1H" else "PREVIOUS_MONTH",
                        governed_reference_basis_availability="AVAILABLE",
                        observation_boundary="2026-09-14T15:30:00+05:30", analysis_boundary="2026-09-14T15:30:00+05:30")
                subject["responses"].append(response)
            value["subjects"].append(subject)
        values.append(value)
    return mcx.McxNativeReviewRequestMapping.create(values[0]), mcx.McxReferenceReviewRequestMapping.create(values[1])


def successor_mappings(families=("GOLDM",)):
    native, reference = retained_mappings(families)
    values = []
    for mapping, role in ((native, mcx.NATIVE_ROLE), (reference, mcx.REFERENCE_ROLE)):
        value = mapping.value
        value.update(schema=mcx.NATIVE_REQUEST_SCHEMA_V2 if role == mcx.NATIVE_ROLE else mcx.REFERENCE_REQUEST_SCHEMA_V2,
                     version="2.0", question_contract_identity=mcx.NATIVE_QUESTIONS_V2 if role == mcx.NATIVE_ROLE else mcx.REFERENCE_QUESTIONS_V2,
                     question_contract_version="2.0", answer_contract_identity=mcx.NATIVE_ANSWER_V2 if role == mcx.NATIVE_ROLE else mcx.REFERENCE_ANSWER_V2,
                     answer_contract_version="2.0")
        values.append(type(mapping).create(value))
    return tuple(values)


def successor_answer(native, reference):
    request = mcx.mcx_question_pack_from_mappings(native, reference)
    answer = answer_for(request)
    answer["answer_identity"] = "ONE-ANSWER-IDENTITY"
    for root, role in ((answer, mcx.NATIVE_ROLE), (answer["supporting_reference_answer"], mcx.REFERENCE_ROLE)):
        mapping = native.value if role == mcx.NATIVE_ROLE else reference.value
        root.update(schema=mapping["answer_contract_identity"],
                    version=mapping["answer_contract_version"], answer_identity="ONE-ANSWER-IDENTITY")
        for subject in root["subjects"]:
            subject.pop("observed_chart_identity")
            for response in subject["responses"]:
                response["question_set_version"] = mapping["question_contract_version"]
                for i, obs in enumerate(response["observations"]):
                    obs["question_id"] = mcx.QUESTION_IDS_V2[i]
                response["observations"][0]["result"]["identity_correspondence"] = "MATCHED"
    pack = request.value["comparison_pack"]
    answer["comparison_answer"] = {"schema": mcx.COMPARISON_ANSWER, "version": "1.0",
        "request_references": pack["request_references"], "answer_identity": answer["answer_identity"],
        "subjects": [{**item, "observations": [
            {"question_id": mcx.COMPARISON_IDS[0], "observation_status": "OBSERVED", "visible_basis": "Exact pair",
             "confidence_in_extraction": "Readable", "ambiguity_reason": "",
             "result": {"mapping_state": "MATCHED", "coverage_state": "SUFFICIENT", "finding": "Visible reference"}},
            {"question_id": mcx.COMPARISON_IDS[1], "observation_status": "OBSERVED", "visible_basis": "Paired frames",
             "confidence_in_extraction": "Readable", "ambiguity_reason": "",
             "result": {"by_timeframe": [{"timeframe": tf, "relationship": "AGREES", "finding": "Visible structure"}
                                         for tf in ("1D", "4H", "1H")]}},
            {"question_id": mcx.COMPARISON_IDS[2], "observation_status": "OBSERVED", "visible_basis": "Paired frames",
             "confidence_in_extraction": "Readable", "ambiguity_reason": "",
             "result": {"relationship_to_native_direction": "NO_MATERIAL_DIVERGENCE",
                        "affected_timeframes": [], "limitations": [], "finding": "No material limitation visible"}},
        ]} for item in pack["subjects"]]}
    return answer


def test_mcx_v2_six_per_leg_and_separate_comparison_identity():
    native, reference = successor_mappings()
    answer = successor_answer(native, reference)
    request = mcx.mcx_question_pack_from_mappings(native, reference)
    assert mcx.validate_mcx_answer(canonical(answer), request) == answer
    six = mcx.mcx_structured_evidence(canonical(answer), native, reference, "f" * 64)
    comparison = mcx.mcx_comparison_evidence(canonical(answer), native, reference, "f" * 64)
    assert len(six) == 6 and len(comparison) == 1
    assert {json.loads(raw)["answer_identity"] for raw in (*six, *comparison)} == {"ONE-ANSWER-IDENTITY"}
    assert json.loads(comparison[0])["pair_binding_sha256"] == mcx.mcx_pair_binding(native.value, reference.value, 0)
    changed = deepcopy(answer)
    changed["supporting_reference_answer"]["answer_identity"] = "ANOTHER"
    with pytest.raises(ReviewEvidenceError):
        mcx.validate_mcx_answer(canonical(changed), request)
    changed = deepcopy(answer)
    changed["subjects"][0]["observed_chart_identity"] = "GOLDM"
    with pytest.raises(ReviewEvidenceError):
        mcx.validate_mcx_answer(canonical(changed), request)
    changed = deepcopy(answer)
    changed["supporting_reference_answer"]["subjects"][0]["responses"][0]["observations"][0]["result"]["observed_identity"] = "COMEX:SI1!"
    with pytest.raises(ReviewEvidenceError):
        mcx.validate_mcx_answer(canonical(changed), request)


def test_mcx_v2_reference_unavailable_keeps_native_facts_without_false_agreement():
    native, reference = successor_mappings()
    answer = successor_answer(native, reference)
    q1 = answer["supporting_reference_answer"]["subjects"][0]["responses"][0]["observations"][0]
    q1["result"].update(observed_identity=None, readability="UNREADABLE", identity_correspondence="UNDETERMINED")
    q1.update(observation_status="UNAVAILABLE", ambiguity_reason="Reference label unreadable")
    comparison = answer["comparison_answer"]["subjects"][0]["observations"]
    comparison[0].update(observation_status="PARTIAL", ambiguity_reason="Reference label unreadable")
    comparison[0]["result"].update(mapping_state="UNDETERMINED", coverage_state="PARTIAL")
    comparison[1].update(observation_status="PARTIAL", ambiguity_reason="First reference label unreadable")
    comparison[1]["result"]["by_timeframe"][0]["relationship"] = "NOT_COMPARABLE"
    comparison[2]["result"]["relationship_to_native_direction"] = "NOT_ESTABLISHED"
    assert mcx.validate_mcx_answer(canonical(answer), mcx.mcx_question_pack_from_mappings(native, reference)) == answer
    wrong = deepcopy(answer)
    wrong["comparison_answer"]["subjects"][0]["observations"][1]["result"]["by_timeframe"][0]["relationship"] = "AGREES"
    with pytest.raises(ReviewEvidenceError):
        mcx.validate_mcx_answer(canonical(wrong), mcx.mcx_question_pack_from_mappings(native, reference))
    wrong = deepcopy(answer)
    wrong["comparison_answer"]["subjects"][0]["observations"][0]["observation_status"] = "INVALID"
    with pytest.raises(ReviewEvidenceError):
        mcx.validate_mcx_answer(canonical(wrong), mcx.mcx_question_pack_from_mappings(native, reference))


def test_mcx_v2_extracted_answer_size_is_bounded_before_json_parse():
    native, reference = successor_mappings()
    with pytest.raises(ReviewEvidenceError, match="MCX_ANSWER_SIZE_INVALID"):
        mcx.validate_mcx_answer(b" " * (8 * 1024 * 1024 + 1),
                                mcx.mcx_question_pack_from_mappings(native, reference))


def test_retained_pair_independent_preimages_and_exact_projection():
    native, reference = retained_mappings(tuple(MCX_REFERENCE_MAPPINGS))
    mcx.validate_mcx_request_pair(native, reference)
    pack = mcx.mcx_question_pack_from_mappings(native, reference).value
    assert len(pack["subjects"]) == 5
    assert native.value["schema"] != reference.value["schema"]
    assert native.value["request_identity"] != reference.value["request_identity"]
    assert pack["request_reference"]["request_sha256"] == native.value["request_sha256"]
    for mapping in (native, reference):
        expected = {key: val for key, val in mapping.value.items() if key not in {"request_sha256", "review_pack_sha256"}}
        assert mapping.value["request_sha256"] == sha256(canonical(expected)).hexdigest()
        changed = mapping.value
        changed.update(request_sha256="f" * 64, review_pack_sha256="e" * 64)
        assert mcx.mcx_pre_render_digest(changed) == mapping.value["request_sha256"]
        # Every leaf included in the canonical preimage participates, not just a selected subset.
        def leaves(value, path=()):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield from leaves(child, (*path, key))
            elif isinstance(value, list):
                for key, child in enumerate(value):
                    yield from leaves(child, (*path, key))
            else:
                yield path
        for path in leaves(expected):
            changed = mapping.value
            node = changed
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = str(node[path[-1]]) + "-CHANGED"
            if path == ("schema",):
                changed["schema"] = mcx.REFERENCE_REQUEST_SCHEMA if mapping is native else mcx.NATIVE_REQUEST_SCHEMA
            assert mcx.mcx_pre_render_digest(changed) != mapping.value["request_sha256"], path
    before_native = native.payload
    changed = reference.value
    changed["subjects"][0]["responses"][0]["chart_revision_sha256"] = "f" * 64
    assert mcx.McxReferenceReviewRequestMapping.create(changed).value["request_sha256"] != reference.value["request_sha256"]
    assert native.payload == before_native
    for subject in pack["supporting_reference_pack"]["subjects"]:
        assert subject["machine_inventory_disclosure"] == "NOT_GOVERNED"
        assert all(chart["reference_period"] is None for chart in subject["charts"])


def test_structured_native_reference_evidence_preserves_exact_separate_authority():
    native, reference = retained_mappings()
    request = mcx.mcx_question_pack_from_mappings(native, reference)
    answer = answer_for(request)
    original = deepcopy(answer)
    pdf_hash = "f" * 64
    values = tuple(json.loads(item) for item in mcx.mcx_structured_evidence(canonical(answer), native, reference, pdf_hash))
    assert len(values) == 6
    assert answer == original
    for index, value in enumerate(values):
        n = index < 3
        mapping = native.value if n else reference.value
        raw = answer if n else answer["supporting_reference_answer"]
        assert value["schema"] == (mcx.NATIVE_EVIDENCE if n else mcx.REFERENCE_EVIDENCE)
        assert value["answer_identity"] == raw["answer_identity"]
        assert value["answer_pdf_sha256"] == pdf_hash
        assert value["response"] == raw["subjects"][0]["responses"][index % 3]
        binding = value["binding"]
        assert binding["native_canonical_instrument"] == "GOLDM"
        assert binding["native_candidate_reference"] == mapping["subjects"][0]["native_candidate_reference"]
        assert binding["native_machine_fact_binding"] == ("d" * 64 if n else None)
        assert binding["request_identity"] == mapping["request_identity"]
        assert binding["request_sha256"] == mapping["request_sha256"]
        assert binding["subject_identity"] == ("GOLDM" if n else "COMEX Gold")
        assert binding["reference_symbol"] == (None if n else "COMEX:GC1!")
        assert "observation_boundary" not in binding and "analysis_boundary" not in binding
        assert value["integrity_sha256"] == sha256(canonical({k: v for k, v in value.items() if k != "integrity_sha256"})).hexdigest()
    answer["supporting_reference_answer"]["subjects"][0]["responses"].pop()
    with pytest.raises(ReviewEvidenceError, match="MCX_TIMEFRAME_MISMATCH"):
        mcx.mcx_structured_evidence(canonical(answer), native, reference, pdf_hash)


@pytest.mark.parametrize("field", ["request_bundle_identity", "review_cycle_identity", "review_pack_identity",
    "review_pack_sha256", "native_run_identity", "committed_run_manifest_identity", "request_timestamp"])
def test_retained_pair_shared_authority_mismatch(field):
    native, reference = retained_mappings()
    changed = reference.value
    changed[field] = "e" * 64 if field.endswith("sha256") else "2026-09-15T01:00:00.000000Z" if field == "request_timestamp" else "OTHER"
    with pytest.raises(ReviewEvidenceError, match="MCX_REQUEST_MISMATCH"):
        mcx.validate_mcx_request_pair(native, mcx.McxReferenceReviewRequestMapping.create(changed))


@pytest.mark.parametrize("native", [True, False])
@pytest.mark.parametrize("mode", ["weekly", "missing", "duplicate", "reorder", "version_number", "foreign_fact"])
def test_retained_mapping_rejects_wrong_shape_and_provenance(native, mode):
    mapping = retained_mappings()[0 if native else 1]
    changed = mapping.value
    responses = changed["subjects"][0]["responses"]
    if mode == "weekly":
        responses[0]["timeframe"] = "1W"
    elif mode == "missing":
        responses.pop()
    elif mode == "duplicate":
        responses[1] = deepcopy(responses[0])
    elif mode == "reorder":
        responses.reverse()
    elif mode == "version_number":
        changed["version"] = 1.0
    else:
        responses[0]["foreign_machine_fact_sha256"] = "f" * 64
    with pytest.raises(ReviewEvidenceError):
        type(mapping).create(changed)


@pytest.mark.parametrize("family", tuple(MCX_REFERENCE_MAPPINGS))
def test_retained_reference_mapping_cannot_substitute_another_family(family):
    native, reference = retained_mappings((family,))
    changed = reference.value
    changed["subjects"][0]["reference_symbol"] = "WRONG:SYMBOL"
    with pytest.raises(ReviewEvidenceError, match="MCX_IDENTITY_MISMATCH"):
        mcx.McxReferenceReviewRequestMapping.create(changed)


@pytest.mark.parametrize("mode", ["missing", "duplicate", "reorder", "candidate", "assessment"])
def test_retained_pair_requires_exact_ordered_population_association(mode):
    native, reference = retained_mappings(("GOLDM", "SILVERM"))
    changed = reference.value
    if mode == "missing":
        changed["subjects"].pop()
    elif mode == "duplicate":
        changed["subjects"][1] = deepcopy(changed["subjects"][0])
    elif mode == "reorder":
        changed["subjects"].reverse()
    elif mode == "candidate":
        changed["subjects"][0]["native_candidate_reference"] = "OTHER"
    else:
        changed["subjects"][0]["native_assessment_sha256"] = "f" * 64
    with pytest.raises(ReviewEvidenceError):
        mcx.validate_mcx_request_pair(native, mcx.McxReferenceReviewRequestMapping.create(changed))


def request_for(family="GOLDM"):
    label, market, symbol = MCX_REFERENCE_MAPPINGS[family]
    packs = []
    for role in (mcx.NATIVE_ROLE, mcx.REFERENCE_ROLE):
        native = role == mcx.NATIVE_ROLE
        subject = {"subject_reference": role + "-SUBJECT", "native_candidate_reference": "CANDIDATE-" + family,
            "role": role, "subject_identity": family if native else label,
            "market": "MCX" if native else market.value, "reference_symbol": None if native else symbol,
            "supplied_native_direction": "LONG", "machine_inventory_disclosure": "NOT_SUPPLIED" if native else "NOT_GOVERNED",
            "charts": []}
        for index, tf in enumerate(("1D", "4H", "1H")):
            subject["charts"].append({"timeframe": tf, "chart_revision_identity": role + "-REV-" + tf,
                "chart_revision_sha256": str(index + (1 if native else 4)) * 64,
                "expected_chart_identity": family if native else symbol, "expected_market": subject["market"],
                "reference_period": ("PREVIOUS_WEEK" if tf == "1H" else "PREVIOUS_MONTH") if native else None,
                "reference_basis_availability": "AVAILABLE" if native else "NOT_APPLICABLE"})
        packs.append({"schema": mcx.NATIVE_QUESTIONS if native else mcx.REFERENCE_QUESTIONS, "version": "1.0",
            "request_reference": {"request_identity": role + "-REQUEST", "request_sha256": ("a" if native else "b") * 64},
            "subjects": [subject], "questions": mcx.question_definitions(role)})
    packs[0]["supporting_reference_pack"] = packs[1]
    return mcx.McxNativeVisualRequest.create(packs[0])


def answer_for(request):
    packs = (request.value, request.value["supporting_reference_pack"])
    answers = []
    for pack in packs:
        expected = pack["subjects"][0]
        native = expected["role"] == mcx.NATIVE_ROLE
        subject = {key: expected[key] for key in ("subject_reference", "native_candidate_reference", "role",
            "subject_identity", "market", "reference_symbol")}
        subject.update(observed_chart_identity=expected["charts"][0]["expected_chart_identity"], responses=[])
        for chart in expected["charts"]:
            tf = chart["timeframe"]
            results = [
                {"observed_identity": chart["expected_chart_identity"], "observed_market": chart["expected_market"], "observed_timeframe": tf, "readability": "READABLE"},
                {"presence": "NOT_PRESENT", "price_relationship": "NOT_OBSERVABLE", "interaction": "NOT_OBSERVABLE"},
                {"finding": "NONE", "machine_coverage_comparison": "COMPARISON_UNAVAILABLE" if native else "NOT_APPLICABLE", "point_price": None, "zone_low": None, "zone_high": None},
                {"reference_period": chart["reference_period"], "presence": "PRESENT" if native else None, "relationship": "INSIDE_REFERENCE_RANGE" if native else None, "interaction": "NONE" if native else None},
                {"setup_quality": "HEALTHY_CONSOLIDATION", "finding": "Visible pause relative to the supplied orientation."},
                {"finding": "NONE", "point_price": None, "zone_low": None, "zone_high": None},
                {"finding": "NONE"}, {"finding": "NONE"},
                {"clustering": "NOT_CLUSTERED", "components": []},
                {"finding": "NONE", "machine_coverage_comparison": "COMPARISON_UNAVAILABLE" if native else "NOT_APPLICABLE"},
            ]
            observations = []
            for index, result in enumerate(results):
                reference_q4 = not native and index == 3
                observations.append({"question_id": mcx.QUESTION_IDS[index], "timeframe": tf,
                    "observation_status": "NOT_APPLICABLE" if reference_q4 else "NOT_VISIBLE" if index == 7 else "OBSERVED",
                    "visible_basis": "Synthetic chart fixture", "confidence_in_extraction": "Readable",
                    "ambiguity_reason": "", "source_chart_identity": chart["expected_chart_identity"],
                    "source_chart_revision": chart["chart_revision_sha256"], "why_not_covered_elsewhere": None,
                    "not_applicable_reason": "REFERENCE_PERIOD_NOT_GOVERNED" if reference_q4 else None, "result": result})
            subject["responses"].append({"model_identity": "SYNTHETIC-NO-PROVIDER-CALL", "question_set_identity": pack["schema"],
                "question_set_version": "1.0", "role": expected["role"], "timeframe": tf,
                "chart_identity": chart["expected_chart_identity"], "chart_revision_sha256": chart["chart_revision_sha256"], "observations": observations})
        answers.append({"schema": mcx.NATIVE_ANSWER if native else mcx.REFERENCE_ANSWER, "version": "1.0",
            "request_reference": pack["request_reference"], "answer_identity": expected["role"] + "-ANSWER", "subjects": [subject]})
    answers[0]["supporting_reference_answer"] = answers[1]
    return answers[0]


def observation(answer, index, reference=False):
    root = answer["supporting_reference_answer"] if reference else answer
    return root["subjects"][0]["responses"][0]["observations"][index]


def reject(request, answer, code):
    with pytest.raises(ReviewEvidenceError, match=code):
        mcx.validate_mcx_answer(canonical(answer), request)


@pytest.mark.parametrize("family", tuple(MCX_REFERENCE_MAPPINGS))
def test_all_five_families_preserve_independent_identity_and_three_frames(family):
    request = request_for(family)
    answer = answer_for(request)
    original = deepcopy(answer)
    assert mcx.validate_mcx_answer(canonical(answer), request) == original
    assert [r["timeframe"] for r in answer["subjects"][0]["responses"]] == ["1D", "4H", "1H"]
    reference = answer["supporting_reference_answer"]["subjects"][0]
    label, market, symbol = MCX_REFERENCE_MAPPINGS[family]
    assert (reference["subject_identity"], reference["market"], reference["observed_chart_identity"]) == (label, market.value, symbol)
    assert answer == original


@pytest.mark.parametrize("reference", [False, True])
@pytest.mark.parametrize("mode", ["weekly", "omit", "duplicate", "reorder"])
def test_exact_timeframe_tuple_is_required(reference, mode):
    request = request_for()
    answer = answer_for(request)
    root = answer["supporting_reference_answer"] if reference else answer
    responses = root["subjects"][0]["responses"]
    if mode == "weekly":
        responses[0]["timeframe"] = "1W"
    elif mode == "omit":
        responses.pop()
    elif mode == "duplicate":
        responses[1] = deepcopy(responses[0])
    else:
        responses.reverse()
    reject(request, answer, "MCX_TIMEFRAME_MISMATCH")


@pytest.mark.parametrize("reference", [False, True])
@pytest.mark.parametrize("field,value,code", [
    ("role", "NATIVE_NSE", "MCX_ROLE_MISMATCH"),
    ("subject_identity", "GOLDM;", "MCX_IDENTITY_MISMATCH"),
    ("native_candidate_reference", "OTHER", "MCX_IDENTITY_MISMATCH"),
    ("observed_chart_identity", "GOLDM26OCTFUT", "MCX_IDENTITY_MISMATCH"),
    ("market", "NSE", "MCX_REFERENCE_MARKET_MISMATCH"),
    ("reference_symbol", "COMEX:SI1!", "MCX_REFERENCE_SYMBOL_MISMATCH"),
])
def test_wrong_role_source_or_executable_substitution_fails(reference, field, value, code):
    request = request_for()
    answer = answer_for(request)
    root = answer["supporting_reference_answer"] if reference else answer
    root["subjects"][0][field] = value
    reject(request, answer, code)


@pytest.mark.parametrize("reference", [False, True])
@pytest.mark.parametrize("index", range(9))
def test_q1_q9_explanation_is_required_null_including_reference_na(reference, index):
    request = request_for()
    answer = answer_for(request)
    observation(answer, index, reference)["why_not_covered_elsewhere"] = "Not allowed"
    reject(request, answer, "MCX_Q10_INVALID")


@pytest.mark.parametrize("reference", [False, True])
@pytest.mark.parametrize("finding,why,valid", [
    ("NONE", None, True), ("NONE", "Explanation", False), ("Distinct visible annotation", "Not addressed by Q1-Q9", True),
    ("Distinct visible annotation", None, False), ("Distinct visible annotation", "", False),
    ("Distinct visible annotation", "x" * 513, False),
])
def test_q10_both_branches(reference, finding, why, valid):
    request = request_for()
    answer = answer_for(request)
    obs = observation(answer, 9, reference)
    obs["result"]["finding"], obs["why_not_covered_elsewhere"] = finding, why
    if valid:
        mcx.validate_mcx_answer(canonical(answer), request)
    else:
        reject(request, answer, "MCX_Q10_INVALID")


def object_paths(value, prefix=()):
    if type(value) is dict:
        yield prefix
        for key, child in value.items():
            yield from object_paths(child, prefix + (key,))
    elif type(value) is list:
        for index, child in enumerate(value):
            yield from object_paths(child, prefix + (index,))


def at(value, path):
    for part in path:
        value = value[part]
    return value


def test_every_nested_answer_object_rejects_unknown_missing_and_provenance_fields():
    request = request_for()
    original = answer_for(request)
    checked = 0
    for path in object_paths(original):
        for field, value, code in (("extra", "not governed", "MCX_UNKNOWN_FIELD"),
                                   ("provider_identity", "forged", "MCX_PROVENANCE_FORBIDDEN")):
            answer = deepcopy(original)
            at(answer, path)[field] = value
            reject(request, answer, code)
        answer = deepcopy(original)
        obj = at(answer, path)
        del obj[next(iter(obj))]
        reject(request, answer, "MCX_REQUIRED_FIELD_MISSING")
        checked += 1
    assert checked == 132


def test_duplicate_keys_and_nonfinite_constants_fail_before_construction():
    for payload, code in ((b'{"a":1,"a":2}', "MCX_DUPLICATE_KEY"),
                          (b'{"a":{"x":1,"x":2}}', "MCX_DUPLICATE_KEY"),
                          (b'{"a":NaN}', "MCX_JSON_INVALID")):
        with pytest.raises(ReviewEvidenceError, match=code):
            mcx.parse_mcx_json(payload)


@pytest.mark.parametrize("reference", [False, True])
def test_contract_version_is_string_and_request_echo_is_exact(reference):
    request = request_for()
    answer = answer_for(request)
    root = answer["supporting_reference_answer"] if reference else answer
    root["version"] = 1.0
    reject(request, answer, "MCX_CONTRACT_MISMATCH")
    root["version"] = "1.0"
    root["request_reference"]["request_identity"] = "OTHER-CYCLE"
    reject(request, answer, "MCX_REQUEST_MISMATCH")


def test_reference_missing_is_incomplete_not_accepted():
    request = request_for()
    answer = answer_for(request)
    answer["supporting_reference_answer"] = None
    reject(request, answer, "MCX_REFERENCE_REQUIRED")


@pytest.mark.parametrize("reference", [False, True])
@pytest.mark.parametrize("index", [2, 9])
def test_machine_inventory_gap_cannot_be_claimed(reference, index):
    request = request_for()
    answer = answer_for(request)
    observation(answer, index, reference)["result"]["machine_coverage_comparison"] = "ABSENT_FROM_MACHINE"
    reject(request, answer, "MCX_MACHINE_COVERAGE_INVALID")


def test_native_q4_basis_unavailable_and_reference_q4_explicit_na():
    raw = request_for().value
    raw["subjects"][0]["charts"][0]["reference_basis_availability"] = "UNAVAILABLE"
    request = mcx.McxNativeVisualRequest.create(raw)
    answer = answer_for(request)
    reject(request, answer, "MCX_REFERENCE_BASIS_INVALID")
    obs = observation(answer, 3)
    obs.update(observation_status="UNAVAILABLE", ambiguity_reason="Governed basis unavailable")
    obs["result"].update(presence="NOT_IDENTIFIABLE", relationship="NOT_OBSERVABLE", interaction="NOT_OBSERVABLE")
    mcx.validate_mcx_answer(canonical(answer), request)
    observation(answer, 3, True)["result"]["reference_period"] = "PREVIOUS_MONTH"
    reject(request, answer, "MCX_REFERENCE_BASIS_INVALID")


@pytest.mark.parametrize("index", [2, 5])
@pytest.mark.parametrize("levels,valid", [
    ((None, None, None), True), ((0, None, None), True), ((100.0, None, None), True), ((None, 1, 2), True),
    ((True, None, None), False), (("100", None, None), False), ((-1, None, None), False),
    ((None, 2, 1), False), ((1, 2, 3), False), ((None, 1, None), False),
])
def test_point_zone_and_no_level_numeric_discipline(index, levels, valid):
    request = request_for()
    answer = answer_for(request)
    result = observation(answer, index)["result"]
    result.update(finding="Independently readable", **dict(zip(("point_price", "zone_low", "zone_high"), levels)))
    if valid:
        mcx.validate_mcx_answer(canonical(answer), request)
    else:
        reject(request, answer, "MCX_LEVEL_INVALID")


@pytest.mark.parametrize("status", ["NOT_VISIBLE", "UNAVAILABLE", "INVALID"])
def test_unavailable_levels_cannot_be_manufactured(status):
    request = request_for()
    answer = answer_for(request)
    obs = observation(answer, 5)
    obs.update(observation_status=status, ambiguity_reason="Unreadable")
    obs["result"].update(finding="Unavailable", point_price=100)
    reject(request, answer, "MCX_LEVEL_INVALID")


def test_q2_absent_q8_unreadable_and_q9_role_constraints():
    request = request_for()
    answer = answer_for(request)
    observation(answer, 1)["result"]["price_relationship"] = "ABOVE"
    reject(request, answer, "MCX_Q2_INVALID")
    answer = answer_for(request)
    obs = observation(answer, 7)
    obs.update(observation_status="UNAVAILABLE", ambiguity_reason="Panel unreadable")
    mcx.validate_mcx_answer(canonical(answer), request)
    obs["result"]["finding"] = "Invented value"
    reject(request, answer, "MCX_AVAILABILITY_INVALID")
    answer = answer_for(request)
    observation(answer, 8, True)["result"].update(clustering="CLUSTERED", components=["CPR", "OPERATIVE_ANCHOR"])
    reject(request, answer, "MCX_COMPONENT_ROLE_INVALID")


@pytest.mark.parametrize("components,valid", [
    (["CPR", "SMA20"], True), (["CPR"], False), (["CPR", "CPR"], False),
    (["SMA20", "CPR"], False), (["CPR", "UNIDENTIFIED_PLOTTED_STRUCTURE"], False),
])
def test_q9_identifiable_unique_ordered_components(components, valid):
    request = request_for()
    answer = answer_for(request)
    observation(answer, 8)["result"].update(clustering="CLUSTERED", components=components)
    if valid:
        mcx.validate_mcx_answer(canonical(answer), request)
    else:
        reject(request, answer, "MCX_Q9_INVALID")


def test_identity_claim_is_not_overwritten_even_when_other_bindings_are_valid():
    request = request_for()
    answer = answer_for(request)
    observation(answer, 0)["result"]["observed_identity"] = "GOLDM;"
    reject(request, answer, "MCX_IDENTITY_MISMATCH")
    assert observation(answer, 0)["result"]["observed_identity"] == "GOLDM;"


def test_reference_quality_is_enum_only_no_keyword_evaluator_or_consequence():
    request = request_for()
    answer = answer_for(request)
    obs = observation(answer, 4, True)
    obs["result"]["finding"] = "Synthetic narrative is not interpreted by this validator."
    mcx.validate_mcx_answer(canonical(answer), request)
    obs["result"]["promotion"] = "BUY_NOW"
    reject(request, answer, "MCX_AUTHORITY_FIELD_FORBIDDEN")
    del obs["result"]["promotion"]
    obs["result"]["setup_quality"] = "CONFIRMED"
    reject(request, answer, "MCX_ENUM_INVALID")


def test_question_definitions_are_exact_independent_text_and_not_nse_aliases():
    assert mcx.NATIVE_QUESTIONS != mcx.REFERENCE_QUESTIONS
    assert len(mcx.NATIVE_QUESTION_TEXTS) == len(mcx.REFERENCE_QUESTION_TEXTS) == 10
    assert all(text1 != text2 for text1, text2 in zip(mcx.NATIVE_QUESTION_TEXTS, mcx.REFERENCE_QUESTION_TEXTS))
    raw = request_for().value
    raw["questions"][0]["text"] = "A paraphrase"
    with pytest.raises(ReviewEvidenceError, match="MCX_CONTRACT_MISMATCH"):
        mcx.McxNativeVisualRequest.create(raw)


def test_closed_field_phase_precedes_request_binding_validation():
    request = request_for()
    answer = answer_for(request)
    answer["request_reference"]["request_identity"] = "STALE"
    observation(answer, 9, True)["result"]["provider_identity"] = "FORGED"
    reject(request, answer, "MCX_PROVENANCE_FORBIDDEN")
    del observation(answer, 9, True)["result"]["provider_identity"]
    reject(request, answer, "MCX_REQUEST_MISMATCH")


@pytest.mark.parametrize("mode", ["unknown", "duplicate", "missing", "reordered"])
def test_exact_question_count_and_order(mode):
    request = request_for()
    answer = answer_for(request)
    observations = answer["subjects"][0]["responses"][0]["observations"]
    if mode == "unknown":
        observations[0]["question_id"] = "UNKNOWN"
    elif mode == "duplicate":
        observations[1] = deepcopy(observations[0])
    elif mode == "missing":
        observations.pop()
    else:
        observations[0], observations[1] = observations[1], observations[0]
    reject(request, answer, "MCX_QUESTION_COUNT_INVALID" if mode == "missing" else "MCX_QUESTION_ORDER_INVALID")


@pytest.mark.parametrize("field", ["source_chart_identity", "source_chart_revision"])
def test_observation_source_binding_is_independent_of_enclosing_response(field):
    request = request_for()
    answer = answer_for(request)
    observation(answer, 6, True)[field] = "c" * 64 if field.endswith("revision") else "GOLDM"
    reject(request, answer, "MCX_CHART_REVISION_MISMATCH" if field.endswith("revision") else "MCX_IDENTITY_MISMATCH")


@pytest.mark.parametrize("field", ["subject_reference", "native_candidate_reference", "subject_identity"])
def test_malformed_retained_request_is_bounded_not_a_python_type_error(field):
    raw = request_for().value
    raw["subjects"][0][field] = []
    with pytest.raises(ReviewEvidenceError, match="MCX_FIELD_TYPE_INVALID"):
        mcx.McxNativeVisualRequest.create(raw)


@pytest.mark.parametrize("role", (mcx.NATIVE_ROLE, mcx.REFERENCE_ROLE))
def test_printed_successor_q10_unavailable_explanation_matches_validator(monkeypatch, role):
    from io import BytesIO
    from pypdf import PdfReader
    _, native, reference, pdf = _rendered_successor_contract(monkeypatch)
    text = " ".join(" ".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages).split())
    # The exact printed rule must describe the already-enforced successor branch.
    answer = _complete_successor_answer(native, reference)
    root = answer if role == mcx.NATIVE_ROLE else answer["supporting_reference_answer"]
    observation = root["subjects"][0]["responses"][0]["observations"][9]
    observation.update(observation_status="UNAVAILABLE", ambiguity_reason="TEST ONLY: no additional visible fact", why_not_covered_elsewhere=None)
    observation["result"]["finding"] = "UNAVAILABLE"
    request = mcx.mcx_question_pack_from_mappings(native, reference)
    assert mcx.validate_mcx_answer(canonical(answer), request) == answer
    # A nonempty explanation suggested by the old PDF must still reject.
    changed = deepcopy(answer)
    wrong = changed if role == mcx.NATIVE_ROLE else changed["supporting_reference_answer"]
    wrong["subjects"][0]["responses"][0]["observations"][9]["why_not_covered_elsewhere"] = "TEST ONLY: unavailable"
    with pytest.raises(ReviewEvidenceError, match="MCX_Q10_INVALID"):
        mcx.validate_mcx_answer(canonical(changed), request)
    assert "Q10 finding NONE or UNAVAILABLE requires null" in text


def test_legacy_mcx_q10_printed_rule_remains_unchanged():
    from io import BytesIO
    from PIL import Image
    from pypdf import PdfReader
    from kronos.swing.v1.pdf_visual_review_v3_live import render_mcx_successor_question_pdf
    output = BytesIO(); Image.new("RGB", (32, 24), "white").save(output, format="PNG")
    image = output.getvalue(); revision = sha256(image).hexdigest(); pair = []
    for mapping in retained_mappings():
        value = mapping.value
        for subject in value["subjects"]:
            for chart in subject["responses"]: chart["chart_revision_sha256"] = revision
        pair.append(type(mapping).create(value))
    _, _, pdf = render_mcx_successor_question_pdf(*pair, {revision: image})
    text = " ".join(" ".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages).split())
    assert "Q10 finding NONE requires null; otherwise a nonempty explanation" in text
    assert "Q10 finding NONE or UNAVAILABLE requires null" not in text
