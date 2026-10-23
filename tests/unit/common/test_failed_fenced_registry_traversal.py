"""Real private-store/codec validation with deterministic traversal interleavings.

Barriers and recursive edges below control test scheduling only; no authority
validator or authentication result is substituted with a successful outcome.
"""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Barrier

import pytest
from kronos.common import failed_fenced_recovery as core
from tests.unit.common.test_failed_fenced_preparation_selection import static_package
from tests.unit.common.test_failed_fenced_recovery import private_store, codec, PROCESS
from tests.unit.common.test_failed_fenced_native_semantics import control_payload, CONTROL


def registry_case(tmp_path, prospective):
    store=private_store(tmp_path)
    if prospective:
        decoder=codec();store.write_custody(CONTROL)
        registry=core._ProspectiveEvidenceWriter(decoder,store,PROCESS)
        raw=decoder.encode_proof('CONTROL_BINDING',control_payload(),PROCESS,'PREDECESSOR',2)
        ref=store.write_blob('native-control-binding',raw)
        kind='CONTROL_BINDING'
    else:
        prep,_,_=static_package(store)
        decoder=core.StaticPreparationCodec.from_preparation(prep)
        registry=core.EvidenceRegistry(decoder,store,prep)
        ref=prep.rows['static-ca-guard']['artifact'];kind='GUARD_APPLICABILITY'
        raw=store.read_blob(ref)
    return registry,ref,kind,raw


@pytest.mark.parametrize('prospective',[False,True])
def test_concurrent_same_proof_readers_are_not_recursive_cycles(tmp_path,monkeypatch,prospective):
    registry,ref,kind,raw=registry_case(tmp_path,prospective)
    evidence=registry.proof_evidence(raw)
    barrier=Barrier(2);validate=registry._validate
    def interleaved(proof,context):
        barrier.wait(timeout=5)
        return validate(proof,context)
    monkeypatch.setattr(registry,'_validate',interleaved)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures=[workers.submit(registry.verify,evidence,kind) for _ in range(2)]
        assert all(f.result(timeout=10)['kind']==kind for f in futures)
    assert core._verification_path.get()==()


@pytest.mark.parametrize('prospective',[False,True])
def test_true_recursive_edge_fails_and_does_not_poison_next_reader(tmp_path,monkeypatch,prospective):
    registry,ref,kind,raw=registry_case(tmp_path,prospective)
    evidence=registry.proof_evidence(raw);validate=registry._validate
    def recursive(proof,context):
        validate(proof,context)
        registry.verify(evidence,kind)
    monkeypatch.setattr(registry,'_validate',recursive)
    with pytest.raises(core.RecoveryError,match='evidence cycle'):
        registry.verify(evidence,kind)
    assert core._verification_path.get()==()
    monkeypatch.setattr(registry,'_validate',validate)
    assert registry.verify(evidence,kind)['kind']==kind


@pytest.mark.parametrize('prospective',[False,True])
def test_blob_path_decodes_once_and_revalidates_every_new_call(tmp_path,monkeypatch,prospective):
    registry,ref,kind,raw=registry_case(tmp_path,prospective)
    decode=registry.codec.decode_proof;calls=[]
    def counted(data,expected_kind=None):
        calls.append(data)
        return decode(data,expected_kind)
    monkeypatch.setattr(registry.codec,'decode_proof',counted)
    assert registry.verify_blob(ref,kind)['kind']==kind
    assert calls==[raw]
    assert registry.verify_blob(ref,kind)['kind']==kind
    assert calls==[raw,raw]
    path=registry.store.root/'blobs'/(ref['hash']+'.blob')
    path.write_bytes(raw+b' ')
    with pytest.raises(core.RecoveryError):registry.verify_blob(ref,kind)


@pytest.mark.parametrize('prospective',[False,True])
def test_wrong_kind_reference_and_changed_authority_remain_denied(tmp_path,prospective):
    registry,ref,kind,raw=registry_case(tmp_path,prospective)
    with pytest.raises(core.RecoveryError):registry.verify_blob(ref,'CONTROLLER_ADMISSION')
    evidence=registry.proof_evidence(raw)
    with pytest.raises(core.RecoveryError):registry.verify(dict(evidence,authority='OTHER'),kind)
    assert registry.verify_blob(ref,kind)['kind']==kind
    if prospective:
        path=registry.store.root/'custody'/(registry.codec.key_id+'.control')
        path.write_bytes(CONTROL.replace(b'b',b'c'))
    else:
        registry.codec.clock=dict(registry.codec.clock,boot_id='changed')
    with pytest.raises(core.RecoveryError):registry.verify_blob(ref,kind)


