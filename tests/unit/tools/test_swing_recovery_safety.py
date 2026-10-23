"""Recovery safety boundaries from ADR-0059; disposable fixtures only.

Run through tools/kronos_test.py. These tests establish safe blocking and
source-admission invariants, not authority to resume a FAILED_FENCED process.
No production bundle, listener, store, Provider or broker is used.
"""
from datetime import UTC, datetime, timedelta
import hmac
import json
import os
import stat
import subprocess

import pytest

from kronos.common import maintenance
from kronos.common.connection_governance import ConnectionGovernanceError
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from tools import runtime_source_gate


GENERATION = "a" * 64
PROOF = "b" * 64
REVISION = "c" * 40
NOW = datetime(2026, 10, 22, 8, tzinfo=UTC)


@pytest.mark.parametrize("reason", [
    "DRAIN_TIMEOUT", "CLEANUP_UNRESOLVED", "OWNER_PROOF_UNAVAILABLE", "HANDOFF_FAILED",
])
def test_failed_fenced_denies_reclaim_finalizer_and_new_admission_without_reset(reason):
    coordinator = MaintenanceAdmissionCoordinator()
    parent = coordinator.admit("WO11")
    child = parent.fork("NOTIFICATION")
    assert coordinator.claim(GENERATION)
    coordinator.draining(GENERATION)
    coordinator.fail(GENERATION, reason)
    before = coordinator.snapshot()
    assert before == {
        "state": "FAILED_FENCED", "generation": GENERATION,
        "owners": {"WO11": 1, "NOTIFICATION": 1}, "failure": reason,
    }
    assert not coordinator.claim(GENERATION)
    assert not coordinator.claim("d" * 64)
    with parent.activate():
        assert coordinator.admit("NOTIFICATION") is None
        assert coordinator.admit_root("SERVER_PULSE") is None
    for operation in (coordinator.finalizer, coordinator.ready,
                      coordinator.draining, coordinator.stopping, coordinator.closed):
        with pytest.raises(ValueError, match="MAINTENANCE_"):
            operation(GENERATION)
        assert coordinator.snapshot() == before
    with pytest.raises(ValueError, match="GENERATION_CONFLICT"):
        coordinator.finalizer("d" * 64)
    assert coordinator.snapshot() == before
    parent.release()
    assert coordinator.snapshot()["owners"] == {"NOTIFICATION": 1}
    child.release()
    assert coordinator.snapshot() == dict(before, owners={})
    with pytest.raises(ValueError, match="OWNER_PROOF_UNAVAILABLE"):
        coordinator.finalizer(GENERATION)
    assert not coordinator.claim("d" * 64)
    assert coordinator.snapshot() == dict(before, owners={})


def test_actual_drain_timeout_preserves_owner_until_its_real_completion():
    coordinator = MaintenanceAdmissionCoordinator()
    owner = coordinator.admit("WO17")
    assert coordinator.claim(GENERATION)
    coordinator.draining(GENERATION)
    assert not coordinator.wait_for_zero(GENERATION, 0)
    before = coordinator.snapshot()
    assert before["state"] == "FAILED_FENCED"
    assert before["failure"] == "DRAIN_TIMEOUT"
    assert before["owners"] == {"WO17": 1}
    with pytest.raises(ValueError, match="STATE_CONFLICT"):
        coordinator.wait_for_zero(GENERATION, 0)
    assert coordinator.snapshot() == before
    owner.release()
    assert coordinator.snapshot() == dict(before, owners={})
    assert coordinator.admit("WO17") is None


@pytest.mark.parametrize("reason", ["CLEANUP_UNRESOLVED", "HANDOFF_FAILED"])
def test_interrupted_finalizer_cannot_be_replaced_or_certify_handoff(reason):
    coordinator = MaintenanceAdmissionCoordinator()
    assert coordinator.claim(GENERATION)
    coordinator.draining(GENERATION)
    assert coordinator.wait_for_zero(GENERATION, 0)
    finalizer = coordinator.finalizer(GENERATION)
    coordinator.fail(GENERATION, reason)
    before = coordinator.snapshot()
    assert before["owners"] == {"FINALIZER": 1}
    with pytest.raises(ValueError, match="OWNER_PROOF_UNAVAILABLE"):
        coordinator.finalizer(GENERATION)
    assert coordinator.snapshot() == before
    finalizer.release()
    with pytest.raises(ValueError, match="OWNER_PROOF_UNAVAILABLE"):
        coordinator.ready(GENERATION)
    assert coordinator.snapshot() == dict(before, owners={})


