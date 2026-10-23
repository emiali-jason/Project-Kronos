"""Isolated qualification of R3 encoding, private storage and atomic ownership.

Synthetic protocol examples here are test inputs, not approvals or live proofs.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
import time

import pytest

from kronos.common.failed_fenced_recovery import (
    RecoveryBudget, RecoveryCodec, RecoveryError, RecoveryStore,
    OriginalExecutorWitness, PreparationContext,
    canonical_bytes, decode_canonical, record_ref, slot_key, source_identity,
    _verify_notice_set,
)
from kronos.common.maintenance_admission import AdmissionTicket, MaintenanceAdmissionCoordinator

GEN='a'*64
PROCESS={'pid':str(os.getpid()),'kernel_birth':{'seconds':'1','microseconds':'2'},'runtime':'unit-runtime'}
LINEAGE={'predecessor':PROCESS,'generation':GEN}
CLOCK={'type':'CLOCK_MONOTONIC','boot_id':'unit-boot','qualification':{'authority':'PCP','contract':'KRONOS-FAILED-FENCED-ROOT-PROOF:1.0.0:CLOCK_QUALIFICATION','identity':'unit-clock','hash':'c'*64,'bytes':'1'}}
CONTROL=f'KRONOS_BROWSER_BACKEND_CONTROL_V1\n{os.getpid()}\n'+('b'*64)+'\n'

def evidence(identity='unit-proof'):
    return {'authority':'PREDECESSOR','contract':'unit-contract','identity':identity,'hash':'d'*64,'bytes':'1'}

def codec():return RecoveryCodec(CONTROL.encode(),CLOCK)

def custody_payload():
    c=codec()
    return {'lineage':LINEAGE,'checkpoint_hash':c.key_id,'checkpoint_bytes':str(len(CONTROL.encode())),
            'controller':PROCESS,'controller_capability':evidence(),'live_control':evidence(),
            'process_binding':evidence(),'verified_ns':'1','execution_owner':'original-publisher'}

def private_store(tmp_path):
    estate=tmp_path/'estate';estate.mkdir(mode=0o700)
    store=RecoveryStore(estate)
    scope={'schema':'KRONOS_FAILED_FENCED_GUARD_SCOPE_V1','version':'1.0.0','service':'unit-service','installation':'unit-install','policy':'MANDATORY'}
    store.provision(scope,sha256(canonical_bytes(scope)).hexdigest())
    return store

def failed_coordinator(ticket_kind=None):
    c=MaintenanceAdmissionCoordinator()
    ticket=c.admit_root(ticket_kind) if ticket_kind else None
    assert c.claim(GEN)
    c.begin_original_execution(GEN,'original-executor')
    c.draining(GEN);c.fail(GEN,'DRAIN_TIMEOUT')
    c.complete_original_execution('original-executor');c.finish_original_publication('original-executor')
    return c,ticket

@pytest.mark.parametrize('raw',[b'{"a":"b", "c":"d"}',b'{"a":"b","a":"b"}',b'{"a":1}',b'{"a":1.0}',b'{"a":"\\u0061"}',b'{"a":"x"}\n',b'\xef\xbb\xbf{}',b'{"a":NaN}'])
def test_noncanonical_and_ambiguous_json_denied(raw):
    with pytest.raises(RecoveryError):decode_canonical(raw)

def test_exact_record_roundtrip_domain_and_unknown_field_denial():
    c=codec();raw=c.encode('CUSTODY',custody_payload(),'LAUNCHER',2)
    assert c.decode(raw,'CUSTODY')['payload']==custody_payload()
    value=json.loads(raw);value['payload']['extension']='not-permitted'
    with pytest.raises(RecoveryError):c.decode(canonical_bytes(value))
    value=json.loads(raw);value['role']='PREDECESSOR'
    with pytest.raises(RecoveryError):c.decode(canonical_bytes(value))
    with pytest.raises(RecoveryError):c.encode('CUSTODY',custody_payload(),'PREDECESSOR',2)
    changed=RecoveryCodec(CONTROL.replace('b','e').encode(),CLOCK)
    with pytest.raises(RecoveryError):changed.decode(raw)

def test_source_identity_preserves_utf8_slashes_spaces_and_case():
    text='NSE/Équity Mixed Case'
    identity=source_identity(text)
    assert bytes.fromhex(identity['bytes'])==text.encode('utf-8')
    assert source_identity(text.lower())!=identity

def test_stable_slot_uses_process_instance_and_generation():
    first=slot_key(LINEAGE)
    assert first==slot_key(json.loads(json.dumps(LINEAGE)))
    changed={**LINEAGE,'predecessor':{**PROCESS,'kernel_birth':{'seconds':'1','microseconds':'3'}}}
    assert slot_key(changed)!=first
    assert slot_key({**LINEAGE,'generation':'b'*64})!=first

def test_custody_and_records_are_private_exclusive_durable_bytes(tmp_path):
    store=private_store(tmp_path);key=store.write_custody(CONTROL.encode())
    assert store.read_custody(key)==CONTROL.encode()
    assert (store.root/'custody'/f'{key}.control').stat().st_mode & 0o777==0o600
    with pytest.raises(RecoveryError):store.write_custody(CONTROL.encode())
    raw=codec().encode('CUSTODY',custody_payload(),'LAUNCHER',2)
    ref=store.publish(raw)
    assert store.resolve(ref)==raw and ref==record_ref(raw)
    with pytest.raises(RecoveryError):store.publish(raw)

def test_private_reader_rejects_symlink_hardlink_mode_and_directory_swap(tmp_path):
    store=private_store(tmp_path);ref=store.write_blob('native',b'exact bytes')
    path=store.root/'blobs'/f"{ref['hash']}.blob"
    os.chmod(path,0o644)
    with pytest.raises(RecoveryError):store.read_blob(ref)
    os.chmod(path,0o600);os.link(path,path.with_suffix('.hardlink'))
    with pytest.raises(RecoveryError):store.read_blob(ref)
    other=tmp_path/'symlink-estate';other.symlink_to(store.estate,target_is_directory=True)
    with pytest.raises(OSError):RecoveryStore(other).read_blob(ref)

def test_interrupted_write_stays_ambiguous_and_is_not_retried(tmp_path,monkeypatch):
    store=private_store(tmp_path);real=os.fsync
    def fail(_fd):raise OSError('injected publication interruption')
    monkeypatch.setattr(os,'fsync',fail)
    with pytest.raises(RecoveryError):store.write_blob('partial',b'actual partial outcome')
    monkeypatch.setattr(os,'fsync',real)
    with pytest.raises(RecoveryError):store.write_blob('partial',b'actual partial outcome')
    assert list((store.root/'blobs').iterdir())

def test_clock_budget_is_shared_and_expiry_sticky(monkeypatch):
    ticks=[100,105,115_000_000_100,106]
    monkeypatch.setattr(time,'clock_gettime_ns',lambda clock:ticks.pop(0))
    b=RecoveryBudget(CLOCK,100,15_000_000_100)
    assert b.check()==100
    assert b.claim(100)==10_000_000_100
    with pytest.raises(RecoveryError):b.check()
    with pytest.raises(RecoveryError):b.check()

def test_counterfeit_ticket_cannot_release_real_owner_or_fork():
    c=MaintenanceAdmissionCoordinator();actual=c.admit_root('WO11')
    forged=AdmissionTicket(c,'WO11','OPEN',False,actual.identity)
    with pytest.raises(ValueError):forged.release()
    assert c.snapshot()['owners']=={'WO11':1}
    with pytest.raises(ValueError):forged.fork('NOTIFICATION')
    actual.release()

def test_first_original_failure_is_immutable_across_later_errors():
    c,t=failed_coordinator('WO11');first=c.failure_snapshot()
    c.fail(GEN,'CLEANUP_UNRESOLVED')
    assert c.failure_snapshot()==first
    t.release()
    with pytest.raises(ValueError):t.release()
    assert c.failure_snapshot()==first

def test_distinct_positive_recovery_preserves_terminal_and_counts_publisher():
    c,t=failed_coordinator('WO11');original=c.failure_snapshot()
    c.claim_recovery('unit-recovery',{t.identity})
    assert c.recovery_snapshot()['owners']==1
    assert c.snapshot()['state']=='FAILED_FENCED'
    t.release()
    deadline=time.clock_gettime_ns(time.CLOCK_MONOTONIC)+1_000_000_000
    assert c.wait_recovery_zero('unit-recovery',deadline)
    c.seal_recovery('unit-recovery',deadline)
    assert c.recovery_snapshot()=={'transaction':'unit-recovery','state':'SEALED','owners':1,'failure':None}
    c.release_recovery('unit-recovery',deadline)
    assert c.recovery_snapshot()['owners']==0
    assert c.failure_snapshot()==original
    assert c.admit_root('WO11') is None
    with pytest.raises(ValueError):c.claim_recovery('another',set())

def test_registered_completion_child_is_counted_without_preclaim_zero():
    c=MaintenanceAdmissionCoordinator();parent=c.admit_root('WO11')
    c.register_completion(parent,'required-reference','NOTIFICATION')
    c.claim(GEN);c.begin_original_execution(GEN,'original');c.draining(GEN);c.fail(GEN,'DRAIN_TIMEOUT')
    c.complete_original_execution('original');c.finish_original_publication('original')
    c.claim_recovery('recovery',{parent.identity})
    child=c.fork_completion(parent,'required-reference')
    assert c.snapshot()['owners']=={'WO11':1,'NOTIFICATION':1}
    parent.release()
    deadline=time.clock_gettime_ns(time.CLOCK_MONOTONIC)+1_000_000_000
    finished=Event()
    worker=Thread(target=lambda:(c.wait_recovery_zero('recovery',deadline),finished.set()))
    worker.start();assert not finished.wait(.01)
    child.release();worker.join(1);assert finished.is_set()
    c.seal_recovery('recovery',deadline);c.release_recovery('recovery',deadline)
    assert c.snapshot()['state']=='FAILED_FENCED'

def test_late_fork_unknown_parent_and_timeout_never_create_zero():
    c,parent=failed_coordinator('WO11');c.claim_recovery('recovery',{parent.identity})
    with pytest.raises(ValueError):parent.fork('NOTIFICATION')
    assert c.recovery_snapshot()['state']=='SPENT_FAILED'
    assert c.snapshot()['owners']=={'WO11':1}
    parent.release()
    c2,t=failed_coordinator('WO11');c2.claim_recovery('recovery',{t.identity})
    assert not c2.wait_recovery_zero('recovery',time.clock_gettime_ns(time.CLOCK_MONOTONIC))
    assert c2.snapshot()['owners']=={'WO11':1} and c2.recovery_snapshot()['owners']==1
    t.release()
    with pytest.raises(ValueError):c2.seal_recovery('recovery',time.clock_gettime_ns(time.CLOCK_MONOTONIC)+1000)

def test_original_executor_publisher_must_really_release_before_recovery():
    c=MaintenanceAdmissionCoordinator();c.claim(GEN);c.begin_original_execution(GEN,'original');c.fail(GEN,'DRAIN_TIMEOUT')
    with pytest.raises(ValueError):c.claim_recovery('recovery',set())
    c.complete_original_execution('original')
    with pytest.raises(ValueError):c.claim_recovery('recovery',set())
    c.finish_original_publication('original');c.claim_recovery('recovery',set())
    assert c.recovery_snapshot()['state']=='ACCEPTED'

def test_sealed_store_forbids_new_external_and_transport_publications(tmp_path):
    store=private_store(tmp_path);store._sealed=True
    with pytest.raises(RecoveryError):store.write_blob('late-proof',b'late')
    with pytest.raises(RecoveryError):store.write_custody(CONTROL.encode())
    raw=codec().encode('CUSTODY',custody_payload(),'LAUNCHER',2)
    with pytest.raises(RecoveryError):store.publish(raw)

def test_preparation_cannot_be_constructed_from_unverified_caller_dicts():
    with pytest.raises(RecoveryError,match='independent pinned loader'):
        PreparationContext({}, {}, {}, {}, None, None)

def original_witness():
    c=MaintenanceAdmissionCoordinator();c.claim(GEN)
    c.begin_original_execution(GEN,'original');c.fail(GEN,'DRAIN_TIMEOUT')
    return c,OriginalExecutorWitness(c,'original',PROCESS,'original-attempt')

def real_budget():
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    return RecoveryBudget(CLOCK,now,now+15_000_000_000)

def test_original_witness_requires_actual_join_and_separate_publisher_release():
    c,w=original_witness();returned=Event();exit_allowed=Event()
    def execute():
        with w.operation('drain'):pass
        w.return_observed();returned.set();exit_allowed.wait(1)
    t=Thread(target=execute);w.bind_thread(t);t.start();assert returned.wait(1)
    try:
        with pytest.raises(RecoveryError):w.termination_payload('termination',PROCESS,LINEAGE)
        assert c.original_execution_snapshot()['operational_owners']==1
        with pytest.raises(ValueError):c.claim_recovery('recovery',set())
    finally:exit_allowed.set()
    w.join_and_close(real_budget())
    payload=w.termination_payload('termination',PROCESS,LINEAGE);w.validate(payload)
    assert payload['accepted_operations']==payload['completed_operations']==['drain']
    assert c.original_execution_snapshot()['publisher_owners']==1
    with pytest.raises(ValueError):c.claim_recovery('recovery',set())
    c.finish_original_publication('original');w.validate(payload)
    c.claim_recovery('recovery',set())
    changed=dict(payload,accepted_operations=[],completed_operations=[])
    with pytest.raises(RecoveryError):w.validate(changed)
    with pytest.raises(RecoveryError):w.join_and_close(real_budget())

def test_actual_helpers_are_joined_and_timeout_never_zeroes_or_retries():
    c,w=original_witness();helper_started=Event();release=Event();threads=[]
    def helper():helper_started.set();release.wait(1)
    def execute():
        with w.operation('drain'):
            h=Thread(target=helper);threads.append(h)
            w.register_helper('native-helper',h);h.start()
        w.return_observed()
    t=Thread(target=execute);w.bind_thread(t);t.start();assert helper_started.wait(1)
    budget=real_budget();deadline=budget.now_ns()+20_000_000
    try:
        with pytest.raises(RecoveryError):w.join_and_close(budget,deadline)
        assert c.original_execution_snapshot()['operational_owners']==1
        assert c.original_execution_snapshot()['publisher_owners']==0
        with pytest.raises(RecoveryError):w.termination_payload('termination',PROCESS,LINEAGE)
        with pytest.raises(RecoveryError):w.join_and_close(real_budget())
    finally:
        release.set();t.join(1)
        for h in threads:h.join(1)

def test_failed_executor_return_does_not_release_product_tickets_or_unspend_slot():
    c,t=failed_coordinator('WO11');original=c.failure_snapshot()
    c.claim_recovery('recovery',{t.identity});c.fail_recovery('CLEANUP')
    c.finish_failed_recovery_execution('recovery')
    assert c.recovery_snapshot()=={'transaction':'recovery','state':'SPENT_FAILED','owners':0,'failure':'CLEANUP'}
    assert c.snapshot()['owners']=={'WO11':1} and c.failure_snapshot()==original
    with pytest.raises(ValueError):c.release_recovery('recovery',real_budget().stop_deadline_ns)
    with pytest.raises(ValueError):c.claim_recovery('retry',{t.identity})
    t.release()

def test_guard_namespace_rejects_unknown_members_and_parent_permissions(tmp_path):
    store=private_store(tmp_path)
    assert store.enumerate_guards()==()
    rogue=store.root/'extra';rogue.write_bytes(b'unknown')
    with pytest.raises(RecoveryError):store.enumerate_guards()
    rogue.unlink();os.chmod(store.estate,0o755)
    with pytest.raises(RecoveryError):store.enumerate_guards()

def test_bootstrap_exact_member_set_and_fixed_identity_are_immutable(tmp_path):
    store=private_store(tmp_path);slot='a'*64
    store.reserve(slot,'claim',b'unit-reserved-claim')
    native=b'unit-native-startup';proof=b'unit-bootstrap-proof';identity=b'unit-child-identity'
    store.publish_bootstrap(slot,native,proof,identity,budget=real_budget())
    assert store.read_bootstrap(slot)=={'native':native,'proof':proof,'identity':identity}
    with pytest.raises(FileExistsError):store.publish_bootstrap(slot,native,proof,identity,budget=real_budget())
    extra=store.root/'slots'/slot/'bootstrap'/'unexpected';extra.write_bytes(b'unknown')
    with pytest.raises(RecoveryError):store.read_bootstrap(slot)

def notice_case(tmp_path):
    # Exercise the fixed native whole-set predicate, not a recovery-authority
    # registry. These synthetic records confer no approval or loaded identity.
    store=private_store(tmp_path);c=codec();identity='native/TRACK Mixed Case'
    raw=json.dumps({'kind':'TRACK','identity':identity,'received_at':'2026-10-22T00:00:00+00:00'},sort_keys=True).encode()
    key=sha256(('TRACK:'+identity).encode()).hexdigest();native=store.write_blob(key+'.pending',raw)
    obligation={'predecessor':PROCESS,'obligation':'reference','previous':None,'state':'COMPLETE',
        'owner':'WO13','owner_instance':'notifications','operation':'reference','relation':'WO11_TRACK_REFERENCE',
        'effect':{'kind':'WO11_TRACK_REFERENCE','identity':source_identity(identity),'source':evidence(),
            'input':evidence(),'target':source_identity(identity),'expected':sha256(raw).hexdigest(),'transition':None},
        'listener':evidence(),'ticket':'ticket:1','admission':evidence(),'owner_scope':evidence(),
        'parent':None,'required_children':[],'notices':[{'identity':source_identity(identity),'state':'PENDING',
            'evidence':{'authority':'WO13','contract':'KRONOS-INTRADAY-WO13-SOURCE-REFERENCE-V1',**native}}],
        'owner_result':evidence(),'failure':None}
    head=store.publish(c.encode('OBLIGATION',obligation,'PREDECESSOR',2))
    digest=sha256((native['identity']+':'+native['hash']).encode()).hexdigest()
    checkpoint={'state':'VALID_PENDING','pending_count':1,'sha256':digest}
    cp=store.write_blob('native-checkpoint',json.dumps(checkpoint,sort_keys=True,separators=(',',':')).encode())
    payload={'obligations':['reference'],'targets':[native],'after':[cp]}
    return store,SimpleNamespace(store=store,codec=c),payload,{'accepted_heads':[head]},checkpoint

def test_native_notice_bijection_preserves_exact_pending_reference(tmp_path):
    _store,reader,payload,context,checkpoint=notice_case(tmp_path)
    assert _verify_notice_set(payload,reader,context)==checkpoint
    assert payload['targets'][0]['identity'].endswith('.pending')

def test_native_notice_rejects_missing_duplicate_or_unregistered_history(tmp_path):
    store,reader,payload,context,_checkpoint=notice_case(tmp_path)
    with pytest.raises(RecoveryError):_verify_notice_set(dict(payload,targets=[]),reader,context)
    with pytest.raises(RecoveryError):_verify_notice_set(dict(payload,targets=payload['targets']*2),reader,context)
    with pytest.raises(RecoveryError):_verify_notice_set(payload,reader,{'accepted_heads':[]})
    empty=store.write_blob('empty-checkpoint',json.dumps({'state':'EMPTY','pending_count':0,'sha256':sha256(b'').hexdigest()},sort_keys=True,separators=(',',':')).encode())
    with pytest.raises(RecoveryError):_verify_notice_set(dict(payload,after=[empty]),reader,context)
    assert _verify_notice_set({'obligations':[],'targets':[],'after':[empty]},reader,{'accepted_heads':[]})['state']=='EMPTY'


def composition_case():
    """Synthetic finite roster; this tests history validation, not authority."""
    from copy import deepcopy
    from kronos.common.failed_fenced_recovery import EvidenceRegistry, SCOPE_HASH
    from kronos.common.failed_fenced_schema import OWNERS
    slots=[{'owner':owner,'slot':'slot-'+owner,'presence':'NOT_INSTALLED','instances':[]}
           for owner in sorted(OWNERS)]
    slot=next(x for x in slots if x['owner']=='UX10')
    slot.update(presence='INSTALLED',instances=['ux-owner'])
    old={'scope':{'hash':SCOPE_HASH},'source':evidence(),'process':PROCESS,
         'registered_ns':'1','observed_ns':'1','slots':slots,'phase':'LIVE','previous':None,
         'instances':[{'identity':'ux-owner','owner':'UX10','slot':'slot-UX10','implementation':{},'constructed_ns':'1'}],
         'resources':[{'identity':'ux-owner-resource','owner_instance':'ux-owner','kind':'OWNER','parent':None,'aliases':[],'registered_ns':'1'}],
         'listeners':[], 'cleanup':[{'step':'ux-close','owner':'UX10','owner_instance':'ux-owner',
             'action':'CLOSE_UX10','resource':'ux-owner-resource','nested':[]}]}
    current=deepcopy(old);current['previous']={'identity':'old','hash':'1'*64,'bytes':'1'}
    reader=object.__new__(EvidenceRegistry)
    reader.verify_blob=lambda ref,kind:{'payload':deepcopy(old)}
    reader._blob=lambda ref:b''
    return reader,old,current


def test_live_inventory_appends_actual_new_timer_and_lazy_owner_before_fence():
    reader,old,current=composition_case()
    current['resources'].append({'identity':'ux-timer','owner_instance':'ux-owner','kind':'TIMER',
        'parent':'ux-owner-resource','aliases':[],'registered_ns':'2'})
    current['cleanup'].append({'step':'ux-timer-cancel','owner':'UX10','owner_instance':'ux-owner',
        'action':'CANCEL_TIMER','resource':'ux-timer','nested':[]})
    current['cleanup'][0]['nested']=['ux-timer-cancel']
    provider=next(x for x in current['slots'] if x['owner']=='PROVIDER_LEASE')
    provider.update(presence='INSTALLED',instances=['provider-lease'])
    current['instances'].append({'identity':'provider-lease','owner':'PROVIDER_LEASE',
        'slot':'slot-PROVIDER_LEASE','implementation':{},'constructed_ns':'2'})
    for field,key in [('resources','identity'),('cleanup','step'),('instances','identity')]:
        current[field].sort(key=lambda x:x[key])
    reader._inventory(current)
    current['phase']='ORIGINAL_FENCE'
    reader._inventory(current)
    assert old['cleanup'][0]['nested']==[]
    assert next(x for x in old['slots'] if x['owner']=='PROVIDER_LEASE')['presence']=='NOT_INSTALLED'


@pytest.mark.parametrize('mutation',['remove_instance','remove_cleanup','change_resource','move_slot',
    'remove_nested','reuse_old_step','fenced_extension','revive_listener','change_retirement',
    'changed_source','changed_process','reversed_time'])
def test_live_inventory_rejects_rewriting_history_or_recovery_time_extension(mutation):
    from copy import deepcopy
    reader,old,current=composition_case()
    if mutation=='remove_instance':
        current['instances']=[]
        next(x for x in current['slots'] if x['owner']=='UX10').update(presence='NOT_INSTALLED',instances=[])
    elif mutation=='remove_cleanup':current['cleanup']=[]
    elif mutation=='change_resource':current['resources'][0]['kind']='QUEUE'
    elif mutation=='move_slot':next(x for x in current['slots'] if x['owner']=='UX10')['slot']='another-slot'
    elif mutation in {'remove_nested','reuse_old_step'}:
        second={'step':'ux-timer-cancel','owner':'UX10','owner_instance':'ux-owner',
            'action':'CANCEL_TIMER','resource':'ux-owner-resource','nested':[]}
        old['cleanup'].append(second);current['cleanup'].append(deepcopy(second))
        if mutation=='remove_nested':old['cleanup'][0]['nested']=['ux-timer-cancel']
        else:current['cleanup'][0]['nested']=['ux-timer-cancel']
    elif mutation=='fenced_extension':old['phase']='ORIGINAL_FENCE'
    elif mutation=='changed_source':current['source']=evidence('another-source')
    elif mutation=='changed_process':current['process']=dict(PROCESS,runtime='another-runtime')
    elif mutation=='reversed_time':current['registered_ns']='0'
    elif mutation in {'revive_listener','change_retirement'}:
        listener={'identity':'native-listener','producer_instance':'ux-owner','consumer_instance':'ux-owner',
            'implementation':{},'registered_ns':'1','retired_ns':'3'}
        old['listeners']=[listener];current['listeners']=[dict(listener,retired_ns=None if mutation=='revive_listener' else '4')]
    with pytest.raises(RecoveryError):reader._inventory(current)


@pytest.mark.parametrize('mutation',['named_inode','metadata'])
def test_immutable_store_read_rejects_named_replacement_and_metadata_change(tmp_path,monkeypatch,mutation):
    store=private_store(tmp_path);raw=b'exact immutable evidence'
    ref=store.write_blob('evidence',raw);path=store.root/'blobs'/(ref['hash']+'.blob')
    read=os.read;inode=path.stat().st_ino;changed=False
    def altering(fd,size):
        nonlocal changed
        part=read(fd,size)
        if not changed and os.fstat(fd).st_ino==inode:
            changed=True
            if mutation=='named_inode':
                replacement=path.with_suffix('.new');replacement.write_bytes(raw);replacement.chmod(0o600)
                os.replace(replacement,path)
            else:
                info=path.stat();os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1_000_000))
        return part
    monkeypatch.setattr(os,'read',altering)
    with pytest.raises(RecoveryError):store.read_blob(ref)
    assert path.read_bytes()==raw


def test_bootstrap_blobs_resolve_only_the_completed_fixed_three_member_publication(tmp_path):
    store=private_store(tmp_path);slot='a'*64
    store.reserve(slot,'claim',b'claim')
    native=b'exact native startup';proof=b'exact bootstrap identity';identity=b'exact child identity'
    store.publish_bootstrap(slot,native,proof,identity,budget=real_budget())
    for name,raw in [('native',native),('bootstrap-proof',proof)]:
        ref={'identity':name,'hash':sha256(raw).hexdigest(),'bytes':str(len(raw))}
        assert store.read_blob(ref)==raw
        assert not (store.root/'blobs'/(ref['hash']+'.blob')).exists()
    ref={'identity':'identity','hash':sha256(identity).hexdigest(),'bytes':str(len(identity))}
    with pytest.raises(RecoveryError):store.read_blob(ref)
    path=store.root/'slots'/slot/'child-identity'
    # Interrupted set is not allowed to support raw native/proof consumption.
    path.unlink()
    ref={'identity':'native','hash':sha256(native).hexdigest(),'bytes':str(len(native))}
    with pytest.raises(RecoveryError):store.read_blob(ref)


def test_bootstrap_resolution_never_masks_an_existing_corrupt_blob(tmp_path):
    store=private_store(tmp_path);slot='a'*64;native=b'original startup'
    store.reserve(slot,'claim',b'claim');store.publish_bootstrap(slot,native,b'proof',b'identity',budget=real_budget())
    ref={'identity':'native','hash':sha256(native).hexdigest(),'bytes':str(len(native))}
    bad=store.root/'blobs'/(ref['hash']+'.blob');bad.write_bytes(b'corrupt');bad.chmod(0o600)
    with pytest.raises(RecoveryError):store.read_blob(ref)


def test_bootstrap_identity_partial_write_is_not_observable_as_complete(tmp_path,monkeypatch):
    import fcntl
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    store=private_store(tmp_path);slot='d'*64
    store.reserve(slot,'claim',b'unit-claim')
    path=store.root/'slots'/slot/'child-identity'
    entered,resume=Event(),Event();original=os.write
    def held_write(fd,data):
        if path.exists() and os.fstat(fd).st_ino==path.stat().st_ino:
            entered.set()
            assert resume.wait(3),'test publication barrier expired'
        return original(fd,data)
    monkeypatch.setattr(os,'write',held_write)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future=executor.submit(store.publish_bootstrap,slot,b'native',b'proof',b'identity',budget=real_budget())
        reader=store._dir(('slots',slot))
        try:
            assert entered.wait(3)
            assert path.stat().st_size==0
            with pytest.raises(BlockingIOError):
                fcntl.flock(reader,fcntl.LOCK_SH|fcntl.LOCK_NB)
        finally:
            fcntl.flock(reader,fcntl.LOCK_UN);os.close(reader);resume.set()
        future.result(timeout=3)
    assert store.read_bootstrap(slot)['identity']==b'identity'


def test_bootstrap_lock_wait_is_bounded_and_writes_nothing(tmp_path):
    import fcntl,time
    store=private_store(tmp_path);slot='e'*64
    store.reserve(slot,'claim',b'claim');reader=store._dir(('slots',slot))
    fcntl.flock(reader,fcntl.LOCK_SH|fcntl.LOCK_NB)
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    budget=RecoveryBudget(CLOCK,now-14_980_000_000,now+20_000_000)
    try:
        with pytest.raises(RecoveryError,match='TIMEOUT'):
            store.publish_bootstrap(slot,b'native',b'proof',b'identity',budget=budget)
        assert set(os.listdir(reader))=={'claim'}
    finally:fcntl.flock(reader,fcntl.LOCK_UN);os.close(reader)


def test_interrupted_bootstrap_releases_lock_but_never_repairs_partial_set(tmp_path,monkeypatch):
    import fcntl
    store=private_store(tmp_path);slot='f'*64;store.reserve(slot,'claim',b'claim')
    write=store._write
    def fail(parts,name,raw):
        if name.endswith('.bootstrap.json'):raise OSError('synthetic durability failure')
        return write(parts,name,raw)
    monkeypatch.setattr(store,'_write',fail)
    with pytest.raises(OSError,match='synthetic durability'):
        store.publish_bootstrap(slot,b'native',b'proof',b'identity',budget=real_budget())
    reader=store._dir(('slots',slot))
    try:fcntl.flock(reader,fcntl.LOCK_SH|fcntl.LOCK_NB)
    finally:fcntl.flock(reader,fcntl.LOCK_UN);os.close(reader)
    with pytest.raises(RecoveryError):store.read_bootstrap(slot)
    with pytest.raises(FileExistsError):
        store.publish_bootstrap(slot,b'native',b'proof',b'identity',budget=real_budget())
