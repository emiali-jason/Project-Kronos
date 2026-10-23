"""Keyless core semantics, not native exchange or operational qualification.

The synthetic native boundary below is explicitly substituted only in tests.
The owning startup tests separately exercise actual pipe/source/parent checks;
this fixture cannot create a production NativeSemanticExchange.
"""
from hashlib import sha256
import os

import pytest

import kronos.common.failed_fenced_recovery as core

PROCESS={'pid':str(os.getpid()),'kernel_birth':{'seconds':'1','microseconds':'2'},'runtime':'unit-runtime'}
CLOCK={'type':'CLOCK_MONOTONIC','boot_id':'unit-boot','qualification':{
    'authority':'PCP','contract':'KRONOS-FAILED-FENCED-ROOT-PROOF:1.0.0:CLOCK_QUALIFICATION',
    'identity':'unit-clock','hash':'c'*64,'bytes':'1'}}
CONTROL=(f'KRONOS_BROWSER_BACKEND_CONTROL_V1\n{os.getpid()}\n'+('b'*64)+'\n').encode()

def control_payload():
    ref=core.blob_ref('native-control',CONTROL)
    return {'identity':'native-control-binding','process':PROCESS,'live_control':ref,
            'retained_control':ref,'schema':'KRONOS_BROWSER_BACKEND_CONTROL_V1',
            'boot_id':CLOCK['boot_id'],'verified_ns':'2'}

def record_payload():
    proof={'authority':'PREDECESSOR','contract':'unit-proof','identity':'unit-proof',
           'hash':'d'*64,'bytes':'1'}
    return {'lineage':{'predecessor':PROCESS,'generation':'a'*64},
        'checkpoint_hash':sha256(CONTROL).hexdigest(),'checkpoint_bytes':str(len(CONTROL)),
        'controller':PROCESS,'controller_capability':proof,'live_control':proof,
        'process_binding':proof,'verified_ns':'1','execution_owner':'original-publisher'}

@pytest.fixture
def semantic_boundary(tmp_path,monkeypatch):
    # Test-only C-authentication substitute. It verifies actual MACs with a
    # separate producer and retains exact wrappers; the tested codec has no key.
    producer=core.RecoveryCodec(CONTROL,CLOCK)
    class SyntheticBoundary:
        def __init__(self):
            self.key_id=producer.key_id;self.control_pid=producer.pid;self.clock=CLOCK
            self.controller=PROCESS;self.helper=PROCESS;self.estate=tmp_path/'estate'
            self.allowed={};self.active=True;self.custody_checks=0
        from contextlib import contextmanager
        @contextmanager
        def _readonly_validation(self):
            # Synthetic test boundary retains its full check at every call;
            # actual native scope behavior is qualified separately.
            self.require_current()
            yield
            self.require_current()
        def require_current(self):
            if not self.active:raise core.RecoveryError('TIMEOUT','synthetic exchange expired')
        def authenticate(self,raw,*,external):
            self.require_current()
            if self.allowed.get((sha256(raw).hexdigest(),external))!=raw:
                raise core.RecoveryError('AUTHORITY','not in actual native exchange')
            (producer.decode_proof if external else producer.decode)(raw)
        def verify_custody(self,payload):
            self.require_current();self.custody_checks+=1
            if payload!=control_payload():
                raise core.RecoveryError('IDENTITY','native custody witness mismatch')
    boundary=SyntheticBoundary()
    boundary.estate.mkdir(mode=0o700)
    writable=core.RecoveryStore(boundary.estate)
    scope={'schema':'KRONOS_FAILED_FENCED_GUARD_SCOPE_V1','version':'1.0.0',
        'service':'unit-service','installation':'unit-install','policy':'MANDATORY'}
    writable.provision(scope,sha256(core.canonical_bytes(scope)).hexdigest())
    def native(actual):
        if actual is not boundary:raise core.RecoveryError('AUTHORITY','foreign synthetic exchange')
        actual.require_current();return actual
    monkeypatch.setattr(core,'_native_semantic_exchange',native)
    codec=core.NativeVerifiedCodec(boundary,_loader=core._NATIVE_SEMANTIC_LOADER)
    readonly=core.NativeReadOnlyStore(boundary,_loader=core._NATIVE_SEMANTIC_LOADER)
    return producer,boundary,codec,writable,readonly

