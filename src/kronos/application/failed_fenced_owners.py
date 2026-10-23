"""Finite native owner adapters for the approved R3 recovery contract.

These adapters capture actual original execution.  They do not reconstruct
history, approve a source, invoke recovery callbacks, deliver notifications or
broaden the finite owner/relation catalogue.  Authentication/storage is owned by
``common.failed_fenced_recovery``.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
from functools import wraps
import json
from threading import RLock, get_ident
from uuid import uuid4

from kronos.intraday.wo09_readiness import artifact_bytes
from kronos.intraday.wo10_futures_contract import Record, encoded
from kronos.intraday.wo11_lifecycle_contract import LifecycleRecord
from kronos.intraday.failed_fenced_native_evidence import (
    CLOSED_NATIVE_CONTRACTS,
    RELATIONS,
    _require,
    source_identity,
    native_bytes,
    native_contract,
    native_identity,
    verify_native_evidence,
    _source_text,
    _decode_native,
    verify_native_peer_registration,
    verify_native_peer_fulfillment,
    verify_native_owner_result,
)
















def bind_failed_fenced_accounting(owner, accounting):
    """Called by canonical composition before its first prospective effect."""
    _require(getattr(owner, "_failed_fenced_accounting", None) is None,
             "FAILED_FENCED_NATIVE_BINDING_CONFLICT")
    _require(accounting.source_owner is owner)
    owner._failed_fenced_accounting = accounting


def prepare_effect(owner, kind, identity, value, *, previous=None, required=True):
    accounting = getattr(owner, "_failed_fenced_accounting", None)
    if accounting is None:
        return None
    return accounting.prepare(kind, identity, value, previous=previous, required=required)


def committed_effect(owner, handle, value):
    if handle is not None:
        owner._failed_fenced_accounting.committed(handle, value)


def dispatch_source(owner, kind, identity, callbacks):
    """Ordinary callback dispatch, recording actual returns when enrolled."""
    accounting = getattr(owner, "_failed_fenced_accounting", None)
    if accounting is not None and (accounting.owner, kind) in RELATIONS:
        return accounting.dispatch(kind, identity, callbacks)
    for attribute, listener, failure in callbacks:
        if listener is not None:
            try:
                listener(kind, identity)
            except Exception:
                setattr(owner, attribute, failure)


class NativeOwnerAccounting:
    """A source-owner bridge into the sole common prospective ledger.

    ``bindings`` comes from actual canonical composition before admission.  It
    contains the exact native listener object and registered inventory IDs, not
    method names discovered during recovery.  R3 never calls ``dispatch`` to
    replay a historical callback; only the original uninterrupted owner does.
    """

    def __init__(self, ledger, source_owner, owner, owner_instance, composition,
                 bindings, *, native_context):
        _require(owner in {"WO09", "WO10", "WO11"})
        self.ledger, self.source_owner = ledger, source_owner
        self.owner, self.owner_instance = owner, owner_instance
        self.composition, self.bindings = composition, dict(bindings)
        self.native_context = dict(native_context)
        self._lock = RLock()
        self._effects = {}
        self._all_effects = {}
        self._reference_active = None
        self._caller = None
        self._callers = {}
        self._reference_group = (self,)

    def bind_caller(self, owner):
        from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
        _require(self.owner == "WO11" and type(owner) is IntradayLifecycleApplication
                 and owner.store is self.source_owner and self._caller is None)
        _require(getattr(owner, "_failed_fenced_accounting", None) is None)
        _require(owner._ff_composition is self.source_owner._ff_composition)
        self._caller = owner
        owner._failed_fenced_accounting = self
        composition = owner._ff_composition
        composition._native_accounting.append(self)

    def register_caller_thread(self, owner, ticket, thread):
        from threading import Thread
        _require(owner is self._caller and type(thread) is Thread and thread.ident is None
                 and self.ledger.coordinator.is_live(ticket))
        with self._lock:
            _require(ticket.identity not in self._callers)
            self._callers[ticket.identity] = {"owner": owner, "ticket": ticket, "thread": thread,
                "phase": "REGISTERED", "handles": [], "business_complete_ns": None,
                "return_path_reached": False, "joined_ns": None}
        record_resource(owner, thread, "WORKER")

    def enter_caller(self, owner, ticket):
        from threading import current_thread
        with self._lock:
            row = self._callers[ticket.identity]
            _require(owner is self._caller and row["owner"] is owner
                     and current_thread() is row["thread"] and row["phase"] == "REGISTERED")
            row["phase"] = "BUSINESS"

    def finish_caller(self, owner, ticket):
        """Original worker, after all native writes and queue bookkeeping."""
        from threading import current_thread
        with self._lock:
            row = self._callers[ticket.identity]
            _require(owner is self._caller and current_thread() is row["thread"]
                     and row["phase"] == "BUSINESS")
            with owner._work_lock:
                eligible = (not owner._work_queue and not owner._pending_work
                    and not owner._continuity_gap_required
                    and owner._continuity_state == "COMPLETE" and owner._work_failure is None)
            if not eligible:
                self.ledger.mark_ineligible("PROVENANCE")
            row["phase"] = "REFERENCE_TAIL"
            row["business_complete_ns"] = str(self.ledger.now_ns())
            handles = tuple(row["handles"])
        # These fixed producer effects and original peers have actually returned;
        # no research handoff, closure or projection write remains in the caller.
        for handle in handles:
            failed = bool(handle.get("failed")) or not eligible
            result = self._owner_result(handle, failed=failed)
            if failed:
                self.ledger.fail_operation(handle["operation"], result, "PROVENANCE")
            else:
                self.ledger.complete_operation(handle["operation"], result)
            handle["producer_completed"] = True
        for handle in handles:
            handle["flushing"] = True
            callback = handle.get("deferred_reference")
            if callback is not None and (eligible or self.ledger.coordinator.snapshot()["state"] == "OPEN"):
                self.dispatch(handle["kind"], handle["identity"], (callback,))
            elif handle["required"]:
                proof = self._owner_result(handle, reference=True, failed=True)
                self.ledger.fail_operation(handle["reference_operation"], proof, "PROVENANCE")
                handle["reference_ticket"].release()
                self.ledger.mark_ineligible("NOTIFICATION")
            if handle["ticket"] is not ticket and self.ledger.coordinator.is_live(handle["ticket"]):
                handle["ticket"].release()
        with self._lock:
            row["phase"] = "RETURNING"

    def caller_returning(self, owner, ticket):
        from threading import current_thread
        with self._lock:
            row = self._callers[ticket.identity]
            _require(owner is row["owner"] and current_thread() is row["thread"]
                     and row["phase"] == "RETURNING")
            row["return_path_reached"] = True

    def observe_callers(self, claim_ns, budget):
        """Independent recovery observer joins the original native callers."""
        from threading import current_thread
        with self._lock:
            rows = tuple(self._callers.values())
        for row in rows:
            thread = row["thread"]
            _require(thread is not current_thread())
            if row["joined_ns"] is not None:
                _require(not thread.is_alive() and row["return_path_reached"]
                         and not self.ledger.coordinator.is_live(row["ticket"]))
                continue
            with self._lock:
                _require(row["phase"] in {"REFERENCE_TAIL", "RETURNING"}
                    and row["business_complete_ns"] is not None
                    and int(row["business_complete_ns"]) < int(claim_ns),
                    "FAILED_FENCED_WO11_CALLER_BUSINESS_ACTIVE")
            thread.join(budget.remaining_seconds(budget.work_deadline_ns))
            budget.check(budget.work_deadline_ns)
            _require(not thread.is_alive() and row["return_path_reached"]
                and not self.ledger.coordinator.is_live(row["ticket"]),
                "FAILED_FENCED_WO11_CALLER_RETURN_UNPROVEN")
            row["joined_ns"] = str(self.ledger.now_ns())

    def _native(self, value, operation, ticket, identity):
        raw = native_bytes(value)
        contract = native_contract(value)
        context = dict(self.native_context, owner=self.owner,
            owner_instance=self.owner_instance, operation=operation,
            ticket=ticket.identity, source_identity=identity)
        return self.ledger.registry.native_evidence(self.owner, contract,
            "native-" + sha256(raw).hexdigest(), raw, context)

    def prepare(self, kind, identity, value, *, previous=None, required=True):
        _require((self.owner, kind) in RELATIONS)
        caller_ticket = self.ledger.current_ticket()
        _require(caller_ticket is not None and self.ledger.coordinator.is_live(caller_ticket))
        # A long-lived native worker can publish multiple sequential effects.
        # Each semantic effect gets actual separate issued ownership; its caller
        # remains independently counted through its own final bookkeeping.
        with self._lock:
            caller = self._callers.get(caller_ticket.identity)
            if caller is not None:
                _require(caller["phase"] == "BUSINESS")
            use_caller = caller is not None and not caller["handles"]
        ticket = caller_ticket if use_caller else caller_ticket.fork(caller_ticket.kind)
        relation, reference_relation = RELATIONS[self.owner, kind]
        operation = "native-" + uuid4().hex
        source = self._native(value, operation, ticket, identity)
        previous_blob = (None if previous is None else
            self.ledger.retain_native("previous-" + operation, native_bytes(previous)))
        targets = {}
        for role, binding in self.bindings.items():
            _require(role in {"JOURNAL", "BOOKS", "WO13"})
            listener = binding.get("callable")
            attribute = {"JOURNAL": "journal_listener", "BOOKS": "book_listener",
                         "WO13": "notification_listener"}[role]
            _require(getattr(self.source_owner, attribute, None) == listener,
                     "FAILED_FENCED_NATIVE_LISTENER_CHANGED")
            targets[role] = binding
        _require("WO13" in targets)
        # Missing composition evidence or peer installation evidence must never
        # become a silent absent listener exemption.
        if kind in {"TRACK", "COMPARISON", "UNAVAILABLE"}:
            _require(set(self.native_context.get("peer_slots", {})) == {"JOURNAL", "BOOKS"})
        reference_operation = "reference-" + uuid4().hex
        effect = {"kind": relation, "identity": source_identity(identity),
            "source": source, "input": source, "target": source_identity(identity),
            "expected": source["hash"], "transition": None}
        if kind == "CURRENTNESS":
            _require(previous_blob is not None)
            effect["transition"] = source
        self.ledger.begin_operation(ticket, self.owner, self.owner_instance,
            operation, relation, effect, required_children=(reference_operation,) if required else ())
        handle = {"operation": operation, "ticket": ticket, "caller_ticket": caller_ticket, "kind": kind,
            "identity": identity, "value": value, "source": source,
            "previous": previous_blob, "effect": effect, "committed": False,
            "required": required, "reference_operation": reference_operation,
            "peers": {}, "peer_results": [], "callbacks": [], "caller": caller}
        if caller is not None:
            with self._lock:
                caller["handles"].append(handle)
        if required:
            self.ledger.coordinator.register_completion(ticket, reference_operation, "NOTIFICATION")
            child_ticket = self.ledger.coordinator.fork_completion(ticket, reference_operation)
            binding = targets["WO13"]
            reference_effect = dict(effect, kind=reference_relation,
                expected=sha256((kind + ":" + identity).encode("utf-8")).hexdigest())
            self.ledger.begin_operation(child_ticket, "WO13", binding["instance"],
                reference_operation, reference_relation, reference_effect,
                listener=binding["evidence"], parent=self.ledger.operation_head(operation))
            handle["reference_ticket"] = child_ticket
            handle["reference_effect"] = reference_effect
        for role in (("JOURNAL", "BOOKS") if kind in {"TRACK", "COMPARISON", "UNAVAILABLE"} else ()):
            slot = self.native_context["peer_slots"][role]
            binding = targets.get(role)
            predicate = self._predicate(role, kind, value, previous, binding, slot)
            now = str(self.ledger.now_ns())
            payload = {"identity": "peer-" + uuid4().hex,
                "process": self.ledger.process, "operation": operation,
                "ticket": ticket.identity, "producer": self.owner,
                "producer_instance": self.owner_instance, "source_kind": kind,
                "source_identity": source_identity(identity),
                "source_input": {k: source[k] for k in ("identity", "hash", "bytes")},
                "previous_source": previous_blob, "peer": role,
                "peer_slot": slot["slot"],
                "peer_instance": None if binding is None else binding["instance"],
                "listener": None if binding is None else binding["listener"],
                "composition": self.composition, "predicate": predicate,
                "registered_ns": now}
            registration = self.ledger.register_peer(payload)
            handle["peers"][role] = {"registration": registration,
                "predicate": predicate, "binding": binding}
            if predicate in {"OWNER_SLOT_NOT_INSTALLED", "JOURNAL_TRACK_UNCHANGED",
                             "JOURNAL_UNSUPPORTED_KIND", "BOOKS_NO_SOURCE_EDGE"}:
                self._peer_finished(handle, role, None, None, (), "NOT_REQUIRED")
        with self._lock:
            if (kind, identity) in self._effects:
                # Existing source currentness updates remain legitimate. They
                # cannot establish a one-to-one new WO13 reference proof.
                self.ledger.mark_ineligible("PROVENANCE")
            self._effects[kind, identity] = handle
            self._all_effects[operation] = handle
        self.ledger.start_operation(operation)
        return handle

    @staticmethod
    def _predicate(role, kind, value, previous, binding, slot):
        if slot["presence"] == "NOT_INSTALLED":
            _require(binding is None)
            return "OWNER_SLOT_NOT_INSTALLED"
        if kind in {"COMPARISON", "UNAVAILABLE"}:
            return "JOURNAL_UNSUPPORTED_KIND" if role == "JOURNAL" else "BOOKS_NO_SOURCE_EDGE"
        _require(binding is not None)
        if kind == "TRACK" and role == "JOURNAL" and previous is not None and all(
                previous.data[key] == value.data[key] for key in ("state", "entry", "exit", "monitoring")):
            return "JOURNAL_TRACK_UNCHANGED"
        if kind == "SELECTION" and value.data["choice"] != "NONE":
            return "SELECTION_NO_OUTPUT"
        if kind == "ACTION" and value.data["action"] != "DO_NOTHING":
            return "ACTION_NO_OUTPUT"
        return "REQUIRED"

    def committed(self, handle, value):
        _require(handle["value"] == value and not handle["committed"])
        handle["committed"] = True

    def _peer_finished(self, handle, role, invoked, returned, outputs, outcome):
        peer = handle["peers"][role]
        rows = []
        for output in outputs:
            rows.append({"adapter": output["adapter"],
                "identity": source_identity(output["identity"]),
                "bytes": self.ledger.retain_native("peer-output-" + uuid4().hex, output["bytes"]),
                "pointer": (None if output["pointer"] is None else self.ledger.retain_native(
                    "peer-pointer-" + uuid4().hex, output["pointer"]))})
        result = self.ledger.complete_peer({"identity": "fulfillment-" + uuid4().hex,
            "process": self.ledger.process,
            "registration": {k: peer["registration"][k] for k in ("identity", "hash", "bytes")},
            "outcome": outcome, "invoked_ns": invoked, "returned_ns": returned,
            "recorded_ns": str(self.ledger.now_ns()),
            "execution_owner": handle["ticket"].identity, "release_state": "HELD",
            "outputs": rows, "failure": outcome == "FAILED"})
        handle["peer_results"].append(result)
        peer["finished"] = True

    def dispatch(self, kind, identity, callbacks):
        with self._lock:
            handle = self._effects.get((kind, identity))
        _require(handle is not None and handle["committed"])
        _require(self.ledger.coordinator.is_live(handle["ticket"]))
        # Journal/Books original returns must be captured before an outstanding
        # notification reference can be a supported completion tail.
        ordered = sorted(callbacks, key=lambda row: row[0] == "notification_failure")
        for attribute, listener, failure in ordered:
            role = {"journal_failure": "JOURNAL", "book_failure": "BOOKS",
                    "notification_failure": "WO13"}[attribute]
            binding = self.bindings.get(role)
            if listener is None:
                continue
            _require(binding is not None and binding["callable"] == listener)
            if role == "WO13" and handle.get("caller") is not None and not handle.get("flushing"):
                _require("deferred_reference" not in handle)
                handle["deferred_reference"] = (attribute, listener, failure)
                continue
            invoked = str(self.ledger.now_ns())
            try:
                if role == "WO13":
                    child = handle.get("reference_ticket")
                    _require(child is not None and self.ledger.coordinator.is_live(child))
                    self.ledger.start_operation(handle["reference_operation"])
                    # Ordinary execution keeps the original delivery semantics.
                    # During FAILED_FENCED only the exact registered reference
                    # boundary may complete under its already-issued ticket.
                    state = self.ledger.coordinator.snapshot()["state"]
                    if state == "FAILED_FENCED":
                        _require(all(peer.get("finished") for peer in handle["peers"].values()))
                        outputs = listener.__self__.complete_registered_reference(handle["reference_operation"])
                    else:
                        with child.activate():
                            outputs = listener(kind, identity)
                    if outputs is None:
                        # The native WO13 owner truthfully de-duplicates an
                        # existing reference. Do not label that ordinary return
                        # a delivery failure or invent a new publication.
                        self.ledger.mark_ineligible("PROVENANCE")
                        handle["failed"] = True
                        result = self._owner_result(handle, reference=True, failed=True)
                        self.ledger.fail_operation(handle["reference_operation"], result, "PROVENANCE")
                        child.release()
                        continue
                    _require(type(outputs) is dict and outputs.get("kind") == kind
                        and outputs.get("identity") == identity and outputs.get("state") == "PENDING",
                        "FAILED_FENCED_REFERENCE_COMPLETION_UNPROVEN")
                    context = dict(self.native_context, owner="WO13", owner_instance=binding["instance"],
                        operation=handle["reference_operation"], ticket=child.identity,
                        source_identity=identity, reference_kind=kind)
                    handle["reference_evidence"] = self.ledger.registry.native_evidence("WO13",
                        "KRONOS-INTRADAY-WO13-SOURCE-REFERENCE-V1", "reference-" + outputs["key"],
                        outputs["bytes"], context)
                    result = self._owner_result(handle, reference=True)
                    self.ledger.complete_operation(handle["reference_operation"], result,
                        notices=({"identity": source_identity(identity), "state": "PENDING",
                                  "evidence": handle["reference_evidence"]},))
                    child.release()
                else:
                    outputs = listener(kind, identity)
            except Exception:
                # Native projection failures never invalidate a source that
                # already committed. Preserve the actual negative receipt and
                # deny recovery instead of replaying or pretending success.
                setattr(self.source_owner, attribute, failure)
                handle["failed"] = True
                self.ledger.mark_ineligible("NOTIFICATION" if role == "WO13" else "PROVENANCE")
                if role != "WO13" and role in handle["peers"]:
                    self._peer_finished(handle, role, invoked,
                        str(self.ledger.now_ns()), (), "FAILED")
                if role == "WO13":
                    result = self._owner_result(handle, reference=True, failed=True)
                    self.ledger.fail_operation(handle["reference_operation"], result, "NOTIFICATION")
                    handle["reference_ticket"].release()
                continue
            returned = str(self.ledger.now_ns())
            if role != "WO13" and role in handle["peers"]:
                peer = handle["peers"][role]
                if not peer.get("finished"):
                    self._peer_finished(handle, role, invoked, returned, outputs or (), "COMPLETED")
            handle["callbacks"].append({"listener": binding["listener"],
                "operation": handle["operation"], "state": "RETURNED", "completed_ns": returned})
        if handle.get("caller") is not None:
            # The enclosing original caller completes producer and reference
            # phases at its exact native final boundary, not this nested return.
            return handle
        handle["failed"] = bool(handle.get("failed")) or any(
            getattr(self.source_owner, field, None) for field in
            ("notification_failure", "journal_failure", "book_failure"))
        result = self._owner_result(handle, failed=bool(handle.get("failed")))
        if handle.get("failed"):
            self.ledger.fail_operation(handle["operation"], result, "PROVENANCE")
        else:
            self.ledger.complete_operation(handle["operation"], result)
        handle["ticket"].release()
        handle["completed"] = True
        return handle

    def _owner_result(self, handle, *, reference=False, failed=False):
        binding = self.bindings.get("WO13") if reference else None
        owner = "WO13" if reference else self.owner
        instance = binding["instance"] if reference else self.owner_instance
        operation = handle["reference_operation"] if reference else handle["operation"]
        relation = (handle["reference_effect"] if reference else handle["effect"])["kind"]
        resource = (binding["resource"] if reference else self.native_context["resource"])
        payload = {"identity": "owner-result-" + uuid4().hex, "owner": owner,
            "owner_instance": instance, "process": self.ledger.process,
            "action": relation, "resource": resource, "operation": operation,
            "scope": _blob(self.ledger.scope), "composition": _blob(self.composition),
            "peer_fulfillment": [] if reference or failed else sorted((_blob(row) for row in handle["peer_results"]), key=lambda row: row["identity"]),
            "callback_results": [] if reference else sorted(handle["callbacks"], key=lambda row: row["listener"]),
            "purpose": "REFERENCE" if reference else "EFFECT",
            "obligations": [operation], "targets": [_blob(handle["source"])],
            "before": [] if handle["previous"] is None else [handle["previous"]],
            "after": ([] if reference and failed else [_blob(handle["reference_evidence"] if reference else handle["source"])]),
            "result": "FAILED" if failed else "COMPLETE",
            "owned_workers": "0", "queued_items": "0", "callbacks": "0", "durable_writes": "0",
            "notification_failure": bool(getattr(self.source_owner, "notification_failure", None)),
            "durability_unproven": False,
            "reason": "UNPROVEN" if failed else "REFERENCE_COMPLETE" if reference else "EFFECT_COMPLETE"}
        _require(failed or not payload["notification_failure"])
        return self.ledger.publish_owner_result(payload)

    @contextmanager
    def reference_completion(self, owner, obligation):
        """Authorize the original uninterrupted registered WO13 tail only."""
        # WO13 has one canonical owner, shared by the three fixed producers.
        # Resolve only an existing exact operation in that already bound group;
        # this does not create, replay or broaden a notification edge.
        found = [adapter for adapter in self._reference_group
                 if any(row["reference_operation"] == obligation
                        for row in adapter._all_effects.values())]
        _require(len(found) == 1, "FAILED_FENCED_REFERENCE_OWNER_UNPROVEN")
        if found[0] is not self:
            with found[0].reference_completion(owner, obligation) as reference:
                yield reference
            return
        with self._lock:
            matches = [row for row in self._all_effects.values()
                       if row["reference_operation"] == obligation]
            _require(len(matches) == 1)
            handle = matches[0]
            binding = self.bindings["WO13"]
            _require(binding["callable"].__self__ is owner
                and owner._failed_fenced_accounting in self._reference_group
                and all(type(item) is NativeOwnerAccounting and item.ledger is self.ledger
                        and item._reference_group == self._reference_group
                        for item in self._reference_group)
                and handle["committed"] and handle["required"]
                and not handle.get("reference_invoked")
                and self._reference_active is None
                and all(peer.get("finished") for peer in handle["peers"].values()))
            ticket = handle["reference_ticket"]
            _require(self.ledger.coordinator.is_live(ticket)
                and self.ledger.coordinator.is_live(handle["ticket"]))
            payload = self.ledger.operation_payload(obligation)
            _require(payload["state"] == "STARTED"
                and payload["ticket"] == ticket.identity
                and payload["owner_instance"] == binding["instance"])
            kind, identity = handle["kind"], handle["identity"]
            if self.owner == "WO09":
                actual = (self.source_owner.load_pointer(identity) if kind == "CURRENTNESS"
                          else self.source_owner.load_readiness(identity))
            else:
                actual = self.source_owner.load(identity)
            _require(actual == handle["value"] and not any(getattr(self.source_owner, field, None)
                for field in ("notification_failure", "journal_failure", "book_failure")))
            handle["reference_invoked"] = True
            self._reference_active = obligation
        try:
            with ticket.activate():
                yield kind, identity
                # Complete the actual existing durability boundary while this
                # child's original ticket remains held. No scheduling occurs.
                owner.checkpoint(certify_durable=True)
        finally:
            with self._lock:
                self._reference_active = None

# Exact initial scope, including absence-only owners. This roster is not a
# recovery-time census; canonical composition declares each actual branch.
FINITE_OWNERS = frozenset({
    "APPLICATION", "LOCAL_ANALYSIS", "APPLICATION_LOCAL_BINDING", "NATIVE_LOCAL_BINDING",
    "RESEARCH", "RESEARCH_CAPTURE_BINDING", "WO09", "WO10", "WO11", "WO17", "WO13",
    "EXPERIMENTAL", "PROGRESSION", "NATIVE", "TRADE_WINDOW", "PAPER_OBSERVATION",
    "MONITORING_HUB", "STEP32", "MCX", "PROVIDER", "PROVIDER_FACADE", "PROVIDER_LEASE",
    "HOUSEKEEPING", "BULK", "UX10", "REMINDERS", "WO08", "CONTROL", "BROWSER",
    "SWING_ANALYSIS", "JOURNAL", "BOOKS",
})


def _blob(evidence):
    return {key: evidence[key] for key in ("identity", "hash", "bytes")}


class ProspectiveComposition:
    """Append-only record of actual construction and registration call sites.

    Source-owned callers register before use, while the composition's activation
    context is in force.  No missing attribute, quiet worker or empty dictionary
    can establish noninstallation. Retired resource identities remain retained.
    """

    def __init__(self, ledger, source, scope):
        self.ledger, self.source, self.scope = ledger, source, scope
        self._lock = RLock()
        self._slots, self._instances, self._resources = {}, {}, {}
        self._objects, self._listeners, self._cleanup = {}, {}, {}
        self._listener_objects, self._resource_objects = {}, {}
        self._cleanup_calls = {}
        self._previous = None
        self._frozen = False
        self._journal_registered = False
        self._cleanup_returns = {}
        self._active_budget = None
        self._cleanup_executing = {}
        self._cleanup_pending_returns = {}
        self._native_accounting = []
        self._registration_edges = []

    def _open(self):
        _require(not self._frozen, "FAILED_FENCED_COMPOSITION_FROZEN")

    def declare(self, owner, slot, presence):
        with self._lock:
            self._open()
            _require(owner in FINITE_OWNERS and owner not in self._slots)
            _require(presence in {"INSTALLED", "NOT_INSTALLED"})
            self._slots[owner] = {"owner": owner, "slot": slot,
                "presence": presence, "instances": []}

    def constructed(self, owner, obj, implementation):
        with self._lock:
            self._open()
            if owner not in self._slots:
                # A witnessed constructor is positive installation evidence;
                # no absence is inferred for any other branch.
                self.declare(owner, "slot-" + owner, "INSTALLED")
            if self._slots[owner]["presence"] == "NOT_INSTALLED":
                # A source-witnessed new constructor is an append-only LIVE
                # installation event, never a recovery-time absence inference.
                _require(not self._slots[owner]["instances"])
                self._slots[owner]["presence"] = "INSTALLED"
            key = id(obj)
            if key in self._objects:
                actual, identity = self._objects[key]
                _require(actual is obj and self._instances[identity]["owner"] == owner
                    and self._instances[identity]["implementation"] == _blob(implementation),
                    "FAILED_FENCED_INSTANCE_ALREADY_REGISTERED")
                return identity
            identity = "instance-" + uuid4().hex
            self._instances[identity] = {"identity": identity, "owner": owner,
                "slot": self._slots[owner]["slot"], "implementation": _blob(implementation),
                "constructed_ns": str(self.ledger.now_ns())}
            self._objects[key] = (obj, identity)
            self._slots[owner]["instances"].append(identity)
            return identity

    def instance(self, obj):
        with self._lock:
            actual = self._objects.get(id(obj))
            _require(actual is not None and actual[0] is obj,
                     "FAILED_FENCED_INSTANCE_UNREGISTERED")
            return actual[1]

    def resource(self, owner_obj, actual_resource, kind, *, parent=None,
                 cleanup_action=None, cleanup=None, nested=(), aliases=()):
        with self._lock:
            self._open()
            _require(kind in {"OWNER", "BINDING", "REGISTRATION", "TIMER", "WORKER",
                             "LEASE", "CALLBACK", "TRANSPORT", "CONTROL_FILE", "QUEUE"})
            owner_instance = self.instance(owner_obj)
            key = id(actual_resource)
            _require(key not in self._resource_objects,
                     "FAILED_FENCED_RESOURCE_ALIAS_REQUIRES_EXISTING_TARGET")
            _require(parent is None or parent in self._resources)
            identity = "resource-" + uuid4().hex
            self._resources[identity] = {"identity": identity,
                "owner_instance": owner_instance, "kind": kind, "parent": parent,
                "aliases": sorted(aliases), "registered_ns": str(self.ledger.now_ns())}
            self._resource_objects[key] = (actual_resource, identity)
            if cleanup_action is not None:
                _require(callable(cleanup))
                step = "cleanup-" + uuid4().hex
                owner = self._instances[owner_instance]["owner"]
                self._cleanup[step] = {"step": step, "owner": owner,
                    "owner_instance": owner_instance, "action": cleanup_action,
                    "resource": identity, "nested": sorted(nested)}
                self._cleanup_calls[step] = cleanup
            return identity

    def add_cleanup(self, owner_obj, action, callback, *, nested=()):
        with self._lock:
            self._open()
            instance = self.instance(owner_obj)
            resource = self.resource_identity(owner_obj)
            step = "cleanup-" + uuid4().hex
            _require(not any(row["owner_instance"] == instance and row["action"] == action
                             for row in self._cleanup.values()))
            self._cleanup[step] = {"step": step, "owner": self._instances[instance]["owner"],
                "owner_instance": instance, "action": action, "resource": resource,
                "nested": sorted(nested)}
            self._cleanup_calls[step] = callback
            return step

    def alias(self, resource, alias):
        with self._lock:
            self._open()
            _require(resource in self._resources)
            _require(alias not in {item for row in self._resources.values() for item in row["aliases"]})
            self._resources[resource]["aliases"] = sorted((*self._resources[resource]["aliases"], alias))

    def resource_identity(self, actual_resource):
        with self._lock:
            row = self._resource_objects.get(id(actual_resource))
            _require(row is not None and row[0] is actual_resource,
                     "FAILED_FENCED_RESOURCE_UNREGISTERED")
            return row[1]

    def listener(self, producer_obj, consumer_obj, callback, implementation):
        with self._lock:
            self._open()
            _require(callable(callback))
            identity = "listener-" + uuid4().hex
            self._listeners[identity] = {"identity": identity,
                "producer_instance": self.instance(producer_obj),
                "consumer_instance": self.instance(consumer_obj),
                "implementation": _blob(implementation),
                "registered_ns": str(self.ledger.now_ns()), "retired_ns": None}
            # Retain actual bound callable, not only a name or mutable attribute.
            self._listener_objects[identity] = callback
            return identity

    def retire_listener(self, identity, callback):
        with self._lock:
            self._open()
            _require(self._listener_objects.get(identity) == callback)
            _require(self._listeners[identity]["retired_ns"] is None,
                     "FAILED_FENCED_LISTENER_ALREADY_RETIRED")
            self._listeners[identity]["retired_ns"] = str(self.ledger.now_ns())

    def cleanup_targets(self):
        with self._lock:
            return tuple(dict(self._cleanup[key]) for key in sorted(self._cleanup))

    def cleanup_callable(self, step):
        with self._lock:
            _require(step in self._cleanup_calls)
            return self._cleanup_calls[step]

    def publish(self, *, original_fence=False):
        with self._lock:
            self._open()
            _require(set(self._slots) == FINITE_OWNERS,
                     "FAILED_FENCED_COMPOSITION_SLOTS_INCOMPLETE")
            for row in self._slots.values():
                _require((row["presence"] == "INSTALLED") == bool(row["instances"]),
                         "FAILED_FENCED_COMPOSITION_INSTANCE_MISSING")
            if original_fence:
                _require(self._previous is not None,
                         "FAILED_FENCED_COMPOSITION_LIVE_ANCESTOR_REQUIRED")
            now = str(self.ledger.now_ns())
            payload = {"identity": "composition-" + uuid4().hex,
                "process": self.ledger.process, "source": _blob(self.source),
                "scope": _blob(self.scope), "previous": self._previous,
                "phase": "ORIGINAL_FENCE" if original_fence else "LIVE",
                "registered_ns": now, "observed_ns": now,
                "slots": [dict(self._slots[key], instances=sorted(self._slots[key]["instances"]))
                          for key in sorted(self._slots)],
                "instances": [dict(self._instances[key]) for key in sorted(self._instances)],
                "resources": [dict(self._resources[key]) for key in sorted(self._resources)],
                "listeners": [dict(self._listeners[key]) for key in sorted(self._listeners)],
                "cleanup": [dict(self._cleanup[key]) for key in sorted(self._cleanup)]}
            result = self.ledger.register_inventory(payload)
            self._previous = _blob(result)
            self._frozen = original_fence
            return result


    def link_nested(self, parent_resource, child_resource):
        with self._lock:
            self._open()
            parent = [row for row in self._cleanup.values() if row["resource"] == parent_resource]
            child = [row["step"] for row in self._cleanup.values() if row["resource"] == child_resource]
            for row in parent:
                row["nested"] = sorted(set(row["nested"]) | set(child))


def initialize_canonical_roster(composition):
    """The canonical factory's empty construction branch, before any owner.

    Actual constructor hooks append every installed instance afterwards. This
    function cannot classify an existing or failed process from quiet objects.
    """
    _require(type(composition) is ProspectiveComposition and not composition._slots
        and not composition._objects and not composition._resources
        and composition._previous is None and not composition._frozen,
        "FAILED_FENCED_INITIAL_COMPOSITION_ALREADY_STARTED")
    for owner in sorted(FINITE_OWNERS):
        composition.declare(owner, "slot-" + owner, "NOT_INSTALLED")


def enroll_canonical_sources(composition, *, wo09, futures, lifecycle, notifications,
                             journal, books, caller):
    """Bind the actual canonical WO09/10/11 listeners before product admission.

    Each proof cites the LIVE inventory containing its actual producer/consumer
    listener; no new native contract, listener execution or historical scan is
    introduced. All inputs are exact native types constructed in this ledger.
    """
    from pathlib import Path
    from kronos.common.failed_fenced_recovery import ProspectiveLedger
    from kronos.intraday.wo09_persistence import Wo09Store
    from kronos.intraday.wo10_futures_store import FuturesStore
    from kronos.intraday.wo11_lifecycle_store import LifecycleStore
    from kronos.application.intraday_notifications import IntradayNotifications
    from kronos.application.intraday_journal import IntradayJournalApplication
    from kronos.application.intraday_books import IntradayBooks
    from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
    _require(type(composition) is ProspectiveComposition
        and type(composition.ledger) is ProspectiveLedger
        and type(wo09) is Wo09Store and type(futures) is FuturesStore
        and type(lifecycle) is LifecycleStore and type(notifications) is IntradayNotifications
        and type(journal) is IntradayJournalApplication and type(books) is IntradayBooks
        and type(caller) is IntradayLifecycleApplication and caller.store is lifecycle,
        "FAILED_FENCED_CANONICAL_OWNER_TYPES_REQUIRED")
    ledger = composition.ledger
    _require(ledger.coordinator.snapshot()["state"] == "OPEN"
        and not composition._native_accounting and not composition._frozen,
        "FAILED_FENCED_CANONICAL_ENROLLMENT_TOO_LATE")
    _require(notifications.wo09 is wo09 and notifications.futures is futures
        and notifications.lifecycle is lifecycle and journal.futures is futures
        and journal.lifecycle is lifecycle and books.futures is futures
        and books.lifecycle is lifecycle, "FAILED_FENCED_CANONICAL_SOURCE_BINDING_CHANGED")
    for actual in (wo09, futures, lifecycle, notifications, journal, books, caller):
        _require(getattr(actual, "_ff_composition", None) is composition,
                 "FAILED_FENCED_CANONICAL_CONSTRUCTOR_UNWITNESSED")
        composition.instance(actual)
    _require(notifications._failed_fenced_accounting is None
        and all(getattr(owner, "_failed_fenced_accounting", None) is None
                for owner in (wo09, futures, lifecycle, caller)),
        "FAILED_FENCED_CANONICAL_ACCOUNTING_ALREADY_BOUND")
    rows = []
    for owner, producer in (("WO09", wo09), ("WO10", futures), ("WO11", lifecycle)):
        bindings = {}
        peers = (("WO13", notifications, "notification_listener"),)
        if owner in {"WO10", "WO11"}:
            peers += (("JOURNAL", journal, "journal_listener"), ("BOOKS", books, "book_listener"))
        for role, consumer, attribute in peers:
            callback = notifications.enqueue if role == "WO13" else consumer.consume_source
            _require(getattr(producer, attribute, None) == callback,
                     "FAILED_FENCED_CANONICAL_LISTENER_CHANGED")
            implementation = ledger.retain_native("listener-code-" + role,
                Path(__import__(type(consumer).__module__, fromlist=["__file__"]).__file__).read_bytes())
            listener = composition.listener(producer, consumer, callback, implementation)
            bindings[role] = {"callable": callback, "instance": composition.instance(consumer),
                "listener": listener, "resource": composition.resource_identity(consumer)}
        rows.append((owner, producer, bindings))
    inventory = composition.publish()
    adapters = []
    for owner, producer, bindings in rows:
        for binding in bindings.values():
            binding["evidence"] = inventory
        accounting = NativeOwnerAccounting(ledger, producer, owner, composition.instance(producer),
            {key: inventory[key] for key in ("identity", "hash", "bytes")}, bindings,
            native_context={"resource": composition.resource_identity(producer),
                "peer_slots": {role: dict(composition._slots[role]) for role in ("JOURNAL", "BOOKS")}})
        adapters.append(accounting)
    group = tuple(adapters)
    for accounting in group:
        accounting._reference_group = group
        bind_failed_fenced_accounting(accounting.source_owner, accounting)
    notifications.bind_failed_fenced_accounting(adapters[-1])
    adapters[-1].bind_caller(caller)
    return group


def active_composition():
    # Import here to avoid a native-codec/common-ledger dependency cycle.
    from kronos.common.failed_fenced_recovery import current_ledger
    ledger = current_ledger()
    return None if ledger is None else getattr(ledger, "native_composition", None)


_CLEANUP_BOUNDARIES = {
    "APPLICATION": ("CLOSE_APPLICATION", "close"),
    "LOCAL_ANALYSIS": ("CLOSE_LOCAL", "close"),
    "RESEARCH": ("CLOSE_RESEARCH", "close"),
    "WO11": ("STOP_WO11", "shutdown"),
    "WO17": ("STOP_WO17", "shutdown"),
    "WO13": ("CLOSE_NOTIFICATIONS", "close"),
    "NATIVE": ("CLOSE_NATIVE", "close"),
    "TRADE_WINDOW": ("CLOSE_TRADE_WINDOW", "close_monitoring"),
    "PROGRESSION": ("CLOSE_PROGRESSION", "close_monitoring"),
    "MONITORING_HUB": ("CLOSE_HUB", "close"),
    "EXPERIMENTAL": ("STOP_EXPERIMENTAL", "shutdown"),
    "UX10": ("CLOSE_UX10", "close"),
    "REMINDERS": ("CLOSE_REMINDERS", "close"),
    "WO08": ("CLOSE_COLLECTOR", "close"),
    "BULK": ("CLOSE_BULK", "close"),
    "HOUSEKEEPING": ("STOP_HOUSEKEEPING", "shutdown"),
    "STEP32": ("CLOSE_STEP32", "close"),
    "MCX": ("CLOSE_MCX", "close"),
    "PROVIDER": ("END_SESSION", "end_kronos_session"),
    "PROVIDER_FACADE": ("RELEASE_PRODUCT_LEASE", "release_product_lease"),
    "PROVIDER_LEASE": ("REVOKE_LEASE", "_revoke"),
}


def register_owner(owner, obj, module_file):
    """Actual native constructor hook, before owner resources or product use."""
    composition = active_composition()
    if composition is None:
        return None
    from pathlib import Path
    raw = Path(module_file).read_bytes()
    implementation = composition.ledger.retain_native(
        "implementation-" + sha256(raw).hexdigest(), raw)
    instance = composition.constructed(owner, obj, implementation)
    obj._ff_composition = composition
    if getattr(obj, "_ff_callback_lock", None) is None:
        obj._ff_callback_lock = RLock()
        obj._ff_active_callbacks = 0
        obj._ff_callback_failed = False
    action, method = _CLEANUP_BOUNDARIES.get(owner, (None, None))
    boundary = getattr(obj, method, None) if method is not None else None
    # Some WO11 namespace objects are immutable stores, not executable workers.
    # They remain enumerated instances but acquire no invented shutdown action.
    if method is not None and not callable(boundary):
        action = boundary = None
    resource = composition.resource(obj, obj, "OWNER", cleanup_action=action, cleanup=boundary)
    if owner == "RESEARCH" and type(obj).__name__ == "SwingResearchControl":
        step = composition.add_cleanup(obj, "QUIESCE_DAILY", obj.quiesce_daily)
        for row in composition._cleanup.values():
            if row["owner_instance"] == instance and row["action"] == "CLOSE_RESEARCH":
                row["nested"] = sorted((*row["nested"], step))
    return instance


def record_resource(owner_obj, resource, kind, *, cleanup_action=None, cleanup=None):
    """Actual allocation/registration site; retained even after retirement."""
    composition = getattr(owner_obj, "_ff_composition", None) or active_composition()
    if composition is None:
        return None
    parent = composition.resource_identity(owner_obj)
    identity = composition.resource(owner_obj, resource, kind, parent=parent,
        cleanup_action=cleanup_action, cleanup=cleanup)
    if cleanup_action is not None:
        composition.link_nested(parent, identity)
    return identity













def recorded_callback(method):
    """Track actual native callback entry/return, not timer cancellation."""
    @wraps(method)
    def owned(self, *args, **kwargs):
        lock = getattr(self, "_ff_callback_lock", None)
        if lock is None:
            return method(self, *args, **kwargs)
        with lock:
            self._ff_active_callbacks += 1
        try:
            return method(self, *args, **kwargs)
        except BaseException:
            with lock:
                self._ff_callback_failed = True
            raise
        finally:
            with lock:
                self._ff_active_callbacks -= 1
    return owned


def callback_state(owner):
    lock = getattr(owner, "_ff_callback_lock", None)
    if lock is None:
        raise ValueError("FAILED_FENCED_NATIVE_CALLBACK_ACCOUNTING_UNAVAILABLE")
    with lock:
        return {"callbacks": owner._ff_active_callbacks, "callback_failure": owner._ff_callback_failed}


def native_owner_snapshot(owner, obj):
    """Finite, source-owned inert facts; unknown implementations deny."""
    callbacks = callback_state(obj)
    result = {"owner": owner, "callbacks": callbacks["callbacks"],
              "callback_failure": callbacks["callback_failure"],
              "owned_workers": 0, "queued_items": 0, "durable_writes": 0}
    name = type(obj).__name__
    if owner == "SWING_ANALYSIS" and type(obj) is _SwingAnalysisOwnership:
        work, execution = obj.application.analysis_work_status(), obj.application.analysis_execution_status()
        result.update(owned_workers=int(work["owned_work_count"]) + int(execution["owned_workers"]),
            queued_items=int(work["queued_jobs"]) + int(execution["queued_jobs"]))
    elif owner == "APPLICATION" and name == "SwingOpportunitiesApplication":
        work, execution = obj.analysis_work_status(), obj.analysis_execution_status()
        connection = obj.connection_attempt_status()
        restoration = obj.sponsor_operability_restoration_status()
        result.update(owned_workers=int(work["owned_work_count"]) + int(execution["owned_workers"]),
            queued_items=int(work["queued_jobs"]) + int(execution["queued_jobs"]),
            connection_active=bool(connection and any(connection.get(key) for key in
                ("worker_active", "resources_pending", "restoration_worker_active"))),
            restoration_active=restoration.get("state") in {"PENDING", "RUNNING"})
    elif owner == "LOCAL_ANALYSIS" and name == "SwingLocalAnalysisWorkflow":
        with obj._lock:
            result.update(owned_workers=int(obj._operation_lock.locked()), closed=obj._closed,
                          failure=obj._failure, history_failure=obj._history_failure)
    elif owner == "RESEARCH" and name == "SwingResearchControl":
        result.update(obj.work_status())
        with obj._worker_lock:
            result["daily_stopping"] = getattr(obj, "_daily_stopping", False)
            result["worker_alive"] = any(thread.is_alive() for thread in obj._worker._threads)
    elif owner == "RESEARCH" and name == "SwingResearchEventCapture":
        # All original capture/retention entry points are source-wrapped above.
        # Capture has no executor or independent scheduling authority.
        pass
    elif owner == "PAPER_OBSERVATION" and name == "PaperObservationTrackingWorkflow":
        with obj._lock:
            result.update(registrations=len(obj._registrations),
                          owned_workers=len(obj._pending_owners))
    elif owner == "WO11" and name == "IntradayLifecycleApplication":
        result.update(obj.work_status())
        result["registrations"] = len(obj._registrations)
        result["caller_threads_alive"] = any(thread.is_alive() for thread in obj._ff_worker_threads)
        result["caller_return_unobserved"] = any(row["joined_ns"] is None
            for row in getattr(obj, "_failed_fenced_accounting", None)._callers.values()) if getattr(obj, "_failed_fenced_accounting", None) is not None else False
    elif owner == "WO11" and name == "LifecycleStore":
        result["deferred_notices"] = len(obj._deferred_notices)
        result["publication_failure"] = any(getattr(obj, field, None) for field in
            ("notification_failure", "journal_failure", "book_failure"))
    elif owner == "WO17" and name == "IntradayWo17MonitoringCoordinator":
        result.update(obj.work_status())
        with obj._lock:
            result["registrations"] = len(obj._attached)
    elif owner == "WO13" and name == "IntradayNotifications":
        result.update(obj.maintenance_status())
        result["owned_workers"] = int(result["scheduled"])
        result["durability_unproven"] = obj._durability_unproven
        result["worker_alive"] = (False if obj._executor is None else
                                   any(thread.is_alive() for thread in obj._executor._threads))
    elif owner == "MONITORING_HUB" and name == "SharedSwingMonitoringHub":
        status = obj.status_document()
        result.update(registrations=int(status["owner_count"]),
            sessions=int(status["session_count"]), subscriptions=int(status["subscription_count"]),
            transport_cleanup=status["transport_cleanup"]["state"])
        with obj._lock:
            result["transport_busy"] = obj._transport_lock.locked()
    elif owner == "REMINDERS" and name == "SwingK5RefreshReminderWorkflow":
        with obj._lock:
            result.update(timers=len(obj._timers), closed=getattr(obj, "_closed", False))
    elif owner == "UX10" and name == "SwingUx10NotificationService":
        result.update(obj.maintenance_status())
    elif owner in {"JOURNAL", "BOOKS"} and name in {"IntradaySourceAdapter", "IntradayJournalApplication", "IntradayBooks"}:
        result["failure"] = obj.last_failure
        if owner == "BOOKS":
            with obj._lock:
                result["failure"] = obj._failure
    elif owner == "WO09" and name == "Wo09Store":
        result["publication_failure"] = any(getattr(obj, field, None) for field in
            ("notification_failure", "journal_failure"))
    elif owner == "WO10" and name == "FuturesStore":
        result["deferred_notices"] = len(obj._deferred_notices)
        result["publication_failure"] = any(getattr(obj, field, None) for field in
            ("notification_failure", "journal_failure", "book_failure"))
    elif owner == "BULK" and name == "SwingBulkImportOwner":
        work = obj.work_status()
        result.update(work)
        result["idle_worker_alive"] = bool(work["owned_workers"])
        result["owned_workers"] = int(work["batch_active"])
        result["incomplete"] = len(obj.store.list_incomplete())
    elif owner == "WO08" and name in {"Wo08ShadowCollector", "UnavailableWo08ShadowCollector"}:
        with obj._condition:
            result.update(queued_items=len(obj._queue), worker_alive=bool(obj._worker and obj._worker.is_alive()),
                          closed=obj._closed)
    elif owner == "PROGRESSION" and name == "SwingProgressionWatchWorkflow":
        with obj._lock:
            result["registrations"] = len(obj._consumers)
    elif owner == "NATIVE" and name == "NativeReviewWorkflow":
        result["registrations"] = obj.active_monitoring_count
    elif owner == "NATIVE" and name == "NativeReviewIntakeWorkflow":
        # This intake has no product worker; its writes occur only under its
        # original counted caller, while Browser requests remain separately owned.
        result["capture_failure"] = obj.research_capture_failure
    elif owner == "TRADE_WINDOW" and name == "SwingTradeWindowWorkflow":
        result["registrations"] = len(obj._monitoring_registrations)
        result["paper_registrations"] = len(obj._paper_observation_tracking._registrations)
    elif owner == "PROVIDER" and name == "SharedAuthenticatedProviderRuntime":
        status = obj.read_only_status()
        result.update(owned_workers=status["owned_work_count"],
            retained_leases=status["retained_lease_count"],
            unresolved_cleanup=status["unresolved_cleanup_count"],
            provider_capability=status["capability_state"],
            provider_cleanup=status["cleanup_state"])
    elif owner == "PROVIDER_FACADE" and name == "ProviderRuntimeCompatibilityFacade":
        # Read retained state only; never ask for active/synchronizing capability.
        result["retained_leases"] = int(obj._ProviderRuntimeCompatibilityFacade__lease is not None)
    elif owner == "PROVIDER_LEASE" and name == "ReadOnlyProviderLease":
        result["retained_leases"] = int(not obj._ReadOnlyProviderLease__revoked and not obj._ReadOnlyProviderLease__released)
    elif owner == "HOUSEKEEPING" and name == "BoundedHousekeeping":
        status = obj.status_document()
        result.update(owned_workers=int(status["pass_active"]),
            idle_worker_alive=bool(status["owned_workers"]), state=status["lifecycle_state"])
    elif owner == "STEP32" and name == "SwingV1BrowserOperationalization":
        result["registrations"] = len(obj._monitoring)
    elif owner == "MCX" and name == "SwingMcxV1OperationalControl":
        result["owned_workers"] = int(obj.worker_status()["pending"])
        result["worker_alive"] = any(thread.is_alive() for thread in obj._advisory_worker._executor._threads)
    elif owner == "EXPERIMENTAL" and name == "GovernedExperimentalWatchCoordinator":
        with obj._queue_lock:
            result.update(owned_workers=int(obj._worker_thread is not None and obj._worker_thread.is_alive()),
                queued_items=len(obj._queue) + int(obj._disconnect_pending is not None),
                registrations=len(obj.registrations), failure=obj._queue_failure)
    elif owner == "EXPERIMENTAL" and name == "IntradayExperimentalWatchCoordinator":
        pass  # Synchronous base owner has no worker/queue/monitoring resources.
    else:
        # Root-owned Browser/control and binding
        # slots have fixed native adapters at their owning composition boundary.
        method = getattr(obj, "failed_fenced_owner_status", None)
        _require(callable(method), "FAILED_FENCED_NATIVE_OWNER_STATUS_UNSUPPORTED")
        result.update(method(owner))
    return result


def _require_quiescent(facts, *, after=False, nested_verified=False):
    _require(all(not facts.get(key) for key in ("callbacks", "callback_failure", "owned_workers",
        "queued_items", "durable_writes", "connection_active", "restoration_active", "publication_failure",
        "failure", "history_failure", "incomplete", "durability_unproven", "transport_busy", "unresolved_cleanup", "caller_threads_alive", "caller_return_unobserved")),
        "FAILED_FENCED_NATIVE_OWNER_NOT_QUIESCENT")
    # Present nested registrations require exact write-free owned adapters.
    # Do not route them through a whole-close shortcut or clear failed handles.
    _require(not facts.get("deferred_notices") and (nested_verified or
        not any(facts.get(key) for key in ("registrations", "paper_registrations"))),
             "FAILED_FENCED_NATIVE_NESTED_CLEANUP_UNPROVEN")
    if "provider_capability" in facts:
        _require(facts["provider_capability"] == "ABSENT" and facts["provider_cleanup"] == "COMPLETE")
    if "transport_cleanup" in facts:
        _require(facts["transport_cleanup"] == "COMPLETE")
    if after:
        _require(not any(facts.get(key) for key in ("timers", "retry_callbacks", "sessions", "subscriptions", "worker_alive", "idle_worker_alive", "retained_leases")))


def _composition_register_cleanup_journal(self, lineage):
    _require(not self._journal_registered)
    _require(self._frozen and self.ledger.inventory is not None)
    composition = _blob(self.ledger.inventory)
    for target in self.cleanup_targets():
        operation = target["step"]
        applicability = self.ledger.publish_proof("CLEANUP_APPLICABILITY", {
            "identity": "applicability-" + uuid4().hex, "owner": target["owner"],
            "owner_instance": target["owner_instance"], "process": self.ledger.process,
            "action": target["action"], "resource": target["resource"], "operation": operation,
            "scope": _blob(self.scope), "composition": composition,
            "registered_ns": str(self.ledger.now_ns()), "state": "APPLICABLE",
            "predicate": {"kind": "REGISTERED_TARGET", "inventory": composition,
                "slot": self._instances[target["owner_instance"]]["slot"], "target": target["step"]}})
        self.ledger.register_cleanup({"lineage": lineage, "step": target["step"], "previous": None,
            "owner": target["owner"], "owner_instance": target["owner_instance"],
            "action": target["action"], "resource": target["resource"], "operation": operation,
            "state": "NOT_STARTED", "applicability": applicability, "obligations": [],
            "owner_result": None, "failure": None})
    self._journal_registered = True


def _composition_complete_recovery(self, tx):
    """Execute the frozen once-only native cleanup roster before SEAL.

    Accepted completion tails must finish in their original workers. This
    method never invokes a producer, peer callback, scan/replay or retry.
    """
    _require(self._frozen and tx.ledger is self.ledger)
    budget, claim_ns = tx.budget, tx.claim_ns
    self._active_budget = budget
    budget.check(budget.work_deadline_ns)
    self.ledger.reconcile(claim_ns, complete=False)
    for accounting in tuple(self._native_accounting):
        accounting.observe_callers(claim_ns, budget)
    # Source-owned quiescence is checked on every actual installed instance,
    # rather than converting omitted optional attributes into absence evidence.
    before = {}
    for actual, identity in self._objects.values():
        owner = self._instances[identity]["owner"]
        facts = native_owner_snapshot(owner, actual)
        _require_quiescent(facts, nested_verified=_verify_native_nested(self, actual))
        before[identity] = facts
    targets = {row["step"]: row for row in self.cleanup_targets()}
    done = set()
    cleanup_results = []
    def finish(step):
        budget.check(budget.work_deadline_ns)
        if step in done:
            return
        target = targets[step]
        for nested in target["nested"]:
            finish(nested)
        state = self.ledger.cleanup_payload(step)
        if state["state"] == "COMPLETE":
            self.ledger.registry.verify(state["owner_result"], "OWNER_RESULT")
            cleanup_results.append(state["owner_result"])
            done.add(step)
            return
        _require(state["state"] == "NOT_STARTED", "FAILED_FENCED_CLEANUP_UNKNOWN_OR_REPEATED")
        actual = next(obj for obj, identity in self._objects.values() if identity == target["owner_instance"])
        _require_quiescent(native_owner_snapshot(target["owner"], actual),
                           nested_verified=_verify_native_nested(self, actual))
        call = self.cleanup_callable(step)
        # Recorded native methods journal themselves when entered through their
        # original call sites. Direct fixed closures use the same central path.
        if getattr(call, "_ff_recorded_action", None) == target["action"]:
            call()
        else:
            self.execute_cleanup(step, call)
        state = self.ledger.cleanup_payload(step)
        _require(state["state"] == "COMPLETE")
        cleanup_results.append(state["owner_result"])
        done.add(step)
    for step in sorted(targets):
        finish(step)
    self.ledger.reconcile(claim_ns, complete=True)
    absence = []
    for owner in sorted(FINITE_OWNERS):
        slot = self._slots[owner]
        instances = slot["instances"] if slot["presence"] == "INSTALLED" else [slot["slot"]]
        for identity in instances:
            installed = slot["presence"] == "INSTALLED"
            if installed:
                actual = next(obj for obj, actual_identity in self._objects.values() if actual_identity == identity)
                facts = native_owner_snapshot(owner, actual)
                _require_quiescent(facts, after=True)
                raw = json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
                targets_blob = [self.ledger.retain_native("quiescent-" + uuid4().hex, raw)]
                resource = self.resource_identity(actual)
            else:
                targets_blob, resource = [], slot["slot"]
            absence.append(self.ledger.publish_owner_result({"identity": "absence-" + uuid4().hex,
                "owner": owner, "owner_instance": identity, "process": self.ledger.process,
                "action": "PROVE_QUIESCENT" if installed else "PROVE_NOT_INSTALLED", "resource": resource,
                "operation": "absence-" + uuid4().hex, "scope": _blob(self.scope),
                "composition": _blob(self.ledger.inventory), "peer_fulfillment": [], "callback_results": [],
                "purpose": "ABSENCE", "obligations": [], "targets": targets_blob, "before": [], "after": targets_blob,
                "result": "COMPLETE" if installed else "NOT_APPLICABLE", "owned_workers": "0", "queued_items": "0",
                "callbacks": "0", "durable_writes": "0", "notification_failure": False,
                "durability_unproven": False, "reason": "QUIESCENT" if installed else "NOT_INSTALLED"}))
    notices = [(obj, identity) for obj, identity in self._objects.values()
               if self._instances[identity]["owner"] == "WO13"]
    _require(len(notices) == 1, "FAILED_FENCED_NOTIFICATION_OWNER_UNPROVEN")
    notifications, identity = notices[0]
    certified = tx.certify_notifications(notifications, identity,
        self.resource_identity(notifications))
    return {"owner_results": [*cleanup_results, *absence],
            "cleanup_heads": self.ledger.cleanup_heads(),
            "obligation_heads": self.ledger.obligation_heads(), **certified}


ProspectiveComposition.register_cleanup_journal = _composition_register_cleanup_journal
ProspectiveComposition.complete_recovery = _composition_complete_recovery


class _OwnedBinding:
    """Actual native binding edge, retaining exact producer/target and clear."""
    def __init__(self, owner, producer, target, clear, read_current, module_file, consumer=None):
        self.owner, self.producer, self.target = owner, producer, target
        self._clear, self._read_current = clear, read_current
        self._active, self._cleared = False, False
        self.consumer = consumer
        register_owner(owner, self, module_file)
        record_resource(self, (producer, target), "BINDING")

    def activated(self):
        _require(self._read_current() is self.target and not self._cleared)
        self._active = True

    def close(self):
        if self._cleared:
            _require(self._read_current() is None)
            return
        _require(self._active and self._read_current() is self.target,
                 "FAILED_FENCED_BINDING_CHANGED")
        self._clear(self.target)
        _require(self._read_current() is None)
        self._cleared, self._active = True, False

    def failed_fenced_owner_status(self, owner):
        _require(owner == self.owner)
        current = self._read_current()
        _require(current is self.target if self._active else current is None,
                 "FAILED_FENCED_BINDING_CHANGED")
        return {"owned_workers": 0, "queued_items": 0, "callbacks": 0,
                "durable_writes": 0, "bound": self._active, "closed": self._cleared}


def record_binding(owner, producer, target, clear, read_current, module_file, consumer=None):
    composition = getattr(producer, "_ff_composition", None) or active_composition()
    if composition is None:
        return None
    if owner == "RESEARCH_CAPTURE_BINDING":
        _require(consumer is not None, "FAILED_FENCED_CAPTURE_OWNER_REQUIRED")
        composition.instance(consumer)
    else:
        consumer = target
        composition.instance(consumer)
    binding = _OwnedBinding(owner, producer, target, clear, read_current, module_file, consumer)
    implementation = composition.ledger.retain_native("binding-code-" + uuid4().hex,
        __import__("pathlib").Path(module_file).read_bytes())
    composition.listener(producer, consumer, target if callable(target) else clear, implementation)
    producer.__dict__.setdefault("_ff_owned_bindings", {})[(owner, id(target))] = binding
    return binding


def binding_activated(binding):
    if binding is not None:
        binding.activated()


def binding_cleared(producer, owner, target):
    bindings = getattr(producer, "_ff_owned_bindings", {})
    binding = bindings.get((owner, id(target)))
    if binding is not None:
        _require(binding.target is target and binding._read_current() is None)
        binding._cleared, binding._active = True, False


_CLEANUP_BOUNDARIES.update({
    "APPLICATION_LOCAL_BINDING": ("CLEAR_LOCAL_BINDING", "close"),
    "NATIVE_LOCAL_BINDING": ("CLEAR_LOCAL_BINDING", "close"),
    "RESEARCH_CAPTURE_BINDING": ("CLEAR_RESEARCH_CAPTURE", "close"),
})


def _execute_native_cleanup(self, step, invoke):
    state = self.ledger.cleanup_payload(step)
    target = self._cleanup[step]
    if state["state"] == "COMPLETE":
        self.ledger.registry.verify(state["owner_result"], "OWNER_RESULT")
        _require(step in self._cleanup_returns, "FAILED_FENCED_CLEANUP_RETURN_UNPROVEN")
        return self._cleanup_returns[step]
    if state["state"] == "STARTED" and self._cleanup_executing.get(step) == get_ident():
        return invoke()  # the exact nested native call of this owned invocation
    _require(state["state"] == "NOT_STARTED", "FAILED_FENCED_CLEANUP_UNKNOWN_OR_REPEATED")
    for child in target["nested"]:
        call = self._cleanup_calls[child]
        self.execute_cleanup(child, call)
    actual = next(obj for obj, identity in self._objects.values() if identity == target["owner_instance"])
    if self._active_budget is not None:
        self._active_budget.check(self._active_budget.work_deadline_ns)
    if target["action"] == "DETACH_REGISTRATION":
        _verify_native_detach(self, target)
    self.ledger.start_cleanup(step)
    self._cleanup_executing[step] = get_ident()
    try:
        value = invoke()
        self._cleanup_pending_returns[step] = value
    finally:
        self._cleanup_executing.pop(step, None)
    if self._active_budget is not None:
        self._active_budget.check(self._active_budget.work_deadline_ns)
    facts = _native_cleanup_facts(self, target, actual)
    if target["action"] not in {"CANCEL_TIMER", "DETACH_REGISTRATION"}:
        _require_quiescent(facts, after=target["action"] != "QUIESCE_DAILY")
    if value is False:
        raise ValueError("FAILED_FENCED_NATIVE_CLEANUP_NOT_COMPLETE")
    raw = json.dumps(dict(facts, returned=_native_return(value)), sort_keys=True, separators=(",", ":")).encode()
    after = self.ledger.retain_native("cleanup-facts-" + uuid4().hex, raw)
    proof = self.ledger.publish_owner_result({"identity": "cleanup-result-" + uuid4().hex,
        "owner": target["owner"], "owner_instance": target["owner_instance"],
        "process": self.ledger.process, "action": target["action"], "resource": target["resource"],
        "operation": state["operation"], "scope": _blob(self.scope),
        "composition": _blob(self.ledger.inventory), "peer_fulfillment": [], "callback_results": [],
        "purpose": "CLEANUP", "obligations": [], "targets": [after], "before": [], "after": [after],
        "result": "COMPLETE", "owned_workers": "0", "queued_items": "0", "callbacks": "0",
        "durable_writes": "0", "notification_failure": False, "durability_unproven": False,
        "reason": "CLEANUP_COMPLETE"})
    self.ledger.complete_cleanup(step, proof)
    self._cleanup_returns[step] = value
    self._cleanup_pending_returns.pop(step, None)
    return value


ProspectiveComposition.execute_cleanup = _execute_native_cleanup


def recorded_cleanup(action):
    """Journal the actual original invocation, not a later reconstruction."""
    def decorate(method):
        @wraps(method)
        def owned(self, *args, **kwargs):
            composition = getattr(self, "_ff_composition", None)
            if composition is None or not composition._journal_registered:
                return method(self, *args, **kwargs)
            instance = composition.instance(self)
            targets = [row for row in composition._cleanup.values()
                       if row["owner_instance"] == instance and row["action"] == action]
            _require(len(targets) == 1, "FAILED_FENCED_NATIVE_CLEANUP_TARGET_UNPROVEN")
            return composition.execute_cleanup(targets[0]["step"], lambda: method(self, *args, **kwargs))
        owned._ff_recorded_action = action
        return owned
    return decorate



def recorded_binding_clear(owner):
    def decorate(method):
        @wraps(method)
        def owned(self, target, *args, **kwargs):
            binding = getattr(self, "_ff_owned_bindings", {}).get((owner, id(target)))
            if binding is None:
                return method(self, target, *args, **kwargs)
            composition = binding._ff_composition
            if not composition._journal_registered:
                return method(self, target, *args, **kwargs)
            instance = composition.instance(binding)
            targets = [row for row in composition._cleanup.values()
                       if row["owner_instance"] == instance]
            _require(len(targets) == 1)
            return composition.execute_cleanup(targets[0]["step"],
                lambda: method(self, target, *args, **kwargs))
        return owned
    return decorate



def verify_native_cleanup_result(payload, registry, composition):
    """Current predecessor issuance must prove the actual retained target."""
    _require(type(composition) is ProspectiveComposition
        and (composition.ledger.registry is registry
             or getattr(registry, "native_ledger", None) is composition.ledger)
        and composition._frozen)
    targets = [row for row in composition._cleanup.values() if all(
        row[key] == payload[key] for key in ("owner", "owner_instance", "action", "resource"))]
    _require(len(targets) == 1)
    target = targets[0]; step = target["step"]
    _require(step in composition._cleanup_pending_returns or step in composition._cleanup_returns,
             "FAILED_FENCED_NATIVE_CLEANUP_RETURN_UNPROVEN")
    state = composition.ledger.cleanup_payload(step)
    _require(state["state"] in {"STARTED", "COMPLETE"}
        and state["operation"] == payload["operation"])
    actual = next(obj for obj, identity in composition._objects.values() if identity == payload["owner_instance"])
    facts = _native_cleanup_facts(composition, target, actual)
    if target["action"] not in {"CANCEL_TIMER", "DETACH_REGISTRATION"}:
        _require_quiescent(facts, after=target["action"] != "QUIESCE_DAILY")
    raw = registry.store.read_blob(payload["after"][0])
    retained = json.loads(raw)
    expected_return = composition._cleanup_pending_returns.get(step, composition._cleanup_returns.get(step))
    _require(retained == dict(facts, returned=_native_return(expected_return))
        and payload["targets"] == payload["after"])
    # Retain the exact actual resource, not only cleared owner dictionaries.
    resource = next(obj for obj, identity in composition._resource_objects.values()
                    if identity == payload["resource"])
    if target["action"] == "CANCEL_TIMER":
        _require(resource.finished.is_set() and not resource.is_alive(),
                 "FAILED_FENCED_TIMER_RETURN_NOT_PROVEN")
    if target["action"] == "DETACH_REGISTRATION":
        # A valid resource-specific adapter must be present; merely a removed
        # map entry never establishes that native disconnect returned.
        _require(getattr(resource, "_ff_disconnect_complete", False),
                 "FAILED_FENCED_REGISTRATION_RETURN_NOT_PROVEN")


def verify_native_absence_result(payload, registry, composition):
    _require(type(composition) is ProspectiveComposition
        and (composition.ledger.registry is registry
             or getattr(registry, "native_ledger", None) is composition.ledger)
        and composition._frozen)
    slot = composition._slots[payload["owner"]]
    if payload["result"] == "NOT_APPLICABLE":
        _require(slot["presence"] == "NOT_INSTALLED" and not slot["instances"]
            and payload["owner_instance"] == payload["resource"] == slot["slot"])
        return
    actual = next(obj for obj, identity in composition._objects.values() if identity == payload["owner_instance"])
    _require(payload["resource"] == composition.resource_identity(actual))
    facts = native_owner_snapshot(payload["owner"], actual)
    _require_quiescent(facts, after=True)
    _require(len(payload["after"]) == 1 and json.loads(registry.store.read_blob(payload["after"][0])) == facts)


def _native_timer_map(owner):
    name = type(owner).__name__
    _require(name in {"SwingK5RefreshReminderWorkflow", "SwingUx10NotificationService"},
             "FAILED_FENCED_TIMER_OWNER_UNSUPPORTED")
    return owner._timers if name == "SwingK5RefreshReminderWorkflow" else owner._retry_handles


def retire_owned_timer(owner, timer):
    """Fixed timer-source cleanup; cancellation alone is not callback return."""
    from threading import current_thread
    composition = getattr(owner, "_ff_composition", None)
    _require(composition is not None and composition.resource_identity(timer))
    # A genuinely finished timer needs no second cancellation. A live timer is
    # cancelled exactly in this registered invocation, then joined only within
    # the caller's existing shared maintenance/recovery budget.
    if not timer.finished.is_set():
        timer.cancel()
    if timer.is_alive():
        _require(timer is not current_thread(), "FAILED_FENCED_TIMER_SELF_CLEANUP")
        budget = composition._active_budget
        timeout = 0.0 if budget is None else budget.remaining_seconds(budget.work_deadline_ns)
        timer.join(timeout)
        if budget is not None:
            budget.check(budget.work_deadline_ns)
    _require(timer.finished.is_set() and not timer.is_alive(),
             "FAILED_FENCED_TIMER_RETURN_NOT_PROVEN")
    with owner._lock:
        timers = _native_timer_map(owner)
        for key, value in tuple(timers.items()):
            if value is timer:
                del timers[key]


def _native_cleanup_facts(composition, target, owner):
    if target["action"] == "DETACH_REGISTRATION":
        registration = next(obj for obj, identity in composition._resource_objects.values()
                            if identity == target["resource"])
        from kronos.application.shared_monitoring import _SharedRegistration
        _require(type(registration) is _SharedRegistration
            and registration._ff_disconnect_complete and not registration._ff_disconnect_failed)
        with registration._hub._lock:
            facts = {"kind": "REGISTRATION", "retired":
                id(registration) not in registration._hub._registrations,
                "instruments": len(registration._instruments),
                "consumer_retained": registration._consumer is not None,
                "capability_retained": registration._capability is not None}
        _require(facts == {"kind": "REGISTRATION", "retired": True, "instruments": 0,
                          "consumer_retained": False, "capability_retained": False})
        return facts
    if target["action"] != "CANCEL_TIMER":
        facts = native_owner_snapshot(target["owner"], owner)
        if target["action"] in {"CLEAR_LOCAL_BINDING", "CLEAR_RESEARCH_CAPTURE"}:
            _require(facts.get("bound") is False and facts.get("closed") is True,
                     "FAILED_FENCED_BINDING_CLEAR_NOT_PROVEN")
        if target["action"] in {"CLOSE_LOCAL", "CLOSE_RESEARCH", "CLOSE_NOTIFICATIONS", "CLOSE_UX10", "CLOSE_COLLECTOR"}:
            _require(facts.get("closed") is True, "FAILED_FENCED_NATIVE_CLOSE_NOT_PROVEN")
        if target["action"] == "QUIESCE_DAILY":
            _require(facts.get("daily_stopping") is True, "FAILED_FENCED_DAILY_QUIESCE_NOT_PROVEN")
            # This separately journaled action stops daily admission, not the
            # research executor. CLOSE_RESEARCH legitimately changes its
            # IDLE/STOPPED, closed and idle-thread state later. Its own exact
            # result and the final full-instance ABSENCE prove that closure.
            # Keep this result scoped to the actual quiescence facts, so an
            # immutable successful quiesce is not invalidated by that close.
            return {key: facts[key] for key in ("owner", "daily_stopping",
                "owned_workers", "queued_items", "callbacks", "callback_failure",
                "durable_writes", "cleanup_state")}
        return facts
    timer = next(obj for obj, identity in composition._resource_objects.values()
                 if identity == target["resource"])
    with owner._lock:
        tracked = any(value is timer for value in _native_timer_map(owner).values())
    facts = {"kind": "TIMER", "finished": timer.finished.is_set(),
             "alive": timer.is_alive(), "tracked": tracked}
    _require(facts == {"kind": "TIMER", "finished": True, "alive": False, "tracked": False},
             "FAILED_FENCED_TIMER_RETURN_NOT_PROVEN")
    return facts


class _SwingAnalysisOwnership:
    """The actual application's analysis branch; no duplicate analysis engine."""
    def __init__(self, application, module_file):
        self.application = application
        register_owner("SWING_ANALYSIS", self, module_file)


