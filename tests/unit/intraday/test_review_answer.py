from __future__ import annotations

import json
from pathlib import Path

import pytest

from kronos.intraday.review import ObservationStatus, ReviewError, ReviewFailure
from kronos.intraday.review_answer import (
    ANSWER_PACK_IDENTITY,
    BATCH_ANSWER_PACK_IDENTITY,
    AnswerImportState,
    answer_pack_filename,
    answer_pack_template,
    batch_answer_pack_filename,
    batch_answer_pack_template,
    parse_batch_answer_transport,
    parse_answer_pack,
)
from tests.unit.intraday.test_probables import _member, _run
from tests.unit.intraday.test_review import _application, _png


def _ready(tmp_path: Path, subjects: tuple[str, ...] = ("WIPRO",)):  # type: ignore[no-untyped-def]
    run = _run(tuple(_member(subject) for subject in subjects))
    current = [run]
    application = _application(tmp_path, current)
    packs = {}
    cycles = {}
    for result in run.results:
        cycle = application.start_review(result.result_identity)
        application.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(len(cycles) + 1))
        pack, _ = application.create_question_pack(cycle.cycle_identity)
        packs[result.canonical_subject_identity] = pack
        cycles[result.canonical_subject_identity] = cycle
    return current, application, packs, cycles


def _document(pack):  # type: ignore[no-untyped-def]
    document = json.loads(answer_pack_template(pack))
    document["observed_visible_subject_identity"] = pack.expected_canonical_subject_identity
    document["global_observation_status"] = "OBSERVED"
    for question, answer in zip(pack.questions, document["answers"], strict=True):
        answer.update(
            observation_status="OBSERVED",
            answer=question.allowed_answers[0],
            visible_timeframes=list(question.timeframe_scope),
            visible_basis="Concise visible chart basis.",
            status_detail=None,
        )
    return document


def _write(tmp_path: Path, pack, document: dict) -> Path:  # type: ignore[no-untyped-def]
    target = tmp_path / "answers" / answer_pack_filename(pack)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def _batch_document(application, packs: dict):  # type: ignore[no-untyped-def]
    result = application.create_all_question_packs()
    assert result.batch_identity is not None
    batch = application.store.load_batch(result.batch_identity)
    ordered = tuple(packs[member.canonical_subject_identity] for member in batch.members)
    return batch, json.loads(batch_answer_pack_template(batch, ordered))


def test_valid_answer_binds_exact_identity_persists_and_restarts(tmp_path: Path) -> None:
    current, application, packs, cycles = _ready(tmp_path)
    pack = packs["WIPRO"]
    document = _document(pack)
    document["answers"][6]["answer"] = "PRESENT"
    document["answers"][6]["visible_basis"] = "Visible overhead shelf on both 15M and 5M panels."
    _write(tmp_path, pack, document)

    result = application.import_answer(cycles["WIPRO"].cycle_identity)
    assert result.state is AnswerImportState.IMPORTED
    assert result.answer_pack_identity and result.visual_evidence_identity
    snapshot = application.snapshot().candidates[0]
    assert snapshot.answer_state == "IMPORTED"
    assert snapshot.visual_state == ObservationStatus.OBSERVED.value
    assert snapshot.observed_visible_subject_identity == "WIPRO"
    assert snapshot.visual_evidence_identity == result.visual_evidence_identity

    restored = _application(tmp_path, current)
    replay = restored.import_answer(cycles["WIPRO"].cycle_identity)
    assert replay.state is AnswerImportState.ALREADY_IMPORTED
    assert replay.visual_evidence_identity == result.visual_evidence_identity
    assert restored.snapshot().provider_operations == 0


