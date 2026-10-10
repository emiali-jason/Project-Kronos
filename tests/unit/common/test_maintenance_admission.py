from __future__ import annotations

from threading import Event, Lock, Thread
from datetime import UTC, datetime, timedelta
import json
import os

import pytest

from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.common.maintenance import (
    DrainStartupContext, consume_drain_handoff, consume_handoff, publish_drain_handoff,
    verify_drain_handoff,
)
from kronos.common.connection_governance import ConnectionGovernanceError


_GENERATION = "a" * 64


def test_claim_fences_late_admission_and_waits_for_final_child() -> None:
    owner = MaintenanceAdmissionCoordinator()
    parent = owner.admit("BROWSER_POST")
    assert parent is not None
    child = parent.fork("FINALIZER")
    assert owner.claim(_GENERATION)
    owner.draining(_GENERATION)
    assert owner.admit("BROWSER_POST") is None
    parent.release()
    observed = Event()
    completed = Event()

    def wait() -> None:
        observed.set()
        assert owner.wait_for_zero(_GENERATION, 1)
        completed.set()

    thread = Thread(target=wait)
    thread.start()
    assert observed.wait(1)
    assert not completed.is_set()
    child.release()
    thread.join(1)
    assert completed.is_set()
    owner.finalizer(_GENERATION).release()
    owner.ready(_GENERATION)
    assert owner.snapshot() == {
        "state": "HANDOFF_READY", "generation": _GENERATION,
        "owners": {}, "failure": None,
    }


def test_timeout_and_generation_conflict_remain_fenced() -> None:
    owner = MaintenanceAdmissionCoordinator()
    ticket = owner.admit("WO11")
    assert ticket is not None
    assert owner.claim(_GENERATION)
    assert not owner.claim("b" * 64)
    owner.draining(_GENERATION)
    with pytest.raises(ValueError, match="GENERATION_CONFLICT"):
        owner.wait_for_zero("b" * 64, 0)
    assert not owner.wait_for_zero(_GENERATION, 0)
    assert owner.snapshot()["failure"] == "DRAIN_TIMEOUT"
    assert owner.admit("WO11") is None
    ticket.release()
    with pytest.raises(ValueError, match="OWNER_PROOF_UNAVAILABLE"):
        owner.ready(_GENERATION)


def test_owner_underflow_fails_closed() -> None:
    owner = MaintenanceAdmissionCoordinator()
    ticket = owner.admit("WO17")
    assert ticket is not None
    assert owner.claim(_GENERATION)
    ticket.release()
    with pytest.raises(ValueError, match="OWNER_UNDERFLOW"):
        ticket.release()
    assert owner.snapshot()["state"] == "FAILED_FENCED"


def test_admitted_parent_can_fork_final_write_after_fence() -> None:
    owner = MaintenanceAdmissionCoordinator()
    parent = owner.admit("WO11")
    assert parent is not None
    assert owner.claim(_GENERATION)
    owner.draining(_GENERATION)
    with parent.activate():
        final_write = owner.admit("NOTIFICATION")
        assert final_write is not None
    assert owner.admit("NOTIFICATION") is None
    parent.release()
    assert owner.snapshot()["owners"] == {"NOTIFICATION": 1}
    final_write.release()
    assert owner.wait_for_zero(_GENERATION, 0)
    owner.finalizer(_GENERATION).release()
    owner.ready(_GENERATION)


def test_finalizing_stopping_and_closed_are_ordered() -> None:
    owner = MaintenanceAdmissionCoordinator()
    assert owner.claim(_GENERATION)
    owner.draining(_GENERATION)
    with pytest.raises(ValueError, match="OWNER_PROOF_UNAVAILABLE"):
        owner.ready(_GENERATION)
    owner.finalizer(_GENERATION).release()
    owner.ready(_GENERATION)
    owner.stopping(_GENERATION)
    owner.closed(_GENERATION)
    assert owner.snapshot()["state"] == "CLOSED"


