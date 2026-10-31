from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, UTC, timedelta
import json
import os
from pathlib import Path
import plistlib
import subprocess

import pytest

from kronos.common import legacy_bootstrap as b

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


@pytest.mark.parametrize('boundary',('before-claim','after-claim'))
def test_s305_partial_setup_fences_actual_restoration(tmp_path,monkeypatch,record_property,boundary):
    import shutil
    from hashlib import sha256
    control=_c02_dispatch_case(tmp_path,monkeypatch);case=control['case']
    monkeypatch.setattr(b,'_verify_bundle_signature',lambda *_:None)
    budget=case.custody.budget;deadline=budget.deadline_ns
    evidence=Path(__file__).resolve().parents[4]/'qualification/s305-restoration-boundaries'/tmp_path.parents[1].name/tmp_path.name
    evidence.mkdir(parents=True)
    original_claim=None;returned=False
    try:
        if boundary=='after-claim':
            context,observation,attempt=_c03_consume(control,monkeypatch)
            original_claim=case.claim_path.read_bytes()
        (case.custody.binding.path/'controlled-setup-v1').mkdir(mode=0o700)
        with pytest.raises(b.BootstrapError,match='RESTORATION'):
            if boundary=='before-claim':
                capture=_c02_capture(control)
                b.consume_startup_context(case.root,control['env'],revision=control['target']['revision'],
                    source_state='CLEAN_COMMIT',repository=control['repository'],runtime_identity=case.child.runtime_identity,
                    now=case.now,custody=case.custody,restoration_observation=capture,restoration_clock=lambda:case.now)
            else:
                b.revalidate_restoration_context(control['env'],context=context,custody=case.custody,
                    child=observation.child,repository=control['repository'],now=case.now,
                    attempt=attempt,clock=lambda:case.now)
            returned=True
        assert not returned and case.custody.budget is budget and budget.deadline_ns==deadline
        if original_claim is None:assert not case.claim_path.exists()
        else:assert case.claim_path.read_bytes()==original_claim
    finally:
        shutil.copytree(case.root,evidence/'original-fixture',symlinks=True)
        (evidence/'application.json').write_text(json.dumps(dict(boundary=boundary,returned=returned,
            original_deadline_ns=deadline,final_deadline_ns=budget.deadline_ns,same_budget=case.custody.budget is budget,
            claim_exists=case.claim_path.exists(),claim_sha256=sha256(case.claim_path.read_bytes()).hexdigest() if case.claim_path.exists() else None,
            original_claim_sha256=sha256(original_claim).hexdigest() if original_claim is not None else None,
            seams='SYNTHETIC AUTHORITY/SIGNATURE/PARENT IMAGE; EXPLICIT FIXTURE UTC; ACTUAL CONSUMER/CUSTODY/BUDGET/CLAIM; NO APPLICATION OWNER'),indent=2))
        case.close()
        (evidence/'fixture-teardown.json').write_text(json.dumps(dict(custody_closed=case.custody.released,
            claims_removed=False,application_cleanup_claimed=False),indent=2))
        record_property('application_before_fixture_teardown','ACTUAL RESTORATION DENIED; PRE-CLAIM ABSENT OR POST-CLAIM PERMANENTLY SPENT; ORIGINAL BUDGET')


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


def test_restoration_selector_is_exclusive_and_never_falls_back(tmp_path, monkeypatch):
    calls = []
    from kronos.common import maintenance
    monkeypatch.setattr(maintenance, 'consume_handoff', lambda *args, **kwargs: calls.append(True))
    env = {
        'KRONOS_LAUNCH_MODE': b.RESTORATION_MODE,
        'KRONOS_RESTORATION_PERMIT_PATH': str(tmp_path / 'permit.json'),
    }
    with pytest.raises(b.BootstrapError, match='RESTORATION_SELECTOR_INVALID'):
        b.consume_startup_context(tmp_path, env, revision='c' * 40,
            source_state='CLEAN_COMMIT', repository='/governed/repository',
            runtime_identity='f' * 64, now=NOW)
    assert calls == []


def test_restoration_rejection_does_not_fall_back_to_v2(tmp_path, monkeypatch):
    calls = []
    from kronos.common import maintenance
    monkeypatch.setattr(maintenance, 'consume_handoff', lambda *args, **kwargs: calls.append(True))
    env = {'KRONOS_LAUNCH_MODE': b.RESTORATION_MODE}
    env.update({
        'KRONOS_RESTORATION_ORIGINAL_ATTEMPT_ID': 'attempt',
        'KRONOS_RESTORATION_PERMIT_PATH': str(tmp_path / 'permit.json'),
        'KRONOS_RESTORATION_PERMIT_BYTES': '1',
        'KRONOS_RESTORATION_PERMIT_SHA256': 'a' * 64,
        'KRONOS_RESTORATION_PERMIT_ID': 'permit',
        'KRONOS_RESTORATION_RESERVATION_PATH': str(tmp_path / 'reservation.json'),
        'KRONOS_RESTORATION_RESERVATION_BYTES': '1',
        'KRONOS_RESTORATION_RESERVATION_SHA256': 'b' * 64,
        'KRONOS_RESTORATION_RESERVATION_ID': 'reservation',
    })
    for name in b.RESTORATION_CHILD_ENV:
        env[name] = 'x' * 64
    env.update(KRONOS_MAINTENANCE_PROTOCOL='V2', KRONOS_MAINTENANCE_REVISION='f' * 40)
    with pytest.raises(b.BootstrapError, match='MIXED_PROTOCOLS'):
        b.consume_startup_context(tmp_path, env, revision='c' * 40,
            source_state='CLEAN_COMMIT', repository='/governed/repository',
            runtime_identity='f' * 64, now=NOW)
    assert calls == []




def _c02_kernel_birth(pid):
    observed = b._observe_process(pid)
    return observed['kernel_birth'], observed


def test_c02_kernel_birth_serialization_vectors():
    assert b._kernel_birth_digest(1, 0) == '6cce36d9f8a9e151b100234af75cca89d55bcb94c153f51847debdf1f39cae45'
    assert b._kernel_birth_digest(1700000000, 123456) == 'c24117bebdd26877357cf322d6dc58d5b5d4f1aa16ae24cf0e1caf09f2bf695d'
    for seconds, microseconds in ((0, 0), (1, -1), (1, 1000000)):
        with pytest.raises(b.BootstrapError, match='PROCESS_IDENTITY'):
            b._kernel_birth_digest(seconds, microseconds)


def _c02_run(repository, *arguments):
    return subprocess.run(arguments, cwd=repository, check=True,
                          capture_output=True).stdout.decode().strip()


def _c02_bundle_manifest(bundle):
    from hashlib import sha256
    rows = []
    for path in sorted(bundle.rglob('*')):
        relative = path.relative_to(bundle).as_posix()
        rows.append({'path': relative,
            'mode': 0o755 if path.is_dir() or relative == 'Contents/MacOS/KRONOS' else 0o644,
            'sha256': sha256(path.read_bytes()).hexdigest() if path.is_file() else None})
    return rows


@pytest.mark.parametrize('finding',('status-only','pid-revision-hash','missing-evidence'))
def test_s304_enrollment_never_manufactures_loaded_evidence(tmp_path,monkeypatch,record_property,finding):
    from tests.unit.common import test_failed_successor_restore as fixture
    from hashlib import sha256
    case=fixture._make_case(tmp_path)
    try:
        path=case.root/'s304-existing-evidence.json'
        value={'status':'READY','pid':os.getpid(),'revision':'a'*40}
        if finding=='pid-revision-hash':
            value['runtime_identity']=sha256(b'PID AND REVISION ARE NOT STARTUP EVIDENCE').hexdigest()
        raw=fixture._put(path,value);ref=fixture._ref(path,'existing-evidence',raw)
        if finding=='missing-evidence':path.unlink()
        budget=case.custody.budget;deadline=budget.deadline_ns
        with pytest.raises((b.BootstrapError,ValueError,KeyError,OSError)):
            b._native_initialization_enrollment(ref,case.custody,
                installation=json.loads(case.permit_path.read_bytes())['installation'])
        assert case.custody.budget is budget and budget.deadline_ns==deadline
        assert not case.claim_path.exists() and not case.custody.released
        record_property('s304_enrollment_outcome','DENIED; no manufactured identity, claim or runtime; fixture closes custody separately')
    finally:case.close()


def _c02_refresh(case, env, *, source_manifest, artifact_manifest,
                 target_values, parent_birth):
    from hashlib import sha256
    from tests.unit.common import test_failed_successor_restore as fixture
    target = dict(target_values,
        source_manifest_sha256=sha256(source_manifest.read_bytes()).hexdigest(),
        artifact_manifest_sha256=sha256(artifact_manifest.read_bytes()).hexdigest())
    permit = json.loads(case.permit_path.read_bytes())
    permit['restoration_target'] = target
    fixture._put(case.permit_path, permit)
    permit_selection = replace(case.selected_permit,
        byte_size=case.permit_path.stat().st_size,
        sha256=sha256(case.permit_path.read_bytes()).hexdigest())
    reservation = json.loads(case.reservation_path.read_bytes())
    reservation['parent']['kernel_birth'] = parent_birth
    reservation['restoration_target'] = target
    reservation['permit_sha256'] = permit_selection.sha256
    fixture._put(case.reservation_path, reservation)
    reservation_selection = replace(case.selected_reservation,
        byte_size=case.reservation_path.stat().st_size,
        sha256=sha256(case.reservation_path.read_bytes()).hexdigest())
    head = json.loads(case.head_path.read_bytes())
    head['active_reservation_sha256'] = reservation_selection.sha256
    fixture._put(case.head_path, head)
    fixture._s304_admit_fixture(case.head_path.parent,permit['installation'])
    env.update(KRONOS_RESTORATION_PERMIT_BYTES=str(permit_selection.byte_size),
        KRONOS_RESTORATION_PERMIT_SHA256=permit_selection.sha256,
        KRONOS_RESTORATION_RESERVATION_BYTES=str(reservation_selection.byte_size),
        KRONOS_RESTORATION_RESERVATION_SHA256=reservation_selection.sha256)
    return permit_selection, reservation_selection


