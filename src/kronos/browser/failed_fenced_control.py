"""R3's exact one-connection control framing; this module grants no authority.

ADR-0068 / KRONOS-FAILED-FENCED-RECOVERY-V1 section 5.  The caller must
independently validate the retained CLAIM, its authority and shared budget before
reading this exchange, and validate the returned bytes through RecoveryTransaction.
No ordinary shutdown handler, response logger or HTTP convenience header is used.
"""

from __future__ import annotations

import hmac
import re
from uuid import uuid4
from typing import BinaryIO, Protocol
from copy import deepcopy
from threading import Lock

from kronos.browser.restart_control import BrowserBackendRestartControl


CONTROL_PATH = "/control/failed-fenced-recovery/v1"
REQUEST_LINE = b"POST /control/failed-fenced-recovery/v1 HTTP/1.0\r\n"
MAX_HEADERS = 8192
MAX_CLAIM = 1024 * 1024
MAX_ACK = 131072
_DECIMAL = re.compile(rb"[1-9][0-9]*\Z")
_HEADERS = frozenset({b"host", b"x-kronos-backend-pid",
    b"x-kronos-restart-token", b"content-type", b"content-length", b"connection"})


class ControlFramingError(ValueError):
    """Redacted framing failure. Never attach header/token bytes to an error."""


class _Budget(Protocol):
    def check(self, deadline_ns: int | None = None) -> object: ...
    def remaining_seconds(self, deadline_ns: int | None = None) -> float: ...


def _timeout(connection, budget: _Budget, deadline_ns: int | None = None) -> None:
    budget.check(deadline_ns)
    remaining = budget.remaining_seconds(deadline_ns)
    if not 0 < remaining <= 15:
        raise ControlFramingError("FAILED_FENCED_CONTROL_BUDGET_INVALID")
    connection.settimeout(remaining)


def _read_once(stream: BinaryIO, maximum: int, *, connection, budget: _Budget) -> bytes:
    """At most one underlying receive, bounded by the unchanged deadline.

    BufferedReader.read/readline can perform multiple raw receives while each
    receive gets the same socket timeout. read1 makes at most one raw read, so
    trickled bytes cannot postpone the next absolute-budget check indefinitely.
    """
    if type(maximum) is not int or not 1 <= maximum <= 65537:
        raise ControlFramingError("FAILED_FENCED_CONTROL_READ_LIMIT_INVALID")
    read1 = getattr(stream, "read1", None)
    if not callable(read1):
        raise ControlFramingError("FAILED_FENCED_CONTROL_SINGLE_READ_REQUIRED")
    _timeout(connection, budget)
    part = read1(maximum)
    budget.check()
    if type(part) is not bytes or len(part) > maximum:
        raise ControlFramingError("FAILED_FENCED_CONTROL_READ_INVALID")
    return part


def read_budgeted_line(stream: BinaryIO, limit: int, *, connection,
                       budget: _Budget) -> bytes:
    """Read through one LF or the caller's finite limit, without over-reading.

    One-byte read1 calls preserve the exact following body/header bytes in the
    original stream. Every raw receive gets freshly computed remaining time.
    The caller retains its own exact CRLF, line and aggregate-size validation.
    """
    if type(limit) is not int or not 1 <= limit <= 65537:
        raise ControlFramingError("FAILED_FENCED_CONTROL_READ_LIMIT_INVALID")
    line = bytearray()
    while len(line) < limit:
        part = _read_once(stream, 1, connection=connection, budget=budget)
        if not part:
            break
        line.extend(part)
        if part == b"\n":
            break
    return bytes(line)


