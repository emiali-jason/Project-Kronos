from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, UTC, timedelta
import json
import os
from pathlib import Path

import pytest

from kronos.common import legacy_bootstrap as b

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


def binding():
    return b.LegacyBinding(39393, b.LEGACY_REVISION, 'INTRADAY-RUNTIME-'+'a'*64,
        NOW.isoformat(), 'INTRADAY-LAUNCHER-CONFIG-'+'b'*64, '/governed/repository',
        'c'*40, 'd'*64, 'e'*64)


def snapshot(expected=None):
    e = expected or binding()
    return b.LegacySnapshot(e, (e.pid,), False, False, False, False)


def coordinator(tmp_path):
    return b.LegacyBootstrapCoordinator(tmp_path/'bootstrap', binding(), clock=lambda: NOW)


def prepared(tmp_path):
    c = coordinator(tmp_path)
    return c, c.prepare(snapshot(), 'SPONSOR_FUTURE_MIGRATION_001')


def stopped(tmp_path):
    c, ticket = prepared(tmp_path)
    c.shutdown(ticket, snapshot, lambda: None)
    c.stopped(ticket, legacy_alive=False, listener_free=True)
    return c, ticket


def consume(c, ticket, **kwargs):
    options = dict(revision='c'*40, source_state='CLEAN_COMMIT', repository='/governed/repository',
        runtime_identity='f'*64, now=NOW, process_id=999999,
        old_alive=lambda pid: False, port_free=lambda: True)
    options.update(kwargs)
    env = ticket.environment()
    result = b.consume_bootstrap(c.root, env, **options)
    assert env == {}
    return result


def test_ordered_consumption_distinct_from_sph_and_permanent(tmp_path):
    c, ticket = stopped(tmp_path)
    assert consume(c, ticket) == ticket.identity
    record = b._load(c.root, ticket, 'consumed')
    assert record['decommissioned'] and record['legacy_pid'] == 39393
    assert b._load(c.root, ticket, 'prepared')['coordinator_pid'] == os.getpid()
    assert b.SCHEMA != 'KRONOS_MAINTENANCE_HANDOFF_V1'
    with pytest.raises(b.BootstrapError): consume(c, ticket)
    with pytest.raises(b.BootstrapError): c.prepare(snapshot(), 'ANOTHER')


@pytest.mark.parametrize('change', [dict(pid=39394), dict(runtime='INTRADAY-RUNTIME-'+'f'*64),
    dict(startup=(NOW-timedelta(seconds=1)).isoformat()), dict(configuration='INTRADAY-LAUNCHER-CONFIG-'+'f'*64),
    dict(repository='/foreign'), dict(installed_launcher_sha256='f'*64), dict(control_digest='f'*64)])
def test_wrong_legacy_identity_prevents_prepare_and_shutdown(tmp_path, change):
    c = coordinator(tmp_path)
    with pytest.raises(b.BootstrapError): c.prepare(snapshot(replace(binding(), **change)), 'AUTH')
    assert not c.root.exists()


@pytest.mark.parametrize('pids', [(), (123,), (39393, 123)])
def test_listener_ownership_exact(tmp_path, pids):
    with pytest.raises(b.BootstrapError): coordinator(tmp_path).prepare(replace(snapshot(), listener_pids=pids), 'AUTH')


@pytest.mark.parametrize('field', ['authentication_inflight', 'analysis_inflight', 'intraday_inflight',
    'historical_inflight', 'provider_task_inflight', 'browser_control_inflight', 'monitoring_inflight'])
def test_busy_rechecked_before_shutdown(tmp_path, field):
    c, ticket = prepared(tmp_path); calls=[]
    with pytest.raises(b.BootstrapError):
        c.shutdown(ticket, lambda: replace(snapshot(), **{field: True}), lambda: calls.append('shutdown'))
    assert calls == [] and not (c.root/'shutdown-authorized.json').exists()


