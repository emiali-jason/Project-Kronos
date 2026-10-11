from dataclasses import asdict, replace
from datetime import timedelta
import json
import pytest

from kronos.intraday.wo09_experimental import (
    evaluate_experimental_readiness, claim_for, claim_identity, create_experimental_handoff,
    ExperimentalReadinessRecord, ExperimentalNextWoHandoff, first_five_from,
)
from kronos.intraday.wo09_persistence import Wo09Store, Wo09PersistenceError, _readiness
from kronos.intraday.wo09_readiness import CurrentnessState, artifact_bytes
from kronos.intraday.wo12_research_contract import opportunity_origin
from kronos.intraday.wo10_construction import validate_intake
from tests.unit.intraday.test_wo08_experimental import experimental_fixture


def origin_for(assessment):
    from datetime import datetime
    d = assessment.data
    return opportunity_origin(canonical_subject_identity=d['subject'], market_family=d['market_family'],
        session_identity=d['session_identity'], origin_at=datetime.fromisoformat(d['analysis_boundary']),
        probable_result_identity=d['probable_result_identity'], probables_run_identity=d['run_identity'])


def publish(store, assessment, origin, at):
    with store.transaction(expected=store.expectation(assessment.data['subject'])) as mutation:
        result = mutation.retain_experimental(assessment, origin, observed_at=at)
    store.notify_publication(mutation.notices)
    return result


@pytest.mark.parametrize('direction', ['LONG', 'SHORT'])
def test_first_five_original_claim_survives_five_four_five_restart(direction, tmp_path):
    *_, first = experimental_fixture(direction)
    origin = origin_for(first)
    from datetime import datetime
    at = datetime.fromisoformat(first.data['created_at']) + timedelta(seconds=1)
    store = Wo09Store(tmp_path)
    r1, _ = publish(store, first, origin, at)
    five = [(108,102,106)]*25+[(115,110,114),(117,110,114)]
    *_, four = experimental_fixture(direction, five_rows=five)
    assert four.data['criteria'][1]['state'] == 'OUTSTANDING'
    r2, _ = publish(store, four, origin, at+timedelta(seconds=1))
    assert r2.satisfied_count == 4
    restarted = Wo09Store(tmp_path)
    r3, _ = publish(restarted, first, origin, at+timedelta(seconds=2))
    assert r1.first_five_document == r2.first_five_document == r3.first_five_document
    assert r3.first_five_of_five_at == at
    assert len(tuple((tmp_path/'experimental-first-five').glob('*.json'))) == 1
    assert restarted.restore_current()[0][1] == r3
    assert _readiness(json.loads(artifact_bytes(r3))) == r3
    pointer = restarted.load_pointer(r3.canonical_subject_identity)
    h = create_experimental_handoff(r3, created_at=at+timedelta(seconds=3),
        current_readiness_identity=r3.readiness_identity, current_pointer_integrity=pointer.integrity_identity,
        currentness=pointer.currentness, superseded_readiness_identity=pointer.superseded_readiness_identity)
    assert type(h) is ExperimentalNextWoHandoff and h.authority == 'EXPERIMENTAL_PAPER_ONLY'
    assert h.wo07f_identity is None and h.visual_evidence_identity is None
    restarted.retain_handoff(h, expected=restarted.expectation(r3.canonical_subject_identity))
    assert restarted.load_handoff(h.handoff_identity) == h
    validate_intake(h, r3, pointer, now=at+timedelta(seconds=4), session_identity=r3.session_identity)
    with pytest.raises(ValueError, match='STALE'):
        validate_intake(h, r3, pointer, now=at+timedelta(seconds=301), session_identity=r3.session_identity)


