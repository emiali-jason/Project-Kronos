"""Actual local joins plus explicit synthetic native-validator boundary.

The stubbed registry results isolate the P observer's ordering/accounting; they
are not native authentication qualification or operational owner approvals.
"""
from copy import deepcopy
from hashlib import sha256
from threading import Thread

import pytest

from kronos.common.failed_fenced_recovery import (
    EvidenceRegistry, RecoveryError, canonical_bytes,
)
from tests.unit.common.test_failed_fenced_recovery import (
    PROCESS, LINEAGE, original_witness, real_budget, evidence,
)


def _observer_case():
    coordinator, witness = original_witness()
    def execute():
        with witness.operation("backend-maintenance-drain"):
            pass
        witness.return_observed()
    thread = Thread(target=execute)
    witness.bind_thread(thread); thread.start()
    witness.join_and_close(real_budget())
    assert not thread.is_alive()
    controller = witness.original_controller
    identity = "controller-closure-" + sha256(canonical_bytes({
        "attempt": witness.original_attempt, "controller": controller})).hexdigest()
    ref = evidence(identity)
    closure = dict(identity=identity, controller=controller,
        attempt=witness.original_attempt, lineage=LINEAGE,
        capability={"identity":"cap"}, admissions=[{"identity":"authorize"}, {"identity":"drain"}],
        dispatch_heads=[{"identity":"authorize-head"}, {"identity":"drain-head"}])
    operations = {
        "authorize": dict(operation="original.authorize", controller=controller,
            attempt=witness.original_attempt, lineage=LINEAGE),
        "drain": dict(operation="backend-maintenance-drain", controller=controller,
            attempt=witness.original_attempt, lineage=LINEAGE),
    }
    blobs = {**operations,
        "cap": dict(controller=controller, predecessor=PROCESS, phase="ORIGINAL"),
        "authorize-head": {key:value for key,value in operations["authorize"].items() if key != "operation"},
        "drain-head": {key:value for key,value in operations["drain"].items() if key != "operation"}}
    registry = object.__new__(EvidenceRegistry)
    registry._executor_witnesses = {witness.executor:witness}
    # Exact source-bound/MAC semantics are independently exercised by the real
    # registry/native tests; this fixed stub cannot authorize production work.
    def verified(actual, kind, **kwargs):
        assert actual == ref and kind == "CONTROLLER_CLOSURE"
        assert kwargs == {"context":{"mode":"ORIGINAL"}}
        return {"payload":deepcopy(closure)}
    def blob(actual, kind, **kwargs):
        assert kwargs == {"context":{"mode":"ORIGINAL"}}
        return {"payload":deepcopy(blobs[actual["identity"]])}
    registry.verify, registry.verify_blob = verified, blob
    return coordinator, witness, registry, ref, closure, blobs


def test_native_closure_augments_complete_work_set_only_after_real_local_join():
    coordinator, witness, registry, ref, _, _ = _observer_case()
    assert coordinator.original_execution_snapshot()["publisher_owners"] == 1
    assert witness.observe_controller_closure(registry, ref, LINEAGE) == ref
    payload = witness.termination_payload("termination", PROCESS, LINEAGE)
    assert payload["accepted_operations"] == payload["completed_operations"] == [
        "backend-maintenance-drain", "original.authorize"]
    assert witness._accepted == witness._completed == {"backend-maintenance-drain"}
    witness.validate(payload)
    with pytest.raises(RecoveryError):
        witness.observe_controller_closure(registry, ref, LINEAGE)
    with pytest.raises(RecoveryError):
        witness.validate({**payload,"completed_operations":["backend-maintenance-drain"]})
    assert coordinator.original_execution_snapshot()["publisher_owners"] == 1


@pytest.mark.parametrize("fault", ["attempt", "controller", "lineage", "local_omission", "publisher_released", "registry"])
def test_invalid_controller_observation_never_completes_original_ownership(fault):
    coordinator, witness, registry, ref, closure, blobs = _observer_case()
    if fault == "attempt": closure["attempt"] = "wrong-attempt"
    elif fault == "controller": closure["controller"] = {**PROCESS,"runtime":"different"}
    elif fault == "lineage": closure["lineage"] = {**LINEAGE,"generation":"b"*64}
    elif fault == "local_omission": blobs["drain"]["operation"] = "unrelated-operation"
    elif fault == "publisher_released": coordinator.finish_original_publication(witness.executor)
    else: registry._executor_witnesses.clear()
    with pytest.raises(RecoveryError):
        witness.observe_controller_closure(registry, ref, LINEAGE)
    assert witness._controller_closure is None and witness._controller_operations is None
    assert witness._accepted == witness._completed == {"backend-maintenance-drain"}


