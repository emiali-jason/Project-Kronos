"""Actual fact capture with explicit synthetic independently-approved rows.

Native object/retained-byte checks run; existing approved static catalogue and
Darwin observations are substituted by the READY component fixture. This is
not operational approval or full C roundtrip qualification.
"""
from dataclasses import replace
from types import SimpleNamespace
from copy import deepcopy
import pytest
from kronos.common.failed_fenced_startup import (PreparedRuntimeFactory, capture_runtime_facts,
    complete_prospective_control, prepare_original_binding, RecoveryStartupError)
from tests.unit.common.test_failed_fenced_ready_producer import ready_case


def capture_case(case):
    ledger=case.runtime.ledger
    ledger.native_parent=case.session.parent
    prep=case.registry.preparation
    prep.record['service']='fixture'
    prep.record['launcher_package']=case.target['package']
    import json
    configuration=ledger.store.write_blob('actual-test-endpoint',json.dumps({'browser_port':case.server.server_port}).encode())
    prep.rows['capture-artifact']={'identity':'capture-artifact','authority':'CA','purpose':'ARTIFACT',
        'bindings':{'revision':ledger.native_startup.source_revision,'source_inventory':case.target['source_inventory'],
                    'package':case.target['package'],'configuration':configuration,'capability_manifest':case.target['capability_manifest']}}
    factory=object.__new__(PreparedRuntimeFactory)
    object.__setattr__(factory,'authority',SimpleNamespace(registry=case.registry,budget=case.session.budget))
    object.__setattr__(factory,'source_inventory',case.target['source_inventory'])
    return replace(case.runtime,factory=factory)


def test_actual_runtime_captures_facts_without_future_original_operation(ready_case):
    case=ready_case;runtime=capture_case(case)
    source,capability,endpoint=capture_runtime_facts(runtime,case.server)
    for evidence,kind in ((source,'SOURCE'),(capability,'CAPABILITY'),(endpoint,'ENDPOINT_CONFIGURATION')):
        proof=runtime.ledger.registry.verify(evidence,kind)
        assert proof['issuer']==runtime.ledger.process and proof['role']=='PREDECESSOR'
    assert not hasattr(runtime.ledger,'prospective_control')
    assert not list((runtime.ledger.store.root/'custody').iterdir())
    assert runtime.ledger.original is None and runtime.ledger.lineage is None
    assert prepare_original_binding(case.server,'a'*64,case.session.budget.origin_ns+10_000_000_000) is None
    with pytest.raises(RecoveryStartupError,match='ONCE'):
        capture_runtime_facts(runtime,case.server)


def test_admitted_pulse_defers_control_until_real_checkpoint_and_publishes_once(ready_case,monkeypatch):
    case=ready_case;runtime=capture_case(case);ledger=runtime.ledger
    capture_runtime_facts(runtime,case.server)
    ordinary=[]
    monkeypatch.setattr(case.server,'_service_actions_admitted',lambda:ordinary.append('pulse'))
    before={p:p.read_bytes() for p in ledger.store.root.rglob('*') if p.is_file()}
    case.server.service_actions()
    assert ledger._prospective_control_state=='WAITING'
    assert before=={p:p.read_bytes() for p in ledger.store.root.rglob('*') if p.is_file()}
    assert not hasattr(ledger,'prospective_control')
    # Exact raw checkpoint normally retained by counted C; fixture substitutes
    # only that external producer, never CONTROL_BINDING validation.
    ledger.store.write_custody(runtime.restart_control.private_bytes_for_recovery())
    publish=ledger.publish_proof;observed=[]
    def owned(kind,payload,**kwargs):
        if kind=='CONTROL_BINDING':
            ticket=ledger.current_ticket()
            observed.append((ticket.kind,ledger.coordinator.is_live(ticket)))
        return publish(kind,payload,**kwargs)
    monkeypatch.setattr(ledger,'publish_proof',owned)
    case.server.service_actions()
    proof=ledger.registry.verify(ledger.prospective_control,'CONTROL_BINDING')
    assert proof['payload']['live_control']==proof['payload']['retained_control']
    assert ledger._prospective_control_state=='COMPLETE'
    assert observed==[('SERVER_PULSE',True)]
    after={p:p.read_bytes() for p in ledger.store.root.rglob('*') if p.is_file()}
    case.server.service_actions()
    assert after=={p:p.read_bytes() for p in ledger.store.root.rglob('*') if p.is_file()}
    assert observed==[('SERVER_PULSE',True)] and ordinary==['pulse']*3
    assert ledger.coordinator.snapshot()['owners']=={}


