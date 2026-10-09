"""Disposable-store proofs for the sealed PROCESS_LOCAL mutation protocol.

These owning tests do not establish application eligibility or first-five time.
"""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Event, Lock, Thread

import pytest

from kronos.intraday import wo09_persistence as persistence
from kronos.intraday.wo09_persistence import (
    Wo09Store, Wo09PersistenceError, Wo09PublicationConflict,
    Wo09PublicationExpectation, Wo09MutationReentry,
)
from kronos.intraday.wo09_readiness import (
    CurrentnessState, create_next_wo_handoff, evaluate_readiness,
)
from tests.unit.intraday.test_wo09_readiness import NOW, source, evidence, evaluated


def retain(store, record=None, requirements=None):
    if record is None:
        record, requirements = evaluated()
    return store.retain(record, requirements,
                        expected=store.expectation(record.canonical_subject_identity))


def handoff(store, record):
    p = store.load_pointer(record.canonical_subject_identity)
    return create_next_wo_handoff(record, created_at=NOW,
        current_readiness_identity=p.readiness_identity,
        current_pointer_integrity=p.integrity_identity, currentness=p.currentness,
        superseded_readiness_identity=p.superseded_readiness_identity,
        first_five_of_five_at=NOW)


def estate(root):
    return {str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}


def test_matching_absent_and_present_expectations_commit(tmp_path):
    store = Wo09Store(tmp_path)
    record, reqs = evaluated()
    absent = store.expectation(record.canonical_subject_identity)
    assert absent.pointer is None and not tmp_path.exists() is False
    pointer = store.retain(record, reqs, expected=absent)
    assert store.expectation(record.canonical_subject_identity).pointer == pointer
    assert store.retain(record, reqs, expected=store.expectation(record.canonical_subject_identity)) == pointer
    h = handoff(store, record)
    store.retain_handoff(h, expected=store.expectation(record.canonical_subject_identity))
    assert store.load_handoff(h.handoff_identity) == h
    assert store.restore_current() == ((pointer, record),)
    assert len(store.load_requirements(record.readiness_identity)) == 5


def test_observational_expectation_creates_nothing(tmp_path):
    root = tmp_path / 'absent'
    store = Wo09Store(root)
    assert store.expectation('NSE-EQ-TEST').pointer is None
    assert not root.exists()


@pytest.mark.parametrize('writer', ['readiness', 'currentness', 'handoff'])
def test_all_writers_reject_stale_currentness_without_success(tmp_path, writer):
    store = Wo09Store(tmp_path)
    record, reqs = evaluated()
    retain(store, record, reqs)
    old = store.expectation(record.canonical_subject_identity)
    h = handoff(store, record)
    store.mark_currentness(record.canonical_subject_identity, CurrentnessState.REASSESSMENT_DUE,
                          updated_at=NOW + timedelta(seconds=1), expected=old)
    before = estate(tmp_path); notices = []
    store.notification_listener = lambda *args: notices.append(args)
    with pytest.raises(Wo09PublicationConflict) as caught:
        if writer == 'readiness':
            store.retain(record, reqs, expected=old)
        elif writer == 'currentness':
            store.mark_currentness(record.canonical_subject_identity, CurrentnessState.SUPERSEDED,
                                  updated_at=NOW + timedelta(seconds=2), expected=old)
        else:
            store.retain_handoff(h, expected=old)
    assert caught.value.failure_stage == 'PUBLICATION_CONFLICT'
    assert caught.value.failure_reason == 'WO09_PUBLICATION_EXPECTATION_CHANGED'
    assert estate(tmp_path) == before and notices == []


def test_expected_absence_is_not_wildcard(tmp_path):
    store = Wo09Store(tmp_path); record, reqs = evaluated()
    absent = store.expectation(record.canonical_subject_identity)
    retain(store, record, reqs)
    before = estate(tmp_path)
    with pytest.raises(Wo09PublicationConflict):
        store.retain(record, reqs, expected=absent)
    assert estate(tmp_path) == before