def test_actual_executor_still_running_cannot_adopt_native_completion():
    coordinator, witness = original_witness()
    registry = object.__new__(EvidenceRegistry)
    registry._executor_witnesses = {witness.executor:witness}
    # The known complete fixture is still insufficient without actual P join.
    _, _, complete, ref, _, _ = _observer_case()
    registry.verify, registry.verify_blob = complete.verify, complete.verify_blob
    with pytest.raises(RecoveryError):
        witness.observe_controller_closure(registry, ref, LINEAGE)
    assert coordinator.original_execution_snapshot()["operational_owners"] == 1
    assert coordinator.original_execution_snapshot()["publisher_owners"] == 0


def _ordinary_completion_fixture(enrolled=True):
    """Real coordinator/drain ordering; fixed domain I/O is the test boundary."""
    from types import SimpleNamespace
    from kronos.browser.server import KronosBrowserServer
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    from tests.unit.common.test_failed_fenced_recovery import GEN
    coordinator = MaintenanceAdmissionCoordinator()
    coordinator.claim(GEN)
    budget = real_budget()
    original = None
    if enrolled:
        coordinator.begin_original_execution(GEN, 'original')
        original = SimpleNamespace(ledger=SimpleNamespace(coordinator=coordinator),
            executor='original', budget=budget,
            payload={'original_drain_deadline_ns':str(budget.origin_ns + 10_000_000_000)})
    server = object.__new__(KronosBrowserServer)
    calls = []
    server.maintenance_admission = coordinator
    server._failed_fenced_original_binding = original
    server.maintenance_replacement_idle = lambda **kwargs: True
    server._quiesce_monitoring_producers = lambda: calls.append('quiesce')
    server._close_domain_owners = lambda **kwargs: calls.append('domain-close')
    server._maintenance_final_owner_proof = lambda: True
    server._maintenance_drain_attestation = lambda: {'test-domain-proof':'zero'}
    server.restart_control = SimpleNamespace(owns_current_process=lambda: True,
        maintenance_drain_handoff=lambda *args: calls.append('handoff'))
    server.connection_governance = SimpleNamespace(process=SimpleNamespace(loaded_revision='a'*40))
    server.shutdown = lambda: calls.append('shutdown')
    return server, coordinator, original, calls, GEN


def test_enrolled_success_preserves_main_until_actual_original_publication_completes():
    server, coordinator, original, calls, generation = _ordinary_completion_fixture()
    server._complete_governed_shutdown(generation, 'test-runtime')
    assert calls == ['quiesce', 'domain-close', 'handoff']
    assert coordinator.snapshot()['state'] == 'STOPPING'
    with pytest.raises(ValueError, match='PUBLICATION_INCOMPLETE'):
        server._finish_original_shutdown_observation(generation, original)
    coordinator.complete_original_execution('original')
    server._failed_fenced_original_completion = {'test-retained-reference':'actual-publication'}
    with pytest.raises(ValueError, match='PUBLICATION_INCOMPLETE'):
        server._finish_original_shutdown_observation(generation, original)
    assert 'shutdown' not in calls
    coordinator.finish_original_publication('original')
    assert server._finish_original_shutdown_observation(generation, original)
    assert calls == ['quiesce', 'domain-close', 'handoff', 'shutdown']


def test_unenrolled_ordinary_shutdown_order_remains_unchanged():
    server, coordinator, _, calls, generation = _ordinary_completion_fixture(False)
    server._complete_governed_shutdown(generation, 'test-runtime')
    assert calls == ['quiesce', 'domain-close', 'handoff', 'shutdown']
    assert coordinator.snapshot()['state'] == 'STOPPING'


def test_failed_original_never_enters_normal_shutdown_after_observer_return():
    server, coordinator, original, calls, generation = _ordinary_completion_fixture()
    coordinator.fail(generation, 'DRAIN_TIMEOUT')
    coordinator.complete_original_execution('original')
    coordinator.finish_original_publication('original')
    server._failed_fenced_original_completion = {'test-retained-reference':'actual-publication'}
    assert server._finish_original_shutdown_observation(generation, original) is False
    assert calls == []
    assert coordinator.snapshot()['state'] == 'FAILED_FENCED'


@pytest.mark.parametrize('fault', ['generation', 'binding', 'missing-publication', 'expired'])
def test_original_observer_denies_changed_or_incomplete_shutdown(fault):
    from time import clock_gettime_ns, CLOCK_MONOTONIC
    server, coordinator, original, calls, generation = _ordinary_completion_fixture()
    server._complete_governed_shutdown(generation, 'test-runtime')
    coordinator.complete_original_execution('original')
    coordinator.finish_original_publication('original')
    server._failed_fenced_original_completion = {'test-retained-reference':'actual-publication'}
    argument = original
    if fault == 'generation': generation += '-changed'
    elif fault == 'binding': argument = object()
    elif fault == 'missing-publication': server._failed_fenced_original_completion = None
    else: original.budget.stop_deadline_ns = clock_gettime_ns(CLOCK_MONOTONIC)-1
    with pytest.raises((ValueError, RecoveryError)):
        server._finish_original_shutdown_observation(generation, argument)
    assert 'shutdown' not in calls