def _c02_dispatch_case(tmp_path, monkeypatch, *, object_format='sha1',
                       missing_resource=None):
    """One coherent control with actual Git/capture/bundle bytes and fixture seams."""
    from hashlib import sha256
    from kronos.common.release_admission import ValidationBudget, monotonic_ns
    from kronos.intraday.runtime_identity import StartupCapture
    from tests.unit.common import test_failed_successor_restore as fixture
    budget = ValidationBudget(monotonic_ns() + 120_000_000_000)
    from kronos.common import release_admission as admission
    fixture_root = (tmp_path / 'c02').resolve() / fixture._h(str(tmp_path / 'c02'))[:12]
    initial_image = str(fixture_root / 'fixture-KRONOS.app/Contents/MacOS/KRONOS')
    monkeypatch.setattr(admission, 'CANONICAL_PARENT', initial_image)
    case = fixture._make_case(tmp_path / 'c02', budget=budget,parent_image=lambda _pid:initial_image)
    child_birth, child_observed = _c02_kernel_birth(os.getpid())
    parent_birth, parent_observed = _c02_kernel_birth(os.getppid())
    repository = Path(json.loads(case.permit_path.read_bytes())['installation']['repository_path'])
    repository.mkdir(mode=0o700)
    # These are the actual retained template bytes. Ordinary controls copy them
    # from the selected disposable Git tree just as package_launcher.build does.
    template = Path(__file__).resolve().parents[3] / 'tools/macos/KRONOS.app'
    resource_bytes = {relative: (template / relative).read_bytes() for relative in (
        'Contents/Info.plist', 'Contents/Resources/KRONOS.icns',
        'Contents/Resources/KRONOS.png')}
    source_files = {
        'src/kronos/__init__.py': b'',
        'src/kronos/probe.py': b'VALUE = 1\n',
        'tools/__init__.py': b'',
        'tools/macos/__init__.py': b'',
        'tools/macos/package_launcher.py': b'PACKAGE_FIXTURE = 1\n',
        'tools/macos/kronos_launcher.c': b'int main(void) { return 0; }\n',
        'tools/macos/KRONOS.app/Contents/MacOS/KRONOS': b'prior-binary\n',
        'README.md': b'fixture repository\n',
    }
    source_files.update({'tools/macos/KRONOS.app/' + relative: raw
                         for relative, raw in resource_bytes.items()
                         if relative != missing_resource})
    for relative, raw in source_files.items():
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o755 if relative.endswith('/KRONOS') else 0o644)
    _c02_run(repository, '/usr/bin/git', 'init', '-q',
             '--object-format=' + object_format)
    assert _c02_run(repository, '/usr/bin/git', 'rev-parse',
                    '--show-object-format=storage') == object_format
    _c02_run(repository, '/usr/bin/git', 'checkout', '-q', '-b',
               'maintenance/release-b-swing-ux')
    _c02_run(repository, '/usr/bin/git', 'remote', 'add', 'origin',
               'git@github.com:imran/Project-Kronos.git')
    _c02_run(repository, '/usr/bin/git', 'add', '--all')
    _c02_run(repository, '/usr/bin/git', '-c', 'user.name=KRONOS Fixture',
               '-c', 'user.email=fixture@example.invalid', 'commit', '-q', '-m', 'fixture')
    revision = _c02_run(repository, '/usr/bin/git', 'rev-parse', 'HEAD')
    tree_oid = _c02_run(repository, '/usr/bin/git', 'rev-parse', 'HEAD^{tree}')
    tracked = []
    for raw in subprocess.run(['/usr/bin/git', 'ls-files', '-s', '-z'], cwd=repository,
                              check=True, capture_output=True).stdout.split(b'\0'):
        if not raw:
            continue
        metadata, encoded = raw.split(b'\t', 1)
        mode = metadata.split(b' ', 1)[0].decode()
        relative = encoded.decode()
        tracked.append({'path': relative, 'mode': mode,
                        'sha256': sha256((repository / relative).read_bytes()).hexdigest()})
    tracked.sort(key=lambda row: row['path'])
    capture = StartupCapture(repository)
    captured_sources = tuple(sorted(
        (name, Path(item[0]).relative_to(repository).as_posix(),
         sha256(item[1]).hexdigest()) for name, item in capture._sources.items()))
    capture_rows = [dict(module=name, path=path, sha256=digest)
                    for name, path, digest in captured_sources]
    pinned_digest = sha256(b._canonical([[row['module'], row['sha256']]
                                         for row in capture_rows])).hexdigest()
    source_document = {'schema': 'KRONOS_RESTORATION_SOURCE_MANIFEST_V1',
        'origin_url': 'git@github.com:imran/Project-Kronos.git',
        'source_ref': 'refs/heads/maintenance/release-b-swing-ux',
        'revision': revision, 'git_tree_oid': tree_oid,
        'files': tracked, 'capture': capture_rows}
    source_manifest = case.root / 'source-manifest.json'
    source_manifest.write_bytes(b._canonical(source_document)); source_manifest.chmod(0o600)

    bundle = Path(json.loads(case.permit_path.read_bytes())['installation']['bundle_path'])
    for relative, raw in {
        'Contents/MacOS/KRONOS': b'signed-fixture-binary\n',
        'Contents/_CodeSignature/CodeResources': b'fixture-signature-seam\n',
    }.items():
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    import shutil
    for relative, raw in resource_bytes.items():
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == missing_resource:
            # Negative fixture only: installed bytes exist, but this selected
            # Git tree genuinely lacks the required source mapping.
            path.write_bytes(raw)
        else:
            shutil.copyfile(repository / 'tools/macos/KRONOS.app' / relative, path)
    bundle.chmod(0o755)
    for path in bundle.rglob('*'):
        path.chmod(0o755 if path.is_dir()
                   or path.relative_to(bundle).as_posix() == 'Contents/MacOS/KRONOS'
                   else 0o644)
    bundle_rows = _c02_bundle_manifest(bundle)
    binary_digest = sha256((bundle / 'Contents/MacOS/KRONOS').read_bytes()).hexdigest()
    file_map = {row['path']: row['sha256'] for row in tracked}
    artifact_document = {'schema': 'KRONOS_LAUNCHER_PACKAGE_V1',
        'source_revision': revision, 'source_state': 'CLEAN_COMMIT',
        'source_launcher_sha256': file_map['tools/macos/kronos_launcher.c'],
        'previous_tracked_binary_sha256': file_map['tools/macos/KRONOS.app/Contents/MacOS/KRONOS'],
        'built_binary_sha256': binary_digest, 'signed_binary_sha256': binary_digest,
        'procedure_sha256': file_map['tools/macos/package_launcher.py'],
        'compiler_flags': ['-Wall', '-Wextra', '-Werror', '-O2', '-mmacosx-version-min=13.0'],
        'compiler': 'fixture compiler seam; no production build',
        'signing': 'AD_HOC; timestamp=none; no entitlements; resources sealed',
        'strict_verification': 'PASS', 'isolated_execution': 'PASS',
        'bundle_identity': sha256(b._canonical(bundle_rows)).hexdigest(),
        'bundle_manifest': bundle_rows, 'archive_sha256': sha256(b'fixture archive').hexdigest()}
    artifact_manifest = case.root / 'artifact-manifest.json'
    artifact_manifest.write_bytes(b._canonical(artifact_document) + b'\n')
    artifact_manifest.chmod(0o600)
    target = {'revision': revision,
        'tree_sha256': sha256(b._canonical(tracked)).hexdigest(),
        'pinned_capture_sha256': pinned_digest,
        'origin_url': source_document['origin_url'], 'source_ref': source_document['source_ref']}
    env = dict(KRONOS_LAUNCH_MODE=b.RESTORATION_MODE,
        KRONOS_RESTORATION_ORIGINAL_ATTEMPT_ID=json.loads(case.incident_path.read_bytes())['original_attempt_id'],
        KRONOS_RESTORATION_PERMIT_PATH=str(case.selected_permit.path),
        KRONOS_RESTORATION_PERMIT_ID=case.selected_permit.permit_id,
        KRONOS_RESTORATION_RESERVATION_PATH=str(case.selected_reservation.path),
        KRONOS_RESTORATION_RESERVATION_ID=case.selected_reservation.reservation_id,
        KRONOS_RESTORATION_PARENT_KERNEL_BIRTH=parent_birth,
        KRONOS_RESTORATION_CHILD_KERNEL_BIRTH=child_birth,
        KRONOS_RESTORATION_SOURCE_MANIFEST_PATH=str(source_manifest),
        KRONOS_RESTORATION_ARTIFACT_MANIFEST_PATH=str(artifact_manifest))
    permit_selection, reservation_selection = _c02_refresh(case, env,
        source_manifest=source_manifest, artifact_manifest=artifact_manifest,
        target_values=target, parent_birth=parent_birth)
    # Test-only canonical location and parent-image observation: no installation
    # or native execution. The actual AdmissionCustody and comparison stay real.
    from kronos.common import release_admission as admission
    canonical_image = str(bundle / 'Contents/MacOS/KRONOS')
    monkeypatch.setattr(admission, 'CANONICAL_PARENT', canonical_image)
    parent_image = {'value': canonical_image, 'error': False, 'calls': [],
                    'actual_kernel_image': admission._parent_image(os.getppid())}
    def observed_image(pid):
        assert pid == os.getppid() == case.custody.parent
        parent_image['calls'].append({'pid': pid, 'value': parent_image['value'],
                                      'error': parent_image['error']})
        if parent_image['error']:
            raise OSError('F02_FIXTURE_PARENT_IMAGE_QUERY_FAILED')
        return parent_image['value']
    case.custody.parent_image = observed_image
    return dict(case=case, env=env, repository=repository, bundle=bundle,
        startup_capture=capture,
        parent_image=parent_image, canonical_image=canonical_image,
        source_manifest=source_manifest, artifact_manifest=artifact_manifest,
        source_document=source_document, artifact_document=artifact_document,
        target=target, captured_sources=captured_sources,
        loaded_modules=(), pinned_digest=pinned_digest,
        observed={'child': child_observed, 'parent': parent_observed},
        permit_selection=permit_selection, reservation_selection=reservation_selection,
        signature_fixture='TEST_ONLY; actual bundle roster/bytes/modes still verified')