@pytest.mark.parametrize('fail_at', ['first_five', 'readiness', 'pointer'])
def test_partial_publication_has_no_notification_or_handoff_and_keeps_original_event(tmp_path, monkeypatch, fail_at):
    *_, assessment = experimental_fixture()
    origin = origin_for(assessment)
    from datetime import datetime
    at = datetime.fromisoformat(assessment.data['created_at']) + timedelta(seconds=1)
    store = Wo09Store(tmp_path)
    notices = []
    store.notification_listener = lambda *args: notices.append(args)
    original_retain, original_atomic = store._retain, store._atomic
    def retain(path, payload):
        if fail_at == 'first_five' and path.parent == store.first_five or fail_at == 'readiness' and path.parent == store.readiness:
            raise OSError('ISOLATED_WRITE_FAILURE')
        return original_retain(path, payload)
    def atomic(path, payload):
        if fail_at == 'pointer':
            raise OSError('ISOLATED_WRITE_FAILURE')
        return original_atomic(path, payload)
    monkeypatch.setattr(store, '_retain', retain)
    monkeypatch.setattr(store, '_atomic', atomic)
    with pytest.raises(OSError):
        publish(store, assessment, origin, at)
    assert store.load_pointer(assessment.data['subject']) is None
    assert notices == [] and not tuple(store.handoffs.glob('*'))
    fact = store.load_first_five(claim_identity(claim_for(assessment, origin)))
    assert (fact is None) == (fail_at == 'first_five')
    monkeypatch.setattr(store, '_retain', original_retain)
    monkeypatch.setattr(store, '_atomic', original_atomic)
    r, _ = publish(store, assessment, origin, at+timedelta(seconds=2))
    assert r.first_five_of_five_at == (at+timedelta(seconds=2) if fact is None else at)
    assert len(notices) == 1


@pytest.mark.parametrize('failed_barrier', ['file', 'first_five_directory', 'root_directory'])
def test_orphan_first_five_must_reestablish_durability_on_every_explicit_attempt(tmp_path, monkeypatch, failed_barrier):
    import os
    import stat
    import kronos.intraday.wo09_persistence as owner
    from datetime import datetime
    assessment = experimental_fixture()[-1]
    origin = origin_for(assessment)
    at = datetime.fromisoformat(assessment.data['created_at'])
    store = Wo09Store(tmp_path)
    notices, failures = [], []
    store.notification_listener = lambda *args: notices.append(args)
    original_sync = owner.os.fsync
    failing = [True]
    def sync(descriptor):
        metadata = os.fstat(descriptor)
        is_target = (stat.S_ISREG(metadata.st_mode) if failed_barrier == 'file' else
            metadata.st_ino == (store.first_five if failed_barrier == 'first_five_directory'
                               else store.root).stat().st_ino)
        if failing[0] and is_target:
            failures.append(failed_barrier)
            raise OSError('FIRST_FIVE_DURABILITY_FAILURE')
        return original_sync(descriptor)
    monkeypatch.setattr(owner.os, 'fsync', sync)
    retained = None
    for attempt in range(2):
        with pytest.raises(OSError, match='FIRST_FIVE_DURABILITY_FAILURE'):
            publish(store, assessment, origin, at + timedelta(seconds=attempt))
        fact = store.load_first_five(claim_identity(claim_for(assessment, origin)))
        assert fact is not None
        if retained is None:
            retained = fact
        assert fact == retained
        assert store.load_pointer(assessment.data['subject']) is None
        assert notices == [] and not tuple(store.handoffs.glob('*'))
    assert len(failures) == 2
    failing[0] = False
    record, _ = publish(store, assessment, origin, at + timedelta(seconds=2))
    assert record.first_five_of_five_at == at
    assert store.load_first_five(retained.claim_identity) == retained
    assert store.load_pointer(assessment.data['subject']) is not None
    assert len(notices) == 1


