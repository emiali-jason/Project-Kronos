from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil
from threading import Event, Thread
import time
import tracemalloc

import pytest

from kronos.application.housekeeping import (
    BoundedHousekeeping,
    DEFAULT_INTERVAL_SECONDS,
    HousekeepingArtifactClass,
    HousekeepingLimits,
    intraday_research_staging_scope,
    review_preparation_scope,
)
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.intraday.wo12_research_contract import digest, record
from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
from tests.unit.application.test_intraday_research import _application


def _review_store(tmp_path: Path) -> ReviewEvidenceStore:
    store = ReviewEvidenceStore(tmp_path)
    store.root.mkdir(parents=True)
    (store.root / "receipts").mkdir()
    return store


def _housekeeper(*scopes, **kwargs) -> BoundedHousekeeping:
    return BoundedHousekeeping(
        scopes,
        limits=kwargs.pop("limits", HousekeepingLimits(max_elapsed_seconds=5.0)),
        **kwargs,
    )


def test_allowlist_is_explicit_and_periodic_activation_defaults_off(tmp_path) -> None:
    store = _review_store(tmp_path)
    worker = _housekeeper(review_preparation_scope(store))

    assert {item.value for item in HousekeepingArtifactClass} == {
        "SWING_REVIEW_PREPARATION",
        "SWING_REVIEW_POINTER_PREPARATION",
        "INTRADAY_RESEARCH_STAGED_WORKBOOK",
        "INTRADAY_RESEARCH_EMPTY_STAGE_DIRECTORY",
    }
    assert DEFAULT_INTERVAL_SECONDS == 21600
    assert worker.trigger_periodic(now=10**9) == "DISABLED"
    status = worker.status_document()
    assert status["production_activation"] is False
    assert status["interval_seconds"] == 21600
    assert status["last_result"] is None


def test_review_preparations_are_removed_under_owner_lock_without_harming_evidence(tmp_path) -> None:
    store = _review_store(tmp_path)
    final = store.root / "receipts" / "authoritative.json"
    final.write_bytes(b"retained evidence")
    hardlink = store.root / "receipts" / ".prepared-pointer-hardlink"
    os.link(final, hardlink)
    standalone = store.root / "receipts" / ".prepared-crash"
    standalone.write_bytes(b"disposable")
    standalone_allocated = standalone.stat().st_blocks * 512
    ordinary = store.root / "receipts" / "ordinary.tmp"
    ordinary.write_bytes(b"protected")
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    symlink = store.root / "receipts" / ".prepared-link"
    symlink.symlink_to(outside)

    result = _housekeeper(review_preparation_scope(store)).run_once()

    assert result.removed_files == 2
    assert result.removed_bytes == len(b"retained evidence") + len(b"disposable")
    assert result.physically_reclaimed_bytes == standalone_allocated
    assert final.read_bytes() == b"retained evidence"
    assert not hardlink.exists() and not standalone.exists()
    assert ordinary.read_bytes() == b"protected"
    assert symlink.is_symlink() and outside.read_bytes() == b"outside"
    assert "SWING_REVIEW_PREPARATION_UNSAFE" in result.diagnostics


def test_review_owner_contention_is_bounded_and_retry_cleans_after_release(tmp_path) -> None:
    store = _review_store(tmp_path)
    pending = store.root / "receipts" / ".prepared-crash"
    pending.write_bytes(b"pending")
    entered, release = Event(), Event()

    def hold_owner() -> None:
        with store.intake_lock():
            entered.set()
            release.wait(5)

    thread = Thread(target=hold_owner)
    thread.start()
    assert entered.wait(2)
    worker = _housekeeper(review_preparation_scope(store))
    started = time.monotonic()
    busy = worker.run_once()
    elapsed = time.monotonic() - started
    release.set()
    thread.join(2)

    assert elapsed < 0.25
    assert busy.removed_files == 0
    assert "SWING_REVIEW_OWNER_BUSY" in busy.diagnostics
    assert worker.run_once().removed_files == 1
    assert not pending.exists()


def test_open_reader_remains_valid_when_hardlink_preparation_is_unlinked(tmp_path) -> None:
    store = _review_store(tmp_path)
    final = store.root / "receipts" / "authoritative.json"
    final.write_bytes(b"reader snapshot")
    pending = store.root / "receipts" / ".prepared-hardlink"
    os.link(final, pending)

    with final.open("rb") as reader:
        result = _housekeeper(review_preparation_scope(store)).run_once()
        assert reader.read() == b"reader snapshot"

    assert result.removed_files == 1
    assert result.physically_reclaimed_bytes == 0
    assert final.read_bytes() == b"reader snapshot"