@pytest.mark.parametrize('fault',['partial_checkpoint','live_changed','unknown_publication'])
def test_control_completion_failure_is_sticky_and_never_repairs_or_republishes(ready_case,monkeypatch,fault):
    case=ready_case;runtime=capture_case(case);ledger=runtime.ledger
    capture_runtime_facts(runtime,case.server)
    monkeypatch.setattr(case.server,'_service_actions_admitted',lambda:None)
    private=runtime.restart_control.private_bytes_for_recovery()
    if fault=='partial_checkpoint':
        ledger.store._write(('custody',),ledger.codec.key_id+'.control',b'partial')
    else:
        ledger.store.write_custody(private)
    if fault=='live_changed':object.__setattr__(runtime.restart_control,'_token','d'*64)
    publish=ledger.publish_proof;attempts=[]
    def uncertain(kind,payload,**kwargs):
        result=publish(kind,payload,**kwargs)
        if kind=='CONTROL_BINDING':
            attempts.append(result)
            raise OSError('synthetic unknown durability outcome')
        return result
    if fault=='unknown_publication':monkeypatch.setattr(ledger,'publish_proof',uncertain)
    case.server.service_actions()
    assert ledger._prospective_control_state=='FAILED' and ledger._ineligible is not None
    assert not hasattr(ledger,'prospective_control')
    assert case.server._failed_fenced_control_failure=='CONTROL_BINDING_UNAVAILABLE'
    after={p:p.read_bytes() for p in ledger.store.root.rglob('*') if p.is_file()}
    case.server.service_actions()
    assert after=={p:p.read_bytes() for p in ledger.store.root.rglob('*') if p.is_file()}
    assert len(attempts)==(1 if fault=='unknown_publication' else 0)
    assert ledger.coordinator.snapshot()['owners']=={}


def test_control_completion_requires_actual_admitted_open_pulse(ready_case,monkeypatch):
    case=ready_case;runtime=capture_case(case);ledger=runtime.ledger
    capture_runtime_facts(runtime,case.server)
    ledger.store.write_custody(runtime.restart_control.private_bytes_for_recovery())
    with pytest.raises(RecoveryStartupError,match='PULSE_REQUIRED'):
        complete_prospective_control(case.server)
    monkeypatch.setattr(case.server,'_service_actions_admitted',lambda:pytest.fail('fenced pulse executed'))
    ledger.coordinator._state='FENCED'
    try:case.server.service_actions()
    finally:ledger.coordinator._state='OPEN'
    assert not hasattr(ledger,'prospective_control')


@pytest.mark.parametrize('fault',['tail','artifact','operation','actual_source','control'])
def test_runtime_fact_capture_rejects_missing_or_changed_source_boundary(ready_case,fault):
    case=ready_case;runtime=capture_case(case)
    if fault=='tail':case.registry.preparation.rows.pop('pcp-tail')
    elif fault=='artifact':case.registry.preparation.rows['capture-artifact']['bindings']['revision']='a'*40
    elif fault=='operation':
        case.registry.preparation.rows['capture-artifact']['bindings']['capability_manifest']=case.target['configuration']
    elif fault=='actual_source':object.__setattr__(runtime.ledger.native_startup,'source_revision','a'*40)
    else:object.__setattr__(runtime.restart_control,'_token','d'*64)
    with pytest.raises((ValueError,OSError)):
        capture_runtime_facts(runtime,case.server)
    assert not hasattr(runtime.ledger,'prospective_control')