def _c02_capture(control, **changes):
    return b.capture_restoration_child(control['env'], custody=control['case'].custody,
        process_id=os.getpid(), parent_pid=os.getppid(),
        runtime_identity=control['case'].child.runtime_identity,
        loaded_revision=control['target']['revision'],
        pinned_capture_sha256=control['pinned_digest'],
        repository=changes.get('repository', control['repository']),
        captured_sources=changes.get('captured_sources', control['captured_sources']),
        loaded_modules=control['loaded_modules'],
        load_verification=changes.get('load_verification', 'PINNED_STARTUP_IMPORTS'))


@pytest.mark.parametrize('object_format', ('sha1', 'sha256'))
def test_restoration_dispatch_consumes_actual_r31_context(
        tmp_path, monkeypatch, record_property, object_format):
    from hashlib import sha256
    from kronos.common.failed_successor_restore import RestorationStartupContext
    from kronos.common.release_admission import ValidationBudget
    control = _c02_dispatch_case(tmp_path, monkeypatch, object_format=object_format)
    case = control['case']
    preserved = {path: path.read_bytes() for path in (
        case.incident_path, case.failure_path, case.settled_path,
        case.original_v2_path, case.retained_path)}
    expected_checkpoint = dict(json.loads(preserved[case.settled_path])['notification_checkpoint'])
    original_budget = case.custody.budget
    assert type(original_budget) is ValidationBudget
    deadline = original_budget.deadline_ns
    try:
        monkeypatch.setattr(b, '_verify_bundle_signature',
                            lambda _bundle, _custody, _identity: None)
        observation = _c02_capture(control)
        context = b.consume_startup_context(case.root, control['env'],
            revision=control['target']['revision'], source_state='CLEAN_COMMIT',
            repository=control['repository'], runtime_identity=case.child.runtime_identity,
            now=case.now, custody=case.custody,
            restoration_observation=observation,
            restoration_clock=lambda: case.now)
        assert type(context) is RestorationStartupContext
        assert context.notification_checkpoint() == expected_checkpoint
        assert case.claim_path.is_file()
        claim = json.loads(case.claim_path.read_bytes())
        selected_parent = json.loads(case.reservation_path.read_bytes())['parent']
        assert claim['parent'] == selected_parent
        assert claim['child']['pid'] == os.getpid()
        assert claim['permit_sha256'] == control['permit_selection'].sha256
        assert claim['reservation_sha256'] == control['reservation_selection'].sha256
        assert claim['claimed_at'] == case.now.isoformat()
        assert case.custody.budget is original_budget
        assert original_budget.deadline_ns == deadline and not case.custody.released
        assert all(path.read_bytes() == raw for path, raw in preserved.items())
        for relative in ('Contents/Info.plist', 'Contents/Resources/KRONOS.icns',
                         'Contents/Resources/KRONOS.png'):
            source = control['repository'] / 'tools/macos/KRONOS.app' / relative
            assert source.read_bytes() == (control['bundle'] / relative).read_bytes()
        record_property('three_copied_resources_match_selected_git_source', True)
        record_property('authority', 'SYNTHETIC_PUBLICATION_SIGNATURE_AUTHORIZATION_SEAMS')
        record_property('actual_consumer_and_kernel_observations', True)
        record_property('parent_image_and_canonical_path', 'TEST_ONLY_SIMULATED_LAUNCHER; NOT_NATIVE_INTEGRATION')
        assert control['parent_image']['calls']
        assert all(row['pid'] == case.custody.parent and
                   row['value'] == control['canonical_image']
                   for row in control['parent_image']['calls'])
        record_property('git_object_format', object_format)
        record_property('original_budget_and_deadline_preserved', True)
        record_property('selected_parent_and_exact_claim_bindings_verified', True)
        record_property('historical_incident_cleanup_checkpoint_v2_bytes_preserved', True)
        record_property('claim_sha256', sha256(case.claim_path.read_bytes()).hexdigest())
    finally:
        case.close()
        record_property('fixture_custody_closed_in_test_teardown', case.custody.released)
        record_property('application_cleanup_claimed_from_test_teardown', False)


@pytest.mark.parametrize('finding',('valid','expired','wrong-mode','changed-decision',
                                   'source-bytes','artifact-bytes','target-digest','extra-field'))
def test_r33_native_selected_inputs_are_read_only(tmp_path,monkeypatch,record_property,finding):
    from datetime import timedelta
    from hashlib import sha256
    from kronos.common import failed_successor_restore as restore
    from tests.unit.common import test_failed_successor_restore as fixture
    control=_c02_dispatch_case(tmp_path,monkeypatch)
    case=control['case'];before_head=case.head_path.read_bytes()
    def reference(path,identity):
        raw=path.read_bytes();return dict(identity=identity,path=str(path),bytes=len(raw),sha256=sha256(raw).hexdigest())
    decisions={}
    for label in ('sponsor','ca','pcp','product'):
        path=case.root/(label+'-synthetic-decision.txt')
        path.write_bytes(('EXPLICIT SYNTHETIC FIXTURE ONLY: '+label).encode());path.chmod(0o600)
        decisions[label]=reference(path,label+'-fixture-decision')
    permit=json.loads(case.permit_path.read_bytes())
    value=dict(schema=b.NATIVE_SELECTION_SCHEMA,selection_id='native-selection-fixture',mode='ORDINARY',
        installation=permit['installation'],target=permit['restoration_target'],
        source_manifest=reference(control['source_manifest'],'source-fixture'),
        artifact_manifest=reference(control['artifact_manifest'],'artifact-fixture'),
        operational_order=decisions['sponsor'],decisions=decisions,permit=None,
        valid_from=(case.now-timedelta(seconds=30)).isoformat(),
        valid_until=(case.now+timedelta(minutes=4)).isoformat())
    if finding=='expired':value['valid_until']=(case.now-timedelta(seconds=1)).isoformat()
    if finding=='wrong-mode':value['mode']='LEGACY_BOOTSTRAP'
    if finding=='target-digest':value['target']=dict(value['target'],pinned_capture_sha256='0'*64)
    if finding=='extra-field':value['SPONSOR_APPROVED']=True
    selected=case.root/'native-selection.json';fixture._put(selected,value)
    selected_ref=reference(selected,value['selection_id'])
    if finding=='changed-decision':Path(decisions['ca']['path']).write_bytes(b'changed after external selection')
    if finding=='source-bytes':(control['repository']/'README.md').write_bytes(b'changed Git-backed source')
    if finding=='artifact-bytes':(control['bundle']/'Contents/Resources/KRONOS.png').write_bytes(b'changed copied resource')
    monkeypatch.setattr(b,'_verify_bundle_signature',lambda *_:None)
    def forbidden(*args,**kwargs):pytest.fail('native read-only validation consumed a child')
    monkeypatch.setattr(restore,'consume_failed_successor_restore',forbidden)
    try:
        def validate():
            return b._native_selection(selected_ref,case.custody,mode='ORDINARY',
                repository=str(control['repository']),bundle=str(control['bundle']),
                anchor=str(case.custody.binding.path),now=case.now)
        if finding=='valid':assert validate()[0]==value
        else:
            with pytest.raises((b.BootstrapError,restore.FailedSuccessorRestoreError)):validate()
        assert case.head_path.read_bytes()==before_head and not case.claim_path.exists()
        record_property('read_only_no_head_or_child_claim',True)
        record_property('authority','SYNTHETIC_SOURCE_SIGNATURE_AND_DECISION_INTEGRITY; NO_HUMAN_AUTHENTICATION_CLAIM')
    finally:case.close()


def _c03_consume(control, monkeypatch):
    case = control['case']
    monkeypatch.setattr(b, '_verify_bundle_signature', lambda *_: None)
    observation = _c02_capture(control)
    context = b.consume_startup_context(case.root, control['env'],
        revision=control['target']['revision'], source_state='CLEAN_COMMIT',
        repository=control['repository'], runtime_identity=case.child.runtime_identity,
        now=case.now, custody=case.custody, restoration_observation=observation,
        restoration_clock=lambda: case.now,
        **({'restoration_retain': True} if hasattr(b, 'retain_restoration_attempt') else {}))
    attempt = context if hasattr(b, 'retain_restoration_attempt') else None
    if attempt is not None:
        context = attempt.context
    return context, observation, attempt


@pytest.mark.parametrize('finding', (
    'handoff-rollback', 'handoff-rollback-to-claim', 'valid-increasing',
    'valid-equal', 'later-rollback'))
