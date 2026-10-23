"""R3 native bootstrap and one-shot composition authority.

This module is deliberately independent of Browser/product construction.  A
caller supplies the already authenticated R3 codec, fixed private estate and
closed evidence registry.  Environment selectors locate a transaction only.
They never grant authority.  No ordinary V1/V2 handoff is produced here.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from threading import get_ident
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import fcntl
import os
import select
import stat
import struct
import subprocess
import json
import time
from typing import Mapping


PREFIX = "KRONOS_FAILED_FENCED_RECOVERY_"
SELECTORS = (PREFIX + "VERSION", PREFIX + "SLOT", PREFIX + "CHILD_NONCE")
ORDINARY_SELECTORS = frozenset({
    "KRONOS_MAINTENANCE_GENERATION", "KRONOS_MAINTENANCE_PARENT",
    "KRONOS_MAINTENANCE_PROOF", "KRONOS_MAINTENANCE_PROTOCOL",
    "KRONOS_MAINTENANCE_REVISION", "KRONOS_LEGACY_BOOTSTRAP_ID",
    "KRONOS_LEGACY_BOOTSTRAP_PROOF", "KRONOS_LAUNCH_MODE",
})
FRAME_LIMIT = 8192


class RecoveryStartupError(ValueError):
    """A bounded denial; never includes private custody or arbitrary paths."""


def run_native_helper(arguments, *, budget, cwd=None, timeout_cap=20):
    """Preserve source predicates while consuming only the inherited budget.

    A helper which crosses the deadline is not killed, forgotten or declared
    complete.  The bootstrap remains synchronously owned through its actual
    return.  Its late result can never grant authority.  This is intentionally
    distinct from subprocess.run's timeout cancellation behavior.
    """
    budget.check()
    timeout = min(timeout_cap, budget.remaining_seconds())
    with subprocess.Popen(arguments, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL) as process:
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # No cancellation/kill fallback, no abandoned child.  A late return
            # remains a failed, spent bootstrap, regardless of its exit code.
            process.communicate()
            raise RecoveryStartupError("RECOVERY_SOURCE_HELPER_DEADLINE") from None
        budget.check()
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, arguments, output=output)
        return output


def selectors(environment: Mapping[str, str]):
    """Parse all-or-none locators, rejecting unknown/mixed protocol selectors."""
    import re
    present = {key for key in environment if key.startswith(PREFIX)}
    if not present:
        return None
    if (present != set(SELECTORS) or environment[SELECTORS[0]] != "1.0.0"
            or any(key in environment for key in ORDINARY_SELECTORS)
            or any(re.fullmatch(r"[0-9a-f]{64}", environment[key]) is None
                   for key in SELECTORS[1:])):
        raise RecoveryStartupError("RECOVERY_STARTUP_SELECTORS_REJECTED")
    return environment[SELECTORS[1]], environment[SELECTORS[2]]


def _wait(fd, event, budget, deadline_ns):
    while True:
        budget.check(deadline_ns)
        poller = select.poll()
        poller.register(fd, event | select.POLLERR | select.POLLHUP | select.POLLNVAL)
        # Round up solely for the wait primitive; check the absolute bound after
        # every return, before consuming or granting authority.
        timeout = max(1, int(budget.remaining_seconds(deadline_ns) * 1000 + .999))
        try:
            events = poller.poll(timeout)
        except InterruptedError:
            continue
        budget.check(deadline_ns)
        if events:
            if events[0][1] & (select.POLLERR | select.POLLNVAL):
                raise RecoveryStartupError("RECOVERY_PIPE_FAILED")
            return


def _pipe(fd):
    before = os.fstat(fd)
    if not stat.S_ISFIFO(before.st_mode):
        raise RecoveryStartupError("RECOVERY_PIPE_REQUIRED")
    # No child qualification helper is allowed to inherit the grant channel.
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
    os.set_blocking(fd, False)
    return before


def receive_composition_frame(budget, *, descriptor=3, expected_descriptor=3):
    """Read exactly one bounded frame and EOF; close even on rejection.

    Production callers use descriptor 3.  A different expected descriptor is
    useful only to the isolated library harness and does not select production
    admission.  This function returns transport bytes, never authority.
    """
    if descriptor != expected_descriptor:
        raise RecoveryStartupError("RECOVERY_PIPE_DESCRIPTOR_REJECTED")
    try:
        before = _pipe(descriptor)
        raw = bytearray()
        size = None
        while True:
            budget.check()
            _wait(descriptor, select.POLLIN, budget, None)
            try:
                chunk = os.read(descriptor, 4 + FRAME_LIMIT + 1 - len(raw))
            except (InterruptedError, BlockingIOError):
                continue
            budget.check()
            if not chunk:
                break
            raw.extend(chunk)
            if size is None and len(raw) >= 4:
                size = struct.unpack("!I", raw[:4])[0]
                if not 1 <= size <= FRAME_LIMIT:
                    raise RecoveryStartupError("RECOVERY_PIPE_LENGTH_REJECTED")
            if (size is not None and len(raw) > size + 4) or len(raw) > FRAME_LIMIT + 4:
                raise RecoveryStartupError("RECOVERY_PIPE_EXTRA_BYTES")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise RecoveryStartupError("RECOVERY_PIPE_CHANGED")
        if size is None or len(raw) != size + 4:
            raise RecoveryStartupError("RECOVERY_PIPE_TRUNCATED")
        return bytes(raw[4:]), budget.now_ns()
    finally:
        os.close(descriptor)


def send_composition_frame(descriptor, raw, budget):
    """One frame on the original private pipe, followed by mandatory closure."""
    try:
        _pipe(descriptor)
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= FRAME_LIMIT:
            raise RecoveryStartupError("RECOVERY_PIPE_LENGTH_REJECTED")
        framed = struct.pack("!I", len(raw)) + raw
        offset = 0
        while offset < len(framed):
            _wait(descriptor, select.POLLOUT, budget, None)
            try:
                count = os.write(descriptor, framed[offset:])
            except (InterruptedError, BlockingIOError):
                continue
            budget.check()
            if count <= 0:
                raise RecoveryStartupError("RECOVERY_PIPE_FAILED")
            offset += count
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class NativeBootstrap:
    """Actual native startup evidence plus separately pinned executing code."""

    startup: object
    process: dict
    modules: tuple[tuple[str, str], ...]

    @property
    def runtime(self):
        return sha256(self.startup.evidence_identity.encode("utf-8")).hexdigest()

    def validate(self, *, expected_process, expected_modules):
        # Reconstruct the native type to enforce its actual evidence digest;
        # neither an arbitrary dictionary nor the nonce can supply identity.
        from kronos.intraday.runtime_identity import StartupEvidence
        if type(self.startup) is not StartupEvidence:
            raise RecoveryStartupError("RECOVERY_NATIVE_IDENTITY_REJECTED")
        replace(self.startup)
        if (self.startup.process_id != os.getpid()
                or self.startup.source_state != "CLEAN_COMMIT"
                or self.startup.load_verification != "PINNED_STARTUP_IMPORTS"
                or self.process != expected_process
                or self.process["pid"] != str(os.getpid())
                or self.process["runtime"] != self.runtime
                or self.modules != tuple(sorted(expected_modules))
                or len(dict(self.modules)) != len(self.modules)):
            raise RecoveryStartupError("RECOVERY_NATIVE_IDENTITY_REJECTED")
        return self


class CompositionLatch:
    """An in-memory authority receipt bound to one actual process and fork.

    Only BootstrapSession creates it after complete frame/MAC/chain checking.
    Persisted authority bytes cannot reconstruct this object after a restart.
    """

    __slots__ = ("raw", "record", "received_ns", "verified_ns", "_pid", "_spent")

    def __init__(self, raw, record, received_ns, verified_ns):
        self.raw, self.record = raw, record
        self.received_ns, self.verified_ns = received_ns, verified_ns
        self._pid, self._spent = os.getpid(), False

    def take(self, budget, ready_deadline_ns):
        if self._spent or os.getpid() != self._pid:
            raise RecoveryStartupError("RECOVERY_COMPOSITION_LATCH_SPENT")
        self._spent = True
        budget.check(ready_deadline_ns)
        return self.record


class ReadyBudget:
    """Post-grant phase with the original fork-enter absolute READY bound.

    Creation requires an already validated live grant receipt. This does not
    extend the stop budget: it cannot be used for any pre-grant helper, grant
    transport, gate or bootstrap identity publication.
    """
    def __init__(self, stop_budget, latch):
        if type(latch) is not CompositionLatch or latch._pid != os.getpid() or latch._spent:
            raise RecoveryStartupError("RECOVERY_LIVE_LATCH_REQUIRED")
        grant = latch.record["payload"]
        self.clock = stop_budget.clock
        self.origin_ns = stop_budget.origin_ns
        self.stop_deadline_ns = stop_budget.stop_deadline_ns
        self.ready_deadline_ns = int(grant["ready_deadline_ns"])
        if (int(grant["stop_deadline_ns"]) != self.stop_deadline_ns
                or not self.origin_ns <= latch.received_ns <= latch.verified_ns < self.stop_deadline_ns
                or self.ready_deadline_ns <= self.stop_deadline_ns):
            raise RecoveryStartupError("RECOVERY_READY_PHASE_REJECTED")
        self._last, self._failed = latch.verified_ns, False
        self.check()

    def now_ns(self):
        now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        if now < self._last:
            self._failed = True
        self._last = max(now, self._last)
        if self._failed:
            raise RecoveryStartupError("RECOVERY_READY_CLOCK_REJECTED")
        return now

    def check(self, deadline_ns=None):
        deadline = self.ready_deadline_ns if deadline_ns is None else min(self.ready_deadline_ns, int(deadline_ns))
        if self.now_ns() >= deadline:
            self._failed = True
            raise RecoveryStartupError("RECOVERY_READY_DEADLINE_EXPIRED")
        return self._last

    def remaining_seconds(self, deadline_ns=None):
        now = self.check(deadline_ns)
        deadline = self.ready_deadline_ns if deadline_ns is None else min(self.ready_deadline_ns, int(deadline_ns))
        return (deadline - now) / 1e9


class BootstrapSession:
    """One source-bound child bootstrap, supplied with verified protocol context.

    The context is the exact chain already checked by the closed R3 registry,
    not a caller's environment.  This class additionally enforces actual child
    identity, timings, one-frame receipt and once-only publication/consumption.
    """

    def __init__(self, *, codec, store, registry, budget, chain, native,
                 parent, canonical_parent_check):
        from kronos.common.failed_fenced_recovery import record_ref
        self.codec, self.store, self.registry, self.budget = codec, store, registry, budget
        self.chain, self.native, self.parent = chain, native, parent
        self._canonical_parent_check = canonical_parent_check
        self._published = self._consumed = False
        self.latch = None
        self._record_ref = record_ref
        self._pid = os.getpid()
        self._validate_context()

    def _validate_context(self):
        self.budget.check()
        if type(self.native) is not NativeBootstrap:
            raise RecoveryStartupError("RECOVERY_NATIVE_IDENTITY_REJECTED")
        modules = self.chain.get("executing_bootstrap_modules")
        process = self.chain.get("observed_child")
        if modules is None or process is None:
            raise RecoveryStartupError("RECOVERY_ACTUAL_BOOTSTRAP_WITNESS_REQUIRED")
        self.native.validate(expected_process=process, expected_modules=modules)
        claim, intent = self.chain["CLAIM"]["payload"], self.chain["CHILD_INTENT"]["payload"]
        if (claim["slot"] != intent["slot"] or claim["transaction"] != intent["transaction"]
                or self.parent != claim["launcher"]
                or self.native.process["pid"] != str(os.getpid())
                or self.native.process["runtime"] != self.native.runtime
                or intent["claim"] != self._record_ref(self.chain["CLAIM_RAW"])):
            raise RecoveryStartupError("RECOVERY_BOOTSTRAP_CONTEXT_REJECTED")
        self._canonical_parent_check()
        self.budget.check()

    def publish_identity(self, bootstrap_evidence, bootstrap_raw, native_raw):
        """Publish the sole dependency-ordered native/bootstrap/identity set."""
        if self._published or self._pid != os.getpid():
            raise RecoveryStartupError("RECOVERY_BOOTSTRAP_ALREADY_PUBLISHED")
        self._published = True  # Failure spends the attempt too.
        self._validate_context()
        # The only permitted pre-grant publications are the dependency-ordered
        # slot bootstrap set below. Validate these exact in-memory bytes before
        # publication; do not create duplicate blobs to make a reader succeed.
        proof = _verify_inline_bootstrap(self.registry, bootstrap_evidence,
            bootstrap_raw, native_raw, self.native.process, self.chain)
        if (sha256(bootstrap_raw).hexdigest() != bootstrap_evidence["hash"]
                or str(len(bootstrap_raw)) != bootstrap_evidence["bytes"]
                or sha256(native_raw).hexdigest() != proof["payload"]["startup"]["hash"]
                or str(len(native_raw)) != proof["payload"]["startup"]["bytes"]
                or decode_native_startup(native_raw) != self.native.startup):
            raise RecoveryStartupError("RECOVERY_BOOTSTRAP_PUBLICATION_BYTES_CHANGED")
        intent = self.chain["CHILD_INTENT"]["payload"]
        now = self.budget.now_ns()
        raw = self.codec.encode("CHILD_IDENTITY", {
            "slot": intent["slot"], "transaction": intent["transaction"],
            "intent": self._record_ref(self.chain["CHILD_INTENT_RAW"]),
            "child": self.native.process, "child_nonce": intent["child_nonce"],
            "parent": self.parent, "bootstrap": bootstrap_evidence,
            "observed_ns": str(now), "execution_owner": intent["bootstrap_owner"],
        }, "SUCCESSOR", now)
        self.store.publish_bootstrap(intent["slot"], native_raw, bootstrap_raw, raw, budget=self.budget)
        self.budget.check()
        self.chain["CHILD_IDENTITY_RAW"] = raw
        self.chain["CHILD_IDENTITY"] = self.codec.decode(raw, expected_kind="CHILD_IDENTITY")
        return raw

    def receive_authority(self, *, descriptor=3, expected_descriptor=3):
        if not self._published or self.latch is not None or self._pid != os.getpid():
            raise RecoveryStartupError("RECOVERY_BOOTSTRAP_SEQUENCE_REJECTED")
        raw, received = receive_composition_frame(self.budget, descriptor=descriptor,
                                                  expected_descriptor=expected_descriptor)
        grant = self.codec.decode(raw, expected_kind="COMPOSITION_AUTHORITY")
        payload = grant["payload"]
        intent = self.chain["CHILD_INTENT"]["payload"]
        started_raw = self.store.resolve(payload["child_started"])
        started = self.codec.decode(started_raw, expected_kind="CHILD_STARTED")["payload"]
        claim = self.chain["CLAIM"]["payload"]
        self._canonical_parent_check()
        self.registry.verify(payload["controller_capability"], "CONTROLLER_CAPABILITY",
                             subject=self.parent, context=self.chain)
        verified = self.budget.now_ns()
        ready = int(started["ready_deadline_ns"])
        if (payload["slot"] != intent["slot"] or payload["transaction"] != intent["transaction"]
                or payload["intent"] != self._record_ref(self.chain["CHILD_INTENT_RAW"])
                or payload["claim"] != self._record_ref(self.chain["CLAIM_RAW"])
                or started["child_identity"] != self._record_ref(self.chain["CHILD_IDENTITY_RAW"])
                or payload["parent"] != self.parent or started["parent"] != self.parent
                or payload["child"] != self.native.process or started["child"] != self.native.process
                or payload["child_nonce"] != intent["child_nonce"]
                or started["child_nonce"] != intent["child_nonce"]
                or payload["controller_capability"] != claim["launcher_capability"]
                or payload["stop_deadline_ns"] != claim["limits"]["stop_deadline_ns"]
                or int(payload["ready_deadline_ns"]) != ready
                or ready != int(started["fork_enter_ns"]) + 120_000_000_000
                or not max(int(payload["child_started_durable_ns"]),
                           int(payload["identity_verified_ns"])) <= int(payload["gate_ns"])
                or not int(payload["gate_ns"]) <= received <= verified < int(payload["stop_deadline_ns"])
                or payload["decision"] != "GRANT_ONCE"):
            raise RecoveryStartupError("RECOVERY_LIVE_AUTHORITY_REJECTED")
        self.budget.check(ready)
        self.chain["CHILD_STARTED_RAW"] = started_raw
        self.chain["CHILD_STARTED"] = self.codec.decode(started_raw, expected_kind="CHILD_STARTED")
        self.latch = CompositionLatch(raw, grant, received, verified)
        return self.latch

    def consume(self, *, bootstrap_evidence, checkpoint, restoration_scope):
        """Persist exact receipt before normal startup ownership or composition."""
        if self._consumed or self.latch is None or self._pid != os.getpid():
            raise RecoveryStartupError("RECOVERY_CONSUMPTION_REJECTED")
        self._consumed = True
        grant = self.latch.record["payload"]
        ready = int(grant["ready_deadline_ns"])
        ready_budget = ReadyBudget(self.budget, self.latch)
        now = ready_budget.check()
        # All live proof freshness predicates are independently re-evaluated at
        # consumption, even when grant verification itself was timely.
        for kind in ("OWNER_PROOF", "CERTIFICATE", "PREPARED_COMMIT", "ACK", "OBSERVATION"):
            if not 0 <= now - int(self.chain[kind]["issued_ns"]) <= 45_000_000_000:
                raise RecoveryStartupError("RECOVERY_CONSUMPTION_PROOF_EXPIRED")
        intent = self.chain["CHILD_INTENT"]["payload"]
        kinds = {"guard": "GUARD", "claim": "CLAIM", "accepted": "CLAIM_ACCEPTED",
                 "seal": "SEAL", "owner_proof": "OWNER_PROOF", "certificate": "CERTIFICATE",
                 "prepared": "PREPARED_COMMIT", "ack": "ACK", "observation": "OBSERVATION",
                 "exit_proof": "EXIT_PROOF", "intent": "CHILD_INTENT", "child_started": "CHILD_STARTED"}
        body = {name: self._record_ref(self.chain[kind + "_RAW"]) for name, kind in kinds.items()}
        body.update(slot=intent["slot"], transaction=intent["transaction"],
                    composition_authority=self._record_ref(self.latch.raw), authority_bytes=self.latch.raw.hex(),
                    authority_received_ns=str(self.latch.received_ns), authority_verified_ns=str(self.latch.verified_ns),
                    consumer=self.native.process, child_nonce=intent["child_nonce"], checkpoint=checkpoint,
                    consumed_ns=str(ready_budget.now_ns()), ready_deadline_ns=str(ready), source=bootstrap_evidence,
                    capability=bootstrap_evidence, execution_owner=intent["bootstrap_owner"])
        raw = self.codec.encode("CONSUMPTION", body, "SUCCESSOR", int(body["consumed_ns"]))
        self.store.reserve(intent["slot"], "consumption", raw)
        ready_budget.check(ready)
        context = self.codec.encode("STARTUP_CONTEXT", {
            "slot": intent["slot"], "transaction": intent["transaction"],
            "original": self._record_ref(self.chain["ORIGINAL_RAW"]),
            "terminal": self._record_ref(self.chain["TERMINAL_RAW"]),
            "consumption": self._record_ref(raw), "child_started": grant["child_started"],
            "runtime": self.native.process, "checkpoint": checkpoint,
            "restoration_scope": restoration_scope, "ready_deadline_ns": str(ready),
        }, "SUCCESSOR", ready_budget.now_ns())
        self.store.publish(context)
        ready_budget.check(ready)
        # The latch is consumed at the actual boundary, after receipt durability.
        self.latch.take(ready_budget, ready)
        # Attempt-spent is not completion. Retain these original bytes only
        # after both durable publications and the live latch consumption pass.
        if (self.store.read_reservation(intent["slot"], "consumption") != raw
                or self.store.resolve(self._record_ref(context)) != context):
            raise RecoveryStartupError("RECOVERY_CONSUMPTION_READBACK_CHANGED")
        ready_budget.check(ready)
        self.consumption_raw, self.startup_context_raw = raw, context
        self.chain["CONSUMPTION_RAW"], self.chain["STARTUP_CONTEXT_RAW"] = raw, context
        self.chain["CONSUMPTION"] = self.codec.decode(raw, expected_kind="CONSUMPTION")
        self.chain["STARTUP_CONTEXT"] = self.codec.decode(context, expected_kind="STARTUP_CONTEXT")
        self.ready_budget = ready_budget
        from tools.runtime_source_gate import advance_native_child_loader
        advance_native_child_loader(self)
        return self.codec.decode(context, expected_kind="STARTUP_CONTEXT")


_EVIDENCE_FIELDS = {
    "CUSTODY": {"controller_capability": "CONTROLLER_CAPABILITY", "live_control": "CONTROL_BINDING",
                "process_binding": "PLATFORM_OBSERVATION"},
    "ORIGINAL": {"source": "SOURCE", "capability": "CAPABILITY", "control": "CONTROL_BINDING",
                 "authorization": "ORIGINAL_AUTHORITY",
                 "ticket_roster": "FENCE_ROSTER", "owner_scope": "SCOPE"},
    "EXECUTOR": {"original_controller": "ORIGINAL_CONTROLLER", "no_child_start": "ORIGINAL_CONTROLLER",
                 "no_consumption": "ORIGINAL_CONTROLLER", "completion": "EXECUTOR_TERMINATION"},
    "TERMINAL": {"failure_evidence": "FAILURE_FACT"},
    "GUARD": {"authorization": "RECOVERY_AUTHORITY", "scope": "SCOPE", "artifacts": "ARTIFACT_APPROVAL"},
    "CLAIM": {"authorization": "RECOVERY_AUTHORITY", "launcher_capability": "CONTROLLER_CAPABILITY",
              "successor_source": "TARGET_ARTIFACT", "successor_capability": "TARGET_ARTIFACT",
              "installed_package": "PACKAGE", "rollback_package": "PACKAGE", "compatibility": "COMPATIBILITY"},
    "CLAIM_ACCEPTED": {"capability": "CAPABILITY", "control": "CONTROL_BINDING"},
    "SEAL": {"write_free_tail": "TAIL", "retained_control": "CONTROL_BINDING", "owner_scope": "SCOPE"},
    "OWNER_PROOF": {"reconciliation": "OWNER_RESULT"},
    "CERTIFICATE": {"authorization": "RECOVERY_AUTHORITY", "scope": "SCOPE", "artifacts": "ARTIFACT_APPROVAL"},
    "EXIT_PROOF": {"process_evidence": "PLATFORM_OBSERVATION", "listener_evidence": "PLATFORM_OBSERVATION"},
    "CHILD_INTENT": {"successor_source": "TARGET_ARTIFACT", "successor_capability": "TARGET_ARTIFACT",
                     "installed_package": "PACKAGE"},
    "CHILD_IDENTITY": {"bootstrap": "BOOTSTRAP_IDENTITY"},
    "CHILD_STARTED": {"kernel_parent": "PLATFORM_OBSERVATION"},
    "CONSUMPTION": {"source": "BOOTSTRAP_IDENTITY", "capability": "BOOTSTRAP_IDENTITY"},
    "STARTUP_CONTEXT": {"restoration_scope": "RESTORATION_PLAN"},
    "READY_RECEIPT": {"restoration": "RESTORATION", "source": "SOURCE", "capability": "CAPABILITY",
                      "provider_absence": "ABSENCE", "transport_absence": "ABSENCE"},
    "FAILURE": {"evidence": "FAILURE_FACT"},
}



def _validate_child_receipts(chain, *, historical, budget):
    """Cross-record child semantics over an already authenticated exact graph.

    This helper confers no issuer or transport authority. It closes the sole
    grant, consumption and final READY identities after the graph's decoder,
    fixed store and closed registry have independently validated their bytes.
    """
    from .failed_fenced_recovery import record_ref
    claim=chain["CLAIM"]["payload"];intent=chain["CHILD_INTENT"]["payload"]
    stop=int(claim["limits"]["stop_deadline_ns"])
    started=chain.get("CHILD_STARTED",{}).get("payload")
    if started is None:
        if any(k in chain for k in ("COMPOSITION_AUTHORITY","CONSUMPTION","STARTUP_CONTEXT","READY_RECEIPT")):
            raise RecoveryStartupError("RECOVERY_CHILD_STARTED_REQUIRED")
        return None
    identity=chain.get("CHILD_IDENTITY",{}).get("payload")
    if (identity is None or started["child_identity"]!=record_ref(chain["CHILD_IDENTITY_RAW"])
            or started["intent"]!=record_ref(chain["CHILD_INTENT_RAW"])
            or started["child"]!=identity["child"] or started["parent"]!=identity["parent"]
            or started["parent"]!=claim["launcher"] or started["child_nonce"]!=intent["child_nonce"]
            or identity["intent"]!=started["intent"] or identity["child_nonce"]!=intent["child_nonce"]
            or not int(claim["limits"]["origin_ns"])<=int(started["fork_enter_ns"])<=int(started["fork_return_ns"])<stop
            or int(started["ready_deadline_ns"])!=int(started["fork_enter_ns"])+120_000_000_000):
        raise RecoveryStartupError("RECOVERY_CHILD_STARTED_BINDING_CHANGED")
    grant=chain.get("COMPOSITION_AUTHORITY",{}).get("payload")
    if grant is None:
        if any(k in chain for k in ("CONSUMPTION","STARTUP_CONTEXT","READY_RECEIPT")):
            raise RecoveryStartupError("RECOVERY_LIVE_AUTHORITY_REQUIRED")
        return None
    ready=int(started["ready_deadline_ns"])
    if (grant["claim"]!=record_ref(chain["CLAIM_RAW"]) or grant["intent"]!=started["intent"]
            or grant["child_started"]!=record_ref(chain["CHILD_STARTED_RAW"])
            or grant["parent"]!=started["parent"] or grant["child"]!=started["child"]
            or grant["child_nonce"]!=intent["child_nonce"] or grant["controller_capability"]!=claim["launcher_capability"]
            or grant["stop_deadline_ns"]!=claim["limits"]["stop_deadline_ns"]
            or int(grant["ready_deadline_ns"])!=ready or grant["decision"]!="GRANT_ONCE"
            or not int(chain["CHILD_STARTED"]["issued_ns"])<=int(grant["child_started_durable_ns"])<=int(grant["gate_ns"])<stop
            or not int(started["fork_return_ns"])<=int(grant["identity_verified_ns"])<=int(grant["gate_ns"])):
        raise RecoveryStartupError("RECOVERY_LIVE_AUTHORITY_BINDING_CHANGED")
    consumption=chain.get("CONSUMPTION",{}).get("payload")
    if consumption is None:
        if any(k in chain for k in ("STARTUP_CONTEXT","READY_RECEIPT")):
            raise RecoveryStartupError("RECOVERY_CONSUMPTION_REQUIRED")
        return None
    refs={"guard":"GUARD","claim":"CLAIM","accepted":"CLAIM_ACCEPTED","seal":"SEAL",
          "owner_proof":"OWNER_PROOF","certificate":"CERTIFICATE","prepared":"PREPARED_COMMIT",
          "ack":"ACK","observation":"OBSERVATION","exit_proof":"EXIT_PROOF","intent":"CHILD_INTENT",
          "child_started":"CHILD_STARTED","composition_authority":"COMPOSITION_AUTHORITY"}
    if (any(consumption[field]!=record_ref(chain[kind+"_RAW"]) for field,kind in refs.items())
            or consumption["authority_bytes"]!=chain["COMPOSITION_AUTHORITY_RAW"].hex()
            or consumption["consumer"]!=started["child"] or consumption["child_nonce"]!=intent["child_nonce"]
            or consumption["source"]!=identity["bootstrap"] or consumption["capability"]!=identity["bootstrap"]
            or consumption["checkpoint"]!=intent["checkpoint"] or int(consumption["ready_deadline_ns"])!=ready
            or consumption["execution_owner"]!=intent["bootstrap_owner"]
            or not int(grant["gate_ns"])<=int(consumption["authority_received_ns"])<=int(consumption["authority_verified_ns"])<stop
            or not int(consumption["authority_verified_ns"])<=int(consumption["consumed_ns"])<ready):
        raise RecoveryStartupError("RECOVERY_CONSUMPTION_BINDING_CHANGED")
    consumed=int(consumption["consumed_ns"])
    for kind in ("OWNER_PROOF","CERTIFICATE","PREPARED_COMMIT","ACK","OBSERVATION"):
        if not 0<=consumed-int(chain[kind]["issued_ns"])<=45_000_000_000:
            raise RecoveryStartupError("RECOVERY_CONSUMPTION_PROOF_EXPIRED")
    context=chain.get("STARTUP_CONTEXT",{}).get("payload")
    if context is not None:
        if (context["consumption"]!=record_ref(chain["CONSUMPTION_RAW"])
                or context["original"]!=record_ref(chain["ORIGINAL_RAW"])
                or context["terminal"]!=record_ref(chain["TERMINAL_RAW"])
                or context["child_started"]!=record_ref(chain["CHILD_STARTED_RAW"])
                or context["runtime"]!=started["child"] or context["checkpoint"]!=intent["checkpoint"]
                or int(context["ready_deadline_ns"])!=ready
                or not consumed<=int(chain["STARTUP_CONTEXT"]["issued_ns"])<ready):
            raise RecoveryStartupError("RECOVERY_STARTUP_CONTEXT_BINDING_CHANGED")
    receipt=chain.get("READY_RECEIPT",{}).get("payload")
    if receipt is not None:
        if (context is None or receipt["guard"]!=claim["guard"]
                or receipt["intent"]!=record_ref(chain["CHILD_INTENT_RAW"])
                or receipt["child_started"]!=record_ref(chain["CHILD_STARTED_RAW"])
                or receipt["consumption"]!=record_ref(chain["CONSUMPTION_RAW"])
                or receipt["startup"]!=record_ref(chain["STARTUP_CONTEXT_RAW"])
                or receipt["runtime"]!=started["child"] or receipt["execution_owner"]!=intent["execution_owner"]
                or not int(chain["STARTUP_CONTEXT"]["issued_ns"])<=int(receipt["ready_ns"])<ready
                or not int(receipt["ready_ns"])<=int(chain["READY_RECEIPT"]["issued_ns"])<ready):
            raise RecoveryStartupError("RECOVERY_READY_RECEIPT_BINDING_CHANGED")
    if not historical and (budget is None or not consumed<=budget.now_ns()<ready):
        raise RecoveryStartupError("RECOVERY_READY_OBSERVATION_DEADLINE")
    return consumed


_HISTORICAL_GRAPH_READER = object()


class _HistoricalRecoveryValidation:
    """Closed read-only mode for an existing exact READY graph, never a grant."""
    __slots__=("_codec","_store","_ready_raw","_ready_ref","_proof_hashes","_payloads")
    def __init__(self,codec,store,ready_raw,chain,*,_reader=None):
        from .failed_fenced_recovery import record_ref
        if _reader is not _HISTORICAL_GRAPH_READER:
            raise RecoveryStartupError("RECOVERY_HISTORICAL_READER_REQUIRED")
        ready=codec.decode(ready_raw,"READY_RECEIPT")
        if chain.get("READY_RECEIPT_RAW")!=ready_raw:
            raise RecoveryStartupError("RECOVERY_HISTORICAL_READY_REQUIRED")
        claim=chain["CLAIM"]["payload"]
        restoration_raw=store.read_blob(ready["payload"]["restoration"])
        restoration=codec.decode_proof(restoration_raw,"RESTORATION")
        if (restoration["role"]!="SUCCESSOR" or restoration["issuer"]!=ready["payload"]["runtime"]
                or restoration["payload"]["process"]!=ready["payload"]["runtime"]):
            raise RecoveryStartupError("RECOVERY_HISTORICAL_RESTORATION_CHANGED")
        self._codec,self._store,self._ready_raw=codec,store,ready_raw
        self._ready_ref=record_ref(ready_raw)
        # RESTORATION deliberately has no compatibility field. The graph's
        # single exact relation is CLAIM.compatibility; actual child SOURCE and
        # restoration validate the corresponding target components separately.
        self._proof_hashes=frozenset((claim["compatibility"]["hash"],))
        original=chain["ORIGINAL"]["payload"];r=ready["payload"]
        references=[("SOURCE",original["source"]),("CAPABILITY",original["capability"]),
            ("SOURCE",r["source"]),("CAPABILITY",r["capability"]),("RESTORATION",r["restoration"]),
            ("ABSENCE",r["provider_absence"]),("ABSENCE",r["transport_absence"]),
            ("BOOTSTRAP_IDENTITY",chain["CHILD_IDENTITY"]["payload"]["bootstrap"])]
        references.extend(("OWNER_RESULT",ref) for ref in chain["OWNER_PROOF"]["payload"]["owner_results"])
        references.append(("OWNER_RESULT",chain["SEAL"]["payload"]["checkpoint"]["evidence"]))
        executor=codec.decode(store.resolve(claim["binding"]["executor"]),"EXECUTOR")["payload"]
        references.append(("EXECUTOR_TERMINATION",executor["completion"]))
        from .failed_fenced_recovery import canonical_bytes
        self._payloads=frozenset((kind,sha256(canonical_bytes(
            codec.decode_proof(store.read_blob(ref),kind)["payload"])).hexdigest()) for kind,ref in references)
    def native_payload(self,kind,payload,registry):
        from .failed_fenced_recovery import canonical_bytes
        return (registry.codec is self._codec and registry.store is self._store
            and self._store.resolve(self._ready_ref)==self._ready_raw
            and (kind,sha256(canonical_bytes(payload)).hexdigest()) in self._payloads)
    def permits(self,proof,registry):
        from .failed_fenced_recovery import canonical_bytes
        if (registry.codec is not self._codec or registry.store is not self._store
                or self._store.resolve(self._ready_ref)!=self._ready_raw
                or proof.get("kind")!="COMPATIBILITY"
                or sha256(canonical_bytes(proof)).hexdigest() not in self._proof_hashes):
            raise RecoveryStartupError("RECOVERY_HISTORICAL_PROOF_CHANGED")
        return True

def _verify_chain_evidence(registry,record,field,chain):
    # CUSTODY was produced by the original C controller. The subsequent
    # recovery launcher is a distinct process, never its historical observer.
    kind=record['kind'];payload=record['payload'];context=chain;subject=None
    if kind=='CUSTODY':
        original=registry._prep(True).record
        if payload['controller']!=original['controller'] or payload['lineage']!=original['lineage']:
            raise RecoveryStartupError('RECOVERY_GRAPH_ORIGINAL_CUSTODY_CHANGED')
        context={**chain,'mode':'ORIGINAL'}
        if field=='process_binding':subject=original['lineage']['predecessor']
    return registry.verify(payload[field],_EVIDENCE_FIELDS[kind][field],subject=subject,context=context)


def validate_recovery_chain(codec, store, registry, tip_raw, *, slot, budget=None,
                            historical=False, native_context=None):
    """Resolve the complete authenticated record graph, with no selected heads.

    The registry applies owning native/evidence predicates.  This traversal
    additionally makes exact cross-record identity, completed publication and
    timely one-child receipt requirements non-optional for every consumer.
    Historical mode validates retained original timing; it never grants a live
    latch or compares old resolved history to today's clock.
    """
    from kronos.common.failed_fenced_recovery import record_ref
    cache, active, by_kind = {}, set(), {}

    def visit(raw, ref=None):
        if budget is not None:
            budget.check()
        if ref is None:
            ref = record_ref(raw)
        if ref["hash"] in active:
            raise RecoveryStartupError("RECOVERY_RECORD_CYCLE")
        if ref["hash"] in cache:
            return
        if len(cache) + len(active) >= 4096:
            raise RecoveryStartupError("RECOVERY_RECORD_GRAPH_LIMIT")
        record = codec.decode(raw, expected_kind=ref["kind"])
        payload = record["payload"]
        if "slot" in payload and payload["slot"] != slot:
            raise RecoveryStartupError("RECOVERY_RECORD_SLOT_CHANGED")
        active.add(ref["hash"])
        # Transport-only bytes resolve their own exact refs without inventing a
        # predecessor durable ACK or a replayable grant file.
        inline = {}
        if record["kind"] == "OBSERVATION":
            inline[payload["ack"]["hash"]] = bytes.fromhex(payload["ack_bytes"])
        if record["kind"] == "CONSUMPTION":
            inline[payload["composition_authority"]["hash"]] = bytes.fromhex(payload["authority_bytes"])
            # ACK has no predecessor durable file. Consumption binds the
            # launcher's immutable OBSERVATION, which alone retains ACK bytes.
            observed_raw = store.resolve(payload["observation"])
            observed = codec.decode(observed_raw, expected_kind="OBSERVATION")
            if (record_ref(observed_raw) != payload["observation"]
                    or observed["payload"]["ack"] != payload["ack"]):
                raise RecoveryStartupError("RECOVERY_REFERENCE_CHANGED")
            inline[payload["ack"]["hash"]] = bytes.fromhex(observed["payload"]["ack_bytes"])

        def children(value):
            if type(value) is dict:
                if set(value) == {"kind", "hash"}:
                    child_raw = inline.get(value["hash"])
                    if child_raw is None:
                        child_raw = store.resolve(value)  # Validates exact canonical Ref on every read.
                    elif record_ref(child_raw) != value:
                        raise RecoveryStartupError("RECOVERY_REFERENCE_CHANGED")
                    visit(child_raw, value)
                else:
                    for child in value.values():
                        children(child)
            elif type(value) is list:
                for child in value:
                    children(child)
        children(payload)
        active.remove(ref["hash"])
        cache[ref["hash"]] = (record, raw)
        by_kind.setdefault(record["kind"], []).append((record, raw))
    visit(tip_raw)

    chain = {}
    for kind, records in by_kind.items():
        if kind not in {"OBLIGATION", "CLEANUP", "EXECUTOR", "FAILURE"} and len(records) != 1:
            raise RecoveryStartupError("RECOVERY_AMBIGUOUS_RECORD_KIND")
        if len(records) == 1:
            chain[kind], chain[kind + "_RAW"] = records[0]
    required = {"CUSTODY", "ORIGINAL", "TERMINAL", "GUARD", "CLAIM", "CLAIM_ACCEPTED",
                "SEAL", "OWNER_PROOF", "CERTIFICATE", "PREPARED_COMMIT", "ACK", "OBSERVATION",
                "EXIT_PROOF", "CHILD_INTENT"}
    if not required <= chain.keys():
        raise RecoveryStartupError("RECOVERY_RECORD_CHAIN_INCOMPLETE")
    if native_context is not None:
        chain.update(native_context)
    chain["historical"] = historical
    chain["accepted_heads"] = chain["SEAL"]["payload"]["obligation_heads"]
    chain["claim_ns"] = chain["CLAIM_ACCEPTED"]["payload"]["claim_ns"]
    if historical:
        chain["historical_validation"] = _HistoricalRecoveryValidation(codec,store,tip_raw,chain,
            _reader=_HISTORICAL_GRAPH_READER)
        identity=chain["CHILD_IDENTITY"]["payload"]
        bootstrap=codec.decode_proof(store.read_blob(identity["bootstrap"]),"BOOTSTRAP_IDENTITY")["payload"]
        chain["observed_child"]=chain["CHILD_STARTED"]["payload"]["child"]
        chain["observed_parent"]=chain["CHILD_STARTED"]["payload"]["parent"]
        chain["executing_bootstrap_modules"]=tuple((row["name"],row["digest"]) for row in bootstrap["loaded_bootstrap"])
    if "CHILD_STARTED" in chain:
        chain["child"] = chain["CHILD_STARTED"]["payload"]["child"]
    elif "observed_child" in chain:
        chain["child"] = chain["observed_child"]
    original = chain["ORIGINAL"]["payload"]
    claim = chain["CLAIM"]["payload"]
    intent = chain["CHILD_INTENT"]["payload"]
    guard = chain["GUARD"]["payload"]
    binding = claim["binding"]
    if (binding != guard["binding"] or original["lineage"] != binding["lineage"]
            or chain["TERMINAL"]["payload"]["lineage"] != binding["lineage"]
            or binding["original"] != record_ref(chain["ORIGINAL_RAW"])
            or binding["terminal"] != record_ref(chain["TERMINAL_RAW"])):
        raise RecoveryStartupError("RECOVERY_ORIGINAL_BINDING_CHANGED")
    target = registry.verify(claim["successor_source"], "TARGET_ARTIFACT")["payload"]
    for kind in ("GUARD", "CERTIFICATE"):
        artifact = registry.verify(chain[kind]["payload"]["artifacts"], "ARTIFACT_APPROVAL")["payload"]
        if artifact["identity"] != target["approval"]:
            raise RecoveryStartupError("RECOVERY_GRAPH_ARTIFACT_APPROVAL_CHANGED")
    transaction = claim["transaction"]
    for record, raw in cache.values():
        payload = record["payload"]
        if "transaction" in payload and payload["transaction"] != transaction:
            raise RecoveryStartupError("RECOVERY_TRANSACTION_CHANGED")
        if "lineage" in payload and payload["lineage"] != binding["lineage"]:
            raise RecoveryStartupError("RECOVERY_LINEAGE_CHANGED")
        if record["clock"] != chain["CLAIM"]["clock"]:
            raise RecoveryStartupError("RECOVERY_BOOT_CLOCK_CHANGED")
        if record["kind"] in {"ORIGINAL", "CLAIM"}:
            if [item["authority"] for item in payload["scope_approvals"]] != ["CA", "EA-INTRADAY", "EA-SWING", "PCP"]:
                raise RecoveryStartupError("RECOVERY_GRAPH_SCOPE_APPROVALS_MISSING")
            for evidence in payload["scope_approvals"]:
                registry.verify(evidence, "SCOPE_APPROVAL", context=chain)
        if record["kind"] == "OWNER_PROOF":
            for evidence in payload["owner_results"]:
                registry.verify(evidence, "OWNER_RESULT", context=chain)
        for field, proof_kind in _EVIDENCE_FIELDS.get(record["kind"], {}).items():
            evidence = payload[field]
            if evidence is not None:
                _verify_chain_evidence(registry,record,field,chain)
    seal, proof, prepared = (chain[k]["payload"] for k in ("SEAL", "OWNER_PROOF", "PREPARED_COMMIT"))
    ack, observed = (chain[k]["payload"] for k in ("ACK", "OBSERVATION"))
    checkpoint = seal["checkpoint"]
    publisher = seal["publisher"]
    for item in (seal, proof, prepared):
        if (item["product_owners"] != "0" or item["accepted_owners"] != "0"
                or item["commit_owners"] != "1" or item["publisher"] != publisher):
            raise RecoveryStartupError("RECOVERY_PUBLISHER_ACCOUNTING_REJECTED")
    if (proof["checkpoint"] != checkpoint or intent["checkpoint"] != checkpoint
            or proof["obligation_heads"] != seal["obligation_heads"]
            or proof["cleanup_heads"] != seal["cleanup_heads"]
            or ack["publisher"] != publisher or ack["recovery_owners"] != "0"
            or ack["release"] != "CONFIRMED" or ack["deadline"] != "WITHIN"
            or ack["predecessor"] != binding["lineage"]["predecessor"]
            or ack["control_challenge"] != claim["control_challenge"]
            or observed["launcher"] != claim["launcher"]
            or not int(ack["publication_complete_ns"]) <= int(ack["released_ns"]) <= int(ack["ack_ns"])
            or not int(ack["ack_ns"]) <= int(observed["received_ns"]) <= int(observed["verified_ns"]) < int(claim["limits"]["stop_deadline_ns"])
            or int(ack["ack_ns"]) >= int(ack["work_deadline_ns"])):
        raise RecoveryStartupError("RECOVERY_COMPLETED_PUBLICATION_REJECTED")
    consumed_at = _validate_child_receipts(chain, historical=historical, budget=budget)
    if not historical:
        if budget is None:
            raise RecoveryStartupError("RECOVERY_LIVE_CLOCK_REQUIRED")
        # Freshness is a live gate through actual consumption. Later READY
        # observation validates that retained consumption instant, allowing
        # the independently bounded fork+120 restoration phase.
        now = budget.now_ns() if consumed_at is None else consumed_at
        for kind in ("OWNER_PROOF", "CERTIFICATE", "PREPARED_COMMIT", "ACK", "OBSERVATION"):
            if not 0 <= now - int(chain[kind]["issued_ns"]) <= 45_000_000_000:
                raise RecoveryStartupError("RECOVERY_PROOF_EXPIRED")
    # The predecessor checkpoint must be sealed after every required cleanup
    # and accepted obligation.  Walking every head prevents omission by alias.
    for kind in ("OBLIGATION", "CLEANUP"):
        for record, raw in by_kind.get(kind, ()):
            payload = record["payload"]
            # Earlier STARTED/ACCEPTED nodes are legitimate immutable history;
            # only heads selected by the complete seal must be terminal.
            head_list = seal["obligation_heads" if kind == "OBLIGATION" else "cleanup_heads"]
            if record_ref(raw) in head_list:
                allowed = {"COMPLETE"} if kind == "OBLIGATION" else {"COMPLETE", "NOT_APPLICABLE"}
                if payload["state"] not in allowed or payload["failure"] is not None:
                    raise RecoveryStartupError("RECOVERY_NONTERMINAL_OWNER_HEAD")
                if int(record["issued_ns"]) > int(seal["sealed_ns"]):
                    raise RecoveryStartupError("RECOVERY_POST_SEAL_PRODUCT_WRITE")
    return chain


def _native_json(raw):
    """Strict native JSON decoding; native blobs retain their own number rules."""
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise RecoveryStartupError("RECOVERY_NATIVE_DUPLICATE_FIELD")
            out[key] = value
        return out
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, TypeError, UnicodeError):
        raise RecoveryStartupError("RECOVERY_NATIVE_BLOB_REJECTED") from None


def decode_native_startup(raw):
    """Materialize the existing native type; no new startup evidence schema."""
    from dataclasses import fields
    from datetime import datetime
    from kronos.intraday.runtime_identity import StartupEvidence, canonical
    value = _native_json(raw)
    if type(value) is not dict or set(value) != {f.name for f in fields(StartupEvidence)}:
        raise RecoveryStartupError("RECOVERY_NATIVE_STARTUP_FIELDS")
    try:
        value["startup_boundary_at"] = datetime.fromisoformat(value["startup_boundary_at"])
        value["loaded_modules"] = tuple(tuple(row) for row in value["loaded_modules"])
        startup = StartupEvidence(**value)
        if canonical(asdict(startup)) != raw:
            raise ValueError
        return startup
    except (ValueError, TypeError, KeyError):
        raise RecoveryStartupError("RECOVERY_NATIVE_STARTUP_REJECTED") from None


def validate_source_inventory_blob(raw):
    """Use StartupCapture's existing complete snapshot list-of-pairs encoding."""
    import re
    from kronos.intraday.runtime_identity import canonical
    value = _native_json(raw)
    if (type(value) is not list or not value or len(value) > 4096
            or any(type(row) is not list or len(row) != 2 or type(row[0]) is not str or type(row[1]) is not str
                   or re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*", row[0]) is None
                   or re.fullmatch(r"[a-f0-9]{64}", row[1]) is None for row in value)):
        raise RecoveryStartupError("RECOVERY_NATIVE_SOURCE_INVENTORY_REJECTED")
    pairs = tuple(tuple(row) for row in value)
    if pairs != tuple(sorted(pairs)) or len(dict(pairs)) != len(pairs) or canonical(pairs) != raw:
        raise RecoveryStartupError("RECOVERY_NATIVE_SOURCE_INVENTORY_REJECTED")
    return pairs


