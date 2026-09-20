"""WO-05 deterministic filesystem commit/fence/recovery proofs, no services."""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json
from threading import Barrier, Thread

import pytest

from kronos.swing import run_publication as pub
from kronos.swing.run_provenance import LocalSwingRunProvenanceStore, SwingAnalysisRunProvenance
from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
from kronos.swing.v1.native_discovery import NativeDiscoveryEvidenceStore
from kronos.swing.v1.relative_context import RelativeContextEvidenceStore, build_relative_context_run
from kronos.swing.v1 import opportunity_continuity as c
from kronos.swing.universe import SWING_PHASE1_UNIVERSE
from tests.unit.swing.v1.test_opportunity_continuity import scenario, later, row


def provenance(snapshot):
    return SwingAnalysisRunProvenance(snapshot.run_identity, snapshot.observed_at,
        snapshot.observed_at, "SWING-MARKET-DATA-SNAPSHOT-" + "a" * 64, snapshot.observed_at)


@pytest.fixture
def checkpoint(tmp_path, scenario):
    snapshot, bindings = scenario
    return make_checkpoint(tmp_path, snapshot, bindings)


def make_checkpoint(tmp_path, snapshot, bindings):
    coordinator = pub.SwingRunPublication(tmp_path / "publication",
        mtf_store=MtfFactEvidenceStore(tmp_path / "mtf"),
        native_store=NativeDiscoveryEvidenceStore(tmp_path / "native"),
        relative_store=RelativeContextEvidenceStore(tmp_path / "relative"),
        provenance_store=LocalSwingRunProvenanceStore(tmp_path / "provenance"))
    native = c.prepare_continuity(snapshot, bindings).native_run
    for store, value in ((coordinator.mtf_store, snapshot), (coordinator.native_store, native),
                        (coordinator.relative_store, build_relative_context_run(snapshot, SWING_PHASE1_UNIVERSE)),
                        (coordinator.provenance_store, provenance(snapshot))):
        store.retain(value)
    refs = coordinator._references(snapshot.run_identity, continuity=False)
    original = {k: p.read_bytes() for k,p in coordinator._paths(snapshot.run_identity).items() if k != "continuity"}
    committed = coordinator.adopt(snapshot.run_identity, {k:v for k,v in refs.items() if k != "continuity"})
    assert committed.continuity is None
    assert original == {k: p.read_bytes() for k,p in coordinator._paths(snapshot.run_identity).items() if k != "continuity"}
    return coordinator, snapshot, bindings, committed


def prepared(coordinator, snapshot, bindings, number):
    updated = later(snapshot, number)
    token, prior = coordinator.admit(updated.run_identity, updated.observed_at)
    continuity = c.prepare_continuity(updated, bindings, predecessor=prior.continuity,
        adopted_predecessor=prior if prior.continuity is None else None)
    args = dict(mtf=updated, native=continuity.native_run,
        relative=build_relative_context_run(updated, SWING_PHASE1_UNIVERSE),
        provenance=provenance(updated), continuity=continuity)
    return token, args


def test_04_05_06_late_success_error_never_override_latest(checkpoint):
    co, snapshot, bindings, p = checkpoint
    a, av = prepared(co, snapshot, bindings, 2)
    b, bv = prepared(co, snapshot, bindings, 3)
    br = co.prepare(b, **bv)
    assert co.publish(b, br, bv['mtf'].observed_at)
    ar = co.prepare(a, **av)
    assert co.publish(a, ar, av['mtf'].observed_at) is None
    assert co.fail(a, av['mtf'].observed_at) is False
    assert co.current().native.run_identity == b.run_id
    assert co.status()['latest_attempt']['state'] == 'SUCCEEDED'
    assert co.publish(b, br, bv['mtf'].observed_at) is None