def test_c03_f01_consumer_utc_handoff(tmp_path, monkeypatch, record_property, finding):
    from datetime import timedelta
    from hashlib import sha256
    from kronos.common import failed_successor_restore as restore
    from kronos.common.release_admission import AdmissionCustody, ValidationBudget
    control = _c02_dispatch_case(tmp_path, monkeypatch)
    case = control['case']
    budget, deadline = case.custody.budget, case.custody.budget.deadline_ns
    assert type(case.custody) is AdmissionCustody
    assert type(budget) is ValidationBudget
    initial, claimed, consumer_final = (
        case.now, case.now + timedelta(seconds=1), case.now + timedelta(seconds=3))
    rollback = finding.startswith('handoff-rollback')
    handoff = claimed if finding == 'handoff-rollback-to-claim' else claimed + timedelta(seconds=1)
    retention_final = consumer_final if finding == 'valid-equal' else consumer_final + timedelta(seconds=2)
    values = [initial, claimed, consumer_final,
              handoff if rollback else consumer_final,
              handoff if rollback else retention_final]
    state = {'utc': values[-1], 'samples': [], 'consumer_returns': 0,
             'claim_writes': 0, 'retention_returned': False, 'recheck_returned': False}
    preserved = {path: path.read_bytes() for path in (
        case.incident_path, case.failure_path, case.settled_path,
        case.original_v2_path, case.retained_path, case.head_path,
        case.permit_path, case.reservation_path, control['source_manifest'],
        control['artifact_manifest'])}
    expected_checkpoint = json.loads(preserved[case.settled_path])['notification_checkpoint']
    real_consume, real_write = restore.consume_failed_successor_restore, restore._write_claim
    def clock():
        value = values[len(state['samples'])] if len(state['samples']) < len(values) else state['utc']
        state['samples'].append(value)
        return value
    def consume(*args, **kwargs):
        result = real_consume(*args, **kwargs)
        state['consumer_returns'] += 1
        assert state['samples'] == [initial, claimed, consumer_final]
        assert type(result) is restore.RestorationStartupContext
        return result
    def write(*args, **kwargs):
        state['claim_writes'] += 1
        return real_write(*args, **kwargs)
    evidence = (Path(__file__).resolve().parents[4] / 'qualification' /
                'c03-f01-handoff-evidence' / tmp_path.parents[1].name / tmp_path.name)
    evidence.mkdir(parents=True)
    try:
        monkeypatch.setattr(b, '_verify_bundle_signature', lambda *_: None)
        monkeypatch.setattr(restore, 'consume_failed_successor_restore', consume)
        monkeypatch.setattr(restore, '_write_claim', write)
        observation = _c02_capture(control)
        def dispatch():
            result = b.consume_startup_context(case.root, control['env'],
                revision=control['target']['revision'], source_state='CLEAN_COMMIT',
                repository=control['repository'], runtime_identity=case.child.runtime_identity,
                now=initial, custody=case.custody, restoration_observation=observation,
                restoration_clock=clock, restoration_retain=True)
            state['retention_returned'] = True
            return result
        if rollback:
            assert initial < claimed <= handoff < consumer_final
            with pytest.raises(b.BootstrapError, match='RESTORATION_RECHECK_REJECTED'):
                dispatch()
        else:
            attempt = dispatch()
            assert attempt.validated_at == retention_final
            assert attempt.claimed_at == claimed.isoformat()
            assert attempt.context.notification_checkpoint() == expected_checkpoint
            claim_before = case.claim_path.read_bytes()
            def recheck(previous):
                result = b.revalidate_restoration_context(control['env'],
                    context=previous.context, custody=case.custody,
                    child=observation.child, repository=control['repository'],
                    now=initial, attempt=previous, clock=clock)
                state['recheck_returned'] = True
                return result
            if finding == 'later-rollback':
                state['utc'] = consumer_final + timedelta(seconds=1)
                assert consumer_final <= state['utc'] < attempt.validated_at
                with pytest.raises(b.BootstrapError, match='RESTORATION_RECHECK_REJECTED'):
                    recheck(attempt)
            else:
                state['utc'] = consumer_final if finding == 'valid-equal' else retention_final + timedelta(seconds=1)
                latest = recheck(attempt)
                assert latest.validated_at == state['utc']
                state['utc'] = latest.validated_at if finding == 'valid-equal' else latest.validated_at + timedelta(seconds=1)
                latest = recheck(latest)
                assert latest.validated_at == state['utc']
                assert latest.claimed_at == claimed.isoformat()
                assert latest.context is attempt.context
                assert latest.observation is attempt.observation
                assert latest.selection is attempt.selection
                assert latest.custody is case.custody and latest.budget is budget
                assert latest.deadline_ns == deadline
                assert latest.head_reference == attempt.head_reference
                assert latest.claim_reference == attempt.claim_reference
            assert case.claim_path.read_bytes() == claim_before
        assert state['consumer_returns'] == state['claim_writes'] == 1
        claim = json.loads(case.claim_path.read_bytes())
        assert claim['claimed_at'] == claimed.isoformat()
        assert claim['parent'] == json.loads(preserved[case.reservation_path])['parent']
        assert claim['child']['pid'] == os.getpid()
        assert claim['permit_sha256'] == control['permit_selection'].sha256
        assert claim['reservation_sha256'] == control['reservation_selection'].sha256
        assert case.custody.budget is budget and budget.deadline_ns == deadline
        assert not case.custody.released
        assert all(path.read_bytes() == raw for path, raw in preserved.items())
        budget.check()
    finally:
        claim_raw = case.claim_path.read_bytes() if case.claim_path.exists() else b''
        (evidence / 'claim.json').write_bytes(claim_raw)
        details = {**state, 'utc': state['utc'].isoformat(),
            'samples': [value.isoformat() for value in state['samples']],
            'finding': finding, 'initial_utc': initial.isoformat(),
            'claim_utc': claimed.isoformat(), 'consumer_final_utc': consumer_final.isoformat(),
            'claim_exists': case.claim_path.exists(), 'claim_sha256': sha256(claim_raw).hexdigest(),
            'same_budget': case.custody.budget is budget,
            'original_deadline_ns': deadline, 'final_deadline_ns': budget.deadline_ns,
            'application_cleanup_claimed': False,
            'seams': 'CONTROLLED_UTC; SIMULATED_PARENT_IMAGE_PATH_SIGNATURE_AUTHORITY; REAL_CONSUMER_CUSTODY_BUDGET_CLAIM_AND_COMPARISONS; RECORDING_ONLY_CONSUMER_AND_CLAIM_WRAPPERS'}
        (evidence / 'observations.json').write_text(json.dumps(details, indent=2) + '\n')
        record_property('finding', finding)
        record_property('consumer_final_utc', consumer_final.isoformat())
        record_property('claim_utc', claimed.isoformat())
        record_property('retention_returned', state['retention_returned'])
        record_property('actual_consumer_returns', state['consumer_returns'])
        record_property('exclusive_claim_writes', state['claim_writes'])
        case.close()
        (evidence / 'test-teardown.json').write_text(json.dumps({
            'fixture_custody_closed': case.custody.released,
            'claim_deleted_or_repaired': False,
            'application_cleanup_claimed': False}, indent=2) + '\n')


@pytest.mark.parametrize('finding', (
    'valid', 'valid-reconciliation', 'utc-io', 'utc-custody', 'monotonic-custody',
    'rollback-io', 'source-document', 'artifact-document', 'source-bytes',
    'artifact-bytes', 'child-birth', 'parent-birth', 'head-valid-change',
    'claim-time', 'permit', 'reservation', 'incident', 'cleanup', 'settled',
    'source-selector'))
def test_c03_read_only_final_revalidation(tmp_path, monkeypatch, record_property, finding):
    from datetime import timedelta
    from hashlib import sha256
    from kronos.common import failed_successor_restore as restore
    from kronos.common import release_admission as admission
    control = _c02_dispatch_case(tmp_path, monkeypatch)
    case = control['case']
    context, observation, attempt = _c03_consume(control, monkeypatch)
    budget, deadline = case.custody.budget, case.custody.budget.deadline_ns
    claim_before, head_before = case.claim_path.read_bytes(), case.head_path.read_bytes()
    evidence = (Path(__file__).resolve().parents[4] / 'qualification' /
                'c03-revalidation-evidence' / tmp_path.parents[1].name / tmp_path.name)
    evidence.mkdir(parents=True)
    state = {'utc': case.now, 'mono': admission.monotonic_ns(), 'armed': False,
             'custody_fault_entered': False, 'returned': False}
    real_current, real_image = restore._current_document, case.custody.parent_image
    def current(path):
        result = real_current(path)
        if Path(path) == case.claim_path:
            if finding == 'utc-io': state['utc'] = case.now + timedelta(minutes=6)
            if finding == 'rollback-io': state['utc'] = case.now - timedelta(seconds=1)
            if finding in {'utc-custody', 'monotonic-custody'}: state['armed'] = True
        return result
    def image(pid):
        result = real_image(pid)
        if state['armed']:
            state['custody_fault_entered'] = True
            if finding == 'utc-custody': state['utc'] = case.now + timedelta(minutes=6)
            if finding == 'monotonic-custody': state['mono'] = deadline
        return result
    try:
        monkeypatch.setattr(restore, '_current_document', current)
        monkeypatch.setattr(admission, 'monotonic_ns', lambda: state['mono'])
        case.custody.parent_image = image
        if finding in {'source-document', 'artifact-document'}:
            path = control['source_manifest' if finding == 'source-document' else 'artifact_manifest']
            path.write_bytes(path.read_bytes() + b' ')
        elif finding == 'source-bytes':
            (control['repository'] / 'README.md').write_bytes(b'C03 changed source\n')
        elif finding == 'artifact-bytes':
            (control['bundle'] / 'Contents/Resources/KRONOS.png').write_bytes(b'C03 changed resource\n')
        elif finding in {'child-birth', 'parent-birth'}:
            real_observe = b._observe_process
            def observe(pid):
                value = real_observe(pid)
                if pid == (os.getpid() if finding == 'child-birth' else os.getppid()):
                    value = dict(value, kernel_birth='f' * 64)
                return value
            monkeypatch.setattr(b, '_observe_process', observe)
        elif finding == 'head-valid-change':
            doc = json.loads(head_before); doc['sequence'] += 1
            case.head_path.write_bytes(b._canonical(doc))
        elif finding == 'claim-time':
            doc = json.loads(claim_before)
            doc['claimed_at'] = (case.now - timedelta(seconds=1)).isoformat()
            case.claim_path.write_bytes(b._canonical(doc))
        elif finding in {'permit', 'reservation', 'incident', 'cleanup', 'settled'}:
            path = getattr(case, {'cleanup': 'failure_path'}.get(finding, finding + '_path'))
            path.write_bytes(path.read_bytes() + b' ')
        elif finding == 'source-selector':
            alias = case.root / 'same-bytes-different-source-selection.json'
            alias.write_bytes(control['source_manifest'].read_bytes()); alias.chmod(0o600)
            control['env']['KRONOS_RESTORATION_SOURCE_MANIFEST_PATH'] = str(alias)
        elif finding == 'valid-reconciliation':
            (case.root / 'legitimate-application-enqueue.json').write_bytes(b'{"new_record":true}\n')
        def recheck():
            options = dict(context=context, custody=case.custody, child=observation.child,
                           repository=control['repository'], now=case.now)
            if attempt is not None:
                options.update(attempt=attempt, clock=lambda: state['utc'])
            result = b.revalidate_restoration_context(control['env'], **options)
            state['returned'] = True
            return result
        if finding.startswith('valid'):
            assert recheck()
            assert case.claim_path.read_bytes() == claim_before
            assert case.head_path.read_bytes() == head_before
            if finding == 'valid-reconciliation':
                assert (case.root / 'legitimate-application-enqueue.json').read_bytes() == b'{"new_record":true}\n'
        else:
            with pytest.raises(b.BootstrapError, match='RESTORATION'):
                recheck()
        assert case.claim_path.is_file()
        assert case.custody.budget is budget and budget.deadline_ns == deadline
        if finding in {'utc-custody', 'monotonic-custody'}:
            assert state['custody_fault_entered']
    finally:
        (evidence / 'original-claim.json').write_bytes(claim_before)
        (evidence / 'current-claim.json').write_bytes(case.claim_path.read_bytes())
        (evidence / 'original-head.json').write_bytes(head_before)
        (evidence / 'current-head.json').write_bytes(case.head_path.read_bytes())
        details = dict(finding=finding, returned=state['returned'], utc=state['utc'].isoformat(),
            mono=state['mono'], original_deadline_ns=deadline, final_deadline_ns=budget.deadline_ns,
            same_original_budget=case.custody.budget is budget,
            custody_fault_entered=state['custody_fault_entered'], claim_exists=True,
            claim_sha256=sha256(case.claim_path.read_bytes()).hexdigest(),
            original_claim_sha256=sha256(claim_before).hexdigest(),
            application_cleanup_claimed=False,
            seams='DISPOSABLE_PARENT_IMAGE_SIGNATURE_AUTHORITY_CLOCK_AND_FAULT_OBSERVATIONS; REAL_CONSUMER_AND_VALIDATORS')
        (evidence / 'observations.json').write_text(json.dumps(details, indent=2) + '\n')
        record_property('finding', finding); record_property('revalidation_returned', state['returned'])
        case.close()
        (evidence / 'test-teardown.json').write_text(json.dumps({
            'fixture_custody_closed': case.custody.released, 'claim_deleted_or_repaired': False,
            'application_cleanup_claimed': False}, indent=2) + '\n')


