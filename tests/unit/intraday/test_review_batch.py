from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
import re
from pypdf import PdfReader

from kronos.application.intraday_review import (
    IntradayReviewBatchMemberState,
    IntradayReviewBatchState,
)
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.review import QUESTIONS
from kronos.intraday.review_batch import batch_artifact_bytes, batch_from_bytes
from kronos.intraday.review_transport import review_batch_stem
from kronos.intraday.review_persistence import IntradayReviewStore
from tests.unit.intraday.test_historical_semantic import BOUNDARY
from tests.unit.intraday.test_probables import _member, _run
from tests.unit.intraday.test_review import _application, _png


def _three_candidate_application(tmp_path: Path):  # type: ignore[no-untyped-def]
    run = _run((
        _member("WIPRO", hourly=SemanticDirection.SHORT, fifteen=SemanticDirection.SHORT),
        _member("LICI"),
        _member("RELIANCE"),
    ))
    current = [run]
    application = _application(tmp_path, current)
    cycles = {
        candidate.canonical_subject_identity: application.start_review(candidate.probable_result_identity)
        for candidate in application.snapshot().candidates
    }
    return run, current, application, cycles


def test_batch_creates_ready_members_skips_chart_required_and_is_idempotent(tmp_path: Path) -> None:
    run, _, application, cycles = _three_candidate_application(tmp_path)
    application.upload_chart(cycles["LICI"].cycle_identity, media_type="image/png", payload=_png(10))
    application.upload_chart(cycles["WIPRO"].cycle_identity, media_type="image/png", payload=_png(20))
    unrelated = tmp_path / "questions" / "UNRELATED.txt"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("preserve", encoding="utf-8")

    first = application.create_all_question_packs()
    assert first.state is IntradayReviewBatchState.COMPLETE_WITH_SKIPS
    assert first.created_count == 2 and first.reused_count == 0
    assert first.skipped_count == 1 and first.failed_count == 0
    assert tuple(item.canonical_subject_identity for item in first.members) == ("LICI", "RELIANCE", "WIPRO")
    assert next(item for item in first.members if item.canonical_subject_identity == "RELIANCE").state is IntradayReviewBatchMemberState.SKIPPED_CHART_REQUIRED
    assert first.batch_identity is not None and first.batch_filename is not None
    assert re.fullmatch(
        r"KRONOS_INTRADAY_REVIEW_20260817_153030_IST_[0-9A-F]{8}_QUESTIONS\.pdf",
        first.batch_filename,
    )
    combined_path = tmp_path / "questions" / first.batch_filename
    first_payload = combined_path.read_bytes()
    text = "\n".join(page.extract_text() or "" for page in PdfReader(combined_path).pages)
    normalized_text = re.sub(r"\s+", " ", text)
    assert text.count("LICI") == text.count("WIPRO") == 2
    assert "RELIANCE" not in text
    assert text.count(cycles["LICI"].cycle_identity) == 2
    assert text.count(cycles["WIPRO"].cycle_identity) == 2
    assert text.count(application.store.load_pack(
        next(item.review_pack_identity for item in first.members if item.canonical_subject_identity == "LICI") or ""
    ).review_request_identity) >= 1
    assert "EXACT COMBINED ANSWER CONTRACT" in text
    assert "one combined JSON Answer Pack" in normalized_text
    assert "REQUIRED ANSWER FILENAME" in text
    assert "Do not return individual files" in normalized_text
    assert len(tuple((tmp_path / "questions").glob("*.pdf"))) == 1
    for question in QUESTIONS:
        assert normalized_text.count(question.wording) == 2
    assert unrelated.read_text(encoding="utf-8") == "preserve"

    repeated = application.create_all_question_packs()
    assert repeated.state is IntradayReviewBatchState.COMPLETE_WITH_SKIPS
    assert repeated.created_count == 0 and repeated.reused_count == 2
    assert repeated.batch_identity == first.batch_identity
    assert repeated.batch_filename == first.batch_filename
    assert combined_path.read_bytes() == first_payload
    restored = _application(tmp_path, [run]).snapshot()
    assert restored.current_batch_identity == first.batch_identity
    assert restored.current_batch_filename == first.batch_filename
    assert restored.current_batch_answer_filename is not None
    assert restored.current_batch_filename.removesuffix("_QUESTIONS.pdf") == (
        restored.current_batch_answer_filename.removesuffix("_ANSWERS.json")
    )
    assert restored.current_batch_generated_at is not None
    assert restored.current_batch_candidate_count == 2


