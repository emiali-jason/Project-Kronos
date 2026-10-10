"""Direct successor qualification using disposable stores and no Provider calls."""
from copy import deepcopy
from datetime import timedelta
import pytest
from kronos.application.intraday_shadow_epochs import restore_epoch
from kronos.intraday.live_shadow import ShadowError, instant
from kronos.intraday.live_shadow_epochs import document, SUCCESSOR_SCHEMA
from kronos.intraday.live_shadow_transition import capability_identity, capability_delta, validate_successor_relation, SUCCESSOR_ADR, SUCCESSOR_OWNERS
from tests.unit.intraday.test_live_shadow_epoch_deterministic_digest import production_case, corrected_restart, retain_equivalence, capability, CALCULATION, sources
from tests.unit.intraday.test_live_shadow_epochs import inventory


def relation(service, approved=True):
    epoch=service._epochs.chain()[0];e=epoch['body'];current=service._runtime_proof()
    changes,_=capability_delta(e['proof'],current)
    rows=[dict(row,source_delta_sha256='a'*64,digest_change_reason='Reviewed composition delta',semantic_impact='Semantically compatible but not identical',owning_tests_sha256='b'*64,protected_tests_sha256='c'*64,failure_behavior='Unapproved targets remain fenced') for row in changes]
    return document('successor_compatibility',dict(schema=SUCCESSOR_SCHEMA,epoch=epoch['identity'],acceptance=e['acceptance'],window=e['window'],start=e['start'],end=e['end'],configuration=current['configuration'],source_capabilities=sorted(deepcopy(e['proof']['capabilities']),key=lambda r:r['identity']),target_capabilities=sorted(deepcopy(current['capabilities']),key=lambda r:r['identity']),source_aggregate=capability_identity(e['proof']),target_aggregate=capability_identity(current),reviewed_changes=rows,semantic_assessment=dict(identity='ISOLATED-SEMANTIC-REVIEW',sha256='d'*64),adr=deepcopy(SUCCESSOR_ADR),direction='SOURCE_TO_TARGET',non_transitive=True,evidence_package=dict(identity='ISOLATED-QUALIFICATION',sha256='e'*64),owner_approvals=[dict(owner=o,disposition='APPROVED' if approved else 'PENDING',identity='ISOLATED-TEST-'+o,sha256='f'*64) for o in SUCCESSOR_OWNERS]))


def validate(record,service):
    return validate_successor_relation(record,service._epochs.chain()[0],service._runtime_proof(),service.clock())


def mutate(record,fn):
    b=deepcopy(record['body']);fn(b);return document('successor_compatibility',b)


def test_direct_restore_preserves_all_authority_and_observation_bytes(production_case):
    s=production_case;e=deepcopy(s._epochs.chain()[0]);s._epochs.retain(relation(s));before=inventory(s._epochs.raw.root)
    s._restore_acceptance();st=s.status()
    assert st['enabled'] and st['runtime_accepted']
    assert st['acceptance_disposition']=='EXISTING_ACCEPTANCE_RESTORED'
    assert st['acceptance_identity']==e['body']['acceptance'] and st['current_epoch']==e['identity']
    assert st['window']['identity']==e['body']['window']
    assert s._window.body['start']==e['body']['start'] and s._window.body['end']==e['body']['end']
    assert st['all_epoch_counts']==dict(cohort_a=34,cohort_b=66,eod_available=0)
    assert st['counts']['cohort_a']==st['counts']['cohort_b']==st['counts']['eod_available']==0
    s._restore_acceptance()
    assert inventory(s._epochs.raw.root)==before and s._epochs.chain()[0]==e and s.status()==st


@pytest.mark.parametrize('field,value',[
('source_aggregate','WO06H-CAPABILITY-'+'0'*64),('target_aggregate','WO06H-CAPABILITY-'+'0'*64),('configuration','INTRADAY-LAUNCHER-CONFIG-'+'0'*64),('epoch','WO06H-EPOCH-'+'0'*64),('acceptance','WO06H-ACCEPTANCE-'+'0'*64),('window','WO06H-WINDOW-'+'0'*64),('start','2026-01-01T00:00:00+05:30'),('end','2099-01-01T00:00:00+05:30'),('schema','KRONOS-WO06H-SUCCESSOR-RUNTIME-COMPATIBILITY/9.0.0'),('direction','TARGET_TO_SOURCE'),('non_transitive',False),('source_aggregate','*'),('target_aggregate','*'),('adr',dict(identity='ARBITRARY',version='1.0.0'))])
def test_wrong_exact_binding_rejected(production_case,field,value):
    with pytest.raises(ShadowError):validate(mutate(relation(production_case),lambda b:b.update({field:value})),production_case)