@pytest.mark.parametrize('finding', (
    'mismatch-plist', 'mismatch-icns', 'mismatch-png',
    'missing-plist', 'missing-icns', 'missing-png'))
def test_c02_f03_copied_resource_binding_denies_before_claim(
        tmp_path, monkeypatch, record_property, finding):
    from hashlib import sha256
    resource = {'plist': 'Contents/Info.plist',
                'icns': 'Contents/Resources/KRONOS.icns',
                'png': 'Contents/Resources/KRONOS.png'}[finding.split('-')[1]]
    missing = finding.startswith('missing-')
    control = _c02_dispatch_case(tmp_path, monkeypatch,
                                missing_resource=resource if missing else None)
    case, env = control['case'], control['env']
    source_path = control['repository'] / 'tools/macos/KRONOS.app' / resource
    installed_path = control['bundle'] / resource
    before_source = source_path.read_bytes() if source_path.exists() else None
    before_installed = installed_path.read_bytes()
    source_document_bytes = control['source_manifest'].read_bytes()
    budget, deadline = case.custody.budget, case.custody.budget.deadline_ns
    evidence = (Path(__file__).resolve().parents[4] / 'qualification' /
                'f03-case-evidence' / tmp_path.parents[1].name / tmp_path.name)
    evidence.mkdir(parents=True)
    signature_calls, returned = [], False
    def signature(bundle, owner, identity):
        assert bundle == control['bundle'] and owner is case.custody
        signature_calls.append({'bundle': str(bundle), 'identity': identity})
    try:
        monkeypatch.setattr(b, '_verify_bundle_signature', signature)
        if not missing:
            if resource == 'Contents/Info.plist':
                original = plistlib.loads(before_installed)
                changed = dict(original, CFBundleDisplayName='F03 changed copied resource')
                for field in ('CFBundleIdentifier', 'CFBundleExecutable',
                              'CFBundlePackageType', 'CFBundleIconFile', 'LSMinimumSystemVersion'):
                    assert changed[field] == original[field]
                installed_path.write_bytes(plistlib.dumps(changed))
            else:
                installed_path.write_bytes(before_installed + b'\nF03 changed copied resource\n')
            assert installed_path.read_bytes() != before_source
        rows = _c02_bundle_manifest(control['bundle'])
        artifact = dict(control['artifact_document'], bundle_manifest=rows,
                        bundle_identity=sha256(b._canonical(rows)).hexdigest())
        control['artifact_manifest'].write_bytes(b._canonical(artifact) + b'\n')
        _c02_refresh(case, env, source_manifest=control['source_manifest'],
            artifact_manifest=control['artifact_manifest'], target_values=control['target'],
            parent_birth=env['KRONOS_RESTORATION_PARENT_KERNEL_BIRTH'])
        assert control['source_manifest'].read_bytes() == source_document_bytes
        assert _c02_run(control['repository'], '/usr/bin/git', 'rev-parse', 'HEAD') == control['target']['revision']
        assert _c02_run(control['repository'], '/usr/bin/git', 'status', '--porcelain=v1') == ''
        if missing:
            assert not source_path.exists()
            assert not any(row['path'] == 'tools/macos/KRONOS.app/' + resource
                           for row in control['source_document']['files'])
        else:
            assert source_path.read_bytes() == before_source
        with pytest.raises(b.BootstrapError, match='RESTORATION_ARTIFACT'):
            capture = _c02_capture(control)
            b.consume_startup_context(case.root, env,
                revision=control['target']['revision'], source_state='CLEAN_COMMIT',
                repository=control['repository'], runtime_identity=case.child.runtime_identity,
                now=case.now, custody=case.custody, restoration_observation=capture,
                restoration_clock=lambda: case.now)
            returned = True
        assert not case.claim_path.exists()
        assert case.custody.budget is budget and budget.deadline_ns == deadline
    finally:
        details = {'finding': finding, 'source_resource': 'tools/macos/KRONOS.app/' + resource,
            'installed_resource': resource, 'selected_revision': control['target']['revision'],
            'selected_git_tree_oid': control['source_document']['git_tree_oid'],
            'source_resource_missing': missing,
            'source_sha256': sha256(before_source).hexdigest() if before_source is not None else None,
            'installed_sha256': sha256(installed_path.read_bytes()).hexdigest(),
            'source_document_unchanged': control['source_manifest'].read_bytes() == source_document_bytes,
            'original_deadline_ns': deadline, 'final_deadline_ns': case.custody.budget.deadline_ns,
            'same_original_budget': case.custody.budget is budget,
            'consumer_context_returned': returned, 'claim_exists': case.claim_path.exists(),
            'signature_calls': signature_calls, 'parent_image_observations': control['parent_image'],
            'seams': 'TEST_ONLY_PARENT_IMAGE_PATH_SIGNATURE_PUBLICATION_AUTHORITY; NOT_NATIVE_INTEGRATION',
            'application_cleanup_claimed': False, 'application_composition_invoked': False}
        (evidence / 'observations.json').write_text(json.dumps(details, indent=2) + '\n')
        (evidence / 'installed-resource.bin').write_bytes(installed_path.read_bytes())
        (evidence / 'original-installed-resource.bin').write_bytes(before_installed)
        if before_source is not None:
            (evidence / 'selected-source-resource.bin').write_bytes(before_source)
        for name, path in {'source.json': control['source_manifest'],
                           'artifact.json': control['artifact_manifest'],
                           'permit.json': case.permit_path, 'reservation.json': case.reservation_path,
                           'head.json': case.head_path, 'incident.json': case.incident_path,
                           'failure.json': case.failure_path, 'settled.json': case.settled_path}.items():
            (evidence / name).write_bytes(path.read_bytes())
        if case.claim_path.exists():
            (evidence / 'spent-claim.json').write_bytes(case.claim_path.read_bytes())
        record_property('finding', finding)
        record_property('claim_exists', case.claim_path.exists())
        case.close()
        (evidence / 'test-teardown.json').write_text(json.dumps({
            'fixture_custody_closed': case.custody.released,
            'application_cleanup_claimed': False,
            'claim_deleted_or_repaired_by_application': False}, indent=2) + '\n')


@pytest.mark.parametrize('finding', (
    'different-bundle', 'missing-image', 'inconsistent-image', 'failed-image',
    'symlink-bundle', 'lexical-image-alias', 'signature-failure', 'custody-cleanup'))
