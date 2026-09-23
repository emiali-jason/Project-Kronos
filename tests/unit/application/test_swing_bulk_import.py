"""Durable Swing bulk Answer import ownership with isolated control stores."""

from pathlib import Path
from threading import Event, Lock
from time import monotonic, sleep
from types import SimpleNamespace

import pytest

from kronos.application.swing_bulk_import import (
    SwingBulkImportOwner,
    SwingBulkImportStore,
)
from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError


PDF = b"%PDF-1.4\nsynthetic isolated Answer\n%%EOF\n"
EXPECTED = {"ONE": {"expected_run_identity": "SWING-RUN-" + "A" * 32}}


def _receipt(index: int):
    instrument = f"CANDIDATE-{index}"
    return SimpleNamespace(
        receipt_id=f"RECEIPT-{index}",
        binding=SimpleNamespace(value={
            "canonical_instrument": instrument,
            "market": "NSE",
        }),
    )


class _Intake:
    def __init__(self, count: int = 8) -> None:
        self.commit = SimpleNamespace(
            identity="COMMIT-ONE",
            receipts=tuple(_receipt(index) for index in range(count)),
        )
        self.store = SimpleNamespace(load_acceptance=lambda identity: self.commit)
        self.extractions = 0
        self.acceptances = 0
        self.handoffs = []
        self.fail_once = set()
        self.entered = Event()
        self.release = Event()
        self.block_handoff = False
        self._active = 0
        self.maximum_active = 0
        self._lock = Lock()

    def bulk_admission(self, market, expected):
        assert market == "NSE" and expected
        return {
            "request_identity": "REQUEST-ONE",
            "review_pack_identity": "KRONOS-V3-REVIEW-" + "B" * 32,
        }

    def extract_answer(self, pdf):
        assert pdf == PDF
        self.extractions += 1
        return b'{"schema":"ISOLATED"}'

    def accept_answer(self, market, expected, pdf, *, extracted_answer,
                      phase_observer):
        assert (market, expected, pdf) == ("NSE", EXPECTED, PDF)
        assert extracted_answer == b'{"schema":"ISOLATED"}'
        self.acceptances += 1
        phase_observer("validation_started_at")
        phase_observer("validation_completed_at")
        phase_observer("acceptance_started_at")
        phase_observer("acceptance_committed_at")
        return self.commit

    def handoff(self, commit, receipt):
        assert commit is self.commit
        with self._lock:
            self._active += 1
            self.maximum_active = max(self.maximum_active, self._active)
        try:
            self.entered.set()
            if self.block_handoff:
                assert self.release.wait(5)
            self.handoffs.append(receipt.receipt_id)
            if receipt.receipt_id in self.fail_once:
                self.fail_once.remove(receipt.receipt_id)
                raise ValueError("REVIEW_DOWNSTREAM_PROCESSING_FAILED")
            return SimpleNamespace(value={"state": "SUCCEEDED"})
        finally:
            with self._lock:
                self._active -= 1


def _wait(owner, state, timeout=5):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        value = owner.status()
        if value is not None and value["state"] == state:
            return value
        sleep(0.01)
    raise AssertionError((state, owner.status()))


def _owner(tmp_path: Path, intake=None):
    intake = intake or _Intake()
    store = SwingBulkImportStore((tmp_path / "runtime-control").resolve())
    return SwingBulkImportOwner(store, intake), intake, store


def test_admission_identity_repeat_and_conflicting_bytes_are_fail_closed(tmp_path):
    owner, _intake, store = _owner(tmp_path)
    first, created = owner.admit("NSE", EXPECTED, PDF)
    replay, replay_created = owner.admit("NSE", EXPECTED, PDF)

    assert created is True and replay_created is False
    assert replay == first
    assert first["batch_identity"] == store.batch_identity(
        "REQUEST-ONE", "KRONOS-V3-REVIEW-" + "B" * 32,
        first["answer_sha256"],
    )
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ANSWER_IDENTITY_CONFLICT"):
        owner.admit("NSE", EXPECTED, PDF + b"different")
    assert len(tuple((store.root / "batches").glob("*.json"))) == 1
    assert len(tuple((store.root / "answers").glob("*.pdf"))) == 1


def test_exact_replay_resolves_retained_batch_after_intake_authority_advances(tmp_path):
    owner, intake, store = _owner(tmp_path)
    first, created = owner.admit("NSE", EXPECTED, PDF)
    intake.bulk_admission = lambda *_args: pytest.fail(
        "exact replay reopened the advanced intake mutation fence"
    )

    replay, replay_created = owner.admit("NSE", EXPECTED, PDF)

    assert created is True and replay_created is False
    assert replay == first == store.load(first["batch_identity"])
    assert len(tuple((store.root / "batches").glob("*.json"))) == 1
    assert len(tuple((store.root / "answers").glob("*.pdf"))) == 1

    intake.answer_bytes_for_review_pack = lambda identity: (
        PDF if identity == first["review_pack_identity"] else b""
    )
    directory_replay, directory_created = owner.admit_from_directory(
        "NSE", EXPECTED
    )
    assert directory_created is False and directory_replay == first

    intake.answer_bytes_for_review_pack = lambda _identity: PDF + b"different"
    with pytest.raises(ReviewEvidenceError,
                       match="REVIEW_ANSWER_IDENTITY_CONFLICT"):
        owner.admit_from_directory("NSE", EXPECTED)


