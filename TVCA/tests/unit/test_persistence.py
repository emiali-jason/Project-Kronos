from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from tvca import (CoreFailureCode, CoreStatus, IdentityChannel, RecordRef,
                  TvcaCore, TvcaCoreError)
from tvca.contracts import _canonical
from tvca import persistence


REQUEST = "12345678-1234-4234-8234-123456789abc"
NOW = datetime(2026, 9, 6, tzinfo=UTC)


def path(root, revision=0):
    return root / "records" / REQUEST / f"{revision}.json"


def setup(root):
    core = TvcaCore(root.resolve())
    first = core.create(REQUEST, "Expected", NOW)
    second = core.record_identity(first.ref, IdentityChannel.ADAPTER_OBSERVED, "raw", NOW)
    third = core.seal(second.ref, NOW)
    return core, first, second, third


def fail(code):
    return pytest.raises(TvcaCoreError, match=f"^{code}$")


def test_deterministic_bytes_sha_restart_and_exact_historical_restore(tmp_path):
    core, first, second, third = setup(tmp_path)
    for record in (first, second, third):
        data = path(tmp_path, record.revision).read_bytes()
        assert data == _canonical(record)
        assert sha256(data).hexdigest() == record.ref.sha256
    del core
    reopened = TvcaCore(tmp_path.resolve())
    assert reopened.restore(second.ref) == second
    assert reopened.restore(first.ref) == first
    assert reopened.restore(third.ref) == third
    assert len(list(tmp_path.rglob("*.json"))) == 3


def test_conflicting_bytes_never_overwritten(tmp_path):
    core = TvcaCore(tmp_path.resolve())
    first = core.create(REQUEST, "Expected", NOW)
    path(tmp_path).write_bytes(b"{}")
    with fail("RECORD_CONFLICT"):
        core.create(REQUEST, "Expected", NOW)
    assert path(tmp_path).read_bytes() == b"{}"
    with fail("INTEGRITY_FAILURE"):
        core.restore(first.ref)


def test_missing_exact_record_and_invalid_ref(tmp_path):
    core = TvcaCore(tmp_path.resolve())
    with fail("RECORD_NOT_FOUND"):
        core.restore(RecordRef(REQUEST, 0, "a" * 64))
    with fail("INVALID_INPUT"):
        core.restore("latest")


def test_wrong_expected_digest_is_rejected(tmp_path):
    core, first, _, _ = setup(tmp_path)
    with fail("INTEGRITY_FAILURE"):
        core.restore(replace(first.ref, sha256="0" * 64))


@pytest.mark.parametrize("damage", ["malformed", "duplicate", "newline", "indent",
                                     "version", "unknown", "missing_field", "wrong_request",
                                     "wrong_revision", "invalid_utf8"])
def test_corrupt_present_record_is_not_restored(damage, tmp_path):
    core = TvcaCore(tmp_path.resolve())
    first = core.create(REQUEST, "Expected", NOW)
    data = path(tmp_path).read_bytes()
    payload = json.loads(data)
    if damage == "malformed":
        data = b"{"
    elif damage == "duplicate":
        data = b'{"revision":0,' + data[1:]
    elif damage == "newline":
        data += b"\n"
    elif damage == "indent":
        data = json.dumps(payload, indent=2).encode()
    elif damage == "invalid_utf8":
        data = b"\xff"
    else:
        if damage == "version":
            payload["format_version"] = 2
        elif damage == "unknown":
            payload["future_field"] = True
        elif damage == "missing_field":
            del payload["status"]
        elif damage == "wrong_request":
            payload["request_id"] = "22345678-1234-4234-8234-123456789abc"
        elif damage == "wrong_revision":
            payload["revision"] = 1
            payload["previous_record_sha256"] = "a" * 64
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path(tmp_path).write_bytes(data)
    # Even a caller supplying the damaged payload's digest cannot bypass parsing/binding.
    damaged_ref = replace(first.ref, sha256=sha256(data).hexdigest())
    with fail("INTEGRITY_FAILURE"):
        core.restore(damaged_ref)


@pytest.mark.parametrize("damage", ["missing_parent", "wrong_digest", "expected_changed",
                                     "backward_time", "two_channels", "after_sealed",
                                     "rewritten_channel"])