def test_c02_f02_parent_bundle_binding_denies_before_claim(
        tmp_path, monkeypatch, record_property, finding):
    from hashlib import sha256
    import shutil
    from kronos.common import release_admission as admission
    control = _c02_dispatch_case(tmp_path, monkeypatch)
    case = control['case']
    budget, deadline = case.custody.budget, case.custody.budget.deadline_ns
    evidence = (Path(__file__).resolve().parents[4] / 'qualification' /
                'f02-case-evidence' / tmp_path.parents[1].name / tmp_path.name)
    evidence.mkdir(parents=True)
    signatures, returned = [], False
    observation = {'finding': finding, 'parent_image_and_path':
        'TEST_ONLY_SIMULATED_LAUNCHER; REAL_KERNEL_IMAGE_RECORDED_SEPARATELY',
        'signature': 'TEST_ONLY_RECORDING_SEAM; NO_SIGNING_OR_NATIVE_INTEGRATION',
        'selected_bundle': str(control['bundle']),
        'actual_birth_observations': control['observed'],
        'original_deadline_ns': deadline}
    def signature(bundle, owner, identity):
        assert owner is case.custody
        signatures.append({'bundle': str(bundle), 'identity': identity})
        if finding == 'signature-failure':
            raise OSError('F02_FIXTURE_SIGNATURE_VERIFICATION_FAILED')
    try:
        monkeypatch.setattr(b, '_verify_bundle_signature', signature)
        if finding == 'different-bundle':
            # B remains coherently selected in every existing document. A is a
            # distinct equally valid bundle at the simulated canonical parent
            # location. No permit/environment string supplies this observation.
            actual_bundle = case.root / 'actual-parent-KRONOS.app'
            shutil.copytree(control['bundle'], actual_bundle)
            canonical = str(actual_bundle / 'Contents/MacOS/KRONOS')
            monkeypatch.setattr(admission, 'CANONICAL_PARENT', canonical)
            control['parent_image']['value'] = canonical
            assert actual_bundle != control['bundle']
            assert _c02_bundle_manifest(actual_bundle) == control['artifact_document']['bundle_manifest']
        elif finding == 'missing-image':
            control['parent_image']['value'] = None
        elif finding == 'inconsistent-image':
            control['parent_image']['value'] = '/not/the/canonical/launcher'
        elif finding == 'failed-image':
            control['parent_image']['error'] = True
        elif finding == 'symlink-bundle':
            backing = case.root / 'bundle-backing.app'
            control['bundle'].rename(backing)
            control['bundle'].symlink_to(backing, target_is_directory=True)
        elif finding == 'lexical-image-alias':
            control['parent_image']['value'] = str(control['bundle']) + '/Contents/MacOS/../MacOS/KRONOS'
        elif finding == 'custody-cleanup':
            case.custody.cleanup_started = True
        selected = json.loads(case.permit_path.read_bytes())['installation']
        assert selected['bundle_path'] == str(control['bundle'])
        assert sha256(control['artifact_manifest'].read_bytes()).hexdigest() == \
            json.loads(case.permit_path.read_bytes())['restoration_target']['artifact_manifest_sha256']
        with pytest.raises(b.BootstrapError, match='RESTORATION'):
            capture = _c02_capture(control)
            b.consume_startup_context(case.root, control['env'],
                revision=control['target']['revision'], source_state='CLEAN_COMMIT',
                repository=control['repository'], runtime_identity=case.child.runtime_identity,
                now=case.now, custody=case.custody, restoration_observation=capture,
                restoration_clock=lambda: case.now)
            returned = True
        assert not case.claim_path.exists()
        assert case.custody.budget is budget and budget.deadline_ns == deadline
    finally:
        observation.update(canonical_parent_requirement=admission.CANONICAL_PARENT,
            parent_image_observations=control['parent_image'],
            signature_calls=signatures, consumer_context_returned=returned,
            claim_exists=case.claim_path.exists(), same_original_budget=case.custody.budget is budget,
            final_deadline_ns=case.custody.budget.deadline_ns,
            application_composition_invoked=False, application_cleanup_claimed=False)
        (evidence / 'observations.json').write_text(json.dumps(observation, indent=2) + '\n')
        for name, path in {'source.json': control['source_manifest'],
                           'artifact.json': control['artifact_manifest'],
                           'permit.json': case.permit_path, 'reservation.json': case.reservation_path,
                           'head.json': case.head_path, 'incident.json': case.incident_path,
                           'failure.json': case.failure_path, 'settled.json': case.settled_path}.items():
            (evidence / name).write_bytes(path.read_bytes())
        if case.claim_path.exists():
            (evidence / 'spent-claim.json').write_bytes(case.claim_path.read_bytes())
        record_property('finding', finding)
        record_property('claim_exists', case.claim_path.exists())
        record_property('native_integration_qualified', False)
        case.close()
        (evidence / 'test-teardown.json').write_text(json.dumps({
            'fixture_custody_closed': case.custody.released,
            'application_cleanup_claimed': False,
            'claim_deleted_or_repaired_by_application': False}, indent=2) + '\n')


@pytest.mark.parametrize('object_format', ('sha1', 'sha256'))
def test_c02_f01_git_content_disagreement_denied_before_claim(
        tmp_path, monkeypatch, record_property, object_format):
    """Coherent manifest/worktree agreement cannot replace selected Git bytes."""
    from hashlib import sha256
    control = _c02_dispatch_case(tmp_path, monkeypatch, object_format=object_format)
    case, env, repository = control['case'], control['env'], control['repository']
    evidence = (Path(__file__).resolve().parents[4] / 'qualification' /
                'f01-case-evidence' / tmp_path.parents[1].name / tmp_path.name)
    evidence.mkdir(parents=True)
    original_budget = case.custody.budget
    deadline = original_budget.deadline_ns
    observations = {'git_object_format': object_format,
        'authority_seams': 'SYNTHETIC_PUBLICATION_SIGNATURE_AUTHORIZATION_ONLY',
        'index_flag': 'git update-index --assume-unchanged -- README.md; DISPOSABLE_REPOSITORY_ONLY',
        'original_deadline_ns': deadline, 'actual_kernel_observations': control['observed']}
    try:
        monkeypatch.setattr(b, '_verify_bundle_signature',
                            lambda _bundle, _custody, _identity: None)
        revision = control['target']['revision']
        tree = control['source_document']['git_tree_oid']
        before = (repository / 'README.md').read_bytes()
        selected_blob = _c02_run(repository, '/usr/bin/git', 'ls-tree',
                                 revision, '--', 'README.md').split()[2]
        _c02_run(repository, '/usr/bin/git', 'update-index',
                  '--assume-unchanged', '--', 'README.md')
        changed = b'coherently selected working bytes outside the Git revision\n'
        (repository / 'README.md').write_bytes(changed)
        files = [dict(row) for row in control['source_document']['files']]
        next(row for row in files if row['path'] == 'README.md')['sha256'] = sha256(changed).hexdigest()
        document = dict(control['source_document'], files=files)
        control['source_manifest'].write_bytes(b._canonical(document))
        target = dict(control['target'], tree_sha256=sha256(b._canonical(files)).hexdigest())
        _c02_refresh(case, env, source_manifest=control['source_manifest'],
            artifact_manifest=control['artifact_manifest'], target_values=target,
            parent_birth=env['KRONOS_RESTORATION_PARENT_KERNEL_BIRTH'])
        assert _c02_run(repository, '/usr/bin/git', 'rev-parse', 'HEAD') == revision
        assert _c02_run(repository, '/usr/bin/git', 'rev-parse', 'HEAD^{tree}') == tree
        assert _c02_run(repository, '/usr/bin/git', 'status', '--porcelain=v1',
                         '--untracked-files=all') == ''
        actual_blob = _c02_run(repository, '/usr/bin/git', 'hash-object',
                               '--no-filters', '--', 'README.md')
        assert actual_blob != selected_blob
        assert next(row for row in document['files'] if row['path'] == 'README.md')['sha256'] \
            == sha256((repository / 'README.md').read_bytes()).hexdigest()
        observations.update(selected_revision=revision, selected_git_tree_oid=tree,
            selected_blob_oid=selected_blob, actual_working_blob_oid=actual_blob,
            original_raw_sha256=sha256(before).hexdigest(),
            working_raw_sha256=sha256(changed).hexdigest(),
            git_status_porcelain='', manifest_matches_changed_working_bytes=True,
            consumer_context_returned=False)
        with pytest.raises(b.BootstrapError, match='RESTORATION'):
            observation = _c02_capture(control)
            b.consume_startup_context(case.root, env,
                revision=revision, source_state='CLEAN_COMMIT', repository=repository,
                runtime_identity=case.child.runtime_identity, now=case.now,
                custody=case.custody, restoration_observation=observation,
                restoration_clock=lambda: case.now)
            observations['consumer_context_returned'] = True
        assert not case.claim_path.exists()
        assert case.custody.budget is original_budget
        assert original_budget.deadline_ns == deadline
    finally:
        observations.update(claim_exists=case.claim_path.exists(),
            same_original_budget=case.custody.budget is original_budget,
            final_deadline_ns=case.custody.budget.deadline_ns,
            application_composition_invoked=False,
            application_cleanup_claimed=False)
        (evidence / 'observations.json').write_text(json.dumps(observations, indent=2) + '\n')
        for name, path in {'selected-source.json': control['source_manifest'],
                           'selected-artifact.json': control['artifact_manifest'],
                           'permit.json': case.permit_path,
                           'reservation.json': case.reservation_path,
                           'head.json': case.head_path}.items():
            (evidence / name).write_bytes(path.read_bytes())
        if case.claim_path.exists():
            (evidence / 'spent-claim.json').write_bytes(case.claim_path.read_bytes())
        record_property('git_object_format', object_format)
        record_property('claim_exists', case.claim_path.exists())
        record_property('index_flag_disposable_only', observations['index_flag'])
        case.close()
        (evidence / 'test-teardown.json').write_text(json.dumps({
            'fixture_custody_closed': case.custody.released,
            'application_cleanup_claimed': False,
            'claim_deleted_or_repaired_by_application': False}, indent=2) + '\n')


def test_c02_f01_unsupported_git_object_format_denied_before_claim(
        tmp_path, monkeypatch):
    control = _c02_dispatch_case(tmp_path, monkeypatch)
    case = control['case']
    budget, deadline = case.custody.budget, case.custody.budget.deadline_ns
    try:
        monkeypatch.setattr(b, '_verify_bundle_signature',
                            lambda _bundle, _custody, _identity: None)
        # An actual disposable Git repository with an unsupported storage format
        # makes Git's format query fail. No content comparator or consumer stub.
        _c02_run(control['repository'], '/usr/bin/git', 'config',
                  'core.repositoryformatversion', '1')
        _c02_run(control['repository'], '/usr/bin/git', 'config',
                  'extensions.objectFormat', 'unsupported-f01')
        with pytest.raises(b.BootstrapError, match='RESTORATION_SOURCE_INVALID'):
            _c02_capture(control)
        assert not case.claim_path.exists()
        assert case.custody.budget is budget and budget.deadline_ns == deadline
    finally:
        case.close()


@pytest.mark.parametrize('object_format', ('sha1', 'sha256'))
def test_c02_f01_manifest_only_content_mismatch_denied_before_claim(
        tmp_path, monkeypatch, object_format):
    """Git and actual file agree; only the selected manifest hash is wrong."""
    control = _c02_dispatch_case(tmp_path, monkeypatch, object_format=object_format)
    case, env = control['case'], control['env']
    try:
        monkeypatch.setattr(b, '_verify_bundle_signature',
                            lambda _bundle, _custody, _identity: None)
        files = [dict(row) for row in control['source_document']['files']]
        next(row for row in files if row['path'] == 'README.md')['sha256'] = '0' * 64
        control['source_manifest'].write_bytes(b._canonical(
            dict(control['source_document'], files=files)))
        from hashlib import sha256
        target = dict(control['target'], tree_sha256=sha256(b._canonical(files)).hexdigest())
        _c02_refresh(case, env, source_manifest=control['source_manifest'],
            artifact_manifest=control['artifact_manifest'], target_values=target,
            parent_birth=env['KRONOS_RESTORATION_PARENT_KERNEL_BIRTH'])
        assert _c02_run(control['repository'], '/usr/bin/git', 'status',
                         '--porcelain=v1', '--untracked-files=all') == ''
        with pytest.raises(b.BootstrapError, match='RESTORATION_SOURCE_INVALID'):
            _c02_capture(control)
        assert not case.claim_path.exists()
    finally:
        case.close()