def test_capture_revalidates_guards_while_canonical_parent_holds_service_lock(tmp_path, monkeypatch):
    """Real lock/estate; Darwin parent and reviewed static row are test leaves."""
    import time
    from kronos.common.failed_fenced_recovery import RecoveryBudget, RecoveryError
    from kronos.common.failed_fenced_startup import PreparedCaptureInstallation
    from tests.unit.common.test_failed_fenced_recovery import private_store, codec, CLOCK, PROCESS
    from tools import runtime_source_gate
    store=private_store(tmp_path)
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    # Only the final 200ms remains. A nested lock acquisition deterministically
    # exhausts it; direct immutable validation completes with the lock retained.
    budget=RecoveryBudget(CLOCK,now-14_800_000_000,now+200_000_000)
    calls=[]
    registry=SimpleNamespace(verify=lambda evidence,kind:calls.append(kind))
    authority=PreparedCaptureInstallation(codec(),store,registry,budget,{},None,PROCESS)
    monkeypatch.setattr(runtime_source_gate,'native_boot_id',lambda:CLOCK['boot_id'])
    monkeypatch.setattr(runtime_source_gate,'canonical_parent_identity',lambda **kwargs:PROCESS)
    with store.service_lock(budget):
        assert authority.verify({}) is None
        assert calls==['GUARD_APPLICABILITY']
        # A retained unresolved/partial guard still denies under that same lock.
        store.reserve('a'*64,'guard',b'{}')
        with pytest.raises(RecoveryError,match='guard/slot mismatch'):
            authority.verify({})
    assert calls==['GUARD_APPLICABILITY']


def test_runtime_capture_distinguishes_reviewed_rollback_with_identical_source(ready_case):
    case=ready_case;runtime=capture_case(case)
    prep=case.registry.preparation
    rollback=deepcopy(prep.rows['capture-artifact'])
    rollback['identity']='reviewed-rollback-artifact'
    rollback['bindings']['package']=case.runtime.ledger.store.write_blob('different-native-package',b'[]')
    prep.rows[rollback['identity']]=rollback
    source,_,_=capture_runtime_facts(runtime,case.server)
    assert runtime.ledger.registry.verify(source,'SOURCE')['payload']['package']==prep.record['launcher_package']


def test_canonical_construction_does_not_publish_original_custody(ready_case,monkeypatch):
    """Actual factory/control/roster; prior static approval is a fixture leaf."""
    from kronos.common import failed_fenced_startup as module
    from kronos.common.failed_fenced_recovery import RecoveryStore
    from tools import runtime_source_gate
    case=ready_case
    authority=module.PreparedCaptureInstallation(case.session.codec,case.session.store,case.registry,
        case.session.budget,{},case.runtime.ledger.native_startup,case.session.parent)
    monkeypatch.setattr(module.PreparedCaptureInstallation,'verify',lambda *_:None)
    monkeypatch.setattr(runtime_source_gate,'fixed_native_estate',lambda:case.session.store.estate)
    monkeypatch.setattr(RecoveryStore,'write_custody',lambda *args:pytest.fail('P cannot publish original custody'))
    factory=module.PreparedRuntimeFactory(authority,case.runtime.ledger.scope,case.target['source_inventory'])
    created=factory.construct(case.runtime.ledger.native_startup)
    assert created.restart_control.owns_current_process()
    assert created.ledger.codec.matches_control(created.restart_control.private_bytes_for_recovery())
    assert created.ledger.original is None and created.ledger.lineage is None
    assert not list((case.session.store.root/'custody').iterdir())
    created.ledger._canonical_startup_ticket.release()