def test_batch_all_ready_new_revision_and_persisted_contract(tmp_path: Path) -> None:
    run, _, application, cycles = _three_candidate_application(tmp_path)
    for index, subject in enumerate(sorted(cycles), start=1):
        application.upload_chart(cycles[subject].cycle_identity, media_type="image/png", payload=_png(index))
    first = application.create_all_question_packs()
    assert first.state is IntradayReviewBatchState.COMPLETE
    assert first.created_count == 3 and first.skipped_count == 0
    wipro_first = next(item for item in first.members if item.canonical_subject_identity == "WIPRO")
    assert wipro_first.review_pack_identity is not None

    chart_two = application.upload_chart(
        cycles["WIPRO"].cycle_identity,
        media_type="image/png",
        payload=_png(99),
    )
    second = application.create_all_question_packs()
    wipro_second = next(item for item in second.members if item.canonical_subject_identity == "WIPRO")
    assert second.state is IntradayReviewBatchState.COMPLETE
    assert second.created_count == 1 and second.reused_count == 2
    assert wipro_second.review_pack_identity != wipro_first.review_pack_identity
    assert second.batch_identity != first.batch_identity
    assert chart_two.revision_ordinal == 2

    store = IntradayReviewStore((tmp_path / "evidence").resolve())
    retained = store.load_batch(second.batch_identity or "")
    assert batch_from_bytes(batch_artifact_bytes(retained)) == retained
    assert retained.probables_run_identity == run.run_identity
    assert tuple(item.canonical_subject_identity for item in retained.members) == ("LICI", "RELIANCE", "WIPRO")
    assert store.load_pack(wipro_first.review_pack_identity).review_pack_identity == wipro_first.review_pack_identity
    transport = store.load_batch_transport_if_present(retained.batch_identity)
    assert transport is not None
    assert transport.question_filename == second.batch_filename
    assert transport.question_filename == f"{review_batch_stem(transport)}_QUESTIONS.pdf"
    assert transport.expected_answer_filename == f"{review_batch_stem(transport)}_ANSWERS.json"


def test_batch_zero_ready_new_run_and_direction_flip_fail_closed(tmp_path: Path) -> None:
    run_a = _run((_member("WIPRO", hourly=SemanticDirection.SHORT, fifteen=SemanticDirection.SHORT),))
    current = [run_a]
    application = _application(tmp_path, current)
    cycle_a = application.start_review(run_a.results[0].result_identity)
    assert application.create_all_question_packs().state is IntradayReviewBatchState.NO_ELIGIBLE_REVIEW_PACKS
    application.upload_chart(cycle_a.cycle_identity, media_type="image/png", payload=_png(1))
    batch_a = application.create_all_question_packs()
    assert batch_a.state is IntradayReviewBatchState.COMPLETE

    boundary_b = BOUNDARY + timedelta(minutes=5)
    run_b = _run((_member("WIPRO", boundary=boundary_b),), boundary=boundary_b)
    current[0] = run_b
    batch_b = application.create_all_question_packs()
    assert batch_b.state is IntradayReviewBatchState.NO_ELIGIBLE_REVIEW_PACKS
    assert batch_b.probables_run_identity == run_b.run_identity
    assert batch_b.members[0].cycle_identity is None
    assert batch_b.members[0].state is IntradayReviewBatchMemberState.SKIPPED_CHART_REQUIRED
    assert _application(tmp_path, current).snapshot().current_batch_identity is None


def test_batch_partial_integrity_failure_is_candidate_isolated(tmp_path: Path) -> None:
    _, _, application, cycles = _three_candidate_application(tmp_path)
    lici_chart = application.upload_chart(cycles["LICI"].cycle_identity, media_type="image/png", payload=_png(3))
    application.upload_chart(cycles["WIPRO"].cycle_identity, media_type="image/png", payload=_png(4))
    store = IntradayReviewStore((tmp_path / "evidence").resolve())
    (store.root / "chart-revisions" / f"{lici_chart.chart_revision_identity}.json").unlink()

    result = application.create_all_question_packs()
    assert result.state is IntradayReviewBatchState.PARTIAL
    lici = next(item for item in result.members if item.canonical_subject_identity == "LICI")
    wipro = next(item for item in result.members if item.canonical_subject_identity == "WIPRO")
    assert lici.state is IntradayReviewBatchMemberState.FAILED
    assert wipro.state is IntradayReviewBatchMemberState.CREATED
    assert wipro.review_pack_identity is not None
    assert result.batch_identity is not None and result.batch_filename is not None


def test_overlapping_batch_operations_reuse_exact_immutable_outputs(tmp_path: Path) -> None:
    _, _, application, cycles = _three_candidate_application(tmp_path)
    for index, subject in enumerate(sorted(cycles), start=1):
        application.upload_chart(cycles[subject].cycle_identity, media_type="image/png", payload=_png(index + 40))
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: application.create_all_question_packs(), range(2)))
    assert results[0].batch_identity == results[1].batch_identity
    assert results[0].batch_filename == results[1].batch_filename
    assert {result.created_count for result in results} == {0, 3}
    assert {result.reused_count for result in results} == {0, 3}
    assert len(tuple((tmp_path / "questions").glob("KRONOS_INTRADAY_REVIEW_*_QUESTIONS.pdf"))) == 1
