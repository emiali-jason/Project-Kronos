"""Per-slot custody/attribution and bounded guard discovery qualification.

Actual codecs, private store, immutable preparation loader, and slot selection
run. The external complete READY graph validator is an explicit test boundary
here: its schema/timing and native proof tests are separate. These tests do not
claim an independently approved complete native C/READY roundtrip.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
import time

import pytest
from kronos.common import failed_fenced_recovery as core
from kronos.common import failed_fenced_startup as startup
from tests.unit.common import test_failed_fenced_preparation_selection as prepared
from tests.unit.common.test_failed_fenced_recovery import private_store, PROCESS, CLOCK, CONTROL
from tests.unit.common.test_failed_fenced_child_receipts import graph


def publish_preparation(store,codec,lineage,*,mode,attempt,original=None):
    package=prepared.prepared_bytes(store,controller=dict(PROCESS,runtime=attempt+'-controller'),
        mode=mode,attempt=attempt,original=original)
    record=core.decode_canonical(package['preparation_raw'])
    record.update(lineage=lineage,clock=codec.clock,control_hash=codec.key_id)
    raw=core.canonical_bytes(record);record_ref=core.blob_ref(record['identity'],raw)
    pin=core.decode_canonical(package['pin_raw']);pin.update(lineage=lineage,preparation=record_ref)
    pin_raw=core.canonical_bytes(pin);pin_ref=core.blob_ref(package['anchors'].pin['identity'],pin_raw)
    approval=core.decode_canonical(package['approval_raw']);approval.update(pin=pin_ref,preparation=record_ref)
    approval_raw=core.canonical_bytes(approval)
    package.update(preparation_raw=raw,pin_raw=pin_raw,approval_raw=approval_raw,
        anchors=replace(package['anchors'],pin=pin_ref,
            approval=core.blob_ref(package['anchors'].approval['identity'],approval_raw)))
    return prepared.publish(store,package)


def slot_case(store,letter,*,ready=True):
    control=CONTROL.replace('b'*64,letter*64).encode()
    clock=deepcopy(CLOCK);clock['boot_id']='historical-boot-'+letter
    codec=core.RecoveryCodec(control,clock);store.write_custody(control)
    lineage={'predecessor':dict(PROCESS,runtime='runtime-'+letter),'generation':letter*64}
    slot=core.slot_key(lineage);attempt='recovery-'+letter
    original=publish_preparation(store,codec,lineage,mode='ORIGINAL',attempt='original-'+letter)
    prep=publish_preparation(store,codec,lineage,mode='RECOVERY',attempt=attempt,original=original.pin['preparation'])
    values=graph()
    payload=deepcopy(values['CLAIM']['payload'])
    payload.update(slot=slot,transaction=attempt,launcher=prep.record['controller'])
    payload['binding']['lineage']=lineage;payload['limits']['clock']=clock
    raw=codec.encode('CLAIM',payload,'LAUNCHER',1)
    store.reserve(slot,'guard',b'{}');store.reserve(slot,'claim',raw)
    ready_raw=None
    if ready:
        receipt=deepcopy(values['READY_RECEIPT']['payload']);receipt['slot']=slot
        ready_raw=codec.encode('READY_RECEIPT',receipt,'LAUNCHER',2)
        store.publish(ready_raw)
    return SimpleNamespace(codec=codec,registry=core.EvidenceRegistry(codec,store,prep),slot=slot,
        claim=raw,ready=ready_raw,prep=prep)


def gate(store,current,monkeypatch):
    real=current.registry.verify
    monkeypatch.setattr(current.registry,'verify',lambda evidence,kind,*a,**kw:
        {'payload':{'classification':'MANDATORY'}} if kind=='GUARD_APPLICABILITY'
        else real(evidence,kind,*a,**kw))
    checked=[]
    def graph_boundary(codec,actual_store,registry,raw,*,slot,budget,historical):
        assert actual_store is store and historical is True
        receipt=codec.decode(raw,'READY_RECEIPT')
        claim=codec.decode(store.read_reservation(slot,'claim'),'CLAIM')['payload']
        assert receipt['payload']['slot']==slot and registry.preparation.record['attempt']==claim['transaction']
        assert registry.preparation.record['control_hash']==codec.key_id
        checked.append((slot,codec.key_id,codec.clock['boot_id']))
    monkeypatch.setattr(startup,'validate_recovery_chain',graph_boundary)
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    budget=core.RecoveryBudget(CLOCK,now,now+15_000_000_000)
    result=startup.guard_admission(codec=current.codec,store=store,registry=current.registry,
        applicability={},budget=budget,recovery_slot=current.slot)
    return result,checked


def test_old_resolved_slot_uses_its_exact_key_clock_and_attributable_preparation(tmp_path,monkeypatch):
    store=private_store(tmp_path);old=slot_case(store,'c');current=slot_case(store,'d',ready=False)
    result,checked=gate(store,current,monkeypatch)
    assert result==(current.slot,)
    assert checked==[(old.slot,old.codec.key_id,old.codec.clock['boot_id'])]
    assert old.codec.key_id!=current.codec.key_id and old.codec.clock!=current.codec.clock


@pytest.mark.parametrize('fault',['missing-custody','changed-custody','missing-approval','changed-attribution','ambiguous-ready','unknown-slot','unresolved-old'])
def test_changed_or_unresolved_history_blocks_current_admission(tmp_path,monkeypatch,fault):
    store=private_store(tmp_path);old=slot_case(store,'c',ready=fault!='unresolved-old');current=slot_case(store,'d',ready=False)
    if fault=='missing-custody':(store.root/'custody'/(old.codec.key_id+'.control')).unlink()
    elif fault=='changed-custody':(store.root/'custody'/(old.codec.key_id+'.control')).write_bytes(CONTROL.encode())
    elif fault in {'missing-approval','changed-attribution'}:
        selector={name:old.prep.record[name] for name in ('mode','service','installation','lineage','attempt')}
        path=store.root/'preparation'/(sha256(core.canonical_bytes(selector)).hexdigest()+'.approval')
        if fault=='missing-approval':path.unlink()
        else:
            value=core.decode_canonical(path.read_bytes());value['attributions'][0]['decision']['hash']='0'*64
            path.write_bytes(core.canonical_bytes(value))
    elif fault=='ambiguous-ready':
        value=old.codec.decode(old.ready,'READY_RECEIPT')
        store.publish(old.codec.encode('READY_RECEIPT',value['payload'],'LAUNCHER',3))
    elif fault=='unknown-slot':
        raw=old.codec.decode(old.claim,'CLAIM');raw['payload']['slot']='f'*64
        (store.root/'slots'/old.slot/'claim').write_bytes(old.codec.encode('CLAIM',raw['payload'],'LAUNCHER',1))
    with pytest.raises((core.RecoveryError,startup.RecoveryStartupError,OSError)):
        gate(store,current,monkeypatch)