@pytest.mark.parametrize(
    ("mutation", "failure"),
    (
        (lambda value: value.update(observed_visible_subject_identity="TCS"), ReviewFailure.ANSWER_IDENTITY_MISMATCH),
        (lambda value: value.update(observed_visible_subject_identity=None), ReviewFailure.ANSWER_IDENTITY_MISMATCH),
        (lambda value: value.update(review_pack_identity="INTRADAY-REVIEW-PACK-WRONG"), ReviewFailure.ANSWER_IDENTITY_MISMATCH),
        (lambda value: value.update(review_cycle_identity="INTRADAY-REVIEW-CYCLE-WRONG"), ReviewFailure.ANSWER_IDENTITY_MISMATCH),
        (lambda value: value.update(chart_revision_identity="INTRADAY-CHART-REVISION-WRONG"), ReviewFailure.ANSWER_IDENTITY_MISMATCH),
        (lambda value: value.update(proposed_direction="SHORT"), ReviewFailure.ANSWER_IDENTITY_MISMATCH),
        (lambda value: value.update(question_set_identity="WRONG"), ReviewFailure.ANSWER_SCHEMA_INVALID),
        (lambda value: value.update(trading_decision="BUY"), ReviewFailure.ANSWER_SCHEMA_INVALID),
        (lambda value: value["answers"].pop(), ReviewFailure.ANSWER_SCHEMA_INVALID),
        (lambda value: value["answers"].append(dict(value["answers"][0])), ReviewFailure.ANSWER_SCHEMA_INVALID),
        (lambda value: value["answers"][0].update(observation_status="UNCLEAR"), ReviewFailure.ANSWER_SCHEMA_INVALID),
    ),
)
def test_cross_identity_unknown_fields_missing_duplicate_and_invalid_status_fail_closed(
    tmp_path: Path, mutation, failure: ReviewFailure,  # type: ignore[no-untyped-def]
) -> None:
    _, application, packs, cycles = _ready(tmp_path)
    document = _document(packs["WIPRO"])
    mutation(document)
    _write(tmp_path, packs["WIPRO"], document)
    result = application.import_answer(cycles["WIPRO"].cycle_identity)
    expected = (
        AnswerImportState.IDENTITY_MISMATCH
        if failure is ReviewFailure.ANSWER_IDENTITY_MISMATCH
        else AnswerImportState.SCHEMA_INVALID
    )
    assert result.state is expected and result.detail == failure.value
    assert application.snapshot().candidates[0].visual_evidence_identity is None


def test_status_visible_basis_q7_and_q10_discipline(tmp_path: Path) -> None:
    _, _, packs, _ = _ready(tmp_path)
    pack = packs["WIPRO"]
    document = _document(pack)
    document["answers"][6].update(answer="PRESENT", visible_basis=None)
    with pytest.raises(ReviewError, match=ReviewFailure.ANSWER_SCHEMA_INVALID.value):
        parse_answer_pack(json.dumps(document).encode())

    document = _document(pack)
    document["answers"][9].update(
        answer="MATERIAL_OBSERVATION",
        visible_basis="A visible condition spans the 1H and 15M panels.",
        why_not_covered_elsewhere=None,
    )
    with pytest.raises(ReviewError, match=ReviewFailure.ANSWER_SCHEMA_INVALID.value):
        parse_answer_pack(json.dumps(document).encode())

    document["answers"][9]["why_not_covered_elsewhere"] = "It is outside the bounded subjects of Q1-Q9."
    assert parse_answer_pack(json.dumps(document).encode()).answers[-1].answer == "MATERIAL_OBSERVATION"


def test_each_exact_q1_to_q10_enum_is_enforced(tmp_path: Path) -> None:
    _, _, packs, _ = _ready(tmp_path)
    pack = packs["WIPRO"]
    for index, question in enumerate(pack.questions):
        document = _document(pack)
        document["answers"][index]["answer"] = question.allowed_answers[-1]
        if question.question_id == "Q10" and question.allowed_answers[-1] == "MATERIAL_OBSERVATION":
            document["answers"][index]["why_not_covered_elsewhere"] = "Not represented by Q1-Q9."
        assert parse_answer_pack(json.dumps(document).encode()).answers[index].answer == question.allowed_answers[-1]
        document["answers"][index]["answer"] = "UNAUTHORIZED_ENUM"
        with pytest.raises(ReviewError, match=ReviewFailure.ANSWER_SCHEMA_INVALID.value):
            parse_answer_pack(json.dumps(document).encode())


