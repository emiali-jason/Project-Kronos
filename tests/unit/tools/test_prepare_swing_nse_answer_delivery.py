"""First-attempt Answer delivery checks use only temporary request stores."""

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json

import pytest
from reportlab.pdfgen.canvas import Canvas

from kronos.swing.v1.pdf_visual_review import BEGIN_GOVERNED_ANSWER_DATA, END_GOVERNED_ANSWER_DATA
from kronos.swing.v1.pdf_visual_review_v3_live import extract_successor_answer_pdf
from kronos.swing.v1.review_evidence_binding import (
    NseReviewRequestMapping, ReviewEvidenceError, canonical, nse_pre_render_digest,
)
from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
from swing.v1.test_review_evidence_binding import nse_v2_answer, nse_v2_mapping
from tools.prepare_swing_nse_answer_delivery import deliver_pdf, validate_draft


def _pdf(lines):
    output = BytesIO()
    canvas = Canvas(output, invariant=1)
    canvas.setFont("Courier", 6)
    for index, line in enumerate(lines):
        if index and index % 105 == 0:
            canvas.showPage()
            canvas.setFont("Courier", 6)
        canvas.drawString(18, 810 - (index % 105) * 7, line)
    canvas.save()
    return output.getvalue()


def _question(mapping):
    value = mapping.value
    return _pdf(value[key] for key in
                ("request_identity", "request_sha256", "review_pack_identity", "answer_schema"))


def _published(tmp_path, instrument="RELIANCE", suffix="A", predecessor=None):
    root = tmp_path / "store"
    store = ReviewEvidenceStore(root)
    value = nse_v2_mapping(instrument).value
    value["request_identity"] = "SWING-REVIEW-REQUEST-" + suffix * 32
    value["review_pack_identity"] = "KRONOS-V3-REVIEW-" + suffix * 32
    value["request_sha256"] = nse_pre_render_digest(value)
    preliminary = NseReviewRequestMapping.create(value)
    question = _question(preliminary)
    value["review_pack_sha256"] = sha256(question).hexdigest()
    mapping = NseReviewRequestMapping.create(value)
    published = store.publish_nse_request(mapping, question,
        publication_timestamp="2026-09-21T00:00:00.000000Z",
        expected_predecessor=predecessor, recheck=lambda *_: None)
    question_path = tmp_path / (value["review_pack_identity"] + "_QUESTIONS.pdf")
    question_path.write_bytes(question)
    return root, mapping, published, question_path


def _answer_file(tmp_path, mapping, visible="Reliance Industries Limited"):
    answer = nse_v2_answer(mapping)
    for response in answer["subjects"][0]["responses"]:
        response["observations"][0]["observed_instrument"] = visible
    path = tmp_path / "draft.json"
    path.write_bytes(canonical(answer))
    return answer, path


def _answer_pdf(tmp_path, answer):
    body = [BEGIN_GOVERNED_ANSWER_DATA, *json.dumps(answer, indent=2).splitlines(),
            END_GOVERNED_ANSWER_DATA]
    path = tmp_path / "draft.pdf"
    path.write_bytes(_pdf(body))
    return path


def test_reliance_raw_visible_name_is_distinct_from_all_40_governed_echoes(tmp_path):
    root, mapping, _, question = _published(tmp_path)
    answer, json_path = _answer_file(tmp_path, mapping)
    assert answer["subjects"][0]["canonical_instrument"] == "RELIANCE"
    assert answer["subjects"][0]["responses"][0]["observations"][0]["observed_instrument"] == "Reliance Industries Limited"
    assert {item["source_chart_identity"] for response in answer["subjects"][0]["responses"]
            for item in response["observations"]} == {"RELIANCE"}
    draft = validate_draft(root, question, json_path)
    pdf = _answer_pdf(tmp_path, answer)
    destination = tmp_path / (draft.pack_identity + "_ANSWERS.pdf")
    assert deliver_pdf(root, draft, pdf, destination) == sha256(pdf.read_bytes()).hexdigest()
    assert destination.read_bytes() == pdf.read_bytes()
    assert json.loads(extract_successor_answer_pdf(destination.read_bytes())) == answer
    with pytest.raises(ReviewEvidenceError, match="ANSWER_DELIVERY_ALREADY_EXISTS"):
        deliver_pdf(root, draft, pdf, destination)