def test_claim_never_waits_for_domain_lock_held_by_admitted_worker() -> None:
    owner = MaintenanceAdmissionCoordinator()
    domain_lock = Lock()
    domain_lock.acquire()
    admitted, finished = Event(), Event()

    def work() -> None:
        ticket = owner.admit("WO17")
        assert ticket is not None
        admitted.set()
        with domain_lock:
            pass
        ticket.release()
        finished.set()

    worker = Thread(target=work)
    worker.start()
    assert admitted.wait(1)
    assert owner.claim(_GENERATION)  # Must not acquire the blocked domain lock.
    owner.draining(_GENERATION)
    domain_lock.release()
    worker.join(1)
    assert finished.is_set()
    assert owner.wait_for_zero(_GENERATION, 0)


def test_signed_v2_handoff_requires_exact_zero_and_v1_reader_rejects_it(tmp_path) -> None:
    drain = {name: 0 for name in (
        "coordinator_owners", "wo11_owned", "wo11_queued", "wo17_owned",
        "wo17_queued", "housekeeping_owned", "bulk_owned",
        "notification_scheduled", "monitoring_sessions", "provider_owned",
        "provider_leases",
    )}
    drain["notification_checkpoint"] = {"state": "EMPTY", "pending_count": 0,
                                         "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
    root = tmp_path / "maintenance"
    now = datetime.now(UTC)
    publish_drain_handoff(
        root, generation=_GENERATION, parent_pid=os.getpid(),
        proof="d" * 64, runtime_identity="e" * 64,
        loaded_revision="f" * 40, drain=drain, now=now,
    )
    record = json.loads((root / f"{_GENERATION}.json").read_text())
    assert record["record"]["schema"] == "KRONOS_MAINTENANCE_HANDOFF_V2"
    assert record["record"]["drain"] == drain
    with pytest.raises(ConnectionGovernanceError, match="HANDOFF_REJECTED"):
        consume_handoff(root, {
            "KRONOS_MAINTENANCE_GENERATION": _GENERATION,
            "KRONOS_MAINTENANCE_PARENT": str(os.getpid()),
            "KRONOS_MAINTENANCE_PROOF": "d" * 64,
        }, runtime_identity="e" * 64, now=now, process_id=os.getpid() + 1)
    with pytest.raises(ConnectionGovernanceError, match="HANDOFF_INVALID"):
        publish_drain_handoff(
            root, generation="b" * 64, parent_pid=os.getpid(),
            proof="d" * 64, runtime_identity="e" * 64,
            loaded_revision="f" * 40,
            drain=dict(drain, wo11_queued=1), now=now,
        )


def test_v2_launch_check_is_read_only_and_successor_claims_once(tmp_path) -> None:
    root = tmp_path / "maintenance"
    now = datetime.now(UTC)
    drain = {name: 0 for name in (
        "coordinator_owners", "wo11_owned", "wo11_queued", "wo17_owned",
        "wo17_queued", "housekeeping_owned", "bulk_owned",
        "notification_scheduled", "monitoring_sessions", "provider_owned",
        "provider_leases",
    )}
    drain["notification_checkpoint"] = {"state": "EMPTY", "pending_count": 0,
                                         "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
    publish_drain_handoff(root, generation=_GENERATION, parent_pid=os.getpid(),
        proof="d" * 64, runtime_identity="e" * 64,
        loaded_revision="f" * 40, drain=drain, now=now)
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    assert verify_drain_handoff(root, generation=_GENERATION, parent_pid=os.getpid(),
        proof="d" * 64, loaded_revision="f" * 40, now=now)["drain"] == drain
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        verify_drain_handoff(root, generation=_GENERATION, parent_pid=os.getpid(),
            proof="d" * 64, loaded_revision="a" * 40, now=now)
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        verify_drain_handoff(root, generation=_GENERATION, parent_pid=os.getpid(),
            proof="d" * 64, loaded_revision="f" * 40,
            now=now + timedelta(seconds=46))
    env = {"KRONOS_MAINTENANCE_GENERATION": _GENERATION,
           "KRONOS_MAINTENANCE_PARENT": str(os.getpid()),
           "KRONOS_MAINTENANCE_PROOF": "d" * 64}
    context = consume_drain_handoff(root, env, runtime_identity="a" * 64,
        now=now, process_id=os.getpid() + 1,
        loaded_revision="f" * 40,
        predecessor_gone=lambda _pid: True, port_free=lambda: True)
    assert isinstance(context, DrainStartupContext)
    assert context.generation == _GENERATION
    assert context.notification_checkpoint() == drain["notification_checkpoint"]
    assert env == {}
    assert (root / f"{_GENERATION}.consumed.json").is_file()
    with pytest.raises(ConnectionGovernanceError, match="DRAIN_HANDOFF_REJECTED"):
        consume_drain_handoff(root, {"KRONOS_MAINTENANCE_GENERATION": _GENERATION,
            "KRONOS_MAINTENANCE_PARENT": str(os.getpid()),
            "KRONOS_MAINTENANCE_PROOF": "d" * 64},
            runtime_identity="b" * 64, now=now,
            process_id=os.getpid() + 2, loaded_revision="f" * 40,
            predecessor_gone=lambda _pid: True, port_free=lambda: True)


def test_v2_handoff_signs_valid_pending_replay_and_rejects_invalid_checkpoint(tmp_path):
    drain = {name: 0 for name in (
        "coordinator_owners", "wo11_owned", "wo11_queued", "wo17_owned",
        "wo17_queued", "housekeeping_owned", "bulk_owned",
        "notification_scheduled", "monitoring_sessions", "provider_owned",
        "provider_leases",
    )}
    drain["notification_checkpoint"] = {
        "state": "VALID_PENDING", "pending_count": 2, "sha256": "a" * 64,
    }
    now = datetime.now(UTC)
    root = tmp_path / "maintenance"
    publish_drain_handoff(root, generation=_GENERATION, parent_pid=os.getpid(),
        proof="d" * 64, runtime_identity="e" * 64,
        loaded_revision="f" * 40, drain=drain, now=now)
    assert verify_drain_handoff(root, generation=_GENERATION, parent_pid=os.getpid(),
        proof="d" * 64, loaded_revision="f" * 40, now=now)["drain"] == drain
    for invalid in (
        dict(drain, notification_checkpoint={"state": "EMPTY", "pending_count": 2,
                                             "sha256": "a" * 64}),
        dict(drain, notification_checkpoint={"state": "VALID_PENDING", "pending_count": 0,
                                             "sha256": "a" * 64}),
        dict(drain, notification_checkpoint={"state": "VALID_PENDING", "pending_count": 2,
                                             "sha256": "invalid"}),
    ):
        with pytest.raises(ConnectionGovernanceError, match="HANDOFF_INVALID"):
            publish_drain_handoff(root, generation="b" * 64, parent_pid=os.getpid(),
                proof="d" * 64, runtime_identity="e" * 64,
                loaded_revision="f" * 40, drain=invalid, now=now)


def test_wo08_root_is_open_only_while_existing_child_contract_is_preserved():
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    c=MaintenanceAdmissionCoordinator();parent=c.admit('BROWSER_POST')
    root=c.admit_root('WO08_SHADOW');assert root.generation=='OPEN'
    assert c.claim('e'*64)
    with parent.activate():
        assert c.admit_root('WO08_SHADOW') is None
        child=c.admit('SWING_RESEARCH');assert child is not None;child.release()
    c.draining('e'*64)
    assert c.snapshot()['owners']=={'BROWSER_POST':1,'WO08_SHADOW':1}
    root.release();parent.release();assert c.wait_for_zero('e'*64,0)