@pytest.mark.parametrize('constructor',[core.NativeVerifiedCodec,core.NativeReadOnlyStore])
def test_no_public_hash_or_mapping_constructor(constructor):
    with pytest.raises(core.RecoveryError,match='native semantic loader'):
        constructor({'authenticated':['a'*64],'key_id':'b'*64})

def test_native_semantic_context_cannot_be_directly_constructed():
    with pytest.raises(core.RecoveryError,match='native semantic factory'):
        core.NativeSemanticContext({},None,None,None)

def test_real_factory_rejects_generic_hash_list_and_verifier_object():
    from types import SimpleNamespace
    for value in ({'authenticated':['a'*64]},SimpleNamespace(require_current=lambda:None)):
        with pytest.raises(core.RecoveryError,match='native semantic exchange required'):
            core.NativeSemanticContext.from_exchange(value)

def test_native_exchange_itself_rejects_direct_context_construction():
    from kronos.common.failed_fenced_startup import NativeSemanticExchange,RecoveryStartupError
    with pytest.raises(RecoveryStartupError,match='RECEIVER_REQUIRED'):
        NativeSemanticExchange({'authenticated':['a'*64]},())

def test_keyless_main_and_external_decode_preserve_exact_schema(semantic_boundary):
    producer,boundary,codec,_writable,_readonly=semantic_boundary
    main=producer.encode('CUSTODY',record_payload(),'LAUNCHER',2)
    proof=producer.encode_proof('CONTROL_BINDING',control_payload(),PROCESS,'PREDECESSOR',2)
    boundary.allowed[(sha256(main).hexdigest(),False)]=main
    boundary.allowed[(sha256(proof).hexdigest(),True)]=proof
    assert codec.decode(main,'CUSTODY')==producer.decode(main,'CUSTODY')
    assert codec.decode_proof(proof,'CONTROL_BINDING')==producer.decode_proof(proof,'CONTROL_BINDING')
    assert '_key' not in vars(codec) and '_control' not in vars(codec)
    with pytest.raises(core.RecoveryError):codec.decode(main,'ACK')
    with pytest.raises(core.RecoveryError):codec.decode_proof(proof,'SOURCE')
    with pytest.raises(core.RecoveryError):codec.decode_proof(b'[]')

def test_other_valid_mac_is_not_native_authenticated_input(semantic_boundary):
    producer,boundary,codec,_writable,_readonly=semantic_boundary
    first=producer.encode('CUSTODY',record_payload(),'LAUNCHER',2)
    other=producer.encode('CUSTODY',record_payload(),'LAUNCHER',3)
    boundary.allowed[(sha256(first).hexdigest(),False)]=first
    assert codec.decode(first)['issued_ns']=='2'
    with pytest.raises(core.RecoveryError,match='not in actual native exchange'):
        codec.decode(other)
    changed=core.decode_canonical(first);changed['role']='PREDECESSOR'
    malformed=core.canonical_bytes(changed)
    boundary.allowed[(sha256(malformed).hexdigest(),False)]=malformed
    with pytest.raises(core.RecoveryError):codec.decode(malformed)

@pytest.mark.parametrize('method',['encode','encode_proof','_mac','matches_control'])
def test_semantic_helper_cannot_issue_or_accept_secret(method,semantic_boundary):
    _producer,_boundary,codec,_writable,_readonly=semantic_boundary
    with pytest.raises(core.RecoveryError,match='semantic helper'):
        getattr(codec,method)(CONTROL)

def test_control_binding_uses_only_native_witness(semantic_boundary,monkeypatch):
    _producer,boundary,codec,_writable,readonly=semantic_boundary
    monkeypatch.setattr(core.RecoveryStore,'read_custody',lambda *args:pytest.fail('custody read'))
    codec.verify_control_binding(control_payload(),readonly)
    assert boundary.custody_checks==1
    changed=dict(control_payload(),verified_ns='3')
    with pytest.raises(core.RecoveryError):codec.verify_control_binding(changed,readonly)
    with pytest.raises(core.RecoveryError):readonly.read_custody(codec.key_id)
    with pytest.raises(core.RecoveryError):readonly._read(('custody',),codec.key_id+'.control')

