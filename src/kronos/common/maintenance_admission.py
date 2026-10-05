"""Process-local admission fence for a governed maintenance generation.

The coordinator owns no product state. Callers acquire a ticket before entering
their own locks and release it after their last callback and durable write.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Condition, Lock
from time import monotonic
import re


_GENERATION = re.compile(r"[0-9a-f]{64}\Z")
_OWNER_KINDS = frozenset({
    "BROWSER_POST", "SERVER_PULSE", "HOUSEKEEPING", "WO11", "WO17",
    "SWING_ANALYSIS", "PROVIDER_CONNECTION", "SPONSOR_RESTORATION",
    "BULK_IMPORT", "MONITORING_CALLBACK", "NOTIFICATION", "REMINDER",
    "PROGRESSION", "PROVIDER_CALLBACK", "FINALIZER",
    "SWING_RESEARCH",
})
_current_ticket = ContextVar(
    "kronos_maintenance_ticket", default=None
)


@dataclass(slots=True)
class AdmissionTicket:
    _owner: MaintenanceAdmissionCoordinator
    kind: str
    generation: str
    _released: bool = False

    def fork(self, kind: str) -> AdmissionTicket:
        """Transfer ownership to an accepted child, even after the fence."""

        return self._owner._fork(self, kind)

    def release(self) -> None:
        self._owner._release(self)

    @contextmanager
    def activate(self):
        if self._released:
            raise ValueError("MAINTENANCE_PARENT_TICKET_INVALID")
        token = _current_ticket.set(self)
        try:
            yield self
        finally:
            _current_ticket.reset(token)

    def __enter__(self) -> AdmissionTicket:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


class MaintenanceAdmissionCoordinator:
    """Short-lock admission and condition-signaled owner completion.

    No domain lock or I/O is entered while this condition is held. The caller
    performs quiescence and cleanup separately, then proves final state before
    publishing an authenticated handoff.
    """

    def __init__(self) -> None:
        self._condition = Condition(Lock())
        self._state = "OPEN"
        self._generation: str | None = None
        self._owners: dict[str, int] = {}
        self._failure: str | None = None

    def admit(self, kind: str) -> AdmissionTicket | None:
        self._require_kind(kind)
        with self._condition:
            if self._state != "OPEN":
                parent = _current_ticket.get()
                if (self._state not in {"FENCED", "DRAINING"}
                    or parent is None or parent._owner is not self
                    or parent._released):
                    return None
            self._owners[kind] = self._owners.get(kind, 0) + 1
            return AdmissionTicket(self, kind, self._generation or "OPEN")

    def claim(self, generation: str) -> bool:
        if type(generation) is not str or _GENERATION.fullmatch(generation) is None:
            raise ValueError("MAINTENANCE_GENERATION_INVALID")
        with self._condition:
            if self._state != "OPEN":
                return False
            self._generation = generation
            self._state = "FENCED"
            self._condition.notify_all()
            return True

    def draining(self, generation: str) -> None:
        with self._condition:
            self._require_generation(generation)
            if self._state != "FENCED":
                raise ValueError("MAINTENANCE_STATE_CONFLICT")
            self._state = "DRAINING"
            self._condition.notify_all()

    def finalizer(self, generation: str) -> AdmissionTicket:
        """Own cleanup after the external gate has closed and initial work drained."""
        with self._condition:
            self._require_generation(generation)
            if self._state not in {"DRAINING", "FINALIZING"} or self._owners:
                raise ValueError("MAINTENANCE_OWNER_PROOF_UNAVAILABLE")
            self._state = "FINALIZING"
            self._owners["FINALIZER"] = 1
            return AdmissionTicket(self, "FINALIZER", generation)

    def wait_for_zero(self, generation: str, timeout_seconds: float) -> bool:
        if type(timeout_seconds) not in {int, float} or not 0 <= timeout_seconds <= 15:
            raise ValueError("MAINTENANCE_DRAIN_TIMEOUT_INVALID")
        deadline = monotonic() + timeout_seconds
        with self._condition:
            self._require_generation(generation)
            if self._state not in {"DRAINING", "FINALIZING"}:
                raise ValueError("MAINTENANCE_STATE_CONFLICT")
            while self._owners:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    self._fail_locked("DRAIN_TIMEOUT")
                    return False
                self._condition.wait(remaining)
            return True

    def ready(self, generation: str) -> None:
        with self._condition:
            self._require_generation(generation)
            if self._state != "FINALIZING" or self._owners:
                raise ValueError("MAINTENANCE_OWNER_PROOF_UNAVAILABLE")
            self._state = "HANDOFF_READY"
            self._condition.notify_all()

    def stopping(self, generation: str) -> None:
        with self._condition:
            self._require_generation(generation)
            if self._state != "HANDOFF_READY" or self._owners:
                raise ValueError("MAINTENANCE_STATE_CONFLICT")
            self._state = "STOPPING"
            self._condition.notify_all()

    def closed(self, generation: str) -> None:
        with self._condition:
            self._require_generation(generation)
            if self._state != "STOPPING" or self._owners:
                raise ValueError("MAINTENANCE_STATE_CONFLICT")
            self._state = "CLOSED"
            self._condition.notify_all()

    def fail(self, generation: str, reason: str) -> None:
        if reason not in {"DRAIN_TIMEOUT", "CLEANUP_UNRESOLVED",
                          "OWNER_PROOF_UNAVAILABLE", "HANDOFF_FAILED"}:
            raise ValueError("MAINTENANCE_FAILURE_INVALID")
        with self._condition:
            self._require_generation(generation)
            self._fail_locked(reason)

    def snapshot(self) -> dict[str, object]:
        with self._condition:
            return {"state": self._state, "generation": self._generation,
                    "owners": dict(self._owners), "failure": self._failure}

    def _fork(self, parent: AdmissionTicket, kind: str) -> AdmissionTicket:
        self._require_kind(kind)
        with self._condition:
            if parent._owner is not self or parent._released:
                self._fail_locked("OWNER_PROOF_UNAVAILABLE")
                raise ValueError("MAINTENANCE_PARENT_TICKET_INVALID")
            self._owners[kind] = self._owners.get(kind, 0) + 1
            return AdmissionTicket(self, kind, parent.generation)

    def _release(self, ticket: AdmissionTicket) -> None:
        with self._condition:
            count = self._owners.get(ticket.kind, 0)
            if ticket._owner is not self or ticket._released or count <= 0:
                self._fail_locked("OWNER_PROOF_UNAVAILABLE")
                raise ValueError("MAINTENANCE_OWNER_UNDERFLOW")
            ticket._released = True
            if count == 1:
                del self._owners[ticket.kind]
            else:
                self._owners[ticket.kind] = count - 1
            self._condition.notify_all()

    def _require_generation(self, generation: str) -> None:
        if generation != self._generation:
            raise ValueError("MAINTENANCE_GENERATION_CONFLICT")

    def _fail_locked(self, reason: str) -> None:
        self._state = "FAILED_FENCED"
        self._failure = reason
        self._condition.notify_all()

    @staticmethod
    def _require_kind(kind: str) -> None:
        if kind not in _OWNER_KINDS:
            raise ValueError("MAINTENANCE_OWNER_KIND_INVALID")