def test_verified_intraday_duplicate_stage_is_removed_and_authority_remains(tmp_path) -> None:
    application, _ = _application(tmp_path)
    operation_identity = "PF08-PUBLISHED-001"
    result = application.update(operation_identity=operation_identity)
    stage = application.store.root / "staging" / digest(operation_identity)
    stage.mkdir(parents=True)
    staged = stage / result.workbook_path.name
    shutil.copyfile(result.workbook_path, staged)
    allocated = staged.stat().st_blocks * 512

    cleaned = _housekeeper(intraday_research_staging_scope(application)).run_once()

    assert cleaned.removed_files == 1
    assert cleaned.removed_directories == 1
    assert cleaned.removed_bytes == result.workbook_bytes
    assert cleaned.physically_reclaimed_bytes == allocated
    assert not stage.exists()
    assert application.open_current("2026_08")[1] == result.workbook_path.read_bytes()
    assert application.store.load(result.receipt_identity).identity == result.receipt_identity


def test_incomplete_and_failed_intraday_stages_remain_visibly_owned(tmp_path) -> None:
    application, _ = _application(tmp_path)
    incomplete_operation = "PF08-INCOMPLETE"
    incomplete = application.store.root / "staging" / digest(incomplete_operation)
    incomplete.mkdir(parents=True)
    (incomplete / "unknown.xlsx").write_bytes(b"unknown")
    failed_operation = "PF08-FAILED"
    failure = record(
        "WO12_LOCAL_PUBLICATION_FAILURE_V1",
        operation_identity=failed_operation,
        projection_identity="WO12-RESEARCH-PROJECTION-" + "0" * 64,
        failed_at=application.clock(),
        reason="WO12_LOCAL_PUBLICATION_FAILED",
    )
    application.store.retain(failure)
    failed = application.store.root / "staging" / digest(failed_operation)
    failed.mkdir(parents=True)
    (failed / "failed.xlsx").write_bytes(b"failed")

    result = _housekeeper(intraday_research_staging_scope(application)).run_once()

    assert result.removed_files == 0
    assert incomplete.exists() and failed.exists()
    assert "INTRADAY_RESEARCH_INCOMPLETE_RECOVERY" in result.diagnostics
    assert "INTRADAY_RESEARCH_FAILED_CLEANUP_OWNED" in result.diagnostics


def test_corrupt_current_publication_prevents_stage_cleanup(tmp_path) -> None:
    application, _ = _application(tmp_path)
    operation_identity = "PF08-CORRUPT-CURRENT"
    result = application.update(operation_identity=operation_identity)
    stage = application.store.root / "staging" / digest(operation_identity)
    stage.mkdir(parents=True)
    staged = stage / result.workbook_path.name
    shutil.copyfile(result.workbook_path, staged)
    result.workbook_path.write_bytes(b"corrupt")

    cleaned = _housekeeper(intraday_research_staging_scope(application)).run_once()

    assert cleaned.removed_files == 0
    assert staged.exists()
    assert "INTRADAY_RESEARCH_CURRENT_UNVERIFIED" in cleaned.diagnostics


def test_intraday_publication_lock_fences_cleanup_until_owner_releases(tmp_path) -> None:
    application, _ = _application(tmp_path)
    operation_identity = "PF08-CONCURRENT-PUBLISHER"
    result = application.update(operation_identity=operation_identity)
    stage = application.store.root / "staging" / digest(operation_identity)
    stage.mkdir(parents=True)
    staged = stage / result.workbook_path.name
    shutil.copyfile(result.workbook_path, staged)
    entered, release = Event(), Event()

    def hold_owner() -> None:
        with application.store.transaction():
            entered.set()
            release.wait(5)

    thread = Thread(target=hold_owner)
    thread.start()
    assert entered.wait(2)
    worker = _housekeeper(intraday_research_staging_scope(application))
    busy = worker.run_once()
    release.set()
    thread.join(2)

    assert busy.removed_files == 0 and staged.exists()
    assert "INTRADAY_RESEARCH_OWNER_BUSY" in busy.diagnostics
    assert worker.run_once().removed_files == 1
    assert not stage.exists()


