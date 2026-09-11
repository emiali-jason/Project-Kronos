"""Successor-epoch tests use fake clocks, isolated stores and no production evidence."""
from datetime import timedelta
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
import json
import pytest

from kronos.application.intraday_live_shadow import IntradayLiveShadowService
from kronos.application.intraday_shadow_epochs import commission, ACTION
from kronos.intraday.live_shadow_epochs import document, MATERIAL, EpochStore, EpochView
from kronos.intraday.live_shadow import artifact, key, ShadowError, COHORT_A, COHORT_B, instant
from kronos.intraday.live_shadow_persistence import ShadowStore
from kronos.intraday.runtime_identity import create_runtime_manifest, LauncherConfiguration
from tests.unit.intraday.test_runtime_identity import _seed
from tests.unit.intraday.test_live_shadow import service, seed_row, NOW

REV = '7159439ea68c07819a5f23d8eb9c4538c02eb54c'


def inventory(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def restart(root, old, *, changed=True, revision=REV, at=NOW+timedelta(hours=1)):
    s = IntradayLiveShadowService(store=ShadowStore(root), clock=lambda:at)
    caps = tuple(replace(c, implementation_digest='b'*64) if changed and c.identity=='INTRADAY_DISCOVERY_OPERATION' else c for c in old._manifest.capabilities)
    m=create_runtime_manifest(_seed(source_revision=revision,startup_boundary_at=at,process_nonce='2'*32),LauncherConfiguration(8947,False),caps)
    s.bind_runtime(m)
    return s


def authorize(s, *, request='SUCCESSOR', fault=None):
    pred=s._epochs.chain()[0]
    d=dict(classification=MATERIAL,subject_revision=REV,predecessor_proof=pred['body']['proof'],
        calculation_digest=next(c['implementation_digest'] for c in pred['body']['proof']['capabilities'] if c['identity']=='WO_06H_LIVE_SHADOW'),
        changed_semantics='Native publication before Probables commit',report_sha256='c'*64,sponsor_reference='ISOLATED-SPONSOR-EA-DIAGNOSIS')
    if fault=='non_material':d['classification']='COMPATIBLE_EVOLUTION'
    if fault=='wrong_predecessor_proof':d['predecessor_proof']=s._runtime_proof()
    if fault=='calculation':d['calculation_digest']='f'*64
    diagnosis=document('diagnosis',d);s._epochs.retain(diagnosis)
    a=dict(request=request,predecessor=pred['identity'],proof=s._runtime_proof(),diagnosis=diagnosis['identity'],
        expires_at=(s.clock()+timedelta(hours=1)).isoformat(),sponsor_reference='ISOLATED-SPONSOR-EA-AUTHORIZATION')
    if fault=='wrong_revision':a['proof']=dict(a['proof'],revision='c'*40)
    if fault=='no_explicit_authority':a['sponsor_reference']=''
    if fault=='missing_diagnosis':a['diagnosis']='WO06H-DIAGNOSIS-'+'0'*64
    if fault=='expired':a['expires_at']=(NOW-timedelta(seconds=1)).isoformat()
    if fault=='predecessor':a['predecessor']='WO06H-EPOCH-'+'f'*64
    auth=document('authorization',a);s._epochs.retain(auth)
    return dict(action=ACTION,request_identity=request,authorization_identity=auth['identity'])


def perform(s, payload, **kwargs):
    return commission(s,payload,maintenance=kwargs.get('maintenance',True),idle=kwargs.get('idle',True),repository=kwargs.get('repository',lambda *args:True))


def current_fixture(tmp_path):
    old,_,_=service(tmp_path);row,_=seed_row(old,price=None)
    raw=old._epochs.raw
    body={k:v for k,v in row.body.items() if k not in {'epoch','acceptance'}}
    (raw.root/'observation'/(row.key+'.json')).write_bytes(artifact('observation',row.key,body).payload)
    batch=raw.all('batch')[0].body
    for cohort,count in [(COHORT_A,33),(COHORT_B,66)]:
        for n in range(count):
            oid=key('observation',old._window.key,cohort,str(n));bid=key('batch',old._window.key,cohort,str(n))
            pair=dict(body['assessment'],authority='WO06C_ADMISSION_PRICE' if cohort==COHORT_A else 'WO06H_COHORT_B_RESEARCH_QUOTE')
            raw.retain(artifact('observation',oid,dict(body,result=str(n),cohort=cohort,narrow=cohort==COHORT_A,assessment=pair)))
            raw.retain(artifact('batch',bid,dict(batch,expected={COHORT_A:[oid] if cohort==COHORT_A else [],COHORT_B:[oid] if cohort==COHORT_B else []})))
    old._reconcile()
    return old,restart(tmp_path,old)


def test_initial_epoch_read_is_deterministic_and_inert(tmp_path):
    s,_,_=service(tmp_path);before=inventory(tmp_path)
    first=s.epoch_status();assert len(first['epochs'])==1 and first['current_epoch']
    assert first==s.epoch_status() and inventory(tmp_path)==before
    assert first['epochs'][0]['counts']['cohort_a']==0


def test_successor_exact_binding_isolated_counts_and_idempotency(tmp_path):
    old,_,_=service(tmp_path);seed_row(old,price=None)
    historical=inventory(tmp_path);s=restart(tmp_path,old);assert not s.status()['enabled']
    payload=authorize(s);result=perform(s,payload)
    assert result['outcome']=='ESTABLISHED'
    st=s.status();assert st['enabled'] and len(st['epochs'])==2
    assert st['last_capture'] is None
    assert st['counts']['cohort_a']==st['counts']['cohort_b']==st['counts']['eod_available']==0
    assert st['epochs'][1]['counts']['cohort_a']==1
    assert st['epochs'][0]['predecessor']==st['epochs'][1]['identity']
    assert st['window']['identity']!=old._window.key
    assert instant(st['window']['start'])==s.clock()
    assert st['window']['end']!=old._window.body['end']
    assert all((tmp_path/p).read_bytes()==b for p,b in historical.items())
    before=inventory(tmp_path);assert perform(s,payload)['outcome']=='ALREADY_ESTABLISHED'
    assert inventory(tmp_path)==before
    restored=restart(tmp_path,s,changed=False,at=s.clock()+timedelta(minutes=1))
    assert restored.status()['enabled'] and restored.status()['current_epoch']==st['current_epoch']


@pytest.mark.parametrize('fault',['non_material','wrong_predecessor_proof','calculation','wrong_revision','no_explicit_authority','missing_diagnosis','expired','predecessor'])
def test_authority_fail_closed(tmp_path,fault):
    old,_,_=service(tmp_path);s=restart(tmp_path,old);payload=authorize(s,fault=fault);before=inventory(tmp_path)
    with pytest.raises((ValueError,KeyError)):perform(s,payload)
    assert s._epochs.pointer() is None
    # Only a lock file may be created on rejected commissioning.
    assert all((tmp_path/p).read_bytes()==b for p,b in before.items())
    assert len(s._epochs.raw.all('window'))==1


@pytest.mark.parametrize('condition',[{'maintenance':False},{'idle':False},{'repository':lambda *args:False}])
def test_server_conditions_fail_closed(tmp_path,condition):
    old,_,_=service(tmp_path);s=restart(tmp_path,old);payload=authorize(s)
    with pytest.raises(ValueError):perform(s,payload,**condition)
    assert s._epochs.pointer() is None and len(s._epochs.raw.all('acceptance'))==1


def test_compatible_current_cannot_be_superseded(tmp_path):
    old,_,_=service(tmp_path);s=restart(tmp_path,old,changed=False);payload=authorize(s)
    with pytest.raises(ValueError,match='COMPATIBLE_CURRENT'):perform(s,payload)


@pytest.mark.parametrize('kind',['window','acceptance','epoch','pointer'])
def test_corrupt_current_never_falls_back(tmp_path,kind):
    old,_,_=service(tmp_path);s=restart(tmp_path,old);perform(s,authorize(s));current=s._epochs.chain()[0]
    if kind=='pointer':path=s._epochs.root/'CURRENT.json'
    elif kind=='epoch':path=s._epochs.root/(current['identity']+'.json')
    else:path=s._epochs.raw.root/kind/(current['body'][kind]+'.json')
    path.write_bytes(b'corrupt');before=inventory(tmp_path)
    new=restart(tmp_path,s,changed=False,at=s.clock()+timedelta(minutes=1))
    assert not new.status()['enabled'] and new.status()['failure'] is not None
    assert inventory(tmp_path)==before


@pytest.mark.parametrize('stage',['window','acceptance','epoch','pointer'])
def test_partial_publication_never_points_to_incomplete_epoch(tmp_path,monkeypatch,stage):
    old,_,_=service(tmp_path);s=restart(tmp_path,old);payload=authorize(s)
    if stage=='pointer':monkeypatch.setattr(s._epochs,'advance',Mock(side_effect=OSError('isolated')))
    elif stage=='epoch':
        original=s._epochs.retain
        def retain(value):
            if value['kind']=='epoch' and value['body']['predecessor']:raise OSError('isolated')
            return original(value)
        monkeypatch.setattr(s._epochs,'retain',retain)
    else:
        original=s._epochs.raw.retain
        def retain(value,**kw):
            if value.kind==stage:raise OSError('isolated')
            return original(value,**kw)
        monkeypatch.setattr(s._epochs.raw,'retain',retain)
    with pytest.raises(OSError):perform(s,payload)
    assert s._epochs.pointer() is None
    assert s._epochs.chain()[0]['body']['window']==old._window.key


def test_foreign_observation_binding_rejected(tmp_path):
    old,_,_=service(tmp_path);row,_=seed_row(old,price=None)
    with pytest.raises(ValueError):old.store.retain(artifact('observation',row.key,dict(row.body,epoch='WO06H-EPOCH-'+'f'*64)))


def test_successor_request_cannot_self_assert_authority(tmp_path):
    old,_,_=service(tmp_path);s=restart(tmp_path,old)
    payload=dict(action=ACTION,request_identity='X',authorization_identity='WO06H-AUTHORIZATION-'+'f'*64,authorized=True)
    with pytest.raises(ValueError):perform(s,payload)
    assert len(s._epochs.raw.all('window'))==1


def test_current_34_66_case_and_prospective_observation_isolation(tmp_path):
    old,s=current_fixture(tmp_path)
    assert (old._summary['cohort_a'],old._summary['cohort_b'],old._summary['eod_available'])==(34,66,0)
    before=inventory(tmp_path);perform(s,authorize(s))
    assert all((tmp_path/p).read_bytes()==b for p,b in before.items())
    assert (s._summary['cohort_a'],s._summary['cohort_b'],s._summary['eod_available'])==(0,0,0)
    original=old._epochs.raw.all('observation')[0]
    oid=key('observation',s._window.key,'NEW');bid=key('batch',s._window.key,'NEW')
    body={k:v for k,v in original.body.items() if k not in {'epoch','acceptance'}}
    body.update(window=s._window.key,run='NEW',captured_at=s.clock().isoformat(),boundary=s.clock().isoformat())
    cohort=body['cohort']
    s.store.retain(artifact('batch',bid,dict(authority='RESEARCH_ONLY',window=s._window.key,run='NEW',run_integrity='I',operation='NEW',boundary=s.clock().isoformat(),recorded_at=s.clock().isoformat(),expected={COHORT_A:[oid] if cohort==COHORT_A else [],COHORT_B:[oid] if cohort==COHORT_B else []},classification_failures=[])))
    s.store.retain(artifact('observation',oid,body));s._reconcile()
    row=s.store.load('observation',oid)
    assert row.body['epoch']==s.status()['current_epoch'] and row.body['acceptance']==s.status()['acceptance_identity']
    st=s.status();assert st['counts']['cohort_a']+st['counts']['cohort_b']==1
    assert st['epochs'][1]['counts']['cohort_a']==34 and st['epochs'][1]['counts']['cohort_b']==66
    assert st['all_epoch_counts']['cohort_a']+st['all_epoch_counts']['cohort_b']==101


def test_current_incompatible_does_not_restore_older_compatible_epoch(tmp_path):
    old,_,_=service(tmp_path);s=restart(tmp_path,old);perform(s,authorize(s))
    current=restart(tmp_path,old,changed=False,at=NOW+timedelta(hours=2))
    assert not current.status()['enabled']
    assert current.status()['failure']=='SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE'
    assert len(current.status()['epochs'])==2
    assert current.status()['epochs'][1]['compatibility']=='COMPATIBLE'


def test_second_successor_has_two_historical_epochs_and_one_current(tmp_path):
    old,_,_=service(tmp_path);s=restart(tmp_path,old);perform(s,authorize(s))
    third=restart(tmp_path,s,changed=False,at=NOW+timedelta(hours=2))
    caps=tuple(replace(c,implementation_digest='d'*64) if c.identity=='INTRADAY_DISCOVERY_OPERATION' else c for c in third._manifest.capabilities)
    third._manifest=create_runtime_manifest(third._manifest.startup,LauncherConfiguration(8947,False),caps)
    third._accepted=None
    perform(third,authorize(third,request='SUCCESSOR_3'))
    rows=third.status()['epochs'];assert len(rows)==3 and sum(r['current'] for r in rows)==1
    assert rows[0]['predecessor']==rows[1]['identity'] and rows[1]['predecessor']==rows[2]['identity']


@pytest.mark.parametrize('fault',['dirty','foreign_pid','missing_authorization','window_conflict','epoch_conflict','pointer_conflict'])
def test_remaining_fail_closed_cases(tmp_path,monkeypatch,fault):
    old,_,_=service(tmp_path);s=restart(tmp_path,old);payload=authorize(s)
    if fault=='dirty':object.__setattr__(s._manifest.startup,'source_state','DIRTY_WORKTREE')
    elif fault=='foreign_pid':object.__setattr__(s._manifest.startup,'process_id',999999)
    elif fault=='missing_authorization':payload['authorization_identity']='WO06H-AUTHORIZATION-'+'f'*64
    elif fault=='window_conflict':
        auth=s._epochs.load(payload['authorization_identity']);wid=key('window','SUCCESSOR',s._epochs.chain()[0]['identity'],auth['identity'],auth['body']['request'])
        s._epochs.raw.retain(artifact('window',wid,old._window.body))
    elif fault=='epoch_conflict':monkeypatch.setattr(s._epochs,'retain',Mock(side_effect=ShadowError('SHADOW_EPOCH_IMMUTABLE_CONFLICT')))
    else:monkeypatch.setattr(s._epochs,'advance',Mock(side_effect=ShadowError('SHADOW_EPOCH_POINTER_CONFLICT')))
    with pytest.raises((ValueError,AttributeError)):perform(s,payload)
    assert s._epochs.pointer() is None


@pytest.mark.parametrize('fault',['HEAD','branch','tracking','remote','dirty','ancestry'])
def test_repository_gate_checks_every_external_boundary(monkeypatch,fault):
    from kronos.application.intraday_shadow_epochs import repository_gate
    def output(command,**kwargs):
        args=tuple(command[1:])
        mapping={('branch','--show-current'):'develop',('rev-parse','HEAD'):REV,('rev-parse','origin/develop'):REV,
            ('status','--porcelain=v1','--untracked-files=all'):'',('ls-remote','--exit-code','origin','refs/heads/develop'):REV+' refs/heads/develop',('merge-base',REV,REV):REV}
        target={'HEAD':('rev-parse','HEAD'),'branch':('branch','--show-current'),'tracking':('rev-parse','origin/develop'),
            'remote':('ls-remote','--exit-code','origin','refs/heads/develop'),'dirty':('status','--porcelain=v1','--untracked-files=all'),'ancestry':('merge-base',REV,REV)}[fault]
        return ('WRONG' if args==target else mapping[args]).encode()
    monkeypatch.setattr('kronos.application.intraday_shadow_epochs.subprocess.check_output',output)
    with pytest.raises(ValueError,match='REPOSITORY_DRIFT'):repository_gate(REV,REV)


def test_two_commissioners_serialize_and_create_only_one_successor(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    old,_,_=service(tmp_path);s=restart(tmp_path,old);payload=authorize(s)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:perform(s,payload),range(2)))
    assert sorted(r['outcome'] for r in results)==['ALREADY_ESTABLISHED','ESTABLISHED']
    assert len(s._epochs.raw.all('window'))==len(s._epochs.raw.all('acceptance'))==2