def validate_bootstrap_evidence(payload, registry, context, *, native_raw=None):
    """Closed BOOTSTRAP_IDENTITY native adapter, shared by parent and consumer."""
    from kronos.intraday.runtime_identity import digest
    from kronos.common.failed_fenced_recovery import record_ref
    raw = registry.store.read_blob(payload["startup"]) if native_raw is None else native_raw
    if (type(raw) is not bytes or sha256(raw).hexdigest() != payload["startup"]["hash"]
            or str(len(raw)) != payload["startup"]["bytes"]):
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_STARTUP_BYTES_CHANGED")
    startup = decode_native_startup(raw)
    target_raw = registry.store.read_blob(payload["target"])
    target = registry.codec.decode_proof(target_raw, expected_kind="TARGET_ARTIFACT")["payload"]
    plan = _native_json(registry.store.read_blob(payload["bootstrap_plan"]))
    if (type(plan) is not dict or set(plan) != {"schema", "identity", "source_inventory", "modules", "qualification"}
            or plan["schema"] != "KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0"
            or plan["source_inventory"] != target["source_inventory"]
            or target["bootstrap_plan"] != payload["bootstrap_plan"]
            or payload["loaded_bootstrap"] != plan["modules"]
            or startup.source_revision != target["revision"]
            or startup.source_state != "CLEAN_COMMIT"
            or startup.load_verification != "PINNED_STARTUP_IMPORTS"
            or payload["process"]["pid"] != str(startup.process_id)
            or payload["process"]["runtime"] != sha256(startup.evidence_identity.encode("utf-8")).hexdigest()):
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_NATIVE_BINDING")
    intent_raw = registry.store.resolve(payload["intent"])
    intent = registry.codec.decode(intent_raw, expected_kind="CHILD_INTENT")["payload"]
    claim_raw = registry.store.resolve(intent["claim"])
    claim = registry.codec.decode(claim_raw, expected_kind="CLAIM")["payload"]
    if (payload["parent"] != claim["launcher"] or payload["child_nonce"] != intent["child_nonce"]
            or payload["intent"] != record_ref(intent_raw)
            or payload["target"] != {"identity": payload["target"]["identity"],
                                      "hash": intent["successor_source"]["hash"],
                                      "bytes": intent["successor_source"]["bytes"]}):
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_INTENT_BINDING")
    # The target's native source inventory is already independently pinned and
    # decoded by the closed preparation owner.  Require the exact complete
    # module map, never just the subset imported during startup.
    source_modules = validate_source_inventory_blob(registry.store.read_blob(target["source_inventory"]))
    executing = context.get("executing_bootstrap_modules") if context else None
    observed_process = context.get("observed_child") if context else None
    observed_parent = context.get("observed_parent") if context else None
    if (startup.source_snapshot_digest != digest(source_modules)
            or any(dict(source_modules).get(name) != value for name, value in startup.loaded_modules)
            or executing != tuple((row["name"], row["digest"]) for row in plan["modules"])
            or observed_process != payload["process"] or observed_parent != payload["parent"]):
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_ACTUAL_SOURCE_UNPROVEN")
    return startup


def _verify_inline_bootstrap(registry, evidence, proof_raw, native_raw, process, context):
    """The fixed S bootstrap proof adapter over its still-unpublished bytes."""
    from kronos.common.failed_fenced_recovery import EvidenceRegistry, RecoveryCodec, RecoveryStore
    if (type(registry) is not EvidenceRegistry or type(registry.codec) is not RecoveryCodec
            or type(registry.store) is not RecoveryStore):
        raise RecoveryStartupError("RECOVERY_CHILD_PRODUCER_CONTEXT_REQUIRED")
    proof = registry.codec.decode_proof(proof_raw, "BOOTSTRAP_IDENTITY")
    if registry.proof_evidence(proof_raw) != evidence or proof["issuer"] != process:
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_INLINE_IDENTITY_CHANGED")
    registry._issuer(proof, process, context)
    registry.verify(proof["clock"]["qualification"], "CLOCK_QUALIFICATION")
    registry.verify_blob(proof["payload"]["target"], "TARGET_ARTIFACT")
    validate_bootstrap_evidence(proof["payload"], registry, context, native_raw=native_raw)
    return proof


def validate_platform_evidence(payload, raw, registry, context):
    """Validate the finite retained native Darwin observation parsers.

    Raw observations are produced by the qualified native platform adapter,
    bound by the external proof's authenticated issuer and preparation.  This
    parser never turns a caller's boolean, missing file or absent row into an
    OS observation, and does not repeat historical observations.
    """
    value = _native_json(raw)
    if (type(value) is not dict or value.get("schema") != "KRONOS_DARWIN_KERNEL_OBSERVATION_V1"
            or value.get("adapter") != "DARWIN_KERNEL_V1"
            or value.get("boot_id") != payload["boot_id"]
            or value.get("observed_ns") != payload["observed_ns"]
            or value.get("observer") != payload["observer"]
            or value.get("subject") != payload["subject"]
            or value.get("kind") != payload["kind"]):
        raise RecoveryStartupError("RECOVERY_NATIVE_PLATFORM_BINDING")
    base = {"schema", "adapter", "boot_id", "observed_ns", "observer", "subject", "kind"}
    kind = payload["kind"]
    if kind in {"PROCESS_BIRTH", "PROCESS_EXIT"}:
        if set(value) != base | {"syscall", "return_bytes", "errno", "observed_process"} or value["syscall"] != "proc_pidinfo:PROC_PIDTBSDINFO":
            raise RecoveryStartupError("RECOVERY_NATIVE_PROCESS_PARSER")
        observed = value["observed_process"]
        if kind == "PROCESS_BIRTH":
            valid = value["return_bytes"] == "136" and value["errno"] == "0" and observed == payload["subject"] and payload["result"] == "MATCH"
        else:
            # ESRCH is affirmative kernel absence; PID reuse is distinguished
            # by an actually returned, different kernel birth of the same PID.
            gone = value["return_bytes"] == "0" and value["errno"] == "3" and observed is None
            reused = (value["return_bytes"] == "136" and value["errno"] == "0" and type(observed) is dict
                      and observed["pid"] == payload["subject"]["pid"]
                      and observed["kernel_birth"] != payload["subject"]["kernel_birth"])
            valid = payload["result"] == "EXITED" and (gone or reused)
    elif kind == "CANONICAL_PARENT":
        valid = (set(value) == base | {"kernel_parent_pid", "resolved_image", "signature_exit", "signature_stderr"}
                 and value["kernel_parent_pid"] == payload["subject"]["pid"]
                 and value["resolved_image"] == "/Applications/KRONOS.app/Contents/MacOS/KRONOS"
                 and value["signature_exit"] == "0" and value["signature_stderr"] == ""
                 and payload["result"] == "MATCH")
    elif kind == "LISTENER_ABSENT":
        endpoint = context.get("CLAIM", {}).get("payload", {}).get("endpoint") if context else None
        valid = (set(value) == base | {"executable", "arguments", "exit", "stdout", "stderr", "endpoint"}
                 and endpoint is not None and value["endpoint"] == endpoint
                 and value["executable"] == "/usr/sbin/lsof"
                 and value["arguments"] == ["-nP", "-Fpfn", "-iTCP:" + endpoint["port"], "-sTCP:LISTEN"]
                 and value["exit"] == "1" and value["stdout"] == value["stderr"] == ""
                 and payload["result"] == "ABSENT")
    else:
        valid = False
    if not valid:
        raise RecoveryStartupError("RECOVERY_NATIVE_PLATFORM_REJECTED")
    return value