def test_symlink_and_path_escape_are_never_followed(tmp_path) -> None:
    application, _ = _application(tmp_path)
    outside = tmp_path / "outside-stage"
    outside.mkdir()
    payload = outside / "keep.xlsx"
    payload.write_bytes(b"keep")
    staging = application.store.root / "staging"
    staging.mkdir(parents=True)
    escaped = staging / ("a" * 64)
    escaped.symlink_to(outside, target_is_directory=True)

    result = _housekeeper(intraday_research_staging_scope(application)).run_once()

    assert result.removed_files == 0
    assert escaped.is_symlink() and payload.read_bytes() == b"keep"
    assert "INTRADAY_RESEARCH_STAGE_UNSAFE" in result.diagnostics


def test_file_and_byte_limits_are_truthful_and_repeated_passes_are_stable(tmp_path) -> None:
    store = _review_store(tmp_path)
    for index in range(5):
        (store.root / "receipts" / f".prepared-{index}").write_bytes(b"x" * 8)
    limits = HousekeepingLimits(
        max_removed_files=2,
        max_removed_bytes=16,
        max_examined_entries=100,
        max_reference_entries=10,
        max_reference_bytes=1024,
        max_elapsed_seconds=5,
        max_diagnostics=8,
    )
    worker = _housekeeper(review_preparation_scope(store), limits=limits)

    first = worker.run_once()
    second = worker.run_once()
    third = worker.run_once()

    assert (first.removed_files, second.removed_files, third.removed_files) == (2, 2, 1)
    assert first.outcome == second.outcome == "LIMIT_REACHED"
    assert third.outcome == "COMPLETED"
    assert not list((store.root / "receipts").glob(".prepared-*"))


def test_large_directory_scan_has_bounded_entries_and_memory(tmp_path) -> None:
    store = _review_store(tmp_path)
    for index in range(1000):
        (store.root / "receipts" / f"evidence-{index:04}.json").write_bytes(b"e")
    limits = HousekeepingLimits(
        max_removed_files=2,
        max_removed_bytes=1024,
        max_examined_entries=25,
        max_reference_entries=10,
        max_reference_bytes=1024,
        max_elapsed_seconds=5,
        max_diagnostics=4,
    )
    tracemalloc.start()
    result = _housekeeper(review_preparation_scope(store), limits=limits).run_once()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result.outcome == "LIMIT_REACHED"
    assert result.examined_entries == 25
    assert result.removed_files == 0
    assert peak < 2 * 1024 * 1024


def test_elapsed_limit_stops_before_additional_files_are_touched(tmp_path) -> None:
    store = _review_store(tmp_path)
    pending = store.root / "receipts" / ".prepared-elapsed"
    pending.write_bytes(b"pending")
    ticks = iter((0.0, 0.0, 0.2, 0.2))
    limits = HousekeepingLimits(max_elapsed_seconds=0.1)
    worker = _housekeeper(
        review_preparation_scope(store),
        limits=limits,
        clock=lambda: next(ticks, 0.2),
    )

    result = worker.run_once()

    assert result.outcome == "LIMIT_REACHED"
    assert result.removed_files == 0 and pending.exists()
    assert "PASS_ELAPSED_LIMIT" in result.diagnostics


def test_overlapping_pass_is_refused_and_status_remains_responsive(tmp_path) -> None:
    store = _review_store(tmp_path)
    pending = store.root / "receipts" / ".prepared-blocked"
    pending.write_bytes(b"blocked")
    entered, release = Event(), Event()

    def blocked_unlink(path: Path) -> None:
        entered.set()
        assert release.wait(5)
        os.unlink(path)

    worker = _housekeeper(review_preparation_scope(store), unlink=blocked_unlink)
    result = []
    thread = Thread(target=lambda: result.append(worker.run_once()))
    thread.start()
    assert entered.wait(2)
    started = time.monotonic()
    overlap = worker.run_once()
    status = worker.status_document()
    elapsed = time.monotonic() - started
    release.set()
    thread.join(2)

    assert overlap.outcome == "OVERLAP_SKIPPED"
    assert elapsed < 0.1
    assert status["pass_active"] is True
    assert result[0].removed_files == 1


