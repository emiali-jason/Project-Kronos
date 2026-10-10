from hashlib import sha256
from pathlib import Path
import os
import pytest
from kronos.intraday.wo08_shadow_persistence import Wo08ShadowStore
from kronos.intraday.wo08_shadow_contract import record, digest
from tests.unit.intraday.test_wo08_shadow_contract import handoff, outcome, LATER


def test_inert_construction_exact_recovery_and_idempotent_bytes(tmp_path):
    store=Wo08ShadowStore(tmp_path)
    assert not store.root.exists()
    h=handoff();store.retain_handoff(h)
    before={str(p): (sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in store.root.rglob('*.json')}
    store.retain_handoff(h)
    assert {str(p): (sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in store.root.rglob('*.json')}==before
    restored=Wo08ShadowStore(tmp_path)
    assert restored.load('RUN',h.manifest.identity)==h.manifest
    assert not list(store.root.rglob('*CURRENT*')) and not list(store.root.rglob('*latest*'))


def test_t1_append_and_link_leave_t0_bytes_and_metadata_unchanged(tmp_path):
    store=Wo08ShadowStore(tmp_path);h=handoff();store.retain_handoff(h)
    p=store._path('T0',h.samples[0].identity);before=(p.read_bytes(),p.stat().st_mtime_ns)
    o=outcome(h.samples[0]);store.retain(o)
    link=record('LINK',link_id='WO08-LINK-'+digest('link'),sample_id=h.samples[0].identity,
        t0_integrity=h.samples[0].data['integrity_sha256'],outcome_ids=[o.identity],visual_reconciliation_ids=[],
        previous_sample_id=None,cluster_key_subject_session='SUBJECT:SESSION',relationship='ORIGINAL',link_created_at=LATER)
    store.retain(link);assert store.load('LINK',link.identity)==link
    assert (p.read_bytes(),p.stat().st_mtime_ns)==before


@pytest.mark.parametrize('stage',['file_fsync','directory_fsync','link','readback'])
def test_failure_does_not_claim_complete_run_and_exact_readback_settles_durability(tmp_path,monkeypatch,stage):
    store=Wo08ShadowStore(tmp_path);h=handoff()
    if stage=='file_fsync':monkeypatch.setattr(os,'fsync',lambda _fd: (_ for _ in ()).throw(OSError('injected')))
    elif stage=='directory_fsync':monkeypatch.setattr(store,'_sync',lambda _p: (_ for _ in ()).throw(OSError('injected')))
    elif stage=='link':monkeypatch.setattr(os,'link',lambda *_a,**_k: (_ for _ in ()).throw(OSError('injected')))
    else:monkeypatch.setattr(store,'_read',lambda _p: b'wrong')
    with pytest.raises((OSError,ValueError)):store.retain_handoff(h)
    assert not store._path('RUN',h.manifest.identity).exists()


def test_immutable_same_id_collision_preserves_original(tmp_path):
    store=Wo08ShadowStore(tmp_path);h=handoff();store.retain_handoff(h)
    d=h.samples[0].data;d.pop('integrity_sha256');d['quality']='UNAVAILABLE'
    changed=record('T0',**d)
    with pytest.raises(ValueError,match='COLLISION'):store.retain(changed)
    assert store.load('T0',h.samples[0].identity)==h.samples[0]


@pytest.mark.parametrize('target',['root','family','file'])
def test_no_follow_roots_families_and_files(tmp_path,target):
    store=Wo08ShadowStore(tmp_path/'owned');h=handoff()
    elsewhere=tmp_path/'other';elsewhere.mkdir()
    if target=='root':
        store.root.parent.mkdir();store.root.symlink_to(elsewhere,target_is_directory=True)
    elif target=='family':
        store.root.mkdir(parents=True);(store.root/'supplement').symlink_to(elsewhere,target_is_directory=True)
    else:
        p=store._path('SUPPLEMENT',h.samples[0].data['candle_supplement_identity']);p.parent.mkdir(parents=True)
        other=elsewhere/'evidence';other.write_bytes(b'original');p.symlink_to(other)
    with pytest.raises(ValueError,match='SYMLINK'):store.retain_handoff(h)
    assert not list(elsewhere.glob('WO08-*'))


def test_interrupted_temp_is_not_replayed_and_missing_sample_blocks_run(tmp_path):
    store=Wo08ShadowStore(tmp_path);h=handoff();store.root.mkdir()
    (store.root/'.interrupted.tmp').write_bytes(b'corrupt')
    with pytest.raises(FileNotFoundError):store.load('RUN',h.manifest.identity)
    store.retain_handoff(h)
    store._path('T0',h.samples[-1].identity).unlink()
    with pytest.raises(FileNotFoundError):Wo08ShadowStore(tmp_path).load('RUN',h.manifest.identity)


def test_corrupted_supplement_cannot_restore_valid_t0(tmp_path):
    store=Wo08ShadowStore(tmp_path);h=handoff();store.retain_handoff(h)
    p=store._path('SUPPLEMENT',h.samples[0].data['candle_supplement_identity']);p.write_bytes(b'{}')
    with pytest.raises(ValueError,match='SUPPLEMENT'):store.load('T0',h.samples[0].identity)


def test_parent_swap_during_link_does_not_redirect_publication(tmp_path,monkeypatch):
    store=Wo08ShadowStore(tmp_path/'owned');h=handoff();other=tmp_path/'external';other.mkdir()
    link=os.link
    changed=[]
    def swap(*args,**kwargs):
        if not changed:
            family=store.root/'supplement'
            family.rename(store.root/'original-supplement')
            family.symlink_to(other,target_is_directory=True)
            changed.append(True)
        return link(*args,**kwargs)
    monkeypatch.setattr(os,'link',swap)
    with pytest.raises(ValueError,match='SYMLINK'):store.retain_handoff(h)
    assert list(other.iterdir())==[]
    assert not store._path('RUN',h.manifest.identity).exists()


def test_complete_outcome_cannot_publish_without_governed_later_source(tmp_path):
    store=Wo08ShadowStore(tmp_path);h=handoff();store.retain_handoff(h)
    o=outcome(h.samples[0],state='COMPLETE_SAME_CONTRACT',quality='COMPLETE',ordered_5m_candle_ids=['LATER'],
        ordered_integrities=['HASH'],outcome_candle_supplement_identity='WO08-SUPPLEMENT-'+digest('missing'),
        outcome_candle_supplement_sha256=digest('missing'))
    with pytest.raises(FileNotFoundError):store.retain_outcome(o)
    assert not store._path('OUTCOME',o.identity).exists()


@pytest.mark.parametrize('kind',['T0','RUN'])
@pytest.mark.parametrize('stage',['before_link','final_directory_sync','final_readback'])
def test_failure_at_final_t0_and_run_preserves_truthful_exact_id_state(tmp_path,monkeypatch,kind,stage):
    store=Wo08ShadowStore(tmp_path);h=handoff();retain=store._retain
    def fault(path,payload):
        if path.parent.name==kind.lower():
            if stage=='before_link':raise OSError('before durable publication')
            if stage=='final_directory_sync':
                sync=store._sync
                def fail(p):
                    if p==path.parent:raise OSError('final directory sync')
                    return sync(p)
                monkeypatch.setattr(store,'_sync',fail)
            else:
                read=store._read
                monkeypatch.setattr(store,'_read',lambda p: b'wrong' if p==path else read(p))
        return retain(path,payload)
    monkeypatch.setattr(store,'_retain',fault)
    with pytest.raises((OSError,ValueError)):store.retain_handoff(h)
    # No false telemetry is produced by this store. After post-link uncertainty,
    # a fresh exact-ID reader establishes retained content without rewriting it.
    fresh=Wo08ShadowStore(tmp_path)
    identity=h.samples[0].identity if kind=='T0' else h.manifest.identity
    if stage=='before_link':
        with pytest.raises(FileNotFoundError):fresh.load(kind,identity)
    else:
        assert fresh.load(kind,identity)==(h.samples[0] if kind=='T0' else h.manifest)
    if kind=='T0':assert not store._path('RUN',h.manifest.identity).exists()


def later_evidence(s, *, count=3, subject=None, session=None, offset=0):
    from datetime import timedelta
    from kronos.intraday.probables_v2_persistence import _to_wire
    from kronos.intraday.contracts import IntradayTimeframe
    from tests.unit.intraday.test_probables_v2 import _candle
    from tests.unit.intraday.test_wo08_shadow_contract import fixture,BOUNDARY,canonical
    from dataclasses import replace
    schedule=fixture(0)[1].current_schedule
    if session:schedule=replace(schedule,session_id=session)
    cs=[_candle(subject or s.data['subject'],schedule,IntradayTimeframe.FIVE_MINUTES,
        BOUNDARY+timedelta(minutes=5*(i+offset)),observation_boundary=BOUNDARY+timedelta(hours=1)) for i in range(count)]
    raw=canonical({'candles':[_to_wire(c) for c in cs]})
    o=outcome(s,state='COMPLETE_SAME_CONTRACT',quality='COMPLETE',ordered_5m_candle_ids=[c.candle_identity for c in cs],
        ordered_integrities=[c.integrity_identity for c in cs],outcome_candle_supplement_identity='WO08-SUPPLEMENT-'+sha256(raw).hexdigest(),
        outcome_candle_supplement_sha256=sha256(raw).hexdigest())
    return o,raw


def test_governed_complete_t1_retains_restores_without_t0_mutation(tmp_path):
    store=Wo08ShadowStore(tmp_path);h=handoff();store.retain_handoff(h)
    p=store._path('T0',h.samples[0].identity);before=(p.read_bytes(),p.stat().st_mtime_ns)
    o,raw=later_evidence(h.samples[0]);store.retain_outcome(o,supplement=raw)
    assert Wo08ShadowStore(tmp_path).load('OUTCOME',o.identity)==o
    assert (p.read_bytes(),p.stat().st_mtime_ns)==before


@pytest.mark.parametrize('changes',[{'count':2},{'subject':'NSE-EQ-OTHER'},{'session':'OTHER'},{'offset':-1},{'offset':2}])
def test_incomplete_or_wrong_later_source_never_publishes_outcome(tmp_path,changes):
    store=Wo08ShadowStore(tmp_path);h=handoff();store.retain_handoff(h)
    o,raw=later_evidence(h.samples[0],**changes)
    with pytest.raises(ValueError):store.retain_outcome(o,supplement=raw)
    assert not store._path('OUTCOME',o.identity).exists()


def test_recovery_rejects_rehashed_wrong_governed_source(tmp_path):
    from tests.unit.intraday.test_wo08_shadow_contract import sample,canonical
    from kronos.intraday.wo08_shadow_contract import validate_t0_supplement
    import json
    store=Wo08ShadowStore(tmp_path);h=handoff();store.retain_handoff(h)
    s=h.samples[0];raw=json.loads(h.supplements[0]);raw['result']=json.loads(sample(1)[1])['result']
    bad=canonical(raw);d=s.data;d.pop('integrity_sha256')
    d.update(candle_supplement_identity='WO08-SUPPLEMENT-'+sha256(bad).hexdigest(),candle_supplement_sha256=sha256(bad).hexdigest())
    changed=record('T0',**d)
    store._path('T0',s.identity).write_bytes(changed.payload)
    p=store._path('SUPPLEMENT',changed.data['candle_supplement_identity']);p.write_bytes(bad)
    with pytest.raises(ValueError):Wo08ShadowStore(tmp_path).load('T0',s.identity)



def test_session_remainder_complete_stays_unavailable_even_with_valid_later_candles(tmp_path):
    store=Wo08ShadowStore(tmp_path);h=handoff();store.retain_handoff(h)
    o,raw=later_evidence(h.samples[0]);d=o.data;d.pop('integrity_sha256');d['horizon']='SESSION_REMAINDER'
    changed=record('OUTCOME',**d)
    with pytest.raises(ValueError,match='HORIZON_AUTHORITY_UNAVAILABLE'):
        store.retain_outcome(changed,supplement=raw)
    assert not store._path('OUTCOME',changed.identity).exists()
    # Rehashed individually valid records cannot evade owning recovery checks.
    store._path('SUPPLEMENT',changed.data['outcome_candle_supplement_identity']).write_bytes(raw)
    p=store._path('OUTCOME',changed.identity);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(changed.payload)
    with pytest.raises(ValueError,match='HORIZON_AUTHORITY_UNAVAILABLE'):
        Wo08ShadowStore(tmp_path).load('OUTCOME',changed.identity)


def test_run_recovery_rejects_rehashed_selected_excluded_overlap(tmp_path):
    store=Wo08ShadowStore(tmp_path);h=handoff();store.retain_handoff(h)
    d=h.manifest.data;d.pop('integrity_sha256')
    d['excluded_result_reasons'][h.samples[0].data['probables_member_id']]='MAPPING_UNAVAILABLE'
    bad=record('RUN',**d);store._path('RUN',bad.identity).write_bytes(bad.payload)
    with pytest.raises(ValueError,match='RUN_INCOMPLETE'):
        Wo08ShadowStore(tmp_path).load('RUN',bad.identity)