@pytest.fixture
def signed_handoff(tmp_path):
    root = tmp_path.resolve() / "maintenance"
    drain = {name: 0 for name in (
        "coordinator_owners", "wo11_owned", "wo11_queued", "wo17_owned",
        "wo17_queued", "housekeeping_owned", "bulk_owned", "notification_scheduled",
        "monitoring_sessions", "provider_owned", "provider_leases",
    )}
    drain["notification_checkpoint"] = {
        "state": "VALID_PENDING", "pending_count": 1, "sha256": "d" * 64,
    }
    maintenance.publish_drain_handoff(
        root, generation=GENERATION, parent_pid=os.getpid(), proof=PROOF,
        runtime_identity="e" * 64, loaded_revision=REVISION, drain=drain, now=NOW,
    )
    return root


def _snapshot(root):
    return {path.name: path.read_bytes() for path in root.iterdir()}


def _verify(root, **changes):
    arguments = dict(generation=GENERATION, parent_pid=os.getpid(), proof=PROOF,
                     loaded_revision=REVISION, now=NOW)
    arguments.update(changes)
    return maintenance.verify_drain_handoff(root, **arguments)


def _consume(root, **changes):
    environment = {
        "KRONOS_MAINTENANCE_GENERATION": GENERATION,
        "KRONOS_MAINTENANCE_PARENT": str(os.getpid()),
        "KRONOS_MAINTENANCE_PROOF": PROOF,
    }
    arguments = dict(runtime_identity="f" * 64, now=NOW,
                     process_id=os.getpid() + 1, loaded_revision=REVISION,
                     predecessor_gone=lambda _pid: True, port_free=lambda: True)
    arguments.update(changes)
    return maintenance.consume_drain_handoff(root, environment, **arguments)


@pytest.mark.parametrize("fault", ["truncated", "missing_drain", "active_owner", "checkpoint"])
def test_partial_or_unsafe_handoff_never_creates_a_successor_claim(signed_handoff, fault):
    root = signed_handoff
    path = root / f"{GENERATION}.json"
    item = json.loads(path.read_bytes())
    if fault == "truncated":
        path.write_bytes(path.read_bytes()[:40])
    else:
        if fault == "missing_drain":
            del item["record"]["drain"]["wo11_owned"]
        elif fault == "active_owner":
            item["record"]["drain"]["wo17_queued"] = 1
        else:
            item["record"]["drain"]["notification_checkpoint"]["pending_count"] = 0
        # A valid signature cannot promote incomplete/nonzero owner proof.
        canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        item["proof"] = hmac.new(bytes.fromhex(PROOF), canonical(item["record"]), "sha256").hexdigest()
        path.write_bytes(canonical(item))
    before = _snapshot(root)
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        _verify(root)
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        _consume(root)
    assert _snapshot(root) == before
    assert not tuple(root.glob("*.consumed.json"))


@pytest.mark.parametrize("age", [-1, 45.000001])
def test_future_and_expired_handoff_remain_unconsumed(signed_handoff, age):
    before = _snapshot(signed_handoff)
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        _consume(signed_handoff, now=NOW + timedelta(seconds=age))
    assert _snapshot(signed_handoff) == before


@pytest.mark.parametrize("field,value", [
    ("parent_pid", 1), ("loaded_revision", "0" * 40),
    ("proof", "0" * 64), ("generation", "0" * 64),
])
def test_handoff_ownership_mismatch_is_read_only(signed_handoff, field, value):
    before = _snapshot(signed_handoff)
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        _verify(signed_handoff, **{field: value})
    assert _snapshot(signed_handoff) == before


@pytest.mark.parametrize("boundary", ["predecessor_gone", "port_free"])
def test_valid_handoff_cannot_override_live_predecessor_or_listener(signed_handoff, boundary):
    before = _snapshot(signed_handoff)
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        _consume(signed_handoff, **{boundary: lambda *_args: False})
    assert _snapshot(signed_handoff) == before


@pytest.mark.parametrize("failure_at", ["file", "directory"])
def test_interrupted_consumption_retains_exclusive_claim_and_denies_replay(
    signed_handoff, monkeypatch, failure_at,
):
    root = signed_handoff
    original_handoff = (root / f"{GENERATION}.json").read_bytes()
    real_fsync = maintenance.os.fsync
    failures = []
    def interrupted(descriptor):
        kind = "directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file"
        if kind == failure_at:
            failures.append(kind)
            raise OSError("disposable consumption interruption")
        return real_fsync(descriptor)
    with monkeypatch.context() as patch:
        patch.setattr(maintenance.os, "fsync", interrupted)
        with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
            _consume(root)
    assert failures == [failure_at]
    assert (root / f"{GENERATION}.consumed.json").is_file()
    retained = _snapshot(root)
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        _consume(root, process_id=os.getpid() + 2)
    assert _snapshot(root) == retained
    assert (root / f"{GENERATION}.json").read_bytes() == original_handoff