def validate_restoration_evidence(payload, registry, context):
    """Apply the unchanged native READY/restoration rules to retained outcomes."""
    from kronos.common.runtime_restoration import _swing_restoration_failure
    if payload["result"] != "READY":
        raise RecoveryStartupError("RECOVERY_RESTORATION_BLOCKED")
    startup_raw = registry.store.resolve(payload["startup_context"])
    startup = registry.codec.decode(startup_raw, expected_kind="STARTUP_CONTEXT")["payload"]
    plan = registry.verify(startup["restoration_scope"], "RESTORATION_PLAN", context=context)["payload"]
    rows = payload["owners"]
    if ({(r["owner"], r["contract"]) for r in rows} != {(r["owner"], r["contract"]) for r in plan["owners"]}
            or len(rows) != len(plan["owners"]) or payload["process"] != startup["runtime"]):
        raise RecoveryStartupError("RECOVERY_RESTORATION_ROSTER_CHANGED")
    for row in rows:
        native = _native_json(registry.store.read_blob(row["native"]))
        if row["owner"] in {"SWING_ANALYSIS", "LOCAL_ANALYSIS", "RESEARCH", "NATIVE", "TRADE_WINDOW", "MCX"}:
            values = native.get("startup_restoration_outcomes")
            outcomes = tuple(tuple(x) for x in values) if type(values) is list else None
            if _swing_restoration_failure(outcomes):
                raise RecoveryStartupError("RECOVERY_SWING_RESTORATION_FAILED")
        elif row["owner"] == "WO11":
            if native.get("last_failure") is not None or native.get("restoration_state") not in {"LOADED", "NOT_YET_RUN"}:
                raise RecoveryStartupError("RECOVERY_WO11_RESTORATION_FAILED")
        elif row["owner"] == "WO17":
            if (native.get("restoration_state") not in {"LOADED", "NOT_YET_RUN"}
                    or native.get("failure_stage") is not None or native.get("failure_reason") is not None
                    or (native.get("restoration_state") == "NOT_YET_RUN" and native.get("current_positions") != [])):
                raise RecoveryStartupError("RECOVERY_WO17_RESTORATION_FAILED")
        elif row["owner"] == "WO08":
            historical = (native.get("historical_restoration") == "KRONOS-WO06H-HISTORICAL-RESTORATION/1.0.0"
                          and native.get("acceptance_disposition") == "HISTORICAL_ACCEPTANCE_EXPIRED"
                          and native.get("historical_evidence") == "READABLE" and native.get("collection_authority") == "EXPIRED"
                          and native.get("enabled") is False and native.get("runtime_accepted") is False)
            if (native.get("failure") is not None or "window" not in native
                    or (native["window"] is not None and native.get("runtime_accepted") is not True and not historical)):
                raise RecoveryStartupError("RECOVERY_WO06H_RESTORATION_FAILED")
        else:
            # No dynamically supplied validation function or caller boolean may
            # broaden the native constructor-restoration roster.
            raise RecoveryStartupError("RECOVERY_NATIVE_RESTORATION_UNPROVEN")
    return startup


def validate_external_native_proof(proof, registry, context):
    """Fixed evidence-registry dispatch, never an executable field in evidence."""
    kind, payload = proof["kind"], proof["payload"]
    historical=context.get("historical_validation")
    retained=(type(historical) is _HistoricalRecoveryValidation
              and historical.native_payload(kind,payload,registry))
    if (kind in {"RESTORATION", "ABSENCE"} and proof["role"] == "SUCCESSOR"
            and payload["process"]["pid"] == str(os.getpid()) and not retained):
        witness = getattr(registry, "_successor_runtime", None)
        if type(witness) is not SuccessorReadyEvidence:
            raise RecoveryStartupError("RECOVERY_READY_NATIVE_WITNESS_REQUIRED")
        witness.verify_native_binding()
        if kind == "RESTORATION":
            witness.verify_restoration_witness(payload)
        else:
            witness.verify_absence_witness(payload)
    if kind == "BOOTSTRAP_IDENTITY":
        return validate_bootstrap_evidence(payload, registry, context)
    if kind == "PLATFORM_OBSERVATION":
        return validate_platform_evidence(payload, registry.store.read_blob(payload["raw"]), registry, context)
    if kind == "RESTORATION":
        return validate_restoration_evidence(payload, registry, context)
    if kind == "ABSENCE":
        native = _native_json(registry.store.read_blob(payload["native"]))
        if payload["kind"] == "PROVIDER":
            valid = (native.get("capability_state") == "ABSENT" and native.get("cleanup_state") == "COMPLETE"
                     and all(type(native.get(key)) is int and native[key] == 0
                             for key in ("owned_work_count", "retained_lease_count", "unresolved_cleanup_count")))
        else:
            valid = (all(type(native.get(key)) is int and native[key] == 0
                         for key in ("session_count", "active_session_count", "owner_count", "subscription_count"))
                     and native.get("transport_cleanup", {}).get("state") == "COMPLETE")
        if not valid:
            raise RecoveryStartupError("RECOVERY_NATIVE_ABSENCE_UNPROVEN")
        return native
    if kind == "COMPATIBILITY":
        from .failed_fenced_compatibility import validate_compatibility_evidence
        return validate_compatibility_evidence(proof, registry, context)
    raise RecoveryStartupError("RECOVERY_NATIVE_VALIDATOR_UNSUPPORTED")


def _guard_context(codec, store, registry, slot):
    """Every retained slot keeps its original key, clock and attributable pin."""
    from .failed_fenced_recovery import (RecoveryCodec, NativeVerifiedCodec,
        EvidenceRegistry, decode_canonical, load_native_preparation, slot_key)
    raw=store.read_reservation(slot,"claim")
    hinted=decode_canonical(raw)
    if (type(hinted) is not dict or hinted.get("kind")!="CLAIM"
            or type(hinted.get("payload")) is not dict):
        raise RecoveryStartupError("RECOVERY_GUARD_CLAIM_REQUIRED")
    if (hinted.get("key_id")==codec.key_id and hinted.get("clock")==codec.clock
            and hinted["payload"].get("transaction")==registry.preparation.record["attempt"]):
        selected_codec,selected_registry=codec,registry
    else:
        selected_codec=(codec.for_historical_claim(store,raw) if type(codec) is NativeVerifiedCodec
            else RecoveryCodec(store.read_custody(hinted["key_id"]),hinted["clock"]))
        claim=selected_codec.decode(raw,"CLAIM")["payload"]
        preparation=load_native_preparation(store,controller=claim["launcher"],mode="RECOVERY",
            lineage=claim["binding"]["lineage"],attempt=claim["transaction"])
        selected_registry=EvidenceRegistry(selected_codec,store,preparation)
    claim=selected_codec.decode(raw,"CLAIM")["payload"]
    if claim["slot"]!=slot or slot_key(claim["binding"]["lineage"])!=slot:
        raise RecoveryStartupError("RECOVERY_GUARD_SLOT_CHANGED")
    return selected_codec,selected_registry


def _guard_ready_candidates(store, slot, budget):
    from .failed_fenced_recovery import decode_canonical
    directory=store._dir(("records",))
    try:names=sorted(os.listdir(directory))
    finally:os.close(directory)
    if len(names)>4096:
        raise RecoveryStartupError("RECOVERY_GUARD_RECORD_BOUND")
    candidates=[]
    for name in names:
        budget.check()
        if not name.startswith("READY_RECEIPT-") or not name.endswith(".json"):
            continue
        raw=store._read(("records",),name)
        if name!="READY_RECEIPT-"+sha256(raw).hexdigest()+".json":
            raise RecoveryStartupError("RECOVERY_GUARD_READY_FILENAME")
        value=decode_canonical(raw)
        # A slot hint narrows candidate bytes only. The selected historical
        # codec and complete graph independently authenticate every match.
        if type(value) is dict and type(value.get("payload")) is dict and value["payload"].get("slot")==slot:
            candidates.append(raw)
    if len(candidates)>1:
        raise RecoveryStartupError("RECOVERY_AMBIGUOUS_GUARD_RESOLUTION")
    return candidates


def guard_admission(*, codec, store, registry, applicability, budget, recovery_slot=None):
    """Both launcher and consumer independently validate every original guard."""
    proof=registry.verify(applicability,"GUARD_APPLICABILITY")
    if proof["payload"]["classification"]=="LEGACY_UNENROLLED":
        if store.root.exists():
            raise RecoveryStartupError("RECOVERY_LEGACY_NAMESPACE_CONFLICT")
        if recovery_slot is not None:
            raise RecoveryStartupError("RECOVERY_LEGACY_HAS_NO_RECOVERY_AUTHORITY")
        return ()
    unresolved=[]
    for slot in store.enumerate_guards():
        budget.check()
        selected_codec,selected_registry=_guard_context(codec,store,registry,slot)
        candidates=_guard_ready_candidates(store,slot,budget)
        if not candidates:
            unresolved.append(slot)
            continue
        validate_recovery_chain(selected_codec,store,selected_registry,candidates[0],slot=slot,
                                budget=budget,historical=True)
    if unresolved and (recovery_slot is None or unresolved!=[recovery_slot]):
        raise RecoveryStartupError("RECOVERY_UNRESOLVED_GUARD")
    if recovery_slot is not None and recovery_slot not in unresolved:
        raise RecoveryStartupError("RECOVERY_RESOLVED_OR_UNKNOWN_SLOT_REUSE")
    return tuple(unresolved)


@dataclass(frozen=True, slots=True)
class PreparedStartupAuthority:
    """Source-owned injection boundary for approved preparation, not env data.

    Operational preparation instances are supplied by the approved canonical
    installation/controller.  This class does not create an approval, provision
    a guard estate, choose an arbitrary catalogue, or repair missing inputs.
    """
    codec: object
    store: object
    registry: object
    budget: object
    applicability: dict
    native_context: dict

    def verify(self, environment):
        from kronos.common.failed_fenced_recovery import (
            EvidenceRegistry, PreparationContext, RecoveryBudget, RecoveryCodec, RecoveryStore,
        )
        if (type(self.codec) is not RecoveryCodec or type(self.store) is not RecoveryStore
                or type(self.registry) is not EvidenceRegistry or type(self.budget) is not RecoveryBudget
                or type(self.registry.preparation) is not PreparationContext
                or self.registry.codec is not self.codec or self.registry.store is not self.store):
            raise RecoveryStartupError("RECOVERY_PREPARED_STARTUP_AUTHORITY_REQUIRED")
        selection = selectors(environment)
        if selection is None:
            with self.store.service_lock(self.budget):
                guard_admission(codec=self.codec, store=self.store, registry=self.registry,
                                applicability=self.applicability, budget=self.budget)
        else:
            # The actual canonical C parent owns the service lock through its
            # sole fork/grant. The child independently reads immutable guards;
            # acquiring C's lock here would deadlock its bootstrap publication.
            guard_admission(codec=self.codec, store=self.store, registry=self.registry,
                            applicability=self.applicability, budget=self.budget,
                            recovery_slot=selection[0])
        self.budget.check()
        return selection

    def child_session(self, environment, native):
        selection = self.verify(environment)
        if selection is None:
            return None
        slot, nonce = selection
        intent_raw = self.store.read_reservation(slot, "child-intent")
        with self.registry._composition_validation(self.budget.check):
            chain = validate_recovery_chain(self.codec, self.store, self.registry, intent_raw,
                                            slot=slot, budget=self.budget, native_context=self.native_context)
        if chain["CHILD_INTENT"]["payload"]["child_nonce"] != nonce:
            raise RecoveryStartupError("RECOVERY_CHILD_NONCE_CHANGED")
        chain.update(self.native_context)
        from tools.runtime_source_gate import canonical_parent
        return BootstrapSession(codec=self.codec, store=self.store, registry=self.registry,
                                budget=self.budget, chain=chain, native=native,
                                parent=chain["CLAIM"]["payload"]["launcher"],
                                canonical_parent_check=lambda: canonical_parent(budget=self.budget))


@dataclass(frozen=True, slots=True)
class PreparedChildStartup:
    """Canonical loader's typed inputs; none may be deserialized from env/HTTP.

    The canonical pinned loader independently establishes executing module and
    actual kernel process observations before constructing this object. Missing
    operational preparation is a denial, never a self-issued approval.
    """
    authority: PreparedStartupAuthority
    native: NativeBootstrap
    bootstrap_evidence: dict
    bootstrap_raw: bytes
    native_raw: bytes
    checkpoint: dict
    restoration_scope: dict

    def enter(self, environment, startup, inherited_budget):
        from kronos.common.failed_fenced_recovery import record_ref
        from tools.runtime_source_gate import native_boot_id
        if (type(self.authority) is not PreparedStartupAuthority or type(self.native) is not NativeBootstrap
                or self.native.startup is not startup or inherited_budget is None):
            raise RecoveryStartupError("RECOVERY_CANONICAL_CHILD_PREPARATION_REQUIRED")
        budget = self.authority.budget
        if (budget.clock['boot_id'] != native_boot_id()
            or budget.clock != inherited_budget.clock or budget.origin_ns != inherited_budget.origin_ns
                or budget.stop_deadline_ns != inherited_budget.stop_deadline_ns):
            raise RecoveryStartupError("RECOVERY_INHERITED_BUDGET_CHANGED")
        session = self.authority.child_session(environment, self.native)
        if session is None or record_ref(session.chain["CLAIM_RAW"])["hash"] != inherited_budget.claim_hash or record_ref(session.chain["CHILD_INTENT_RAW"])["hash"] != inherited_budget.intent_hash:
            raise RecoveryStartupError("RECOVERY_INHERITED_TRANSACTION_CHANGED")
        session.publish_identity(self.bootstrap_evidence, self.bootstrap_raw, self.native_raw)
        session.receive_authority()
        context = session.consume(bootstrap_evidence=self.bootstrap_evidence,
                                  checkpoint=self.checkpoint, restoration_scope=self.restoration_scope)
        return session, context


@dataclass(frozen=True, slots=True)
class ProspectiveRuntimeStartup:
    """Actual source-owned pre-construction composition and ownership context."""
    ledger: object
    composition: object
    restart_control: object
    binding: object | None = None
    original_binding: object | None = None
    factory: object | None = None

    def validate(self, startup):
        from kronos.common.failed_fenced_recovery import ProspectiveLedger
        from kronos.application.failed_fenced_owners import ProspectiveComposition
        from kronos.browser.restart_control import BrowserBackendRestartControl
        from kronos.browser.failed_fenced_control import RecoveryBrowserBinding, OriginalBrowserBinding
        if (type(self.ledger) is not ProspectiveLedger or type(self.composition) is not ProspectiveComposition
                or self.composition.ledger is not self.ledger
                or type(self.restart_control) is not BrowserBackendRestartControl
                or not self.restart_control.owns_current_process()
                or self.ledger.process["pid"] != str(startup.process_id)
                or self.ledger.process["runtime"] != sha256(startup.evidence_identity.encode("utf-8")).hexdigest()
                or self.ledger.coordinator.snapshot()["state"] != "OPEN"
                or self.ledger.inventory is not None
                or (self.binding is not None and (type(self.binding) is not RecoveryBrowserBinding or self.binding.ledger is not self.ledger))
                or (self.original_binding is not None and (type(self.original_binding) is not OriginalBrowserBinding
                    or self.original_binding.ledger is not self.ledger))):
            raise RecoveryStartupError("RECOVERY_PROSPECTIVE_RUNTIME_REQUIRED")
        return self

    def activate(self, startup):
        self.validate(startup)
        # Context remains active across every real constructor and attachment.
        # Owners declare their source branches; no post-failure census exists.
        self.ledger.native_composition = self.composition
        return self.ledger.activate()

    def complete_construction(self, server):
        if server._failed_fenced_ledger is not self.ledger:
            raise RecoveryStartupError("RECOVERY_COMPOSITION_COORDINATOR_CHANGED")
        # This is deliberately strict. An unwitnessed owner is not absent.
        result = self.composition.publish()
        if self.factory is not None:
            capture_runtime_facts(self, server)
        if self.original_binding is not None:
            server.bind_failed_fenced_original(self.original_binding)
        if self.binding is not None:
            server.bind_failed_fenced_recovery(self.binding)
        return result


def validate_original_reservation(reservation_raw, permission_raw, authority, prepared_binding):
    """Existing FAILED_ACTIVE launcher's immutable attempt byte format only.

    Ordinary prospective RESERVE_ORIGINAL uses the separately specified closed
    CONTROLLER_ADMISSION proof and is validated by the registry itself.
    """
    import re
    if authority["kind"] != "FAILED_ACTIVE":
        raise RecoveryStartupError("RECOVERY_NATIVE_ORIGINAL_RESERVATION_UNSUPPORTED")
    reservation = _native_json(reservation_raw)
    permission = _native_json(permission_raw)
    fields = {"schema", "attempt", "authorization_sha256", "generation", "predecessor_pid",
              "predecessor_revision", "successor_revision", "reserved_at_us"}
    if (type(reservation) is not dict or set(reservation) != fields
            or reservation["schema"] != "KRONOS-FAILED-ACTIVE-RECOVERY-ATTEMPT/1.0.0"
            or reservation["attempt"] != prepared_binding["attempt"]
            or reservation["generation"] != authority["generation"]
            or type(reservation["predecessor_pid"]) is not int
            or str(reservation["predecessor_pid"]) != authority["process"]["pid"]
            or reservation["authorization_sha256"] != sha256(permission_raw).hexdigest()
            or type(reservation["reserved_at_us"]) is not int
            or any(type(reservation[k]) is not str or re.fullmatch(r"[0-9a-f]{40}", reservation[k]) is None
                   for k in ("predecessor_revision", "successor_revision"))):
        raise RecoveryStartupError("RECOVERY_NATIVE_ORIGINAL_RESERVATION_REJECTED")
    expected = ('{"schema":"KRONOS-FAILED-ACTIVE-RECOVERY-ATTEMPT/1.0.0",'
        '"attempt":"%s","authorization_sha256":"%s","generation":"%s",'
        '"predecessor_pid":%d,"predecessor_revision":"%s","successor_revision":"%s","reserved_at_us":%d}\n') % tuple(reservation[k] for k in ("attempt", "authorization_sha256", "generation", "predecessor_pid", "predecessor_revision", "successor_revision", "reserved_at_us"))
    if (expected.encode("ascii") != reservation_raw
            or type(permission) is not dict
            or permission.get("attempt_identity") != reservation["attempt"]
            or permission.get("predecessor_pid") != reservation["predecessor_pid"]
            or permission.get("predecessor_revision") != reservation["predecessor_revision"]
            or permission.get("successor_revision") != reservation["successor_revision"]
            or type(permission.get("valid_from_us")) is not int or type(permission.get("valid_until_us")) is not int
            or not permission["valid_from_us"] <= reservation["reserved_at_us"] < permission["valid_until_us"]):
        raise RecoveryStartupError("RECOVERY_NATIVE_ORIGINAL_PERMISSION_CHANGED")
    return reservation


@dataclass(frozen=True, slots=True)
class PreparedCaptureInstallation:
    """Static installation verification for factual capture, not an operation.

    This internal value contains only existing approved records. It grants no
    maintenance generation, recovery authority, controller right or child grant.
    """
    codec: object
    store: object
    registry: object
    budget: object
    applicability: dict
    startup: object
    parent: dict

    def verify(self, environment):
        from tools.runtime_source_gate import native_boot_id, canonical_parent_identity
        if selectors(environment) is not None or self.codec.clock['boot_id'] != native_boot_id():
            raise RecoveryStartupError("RECOVERY_CAPTURE_INSTALLATION_CHANGED")
        if canonical_parent_identity(budget=self.budget) != self.parent:
            raise RecoveryStartupError("RECOVERY_CAPTURE_PARENT_CHANGED")
        # The actual canonical C parent retains the service lock across this
        # ordinary entry. This child only revalidates immutable publications;
        # reacquiring the same lock would block its parent's readiness wait.
        _verify_installation_guards(self.store, self.budget)
        self.registry.verify(self.applicability, "GUARD_APPLICABILITY")
        self.budget.check()
        return None


def _verify_installation_guards(store, budget):
    """Resolve every existing guard with its own historical key/preparation."""
    from kronos.common.failed_fenced_recovery import (RecoveryCodec, EvidenceRegistry,
        decode_canonical, load_native_preparation)
    for slot in store.enumerate_guards():
        budget.check()
        raw=store.read_reservation(slot,"claim")
        hint=decode_canonical(raw)
        codec=RecoveryCodec(store.read_custody(hint["key_id"]),hint["clock"])
        claim=codec.decode(raw,"CLAIM")["payload"]
        prep=load_native_preparation(store,controller=claim["launcher"],mode="RECOVERY",
            lineage=claim["binding"]["lineage"],attempt=claim["transaction"])
        registry=EvidenceRegistry(codec,store,prep)
        codec,registry=_guard_context(codec,store,registry,slot)
        candidates=_guard_ready_candidates(store,slot,budget)
        if not candidates:
            raise RecoveryStartupError("RECOVERY_UNRESOLVED_GUARD")
        validate_recovery_chain(codec,store,registry,candidates[0],slot=slot,
                                budget=budget,historical=True)
        budget.check()


def load_capture_installation(startup, *, origin_ns):
    """Fixed ordinary capable-entry acquisition before all owner construction.

    Static guard/source/scope approvals may be retained across operations; their
    selection is by this actual installation and executing source, never a future
    generation or a caller catalogue. Later ORIGINAL attachment is still required.
    """
    from kronos.common.failed_fenced_recovery import (RecoveryStore, StaticPreparationCodec,
        RecoveryBudget, EvidenceRegistry, _fixed_preparation_entries, load_native_preparation,
        decode_canonical, SCOPE_HASH, SCOPE_BYTES, PROTOCOL, VERSION)
    from tools.runtime_source_gate import native_boot_id, canonical_parent_identity, fixed_native_estate
    from kronos.intraday.runtime_identity import StartupEvidence
    if type(startup) is not StartupEvidence or startup.process_id != os.getpid():
        raise RecoveryStartupError('RECOVERY_CAPTURE_STARTUP_REQUIRED')
    replace(startup)
    store = RecoveryStore(fixed_native_estate())
    boot = native_boot_id()
    entries = _fixed_preparation_entries(store)
    selected = {}
    for selector, _pinraw, _approvalraw, _pin, _approval, record in entries:
        if record['clock']['boot_id'] != boot:
            continue
        budget = RecoveryBudget(record['clock'], origin_ns, origin_ns + 15_000_000_000)
        budget.check()
        prep = load_native_preparation(store, controller=record['controller'], mode=record['mode'],
            lineage=record['lineage'], attempt=record['attempt'])
        codec = StaticPreparationCodec.from_preparation(prep)
        registry = EvidenceRegistry(codec, store, prep)
        registry.verify(codec.clock['qualification'], 'CLOCK_QUALIFICATION')
        parent = canonical_parent_identity(budget=budget)
        from tools.macos import package_launcher
        from tools.runtime_source_gate import CANONICAL
        actual_package=package_launcher.canonical(package_launcher.manifest(CANONICAL,budget=budget))
        if (sha256(actual_package).hexdigest()!=record['launcher_package']['hash']
                or store.read_blob(record['launcher_package'])!=actual_package):
            continue
        for row in prep.rows.values():
            if row['purpose'] != 'GUARD' or row['authority'] != 'CA':
                continue
            binding = row['bindings']
            inventory = store.read_blob(binding['source_inventory'])
            if (sha256(inventory).hexdigest() != startup.source_snapshot_digest
                    or binding['launcher']['hash'] != parent['runtime']):
                continue
            modules = validate_source_inventory_blob(inventory)
            loaded = _actual_ready_modules(startup, modules, budget)
            backend = dict(loaded).get('tools.kronos_browser')
            if binding['backend']['hash'] != backend:
                continue
            root_raw = store.read_blob(row['artifact'])
            root = decode_canonical(root_raw)
            if root.get('kind') != 'GUARD_APPLICABILITY':
                continue
            applicability = registry.proof_evidence(root_raw)
            registry.verify(applicability, 'GUARD_APPLICABILITY')
            artifacts = [item for item in prep.rows.values() if item['purpose'] == 'ARTIFACT'
                and item['authority'] == 'CA' and item['bindings']['revision'] == startup.source_revision
                and item['bindings']['source_inventory'] == binding['source_inventory']
                and item['bindings']['package'] == record['launcher_package']]
            if len(artifacts) != 1 or root['payload']['classification'] != 'MANDATORY':
                raise RecoveryStartupError('RECOVERY_CAPTURE_SOURCE_APPROVAL_AMBIGUOUS')
            scope = {'authority':'CA','contract':PROTOCOL+':'+VERSION,
                'identity':'FAILED_FENCED_INITIAL_OWNER_SCOPE_V1','hash':SCOPE_HASH,'bytes':SCOPE_BYTES}
            registry.verify(scope, 'SCOPE')
            key = (applicability['hash'], binding['source_inventory']['hash'], codec.clock['boot_id'])
            authority = PreparedCaptureInstallation(codec, store, registry, budget, applicability, startup, parent)
            selected[key] = PreparedRuntimeFactory(authority, scope, binding['source_inventory'])
    if len(selected) != 1:
        raise RecoveryStartupError('RECOVERY_CAPTURE_PREPARATION_MISSING_OR_AMBIGUOUS')
    factory = next(iter(selected.values()))
    factory.authority.verify({})
    return factory


