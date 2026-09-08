"""One-use controlled restart handoff and scoped expected-disconnect cause."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re

from kronos.common.connection_governance import (
    ConnectionGovernanceError, _bytes, immutable_write, private_directory,
)

# Existing governed launcher waits at most 15s for shutdown plus 30s for startup.
HANDOFF_SECONDS = 45
_ENV = ("KRONOS_MAINTENANCE_GENERATION", "KRONOS_MAINTENANCE_PARENT", "KRONOS_MAINTENANCE_PROOF")
_expected_disconnect = ContextVar("expected_disconnect", default=None)


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