def test_copied_context_has_an_immutable_path_and_preserves_cycle_detection():
    registry=object()
    with core._evidence_path(registry,'a'*64):
        context=copy_context()
        with pytest.raises(core.RecoveryError,match='evidence cycle'):
            context.run(lambda: core._evidence_path(registry,'a'*64).__enter__())
        assert core._verification_path.get()==((registry,'a'*64),)
    assert core._verification_path.get()==()


def inventory_registry(tmp_path):
    """Synthetic preparation/catalogue; real codec, store and all validators.

    No operational approval or source authority is asserted by this fixture.
    """
    from copy import deepcopy
    from tests.unit.common.test_failed_fenced_recovery import composition_case, CLOCK, CONTROL
    store=private_store(tmp_path)
    data=store.write_blob('synthetic-report',b'synthetic clock and listener bytes')
    payload=dict(identity='synthetic-clock',approval='clock-pcp',platform=data,
        boot_id=CLOCK['boot_id'],c_clock='clock_gettime:CLOCK_MONOTONIC',
        python_clock='time.clock_gettime_ns:CLOCK_MONOTONIC',unit='NANOSECONDS',
        report=data,equivalent=True,nondecreasing=True,sleep_behavior_equal=True)
    raw=core.canonical_bytes(dict(schema=core.ROOT_SCHEMA,kind='CLOCK_QUALIFICATION',payload=payload))
    clock_ref=store.write_blob(payload['identity'],raw)
    clock=dict(CLOCK,qualification={'authority':'PCP','contract':core.PROTOCOL.replace('-RECOVERY-V1','-ROOT-PROOF')+':1.0.0:CLOCK_QUALIFICATION',**clock_ref})
    decoder=core.RecoveryCodec(CONTROL.encode(),clock)
    prep=object.__new__(core.PreparationContext)
    prep.store=store;prep.record=dict(mode='ORIGINAL',control_hash=decoder.key_id,clock=clock,
        lineage={'predecessor':PROCESS,'generation':'a'*64},controller=PROCESS)
    bindings=dict(root=clock_ref,report=data)
    prep.rows={name:dict(purpose='CLOCK',authority=authority,bindings=bindings)
               for name,authority in [('clock-pcp','PCP'),('clock-ca','CA')]}
    registry=core.EvidenceRegistry(decoder,store,prep)
    _,old,_=composition_case()
    old.update(identity='inventory-0',source=data,scope=dict(data,hash=core.SCOPE_HASH))
    old['instances'][0]['implementation']=data
    old['listeners']=[dict(identity='listener-0',producer_instance='ux-owner',consumer_instance='ux-owner',
                           implementation=data,registered_ns='1',retired_ns=None)]
    def retain(p,issuer=PROCESS):
        raw=decoder.encode_proof('COMPOSITION_INVENTORY',p,issuer,'PREDECESSOR',int(p['observed_ns']))
        return store.write_blob(p['identity'],raw)
    refs=[retain(old)]
    for n in range(1,4):
        new=deepcopy(old);new.update(identity='inventory-'+str(n),previous=refs[-1],
                                    registered_ns=str(n+1),observed_ns=str(n+1))
        refs.append(retain(new));old=new
    return registry,refs,data,retain,old


def test_closed_inventory_scope_reuses_only_structure_and_rechecks_each_proof(tmp_path,monkeypatch):
    registry,refs,_,_,_=inventory_registry(tmp_path)
    structure=registry._inventory_structure;decode=registry.codec.decode_proof
    structures=[];decodes=[]
    def counted(p):
        structures.append(p['identity']);return structure(p)
    def decoded(raw,kind=None):
        decodes.append(kind);return decode(raw,kind)
    monkeypatch.setattr(registry,'_inventory_structure',counted)
    monkeypatch.setattr(registry.codec,'decode_proof',decoded)
    with registry._composition_validation(lambda:None):
        registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')
        assert len(structures)==4
        registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')
        assert len(structures)==4
        assert decodes.count('COMPOSITION_INVENTORY')==5
        assert decodes.count('CLOCK_QUALIFICATION')==5
    registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')
    assert len(structures)==8
    assert core._composition_scope.get() is None