@pytest.mark.parametrize('finding', (
    'A-wrong-child-birth', 'A-wrong-parent-birth',
    'B-hashed-incompatible-documents', 'B-wrong-roster', 'B-wrong-source-bytes',
    'B-wrong-mode', 'B-wrong-revision-tree', 'B-wrong-capture',
    'B-wrong-bundle-identity', 'B-missing-capture-observation',
    'C-repository-mismatch'))
def test_c02_initial_identity_denials_before_actual_consumer_claim(
        tmp_path, monkeypatch, record_property, finding):
    """Every negative begins with the same coherent control and changes one fact."""
    control = _c02_dispatch_case(tmp_path, monkeypatch)
    case, env = control['case'], control['env']
    evidence = (Path(__file__).resolve().parents[4] / 'qualification' / 'c02-case-evidence'
                / tmp_path.parents[1].name / tmp_path.name)
    evidence.mkdir(parents=True)
    returned = False
    try:
        monkeypatch.setattr(b, '_verify_bundle_signature',
                            lambda _bundle, _custody, _identity: None)
        if finding == 'A-wrong-child-birth':
            env['KRONOS_RESTORATION_CHILD_KERNEL_BIRTH'] = '1' * 64
        elif finding == 'A-wrong-parent-birth':
            env['KRONOS_RESTORATION_PARENT_KERNEL_BIRTH'] = '2' * 64
        elif finding == 'B-hashed-incompatible-documents':
            document = dict(control['source_document'], origin_url='git@example.invalid:wrong/repository.git')
            control['source_manifest'].write_bytes(b._canonical(document))
            _c02_refresh(case, env, source_manifest=control['source_manifest'],
                artifact_manifest=control['artifact_manifest'], target_values=control['target'],
                parent_birth=env['KRONOS_RESTORATION_PARENT_KERNEL_BIRTH'])
        elif finding == 'B-wrong-roster':
            document = dict(control['source_document'], files=control['source_document']['files'][:-1])
            control['source_manifest'].write_bytes(b._canonical(document))
            _c02_refresh(case, env, source_manifest=control['source_manifest'],
                artifact_manifest=control['artifact_manifest'], target_values=control['target'],
                parent_birth=env['KRONOS_RESTORATION_PARENT_KERNEL_BIRTH'])
        elif finding == 'B-wrong-source-bytes':
            (control['repository'] / 'README.md').write_bytes(b'changed after publication\n')
        elif finding == 'B-wrong-mode':
            (control['repository'] / 'README.md').chmod(0o755)
        elif finding == 'B-wrong-revision-tree':
            document = dict(control['source_document'], git_tree_oid='0' * 40)
            control['source_manifest'].write_bytes(b._canonical(document))
            _c02_refresh(case, env, source_manifest=control['source_manifest'],
                artifact_manifest=control['artifact_manifest'], target_values=control['target'],
                parent_birth=env['KRONOS_RESTORATION_PARENT_KERNEL_BIRTH'])
        elif finding == 'B-wrong-capture':
            rows = [dict(row) for row in control['source_document']['capture']]
            rows[0]['sha256'] = '9' * 64
            document = dict(control['source_document'], capture=rows)
            control['source_manifest'].write_bytes(b._canonical(document))
            _c02_refresh(case, env, source_manifest=control['source_manifest'],
                artifact_manifest=control['artifact_manifest'], target_values=control['target'],
                parent_birth=env['KRONOS_RESTORATION_PARENT_KERNEL_BIRTH'])
        elif finding == 'B-wrong-bundle-identity':
            (control['bundle'] / 'Contents/MacOS/KRONOS').write_bytes(b'wrong installed bundle\n')
        elif finding == 'C-repository-mismatch':
            control['repository_override'] = case.root / 'different-repository'
        with pytest.raises(b.BootstrapError, match='RESTORATION'):
            observation = _c02_capture(control,
                repository=control.get('repository_override', control['repository']),
                captured_sources=(() if finding == 'B-missing-capture-observation'
                                  else control['captured_sources']))
            b.consume_startup_context(case.root, env,
                revision=control['target']['revision'], source_state='CLEAN_COMMIT',
                repository=control['repository'], runtime_identity=case.child.runtime_identity,
                now=case.now, custody=case.custody,
                restoration_observation=observation,
                restoration_clock=lambda: case.now)
            returned = True
        assert not case.claim_path.exists()
    finally:
        details = dict(finding=finding, actual_kernel_observations=control['observed'],
            consumer_context_returned=returned, claim_exists=case.claim_path.exists(),
            application_composition_invoked=False,
            synthetic_publication_signature_authorization_seams=True,
            original_deadline_ns=case.custody.budget.deadline_ns)
        (evidence / 'observations.json').write_text(json.dumps(details, indent=2) + '\n')
        if case.claim_path.exists():
            (evidence / 'spent-claim.json').write_bytes(case.claim_path.read_bytes())
        record_property('finding', finding)
        record_property('claim_exists', case.claim_path.exists())
        case.close()
        (evidence / 'test-teardown.json').write_text(json.dumps(dict(
            fixture_custody_closed=True, application_cleanup_claimed=False,
            spent_claim_deleted_or_repaired=False), indent=2) + '\n')


