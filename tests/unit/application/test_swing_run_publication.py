from dataclasses import replace
from types import SimpleNamespace

import pytest

from kronos.application import swing_opportunities as app
from kronos.swing.v1 import opportunity_continuity as c
from kronos.swing.v1.relative_context import build_relative_context_run
from kronos.swing.universe import SWING_PHASE1_UNIVERSE
from tests.unit.swing.test_run_publication import checkpoint, scenario, later
from tests.unit.application.test_swing_opportunities import _Provider


def service_for(checkpoint):
    co, snapshot, bindings, p = checkpoint
    next_snapshot = later(snapshot)
    queued = []
    service = app.SwingOpportunitiesApplication(_Provider, run_publication=co,
        clock=lambda:next_snapshot.observed_at,
        swing_run_identity_factory=lambda:next_snapshot.run_identity,
        background_runner=lambda callback,name:queued.append(callback))
    assert service.connect_provider()
    queued.pop(0)()
    return service,queued,next_snapshot


def test_02_duplicate_no_generation_or_dispatch_and_provider_distinct(checkpoint):
    service, queued, snapshot = service_for(checkpoint)
    co = checkpoint[0]
    assert service.run_analysis()
    control = co.status()
    assert not service.run_analysis()
    assert co.status() == control and len(queued) == 1
    assert service.publication_status()['request_result'] == 'DUPLICATE_RUNNING'
    unconnected = app.SwingOpportunitiesApplication(_Provider)
    assert not unconnected.run_analysis()
    assert unconnected.publication_status()['request_result'] == 'PROVIDER_UNAVAILABLE'


def test_03_admission_failure_does_not_dispatch(checkpoint):
    service, queued, snapshot = service_for(checkpoint)
    co = checkpoint[0]
    before = co.status()
    def fail(at):
        if at == 'before_control_replace': raise OSError('fault')
    co.fault = fail
    assert not service.run_analysis() and not queued and co.status() == before


def test_01_15_committed_predecessor_and_reconciliation_failure(checkpoint, monkeypatch):
    service, queued, snapshot = service_for(checkpoint)
    co, old, bindings, p = checkpoint
    prepared = c.prepare_continuity(snapshot,bindings,adopted_predecessor=p)
    captured = []
    def build(capability, **kwargs):
        captured.append(kwargs)
        assert kwargs['committed_predecessor'].reference == p.reference
        assert kwargs['prepare_publication'] is True
        return SimpleNamespace(
            workspace=replace(service.snapshot(), analysis_state=app.AnalysisState.READY,
                swing_analysis_run_identity=snapshot.run_identity,
                run_created_at=snapshot.observed_at, completed_at=snapshot.observed_at),
            evidence=SimpleNamespace(observation_boundary=snapshot.observed_at,
                market_data_snapshot_identity='SWING-MARKET-DATA-SNAPSHOT-'+'a'*64),
            mtf_fact_snapshot=snapshot,native_discovery_run=prepared.native_run,
            relative_context_run=build_relative_context_run(snapshot,SWING_PHASE1_UNIVERSE),
            continuity_contribution=prepared)
    monkeypatch.setattr(app,'build_completed_swing_analysis',build)
    effects=[]
    def reconcile():
        effects.append(co.current().native.run_identity)
        raise ValueError('downstream unavailable')
    service.register_analysis_reconciliation(reconcile)
    assert service.run_analysis()
    queued.pop()()
    assert len(captured)==1 and effects==[snapshot.run_identity]
    assert co.status()['latest_attempt']['state']=='SUCCEEDED'
    assert service.native_discovery_run()==prepared.native_run
    assert service.publication_status()['reconciliation_unavailable']
    service.register_analysis_reconciliation(lambda:effects.append('retry'))
    service.reconcile_committed_analysis()
    assert not service.publication_status()['reconciliation_unavailable']
    assert co.current().native==prepared.native_run


def test_10_no_latest_fallback_in_builder():
    import inspect
    source=inspect.getsource(app.build_completed_swing_analysis)
    assert '.latest()' not in source
    assert 'committed_predecessor.mtf' in source and 'committed_predecessor.native' in source


def test_10_foreign_commit_cannot_reconcile_or_refresh_old_native(checkpoint):
    from tests.unit.swing.test_run_publication import prepared
    service, queued, snapshot = service_for(checkpoint)
    co, old, bindings, prior = checkpoint
    token, values = prepared(co, old, bindings, 3)
    co.publish(token, co.prepare(token, **values), values['mtf'].observed_at)
    calls = []
    service.register_analysis_reconciliation(lambda: calls.append(True))
    service.reconcile_committed_analysis()
    assert not calls
    assert service.native_discovery_run() is None
    assert service.mtf_fact_snapshot() is None
    assert service.relative_context_run() is None
    assert service.publication_status()['request_result'] == 'PUBLICATION_UNAVAILABLE'
    # An explicit canonical restoration uses the control authority, not old memory.
    restored = app.SwingOpportunitiesApplication(_Provider, run_publication=co,
        clock=lambda: snapshot.observed_at)
    assert restored.native_discovery_run() == values['native']


