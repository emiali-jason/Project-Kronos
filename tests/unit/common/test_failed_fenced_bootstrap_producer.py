"""Actual captured-code checks plus a synthetic approved bootstrap context.

No native C loader, owner approval or complete recovery is established here.
The fixture substitutes completed preparation/graph validation and kernel calls;
the producer, exact codec, in-memory S proof and source-loader checks are real.
"""
from dataclasses import replace
from hashlib import sha256
import importlib.util
import os
from types import MappingProxyType, SimpleNamespace
import time

import pytest

import kronos.common.failed_fenced_startup as startup_module
from kronos.common.failed_fenced_recovery import (
    RecoveryCodec, RecoveryStore, RecoveryBudget, EvidenceRegistry, PreparationContext,
    canonical_bytes, blob_ref, record_ref, ROOT_SCHEMA,
)
from kronos.intraday.runtime_identity import StartupCapture, _PinnedLoader, canonical, digest
from tests.unit.intraday.test_runtime_identity import _seed


@pytest.fixture
def captured(monkeypatch):
    name='kronos.synthetic_bootstrap';payload=b'answer = 7\n'
    capture=object.__new__(StartupCapture)
    capture._pid=os.getpid();capture._finished=None;capture._loaded={}
    capture._sources=MappingProxyType({name:('/synthetic/bootstrap.py',payload,False)})
    loader=_PinnedLoader(capture,name,'/synthetic/bootstrap.py',payload)
    spec=importlib.util.spec_from_loader(name,loader)
    module=importlib.util.module_from_spec(spec);loader.exec_module(module)
    pairs=((name,sha256(payload).hexdigest()),)
    evidence=_seed(source_snapshot_digest=digest(pairs),loaded_modules=pairs)
    capture._finished=evidence
    plan={'modules':[{'name':name,'digest':pairs[0][1]}]}
    monkeypatch.setattr(startup_module,'_bootstrap_module_snapshot',lambda:((name,module),))
    return evidence,capture,module,plan,pairs


def test_actual_capture_proves_executed_bytes_without_file_reread(captured):
    evidence,_capture,module,plan,pairs=captured
    assert module.answer==7
    budget=SimpleNamespace(check=lambda:None)
    assert startup_module._actual_bootstrap_modules(evidence,plan,pairs,budget)==pairs


@pytest.mark.parametrize('fault',['wrong_payload','wrong_capture','wrong_process','unknown_loader',
    'missing_module','extra_plan_module','changed_inventory','foreign_alias'])
def test_executed_source_changes_or_unknown_identity_deny(captured,monkeypatch,fault):
    evidence,capture,module,plan,pairs=captured
    loader=module.__spec__.loader
    if fault=='wrong_payload':loader.payload=b'answer = 8\n'
    elif fault=='wrong_capture':capture._finished=replace(evidence)
    elif fault=='wrong_process':capture._pid+=1
    elif fault=='unknown_loader':module.__spec__.loader=SimpleNamespace(payload=loader.payload)
    elif fault=='missing_module':monkeypatch.setattr(startup_module,'_bootstrap_module_snapshot',lambda:())
    elif fault=='extra_plan_module':plan['modules'].append({'name':'kronos.unexecuted','digest':'a'*64})
    elif fault=='changed_inventory':pairs=((pairs[0][0],'e'*64),)
    else:
        duplicate=SimpleNamespace(__spec__=module.__spec__)
        monkeypatch.setattr(startup_module,'_bootstrap_module_snapshot',lambda:((pairs[0][0],module),('kronos.alias',duplicate)))
    with pytest.raises(startup_module.RecoveryStartupError):
        startup_module._actual_bootstrap_modules(evidence,plan,pairs,SimpleNamespace(check=lambda:None))