def test_rehashed_transition_cannot_detach_retained_authority(tmp_path):
    from kronos.intraday.population_measurement import canonical
    old,_,_=service(tmp_path);s=restart(tmp_path,old);perform(s,authorize(s))
    current=s._epochs.pointer();invalid=document('transition',dict(current['body'],request='UNAUTHORIZED'))
    s._epochs.retain(invalid);(s._epochs.root/'CURRENT.json').write_bytes(canonical(invalid))
    new=restart(tmp_path,s,changed=False)
    assert not new.status()['enabled'] and new.status()['epoch_failure']


def test_immutable_write_failure_publishes_no_partial_document(tmp_path,monkeypatch):
    old,_,_=service(tmp_path);s=restart(tmp_path,old)
    item=document('diagnosis',dict(classification=MATERIAL,subject_revision=REV,predecessor_proof={},
        calculation_digest='a'*64,changed_semantics='ISOLATED',report_sha256='b'*64,sponsor_reference='ISOLATED'))
    monkeypatch.setattr('kronos.intraday.live_shadow_epochs.os.fsync',Mock(side_effect=OSError('ISOLATED')))
    with pytest.raises(OSError):s._epochs.retain(item)
    assert not (s._epochs.root/(item['identity']+'.json')).exists()


def test_ordinary_accept_cannot_create_new_authority_in_managed_epoch(tmp_path):
    old,_,_=service(tmp_path);s=restart(tmp_path,old);perform(s,authorize(s))
    new=restart(tmp_path,s,changed=False,at=s.clock()+timedelta(minutes=1));before=inventory(tmp_path)
    with pytest.raises(ValueError,match='EXPLICIT_SUCCESSOR_REQUIRED'):
        new.accept_runtime(expected_revision=REV,request_identity='ORDINARY_REACCEPT')
    assert inventory(tmp_path)==before