@pytest.mark.parametrize('dependency',['root','ancestor','listener'])
def test_scope_exit_rejects_dependency_changed_after_completed_structure(tmp_path,dependency):
    registry,refs,listener,_,_=inventory_registry(tmp_path)
    ref=refs[-1] if dependency=='root' else refs[0] if dependency=='ancestor' else listener
    with pytest.raises(core.RecoveryError):
        with registry._composition_validation(lambda:None):
            registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')
            (registry.store.root/'blobs'/(ref['hash']+'.blob')).write_bytes(b'tampered')
    assert core._composition_scope.get() is None


@pytest.mark.parametrize('fault',['issuer','clock','kind','authority','structure'])
def test_completed_inventory_does_not_authorize_changed_proof(tmp_path,fault):
    from copy import deepcopy
    registry,refs,_,retain,p=inventory_registry(tmp_path)
    with registry._composition_validation(lambda:None):
        registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')
        with pytest.raises(core.RecoveryError):
            if fault=='issuer':
                ref=retain(p,dict(PROCESS,runtime='foreign'))
                registry.verify_blob(ref,'COMPOSITION_INVENTORY')
            elif fault=='clock':
                registry.preparation.rows['clock-ca']['bindings']={}
                registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')
            elif fault=='kind':registry.verify_blob(refs[-1],'OWNER_RESULT')
            elif fault=='authority':
                raw=registry.store.read_blob(refs[-1]);e=registry.proof_evidence(raw)
                registry.verify(dict(e,authority='OTHER'),'COMPOSITION_INVENTORY')
            else:
                changed=deepcopy(p);changed['slots']=[]
                registry.verify_blob(retain(changed),'COMPOSITION_INVENTORY')


def test_completed_inventory_cannot_bypass_true_cycle_path(tmp_path):
    registry,refs,_,_,_=inventory_registry(tmp_path)
    with registry._composition_validation(lambda:None):
        registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')
        with core._evidence_path(registry,refs[-1]['hash']):
            with pytest.raises(core.RecoveryError,match='evidence cycle'):
                registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')


def test_inventory_scope_cannot_cross_thread_or_outlive_closed_context(tmp_path):
    registry,refs,_,_,_=inventory_registry(tmp_path)
    with registry._composition_validation(lambda:None):
        registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')
        context=copy_context()
        with ThreadPoolExecutor(max_workers=1) as workers:
            assert workers.submit(context.run,registry._active_composition_scope).result(timeout=5) is None
        assert registry._active_composition_scope() is not None
    assert context.run(registry._active_composition_scope) is None


def test_inventory_scope_checks_deadline_before_return_and_clears_after_failure(tmp_path):
    registry,refs,_,_,_=inventory_registry(tmp_path);expired=False
    def deadline():
        if expired:raise core.RecoveryError('TIMEOUT','test deadline')
    with pytest.raises(core.RecoveryError,match='test deadline'):
        with registry._composition_validation(deadline):
            registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY');expired=True
    assert core._composition_scope.get() is None


def test_inventory_scope_rejects_changed_preparation_context(tmp_path):
    from copy import copy
    registry,refs,_,_,_=inventory_registry(tmp_path)
    with pytest.raises(core.RecoveryError,match='composition context changed'):
        with registry._composition_validation(lambda:None):
            registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')
            registry.preparation=copy(registry.preparation)


def test_inventory_reuse_is_bound_to_effective_validation_context(tmp_path,monkeypatch):
    registry,refs,_,_,_=inventory_registry(tmp_path)
    structure=registry._inventory_structure;calls=[]
    def counted(p):
        calls.append(p['identity']);return structure(p)
    monkeypatch.setattr(registry,'_inventory_structure',counted)
    with registry._composition_validation(lambda:None):
        registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY',context={'claim_ns':'10'})
        registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY',context={'claim_ns':'10'})
        assert len(calls)==4
        registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY',context={'claim_ns':'11'})
        assert len(calls)==8


