"""One-use controlled restart handoff and scoped expected-disconnect cause."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import hmac
import json
import os
import errno
from pathlib import Path
import re
import socket
import sys

from kronos.common.connection_governance import (
    ConnectionGovernanceError, _bytes, immutable_write, private_directory,
)

# Existing governed launcher waits at most 15s for shutdown plus 30s for startup.
HANDOFF_SECONDS = 45
_ENV = ("KRONOS_MAINTENANCE_GENERATION", "KRONOS_MAINTENANCE_PARENT", "KRONOS_MAINTENANCE_PROOF")
_expected_disconnect = ContextVar("expected_disconnect", default=None)
_DRAIN_ZERO_FIELDS = frozenset({
    "coordinator_owners", "wo11_owned", "wo11_queued", "wo17_owned",
    "wo17_queued", "housekeeping_owned", "bulk_owned",
    "notification_scheduled", "monitoring_sessions", "provider_owned",
    "provider_leases",
})
_DRAIN_FIELDS = _DRAIN_ZERO_FIELDS | {"notification_checkpoint"}


@dataclass(frozen=True, slots=True)
class DrainStartupContext:
    """Verified one-use V2 authority retained until notification composition."""

    generation: str
    notification_state: str
    notification_pending_count: int
    notification_sha256: str

    def notification_checkpoint(self) -> dict[str, object]:
        return {"state": self.notification_state,
                "pending_count": self.notification_pending_count,
                "sha256": self.notification_sha256}


def _valid_notification_checkpoint(value: object) -> bool:
    return (
        type(value) is dict
        and set(value) == {"state", "pending_count", "sha256"}
        and value["state"] in {"EMPTY", "VALID_PENDING"}
        and type(value["pending_count"]) is int
        and value["pending_count"] >= 0
        and (value["state"] == "EMPTY") == (value["pending_count"] == 0)
        and type(value["sha256"]) is str
        and re.fullmatch(r"[a-f0-9]{64}", value["sha256"]) is not None
    )


def _valid_drain(value: object) -> bool:
    return (
        type(value) is dict and set(value) == _DRAIN_FIELDS
        and all(type(value[key]) is int and value[key] == 0
                for key in _DRAIN_ZERO_FIELDS)
        and _valid_notification_checkpoint(value["notification_checkpoint"])
    )


def publish_handoff(path: Path, *, generation: str, parent_pid: int, proof: str,
                    runtime_identity: str, now: datetime) -> None:
    if (re.fullmatch(r"[a-f0-9]{64}", generation) is None
        or re.fullmatch(r"[a-f0-9]{64}", proof) is None
        or parent_pid != os.getpid() or now.tzinfo is None):
        raise ConnectionGovernanceError("MAINTENANCE_HANDOFF_INVALID")
    core = {"schema": "KRONOS_MAINTENANCE_HANDOFF_V1", "generation": generation,
            "parent_pid": parent_pid, "runtime_identity": runtime_identity,
            "created_at": now.isoformat()}
    immutable_write(path / f"{generation}.json", {
        "record": core, "proof": hmac.new(bytes.fromhex(proof), _bytes(core), "sha256").hexdigest(),
    })


def publish_drain_handoff(path: Path, *, generation: str, parent_pid: int,
                          proof: str, runtime_identity: str, loaded_revision: str,
                          drain: dict[str, object], now: datetime) -> None:
    """Sign an exact fenced-zero proof without changing historical V1 bytes.

    The successor's V2 consumer belongs to the separately qualified launcher
    slice. Existing V1 consumption deliberately rejects this schema.
    """
    if (re.fullmatch(r"[a-f0-9]{64}", generation) is None
        or re.fullmatch(r"[a-f0-9]{64}", proof) is None
        or re.fullmatch(r"[a-f0-9]{64}", runtime_identity) is None
        or re.fullmatch(r"[a-f0-9]{40}", loaded_revision) is None
        or parent_pid != os.getpid() or now.tzinfo is None
        or not _valid_drain(drain)):
        raise ConnectionGovernanceError("MAINTENANCE_DRAIN_HANDOFF_INVALID")
    core = {
        "schema": "KRONOS_MAINTENANCE_HANDOFF_V2",
        "generation": generation,
        "parent_pid": parent_pid,
        "runtime_identity": runtime_identity,
        "loaded_revision": loaded_revision,
        "drain": dict(sorted(drain.items())),
        "created_at": now.isoformat(),
    }
    immutable_write(path / f"{generation}.json", {
        "record": core,
        "proof": hmac.new(bytes.fromhex(proof), _bytes(core), "sha256").hexdigest(),
    })


def consume_handoff(path: Path, environment, *, runtime_identity: str,
                    now: datetime, process_id: int | None = None) -> str | None:
    values = [environment.pop(key, None) for key in _ENV]
    if not any(v is not None for v in values):
        return None
    generation, parent, proof = values
    try:
        if (any(not isinstance(v, str) for v in values)
            or re.fullmatch(r"[a-f0-9]{64}", generation) is None
            or re.fullmatch(r"[a-f0-9]{64}", proof) is None):
            raise ValueError
        private_directory(path)
        source = path / f"{generation}.json"
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            stat = os.fstat(handle.fileno())
            if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
                raise ValueError
            item = json.loads(handle.read(4096))
        core = item["record"]
        pid = os.getpid() if process_id is None else process_id
        if (set(item) != {"record", "proof"}
            or set(core) != {"schema", "generation", "parent_pid", "runtime_identity", "created_at"}
            or core["schema"] != "KRONOS_MAINTENANCE_HANDOFF_V1"
            or core["generation"] != generation or str(core["parent_pid"]) != parent
            or core["parent_pid"] == pid
            or not hmac.compare_digest(item["proof"], hmac.new(bytes.fromhex(proof), _bytes(core), "sha256").hexdigest())
            or not 0 <= (now - datetime.fromisoformat(core["created_at"])).total_seconds() <= HANDOFF_SECONDS):
            raise ValueError
        # Atomic exclusive claim; a copied environment cannot replay this generation.
        claim = path / f"{generation}.consumed.json"
        claim_fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(claim_fd, "wb") as handle:
            handle.write(_bytes({"generation": generation, "parent_pid": core["parent_pid"],
                "process_id": pid, "runtime_identity": runtime_identity, "accepted_at": now.isoformat()}))
            handle.flush()
            os.fsync(handle.fileno())
        return generation
    except (ValueError, TypeError, KeyError, OSError):
        raise ConnectionGovernanceError("MAINTENANCE_HANDOFF_REJECTED") from None


def verify_drain_handoff(path: Path, *, generation: str, parent_pid: int,
                         proof: str, loaded_revision: str, now: datetime) -> dict:
    """Read-only V2 verification for the launcher; never create a directory."""
    try:
        if (re.fullmatch(r"[a-f0-9]{64}", generation) is None
            or re.fullmatch(r"[a-f0-9]{64}", proof) is None
            or re.fullmatch(r"[a-f0-9]{40}", loaded_revision) is None
            or type(parent_pid) is not int or parent_pid < 2 or now.tzinfo is None
            or not path.is_absolute() or any(p.is_symlink() for p in (*path.parents, path))):
            raise ValueError
        directory = path.stat()
        if (not path.is_dir() or directory.st_uid != os.getuid()
            or directory.st_mode & 0o077):
            raise ValueError
        source = path / f"{generation}.json"
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            stat = os.fstat(handle.fileno())
            if (not os.path.isfile(source) or stat.st_uid != os.getuid()
                or stat.st_mode & 0o077 or stat.st_size > 4096):
                raise ValueError
            raw = handle.read(4097)
        item = json.loads(raw)
        core = item["record"]
        if (raw != _bytes(item) or set(item) != {"record", "proof"}
            or set(core) != {"schema", "generation", "parent_pid", "runtime_identity",
                             "loaded_revision", "drain", "created_at"}
            or core["schema"] != "KRONOS_MAINTENANCE_HANDOFF_V2"
            or core["generation"] != generation
            or core["parent_pid"] != parent_pid
            or core["loaded_revision"] != loaded_revision
            or re.fullmatch(r"[a-f0-9]{64}", core["runtime_identity"]) is None
            or not _valid_drain(core["drain"])
            or not isinstance(item["proof"], str)
            or not hmac.compare_digest(item["proof"], hmac.new(
                bytes.fromhex(proof), _bytes(core), "sha256").hexdigest())
            or not 0 <= (now - datetime.fromisoformat(core["created_at"])).total_seconds() <= HANDOFF_SECONDS
            or (path / f"{generation}.consumed.json").exists()):
            raise ValueError
        return core
    except (ValueError, TypeError, KeyError, OSError, AttributeError, OverflowError):
        raise ConnectionGovernanceError("MAINTENANCE_DRAIN_HANDOFF_REJECTED") from None


def consume_drain_handoff(path: Path, environment, *, runtime_identity: str,
                          now: datetime, process_id: int | None = None,
                          loaded_revision: str | None = None,
                          predecessor_gone=None, port_free=None) -> DrainStartupContext:
    """Claim the verified V2 generation before application composition."""
    values = [environment.pop(key, None) for key in _ENV]
    try:
        generation, parent, proof = values
        if (any(not isinstance(value, str) for value in values)
            or re.fullmatch(r"[0-9]+", parent) is None
            or loaded_revision is None):
            raise ValueError
        pid = os.getpid() if process_id is None else process_id
        core = verify_drain_handoff(path, generation=generation, parent_pid=int(parent),
            proof=proof, loaded_revision=loaded_revision, now=now)
        if predecessor_gone is None:
            def predecessor_gone(parent_pid: int) -> bool:
                try:
                    os.kill(parent_pid, 0)
                except OSError as error:
                    return error.errno == errno.ESRCH
                return False
        if port_free is None:
            def port_free() -> bool:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    return probe.bind(("127.0.0.1", 8947)) is None
        if not predecessor_gone(core["parent_pid"]) or not port_free():
            raise ValueError
        if pid == core["parent_pid"] or re.fullmatch(r"[a-f0-9]{64}", runtime_identity) is None:
            raise ValueError
        claim = path / f"{generation}.consumed.json"
        fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(_bytes({"generation": generation, "parent_pid": core["parent_pid"],
                "process_id": pid, "runtime_identity": runtime_identity,
                "accepted_at": now.isoformat(), "schema": "KRONOS_MAINTENANCE_CONSUMPTION_V2"}))
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        checkpoint = core["drain"]["notification_checkpoint"]
        return DrainStartupContext(generation, checkpoint["state"],
            checkpoint["pending_count"], checkpoint["sha256"])
    except (ValueError, TypeError, KeyError, OSError, ConnectionGovernanceError):
        raise ConnectionGovernanceError("MAINTENANCE_DRAIN_HANDOFF_REJECTED") from None


def _launcher_verify_cli() -> int:
    """The launcher passes the control proof on stdin, never on argv."""
    try:
        if len(sys.argv) != 6 or sys.argv[1] != "verify-v2":
            return 1
        proof = sys.stdin.read(65)
        if len(proof) != 64:
            return 1
        verify_drain_handoff(Path(sys.argv[2]), generation=sys.argv[3],
            parent_pid=int(sys.argv[4]), loaded_revision=sys.argv[5],
            proof=proof, now=datetime.now(UTC))
        return 0
    except (ValueError, ConnectionGovernanceError):
        return 1


if __name__ == "__main__":
    raise SystemExit(_launcher_verify_cli())


@contextmanager
def expected_transport_close(governance):
    """Only synchronous disconnects caused by a successful explicit close qualify.

    Failed close and unrelated callback threads keep ordinary outage semantics.
    Provider monitoring consumers still receive their actual interruption event.
    """
    if governance is None or not governance.shutting_down:
        yield
        return
    callbacks = []
    token = _expected_disconnect.set(callbacks)
    succeeded = False
    try:
        yield
        succeeded = True
    finally:
        _expected_disconnect.reset(token)
        for callback in callbacks:
            if succeeded:
                immutable_write(governance.store.root / "maintenance" /
                    f"{governance.process.runtime_identity}-disconnect.json", {
                        "schema": "EXPECTED_MAINTENANCE_DISCONNECT_V1",
                        "runtime_identity": governance.process.runtime_identity,
                        "maintenance_identity": governance.maintenance_identity,
                        "state": "DISCONNECTED", "notification": "SUPPRESSED_EXPECTED_MAINTENANCE",
                    })
            callback(succeeded)


def defer_expected_disconnect(callback) -> bool:
    callbacks = _expected_disconnect.get()
    if callbacks is None:
        return False
    callbacks.append(callback)
    return True