def test_broken_chain_and_illegal_stored_transition(damage, tmp_path):
    core, first, second, third = setup(tmp_path)
    target = second
    if damage == "missing_parent":
        path(tmp_path, 0).unlink()
    elif damage == "wrong_digest":
        target = replace(second, previous_record_sha256="0" * 64)
    elif damage == "expected_changed":
        target = replace(second, expected_subject_identity="changed")
    elif damage == "backward_time":
        target = replace(second, recorded_at=NOW - timedelta(seconds=1))
    elif damage == "two_channels":
        target = replace(second, visually_observed_identity="second")
    elif damage == "after_sealed":
        target = replace(third, revision=3, previous_record_sha256=third.ref.sha256)
    elif damage == "rewritten_channel":
        target = replace(third, status=CoreStatus.OPEN, adapter_observed_identity="changed")
    path(tmp_path, target.revision).write_bytes(_canonical(target))
    with fail("INTEGRITY_FAILURE"):
        core.restore(target.ref)


def test_revision_gap_blocks_append_and_does_not_repair_history(tmp_path):
    core, first, second, third = setup(tmp_path)
    path(tmp_path, 1).unlink()
    with fail("INTEGRITY_FAILURE"):
        core.restore(third.ref)
    with fail("INTEGRITY_FAILURE"):
        core.record_identity(first.ref, IdentityChannel.ADAPTER_OBSERVED, "raw", NOW)
    assert not path(tmp_path, 1).exists()
    assert path(tmp_path, 2).read_bytes() == _canonical(third)


def test_parent_tamper_detected_by_child_digest(tmp_path):
    core, first, second, _ = setup(tmp_path)
    path(tmp_path, 0).write_bytes(_canonical(replace(first, expected_subject_identity="changed")))
    with fail("INTEGRITY_FAILURE"):
        core.restore(second.ref)


def test_temporary_artifact_and_mtime_cannot_supply_missing_record(tmp_path):
    core, first, second, third = setup(tmp_path)
    temporary = path(tmp_path, 1).with_name(".tmp-incomplete")
    temporary.write_bytes(_canonical(second))
    os.utime(path(tmp_path, 0), (1_900_000_000, 1_900_000_000))
    os.utime(path(tmp_path, 2), (1, 1))
    assert core.restore(first.ref) == first
    path(tmp_path, 1).unlink()
    with fail("RECORD_NOT_FOUND"):
        core.restore(second.ref)
    with fail("INTEGRITY_FAILURE"):
        core.restore(third.ref)


def test_orphan_temp_is_ignored_for_valid_publication(tmp_path):
    core = TvcaCore(tmp_path.resolve())
    path(tmp_path).parent.mkdir(parents=True)
    orphan = path(tmp_path).with_name(".tmp-abandoned")
    orphan.write_bytes(b"incomplete")
    record = core.create(REQUEST, "Expected", NOW)
    assert core.restore(record.ref) == record
    assert orphan.read_bytes() == b"incomplete"


@pytest.mark.parametrize("request_id", ["../escape", "/escape", "a/b", "..", "a\\b"])
def test_request_id_traversal_rejected_before_any_write(request_id, tmp_path):
    core = TvcaCore(tmp_path.resolve())
    with fail("INVALID_INPUT"):
        core.create(request_id, "Expected", NOW)
    assert list(tmp_path.iterdir()) == []


def test_identity_text_is_never_a_path(tmp_path):
    core = TvcaCore(tmp_path.resolve())
    record = core.create(REQUEST, "../../outside/ RAW ", NOW)
    second = core.record_identity(record.ref, IdentityChannel.ADAPTER_OBSERVED,
                                  "/outside/../ raw ", NOW)
    assert core.restore(second.ref).adapter_observed_identity == "/outside/../ raw "
    assert {p.name for p in path(tmp_path).parent.iterdir()} == {"0.json", "1.json"}


@pytest.mark.parametrize("kind", ["relative", "filesystem_root", "absent", "file", "string"])
def test_invalid_storage_root(kind, tmp_path):
    file = tmp_path / "file"
    file.write_text("not a directory")
    root = {"relative": Path("relative"), "filesystem_root": Path("/"),
            "absent": tmp_path / "missing", "file": file, "string": str(tmp_path)}[kind]
    with fail("STORAGE_ROOT_INVALID"):
        TvcaCore(root)