def test_read_only_projection_cannot_mint_first_five(tmp_path):
    *_, assessment = experimental_fixture()
    origin = origin_for(assessment)
    from datetime import datetime
    at = datetime.fromisoformat(assessment.data['created_at'])
    r, requirements = evaluate_experimental_readiness(assessment, observed_at=at, origin=origin)
    store = Wo09Store(tmp_path)
    assert r.satisfied_count == 5 and r.first_five_document is None
    with pytest.raises(Wo09PersistenceError, match='FIRST_FIVE_NOT_RETAINED'):
        store.retain(r, requirements, expected=store.expectation(r.canonical_subject_identity))
    assert store.restore_current() == ()
    assert not tuple((tmp_path/'experimental-first-five').glob('*'))
    with pytest.raises(ValueError, match='NOT_CURRENT_FIVE'):
        create_experimental_handoff(r, created_at=at, current_readiness_identity=r.readiness_identity,
            current_pointer_integrity='POINTER', currentness=CurrentnessState.CURRENT,
            superseded_readiness_identity=None)


def test_same_claim_does_not_depend_on_analysis_cycle(tmp_path):
    *_, first = experimental_fixture()
    origin = origin_for(first)
    from datetime import datetime
    at = datetime.fromisoformat(first.data['created_at'])
    store = Wo09Store(tmp_path)
    r1, _ = publish(store, first, origin, at)
    rows = [(109,104,106),(107,100,105),(110,105,108),(120,108,115),(114,106,110),(112,103,108),(113,107,109),(114,108,113),(117,110,116)]
    # Identical source refresh is also idempotent at the exact observation boundary.
    r2, _ = publish(store, first, origin, at)
    assert r2 == r1
    assert len(tuple(store.first_five.glob('*'))) == 1


def test_experimental_notifications_reuse_ready_families_only(tmp_path):
    from kronos.application.intraday_notification_sources import ready
    from kronos.application.intraday_wo09_notifications import project_notification
    from kronos.intraday.notification_policy import telegram_text
    *_, assessment = experimental_fixture()
    from datetime import datetime
    origin = origin_for(assessment)
    r, _ = publish(Wo09Store(tmp_path), assessment, origin, datetime.fromisoformat(assessment.data['created_at']))
    notice = ready(origin, r)
    assert notice['family'] == 'READY_FIVE'
    assert 'Experimental PAPER' in telegram_text(notice)
    assert 'Experimental PAPER' in project_notification(r).summary