@pytest.mark.parametrize('delta', [-1, 46])
def test_future_and_stale_context_reject(tmp_path, delta):
    c, ticket = stopped(tmp_path)
    with pytest.raises(b.BootstrapError): consume(c, ticket, now=NOW+timedelta(seconds=delta))


@pytest.mark.parametrize('phase', ['prepared', 'shutdown-authorized', 'stopped'])
def test_tamper_rejected(tmp_path, phase):
    c, ticket = stopped(tmp_path)
    path=c.root/(phase+'.json'); data=json.loads(path.read_bytes())
    data['body']['record']['extra']='tampered'; path.write_text(json.dumps(data))
    with pytest.raises(b.BootstrapError): consume(c, ticket)
    assert not (c.root/'consumed.json').exists()


@pytest.mark.parametrize('mode', [0o644, 0o666, 0o700])
def test_file_permission_rejects(tmp_path, mode):
    c, ticket = stopped(tmp_path); (c.root/'prepared.json').chmod(mode)
    with pytest.raises(b.BootstrapError): consume(c, ticket)


def test_wrong_owner_rejects(tmp_path, monkeypatch):
    c,t=stopped(tmp_path); monkeypatch.setattr(b.os,'getuid',lambda: os.stat(c.root).st_uid+1)
    with pytest.raises(b.BootstrapError): consume(c,t)


@pytest.mark.parametrize('kind', ['file', 'root', 'ancestor', 'traversal'])
def test_symlink_and_traversal_rejection(tmp_path, kind):
    c,t=stopped(tmp_path)
    if kind=='file':
        p=c.root/'prepared.json'; other=tmp_path/'actual'; p.rename(other);p.symlink_to(other)
    elif kind=='root':
        p=tmp_path/'link';p.symlink_to(c.root,target_is_directory=True);c.root=p
    elif kind=='ancestor':
        p=tmp_path/'parent';p.symlink_to(tmp_path,target_is_directory=True);c.root=p/'bootstrap'
    else:c.root=tmp_path/'unused'/'..'/'bootstrap'
    with pytest.raises(b.BootstrapError): consume(c,t)


@pytest.mark.parametrize('change', [dict(revision='a'*40),dict(source_state='DIRTY_WORKTREE'),
    dict(source_state='REVISION_UNAVAILABLE'),dict(repository='/wrong'),dict(process_id=39393),
    dict(process_id=os.getpid()),dict(process_id=0),dict(runtime_identity='wrong'),
    dict(old_alive=lambda pid:True),dict(port_free=lambda:False)])
def test_replacement_binding_fail_closed(tmp_path, change):
    c,t=stopped(tmp_path)
    with pytest.raises(b.BootstrapError): consume(c,t,**change)
    assert not (c.root/'consumed.json').exists()


def test_prepare_failure_cannot_dispatch(tmp_path, monkeypatch):
    c=coordinator(tmp_path); calls=[]
    monkeypatch.setattr(b,'_write',lambda *a: (_ for _ in ()).throw(b.BootstrapError('DISK_FAILURE')))
    with pytest.raises(b.BootstrapError): c.prepare(snapshot(),'AUTH')
    with pytest.raises(b.BootstrapError): c.shutdown(b.Ticket('a'*64,'b'*64),snapshot,lambda:calls.append(1))
    assert calls==[]


def test_consumption_requires_shutdown_and_stopped_proof(tmp_path):
    c,t=prepared(tmp_path)
    with pytest.raises(b.BootstrapError):consume(c,t)
    c.shutdown(t,snapshot,lambda:None)
    with pytest.raises(b.BootstrapError):consume(c,t)


@pytest.mark.parametrize('phase', ['dispatch', 'consume'])
def test_concurrent_use_has_exactly_one_winner(tmp_path, phase):
    c,t=stopped(tmp_path) if phase=='consume' else prepared(tmp_path)
    calls=[]
    def attempt(_):
        try:
            if phase=='consume':return consume(c,t)
            c.shutdown(t,snapshot,lambda:calls.append(1));return True
        except b.BootstrapError:return False
    with ThreadPoolExecutor(8) as pool:results=list(pool.map(attempt,range(8)))
    assert sum(bool(r) for r in results)==1
    assert calls==([1] if phase=='dispatch' else [])