@pytest.fixture
def producer_case(tmp_path,monkeypatch,captured):
    evidence,capture,module,_plan,pairs=captured
    process={'pid':str(os.getpid()),'kernel_birth':{'seconds':'2','microseconds':'3'},
             'runtime':sha256(evidence.evidence_identity.encode()).hexdigest()}
    parent={'pid':str(os.getppid()),'kernel_birth':{'seconds':'1','microseconds':'4'},'runtime':'synthetic-parent'}
    predecessor={'pid':'987654','kernel_birth':{'seconds':'1','microseconds':'1'},'runtime':'synthetic-old'}
    dummy={'authority':'CA','contract':'synthetic-only','identity':'fixture','hash':'d'*64,'bytes':'1'}
    clock={'type':'CLOCK_MONOTONIC','boot_id':'fixture-boot','qualification':dummy}
    origin=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    budget=RecoveryBudget(clock,origin,origin+15_000_000_000)
    codec=RecoveryCodec(b'KRONOS_BROWSER_BACKEND_CONTROL_V1\n987654\n'+b'b'*64+b'\n',clock)
    estate=tmp_path/'estate';estate.mkdir(mode=0o700);store=RecoveryStore(estate)
    scope={'schema':'KRONOS_FAILED_FENCED_GUARD_SCOPE_V1','version':'1.0.0',
           'service':'fixture','installation':'fixture','policy':'MANDATORY'}
    store.provision(scope,sha256(canonical_bytes(scope)).hexdigest())
    inventory=store.write_blob('source-inventory',canonical(pairs))
    irrelevant=store.write_blob('fixture-artifact',b'fixture artifact')
    plan={'schema':'KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0','identity':'fixture-plan',
          'source_inventory':inventory,'modules':[{'name':n,'digest':d} for n,d in pairs],
          'qualification':irrelevant}
    plan_ref=store.write_blob('bootstrap-plan',canonical_bytes(plan))
    restoration_raw=canonical_bytes({'schema':ROOT_SCHEMA,'kind':'RESTORATION_PLAN','payload':{
        'identity':'restore','approval':'fixture','service':'fixture','revision':evidence.source_revision,
        'source_inventory':inventory,'configuration':irrelevant,'owners':[]}})
    restoration=store.write_blob('restore',restoration_raw)
    target={'identity':'target','approval':'fixture','service':'fixture','revision':evidence.source_revision,
        'source_inventory':inventory,'capability_manifest':irrelevant,'configuration':irrelevant,
        'package':irrelevant,'interface':irrelevant,'scope':irrelevant,'restoration_plan':restoration,
        'bootstrap_plan':plan_ref}
    target_raw=codec.encode_proof('TARGET_ARTIFACT',target,parent,'LAUNCHER',origin)
    store.write_blob('target',target_raw)
    registry=object.__new__(EvidenceRegistry);registry.codec=codec;registry.store=store
    prep=object.__new__(PreparationContext)
    prep.record={'mode':'RECOVERY','controller':parent,'lineage':{'predecessor':predecessor,'generation':'e'*64}}
    prep.store=store;registry.preparation=prep
    target_evidence=registry.proof_evidence(target_raw)
    def approved(ref,kind,*args,**kwargs):
        # Explicitly synthetic already-approved boundary, never operational input.
        return {'payload':target if kind=='TARGET_ARTIFACT' else {}}
    registry.verify=approved;registry.verify_blob=approved
    limits={'clock':clock,'origin_ns':str(origin),'stop_deadline_ns':str(budget.stop_deadline_ns)}
    slot='a'*64;nonce='b'*64
    ref=lambda k:{'kind':k,'hash':'f'*64}
    binding={'lineage':prep.record['lineage'],'original':ref('ORIGINAL'),'terminal':ref('TERMINAL'),
             'obligations':[],'cleanup':[],'executor':ref('EXECUTOR')}
    claim={'slot':slot,'guard':ref('GUARD'),'transaction':'fixture','binding':binding,
        'authorization':dummy,'scope_approvals':[],'control_challenge':'c'*64,'launcher':parent,
        'launcher_capability':dummy,'endpoint':{'host':'127.0.0.1','port':'12345','configuration':dummy},
        'limits':limits,'successor_source':target_evidence,'successor_capability':target_evidence,
        'installed_package':dummy,'rollback_package':dummy,'compatibility':dummy}
    claim_raw=codec.encode('CLAIM',claim,'LAUNCHER',origin);store.reserve(slot,'claim',claim_raw)
    checkpoint={'state':'EMPTY','pending':'0','digest':sha256(b'').hexdigest(),'evidence':dummy}
    intent={'slot':slot,'transaction':'fixture','claim':record_ref(claim_raw),
        'observation':ref('OBSERVATION'),'exit_proof':ref('EXIT_PROOF'),'child_nonce':nonce,
        'successor_source':target_evidence,'successor_capability':target_evidence,'installed_package':dummy,
        'checkpoint':checkpoint,'limits':limits,'execution_owner':'launcher','bootstrap_owner':'bootstrap'}
    intent_raw=codec.encode('CHILD_INTENT',intent,'LAUNCHER',origin);store.reserve(slot,'child-intent',intent_raw)
    authority=startup_module.PreparedStartupAuthority(codec,store,registry,budget,{}, {})
    monkeypatch.setattr(startup_module.PreparedStartupAuthority,'verify',lambda self,env:startup_module.selectors(env))
    def graph(*args,**kwargs):
        return dict(kwargs['native_context'],CLAIM=codec.decode(claim_raw),CLAIM_RAW=claim_raw,
                    CHILD_INTENT=codec.decode(intent_raw),CHILD_INTENT_RAW=intent_raw)
    monkeypatch.setattr(startup_module,'validate_recovery_chain',graph)
    monkeypatch.setattr('tools.runtime_source_gate.canonical_parent',lambda **kwargs:None)
    def observation(pid,_budget):
        actual=process if pid==os.getpid() else parent
        return {'pid':str(pid),'kernel_birth':actual['kernel_birth'],
                'parent_pid':parent['pid'] if pid==os.getpid() else '1'}
    monkeypatch.setattr(startup_module,'_bootstrap_process_observation',observation)
    env=dict(zip(startup_module.SELECTORS,('1.0.0',slot,nonce)))
    return SimpleNamespace(authority=authority,startup=evidence,env=env,store=store,codec=codec,
        process=process,parent=parent,slot=slot,target=target,checkpoint=checkpoint)


