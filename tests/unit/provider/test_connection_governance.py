from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path

import pytest

from kronos.common.connection_governance import (
    ConnectionAuditStore, ConnectionGovernance, ConnectionGovernanceError,
    ConnectionProcess, ConnectionRequest, immutable_write,
)
from kronos.common.maintenance import consume_handoff, publish_handoff

NOW = datetime(2026, 9, 8, 10, tzinfo=UTC)
GENERATION = "c" * 64
PROOF = "b" * 64


def governance(tmp_path, *, maintenance=None, clock=lambda: NOW):
    return ConnectionGovernance(ConnectionProcess(os.getpid(), NOW.isoformat(),
        "a" * 64, "d" * 40, "CLEAN_COMMIT"), ConnectionAuditStore(tmp_path / "audit"),
        maintenance_identity=maintenance, clock=clock)


def environment():
    return dict(KRONOS_MAINTENANCE_GENERATION=GENERATION,
        KRONOS_MAINTENANCE_PARENT=str(os.getpid()), KRONOS_MAINTENANCE_PROOF=PROOF)


def handoff(tmp_path):
    publish_handoff(tmp_path / "maintenance", generation=GENERATION,
        parent_pid=os.getpid(), proof=PROOF, runtime_identity="a" * 64, now=NOW)


@pytest.mark.parametrize("surface", [None, "HEADER", "SETTINGS"])
def test_durable_request_precedes_dispatch_without_claiming_human(tmp_path, surface):
    g = governance(tmp_path)
    r = g.request(reference=g.action_reference(surface) if surface else None)
    retained = g.store.read(r.connection_request_id)
    assert retained['request']['trigger'] == 'LOCAL_HTTP_UNATTRIBUTED'
    assert retained['request']['surface'] == surface
    assert retained['request']['process']['pid'] == os.getpid()
    assert retained['request']['process']['loaded_revision'] == 'd' * 40
    assert set(retained) == {'request'}
    assert g.admit(r)
    with g.dispatch(r): g.require_authentication()
    g.finish(r, True)
    rows = g.store.read(r.connection_request_id)
    assert [rows[k]['state'] for k in ('admission','dispatch','completion')] == ['ACCEPTED','UNFINISHED','SUCCESS']
    assert len({rows[k]['request_integrity'] for k in ('admission','dispatch','completion')}) == 1


@pytest.mark.parametrize('reference', ['', '127.0.0.1', 'HEADER', 'SPONSOR_EXPLICIT', 'f' * 64])
def test_unproven_surface_is_unattributed(tmp_path, reference):
    r = governance(tmp_path).request(reference=reference)
    assert r.trigger == 'LOCAL_HTTP_UNATTRIBUTED' and r.surface is None


def test_process_specific_surface_cannot_replay(tmp_path):
    a, b = governance(tmp_path/'a'), governance(tmp_path/'b')
    assert b.surface(a.action_reference('HEADER')) is None


@pytest.mark.parametrize('state', ['SUCCESS','FAILURE'])
def test_results_idempotent_conflict_rejected(tmp_path, state):
    g=governance(tmp_path); r=g.request(); assert g.admit(r)
    g.result(r,'completion',state)
    before={p:p.read_bytes() for p in (tmp_path/'audit').rglob('*.json')}
    g.result(r,'completion',state)
    assert before=={p:p.read_bytes() for p in before}
    with pytest.raises(ConnectionGovernanceError,match='CONFLICT'):
        g.result(r,'completion','FAILURE' if state=='SUCCESS' else 'SUCCESS')


def test_accepted_dispatch_unfinished_after_restore(tmp_path):
    g=governance(tmp_path);r=g.request();g.admit(r)
    restored=ConnectionAuditStore(g.store.root).read(r.connection_request_id)
    assert restored['dispatch']['state']=='UNFINISHED'
    assert 'completion' not in restored