def test_unknown_quiescence_preserved_legacy_notification_not_rewritten(tmp_path):
    c,t=prepared(tmp_path); r=b._load(c.root,t,'prepared')
    assert r['quiescence']['monitoring_inflight'] is None
    assert r['quiescence']['provider_task_inflight'] is None
    assert r['risk']=='LEGACY_SHUTDOWN_SIDE_EFFECT_RISK'
    assert r['notification_policy']=='EXPECTED_LEGACY_BOOTSTRAP_NOTIFICATION_SIDE_EFFECT'
    assert 'EXPECTED_MAINTENANCE_DISCONNECT_V1' not in (c.root/'prepared.json').read_text()
    assert t.proof not in repr(t) and t.proof not in (c.root/'prepared.json').read_text()


def test_empty_context_normal_start_and_mixed_context_fail_closed(tmp_path):
    assert b.consume_startup_context(tmp_path,{},revision='c'*40,source_state='CLEAN_COMMIT',
        repository='/governed/repository',runtime_identity='f'*64,now=NOW) is None
    c,t=prepared(tmp_path);env=t.environment();env['KRONOS_MAINTENANCE_PARENT']='39393'
    with pytest.raises(b.BootstrapError,match='MIXED'):
        b.consume_startup_context(tmp_path,env,revision='c'*40,source_state='CLEAN_COMMIT',
            repository='/governed/repository',runtime_identity='f'*64,now=NOW)


def test_consumed_context_composes_existing_guard_without_provider_restoration(tmp_path):
    from tests.unit.application.test_sph_maintenance import composed
    from kronos.application.swing_opportunities import ProviderConnectionState
    from kronos.provider.runtime import SharedProviderRuntimeLifecycle
    from kronos.common.connection_governance import ConnectionGovernanceError
    c,t=stopped(tmp_path); migration=consume(c,t)
    g,shared,app,p,calls=composed(tmp_path/'replacement',maintenance=migration)
    restored=[];app.register_sponsor_operability_restorer(restored.append)
    assert app.snapshot().provider_state is ProviderConnectionState.DISCONNECTED
    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.ABSENT
    assert not app.connect_provider()
    with pytest.raises(ConnectionGovernanceError):shared.begin_login()
    assert calls==[] and p.begin_count==0 and restored==[] and shared.active_lease_count==0
    assert g.maintenance_active


@pytest.mark.parametrize('mode', ['LEGACY_BOOTSTRAP','UNKNOWN','PACKAGE_VERIFY'])
def test_python_startup_mode_cannot_fall_back_without_context(tmp_path, mode):
    with pytest.raises(b.BootstrapError,match='MODE_CONTEXT'):
        b.consume_startup_context(tmp_path,{'KRONOS_LAUNCH_MODE':mode},revision='c'*40,
            source_state='CLEAN_COMMIT',repository='/governed/repository',runtime_identity='f'*64,now=NOW)


def test_expiry_during_pre_shutdown_recheck_leaves_old_runtime_running(tmp_path):
    c,t=prepared(tmp_path);calls=[]
    def slow_observe():
        c.clock=lambda: NOW+timedelta(seconds=46)
        return snapshot()
    with pytest.raises(b.BootstrapError,match='STALE'):
        c.shutdown(t,slow_observe,lambda:calls.append('stop'))
    assert calls==[] and not (c.root/'shutdown-authorized.json').exists()


def test_expiry_during_durable_authorization_does_not_dispatch(tmp_path,monkeypatch):
    c,t=prepared(tmp_path);calls=[];original=b._write
    def delayed_write(*args):
        original(*args);c.clock=lambda: NOW+timedelta(seconds=46)
    monkeypatch.setattr(b,'_write',delayed_write)
    with pytest.raises(b.BootstrapError,match='STALE'):
        c.shutdown(t,snapshot,lambda:calls.append('stop'))
    assert calls==[] and (c.root/'shutdown-authorized.json').exists()
