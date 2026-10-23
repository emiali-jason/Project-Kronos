"""Fixed preparation publication/selection; synthetic offline review inputs.

These fixtures stand for previously reviewed offline bytes. They do not obtain
human approvals or qualify an operational process, package, or C launch.
"""
from hashlib import sha256
import os
import time
from copy import deepcopy
import pytest

from kronos.common.failed_fenced_recovery import (
    RecoveryBudget, RecoveryError, PreparationAnchors, canonical_bytes, blob_ref,
    load_native_preparation, publish_reviewed_preparation, SCOPE_HASH, APPENDIX_HASH,
)
from tests.unit.common.test_failed_fenced_recovery import private_store, CLOCK, PROCESS, LINEAGE


def prepared_bytes(store, *, controller=PROCESS, mode='ORIGINAL', attempt='original-attempt', original=None):
    native = b'synthetic offline artifact; no operational authority'
    native_ref = blob_ref('fixture-artifact', native)
    ca_raw, pcp_raw = b'synthetic decisive CA source-channel capture', b'synthetic decisive PCP source-channel capture'
    ca, pcp = blob_ref('ca-decision', ca_raw), blob_ref('pcp-decision', pcp_raw)
    catalogue = {'schema':'KRONOS-RECOVERY-APPROVAL-CATALOGUE/1.0.0','identity':'fixture-catalogue',
        'service':'unit-service','package_manifest':native_ref,'interface':native_ref,
        'scope':dict(native_ref,hash=SCOPE_HASH),'appendix':dict(native_ref,hash=APPENDIX_HASH),'rows':[]}
    catalogue_raw = canonical_bytes(catalogue); catalogue_ref = blob_ref(catalogue['identity'],catalogue_raw)
    selector = dict(mode=mode,service='unit-service',installation='unit-install',lineage=LINEAGE,attempt=attempt)
    record = dict(schema='KRONOS-FAILED-FENCED-CONTROL-PREPARATION/1.0.0',identity='fixture-preparation-'+attempt,
        **selector,controller=controller,control_hash='b'*64,catalogue=catalogue_ref,
        original_preparation=original,launcher_source=native_ref,launcher_package=native_ref,
        clock=CLOCK,prepared_ns='1')
    record_raw=canonical_bytes(record);record_ref=blob_ref(record['identity'],record_raw)
    pin=dict(schema='KRONOS-FAILED-FENCED-PREPARATION-PIN/1.0.0',**selector,preparation=record_ref,catalogue=catalogue_ref)
    pin_raw=canonical_bytes(pin);pin_ref=blob_ref('fixture-pin-'+attempt,pin_raw)
    decisions=[ca,pcp];retained=[(native_ref,native),(ca,ca_raw),(pcp,pcp_raw)]
    attributions=[{'authority':'CA','decision':ca},{'authority':'PCP','decision':pcp}]
    if mode=='RECOVERY':
        raw=b'synthetic exact Sponsor operation capture';ref=blob_ref('sponsor-decision',raw)
        decisions.append(ref);retained.append((ref,raw));attributions.append({'authority':'SPONSOR','decision':ref})
    approval=dict(schema='KRONOS-FAILED-FENCED-PREPARATION-APPROVAL/1.0.0',pin=pin_ref,preparation=record_ref,attributions=attributions)
    approval_raw=canonical_bytes(approval)
    anchors=PreparationAnchors(pin_ref,blob_ref('fixture-approval-'+attempt,approval_raw),catalogue_ref,tuple(decisions))
    return dict(pin_raw=pin_raw,approval_raw=approval_raw,preparation_raw=record_raw,catalogue_raw=catalogue_raw,
                anchors=anchors,retained=tuple(retained))


def publish(store, package):
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    return publish_reviewed_preparation(store,**package,budget=RecoveryBudget(CLOCK,now,now+15_000_000_000))


def test_exact_fixed_publication_roundtrip_without_new_anchor_file(tmp_path):
    store=private_store(tmp_path);package=prepared_bytes(store)
    context=publish(store,package)
    actual=load_native_preparation(store,controller=PROCESS,mode='ORIGINAL')
    assert actual.record==context.record and actual.catalogue==context.catalogue
    assert {p.suffix for p in (store.root/'preparation').iterdir() if p.is_file()}=={'.pin','.approval'}
    with pytest.raises((RecoveryError,FileExistsError)):
        publish(store,package)


