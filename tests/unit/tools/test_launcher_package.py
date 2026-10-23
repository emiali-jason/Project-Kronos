import json
import os
import plistlib
from pathlib import Path
import shutil
import subprocess

import pytest

from tools.macos import package_launcher as p

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    root=tmp_path_factory.mktemp('sealed-package')
    record=p.build(ROOT,root/'build')
    return root,root/'build/KRONOS.app',record


def test_strict_sealed_bundle_and_signed_execution(package):
    root,bundle,r=package
    assert p.verify(bundle,r['bundle_identity'])==r['bundle_identity']
    assert r['strict_verification']=='PASS' and r['isolated_execution']=='PASS'
    assert r['archive_sha256']==p.digest(root/'build/KRONOS-launcher.zip')
    assert r['signed_binary_sha256']==p.digest(bundle/p.BINARY)
    assert any(x['path']=='Contents/_CodeSignature/CodeResources' for x in r['bundle_manifest'])
    assert r['procedure_sha256']==p.digest(ROOT/'tools/macos/package_launcher.py')


def test_rebuild_identity_measured_not_assumed(package):
    root,bundle,a=package;b=p.build(ROOT,root/'second')
    assert a['source_launcher_sha256']==b['source_launcher_sha256']
    assert a['procedure_sha256']==b['procedure_sha256']
    assert a['compiler_flags']==b['compiler_flags']
    # The actual byte reproducibility result is evidence, not a weakened signature check.
    comparison={k:a[k]==b[k] for k in ('built_binary_sha256','signed_binary_sha256','bundle_identity','archive_sha256')}
    (root/'reproducibility.json').write_text(json.dumps(comparison))
    assert p.verify(root/'second/KRONOS.app',b['bundle_identity'])


@pytest.mark.parametrize('target', ['Contents/Info.plist','Contents/Resources/KRONOS.png',p.BINARY])
def test_tamper_rejected_before_install(package,tmp_path,target):
    _,bundle,r=package;bad=tmp_path/'bad.app';shutil.copytree(bundle,bad)
    with (bad/target).open('ab') as h:h.write(b'tamper')
    with pytest.raises(p.PackageError):p.verify(bad,r['bundle_identity'])


@pytest.mark.parametrize('violation', ['symlink','mode','missing-resource','extra-file'])
def test_structure_controls(package,tmp_path,violation):
    _,bundle,r=package;bad=tmp_path/'bad.app';shutil.copytree(bundle,bad)
    path=bad/'Contents/Resources/KRONOS.png'
    if violation=='symlink':path.unlink();path.symlink_to(bundle/'Contents/Resources/KRONOS.png')
    elif violation=='mode':path.chmod(0o666)
    elif violation=='missing-resource':path.unlink()
    else:(bad/'extra').write_text('not-approved')
    with pytest.raises(p.PackageError):p.verify(bad)


def installed_copy(bundle,tmp_path):
    target=tmp_path/'Installed.app';shutil.copytree(bundle,target)
    info=target/'Contents/Info.plist'; document=plistlib.loads(info.read_bytes())
    document['CFBundleVersion']='isolated-old-rollback-fixture'
    info.write_bytes(plistlib.dumps(document))
    p.run('/usr/bin/codesign','--force','--sign','-','--timestamp=none',str(target))
    assert p.verify(target)!=p.verify(bundle)
    return target


def test_atomic_install_retains_exact_rollback_and_never_launches(package,tmp_path):
    _,bundle,r=package;target=installed_copy(bundle,tmp_path);before=p.identity(target)
    result=p.install(bundle,target,candidate_identity=r['bundle_identity'],installed_identity=before,rollback=tmp_path/'rollback.app')
    assert result['launched'] is False
    assert p.verify(tmp_path/'rollback.app',before)==before
    assert p.verify(target,r['bundle_identity'])
    assert p.verify(Path(result['exchanged_original']),before)


def test_failed_initial_verification_keeps_installed_bytes(package,tmp_path):
    _,bundle,r=package;target=installed_copy(bundle,tmp_path);before=p.identity(target)
    with pytest.raises(p.PackageError):
        p.install(bundle,target,candidate_identity='0'*64,installed_identity=before,rollback=tmp_path/'rollback.app')
    assert p.identity(target)==before and not (tmp_path/'rollback.app').exists()