def test_05_b_failed_a_late_cannot_be_fallback(checkpoint):
    co, snapshot, bindings, p = checkpoint
    a, av = prepared(co, snapshot, bindings, 2)
    b, bv = prepared(co, snapshot, bindings, 3)
    assert co.fail(b, bv['mtf'].observed_at)
    assert co.publish(a, co.prepare(a, **av), av['mtf'].observed_at) is None
    assert co.current().reference == p.reference
    assert co.status()['latest_attempt']['run_id'] == b.run_id
    assert co.status()['latest_attempt']['state'] == 'FAILED'


@pytest.mark.parametrize('phase', ['after_mtf','after_native','after_relative','after_provenance',
                                 'after_continuity','after_manifest','before_control_replace'])
def test_08_fault_boundaries_preserve_prior(checkpoint, phase):
    co, snapshot, bindings, p = checkpoint
    token, values = prepared(co, snapshot, bindings, 2)
    def fail(at):
        if at == phase:
            raise OSError('controlled fault')
    co.fault = fail
    with pytest.raises(OSError):
        ref = co.prepare(token, **values)
        co.publish(token, ref, values['mtf'].observed_at)
    assert co.current().reference == p.reference


def test_03_admission_failure_no_operation_dispatched(checkpoint):
    co, snapshot, bindings, p = checkpoint
    before = co.status()
    def fail(phase):
        if phase == 'before_control_replace':
            raise OSError('admission fault')
    co.fault = fail
    dispatched = []
    with pytest.raises(OSError):
        co.admit(later(snapshot).run_identity, later(snapshot).observed_at)
        dispatched.append(True)
    assert not dispatched and co.status() == before


def test_07_two_local_writers_stable_lock(checkpoint):
    co, snapshot, bindings, p = checkpoint
    other = pub.SwingRunPublication(co.root, mtf_store=co.mtf_store, native_store=co.native_store,
        relative_store=co.relative_store, provenance_store=co.provenance_store)
    barrier = Barrier(2)
    results, errors = [], []
    def work(owner, number):
        try:
            barrier.wait()
            run = later(snapshot, number)
            results.append(owner.admit(run.run_identity, run.observed_at)[0])
        except Exception as error:
            errors.append(error)
    inode = (co.root/'publication.lock').stat().st_ino
    threads = [Thread(target=work,args=(co,2)),Thread(target=work,args=(other,3))]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=30)
    assert not any(t.is_alive() for t in threads) and not errors
    assert sorted(t.generation for t in results) == [1,2]
    assert (co.root/'publication.lock').stat().st_ino == inode
    assert all(t.predecessor_manifest == p.reference for t in results)


def test_09_10_11_12_integrity_orphans_recovery(checkpoint):
    co, snapshot, bindings, p = checkpoint
    token, values = prepared(co, snapshot, bindings, 2)
    reference = co.prepare(token, **values)
    assert co.current().reference == p.reference  # Prepared/newer Native is not current.
    co.recover(values['mtf'].observed_at)
    assert co.status()['latest_attempt']['state'] == 'INTERRUPTED'
    assert co.publish(token, reference, values['mtf'].observed_at) is None
    b, bv = prepared(co, snapshot, bindings, 3)
    br = co.prepare(b, **bv)
    co.publish(b, br, bv['mtf'].observed_at)  # Crash before any projection install.
    restored = co.recover(bv['mtf'].observed_at)
    assert restored.native == bv['native'] and restored.mtf == bv['mtf']
    assert restored.continuity.contribution == bv['continuity']
    path = co._paths(b.run_id)['native']
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='BUNDLE_INVALID'):
        co.current()  # Never fall back to P or an orphan.


def test_13_uncertain_replace_rereads_control(checkpoint):
    co, snapshot, bindings, p = checkpoint
    token, values = prepared(co, snapshot, bindings, 2)
    reference = co.prepare(token, **values)
    def fail(at):
        if at == 'after_control_replace': raise OSError('uncertain')
    co.fault = fail
    assert co.publish(token, reference, values['mtf'].observed_at)
    assert co.current().reference == reference