def test_forward_predecessor_and_timestamp_are_compared(tmp_path):
    store = Wo09Store(tmp_path); record, reqs = evaluated()
    retain(store, record, reqs); old = store.expectation(record.canonical_subject_identity)
    newer, next_reqs = evaluate_readiness(source(), evidence(), created_at=NOW + timedelta(seconds=1))
    new = store.retain(newer, next_reqs, expected=old)
    assert new.superseded_readiness_identity == record.readiness_identity
    with pytest.raises(Wo09PublicationConflict):
        store.retain(record, reqs, expected=old)
    assert store.load_pointer(record.canonical_subject_identity) == new


@pytest.mark.parametrize('kind', ['root', 'subject', 'type'])
def test_expectation_contract_errors_are_not_conflicts(tmp_path, kind):
    store = Wo09Store(tmp_path); record, reqs = evaluated()
    e = store.expectation(record.canonical_subject_identity)
    if kind == 'root':
        e = replace(e, root_key=tmp_path / 'other')
    elif kind == 'subject':
        e = replace(e, canonical_subject_identity='NSE-EQ-OTHER')
    else:
        e = object()
    with pytest.raises(Wo09PersistenceError) as caught:
        store.retain(record, reqs, expected=e)
    assert not isinstance(caught.value, Wo09PublicationConflict)
    assert not store.current.exists()


def test_required_keyword_cannot_silently_recapture(tmp_path):
    store = Wo09Store(tmp_path); record, reqs = evaluated()
    with pytest.raises(TypeError, match='expected'):
        store.retain(record, reqs)
    with pytest.raises(TypeError, match='expected'):
        store.mark_currentness(record.canonical_subject_identity, CurrentnessState.SUPERSEDED, updated_at=NOW)
    with pytest.raises(TypeError, match='expected'):
        store.retain_handoff(None)
    assert not store.current.exists()


@pytest.mark.parametrize('corrupt', ['pointer', 'readiness'])
def test_corruption_is_integrity_failure_never_cas(tmp_path, corrupt):
    store = Wo09Store(tmp_path); record, reqs = evaluated()
    retain(store, record, reqs); e = store.expectation(record.canonical_subject_identity)
    path = (next(store.current.glob('*.json')) if corrupt == 'pointer'
            else store.readiness / (record.readiness_identity + '.json'))
    original = path.read_bytes()
    path.write_bytes(original.replace(record.integrity_identity.encode(), b'bad-integrity'))
    with pytest.raises(ValueError) as caught:
        with store.transaction(expected=e):
            pytest.fail('corrupt state reached final effect')
    assert not isinstance(caught.value, Wo09PublicationConflict)


@pytest.mark.parametrize('other', ['same', 'subject', 'root'])
def test_nested_public_writer_rejected_before_wait(tmp_path, other):
    store = Wo09Store(tmp_path); record, reqs = evaluated()
    target = Wo09Store(tmp_path / 'other') if other == 'root' else Wo09Store(tmp_path)
    subject = 'NSE-EQ-OTHER' if other == 'subject' else record.canonical_subject_identity
    with store.transaction(expected=store.expectation(record.canonical_subject_identity)):
        with pytest.raises(Wo09MutationReentry, match='WO09_MUTATION_REENTRY_NOT_PERMITTED'):
            with target.transaction(expected=target.expectation(subject)):
                pytest.fail('nested transaction entered')
        with pytest.raises(Wo09MutationReentry):
            store.retain(record, reqs, expected=store.expectation(record.canonical_subject_identity))