def test_one_extraction_atomic_acceptance_and_eight_retained_candidate_results(tmp_path):
    owner, intake, store = _owner(tmp_path)
    owner.start()
    try:
        admitted, _ = owner.admit("NSE", EXPECTED, PDF)
        completed = _wait(owner, "COMPLETED")
    finally:
        owner.close()

    assert intake.extractions == 1 and intake.acceptances == 1
    assert intake.handoffs == [f"RECEIPT-{index}" for index in range(8)]
    assert [item["state"] for item in completed["candidates"]] == ["SUCCEEDED"] * 8
    assert all(item["attempt_identity"] for item in completed["candidates"])
    assert store.extracted(admitted) == b'{"schema":"ISOLATED"}'
    assert completed["commit_identity"] == "COMMIT-ONE"
    assert completed["timings"].keys() >= {
        "request_admitted_at", "extraction_started_at", "extraction_completed_at",
        "validation_started_at", "validation_completed_at",
        "acceptance_started_at", "acceptance_committed_at",
        "downstream_started_at", "batch_completed_at",
    }


@pytest.mark.parametrize("restart_state", ["ADMITTED", "VALIDATING", "ACCEPTING"])
def test_restart_resumes_preacceptance_states_without_duplicate_extraction(
    tmp_path, restart_state
):
    owner, intake, store = _owner(tmp_path)
    record, _ = store.admit(
        request_identity="REQUEST-ONE",
        review_pack_identity="KRONOS-V3-REVIEW-" + "B" * 32,
        answer=PDF, market="NSE", expected=EXPECTED,
        received_at="2026-09-22T10:00:00+00:00",
    )
    if restart_state != "ADMITTED":
        store.transition(record["batch_identity"], restart_state)
    extracted = intake.extract_answer(PDF)
    store.retain_extracted(record["batch_identity"], extracted)
    intake.extractions = 0

    owner.start()
    try:
        _wait(owner, "COMPLETED")
    finally:
        owner.close()

    assert intake.extractions == 0
    assert intake.acceptances == 1
    assert len(intake.handoffs) == 8


@pytest.mark.parametrize("running", [False, True])
def test_restart_resumes_accepted_and_running_candidates_effectively_once(
    tmp_path, running
):
    owner, intake, store = _owner(tmp_path)
    record, _ = store.admit(
        request_identity="REQUEST-ONE",
        review_pack_identity="KRONOS-V3-REVIEW-" + "B" * 32,
        answer=PDF, market="NSE", expected=EXPECTED,
        received_at="2026-09-22T10:00:00+00:00",
    )
    store.acceptance(record["batch_identity"], intake.commit)
    if running:
        store.transition(record["batch_identity"], "DOWNSTREAM_RUNNING")
        store.candidate(record["batch_identity"], "RECEIPT-0", "RUNNING")

    owner.start()
    try:
        completed = _wait(owner, "COMPLETED")
    finally:
        owner.close()

    assert intake.extractions == 0 and intake.acceptances == 0
    assert len(intake.handoffs) == 8
    assert all(item["state"] == "SUCCEEDED" for item in completed["candidates"])


def test_two_workers_share_atomic_batch_lease_and_never_overlap(tmp_path):
    intake = _Intake(count=1)
    intake.block_handoff = True
    root = (tmp_path / "runtime-control").resolve()
    owner_a = SwingBulkImportOwner(SwingBulkImportStore(root), intake)
    owner_b = SwingBulkImportOwner(SwingBulkImportStore(root), intake)
    owner_a.start()
    owner_b.start()
    try:
        owner_a.admit("NSE", EXPECTED, PDF)
        assert intake.entered.wait(2)
        sleep(0.1)
        assert intake.maximum_active == 1
        intake.release.set()
        _wait(owner_a, "COMPLETED")
    finally:
        intake.release.set()
        owner_a.close()
        owner_b.close()

    assert intake.handoffs == ["RECEIPT-0"]


def test_downstream_failure_is_retained_and_only_explicit_retry_resumes(tmp_path):
    owner, intake, _store = _owner(tmp_path, _Intake(count=2))
    intake.fail_once.add("RECEIPT-1")
    owner.start()
    try:
        record, _ = owner.admit("NSE", EXPECTED, PDF)
        failed = _wait(owner, "COMPLETED_WITH_FAILURE")
        sleep(0.05)
        assert failed["candidates"][1]["state"] == "FAILED"
        assert intake.handoffs.count("RECEIPT-1") == 1
        owner.retry_candidate(record["batch_identity"], "CANDIDATE-1")
        completed = _wait(owner, "COMPLETED")
    finally:
        owner.close()

    assert completed["candidates"][0]["state"] == "SUCCEEDED"
    assert completed["candidates"][1]["state"] == "SUCCEEDED"
    assert intake.acceptances == 1
    assert intake.handoffs.count("RECEIPT-0") == 1
    assert intake.handoffs.count("RECEIPT-1") == 2


def test_presentation_excludes_staged_paths_answer_digest_and_binding_payload(tmp_path):
    owner, _intake, _store = _owner(tmp_path)
    admitted, _ = owner.admit("NSE", EXPECTED, PDF)
    value = owner.presentation(admitted["batch_identity"])
    assert value is not None
    serialized = repr(value)
    assert "answer_relative_path" not in serialized
    assert "answer_sha256" not in serialized
    assert "expected_run_identity" not in serialized
    assert value["status_location"].endswith(admitted["batch_identity"])
