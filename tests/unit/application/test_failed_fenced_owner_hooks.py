"""Native owner hooks: prospective facts only, no production authority fixtures."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from threading import RLock
from types import SimpleNamespace

import pytest

from kronos.application.failed_fenced_owners import (
    ProspectiveComposition, FINITE_OWNERS, _OwnedBinding, native_owner_snapshot,
    verify_native_peer_fulfillment, _source_text,
)
from kronos.application.intraday_books import IntradayBooks
from kronos.application.intraday_notifications import IntradayNotifications
from kronos.intraday.wo09_persistence import Wo09Store
from tests.unit.intraday.test_wo09_readiness import evaluated
from tests.unit.intraday.test_wo14_journal import build
from tests.unit.intraday.test_wo13_notifications import (
    centre, _NotificationSourceStore, _ResearchOriginSource,
)


def blob(raw, name="fixture"):
    return {"identity": name, "hash": sha256(raw).hexdigest(), "bytes": str(len(raw))}


class NativeBytes:
    def __init__(self):
        self.values = {}
    def retain(self, raw):
        value = blob(raw)
        self.values[value["hash"]] = raw
        return value
    def read_blob(self, value):
        raw = self.values[value["hash"]]
        assert blob(raw)["hash"] == value["hash"] and str(len(raw)) == value["bytes"]
        return raw


def test_wo09_pre_effect_failure_does_not_publish_source(tmp_path):
    source, requirements = evaluated()
    store = Wo09Store(tmp_path)
    class Reject:
        def prepare(self, *args, **kwargs):
            assert not store.readiness.exists() and not store.current.exists()
            raise OSError("PROSPECTIVE_REGISTRATION_NOT_DURABLE")
    store._failed_fenced_accounting = Reject()
    with pytest.raises(OSError, match="REGISTRATION_NOT_DURABLE"):
        store.retain(source, requirements, expected=store.expectation(source.canonical_subject_identity))
    assert not store.readiness.exists() and not store.current.exists()


@pytest.mark.parametrize("peer", ["JOURNAL", "BOOKS"])
def test_actual_original_callback_outputs_validate_without_hydration(tmp_path, peer):
    journal, futures, lifecycle, selection, action, current = build(tmp_path)
    owner = journal if peer == "JOURNAL" else IntradayBooks(
        research=journal.research, futures=futures, lifecycle=lifecycle)
    output, = owner.consume_source("TRACK", current.identity)
    if peer == "BOOKS":
        owner.snapshot = lambda: pytest.fail("RECOVERY_MUST_NOT_HYDRATE")
    native = NativeBytes()
    retained = dict(output,
        identity={"encoding": "UTF-8", "bytes": output["identity"].encode().hex()},
        bytes=native.retain(output["bytes"]),
        pointer=None if output["pointer"] is None else native.retain(output["pointer"]))
    registration = {"predicate": "REQUIRED", "peer": peer, "source_kind": "TRACK",
        "source_identity": {"encoding": "UTF-8", "bytes": current.identity.encode().hex()}}
    fulfillment = {"outcome": "COMPLETED", "failure": False, "invoked_ns": "10",
                   "returned_ns": "11", "recorded_ns": "12", "outputs": [retained]}
    verify_native_peer_fulfillment(registration, fulfillment, SimpleNamespace(store=native))
    # A fully rehashed output still cannot satisfy another source's callback.
    other = dict(registration, source_identity={"encoding": "UTF-8", "bytes": b"OTHER".hex()})
    with pytest.raises(ValueError):
        verify_native_peer_fulfillment(other, fulfillment, SimpleNamespace(store=native))
    changed = deepcopy(fulfillment)
    changed["outputs"][0]["identity"]["bytes"] = b"OTHER-OUTPUT".hex()
    with pytest.raises(ValueError):
        verify_native_peer_fulfillment(registration, changed, SimpleNamespace(store=native))


def notification_owner(tmp_path):
    stores = [_NotificationSourceStore() for _ in range(3)]
    return IntradayNotifications(centre=centre(tmp_path), research=_ResearchOriginSource(),
        wo09=stores[0], futures=stores[1], lifecycle=stores[2], background=False)


def test_reference_only_publication_does_not_schedule_deliver_or_replay(tmp_path, monkeypatch):
    owner = notification_owner(tmp_path)
    monkeypatch.setattr(owner, "_schedule", lambda: pytest.fail("SCHEDULE_FORBIDDEN"))
    monkeypatch.setattr(owner, "drain", lambda: pytest.fail("DELIVERY_FORBIDDEN"))
    before = owner.checkpoint()
    receipt = owner._enqueue_owned("TRACK", "exact/source ä", schedule=False, require_new=True)
    assert receipt["identity"] == "exact/source ä" and receipt["state"] == "PENDING"
    after = owner.checkpoint(certify_durable=True)
    assert before["pending_count"] == 0 and after["pending_count"] == 1
    original = {path: path.read_bytes() for path in owner.root.iterdir()}
    with pytest.raises(ValueError, match="ALREADY_EXISTS"):
        owner._enqueue_owned("TRACK", "exact/source ä", schedule=False, require_new=True)
    assert {path: path.read_bytes() for path in owner.root.iterdir()} == original


def test_unauthorized_reference_completion_has_no_effect(tmp_path):
    owner = notification_owner(tmp_path)
    with pytest.raises(ValueError, match="ACCOUNTING_REQUIRED"):
        owner.complete_registered_reference("caller-selected-obligation")
    assert not owner.root.exists()


class LedgerProbe:
    """Durability event probe only; never substituted for a source approval."""
    def __init__(self):
        self.process = {"pid": "10", "kernel_birth": {"seconds": "1", "microseconds": "0"}, "runtime": "fixture"}
        self.scope = blob(b"scope"); self.inventory = None
        self.events, self.states, self.proofs = [], {}, {}
        self.registry = SimpleNamespace(verify=lambda *args, **kwargs: {})
        self.now = 0
    def now_ns(self):
        self.now += 1
        return self.now
    def retain_native(self, identity, raw):
        return blob(raw, identity)
    def register_inventory(self, payload):
        self.events.append(("inventory", deepcopy(payload)))
        self.inventory = blob(json.dumps(payload, sort_keys=True).encode(), payload["identity"])
        return self.inventory
    def cleanup_payload(self, step):
        return dict(self.states[step])
    def start_cleanup(self, step):
        assert self.states[step]["state"] == "NOT_STARTED"
        self.events.append(("STARTED", step)); self.states[step]["state"] = "STARTED"
    def publish_owner_result(self, payload):
        self.events.append(("owner-result", payload))
        evidence = blob(json.dumps(payload, sort_keys=True).encode(), payload["identity"])
        self.proofs[evidence["hash"]] = payload
        return evidence
    def complete_cleanup(self, step, proof):
        assert self.states[step]["state"] == "STARTED"
        self.events.append(("COMPLETE", step)); self.states[step].update(state="COMPLETE", owner_result=proof)


def cleanup_fixture():
    ledger = LedgerProbe(); composition = ProspectiveComposition(ledger, blob(b"source"), ledger.scope)
    actual = SimpleNamespace(value=object()); target = actual.value; calls = []
    binding = _OwnedBinding.__new__(_OwnedBinding)
    binding.owner, binding.producer, binding.target = "RESEARCH_CAPTURE_BINDING", actual, target
    binding._read_current = lambda: actual.value
    binding._active, binding._cleared = True, False
    def clear(value):
        assert ledger.events[-1][0] == "STARTED"
        assert actual.value is value
        calls.append(value); actual.value = None
    binding._clear = clear
    binding._ff_callback_lock, binding._ff_active_callbacks, binding._ff_callback_failed = RLock(), 0, False
    composition.constructed(binding.owner, binding, blob(b"implementation"))
    composition.resource(binding, binding, "OWNER", cleanup_action="CLEAR_RESEARCH_CAPTURE", cleanup=binding.close)
    step, = composition._cleanup
    ledger.inventory = blob(b"frozen-inventory")
    ledger.states[step] = {"state": "NOT_STARTED", "operation": step}
    composition._frozen, composition._journal_registered = True, True
    return ledger, composition, binding, step, calls


def test_original_cleanup_is_started_before_effect_and_never_reinvoked():
    ledger, composition, binding, step, calls = cleanup_fixture()
    assert composition.execute_cleanup(step, binding.close) is None
    assert len(calls) == 1 and ledger.states[step]["state"] == "COMPLETE"
    assert composition.execute_cleanup(step, lambda: pytest.fail("REPLAY_FORBIDDEN")) is None
    assert len(calls) == 1


@pytest.mark.parametrize("state", ["STARTED", "FAILED", "UNKNOWN"])
def test_unknown_or_interrupted_cleanup_cannot_repeat(state):
    ledger, composition, binding, step, calls = cleanup_fixture()
    ledger.states[step]["state"] = state
    with pytest.raises(ValueError, match="UNKNOWN_OR_REPEATED"):
        composition.execute_cleanup(step, binding.close)
    assert calls == []


def test_failed_native_cleanup_remains_started_and_cannot_be_retried():
    ledger, composition, binding, step, calls = cleanup_fixture()
    def interrupted():
        raise OSError("AFTER_START_BEFORE_RETURN")
    with pytest.raises(OSError):
        composition.execute_cleanup(step, interrupted)
    assert ledger.states[step]["state"] == "STARTED"
    with pytest.raises(ValueError):
        composition.execute_cleanup(step, binding.close)
    assert calls == []


def test_missing_owner_slot_does_not_become_absence():
    ledger = LedgerProbe(); composition = ProspectiveComposition(ledger, blob(b"source"), ledger.scope)
    for owner in sorted(FINITE_OWNERS - {"BOOKS"}):
        composition.declare(owner, "slot-" + owner, "NOT_INSTALLED")
    with pytest.raises(ValueError, match="SLOTS_INCOMPLETE"):
        composition.publish()
    assert ledger.events == []


def test_source_identity_preserves_nonascii_and_separators():
    original = "NSE / Sponsor ä / opportunity:exact"
    assert _source_text({"encoding": "UTF-8", "bytes": original.encode().hex()}) == original


def test_reference_capture_survives_immediate_native_drain(tmp_path, monkeypatch):
    owner = notification_owner(tmp_path)
    def rename_before_return():
        path, = owner.root.glob("*.pending")
        path.rename(path.with_suffix(".done"))
    monkeypatch.setattr(owner, "_schedule", rename_before_return)
    receipt = owner._enqueue_owned("TRACK", "ORIGINAL")
    retained = json.loads(receipt["bytes"])
    assert retained["identity"] == "ORIGINAL"
    assert not tuple(owner.root.glob("*.pending"))
    assert tuple(owner.root.glob("*.done"))


def test_timer_child_cleanup_proves_exact_return_without_clearing_other_timers():
    from threading import Timer
    from kronos.application.failed_fenced_owners import retire_owned_timer
    from kronos.application.swing_refresh_reminder import SwingK5RefreshReminderWorkflow
    ledger = LedgerProbe()
    composition = ProspectiveComposition(ledger, blob(b"source"), ledger.scope)
    owner = SwingK5RefreshReminderWorkflow.__new__(SwingK5RefreshReminderWorkflow)
    owner._lock, owner._timers = RLock(), {}
    owner._ff_composition = composition
    owner._ff_callback_lock, owner._ff_active_callbacks, owner._ff_callback_failed = RLock(), 0, False
    composition.constructed("REMINDERS", owner, blob(b"implementation"))
    composition.resource(owner, owner, "OWNER")
    timers = [Timer(60, lambda: pytest.fail("TIMER_MUST_NOT_FIRE")) for _ in range(2)]
    for index, timer in enumerate(timers):
        owner._timers[str(index)] = timer
        composition.resource(owner, timer, "TIMER", parent=composition.resource_identity(owner),
            cleanup_action="CANCEL_TIMER", cleanup=lambda timer=timer: retire_owned_timer(owner, timer))
        timer.start()
    ledger.inventory = blob(b"frozen-inventory")
    composition._frozen, composition._journal_registered = True, True
    composition._active_budget = SimpleNamespace(work_deadline_ns=1,
        remaining_seconds=lambda deadline: 0.5, check=lambda deadline: None)
    for step in composition._cleanup:
        ledger.states[step] = {"state": "NOT_STARTED", "operation": step}
    first, second = tuple(composition._cleanup)
    try:
        composition.execute_cleanup(first, composition.cleanup_callable(first))
        assert not timers[0].is_alive() and timers[1].is_alive()
        assert list(owner._timers) == ["1"]
        composition.execute_cleanup(first, lambda: pytest.fail("DUPLICATE_CANCEL"))
        composition.execute_cleanup(second, composition.cleanup_callable(second))
        assert not owner._timers and not any(timer.is_alive() for timer in timers)
    finally:
        for timer in timers:
            timer.cancel(); timer.join(1)


def test_native_projection_failure_does_not_replay_or_invalidate_committed_source():
    from kronos.application.failed_fenced_owners import NativeOwnerAccounting
    calls = []
    source = SimpleNamespace(notification_failure=None, journal_failure=None, book_failure=None)
    ticket = SimpleNamespace(release=lambda: calls.append("release"))
    def failed_projection(kind, identity):
        calls.append((kind, identity)); raise OSError("ORIGINAL_PROJECTION_FAILURE")
    accounting = NativeOwnerAccounting.__new__(NativeOwnerAccounting)
    accounting.source_owner, accounting.owner, accounting._lock = source, "WO11", RLock()
    accounting.bindings = {"JOURNAL": {"callable": failed_projection, "listener": "listener"}}
    handle = {"committed": True, "ticket": ticket, "operation": "effect",
              "peers": {"JOURNAL": {}}, "callbacks": []}
    accounting._effects = {("TRACK", "identity"): handle}
    accounting.ledger = SimpleNamespace(
        coordinator=SimpleNamespace(is_live=lambda value: value is ticket), now_ns=lambda: 5,
        mark_ineligible=lambda code: calls.append(("ineligible", code)),
        fail_operation=lambda *args: calls.append(("failed", args[0])),
        complete_operation=lambda *args: pytest.fail("FAILURE_IS_NOT_COMPLETE"))
    accounting._peer_finished = lambda *args: calls.append(("peer-failed", args[-1]))
    accounting._owner_result = lambda *args, **kwargs: (calls.append(("result", kwargs)), {})[1]
    accounting.dispatch("TRACK", "identity", (("journal_failure", failed_projection, "JOURNAL_UNAVAILABLE"),))
    assert calls.count(("TRACK", "identity")) == 1
    assert source.journal_failure == "JOURNAL_UNAVAILABLE"
    assert ("failed", "effect") in calls and calls[-1] == "release"


def test_live_constructor_appends_instance_without_false_absence():
    ledger = LedgerProbe(); composition = ProspectiveComposition(ledger, blob(b"source"), ledger.scope)
    composition.declare("PROVIDER_LEASE", "slot-PROVIDER_LEASE", "NOT_INSTALLED")
    actual = object()
    identity = composition.constructed("PROVIDER_LEASE", actual, blob(b"native-lease-code"))
    assert composition._slots["PROVIDER_LEASE"] == {"owner": "PROVIDER_LEASE",
        "slot": "slot-PROVIDER_LEASE", "presence": "INSTALLED", "instances": [identity]}
    composition._frozen = True
    with pytest.raises(ValueError, match="FROZEN"):
        composition.constructed("PROVIDER_LEASE", object(), blob(b"native-lease-code"))


def hub_cleanup_fixture():
    from kronos.application.shared_monitoring import SharedSwingMonitoringHub
    ledger = LedgerProbe(); composition = ProspectiveComposition(ledger, blob(b"source"), ledger.scope)
    hub = SharedSwingMonitoringHub()
    hub._ff_composition = composition
    hub._ff_callback_lock, hub._ff_active_callbacks, hub._ff_callback_failed = RLock(), 0, False
    composition.constructed("MONITORING_HUB", hub, blob(b"hub-code"))
    composition.resource(hub, hub, "OWNER", cleanup_action="CLOSE_HUB", cleanup=hub.close)
    consumer = SimpleNamespace(on_market_tick=lambda value: pytest.fail("NO_CALLBACK"),
        on_order_update=lambda value: pytest.fail("NO_CALLBACK"),
        on_connection_state=lambda value: pytest.fail("NO_CALLBACK"))
    registration = hub.open(SimpleNamespace(active=True), consumer)
    ledger.inventory = blob(b"frozen-inventory")
    composition._frozen, composition._journal_registered = True, True
    for step in composition._cleanup:
        ledger.states[step] = {"state": "NOT_STARTED", "operation": step}
    return ledger, composition, hub, registration


def test_actual_nested_registration_disconnect_once_before_hub_close():
    ledger, composition, hub, registration = hub_cleanup_fixture()
    calls = []
    native = hub._disconnect
    def observed(value):
        calls.append(value); return native(value)
    hub._disconnect = observed
    parent = next(row["step"] for row in composition._cleanup.values() if row["action"] == "CLOSE_HUB")
    child = next(row["step"] for row in composition._cleanup.values() if row["action"] == "DETACH_REGISTRATION")
    assert child in composition._cleanup[parent]["nested"]
    composition.execute_cleanup(parent, hub.close)
    assert calls == [registration] and registration._ff_disconnect_complete
    assert not hub._registrations and registration._consumer is None
    assert all(row["state"] == "COMPLETE" for row in ledger.states.values())
    composition.execute_cleanup(parent, lambda: pytest.fail("NO_PARENT_REPLAY"))
    assert calls == [registration]


def test_registration_requiring_product_callback_is_denied_before_start():
    ledger, composition, hub, registration = hub_cleanup_fixture()
    hub.maintenance_governance = SimpleNamespace(shutting_down=True)
    step = next(row["step"] for row in composition._cleanup.values() if row["action"] == "DETACH_REGISTRATION")
    with pytest.raises(ValueError, match="PRODUCT_CALLBACK_REQUIRED"):
        composition.execute_cleanup(step, registration.disconnect)
    assert ledger.states[step]["state"] == "NOT_STARTED"
    assert hub._registrations[id(registration)] is registration
    assert not registration._ff_disconnect_complete


def test_original_wo11_caller_completes_business_before_registered_reference_tail(tmp_path):
    """Actual native thread/tickets/stores; ledger probe is not release authority."""
    from threading import Event
    from time import monotonic_ns
    from kronos.application.failed_fenced_owners import NativeOwnerAccounting, verify_native_evidence, verify_native_owner_result
    from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    from kronos.intraday.wo11_lifecycle_store import LifecycleStore
    coordinator = MaintenanceAdmissionCoordinator()
    events, entered, release = [], Event(), Event()
    class CallerLedger(LedgerProbe):
        def __init__(self):
            super().__init__(); self.coordinator = coordinator
            self.store = NativeBytes(); self.operations = {}
            self.registry = SimpleNamespace(store=self.store, native_evidence=self.native,
                                            verify=lambda *args, **kwargs: {})
        def now_ns(self): return monotonic_ns()
        def current_ticket(self): return coordinator.current_ticket()
        def retain_native(self, identity, raw): return self.store.retain(raw)
        def native(self, owner, contract, identity, raw, context):
            result = dict(self.store.retain(raw), authority=owner, contract=contract)
            verify_native_evidence(result, raw, context)
            return result
        def begin_operation(self, ticket, owner, owner_instance, operation, relation, effect, **kwargs):
            coordinator.bind_operation(ticket, operation)
            self.operations[operation] = dict(state="ACCEPTED", ticket=ticket.identity,
                owner=owner, owner_instance=owner_instance, operation=operation, relation=relation,
                parent=kwargs.get("parent"))
            events.append(("registered", relation))
        def operation_head(self, operation): return blob(operation.encode(), operation)
        def operation_payload(self, operation): return dict(self.operations[operation])
        def start_operation(self, operation):
            assert self.operations[operation]["state"] == "ACCEPTED"
            self.operations[operation]["state"] = "STARTED"
        def register_peer(self, payload): return blob(json.dumps(payload, sort_keys=True).encode(), payload["identity"])
        def complete_peer(self, payload): return blob(json.dumps(payload, sort_keys=True).encode(), payload["identity"])
        def publish_owner_result(self, payload):
            verify_native_owner_result(payload, self.registry, {})
            return super().publish_owner_result(payload)
        def complete_operation(self, operation, result, notices=()):
            row = self.operations[operation]
            events.append(("complete", row["relation"]))
            assert row["state"] == "STARTED"
            row["state"] = "COMPLETE"
            if row["relation"] == "WO11_PUBLICATION":
                assert "business-return" in events
                assert coordinator.claim("d" * 64)
                coordinator.draining("d" * 64)
                coordinator.fail("d" * 64, "DRAIN_TIMEOUT")
            else:
                assert coordinator.snapshot()["state"] == "FAILED_FENCED"
                assert notices and notices[0]["state"] == "PENDING"
        def fail_operation(self, *args): pytest.fail("VALID_TAIL_MUST_NOT_FAIL")
        def mark_ineligible(self, *args): pytest.fail("VALID_TAIL_MUST_NOT_BECOME_INELIGIBLE")
    ledger = CallerLedger(); composition = ProspectiveComposition(ledger, blob(b"source"), ledger.scope)
    source = LifecycleStore(tmp_path / "owned-lifecycle")
    app = IntradayLifecycleApplication(futures=None, store=source, clock=lambda: None,
        session_source=None, timing_source=None, operational_guard=lambda: True)
    app.bind_maintenance_admission(coordinator)
    notices = notification_owner(tmp_path / "notifications")
    for owner, actual in (("WO11", source), ("WO11", app), ("WO13", notices)):
        composition.constructed(owner, actual, blob((owner+type(actual).__name__).encode()))
        composition.resource(actual, actual, "OWNER")
        actual._ff_composition = composition
        actual._ff_callback_lock, actual._ff_active_callbacks, actual._ff_callback_failed = RLock(), 0, False
    source.notification_listener = notices.enqueue
    binding = {"callable": notices.enqueue, "instance": composition.instance(notices),
        "listener": "actual-reference-listener", "evidence": blob(b"actual-reference-listener"),
        "resource": composition.resource_identity(notices)}
    accounting = NativeOwnerAccounting(ledger, source, "WO11", composition.instance(source),
        blob(b"live-composition"), {"WO13": binding}, native_context={
            "resource": composition.resource_identity(source), "peer_slots": {
                role: {"slot": "slot-"+role, "presence": "NOT_INSTALLED"} for role in ("JOURNAL", "BOOKS")}})
    source._failed_fenced_accounting = accounting
    notices.bind_failed_fenced_accounting(accounting)
    accounting.bind_caller(app)
    from tests.unit.intraday.test_wo11_lifecycle import track
    current = track()
    def original_pulse():
        handle = accounting.prepare("TRACK", current.identity, current)
        assert handle["ticket"] is handle["caller_ticket"]
        source.retain(current); accounting.committed(handle, current)
        events.append("source-committed")
        accounting.dispatch("TRACK", current.identity, (("notification_failure", notices.enqueue, "FAILED"),))
        assert not notices.root.exists()
        entered.set(); assert release.wait(2)
        # Represents actual remaining caller handoff/projection bookkeeping.
        events.append("business-return")
    app.pulse = original_pulse
    try:
        assert app.request_pulse() and entered.wait(2)
        assert coordinator.snapshot()["owners"] == {"WO11": 1, "NOTIFICATION": 1}
        assert not notices.root.exists()
    finally:
        release.set()
    thread, = app._ff_worker_threads
    thread.join(2); assert not thread.is_alive()
    assert coordinator.snapshot()["owners"] == {}
    assert events.index("business-return") < events.index(("complete", "WO11_PUBLICATION"))
    assert events.index(("complete", "WO11_PUBLICATION")) < events.index(("complete", "WO11_TRACK_REFERENCE"))
    assert notices.checkpoint(certify_durable=True)["pending_count"] == 1
    budget = SimpleNamespace(work_deadline_ns=monotonic_ns()+1_000_000_000,
        remaining_seconds=lambda deadline: 1, check=lambda deadline: None)
    accounting.observe_callers(monotonic_ns(), budget)
    row, = accounting._callers.values()
    assert row["return_path_reached"] and row["joined_ns"] is not None


@pytest.mark.parametrize("idle_thread", [False, True])
def test_daily_quiesce_result_remains_exact_after_separate_research_close(tmp_path, idle_thread):
    from tests.unit.application.test_swing_research_worker import _control
    from kronos.application.failed_fenced_owners import _native_cleanup_facts, _require_quiescent
    control = _control(tmp_path)
    control._ff_callback_lock = RLock()
    control._ff_active_callbacks, control._ff_callback_failed = 0, False
    target = {"owner": "RESEARCH", "action": "QUIESCE_DAILY"}
    try:
        if idle_thread:
            assert control._worker.submit(lambda: "fixture-only-no-acquisition").result(timeout=3) == "fixture-only-no-acquisition"
        with pytest.raises(ValueError, match="DAILY_QUIESCE_NOT_PROVEN"):
            _native_cleanup_facts(None, target, control)
        control.quiesce_daily()
        original = _native_cleanup_facts(None, target, control)
        _require_quiescent(original)
        before = native_owner_snapshot("RESEARCH", control)
        assert before["state"] == "IDLE" and before["closed"] is False
        assert before["worker_alive"] is idle_thread
        control.close()
        assert _native_cleanup_facts(None, target, control) == original
        closed = _native_cleanup_facts(None, {**target, "action": "CLOSE_RESEARCH"}, control)
        assert closed["state"] == "STOPPED" and closed["closed"] is True and closed["worker_alive"] is False
        _require_quiescent(closed, after=True)
        assert original["daily_stopping"] is True and "closed" not in original
        control._daily_stopping = False
        with pytest.raises(ValueError, match="DAILY_QUIESCE_NOT_PROVEN"):
            _native_cleanup_facts(None, target, control)
    finally:
        control.close()


@pytest.mark.parametrize("fault", ["active-work", "callback", "callback-failure"])
def test_daily_quiesce_action_facts_do_not_hide_live_or_failed_ownership(tmp_path, fault):
    from tests.unit.application.test_swing_research_worker import _control
    from kronos.application.failed_fenced_owners import _native_cleanup_facts, _require_quiescent
    control = _control(tmp_path)
    control._ff_callback_lock = RLock()
    control._ff_active_callbacks, control._ff_callback_failed = 0, False
    try:
        control.quiesce_daily()
        if fault == "active-work": control._active_operation = "fixture-incomplete"
        elif fault == "callback": control._ff_active_callbacks = 1
        else: control._ff_callback_failed = True
        facts = _native_cleanup_facts(None, {"owner": "RESEARCH", "action": "QUIESCE_DAILY"}, control)
        with pytest.raises(ValueError): _require_quiescent(facts)
    finally:
        control._active_operation = None
        control.close()


@pytest.mark.parametrize("tamper", [None, "daily_stopping", "owned_workers", "returned", "targets", "operation"])
def test_quiesce_original_binding_remains_verified_and_tampering_denied_after_close(tmp_path, tamper):
    from tests.unit.application.test_swing_research_worker import _control
    from kronos.application.failed_fenced_owners import verify_native_cleanup_result
    control = _control(tmp_path)
    control._ff_callback_lock = RLock()
    control._ff_active_callbacks, control._ff_callback_failed = 0, False
    ledger = LedgerProbe(); native = NativeBytes()
    ledger.retain_native = lambda identity, raw: native.retain(raw)
    ledger.registry = SimpleNamespace(store=native, verify=lambda *args, **kwargs: {})
    composition = ProspectiveComposition(ledger, blob(b"source"), ledger.scope)
    composition.constructed("RESEARCH", control, blob(b"implementation"))
    composition.resource(control, control, "OWNER")
    quiesce = composition.add_cleanup(control, "QUIESCE_DAILY", control.quiesce_daily)
    close = composition.add_cleanup(control, "CLOSE_RESEARCH", control.close)
    ledger.inventory = blob(b"frozen-inventory")
    composition._frozen, composition._journal_registered = True, True
    for step in (quiesce, close): ledger.states[step] = {"state": "NOT_STARTED", "operation": step}
    try:
        composition.execute_cleanup(quiesce, control.quiesce_daily)
        original = deepcopy(ledger.proofs[ledger.states[quiesce]["owner_result"]["hash"]])
        original_bytes = native.read_blob(original["after"][0])
        verify_native_cleanup_result(original, ledger.registry, composition)
        composition.execute_cleanup(close, control.close)
        verify_native_cleanup_result(original, ledger.registry, composition)
        assert native.read_blob(original["after"][0]) == original_bytes
        changed = deepcopy(original)
        if tamper in {"daily_stopping", "owned_workers", "returned"}:
            data = json.loads(original_bytes)
            data[tamper] = False if tamper == "daily_stopping" else 1
            forged = native.retain(json.dumps(data, sort_keys=True).encode())
            changed["after"] = changed["targets"] = [forged]
        elif tamper == "targets": changed["targets"] = []
        elif tamper == "operation": changed["operation"] = "another-cleanup"
        if tamper is not None:
            with pytest.raises(ValueError): verify_native_cleanup_result(changed, ledger.registry, composition)
    finally:
        control.close()