def test_failed_exchange_preserves_current_launcher(package,tmp_path):
    _,bundle,r=package;target=installed_copy(bundle,tmp_path);before=p.identity(target)
    def failure(*a):raise p.PackageError('INJECTED_EXCHANGE_FAILURE')
    with pytest.raises(p.PackageError):
        p.install(bundle,target,candidate_identity=r['bundle_identity'],installed_identity=before,
            rollback=tmp_path/'rollback.app',swap=failure)
    assert p.verify(target,before) and p.verify(tmp_path/'rollback.app',before)


def test_post_install_failure_atomically_rolls_back(package,tmp_path):
    _,bundle,r=package;target=installed_copy(bundle,tmp_path);before=p.identity(target);exchanges=[]
    def swap(a,b):exchanges.append(1);p.exchange(a,b)
    def verify(path,identity):
        if path==target and len(exchanges)==1:raise p.PackageError('INJECTED_POST_INSTALL_FAILURE')
        return p.verify(path,identity)
    with pytest.raises(p.PackageError,match='ROLLED_BACK'):
        p.install(bundle,target,candidate_identity=r['bundle_identity'],installed_identity=before,
            rollback=tmp_path/'rollback.app',swap=swap,verifier=verify)
    assert len(exchanges)==2 and p.verify(target,before)


@pytest.mark.parametrize('environment', [dict(KRONOS_LAUNCH_MODE='UNKNOWN'),
    dict(KRONOS_LAUNCH_MODE='LEGACY_BOOTSTRAP'),dict(KRONOS_LEGACY_BOOTSTRAP_ID='a'*64),
    dict(KRONOS_LAUNCH_MODE='LEGACY_BOOTSTRAP',KRONOS_LEGACY_BOOTSTRAP_ID='a'*64,
         KRONOS_LEGACY_BOOTSTRAP_PROOF='b'*64,KRONOS_MAINTENANCE_PARENT='39393')])
def test_launcher_rejects_invalid_mode_before_any_runtime_access(package,environment):
    _,bundle,r=package
    result=subprocess.run([str(bundle/p.BINARY)],env=environment,timeout=5,capture_output=True)
    assert result.returncode==1 and not result.stdout


def test_nested_install_paths_reject_before_any_copy(package,tmp_path):
    _,bundle,r=package;target=installed_copy(bundle,tmp_path);before=p.identity(target)
    with pytest.raises(p.PackageError,match='PATH_INVALID'):
        p.install(bundle,target,candidate_identity=r['bundle_identity'],installed_identity=before,rollback=target/'rollback.app')
    assert p.identity(target)==before


@pytest.mark.parametrize('value',[None,'','not-a-hash'])
def test_install_requires_independently_approved_identities(package,tmp_path,value):
    _,bundle,r=package;target=installed_copy(bundle,tmp_path);before=p.identity(target)
    with pytest.raises(p.PackageError,match='APPROVED_IDENTITIES'):
        p.install(bundle,target,candidate_identity=value,installed_identity=before,rollback=tmp_path/'rollback.app')
    assert p.identity(target)==before and not (tmp_path/'rollback.app').exists()


def test_bundle_root_permissions_are_verified(package,tmp_path):
    _,bundle,r=package;bad=tmp_path/'bad.app';shutil.copytree(bundle,bad);bad.chmod(0o777)
    with pytest.raises(p.PackageError,match='BUNDLE_OWNER_OR_MODE'):
        p.verify(bad,r['bundle_identity'])


def test_governed_verify_uses_same_seal_and_actual_shared_deadline(package):
    from kronos.common.failed_fenced_recovery import RecoveryBudget
    from tests.unit.common.test_failed_fenced_recovery import CLOCK
    import time
    _,bundle,record=package
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    budget=RecoveryBudget(CLOCK,now,now+15_000_000_000)
    assert p.verify(bundle,record['bundle_identity'],budget=budget)==record['bundle_identity']
    assert budget.origin_ns==now and budget.stop_deadline_ns==now+15_000_000_000


