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