def test_inventory_scope_rejects_changed_store_identity(tmp_path):
    registry,refs,_,_,_=inventory_registry(tmp_path)
    with pytest.raises(core.RecoveryError,match='composition context changed'):
        with registry._composition_validation(lambda:None):
            registry.verify_blob(refs[-1],'COMPOSITION_INVENTORY')
            registry.store=core.RecoveryStore(registry.store.root)


@pytest.mark.parametrize('fault',[None,'recovery-issuer','wrong-observed-process','custody-controller','custody-lineage','exit-proof-original-issuer'])
def test_original_custody_graph_uses_original_observer_not_recovery_launcher(tmp_path,fault):
    from copy import deepcopy,copy
    from kronos.common.failed_fenced_startup import _verify_chain_evidence,RecoveryStartupError
    registry,_,_,_,_=inventory_registry(tmp_path)
    original=registry.preparation
    recovery=copy(original);recovery.record=deepcopy(original.record)
    recovery.record.update(mode='RECOVERY',controller=dict(PROCESS,pid=str(int(PROCESS['pid'])+1)))
    recovery.original=original;registry.preparation=recovery
    observer=original.record['controller']
    if fault=='recovery-issuer':observer=recovery.record['controller']
    subject=dict(PROCESS,runtime='foreign') if fault=='wrong-observed-process' else PROCESS
    raw=core.canonical_bytes(dict(schema='KRONOS_DARWIN_KERNEL_OBSERVATION_V1',adapter='DARWIN_KERNEL_V1',
        boot_id=registry.codec.clock['boot_id'],observed_ns='2',observer=observer,subject=subject,
        kind='PROCESS_BIRTH',syscall='proc_pidinfo:PROC_PIDTBSDINFO',return_bytes='136',errno='0',observed_process=subject))
    raw_ref=registry.store.write_blob('original-kernel-observation',raw)
    payload=dict(identity='original-birth-proof',adapter='DARWIN_KERNEL_V1',boot_id=registry.codec.clock['boot_id'],
        observed_ns='2',observer=observer,subject=subject,kind='PROCESS_BIRTH',raw=raw_ref,result='MATCH')
    proof=registry.codec.encode_proof('PLATFORM_OBSERVATION',payload,observer,'LAUNCHER',2)
    registry.store.write_blob(payload['identity'],proof);evidence=registry.proof_evidence(proof)
    record=dict(kind='CUSTODY',payload=dict(controller=original.record['controller'],lineage=deepcopy(original.record['lineage']),process_binding=evidence))
    if fault=='custody-controller':record['payload']['controller']=recovery.record['controller']
    if fault=='custody-lineage':record['payload']['lineage']['generation']='b'*64
    field='process_binding'
    if fault=='exit-proof-original-issuer':record=dict(kind='EXIT_PROOF',payload={'process_evidence':evidence});field='process_evidence'
    if fault is None:
        assert _verify_chain_evidence(registry,record,field,{})['issuer']==original.record['controller']
    else:
        with pytest.raises((core.RecoveryError,RecoveryStartupError)):
            _verify_chain_evidence(registry,record,field,{})


def test_read_only_directory_scope_keeps_fresh_bytes_and_closes_descriptor(tmp_path):
    import os
    store=private_store(tmp_path);ref=store.write_blob('original',b'original')
    checks=[]
    with store._read_directories(lambda:checks.append(True)):
        scope=store._active_read_directory_scope();descriptor=scope['fd']
        assert store.read_blob(ref)==b'original'
        assert store.read_blob(ref)==b'original'
        assert not os.get_inheritable(descriptor)
    assert checks and store._active_read_directory_scope() is None
    with pytest.raises(OSError):os.fstat(descriptor)