def test_cleanup_failure_stays_owned_with_bounded_path_free_diagnostic(tmp_path) -> None:
    store = _review_store(tmp_path)
    pending = store.root / "receipts" / ".prepared-failure"
    pending.write_bytes(b"owned")

    def fail(_path: Path) -> None:
        raise OSError("raw/path detail")

    result = _housekeeper(review_preparation_scope(store), unlink=fail).run_once()

    assert pending.exists()
    assert result.removed_files == 0
    assert result.diagnostics == ("SWING_REVIEW_PREPARATION_REMOVE_FAILED",)
    assert "raw/path" not in repr(result.document()) and str(tmp_path) not in repr(result.document())


def test_periodic_trigger_is_fixed_interval_single_pending_work(tmp_path) -> None:
    store = _review_store(tmp_path)
    queued = []
    clock = [0.0]
    worker = _housekeeper(
        review_preparation_scope(store),
        production_activation=True,
        interval_seconds=10,
        clock=lambda: clock[0],
        background_runner=queued.append,
    )

    assert worker.trigger_periodic(now=9) == "NOT_DUE"
    assert worker.trigger_periodic(now=10) == "SCHEDULED"
    assert worker.trigger_periodic(now=100) == "PENDING"
    assert len(queued) == 1
    clock[0] = 10
    queued.pop()()
    assert worker.trigger_periodic(now=19) == "NOT_DUE"
    assert worker.trigger_periodic(now=20) == "SCHEDULED"


def test_shutdown_retains_queued_owner_until_fenced_callback_finishes(tmp_path) -> None:
    store = _review_store(tmp_path)
    queued = []
    cleaned = []

    class Scope:
        def clean(self, _owner, _budget) -> None:
            cleaned.append(True)

    worker = _housekeeper(
        Scope(),
        production_activation=True,
        interval_seconds=10,
        clock=lambda: 0.0,
        background_runner=queued.append,
    )

    assert worker.trigger_periodic(now=10) == "SCHEDULED"
    assert worker.status_document()["lifecycle_state"] == "SCHEDULED"
    stopped = worker.shutdown(timeout_seconds=0)

    assert stopped["lifecycle_state"] == "SHUTDOWN_PENDING"
    assert stopped["owned_workers"] == 1
    assert worker.trigger_periodic(now=100) == "SHUTDOWN"
    queued.pop()()
    final = worker.status_document()
    assert final["lifecycle_state"] == "STOPPED"
    assert final["owned_workers"] == 0
    assert cleaned == []


def test_maintenance_fence_preserves_queued_housekeeping_owner(tmp_path) -> None:
    queued=[]
    cleaned=[]
    class Scope:
        def clean(self, _owner, _budget):
            cleaned.append(True)
    worker=_housekeeper(Scope(),production_activation=True,
                        interval_seconds=10,clock=lambda:0.0,
                        background_runner=queued.append)
    admission=MaintenanceAdmissionCoordinator()
    worker.bind_maintenance_admission(admission)
    assert worker.trigger_periodic(now=10)=="SCHEDULED"
    assert admission.snapshot()["owners"]=={"HOUSEKEEPING":1}
    generation="c"*64
    assert admission.claim(generation)
    admission.draining(generation)
    assert worker.trigger_periodic(now=100)=="SHUTDOWN"
    queued.pop()()
    assert admission.wait_for_zero(generation,0)
    assert cleaned==[True]