def test_partial_and_absent_statuses_preserve_scope_without_invented_confidence(tmp_path: Path) -> None:
    _, _, packs, _ = _ready(tmp_path)
    document = _document(packs["WIPRO"])
    document["global_observation_status"] = "PARTIAL"
    document["answers"][6].update(
        observation_status="PARTIAL",
        visible_timeframes=["15M"],
        visible_basis="15M obstacle is visible; 5M panel is cropped.",
        status_detail="5M panel not fully visible.",
    )
    pack = parse_answer_pack(json.dumps(document).encode())
    assert pack.global_observation_status is ObservationStatus.PARTIAL
    assert pack.answers[6].visible_timeframes == ("15M",)
    assert "confidence" not in answer_pack_template(packs["WIPRO"]).decode()

    document["answers"][6].update(
        observation_status="NOT_VISIBLE", answer=None, visible_timeframes=[],
        visible_basis=None, status_detail=None,
    )
    with pytest.raises(ReviewError, match=ReviewFailure.ANSWER_SCHEMA_INVALID.value):
        parse_answer_pack(json.dumps(document).encode())


def test_invalid_answer_never_blanks_prior_trusted_evidence(tmp_path: Path) -> None:
    current, application, packs, cycles = _ready(tmp_path)
    pack, cycle = packs["WIPRO"], cycles["WIPRO"]
    target = _write(tmp_path, pack, _document(pack))
    first = application.import_answer(cycle.cycle_identity)
    target.write_text("not-json", encoding="utf-8")
    second = application.import_answer(cycle.cycle_identity)
    assert first.state is AnswerImportState.IMPORTED
    assert second.state is AnswerImportState.SCHEMA_INVALID
    assert application.snapshot().candidates[0].visual_evidence_identity == first.visual_evidence_identity

    persisted = next((tmp_path / "evidence" / "answer-packs").glob("*.json"))
    persisted.write_bytes(persisted.read_bytes().replace(b"SUPPORTIVE", b"OPPOSING", 1))
    with pytest.raises(ReviewError, match=ReviewFailure.INTEGRITY_INVALID.value):
        _application(tmp_path, current).snapshot()


def test_exact_inbox_file_safety_missing_symlink_and_oversize(tmp_path: Path) -> None:
    _, application, packs, cycles = _ready(tmp_path)
    pack, cycle = packs["WIPRO"], cycles["WIPRO"]
    missing = application.import_answer(cycle.cycle_identity)
    assert missing.state is AnswerImportState.MISSING

    outside = tmp_path / "outside.json"
    outside.write_bytes(answer_pack_template(pack))
    target = tmp_path / "answers" / answer_pack_filename(pack)
    target.symlink_to(outside)
    linked = application.import_answer(cycle.cycle_identity)
    assert linked.state is AnswerImportState.INVALID
    target.unlink()
    target.write_bytes(b"x" * (1024 * 1024 + 1))
    oversized = application.import_answer(cycle.cycle_identity)
    assert oversized.state is AnswerImportState.SCHEMA_INVALID


def test_batch_is_deterministic_candidate_isolated_and_does_not_scan_unrelated_files(tmp_path: Path) -> None:
    _, application, packs, cycles = _ready(tmp_path, ("WIPRO", "LICI"))
    batch_contract, document = _batch_document(application, packs)
    documents = {pack.review_pack_identity: _document(pack) for pack in packs.values()}
    document["candidates"] = [documents[item.review_pack_identity] for item in reversed(batch_contract.members)]
    target = tmp_path / "answers" / batch_answer_pack_filename(batch_contract)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document), encoding="utf-8")
    unrelated = tmp_path / "answers" / "ARBITRARY.json"
    unrelated.write_text("{}", encoding="utf-8")
    batch = application.import_all_answers()
    assert tuple(item.canonical_subject_identity for item in batch.members) == ("LICI", "WIPRO")
    assert batch.eligible_candidates == 2 and batch.files_discovered == 2
    assert batch.count(AnswerImportState.IMPORTED) == 2
    assert batch.answer_filename == target.name and batch.transport_state == "COMPLETE"
    assert unrelated.read_text(encoding="utf-8") == "{}"
    assert application.snapshot().candidates[0].cycle_identity == cycles["LICI"].cycle_identity


