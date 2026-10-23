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
from time import clock_gettime_ns, CLOCK_MONOTONIC
import re


_GENERATION = re.compile(r"[0-9a-f]{64}\Z")
_OWNER_KINDS = frozenset({
    "BROWSER_POST", "SERVER_PULSE", "HOUSEKEEPING", "WO11", "WO17",
    "SWING_ANALYSIS", "PROVIDER_CONNECTION", "SPONSOR_RESTORATION",
    "BULK_IMPORT", "MONITORING_CALLBACK", "NOTIFICATION", "REMINDER",
    "PROGRESSION", "PROVIDER_CALLBACK", "FINALIZER",
    "SWING_RESEARCH", "WO08_SHADOW",
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
    identity: str = ""
    parent_identity: str | None = None

    def fork(self, kind: str) -> AdmissionTicket:
        """Transfer ownership to an accepted child, even after the fence."""

        return self._owner._fork(self, kind)

    def release(self) -> None:
        self._owner._release(self)

    @contextmanager
    def activate(self):
        if not self._owner.is_live(self):
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
        self._failed_ns: int | None = None
        # Object identity, not a caller-created dataclass or a kind counter,
        # establishes issued ownership. Released identities are never reused.
        self._tickets: dict[str, AdmissionTicket] = {}
        self._ticket_sequence = 0
        self._ticket_history: dict[str, dict[str, object]] = {}
        self._recovery: dict[str, object] | None = None
        self._completion_rights: dict[str, tuple[str, str]] = {}
        self._fence_tickets: tuple[str, ...] = ()
        self._original_execution: dict[str, object] | None = None
        self._prospective_ledger = None

    def admit(self, kind: str) -> AdmissionTicket | None:
        self._require_kind(kind)
        with self._condition:
            if self._state != "OPEN":
                parent = _current_ticket.get()
                if (self._state not in {"FENCED", "DRAINING"}
                    or not self._live_locked(parent)):
                    return None
            else:
                parent = _current_ticket.get()
                if not self._live_locked(parent):
                    parent = None
            return self._issue_locked(kind, self._generation or "OPEN", parent)

    def admit_root(self, kind: str) -> AdmissionTicket | None:
        """OPEN-only independent work; never inherit an accepted parent at fence."""
        self._require_kind(kind)
        with self._condition:
            if self._state != "OPEN":
                return None
            return self._issue_locked(kind, "OPEN")

    def claim(self, generation: str) -> bool:
        if type(generation) is not str or _GENERATION.fullmatch(generation) is None:
            raise ValueError("MAINTENANCE_GENERATION_INVALID")
        with self._condition:
            if self._state != "OPEN":
                return False
            self._generation = generation
            self._fence_tickets = tuple(sorted(self._tickets))
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
            return self._issue_locked("FINALIZER", generation)

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
            if not self._live_locked(parent):
                self._fail_locked("OWNER_PROOF_UNAVAILABLE")
                raise ValueError("MAINTENANCE_PARENT_TICKET_INVALID")
            if self._state not in {"OPEN", "FENCED", "DRAINING", "FINALIZING"}:
                self._recovery_fail_locked("ACCOUNTING")
                raise ValueError("MAINTENANCE_COMPLETION_RIGHT_REQUIRED")
            return self._issue_locked(kind, parent.generation, parent)

    def _release(self, ticket: AdmissionTicket) -> None:
        with self._condition:
            count = self._owners.get(ticket.kind, 0)
            if not self._live_locked(ticket) or count <= 0:
                self._fail_locked("OWNER_PROOF_UNAVAILABLE")
                raise ValueError("MAINTENANCE_OWNER_UNDERFLOW")
            ticket._released = True
            del self._tickets[ticket.identity]
            self._ticket_history[ticket.identity]["released_ns"] = clock_gettime_ns(CLOCK_MONOTONIC)
            if count == 1:
                del self._owners[ticket.kind]
            else:
                self._owners[ticket.kind] = count - 1
            self._condition.notify_all()

    def _require_generation(self, generation: str) -> None:
        if generation != self._generation:
            raise ValueError("MAINTENANCE_GENERATION_CONFLICT")

    def _fail_locked(self, reason: str) -> None:
        # The first ordinary failure is terminal. A later recovery failure is
        # recorded on the distinct transaction and cannot rewrite this fact.
        self._state = "FAILED_FENCED"
        if self._failure is None:
            self._failure = reason
            self._failed_ns = clock_gettime_ns(CLOCK_MONOTONIC)
        self._condition.notify_all()

    def _issue_locked(self, kind: str, generation: str,
                      parent: AdmissionTicket | None = None) -> AdmissionTicket:
        self._ticket_sequence += 1
        identity = f"ticket:{self._ticket_sequence}"
        ticket = AdmissionTicket(self, kind, generation, False, identity,
                                 parent.identity if parent else None)
        self._tickets[identity] = ticket
        self._owners[kind] = self._owners.get(kind, 0) + 1
        self._ticket_history[identity] = {
            "identity": identity, "kind": kind, "generation": generation,
            "parent": ticket.parent_identity,
            "accepted_ns": clock_gettime_ns(CLOCK_MONOTONIC),
            "released_ns": None, "operation": None,
        }
        return ticket

    def _live_locked(self, ticket: AdmissionTicket | None) -> bool:
        return (isinstance(ticket, AdmissionTicket) and ticket._owner is self
                and not ticket._released and self._tickets.get(ticket.identity) is ticket)

    def is_live(self, ticket: AdmissionTicket) -> bool:
        with self._condition:
            return self._live_locked(ticket)

    def current_ticket(self) -> AdmissionTicket | None:
        ticket = _current_ticket.get()
        return ticket if self.is_live(ticket) else None

    def bind_operation(self, ticket: AdmissionTicket, operation: str) -> None:
        with self._condition:
            if not self._live_locked(ticket):
                raise ValueError("MAINTENANCE_PARENT_TICKET_INVALID")
            old = self._ticket_history[ticket.identity]["operation"]
            if old is not None and old != operation:
                raise ValueError("MAINTENANCE_OPERATION_CONFLICT")
            self._ticket_history[ticket.identity]["operation"] = operation

    def ticket_snapshot(self) -> dict[str, object]:
        with self._condition:
            return {"live": tuple(sorted(self._tickets)),
                    "fence": self._fence_tickets,
                    "history": {k: dict(v) for k, v in self._ticket_history.items()}}

    def register_completion(self, parent: AdmissionTicket, obligation: str, kind: str) -> None:
        self._require_kind(kind)
        with self._condition:
            if (self._state != "OPEN" or not self._live_locked(parent)
                    or obligation in self._completion_rights):
                raise ValueError("MAINTENANCE_COMPLETION_REGISTRATION_INVALID")
            self._completion_rights[obligation] = (parent.identity, kind)

    def fork_completion(self, parent: AdmissionTicket, obligation: str) -> AdmissionTicket:
        with self._condition:
            right = self._completion_rights.get(obligation)
            if (not self._live_locked(parent) or right is None or right[0] != parent.identity
                    or (self._recovery and self._recovery["state"] not in {"ACCEPTED"})
                    or self._state not in {"OPEN", "FENCED", "DRAINING", "FAILED_FENCED"}):
                self._recovery_fail_locked("ACCOUNTING")
                raise ValueError("MAINTENANCE_COMPLETION_RIGHT_INVALID")
            del self._completion_rights[obligation]
            return self._issue_locked(right[1], parent.generation, parent)

    def claim_recovery(self, transaction: str, known_tickets: set[str]) -> None:
        with self._condition:
            if (self._state != "FAILED_FENCED" or self._recovery is not None
                    or set(self._tickets) != known_tickets
                    or self._original_execution is None
                    or self._original_execution["state"] != "COMPLETE"
                    or self._original_execution["operational_owners"] != 0
                    or self._original_execution["publisher_owners"] != 0):
                raise ValueError("MAINTENANCE_RECOVERY_CLAIM_INVALID")
            self._recovery = {"transaction": transaction, "state": "ACCEPTED",
                              "owners": 1, "failure": None}

    def failure_snapshot(self) -> dict[str, object]:
        with self._condition:
            return {"state": self._state, "generation": self._generation,
                    "failure": self._failure, "failed_ns": self._failed_ns}

    def begin_original_execution(self, generation: str, executor: str) -> None:
        with self._condition:
            self._require_generation(generation)
            if self._state != "FENCED" or self._original_execution is not None:
                raise ValueError("MAINTENANCE_ORIGINAL_EXECUTOR_INVALID")
            self._original_execution = {"executor": executor, "state": "OWNED",
                                        "operational_owners": 1, "publisher_owners": 0}

    def complete_original_execution(self, executor: str) -> None:
        """Actual original executor return transfers ownership to its publisher."""
        with self._condition:
            e = self._original_execution
            if e is None or e["executor"] != executor or e["state"] != "OWNED":
                raise ValueError("MAINTENANCE_ORIGINAL_EXECUTOR_INVALID")
            e.update(state="PUBLISHING", operational_owners=0, publisher_owners=1)

    def finish_original_publication(self, executor: str) -> None:
        """Called after every actual original closure fsync and exact readback."""
        with self._condition:
            e = self._original_execution
            if e is None or e["executor"] != executor or e["state"] != "PUBLISHING":
                raise ValueError("MAINTENANCE_ORIGINAL_PUBLISHER_INVALID")
            e.update(state="COMPLETE", publisher_owners=0)
            self._condition.notify_all()

    def original_execution_snapshot(self) -> dict[str, object]:
        with self._condition:
            return dict(self._original_execution) if self._original_execution else {
                "state": "NOT_REGISTERED", "operational_owners": None, "publisher_owners": None}

    def wait_recovery_zero(self, transaction: str, deadline_ns: int) -> bool:
        with self._condition:
            self._require_recovery_locked(transaction, "ACCEPTED")
            while self._tickets:
                remaining = deadline_ns - clock_gettime_ns(CLOCK_MONOTONIC)
                if remaining <= 0:
                    self._recovery_fail_locked("TIMEOUT")
                    return False
                self._condition.wait(remaining / 1_000_000_000)
                self._require_recovery_locked(transaction, "ACCEPTED")
            if clock_gettime_ns(CLOCK_MONOTONIC) >= deadline_ns:
                self._recovery_fail_locked("TIMEOUT")
                return False
            return True

    def seal_recovery(self, transaction: str, deadline_ns: int) -> int:
        with self._condition:
            self._require_recovery_locked(transaction, "ACCEPTED")
            now = clock_gettime_ns(CLOCK_MONOTONIC)
            if self._tickets or self._owners or now >= deadline_ns:
                self._recovery_fail_locked("TIMEOUT" if now >= deadline_ns else "ACCOUNTING")
                raise ValueError("MAINTENANCE_RECOVERY_SEAL_INVALID")
            self._recovery["state"] = "SEALED"
            # The sole execution owner transfers, rather than temporarily
            # disappearing, into the commit publisher.
            return now

    def release_recovery(self, transaction: str, deadline_ns: int) -> int:
        with self._condition:
            self._require_recovery_locked(transaction, "SEALED")
            now = clock_gettime_ns(CLOCK_MONOTONIC)
            if self._tickets or self._owners or now >= deadline_ns:
                self._recovery_fail_locked("TIMEOUT" if now >= deadline_ns else "ACCOUNTING")
                raise ValueError("MAINTENANCE_RECOVERY_RELEASE_INVALID")
            self._recovery["owners"] = 0
            self._recovery["state"] = "RELEASED"
            self._condition.notify_all()
            return now

    def fail_recovery(self, code: str) -> None:
        with self._condition:
            self._recovery_fail_locked(code)

    def finish_failed_recovery_execution(self, transaction: str) -> None:
        """Release only the returned failed executor, never product ownership.

        The source-owned transaction execution context calls this on its actual
        return. This cannot produce a success proof or reopen the spent slot.
        """
        with self._condition:
            self._require_recovery_locked(transaction, "SPENT_FAILED")
            self._recovery["owners"] = 0
            self._condition.notify_all()

    def recovery_snapshot(self) -> dict[str, object] | None:
        with self._condition:
            return dict(self._recovery) if self._recovery else None

    def _recovery_fail_locked(self, code: str) -> None:
        if self._recovery is not None:
            self._recovery["state"] = "SPENT_FAILED"
            if self._recovery["failure"] is None:
                self._recovery["failure"] = code
        self._condition.notify_all()

    def _require_recovery_locked(self, transaction: str, state: str) -> None:
        if (self._recovery is None or self._recovery["transaction"] != transaction
                or self._recovery["state"] != state or self._recovery["owners"] != 1):
            raise ValueError("MAINTENANCE_RECOVERY_STATE_CONFLICT")

    @staticmethod
    def _require_kind(kind: str) -> None:
        if kind not in _OWNER_KINDS:
            raise ValueError("MAINTENANCE_OWNER_KIND_INVALID")