def test_governed_command_late_return_remains_joined_and_denied(tmp_path):
    from kronos.common.failed_fenced_recovery import RecoveryBudget
    from kronos.common.failed_fenced_startup import RecoveryStartupError
    from tests.unit.common.test_failed_fenced_recovery import CLOCK
    import sys,time
    completed=tmp_path/'actual-late-return'
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    budget=RecoveryBudget(CLOCK,now-14_990_000_000,now+10_000_000)
    program='import time,pathlib;time.sleep(.06);pathlib.Path('+repr(str(completed))+').write_text("returned")'
    with pytest.raises(RecoveryStartupError,match='HELPER_DEADLINE'):
        p.run(sys.executable,'-c',program,budget=budget)
    assert completed.read_text()=='returned'
    assert budget.stop_deadline_ns==now+10_000_000


@pytest.mark.parametrize('fault',[None,'missing-signature','wrong-manifest','ambiguous-artifact'])
def test_native_package_fact_uses_real_seal_and_exact_retained_artifacts(package,tmp_path,fault):
    """Actual package/syscalls; the prepared CA row is synthetic test authority."""
    import time
    from kronos.common import failed_fenced_recovery as core
    from kronos.common.failed_fenced_startup import capture_native_package_fact
    from tests.unit.common.test_failed_fenced_guard_history import slot_case
    from tests.unit.common.test_failed_fenced_recovery import private_store
    _,bundle,record=package
    store=private_store(tmp_path);case=slot_case(store,'c')
    registry=core.EvidenceRegistry(case.codec,store,case.prep.original)
    manifest=store.write_blob('native-manifest',p.canonical(p.manifest(bundle)))
    executable=store.write_blob('native-executable',(bundle/p.BINARY).read_bytes())
    signature=(bundle/'Contents/_CodeSignature/CodeResources').read_bytes()
    if fault!='missing-signature':store.write_blob('native-CodeResources',signature)
    row=dict(identity='synthetic-reviewed-package',purpose='ARTIFACT',authority='CA',
        bindings=dict(package=manifest,executable=executable))
    registry.preparation.rows[row['identity']]=row
    if fault=='wrong-manifest':row['bindings']['package']=store.write_blob('different-manifest',b'[]')
    elif fault=='ambiguous-artifact':registry.preparation.rows['other']=dict(row,identity='other')
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    budget=core.RecoveryBudget(case.codec.clock,now,now+15_000_000_000)
    before={str(path.relative_to(store.root)):path.read_bytes() for path in store.root.rglob('*') if path.is_file()}
    if fault:
        with pytest.raises(ValueError):capture_native_package_fact(registry,bundle,record['bundle_identity'],'INSTALLED',budget=budget)
    else:
        value=capture_native_package_fact(registry,bundle,record['bundle_identity'],'INSTALLED',budget=budget)
        assert value['signature']['hash']==__import__('hashlib').sha256(signature).hexdigest()
        assert value['manifest']==manifest and value['executable']==executable
        assert now<=int(value['verified_ns'])<budget.stop_deadline_ns
        assert 'mac' not in value and 'role' in value and value['role']=='INSTALLED'
    assert before=={str(path.relative_to(store.root)):path.read_bytes() for path in store.root.rglob('*') if path.is_file()}


def _retained_fixture(package,tmp_path,monkeypatch):
    from tools import runtime_source_gate
    from kronos.common.failed_fenced_recovery import RecoveryBudget
    from tests.unit.common.test_failed_fenced_recovery import CLOCK
    import time
    _,bundle,record=package
    applications=tmp_path/'Applications';applications.mkdir()
    target=installed_copy(bundle,applications);target.rename(applications/'KRONOS.app')
    target=applications/'KRONOS.app';old=p.identity(target)
    result=p.install(bundle,target,candidate_identity=record['bundle_identity'],installed_identity=old,
        rollback=tmp_path/'separate-rollback.app')
    monkeypatch.setattr(runtime_source_gate,'CANONICAL',target)
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    return target,Path(result['exchanged_original']),old,RecoveryBudget(CLOCK,now,now+15_000_000_000)


def test_retained_locator_uses_actual_installer_exchange_and_exact_approved_identity(package,tmp_path,monkeypatch):
    target,original,identity,budget=_retained_fixture(package,tmp_path,monkeypatch)
    before=p.identity(target)
    with p.retained_install_package({identity},budget=budget) as selected:
        assert selected==(original,identity)
        assert p.verify(selected[0],selected[1],budget=budget)==identity
    assert p.identity(target)==before and p.verify(original,identity)==identity