@dataclass(frozen=True, slots=True)
class PreparedRuntimeFactory:
    """Canonical pre-construction factory for an enrolled successor process.

    Static installation preparation is independently verified before entry.
    A recovery child's new process-control bytes are created only after its old
    custody transaction has a durable consumption receipt. Prospective facts
    here confer no operational ORIGINAL or RECOVERY authorization.
    """
    authority: PreparedStartupAuthority
    scope: dict
    source_inventory: dict

    def construct(self, startup, child_session=None):
        import ctypes
        import secrets
        from kronos.common.failed_fenced_recovery import RecoveryCodec, ProspectiveLedger
        from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
        from kronos.application.failed_fenced_owners import ProspectiveComposition, initialize_canonical_roster
        from kronos.browser.restart_control import BrowserBackendRestartControl
        from tools.runtime_source_gate import fixed_native_estate
        from tools.failed_fenced_launcher import _ProcBSDInfo
        if type(self.authority) not in {PreparedStartupAuthority, PreparedCaptureInstallation} or startup.process_id != os.getpid():
            raise RecoveryStartupError("RECOVERY_CANONICAL_RUNTIME_FACTORY_REQUIRED")
        if child_session is None:
            if type(self.authority) is PreparedCaptureInstallation and self.authority.startup is not startup:
                raise RecoveryStartupError("RECOVERY_CAPTURE_STARTUP_CHANGED")
            self.authority.verify(os.environ)
        elif (type(child_session) is not BootstrapSession or not child_session._consumed
                or type(getattr(child_session, "consumption_raw", None)) is not bytes
                or type(getattr(child_session, "startup_context_raw", None)) is not bytes
                or type(child_session.latch) is not CompositionLatch or not child_session.latch._spent):
            raise RecoveryStartupError("RECOVERY_DURABLE_CONSUMPTION_REQUIRED")
        else:
            child_session.ready_budget.check()
        raw_inventory = self.authority.store.read_blob(self.source_inventory)
        validate_source_inventory_blob(raw_inventory)
        if sha256(raw_inventory).hexdigest() != startup.source_snapshot_digest:
            raise RecoveryStartupError("RECOVERY_RUNTIME_SOURCE_INVENTORY_CHANGED")
        if __import__("sys").platform != "darwin" or ctypes.sizeof(_ProcBSDInfo) != 136:
            raise RecoveryStartupError("RECOVERY_DARWIN_PLATFORM_REQUIRED")
        lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        lib.proc_pidinfo.restype = ctypes.c_int
        info = _ProcBSDInfo()
        if lib.proc_pidinfo(os.getpid(), 3, 0, ctypes.byref(info), ctypes.sizeof(info)) != ctypes.sizeof(info) or info.pid != os.getpid():
            raise RecoveryStartupError("RECOVERY_NATIVE_PROCESS_BIRTH_REQUIRED")
        process = {"pid": str(os.getpid()), "kernel_birth": {"seconds": str(info.start_seconds),
            "microseconds": str(info.start_microseconds)},
            "runtime": sha256(startup.evidence_identity.encode("utf-8")).hexdigest()}
        token = secrets.token_hex(32)
        private = ("KRONOS_BROWSER_BACKEND_CONTROL_V1\n" + str(os.getpid()) + "\n" + token + "\n").encode("ascii")
        codec = RecoveryCodec(private, self.authority.codec.clock)
        coordinator = MaintenanceAdmissionCoordinator()
        startup_ticket = coordinator.admit("SPONSOR_RESTORATION")
        ledger = ProspectiveLedger.capture(coordinator, codec, self.authority.store, process, self.scope)
        ledger.native_startup = startup
        ledger.native_process = process
        composition = ProspectiveComposition(ledger, self.source_inventory, self.scope)
        initialize_canonical_roster(composition)
        ledger.native_composition = composition
        with ledger.activate(), startup_ticket.activate():
            # This exact real construction call is prospectively registered by
            # the existing CONTROL hook before its private file publication.
            control = BrowserBackendRestartControl.create(fixed_native_estate()/'browser-backend-v1.control', token=token)
            if not codec.matches_control(control.private_bytes_for_recovery()):
                raise RecoveryStartupError("RECOVERY_NEW_CONTROL_READBACK_CHANGED")
            # Only the later counted original C controller checkpoints custody.
            # This process retains its own codec in memory; startup grants no
            # original reservation, controller ownership or custody publication.
        ledger.native_parent = (self.authority.parent if type(self.authority) is PreparedCaptureInstallation
            else child_session.parent if child_session is not None else None)
        result = ProspectiveRuntimeStartup(ledger, composition, control, factory=self)
        ledger._canonical_startup_ticket = startup_ticket
        return result



_RECOVERY_OPERATION_MODULES = (
    ("ACCOUNTING", "kronos.common.maintenance_admission"),
    ("CLEANUP_JOURNAL", "kronos.common.failed_fenced_recovery"),
    ("GUARD_ADMISSION", "kronos.common.failed_fenced_startup"),
    ("ORIGINAL_CONTROLLER_CLOSURE", "kronos.browser.failed_fenced_control"),
    ("PRE_EFFECT_OBLIGATIONS", "kronos.application.failed_fenced_owners"),
    ("RECOVERY_PROTOCOL", "kronos.common.failed_fenced_recovery"),
    ("WRITE_FREE_TAIL", "kronos.browser.failed_fenced_control"),
)


def recovery_operation_manifest(source_modules):
    """Closed source-owned operations, distinct from analytical capabilities.

    Every row is implemented by a fixed qualified loaded module. The complete
    ARTIFACT source inventory supplies its digest; neither a target declaration
    nor request data may choose another operation, module, or contract.
    """
    inventory = dict(source_modules)
    if any(module not in inventory for _, module in _RECOVERY_OPERATION_MODULES):
        raise RecoveryStartupError("RECOVERY_OPERATION_SOURCE_INCOMPLETE")
    return [{"operation":operation,"module":module,"digest":inventory[module],
             "contract":"KRONOS_FAILED_FENCED_RECOVERY_V1"}
            for operation,module in _RECOVERY_OPERATION_MODULES]


def _verify_target_declarations(manifest, store, target):
    from .failed_fenced_compatibility import verify_target_runtime_manifest
    return verify_target_runtime_manifest(manifest,store.read_blob(target['capability_manifest']),
        target,store.read_blob(target['source_inventory']))

def capture_runtime_facts(runtime, server):
    """Capture source/capability/endpoint facts, before original C custody."""
    from kronos.common.failed_fenced_recovery import canonical_bytes, _as_blob
    from kronos.intraday.runtime_identity import canonical
    ledger, factory = runtime.ledger, runtime.factory
    if type(factory) is not PreparedRuntimeFactory or hasattr(ledger, 'prospective_source'):
        raise RecoveryStartupError('RECOVERY_PROSPECTIVE_FACT_CAPTURE_ONCE')
    startup, manifest = ledger.native_startup, ledger.native_runtime_manifest
    prep = factory.authority.registry.preparation
    artifacts = [row for row in prep.rows.values() if row['authority']=='CA' and row['purpose']=='ARTIFACT'
        and row['bindings']['revision']==startup.source_revision
        and row['bindings']['source_inventory']==factory.source_inventory
        and row['bindings']['package']==prep.record['launcher_package']]
    tails = [row for row in prep.rows.values() if row['authority']=='CA' and row['purpose']=='TAIL'
        and row['bindings']['source_inventory']==factory.source_inventory]
    if len(artifacts)!=1 or len(tails)!=1 or ledger.native_parent is None:
        raise RecoveryStartupError('RECOVERY_PROSPECTIVE_ARTIFACT_FACTS_REQUIRED')
    artifact, tail = artifacts[0], tails[0]
    if not any(row['authority']=='PCP' and row['purpose']=='TAIL' and row['bindings']==tail['bindings'] for row in prep.rows.values()):
        raise RecoveryStartupError('RECOVERY_PROSPECTIVE_TAIL_APPROVAL_REQUIRED')
    prefix='runtime-'+ledger.process['runtime']
    start=ledger.retain_native(prefix+'-startup',canonical(asdict(startup)))
    runtime_manifest=ledger.retain_native(prefix+'-manifest',canonical(asdict(manifest)))
    parent=ledger.retain_native(prefix+'-parent',canonical_bytes(ledger.native_parent))
    source_payload={'identity':prefix+'-source','process':ledger.process,'revision':startup.source_revision,
        'repository':prep.record['installation'],'startup':start,'runtime_manifest':runtime_manifest,
        'source_inventory':factory.source_inventory,'canonical_parent':parent,'publication':start,
        'package':artifact['bindings']['package'],'verified_ns':str(ledger.now_ns())}
    source=ledger.publish_proof('SOURCE',source_payload)
    modules=validate_source_inventory_blob(ledger.store.read_blob(factory.source_inventory))
    _verify_target_declarations(manifest,ledger.store,artifact['bindings'])
    operations=recovery_operation_manifest(modules)
    operation_blob=ledger.retain_native(prefix+'-recovery-operations',canonical_bytes(operations))
    # The actual loaders independently supply the executing module set. A
    # reviewed manifest alone never attests that these bytes ran.
    budget=(factory.authority.budget if not hasattr(server,'_failed_fenced_child_session')
            else server._failed_fenced_child_session.ready_budget)
    # Load each finite implementation through the retained qualified finder
    # before claiming its capability. Lazy original-controller modules must not
    # be certified merely because their expected bytes appear in an inventory.
    import importlib
    for module in sorted({module for _,module in _RECOVERY_OPERATION_MODULES}):
        budget.check()
        importlib.import_module(module)
    actual=dict(_actual_ready_modules(startup,modules,budget))
    if (type(operations) is not list or not operations or len(operations)>4096
            or any(type(row) is not dict or set(row)!={'operation','module','digest','contract'}
                   or actual.get(row['module'])!=row['digest'] for row in operations)
            or [row['operation'] for row in operations]!=sorted({row['operation'] for row in operations})):
        raise RecoveryStartupError('RECOVERY_PROSPECTIVE_OPERATION_BYTES_CHANGED')
    capability={'identity':prefix+'-capability','process':ledger.process,'source':_as_blob(source),
        'capability':'FAILED_FENCED_RECOVERY_V1','implementation':artifact['bindings']['capability_manifest'],
        'owner_scope':_as_blob(ledger.scope),'operation_manifest':operation_blob,
        'tail_plan':tail['bindings']['callgraph'],'qualified_artifact':artifact['identity']}
    ledger.native_capability_payload=capability
    cap=ledger.publish_proof('CAPABILITY',capability)
    control_bytes=runtime.restart_control.private_bytes_for_recovery()
    if not ledger.codec.matches_control(control_bytes):
        raise RecoveryStartupError('RECOVERY_PROSPECTIVE_CONTROL_CHANGED')
    address=server.socket.getsockname()
    configuration=_native_json(ledger.store.read_blob(artifact['bindings']['configuration']))
    if (len(address)!=2 or address[0]!='127.0.0.1' or address[1]!=server.server_port
            or type(configuration) is not dict or configuration.get('browser_port')!=address[1]):
        raise RecoveryStartupError('RECOVERY_PROSPECTIVE_ENDPOINT_CHANGED')
    descriptor=os.fstat(server.socket.fileno())
    listener=ledger.retain_native(prefix+'-listener',canonical_bytes({'process':ledger.process,
        'host':address[0],'port':str(address[1]),'device':str(descriptor.st_dev),'inode':str(descriptor.st_ino)}))
    endpoint={'identity':prefix+'-endpoint','service':prep.record['service'],'process':ledger.process,
        'host':address[0],'port':str(address[1]),'configuration':artifact['bindings']['configuration'],
        'source':_as_blob(source),'listener':listener}
    ledger.native_endpoint_payload,ledger.native_server=endpoint,server
    endpoint_evidence=ledger.publish_proof('ENDPOINT_CONFIGURATION',endpoint)
    ledger.prospective_source,ledger.prospective_capability=source,cap
    ledger.prospective_endpoint=endpoint_evidence
    # CONTROL_BINDING truthfully requires the later original controller's raw
    # checkpoint. Only the existing admitted pulse may complete it; startup
    # neither creates custody nor asserts that a future checkpoint exists.
    ledger._prospective_control_runtime=runtime
    ledger._prospective_control_state='WAITING'
    return source,cap,endpoint_evidence


def complete_prospective_control(server):
    """Once-only control proof after actual C retention, on SERVER_PULSE.

    Absence before the checkpoint exists is not a publication attempt. Once a
    named checkpoint is observed, a missing/partial/changed checkpoint or an
    unknown proof-publication outcome permanently denies this capture.
    """
    from kronos.common.failed_fenced_recovery import ProspectiveLedger
    ledger=getattr(server,'_failed_fenced_ledger',None)
    if ledger is None or not hasattr(ledger,'_prospective_control_runtime'):
        return None
    if type(ledger) is not ProspectiveLedger:
        raise RecoveryStartupError('RECOVERY_PROSPECTIVE_CONTROL_LEDGER_REQUIRED')
    with ledger._lock:
        state=ledger._prospective_control_state
        if state=='COMPLETE':
            return ledger.prospective_control
        if state!='WAITING':
            raise RecoveryStartupError('RECOVERY_PROSPECTIVE_CONTROL_ATTEMPT_SPENT')
        ticket=ledger.current_ticket()
        if (ticket is None or ticket.kind!='SERVER_PULSE'
                or ledger.coordinator.snapshot()['state']!='OPEN'):
            raise RecoveryStartupError('RECOVERY_PROSPECTIVE_CONTROL_PULSE_REQUIRED')
        try:
            runtime=ledger._prospective_control_runtime
            if (type(runtime) is not ProspectiveRuntimeStartup or runtime.ledger is not ledger
                    or ledger.native_server is not server
                    or server.restart_control is not runtime.restart_control):
                raise RecoveryStartupError('RECOVERY_PROSPECTIVE_CONTROL_RUNTIME_CHANGED')
            # Inspect only the exact fixed name in an independently checked
            # private directory. No missing directory, symlink or corrupt file
            # is treated as a not-yet-created checkpoint.
            directory=ledger.store._dir(('custody',))
            try:
                try:os.stat(ledger.codec.key_id+'.control',dir_fd=directory,follow_symlinks=False)
                except FileNotFoundError:return None
            finally:os.close(directory)
            ledger._prospective_control_state='STARTED'
            private=runtime.restart_control.private_bytes_for_recovery()
            retained=ledger.store.read_custody(ledger.codec.key_id)
            if (not runtime.restart_control.owns_current_process()
                    or not ledger.codec.matches_control(private)
                    or not ledger.codec.matches_control(retained)):
                raise RecoveryStartupError('RECOVERY_PROSPECTIVE_CONTROL_CHANGED')
            prefix='runtime-'+ledger.process['runtime']
            descriptor={'identity':prefix+'-private-control','hash':ledger.codec.key_id,'bytes':str(len(private))}
            payload={'identity':prefix+'-control','process':ledger.process,
                'live_control':descriptor,'retained_control':dict(descriptor),
                'schema':'KRONOS_BROWSER_BACKEND_CONTROL_V1','boot_id':ledger.codec.clock['boot_id'],
                'verified_ns':str(ledger.now_ns())}
            # The unchanged native validator independently rereads custody.
            proof=ledger.publish_proof('CONTROL_BINDING',payload)
            ledger.prospective_control=proof
            ledger._prospective_control_state='COMPLETE'
            return proof
        except (ValueError,OSError,TypeError,KeyError):
            ledger._prospective_control_state='FAILED'
            # The in-memory negative gate is set before its own durability
            # attempt. Ordinary service remains available; recovery cannot
            # retry or reinterpret an unknown outcome as success/absence.
            try:ledger.mark_ineligible('PROVENANCE')
            except (ValueError,OSError,TypeError,KeyError):pass
            raise



def _interface_evidence(authority, artifact):
    """A typed locator under this interface; pinned bytes supply authority."""
    from .failed_fenced_recovery import PROTOCOL, VERSION, _check_type
    _check_type('Blob',artifact)
    evidence={'authority':authority,'contract':PROTOCOL+':'+VERSION,**artifact}
    _check_type('Evidence',evidence)
    return evidence


def prepare_original_binding(server, generation, deadline_ns):
    """Acquire the later original operation from the fixed private estate.

    No matching preparation preserves ordinary operation without R3 eligibility.
    A matching malformed, stale, ambiguous or incomplete preparation denies. The
    backend does not supply an authority root, controller identity or deadline.
    """
    import re
    from kronos.common.failed_fenced_recovery import (ProspectiveLedger, EvidenceRegistry,
        RecoveryBudget, MAX_RECORD, _fixed_preparation_entries, load_native_preparation,
        decode_canonical, record_ref, _as_blob, _verify_scope_approvals)
    from kronos.browser.failed_fenced_control import OriginalBrowserBinding
    from tools.runtime_source_gate import canonical_controller_identity, native_boot_id
    ledger = getattr(server, '_failed_fenced_ledger', None)
    if ledger is None:
        return None
    if type(ledger) is not ProspectiveLedger or ledger.coordinator.snapshot()['state'] != 'OPEN':
        raise RecoveryStartupError('RECOVERY_ORIGINAL_CAPTURE_REQUIRED')
    lineage = {'predecessor': ledger.process, 'generation': generation}
    from kronos.common.failed_fenced_recovery import _check_type
    _check_type('Lineage', lineage)
    entries = _fixed_preparation_entries(ledger.store)
    matches = [row for row in entries if row[0]['mode']=='ORIGINAL' and row[0]['lineage']==lineage]
    if not matches:
        return None
    if len(matches)!=1 or not all(hasattr(ledger, name) for name in
            ('prospective_source','prospective_capability','prospective_control')):
        raise RecoveryStartupError('RECOVERY_ORIGINAL_PREPARATION_AMBIGUOUS_OR_UNCAPTURED')
    record = matches[0][5]
    if record['control_hash']!=ledger.codec.key_id or record['clock']!=ledger.codec.clock:
        raise RecoveryStartupError('RECOVERY_ORIGINAL_CURRENT_CONTROL_CHANGED')
    # This provisional read ceiling never authorizes an operation. The retained
    # sequence-zero admission below supplies the actual immutable origin.
    now = ledger.now_ns()
    ceiling = min(int(deadline_ns), now+10_000_000_000)
    budget = RecoveryBudget(ledger.codec.clock, ceiling-10_000_000_000, ceiling+5_000_000_000)
    budget.work_deadline_ns = ceiling
    budget.check(ceiling)
    if ledger.codec.clock['boot_id']!=native_boot_id():
        raise RecoveryStartupError('RECOVERY_ORIGINAL_BOOT_CHANGED')
    # C retains the service lock while awaiting this actual backend. Reads
    # use the immutable fixed estate; P must not deadlock on C's lock.
    prep=load_native_preparation(ledger.store, controller=record['controller'], mode='ORIGINAL',
        lineage=lineage, attempt=record['attempt'])
    registry=EvidenceRegistry(ledger.codec,ledger.store,prep)
    registry.bind_native_ledger(ledger)
    registry.verify(ledger.codec.clock['qualification'],'CLOCK_QUALIFICATION')
    if canonical_controller_identity(int(record['controller']['pid']),budget=budget)!=record['controller']:
        raise RecoveryStartupError('RECOVERY_ORIGINAL_NATIVE_CONTROLLER_CHANGED')
    for evidence, kind in ((ledger.prospective_source,'SOURCE'),
            (ledger.prospective_capability,'CAPABILITY'),(ledger.prospective_control,'CONTROL_BINDING')):
        registry.verify(evidence,kind,context={'mode':'ORIGINAL'})
    # Fixed immutable namespaces only; untrusted payload fields only narrow
    # candidates, followed by exact MAC, issuer and closed-registry checks.
    proofs={kind:[] for kind in ('ORIGINAL_AUTHORITY','CONTROLLER_ADMISSION')}
    custody=[]; consumed=0
    for directory in ('blobs','records'):
        fd=ledger.store._dir((directory,))
        try: names=sorted(os.listdir(fd))
        finally: os.close(fd)
        if len(names)>4096:
            raise RecoveryStartupError('RECOVERY_ORIGINAL_PROOF_BOUND')
        for name in names:
            budget.check(ceiling)
            if directory=='records' and not name.startswith('CUSTODY-'):
                continue
            if directory=='blobs' and re.fullmatch(r'[0-9a-f]{64}\.blob',name) is None:
                raise RecoveryStartupError('RECOVERY_ORIGINAL_BLOB_NAMESPACE')
            raw=ledger.store._read((directory,),name,16*MAX_RECORD+1)
            consumed+=len(raw)
            if consumed>64*MAX_RECORD:
                raise RecoveryStartupError('RECOVERY_ORIGINAL_PROOF_BYTES_BOUND')
            if directory=='blobs' and sha256(raw).hexdigest()!=name[:-5]:
                raise RecoveryStartupError('RECOVERY_ORIGINAL_BLOB_CHANGED')
            try: candidate=decode_canonical(raw)
            except ValueError: continue
            if type(candidate) is not dict or type(candidate.get('payload')) is not dict:
                continue
            payload=candidate['payload']; kind=candidate.get('kind')
            if directory=='records' and kind=='CUSTODY' and payload.get('lineage')==lineage:
                checked=ledger.codec.decode(raw,'CUSTODY')['payload']
                if (checked['controller']!=record['controller'] or checked['checkpoint_hash']!=ledger.codec.key_id
                        or checked['live_control']!=ledger.prospective_control):
                    raise RecoveryStartupError('RECOVERY_ORIGINAL_CUSTODY_CHANGED')
                cap=registry.verify(checked['controller_capability'],'CONTROLLER_CAPABILITY',context={'mode':'ORIGINAL'})['payload']
                if cap['executable']['hash']!=record['controller']['runtime'] or name!='CUSTODY-'+sha256(raw).hexdigest()+'.json':
                    raise RecoveryStartupError('RECOVERY_ORIGINAL_CONTROLLER_SOURCE_CHANGED')
                observation=registry.verify(checked['process_binding'],'PLATFORM_OBSERVATION',
                    subject=ledger.process,context={'mode':'ORIGINAL'})['payload']
                if observation['subject']!=ledger.process:
                    raise RecoveryStartupError('RECOVERY_ORIGINAL_PROCESS_CHANGED')
                custody.append(raw)
            elif kind in proofs and candidate.get('issuer')==record['controller']:
                if kind=='ORIGINAL_AUTHORITY' and (payload.get('generation')!=generation or payload.get('process')!=ledger.process):
                    continue
                if kind=='CONTROLLER_ADMISSION' and (payload.get('lineage')!=lineage or payload.get('attempt')!=record['attempt']):
                    continue
                evidence=registry.proof_evidence(raw)
                checked=registry.verify(evidence,kind,context={'mode':'ORIGINAL'})
                proofs[kind].append((raw,evidence,checked['payload']))
    if len(custody)!=1 or len(proofs['ORIGINAL_AUTHORITY'])!=1:
        raise RecoveryStartupError('RECOVERY_ORIGINAL_NATIVE_PUBLICATION_INCOMPLETE')
    admissions=proofs['CONTROLLER_ADMISSION']
    first=[item for item in admissions if item[2]['sequence']=='0']
    if len(first)!=1 or first[0][2]['action']!='AUTHORIZE':
        raise RecoveryStartupError('RECOVERY_ORIGINAL_NATIVE_ORIGIN_REQUIRED')
    origin=int(first[0][2]['accepted_ns']); stop=origin+15_000_000_000
    drain=min(int(deadline_ns),origin+10_000_000_000)
    actual_budget=RecoveryBudget(ledger.codec.clock,origin,stop)
    actual_budget.check(drain)
    authority_raw,authorization,authority=proofs['ORIGINAL_AUTHORITY'][0]
    if not int(authority['valid_from_ns'])<=origin<actual_budget.check(drain)<int(authority['valid_until_ns']):
        raise RecoveryStartupError('RECOVERY_ORIGINAL_PERMISSION_EXPIRED')
    if authority['source']!=_as_blob(ledger.prospective_source) or authority['control']['hash']!=ledger.codec.key_id:
        raise RecoveryStartupError('RECOVERY_ORIGINAL_SOURCE_CONTROL_CHANGED')
    reservation=(registry.proof_evidence(ledger.store.read_blob(authority['reservation'])) if authority['kind']=='ORDINARY'
        else _interface_evidence('SPONSOR',authority['reservation']))
    approvals=[]
    for owner in ('CA','EA-INTRADAY','EA-SWING','PCP'):
        rows=[row for row in prep.rows.values() if row['purpose']=='OWNER_SCOPE' and row['authority']==owner]
        if len(rows)!=1:
            raise RecoveryStartupError('RECOVERY_ORIGINAL_SCOPE_APPROVAL_REQUIRED')
        approvals.append(_interface_evidence(owner,rows[0]['artifact']))
    _verify_scope_approvals(registry,approvals)
    payload={'lineage':lineage,'custody':record_ref(custody[0]),'source':ledger.prospective_source,
        'capability':ledger.prospective_capability,'control':ledger.prospective_control,
        'authorization':authorization,'reservation':reservation,'attempt':record['attempt'],
        'original_kind':authority['kind'],'original_limits':{'clock':ledger.codec.clock,
            'origin_ns':str(origin),'stop_deadline_ns':str(stop)},
        'original_drain_deadline_ns':str(drain),'owner_scope':ledger.scope,'scope_approvals':approvals}
    actual_budget.check(drain)
    return OriginalBrowserBinding(ledger,registry,payload,
        executor='backend-original-'+sha256((record['attempt']+generation).encode('ascii')).hexdigest())



def prepare_recovery_binding(server):
    """Resolve the already-reserved exact claim before any HTTP input read."""
    from kronos.common.failed_fenced_recovery import (ProspectiveLedger, RecoveryError,
        RecoveryTransaction, RecoveryBudget, EvidenceRegistry, slot_key, load_native_preparation)
    from kronos.browser.failed_fenced_control import RecoveryBrowserBinding
    from tools.runtime_source_gate import canonical_controller_identity, native_boot_id
    ledger=getattr(server,'_failed_fenced_ledger',None)
    if ledger is None:
        return None
    if type(ledger) is not ProspectiveLedger:
        raise RecoveryStartupError('RECOVERY_ACTUAL_LEDGER_REQUIRED')
    if ledger.coordinator.snapshot()['state']!='FAILED_FENCED':
        return None
    if ledger.lineage is None or ledger.original is None or ledger.terminal is None:
        raise RecoveryStartupError('RECOVERY_ORIGINAL_PROVENANCE_UNAVAILABLE')
    slot=slot_key(ledger.lineage)
    try:raw=ledger.store.read_reservation(slot,'claim')
    except (FileNotFoundError,RecoveryError) as exc:
        if isinstance(exc,FileNotFoundError) or isinstance(exc.__cause__,FileNotFoundError):
            return None
        raise
    claim=ledger.codec.decode(raw,'CLAIM')['payload']
    limits=claim['limits']
    budget=RecoveryBudget(limits['clock'],int(limits['origin_ns']),int(limits['stop_deadline_ns']))
    budget.check()
    if claim['slot']!=slot or claim['binding']['lineage']!=ledger.lineage or budget.clock!=ledger.codec.clock or budget.clock['boot_id']!=native_boot_id():
        raise RecoveryStartupError('RECOVERY_RESERVED_CLAIM_IDENTITY_CHANGED')
    # C holds service.lock across this endpoint. Every read independently checks
    # the immutable fixed publication; P does not acquire the controller lock.
    preparation=load_native_preparation(ledger.store,controller=claim['launcher'],mode='RECOVERY',
        lineage=ledger.lineage,attempt=claim['transaction'])
    registry=EvidenceRegistry(ledger.codec,ledger.store,preparation)
    registry.bind_native_ledger(ledger)
    registry.verify(budget.clock['qualification'],'CLOCK_QUALIFICATION')
    if canonical_controller_identity(int(claim['launcher']['pid']),budget=budget)!=claim['launcher']:
        raise RecoveryStartupError('RECOVERY_NATIVE_CONTROLLER_CHANGED')
    source=registry.verify(ledger._original_payload['source'],'SOURCE',context={'mode':'ORIGINAL'})['payload']
    tails=[row for row in preparation.rows.values() if row['authority']=='CA' and row['purpose']=='TAIL'
        and row['bindings']['entry']==RecoveryBrowserBinding.TAIL_ENTRY
        and row['bindings']['source_inventory']==source['source_inventory']]
    if len(tails)!=1:
        raise RecoveryStartupError('RECOVERY_TAIL_PREPARATION_UNAVAILABLE')
    tx=RecoveryTransaction(ledger.coordinator,ledger,ledger.codec,ledger.store,registry,budget)
    if tx.expected_claim_raw()!=raw:
        raise RecoveryStartupError('RECOVERY_RESERVED_CLAIM_CHANGED')
    ledger.attach_registry(registry)
    budget.check()
    return RecoveryBrowserBinding(tx,tail_approval=tails[0]['identity'])