def test_shutdown_is_bounded_while_uninterruptible_pass_remains_owned(tmp_path) -> None:
    entered, release = Event(), Event()

    class Scope:
        def clean(self, _owner, _budget) -> None:
            entered.set()
            assert release.wait(5)

    worker = _housekeeper(
        Scope(),
        production_activation=True,
        interval_seconds=1,
    )
    assert worker.trigger_periodic(now=10**9) == "SCHEDULED"
    assert entered.wait(2)

    started = time.monotonic()
    pending = worker.shutdown(timeout_seconds=0.02)
    elapsed = time.monotonic() - started

    assert elapsed < 0.2
    assert pending["lifecycle_state"] == "SHUTDOWN_PENDING"
    assert pending["owned_workers"] == 1
    assert pending["pass_active"] is True
    release.set()
    deadline = time.monotonic() + 2
    while worker.status_document()["owned_workers"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert worker.status_document()["lifecycle_state"] == "STOPPED"


def test_periodic_worker_and_schedule_failures_are_visible_without_immediate_retry(
    tmp_path,
) -> None:
    class FailedScope:
        def clean(self, _owner, _budget) -> None:
            raise RuntimeError("private failure detail")

    worker = _housekeeper(
        FailedScope(), production_activation=True, interval_seconds=60
    )
    assert worker.trigger_periodic(now=10**9) == "SCHEDULED"
    deadline = time.monotonic() + 2
    while worker.status_document()["owned_workers"] and time.monotonic() < deadline:
        time.sleep(0.01)
    status = worker.status_document()
    assert status["last_failure"] == "HOUSEKEEPING_PASS_FAILED"
    assert status["owned_workers"] == 0
    assert worker.trigger_periodic(now=status["next_due_monotonic"] - 1) == "NOT_DUE"
    assert "private failure detail" not in repr(status)

    def reject(_callback) -> None:
        raise RuntimeError("runner unavailable")

    rejected = _housekeeper(
        FailedScope(),
        production_activation=True,
        interval_seconds=1,
        background_runner=reject,
    )
    assert rejected.trigger_periodic(now=10**9) == "FAILED"
    rejected_status = rejected.status_document()
    assert rejected_status["last_failure"] == "HOUSEKEEPING_SCHEDULE_FAILED"
    assert rejected_status["owned_workers"] == 0
    assert rejected.trigger_periodic(now=10**9) == "NOT_DUE"


def test_reference_caps_prevent_deletion_when_complete_proof_cannot_be_read(tmp_path) -> None:
    application, _ = _application(tmp_path)
    operation_identity = "PF08-REFERENCE-CAP"
    result = application.update(operation_identity=operation_identity)
    stage = application.store.root / "staging" / digest(operation_identity)
    stage.mkdir(parents=True)
    staged = stage / result.workbook_path.name
    shutil.copyfile(result.workbook_path, staged)
    limits = HousekeepingLimits(
        max_removed_files=4,
        max_removed_bytes=10**7,
        max_examined_entries=100,
        max_reference_entries=1,
        max_reference_bytes=10**7,
        max_elapsed_seconds=5,
        max_diagnostics=4,
    )

    cleaned = _housekeeper(intraday_research_staging_scope(application), limits=limits).run_once()

    assert cleaned.outcome == "LIMIT_REACHED"
    assert cleaned.removed_files == 0 and staged.exists()
    assert "REFERENCE_ENTRY_LIMIT" in cleaned.diagnostics


def test_hash_contract_used_for_staged_duplicate_is_exact(tmp_path) -> None:
    application, _ = _application(tmp_path)
    operation_identity = "PF08-MISMATCH"
    result = application.update(operation_identity=operation_identity)
    stage = application.store.root / "staging" / digest(operation_identity)
    stage.mkdir(parents=True)
    staged = stage / result.workbook_path.name
    payload = result.workbook_path.read_bytes()
    staged.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))

    cleaned = _housekeeper(intraday_research_staging_scope(application)).run_once()

    assert sha256(staged.read_bytes()).hexdigest() != result.workbook_sha256
    assert cleaned.removed_files == 0
    assert "INTRADAY_RESEARCH_STAGE_MISMATCH" in cleaned.diagnostics


# Current layout is owned by Sponsor reporting 2.4; historical layout requires
# its exact retained 2.2/2.3 receipt, never a basename/hash fallback.


def _publication_stage(tmp_path):
    application, _ = _application(tmp_path)
    operation = "PF08-LAYOUT-BOUND"
    result = application.update(operation_identity=operation)
    stage = application.store.root / "staging" / digest(operation)
    stage.mkdir(parents=True)
    shutil.copyfile(result.workbook_path, stage / result.workbook_path.name)
    return application, result, stage


def _verify_publication(application, receipt):
    from kronos.application.housekeeping import _Budget
    budget = _Budget(HousekeepingLimits(max_elapsed_seconds=5), time.monotonic, time.monotonic())
    return intraday_research_staging_scope(application)._verified_current(receipt, budget)


def _inventory_bytes(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino)
            for p in root.rglob("*") if p.is_file() and not p.is_symlink()}