def test_combined_two_candidate_contract_is_strict_order_independent_idempotent_and_restores(tmp_path: Path) -> None:
    current, application, packs, _ = _ready(
        tmp_path, ("NSE-EQ-RBLBANK", "NSE-INDEX-BANKNIFTY"),
    )
    batch, document = _batch_document(application, packs)
    assert document["schema_identity"] == BATCH_ANSWER_PACK_IDENTITY
    assert document["review_batch_identity"] == batch.batch_identity
    document["candidates"] = [
        _document(packs["NSE-INDEX-BANKNIFTY"]),
        _document(packs["NSE-EQ-RBLBANK"]),
    ]
    payload = json.dumps(document).encode()
    parsed = parse_batch_answer_transport(payload)
    assert parsed.review_batch_identity == batch.batch_identity

    first = application.import_all_answers(media_type="application/json", payload=payload)
    assert first.transport_state == "COMPLETE"
    assert first.count(AnswerImportState.IMPORTED) == 2
    second = application.import_all_answers(media_type="application/json", payload=payload)
    assert second.count(AnswerImportState.ALREADY_IMPORTED) == 2
    assert len(tuple((tmp_path / "evidence" / "visual-evidence").glob("*.json"))) == 2
    assert len(tuple((tmp_path / "evidence" / "batch-answer-transports").glob("*.json"))) == 1

    restored = _application(tmp_path, current)
    restored_candidates = restored.snapshot().candidates
    assert all(item.answer_state == "IMPORTED" for item in restored_candidates)
    assert {item.observed_visible_subject_identity for item in restored_candidates} == {
        "NSE-EQ-RBLBANK", "NSE-INDEX-BANKNIFTY",
    }


def test_combined_candidate_validation_isolated_for_schema_and_identity_failures(tmp_path: Path) -> None:
    _, application, packs, _ = _ready(
        tmp_path, ("NSE-EQ-RBLBANK", "NSE-INDEX-BANKNIFTY"),
    )
    _, document = _batch_document(application, packs)
    rblbank = _document(packs["NSE-EQ-RBLBANK"])
    banknifty = _document(packs["NSE-INDEX-BANKNIFTY"])
    banknifty["answers"][0].pop("status_detail")
    document["candidates"] = [banknifty, rblbank]
    result = application.import_all_answers(
        media_type="application/json", payload=json.dumps(document).encode(),
    )
    states = {item.canonical_subject_identity: item.state for item in result.members}
    assert states == {
        "NSE-EQ-RBLBANK": AnswerImportState.IMPORTED,
        "NSE-INDEX-BANKNIFTY": AnswerImportState.SCHEMA_INVALID,
    }
    assert result.transport_state == "PARTIAL"


@pytest.mark.parametrize("field", ("review_cycle_identity", "chart_revision_identity", "observed_visible_subject_identity"))
def test_combined_wrong_exact_candidate_identity_fails_closed(tmp_path: Path, field: str) -> None:
    _, application, packs, _ = _ready(tmp_path, ("NSE-EQ-RBLBANK", "NSE-INDEX-BANKNIFTY"))
    _, document = _batch_document(application, packs)
    candidates = [_document(pack) for pack in packs.values()]
    candidates[0][field] = "WRONG"
    document["candidates"] = candidates
    result = application.import_all_answers(media_type="application/json", payload=json.dumps(document).encode())
    states = {item.canonical_subject_identity: item.state for item in result.members}
    assert states[candidates[0]["expected_canonical_subject_identity"]] is AnswerImportState.IDENTITY_MISMATCH
    assert tuple(states.values()).count(AnswerImportState.IMPORTED) == 1