def test_child_producer_issues_only_s_attestation_without_publishing(producer_case):
    case=producer_case
    before=sorted(str(p.relative_to(case.store.root)) for p in case.store.root.rglob('*'))
    prepared=startup_module.prepare_child_startup(case.authority,case.startup,case.env)
    proof=case.codec.decode_proof(prepared.bootstrap_raw,'BOOTSTRAP_IDENTITY')
    assert proof['role']=='SUCCESSOR' and proof['issuer']==case.process
    assert prepared.native.startup is case.startup and prepared.native.process==case.process
    assert prepared.native.runtime==sha256(case.startup.evidence_identity.encode()).hexdigest()
    assert prepared.checkpoint==case.checkpoint
    assert prepared.restoration_scope['contract'].endswith(':RESTORATION_PLAN')
    assert case.authority.native_context=={}
    assert prepared.authority.native_context['observed_parent']==case.parent
    assert sorted(str(p.relative_to(case.store.root)) for p in case.store.root.rglob('*'))==before


@pytest.mark.parametrize('fault',['pid','parent_birth','nonce','unknown_selector','context_override','dirty_source'])
def test_child_producer_rejects_changed_native_identity_or_authority(producer_case,monkeypatch,fault):
    case=producer_case;authority=case.authority;startup=case.startup;env=dict(case.env)
    if fault=='pid':
        startup=_seed(process_id=os.getpid()+1)
    elif fault=='parent_birth':
        original=startup_module._bootstrap_process_observation
        def changed(pid,budget):
            value=original(pid,budget)
            return dict(value,kernel_birth={'seconds':'9','microseconds':'9'}) if pid==os.getppid() else value
        monkeypatch.setattr(startup_module,'_bootstrap_process_observation',changed)
    elif fault=='nonce':env[startup_module.SELECTORS[2]]='c'*64
    elif fault=='unknown_selector':env[startup_module.PREFIX+'AUTHORITY']='fabricated'
    elif fault=='context_override':authority=replace(authority,native_context={'CLAIM':{'payload':{}}})
    elif fault=='dirty_source':startup=_seed(source_state='DIRTY_WORKTREE')
    with pytest.raises(startup_module.RecoveryStartupError):
        startup_module.prepare_child_startup(authority,startup,env)


def test_bootstrap_exact_executed_set_does_not_claim_unused_inventory(captured):
    evidence,capture,module,plan,pairs=captured
    extra=('kronos.unexecuted',sha256(b'unused').hexdigest())
    complete=tuple(sorted((*pairs,extra)))
    from dataclasses import asdict
    core=asdict(evidence);core.pop('evidence_identity');core['source_snapshot_digest']=digest(complete)
    evidence=replace(evidence,source_snapshot_digest=core['source_snapshot_digest'],
        evidence_identity='INTRADAY-STARTUP-'+digest(core))
    capture._finished=evidence
    capture._sources=MappingProxyType({**dict(capture._sources),'kronos.unexecuted':('/synthetic/unused.py',b'unused',False)})
    assert startup_module._actual_bootstrap_modules(evidence,plan,complete,SimpleNamespace(check=lambda:None))==pairs