def test_retained_locator_never_selects_unapproved_or_arbitrary_rollback_path(package,tmp_path,monkeypatch):
    target,original,identity,budget=_retained_fixture(package,tmp_path,monkeypatch)
    with p.retained_install_package({'0'*64},budget=budget) as selected:
        assert selected is None
    original.rename(original.parent/'other.app')
    # A partial installer namespace cannot be silently treated as absence.
    with pytest.raises(p.PackageError,match='PATH_REJECTED'):
        with p.retained_install_package({identity},budget=budget):pass


@pytest.mark.parametrize('fault',['duplicate','stage-symlink','bundle-symlink','ancestor-symlink','stage-mode','file-hardlink'])
def test_retained_locator_rejects_ambiguous_or_unsafe_locations(package,tmp_path,monkeypatch,fault):
    from tools import runtime_source_gate
    target,original,identity,budget=_retained_fixture(package,tmp_path,monkeypatch)
    if fault=='duplicate':
        other=target.parent/'.kronos-install-duplicate';other.mkdir(mode=0o700)
        shutil.copytree(original,other/'KRONOS.app')
    elif fault=='stage-symlink':
        original.parent.rename(tmp_path/'moved-stage')
        original.parent.symlink_to(tmp_path/'moved-stage',target_is_directory=True)
    elif fault=='bundle-symlink':
        original.rename(tmp_path/'moved.app');original.symlink_to(tmp_path/'moved.app',target_is_directory=True)
    elif fault=='ancestor-symlink':
        link=tmp_path/'linked';link.symlink_to(target.parent,target_is_directory=True)
        monkeypatch.setattr(runtime_source_gate,'CANONICAL',link/'KRONOS.app')
    elif fault=='stage-mode':original.parent.chmod(0o755)
    else:os.link(original/'Contents/Info.plist',tmp_path/'info-link')
    with pytest.raises(p.PackageError,match='PACKAGE_RETAINED_'):
        with p.retained_install_package({identity},budget=budget):pass


@pytest.mark.parametrize('fault',['bundle-replacement','parent-replacement','file-change'])
def test_retained_locator_rechecks_named_inodes_and_native_bytes_after_consumer(package,tmp_path,monkeypatch,fault):
    target,original,identity,budget=_retained_fixture(package,tmp_path,monkeypatch)
    with pytest.raises(p.PackageError,match='PACKAGE_RETAINED_'):
        with p.retained_install_package({identity},budget=budget) as selected:
            assert selected==(original,identity)
            if fault=='bundle-replacement':
                original.rename(original.parent/'old.app');shutil.copytree(original.parent/'old.app',original)
            elif fault=='parent-replacement':
                original.parent.rename(tmp_path/'old-stage');original.parent.mkdir(mode=0o700)
                shutil.copytree(tmp_path/'old-stage/KRONOS.app',original)
            else:
                with (original/'Contents/Info.plist').open('ab') as handle:handle.write(b'changed')


@pytest.mark.parametrize('changed',[False,True])
def test_current_recovery_rechecks_native_package_after_original_fact_capture(package,tmp_path,monkeypatch,changed):
    """Actual installer/native package bytes; proof approval dispatch is a test leaf."""
    from kronos.common import failed_fenced_recovery as core
    from kronos.common.failed_fenced_startup import capture_native_package_fact,verify_current_package_facts
    from tests.unit.common.test_failed_fenced_guard_history import slot_case
    from tests.unit.common.test_failed_fenced_recovery import private_store
    target,original,identity,budget=_retained_fixture(package,tmp_path,monkeypatch)
    (tmp_path/'private').mkdir()
    store=private_store(tmp_path/'private');case=slot_case(store,'c')
    budget=core.RecoveryBudget(case.codec.clock,budget.origin_ns,budget.stop_deadline_ns)
    original_registry=core.EvidenceRegistry(case.codec,store,case.prep.original)
    payloads=[]
    for role,path in [('INSTALLED',target),('ROLLBACK',original)]:
        manifest=store.write_blob('native-'+role+'-manifest',p.canonical(p.manifest(path)))
        executable=store.retain_blob('native-'+role+'-executable',(path/p.BINARY).read_bytes())
        store.retain_blob('native-'+role+'-signature',(path/'Contents/_CodeSignature/CodeResources').read_bytes())
        row=dict(identity='synthetic-reviewed-'+role,purpose='ARTIFACT',authority='CA',bindings=dict(package=manifest,executable=executable))
        original_registry.preparation.rows[row['identity']]=row
        payloads.append(capture_native_package_fact(original_registry,path,manifest['hash'],role,budget=budget))
    original_registry.preparation.rows['operation']=dict(identity='operation',purpose='ORIGINAL_OPERATION',authority='SPONSOR',bindings={'operation_kind':'ORDINARY'})
    # Recovery uses the exact same prepared payloads, with no regenerated timestamp.
    registry=core.EvidenceRegistry(case.codec,store,case.prep)
    registry.preparation.original=original_registry.preparation
    timestamps=tuple(value['verified_ns'] for value in payloads)
    monkeypatch.setattr(registry,'verify_blob',lambda reference,kind:{'payload':payloads[reference]})
    if changed:
        with (original/'Contents/Info.plist').open('ab') as handle:handle.write(b'mutated-after-FACT')
        with pytest.raises(ValueError):verify_current_package_facts(registry,0,1,budget=budget)
    else:verify_current_package_facts(registry,0,1,budget=budget)
    assert timestamps==tuple(value['verified_ns'] for value in payloads)


