"""Recovery-only private control custody; disposable files and no live service."""
from __future__ import annotations

import os

import pytest

from kronos.browser.restart_control import BrowserBackendRestartControl


@pytest.fixture
def control(tmp_path):
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    value = BrowserBackendRestartControl(parent / "backend.control", os.getpid(), "a" * 64)
    value.path.write_bytes(value._serialized().encode("ascii"))
    value.path.chmod(0o600)
    return value


def invoke(control, operation):
    return getattr(control, operation)()


def replace_on_control_read(monkeypatch, control, mutation):
    read = os.read
    inode = control.path.stat().st_ino
    changed = False

    def changing(fd, count):
        nonlocal changed
        raw = read(fd, count)
        if not changed and count == 256 and os.fstat(fd).st_ino == inode:
            changed = True
            mutation()
        return raw

    monkeypatch.setattr(os, "read", changing)


def test_exact_private_read_and_once_only_durable_removal(control):
    assert control.private_bytes_for_recovery() == control._serialized().encode("ascii")
    assert control.owns_current_process()
    control.remove_for_recovery()
    assert not control.path.exists()
    assert control.failed_fenced_owner_status("CONTROL")["control_removed"] is True
    with pytest.raises(ValueError):
        control.remove_for_recovery()


@pytest.mark.parametrize("operation", ["private_bytes_for_recovery", "remove_for_recovery"])
def test_ancestor_symlink_is_denied_without_touching_actual_control(control, tmp_path, operation):
    alias = tmp_path / "alias"
    alias.symlink_to(control.path.parent.parent, target_is_directory=True)
    through_alias = BrowserBackendRestartControl(alias / "private" / control.path.name,
        control.process_id, control._token)
    with pytest.raises((OSError, ValueError)):
        invoke(through_alias, operation)
    assert control.private_bytes_for_recovery() == control._serialized().encode("ascii")


@pytest.mark.parametrize("operation", ["private_bytes_for_recovery", "remove_for_recovery"])
def test_named_inode_replacement_during_read_is_denied(control, monkeypatch, operation):
    expected = control._serialized().encode("ascii")

    def replace():
        replacement = control.path.with_name("replacement")
        replacement.write_bytes(expected)
        replacement.chmod(0o600)
        os.replace(replacement, control.path)

    replace_on_control_read(monkeypatch, control, replace)
    with pytest.raises(ValueError):
        invoke(control, operation)
    assert control.path.read_bytes() == expected
    assert not control._ff_control_removed


@pytest.mark.parametrize("operation", ["private_bytes_for_recovery", "remove_for_recovery"])
def test_post_read_file_metadata_change_is_denied(control, monkeypatch, operation):
    info = control.path.stat()
    replace_on_control_read(monkeypatch, control,
        lambda: os.utime(control.path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000)))
    with pytest.raises(ValueError):
        invoke(control, operation)
    assert control.path.exists()
    assert not control._ff_control_removed


@pytest.mark.parametrize("operation", ["private_bytes_for_recovery", "remove_for_recovery"])
def test_parent_replacement_during_read_is_denied(control, monkeypatch, operation):
    original = control.path.parent.with_name("retained-parent")
    expected = control._serialized().encode("ascii")

    def replace():
        control.path.parent.rename(original)
        control.path.parent.mkdir(mode=0o700)
        control.path.write_bytes(expected)
        control.path.chmod(0o600)

    replace_on_control_read(monkeypatch, control, replace)
    with pytest.raises(ValueError):
        invoke(control, operation)
    assert (original / control.path.name).read_bytes() == expected
    assert control.path.read_bytes() == expected
    assert not control._ff_control_removed


def test_parent_replacement_after_unlink_is_unresolved(control, monkeypatch):
    fsync = os.fsync
    original = control.path.parent.with_name("retained-parent")
    changed = False

    def changing(fd):
        nonlocal changed
        fsync(fd)
        if not changed:
            changed = True
            control.path.parent.rename(original)
            control.path.parent.mkdir(mode=0o700)

    monkeypatch.setattr(os, "fsync", changing)
    with pytest.raises(ValueError):
        control.remove_for_recovery()
    assert not control._ff_control_removed
    assert not (original / control.path.name).exists()


def test_completed_removal_cannot_certify_replaced_parent(control):
    control.remove_for_recovery()
    control.path.parent.rename(control.path.parent.with_name("retained-parent"))
    control.path.parent.mkdir(mode=0o700)
    with pytest.raises(ValueError):
        control.failed_fenced_owner_status("CONTROL")


@pytest.mark.parametrize("operation", ["private_bytes_for_recovery", "remove_for_recovery"])
def test_hardlink_and_permissive_parent_are_denied(control, operation):
    alias = control.path.with_name("hardlink")
    os.link(control.path, alias)
    with pytest.raises(ValueError):
        invoke(control, operation)
    alias.unlink()
    control.path.parent.chmod(0o755)
    with pytest.raises(ValueError):
        invoke(control, operation)
    assert control.path.exists()
