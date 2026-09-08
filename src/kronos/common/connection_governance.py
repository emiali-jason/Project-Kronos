"""SPH-001/003: non-secret connection journal and process-owned dispatch guard.

Authentication remains Provider-owned. Surface references attest a rendered
control context, never a human identity. No automatic authentication authority.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import secrets
from threading import RLock
from uuid import uuid4


class ConnectionGovernanceError(ValueError):
    """Bounded failure; never includes Provider exceptions or request bodies."""


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def private_directory(path: Path) -> None:
    """Reject symlink ancestors before using a private local evidence directory."""
    if not path.is_absolute():
        raise ConnectionGovernanceError("CONNECTION_PATH_INVALID")
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise ConnectionGovernanceError("CONNECTION_PATH_INVALID")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise ConnectionGovernanceError("CONNECTION_PATH_INVALID")


def immutable_write(path: Path, value: object) -> None:
    private_directory(path.parent)
    payload = _bytes(value)
    temporary = path.with_name(f".{uuid4().hex}.tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != payload:
                raise ConnectionGovernanceError("CONNECTION_IMMUTABLE_CONFLICT") from None
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class ConnectionProcess:
    pid: int
    startup_at: str
    runtime_identity: str
    loaded_revision: str | None
    source_state: str

    def __post_init__(self):
        if (type(self.pid) is not int or self.pid < 2
            or re.fullmatch(r"[a-f0-9]{64}", self.runtime_identity) is None
            or self.source_state not in {"CLEAN_COMMIT", "DIRTY_WORKTREE", "REVISION_UNAVAILABLE"}
            or (self.loaded_revision is not None and re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", self.loaded_revision) is None)
            or (self.source_state == "CLEAN_COMMIT" and self.loaded_revision is None)
            or datetime.fromisoformat(self.startup_at).tzinfo is None):
            raise ConnectionGovernanceError("CONNECTION_PROCESS_INVALID")


@dataclass(frozen=True, slots=True)
class ConnectionRequest:
    connection_request_id: str
    server_receipt_at: str
    route: str
    provider_identity: str
    process: ConnectionProcess
    trigger: str
    surface: str | None

    def __post_init__(self):
        if (re.fullmatch(r"[a-f0-9]{32}", self.connection_request_id) is None
            or self.route not in {"/provider/connect", "SHARED_PROVIDER_API"}
            or re.fullmatch(r"[A-Z][A-Z0-9_-]{0,31}", self.provider_identity) is None
            or self.trigger not in {"SPONSOR_EXPLICIT", "LOCAL_HTTP_UNATTRIBUTED", "OTHER_ESTABLISHED_GOVERNED_TRIGGER", "UNATTRIBUTED_API"}
            or self.surface not in {None, "HEADER", "SETTINGS"}
            or datetime.fromisoformat(self.server_receipt_at).tzinfo is None
            or type(self.process) is not ConnectionProcess):
            raise ConnectionGovernanceError("CONNECTION_REQUEST_INVALID")


class ConnectionAuditStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def request(self, request: ConnectionRequest) -> None:
        core = asdict(request)
        self._put(request.connection_request_id, "request", core)

    def result(self, request: ConnectionRequest, phase: str, state: str, at: str) -> None:
        if ((phase == "admission" and state not in {"ACCEPTED", "REJECTED", "ALREADY_CONNECTED"})
            or (phase == "dispatch" and state != "UNFINISHED")
            or (phase == "completion" and state not in {"SUCCESS", "FAILURE", "UNFINISHED"})
            or phase not in {"admission", "dispatch", "completion"}
            or datetime.fromisoformat(at).tzinfo is None):
            raise ConnectionGovernanceError("CONNECTION_RESULT_INVALID")
        self._put(request.connection_request_id, phase, {
            "connection_request_id": request.connection_request_id,
            "request_integrity": sha256(_bytes(asdict(request))).hexdigest(),
            "phase": phase, "state": state, "recorded_at": at,
        })

    def _put(self, identity: str, phase: str, core: dict):
        immutable_write(self.root / identity / f"{phase}.json", {
            "schema": "PROVIDER_CONNECTION_AUDIT_V1", "record": core,
            "integrity_sha256": sha256(_bytes(core)).hexdigest(),
        })

    def read(self, identity: str) -> dict:
        if re.fullmatch(r"[a-f0-9]{32}", identity) is None:
            raise ConnectionGovernanceError("CONNECTION_ID_INVALID")
        private_directory(self.root)
        result = {}
        for phase in ("request", "admission", "dispatch", "completion"):
            path = self.root / identity / f"{phase}.json"
            if path.parent.is_symlink() or path.is_symlink():
                raise ConnectionGovernanceError("CONNECTION_PATH_INVALID")
            if not path.exists():
                continue
            item = json.loads(path.read_bytes())
            if (set(item) != {"schema", "record", "integrity_sha256"}
                or item["schema"] != "PROVIDER_CONNECTION_AUDIT_V1"
                or sha256(_bytes(item["record"])).hexdigest() != item["integrity_sha256"]):
                raise ConnectionGovernanceError("CONNECTION_INTEGRITY_INVALID")
            result[phase] = item["record"]
        return result


class ConnectionGovernance:
    def __init__(self, process: ConnectionProcess, store: ConnectionAuditStore, *,
                 provider_identity: str = "KITE", maintenance_identity: str | None = None,
                 clock=lambda: datetime.now(UTC)):
        self.process = process
        self.store = store
        self.provider_identity = provider_identity
        self.clock = clock
        self.lock = RLock()
        if maintenance_identity is not None and re.fullmatch(r"[a-f0-9]{64}", maintenance_identity) is None:
            raise ConnectionGovernanceError("MAINTENANCE_ID_INVALID")
        self.maintenance_identity = maintenance_identity
        self.maintenance_active = maintenance_identity is not None
        self.shutting_down = False
        self._key = secrets.token_bytes(32)
        self._pending: dict[str, ConnectionRequest] = {}
        self._context = ContextVar("connection_request", default=None)
        self._results: dict[tuple[str, str], tuple[str, str]] = {}
        self._issued: dict[str, ConnectionRequest] = {}

    def action_reference(self, surface: str) -> str:
        if surface not in {"HEADER", "SETTINGS", "MAINTENANCE_EXIT"}:
            raise ConnectionGovernanceError("CONNECTION_SURFACE_INVALID")
        message = f"{self.process.runtime_identity}:{self.maintenance_identity}:{surface}"
        return hmac.new(self._key, message.encode(), "sha256").hexdigest()

    def surface(self, reference: str | None) -> str | None:
        return next((surface for surface in ("HEADER", "SETTINGS")
                     if isinstance(reference, str) and hmac.compare_digest(reference, self.action_reference(surface))), None)

    def request(self, *, reference=None, route="/provider/connect", received_at=None) -> ConnectionRequest:
        request = ConnectionRequest(uuid4().hex, received_at or self.clock().isoformat(), route,
            self.provider_identity, self.process,
            "LOCAL_HTTP_UNATTRIBUTED" if route == "/provider/connect" else "UNATTRIBUTED_API",
            self.surface(reference) if route == "/provider/connect" else None)
        self.store.request(request)  # Fail closed before authentication dispatch.
        self._issued[request.connection_request_id] = request
        return request

    def result(self, request, phase, state):
        with self.lock:
            key = (request.connection_request_id, phase)
            previous = self._results.get(key)
            if previous is not None:
                if previous[0] != state:
                    raise ConnectionGovernanceError("CONNECTION_IMMUTABLE_CONFLICT")
                return
            at = self.clock().isoformat()
            self.store.result(request, phase, state, at)
            self._results[key] = (state, at)

    def admit(self, request, *, already_connected=False) -> bool:
        with self.lock:
            if request.process != self.process or self._issued.get(request.connection_request_id) != request:
                raise ConnectionGovernanceError("CONNECTION_FOREIGN_PROCESS")
            if (request.connection_request_id, "admission") in self._results:
                return False
            if self.maintenance_active or self.shutting_down:
                self.result(request, "admission", "REJECTED")
                return False
            if already_connected:
                self.result(request, "admission", "ALREADY_CONNECTED")
                return False
            if request.connection_request_id in self._pending:
                return False
            self.result(request, "admission", "ACCEPTED")
            self.result(request, "dispatch", "UNFINISHED")
            self._pending[request.connection_request_id] = request
            return True

    @contextmanager
    def dispatch(self, request):
        token = self._context.set(request)
        try:
            self.require_authentication()
            yield
        finally:
            self._context.reset(token)

    def require_authentication(self):
        with self.lock:
            request = self._context.get()
            if (self.maintenance_active or self.shutting_down or request is None
                or self._pending.get(request.connection_request_id) != request):
                if request is None:
                    rejected = self.request(route="SHARED_PROVIDER_API")
                    self.result(rejected, "admission", "REJECTED")
                raise ConnectionGovernanceError("PROVIDER_AUTHENTICATION_NOT_ADMITTED")

    def finish(self, request, success):
        with self.lock:
            if request.connection_request_id in self._pending:
                self.result(request, "completion", "SUCCESS" if success else "FAILURE")
                self._pending.pop(request.connection_request_id)

    def enter_maintenance(self, identity: str):
        if re.fullmatch(r"[a-f0-9]{64}", identity) is None:
            raise ConnectionGovernanceError("MAINTENANCE_ID_INVALID")
        with self.lock:
            if self.shutting_down and self.maintenance_identity != identity:
                raise ConnectionGovernanceError("MAINTENANCE_GENERATION_CONFLICT")
            self.maintenance_identity = identity
            self.maintenance_active = True
            self.shutting_down = True
            for request in tuple(self._pending.values()):
                self.result(request, "completion", "UNFINISHED")
            self._pending.clear()

    def exit_maintenance(self, reference: str) -> bool:
        with self.lock:
            if self.shutting_down or not isinstance(reference, str) or not hmac.compare_digest(reference, self.action_reference("MAINTENANCE_EXIT")):
                return False
            if self.maintenance_active:
                immutable_write(self.store.root / "maintenance" / f"{self.process.runtime_identity}.json", {
                    "schema": "MAINTENANCE_EXIT_V1", "runtime_identity": self.process.runtime_identity,
                    "maintenance_identity": self.maintenance_identity, "at": self.clock().isoformat(),
                    "trigger": "LOCAL_HTTP_UNATTRIBUTED", "surface": "MAINTENANCE_EXIT",
                })
                self.maintenance_active = False
            return True

    def require_operations(self):
        if self.maintenance_active or self.shutting_down:
            raise ConnectionGovernanceError("CONTROLLED_MAINTENANCE_ACTIVE")