@pytest.mark.parametrize('fault',['absent','epoch','acceptance'])
def test_explicit_epoch_binding_is_required_for_successor_rows(tmp_path,fault):
    old,_,_=service(tmp_path);row,_=seed_row(old,price=None)
    s=restart(tmp_path,old);perform(s,authorize(s))
    body={k:v for k,v in row.body.items() if k not in {'epoch','acceptance'}}
    body.update(window=s._window.key,captured_at=s.clock().isoformat())
    if fault != 'absent':
        current=s._epochs.chain()[0];body.update(epoch=current['identity'],acceptance=current['body']['acceptance'])
        body[fault]='WO06H-'+fault.upper()+'-'+'f'*64
    oid=key('observation','UNBOUND');s._epochs.raw.retain(artifact('observation',oid,body))
    with pytest.raises(ValueError,match='OBSERVATION_BINDING'):s.store.load('observation',oid)
    assert s.status()['epoch_failure']=='SHADOW_EPOCH_READ_FAILED'


def test_exact_repeat_after_window_end_does_not_reactivate_or_duplicate(tmp_path):
    old,_,_=service(tmp_path);s=restart(tmp_path,old);payload=authorize(s)
    first=perform(s,payload);before=inventory(tmp_path)
    s.clock=lambda:instant(first['status']['window']['end'])
    result=perform(s,payload)
    assert result['outcome']=='ALREADY_ESTABLISHED' and result['epoch']==first['epoch']
    assert not result['status']['enabled'] and inventory(tmp_path)==before