def test_16_adoption_exact_no_backfill(checkpoint):
    co, snapshot, bindings, p = checkpoint
    assert p.manifest['kind'] == 'ADOPTED_EXISTING_CHECKPOINT'
    assert p.manifest['artifacts']['continuity'] is None and p.continuity is None
    refs = {k:v for k,v in p.manifest['artifacts'].items() if k != 'continuity'}
    refs['native'] = {**refs['native'], 'sha256':'0'*64}
    with pytest.raises(ValueError, match='CHECKPOINT_INVALID'):
        co.adopt(snapshot.run_identity,refs)
    assert co.current().reference == p.reference


def test_17_18_19_continuity_through_committed_bundle(checkpoint):
    co, snapshot, bindings, p = checkpoint
    a, av = prepared(co,snapshot,bindings,2)
    first = co.publish(a,co.prepare(a,**av),av['mtf'].observed_at)
    b, bv = prepared(co,snapshot,bindings,3)
    second = co.publish(b,co.prepare(b,**bv),bv['mtf'].observed_at)
    assert row(first.continuity.contribution).opportunity_id == row(second.continuity.contribution).opportunity_id
    assert row(first.continuity.contribution).material_revision == row(second.continuity.contribution).material_revision
    assert first.native.result_sha256 != second.native.result_sha256
    assert co.native_store.load(a.run_id) == first.native


def test_17_new_probable_origin_only_after_committed_new_evidence(tmp_path, scenario):
    from tests.unit.swing.v1.test_native_discovery import _fact, FactualTimeframe as TF
    snapshot, bindings = scenario
    gold = snapshot.instrument('GOLDM')
    failed = _fact(TF.FOUR_HOUR,close=80.0,bucket='FULL_DURATION')
    old_gold = replace(gold,timeframes=tuple(failed if f.timeframe is TF.FOUR_HOUR else f for f in gold.timeframes))
    old = replace(snapshot,instruments=tuple(old_gold if i.canonical_instrument=='GOLDM' else i for i in snapshot.instruments))
    co, _, _, adopted = make_checkpoint(tmp_path,old,bindings)
    updates={f.timeframe:replace(f,observation_boundary=f.observation_boundary+timedelta(hours=4),
        source_timestamp=f.source_timestamp+timedelta(hours=4)) for f in gold.timeframes if f.timeframe in {TF.FOUR_HOUR,TF.ONE_HOUR}}
    current=later(snapshot,2,changes=updates)
    token, prior=co.admit(current.run_identity,current.observed_at)
    draft=c.prepare_continuity(current,bindings,adopted_predecessor=prior)
    assert row(draft).opportunity_id is not None
    assert co.current().continuity is None
    ref=co.prepare(token,mtf=current,native=draft.native_run,
        relative=build_relative_context_run(current,SWING_PHASE1_UNIVERSE),
        provenance=provenance(current),continuity=draft)
    committed=co.publish(token,ref,current.observed_at)
    assert row(committed.continuity.contribution).opportunity_id==row(draft).opportunity_id
    refreshed=later(current,3)
    second_token,previous=co.admit(refreshed.run_identity,refreshed.observed_at)
    second=c.prepare_continuity(refreshed,bindings,predecessor=previous.continuity)
    assert row(second).opportunity_id==row(draft).opportunity_id
    assert row(second).material_revision==row(draft).material_revision
    second_ref=co.prepare(second_token,mtf=refreshed,native=second.native_run,
        relative=build_relative_context_run(refreshed,SWING_PHASE1_UNIVERSE),
        provenance=provenance(refreshed),continuity=second)
    co.publish(second_token,second_ref,refreshed.observed_at)
    hour=refreshed.instrument('GOLDM').fact(TF.ONE_HOUR)
    next_hour=replace(hour,source_timestamp=hour.source_timestamp+timedelta(hours=1),
        observation_boundary=hour.observation_boundary+timedelta(hours=1))
    third_snapshot=later(refreshed,4,changes={TF.ONE_HOUR:next_hour})
    third_snapshot=replace(third_snapshot,observed_at=third_snapshot.observed_at+timedelta(days=1))
    third_token,previous=co.admit(third_snapshot.run_identity,third_snapshot.observed_at)
    third=c.prepare_continuity(third_snapshot,bindings,predecessor=previous.continuity)
    third_ref=co.prepare(third_token,mtf=third_snapshot,native=third.native_run,
        relative=build_relative_context_run(third_snapshot,SWING_PHASE1_UNIVERSE),
        provenance=provenance(third_snapshot),continuity=third)
    result=co.publish(third_token,third_ref,third_snapshot.observed_at)
    assert row(result.continuity.contribution).consumptions==row(second).consumptions
    assert row(third).opportunity_id==row(second).opportunity_id
    assert row(third).material_revision!=row(second).material_revision