def test_r3_estate_ignores_redirected_home_and_checks_native_account_guards(tmp_path,monkeypatch):
    import pwd,os,time
    from tools import runtime_source_gate
    from kronos.common.failed_fenced_startup import _verify_installation_guards
    from kronos.common.failed_fenced_recovery import RecoveryStore,RecoveryBudget,canonical_bytes,RecoveryError
    from tests.unit.common.test_failed_fenced_recovery import CLOCK
    from hashlib import sha256
    native=tmp_path/'native-home';redirected=tmp_path/'untrusted-home';redirected.mkdir()
    estate=native/'Library/Application Support/KRONOS/runtime';estate.mkdir(parents=True,mode=0o700)
    store=RecoveryStore(estate)
    scope={'schema':'KRONOS_FAILED_FENCED_GUARD_SCOPE_V1','version':'1.0.0','service':'unit-service','installation':'unit-install','policy':'MANDATORY'}
    store.provision(scope,sha256(canonical_bytes(scope)).hexdigest())
    store.reserve('a'*64,'guard',b'{}')  # actual unresolved/partial canonical guard
    monkeypatch.setenv('HOME',str(redirected))
    monkeypatch.setattr(pwd,'getpwuid',lambda uid:SimpleNamespace(pw_dir=str(native)))
    assert runtime_source_gate.fixed_native_estate()==estate
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    with pytest.raises(RecoveryError,match='guard/slot mismatch'):
        _verify_installation_guards(RecoveryStore(runtime_source_gate.fixed_native_estate()),RecoveryBudget(CLOCK,now,now+15_000_000_000))
    assert list(redirected.iterdir())==[]
    monkeypatch.setattr(os,'geteuid',lambda:os.getuid()+1)
    with pytest.raises(ValueError,match='ACCOUNT_CHANGED'):runtime_source_gate.fixed_native_estate()


@pytest.mark.parametrize('fault',[None,'slash-contract','missing-row','changed-artifact'])
def test_interface_evidence_preserves_closed_scope_and_artifact_authority(tmp_path,fault):
    """Synthetic reviewed rows; real Evidence grammar and pinned-row checks."""
    from kronos.common import failed_fenced_recovery as core
    from kronos.common.failed_fenced_startup import _interface_evidence
    from tests.unit.common.test_failed_fenced_recovery import private_store
    from tests.unit.common.test_failed_fenced_guard_history import slot_case
    store=private_store(tmp_path);case=slot_case(store,'c')
    registry=core.EvidenceRegistry(case.codec,store,case.prep.original)
    approvals=[]
    for owner in ('CA','EA-INTRADAY','EA-SWING','PCP'):
        ref=store.write_blob('synthetic-'+owner,('synthetic exact scope decision '+owner).encode())
        registry.preparation.rows[owner]={'authority':owner,'purpose':'OWNER_SCOPE','artifact':ref,
            'bindings':{'scope':{'hash':core.SCOPE_HASH}}}
        approvals.append(_interface_evidence(owner,ref))
    artifact=store.write_blob('synthetic-reviewed-artifact',b'synthetic exact artifact decision')
    registry.preparation.rows['artifact']={'authority':'CA','purpose':'ARTIFACT','artifact':artifact}
    artifact_evidence=_interface_evidence('CA',artifact)
    assert all(item['contract']==core.PROTOCOL+':'+core.VERSION for item in approvals+[artifact_evidence])
    if fault=='slash-contract':approvals[0]['contract']='KRONOS-FAILED-FENCED-OWNER-SCOPE/1.0.0'
    elif fault=='missing-row':del registry.preparation.rows['CA']
    elif fault=='changed-artifact':approvals[0]=_interface_evidence('CA',artifact)
    if fault:
        with pytest.raises(core.RecoveryError):core._verify_scope_approvals(registry,approvals)
    else:
        core._verify_scope_approvals(registry,approvals)
        assert registry.verify(artifact_evidence,'ARTIFACT_APPROVAL')['payload']['artifact']==artifact
        bad=dict(artifact_evidence,contract='KRONOS-FAILED-FENCED-ARTIFACT-APPROVAL/1.0.0')
        with pytest.raises(core.RecoveryError):registry.verify(bad,'ARTIFACT_APPROVAL')