def test_current_publisher_path_is_verified_observationally_before_cleanup(tmp_path):
    application, result, stage = _publication_stage(tmp_path)
    receipt = application.store.load(result.receipt_identity)
    from kronos.application.intraday_sponsor_reporting import monthly_path
    assert result.workbook_path == monthly_path(application.publication_root, "2026_08")
    assert result.workbook_path.parent.name == "2026"
    before = _inventory_bytes(tmp_path)
    assert _verify_publication(application, receipt) is not None
    assert _inventory_bytes(tmp_path) == before
    keep = stage.parent / "unrelated.xlsx"
    keep.write_bytes(b"not disposable")
    cleaned = _housekeeper(intraday_research_staging_scope(application)).run_once()
    assert cleaned.removed_files == cleaned.removed_directories == 1
    assert not stage.exists() and keep.read_bytes() == b"not disposable"
    assert application.store.current_receipt("2026_08") == receipt
    assert result.workbook_path.read_bytes() == before[str(result.workbook_path.relative_to(tmp_path))][0]


@pytest.mark.parametrize("fault", [
    "omitted-year", "wrong-year", "wrong-month", "wrong-filename", "wrong-root",
    "traversal", "relative", "wrong-path-identity", "wrong-hash", "wrong-size",
    "unknown-version", "noncanonical-month", "missing-workbook", "directory-workbook",
    "symlink-file", "symlink-year", "symlink-root", "stale-pointer", "missing-pointer",
    "symlink-pointer", "invalid-receipt"])
def test_publication_layout_rejects_unproved_binding_and_preserves_stage(tmp_path, fault):
    from dataclasses import asdict
    from kronos.intraday.wo12_research_contract import encoded
    application, result, stage = _publication_stage(tmp_path)
    receipt = application.store.load(result.receipt_identity)
    data = receipt.data
    target = result.workbook_path
    pointer = application.store.root / "current" / "2026_08.json"
    if fault in {"omitted-year", "wrong-year", "wrong-month", "wrong-filename", "wrong-root", "traversal", "relative"}:
        paths = {
            "omitted-year": application.publication_root / target.name,
            "wrong-year": application.publication_root / "2025" / target.name,
            "wrong-month": application.publication_root / "2026" / "2026-09 — September.xlsx",
            "wrong-filename": target.parent / "other.xlsx",
            "wrong-root": tmp_path / "other-root" / "2026" / target.name,
            "traversal": application.publication_root / "2026" / ".." / "2026" / target.name,
            "relative": Path("2026") / target.name,
        }
        replacement = paths[fault]
        if fault not in {"relative", "traversal"}:
            replacement.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, replacement)
        data["workbook_path"] = str(replacement)
        data["workbook_filename"] = replacement.name
        data["workbook_path_identity"] = "WO12-WORKBOOK-PATH-" + digest(
            {"root": str(application.publication_root), "filename": replacement.name})
    elif fault == "wrong-path-identity": data["workbook_path_identity"] = "wrong"
    elif fault == "wrong-hash": data["workbook_sha256"] = "0" * 64
    elif fault == "wrong-size": data["workbook_bytes"] += 1
    elif fault == "unknown-version": data["schema_version"] = "9.9.0"
    elif fault == "noncanonical-month": data["year_month"] = "2026_8"
    elif fault == "missing-workbook": target.unlink()
    elif fault == "directory-workbook": target.unlink(); target.mkdir()
    elif fault == "symlink-file":
        other = tmp_path / "workbook-copy"; shutil.copyfile(target, other)
        target.unlink(); target.symlink_to(other)
    elif fault in {"symlink-year", "symlink-root"}:
        directory = target.parent if fault == "symlink-year" else application.publication_root
        other = tmp_path / "moved-publication"
        directory.rename(other); directory.symlink_to(other, target_is_directory=True)
    changed = record(receipt.schema, **data)
    # Isolate the exact path/hash verifier, with a valid content-addressed pointer.
    pointer.write_bytes(encoded(asdict(changed)) + b"\n")
    if fault == "noncanonical-month":
        pointer.rename(pointer.with_name("2026_8.json"))
    elif fault == "stale-pointer":
        pointer.write_bytes(encoded(asdict(record(receipt.schema, **dict(data, published_at="2000-01-01T00:00:00+00:00")))) + b"\n")
    elif fault == "missing-pointer": pointer.unlink()
    elif fault == "symlink-pointer":
        other = tmp_path / "pointer-copy"; shutil.copyfile(pointer, other)
        pointer.unlink(); pointer.symlink_to(other)
    elif fault == "invalid-receipt": pointer.write_bytes(b'{"invalid":true}')
    before = _inventory_bytes(tmp_path)
    assert _verify_publication(application, changed) is None
    assert _inventory_bytes(tmp_path) == before
    cleaned = _housekeeper(intraday_research_staging_scope(application)).run_once()
    assert cleaned.removed_files == 0 and stage.exists()