@pytest.mark.parametrize('fault',[None,'oversize','symlink','replace-during-read','late-read'])
def test_governed_package_member_retains_exact_bounds_identity_and_deadline(package,tmp_path,monkeypatch,fault):
    from kronos.common.failed_fenced_recovery import RecoveryBudget,RecoveryError
    from tests.unit.common.test_failed_fenced_recovery import CLOCK
    import time,os
    _,source,_=package
    bundle=tmp_path/'native-copy.app';shutil.copytree(source,bundle)
    member=bundle/p.BINARY;expected=member.read_bytes()
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    budget=RecoveryBudget(CLOCK,now,now+15_000_000_000)
    if fault=='oversize':
        with member.open('ab') as stream:stream.write(b'oversize')
        monkeypatch.setattr(os,'read',lambda *_:pytest.fail('oversize member was read'))
    elif fault=='symlink':
        other=tmp_path/'other';member.rename(other);member.symlink_to(other)
    elif fault in {'replace-during-read','late-read'}:
        read=os.read;observed=[]
        def controlled(fd,length):
            raw=read(fd,length)
            if not observed:
                observed.append(True)
                if fault=='replace-during-read':
                    member.rename(member.with_name('previous'))
                    member.write_bytes(expected);member.chmod(0o755)
                else:
                    monkeypatch.setattr(time,'clock_gettime_ns',lambda _:now+15_000_000_000)
            return raw
        monkeypatch.setattr(os,'read',controlled)
    if fault:
        with pytest.raises((p.PackageError,RecoveryError)):
            p.read_governed_member(bundle,p.BINARY,expected,budget=budget)
    else:
        assert p.read_governed_member(bundle,p.BINARY,expected,budget=budget)==expected
    assert budget.origin_ns==now and budget.stop_deadline_ns==now+15_000_000_000


def test_governed_manifest_streams_source_without_unbounded_digest(package,monkeypatch):
    from kronos.common.failed_fenced_recovery import RecoveryBudget
    from tests.unit.common.test_failed_fenced_recovery import CLOCK
    import time
    _,bundle,_=package
    expected=p.manifest(bundle)
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    budget=RecoveryBudget(CLOCK,now,now+15_000_000_000)
    monkeypatch.setattr(p,'digest',lambda *_:pytest.fail('governed path called unbounded read_bytes'))
    assert p.manifest(bundle,budget=budget)==expected


@pytest.mark.parametrize('changed',['shared-ancestor-sibling','selected-install-parent','ancestor-mode'])
def test_retained_locator_distinguishes_shared_ancestor_activity_from_custody_change(package,tmp_path,monkeypatch,changed):
    target,original,identity,budget=_retained_fixture(package,tmp_path,monkeypatch)
    def consume():
        with p.retained_install_package({identity},budget=budget) as selected:
            assert selected==(original,identity)
            if changed=='shared-ancestor-sibling':(tmp_path/'unrelated-sibling').write_bytes(b'unrelated')
            elif changed=='selected-install-parent':(target.parent/'new-install-sibling').write_bytes(b'changed selection directory')
            else:tmp_path.chmod(p.stat.S_IMODE(tmp_path.stat().st_mode)^0o010)
    if changed=='shared-ancestor-sibling':consume()
    else:
        with pytest.raises(p.PackageError,match='PACKAGE_RETAINED_CHANGED'):consume()