def test_v2_startup_context_is_version_distinct_and_one_use(tmp_path):
    from kronos.common.maintenance import publish_drain_handoff
    from kronos.common.connection_governance import ConnectionGovernanceError
    root = tmp_path / 'maintenance'
    generation = 'a' * 64
    drain = {name: 0 for name in (
        'coordinator_owners', 'wo11_owned', 'wo11_queued', 'wo17_owned',
        'wo17_queued', 'housekeeping_owned', 'bulk_owned',
        'notification_scheduled', 'monitoring_sessions', 'provider_owned',
        'provider_leases',
    )}
    drain['notification_checkpoint'] = {'state': 'EMPTY', 'pending_count': 0,
        'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}
    publish_drain_handoff(root, generation=generation, parent_pid=os.getpid(),
        proof='d' * 64, runtime_identity='e' * 64,
        loaded_revision='f' * 40, drain=drain, now=NOW)
    context = {'KRONOS_MAINTENANCE_PROTOCOL': 'V2',
        'KRONOS_MAINTENANCE_REVISION': 'f' * 40,
        'KRONOS_MAINTENANCE_GENERATION': generation,
        'KRONOS_MAINTENANCE_PARENT': str(os.getpid()),
        'KRONOS_MAINTENANCE_PROOF': 'd' * 64}
    with pytest.raises(ConnectionGovernanceError, match='DRAIN_HANDOFF_REJECTED'):
        b.consume_startup_context(tmp_path, dict(context), revision='c' * 40,
            source_state='CLEAN_COMMIT', repository='/governed/repository',
            runtime_identity='f' * 64, now=NOW)
    # The running pytest process is the signer, so a test-only distinct PID
    # proves the successor's one-use claim without launching a backend.
    from kronos.common.maintenance import consume_drain_handoff
    admitted = b.consume_startup_context(tmp_path, dict(context),
        revision='c' * 40, source_state='CLEAN_COMMIT',
        repository='/governed/repository', runtime_identity='f' * 64,
        now=NOW, process_id=os.getpid() + 1,
        predecessor_gone=lambda _pid: True, port_free=lambda: True)
    assert admitted.generation == generation
    assert admitted.notification_checkpoint() == drain['notification_checkpoint']
    with pytest.raises(ConnectionGovernanceError, match='DRAIN_HANDOFF_REJECTED'):
        consume_drain_handoff(root, dict(context), runtime_identity='f' * 64,
            now=NOW, process_id=os.getpid() + 2,
            loaded_revision='f' * 40,
            predecessor_gone=lambda _pid: True, port_free=lambda: True)


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


@pytest.mark.parametrize('raw,accepted', [
    (b'{"schema":"fixture","a":1}', True),
    (b'{ "a":1, "schema":"fixture" }', True),
    (b'{"a":1,"a":2}', False),
    (b'{"a":{"key":1,"key":2}}', False),
    (b'{"a":NaN}', False), (b'{"a":Infinity}', False),
    (b'[]', False), (b'{} trailing', False),
    (b'\xef\xbb\xbf{}', False), (b'{"a":"\xff"}', False),
])
def test_r33_native_runtime_observation_preserves_json_checks(raw,accepted):
    if accepted:
        assert b._native_runtime_observation(raw.hex()) == json.loads(raw)
    else:
        with pytest.raises(b.BootstrapError):b._native_runtime_observation(raw.hex())


@pytest.mark.parametrize('encoded', ['', 'a', '0g', 'AA', 2, None])
def test_r33_native_runtime_observation_rejects_invalid_transport(encoded):
    with pytest.raises(b.BootstrapError):b._native_runtime_observation(encoded)


def _e02_installed_control(tmp_path,monkeypatch,*,device_delta=0,anchor_path=None):
    """Coherent disposable activation; authority/signature are explicitly synthetic.

    device_delta is a simulated enrollment device observation, never an OS test.
    Kernel volume/file ID, opens, actual custody, budget and comparisons are real.
    """
    from hashlib import sha256
    from datetime import UTC,datetime,timedelta
    from kronos.common import release_admission as admission
    from tests.unit.common import test_failed_successor_restore as fixture
    from types import SimpleNamespace
    control=_c02_dispatch_case(tmp_path,monkeypatch);case=control['case']
    budget=case.custody.budget
    case.close()  # End unused restoration setup; E02 owns a separate installation.
    anchor=Path(anchor_path) if anchor_path is not None else case.root/'e02-anchor'
    anchor.mkdir(mode=0o700,parents=True)
    journal=anchor/'failed-successor-restore-v1';journal.mkdir(mode=0o700)
    st=anchor.stat()
    core=dict(anchor_path=str(anchor),device=st.st_dev+device_delta,inode=st.st_ino,owner=os.getuid(),
        bundle_id='com.project-kronos.browser-v1',bundle_path=str(control['bundle']),repository_path=str(control['repository']))
    installation=dict(identity=sha256(b._canonical(core)).hexdigest(),**core)
    enrollment=case.root/'e02-frozen-enrollment.json';raw=fixture._put(enrollment,installation)
    fd=os.open(anchor,os.O_RDONLY|os.O_DIRECTORY);fcntl=__import__('fcntl');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    observed=admission.descriptor_filesystem_identity(fd)
    persistent=dict(schema='KRONOS_PERSISTENT_ANCHOR_BINDING_V1',installation_identity=installation['identity'],
        enrollment=fixture._ref(enrollment,installation['identity'],raw),anchor_path=str(anchor),
        volume_uuid=observed['volume_uuid'],file_id=observed['file_id'],owner=os.getuid(),required_mode='0700',
        bundle_id=core['bundle_id'],bundle_path=core['bundle_path'],repository_path=core['repository_path'])
    binding=admission.AnchorBinding(anchor,core['device'],st.st_ino,os.getuid())
    monkeypatch.setattr(admission,'APPROVED_BINDING',binding)
    monkeypatch.setattr(admission,'PERSISTENT_ANCHOR_BINDING',b._canonical(persistent))
    owner=admission.AdmissionCustody(fd,binding,os.getppid(),budget=budget,parent_image=case.custody.parent_image)
    now=datetime.now(UTC)
    process=dict(pid=os.getpid(),kernel_birth=b._observe_process(os.getpid())['kernel_birth'],
        runtime_identity='a'*64,revision=control['target']['revision'])
    phase=b._native_phase('e02-fixture-genesis','NATIVE_ACTIVATED',original='e02-fixture-genesis',
        installation=installation,parent=process,selected=None,predecessor=None,previous=None,details={},now=now)
    raw=fixture._put(journal/(phase['identity']+'.json'),phase)
    head=dict(schema='KRONOS_RESTORATION_ADMISSION_HEAD_V1',installation_identity=installation['identity'],
        sequence=1,state='NATIVE_ACTIVATED',incident_id=None,active_reservation_id=phase['identity'],
        active_reservation_sha256=sha256(raw).hexdigest(),previous_head_sha256='0'*64,recorded_at=now.isoformat())
    fixture._put(journal/'head-1.json',head);fixture._put(journal/'admission-head.json',head)
    genesis=fixture._s304_admit_fixture(journal,installation)
    policy=dict(schema='ORDINARY_SAME_RELEASE_V1',scope='ORDINARY_SAME_RELEASE_WITH_QUALIFIED_STOP',
        installation_identity=installation['identity'],binding_sha256=sha256(b._canonical(persistent)).hexdigest(),
        genesis_disposition_sha256=sha256(genesis).hexdigest(),release_id='E02-SYNTHETIC-DISPOSABLE-RELEASE',
        installed_selection_path=str(anchor/'ordinary-start-v1/installed-selection.json'))
    monkeypatch.setattr(b,'ORDINARY_RESTART_POLICY',b._canonical(policy))
    decisions={}
    for label in ('sponsor','ca','pcp','product'):
        path=case.root/('e02-'+label+'.txt');path.write_bytes(('EXPLICIT SYNTHETIC '+label+'; NOT OPERATIONAL AUTHORITY').encode());path.chmod(0o600)
        decisions[label]=fixture._ref(path,'e02-'+label,path.read_bytes())
    permit=json.loads(case.permit_path.read_bytes())
    selected=dict(schema=b.NATIVE_SELECTION_SCHEMA,selection_id='e02-installed-selection',mode='ORDINARY',
        installation=installation,target=permit['restoration_target'],
        source_manifest=fixture._ref(control['source_manifest'],'e02-source',control['source_manifest'].read_bytes()),
        artifact_manifest=fixture._ref(control['artifact_manifest'],'e02-artifact',control['artifact_manifest'].read_bytes()),
        operational_order=decisions['sponsor'],decisions=decisions,permit=None,
        valid_from=(now-timedelta(seconds=30)).isoformat(),valid_until=(now+timedelta(minutes=8)).isoformat())
    monkeypatch.setattr(b,'_verify_bundle_signature',lambda *_:None)
    result=SimpleNamespace(**control,anchor=anchor,journal=journal,installation=installation,custody=owner,
        budget=budget,persistent=persistent,policy=policy,genesis=genesis,selection=selected,now=now,
        process=process,simulated_device_delta=device_delta)
    _e02_publish_control_activation(result)
    return result


def _e02_publish_control_activation(control):
    """Test-only controlled setup, called before any selected operation."""
    from hashlib import sha256
    from tests.unit.common import test_failed_successor_restore as fixture
    c=control;path=Path(c.policy['installed_selection_path']);raw=fixture._put(path,c.selection)
    selected=fixture._ref(path,c.selection['selection_id'],raw)
    activation=dict(schema=b.ORDINARY_ACTIVATION_SCHEMA,identity='e02-controlled-activation',
        policy_sha256=sha256(b._canonical(c.policy)).hexdigest(),installation_identity=c.installation['identity'],
        genesis_disposition_sha256=c.policy['genesis_disposition_sha256'],release_id=c.policy['release_id'],
        selection=selected,decisions=c.selection['decisions'],activated_at=c.now.isoformat())
    activation_path=path.with_name('activation.json');raw=fixture._put(activation_path,activation)
    ref=fixture._ref(activation_path,activation['identity'],raw)
    # One explicit activation after build, outside the source/artifact inventory.
    first=json.loads((c.journal/'head-1.json').read_bytes())
    first_record=c.journal/(first['active_reservation_id']+'.json')
    previous=fixture._ref(first_record,first['active_reservation_id'],first_record.read_bytes())
    phase=b._native_phase('e02-activation-phase','ORDINARY_ACTIVATED',original='e02-activation-phase',
        installation=c.installation,parent=c.process,selected=selected,predecessor=None,
        previous=previous,details=dict(activation=ref),now=c.now)
    raw=fixture._put(c.journal/(phase['identity']+'.json'),phase)
    head=dict(first,sequence=2,state=phase['phase'],active_reservation_id=phase['identity'],
        active_reservation_sha256=sha256(raw).hexdigest(),previous_head_sha256=sha256((c.journal/'head-1.json').read_bytes()).hexdigest())
    fixture._put(c.journal/'head-2.json',head);fixture._put(c.journal/'admission-head.json',head)
    c.selected_reference=selected;c.activation_reference=ref


@pytest.mark.parametrize('fault',('valid','default-disabled','wrong-policy','foreign-selection','changed-source',
    'changed-artifact','changed-volume','changed-file-id','changed-enrollment','missing-history'))
def test_e02_actual_installed_selection_and_source_denials(tmp_path,monkeypatch,record_property,fault):
    from kronos.common import release_admission as admission
    from hashlib import sha256
    c=_e02_installed_control(tmp_path,monkeypatch)
    initial={p.name:p.read_bytes() for p in c.journal.iterdir()}
    try:
        if fault=='default-disabled':monkeypatch.setattr(b,'ORDINARY_RESTART_POLICY',None)
        if fault=='wrong-policy':
            bad=dict(c.policy,release_id='foreign');monkeypatch.setattr(b,'ORDINARY_RESTART_POLICY',b._canonical(bad))
        if fault=='foreign-selection':
            bad=dict(c.selection,installation=dict(c.installation,identity='0'*64))
            Path(c.policy['installed_selection_path']).write_bytes(b._canonical(bad))
        if fault=='changed-source':(c.repository/'README.md').write_bytes(b'changed after controlled activation')
        if fault=='changed-artifact':(c.bundle/'Contents/Resources/KRONOS.png').write_bytes(b'changed copied artifact')
        if fault in {'changed-volume','changed-file-id'}:
            p=dict(c.persistent)
            p['volume_uuid']='00000000-0000-0000-0000-000000000001' if fault=='changed-volume' else p['volume_uuid']
            if fault=='changed-file-id':p['file_id']+=1
            monkeypatch.setattr(admission,'PERSISTENT_ANCHOR_BINDING',b._canonical(p))
        if fault=='changed-enrollment':Path(c.persistent['enrollment']['path']).write_bytes(b'corrupted frozen identity')
        if fault=='missing-history':(c.journal/'head-1.json').rename(c.case.root/'retained-removed-genesis.json')
        def check():return b._ordinary_activation(c.installation,c.custody,now=c.now)
        if fault=='valid':assert check()[0]==c.selection
        else:
            with pytest.raises((ValueError,OSError,KeyError)):check()
        assert not list(c.journal.glob('original-*')) and not list(c.journal.glob('*.child-claimed.json'))
        assert c.custody.budget is c.budget and not c.custody.released
        record_property('e02_application',json.dumps(dict(fault=fault,actual_custody=True,
            actual_git_artifact_comparisons=True,no_child=True,teardown_not_application=True)))
    finally:c.custody._close()


@pytest.mark.parametrize('device_delta',(0,-1))
def test_e02_frozen_identity_survives_accepted_device_observation(tmp_path,monkeypatch,record_property,device_delta):
    from kronos.common import release_admission as admission
    c=_e02_installed_control(tmp_path,monkeypatch,device_delta=device_delta)
    try:
        before={p.name:p.read_bytes() for p in c.journal.iterdir()}
        assert admission.frozen_installation(str(c.repository),str(c.bundle),str(c.anchor))==c.installation
        c.custody.check()
        assert b._ordinary_activation(c.installation,c.custody,now=c.now)[0]==c.selection
        assert {p.name:p.read_bytes() for p in c.journal.iterdir()}==before
        assert c.installation['device']+(-device_delta)==c.anchor.stat().st_dev
        record_property('e02_device_transition',json.dumps(dict(simulated_enrollment_device_delta=device_delta,
            real_fd_attributes=True,real_exclusion=True,actual_host_reboot=False,frozen_identity=c.installation['identity'])))
    finally:c.custody._close()