def test_mcx_same_contract_new_acquisition_binding_keeps_first_five(tmp_path):
    from datetime import datetime
    from dataclasses import fields
    from tests.unit.instrument.test_active_derivative_selection import _resolve, _rows
    from tests.unit.intraday.test_discovery_runtime import _publications, _bundle
    from tests.unit.intraday.test_native_pullback_policy import START, BARS
    from kronos.intraday.discovery_runtime import DiscoveryRunBoundary
    from kronos.intraday.discovery import create_machine_fact_bundle
    subject = 'MCX-SUBJECT-GOLDM'
    def source(minutes, *, rolled=False):
        boundary = START + timedelta(minutes=minutes)
        rows = None
        if rolled:
            rows = _rows()
            front = min(r.expiry for r in rows if r.name == 'GOLDM' and r.expiry >= boundary.date())
            rows = tuple(r for r in rows if r.name != 'GOLDM' or r.expiry != front)
        binding = _resolve(boundary, rows=rows).for_subject(subject).binding
        _, reconciliation = _publications()
        member = next(m for m in reconciliation.members if m.canonical_identity == subject)
        bundle = _bundle(member, DiscoveryRunBoundary(boundary, binding.domain008_session_identity, 'BOUNDARY'), reconciliation)
        values = {f.name:getattr(bundle, f.name) for f in fields(bundle) if f.name != 'bundle_identity'}
        values['source_identities'] += (binding.binding_identity, binding.provider_snapshot_identity)
        values['provenance'] += (binding.integrity_identity, binding.domain008_session_identity)
        bundle = create_machine_fact_bundle(**values)
        extra = {} if minutes == 135 else dict(rows=list(BARS)+[(117,110,116),(118,112,117)],
            five_rows=[(108,102,106)]*28+[(116,112,115),(118,115,117)])
        return experimental_fixture(minutes=minutes, subject=subject, session=binding.domain008_session_identity,
            binding=binding, bundle=bundle, **extra)[-1]
    first, later = source(135), source(150)
    assert first.data['exact_mcx_roll_lineage'] != later.data['exact_mcx_roll_lineage']
    assert first.data['exact_mcx_contract_identity'] == later.data['exact_mcx_contract_identity']
    origin = origin_for(first)
    assert claim_for(first, origin) == claim_for(later, origin)
    store = Wo09Store(tmp_path)
    one, _ = publish(store, first, origin, datetime.fromisoformat(first.data['created_at']))
    two, _ = publish(store, later, origin, datetime.fromisoformat(later.data['created_at']))
    assert one.satisfied_count == two.satisfied_count == 5
    assert one.first_five_document == two.first_five_document
    assert two.first_five_of_five_at < two.created_at
    assert len(tuple(store.first_five.glob('*.json'))) == 1
    # A real exact-contract roll is a different claim even within the same
    # opportunity and session; no inferred historical roll chain is fabricated.
    rolled = source(150, rolled=True)
    assert rolled.data['exact_mcx_contract_identity'] != later.data['exact_mcx_contract_identity']
    assert claim_for(rolled, origin) != claim_for(later, origin)
    rolled_store = Wo09Store(tmp_path/'rolled')
    new_contract, _ = publish(rolled_store, rolled, origin, datetime.fromisoformat(rolled.data['created_at']))
    assert new_contract.first_five_of_five_at == new_contract.created_at
    # A same-opportunity source refresh cannot reset the original 300s clock.
    p = store.load_pointer(two.canonical_subject_identity)
    with pytest.raises(ValueError, match='NOT_CURRENT_FIVE'):
        create_experimental_handoff(two, created_at=two.created_at,
            current_readiness_identity=two.readiness_identity, current_pointer_integrity=p.integrity_identity,
            currentness=p.currentness, superseded_readiness_identity=p.superseded_readiness_identity)


def test_concurrent_first_five_claim_uses_existing_subject_compare_and_swap(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from datetime import datetime
    from kronos.intraday.wo09_persistence import Wo09PublicationConflict
    *_, assessment = experimental_fixture()
    origin = origin_for(assessment)
    at = datetime.fromisoformat(assessment.data['created_at'])
    owners = [Wo09Store(tmp_path), Wo09Store(tmp_path)]
    expected = [s.expectation(assessment.data['subject']) for s in owners]
    barrier = Barrier(2)
    def attempt(index):
        barrier.wait()
        try:
            with owners[index].transaction(expected=expected[index]) as mutation:
                return mutation.retain_experimental(assessment, origin, observed_at=at+timedelta(seconds=index))[0]
        except Wo09PublicationConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(attempt, (0, 1)))
    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    retained = Wo09Store(tmp_path).restore_current()[0][1]
    assert retained == winners[0]
    assert len(tuple((tmp_path/'experimental-first-five').glob('*.json'))) == 1
    assert retained.first_five_of_five_at in {at, at+timedelta(seconds=1)}


def test_experimental_requirement_substitution_is_rejected(tmp_path):
    from datetime import datetime
    *_, assessment = experimental_fixture()
    store = Wo09Store(tmp_path)
    at = datetime.fromisoformat(assessment.data['created_at'])
    record, requirements = publish(store, assessment, origin_for(assessment), at)
    from kronos.intraday.wo09_readiness import create_requirement
    substituted = tuple(create_requirement(record, c, at+timedelta(seconds=1)) for c in record.criteria)
    with pytest.raises(Wo09PersistenceError, match='EXPERIMENTAL_REQUIREMENT_BINDING_INVALID'):
        store.retain(record, substituted, expected=store.expectation(record.canonical_subject_identity))