def test_token_is_one_effect_thread_bound_and_closed(tmp_path):
    store = Wo09Store(tmp_path); record, reqs = evaluated(); errors = []
    with store.transaction(expected=store.expectation(record.canonical_subject_identity)) as token:
        def misuse():
            try:
                token.retain_readiness(record, reqs)
            except Exception as exc:
                errors.append(exc)
        thread = Thread(target=misuse); thread.start(); thread.join(3)
        assert not thread.is_alive() and len(errors) == 1
        assert str(errors[0]) == 'WO09_MUTATION_TOKEN_INVALID'
        token.retain_readiness(record, reqs)
        with pytest.raises(Wo09PersistenceError, match='WO09_MUTATION_TOKEN_INVALID'):
            token.retain_readiness(record, reqs)
    with pytest.raises(Wo09PersistenceError, match='WO09_MUTATION_TOKEN_INVALID'):
        token.retain_readiness(record, reqs)


@pytest.mark.parametrize('writer', ['readiness', 'currentness', 'handoff'])
def test_same_root_writer_waits_and_does_not_recapture(tmp_path, monkeypatch, writer):
    store = Wo09Store(tmp_path); other = Wo09Store(tmp_path / '.' )
    record, reqs = evaluated(); retain(store, record, reqs)
    e = store.expectation(record.canonical_subject_identity); h = handoff(store, record)
    attempted = Event(); compared = Event(); finished = Event(); errors = []
    key = (e.root_key, e.canonical_subject_identity)
    class TracedLock:
        def __init__(self): self.lock = Lock()
        def __enter__(self):
            attempted.set(); self.lock.acquire(); return self
        def __exit__(self, *args): self.lock.release()
    controller = TracedLock()
    monkeypatch.setitem(persistence._MUTATION_CONTROLLERS, key, controller)
    compare = other._compare
    def traced_compare(expected):
        compared.set(); return compare(expected)
    monkeypatch.setattr(other, '_compare', traced_compare)
    def competing():
        try:
            if writer == 'readiness': other.retain(record, reqs, expected=e)
            elif writer == 'handoff': other.retain_handoff(h, expected=e)
            else: other.mark_currentness(record.canonical_subject_identity, CurrentnessState.SUPERSEDED,
                                        updated_at=NOW + timedelta(seconds=2), expected=e)
        except Exception as exc: errors.append(exc)
        finally: finished.set()
    with store.transaction(expected=e) as token:
        attempted.clear(); thread = Thread(target=competing); thread.start()
        assert attempted.wait(3) and controller.lock.locked()
        assert not compared.is_set() and not finished.is_set()
        token.mark_currentness(record.canonical_subject_identity, CurrentnessState.REASSESSMENT_DUE,
                              updated_at=NOW + timedelta(seconds=1))
    thread.join(3)
    assert not thread.is_alive() and finished.is_set() and compared.is_set()
    assert len(errors) == 1 and type(errors[0]) is Wo09PublicationConflict
    assert not store.handoffs.exists()


def test_distinct_root_subject_and_resolved_alias_controllers(tmp_path):
    root = tmp_path / 'store'; root.mkdir()
    alias = tmp_path / 'alias'; alias.symlink_to(root, target_is_directory=True)
    a, b = Wo09Store(root), Wo09Store(alias)
    assert a.expectation('NSE-EQ-TEST') == b.expectation('NSE-EQ-TEST')
    with a.transaction(expected=a.expectation('NSE-EQ-TEST')):
        outcomes = []
        def independent():
            with b.transaction(expected=b.expectation('MCX-FUT-COPPER')): outcomes.append('subject')
            c = Wo09Store(tmp_path / 'other')
            with c.transaction(expected=c.expectation('NSE-EQ-TEST')): outcomes.append('root')
        thread = Thread(target=independent); thread.start(); thread.join(3)
        assert not thread.is_alive() and outcomes == ['subject', 'root']