def record_analysis_owner(application, module_file):
    if getattr(application, "_ff_composition", None) is None:
        return None
    return _SwingAnalysisOwnership(application, module_file)


def native_registration_disconnect(registration, invoke):
    """Actual shared-registration edge, never a recovered callback replay."""
    composition = getattr(registration._hub, "_ff_composition", None)
    def original():
        if registration._ff_disconnect_failed:
            raise ValueError("FAILED_FENCED_NATIVE_DETACH_FAILED")
        if registration._ff_disconnect_complete:
            return registration._ff_disconnect_return
        try:
            value = invoke()
        except BaseException:
            registration._ff_disconnect_failed = True
            raise
        registration._ff_disconnect_return = value
        registration._ff_disconnect_complete = True
        return value
    if composition is None:
        return invoke()  # Ordinary legacy release counters/behavior unchanged.
    if not composition._journal_registered:
        # Ordinary repeated disconnect remains native-idempotent and preserves
        # its release counters. Recovery will only validate the retained return.
        try:
            value = invoke()
        except BaseException:
            registration._ff_disconnect_failed = True
            raise
        registration._ff_disconnect_return = value
        registration._ff_disconnect_complete = True
        return value
    resource = composition.resource_identity(registration)
    steps = [row for row in composition._cleanup.values()
             if row["resource"] == resource and row["action"] == "DETACH_REGISTRATION"]
    _require(len(steps) == 1)
    return composition.execute_cleanup(steps[0]["step"], original)