@pytest.mark.parametrize('fault',['source_missing','target_missing','source_extra','target_extra','duplicate','reorder','digest','version','missing_delta','extra_delta','unreviewed','wrong_old','source_evidence','owning_evidence','protected_evidence','semantic_empty','reason_empty','failure_empty','package','assessment','owner_missing','owner_duplicate','owner_pending'])
def test_maps_review_and_approval_fail_closed(production_case,fault):
    def change(b):
        if fault in ('source_missing','target_missing'):b[fault.split('_')[0]+'_capabilities'].pop()
        elif fault in ('source_extra','target_extra'):b[fault.split('_')[0]+'_capabilities'].append(dict(identity='EXTRA',version='1.0.0',implementation_digest='1'*64))
        elif fault=='duplicate':b['target_capabilities'].append(b['target_capabilities'][0])
        elif fault=='reorder':b['target_capabilities'].reverse()
        elif fault=='digest':b['target_capabilities'][0]['implementation_digest']='0'*64
        elif fault=='version':b['target_capabilities'][0]['version']='9.0.0'
        elif fault=='missing_delta':b['reviewed_changes'].pop()
        elif fault=='extra_delta':b['reviewed_changes'].append(deepcopy(b['reviewed_changes'][0]))
        elif fault=='unreviewed':b['reviewed_changes']=[]
        elif fault=='wrong_old':b['reviewed_changes'][0]['predecessor']['implementation_digest']='0'*64
        elif fault in ('source_evidence','owning_evidence','protected_evidence'):b['reviewed_changes'][0][{'source_evidence':'source_delta_sha256','owning_evidence':'owning_tests_sha256','protected_evidence':'protected_tests_sha256'}[fault]]='invalid'
        elif fault in ('semantic_empty','reason_empty','failure_empty'):b['reviewed_changes'][0][{'semantic_empty':'semantic_impact','reason_empty':'digest_change_reason','failure_empty':'failure_behavior'}[fault]]=''
        elif fault=='package':b['evidence_package']['sha256']=''
        elif fault=='assessment':b['semantic_assessment']['identity']='*'
        elif fault=='owner_missing':b['owner_approvals'].pop()
        elif fault=='owner_duplicate':b['owner_approvals'][1]=b['owner_approvals'][0]
        elif fault=='owner_pending':b['owner_approvals'][0]['disposition']='PENDING'
    with pytest.raises(ShadowError):validate(mutate(relation(production_case),change),production_case)


def test_incomplete_and_tampered_relation(production_case):
    r=relation(production_case)
    for field in ('window','integrity','kind'):
        bad=deepcopy(r)
        if field=='window':bad['body'].pop(field)
        else:bad[field]='CORRUPTED'
        with pytest.raises((ShadowError,KeyError)):validate(bad,production_case)
    bad=deepcopy(r);bad['body']['end']='2099-01-01T00:00:00+05:30'
    with pytest.raises(ShadowError,match='INTEGRITY'):validate(bad,production_case)


def test_draft_has_no_restoration_authority(production_case):
    r=relation(production_case,approved=False)
    assert validate_successor_relation(r,production_case._epochs.chain()[0],production_case._runtime_proof(),production_case.clock(),require_approval=False)
    production_case._epochs.retain(r)
    with pytest.raises(ShadowError,match='NOT_APPROVED'):restore_epoch(production_case)
    assert not production_case.status()['enabled']


def test_duplicate_conflicting_relations(production_case):
    r=relation(production_case);production_case._epochs.retain(r)
    production_case._epochs.retain(mutate(r,lambda b:b['semantic_assessment'].update(identity='ANOTHER-REVIEW')))
    with pytest.raises(ShadowError,match='AMBIGUOUS'):restore_epoch(production_case)
    assert not production_case.status()['enabled']