@pytest.mark.parametrize("component", ["root", "ancestor", "records", "request", "record"])
def test_symlink_roots_and_components_fail_closed(component, tmp_path):
    root = tmp_path.resolve() / "root"
    outside = tmp_path.resolve() / "outside"
    root.mkdir()
    outside.mkdir()
    if component == "root":
        link = tmp_path / "root-link"
        link.symlink_to(root, target_is_directory=True)
        with fail("STORAGE_ROOT_INVALID"):
            TvcaCore(link)
        return
    if component == "ancestor":
        link = tmp_path / "parent-link"
        link.symlink_to(tmp_path.resolve(), target_is_directory=True)
        with fail("STORAGE_ROOT_INVALID"):
            TvcaCore(link / "root")
        return
    core = TvcaCore(root)
    destination = {"records": root / "records", "request": path(root).parent,
                   "record": path(root)}[component]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(outside / "missing" if component == "record" else outside,
                           target_is_directory=component != "record")
    with fail("STORAGE_ROOT_INVALID"):
        core.create(REQUEST, "Expected", NOW)
    assert list(outside.iterdir()) == []


def test_read_symlink_rejected_after_original_record_removed(tmp_path):
    core = TvcaCore(tmp_path.resolve())
    record = core.create(REQUEST, "Expected", NOW)
    external = tmp_path / "copy"
    external.write_bytes(path(tmp_path).read_bytes())
    path(tmp_path).unlink()
    path(tmp_path).symlink_to(external)
    with fail("STORAGE_ROOT_INVALID"):
        core.restore(record.ref)


def test_io_failure_before_publication_leaves_no_accepted_record_and_can_replay(tmp_path, monkeypatch):
    core = TvcaCore(tmp_path.resolve())
    original = persistence.os.link
    def unavailable(*args, **kwargs):
        raise OSError("private filesystem detail")
    monkeypatch.setattr(persistence.os, "link", unavailable)
    with fail("STORAGE_IO_FAILURE") as caught:
        core.create(REQUEST, "Expected", NOW)
    assert "private" not in str(caught.value)
    assert not path(tmp_path).exists()
    assert not list(tmp_path.rglob(".tmp-*"))
    monkeypatch.setattr(persistence.os, "link", original)
    record = core.create(REQUEST, "Expected", NOW)
    assert core.restore(record.ref) == record


def test_io_failure_after_publication_resolved_by_exact_replay(tmp_path, monkeypatch):
    core = TvcaCore(tmp_path.resolve())
    original = persistence._RecordStore._sync_directory
    def unavailable(directory):
        raise OSError("directory fsync unavailable")
    monkeypatch.setattr(persistence._RecordStore, "_sync_directory", staticmethod(unavailable))
    with fail("STORAGE_IO_FAILURE"):
        core.create(REQUEST, "Expected", NOW)
    before = path(tmp_path).read_bytes()
    with fail("STORAGE_IO_FAILURE"):
        core.create(REQUEST, "Expected", NOW)
    monkeypatch.setattr(persistence._RecordStore, "_sync_directory", staticmethod(original))
    record = core.create(REQUEST, "Expected", NOW)
    assert path(tmp_path).read_bytes() == before
    assert core.restore(record.ref) == record
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_exclusive_publication_never_replaces_a_destination(tmp_path, monkeypatch):
    core = TvcaCore(tmp_path.resolve())
    original = persistence.os.link
    def occupied(source, destination):
        Path(destination).write_bytes(b"occupied")
        return original(source, destination)
    monkeypatch.setattr(persistence.os, "link", occupied)
    with fail("RECORD_CONFLICT"):
        core.create(REQUEST, "Expected", NOW)
    assert path(tmp_path).read_bytes() == b"occupied"


def test_read_io_error_is_explicit_and_does_not_change_record(tmp_path, monkeypatch):
    core = TvcaCore(tmp_path.resolve())
    record = core.create(REQUEST, "Expected", NOW)
    original = Path.read_bytes
    def unavailable(self):
        raise PermissionError("private path")
    monkeypatch.setattr(Path, "read_bytes", unavailable)
    with fail("STORAGE_IO_FAILURE"):
        core.restore(record.ref)
    monkeypatch.setattr(Path, "read_bytes", original)
    assert core.restore(record.ref) == record


def test_file_fsync_failure_prevents_publication(tmp_path, monkeypatch):
    core = TvcaCore(tmp_path.resolve())
    original = persistence.os.fsync
    def unavailable(descriptor):
        raise OSError("file flush failed")
    monkeypatch.setattr(persistence.os, "fsync", unavailable)
    with fail("STORAGE_IO_FAILURE"):
        core.create(REQUEST, "Expected", NOW)
    assert not path(tmp_path).exists()
    assert not list(tmp_path.rglob(".tmp-*"))
    monkeypatch.setattr(persistence.os, "fsync", original)
    record = core.create(REQUEST, "Expected", NOW)
    assert core.restore(record.ref) == record