def read_claim(
    stream: BinaryIO, raw_requestline: bytes, *, connection,
    control: BrowserBackendRestartControl, endpoint_port: int, budget: _Budget,
) -> bytes:
    """Read only exact R3 framing, under the already authenticated shared budget.

    This returns untrusted CLAIM bytes. Token/header agreement is not a recovery
    grant, loaded capability, controller proof or a successful recovery result.
    """
    if (raw_requestline != REQUEST_LINE
            or type(control) is not BrowserBackendRestartControl
            or type(endpoint_port) is not int or not 1 <= endpoint_port <= 65535):
        raise ControlFramingError("FAILED_FENCED_CONTROL_REQUEST_INVALID")
    headers: dict[bytes, bytes] = {}
    size = 0
    while True:
        line = read_budgeted_line(stream, MAX_HEADERS - size + 1,
                                 connection=connection, budget=budget)
        size += len(line)
        if not line or size > MAX_HEADERS or not line.endswith(b"\r\n"):
            raise ControlFramingError("FAILED_FENCED_CONTROL_HEADERS_INVALID")
        if line == b"\r\n":
            break
        if line[:1] in {b" ", b"\t"} or b": " not in line:
            raise ControlFramingError("FAILED_FENCED_CONTROL_HEADERS_INVALID")
        name, value = line[:-2].split(b": ", 1)
        name = name.lower()
        if (name not in _HEADERS or name in headers or not value
                or any(byte < 32 or byte > 126 for byte in value)):
            raise ControlFramingError("FAILED_FENCED_CONTROL_HEADERS_INVALID")
        headers[name] = value
    if set(headers) != _HEADERS:
        raise ControlFramingError("FAILED_FENCED_CONTROL_HEADERS_INVALID")
    length = headers[b"content-length"]
    if (not _DECIMAL.fullmatch(length) or len(length) > 7
            or not 1 <= int(length) <= MAX_CLAIM
            or headers[b"host"] != f"127.0.0.1:{endpoint_port}".encode("ascii")
            or headers[b"content-type"] != b"application/json"
            or headers[b"connection"] != b"close"
            or not control.authorized(
                process_id=headers[b"x-kronos-backend-pid"].decode("ascii"),
                token=headers[b"x-kronos-restart-token"].decode("ascii"))
            or not control.owns_current_process()):
        raise ControlFramingError("FAILED_FENCED_CONTROL_BINDING_INVALID")
    # No headers, and especially no process token, escape this local scope.
    headers.clear()
    body = bytearray()
    outstanding = int(length)
    while outstanding:
        part = _read_once(stream, min(outstanding, 65536),
                          connection=connection, budget=budget)
        if not part or len(part) > outstanding:
            raise ControlFramingError("FAILED_FENCED_CONTROL_BODY_INVALID")
        body.extend(part)
        outstanding -= len(part)
    reject_extra_bytes(stream, connection=connection, budget=budget)
    return bytes(body)


def reject_extra_bytes(stream: BinaryIO, *, connection, budget: _Budget) -> None:
    """Reject buffered or already available extra/pipelined bytes, without a wait.

    The caller also performs this check immediately before SEAL, before its
    write-free tail. Later peer writes confer no authority and the socket closes.
    """
    budget.check()
    old_timeout = connection.gettimeout()
    try:
        connection.setblocking(False)
        try:
            extra = stream.peek(1)
        except (BlockingIOError, InterruptedError):
            extra = b""
        if extra:
            raise ControlFramingError("FAILED_FENCED_CONTROL_EXTRA_BYTES")
    finally:
        connection.settimeout(old_timeout)
    budget.check()


def require_exact_claim(actual: bytes, retained: bytes) -> None:
    if type(actual) is not bytes or type(retained) is not bytes or not hmac.compare_digest(actual, retained):
        raise ControlFramingError("FAILED_FENCED_CONTROL_CLAIM_CHANGED")


def _write_all(stream: BinaryIO, data: bytes, *, connection, budget: _Budget,
               deadline_ns: int | None) -> None:
    remaining = memoryview(data)
    while remaining:
        _timeout(connection, budget, deadline_ns)
        count = stream.write(remaining)
        budget.check(deadline_ns)
        if type(count) is not int or not 0 < count <= len(remaining):
            raise ControlFramingError("FAILED_FENCED_CONTROL_WRITE_INCOMPLETE")
        remaining = remaining[count:]
    _timeout(connection, budget, deadline_ns)
    stream.flush()
    budget.check(deadline_ns)


def write_ack(stream: BinaryIO, ack: bytes, *, connection, budget: _Budget,
              work_deadline_ns: int) -> None:
    """Write exact ACK transport bytes only, after transaction release.

    The caller already validated the authenticated canonical ACK. No Date,
    Server, diagnostic, access-log, trailer or product callback is introduced.
    A partial transport failure never authorizes another response or resend.
    """
    if type(ack) is not bytes or not 1 <= len(ack) <= MAX_ACK:
        raise ControlFramingError("FAILED_FENCED_CONTROL_ACK_INVALID")
    if type(work_deadline_ns) is not int:
        raise ControlFramingError("FAILED_FENCED_CONTROL_BUDGET_INVALID")
    response = (b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n"
        + f"Content-Length: {len(ack)}\r\n".encode("ascii")
        + b"Connection: close\r\n\r\n" + ack)
    _write_all(stream, response, connection=connection, budget=budget,
               deadline_ns=work_deadline_ns)