@pytest.mark.parametrize('fault',['missing-approval','unknown-file','wrong-controller','ambiguous','wrong-attribution'])
def test_fixed_loader_denies_missing_ambiguous_or_changed_authority(tmp_path,fault):
    store=private_store(tmp_path);package=prepared_bytes(store);publish(store,package)
    controller=PROCESS
    if fault=='missing-approval':
        next((store.root/'preparation').glob('*.approval')).unlink()
    elif fault=='unknown-file':
        store._write(('preparation',),'caller-anchor.json',b'{}')
    elif fault=='wrong-controller':
        controller=dict(PROCESS,runtime='other-loaded-image')
    elif fault=='ambiguous':
        # A second complete preparation for the same actual controller requires
        # exact lineage/attempt selection; no newest-file or arbitrary choice.
        publish(store,prepared_bytes(store,attempt='second-attempt'))
    else:
        path=next((store.root/'preparation').glob('*.approval'))
        # Opaque Blob.identity is not an approval authority. Corrupt the
        # attributed bytes' actual hash so the retained decision is unavailable.
        raw=path.read_bytes().replace(package['anchors'].decisions[0]['hash'].encode(), b'0'*64)
        path.write_bytes(raw)
    with pytest.raises((RecoveryError,FileNotFoundError)):
        load_native_preparation(store,controller=controller,mode='ORIGINAL')


def test_offline_publisher_does_not_accept_unreviewed_bytes_or_missing_decisions(tmp_path):
    store=private_store(tmp_path);package=prepared_bytes(store)
    changed=dict(package,approval_raw=package['approval_raw']+b' ')
    with pytest.raises(RecoveryError):publish(store,changed)
    assert list((store.root/'preparation').iterdir())==[store.root/'preparation'/'records']
    with pytest.raises(RecoveryError):publish(store,dict(package,retained=package['retained'][:-1]))


def test_recovery_selects_exact_original_and_controller_independently(tmp_path):
    store=private_store(tmp_path);original=publish(store,prepared_bytes(store))
    controller=dict(PROCESS,runtime='recovery-controller')
    recovery=publish(store,prepared_bytes(store,controller=controller,mode='RECOVERY',attempt='recovery-attempt',original=original.pin['preparation']))
    assert recovery.original.record==original.record
    assert load_native_preparation(store,controller=controller,mode='RECOVERY').record==recovery.record
    with pytest.raises(RecoveryError):
        load_native_preparation(store,controller=PROCESS,mode='RECOVERY')


def static_package(store,*,fault=None,attempt='static-original'):
    """Full fixed publisher/loader with explicitly synthetic review artifacts."""
    from dataclasses import replace
    import kronos.common.failed_fenced_recovery as core
    package=prepared_bytes(store,controller=dict(PROCESS,runtime='historical-controller'),attempt=attempt)
    record=core.decode_canonical(package['preparation_raw']);native=record['launcher_package']
    ca,pcp=package['anchors'].decisions
    artifact=dict(kind='ARTIFACT',revision='a'*40,source_inventory=native,capability_manifest=native,
        executable=native,package=native,configuration=native,bootstrap_plan=native,qualification=native)
    guard=dict(kind='GUARD',service=record['service'],installation=record['installation'],classification='MANDATORY',
        launcher=native,backend=native,source_inventory=native,sentinel=native,provisioning=native)
    sentinel_raw=store._read((),'guard-scope.json');sentinel=blob_ref('actual-sentinel',sentinel_raw)
    provisioning=dict(schema='KRONOS-FAILED-FENCED-GUARD-PROVISIONING/1.0.0',identity='actual-fixture-provisioning',
        service=record['service'],installation=record['installation'],launcher=native,backend=native,source=native,
        sentinel=sentinel,lock_scope='unit-service',before_first_capable_start=True,fsync_verified=True,readback_verified=True)
    provisioning_raw=canonical_bytes(provisioning);provisioning_ref=blob_ref(provisioning['identity'],provisioning_raw)
    guard.update(sentinel=sentinel,provisioning=provisioning_ref)
    root=dict(schema=core.ROOT_SCHEMA,kind='GUARD_APPLICABILITY',payload=dict(identity='static-guard-root',
        approval='static-ca-guard',service=record['service'],launcher=native,backend=native,source=native,
        classification='MANDATORY',sentinel=sentinel,provisioning=provisioning_ref))
    root_raw=canonical_bytes(root);root_ref=blob_ref(root['payload']['identity'],root_raw)
    package['retained']+=((sentinel,sentinel_raw),(provisioning_ref,provisioning_raw),(root_ref,root_raw))
    rows=[dict(identity='static-artifact',authority='CA',purpose='ARTIFACT',artifact=native,attribution=ca,bindings=artifact),
        dict(identity='static-ca-guard',authority='CA',purpose='GUARD',artifact=root_ref,attribution=ca,bindings=guard),
        dict(identity='static-pcp-guard',authority='PCP',purpose='GUARD',artifact=root_ref,attribution=pcp,bindings=deepcopy(guard))]
    if fault=='missing-pcp':rows.pop()
    elif fault=='changed-pcp':rows[-1]['bindings']['classification']='LEGACY_UNENROLLED'
    elif fault=='wrong-package':rows[0]['bindings']['package']=dict(native,hash='0'*64)
    elif fault=='duplicate-artifact':rows.append(dict(rows[0],identity='another-artifact'))
    catalogue=core.decode_canonical(package['catalogue_raw']);catalogue['rows']=sorted(rows,key=lambda row:row['identity'])
    catraw=canonical_bytes(catalogue);catref=blob_ref(catalogue['identity'],catraw)
    record['catalogue']=catref;raw=canonical_bytes(record);ref=blob_ref(record['identity'],raw)
    pin=core.decode_canonical(package['pin_raw']);pin.update(catalogue=catref,preparation=ref)
    pinraw=canonical_bytes(pin);pinref=blob_ref(package['anchors'].pin['identity'],pinraw)
    approval=core.decode_canonical(package['approval_raw']);approval.update(pin=pinref,preparation=ref)
    approved=canonical_bytes(approval)
    package.update(preparation_raw=raw,pin_raw=pinraw,approval_raw=approved,catalogue_raw=catraw,
        anchors=replace(package['anchors'],pin=pinref,catalogue=catref,
            approval=blob_ref(package['anchors'].approval['identity'],approved)))
    context=publish(store,package)
    return context,dict(PROCESS,runtime=native['hash']),native