@pytest.mark.parametrize('method',['_mkdir','_write','provision','write_blob','publish','reserve',
    'publish_bootstrap','write_custody','service_lock'])
def test_readonly_store_cannot_mutate_or_acquire_controller_lock(method,semantic_boundary):
    _producer,_boundary,_codec,_writable,readonly=semantic_boundary
    with pytest.raises(core.RecoveryError,match='read-only'):
        getattr(readonly,method)()

def test_readonly_blob_read_has_exact_bytes_and_context_lifetime(semantic_boundary):
    _producer,boundary,codec,writable,readonly=semantic_boundary
    ref=writable.write_blob('native-result',b'exact native result')
    assert readonly.read_blob(ref)==b'exact native result'
    changed=dict(ref,bytes='1')
    with pytest.raises(core.RecoveryError):readonly.read_blob(changed)
    boundary.active=False
    with pytest.raises(core.RecoveryError,match='expired'):readonly.read_blob(ref)
    with pytest.raises(core.RecoveryError,match='expired'):codec.decode(b'{}')

def test_readonly_store_cannot_be_redirected(semantic_boundary):
    _producer,boundary,_codec,_writable,readonly=semantic_boundary
    readonly.estate=boundary.estate.parent
    with pytest.raises(core.RecoveryError,match='estate changed'):
        readonly._read((),'guard-scope.json')

def test_semantic_registry_cannot_mix_producer_store_or_codec(semantic_boundary):
    producer,_boundary,codec,writable,readonly=semantic_boundary
    prep=object.__new__(core.PreparationContext)
    prep.store=writable
    with pytest.raises(core.RecoveryError,match='typed evidence context'):
        core.EvidenceRegistry(codec,writable,prep)
    prep.store=readonly
    with pytest.raises(core.RecoveryError,match='typed evidence context'):
        core.EvidenceRegistry(producer,readonly,prep)

def test_original_secret_codec_keeps_actual_custody_validation(semantic_boundary):
    producer,_boundary,_codec,writable,_readonly=semantic_boundary
    writable.write_custody(CONTROL)
    producer.verify_control_binding(control_payload(),writable)
    bad=control_payload();bad['retained_control']=dict(bad['retained_control'],bytes='1')
    with pytest.raises(core.RecoveryError,match='retained control mismatch'):
        producer.verify_control_binding(bad,writable)


@pytest.mark.parametrize('fault',[None,'claim-not-retained','claim-changed','context-changed','custody-changed'])
def test_keyless_historical_claim_keeps_original_key_and_actual_custody_boundary(semantic_boundary,monkeypatch,fault):
    from tests.unit.common.test_failed_fenced_guard_history import slot_case
    _producer,boundary,current,writable,readonly=semantic_boundary
    old=slot_case(writable,'c')
    old_payload=old.codec.decode(old.claim,'CLAIM')['payload']
    raw_control=old.codec._control
    ref=core.blob_ref('historical-control',raw_control)
    payload=dict(identity='historical-control-binding',process=old_payload['binding']['lineage']['predecessor'],
        live_control=ref,retained_control=ref,schema='KRONOS_BROWSER_BACKEND_CONTROL_V1',
        boot_id=old.codec.clock['boot_id'],verified_ns='2')
    proof=old.codec.encode_proof('CONTROL_BINDING',payload,payload['process'],'PREDECESSOR',3)
    writable.write_blob(payload['identity'],proof)
    authenticated=[]
    def actual_native_leaf(raw,*,external):
        boundary.require_current()
        assert raw in (old.claim,proof)
        checked=(old.codec.decode_proof if external else old.codec.decode)(raw)
        if external:
            old.codec.verify_control_binding(checked['payload'],writable)
        authenticated.append(raw)
    monkeypatch.setattr(boundary,'authenticate',actual_native_leaf)
    if fault=='claim-not-retained':
        (writable.root/'slots'/old.slot/'claim').unlink()
        with pytest.raises(core.RecoveryError):current.for_historical_claim(readonly,old.claim)
        return
    historical=current.for_historical_claim(readonly,old.claim)
    assert historical.key_id==old.codec.key_id!=current.key_id
    assert historical.clock==old.codec.clock!=current.clock
    assert '_control' not in vars(historical) and '_key' not in vars(historical)
    if fault=='claim-changed':(writable.root/'slots'/old.slot/'claim').write_bytes(b'{}')
    elif fault=='context-changed':historical.clock=CLOCK
    elif fault=='custody-changed':(writable.root/'custody'/(old.codec.key_id+'.control')).write_bytes(CONTROL)
    if fault:
        with pytest.raises(core.RecoveryError):historical.decode_proof(proof,'CONTROL_BINDING')
    else:
        with pytest.raises(core.RecoveryError,match='not authenticated'):
            historical.verify_control_binding(payload,readonly)
        assert historical.decode_proof(proof,'CONTROL_BINDING')['payload']==payload
        historical.verify_control_binding(payload,readonly)
        assert proof in authenticated and old.claim in authenticated
        with pytest.raises(core.RecoveryError):historical.encode('CUSTODY',record_payload(),'LAUNCHER',4)