def test_notice_runs_after_transaction_and_idempotent_write_is_silent(tmp_path):
    store = Wo09Store(tmp_path); record, reqs = evaluated(); notices = []
    def listener(kind, identity):
        complete = Event()
        def inspect():
            with Wo09Store(tmp_path).transaction(expected=store.expectation(record.canonical_subject_identity)):
                complete.set()
        thread = Thread(target=inspect); thread.start(); thread.join(3)
        assert not thread.is_alive() and complete.is_set()
        notices.append((kind, identity))
    store.notification_listener = listener
    retain(store, record, reqs)
    assert notices == [('READINESS', record.readiness_identity)]
    retain(store, record, reqs)
    assert len(notices) == 1


@pytest.mark.parametrize('phase', ['before', 'after'])
def test_pointer_storage_failure_preserves_truth_and_no_success(tmp_path, monkeypatch, phase):
    store = Wo09Store(tmp_path); record, reqs = evaluated(); notices = []
    store.notification_listener = lambda *args: notices.append(args)
    atomic = store._atomic
    def fail(path, payload):
        if phase == 'after': atomic(path, payload)
        raise OSError('EXACT_REPLACE_FAILURE_' + phase)
    monkeypatch.setattr(store, '_atomic', fail)
    with pytest.raises(OSError, match='EXACT_REPLACE_FAILURE_' + phase):
        retain(store, record, reqs)
    assert notices == [] and store.load_readiness(record.readiness_identity) == record
    pointer = store.load_pointer(record.canonical_subject_identity)
    assert (pointer is None) == (phase == 'before')
    if phase == 'after': assert store.restore_current() == ((pointer, record),)


def test_handoff_wrong_graph_rejected_without_mutation(tmp_path):
    store = Wo09Store(tmp_path); record, reqs = evaluated(); retain(store, record, reqs)
    h = handoff(store, record)
    # Make a valid different handoff from another lawful readiness graph.
    other, other_reqs = evaluate_readiness(source(subject='NSE-EQ-OTHER'),
        evidence(subject='NSE-EQ-OTHER'), created_at=NOW)
    other_store = Wo09Store(tmp_path / 'other'); retain(other_store, other, other_reqs)
    wrong = handoff(other_store, other)
    with pytest.raises(Wo09PersistenceError, match='WO09_MUTATION_TOKEN_INVALID'):
        store.retain_handoff(wrong, expected=store.expectation(record.canonical_subject_identity))
    store.retain_handoff(h, expected=store.expectation(record.canonical_subject_identity))
    assert store.load_handoff(h.handoff_identity) == h


def test_fixed_boundary_reads_real_retained_graph_and_rejects_arbitrary_constructor(tmp_path):
    from tests.unit.intraday.test_wo11_lifecycle_application import early_source_fixture, BOUNDARY
    from tests.unit.intraday.recovery_r2b_fixtures import governed_graph
    from kronos.application.intraday_evidence_currentness import IntradayPublicationBoundary
    _,facts,mapping,run=early_source_fixture()
    graph=governed_graph(tmp_path,mapping,run,facts,clock=lambda:BOUNDARY)
    captured=graph.boundary.capture_readiness(record=graph.reconciliation.store.restore_current(
        graph.readiness.review_cycle_identity),semantic=mapping.semantic_evidence,
        selection=mapping.completed_evidence,
        visual=graph.review.review_store.load_visual_evidence(graph.readiness.visual_evidence_identity),created_at=BOUNDARY)
    with graph.boundary.final_readiness(captured) as mutation:
        pointer=mutation.retain_readiness(graph.readiness,graph.requirements)
    assert graph.wo09.load_pointer(graph.readiness.canonical_subject_identity)==pointer
    assert graph.readiness.satisfied_count==5
    with pytest.raises(TypeError):
        IntradayPublicationBoundary(scope=lambda:Lock(),read=lambda *a:(),assess=lambda *a:True)