@pytest.mark.parametrize("version", ["2.2.0", "2.3.0"])
def test_historical_layout_requires_exact_explicit_original_version(tmp_path, version):
    from dataclasses import asdict
    from kronos.intraday.wo12_research_contract import encoded
    application, result, stage = _publication_stage(tmp_path)
    receipt = application.store.load(result.receipt_identity)
    legacy = application.publication_root / "KRONOS_Intraday_Research_2026_08.xlsx"
    shutil.copyfile(result.workbook_path, legacy)
    data = dict(receipt.data, schema_version=version, workbook_path=str(legacy),
                workbook_filename=legacy.name,
                workbook_path_identity="WO12-WORKBOOK-PATH-" + digest(
                    {"root": str(application.publication_root), "filename": legacy.name}))
    original = record(receipt.schema, **data)
    pointer = application.store.root / "current" / "2026_08.json"
    pointer.write_bytes(encoded(asdict(original)) + b"\n")
    assert _verify_publication(application, original) is not None
    current = record(receipt.schema, **dict(data, schema_version="2.4.0"))
    pointer.write_bytes(encoded(asdict(current)) + b"\n")
    assert _verify_publication(application, current) is None
    assert stage.exists()


def test_current_publication_is_rechecked_before_stage_removal(tmp_path, monkeypatch):
    application, result, stage = _publication_stage(tmp_path)
    scope = intraday_research_staging_scope(application)
    original = type(scope)._verified_current
    reads = []
    def invalidate_after_initial(self, receipt, budget):
        reads.append(receipt.identity)
        if len(reads) == 2:
            result.workbook_path.write_bytes(b"changed after initial proof")
        return original(self, receipt, budget)
    monkeypatch.setattr(type(scope), "_verified_current", invalidate_after_initial)
    cleaned = _housekeeper(scope).run_once()
    assert len(reads) == 2
    assert cleaned.removed_files == 0 and stage.exists()
    assert "INTRADAY_RESEARCH_REFERENCE_CHANGED" in cleaned.diagnostics


def test_conflicting_and_missing_retained_receipts_never_authorize_cleanup(tmp_path):
    application, result, stage = _publication_stage(tmp_path)
    receipt = application.store.load(result.receipt_identity)
    conflict = record(receipt.schema, **dict(receipt.data, workbook_bytes=result.workbook_bytes + 1))
    application.store.retain(conflict)
    cleaned = _housekeeper(intraday_research_staging_scope(application)).run_once()
    assert cleaned.removed_files == 0 and stage.exists()
    assert "INTRADAY_RESEARCH_REFERENCE_UNCERTAIN" in cleaned.diagnostics
    # Remove only synthetic conflicting evidence; missing authoritative receipt
    # with its update/pointer retained must still leave the stage owned.
    (application.store.root / "records" / (conflict.identity + ".json")).unlink()
    (application.store.root / "records" / (receipt.identity + ".json")).unlink()
    missing = _housekeeper(intraday_research_staging_scope(application)).run_once()
    assert missing.removed_files == 0 and stage.exists()
    assert "INTRADAY_RESEARCH_INCOMPLETE_RECOVERY" in missing.diagnostics


def test_intraday_publication_proof_does_not_bypass_removal_budget(tmp_path):
    application, result, stage = _publication_stage(tmp_path)
    limits = HousekeepingLimits(max_removed_bytes=result.workbook_bytes - 1, max_elapsed_seconds=5)
    cleaned = _housekeeper(intraday_research_staging_scope(application), limits=limits).run_once()
    assert cleaned.outcome == "LIMIT_REACHED"
    assert "REMOVAL_BYTE_LIMIT" in cleaned.diagnostics
    assert cleaned.removed_files == 0 and stage.exists()


def test_verified_empty_stage_is_disposable_but_unproved_empty_stage_is_retained(tmp_path):
    application, result, stage = _publication_stage(tmp_path)
    (stage / result.workbook_path.name).unlink()
    unknown = stage.parent / digest("PF08-UNPROVED-EMPTY")
    unknown.mkdir()
    cleaned = _housekeeper(intraday_research_staging_scope(application)).run_once()
    assert cleaned.removed_files == 0 and cleaned.removed_directories == 1
    assert not stage.exists() and unknown.exists()
    assert "INTRADAY_RESEARCH_INCOMPLETE_RECOVERY" in cleaned.diagnostics
