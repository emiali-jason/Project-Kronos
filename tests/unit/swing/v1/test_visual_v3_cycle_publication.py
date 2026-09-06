"""WO-SWING-V3-UPLOAD-ENG-02: isolated, deterministic publication proofs.

All evidence is generated under pytest tmp_path. No production store, Provider,
Chart Analyst, or live Browser is used.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import Barrier, Event
from types import SimpleNamespace

from pypdf import PdfReader
import pytest

from kronos.application.swing_visual_v3_live import SwingVisualV3LiveWorkflow
from kronos.swing.v1.pdf_visual_review import PdfReviewTransportError
from kronos.swing.v1.pdf_visual_review_v3_live import (
    VisualV3PdfRecordStore,
    VisualV3PdfReviewTransport,
    _pack_from_dict,
    _validate_answer,
)
import kronos.swing.v1.pdf_visual_review_v3_live as transport_module
from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf, _live, _payload


def _prepared(native, facts, live):
    return live._prepare(native.snapshot(), facts, native.original_chart_bytes, None)[0]


def _later(prepared):
    # Two distinct requests within the SAME filename timestamp second.
    return tuple(tuple(replace(r, request_timestamp=r.request_timestamp + timedelta(microseconds=1))
                       for r in requests) for requests in prepared)


def _digests(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def _assert_binding(record, store):
    payload = Path(record.question_path).read_bytes()
    assert sha256(payload).hexdigest() == record.question_pdf_sha256
    text = "\n".join(p.extract_text() or "" for p in PdfReader(record.question_path).pages)
    assert set(re.findall(r"KRONOS-V3-REVIEW-[A-F0-9]{32}", text)) == {record.review_pack_id}
    assert set(re.findall(r"SWING-RUN-[A-F0-9]{32}", text)) == {record.native_run_identity}
    persisted = json.loads((store.root / "review-packs" / f"{record.review_pack_id}.json").read_text())
    assert _pack_from_dict(persisted["record"]) == record
    assert all(p.review_pack_id == record.review_pack_id
               and p.question_pdf_sha256 == record.question_pdf_sha256
               and p.question_path == record.question_path
               and p.native_run_identity == record.native_run_identity
               for p in record.candidate_packs)


def test_concurrent_cycles_serialize_and_cannot_cross_bind(tmp_path, monkeypatch):
    native, facts, live = _live(tmp_path)
    prepared = _prepared(native, facts, live)
    store = live.transport.record_store
    other = VisualV3PdfReviewTransport(live.transport.configuration, VisualV3PdfRecordStore(store.root))
    entered, release, attempted = Event(), Event(), Event()
    source = transport_module.write_visual_v3_question_pack
    candidate_paths, publication_paths = [], []

    def blocked_writer(requests, path, **kwargs):
        candidate_paths.append(path)
        if not entered.is_set():
            entered.set()
            assert release.wait(10)
        return source(requests, path, **kwargs)

    publish = VisualV3PdfRecordStore.publish

    def observed_publish(self, record, temporary):
        publication_paths.append((temporary, Path(record.question_path)))
        return publish(self, record, temporary)

    monkeypatch.setattr(transport_module, "write_visual_v3_question_pack", blocked_writer)
    monkeypatch.setattr(VisualV3PdfRecordStore, "publish", observed_publish)

    def second():
        assert not other.record_store.cycle_lock.acquire(blocking=False)
        attempted.set()
        return other.generate(_later(prepared), scope="ALL_ELIGIBLE", skipped=())

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(live.transport.generate, prepared, scope="ALL_ELIGIBLE", skipped=())
        assert entered.wait(10)
        two = pool.submit(second)
        assert attempted.wait(10)
        release.set()
        first, last = one.result(30), two.result(30)
    assert first.review_pack_id != last.review_pack_id
    assert len(set(candidate_paths)) == len(candidate_paths)
    assert len({p[0] for p in publication_paths}) == 2
    assert len({p[1] for p in publication_paths}) == 2
    for record in (first, last):
        _assert_binding(record, store)
    assert store.load_current() == last
    assert not any(p[0].exists() for p in publication_paths)


def test_workflow_lock_includes_preparation_and_memory_selection(tmp_path, monkeypatch):
    native, facts, live = _live(tmp_path)
    prepare = live._prepare
    entered, release, checked = Event(), Event(), Event()

    def hold(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return prepare(*args, **kwargs)

    def check():
        assert not live.transport.record_store.cycle_lock.acquire(blocking=False)
        checked.set()
        return live.snapshot(facts.run_identity)

    monkeypatch.setattr(live, "_prepare", hold)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(live.generate, native.snapshot(), facts, native.original_chart_bytes)
        assert entered.wait(10)
        snapshot = pool.submit(check)
        assert checked.wait(10)
        release.set()
        record = future.result(30)
        assert snapshot.result(30).review_pack == record
    assert live.transport.record_store.load_current() == record


def test_identical_generation_replay_survives_reinstantiation_without_mutation(tmp_path):
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    before = _digests(tmp_path)
    restored = SwingVisualV3LiveWorkflow(live.cycle, VisualV3PdfReviewTransport(
        live.transport.configuration, VisualV3PdfRecordStore(live.transport.record_store.root)))
    prepared, _ = restored._prepare_for_record(native.snapshot(), facts, native.original_chart_bytes, record)
    assert restored.transport.generate(prepared, scope=record.scope, skipped=record.skipped) == record
    assert _digests(tmp_path) == before
    _assert_binding(record, restored.transport.record_store)


def test_conflicting_generation_replay_cannot_overwrite_cycle(tmp_path):
    native, facts, live = _live(tmp_path)
    prepared = _prepared(native, facts, live)
    record = live.transport.generate(prepared, scope="ALL_ELIGIBLE", skipped=())
    image = prepared[0][0].original_image + b"different-revision"
    changed = (tuple(replace(r, original_image=image, chart_revision_sha256=sha256(image).hexdigest())
                     for r in prepared[0]), *prepared[1:])
    before = _digests(tmp_path)
    with pytest.raises(PdfReviewTransportError, match="^REVIEW_PACK_REPLAY_CONFLICT$"):
        live.transport.generate(changed, scope="ALL_ELIGIBLE", skipped=())
    assert _digests(tmp_path) == before
    assert live.transport.record_store.load_current() == record


@pytest.mark.parametrize("filename", ["expected", "OTHER_ANSWERS.pdf", "OTHER_ANSWERS(1).pdf"])
def test_foreign_answer_reports_exact_pack_mismatch_without_import(tmp_path, filename):
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    payload = _payload(live, native, facts, record)
    payload["manifest"]["review_pack_id"] = "KRONOS-V3-REVIEW-" + "F" * 32
    path = live.transport.configuration.answer_directory / (record.expected_answer_filename if filename == "expected" else filename)
    _answer_pdf(path, payload)
    prepared = _prepared(native, facts, live)
    before = _digests(tmp_path)
    with pytest.raises(PdfReviewTransportError, match="^REVIEW_PACK_ID_MISMATCH$"):
        live.transport.find_and_validate_answer(record, prepared)
    with pytest.raises(PdfReviewTransportError, match="^REVIEW_PACK_ID_MISMATCH$"):
        _validate_answer(record, prepared, payload)
    assert _digests(tmp_path) == before
    assert not live.cycle.completed_snapshot()


def test_absent_answer_is_the_only_not_found_case(tmp_path):
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    with pytest.raises(PdfReviewTransportError, match="^ANSWER_PACK_NOT_FOUND$"):
        live.transport.find_and_validate_answer(record, _prepared(native, facts, live))


def test_present_malformed_pdf_is_not_mapped_to_not_found(tmp_path):
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    _answer_pdf(live.transport.configuration.answer_directory / "BAD.pdf", {})
    with pytest.raises(PdfReviewTransportError) as failure:
        live.transport.find_and_validate_answer(record, _prepared(native, facts, live))
    assert str(failure.value) != "ANSWER_PACK_NOT_FOUND"


def test_identical_answer_replay_returns_bound_result_and_conflict_is_read_only(tmp_path):
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    path = live.transport.configuration.answer_directory / record.expected_answer_filename
    payload = _payload(live, native, facts, record)
    _answer_pdf(path, payload)
    imported = live.upload(native.snapshot(), facts, native.original_chart_bytes)
    before = _digests(tmp_path)
    assert live.upload(native.snapshot(), facts, native.original_chart_bytes) == imported
    assert _digests(tmp_path) == before
    # A different PDF for the already-consumed cycle must not re-import.
    payload["extra"] = "conflicting-answer"
    _answer_pdf(path, payload)
    before = _digests(tmp_path)
    with pytest.raises(PdfReviewTransportError, match="^ANSWER_REPLAY_CONFLICT$"):
        live.transport.find_and_validate_answer(record, _prepared(native, facts, live))
    assert _digests(tmp_path) == before
    assert live.transport.record_store.load_imports(record.review_pack_id) == imported


@pytest.mark.parametrize("stage", ["pdf", "binding", "record", "selection"])
def test_generation_and_persistence_failures_preserve_previous_complete_cycle(tmp_path, monkeypatch, stage):
    native, facts, live = _live(tmp_path)
    prepared = _prepared(native, facts, live)
    old = live.transport.generate(prepared, scope="ALL_ELIGIBLE", skipped=())
    before = _digests(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("CONTROLLED_FAILURE")

    if stage == "pdf":
        monkeypatch.setattr(transport_module, "write_visual_v3_question_pack", fail)
    elif stage == "binding":
        original = transport_module._write_answer_contract

        def wrong(path, identity, *args):
            return original(path, "KRONOS-V3-REVIEW-" + "E" * 32, *args)
        monkeypatch.setattr(transport_module, "_write_answer_contract", wrong)
    elif stage == "record":
        monkeypatch.setattr(live.transport.record_store, "retain_pack", fail)
    else:
        atomic = transport_module._atomic_json

        def fail_selection(path, *args, **kwargs):
            if path.name == "current-review-pack.json":
                fail()
            return atomic(path, *args, **kwargs)
        monkeypatch.setattr(transport_module, "_atomic_json", fail_selection)
    with pytest.raises((OSError, PdfReviewTransportError)):
        live.transport.generate(_later(prepared), scope="ALL_ELIGIBLE", skipped=())
    assert _digests(tmp_path) == before
    assert live.transport.record_store.load_current() == old


class SimulatedCrash(BaseException):
    pass


@pytest.mark.parametrize("stage", ["before_pdf", "after_pdf", "after_record", "after_selection"])
def test_interruption_recovery_has_no_orphan_or_cross_cycle_binding(tmp_path, monkeypatch, stage):
    native, facts, live = _live(tmp_path)
    prepared = _prepared(native, facts, live)
    store = live.transport.record_store
    old = live.transport.generate(prepared, scope="ALL_ELIGIBLE", skipped=())
    old_bytes = Path(old.question_path).read_bytes()
    select = store.select_current

    def crash_select(record):
        if stage == "after_record":
            store.retain_pack(record)
        if stage == "after_selection":
            select(record)
        raise SimulatedCrash()

    def crash_link(*args):
        raise SimulatedCrash()

    if stage == "before_pdf":
        monkeypatch.setattr(transport_module.os, "link", crash_link)
    else:
        monkeypatch.setattr(store, "select_current", crash_select)
    with pytest.raises(SimulatedCrash):
        live.transport.generate(_later(prepared), scope="ALL_ELIGIBLE", skipped=())
    pending = json.loads((store.root / "pending-publication.json").read_text())
    interrupted = _pack_from_dict(pending["record"])
    restored_store = VisualV3PdfRecordStore(store.root)
    current = restored_store.load_current()
    expected = interrupted if stage == "after_selection" else old
    assert current == expected
    assert Path(old.question_path).read_bytes() == old_bytes
    _assert_binding(expected, restored_store)
    assert {p.name for p in live.transport.configuration.question_directory.glob("*.pdf")} == (
        {old.question_filename, interrupted.question_filename} if stage == "after_selection" else {old.question_filename})
    assert not (store.root / "pending-publication.json").exists()
    assert not tuple(live.transport.configuration.question_directory.glob("*.tmp"))
    assert restored_store.load_current() == expected


def test_unrelated_temporary_residue_cannot_replace_complete_cycle(tmp_path):
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    residue = Path(record.question_path).with_suffix(".tmp")
    residue.write_bytes(b"historical shared temp residue")
    restored = VisualV3PdfRecordStore(live.transport.record_store.root)
    assert restored.load_current() == record
    _assert_binding(record, restored)
    assert residue.read_bytes() == b"historical shared temp residue"


def test_tampered_pdf_cannot_restore_even_with_matching_record_digest(tmp_path):
    native, facts, live = _live(tmp_path)
    prepared = _prepared(native, facts, live)
    first = live.transport.generate(prepared, scope="ALL_ELIGIBLE", skipped=())
    second = live.transport.generate(_later(prepared), scope="ALL_ELIGIBLE", skipped=())
    # Simulate the diagnosed foreign PDF + own record, including a matching hash.
    Path(second.question_path).write_bytes(Path(first.question_path).read_bytes())
    record_path = live.transport.record_store.root / "review-packs" / f"{second.review_pack_id}.json"
    payload = json.loads(record_path.read_text())
    payload["record"]["question_pdf_sha256"] = first.question_pdf_sha256
    for candidate in payload["record"]["candidate_packs"]:
        candidate["question_pdf_sha256"] = first.question_pdf_sha256
    record_path.write_text(json.dumps(payload))
    with pytest.raises(PdfReviewTransportError, match="^VISUAL_V3_REVIEW_PDF_BINDING_INVALID$"):
        VisualV3PdfRecordStore(live.transport.record_store.root).load_current()


@pytest.mark.parametrize("stage", ["pdf", "record"])
def test_failed_first_generation_has_no_successful_selection_or_pdf(tmp_path, monkeypatch, stage):
    native, facts, live = _live(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("CONTROLLED_FIRST_GENERATION_FAILURE")

    if stage == "pdf":
        monkeypatch.setattr(transport_module, "write_visual_v3_question_pack", fail)
    else:
        monkeypatch.setattr(live.transport.record_store, "retain_pack", fail)
    with pytest.raises(OSError, match="CONTROLLED_FIRST_GENERATION_FAILURE"):
        live.generate(native.snapshot(), facts, native.original_chart_bytes)
    assert live.snapshot(facts.run_identity).review_pack is None
    assert live.transport.record_store.load_current() is None
    assert not tuple(live.transport.record_store.root.rglob("*.json"))
    assert not tuple(live.transport.configuration.question_directory.iterdir())


def test_colliding_cycle_identifier_cannot_clobber_final_pdf(tmp_path, monkeypatch):
    native, facts, live = _live(tmp_path)
    prepared = _prepared(native, facts, live)
    old = live.transport.generate(prepared, scope="ALL_ELIGIBLE", skipped=())
    before = _digests(tmp_path)
    monkeypatch.setattr(transport_module, "uuid4", lambda: SimpleNamespace(
        hex=old.review_pack_id.removeprefix("KRONOS-V3-REVIEW-").lower()))
    with pytest.raises(PdfReviewTransportError, match="^REVIEW_PACK_PUBLICATION_CONFLICT$"):
        live.transport.generate(_later(prepared), scope="ALL_ELIGIBLE", skipped=())
    assert _digests(tmp_path) == before
    _assert_binding(old, live.transport.record_store)


def test_superseded_generation_replay_cannot_rebind_current_cycle(tmp_path):
    native, facts, live = _live(tmp_path)
    prepared = _prepared(native, facts, live)
    live.transport.generate(prepared, scope="ALL_ELIGIBLE", skipped=())
    current = live.transport.generate(_later(prepared), scope="ALL_ELIGIBLE", skipped=())
    before = _digests(tmp_path)
    with pytest.raises(PdfReviewTransportError, match="^VISUAL_V3_REVIEW_PACK_SUPERSEDED$"):
        live.transport.generate(prepared, scope="ALL_ELIGIBLE", skipped=())
    assert _digests(tmp_path) == before
    assert live.transport.record_store.load_current() == current


def test_concurrent_identical_upload_imports_once(tmp_path, monkeypatch):
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    _answer_pdf(live.transport.configuration.answer_directory / record.expected_answer_filename,
                _payload(live, native, facts, record))
    barrier = Barrier(2)
    completed = []
    complete = live.cycle.complete

    def observe(*args, **kwargs):
        result = complete(*args, **kwargs)
        completed.append(result)
        return result

    def upload():
        barrier.wait(timeout=10)
        return live.upload(native.snapshot(), facts, native.original_chart_bytes)

    monkeypatch.setattr(live.cycle, "complete", observe)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one, two = pool.submit(upload), pool.submit(upload)
        assert one.result(30) == two.result(30)
    assert len(completed) == len(record.candidate_packs)
    imports = live.transport.record_store.load_imports(record.review_pack_id)
    assert len(imports) == 1
    assert imports[0].consumed and imports[0].review_pack_id == record.review_pack_id