def _bootstrap_process_observation(pid, budget):
    """Actual Darwin process birth and parent, with no supplied observation."""
    import ctypes
    import sys
    from tools.failed_fenced_launcher import _ProcBSDInfo
    budget.check()
    if sys.platform != "darwin" or ctypes.sizeof(_ProcBSDInfo) != 136:
        raise RecoveryStartupError("RECOVERY_DARWIN_PLATFORM_REQUIRED")
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    library.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                    ctypes.c_void_p, ctypes.c_int]
    library.proc_pidinfo.restype = ctypes.c_int
    info = _ProcBSDInfo()
    ctypes.set_errno(0)
    size = library.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
    budget.check()
    if size != ctypes.sizeof(info) or info.pid != pid or ctypes.get_errno() != 0:
        raise RecoveryStartupError("RECOVERY_NATIVE_PROCESS_BIRTH_REQUIRED")
    return {"pid": str(info.pid), "kernel_birth": {"seconds": str(info.start_seconds),
            "microseconds": str(info.start_microseconds)}, "parent_pid": str(info.ppid)}


def _bootstrap_module_snapshot():
    import sys
    return tuple(sys.modules.items())


def _actual_bootstrap_modules(startup, plan, source_modules, budget):
    """Compare executing loaders' captured bytes, never reread current source."""
    import importlib.machinery
    from types import MappingProxyType
    from kronos.intraday.runtime_identity import _PinnedLoader, StartupCapture, digest
    expected = tuple((row["name"], row["digest"]) for row in plan["modules"])
    inventory = dict(source_modules)
    if (expected != tuple(sorted(expected)) or len(dict(expected)) != len(expected)
            or any(inventory.get(name) != value for name, value in expected)
            or startup.source_snapshot_digest != digest(source_modules)):
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_PLAN_INVENTORY_CHANGED")
    seen, captures = {}, set()
    snapshot = _bootstrap_module_snapshot()
    native_modules = []
    for alias, module in snapshot:
        specification = getattr(module, "__spec__", None)
        name = getattr(specification, "name", None)
        loader = getattr(specification, "loader", None)
        if (type(name) is str and (name in {"kronos", "tools"} or name.startswith(("kronos.", "tools.")))
                and loader is not None and type(loader) not in {_PinnedLoader, importlib.machinery.NamespaceLoader}):
            native_modules.append(module)
    native = {}
    if native_modules:
        from tools.runtime_source_gate import native_child_pinned_modules
        try:
            native = {id(module): result for module, result in zip(native_modules,
                native_child_pinned_modules(native_modules, check_deadline=budget.check), strict=True)}
        except (ValueError, AttributeError, KeyError, TypeError):
            raise RecoveryStartupError("RECOVERY_BOOTSTRAP_EXECUTED_BYTES_UNPROVEN") from None
    for alias, module in snapshot:
        budget.check()
        specification = getattr(module, "__spec__", None)
        name = getattr(specification, "name", None)
        if not (alias in {"kronos", "tools"} or alias.startswith(("kronos.", "tools."))
                or type(name) is str and (name in {"kronos", "tools"} or name.startswith(("kronos.", "tools.")))):
            continue
        if type(name) is not str or specification is None:
            raise RecoveryStartupError("RECOVERY_BOOTSTRAP_UNKNOWN_MODULE")
        if name in seen:
            if seen[name][0] is not module:
                raise RecoveryStartupError("RECOVERY_BOOTSTRAP_MODULE_ALIAS_CHANGED")
            continue
        loader = specification.loader
        if (loader is None or type(loader) is importlib.machinery.NamespaceLoader):
            if (getattr(module, "__file__", None) is not None
                    or specification.submodule_search_locations is None
                    or name in inventory or name in dict(expected)
                    or not any(key.startswith(name + ".") for key in inventory)):
                raise RecoveryStartupError("RECOVERY_BOOTSTRAP_UNKNOWN_NAMESPACE")
            continue
        if type(loader) is not _PinnedLoader:
            try:
                native_name, actual = native[id(module)]
            except (ValueError, AttributeError, KeyError, TypeError):
                raise RecoveryStartupError("RECOVERY_BOOTSTRAP_EXECUTED_BYTES_UNPROVEN") from None
            if native_name != name or inventory.get(name) != actual:
                raise RecoveryStartupError("RECOVERY_BOOTSTRAP_SOURCE_BYTES_CHANGED")
            seen[name] = (module, actual)
            continue
        capture = loader.capture
        if (type(capture) is not StartupCapture or capture._finished is not startup
                or capture._pid != os.getpid() or loader.name != name
                or type(loader.payload) is not bytes or name not in capture._sources
                or type(capture._sources) is not MappingProxyType
                or capture._sources[name][1] != loader.payload
                or capture._sources[name][0] != loader.filename):
            raise RecoveryStartupError("RECOVERY_BOOTSTRAP_CAPTURE_CHANGED")
        if id(capture) not in captures:
            captured = []
            for key, value in capture._sources.items():
                budget.check()
                captured.append((key, sha256(value[1]).hexdigest()))
            if digest(tuple(sorted(captured))) != startup.source_snapshot_digest:
                raise RecoveryStartupError("RECOVERY_BOOTSTRAP_CAPTURE_CHANGED")
            captures.add(id(capture))
        actual = sha256(loader.payload).hexdigest()
        if inventory.get(name) != actual:
            raise RecoveryStartupError("RECOVERY_BOOTSTRAP_SOURCE_BYTES_CHANGED")
        seen[name] = (module, actual)
    observed = tuple(sorted((name, value[1]) for name, value in seen.items()))
    if observed != expected or any(dict(observed).get(name) != value for name, value in startup.loaded_modules):
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_EXECUTED_SET_CHANGED")
    return observed


def load_child_preparation(startup, environment, inherited_budget):
    """Independently acquire the child authority from the existing fixed estate.

    The three environment values locate an immutable spent intent only. The
    actual canonical kernel parent selects the trusted §1A preparation. This
    reads neither extra argv/root fields nor an additional pipe authority.
    """
    from kronos.common.failed_fenced_recovery import (RecoveryStore, RecoveryCodec,
        RecoveryBudget, EvidenceRegistry, load_native_preparation, decode_canonical,
        record_ref, SCOPE_HASH, SCOPE_BYTES, PROTOCOL, VERSION)
    from tools.runtime_source_gate import canonical_parent_identity, native_boot_id, fixed_native_estate
    from kronos.intraday.runtime_identity import StartupEvidence
    if (type(startup) is not StartupEvidence or startup.process_id != os.getpid()
            or inherited_budget is None):
        raise RecoveryStartupError("RECOVERY_CANONICAL_CHILD_IDENTITY_REQUIRED")
    selected = selectors(environment)
    if selected is None:
        raise RecoveryStartupError("RECOVERY_CHILD_SELECTORS_REQUIRED")
    slot, nonce = selected
    store = RecoveryStore(fixed_native_estate())
    inherited_budget.check()
    raw = store.read_reservation(slot, "claim")
    hinted = decode_canonical(raw)
    # The key hint locates private retained custody only. The MAC, the fixed
    # parent-selected preparation and the full chain must independently agree.
    from kronos.common import failed_fenced_schema as schema
    schema.validate_type("Hash", hinted.get("key_id"))
    schema.validate_type("Clock", hinted.get("clock"))
    codec = RecoveryCodec(store.read_custody(hinted["key_id"]), hinted["clock"])
    claim = codec.decode(raw, "CLAIM")["payload"]
    limits = claim["limits"]
    budget = RecoveryBudget(limits["clock"], int(limits["origin_ns"]), int(limits["stop_deadline_ns"]))
    if (budget.clock != inherited_budget.clock or budget.origin_ns != inherited_budget.origin_ns
            or budget.stop_deadline_ns != inherited_budget.stop_deadline_ns
            or record_ref(raw)["hash"] != inherited_budget.claim_hash):
        raise RecoveryStartupError("RECOVERY_INHERITED_BUDGET_CHANGED")
    budget.check()
    parent = canonical_parent_identity(budget=budget)
    if claim["launcher"] != parent:
        raise RecoveryStartupError("RECOVERY_CHILD_CANONICAL_PARENT_CHANGED")
    # The live canonical parent retains service.lock across this child entry.
    preparation = load_native_preparation(store, controller=parent, mode="RECOVERY",
        lineage=claim["binding"]["lineage"], attempt=claim["transaction"])
    registry = EvidenceRegistry(codec, store, preparation)
    intent_raw = store.read_reservation(slot, "child-intent")
    intent = codec.decode(intent_raw, "CHILD_INTENT")["payload"]
    if (record_ref(intent_raw)["hash"] != inherited_budget.intent_hash or intent["slot"] != slot
            or intent["child_nonce"] != nonce or intent["claim"] != record_ref(raw)
            or intent["transaction"] != claim["transaction"]):
        raise RecoveryStartupError("RECOVERY_CHILD_RETAINED_INTENT_CHANGED")
    # Root proof identity comes from the exact independently published catalogue
    # row; unknown or multiple roots cannot be repaired or selected by a caller.
    candidates = []
    for row in preparation.rows.values():
        if row["purpose"] != "GUARD" or row["authority"] != "CA":
            continue
        root_raw = store.read_blob(row["artifact"])
        root = decode_canonical(root_raw)
        if (root.get("schema") == "KRONOS-FAILED-FENCED-ROOT-PROOF/1.0.0"
                and root.get("kind") == "GUARD_APPLICABILITY"):
            evidence = registry.proof_evidence(root_raw)
            registry.verify(evidence, "GUARD_APPLICABILITY")
            candidates.append(evidence)
    if len(candidates) != 1:
        raise RecoveryStartupError("RECOVERY_CHILD_GUARD_PREPARATION_AMBIGUOUS")
    authority = PreparedStartupAuthority(codec, store, registry, budget, candidates[0], {})
    authority.verify(environment)
    target = registry.verify(intent["successor_source"], "TARGET_ARTIFACT")["payload"]
    scope = {"authority": "CA", "contract": PROTOCOL + ":" + VERSION,
        "identity": "FAILED_FENCED_INITIAL_OWNER_SCOPE_V1", "hash": SCOPE_HASH, "bytes": SCOPE_BYTES}
    registry.verify(scope, "SCOPE")
    budget.check()
    return authority, PreparedRuntimeFactory(authority, scope, target["source_inventory"])


def prepare_child_startup(authority, startup, environment):
    """Produce the actual child's S bootstrap attestation, without publication.

    Only existing selectors locate the already retained intent. The supplied
    typed preparation owns authority; actual kernel and loaded source facts are
    collected here, independently of any claimed native_context observations.
    """
    from kronos.common.failed_fenced_recovery import (
        RecoveryCodec, RecoveryStore, RecoveryBudget, EvidenceRegistry,
        PreparationContext, blob_ref, decode_canonical, record_ref,
    )
    from kronos.common import failed_fenced_schema as schema
    from kronos.intraday.runtime_identity import StartupEvidence, canonical
    from tools.runtime_source_gate import canonical_parent
    if (type(authority) is not PreparedStartupAuthority or type(startup) is not StartupEvidence
            or type(authority.codec) is not RecoveryCodec or type(authority.store) is not RecoveryStore
            or type(authority.registry) is not EvidenceRegistry or type(authority.budget) is not RecoveryBudget
            or type(authority.registry.preparation) is not PreparationContext
            or authority.registry.codec is not authority.codec or authority.registry.store is not authority.store
            or authority.registry.preparation.record["mode"] != "RECOVERY"):
        raise RecoveryStartupError("RECOVERY_CANONICAL_CHILD_PREPARATION_REQUIRED")
    replace(startup)
    if (startup.process_id != os.getpid() or startup.source_state != "CLEAN_COMMIT"
            or startup.load_verification != "PINNED_STARTUP_IMPORTS"):
        raise RecoveryStartupError("RECOVERY_NATIVE_IDENTITY_REJECTED")
    selection = authority.verify(environment)
    if selection is None:
        raise RecoveryStartupError("RECOVERY_CHILD_SELECTORS_REQUIRED")
    slot, nonce = selection
    budget, store, codec, registry = authority.budget, authority.store, authority.codec, authority.registry
    budget.check()
    intent_raw = store.read_reservation(slot, "child-intent")
    intent = codec.decode(intent_raw, "CHILD_INTENT")["payload"]
    claim_raw = store.resolve(intent["claim"])
    claim = codec.decode(claim_raw, "CLAIM")["payload"]
    target = registry.verify(intent["successor_source"], "TARGET_ARTIFACT")["payload"]
    plan_raw = store.read_blob(target["bootstrap_plan"])
    plan = decode_canonical(plan_raw)
    schema.validate_type("BootstrapPlan", plan)
    if (intent["slot"] != slot or intent["child_nonce"] != nonce
            or intent["claim"] != record_ref(claim_raw) or claim["slot"] != slot
            or claim["transaction"] != intent["transaction"]
            or intent["successor_source"] != claim["successor_source"]
            or intent["successor_capability"] != claim["successor_capability"]
            or intent["limits"] != claim["limits"]
            or claim["limits"]["clock"] != budget.clock
            or int(claim["limits"]["origin_ns"]) != budget.origin_ns
            or int(claim["limits"]["stop_deadline_ns"]) != budget.stop_deadline_ns
            or claim["launcher"] != registry.preparation.record["controller"]
            or startup.source_revision != target["revision"]
            or plan["source_inventory"] != target["source_inventory"]):
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_PREPARATION_CHANGED")
    registry.verify(claim["launcher_capability"], "CONTROLLER_CAPABILITY")
    canonical_parent(budget=budget)
    child_fact = _bootstrap_process_observation(os.getpid(), budget)
    parent_fact = _bootstrap_process_observation(os.getppid(), budget)
    parent = claim["launcher"]
    if (child_fact["pid"] != str(os.getpid()) or child_fact["parent_pid"] != parent["pid"]
            or parent_fact["pid"] != parent["pid"] or parent_fact["kernel_birth"] != parent["kernel_birth"]):
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_ACTUAL_PARENT_CHANGED")
    process = {"pid": child_fact["pid"], "kernel_birth": child_fact["kernel_birth"],
               "runtime": sha256(startup.evidence_identity.encode("utf-8")).hexdigest()}
    source_modules = validate_source_inventory_blob(store.read_blob(target["source_inventory"]))
    allowed = {"wo06h_epoch", "wo06h_predecessor", "wo06h_successor", "wo06h_verified_at",
               "observed_child", "observed_parent", "executing_bootstrap_modules"}
    if type(authority.native_context) is not dict or not set(authority.native_context) <= allowed:
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_NATIVE_CONTEXT_REJECTED")
    context = {key: value for key, value in authority.native_context.items() if key.startswith("wo06h_")}
    context.update(observed_child=process, observed_parent=parent)
    with registry._composition_validation(budget.check):
        chain = validate_recovery_chain(codec, store, registry, intent_raw, slot=slot,
                                        budget=budget, native_context=context)
    # The intent graph has no future child identity. Validate its actual
    # adapters before attesting the complete executing verifier closure.
    modules = _actual_bootstrap_modules(startup, plan, source_modules, budget)
    context["executing_bootstrap_modules"] = modules
    chain["executing_bootstrap_modules"] = modules
    prepared_authority = replace(authority, native_context=context)
    native = NativeBootstrap(startup, process, modules).validate(expected_process=process, expected_modules=modules)
    native_raw = canonical(asdict(startup))
    qualified = budget.check()
    identity = "bootstrap-" + nonce
    payload = {"identity": identity, "process": process, "parent": parent,
        "intent": record_ref(intent_raw), "child_nonce": nonce,
        "startup": blob_ref("startup-" + nonce, native_raw),
        "target": {key: intent["successor_source"][key] for key in ("identity", "hash", "bytes")},
        "bootstrap_plan": target["bootstrap_plan"],
        "loaded_bootstrap": [{"name": name, "digest": value} for name, value in modules],
        "qualified_ns": str(qualified)}
    proof_raw = codec.encode_proof("BOOTSTRAP_IDENTITY", payload, process, "SUCCESSOR", qualified)
    evidence = registry.proof_evidence(proof_raw)
    _verify_inline_bootstrap(registry, evidence, proof_raw, native_raw, process, chain)
    restoration_raw = store.read_blob(target["restoration_plan"])
    restoration_scope = registry.proof_evidence(restoration_raw)
    registry.verify(restoration_scope, "RESTORATION_PLAN")
    if _actual_bootstrap_modules(startup, plan, source_modules, budget) != modules:
        raise RecoveryStartupError("RECOVERY_BOOTSTRAP_EXECUTED_SET_CHANGED")
    budget.check()
    return PreparedChildStartup(prepared_authority, native, evidence, proof_raw, native_raw,
                                chain["CHILD_INTENT"]["payload"]["checkpoint"], restoration_scope)


def _actual_ready_modules(startup, inventory, budget):
    """Check later imports against the complete original pinned snapshot.

    The earlier bootstrap list intentionally predates product construction.
    Actual executing loaders, including later imports, supply the observed set;
    the immutable complete snapshot supplies their expected byte identities.
    """
    from kronos.intraday.runtime_identity import _PinnedLoader
    observed = {}
    for _alias, module in _bootstrap_module_snapshot():
        specification = getattr(module, "__spec__", None)
        loader = getattr(specification, "loader", None)
        if type(loader) is _PinnedLoader:
            observed[specification.name] = sha256(loader.payload).hexdigest()
        elif specification is not None and type(getattr(specification, "name", None)) is str:
            name = specification.name
            if name in {"kronos", "tools"} or name.startswith(("kronos.", "tools.")):
                from tools.runtime_source_gate import native_child_pinned_module
                try:
                    actual_name, actual = native_child_pinned_module(module)
                except (ValueError, AttributeError, KeyError, TypeError):
                    # The full walk below distinguishes a legitimate namespace
                    # from an unknown/unpinned executing application loader.
                    continue
                if actual_name != name:
                    raise RecoveryStartupError("RECOVERY_BOOTSTRAP_SOURCE_BYTES_CHANGED")
                observed[name] = actual
    plan = {"modules": [{"name": name, "digest": observed[name]}
                        for name in sorted(observed)]}
    return _actual_bootstrap_modules(startup, plan, inventory, budget)