def write_denial(stream: BinaryIO, *, connection, budget: _Budget) -> None:
    """Optional pre-release empty denial; a spent/late caller should just close."""
    _write_all(stream,
        b"HTTP/1.0 409 Conflict\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
        connection=connection, budget=budget, deadline_ns=None)


class RecoveryBrowserBinding:
    """Fixed Browser integration of a separately prepared R3 transaction.

    This object is composed internally from the independently verified recovery
    preparation. A request cannot construct it, select its registry or supply a
    cleanup/tail callback. Missing preparation leaves this endpoint unavailable.
    """

    TAIL_ENTRY = "KronosBrowserServer.failed_fenced_write_free"
    FORBIDDEN_HOOKS = (
        "ordinary_server_close", "domain_finalizers", "research_capture",
        "notification_delivery", "monitoring_callbacks", "control_remove",
        "request_diagnostics", "maintenance_handoff", "audit_publication",
    )

    def __init__(self, transaction, *, tail_approval: str):
        from kronos.common.failed_fenced_recovery import RecoveryTransaction
        if type(transaction) is not RecoveryTransaction:
            raise ValueError("FAILED_FENCED_CONTROL_BINDING_INVALID")
        self.transaction = transaction
        self.ledger = transaction.ledger
        self.tail_approval = tail_approval
        self._server = None
        self._entered = False

    def bind(self, server) -> None:
        from kronos.browser.server import KronosBrowserServer
        if (type(server) is not KronosBrowserServer or self._server is not None
                or server.maintenance_admission is not self.ledger.coordinator
                or server.restart_control is None):
            raise ValueError("FAILED_FENCED_CONTROL_BINDING_INVALID")
        self._server = server

    def prepare_transport(self, connection) -> None:
        # This is a deny-only check before the HTTP request-line read. The
        # request cannot choose an origin, a timeout or an authority context.
        self.transaction.expected_claim_raw()
        _timeout(connection, self.transaction.budget)

    def _tail(self, publisher):
        from kronos.common.failed_fenced_recovery import record_ref
        tx, ledger = self.transaction, self.ledger
        source = ledger._original_payload["source"]
        source_proof = tx.registry.verify(source, "SOURCE", context={"mode": "ORIGINAL"})
        row = tx.registry.preparation.approval(
            self.tail_approval, purpose="TAIL", authority="CA")
        if (row["bindings"]["entry"] != self.TAIL_ENTRY
                or row["bindings"]["source_inventory"]
                   != source_proof["payload"]["source_inventory"]):
            raise ValueError("FAILED_FENCED_TAIL_SOURCE_UNPROVEN")
        # Inspect retained journal heads, never execute a callback for proof.
        required, complete = [], []
        for ref in ledger.cleanup_heads():
            raw = ledger.store.resolve(ref)
            if record_ref(raw) != ref:
                raise ValueError("FAILED_FENCED_CLEANUP_CHANGED")
            step = ledger.codec.decode(raw, "CLEANUP")["payload"]
            required.append(step["step"])
            if step["state"] in {"COMPLETE", "NOT_APPLICABLE"}:
                complete.append(step["step"])
        if sorted(required) != sorted(complete):
            raise ValueError("FAILED_FENCED_CLEANUP_INCOMPLETE")
        snapshot = ledger.coordinator.snapshot()
        if snapshot["owners"]:
            raise ValueError("FAILED_FENCED_PRODUCT_OWNER_REMAINS")
        return ledger.publish_proof("TAIL", {
            "identity": "tail-" + uuid4().hex, "process": ledger.process,
            "source": {key: source[key] for key in ("identity", "hash", "bytes")},
            "approval": self.tail_approval, "entry": self.TAIL_ENTRY,
            "allowed": ["CONTROL_RESPONSE", "CLOSE_DESCRIPTORS", "PROCESS_EXIT"],
            "forbidden_hooks": sorted(self.FORBIDDEN_HOOKS),
            "required_cleanup": sorted(required), "completed_cleanup": sorted(complete),
            "product_owners": "0", "recovery_executor_owners": "1", "executor": publisher,
        })

    def handle(self, handler) -> None:
        if (self._server is None or handler.server is not self._server
                or self._entered):
            return
        with self.transaction.execution():
            self._handle(handler)

    def _handle(self, handler) -> None:
        from kronos.application.failed_fenced_owners import ProspectiveComposition
        tx, server = self.transaction, self._server
        if server is None or handler.server is not server or self._entered:
            return
        self._entered = True
        accepted = False
        try:
            # The reserved, fully authenticated CLAIM establishes the absolute
            # budget before any potentially blocking private-header/body read.
            expected = tx.expected_claim_raw()
            control_bytes = server.restart_control.private_bytes_for_recovery()
            raw = read_claim(handler.rfile, handler.raw_requestline,
                connection=handler.connection, control=server.restart_control,
                endpoint_port=server.server_port, budget=tx.budget)
            require_exact_claim(raw, expected)
            tx.accept_claim(raw, control_bytes)
            accepted = True
            server._detach_failed_fenced_request(handler.connection)
            server._freeze_failed_fenced_transport(tx.budget, tx.work_deadline_ns)
            tx.wait_for_accepted_completion()
            composition = self.ledger.native_composition
            if type(composition) is not ProspectiveComposition:
                raise ValueError("FAILED_FENCED_COMPOSITION_UNPROVEN")
            completed = composition.complete_recovery(tx)
            reject_extra_bytes(handler.rfile, connection=handler.connection,
                               budget=tx.budget)
            publisher = "publisher-" + uuid4().hex
            tail = self._tail(publisher)
            # No ordinary owner or diagnostic cleanup is reachable from here.
            server._failed_fenced_write_free = True
            tx.seal(checkpoint=completed["checkpoint"],
                owner_results=completed["owner_results"],
                reconciliation=completed["reconciliation"],
                write_free_tail=tail,
                retained_control=self.ledger._original_payload["control"],
                publisher=publisher)
            tx.publish_commit()
            ack = tx.release_ack()
            write_ack(handler.wfile, ack, connection=handler.connection,
                budget=tx.budget, work_deadline_ns=tx.work_deadline_ns)
        except (OSError, RuntimeError, TypeError, ValueError, TimeoutError) as error:
            # No second response after acceptance/release, no traceback or
            # ordinary callback in the reviewed write-free path. Transaction
            # storage/counts retain its immutable spent state on any failure.
            tx.fail(error)
            if not accepted:
                try:
                    write_denial(handler.wfile, connection=handler.connection,
                                 budget=tx.budget)
                except (OSError, RuntimeError, ValueError, TimeoutError):
                    pass
        finally:
            if tx.write_free_tail_required:
                server._failed_fenced_write_free = True
                # ThreadingHTTPServer.shutdown only coordinates serve_forever;
                # tools/kronos_browser owns the separately reviewed write-free
                # process exit instead of invoking product finalizers again.
                server.shutdown()