def test_static_native_selection_does_not_impersonate_historical_controller_or_grant_operation(tmp_path):
    from kronos.common.failed_fenced_recovery import load_static_native_preparation
    store=private_store(tmp_path);expected,current,plan=static_package(store)
    actual,root=load_static_native_preparation(store,controller=current,clock=CLOCK,key_id='b'*64,helper_plan=plan)
    assert actual.record==expected.record and actual.record['controller']!=current
    assert all(row['purpose'] not in {'ORIGINAL_OPERATION','RECOVERY_OPERATION'} for row in actual.rows.values())
    assert root==expected.rows['static-ca-guard']['artifact']


@pytest.mark.parametrize('fault',['missing-pcp','changed-pcp','wrong-package','duplicate-artifact','wrong-image','wrong-plan','wrong-key','ambiguous-preparation'])
def test_static_native_selection_rejects_incomplete_or_ambiguous_independent_bindings(tmp_path,fault):
    from kronos.common.failed_fenced_recovery import load_static_native_preparation
    store=private_store(tmp_path);_,current,plan=static_package(store,fault=fault)
    key='b'*64
    if fault=='wrong-image':current=dict(current,runtime='0'*64)
    elif fault=='wrong-plan':plan=dict(plan,hash='0'*64)
    elif fault=='wrong-key':key='0'*64
    elif fault=='ambiguous-preparation':static_package(store,attempt='second-static')
    with pytest.raises(RecoveryError):
        load_static_native_preparation(store,controller=current,clock=CLOCK,key_id=key,helper_plan=plan)


def test_first_static_guard_is_keyless_and_never_reads_or_creates_custody(tmp_path,monkeypatch):
    import kronos.common.failed_fenced_recovery as core
    from kronos.common.failed_fenced_startup import guard_admission
    store=private_store(tmp_path);expected,current,plan=static_package(store)
    before={str(p.relative_to(store.root)):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    monkeypatch.setattr(core.RecoveryStore,'read_custody',lambda *args:pytest.fail('cold custody read'))
    monkeypatch.setattr(core.RecoveryStore,'write_custody',lambda *args:pytest.fail('cold custody write'))
    prep,reference=core.load_static_native_preparation(store,controller=current,clock=CLOCK,key_id=None,helper_plan=plan)
    codec=core.StaticPreparationCodec.from_preparation(prep)
    registry=core.EvidenceRegistry(codec,store,prep)
    evidence=registry.proof_evidence(store.read_blob(reference))
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC);budget=RecoveryBudget(CLOCK,now,now+15_000_000_000)
    assert guard_admission(codec=codec,store=store,registry=registry,applicability=evidence,budget=budget)==()
    assert codec.key_id is None and codec.pid is None and not {'_key','_control'}&vars(codec).keys()
    assert before=={str(p.relative_to(store.root)):p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    assert not list((store.root/'custody').iterdir())
    for method in ('decode','encode','encode_proof','_mac','matches_control'):
        with pytest.raises(core.RecoveryError,match='no operational or key authority'):getattr(codec,method)(b'{}')


def test_static_decoder_denies_signed_runtime_proof_and_changed_context(tmp_path):
    import kronos.common.failed_fenced_recovery as core
    from tests.unit.common.test_failed_fenced_recovery import codec as producer,custody_payload
    store=private_store(tmp_path);prep,_,_=static_package(store)
    decoder=core.StaticPreparationCodec.from_preparation(prep)
    with pytest.raises(core.RecoveryError,match='static roots only'):
        decoder.decode_proof(producer().encode('CUSTODY',custody_payload(),'LAUNCHER',2))
    decoder.clock=dict(CLOCK,boot_id='different')
    with pytest.raises(core.RecoveryError,match='static prepared decoder changed'):
        decoder.decode_proof(store.read_blob(prep.rows['static-ca-guard']['artifact']))