@pytest.mark.parametrize("case", ("missing", "extra", "duplicate"))
def test_combined_population_anomalies_are_accounted_without_order_association(tmp_path: Path, case: str) -> None:
    _, application, packs, _ = _ready(tmp_path, ("NSE-EQ-RBLBANK", "NSE-INDEX-BANKNIFTY"))
    _, document = _batch_document(application, packs)
    candidates = [_document(pack) for pack in packs.values()]
    if case == "missing":
        candidates.pop()
    elif case == "extra":
        extra = dict(candidates[0])
        extra["review_pack_identity"] = "INTRADAY-REVIEW-PACK-EXTRA"
        candidates.append(extra)
    else:
        candidates.append(dict(candidates[0]))
    document["candidates"] = candidates
    result = application.import_all_answers(media_type="application/json", payload=json.dumps(document).encode())
    assert result.transport_state == "PARTIAL"
    if case == "missing":
        assert result.count(AnswerImportState.MISSING) == 1
    elif case == "extra":
        assert result.extra_candidates == 1 and result.count(AnswerImportState.IMPORTED) == 2
    else:
        assert result.duplicate_candidates == 1
        assert result.count(AnswerImportState.SCHEMA_INVALID) == 1
        assert result.count(AnswerImportState.IMPORTED) == 1


def test_combined_changed_content_conflicts_only_with_exact_bound_candidate(tmp_path: Path) -> None:
    _, application, packs, _ = _ready(tmp_path, ("NSE-EQ-RBLBANK", "NSE-INDEX-BANKNIFTY"))
    _, document = _batch_document(application, packs)
    document["candidates"] = [_document(pack) for pack in packs.values()]
    assert application.import_all_answers(
        media_type="application/json", payload=json.dumps(document).encode(),
    ).count(AnswerImportState.IMPORTED) == 2
    changed = next(
        item for item in document["candidates"]
        if item["expected_canonical_subject_identity"] == "NSE-EQ-RBLBANK"
    )
    changed["answers"][0]["answer"] = packs["NSE-EQ-RBLBANK"].questions[0].allowed_answers[-1]
    result = application.import_all_answers(
        media_type="application/json", payload=json.dumps(document).encode(),
    )
    states = {item.canonical_subject_identity: item.state for item in result.members}
    assert states["NSE-EQ-RBLBANK"] is AnswerImportState.CONFLICT
    assert states["NSE-INDEX-BANKNIFTY"] is AnswerImportState.ALREADY_IMPORTED


def test_answer_pack_contract_is_visual_only_and_has_no_internal_or_trading_fields(tmp_path: Path) -> None:
    _, _, packs, _ = _ready(tmp_path)
    document = _document(packs["WIPRO"])
    assert document["schema_identity"] == ANSWER_PACK_IDENTITY
    prohibited = {"probables_run_identity", "provider_token", "machine_hash", "entry", "stop", "target", "risk", "paper", "live"}
    assert prohibited.isdisjoint(document)
    assert tuple(item["question_id"] for item in document["answers"]) == tuple(f"Q{index}" for index in range(1, 11))
    blank = json.loads(answer_pack_template(packs["WIPRO"]))
    assert blank["observed_visible_subject_identity"] is None
    assert all(item["answer"] is None for item in blank["answers"])


def test_current_rblbank_legacy_response_shape_remains_schema_invalid(tmp_path: Path) -> None:
    _, _, packs, _ = _ready(tmp_path, ("NSE-EQ-RBLBANK",))
    pack = packs["NSE-EQ-RBLBANK"]
    received = {
        "schema": ANSWER_PACK_IDENTITY,
        "schema_version": "1.0.0",
        "review_pack_identity": pack.review_pack_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "chart_revision": pack.chart_revision_identity,
        "expected_canonical_instrument": pack.expected_canonical_subject_identity,
        "observed_chart_instrument": pack.expected_canonical_subject_identity,
        "answers": [{"question_id": f"Q{index}", "answer": "NEUTRAL"} for index in range(1, 11)],
    }
    with pytest.raises(ReviewError, match=ReviewFailure.ANSWER_SCHEMA_INVALID.value):
        parse_answer_pack(json.dumps(received).encode())