@pytest.mark.parametrize("partial", [b"{", b"{}"])
def test_partial_prior_claim_is_not_reset_into_a_new_attempt(signed_handoff, partial):
    claim = signed_handoff / f"{GENERATION}.consumed.json"
    claim.write_bytes(partial)
    claim.chmod(0o600)
    before = _snapshot(signed_handoff)
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        _consume(signed_handoff)
    assert _snapshot(signed_handoff) == before


def test_successful_consumption_retains_pending_checkpoint_and_rejects_second_successor(signed_handoff):
    context = _consume(signed_handoff)
    assert context.notification_checkpoint() == {
        "state": "VALID_PENDING", "pending_count": 1, "sha256": "d" * 64,
    }
    before = _snapshot(signed_handoff)
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        _consume(signed_handoff, process_id=os.getpid() + 2)
    assert _snapshot(signed_handoff) == before


@pytest.fixture
def local_rollback_repository(tmp_path):
    """Two source versions and a local-only remote; no retained bundle needed."""
    root = tmp_path / "repository"
    root.mkdir()
    remote = tmp_path / "local-only-remote.git"
    def git(*arguments):
        return subprocess.check_output(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *arguments],
            cwd=root, stderr=subprocess.DEVNULL, text=True,
        ).strip()
    git("init", "--bare", str(remote))
    git("init", "-b", "develop")
    git("config", "user.name", "Disposable Recovery Safety")
    git("config", "user.email", "recovery-safety@example.invalid")
    (root / "tools").mkdir()
    source = root / "tools" / "fixture.py"
    source.write_text("VALUE = 'predecessor'\n")
    git("add", ".")
    git("commit", "-m", "disposable predecessor")
    predecessor = git("rev-parse", "HEAD")
    source.write_text("VALUE = 'successor'\n")
    git("commit", "-am", "disposable successor")
    successor = git("rev-parse", "HEAD")
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "develop")
    return root, git, remote, predecessor, successor


def test_rollback_tree_requires_new_forward_commit_and_exact_publication(local_rollback_repository):
    root, git, _, predecessor, successor = local_rollback_repository
    git("read-tree", "--reset", "-u", predecessor)
    git("commit", "-m", "disposable forward rollback")
    recovery = git("rev-parse", "HEAD")
    assert recovery not in {predecessor, successor}
    assert git("rev-parse", "HEAD^") == successor
    assert git("rev-parse", "HEAD^{tree}") == git("rev-parse", predecessor + "^{tree}")
    with pytest.raises(ValueError, match="SOURCE_REVISION_NOT_AUTHORIZED"):
        runtime_source_gate.qualify_repository(root)
    git("push", "origin", "develop")
    assert runtime_source_gate.qualify_repository(root) == recovery


def test_old_commit_cannot_borrow_published_successor_authority(local_rollback_repository):
    root, git, _, predecessor, _ = local_rollback_repository
    git("reset", "--hard", predecessor)  # Disposable test repository only.
    with pytest.raises(ValueError, match="SOURCE_REVISION_NOT_AUTHORIZED"):
        runtime_source_gate.qualify_repository(root)


def test_rollback_overlay_cannot_borrow_current_commit_authority(local_rollback_repository):
    root, git, _, predecessor, _ = local_rollback_repository
    (root / "tools" / "fixture.py").write_text(git("show", predecessor + ":tools/fixture.py") + "\n")
    with pytest.raises(ValueError, match="SOURCE_NOT_CLEAN"):
        runtime_source_gate.qualify_repository(root)


def test_current_tracking_ref_cannot_hide_changed_remote_authority(local_rollback_repository):
    root, git, remote, _, successor = local_rollback_repository
    later = git("commit-tree", "HEAD^{tree}", "-p", successor, "-m", "disposable competing publication")
    git("--git-dir=" + str(remote), "fetch", str(root), later)
    git("--git-dir=" + str(remote), "update-ref", "refs/heads/develop", later, successor)
    assert git("rev-parse", "origin/develop") == successor
    with pytest.raises(ValueError, match="SOURCE_REVISION_NOT_AUTHORIZED"):
        runtime_source_gate.qualify_repository(root)