def test_cold_native_guard_has_no_current_key_and_authenticates_no_runtime_bytes(semantic_boundary,monkeypatch):
    from tests.unit.common.test_failed_fenced_preparation_selection import static_package
    from kronos.common.failed_fenced_startup import guard_admission
    import time
    _producer,boundary,_codec,writable,readonly=semantic_boundary
    expected,current,plan=static_package(writable)
    boundary.stage='GUARD_ADMISSION';boundary.key_id=boundary.control_pid=None
    boundary._body={'custody':None};boundary.clock=expected.record['clock']
    monkeypatch.setattr(boundary,'authenticate',lambda *a,**kw:pytest.fail('empty guard authenticated runtime bytes'))
    monkeypatch.setattr(boundary,'verify_custody',lambda *a,**kw:pytest.fail('empty guard custody observation'))
    monkeypatch.setattr(core.RecoveryStore,'read_custody',lambda *a,**kw:pytest.fail('empty guard custody read'))
    codec=core.NativeVerifiedCodec(boundary,_loader=core._NATIVE_SEMANTIC_LOADER)
    prep,reference=core.load_static_native_preparation(readonly,controller=current,clock=codec.clock,key_id=None,helper_plan=plan)
    registry=core.EvidenceRegistry(codec,readonly,prep)
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC);budget=core.RecoveryBudget(codec.clock,now,now+15_000_000_000)
    before={str(p.relative_to(writable.root)):p.read_bytes() for p in writable.root.rglob('*') if p.is_file()}
    assert guard_admission(codec=codec,store=readonly,registry=registry,
        applicability=registry.proof_evidence(readonly.read_blob(reference)),budget=budget)==()
    assert codec.key_id is None and codec.pid is None
    assert not list((writable.root/'custody').iterdir())
    assert before=={str(p.relative_to(writable.root)):p.read_bytes() for p in writable.root.rglob('*') if p.is_file()}
    with pytest.raises(core.RecoveryError,match='no control custody'):codec.verify_control_binding(control_payload(),readonly)


def test_keyless_guard_still_requires_actual_historical_custody(semantic_boundary,monkeypatch):
    from tests.unit.common.test_failed_fenced_guard_history import slot_case
    _producer,boundary,_codec,writable,readonly=semantic_boundary
    old=slot_case(writable,'c')
    boundary.stage='GUARD_ADMISSION';boundary.key_id=boundary.control_pid=None;boundary._body={'custody':None}
    current=core.NativeVerifiedCodec(boundary,_loader=core._NATIVE_SEMANTIC_LOADER)
    def native_retained_auth(raw,*,external):
        value=core.decode_canonical(raw)
        actual=core.RecoveryCodec(writable.read_custody(value['key_id']),value['clock'])
        return (actual.decode_proof if external else actual.decode)(raw)
    monkeypatch.setattr(boundary,'authenticate',native_retained_auth)
    assert current.for_historical_claim(readonly,old.claim).key_id==old.codec.key_id
    (writable.root/'custody'/(old.codec.key_id+'.control')).unlink()
    with pytest.raises(core.RecoveryError):current.for_historical_claim(readonly,old.claim)
    assert not list((writable.root/'custody').iterdir())