class SuccessorReadyEvidence:
    """Child-owned evidence after actual consumption and canonical startup.

    This producer neither completes startup nor grants composition authority.
    It reads the exact constructed owners, publishes only role-S facts, and
    returns an unsigned READY_RECEIPT payload for the real role-L issuer.
    """

    def __init__(self, session, prepared_runtime, server):
        self.session, self.prepared_runtime, self.server = session, prepared_runtime, server
        self._pid, self._attempted = os.getpid(), False
        self._source_payload = self._capability_payload = None
        self._restoration_payload = None
        self._absence_native = {}
        self._receipt = None
        self.verify_native_binding()
        session.registry.bind_successor_runtime(self)

    @staticmethod
    def _deny(condition, reason):
        if not condition:
            raise RecoveryStartupError(reason)

    def _target(self):
        session = self.session
        intent = session.chain["CHILD_INTENT"]["payload"]
        self._deny(intent["successor_source"] == intent["successor_capability"],
                   "RECOVERY_READY_TARGET_CHANGED")
        return session.registry.verify(intent["successor_source"], "TARGET_ARTIFACT")["payload"]

    def _routes(self):
        from kronos.browser.product_routes import ProductBrowserRoutes
        from kronos.browser.intraday_routes import IntradayBrowserRoutes
        routes = self.server.product_routes
        self._deny(type(routes) is ProductBrowserRoutes, "RECOVERY_READY_PRODUCT_ROUTES_REQUIRED")
        matches = [row for row in routes._routes if type(row) is IntradayBrowserRoutes]
        self._deny(len(matches) == 1, "RECOVERY_READY_INTRADAY_OWNER_AMBIGUOUS")
        return matches[0]

    def _restoration_objects(self):
        from kronos.browser.intraday_probables_v2_control import IntradayProbablesV2OperationalControl
        from kronos.browser.intraday_wo17_control import IntradayWo17OperationalControl
        from kronos.application.intraday_live_shadow import IntradayLiveShadowService
        from kronos.application.intraday_shadow_history import HistoricalIntradayLiveShadowService
        from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
        routes = self._routes()
        control, wo17 = routes._probables_v2_control, routes._wo17_control
        self._deny(type(control) is IntradayProbablesV2OperationalControl
            and type(wo17) is IntradayWo17OperationalControl
            and type(self.server.intraday_lifecycle) is IntradayLifecycleApplication,
            "RECOVERY_READY_RESTORATION_OWNER_REQUIRED")
        shadow = control.operation_service.live_shadow
        self._deny(type(shadow) in {IntradayLiveShadowService, HistoricalIntradayLiveShadowService}
            and control._runtime_manifest is self.prepared_runtime.ledger.native_runtime_manifest
            and wo17._monitoring is self.server.intraday_wo17_monitoring,
            "RECOVERY_READY_RESTORATION_BINDING_CHANGED")
        return shadow, self.server.intraday_lifecycle, wo17

    def _native_states(self):
        from kronos.common.runtime_restoration import _swing_restoration_failure
        from kronos.application.failed_fenced_owners import callback_state
        server = self.server
        outcomes = server.startup_restoration_outcomes()
        self._deny(not _swing_restoration_failure(outcomes), "RECOVERY_READY_SWING_RESTORATION_FAILED")
        shadow, wo11, wo17 = self._restoration_objects()
        window, wo17_status = shadow.status(), wo17.status_document()
        historical = (window.get("historical_restoration") == "KRONOS-WO06H-HISTORICAL-RESTORATION/1.0.0"
            and window.get("acceptance_disposition") == "HISTORICAL_ACCEPTANCE_EXPIRED"
            and window.get("historical_evidence") == "READABLE" and window.get("collection_authority") == "EXPIRED"
            and window.get("enabled") is False and window.get("runtime_accepted") is False)
        self._deny(window.get("failure") is None and "window" in window
            and (window["window"] is None or window.get("runtime_accepted") is True or historical),
            "RECOVERY_READY_WO08_RESTORATION_FAILED")
        self._deny(wo11.last_failure is None, "RECOVERY_READY_WO11_RESTORATION_FAILED")
        self._deny(wo17_status.get("restoration_state") in {"LOADED", "NOT_YET_RUN"}
            and wo17_status.get("failure_stage") is None and wo17_status.get("failure_reason") is None
            and (wo17_status["restoration_state"] != "NOT_YET_RUN" or wo17_status.get("current_positions") == []),
            "RECOVERY_READY_WO17_RESTORATION_FAILED")
        provider, transport = server.provider_runtime.read_only_status(), server.swing_monitoring_hub.status_document()
        self._deny(provider.get("capability_state") == "ABSENT" and provider.get("cleanup_state") == "COMPLETE"
            and all(type(provider.get(key)) is int and provider[key] == 0 for key in
                ("owned_work_count", "retained_lease_count", "unresolved_cleanup_count")),
            "RECOVERY_READY_PROVIDER_NOT_ABSENT")
        self._deny(all(type(transport.get(key)) is int and transport[key] == 0 for key in
            ("session_count", "active_session_count", "owner_count", "subscription_count"))
            and transport.get("transport_cleanup", {}).get("state") == "COMPLETE",
            "RECOVERY_READY_TRANSPORT_NOT_ABSENT")
        for owner in (server.provider_runtime, server.swing_monitoring_hub):
            callbacks = callback_state(owner)
            self._deny(callbacks["callbacks"] == 0 and not callbacks["callback_failure"],
                       "RECOVERY_READY_CALLBACKS_NOT_ABSENT")
        return outcomes, window, {"last_failure": wo11.last_failure, "restoration_state": "LOADED"}, wo17_status, provider, transport

    def verify_native_binding(self):
        from kronos.common.failed_fenced_recovery import ProspectiveLedger, EvidenceRegistry, RecoveryCodec, RecoveryStore, record_ref
        from kronos.application.failed_fenced_owners import ProspectiveComposition, FINITE_OWNERS
        from kronos.browser.server import KronosBrowserServer
        from kronos.browser.restart_control import BrowserBackendRestartControl
        from kronos.common.connection_governance import ConnectionGovernance
        from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
        from kronos.application.shared_monitoring import SharedSwingMonitoringHub
        from kronos.intraday.runtime_identity import RuntimeManifest, StartupEvidence
        session, runtime, server = self.session, self.prepared_runtime, self.server
        self._deny(type(session) is BootstrapSession and session._pid == self._pid == os.getpid()
            and type(session.codec) is RecoveryCodec and type(session.store) is RecoveryStore
            and type(session.registry) is EvidenceRegistry and session.registry.codec is session.codec
            and session.registry.store is session.store and type(session.native) is NativeBootstrap
            and type(runtime) is ProspectiveRuntimeStartup and type(server) is KronosBrowserServer
            and type(runtime.ledger) is ProspectiveLedger and type(runtime.composition) is ProspectiveComposition
            and runtime.composition.ledger is runtime.ledger
            and runtime.ledger.native_composition is runtime.composition
            and server._failed_fenced_ledger is runtime.ledger
            and server.maintenance_admission is runtime.ledger.coordinator
            and type(runtime.restart_control) is BrowserBackendRestartControl
            and server.restart_control is runtime.restart_control and runtime.restart_control.owns_current_process()
            and runtime.ledger.codec is not session.codec and runtime.ledger.codec.key_id != session.codec.key_id
            and runtime.ledger.codec.matches_control(runtime.restart_control.private_bytes_for_recovery()),
            "RECOVERY_READY_NATIVE_BINDING_REQUIRED")
        self._deny(session._consumed and type(session.latch) is CompositionLatch and session.latch._spent
            and type(getattr(session, "ready_budget", None)) is ReadyBudget
            and type(getattr(session, "consumption_raw", None)) is bytes
            and type(getattr(session, "startup_context_raw", None)) is bytes,
            "RECOVERY_READY_DURABLE_CONSUMPTION_REQUIRED")
        session.ready_budget.check()
        context = session.codec.decode(session.startup_context_raw, "STARTUP_CONTEXT")["payload"]
        consumption = session.codec.decode(session.consumption_raw, "CONSUMPTION")["payload"]
        grant = session.codec.decode(session.latch.raw, "COMPOSITION_AUTHORITY")["payload"]
        started = session.codec.decode(session.chain["CHILD_STARTED_RAW"], "CHILD_STARTED")["payload"]
        self._deny(session.store.resolve(context["consumption"]) == session.consumption_raw
            and session.store.resolve(record_ref(session.startup_context_raw)) == session.startup_context_raw
            and context["runtime"] == consumption["consumer"] == session.native.process == runtime.ledger.process
            and context["consumption"] == record_ref(session.consumption_raw)
            and consumption["composition_authority"] == record_ref(session.latch.raw)
            and consumption["authority_bytes"] == session.latch.raw.hex()
            and context["child_started"] == consumption["child_started"] == grant["child_started"] == record_ref(session.chain["CHILD_STARTED_RAW"])
            and context["ready_deadline_ns"] == consumption["ready_deadline_ns"] == grant["ready_deadline_ns"]
                == str(session.ready_budget.ready_deadline_ns) == str(int(started["fork_enter_ns"]) + 120_000_000_000),
            "RECOVERY_READY_CONSUMPTION_BINDING_CHANGED")
        startup, manifest = runtime.ledger.native_startup, runtime.ledger.native_runtime_manifest
        self._deny(type(startup) is StartupEvidence and startup is session.native.startup
            and type(manifest) is RuntimeManifest and manifest.startup is startup
            and startup.process_id == os.getpid() and startup.source_state == "CLEAN_COMMIT"
            and startup.load_verification == "PINNED_STARTUP_IMPORTS", "RECOVERY_READY_SOURCE_CHANGED")
        replace(startup); replace(manifest)
        inventory = runtime.ledger._inventory_payload
        composition = runtime.composition
        self._deny(type(inventory) is dict and inventory["phase"] == "LIVE"
            and inventory["process"] == session.native.process
            and inventory["source"] == composition.source and set(composition._slots) == FINITE_OWNERS
            and inventory["slots"] == [dict(composition._slots[key], instances=sorted(composition._slots[key]["instances"]))
                                       for key in sorted(composition._slots)]
            and {row["identity"] for row in inventory["instances"]} == {value[1] for value in composition._objects.values()}
            and not composition._frozen, "RECOVERY_READY_CONSTRUCTION_INCOMPLETE")
        governance = server.connection_governance
        self._deny(type(governance) is ConnectionGovernance and governance is server.application.connection_governance
            and governance.process.pid == os.getpid() and governance.process.loaded_revision == startup.source_revision
            and governance.process.source_state == "CLEAN_COMMIT"
            and governance.process.runtime_identity == session.native.process["runtime"]
            and governance.process.startup_at == startup.startup_boundary_at.isoformat()
            and governance.maintenance_identity == sha256(context["transaction"].encode("ascii")).hexdigest(),
            "RECOVERY_READY_GOVERNANCE_BINDING_CHANGED")
        with governance.lock:
            self._deny(governance.startup_state == "READY" and governance.startup_failure is None
                and not governance.maintenance_active and not governance.shutting_down,
                "RECOVERY_READY_STARTUP_NOT_READY")
            path = governance.store.root / "maintenance" / (governance.process.runtime_identity + "-startup.json")
            self._deny(not path.is_symlink() and not path.parent.is_symlink(), "RECOVERY_READY_STARTUP_RECORD_CHANGED")
            document = _native_json(path.read_bytes())
            self._deny(set(document) == {"schema", "runtime_identity", "maintenance_identity", "at", "trigger"}
                and document["schema"] == "RUNTIME_STARTUP_MAINTENANCE_EXIT_V1"
                and document["runtime_identity"] == governance.process.runtime_identity
                and document["maintenance_identity"] == governance.maintenance_identity
                and document["trigger"] == "VERIFIED_CANONICAL_STARTUP",
                "RECOVERY_READY_STARTUP_RECORD_CHANGED")
        admission = runtime.ledger.coordinator.snapshot()
        ticket = getattr(runtime.ledger, "_canonical_startup_ticket", None)
        self._deny(admission["state"] == "OPEN" and not admission["failure"] and not any(admission["owners"].values())
            and ticket is not None and ticket._released and not runtime.ledger.coordinator.is_live(ticket),
            "RECOVERY_READY_ADMISSION_NOT_OPEN")
        self._deny(type(server.provider_runtime) is SharedAuthenticatedProviderRuntime
            and type(server.swing_monitoring_hub) is SharedSwingMonitoringHub,
            "RECOVERY_READY_SHARED_OWNER_REQUIRED")
        target = self._target()
        self._deny(target["revision"] == startup.source_revision and target["source_inventory"] == composition.source
            and target["scope"] == {key: composition.scope[key] for key in ("identity", "hash", "bytes")},
            "RECOVERY_READY_TARGET_CHANGED")
        modules = validate_source_inventory_blob(session.store.read_blob(target["source_inventory"]))
        self._loaded_modules = _actual_ready_modules(startup, modules, session.ready_budget)
        _verify_target_declarations(manifest,session.store,target)
        child = _bootstrap_process_observation(os.getpid(), session.ready_budget)
        parent = _bootstrap_process_observation(os.getppid(), session.ready_budget)
        self._deny(child["kernel_birth"] == session.native.process["kernel_birth"]
            and child["parent_pid"] == session.parent["pid"]
            and parent["pid"] == session.parent["pid"] and parent["kernel_birth"] == session.parent["kernel_birth"],
            "RECOVERY_READY_PARENT_CHANGED")
        from tools.runtime_source_gate import canonical_parent
        canonical_parent(budget=session.ready_budget)
        self._native_states()
        session.ready_budget.check()
        return context

    def verify_source_witness(self, payload):
        from kronos.intraday.runtime_identity import canonical
        self._deny(self._source_payload is not None and payload == self._source_payload,
                   "RECOVERY_READY_SOURCE_WITNESS_CHANGED")
        ledger, store = self.prepared_runtime.ledger, self.session.store
        self._deny(store.read_blob(payload["startup"]) == canonical(asdict(ledger.native_startup))
            and store.read_blob(payload["runtime_manifest"]) == canonical(asdict(ledger.native_runtime_manifest)),
            "RECOVERY_READY_SOURCE_NATIVE_BYTES_CHANGED")
        return ledger.native_startup, ledger.native_runtime_manifest

    def verify_capability_witness(self, payload):
        from kronos.common.failed_fenced_recovery import decode_canonical
        self._deny(self._capability_payload is not None and payload == self._capability_payload,
                   "RECOVERY_READY_CAPABILITY_WITNESS_CHANGED")
        rows = decode_canonical(self.session.store.read_blob(payload["operation_manifest"]))
        self._deny(type(rows) is list and bool(rows) and len(rows) <= 4096
            and all(type(row) is dict and set(row) == {"operation", "module", "digest", "contract"} for row in rows)
            and [row["operation"] for row in rows] == sorted({row["operation"] for row in rows})
            and len({(row["operation"], row["contract"]) for row in rows}) == len(rows),
            "RECOVERY_READY_OPERATION_MANIFEST_REJECTED")
        from kronos.common import failed_fenced_schema as schema
        loaded = dict(self._loaded_modules)
        expected = recovery_operation_manifest(validate_source_inventory_blob(
            self.session.store.read_blob(self._target()["source_inventory"])))
        self._deny(rows == expected, "RECOVERY_READY_OPERATION_MANIFEST_REJECTED")
        for row in rows:
            for key in ("operation", "module", "contract"):
                schema.validate_type("Id", row[key])
            schema.validate_type("Hash", row["digest"])
            self._deny(loaded.get(row["module"]) == row["digest"], "RECOVERY_READY_OPERATION_BYTES_CHANGED")
        registry = self.session.registry
        tails = [row for row in registry.preparation.rows.values() if row["authority"] == "CA"
                 and row["purpose"] == "TAIL" and row["bindings"]["source_inventory"] == self._target()["source_inventory"]
                 and row["bindings"]["callgraph"] == payload["tail_plan"]]
        self._deny(len(tails) == 1 and any(row["authority"] == "PCP" and row["purpose"] == "TAIL"
            and row["bindings"] == tails[0]["bindings"] for row in registry.preparation.rows.values()),
            "RECOVERY_READY_TAIL_APPROVAL_UNAVAILABLE")
        registry.store.read_blob(payload["tail_plan"])
        return self

    def verify_restoration_witness(self, payload):
        self._deny(self._restoration_payload is not None and payload == self._restoration_payload,
                   "RECOVERY_READY_RESTORATION_WITNESS_CHANGED")

    def verify_absence_witness(self, payload):
        self._deny(payload["kind"] in self._absence_native, "RECOVERY_READY_ABSENCE_WITNESS_UNAVAILABLE")
        native = self._native_states()[4 if payload["kind"] == "PROVIDER" else 5]
        from kronos.intraday.runtime_identity import canonical
        self._deny(self.session.store.read_blob(payload["native"]) == canonical(native)
            == self._absence_native[payload["kind"]], "RECOVERY_READY_ABSENCE_NATIVE_CHANGED")

    def publish(self):
        from kronos.common.failed_fenced_recovery import canonical_bytes, record_ref
        from kronos.intraday.runtime_identity import canonical
        self._deny(not self._attempted, "RECOVERY_READY_ATTEMPT_SPENT")
        self._attempted = True
        context = self.verify_native_binding()
        session, registry, store, ledger = self.session, self.session.registry, self.session.store, self.prepared_runtime.ledger
        target = self._target(); process = session.native.process
        prefix = "ready-" + session.chain["CHILD_INTENT"]["payload"]["child_nonce"]
        native_blobs = {}
        def native_blob(label, value):
            raw = canonical(value)
            digest = sha256(raw).hexdigest()
            if digest in native_blobs:
                result = native_blobs[digest]
                self._deny(store.read_blob(result) == raw, "RECOVERY_READY_NATIVE_READBACK_CHANGED")
                return result
            result = store.retain_blob(prefix + "-" + label, raw)
            native_blobs[digest] = result
            return result
        def proof(kind, payload):
            session.ready_budget.check()
            raw = session.codec.encode_proof(kind, payload, process, "SUCCESSOR", session.ready_budget.now_ns())
            store.write_blob(payload["identity"], raw)
            evidence = registry.proof_evidence(raw)
            registry.verify(evidence, kind, subject=process, context=dict(session.chain, child=process))
            session.ready_budget.check()
            return evidence
        startup_ref = store.retain_blob(prefix + "-startup", canonical(asdict(ledger.native_startup)))
        manifest_ref = store.retain_blob(prefix + "-runtime", canonical(asdict(ledger.native_runtime_manifest)))
        self._source_payload = {"identity": prefix + "-source", "process": process,
            "revision": ledger.native_startup.source_revision, "repository": registry.preparation.record["installation"],
            "startup": startup_ref, "runtime_manifest": manifest_ref, "source_inventory": target["source_inventory"],
            "canonical_parent": native_blob("parent", {"process": session.parent,
                "image": "/Applications/KRONOS.app/Contents/MacOS/KRONOS", "predicate": "tools.runtime_source_gate.canonical_parent"}),
            "publication": startup_ref, "package": target["package"], "verified_ns": str(session.ready_budget.now_ns())}
        source = proof("SOURCE", self._source_payload)
        tails = [row for row in registry.preparation.rows.values() if row["authority"] == "CA" and row["purpose"] == "TAIL"
                 and row["bindings"]["source_inventory"] == target["source_inventory"]]
        self._deny(len(tails) == 1, "RECOVERY_READY_TAIL_APPROVAL_UNAVAILABLE")
        operation_manifest = store.retain_blob(prefix + "-recovery-operations", canonical_bytes(
            recovery_operation_manifest(validate_source_inventory_blob(store.read_blob(target["source_inventory"])))))
        self._capability_payload = {"identity": prefix + "-capability", "process": process,
            "source": {key: source[key] for key in ("identity", "hash", "bytes")}, "capability": "FAILED_FENCED_RECOVERY_V1",
            "implementation": target["capability_manifest"], "owner_scope": target["scope"],
            "operation_manifest": operation_manifest, "tail_plan": tails[0]["bindings"]["callgraph"],
            "qualified_artifact": target["approval"]}
        self.verify_capability_witness(self._capability_payload)
        capability = proof("CAPABILITY", self._capability_payload)
        outcomes, window, wo11, wo17, provider, transport = self._native_states()
        owner_native = {owner: {"startup_restoration_outcomes": [list(row) for row in outcomes]}
                        for owner in ("SWING_ANALYSIS", "LOCAL_ANALYSIS", "RESEARCH", "NATIVE", "TRADE_WINDOW", "MCX")}
        owner_native.update(WO08=window, WO11=wo11, WO17=wo17)
        plan = registry.verify(context["restoration_scope"], "RESTORATION_PLAN")["payload"]
        self._deny(bool(plan["owners"]) and all(row["owner"] in owner_native for row in plan["owners"]),
                   "RECOVERY_READY_RESTORATION_PLAN_UNSUPPORTED")
        owners = [{"owner": row["owner"], "contract": row["contract"],
                   "native": native_blob("owner-" + row["owner"], owner_native[row["owner"]])} for row in plan["owners"]]
        source_blob = {key: source[key] for key in ("identity", "hash", "bytes")}
        self._restoration_payload = {"identity": prefix + "-restoration", "process": process,
            "startup_context": record_ref(session.startup_context_raw), "owners": owners,
            "native_runtime": native_blob("runtime-ready", {"startup": self.server.connection_governance.startup_state,
                "maintenance": self.server.connection_governance.maintenance_status(),
                "admission": ledger.coordinator.snapshot(), "composition": ledger.inventory}),
            "source": source_blob, "window": native_blob("window", window),
            "provider": native_blob("provider", provider), "transport": native_blob("transport", transport),
            "completed_ns": str(session.ready_budget.now_ns()), "result": "READY"}
        restoration = proof("RESTORATION", self._restoration_payload)
        absences = {}
        for kind, native in (("PROVIDER", provider), ("MARKET_TRANSPORT", transport)):
            self._absence_native[kind] = canonical(native)
            absences[kind] = proof("ABSENCE", {"identity": prefix + "-absence-" + kind, "process": process,
                "kind": kind, "native": native_blob("absence-" + kind, native), "active": "0", "retained_leases": "0",
                "callbacks": "0", "unresolved_cleanup": "0", "cleanup": "COMPLETE",
                "observed_ns": str(session.ready_budget.now_ns())})
        self.verify_native_binding()
        intent = session.chain["CHILD_INTENT"]["payload"]
        self._receipt = {"slot": intent["slot"], "transaction": intent["transaction"], "guard": session.chain["CLAIM"]["payload"]["guard"],
            "intent": record_ref(session.chain["CHILD_INTENT_RAW"]), "child_started": record_ref(session.chain["CHILD_STARTED_RAW"]),
            "consumption": record_ref(session.consumption_raw), "startup": record_ref(session.startup_context_raw),
            "runtime": process, "ready_ns": str(session.ready_budget.now_ns()), "restoration": restoration,
            "source": source, "capability": capability, "provider_absence": absences["PROVIDER"],
            "transport_absence": absences["MARKET_TRANSPORT"], "execution_owner": intent["execution_owner"]}
        from kronos.common import failed_fenced_schema as schema
        schema.validate_payload("READY_RECEIPT", self._receipt)
        session.ready_budget.check()
        return dict(self._receipt)


def run_native_guard_admission(context):
    """Current C's read-only full historical gate before ordinary product fork."""
    from .failed_fenced_recovery import NativeSemanticContext
    if (type(context) is not NativeSemanticContext or context.exchange.stage!='GUARD_ADMISSION'
            or context.exchange._body['controller_capability'] is not None
            or not hasattr(context,'guard_applicability')):
        raise RecoveryStartupError('RECOVERY_NATIVE_STATIC_READER_REQUIRED')
    result=guard_admission(codec=context.codec,store=context.store,registry=context.registry,
        applicability=context.guard_applicability,budget=context.budget)
    context.exchange.native_call('DONE',{})
    return result


def capture_native_package_fact(registry, bundle, expected_identity, role, *, budget):
    """Actual native sealed package fact, inside the counted original helper.

    The signature Blob is the unchanged native CodeResources artifact after
    strict verification, not a fabricated success report. Every byte must
    already be retained by the independent offline preparation publisher.
    """
    from tools.macos import package_launcher
    from .failed_fenced_recovery import EvidenceRegistry, RecoveryBudget, blob_ref, MAX_RECORD
    if (type(registry) is not EvidenceRegistry or type(budget) is not RecoveryBudget
            or registry.preparation.record['mode']!='ORIGINAL' or budget.clock!=registry.codec.clock
            or role not in {'INSTALLED','ROLLBACK'}):
        raise RecoveryStartupError('RECOVERY_PACKAGE_FACT_CONTEXT')
    budget.check()
    package_launcher.verify(bundle,expected_identity,budget=budget)
    rows=package_launcher.manifest(bundle,budget=budget)
    raw=package_launcher.canonical(rows)
    if sha256(raw).hexdigest()!=expected_identity:
        raise RecoveryStartupError('RECOVERY_PACKAGE_FACT_CHANGED')
    native={item['path']:item for item in rows}
    selected=[row for row in registry.preparation.rows.values()
        if row['purpose']=='ARTIFACT' and row['authority']=='CA'
        and row['bindings']['package']['hash']==expected_identity
        and row['bindings']['executable']['hash']==native[package_launcher.BINARY]['sha256']]
    if len(selected)!=1:
        raise RecoveryStartupError('RECOVERY_PACKAGE_ARTIFACT_AMBIGUOUS')
    row=selected[0];manifest=row['bindings']['package'];executable=row['bindings']['executable']
    executable_raw=package_launcher.read_governed_member(bundle,package_launcher.BINARY,
        registry.store.read_blob(executable),budget=budget)
    signature_path='Contents/_CodeSignature/CodeResources'
    signature_hash=native[signature_path]['sha256']
    # The approved native package manifest selects the retained signature bytes.
    # No replaced filesystem member determines its own read bound.
    signature_expected=registry.store._read(('blobs',),signature_hash+'.blob',16*MAX_RECORD+1)
    if sha256(signature_expected).hexdigest()!=signature_hash:
        raise RecoveryStartupError('RECOVERY_PACKAGE_RETAINED_FACT_CHANGED')
    signature_raw=package_launcher.read_governed_member(bundle,signature_path,signature_expected,budget=budget)
    signature=blob_ref('native-'+role.lower()+'-CodeResources',signature_raw)
    if (registry.store.read_blob(manifest)!=raw or registry.store.read_blob(executable)!=executable_raw
            or registry.store.read_blob(signature)!=signature_raw
            or package_launcher.manifest(bundle,budget=budget)!=rows):
        raise RecoveryStartupError('RECOVERY_PACKAGE_RETAINED_FACT_CHANGED')
    return dict(identity='native-package-'+role.lower()+'-'+expected_identity,
        manifest=manifest,executable=executable,signature=signature,artifact_approval=row['identity'],
        role=role,verified_ns=str(budget.check()))


def _verify_current_package_bytes(registry,bundle,payload,budget):
    """Reobserve exact retained bytes; never restamp a prepared package fact."""
    from tools.macos import package_launcher
    budget.check()
    package_launcher.verify(bundle,payload['manifest']['hash'],budget=budget)
    rows=package_launcher.manifest(bundle,budget=budget)
    if (registry.store.read_blob(payload['manifest'])!=package_launcher.canonical(rows)
            or registry.store.read_blob(payload['executable'])!=package_launcher.read_governed_member(
                bundle,package_launcher.BINARY,registry.store.read_blob(payload['executable']),budget=budget)
            or registry.store.read_blob(payload['signature'])!=package_launcher.read_governed_member(
                bundle,'Contents/_CodeSignature/CodeResources',registry.store.read_blob(payload['signature']),budget=budget)
            or package_launcher.manifest(bundle,budget=budget)!=rows):
        raise RecoveryStartupError('RECOVERY_CURRENT_PACKAGE_CHANGED')
    budget.check()


def verify_current_package_facts(registry,installed_ref,rollback_ref,*,budget):
    """Actual counted recovery checks precede any claim or product effect."""
    from .failed_fenced_recovery import EvidenceRegistry,RecoveryBudget
    from tools.runtime_source_gate import CANONICAL
    from tools.macos import package_launcher
    if (type(registry) is not EvidenceRegistry or type(budget) is not RecoveryBudget
            or registry.preparation.record['mode']!='RECOVERY' or registry.codec.clock!=budget.clock):
        raise RecoveryStartupError('RECOVERY_CURRENT_PACKAGE_CONTEXT')
    installed=registry.verify_blob(installed_ref,'PACKAGE')['payload']
    rollback=registry.verify_blob(rollback_ref,'PACKAGE')['payload']
    if (installed['role']!='INSTALLED' or rollback['role']!='ROLLBACK'
            or installed['manifest']['hash']==rollback['manifest']['hash']):
        raise RecoveryStartupError('RECOVERY_CURRENT_PACKAGE_ROLES')
    original=registry.preparation.original
    rows=[row for row in original.rows.values() if row['purpose']=='ORIGINAL_OPERATION' and row['authority']=='SPONSOR']
    if len(rows)!=1:raise RecoveryStartupError('RECOVERY_ORIGINAL_FACT_OPERATION_AMBIGUOUS')
    binding=rows[0]['bindings']
    _verify_current_package_bytes(registry,CANONICAL,installed,budget)
    if binding['operation_kind']=='ORDINARY':
        with package_launcher.retained_install_package({rollback['manifest']['hash']},budget=budget) as selected:
            if selected is None:raise RecoveryStartupError('RECOVERY_CURRENT_ROLLBACK_MISSING')
            _verify_current_package_bytes(registry,selected[0],rollback,budget)
    elif binding['operation_kind']=='FAILED_ACTIVE':
        permission=_native_json(registry.store.read_blob(binding['permission']))
        if (type(permission) is not dict or type(permission.get('rollback_bundle')) is not str
                or permission.get('installed_package_identity')!=installed['manifest']['hash']
                or permission.get('rollback_package_identity')!=rollback['manifest']['hash']):
            raise RecoveryStartupError('RECOVERY_ORIGINAL_PACKAGE_DESCRIPTOR_REQUIRED')
        _verify_current_package_bytes(registry,permission['rollback_bundle'],rollback,budget)
    else:raise RecoveryStartupError('RECOVERY_ORIGINAL_PACKAGE_DESCRIPTOR_REQUIRED')
    budget.check()


def run_native_original_facts(context):
    """Four unsigned prospective facts, never a recovery grant or L wrapper.

    Ordinary preparation supplies approved artifact bytes, not a rollback path.
    Only the installer's fixed retained-exchange layout can locate an ordinary
    rollback package. FAILED_ACTIVE continues to use its existing closed native
    permission. Missing ordinary facts leave ordinary shutdown unenrolled for
    this later recovery; ambiguity and unsafe retained state are denials.
    """
    from contextlib import ExitStack
    import re
    from .failed_fenced_recovery import NativeSemanticContext, canonical_bytes, blob_ref, _check_payload, MAX_RECORD
    from .failed_fenced_compatibility import capture_native_compatibility_facts
    from tools.runtime_source_gate import CANONICAL
    from tools.macos import package_launcher
    if (type(context) is not NativeSemanticContext or context.registry.preparation.record['mode']!='ORIGINAL'
            or context.exchange.stage!='PREPARATION'):
        raise RecoveryStartupError('RECOVERY_ORIGINAL_FACT_CONTEXT')
    registry,store,budget,exchange=context.registry,context.store,context.budget,context.exchange
    prep=registry.preparation
    operations=[r for r in prep.rows.values() if r['purpose']=='ORIGINAL_OPERATION' and r['authority']=='SPONSOR']
    if len(operations)!=1:
        raise RecoveryStartupError('RECOVERY_ORIGINAL_FACT_OPERATION_AMBIGUOUS')
    binding=operations[0]['bindings']
    ordinary=binding['operation_kind']=='ORDINARY'
    with ExitStack() as retained:
        if ordinary:
            installed_identity=prep.record['launcher_package']['hash']
            candidates={r['bindings']['package']['hash'] for r in prep.rows.values()
                if r['purpose']=='ARTIFACT' and r['authority']=='CA'
                and r['bindings']['package']['hash']!=installed_identity}
            if not candidates:return ()
            selected=retained.enter_context(package_launcher.retained_install_package(candidates,budget=budget))
            if selected is None:return ()
            rollback_bundle,rollback_identity=selected
            successor_revision=None
        else:
            permission=_native_json(store.read_blob(binding['permission']))
            if (binding['operation_kind']!='FAILED_ACTIVE' or type(permission) is not dict
                    or any(type(permission.get(key)) is not str for key in
                        ('rollback_bundle','installed_package_identity','rollback_package_identity','successor_revision'))):
                raise RecoveryStartupError('RECOVERY_ORIGINAL_PACKAGE_DESCRIPTOR_REQUIRED')
            installed_identity=permission['installed_package_identity']
            rollback_identity=permission['rollback_package_identity']
            rollback_bundle=permission['rollback_bundle']
            successor_revision=permission['successor_revision']
        if installed_identity==rollback_identity:
            raise RecoveryStartupError('RECOVERY_ORIGINAL_ROLLBACK_NOT_DISTINCT')
        # Exact static root plans select reviewed targets; no newest-file rule,
        # invented permission field or request-supplied artifact is accepted.
        fd=store._dir(('blobs',))
        try:names=sorted(os.listdir(fd))
        finally:os.close(fd)
        if len(names)>4096:
            raise RecoveryStartupError('RECOVERY_ORIGINAL_FACT_BLOB_BOUND')
        plans=[];total=0
        for name in names:
            budget.check()
            if re.fullmatch(r'[0-9a-f]{64}\.blob',name) is None:
                raise RecoveryStartupError('RECOVERY_ORIGINAL_FACT_BLOB_NAME')
            raw=store._read(('blobs',),name,16*MAX_RECORD+1);total+=len(raw)
            if total>64*MAX_RECORD or sha256(raw).hexdigest()!=name[:-5]:
                raise RecoveryStartupError('RECOVERY_ORIGINAL_FACT_BYTES_BOUND')
            try:value=_native_json(raw)
            except (ValueError,TypeError):continue
            if (type(value) is not dict or value.get('kind')!='RESTORATION_PLAN'
                    or type(value.get('payload')) is not dict
                    or successor_revision is not None and value['payload'].get('revision')!=successor_revision):
                continue
            reference=blob_ref(value['payload']['identity'],raw)
            checked=registry.verify_blob(reference,'RESTORATION_PLAN')['payload']
            row=prep.approval(checked['approval'],purpose='ARTIFACT',authority='CA')
            if row['bindings']['bootstrap_plan'] is not None:
                plans.append((row['identity'],reference))
        if not plans and ordinary:return ()
        if len(plans)!=1:
            raise RecoveryStartupError('RECOVERY_ORIGINAL_FACT_TARGET_AMBIGUOUS')
        target,compatibility=capture_native_compatibility_facts(registry,binding['source'],*plans[0],budget=budget)
        installed=capture_native_package_fact(registry,CANONICAL,installed_identity,'INSTALLED',budget=budget)
        rollback=capture_native_package_fact(registry,rollback_bundle,rollback_identity,'ROLLBACK',budget=budget)
    # Retained pathname/inode checks finish before the first factual output.
    def retain(kind,payload):
        budget.check();_check_payload(kind,payload,True)
        raw=canonical_bytes(payload)
        response=exchange.native_call('FACT',{'kind':kind,'payload':payload})
        expected=blob_ref(payload['identity'],raw)
        if response!={'fact':expected} or store.read_blob(expected)!=raw:
            raise RecoveryStartupError('RECOVERY_ORIGINAL_FACT_READBACK_CHANGED')
        budget.check();return expected
    target_ref=retain('TARGET_ARTIFACT',target)
    compatibility=dict(compatibility,successor=target_ref)
    return (target_ref,retain('PACKAGE',installed),retain('PACKAGE',rollback),retain('COMPATIBILITY',compatibility))