def test_already_connected_creates_no_dispatch(tmp_path):
    g=governance(tmp_path);r=g.request()
    assert not g.admit(r,already_connected=True)
    assert g.store.read(r.connection_request_id)['admission']['state']=='ALREADY_CONNECTED'
    assert 'dispatch' not in g.store.read(r.connection_request_id)


def test_maintenance_rejects_and_requires_explicit_exit(tmp_path):
    g=governance(tmp_path,maintenance=GENERATION);r=g.request()
    assert not g.admit(r)
    assert g.store.read(r.connection_request_id)['admission']['state']=='REJECTED'
    assert not g.exit_maintenance('HEADER')
    assert not g.exit_maintenance(g.action_reference('HEADER'))
    assert g.exit_maintenance(g.action_reference('MAINTENANCE_EXIT'))
    assert g.exit_maintenance(g.action_reference('MAINTENANCE_EXIT'))
    assert g.admit(g.request())


def test_inflight_attempt_cancelled_and_not_republished(tmp_path):
    g=governance(tmp_path);r=g.request();g.admit(r)
    with g.dispatch(r):
        g.enter_maintenance(GENERATION)
        with pytest.raises(ConnectionGovernanceError):g.require_authentication()
    g.finish(r,True)
    assert g.store.read(r.connection_request_id)['completion']['state']=='UNFINISHED'
    assert not g.exit_maintenance(g.action_reference('MAINTENANCE_EXIT'))
    g.enter_maintenance(GENERATION)
    with pytest.raises(ConnectionGovernanceError):g.enter_maintenance('e'*64)


def test_direct_shared_api_is_rejected_and_audited(tmp_path):
    g=governance(tmp_path)
    with pytest.raises(ConnectionGovernanceError):g.require_authentication()
    identity=next(g.store.root.iterdir()).name
    rows=g.store.read(identity)
    assert rows['request']['route']=='SHARED_PROVIDER_API'
    assert rows['request']['trigger']=='UNATTRIBUTED_API'
    assert rows['admission']['state']=='REJECTED'


def test_foreign_or_unissued_request_not_authority(tmp_path):
    a,b=governance(tmp_path/'a'),governance(tmp_path/'b')
    with pytest.raises(ConnectionGovernanceError):b.admit(a.request())


def test_completed_request_cannot_initiate_second_attempt(tmp_path):
    g=governance(tmp_path);r=g.request();g.admit(r);g.finish(r,True)
    assert not g.admit(r)
    with pytest.raises(ConnectionGovernanceError):
        with g.dispatch(r):pass


def test_audit_write_failure_prevents_admission(tmp_path,monkeypatch):
    g=governance(tmp_path)
    def fail(*args):raise OSError('offline storage failure')
    monkeypatch.setattr(g.store,'request',fail)
    with pytest.raises(OSError):g.request()
    assert not g._pending


def test_immutable_bytes_and_integrity_rejection(tmp_path):
    path=tmp_path/'immutable.json';immutable_write(path,{'value':1})
    immutable_write(path,{'value':1})
    with pytest.raises(ConnectionGovernanceError):immutable_write(path,{'value':2})
    g=governance(tmp_path);r=g.request()
    path=g.store.root/r.connection_request_id/'request.json'
    value=json.loads(path.read_bytes());value['record']['provider_identity']='OTHER'
    path.write_text(json.dumps(value))
    with pytest.raises(ConnectionGovernanceError):g.store.read(r.connection_request_id)


@pytest.mark.parametrize('ancestor', [False, True])
def test_symlink_evidence_path_rejected(tmp_path,ancestor):
    target=tmp_path/'target';target.mkdir()
    (tmp_path/'alias').symlink_to(target,target_is_directory=True)
    root=tmp_path/'alias'/'nested' if ancestor else tmp_path/'alias'
    with pytest.raises(ConnectionGovernanceError):immutable_write(root/'record.json',{})