class OriginalBrowserBinding:
    """Prospective original-operation enrollment before its first cleanup.

    All authority/custody fields come from the separate typed ORIGINAL control
    preparation. This class cannot manufacture controller closure or declare a
    timed-out thread terminated. A later positive recovery still requires the
    actual original executor and native controller closure evidence.
    """

    def __init__(self, ledger, registry, original_payload, *, executor: str):
        from kronos.common.failed_fenced_recovery import (
            EvidenceRegistry, OriginalExecutorWitness, ProspectiveLedger,
        )
        if (type(ledger) is not ProspectiveLedger or type(registry) is not EvidenceRegistry
                or registry.preparation.record["mode"] != "ORIGINAL"
                or registry.codec is not ledger.codec or registry.store is not ledger.store):
            raise ValueError("FAILED_FENCED_ORIGINAL_PREPARATION_REQUIRED")
        self.ledger, self.registry = ledger, registry
        self.payload, self.executor = deepcopy(original_payload), executor
        self._lock = Lock()
        self._thread = None
        self._started = False
        self._returned = False
        from kronos.common.failed_fenced_recovery import RecoveryBudget
        limits = self.payload["original_limits"]
        self.budget = RecoveryBudget(limits["clock"], int(limits["origin_ns"]),
                                     int(limits["stop_deadline_ns"]))
        deadline = int(self.payload["original_drain_deadline_ns"])
        if not self.budget.origin_ns < deadline <= min(
                self.budget.origin_ns + 10_000_000_000, self.budget.stop_deadline_ns):
            raise ValueError("FAILED_FENCED_ORIGINAL_DEADLINE_INVALID")
        self.budget.work_deadline_ns = deadline
        self.witness = OriginalExecutorWitness(ledger.coordinator, executor,
            registry.preparation.record["controller"], original_payload["attempt"])
        registry.bind_original_executor(self.witness)

    def prepare(self, generation: str, control) -> None:
        if (self.payload["lineage"] != {"predecessor": self.ledger.process,
                "generation": generation} or not control.owns_current_process()
                or not self.ledger.codec.matches_control(control.private_bytes_for_recovery())):
            raise ValueError("FAILED_FENCED_ORIGINAL_BINDING_INVALID")
        self.ledger.attach_registry(self.registry)
        self.registry.verify(self.payload["authorization"], "ORIGINAL_AUTHORITY",
                             context={"mode": "ORIGINAL"})

    def fenced(self, generation: str) -> None:
        with self._lock:
            if self._started:
                raise ValueError("FAILED_FENCED_ORIGINAL_ALREADY_REGISTERED")
            self.ledger.coordinator.begin_original_execution(generation, self.executor)
            self._started = True
            composition = self.ledger.native_composition
            composition._active_budget = self.budget
            composition.publish(original_fence=True)
            self.ledger.finalize_original(self.payload)
            composition.register_cleanup_journal(self.payload["lineage"])
            self.ledger.publish_executor({
                "lineage": self.payload["lineage"], "original": self.ledger.original,
                "executor": self.executor, "previous": None, "state": "OWNED",
                "original_controller": None, "no_child_start": None,
                "no_consumption": None, "completion": None})

    def attach_thread(self, thread) -> None:
        from threading import Thread
        with self._lock:
            if type(thread) is not Thread or self._thread is not None or thread.ident is not None:
                raise ValueError("FAILED_FENCED_ORIGINAL_EXECUTOR_INVALID")
            self._thread = thread
            self.witness.bind_thread(thread)

    def run(self, target) -> None:
        from threading import current_thread
        if current_thread() is not self._thread:
            raise ValueError("FAILED_FENCED_ORIGINAL_EXECUTOR_INVALID")
        try:
            with self.witness.operation("backend-maintenance-drain"):
                try:
                    target()
                finally:
                    self.retain_first_failure()
        finally:
            # This is actual body return, NOT thread join/termination, and does
            # not release the original executor's separately counted ownership.
            with self._lock:
                self._returned = True
            self.witness.return_observed()

    def join_executor(self, budget, *, deadline_ns: int):
        """Actual observer join, still holding the original closure publisher.

        Native C closes its own ledger first. Only after its exact closure is
        independently verified does P publish the complete termination witness.
        C then publishes ORIGINAL_CONTROLLER; P validates it before releasing
        the separately counted publisher. No timeout is treated as completion.
        """
        from hashlib import sha256
        from kronos.common.failed_fenced_recovery import canonical_bytes
        self.witness.join_and_close(budget, deadline_ns)
        identity = "controller-closure-" + sha256(canonical_bytes({
            "attempt": self.witness.original_attempt,
            "controller": self.witness.original_controller})).hexdigest()
        closure = self._wait_native_proof("CONTROLLER_CLOSURE", budget, deadline_ns,
            lambda value: value["identity"] == identity)
        self.witness.observe_controller_closure(self.registry, closure, self.ledger.lineage)
        payload = self.witness.termination_payload("executor-return-" + uuid4().hex,
            self.ledger.process, self.ledger.lineage)
        budget.check(deadline_ns)
        result = self.ledger.publish_proof("EXECUTOR_TERMINATION", payload)
        budget.check(deadline_ns)
        from kronos.common.failed_fenced_recovery import _as_blob
        controller = self._wait_native_proof("ORIGINAL_CONTROLLER", budget, deadline_ns,
            lambda value: value["execution_closure"] == _as_blob(closure)
                and value["executor"] == _as_blob(result))
        self.retain_controller_closure(controller, result)
        budget.check(deadline_ns)
        return result

    def _wait_native_proof(self, kind, budget, deadline_ns, matches):
        """Observe bounded immutable native publications, never retry an effect.

        No HTTP field, environment value or supplied filename selects a proof.
        Every candidate comes from the existing private no-follow blob estate,
        exact actual original controller/lineage, fixed kind and full registry.
        Absence merely waits within the original absolute deadline; corrupt or
        ambiguous matching evidence denies and leaves ownership counted.
        """
        from hashlib import sha256
        import os
        import time
        from kronos.common.failed_fenced_recovery import MAX_RECORD, decode_canonical
        while True:
            budget.check(deadline_ns)
            directory = self.ledger.store._dir(("blobs",))
            try:
                names = sorted(os.listdir(directory))
            finally:
                os.close(directory)
            if len(names) > 4096:
                raise ValueError("FAILED_FENCED_ORIGINAL_PROOF_SCAN_LIMIT")
            found, consumed = [], 0
            for name in names:
                budget.check(deadline_ns)
                if re.fullmatch(r"[0-9a-f]{64}\.blob", name) is None:
                    raise ValueError("FAILED_FENCED_ORIGINAL_PROOF_NAMESPACE_INVALID")
                raw = self.ledger.store._read(("blobs",), name, 16 * MAX_RECORD + 1)
                consumed += len(raw)
                if consumed > 64 * MAX_RECORD or sha256(raw).hexdigest() != name[:-5]:
                    raise ValueError("FAILED_FENCED_ORIGINAL_PROOF_SCAN_INVALID")
                try:
                    value = decode_canonical(raw)
                except ValueError:
                    continue  # An opaque source/package blob is not a proof.
                if type(value) is not dict or value.get("kind") != kind:
                    continue
                payload = value.get("payload")
                if (type(payload) is not dict
                        or payload.get("controller") != self.witness.original_controller
                        or payload.get("lineage") != self.ledger.lineage):
                    continue
                # Authentication and complete semantic validation precede use
                # of any purported controller completion or matching predicate.
                evidence = self.registry.proof_evidence(raw)
                checked = self.registry.verify(evidence, kind, context={"mode": "ORIGINAL"})
                if matches(checked["payload"]):
                    found.append(evidence)
            if len(found) > 1:
                raise ValueError("FAILED_FENCED_ORIGINAL_PROOF_AMBIGUOUS")
            if found:
                budget.check(deadline_ns)
                return found[0]
            time.sleep(min(0.01, budget.remaining_seconds(deadline_ns)))

    def retain_controller_closure(self, controller, completion):
        ledger = self.ledger
        # All fields are verified by their fixed owner adapters; this operation
        # cannot construct a missing controller closure or infer closed rights.
        result = ledger.publish_executor({"lineage": ledger.lineage,
            "original": ledger.original, "executor": self.executor,
            "previous": ledger.executor_head, "state": "TERMINATED",
            "original_controller": controller, "no_child_start": controller,
            "no_consumption": controller, "completion": completion})
        ledger.coordinator.finish_original_publication(self.executor)
        return result

    def retain_first_failure(self) -> None:
        with self._lock:
            ledger = self.ledger
            failure = ledger.coordinator.failure_snapshot()
            if (ledger.original is None or ledger.terminal is not None
                    or failure["state"] != "FAILED_FENCED"):
                return
            codes = {"DRAIN_TIMEOUT": "TIMEOUT", "CLEANUP_UNRESOLVED": "CLEANUP",
                     "OWNER_PROOF_UNAVAILABLE": "ACCOUNTING", "HANDOFF_FAILED": "DURABILITY"}
            code = codes[failure["failure"]]
            evidence = ledger.publish_proof("FAILURE_FACT", {
                "identity": "original-failure-" + uuid4().hex,
                "process": ledger.process, "phase": "ORIGINAL", "code": code,
                "original_failure": None, "observed_ns": str(failure["failed_ns"]),
                "owner_facts": [], "outstanding_owners": "1"})
            ledger.record_terminal({"lineage": self.payload["lineage"],
                "original": ledger.original, "first_failure": code,
                "failure_evidence": evidence,
                "original_deadline_ns": self.payload["original_drain_deadline_ns"],
                "failed_ns": str(failure["failed_ns"]), "obligations": [],
                "cleanup": [], "executor": ledger.executor_head})