def test_01_two_explicit_factual_builds_each_retrieve_same_98():
    from tests.unit.application.test_swing_mtf_facts import _build
    from kronos.provider.contracts.market_data import HistoricalInterval
    first, first_requests = _build()
    second, second_requests = _build()
    expected = {i.canonical_identity for i in SWING_PHASE1_UNIVERSE}
    for snapshot, requests in ((first, first_requests), (second, second_requests)):
        hours = [r for r in requests if r.interval is HistoricalInterval.SIXTY_MINUTE]
        assert len(hours) == 98
        assert {r.instrument.trading_symbol for r in hours} == expected
        assert {i.canonical_instrument for i in snapshot.instruments} == expected
    assert first_requests is not second_requests
    assert len(first_requests) == len(second_requests)


def _guard_service(co, now):
    return app.SwingOpportunitiesApplication(_Provider, run_publication=co, clock=lambda: now)


def _guard_inventory(root):
    from hashlib import sha256
    return {str(p.relative_to(root)): (sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def test_wo07_guard_exact_lock_immutable_snapshot_and_zero_publication_writes(checkpoint):
    import fcntl
    import os
    from dataclasses import FrozenInstanceError
    co, snapshot, _, prior = checkpoint
    service = _guard_service(co, snapshot.observed_at)
    inode = (co.root / 'publication.lock').stat().st_ino
    before = _guard_inventory(co.root.parent)
    with service.publication_mutation_guard() as frozen:
        assert frozen.manifest == prior.manifest
        assert frozen.control == co.status()
        assert frozen.control['current_manifest'] == prior.reference
        assert frozen.manifest['run_id'] == snapshot.run_identity
        assert frozen.control['admission_generation'] == 0
        assert frozen.manifest['artifacts']['continuity'] is None
        with pytest.raises(TypeError):
            frozen.manifest['run_id'] = 'not-authoritative'
        with pytest.raises(TypeError):
            frozen.manifest['artifacts']['native']['sha256'] = 'f' * 64
        assert frozen.manifest == prior.manifest
        with pytest.raises(FrozenInstanceError):
            frozen.payload = b'changed'
        fd = os.open(co.root / 'publication.lock', os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
        assert _guard_inventory(co.root.parent) == before
    assert _guard_inventory(co.root.parent) == before
    assert (co.root / 'publication.lock').stat().st_ino == inode


def test_wo07_guard_exception_and_reentry_release_without_recovery(checkpoint, monkeypatch):
    co, snapshot, _, prior = checkpoint
    service = _guard_service(co, snapshot.observed_at)
    monkeypatch.setattr(co, 'recover', lambda *a: pytest.fail('implicit recovery'))
    before = _guard_inventory(co.root.parent)
    with pytest.raises(RuntimeError, match='controlled'):
        with service.publication_mutation_guard():
            with pytest.raises(ValueError, match='GUARD_REENTRY'):
                with service.publication_mutation_guard():
                    pytest.fail('nested flock must not be entered')
            raise RuntimeError('controlled')
    with service.publication_mutation_guard() as frozen:
        assert frozen.manifest == prior.manifest
    assert _guard_inventory(co.root.parent) == before


def test_wo07_guard_serializes_two_applications_and_competing_publication(checkpoint):
    from threading import Event, Thread
    from kronos.swing.run_publication import SwingRunPublication
    from tests.unit.swing.test_run_publication import prepared
    co, snapshot, bindings, prior = checkpoint
    other = SwingRunPublication(co.root, mtf_store=co.mtf_store, native_store=co.native_store,
        relative_store=co.relative_store, provenance_store=co.provenance_store)
    service = _guard_service(co, snapshot.observed_at)
    second = _guard_service(other, snapshot.observed_at)
    token, values = prepared(co, snapshot, bindings, 2)
    reference = co.prepare(token, **values)
    started, entered, published = Event(), Event(), Event()
    errors = []
    def compete():
        try:
            started.set()
            with second.publication_mutation_guard() as frozen:
                assert frozen.manifest == prior.manifest
                entered.set()
            assert other.publish(token, reference, values['mtf'].observed_at)
            published.set()
        except Exception as error:
            errors.append(error)
    with service.publication_mutation_guard() as frozen:
        thread = Thread(target=compete)
        thread.start()
        assert started.wait(5)
        assert not entered.wait(.1) and not published.is_set()
        assert frozen.control['admission_generation'] == token.generation
        assert frozen.manifest == prior.manifest
    thread.join(15)
    assert not thread.is_alive() and not errors and published.is_set()
    assert co.current().reference == reference


def test_wo07_guard_blocks_direct_wo05_publication_until_exit(checkpoint):
    from threading import Event, Thread
    from tests.unit.swing.test_run_publication import prepared
    co, snapshot, bindings, prior = checkpoint
    service = _guard_service(co, snapshot.observed_at)
    token, values = prepared(co, snapshot, bindings, 2)
    reference = co.prepare(token, **values)
    started, finished = Event(), Event()
    errors = []
    def publish():
        try:
            started.set()
            assert co.publish(token, reference, values['mtf'].observed_at)
            finished.set()
        except Exception as error:
            errors.append(error)
    with service.publication_mutation_guard() as frozen:
        thread = Thread(target=publish)
        thread.start()
        assert started.wait(5)
        assert not finished.wait(.2)
        assert co.current().reference == prior.reference
        assert frozen.manifest == prior.manifest
    thread.join(15)
    assert not thread.is_alive() and not errors and finished.is_set()
    assert co.current().reference == reference


def _guard_process(root, now, ready, enter, finish):
    from pathlib import Path
    from kronos.swing.run_publication import SwingRunPublication
    from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
    from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
    from kronos.swing.v1.native_discovery import NativeDiscoveryEvidenceStore
    from kronos.swing.v1.relative_context import RelativeContextEvidenceStore
    root = Path(root)
    co = SwingRunPublication(root / 'publication', mtf_store=MtfFactEvidenceStore(root / 'mtf'),
        native_store=NativeDiscoveryEvidenceStore(root / 'native'),
        relative_store=RelativeContextEvidenceStore(root / 'relative'),
        provenance_store=LocalSwingRunProvenanceStore(root / 'provenance'))
    service = _guard_service(co, now)
    ready.set()
    if not enter.wait(10):
        raise RuntimeError('parent did not release process')
    with service.publication_mutation_guard():
        finish.set()


def test_wo07_guard_separate_processes_share_stable_inode(checkpoint):
    import multiprocessing
    co, snapshot, _, _ = checkpoint
    service = _guard_service(co, snapshot.observed_at)
    ctx = multiprocessing.get_context('spawn')
    ready, enter, finish = ctx.Event(), ctx.Event(), ctx.Event()
    process = ctx.Process(target=_guard_process,
        args=(str(co.root.parent), snapshot.observed_at, ready, enter, finish))
    process.start()
    try:
        assert ready.wait(15)
        before = _guard_inventory(co.root.parent)
        inode = (co.root / 'publication.lock').stat().st_ino
        with service.publication_mutation_guard():
            enter.set()
            assert not finish.wait(.2)
        assert finish.wait(15)
        process.join(15)
        assert process.exitcode == 0
        assert _guard_inventory(co.root.parent) == before
        assert (co.root / 'publication.lock').stat().st_ino == inode
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)


def test_wo07_guard_does_not_enter_observational_paths(checkpoint, monkeypatch):
    co, snapshot, _, _ = checkpoint
    service = _guard_service(co, snapshot.observed_at)
    before = _guard_inventory(co.root.parent)
    monkeypatch.setattr(service, 'publication_mutation_guard', lambda: pytest.fail('GET guard'))
    monkeypatch.setattr(co, '_lock', lambda: pytest.fail('GET flock'))
    for _ in range(5):
        service.snapshot()
        service.publication_status()
        service.opportunities_bundle_projection()
    assert _guard_inventory(co.root.parent) == before


def test_wo07_guard_missing_authority_fails_without_creating_a_lock(tmp_path):
    service = app.SwingOpportunitiesApplication(_Provider)
    with pytest.raises(ValueError, match='CURRENT_UNAVAILABLE'):
        with service.publication_mutation_guard():
            pytest.fail('no publication')
    assert not list(tmp_path.iterdir())


def test_wo07_commit_guard_order_stale_envelope_and_exception_keep_predecessor(checkpoint, tmp_path):
    import fcntl
    import os
    from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    from tests.unit.swing.v1.test_review_evidence_publication import publish
    co, snapshot, _, prior = checkpoint
    service = _guard_service(co, snapshot.observed_at)
    store = ReviewEvidenceStore(tmp_path / 'review')
    predecessor = publish(store)
    before = _guard_inventory(tmp_path)
    observed = []
    def recheck(frozen):
        for path in (co.root / 'publication.lock', store.root / 'intake.lock'):
            fd = os.open(path, os.O_RDWR)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
        observed.append(frozen.control['current_manifest'])
        raise ReviewEvidenceError('REVIEW_BINDING_STALE')
    with pytest.raises(ReviewEvidenceError, match='REVIEW_BINDING_STALE'):
        with store.publication_commit_guard(service.publication_mutation_guard, recheck):
            pytest.fail('stale envelope reached publication')
    assert observed == [prior.reference]
    assert _guard_inventory(tmp_path) == before
    assert store.load_current_request() == predecessor
    assert co.current().reference == prior.reference
    with store.intake_lock():
        with pytest.raises(ReviewEvidenceError, match='LOCK_ORDER_INVALID'):
            with store.publication_commit_guard(service.publication_mutation_guard, recheck):
                pytest.fail('reverse acquisition')
    with pytest.raises(RuntimeError, match='before commit'):
        with store.publication_commit_guard(service.publication_mutation_guard, lambda frozen: None):
            raise RuntimeError('before commit')
    assert _guard_inventory(tmp_path) == before


def test_wo07_guard_raced_admission_fails_without_retry_or_recovery(checkpoint, monkeypatch):
    from contextlib import contextmanager
    co, snapshot, _, prior = checkpoint
    service = _guard_service(co, snapshot.observed_at)
    lock = co._lock
    newer = later(snapshot, 4)
    @contextmanager
    def raced_lock():
        # A real competing admission wins in the pre-validation/lock interval.
        with lock():
            control = co._control()
            co._write_control({**control, 'admission_generation': 1,
                'latest_attempt': {'run_id': newer.run_identity, 'state': 'RUNNING',
                    'predecessor_manifest': prior.reference,
                    'accepted_at': newer.observed_at.isoformat(),
                    'completed_at': None, 'failure_reason': None}})
        with lock():
            yield
    monkeypatch.setattr(co, '_lock', raced_lock)
    with pytest.raises(ValueError, match='CURRENT_CHANGED'):
        with service.publication_mutation_guard():
            pytest.fail('obsolete snapshot exposed')
    assert co.current().reference == prior.reference
    assert co.status()['latest_attempt']['state'] == 'RUNNING'


@pytest.mark.parametrize('failure', [None, 'before_acceptance_pointer', 'stale_final'])
def test_wo07_actual_request_and_acceptance_commit_are_fenced(checkpoint, tmp_path, failure):
    import fcntl
    import os
    from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    from tests.unit.swing.v1.test_review_evidence_publication import publication_fixture, acceptance_fixture
    co, snapshot, _, prior = checkpoint
    service = _guard_service(co, snapshot.observed_at)
    store = ReviewEvidenceStore(tmp_path / 'review')
    before = _guard_inventory(co.root)
    calls = []
    def check(frozen):
        assert frozen.control['current_manifest'] == prior.reference
        assert frozen.manifest['run_id'] == snapshot.run_identity
        for path in (co.root / 'publication.lock', store.root / 'intake.lock'):
            fd = os.open(path, os.O_RDWR)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
        calls.append(frozen.payload)
    publication = store.publish_nse_request(*publication_fixture(),
        publication_timestamp='2026-09-15T00:01:00.000000Z', expected_predecessor=None,
        recheck=lambda mapping: None, publication_guard=service.publication_mutation_guard,
        guarded_recheck=check)
    assert len(calls) == 2 and calls[0] == calls[1]
    accepted = store.publish_acceptance(*acceptance_fixture(),
        request_publication_identity=publication.identity, expected_predecessor=None,
        committed_at='2026-09-15T00:02:00.000000Z', recheck=lambda *args: None,
        publication_guard=service.publication_mutation_guard, guarded_recheck=check)
    assert len(calls) == 4
    def fault(phase):
        if phase == failure:
            raise RuntimeError('controlled before commit')
    store._fault = fault
    checks = []
    def final_check(frozen):
        check(frozen)
        checks.append(True)
        if failure == 'stale_final' and len(checks) == 2:
            raise ReviewEvidenceError('REVIEW_BINDING_STALE')
    def successor():
        return store.publish_acceptance(*acceptance_fixture(suffix='2', prior=accepted),
            request_publication_identity=publication.identity, expected_predecessor=accepted.identity,
            committed_at='2026-09-15T00:03:00.000000Z', recheck=lambda *args: None,
            publication_guard=service.publication_mutation_guard, guarded_recheck=final_check)
    if failure is None:
        result = successor()
        assert store.load_current_acceptance(result.value['package_key']) == result
    else:
        with pytest.raises((RuntimeError, ReviewEvidenceError)):
            successor()
        assert store.load_current_acceptance(accepted.value['package_key']) == accepted
    assert _guard_inventory(co.root) == before
    assert co.current().reference == prior.reference