def test_adopted_legacy_state_not_reset_or_backfilled(checkpoint):
    co, snapshot, bindings, p = checkpoint
    next_snapshot = later(snapshot)
    draft = c.prepare_continuity(next_snapshot, bindings, adopted_predecessor=p)
    assert all(r.opportunity_id is None and r.material_revision is None for r in draft.rows)
    assert all(r.disposition is c.ContinuityDisposition.MANUAL_REVIEW_REQUIRED for r in draft.rows)
    assert all(a.predecessor_result_sha256 is not None for a in draft.native_run.assessments)
    assert co.current().native == p.native


@pytest.mark.parametrize('fault', ['missing', 'hash', 'run', 'schema'])
def test_09_prepared_artifact_fault_blocks_commit(checkpoint, fault):
    co, snapshot, bindings, prior = checkpoint
    token, values = prepared(co, snapshot, bindings, 2)
    ref = co.prepare(token, **values)
    path = co._paths(token.run_id)['native']
    if fault == 'missing':
        path.unlink()  # Disposable isolated fixture, not retained production evidence.
    elif fault == 'hash':
        path.write_bytes(path.read_bytes() + b' ')
    else:
        payload = json.loads(path.read_bytes())
        if fault == 'schema':
            payload['schema'] = 'UNSUPPORTED'
        else:
            payload['run']['run_identity'] = snapshot.run_identity
        path.write_bytes(pub._bytes(payload))
        # Even a newly computed outer digest cannot bypass typed owner checks.
        manifest = json.loads(co._manifest_path(ref).read_bytes())
        manifest['artifacts']['native']['sha256'] = sha256(path.read_bytes()).hexdigest()
        digest = pub._hash(manifest)
        ref = {'path': 'manifests/' + digest + '.json', 'sha256': digest}
        co._manifest_path(ref).write_bytes(pub._bytes(manifest))
    with pytest.raises(ValueError, match='BUNDLE_INVALID'):
        co.publish(token, ref, values['mtf'].observed_at)
    assert co.current().reference == prior.reference


@pytest.mark.parametrize('field,value', [('latest_attempt',None),('admission_generation',True),
                                        ('schema_version','UNKNOWN')])
def test_09_malformed_control_is_bounded_and_never_repaired(checkpoint, field, value):
    co, snapshot, bindings, prior = checkpoint
    control = co.status()
    control[field] = value
    raw = pub._bytes({**control,'integrity_sha256':pub._hash(control)})
    (co.root/'control.json').write_bytes(raw)
    with pytest.raises(ValueError,match='SWING_PUBLICATION_CONTROL_INVALID'):
        co.recover(snapshot.observed_at)
    assert (co.root/'control.json').read_bytes() == raw