def test_first_attempt_company_name_in_any_source_echo_is_rejected_before_delivery(tmp_path):
    root, mapping, _, question = _published(tmp_path)
    answer, json_path = _answer_file(tmp_path, mapping)
    observations = [item for response in answer["subjects"][0]["responses"]
                    for item in response["observations"]]
    assert len(observations) == 40
    for index in range(40):
        for field, bad in (("source_chart_identity", "Reliance Industries Limited"),
                           ("source_chart_revision", "d" * 64)):
            changed = deepcopy(answer)
            changed["subjects"][0]["responses"][index // 10]["observations"][index % 10][field] = bad
            json_path.write_bytes(canonical(changed))
            with pytest.raises(ReviewEvidenceError) as caught:
                validate_draft(root, question, json_path)
            assert caught.value.code == "REVIEW_REQUEST_MISMATCH"
            assert caught.value.path == f"$.subjects[0].responses[{index // 10}].observations[{index % 10}]"
    assert not list(tmp_path.glob("*_ANSWERS.pdf"))


def test_m_and_m_punctuation_and_lowercase_visible_timeframe_remain_raw(tmp_path):
    root, mapping, _, question = _published(tmp_path, "M&M")
    answer, json_path = _answer_file(tmp_path, mapping, "M and M Ltd")
    visible = ("1w", "1d", "4h", "1h")
    for response, raw in zip(answer["subjects"][0]["responses"], visible, strict=True):
        response["observations"][0]["observed_timeframe"] = raw
    json_path.write_bytes(canonical(answer))
    validate_draft(root, question, json_path)
    assert [r["observations"][0]["observed_timeframe"] for r in answer["subjects"][0]["responses"]] == list(visible)
    assert all(r["chart_identity"] == "M&M" and all(o["source_chart_identity"] == "M&M" for o in r["observations"])
               for r in answer["subjects"][0]["responses"])
    changed = deepcopy(answer)
    changed["subjects"][0]["responses"][0]["chart_identity"] = "M and M"
    json_path.write_bytes(canonical(changed))
    with pytest.raises(ReviewEvidenceError, match="REVIEW_REQUEST_MISMATCH"):
        validate_draft(root, question, json_path)
    changed = deepcopy(answer)
    changed["subjects"][0]["responses"][0]["timeframe"] = "weekly"
    json_path.write_bytes(canonical(changed))
    with pytest.raises(ReviewEvidenceError, match="REVIEW_REQUEST_MISMATCH"):
        validate_draft(root, question, json_path)


@pytest.mark.parametrize("change", ["canonical", "response_revision", "source_revision", "why_q1",
                                     "why_q10_none", "question_order", "extra_field"])
def test_closed_contract_and_all_binding_checks_precede_delivery(tmp_path, change):
    root, mapping, _, question = _published(tmp_path)
    answer, json_path = _answer_file(tmp_path, mapping)
    subject = answer["subjects"][0]
    response = subject["responses"][0]
    observation = response["observations"][0]
    if change == "canonical":
        subject["canonical_instrument"] = "Reliance Industries Limited"
    elif change == "response_revision":
        response["chart_revision_sha256"] = "d" * 64
    elif change == "source_revision":
        observation["source_chart_revision"] = "d" * 64
    elif change == "why_q1":
        observation["why_not_covered_elsewhere"] = "not null"
    elif change == "why_q10_none":
        response["observations"][9]["why_not_covered_elsewhere"] = "not null"
    elif change == "question_order":
        response["observations"][0], response["observations"][1] = response["observations"][1], response["observations"][0]
    else:
        observation["unexpected"] = "closed"
    json_path.write_bytes(canonical(answer))
    with pytest.raises(ReviewEvidenceError):
        validate_draft(root, question, json_path)
    assert not list(tmp_path.glob("*_ANSWERS.pdf"))


def test_every_q1_to_q9_why_field_must_be_null(tmp_path):
    root, mapping, _, question = _published(tmp_path)
    answer, json_path = _answer_file(tmp_path, mapping)
    for response_index in range(4):
        for question_index in range(9):
            changed = deepcopy(answer)
            changed["subjects"][0]["responses"][response_index]["observations"][question_index]["why_not_covered_elsewhere"] = "unapproved"
            json_path.write_bytes(canonical(changed))
            with pytest.raises(ReviewEvidenceError) as caught:
                validate_draft(root, question, json_path)
            assert caught.value.code == "REVIEW_OBSERVATION_INVALID"
    assert not list(tmp_path.glob("*_ANSWERS.pdf"))


def test_stale_request_and_rendered_pdf_mismatch_never_deliver(tmp_path):
    root, mapping, current, question = _published(tmp_path)
    answer, json_path = _answer_file(tmp_path, mapping)
    draft = validate_draft(root, question, json_path)
    destination = tmp_path / (draft.pack_identity + "_ANSWERS.pdf")
    changed = deepcopy(answer)
    changed["answer_identity"] = "OTHER-ANSWER"
    mismatched_pdf = _answer_pdf(tmp_path, changed)
    with pytest.raises(ReviewEvidenceError, match="ANSWER_DELIVERY_CONTENT_MISMATCH"):
        deliver_pdf(root, draft, mismatched_pdf, destination)
    assert not destination.exists()
    exact_pdf = _answer_pdf(tmp_path, answer)
    _published(tmp_path, suffix="B", predecessor=current.identity)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        deliver_pdf(root, draft, exact_pdf, destination)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_REQUEST_MISMATCH"):
        validate_draft(root, question, json_path)  # old pack filename is not current
    assert not destination.exists()