def _read_recovery_bound_record(store, codec, reference, *, purpose, budget):
    """Read the approval-bound original record at its sole fixed location.

    RECOVERY_OPERATION uses Blob descriptors to bind exact retained bytes.
    TERMINAL and journal heads remain records; this reader never copies them
    into blobs, searches arbitrary kinds, repairs files, or grants authority.
    The actual codec still authenticates the selected closed record.
    """
    from kronos.common.failed_fenced_recovery import RecoveryError, _check_type
    _check_type('Blob', reference)
    kinds = {'TERMINAL': ('TERMINAL',),
             'JOURNAL_HEAD': ('OBLIGATION', 'CLEANUP')}.get(purpose)
    if kinds is None:
        raise RecoveryStartupError('RECOVERY_NATIVE_RECORD_PURPOSE')
    matches = []
    for kind in kinds:
        budget.check()
        try:
            raw = store.resolve({'kind': kind, 'hash': reference['hash']})
        except RecoveryError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                continue
            raise
        if len(raw) != int(reference['bytes']) or sha256(raw).hexdigest() != reference['hash']:
            raise RecoveryStartupError('RECOVERY_NATIVE_RECORD_BINDING_CHANGED')
        matches.append((raw, codec.decode(raw, kind)))
    budget.check()
    if len(matches) != 1:
        raise RecoveryStartupError('RECOVERY_NATIVE_RECORD_MISSING_OR_AMBIGUOUS')
    return matches[0]


def run_native_recovery(context):
    """Fixed keyless recovery driver on the original C-owned private exchange.

    The helper proposes closed payloads; only the actual C controller authenticates,
    signs, reserves, exchanges, forks or grants. Every returned publication is
    decoded and compared before its next dependent operation. No role key enters
    this driver and no caller may substitute proof validators or transports.
    """
    from kronos.common.failed_fenced_recovery import (NativeSemanticContext,
        canonical_bytes, decode_canonical, record_ref, blob_ref, _as_blob,
        _check_payload, _semantics, _verify_scope_approvals, slot_key, MAX_RECORD)
    if type(context) is not NativeSemanticContext:
        raise RecoveryStartupError('RECOVERY_NATIVE_CONTEXT_REQUIRED')
    exchange,codec,store,registry,budget=(context.exchange,context.codec,context.store,
        context.registry,context.budget)
    exchange.require_current()
    prep=registry.preparation
    if prep.record['mode']!='RECOVERY' or exchange.stage!='RECOVERY_CLAIM':
        raise RecoveryStartupError('RECOVERY_NATIVE_RECOVERY_STAGE_REQUIRED')
    rows=[r for r in prep.rows.values() if r['purpose']=='RECOVERY_OPERATION' and r['authority']=='SPONSOR']
    if len(rows)!=1:
        raise RecoveryStartupError('RECOVERY_NATIVE_OPERATION_SELECTION')
    row=rows[0];binding=row['bindings'];lineage=prep.record['lineage']
    slot=slot_key(lineage);transaction=prep.record['attempt'];owner=exchange.operation
    if (binding['controller']!=exchange.controller or binding['lineage']!=lineage
            or binding['transaction']!=transaction or binding['slot']!=slot
            or binding['clock']!=budget.clock or not int(binding['valid_from_ns'])<=budget.origin_ns
            <=budget.check()<int(binding['valid_until_ns'])):
        raise RecoveryStartupError('RECOVERY_NATIVE_OPERATION_BINDING')
    limits={'clock':budget.clock,'origin_ns':str(budget.origin_ns),'stop_deadline_ns':str(budget.stop_deadline_ns)}
    def exact_proof(ref,kind,*,subject=None,native=None):
        raw=store.read_blob(ref);evidence=registry.proof_evidence(raw)
        checked=registry.verify(evidence,kind,subject=subject,context=native or {})
        if _as_blob(evidence)!=ref:
            raise RecoveryStartupError('RECOVERY_NATIVE_PROOF_REFERENCE_CHANGED')
        return evidence,checked['payload']
    def publish(kind,payload,*,external=False,reserve=False,native=None):
        budget.check();_check_payload(kind,payload,external);_semantics(kind,payload)
        if external:
            unsigned={'kind':kind,'payload':payload,'role':'LAUNCHER','issuer':exchange.controller,
                'clock':codec.clock,'issued_ns':str(budget.check())}
            registry._issuer(unsigned,None,native or {});registry._validate(unsigned,native or {})
        response=exchange.native_call('RESERVE' if reserve else 'PUBLISH',
            {'kind':kind,'external':external,'payload':payload})
        if type(response) is not dict or set(response)!={'raw'}:
            raise RecoveryStartupError('RECOVERY_NATIVE_PUBLICATION_RESPONSE')
        raw=bytes.fromhex(response['raw'])
        checked=codec.decode_proof(raw,kind) if external else codec.decode(raw,kind)
        if checked['payload']!=payload or checked['role']!='LAUNCHER' or not budget.origin_ns<=int(checked['issued_ns'])<=budget.check():
            raise RecoveryStartupError('RECOVERY_NATIVE_PUBLICATION_CHANGED')
        if external:
            evidence=registry.proof_evidence(raw)
            registry.verify(evidence,kind,context=native or {})
            if store.read_blob(evidence)!=raw:raise RecoveryStartupError('RECOVERY_NATIVE_PUBLICATION_READBACK')
            return evidence,raw
        if kind!='COMPOSITION_AUTHORITY' and store.resolve(record_ref(raw))!=raw:
            raise RecoveryStartupError('RECOVERY_NATIVE_PUBLICATION_READBACK')
        return record_ref(raw),raw
    def records(kind):
        descriptor=store._dir(('records',))
        try:names=sorted(os.listdir(descriptor))
        finally:os.close(descriptor)
        if len(names)>4096:raise RecoveryStartupError('RECOVERY_NATIVE_RECORD_BOUND')
        result=[]
        for name in names:
            budget.check()
            if not name.startswith(kind+'-') or not name.endswith('.json'):continue
            raw=store._read(('records',),name)
            if name!=kind+'-'+sha256(raw).hexdigest()+'.json':raise RecoveryStartupError('RECOVERY_NATIVE_RECORD_FILENAME')
            value=codec.decode(raw,kind)
            if value['payload'].get('lineage')==lineage:result.append((raw,value['payload']))
        return result
    # One closed read-only traversal: full source checks bracket every
    # authenticated leaf; no native effect can escape before exit validation.
    with exchange._readonly_validation(), registry._composition_validation(budget.check):
        terminal_raw,terminal_record=_read_recovery_bound_record(store,codec,binding['terminal'],purpose='TERMINAL',budget=budget)
        terminal=terminal_record['payload']
        original_raw=store.resolve(terminal['original']);original=codec.decode(original_raw,'ORIGINAL')['payload']
        if terminal['lineage']!=lineage or original['lineage']!=lineage:
            raise RecoveryStartupError('RECOVERY_NATIVE_ORIGINAL_CHANGED')
        # SOURCE must precede any historical executor verification.
        for name,kind in (('source','SOURCE'),('capability','CAPABILITY'),('control','CONTROL_BINDING'),
                ('authorization','ORIGINAL_AUTHORITY'),('ticket_roster','FENCE_ROSTER')):
            registry.verify(original[name],kind,context={'mode':'ORIGINAL'})
        executors=[item for item in records('EXECUTOR') if item[1]['original']==terminal['original'] and item[1]['state']=='TERMINATED']
        if len(executors)!=1:raise RecoveryStartupError('RECOVERY_NATIVE_ORIGINAL_EXECUTOR_UNRESOLVED')
        executor_raw,executor=executors[0]
        for name in ('original_controller','no_child_start','no_consumption'):
            registry.verify(executor[name],'ORIGINAL_CONTROLLER',context={'mode':'ORIGINAL'})
        registry.verify(executor['completion'],'EXECUTOR_TERMINATION',context={'mode':'ORIGINAL'})
        heads={'OBLIGATION':[],'CLEANUP':[]}
        for reference in binding['journal_heads']:
            raw,journal_record=_read_recovery_bound_record(store,codec,reference,purpose='JOURNAL_HEAD',budget=budget)
            kind=journal_record['kind'];payload=journal_record['payload']
            if (payload.get('lineage',lineage)!=lineage or payload.get('predecessor',lineage['predecessor'])!=lineage['predecessor']):
                raise RecoveryStartupError('RECOVERY_NATIVE_JOURNAL_LINEAGE')
            heads[kind].append(record_ref(raw))
        original_binding={'lineage':lineage,'original':terminal['original'],'terminal':record_ref(terminal_raw),
            'obligations':sorted(heads['OBLIGATION'],key=lambda x:(x['kind'],x['hash'])),
            'cleanup':sorted(heads['CLEANUP'],key=lambda x:(x['kind'],x['hash'])),'executor':record_ref(executor_raw)}
        target,target_payload=exact_proof(binding['target'],'TARGET_ARTIFACT')
        installed,_=exact_proof(binding['installed_package'],'PACKAGE')
        rollback,_=exact_proof(binding['rollback_package'],'PACKAGE')
        verify_current_package_facts(registry,binding['installed_package'],binding['rollback_package'],budget=budget)
        compatibility,_=exact_proof(binding['compatibility'],'COMPATIBILITY')
        capability,_=exact_proof(exchange._body['controller_capability'],'CONTROLLER_CAPABILITY')
        approvals=[]
        for authority in ('CA','EA-INTRADAY','EA-SWING','PCP'):
            selected=[r for r in prep.rows.values() if r['authority']==authority and r['purpose']=='OWNER_SCOPE']
            if len(selected)!=1:raise RecoveryStartupError('RECOVERY_NATIVE_SCOPE_APPROVAL')
            approvals.append(_interface_evidence(authority,selected[0]['artifact']))
        _verify_scope_approvals(registry,approvals)
        artifact=prep.approval(target_payload['approval'],purpose='ARTIFACT',authority='CA')
        artifacts=_interface_evidence('CA',artifact['artifact'])
        registry.verify(artifacts,'ARTIFACT_APPROVAL')
        scope=original['owner_scope'];registry.verify(scope,'SCOPE')
    authority_payload={'identity':'recovery-authority-'+transaction,'approval':row['identity'],
        'preparation':prep.pin['preparation'],**{k:binding[k] for k in ('service','lineage','slot','transaction',
        'original_reservation','terminal','journal_heads','predecessor_source','predecessor_capability',
        'installed_package','rollback_package','compatibility','diagnosis','interface','scope','valid_from_ns','valid_until_ns','clock')},
        'successor_source':binding['target'],'successor_capability':binding['target']}
    authorization,_=publish('RECOVERY_AUTHORITY',authority_payload,external=True)
    guard,_=publish('GUARD',{'slot':slot,'service':prep.record['service'],'binding':original_binding,
        'transaction':transaction,'authorization':authorization,'limits':limits,'scope':scope,'artifacts':artifacts},reserve=True)
    # Endpoint is the original P producer's actual configured/listening socket;
    # its exact authority is discovered only in the fixed retained blob estate.
    # Discovery reads the complete bounded estate under the same read-only
    # source boundary; every file remains freshly read and authenticated.
    with exchange._readonly_validation(), registry._composition_validation(budget.check):
        descriptor=store._dir(('blobs',))
        try:names=sorted(os.listdir(descriptor))
        finally:os.close(descriptor)
        endpoints=[];size=0
        if len(names)>4096:raise RecoveryStartupError('RECOVERY_NATIVE_ENDPOINT_BOUND')
        for name in names:
            budget.check();raw=store._read(('blobs',),name,16*MAX_RECORD+1);size+=len(raw)
            if size>64*MAX_RECORD:raise RecoveryStartupError('RECOVERY_NATIVE_ENDPOINT_BYTES_BOUND')
            try:value=decode_canonical(raw)
            except ValueError:continue
            if type(value) is dict and value.get('kind')=='ENDPOINT_CONFIGURATION' and value.get('payload',{}).get('process')==lineage['predecessor']:
                evidence=registry.proof_evidence(raw);p=registry.verify(evidence,'ENDPOINT_CONFIGURATION')['payload']
                endpoints.append({'host':p['host'],'port':p['port'],'configuration':evidence})
        if len(endpoints)!=1:raise RecoveryStartupError('RECOVERY_NATIVE_ENDPOINT_AMBIGUOUS')
    claim,claim_raw=publish('CLAIM',{'slot':slot,'guard':guard,'transaction':transaction,'binding':original_binding,
        'authorization':authorization,'scope_approvals':approvals,'control_challenge':os.urandom(32).hex(),
        'launcher':exchange.controller,'launcher_capability':capability,'endpoint':endpoints[0],'limits':limits,
        'successor_source':target,'successor_capability':target,'installed_package':installed,
        'rollback_package':rollback,'compatibility':compatibility},reserve=True)
    response=exchange.native_call('EXCHANGE',{})
    if type(response) is not dict or set(response)!={'ack','received_ns'}:raise RecoveryStartupError('RECOVERY_NATIVE_ACK_RESPONSE')
    ack_raw=bytes.fromhex(response['ack']);ack=codec.decode(ack_raw,'ACK')['payload'];received=int(response['received_ns'])
    if (ack['claim']!=claim or ack['slot']!=slot or ack['transaction']!=transaction
            or ack['predecessor']!=lineage['predecessor'] or ack['control_challenge']!=codec.decode(claim_raw)['payload']['control_challenge']
            or ack['recovery_owners']!='0' or ack['release']!='CONFIRMED' or ack['deadline']!='WITHIN'
            or not int(ack['publication_complete_ns'])<=int(ack['released_ns'])<=int(ack['ack_ns'])<=received<=budget.check()
            or int(ack['ack_ns'])>=int(ack['work_deadline_ns']) or int(ack['stop_deadline_ns'])!=budget.stop_deadline_ns):
        raise RecoveryStartupError('RECOVERY_NATIVE_ACK_INVALID')
    observation,observation_raw=publish('OBSERVATION',{'slot':slot,'transaction':transaction,'claim':claim,
        'ack':record_ref(ack_raw),'ack_bytes':ack_raw.hex(),'launcher':exchange.controller,'received_ns':str(received),
        'verified_ns':str(budget.check()),'limits':limits,'execution_owner':owner})
    native_context={'CLAIM':codec.decode(claim_raw)}
    probes=[]
    for kind in ('PROCESS_EXIT','LISTENER_ABSENT'):
        response=exchange.native_call('PROBE',{'kind':kind,'subject':lineage['predecessor']})
        raw=bytes.fromhex(response['raw']);evidence=registry.proof_evidence(raw)
        proof=registry.verify(evidence,'PLATFORM_OBSERVATION',subject=lineage['predecessor'],context=native_context)
        if proof['payload']['kind']!=kind or proof['payload']['result']!=('EXITED' if kind=='PROCESS_EXIT' else 'ABSENT'):
            raise RecoveryStartupError('RECOVERY_NATIVE_EXIT_UNPROVEN')
        probes.append((evidence,proof['payload']))
    exit_ref,_=publish('EXIT_PROOF',{'slot':slot,'transaction':transaction,'observation':observation,
        'predecessor':lineage['predecessor'],'exited_ns':probes[0][1]['observed_ns'],
        'listener_absent_ns':probes[1][1]['observed_ns'],'process_evidence':probes[0][0],
        'listener_evidence':probes[1][0],'limits':limits,'execution_owner':owner})
    owner_proof=codec.decode(store.resolve(ack['owner_proof']),'OWNER_PROOF')['payload']
    intent,intent_raw=publish('CHILD_INTENT',{'slot':slot,'transaction':transaction,'claim':claim,
        'observation':observation,'exit_proof':exit_ref,'child_nonce':os.urandom(32).hex(),
        'successor_source':target,'successor_capability':target,'installed_package':installed,
        'checkpoint':owner_proof['checkpoint'],'limits':limits,'execution_owner':owner,
        'bootstrap_owner':'bootstrap-'+transaction},reserve=True)
    with exchange._readonly_validation(), registry._composition_validation(budget.check):
        chain=validate_recovery_chain(codec,store,registry,intent_raw,slot=slot,budget=budget)
    fork=exchange.native_call('FORK',{})
    if type(fork) is not dict or set(fork)!={'child','fork_enter_ns','fork_return_ns','ready_deadline_ns'}:
        raise RecoveryStartupError('RECOVERY_NATIVE_FORK_RESPONSE')
    enter,returned,ready=(int(fork[k]) for k in ('fork_enter_ns','fork_return_ns','ready_deadline_ns'))
    if not budget.origin_ns<=enter<=returned<=budget.check() or ready!=enter+120_000_000_000:
        raise RecoveryStartupError('RECOVERY_NATIVE_FORK_BUDGET')
    bundle=store.read_bootstrap(slot)
    child_raw=bundle['identity'];child_identity=codec.decode(child_raw,'CHILD_IDENTITY')['payload']
    if (child_identity['child']!=fork['child'] or child_identity['parent']!=exchange.controller
            or child_identity['intent']!=intent or child_identity['child_nonce']!=codec.decode(intent_raw)['payload']['child_nonce']):
        raise RecoveryStartupError('RECOVERY_NATIVE_CHILD_IDENTITY_CHANGED')
    actual_bootstrap=codec.decode_proof(bundle['proof'],'BOOTSTRAP_IDENTITY')
    if registry.proof_evidence(bundle['proof'])!=child_identity['bootstrap']:
        raise RecoveryStartupError('RECOVERY_NATIVE_BOOTSTRAP_PUBLICATION_CHANGED')
    native_child={'observed_child':fork['child'],'observed_parent':exchange.controller,
        'executing_bootstrap_modules':tuple((r['name'],r['digest']) for r in actual_bootstrap['payload']['loaded_bootstrap'])}
    # These are the actual qualified S producer's authenticated loaded-byte
    # receipt, independently matched to C's real child PID/birth and target.
    with exchange._readonly_validation(), registry._composition_validation(budget.check):
        bootstrap=registry.verify(child_identity['bootstrap'],'BOOTSTRAP_IDENTITY',subject=fork['child'],
            context={**chain,**native_child})
    parent_response=exchange.native_call('PROBE',{'kind':'CANONICAL_PARENT','subject':exchange.controller})
    parent_evidence=registry.proof_evidence(bytes.fromhex(parent_response['raw']))
    with exchange._readonly_validation(), registry._composition_validation(budget.check):
        registry.verify(parent_evidence,'PLATFORM_OBSERVATION',subject=exchange.controller,context=chain)
    started,started_raw=publish('CHILD_STARTED',{'slot':slot,'transaction':transaction,'intent':intent,
        'child_identity':record_ref(child_raw),'child':fork['child'],'child_nonce':child_identity['child_nonce'],
        'fork_enter_ns':str(enter),'fork_return_ns':str(returned),'ready_deadline_ns':str(ready),
        'parent':exchange.controller,'kernel_parent':parent_evidence})
    with exchange._readonly_validation(), registry._composition_validation(budget.check):
        validate_recovery_chain(codec,store,registry,started_raw,slot=slot,budget=budget,
            native_context=native_child)
    now=budget.check()
    grant={'slot':slot,'transaction':transaction,'claim':claim,'intent':intent,'child_started':started,
        'parent':exchange.controller,'controller_capability':capability,'child':fork['child'],
        'child_nonce':child_identity['child_nonce'],'child_started_durable_ns':str(now),
        'identity_verified_ns':str(now),'gate_ns':str(now),'stop_deadline_ns':str(budget.stop_deadline_ns),
        'ready_deadline_ns':str(ready),'decision':'GRANT_ONCE'}
    sent=exchange.native_call('SEND_GRANT',grant)
    if (type(sent) is not dict or set(sent)!={'sent_ns','fork_enter_ns','ready_deadline_ns'}
            or sent['fork_enter_ns']!=str(enter) or sent['ready_deadline_ns']!=str(ready)
            or not now<=int(sent['sent_ns'])<=budget.check()):
        raise RecoveryStartupError('RECOVERY_NATIVE_GRANT_LATE')
    # Native C owns the one-way READY observation transition and its whitelist.
    # The original stop remains immutable; this call grants no new operation.
    exchange.begin_ready_observation()
    budget=exchange.budget
    response=exchange.native_call('WAIT_READY',{})
    if type(response) is not dict or set(response)!={'payload'}:
        raise RecoveryStartupError('RECOVERY_NATIVE_READY_RESPONSE')
    receipt=response['payload'];_check_payload('READY_RECEIPT',receipt)
    if receipt['runtime']!=fork['child'] or receipt['child_started']!=started or int(receipt['ready_ns'])>=ready:
        raise RecoveryStartupError('RECOVERY_NATIVE_READY_IDENTITY_CHANGED')
    # The response is an unsigned proposal. The actual immutable S chain is the
    # evidence; no boolean READY field or proposal can replace its validation.
    consumed=store.resolve(receipt['consumption']);startup=store.resolve(receipt['startup'])
    consume=codec.decode(consumed,'CONSUMPTION')['payload'];startup_record=codec.decode(startup,'STARTUP_CONTEXT')['payload']
    if (consume['consumer']!=fork['child'] or startup_record['runtime']!=fork['child']
            or consume['child_started']!=started or startup_record['consumption']!=receipt['consumption']
            or not int(consume['authority_received_ns'])<=int(consume['authority_verified_ns'])<int(grant['stop_deadline_ns'])
            or int(consume['consumed_ns'])>=ready):
        raise RecoveryStartupError('RECOVERY_NATIVE_CONSUMPTION_UNPROVEN')
    with exchange._readonly_validation(), registry._composition_validation(exchange.budget.check):
        ready_context=validate_recovery_chain(codec,store,registry,startup,slot=slot,budget=exchange.budget,
            native_context=native_child)
    for field,kind in _EVIDENCE_FIELDS['READY_RECEIPT'].items():
        registry.verify(receipt[field],kind,subject=fork['child'],context=ready_context)
    budget=exchange.budget
    ready_ref,ready_raw=publish('READY_RECEIPT',receipt)
    with exchange._readonly_validation(), registry._composition_validation(budget.check):
        validate_recovery_chain(codec,store,registry,ready_raw,slot=slot,budget=budget,
            native_context=native_child)
    exchange.native_call('DONE',{'ready':ready_ref})
    return {'stage':'READY','slot':slot,'transaction':transaction,'ready':ready_ref}


_NATIVE_SEMANTIC_RECEIVER = object()
_SEMANTIC_STAGES = frozenset({"PREPARATION", "ORIGINAL_BEFORE_EFFECT", "ORIGINAL_CLOSE",
    "GUARD_ADMISSION", "RECOVERY_CLAIM", "ACK_OBSERVE", "PRE_FORK", "CHILD_BOOTSTRAP", "READY"})
_SEMANTIC_ACTION = {"PREPARATION": "AUTHORIZE", "ORIGINAL_BEFORE_EFFECT": "DISPATCH_SHUTDOWN",
    "ORIGINAL_CLOSE": "VERIFY_HANDOFF", "GUARD_ADMISSION": "VERIFY_STATUS", "RECOVERY_CLAIM": "AUTHORIZE",
    "ACK_OBSERVE": "VERIFY_EXIT", "PRE_FORK": "CHILD_INTENT", "CHILD_BOOTSTRAP": "CHILD_FORK", "READY": "VERIFY_STATUS"}


# Cache only the fixed Darwin FFI binding, never a process observation.
# Each use still invokes proc_pidinfo and validates the complete PID/birth result.
_native_process_function = None


def _native_process_syscall():
    global _native_process_function
    if _native_process_function is None:
        import ctypes
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        function = library.proc_pidinfo
        function.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        function.restype = ctypes.c_int
        _native_process_function = function
    return _native_process_function


_native_readonly_validation = ContextVar('failed_fenced_native_readonly_validation', default=None)

class _NativeReadonlyValidation:
    def __init__(self,exchange):
        self.exchange=exchange;self.thread=get_ident();self.active=True