def test_committed_notice_captures_callback_and_failure_cannot_rollback(tmp_path):
    store=Wo09Store(tmp_path);record,reqs=evaluated();calls=[]
    def captured(kind,identity):
        calls.append((kind,identity))
        raise RuntimeError('notification failed after commit')
    store.notification_listener=captured
    with store.transaction(expected=store.expectation(record.canonical_subject_identity)) as token:
        pointer=token.retain_readiness(record,reqs)
    store.notification_listener=lambda *args:pytest.fail('replacement callback used')
    assert calls==[]
    store.notify_publication(token.notices)
    assert calls==[('READINESS',record.readiness_identity)]
    assert store.notification_failure=='NOTIFICATION_PROJECTION_UNAVAILABLE'
    assert store.restore_current()==((pointer,record),)


@pytest.mark.parametrize('phase',['before_transaction','after_acquire','before_write','immutable_write','after_commit_before_dispatch'])
def test_readiness_failure_matrix_exact_source_truth(tmp_path,monkeypatch,phase):
    store=Wo09Store(tmp_path);record,reqs=evaluated();calls=[]
    store.notification_listener=lambda *args:calls.append(args)
    expected=store.expectation(record.canonical_subject_identity)
    if phase=='before_transaction':
        def fail(expected):raise OSError('INJECTED_BEFORE_TRANSACTION')
        monkeypatch.setattr(store,'_check_expectation',fail)
    elif phase=='after_acquire':
        def fail(expected):raise OSError('INJECTED_AFTER_ACQUIRE')
        monkeypatch.setattr(store,'_compare',fail)
    elif phase=='before_write':
        def fail(*args):raise OSError('INJECTED_BEFORE_WRITE')
        monkeypatch.setattr(store,'_retain_readiness',fail)
    elif phase=='immutable_write':
        def fail(*args):raise OSError('INJECTED_IMMUTABLE_WRITE')
        monkeypatch.setattr(store,'_retain',fail)
    else:
        def fail(*args):raise OSError('INJECTED_AFTER_COMMIT_BEFORE_DISPATCH')
        monkeypatch.setattr(store,'notify_publication',fail)
    with pytest.raises(OSError,match='INJECTED_') as caught:
        store.retain(record,reqs,expected=expected)
    assert not isinstance(caught.value,Wo09PublicationConflict) and calls==[]
    pointer=store.load_pointer(record.canonical_subject_identity)
    if phase=='after_commit_before_dispatch':
        assert store.restore_current()==((pointer,record),)
        assert store.load_requirements(record.readiness_identity)==reqs
        # Crash before enqueue is a missing projection, not rolled-back source.
    else:
        assert pointer is None and not store.readiness.exists()


def test_well_formed_different_expected_pointer_conflicts_not_integrity(tmp_path):
    from kronos.intraday.wo09_persistence import create_pointer
    store=Wo09Store(tmp_path);record,reqs=evaluated();retain(store,record,reqs)
    expected=store.expectation(record.canonical_subject_identity)
    different=create_pointer(record,currentness=CurrentnessState.CURRENT,superseded=None,updated_at=NOW+timedelta(microseconds=1))
    assert different.integrity_identity!=expected.pointer.integrity_identity
    with pytest.raises(Wo09PublicationConflict):
        with store.transaction(expected=replace(expected,pointer=different)):
            pytest.fail('different full expectation admitted')
    assert store.expectation(record.canonical_subject_identity)==expected


def test_immutable_fsync_failure_is_storage_not_conflict(tmp_path,monkeypatch):
    store=Wo09Store(tmp_path);record,reqs=evaluated();calls=[]
    store.notification_listener=lambda *args:calls.append(args)
    def fail(*args):raise OSError('EXACT_IMMUTABLE_FSYNC_FAILURE')
    monkeypatch.setattr(persistence.os,'fsync',fail)
    with pytest.raises(OSError,match='EXACT_IMMUTABLE_FSYNC_FAILURE') as caught:
        retain(store,record,reqs)
    assert not isinstance(caught.value,Wo09PublicationConflict)
    assert store.load_pointer(record.canonical_subject_identity) is None and calls==[]
    assert store.load_readiness(record.readiness_identity)==record
    assert store.load_requirements(record.readiness_identity)==()