def test_no_reverse_chaining_or_transitive_inference(production_case):
    r=relation(production_case)
    def reverse(b):
        b['source_aggregate'],b['target_aggregate']=b['target_aggregate'],b['source_aggregate']
        b['source_capabilities'],b['target_capabilities']=b['target_capabilities'],b['source_capabilities']
    production_case._epochs.retain(mutate(r,reverse));assert not production_case.status()['enabled']
    production_case._epochs.retain(r)
    drift=corrected_restart(production_case._epochs.raw.root.parent,production_case,mutation='INTRADAY_DISCOVERY_OPERATION')
    assert not drift.status()['enabled']
    bridge=mutate(relation(drift),lambda b:b.update(source_aggregate=r['body']['target_aggregate'],source_capabilities=deepcopy(r['body']['target_capabilities'])))
    drift._epochs.retain(bridge)
    with pytest.raises(ShadowError,match='INCOMPATIBLE'):restore_epoch(drift)
    assert not drift.status()['enabled']


@pytest.mark.parametrize('when',['before','end','after'])
def test_window_expiry_and_no_backfill(production_case,when):
    production_case._epochs.retain(relation(production_case));e=production_case._epochs.chain()[0]['body']
    now=instant(e['start'])-timedelta(microseconds=1) if when=='before' else instant(e['end'])+(timedelta(microseconds=1) if when=='after' else timedelta())
    production_case.clock=lambda:now;before=inventory(production_case._epochs.raw.root)
    with pytest.raises(ShadowError,match='WINDOW_NOT_ACTIVE'):restore_epoch(production_case)
    status=production_case.status()
    assert inventory(production_case._epochs.raw.root)==before and not status['enabled']
    assert status['epoch_failure'] is None and status['current_epoch']==production_case._epochs.chain()[0]['identity']
    assert len(status['epochs'])==len(production_case._epochs.chain())==2
    retained=status['epochs'][0]
    assert retained['acceptance']==e['acceptance'] and retained['window']==e['window']
    assert retained['start']==e['start'] and retained['end']==e['end']
    assert retained['compatibility']=='INCOMPATIBLE'
    assert status['all_epoch_counts']==dict(cohort_a=34,cohort_b=66,eod_available=0)


def test_legacy_precedence_preserved(production_case):
    retain_equivalence(production_case)
    production_case._epochs.retain(mutate(relation(production_case),lambda b:b.update(schema='BAD')))
    production_case._restore_acceptance();assert production_case.status()['enabled']


def test_frozen_calculation_cannot_be_changed(production_case):
    drift=corrected_restart(production_case._epochs.raw.root.parent,production_case,mutation='WO_06H_LIVE_SHADOW')
    with pytest.raises(ShadowError,match='FROZEN_IMPLEMENTATION_CHANGED'):validate(relation(drift),drift)


def test_new_process_manifest_same_exact_target(production_case):
    production_case._epochs.retain(relation(production_case))
    restart=corrected_restart(production_case._epochs.raw.root.parent,production_case)
    assert restart._runtime_proof()['manifest']!=production_case._runtime_proof()['manifest']
    assert restart.status()['enabled']


def test_retention_readback_and_corruption(production_case):
    r=relation(production_case);production_case._epochs.retain(r);production_case._epochs.retain(r)
    assert production_case._epochs.load(r['identity'])==r
    p=production_case._epochs.root/(r['identity']+'.json');p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(ShadowError,match='ENCODING_INVALID'):restore_epoch(production_case)
    assert not production_case.status()['enabled']


def test_storage_failure_preserved(production_case,monkeypatch):
    r=relation(production_case);before=inventory(production_case._epochs.raw.root)
    monkeypatch.setattr(production_case._epochs,'_directory',lambda *args:(_ for _ in ()).throw(OSError('isolated storage failure')))
    with pytest.raises(OSError):production_case._epochs.retain(r)
    assert inventory(production_case._epochs.raw.root)==before and production_case._accepted is None


def test_successor_policy_changes_are_digest_protected():
    original=sources();changed=dict(original);module='kronos.intraday.live_shadow_transition'
    changed[module]=changed[module].replace("body['non_transitive'] is not True","body['non_transitive'] is True")
    assert capability(CALCULATION,sources=changed)!=capability(CALCULATION,sources=original)


def test_no_relation_still_incompatible(production_case):
    with pytest.raises(ShadowError,match='INCOMPATIBLE'):restore_epoch(production_case)
    assert not production_case.status()['enabled']