def _verify_native_detach(composition, target):
    from kronos.application.shared_monitoring import _SharedRegistration
    registration = next(obj for obj, identity in composition._resource_objects.values()
                        if identity == target["resource"])
    _require(type(registration) is _SharedRegistration and not registration._ff_disconnect_failed)
    if registration._ff_disconnect_complete:
        return
    hub = registration._hub
    with hub._lock:
        _require(hub._registrations.get(id(registration)) is registration)
        # This initial cleanup path permits no transport operation or product
        # callback. Passive registrations return before either native boundary.
        _require(hub._session is None and hub._retired_session is None
            and not hub._subscribed and hub._transport_cleanup_state == "COMPLETE",
            "FAILED_FENCED_DETACH_TRANSPORT_ACTIVE")
        governance = hub.maintenance_governance
        _require(registration._passive or (not registration._instruments
            and (governance is None or not governance.shutting_down)),
            "FAILED_FENCED_DETACH_PRODUCT_CALLBACK_REQUIRED")


def _verify_native_nested(composition, owner):
    """Only actually registered, native write-free children can be cleaned."""
    from kronos.application.shared_monitoring import SharedSwingMonitoringHub
    name = type(owner).__name__
    if type(owner) is SharedSwingMonitoringHub:
        with owner._lock:
            registrations = tuple(owner._registrations.values())
    elif name == "IntradayLifecycleApplication":
        with owner._lock:
            registrations = tuple(value[0] for value in owner._registrations.values())
    elif name == "IntradayWo17MonitoringCoordinator":
        with owner._lock:
            registrations = tuple(value.registration for value in owner._attached.values())
    elif name == "GovernedExperimentalWatchCoordinator":
        registrations = tuple(owner.registrations.values())
    elif name == "SwingProgressionWatchWorkflow":
        with owner._lock:
            registrations = tuple(value.session for value in owner._consumers.values()
                                  if value.session is not None)
    elif name == "SwingTradeWindowWorkflow":
        registrations = tuple(owner._monitoring_registrations.values())
        if owner._paper_observation_tracking.active_monitoring_count:
            return False  # Its retained monitoring writes are not cleanup authority.
    else:
        return False
    for registration in registrations:
        resource = composition.resource_identity(registration)
        if type(owner) is not SharedSwingMonitoringHub:
            _require(any(edge[0] is owner and edge[1] is registration
                         for edge in composition._registration_edges),
                     "FAILED_FENCED_REGISTRATION_EDGE_UNREGISTERED")
        rows = [row for row in composition._cleanup.values()
                if row["resource"] == resource and row["action"] == "DETACH_REGISTRATION"]
        _require(len(rows) == 1)
        _verify_native_detach(composition, rows[0])
    return True


def record_registration_alias(owner, registration):
    """Actual product-to-shared-registration edge before first product use."""
    composition = getattr(owner, "_ff_composition", None)
    if composition is None:
        return
    from kronos.application.shared_monitoring import _SharedRegistration
    _require(type(registration) is _SharedRegistration
        and registration._hub._ff_composition is composition)
    resource = composition.resource_identity(registration)
    _require(not any(edge[0] is owner and edge[1] is registration
                     for edge in composition._registration_edges))
    composition._registration_edges.append((owner, registration))
    composition.alias(resource, "registration-consumer-" + uuid4().hex)
    composition.link_nested(composition.resource_identity(owner), resource)


def _native_return(value):
    # Preserve the original native return type while storing its bounded JSON
    # value; a tuple release result must not become an unverified list claim.
    _require(type(value) in {type(None), bool, int, float, str, tuple, list, dict})
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"python_type": type(value).__name__, "value": json.loads(raw)}