def test_no_raw_credentials_exception_or_body_field(tmp_path):
    g=governance(tmp_path)
    secret='token=DO_NOT_RETAIN_PASSWORD'
    r=g.request(reference=secret);g.admit(r);g.finish(r,False)
    assert all(secret.encode() not in p.read_bytes() for p in g.store.root.rglob('*.json'))
    with pytest.raises(TypeError):g.request(body=secret)
    with pytest.raises(ConnectionGovernanceError):replace(r,provider_identity=secret)


def test_handoff_signed_one_use_generation_and_environment_consumed(tmp_path):
    handoff(tmp_path);env=environment()
    actual=consume_handoff(tmp_path/'maintenance',env,runtime_identity='e'*64,
        now=NOW+timedelta(seconds=1),process_id=os.getpid()+1)
    assert actual==GENERATION and env=={}
    with pytest.raises(ConnectionGovernanceError):consume_handoff(tmp_path/'maintenance',environment(),
        runtime_identity='f'*64,now=NOW+timedelta(seconds=2),process_id=os.getpid()+2)


@pytest.mark.parametrize('fault', ['stale','future','same_process','wrong_parent','wrong_proof','tampered','missing','symlink'])
def test_handoff_fails_closed(tmp_path,fault):
    handoff(tmp_path);env=environment();now=NOW;pid=os.getpid()+1
    source=tmp_path/'maintenance'/f'{GENERATION}.json'
    if fault=='stale':now+=timedelta(seconds=46)
    elif fault=='future':now-=timedelta(microseconds=1)
    elif fault=='same_process':pid=os.getpid()
    elif fault=='wrong_parent':env['KRONOS_MAINTENANCE_PARENT']='9999999'
    elif fault=='wrong_proof':env['KRONOS_MAINTENANCE_PROOF']='e'*64
    elif fault=='tampered':
        v=json.loads(source.read_bytes());v['record']['runtime_identity']='f'*64;source.write_text(json.dumps(v))
    elif fault=='missing':source.unlink()
    elif fault=='symlink':
        other=source.with_suffix('.other');source.rename(other);source.symlink_to(other)
    with pytest.raises(ConnectionGovernanceError):consume_handoff(tmp_path/'maintenance',env,
        runtime_identity='e'*64,now=now,process_id=pid)


def test_normal_startup_has_no_handoff_or_evidence(tmp_path):
    assert consume_handoff(tmp_path/'absent',{},runtime_identity='a'*64,now=NOW) is None
    assert list(tmp_path.iterdir())==[]


def test_foreign_process_cannot_mint_maintenance(tmp_path):
    with pytest.raises(ConnectionGovernanceError):publish_handoff(tmp_path,generation=GENERATION,
        parent_pid=os.getpid()+1,proof=PROOF,runtime_identity='a'*64,now=NOW)


@pytest.mark.parametrize('field,value',[('loaded_revision',None),('runtime_identity','not-an-identity'),('source_state','UNKNOWN')])
def test_runtime_reference_fails_closed(tmp_path,field,value):
    process=governance(tmp_path).process
    with pytest.raises(ConnectionGovernanceError):replace(process,**{field:value})


def test_normal_startup_is_inert_even_when_old_fixture_context_expired(tmp_path):
    from tests.unit.provider.test_shared_provider_runtime import _Runtime, NOW as PROVIDER_NOW
    from kronos.provider.models.authentication import AuthenticatedContextState
    from kronos.provider.runtime import SharedAuthenticatedProviderRuntime, SharedProviderRuntimeLifecycle
    provider=_Runtime();provider.context_state=AuthenticatedContextState.EXPIRED
    calls=[]
    def factory():calls.append(1);return provider
    runtime=SharedAuthenticatedProviderRuntime(factory,provider_identity='KITE',
        clock=lambda:PROVIDER_NOW,connection_governance=governance(tmp_path,maintenance=GENERATION))
    assert runtime.lifecycle_state is SharedProviderRuntimeLifecycle.ABSENT
    assert calls==[] and provider.begin_count==0
    assert provider.context_state is AuthenticatedContextState.EXPIRED