@pytest.mark.parametrize('fault',['root-replaced','root-symlink','root-mode','root-object','leaf-bytes','leaf-symlink','leaf-alias','deadline'])
def test_read_only_directory_scope_denies_mutated_authority_or_content(tmp_path,fault):
    import os
    store=private_store(tmp_path);ref=store.write_blob('original',b'original')
    expired=[False]
    def check():
        if expired[0]:raise core.RecoveryError('TIMEOUT','fixture expired')
    with pytest.raises((core.RecoveryError,OSError)):
        with store._read_directories(check):
            assert store.read_blob(ref)==b'original'
            if fault in {'root-replaced','root-symlink'}:
                moved=store.root.with_name('retained');store.root.rename(moved)
                if fault=='root-replaced':store.root.mkdir(mode=0o700)
                else:store.root.symlink_to(moved,target_is_directory=True)
            elif fault=='root-mode':store.root.chmod(0o755)
            elif fault=='root-object':store.root=store.root.with_name('other')
            elif fault=='deadline':expired[0]=True
            else:
                path=store.root/'blobs'/(ref['hash']+'.blob')
                if fault=='leaf-bytes':path.write_bytes(b'changed!')
                elif fault=='leaf-symlink':
                    moved=path.with_suffix('.retained');path.rename(moved);path.symlink_to(moved)
                else:os.link(path,path.with_suffix('.alias'))
                store.read_blob(ref)
    assert store._active_read_directory_scope() is None


@pytest.mark.parametrize('action',['write','mkdir','provision'])
def test_read_only_directory_scope_cannot_publish_or_repair(tmp_path,action):
    store=private_store(tmp_path);before=sorted(str(p) for p in store.root.rglob('*'))
    with store._read_directories(lambda:None):
        with pytest.raises(core.RecoveryError,match='mutation during read-only'):
            if action=='write':store.write_blob('forbidden',b'no')
            elif action=='mkdir':store._mkdir((),'forbidden')
            else:store.provision({},'0'*64)
    assert sorted(str(p) for p in store.root.rglob('*'))==before


def test_read_directory_scope_cannot_be_reused_by_copied_thread_or_after_exit(tmp_path):
    store=private_store(tmp_path);ref=store.write_blob('original',b'original')
    with store._read_directories(lambda:None):
        copied=copy_context()
        with ThreadPoolExecutor(max_workers=1) as worker:
            assert worker.submit(copied.run,store._active_read_directory_scope).result() is None
            assert worker.submit(copied.run,store.read_blob,ref).result()==b'original'
    assert copied.run(store._active_read_directory_scope) is None


@pytest.mark.parametrize('fault',[None,'read','scope-exit','final-deadline'])
def test_claim_state_is_exposed_only_after_read_scope_and_final_deadline(monkeypatch,fault):
    """Scheduling-only unit test; actual native roundtrip tests authenticate claims.

    The read boundary supplies a schema-valid, MAC-encoded synthetic claim.
    Rejection at any later boundary must not leave a reusable validated claim.
    """
    from contextlib import contextmanager
    from threading import RLock
    from types import SimpleNamespace
    from tests.unit.common.test_failed_fenced_child_receipts import graph
    raw=graph()['CLAIM_RAW'];payload=codec().decode(raw,'CLAIM')['payload']
    transaction=object.__new__(core.RecoveryTransaction)
    transaction._lock=RLock()
    transaction._claim_raw=transaction._claim_payload=transaction._guard_payload=transaction.claim=None
    events=[]
    def assert_unpublished():
        assert transaction._claim_raw is None
        assert transaction._claim_payload is None
        assert transaction._guard_payload is None
        assert transaction.claim is None
    @contextmanager
    def scope(check):
        events.append('enter');yield
        assert_unpublished();events.append('exit')
        if fault=='scope-exit':raise core.RecoveryError('PROVENANCE','changed dependency')
    def read():
        assert_unpublished();events.append('read')
        if fault=='read':raise core.RecoveryError('IDENTITY','invalid claim')
        return raw,payload,{'fixture':'guard'}
    def check():
        assert_unpublished();assert events==['enter','read','exit']
        events.append('deadline')
        if fault=='final-deadline':raise core.RecoveryError('TIMEOUT','expired')
    transaction.registry=SimpleNamespace(_composition_validation=scope)
    transaction.budget=SimpleNamespace(check=check)
    monkeypatch.setattr(transaction,'_read_expected_claim',read)
    if fault:
        with pytest.raises(core.RecoveryError):transaction.expected_claim_raw()
        assert_unpublished()
    else:
        assert transaction.expected_claim_raw()==raw
        assert transaction._claim_raw==raw and transaction._claim_payload==payload
        assert transaction._guard_payload=={'fixture':'guard'}
        assert transaction.claim==core.record_ref(raw)
        assert events==['enter','read','exit','deadline']