class NativeSemanticExchange:
    """One actual native-parent validation call, with no role key or issuer.

    This internal, ephemeral call is neither a durable protocol record nor a
    startup/composition grant. Only receive() can create it from the original
    inherited pipes and source-pinned helper executing under canonical C.
    Approval authority still comes from the independently pinned preparation.
    """
    def __init__(self, body, pipes, *, _receiver=None):
        if _receiver is not _NATIVE_SEMANTIC_RECEIVER:
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_RECEIVER_REQUIRED")
        from kronos.common.failed_fenced_recovery import RecoveryBudget, RecoveryStore, canonical_bytes, decode_canonical
        from kronos.common import failed_fenced_schema as schema
        expected = {"stage", "action", "operation", "controller", "helper", "clock", "origin_ns",
            "stop_deadline_ns", "key_id", "control_pid", "controller_capability", "admission", "dispatch",
            "authenticated", "custody", "preparations", "helper_plan", "helper_entry"}
        broker = type(body) is dict and body.get("broker") is True
        if type(body) is not dict or set(body) != expected | ({"broker"} if broker else set()) or body["stage"] not in _SEMANTIC_STAGES:
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_FIELDS_REJECTED")
        if body["action"] != _SEMANTIC_ACTION[body["stage"]]:
            raise RecoveryStartupError("RECOVERY_NATIVE_STAGE_ACTION_CHANGED")
        for key, kind in (("action", "ControllerAction"), ("operation", "Id"), ("controller", "Process"),
                ("helper", "Process"), ("clock", "Clock"), ("origin_ns", "Ns"), ("stop_deadline_ns", "Ns"),
                ("key_id", "Hash"), ("control_pid", "U64"), ("controller_capability", "Blob"),
                ("helper_plan", "Blob"), ("helper_entry", "Blob")):
            if key in {"controller_capability", "key_id", "control_pid"} and body["stage"] == "GUARD_ADMISSION" and body[key] is None:
                continue  # Read-only installation guard traversal has no operation/current key.
            schema.validate_type(kind, body[key])
        if body["stage"] == "GUARD_ADMISSION" and (body["controller_capability"] is not None
                or body["admission"] is not None or body["dispatch"] is not None
                or body["authenticated"] != [] or body["operation"] != "installation.guard"
                or body["key_id"] is not None or body["control_pid"] is not None or body["custody"] is not None):
            raise RecoveryStartupError("RECOVERY_NATIVE_READONLY_GUARD_CONTEXT")
        self._body, self._pipes = body, pipes
        self._accepted_body = canonical_bytes(body)
        self._broker = broker
        self._broker_sequence = 0
        self._broker_authenticated = {}
        self._native_grant_receipt = None
        self._ready_observation = False
        for key in ("stage", "action", "operation", "controller", "helper", "clock", "key_id", "control_pid", "admission", "dispatch", "preparations"):
            setattr(self, key, body[key])
        self.budget = RecoveryBudget(body["clock"], int(body["origin_ns"]), int(body["stop_deadline_ns"]))
        from tools.runtime_source_gate import fixed_native_estate
        self.estate = fixed_native_estate()
        self._store = RecoveryStore(self.estate)
        if type(self.preparations) is not list or len(self.preparations) not in {1, 2}:
            raise RecoveryStartupError("RECOVERY_NATIVE_PREPARATION_ROSTER")
        for index, preparation in enumerate(self.preparations):
            if (type(preparation) is not dict or set(preparation) != {"mode", "service", "installation", "lineage", "attempt", "anchors"}
                    or preparation["mode"] != ("ORIGINAL" if index == 0 else "RECOVERY")
                    or type(preparation["anchors"]) is not dict
                    or set(preparation["anchors"]) != {"pin", "approval", "catalogue", "decisions"}):
                raise RecoveryStartupError("RECOVERY_NATIVE_PREPARATION_ROSTER")
        if type(body["authenticated"]) is not list or len(body["authenticated"]) > 4096:
            raise RecoveryStartupError("RECOVERY_NATIVE_AUTHENTICATED_SET")
        self._authenticated = {}
        for row in body["authenticated"]:
            if (type(row) is not dict or set(row) != {"hash", "bytes", "kind", "external"}
                    or type(row["external"]) is not bool):
                raise RecoveryStartupError("RECOVERY_NATIVE_AUTHENTICATED_SET")
            schema.validate_type("Hash", row["hash"])
            schema.validate_type("U64", row["bytes"])
            definitions = schema.PROOF_SCHEMAS if row["external"] else schema.RECORD_SCHEMAS
            if row["kind"] not in definitions or row["hash"] in self._authenticated:
                raise RecoveryStartupError("RECOVERY_NATIVE_AUTHENTICATED_SET")
            self._authenticated[row["hash"]] = dict(row)
        if [row["hash"] for row in body["authenticated"]] != sorted(self._authenticated):
            raise RecoveryStartupError("RECOVERY_NATIVE_AUTHENTICATED_SET")
        custody = body["custody"]
        if body["stage"] != "GUARD_ADMISSION":
            if (type(custody) is not dict or set(custody) != {"key_id", "control_pid", "retained_control_hash", "retained_control_bytes", "verified_ns"}
                    or custody["key_id"] != self.key_id or custody["retained_control_hash"] != self.key_id
                    or custody["control_pid"] != self.control_pid):
                raise RecoveryStartupError("RECOVERY_NATIVE_CUSTODY_WITNESS")
            for name, rule in (("retained_control_bytes", "U64"), ("verified_ns", "Ns")):
                schema.validate_type(rule, custody[name])
            if not int(body["origin_ns"]) <= int(custody["verified_ns"]) < int(body["stop_deadline_ns"]):
                raise RecoveryStartupError("RECOVERY_NATIVE_CUSTODY_WITNESS")
        plan_raw = self._store.read_blob(body["helper_plan"])
        plan = decode_canonical(plan_raw)
        schema.validate_type("BootstrapPlan", plan)
        modules = tuple((row["name"], row["digest"]) for row in plan["modules"])
        if modules != tuple(sorted(modules)) or len(dict(modules)) != len(modules):
            raise RecoveryStartupError("RECOVERY_NATIVE_HELPER_PLAN")
        inventory = validate_source_inventory_blob(self._store.read_blob(plan["source_inventory"]))
        if (any(dict(inventory).get(name) != digest for name, digest in modules)
                or dict(inventory).get("tools.failed_fenced_launcher") != body["helper_entry"]["hash"]):
            raise RecoveryStartupError("RECOVERY_NATIVE_HELPER_PLAN")
        self._plan, self._modules = plan, dict(inventory)
        self._accepted_inventory = canonical_bytes(self._modules)
        self._accepted_plan = canonical_bytes(plan)
        self._accepted_rows = canonical_bytes(self._authenticated)
        self._pid = os.getpid()
        self._process_info = self._native_process(self._pid)
        self._parent_info = self._native_process(os.getppid())
        if self._process_info != self.helper["kernel_birth"] or self._parent_info != self.controller["kernel_birth"]:
            raise RecoveryStartupError("RECOVERY_NATIVE_PROCESS_BINDING")
        self._parent_image = self._native_image_identity(os.getppid(), self.budget)
        self.require_current()
        from tools.runtime_source_gate import canonical_parent
        canonical_parent(budget=self.budget)
        # Signature verification is performed once on the exact kernel image;
        # each later use rechecks process birth, original descriptors and clock.
        self._signature_checked = True

    @staticmethod
    def _native_image_identity(pid, budget):
        """Bind the current named file to an actual executable kernel mapping.

        proc_pidpath alone names a path; it does not prove that a subsequently
        replaced file is the image already executing. PROC_PIDREGIONPATHINFO's
        executable mapping retains the loaded vnode identity. Secure descriptor
        reads and pre/post metadata checks bind its exact current bytes too.
        """
        import ctypes
        from pathlib import Path
        class Region(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint32) for n in ("protection", "maximum", "inheritance", "flags")]
            _fields_ += [("offset", ctypes.c_uint64)]
            _fields_ += [("field" + str(n), ctypes.c_uint32) for n in range(14)]
            _fields_ += [("address", ctypes.c_uint64), ("size", ctypes.c_uint64)]
        class VStat(ctypes.Structure):
            _fields_ = [("dev", ctypes.c_uint32), ("mode", ctypes.c_uint16), ("nlink", ctypes.c_uint16),
                ("ino", ctypes.c_uint64), ("uid", ctypes.c_uint32), ("gid", ctypes.c_uint32)]
            _fields_ += [("times" + str(n), ctypes.c_int64) for n in range(8)]
            _fields_ += [("size", ctypes.c_int64), ("blocks", ctypes.c_int64)]
            _fields_ += [("stat" + str(n), ctypes.c_uint32) for n in range(4)]
            _fields_ += [("spare", ctypes.c_int64 * 2)]
        class Mapping(ctypes.Structure):
            _fields_ = [("region", Region), ("vstat", VStat), ("type", ctypes.c_int),
                ("pad", ctypes.c_int), ("fsid", ctypes.c_int32 * 2), ("path", ctypes.c_char * 1024)]
        if ctypes.sizeof(Region) != 96 or ctypes.sizeof(VStat) != 136 or ctypes.sizeof(Mapping) != 1272:
            raise RecoveryStartupError("RECOVERY_NATIVE_IMAGE_LAYOUT")
        canonical = "/Applications/KRONOS.app/Contents/MacOS/KRONOS"
        lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        lib.proc_pidinfo.restype = ctypes.c_int
        descriptor = os.open(canonical, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            before, named = os.fstat(descriptor), os.stat(canonical, follow_symlinks=False)
            stamp = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
                value.st_ctime_ns, value.st_mode, value.st_uid, value.st_gid)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_size < 1 or before.st_size > 16 * 1024 * 1024
                    or stamp(before) != stamp(named) or Path(canonical).resolve() != Path(canonical)):
                raise RecoveryStartupError("RECOVERY_NATIVE_IMAGE_FILE_CHANGED")
            address, found = 0, False
            for _ in range(4096):
                budget.check()
                value = Mapping()
                count = lib.proc_pidinfo(pid, 8, address, ctypes.byref(value), ctypes.sizeof(value))
                if count != ctypes.sizeof(value):
                    raise RecoveryStartupError("RECOVERY_NATIVE_IMAGE_MAPPING_UNAVAILABLE")
                if value.region.protection & 4 and os.fsdecode(value.path) == canonical:
                    if value.vstat.ino != before.st_ino or value.vstat.dev != before.st_dev & 0xffffffff:
                        raise RecoveryStartupError("RECOVERY_NATIVE_LOADED_IMAGE_REPLACED")
                    found = True
                    break
                following = value.region.address + value.region.size
                if following <= address or following >= 1 << 64:
                    raise RecoveryStartupError("RECOVERY_NATIVE_IMAGE_MAPPING_CHANGED")
                address = following
            if not found:
                raise RecoveryStartupError("RECOVERY_NATIVE_IMAGE_MAPPING_UNAVAILABLE")
            raw = bytearray()
            while len(raw) <= before.st_size:
                budget.check()
                part = os.read(descriptor, min(65536, before.st_size + 1 - len(raw)))
                if not part:
                    break
                raw.extend(part)
            after, named_after = os.fstat(descriptor), os.stat(canonical, follow_symlinks=False)
            if len(raw) != before.st_size or stamp(before) != stamp(after) or stamp(before) != stamp(named_after):
                raise RecoveryStartupError("RECOVERY_NATIVE_IMAGE_FILE_CHANGED")
            budget.check()
            return stamp(before), sha256(raw).hexdigest()
        finally:
            os.close(descriptor)

    @staticmethod
    def _native_process(pid):
        import ctypes
        import sys
        from tools.failed_fenced_launcher import _ProcBSDInfo
        if sys.platform != "darwin" or ctypes.sizeof(_ProcBSDInfo) != 136:
            raise RecoveryStartupError("RECOVERY_DARWIN_PLATFORM_REQUIRED")
        function = _native_process_syscall()
        value = _ProcBSDInfo()
        if function(pid, 3, 0, ctypes.byref(value), ctypes.sizeof(value)) != ctypes.sizeof(value) or value.pid != pid:
            raise RecoveryStartupError("RECOVERY_NATIVE_PROCESS_BINDING")
        return {"seconds": str(value.start_seconds), "microseconds": str(value.start_microseconds)}

    @staticmethod
    def _native_parent_image_path(pid):
        import ctypes
        buffer = ctypes.create_string_buffer(4096)
        lib = ctypes.CDLL("/usr/lib/libproc.dylib")
        lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        lib.proc_pidpath.restype = ctypes.c_int
        if lib.proc_pidpath(pid, buffer, len(buffer)) <= 0:
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_PARENT_CHANGED")
        return os.fsdecode(buffer.value)

    @classmethod
    def receive(cls, *, origin_ns, stop_deadline_ns):
        from kronos.common.failed_fenced_recovery import decode_canonical
        # These inherited values can only restrict this initial read. The exact
        # C exchange must repeat them and later prove its qualified clock.
        origin_ns, stop_deadline_ns = int(origin_ns), int(stop_deadline_ns)
        if stop_deadline_ns != origin_ns + 15_000_000_000:
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_BUDGET")
        class InitialBudget:
            def now_ns(self):
                return time.clock_gettime_ns(time.CLOCK_MONOTONIC)
            def check(self, deadline_ns=None):
                now = self.now_ns()
                if not origin_ns <= now < min(stop_deadline_ns, stop_deadline_ns if deadline_ns is None else deadline_ns):
                    raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_BUDGET")
            def remaining_seconds(self, deadline_ns=None):
                self.check(deadline_ns)
                return (min(stop_deadline_ns, stop_deadline_ns if deadline_ns is None else deadline_ns) - self.now_ns()) / 1e9
        budget = InitialBudget()
        budget.check()
        pipes = tuple((os.fstat(fd).st_dev, os.fstat(fd).st_ino) for fd in (0, 1))
        for fd in (0, 1):
            _pipe(fd)
        data, length = bytearray(), None
        while True:
            _wait(0, select.POLLIN, budget, None)
            try:
                maximum = ((1 << 20) + 5 - len(data)) if length is None else length + 4 - len(data)
                part = os.read(0, min(65536, max(1, maximum)))
            except (InterruptedError, BlockingIOError):
                continue
            budget.check()
            if not part:
                break
            data.extend(part)
            if length is None and len(data) >= 4:
                length = struct.unpack("!I", data[:4])[0]
                if not 1 <= length <= 1 << 20:
                    raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_LENGTH")
            if length is not None and len(data) > length + 4:
                raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_EXTRA")
            if length is not None and len(data) == length + 4:
                complete = decode_canonical(bytes(data[4:]))
                if type(complete) is dict and complete.get("broker") is True:
                    break
        if length is None or len(data) != length + 4:
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_TRUNCATED")
        body = decode_canonical(bytes(data[4:]))
        if int(body.get("origin_ns", "-1")) != origin_ns or int(body.get("stop_deadline_ns", "-1")) != stop_deadline_ns:
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_BUDGET_CHANGED")
        return cls(body, pipes, _receiver=_NATIVE_SEMANTIC_RECEIVER)

    def _within_readonly_validation(self):
        scope=_native_readonly_validation.get()
        return (type(scope) is _NativeReadonlyValidation and scope.active
                and scope.exchange is self and scope.thread==get_ident())

    @contextmanager
    def _readonly_validation(self):
        # Only a synchronous read-only proof traversal may share full loaded
        # image/code sweeps. It cannot release authority or publish anything.
        # No proof result is cached, and every leaf still checks live process,
        # pipes, context, budget, exact files, authentication and semantics.
        if self._within_readonly_validation():
            self.require_current()
            yield
            return
        self.require_current()
        scope=_NativeReadonlyValidation(self)
        token=_native_readonly_validation.set(scope)
        try:
            yield
        except BaseException:
            # Preserve the original denial; no successful result escapes.
            raise
        else:
            scope.active=False
            self.require_current()  # full image/code sweep before acceptance
        finally:
            scope.active=False
            _native_readonly_validation.reset(token)

    def require_current(self):
        import ctypes
        import sys
        from kronos.common.failed_fenced_recovery import canonical_bytes
        self.budget.check()
        readonly=self._within_readonly_validation()
        if (not readonly and (canonical_bytes(self._body) != self._accepted_body
                or canonical_bytes(self._plan) != self._accepted_plan
                or canonical_bytes(self._authenticated) != self._accepted_rows
                or canonical_bytes(self._modules) != self._accepted_inventory)):
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_CONTEXT_CHANGED")
        if (any(getattr(self, key) != self._body[key] for key in ("stage", "action", "operation", "controller",
                    "helper", "clock", "key_id", "control_pid", "admission", "dispatch", "preparations"))
                or self.action != _SEMANTIC_ACTION[self.stage]
                or self.budget.clock != self.clock
                or self.budget.origin_ns != int(self._body["origin_ns"])
                or self.budget.stop_deadline_ns != int(self._body["stop_deadline_ns"])):
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_CONTEXT_CHANGED")
        if (os.getpid() != self._pid or str(os.getpid()) != self.helper["pid"]
                or str(os.getppid()) != self.controller["pid"]
                or self._native_process(self._pid) != self._process_info
                or self._native_process(os.getppid()) != self._parent_info):
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_PROCESS_CHANGED")
        for fd, identity in zip((0, 1), self._pipes):
            value = os.fstat(fd)
            if not stat.S_ISFIFO(value.st_mode) or (value.st_dev, value.st_ino) != identity:
                raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_PIPE_CHANGED")
        if self._within_readonly_validation():
            self.budget.check()
            return
        if self._native_parent_image_path(os.getppid()) != "/Applications/KRONOS.app/Contents/MacOS/KRONOS":
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_PARENT_CHANGED")
        if self._native_image_identity(os.getppid(), self.budget) != self._parent_image:
            raise RecoveryStartupError("RECOVERY_NATIVE_EXCHANGE_IMAGE_CHANGED")
        # The C-owned loader executes each exact captured byte object. Reading
        # current files after execution is not accepted as a loaded-code proof.
        seen = set()
        from tools.failed_fenced_launcher import native_pinned_module
        for module in tuple(sys.modules.values()):
            specification = getattr(module, "__spec__", None)
            name = getattr(specification, "name", None)
            if type(name) is not str or not (name in {"tools", "kronos"} or name.startswith(("tools.", "kronos."))):
                continue
            if name in seen:
                continue
            if (name in {"tools", "tools.macos"} and name not in self._modules
                    and getattr(specification, "origin", None) is None
                    and getattr(module, "__file__", None) is None
                    and tuple(getattr(specification, "submodule_search_locations", ())) == ()
                    and any(key.startswith(name + ".") for key in self._modules)):
                # The approved tooling namespace executes no module body.
                # Every actual tools.* body is still independently captured.
                continue
            seen.add(name)
            payload = native_pinned_module(module, self._body["helper_plan"]["hash"])
            if self._modules.get(name) != sha256(payload).hexdigest():
                raise RecoveryStartupError("RECOVERY_NATIVE_HELPER_BYTES_UNPROVEN")
        if "tools.failed_fenced_launcher" not in seen:
            raise RecoveryStartupError("RECOVERY_NATIVE_HELPER_ENTRY_UNPROVEN")

    def authenticate(self, raw, *, external):
        self.require_current()
        from kronos.common.failed_fenced_recovery import decode_canonical
        value = decode_canonical(raw)
        digest = sha256(raw).hexdigest()
        row = self._authenticated.get(digest) or self._broker_authenticated.get(digest)
        if row is None and self._broker:
            observed = self.native_call("VERIFY", {"raw": raw.hex(), "external": external})
            expected = {"hash": digest, "bytes": str(len(raw)), "kind": value.get("kind"), "external": external}
            if observed != expected:
                raise RecoveryStartupError("RECOVERY_NATIVE_PROOF_NOT_AUTHENTICATED")
            row = self._broker_authenticated[digest] = observed
        if row is None or row["bytes"] != str(len(raw)) or row["kind"] != value.get("kind") or row["external"] is not external:
            raise RecoveryStartupError("RECOVERY_NATIVE_PROOF_NOT_AUTHENTICATED")

    def native_call(self, kind, payload):
        """One finite call to the same actual source-bound native controller.

        This private implementation channel carries no new durable schema,
        human approval or composition grant. FD3's one-frame rule is unchanged.
        A caller cannot install a transport, key, path or validation callback.
        """
        from kronos.common.failed_fenced_recovery import canonical_bytes, decode_canonical
        if self._within_readonly_validation() and kind != "VERIFY":
            raise RecoveryStartupError("RECOVERY_NATIVE_EFFECT_DURING_VALIDATION")
        if not self._broker or kind not in {"VERIFY", "FACT", "PUBLISH", "RESERVE", "PROBE", "EXCHANGE", "FORK", "SEND_GRANT", "WAIT_READY", "DONE"}:
            raise RecoveryStartupError("RECOVERY_NATIVE_BROKER_CALL_REJECTED")
        if self._ready_observation and not (kind in {"VERIFY", "WAIT_READY", "DONE"}
                or kind == "PUBLISH" and type(payload) is dict
                and payload.get("kind") == "READY_RECEIPT" and payload.get("external") is False):
            raise RecoveryStartupError("RECOVERY_NATIVE_READY_OPERATION_FORBIDDEN")
        self.require_current()
        sequence = self._broker_sequence
        self._broker_sequence += 1  # spent even if write/read fails
        request = {"context": sha256(self._accepted_body).hexdigest(), "sequence": str(sequence), "kind": kind, "payload": payload}
        raw = canonical_bytes(request)
        if not 1 <= len(raw) <= 4 << 20:
            raise RecoveryStartupError("RECOVERY_NATIVE_BROKER_BOUND")
        frame, offset = struct.pack("!I", len(raw)) + raw, 0
        while offset < len(frame):
            _wait(1, select.POLLOUT, self.budget, None)
            try:
                count = os.write(1, frame[offset:])
            except (InterruptedError, BlockingIOError):
                continue
            if count <= 0:
                raise RecoveryStartupError("RECOVERY_NATIVE_BROKER_WRITE")
            offset += count
            self.budget.check()
        data, length = bytearray(), None
        while length is None or len(data) != length + 4:
            _wait(0, select.POLLIN, self.budget, None)
            try:
                part = os.read(0, 4 - len(data) if length is None else min(65536, length + 4 - len(data)))
            except (InterruptedError, BlockingIOError):
                continue
            if not part:
                raise RecoveryStartupError("RECOVERY_NATIVE_BROKER_TRUNCATED")
            data.extend(part)
            if length is None and len(data) == 4:
                length = struct.unpack("!I", data)[0]
                if not 1 <= length <= 4 << 20:
                    raise RecoveryStartupError("RECOVERY_NATIVE_BROKER_BOUND")
            self.budget.check()
        response = decode_canonical(bytes(data[4:]))
        if (type(response) is not dict or set(response) != {"context", "sequence", "kind", "result"}
                or any(response[name] != request[name] for name in ("context", "sequence", "kind"))):
            raise RecoveryStartupError("RECOVERY_NATIVE_BROKER_RESPONSE_CHANGED")
        self.require_current()
        result = response["result"]
        if kind == "SEND_GRANT":
            if (self._native_grant_receipt is not None or type(result) is not dict
                    or set(result) != {"sent_ns", "fork_enter_ns", "ready_deadline_ns"}
                    or int(result["ready_deadline_ns"]) != int(result["fork_enter_ns"]) + 120_000_000_000
                    or not self.budget.origin_ns <= int(result["fork_enter_ns"]) <= int(result["sent_ns"]) < self.budget.stop_deadline_ns):
                raise RecoveryStartupError("RECOVERY_NATIVE_GRANT_RECEIPT_REJECTED")
            self._native_grant_receipt = canonical_bytes(result)
        return result

    def begin_ready_observation(self):
        """Observe S's result after the actual C parent sent its sole grant.

        No pre-grant operation is possible in this phase. The original origin
        and stop remain immutable; only read-only READY observation and the
        final parent receipt use the existing fork-enter plus 120-second bound.
        """
        self.require_current()
        if self._ready_observation or self._native_grant_receipt is None:
            raise RecoveryStartupError("RECOVERY_NATIVE_READY_GRANT_REQUIRED")
        from kronos.common.failed_fenced_recovery import decode_canonical
        receipt = decode_canonical(self._native_grant_receipt)
        self.budget = _NativeReadyObservationBudget(self.budget, receipt, _receiver=_NATIVE_SEMANTIC_RECEIVER)
        self._ready_observation = True
        self.require_current()

    def verify_custody(self, payload):
        self.require_current()
        if self.stage == "GUARD_ADMISSION":
            raise RecoveryStartupError("RECOVERY_NATIVE_STATIC_READER_HAS_NO_CURRENT_CUSTODY")
        witness = self._body["custody"]
        if (payload["process"]["pid"] != self.control_pid or payload["live_control"]["hash"] != self.key_id
                or payload["retained_control"]["hash"] != self.key_id
                or payload["live_control"]["bytes"] != witness["retained_control_bytes"]
                or payload["retained_control"]["bytes"] != witness["retained_control_bytes"]
                or payload["boot_id"] != self.clock["boot_id"]):
            raise RecoveryStartupError("RECOVERY_NATIVE_CUSTODY_BINDING_CHANGED")

    def verify_preparation(self, registry):
        self.require_current()
        if self.stage == "GUARD_ADMISSION":
            self._verify_static_preparation(registry)
            return
        capability = registry.verify_blob(self._body["controller_capability"], "CONTROLLER_CAPABILITY")["payload"]
        expected_phase = registry.preparation.record["mode"]
        matches = [row for row in capability["operations"] if row["action"] == self.action]
        image_stamp, image_hash = self._native_image_identity(os.getppid(), self.budget)
        if (capability["phase"] != expected_phase or capability["controller"] != self.controller
                or registry.preparation.record["controller"] != self.controller
                or capability["source_inventory"] != registry.preparation.record["launcher_source"]
                or capability["package"] != registry.preparation.record["launcher_package"]
                or capability["executable"]["hash"] != image_hash
                or capability["executable"]["bytes"] != str(image_stamp[2])
                or self._plan["source_inventory"] != capability["source_inventory"]
                or len(matches) != 1 or matches[0]["implementation"] != self._plan["source_inventory"]):
            raise RecoveryStartupError("RECOVERY_NATIVE_PREPARATION_SOURCE_CHANGED")

    def _verify_static_preparation(self, registry):
        """Read-only guard source authority; never an operation or capability."""
        image_stamp, image_hash = self._native_image_identity(os.getppid(), self.budget)
        prep = registry.preparation
        guards = [row for row in prep.rows.values() if row["authority"] == "CA"
            and row["purpose"] == "GUARD" and row["bindings"]["classification"] == "MANDATORY"
            and row["bindings"]["launcher"]["hash"] == image_hash
            and row["bindings"]["launcher"]["bytes"] == str(image_stamp[2])]
        artifacts = [row for row in prep.rows.values() if row["authority"] == "CA"
            and row["purpose"] == "ARTIFACT" and row["bindings"]["executable"]["hash"] == image_hash
            and row["bindings"]["executable"]["bytes"] == str(image_stamp[2])
            and row["bindings"]["source_inventory"] == prep.record["launcher_source"]
            and row["bindings"]["package"] == prep.record["launcher_package"]
            and row["bindings"]["bootstrap_plan"] == self._body["helper_plan"]]
        if (self._plan["source_inventory"] != prep.record["launcher_source"]
                or len(guards) != 1 or len(artifacts) != 1
                or not any(row["authority"] == "PCP" and row["purpose"] == "GUARD"
                    and row["bindings"] == guards[0]["bindings"] for row in prep.rows.values())
                or prep.record["clock"] != self.clock or self.key_id is not None
                or self.control_pid is not None or self._body["custody"] is not None):
            raise RecoveryStartupError("RECOVERY_NATIVE_STATIC_GUARD_SOURCE_CHANGED")


class _NativeReadyObservationBudget:
    """Parent observation only, created from the actual private native reply."""
    def __init__(self, stop_budget, receipt, *, _receiver=None):
        if _receiver is not _NATIVE_SEMANTIC_RECEIVER:
            raise RecoveryStartupError("RECOVERY_NATIVE_READY_RECEIVER_REQUIRED")
        self.clock = stop_budget.clock
        self.origin_ns = stop_budget.origin_ns
        self.stop_deadline_ns = stop_budget.stop_deadline_ns
        self.ready_deadline_ns = int(receipt["ready_deadline_ns"])
        self._last = int(receipt["sent_ns"])
        self._failed = False
        if (self.ready_deadline_ns != int(receipt["fork_enter_ns"]) + 120_000_000_000
                or not self.origin_ns <= int(receipt["fork_enter_ns"]) <= self._last < self.stop_deadline_ns):
            raise RecoveryStartupError("RECOVERY_NATIVE_READY_BUDGET_REJECTED")
        self.check()

    def now_ns(self):
        now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        if now < self._last:
            self._failed = True
        self._last = max(self._last, now)
        if self._failed:
            raise RecoveryStartupError("RECOVERY_NATIVE_READY_CLOCK_REJECTED")
        return now

    def check(self, deadline_ns=None):
        bound = self.ready_deadline_ns if deadline_ns is None else min(self.ready_deadline_ns, int(deadline_ns))
        now = self.now_ns()
        if self._failed or now >= bound:
            self._failed = True
            raise RecoveryStartupError("RECOVERY_NATIVE_READY_DEADLINE_EXPIRED")
        return now

    def remaining_seconds(self, deadline_ns=None):
        bound = self.ready_deadline_ns if deadline_ns is None else min(self.ready_deadline_ns, int(deadline_ns))
        return (bound - self.check(deadline_ns)) / 1_000_000_000