def test_07_two_writers_only_latest_can_publish(checkpoint):
    co, snapshot, bindings, prior = checkpoint
    first, av = prepared(co, snapshot, bindings, 2)
    second, bv = prepared(co, snapshot, bindings, 3)
    refs = [co.prepare(first, **av), co.prepare(second, **bv)]
    barrier, results, errors = Barrier(2), [], []
    def finish(token, reference, values):
        try:
            barrier.wait()
            results.append(co.publish(token, reference, values['mtf'].observed_at))
        except Exception as error:
            errors.append(error)
    threads = [Thread(target=finish, args=args) for args in
               ((first, refs[0], av), (second, refs[1], bv))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors and not any(thread.is_alive() for thread in threads)
    assert sum(result is not None for result in results) == 1
    assert co.current().native.run_identity == second.run_id


def test_publish_validates_before_one_precommit_authority_gate(checkpoint):
    co, snapshot, bindings, prior = checkpoint
    token, values = prepared(co, snapshot, bindings, 2)
    reference = co.prepare(token, **values)
    events = []

    def reject(bundle):
        events.append((bundle.reference, co.current().reference))
        return False

    with pytest.raises(ValueError, match="SWING_PUBLICATION_COMMIT_NOT_AUTHORIZED"):
        co.publish(
            token,
            reference,
            values["mtf"].observed_at,
            before_commit=reject,
        )
    assert events == [(reference, prior.reference)]
    assert co.current().reference == prior.reference

    native_path = co._paths(token.run_id)["native"]
    native_bytes = native_path.read_bytes()

    def corrupt_after_validation(bundle):
        events.append((bundle.reference, co.current().reference))
        native_path.write_bytes(native_bytes + b" ")
        return True

    with pytest.raises(ValueError, match="SWING_PUBLICATION_CONSTRAINT_INVALID"):
        co.publish(
            token,
            reference,
            values["mtf"].observed_at,
            before_commit=corrupt_after_validation,
        )
    assert co.current().reference == prior.reference
    native_path.write_bytes(native_bytes)

    with pytest.raises(ValueError, match="SWING_PUBLICATION_COMMIT_NOT_AUTHORIZED"):
        co.publish(
            token,
            reference,
            values["mtf"].observed_at,
            before_commit=lambda bundle: (
                events.append((bundle.reference, co.current().reference)) or True
            ),
            commit_ready=lambda bundle: (
                events.append((bundle.reference, co.current().reference)) or False
            ),
        )
    assert co.current().reference == prior.reference

    committed = co.publish(
        token,
        reference,
        values["mtf"].observed_at,
        before_commit=lambda bundle: (
            events.append((bundle.reference, co.current().reference)) or True
        ),
        commit_ready=lambda bundle: (
            events.append((bundle.reference, co.current().reference)) or True
        ),
    )
    assert committed.reference == reference
    assert events == [
        (reference, prior.reference),
        (reference, prior.reference),
        (reference, prior.reference),
        (reference, prior.reference),
        (reference, prior.reference),
        (reference, prior.reference),
    ]
    assert co.current().reference == reference


def test_17_C01_to_C11_continuity_replayed_through_real_publication(tmp_path, scenario):
    """WO-04 transition assertions with actual five-artifact commits/recovery."""
    from tests.unit.swing.v1.test_native_discovery import _fact, FactualTimeframe as TF
    from kronos.swing.v1 import native_discovery as native
    snapshot, bindings = scenario
    # Every synthetic progression below must already be completed at observation.
    snapshot = replace(snapshot, observed_at=snapshot.observed_at + timedelta(days=1))
    gold = snapshot.instrument('GOLDM')
    failed = _fact(TF.FOUR_HOUR, close=80.0, bucket='FULL_DURATION')
    seed = replace(snapshot, instruments=tuple(
        replace(i, timeframes=tuple(failed if f.timeframe is TF.FOUR_HOUR else f for f in i.timeframes))
        if i.canonical_instrument == 'GOLDM' else i for i in snapshot.instruments))
    co, _, _, adopted = make_checkpoint(tmp_path, seed, bindings)
    def commit_next(current, selected_bindings=bindings):
        token, previous = co.admit(current.run_identity, current.observed_at)
        draft = c.prepare_continuity(current, selected_bindings,
            predecessor=previous.continuity,
            adopted_predecessor=previous if previous.continuity is None else None)
        ref = co.prepare(token, mtf=current, native=draft.native_run,
            relative=build_relative_context_run(current, SWING_PHASE1_UNIVERSE),
            provenance=provenance(current), continuity=draft)
        assert co.current().reference == previous.reference
        committed = co.publish(token, ref, current.observed_at)
        recovered = co.recover(current.observed_at)
        assert recovered.continuity == committed.continuity
        assert recovered.native == draft.native_run
        return draft
    def newer(fact, hours):
        return replace(fact, source_timestamp=fact.source_timestamp+timedelta(hours=hours),
            observation_boundary=fact.observation_boundary+timedelta(hours=hours))
    hold = newer(_fact(TF.FOUR_HOUR, close=110.0, low=90.0, high=112.0, bucket='FULL_DURATION'), 4)
    hour = newer(gold.fact(TF.ONE_HOUR), 4)
    s1 = later(snapshot, 2, changes={TF.FOUR_HOUR:hold, TF.ONE_HOUR:hour})
    b1 = commit_next(s1)
    def assessment(bundle):
        return next(a for a in bundle.native_run.assessments if a.canonical_instrument == 'GOLDM')
    assert assessment(b1).four_hour_state is native.Native4HState.STRUCTURAL_HOLD
    progress = newer(_fact(TF.FOUR_HOUR, close=116.0, bucket='FULL_DURATION'), 8)
    s2 = later(s1, 3, changes={TF.FOUR_HOUR:progress, TF.ONE_HOUR:newer(hour,4)})
    b2 = commit_next(s2)
    assert assessment(b2).four_hour_state is native.Native4HState.RESUMPTION_DEVELOPING
    assert row(b2).opportunity_id is not None
    # HOLD's interaction anchor differs from the radius-2 resumption basis.
    # Preserve WO-04's manual boundary rather than inventing a successor.
    assert row(b2).reason == 'OPERATIVE_ANCHOR_CHANGED'
    s3 = later(s2, 4)
    b3 = commit_next(s3)
    assert row(b3).opportunity_id == row(b2).opportunity_id
    assert row(b3).material_revision == row(b2).material_revision
    assert row(b3).consumptions == row(b2).consumptions
    assert assessment(b3).four_hour_state is native.Native4HState.RESUMPTION_DEVELOPING
    s4 = later(s3, 5, changes={TF.ONE_HOUR:newer(s3.instrument('GOLDM').fact(TF.ONE_HOUR),1)})
    b4 = commit_next(s4)
    assert row(b4).consumptions == row(b3).consumptions
    assert row(b4).material_revision == row(b3).material_revision
    assert row(b4).reason == 'UNRESOLVED_CONTINUITY_BREAK'
    s5 = later(s4, 6, changes={TF.FOUR_HOUR:replace(progress,close=117.0)})
    b5 = commit_next(s5)
    assert row(b5).consumptions[-1].entering_state is native.Native4HState.STRUCTURAL_HOLD
    assert assessment(b5).four_hour_state is native.Native4HState.RESUMPTION_DEVELOPING
    daily = s5.instrument('GOLDM').fact(TF.DAILY)
    s6 = later(s5, 7, changes={TF.DAILY:replace(daily,close=70.0,low=69.0)})
    b6 = commit_next(s6)
    assert 'DAILY_RADIUS2_STRUCTURAL_FAILURE' in assessment(b6).reason_codes
    assert row(b6).disposition is c.ContinuityDisposition.MANUAL_REVIEW_REQUIRED
    assert row(b6).opportunity_id == row(b2).opportunity_id
    original = co.native_store.load(s2.run_identity)
    assert original == b2.native_run  # History is exact; no Review/position dependency.
